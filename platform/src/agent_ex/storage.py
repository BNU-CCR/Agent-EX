"""Per-run SQLite transaction storage for Paper 1 mock execution."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from .artifacts import ArtifactEnvelope
from .domain import (
    EventStatus,
    FrozenSchedule,
    GenerationAttempt,
    GenerationEvent,
    RunManifest,
    ScheduleSlot,
    _require_evidence_uri,
    _require_id,
    _require_int,
    _require_sha256,
    canonical_payload_hash,
    derive_event_id,
)
from .feed import FeedCursor
from .network import validate_shadow_artifact, validate_ws_artifact
from .state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost


_SCHEMA_VERSION = "paper1.run-storage.v2"
_SQLITE_USER_VERSION = 2


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _freeze_recovery_evidence(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_recovery_evidence(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_recovery_evidence(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_recovery_evidence(item) for item in value)
    return value


def _load_canonical_json(value: str, label: str) -> object:
    if type(value) is not str:
        raise ValueError(f"stored {label} JSON is not text")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"stored {label} JSON contains a duplicate key")
            result[key] = item
        return result

    try:
        payload = json.loads(value, object_pairs_hook=reject_duplicates)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"stored {label} JSON is invalid or contains a duplicate key") from error
    if value != _canonical_json(payload):
        raise ValueError(f"stored {label} JSON bytes are not canonical")
    return payload


def _validate_expected_agent_ids(value: object) -> tuple[str, ...]:
    if type(value) not in {tuple, list} or not value:
        raise ValueError("expected_agent_ids must be a non-empty tuple or list")
    values = tuple(value)
    for agent_id in values:
        _require_id("expected_agent_id", agent_id)
    if len(set(values)) != len(values):
        raise ValueError("expected_agent_ids must not contain duplicates")
    return tuple(sorted(values))


def _validate_expected_exposure(
    manifest: RunManifest,
    artifacts: Mapping[str, str],
    expected_population_size: int,
    mode: object,
    graph_hash: object,
    graph_artifact: ArtifactEnvelope | None,
    source_ws_artifact: ArtifactEnvelope | None,
) -> tuple[
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    cell_id = manifest.run_spec.get("cell_id")
    if type(cell_id) is not str:
        raise ValueError("manifest run_spec must contain canonical cell_id")
    parts = cell_id.split("-")
    if (
        len(parts) != 4
        or parts[0] != "P1"
        or parts[1] not in {"I0", "I1"}
        or parts[2] not in {"C0", "C1"}
        or parts[3] not in {"E0", "E1", "E2"}
    ):
        raise ValueError("manifest cell_id is not a canonical Paper 1 cell")
    expected_mode = {
        "E0": "self_history_only",
        "E1": "shuffled_social",
        "E2": "ws_neighbors",
    }[parts[3]]
    if mode != expected_mode:
        raise ValueError("expected exposure mode does not match manifest canonical cell")
    if expected_mode == "self_history_only":
        if graph_hash is not None or graph_artifact is not None or source_ws_artifact is not None:
            raise ValueError("self_history_only network artifacts and graph hash must be None")
        return expected_mode, None, None, None, None, None, None
    if not isinstance(graph_artifact, ArtifactEnvelope):
        raise TypeError("social exposure graph must be a typed ArtifactEnvelope")
    replayed_artifact = ArtifactEnvelope.from_payload(graph_artifact.to_payload())
    expected_artifact_type = {
        "shuffled_social": "paper1.mock_shadow_graph",
        "ws_neighbors": "paper1.mock_ws_graph",
    }[expected_mode]
    if replayed_artifact.artifact_type != expected_artifact_type:
        raise ValueError(f"exposure graph artifact type must be {expected_artifact_type}")
    _require_sha256("expected_exposure_graph_hash", graph_hash)
    if graph_hash != replayed_artifact.output_hash:
        raise ValueError("expected exposure graph hash does not match artifact output")
    if artifacts.get(replayed_artifact.artifact_id) != replayed_artifact.output_hash:
        raise ValueError("exposure graph artifact ID and output hash are not exactly bound")
    if expected_mode == "ws_neighbors":
        replayed_source = (
            replayed_artifact
            if source_ws_artifact is None
            else ArtifactEnvelope.from_payload(source_ws_artifact.to_payload())
        )
        if (
            replayed_source.artifact_id != replayed_artifact.artifact_id
            or replayed_source.output_hash != replayed_artifact.output_hash
        ):
            raise ValueError("E2 source WS must be the single exposure WS artifact")
        report = validate_ws_artifact(replayed_artifact)
    else:
        if not isinstance(source_ws_artifact, ArtifactEnvelope):
            raise TypeError("E1 exposure requires an explicit typed source WS artifact")
        replayed_source = ArtifactEnvelope.from_payload(source_ws_artifact.to_payload())
        validate_ws_artifact(replayed_source)
        report = validate_shadow_artifact(replayed_artifact, replayed_source)
    if artifacts.get(replayed_source.artifact_id) != replayed_source.output_hash:
        raise ValueError("source WS artifact ID and output hash are not exactly bound")
    for label, artifact in (("exposure graph", replayed_artifact), ("source WS", replayed_source)):
        if not isinstance(artifact.payload, Mapping):
            raise TypeError(f"{label} payload must be a mapping")
        if artifact.payload.get("matched_seed") != manifest.matched_seed:
            raise ValueError(f"{label} matched seed does not match run manifest")
    if report.get("node_count") != expected_population_size:
        raise ValueError("exposure graph node count does not match population roster")
    source_report = validate_ws_artifact(replayed_source)
    if source_report.get("node_count") != expected_population_size:
        raise ValueError("source WS node count does not match population roster")
    return (
        expected_mode,
        replayed_artifact.output_hash,
        replayed_artifact.artifact_id,
        replayed_artifact.artifact_type,
        replayed_source.output_hash,
        replayed_source.artifact_id,
        replayed_source.artifact_type,
    )


def _validate_artifact_hashes(value: Mapping[str, str]) -> dict[str, str]:
    if type(value) is not dict or not value:
        raise ValueError("artifact_hashes must be a non-empty plain mapping")
    normalized: dict[str, str] = {}
    for artifact_id, artifact_hash in value.items():
        _require_id("artifact_id", artifact_id)
        _require_sha256(f"artifact_hashes[{artifact_id}]", artifact_hash)
        normalized[artifact_id] = artifact_hash
    return normalized


def _replay_manifest(value: RunManifest) -> tuple[RunManifest, FrozenSchedule]:
    if not isinstance(value, RunManifest):
        raise TypeError("manifest must be a RunManifest")
    schedule = FrozenSchedule.from_payload(value.schedule.to_payload())
    manifest = RunManifest.from_payload(value.to_payload(), schedule=schedule)
    return manifest, schedule


@dataclass(frozen=True, slots=True)
class StorageBinding:
    schema_version: str
    run_id: str
    run_spec_hash: str
    manifest_hash: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    schedule_hash: str
    schedule_count: int
    artifact_hashes: Mapping[str, str]
    expected_agent_ids: tuple[str, ...]
    expected_agent_ids_hash: str
    expected_exposure_mode: str
    expected_exposure_graph_hash: str | None
    expected_exposure_graph_artifact_id: str | None
    expected_exposure_graph_artifact_type: str | None
    expected_source_ws_artifact_hash: str | None
    expected_source_ws_artifact_id: str | None
    expected_source_ws_artifact_type: str | None
    round0_root: str | None


@dataclass(frozen=True, slots=True)
class StorageProgress:
    next_event_ordinal: int
    expected_event_count: int
    succeeded_event_count: int
    event_chain_head: str


@dataclass(frozen=True, slots=True)
class ExternalResponseReference:
    uri: str
    sha256: str

    def __post_init__(self) -> None:
        _require_evidence_uri("external response uri", self.uri)
        _require_sha256("external response sha256", self.sha256)


def _validate_success_bundle(
    *,
    run_id: str,
    slot: ScheduleSlot,
    event: GenerationEvent,
    attempts: tuple[GenerationAttempt, ...],
    private_update: PrivateUpdate,
    private_state: PrivateState,
    previous_private_state: PrivateState,
    feed_cursor: FeedCursor,
    previous_feed_cursor: FeedCursor,
    public_post: PublicPost | None,
    latest_public_pointer: LatestPublicPointer | None,
    previous_latest_public_pointer: LatestPublicPointer,
) -> None:
    if (
        event.run_id != run_id
        or event.event_id != derive_event_id(run_id, slot.event_ordinal)
        or event.event_ordinal != slot.event_ordinal
        or event.sweep_index != slot.sweep_index
        or event.draw_index != slot.draw_index
        or event.agent_id != slot.agent_id
        or event.publish_flag is not slot.publish_flag
        or event.status is not EventStatus.SUCCEEDED
    ):
        raise ValueError("successful event does not match frozen schedule slot")
    if (
        not attempts
        or tuple(item.attempt_id for item in attempts) != event.attempt_ids
        or any(item.event_id != event.event_id for item in attempts)
        or any(item.exposure_id != event.exposure_id for item in attempts)
        or any(item.status is not EventStatus.FAILED for item in attempts[:-1])
        or attempts[-1].status is not EventStatus.SUCCEEDED
    ):
        raise ValueError("successful event attempt evidence is invalid")
    final_attempt = attempts[-1]
    if (
        private_update.event_id != event.event_id
        or private_update.event_ordinal != event.event_ordinal
        or private_update.agent_id != event.agent_id
        or private_update.source_attempt_id != final_attempt.attempt_id
        or private_update.published is not event.publish_flag
    ):
        raise ValueError("private update does not bind final successful attempt")
    parsed = final_attempt.parsed_response
    if parsed is None or (
        parsed.get("stance") != private_update.stance_label
        or parsed.get("confidence") != private_update.confidence
        or parsed.get("public_reason") != private_update.reason
    ):
        raise ValueError("private update content does not match final successful attempt")
    if private_state != PrivateState.from_update(
        private_update, previous=previous_private_state, mock_only=True
    ):
        raise ValueError("private state does not replay from successful private update")
    if feed_cursor != previous_feed_cursor.advance(event.event_ordinal):
        raise ValueError("feed cursor does not replay from successful event")
    if event.publish_flag:
        if public_post is None or latest_public_pointer is None:
            raise ValueError("published event lacks public post or latest pointer")
        if public_post != PublicPost.from_private_update(private_update, mock_only=True):
            raise ValueError("public post does not replay from successful private update")
        if latest_public_pointer != LatestPublicPointer.from_post(
            public_post, previous=previous_latest_public_pointer, mock_only=True
        ):
            raise ValueError("latest public pointer does not replay from successful post")
    elif public_post is not None or latest_public_pointer is not None:
        raise ValueError("unpublished event cannot mutate public state")


def _validate_provider_progression(previous: GenerationAttempt, current: GenerationAttempt) -> None:
    if (
        previous.provider_request_id is not None
        and current.provider_request_id != previous.provider_request_id
    ):
        raise ValueError("provider_request_id cannot change or clear after first observation")
    current_metadata = dict(current.provider_metadata)
    if any(
        key not in current_metadata or current_metadata[key] != value
        for key, value in previous.provider_metadata.items()
    ):
        raise ValueError("provider metadata may only add keys without changing prior evidence")


def _validate_attempt_transition_prefix(
    transitions: tuple[GenerationAttempt, ...],
) -> None:
    statuses = tuple(item.status for item in transitions)
    if statuses not in {
        (EventStatus.PENDING,),
        (EventStatus.PENDING, EventStatus.IN_PROGRESS),
        (EventStatus.PENDING, EventStatus.IN_PROGRESS, EventStatus.FAILED),
        (EventStatus.PENDING, EventStatus.IN_PROGRESS, EventStatus.SUCCEEDED),
    }:
        raise ValueError("attempt transition lifecycle is not a legal prefix")
    immutable_fields = (
        "attempt_id",
        "event_id",
        "attempt_index",
        "request_id",
        "exposure_id",
        "rendered_messages",
        "rendered_prompt_hash",
        "request_parameters",
        "request_parameters_hash",
        "model_identity",
        "model_identity_hash",
        "model_seed",
    )
    first = transitions[0]
    if any(
        getattr(item, name) != getattr(first, name)
        for item in transitions[1:]
        for name in immutable_fields
    ):
        raise ValueError("attempt transition immutable request evidence drifted")
    if first.started_at is not None or first.finished_at is not None:
        raise ValueError("PENDING transition cannot carry lifecycle timestamps")
    if len(transitions) >= 2 and transitions[1].finished_at is not None:
        raise ValueError("IN_PROGRESS transition cannot carry a finished timestamp")
    if len(transitions) == 3 and transitions[2].started_at != transitions[1].started_at:
        raise ValueError("terminal attempt started_at does not match IN_PROGRESS evidence")
    for previous, current in zip(transitions, transitions[1:]):
        _validate_provider_progression(previous, current)


class RunStorage:
    """Single-writer SQLite store bound to exactly one immutable run."""

    def __init__(
        self,
        path: Path,
        connection: sqlite3.Connection,
        schedule: FrozenSchedule,
        raw_response_resolver: Callable[[ExternalResponseReference], str] | None = None,
    ) -> None:
        self._path = path
        self._connection = connection
        self._schedule = schedule
        self._raw_response_resolver = raw_response_resolver
        self._binding = self._read_binding()

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        manifest: RunManifest,
        artifact_hashes: Mapping[str, str],
        expected_agent_ids: tuple[str, ...] | list[str],
        expected_exposure_mode: str,
        expected_exposure_graph_hash: str | None,
        expected_exposure_graph_artifact: ArtifactEnvelope | None = None,
        expected_source_ws_artifact: ArtifactEnvelope | None = None,
        raw_response_resolver: Callable[[ExternalResponseReference], str] | None = None,
    ) -> RunStorage:
        manifest, replayed_schedule = _replay_manifest(manifest)
        artifacts = _validate_artifact_hashes(artifact_hashes)
        roster = _validate_expected_agent_ids(expected_agent_ids)
        (
            exposure_mode,
            exposure_graph_hash,
            graph_artifact_id,
            graph_artifact_type,
            source_ws_hash,
            source_ws_id,
            source_ws_type,
        ) = _validate_expected_exposure(
            manifest,
            artifacts,
            len(roster),
            expected_exposure_mode,
            expected_exposure_graph_hash,
            expected_exposure_graph_artifact,
            expected_source_ws_artifact,
        )
        if len(roster) != replayed_schedule.population_size:
            raise ValueError("expected population roster cardinality does not match schedule")
        if any(slot.agent_id not in roster for slot in replayed_schedule.slots):
            raise ValueError("frozen schedule contains an agent outside expected population roster")
        roster_payload = list(roster)
        roster_hash = canonical_payload_hash(roster_payload)
        database = Path(path)
        if database.exists():
            raise FileExistsError(f"run database already exists: {database}")
        connection = sqlite3.connect(database, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA user_version = {_SQLITE_USER_VERSION}")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE binding (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    run_spec_hash TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL,
                    protocol_id TEXT NOT NULL,
                    protocol_version TEXT NOT NULL,
                    protocol_hash TEXT NOT NULL,
                    schedule_hash TEXT NOT NULL,
                    schedule_count INTEGER NOT NULL,
                    artifact_hashes_json TEXT NOT NULL,
                    expected_agent_ids_json TEXT NOT NULL,
                    expected_agent_ids_hash TEXT NOT NULL,
                    expected_exposure_mode TEXT NOT NULL,
                    expected_exposure_graph_hash TEXT,
                    expected_exposure_graph_artifact_id TEXT,
                    expected_exposure_graph_artifact_type TEXT,
                    expected_source_ws_artifact_hash TEXT,
                    expected_source_ws_artifact_id TEXT,
                    expected_source_ws_artifact_type TEXT,
                    round0_root TEXT,
                    schedule_payload_json TEXT NOT NULL,
                    manifest_payload_json TEXT NOT NULL
                );
                CREATE TABLE progress (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    next_event_ordinal INTEGER NOT NULL,
                    expected_event_count INTEGER NOT NULL,
                    succeeded_event_count INTEGER NOT NULL,
                    event_chain_head TEXT NOT NULL
                );
                CREATE TABLE attempts (
                    attempt_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    attempt_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    raw_response_uri TEXT,
                    raw_response_hash TEXT,
                    UNIQUE (event_id, attempt_index)
                );
                CREATE TABLE attempt_transitions (
                    attempt_id TEXT NOT NULL,
                    transition_index INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    attempt_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    raw_response_uri TEXT,
                    raw_response_hash TEXT,
                    PRIMARY KEY (attempt_id, transition_index),
                    UNIQUE (attempt_id, status)
                );
                CREATE INDEX idx_attempt_transitions_event
                    ON attempt_transitions(event_id, attempt_index, transition_index);
                CREATE TABLE events (
                    event_ordinal INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE private_updates (
                    update_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    event_ordinal INTEGER,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    UNIQUE (event_ordinal)
                );
                CREATE INDEX idx_private_updates_event
                    ON private_updates(event_ordinal);
                CREATE TABLE private_states (
                    agent_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE public_posts (
                    post_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    event_ordinal INTEGER,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    UNIQUE (event_ordinal)
                );
                CREATE INDEX idx_public_posts_event
                    ON public_posts(event_ordinal);
                CREATE INDEX idx_public_posts_agent_event
                    ON public_posts(agent_id, event_ordinal);
                CREATE TABLE latest_public_pointers (
                    agent_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE feed_cursors (
                    agent_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE initial_feed_cursors (
                    agent_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                COMMIT;
                """
            )
            manifest_payload = manifest.to_payload()
            genesis = canonical_payload_hash(
                {
                    "schema_version": _SCHEMA_VERSION,
                    "run_id": manifest.run_id,
                    "run_spec_hash": manifest.run_spec_hash,
                    "protocol_hash": manifest.protocol_hash,
                    "schedule_hash": manifest.schedule_hash,
                    "artifact_hashes": artifacts,
                    "expected_agent_ids_hash": roster_hash,
                    "expected_exposure_mode": exposure_mode,
                    "expected_exposure_graph_hash": exposure_graph_hash,
                    "expected_exposure_graph_artifact_id": graph_artifact_id,
                    "expected_exposure_graph_artifact_type": graph_artifact_type,
                    "expected_source_ws_artifact_hash": source_ws_hash,
                    "expected_source_ws_artifact_id": source_ws_id,
                    "expected_source_ws_artifact_type": source_ws_type,
                    "round0_root": None,
                }
            )
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO binding VALUES
                   (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _SCHEMA_VERSION,
                    manifest.run_id,
                    manifest.run_spec_hash,
                    canonical_payload_hash(manifest_payload),
                    manifest.protocol_id,
                    manifest.protocol_version,
                    manifest.protocol_hash,
                    manifest.schedule_hash,
                    manifest.schedule.count,
                    _canonical_json(artifacts),
                    _canonical_json(roster_payload),
                    roster_hash,
                    exposure_mode,
                    exposure_graph_hash,
                    graph_artifact_id,
                    graph_artifact_type,
                    source_ws_hash,
                    source_ws_id,
                    source_ws_type,
                    None,
                    _canonical_json(manifest.schedule.to_payload()),
                    _canonical_json(manifest_payload),
                ),
            )
            connection.execute(
                "INSERT INTO progress VALUES (1, 0, ?, 0, ?)",
                (manifest.schedule.count, genesis),
            )
            connection.commit()
            return cls(
                database,
                connection,
                replayed_schedule,
                raw_response_resolver=raw_response_resolver,
            )
        except BaseException:
            connection.rollback()
            connection.close()
            raise

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        manifest: RunManifest,
        artifact_hashes: Mapping[str, str],
        expected_agent_ids: tuple[str, ...] | list[str],
        expected_exposure_mode: str,
        expected_exposure_graph_hash: str | None,
        expected_exposure_graph_artifact: ArtifactEnvelope | None = None,
        expected_source_ws_artifact: ArtifactEnvelope | None = None,
        raw_response_resolver: Callable[[ExternalResponseReference], str] | None = None,
    ) -> RunStorage:
        manifest, replayed_schedule = _replay_manifest(manifest)
        artifacts = _validate_artifact_hashes(artifact_hashes)
        roster = _validate_expected_agent_ids(expected_agent_ids)
        (
            exposure_mode,
            exposure_graph_hash,
            graph_artifact_id,
            graph_artifact_type,
            source_ws_hash,
            source_ws_id,
            source_ws_type,
        ) = _validate_expected_exposure(
            manifest,
            artifacts,
            len(roster),
            expected_exposure_mode,
            expected_exposure_graph_hash,
            expected_exposure_graph_artifact,
            expected_source_ws_artifact,
        )
        if len(roster) != replayed_schedule.population_size:
            raise ValueError("expected population roster cardinality does not match schedule")
        if any(slot.agent_id not in roster for slot in replayed_schedule.slots):
            raise ValueError("frozen schedule contains an agent outside expected population roster")
        database = Path(path)
        if not database.is_file():
            raise FileNotFoundError(f"run database does not exist: {database}")
        database_uri = database.resolve().as_uri() + "?mode=rw"
        connection = sqlite3.connect(database_uri, isolation_level=None, uri=True)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            if connection.execute("PRAGMA user_version").fetchone()[0] != _SQLITE_USER_VERSION:
                raise ValueError("storage schema version is unsupported")
            store = cls(
                database,
                connection,
                replayed_schedule,
                raw_response_resolver=raw_response_resolver,
            )
            expected = {
                "run_id": manifest.run_id,
                "run_spec_hash": manifest.run_spec_hash,
                "manifest_hash": canonical_payload_hash(manifest.to_payload()),
                "protocol_id": manifest.protocol_id,
                "protocol_version": manifest.protocol_version,
                "protocol_hash": manifest.protocol_hash,
                "schedule_hash": manifest.schedule_hash,
                "schedule_count": manifest.schedule.count,
                "artifact_hashes": artifacts,
                "expected_agent_ids": roster,
                "expected_agent_ids_hash": canonical_payload_hash(list(roster)),
                "expected_exposure_mode": exposure_mode,
                "expected_exposure_graph_hash": exposure_graph_hash,
                "expected_exposure_graph_artifact_id": graph_artifact_id,
                "expected_exposure_graph_artifact_type": graph_artifact_type,
                "expected_source_ws_artifact_hash": source_ws_hash,
                "expected_source_ws_artifact_id": source_ws_id,
                "expected_source_ws_artifact_type": source_ws_type,
            }
            actual = store.binding
            if actual.schema_version != _SCHEMA_VERSION:
                raise ValueError("stored schema version does not match")
            for name, value in expected.items():
                observed = (
                    dict(actual.artifact_hashes)
                    if name == "artifact_hashes"
                    else getattr(actual, name)
                )
                if observed != value:
                    raise ValueError(f"stored {name.replace('_', ' ')} binding does not match")
            store.verify_integrity()
            return store
        except BaseException:
            connection.close()
            raise

    def _read_binding(self) -> StorageBinding:
        row = self._connection.execute(
            """SELECT schema_version, run_id, run_spec_hash, manifest_hash,
                      protocol_id, protocol_version, protocol_hash, schedule_hash,
                      schedule_count, artifact_hashes_json, expected_agent_ids_json,
                      expected_agent_ids_hash, expected_exposure_mode,
                      expected_exposure_graph_hash, expected_exposure_graph_artifact_id,
                      expected_exposure_graph_artifact_type,
                      expected_source_ws_artifact_hash, expected_source_ws_artifact_id,
                      expected_source_ws_artifact_type, round0_root
               FROM binding WHERE singleton = 1"""
        ).fetchone()
        if row is None:
            raise ValueError("storage binding is missing")
        artifacts = _load_canonical_json(row[9], "artifact hashes")
        roster_payload = _load_canonical_json(row[10], "expected agent IDs")
        roster = _validate_expected_agent_ids(roster_payload)
        if canonical_payload_hash(list(roster)) != row[11]:
            raise ValueError("stored expected agent IDs hash does not match roster")
        if row[19] is not None:
            _require_sha256("round0_root", row[19])
        return StorageBinding(
            schema_version=row[0],
            run_id=row[1],
            run_spec_hash=row[2],
            manifest_hash=row[3],
            protocol_id=row[4],
            protocol_version=row[5],
            protocol_hash=row[6],
            schedule_hash=row[7],
            schedule_count=row[8],
            artifact_hashes=MappingProxyType(artifacts),
            expected_agent_ids=roster,
            expected_agent_ids_hash=row[11],
            expected_exposure_mode=row[12],
            expected_exposure_graph_hash=row[13],
            expected_exposure_graph_artifact_id=row[14],
            expected_exposure_graph_artifact_type=row[15],
            expected_source_ws_artifact_hash=row[16],
            expected_source_ws_artifact_id=row[17],
            expected_source_ws_artifact_type=row[18],
            round0_root=row[19],
        )

    @property
    def binding(self) -> StorageBinding:
        return self._binding

    @property
    def progress(self) -> StorageProgress:
        row = self._connection.execute(
            """SELECT next_event_ordinal, expected_event_count,
                      succeeded_event_count, event_chain_head
               FROM progress WHERE singleton = 1"""
        ).fetchone()
        if row is None:
            raise ValueError("storage progress is missing")
        return StorageProgress(*row)

    def append_attempt(
        self,
        attempt: GenerationAttempt,
        *,
        external_response: ExternalResponseReference | None = None,
    ) -> None:
        if self.binding.round0_root is None:
            raise ValueError("initial state must be sealed before appending attempts")
        if not isinstance(attempt, GenerationAttempt):
            raise TypeError("attempt must be a GenerationAttempt")
        replayed = GenerationAttempt.from_payload(attempt.to_payload())
        if external_response is not None:
            if not isinstance(external_response, ExternalResponseReference):
                raise TypeError("external_response must be an ExternalResponseReference")
            if (
                replayed.raw_response is None
                or replayed.raw_response_hash != external_response.sha256
            ):
                raise ValueError("external response URI and hash must bind the raw response")
        progress = self.progress
        ordinal = progress.next_event_ordinal
        if not 0 <= ordinal < min(progress.expected_event_count, self._schedule.count):
            raise ValueError("run is complete or next ordinal is outside the frozen schedule")
        expected_event_id = derive_event_id(self.binding.run_id, ordinal)
        if replayed.event_id != expected_event_id:
            raise ValueError("attempt run or next event identity does not match storage")
        if self._connection.execute(
            "SELECT 1 FROM attempts WHERE event_id = ? AND status = ?",
            (replayed.event_id, EventStatus.SUCCEEDED.value),
        ).fetchone():
            raise ValueError("terminal success forbids further attempt transitions")
        transition_rows = self._connection.execute(
            """SELECT status, payload_json FROM attempt_transitions
               WHERE attempt_id = ? ORDER BY transition_index""",
            (replayed.attempt_id,),
        ).fetchall()
        if not transition_rows:
            maximum = self._connection.execute(
                """SELECT COALESCE(MAX(attempt_index), 0) FROM attempt_transitions
                   WHERE event_id = ?""",
                (replayed.event_id,),
            ).fetchone()[0]
            expected_index = maximum + 1
            if replayed.attempt_index != expected_index:
                if replayed.attempt_index < expected_index:
                    raise ValueError("attempt records are append-only")
                raise ValueError("attempt index must be continuous within an event")
            if replayed.status is not EventStatus.PENDING:
                raise ValueError("attempt lifecycle must begin with PENDING")
            if expected_index > 1:
                previous = self._connection.execute(
                    """SELECT status FROM attempts
                       WHERE event_id = ? AND attempt_index = ?""",
                    (replayed.event_id, expected_index - 1),
                ).fetchone()
                if previous is None or previous[0] != EventStatus.FAILED.value:
                    raise ValueError(
                        "next attempt requires the prior attempt to be terminal FAILED"
                    )
            transition_index = 1
        else:
            statuses = tuple(row[0] for row in transition_rows)
            if statuses == (EventStatus.PENDING.value,):
                if replayed.status is not EventStatus.IN_PROGRESS:
                    raise ValueError("attempt transition must be PENDING then IN_PROGRESS")
            elif statuses == (
                EventStatus.PENDING.value,
                EventStatus.IN_PROGRESS.value,
            ):
                if replayed.status not in {EventStatus.FAILED, EventStatus.SUCCEEDED}:
                    raise ValueError("attempt transition must end in FAILED or SUCCEEDED")
                in_progress_payload = _load_canonical_json(
                    transition_rows[1][1], "attempt transition"
                )
                if replayed.started_at != in_progress_payload["started_at"]:
                    raise ValueError(
                        "terminal attempt started_at must equal IN_PROGRESS started_at"
                    )
            else:
                raise ValueError("terminal attempt transition cannot be overwritten")
            first_payload = _load_canonical_json(transition_rows[0][1], "attempt transition")
            current_payload = replayed.to_payload()
            immutable_fields = (
                "attempt_id",
                "event_id",
                "attempt_index",
                "request_id",
                "exposure_id",
                "rendered_messages",
                "rendered_prompt_hash",
                "request_parameters",
                "request_parameters_hash",
                "model_identity",
                "model_identity_hash",
                "model_seed",
            )
            if any(first_payload[name] != current_payload[name] for name in immutable_fields):
                raise ValueError("attempt transition immutable request evidence drifted")
            previous_attempt = GenerationAttempt.from_payload(
                _load_canonical_json(transition_rows[-1][1], "attempt transition")  # type: ignore[arg-type]
            )
            _validate_provider_progression(previous_attempt, replayed)
            transition_index = len(transition_rows) + 1
        full_payload = replayed.to_payload()
        payload = dict(full_payload)
        if external_response is not None:
            payload["raw_response"] = None
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """INSERT INTO attempt_transitions
                   (attempt_id, transition_index, event_id, attempt_index, status,
                    payload_json, payload_hash, raw_response_uri, raw_response_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    replayed.attempt_id,
                    transition_index,
                    replayed.event_id,
                    replayed.attempt_index,
                    replayed.status.value,
                    _canonical_json(payload),
                    canonical_payload_hash(full_payload),
                    None if external_response is None else external_response.uri,
                    None if external_response is None else external_response.sha256,
                ),
            )
            if replayed.status not in {EventStatus.FAILED, EventStatus.SUCCEEDED}:
                self._connection.commit()
                return
            self._connection.execute(
                """INSERT INTO attempts
                   (attempt_id, event_id, attempt_index, status, payload_json, payload_hash,
                    raw_response_uri, raw_response_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    replayed.attempt_id,
                    replayed.event_id,
                    replayed.attempt_index,
                    replayed.status.value,
                    _canonical_json(payload),
                    canonical_payload_hash(full_payload),
                    None if external_response is None else external_response.uri,
                    None if external_response is None else external_response.sha256,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            raise ValueError("attempt records are append-only") from error
        except BaseException:
            self._connection.rollback()
            raise

    def attempt_transitions(self, attempt_id: str) -> tuple[GenerationAttempt, ...]:
        transitions, _ = self._attempt_transition_chain_entries(attempt_id)
        return transitions

    def _attempt_transition_chain_entries(
        self,
        attempt_id: str,
        *,
        external_raw_responses: Mapping[str, str] | None = None,
    ) -> tuple[tuple[GenerationAttempt, ...], list[dict[str, object]]]:
        _require_id("attempt_id", attempt_id)
        rows = self._connection.execute(
            """SELECT attempt_id, event_id, attempt_index, transition_index, status,
                      payload_json, payload_hash, raw_response_uri, raw_response_hash
               FROM attempt_transitions WHERE attempt_id = ? ORDER BY transition_index""",
            (attempt_id,),
        ).fetchall()
        if tuple(row[3] for row in rows) != tuple(range(1, len(rows) + 1)):
            raise ValueError("attempt transition index envelope has a gap")
        replayed = tuple(
            self._replay_attempt_payload(
                row[5],
                row[6],
                row[7],
                row[8],
                attempt_id=attempt_id,
                external_raw_responses=external_raw_responses,
            )
            for row in rows
        )
        if any(
            row[0] != attempt_id
            or row[0] != item.attempt_id
            or row[1] != item.event_id
            or row[2] != item.attempt_index
            or row[4] != item.status.value
            for row, item in zip(rows, replayed)
        ):
            raise ValueError("attempt transition row envelope does not match typed payload")
        _validate_attempt_transition_prefix(replayed)
        entries = [
            {
                "transition": item.to_payload(),
                "row_envelope": {
                    "attempt_id": row[0],
                    "event_id": row[1],
                    "attempt_index": row[2],
                    "transition_index": row[3],
                    "status": row[4],
                    "payload_hash": row[6],
                    "raw_response_uri": row[7],
                    "raw_response_hash": row[8],
                },
            }
            for row, item in zip(rows, replayed)
        ]
        return replayed, entries

    def initialize_agent(
        self,
        private_update: PrivateUpdate,
        private_state: PrivateState,
        public_post: PublicPost,
        latest_public_pointer: LatestPublicPointer,
        feed_cursor: FeedCursor,
    ) -> None:
        if self.binding.round0_root is not None:
            raise ValueError("initial state is already sealed")
        values = (private_update, private_state, public_post, latest_public_pointer, feed_cursor)
        expected_types = (
            PrivateUpdate,
            PrivateState,
            PublicPost,
            LatestPublicPointer,
            FeedCursor,
        )
        if any(not isinstance(value, expected) for value, expected in zip(values, expected_types)):
            raise TypeError("initial state requires typed private, public, and cursor records")
        replayed_update = PrivateUpdate.from_payload(private_update.to_payload())
        replayed_state = PrivateState.from_payload(private_state.to_payload())
        replayed_post = PublicPost.from_payload(public_post.to_payload())
        replayed_pointer = LatestPublicPointer.from_payload(latest_public_pointer.to_payload())
        replayed_cursor = FeedCursor.from_payload(feed_cursor.to_payload())
        agent_id = replayed_update.agent_id
        if agent_id not in self.binding.expected_agent_ids:
            raise ValueError("initial agent is outside expected population roster")
        if (
            replayed_update.event_ordinal is not None
            or replayed_state.event_ordinal is not None
            or replayed_post.published_event_ordinal is not None
            or replayed_pointer.published_event_ordinal is not None
            or replayed_cursor.last_scanned_event_ordinal is not None
        ):
            raise ValueError("agent initialization requires round-0 records")
        if any(
            candidate != agent_id
            for candidate in (
                replayed_state.agent_id,
                replayed_post.author_agent_id,
                replayed_pointer.agent_id,
                replayed_cursor.receiver_agent_id,
            )
        ):
            raise ValueError("initial records must bind the same agent")
        if replayed_state != PrivateState.from_update(
            replayed_update, previous=None, mock_only=True
        ):
            raise ValueError("initial private state does not replay from update")
        if replayed_post != PublicPost.from_private_update(replayed_update, mock_only=True):
            raise ValueError("initial public post does not replay from update")
        if replayed_pointer != LatestPublicPointer.from_post(
            replayed_post, previous=None, mock_only=True
        ):
            raise ValueError("initial latest public pointer does not replay from post")
        run_seed = self._manifest_matched_seed()
        if any(
            value != run_seed
            for value in (
                replayed_update.matched_seed,
                replayed_state.matched_seed,
                replayed_post.matched_seed,
                replayed_pointer.matched_seed,
                replayed_cursor.matched_seed,
            )
        ):
            raise ValueError("initial records do not match run seed")
        if (
            replayed_cursor.exposure_mode != self.binding.expected_exposure_mode
            or replayed_cursor.exposure_graph_hash != self.binding.expected_exposure_graph_hash
        ):
            raise ValueError("initial feed cursor exposure provenance does not match run binding")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._insert_payload(
                "private_updates",
                ("update_id", "agent_id", "event_ordinal"),
                (replayed_update.update_id, agent_id, None),
                replayed_update.to_payload(),
            )
            self._insert_current("private_states", agent_id, replayed_state.to_payload())
            self._insert_payload(
                "public_posts",
                ("post_id", "agent_id", "event_ordinal"),
                (replayed_post.post_id, agent_id, None),
                replayed_post.to_payload(),
            )
            self._insert_current("latest_public_pointers", agent_id, replayed_pointer.to_payload())
            self._insert_current("feed_cursors", agent_id, replayed_cursor.to_payload())
            self._insert_current("initial_feed_cursors", agent_id, replayed_cursor.to_payload())
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            raise ValueError("agent initial state is append-only") from error
        except BaseException:
            self._connection.rollback()
            raise

    def _event_chain_genesis(self, round0_root: str | None) -> str:
        return canonical_payload_hash(
            {
                "schema_version": _SCHEMA_VERSION,
                "run_id": self.binding.run_id,
                "run_spec_hash": self.binding.run_spec_hash,
                "protocol_hash": self.binding.protocol_hash,
                "schedule_hash": self.binding.schedule_hash,
                "artifact_hashes": dict(self.binding.artifact_hashes),
                "expected_agent_ids_hash": self.binding.expected_agent_ids_hash,
                "expected_exposure_mode": self.binding.expected_exposure_mode,
                "expected_exposure_graph_hash": self.binding.expected_exposure_graph_hash,
                "expected_exposure_graph_artifact_id": (
                    self.binding.expected_exposure_graph_artifact_id
                ),
                "expected_exposure_graph_artifact_type": (
                    self.binding.expected_exposure_graph_artifact_type
                ),
                "expected_source_ws_artifact_hash": (self.binding.expected_source_ws_artifact_hash),
                "expected_source_ws_artifact_id": self.binding.expected_source_ws_artifact_id,
                "expected_source_ws_artifact_type": (self.binding.expected_source_ws_artifact_type),
                "round0_root": round0_root,
            }
        )

    def _round0_entries(self, *, require_exact: bool) -> list[dict[str, object]]:
        roster = self.binding.expected_agent_ids
        table_agents = tuple(
            {row[0] for row in self._connection.execute(f"SELECT agent_id FROM {table}").fetchall()}
            for table in (
                "private_states",
                "latest_public_pointers",
                "feed_cursors",
                "initial_feed_cursors",
            )
        )
        update_agents = {
            row[0]
            for row in self._connection.execute(
                "SELECT agent_id FROM private_updates WHERE event_ordinal IS NULL"
            ).fetchall()
        }
        post_agents = {
            row[0]
            for row in self._connection.execute(
                "SELECT agent_id FROM public_posts WHERE event_ordinal IS NULL"
            ).fetchall()
        }
        expected = set(roster)
        observed_sets = (*table_agents, update_agents, post_agents)
        if require_exact and any(values != expected for values in observed_sets):
            raise ValueError("round-0 evidence does not exact-cover expected population roster")
        if any(not values.issubset(expected) for values in observed_sets):
            raise ValueError("round-0 evidence contains an agent outside expected roster")
        initialized = set.intersection(*observed_sets)
        entries: list[dict[str, object]] = []
        topic_binding: tuple[str, str] | None = None
        run_seed = self._manifest_matched_seed()
        for agent_id in sorted(initialized):
            update_row = self._connection.execute(
                """SELECT update_id, agent_id, payload_json, payload_hash
                   FROM private_updates WHERE event_ordinal IS NULL AND agent_id = ?""",
                (agent_id,),
            ).fetchone()
            post_row = self._connection.execute(
                """SELECT post_id, agent_id, payload_json, payload_hash
                   FROM public_posts WHERE event_ordinal IS NULL AND agent_id = ?""",
                (agent_id,),
            ).fetchone()
            if update_row is None or post_row is None:
                raise ValueError("round-0 append-only evidence is incomplete")
            update_payload = _load_canonical_json(update_row[2], "round-0 private update")
            post_payload = _load_canonical_json(post_row[2], "round-0 public post")
            if canonical_payload_hash(update_payload) != update_row[3]:
                raise ValueError("round-0 private update hash does not match")
            if canonical_payload_hash(post_payload) != post_row[3]:
                raise ValueError("round-0 public post hash does not match")
            update = PrivateUpdate.from_payload(update_payload)  # type: ignore[arg-type]
            post = PublicPost.from_payload(post_payload)  # type: ignore[arg-type]
            state = self._read_typed_current("private_states", agent_id, PrivateState)
            pointer = self._read_typed_current(
                "latest_public_pointers", agent_id, LatestPublicPointer
            )
            cursor = self._read_typed_current("feed_cursors", agent_id, FeedCursor)
            initial_cursor = self._read_typed_current("initial_feed_cursors", agent_id, FeedCursor)
            if not (
                isinstance(state, PrivateState)
                and isinstance(pointer, LatestPublicPointer)
                and isinstance(cursor, FeedCursor)
                and isinstance(initial_cursor, FeedCursor)
            ):
                raise ValueError("round-0 current evidence is incomplete")
            initial_state = PrivateState.from_update(update, previous=None, mock_only=True)
            initial_pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
            if (
                update_row[0] != update.update_id
                or update_row[1] != update.agent_id
                or post_row[0] != post.post_id
                or post_row[1] != post.author_agent_id
                or update.agent_id != agent_id
                or update.matched_seed != run_seed
                or post != PublicPost.from_private_update(update, mock_only=True)
                or initial_cursor.exposure_mode != self.binding.expected_exposure_mode
                or initial_cursor.exposure_graph_hash != self.binding.expected_exposure_graph_hash
            ):
                raise ValueError("round-0 bundle provenance does not replay")
            if self.progress.next_event_ordinal == 0 and (
                state != initial_state or pointer != initial_pointer or cursor != initial_cursor
            ):
                raise ValueError("round-0 current state does not match initial evidence")
            current_topic = (update.topic_package_id, update.topic_package_hash)
            if topic_binding is None:
                topic_binding = current_topic
            elif current_topic != topic_binding:
                raise ValueError("round-0 topic provenance is inconsistent across roster")
            entries.append(
                {
                    "agent_id": agent_id,
                    "private_update": update.to_payload(),
                    "private_state": initial_state.to_payload(),
                    "public_post": post.to_payload(),
                    "latest_public_pointer": initial_pointer.to_payload(),
                    "feed_cursor": initial_cursor.to_payload(),
                    "initial_feed_cursor": initial_cursor.to_payload(),
                }
            )
        return entries

    def seal_initial_state(self) -> str:
        if self.binding.round0_root is not None:
            raise ValueError("initial state is already sealed")
        if self._connection.execute("SELECT 1 FROM attempt_transitions LIMIT 1").fetchone():
            raise ValueError("cannot seal initial state after attempt evidence")
        entries = self._round0_entries(require_exact=True)
        round0_root = canonical_payload_hash(entries)
        genesis = self._event_chain_genesis(round0_root)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                "UPDATE binding SET round0_root = ? WHERE singleton = 1 AND round0_root IS NULL",
                (round0_root,),
            )
            self._connection.execute(
                "UPDATE progress SET event_chain_head = ? WHERE singleton = 1",
                (genesis,),
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        self._binding = self._read_binding()
        return round0_root

    def commit_success(
        self,
        event: GenerationEvent,
        *,
        final_attempt: GenerationAttempt,
        private_update: PrivateUpdate,
        private_state: PrivateState,
        feed_cursor: FeedCursor,
        public_post: PublicPost | None,
        latest_public_pointer: LatestPublicPointer | None,
    ) -> None:
        records = (event, final_attempt, private_update, private_state, feed_cursor)
        types = (GenerationEvent, GenerationAttempt, PrivateUpdate, PrivateState, FeedCursor)
        if any(not isinstance(value, expected) for value, expected in zip(records, types)):
            raise TypeError("success commit requires typed event, attempt, and state records")
        replayed_event = GenerationEvent.from_payload(event.to_payload())
        replayed_attempt = GenerationAttempt.from_payload(final_attempt.to_payload())
        replayed_update = PrivateUpdate.from_payload(private_update.to_payload())
        replayed_state = PrivateState.from_payload(private_state.to_payload())
        replayed_cursor = FeedCursor.from_payload(feed_cursor.to_payload())
        ordinal = self.progress.next_event_ordinal
        if replayed_event.run_id != self.binding.run_id:
            raise ValueError("event run does not match storage")
        if replayed_event.event_ordinal != ordinal:
            raise ValueError("event must be the continuous next ordinal")
        slot_record = self.schedule_slot(ordinal)
        slot = (
            slot_record.sweep_index,
            slot_record.draw_index,
            slot_record.agent_id,
            slot_record.publish_flag,
        )
        if (
            replayed_event.sweep_index != slot[0]
            or replayed_event.draw_index != slot[1]
            or replayed_event.agent_id != slot[2]
            or replayed_event.publish_flag is not slot[3]
        ):
            raise ValueError("event does not match its frozen schedule slot")
        if replayed_event.status is not EventStatus.SUCCEEDED:
            raise ValueError("success commit requires a succeeded event")
        raw_response_inputs = (
            None
            if replayed_attempt.raw_response is None
            else {replayed_attempt.attempt_id: replayed_attempt.raw_response}
        )
        attempts = self.attempts_for_event(
            replayed_event.event_id, external_raw_responses=raw_response_inputs
        )
        if (
            not attempts
            or attempts[-1] != replayed_attempt
            or replayed_attempt.status is not EventStatus.SUCCEEDED
            or any(item.status is not EventStatus.FAILED for item in attempts[:-1])
            or tuple(item.attempt_id for item in attempts) != replayed_event.attempt_ids
        ):
            raise ValueError("event final-success attempt evidence does not match")
        if any(item.exposure_id != replayed_event.exposure_id for item in attempts):
            raise ValueError("every attempt must bind the event exposure_id")
        if (
            replayed_update.event_id != replayed_event.event_id
            or replayed_update.event_ordinal != ordinal
            or replayed_update.agent_id != replayed_event.agent_id
            or replayed_update.source_attempt_id != replayed_attempt.attempt_id
            or replayed_update.published is not replayed_event.publish_flag
        ):
            raise ValueError("private update does not bind the successful event")
        parsed = replayed_attempt.parsed_response
        if parsed is None or (
            parsed.get("stance") != replayed_update.stance_label
            or parsed.get("confidence") != replayed_update.confidence
            or parsed.get("public_reason") != replayed_update.reason
        ):
            raise ValueError("private update content does not match final attempt")
        previous_state = self.private_state(replayed_event.agent_id)
        previous_cursor = self.feed_cursor(replayed_event.agent_id)
        if previous_state is None or previous_cursor is None:
            raise ValueError("agent round-0 state must exist before event commit")
        if replayed_state != PrivateState.from_update(
            replayed_update, previous=previous_state, mock_only=True
        ):
            raise ValueError("private state does not replay from successful update")
        if replayed_cursor != previous_cursor.advance(ordinal):
            raise ValueError("feed cursor does not strictly advance with the event")
        previous_pointer = self.latest_public_pointer(replayed_event.agent_id)
        if previous_pointer is None:
            raise ValueError("agent round-0 latest public pointer must exist")
        if replayed_event.publish_flag:
            if not isinstance(public_post, PublicPost) or not isinstance(
                latest_public_pointer, LatestPublicPointer
            ):
                raise ValueError("published event requires public post and latest pointer")
            replayed_post = PublicPost.from_payload(public_post.to_payload())
            replayed_pointer = LatestPublicPointer.from_payload(latest_public_pointer.to_payload())
            if replayed_post != PublicPost.from_private_update(replayed_update, mock_only=True):
                raise ValueError("public post does not replay from private update")
            if replayed_pointer != LatestPublicPointer.from_post(
                replayed_post, previous=previous_pointer, mock_only=True
            ):
                raise ValueError("latest public pointer does not replay from public post")
        else:
            if public_post is not None or latest_public_pointer is not None:
                raise ValueError("unpublished event cannot mutate public state")
            replayed_post = None
            replayed_pointer = None
        _validate_success_bundle(
            run_id=self.binding.run_id,
            slot=slot_record,
            event=replayed_event,
            attempts=attempts,
            private_update=replayed_update,
            private_state=replayed_state,
            previous_private_state=previous_state,
            feed_cursor=replayed_cursor,
            previous_feed_cursor=previous_cursor,
            public_post=replayed_post,
            latest_public_pointer=replayed_pointer,
            previous_latest_public_pointer=previous_pointer,
        )
        attempt_chain_entries = self._attempt_chain_entries(replayed_event.event_id, attempts)
        event_payload = replayed_event.to_payload()
        chain_head = canonical_payload_hash(
            {
                "previous": self.progress.event_chain_head,
                "event": event_payload,
                "attempts": attempt_chain_entries,
                "private_update_hash": replayed_update.record_hash,
                "private_state_hash": replayed_state.record_hash,
                "public_post_hash": None if replayed_post is None else replayed_post.record_hash,
                "cursor_hash": replayed_cursor.record_hash,
            }
        )
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._insert_payload(
                "events",
                ("event_ordinal", "event_id", "run_id", "status"),
                (
                    ordinal,
                    replayed_event.event_id,
                    replayed_event.run_id,
                    replayed_event.status.value,
                ),
                event_payload,
            )
            self._insert_payload(
                "private_updates",
                ("update_id", "agent_id", "event_ordinal"),
                (replayed_update.update_id, replayed_update.agent_id, ordinal),
                replayed_update.to_payload(),
            )
            self._replace_current(
                "private_states", replayed_update.agent_id, replayed_state.to_payload()
            )
            if replayed_post is not None and replayed_pointer is not None:
                self._insert_payload(
                    "public_posts",
                    ("post_id", "agent_id", "event_ordinal"),
                    (replayed_post.post_id, replayed_post.author_agent_id, ordinal),
                    replayed_post.to_payload(),
                )
                self._replace_current(
                    "latest_public_pointers",
                    replayed_post.author_agent_id,
                    replayed_pointer.to_payload(),
                )
            self._replace_current(
                "feed_cursors", replayed_event.agent_id, replayed_cursor.to_payload()
            )
            self._connection.execute(
                """UPDATE progress
                   SET next_event_ordinal = ?, succeeded_event_count = ?, event_chain_head = ?
                   WHERE singleton = 1""",
                (ordinal + 1, ordinal + 1, chain_head),
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise

    def _manifest_matched_seed(self) -> int:
        payload = _load_canonical_json(
            self._connection.execute(
                "SELECT manifest_payload_json FROM binding WHERE singleton = 1"
            ).fetchone()[0],
            "baseline manifest",
        )
        value = payload["matched_seed"]
        if type(value) is not int:
            raise ValueError("stored manifest seed is invalid")
        return value

    def _schedule_slot(self, ordinal: int) -> tuple[int, int, str, bool]:
        slot = self.schedule_slot(ordinal)
        return slot.sweep_index, slot.draw_index, slot.agent_id, slot.publish_flag

    def schedule_slot(self, event_ordinal: int) -> ScheduleSlot:
        _require_int("event_ordinal", event_ordinal)
        if event_ordinal >= self._schedule.count:
            raise ValueError("event_ordinal is outside the frozen schedule")
        return self._schedule.slots[event_ordinal]

    def _insert_payload(
        self, table: str, columns: tuple[str, ...], values: tuple[object, ...], payload: object
    ) -> None:
        payload_json = _canonical_json(payload)
        names = ", ".join((*columns, "payload_json", "payload_hash"))
        placeholders = ", ".join("?" for _ in range(len(columns) + 2))
        self._connection.execute(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
            (*values, payload_json, canonical_payload_hash(payload)),
        )

    def _insert_current(self, table: str, agent_id: str, payload: object) -> None:
        self._connection.execute(
            f"INSERT INTO {table} (agent_id, payload_json, payload_hash) VALUES (?, ?, ?)",
            (agent_id, _canonical_json(payload), canonical_payload_hash(payload)),
        )

    def _replace_current(self, table: str, agent_id: str, payload: object) -> None:
        self._connection.execute(
            f"""INSERT INTO {table} (agent_id, payload_json, payload_hash) VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE
                SET payload_json = excluded.payload_json, payload_hash = excluded.payload_hash""",
            (agent_id, _canonical_json(payload), canonical_payload_hash(payload)),
        )

    def _read_typed_current(self, table: str, agent_id: str, record_type: object) -> object | None:
        _require_id("agent_id", agent_id)
        row = self._connection.execute(
            f"SELECT payload_json, payload_hash FROM {table} WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        payload = _load_canonical_json(row[0], table)
        if canonical_payload_hash(payload) != row[1]:
            raise ValueError(f"stored {table} payload hash does not match")
        return record_type.from_payload(payload)  # type: ignore[attr-defined]

    def attempts_for_event(
        self,
        event_id: str,
        *,
        external_raw_responses: Mapping[str, str] | None = None,
    ) -> tuple[GenerationAttempt, ...]:
        _require_id("event_id", event_id)
        rows = self._connection.execute(
            """SELECT attempt_id, event_id, attempt_index, status, payload_json, payload_hash,
                      raw_response_uri, raw_response_hash
               FROM attempts WHERE event_id = ? ORDER BY attempt_index""",
            (event_id,),
        ).fetchall()
        values: list[GenerationAttempt] = []
        for (
            row_attempt_id,
            row_event_id,
            row_attempt_index,
            row_status,
            payload_json,
            payload_hash,
            raw_uri,
            raw_hash,
        ) in rows:
            value = self._replay_attempt_payload(
                payload_json,
                payload_hash,
                raw_uri,
                raw_hash,
                attempt_id=row_attempt_id,
                external_raw_responses=external_raw_responses,
            )
            if (
                row_attempt_id != value.attempt_id
                or row_event_id != value.event_id
                or row_attempt_index != value.attempt_index
                or row_status != value.status.value
            ):
                raise ValueError("attempt row identity or status does not match typed payload")
            values.append(value)
        return tuple(values)

    def _replay_attempt_payload(
        self,
        payload_json: str,
        payload_hash: str,
        raw_uri: str | None,
        raw_hash: str | None,
        *,
        attempt_id: str,
        external_raw_responses: Mapping[str, str] | None,
    ) -> GenerationAttempt:
        payload = _load_canonical_json(payload_json, "attempt")
        if (raw_uri is None) != (raw_hash is None):
            raise ValueError("external raw response URI/hash binding is incomplete")
        if raw_uri is not None:
            reference = ExternalResponseReference(uri=raw_uri, sha256=raw_hash)  # type: ignore[arg-type]
            raw_response = (
                None if external_raw_responses is None else external_raw_responses.get(attempt_id)
            )
            if raw_response is None and self._raw_response_resolver is not None:
                raw_response = self._raw_response_resolver(reference)
            if type(raw_response) is not str:
                raise ValueError("external raw response resolver is required for strict replay")
            if canonical_payload_hash(raw_response) != raw_hash:
                raise ValueError("external raw response hash does not match")
            payload["raw_response"] = raw_response
        if canonical_payload_hash(payload) != payload_hash:
            raise ValueError("stored attempt payload hash does not match")
        return GenerationAttempt.from_payload(payload)

    def external_response_reference(self, attempt_id: str) -> ExternalResponseReference | None:
        _require_id("attempt_id", attempt_id)
        row = self._connection.execute(
            "SELECT raw_response_uri, raw_response_hash FROM attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise ValueError("attempt does not exist")
        if row[0] is None and row[1] is None:
            return None
        if row[0] is None or row[1] is None:
            raise ValueError("external raw response URI/hash binding is incomplete")
        return ExternalResponseReference(uri=row[0], sha256=row[1])

    def _attempt_chain_entries(
        self,
        event_id: str,
        attempts: tuple[GenerationAttempt, ...],
    ) -> list[dict[str, object]]:
        rows = self._connection.execute(
            """SELECT attempt_id, event_id, attempt_index, status, payload_hash,
                      raw_response_uri, raw_response_hash
               FROM attempts WHERE event_id = ? ORDER BY attempt_index""",
            (event_id,),
        ).fetchall()
        if len(rows) != len(attempts):
            raise ValueError("terminal attempt chain evidence is not exact-cover")
        entries: list[dict[str, object]] = []
        for row, attempt in zip(rows, attempts):
            (
                attempt_id,
                row_event_id,
                attempt_index,
                status,
                payload_hash,
                raw_uri,
                raw_hash,
            ) = row
            if (
                attempt_id != attempt.attempt_id
                or row_event_id != attempt.event_id
                or attempt_index != attempt.attempt_index
                or status != attempt.status.value
            ):
                raise ValueError("terminal attempt row identity does not match typed payload")
            transitions, transition_entries = self._attempt_transition_chain_entries(
                attempt.attempt_id,
                external_raw_responses=(
                    None
                    if attempt.raw_response is None
                    else {attempt.attempt_id: attempt.raw_response}
                ),
            )
            if transitions[-1] != attempt:
                raise ValueError("terminal attempt does not match terminal transition evidence")
            terminal_transition_envelope = transition_entries[-1]["row_envelope"]
            assert isinstance(terminal_transition_envelope, dict)
            if (
                terminal_transition_envelope["event_id"],
                terminal_transition_envelope["attempt_index"],
                terminal_transition_envelope["status"],
                terminal_transition_envelope["raw_response_uri"],
                terminal_transition_envelope["raw_response_hash"],
            ) != (row_event_id, attempt_index, status, raw_uri, raw_hash):
                raise ValueError(
                    "terminal attempt and transition URI/hash row envelopes do not match"
                )
            if (raw_uri is None) != (raw_hash is None):
                raise ValueError("external raw response URI/hash binding is incomplete")
            entries.append(
                {
                    "terminal_attempt": attempt.to_payload(),
                    "terminal_row_envelope": {
                        "attempt_id": attempt_id,
                        "event_id": row_event_id,
                        "attempt_index": attempt_index,
                        "status": status,
                        "payload_hash": payload_hash,
                        "raw_response_uri": raw_uri,
                        "raw_response_hash": raw_hash,
                    },
                    "transitions": transition_entries,
                }
            )
        return entries

    def event_at(self, event_ordinal: int) -> GenerationEvent | None:
        row = self._connection.execute(
            """SELECT event_ordinal, event_id, run_id, status, payload_json, payload_hash
               FROM events WHERE event_ordinal = ?""",
            (event_ordinal,),
        ).fetchone()
        if row is None:
            return None
        payload = _load_canonical_json(row[4], "event")
        if canonical_payload_hash(payload) != row[5]:
            raise ValueError("stored event payload hash does not match")
        event = GenerationEvent.from_payload(payload)
        if (
            row[0] != event.event_ordinal
            or row[1] != event.event_id
            or row[2] != event.run_id
            or row[3] != event.status.value
            or event.run_id != self.binding.run_id
        ):
            raise ValueError("event row identity or status does not match typed payload")
        return event

    def private_state(self, agent_id: str) -> PrivateState | None:
        return self._read_typed_current("private_states", agent_id, PrivateState)  # type: ignore[return-value]

    def latest_public_pointer(self, agent_id: str) -> LatestPublicPointer | None:
        return self._read_typed_current("latest_public_pointers", agent_id, LatestPublicPointer)  # type: ignore[return-value]

    def feed_cursor(self, agent_id: str) -> FeedCursor | None:
        return self._read_typed_current("feed_cursors", agent_id, FeedCursor)  # type: ignore[return-value]

    def public_posts_for_agent(self, agent_id: str) -> tuple[PublicPost, ...]:
        _require_id("agent_id", agent_id)
        rows = self._connection.execute(
            """SELECT payload_json, payload_hash FROM public_posts
               WHERE agent_id = ? ORDER BY event_ordinal""",
            (agent_id,),
        ).fetchall()
        result: list[PublicPost] = []
        for payload_json, payload_hash in rows:
            payload = _load_canonical_json(payload_json, "public post")
            if canonical_payload_hash(payload) != payload_hash:
                raise ValueError("stored public post payload hash does not match")
            result.append(PublicPost.from_payload(payload))
        return tuple(result)

    def recovery_evidence(self, next_event_ordinal: int | None = None) -> Mapping[str, object]:
        """Return a canonical read-only recovery projection after full integrity replay."""

        self.verify_integrity()
        progress = self.progress
        ordinal = progress.next_event_ordinal if next_event_ordinal is None else next_event_ordinal
        _require_int("next_event_ordinal", ordinal)
        if not 0 <= ordinal <= progress.next_event_ordinal:
            raise ValueError("recovery evidence ordinal is ahead of committed SQLite progress")
        if self.binding.round0_root is None:
            raise ValueError("recovery evidence requires sealed round-0 state")

        round0_entries = self._round0_entries(require_exact=True)
        private_states = {
            entry["agent_id"]: PrivateState.from_payload(entry["private_state"])
            for entry in round0_entries
        }
        latest_pointers = {
            entry["agent_id"]: LatestPublicPointer.from_payload(entry["latest_public_pointer"])
            for entry in round0_entries
        }
        cursors = {
            entry["agent_id"]: FeedCursor.from_payload(entry["initial_feed_cursor"])
            for entry in round0_entries
        }
        public_stock = [entry["public_post"] for entry in round0_entries]
        chain_head = self._event_chain_genesis(self.binding.round0_root)
        for event_ordinal in range(ordinal):
            event = self.event_at(event_ordinal)
            if event is None:
                raise ValueError("recovery evidence event prefix has a gap")
            attempts = self.attempts_for_event(event.event_id)
            update_row = self._connection.execute(
                """SELECT payload_json, payload_hash FROM private_updates
                   WHERE event_ordinal = ?""",
                (event_ordinal,),
            ).fetchone()
            if update_row is None:
                raise ValueError("recovery evidence lacks private update")
            update_payload = _load_canonical_json(update_row[0], "private update")
            if canonical_payload_hash(update_payload) != update_row[1]:
                raise ValueError("stored private update payload hash does not match")
            update = PrivateUpdate.from_payload(update_payload)
            state = PrivateState.from_update(
                update,
                previous=private_states[event.agent_id],
                mock_only=True,
            )
            cursor = cursors[event.agent_id].advance(event_ordinal)
            post_row = self._connection.execute(
                """SELECT payload_json, payload_hash FROM public_posts
                   WHERE event_ordinal = ?""",
                (event_ordinal,),
            ).fetchone()
            post = None
            if post_row is not None:
                post_payload = _load_canonical_json(post_row[0], "public post")
                if canonical_payload_hash(post_payload) != post_row[1]:
                    raise ValueError("stored public post payload hash does not match")
                post = PublicPost.from_payload(post_payload)
                public_stock.append(post.to_payload())
                latest_pointers[event.agent_id] = LatestPublicPointer.from_post(
                    post,
                    previous=latest_pointers[event.agent_id],
                    mock_only=True,
                )
            private_states[event.agent_id] = state
            cursors[event.agent_id] = cursor
            chain_head = canonical_payload_hash(
                {
                    "previous": chain_head,
                    "event": event.to_payload(),
                    "attempts": self._attempt_chain_entries(event.event_id, attempts),
                    "private_update_hash": update.record_hash,
                    "private_state_hash": state.record_hash,
                    "public_post_hash": None if post is None else post.record_hash,
                    "cursor_hash": cursor.record_hash,
                }
            )

        attempt_prefix: list[dict[str, object]] = []
        if ordinal < self.binding.schedule_count:
            event_id = derive_event_id(self.binding.run_id, ordinal)
            rows = self._connection.execute(
                """SELECT DISTINCT attempt_id, attempt_index FROM attempt_transitions
                   WHERE event_id = ? ORDER BY attempt_index""",
                (event_id,),
            ).fetchall()
            for attempt_id, attempt_index in rows:
                transitions, entries = self._attempt_transition_chain_entries(attempt_id)
                checkpoint_transitions: list[dict[str, object]] = []
                checkpoint_entries: list[dict[str, object]] = []
                for transition, entry in zip(transitions, entries):
                    transition_payload = transition.to_payload()
                    row_envelope = dict(entry["row_envelope"])
                    if row_envelope["raw_response_uri"] is not None:
                        transition_payload["raw_response"] = None
                    row_envelope["checkpoint_payload_hash"] = canonical_payload_hash(
                        transition_payload
                    )
                    checkpoint_transitions.append(transition_payload)
                    checkpoint_entries.append(
                        {
                            "transition": dict(transition_payload),
                            "row_envelope": row_envelope,
                        }
                    )
                attempt_prefix.append(
                    {
                        "attempt_id": attempt_id,
                        "attempt_index": attempt_index,
                        "transitions": tuple(checkpoint_transitions),
                        "transition_entries": tuple(checkpoint_entries),
                    }
                )
        roster = self.binding.expected_agent_ids
        return _freeze_recovery_evidence(
            {
                "next_event_ordinal": ordinal,
                "event_chain_head": chain_head,
                "private_states": tuple(
                    private_states[agent_id].to_payload() for agent_id in roster
                ),
                "public_stock": tuple(public_stock),
                "latest_public_pointers": tuple(
                    latest_pointers[agent_id].to_payload() for agent_id in roster
                ),
                "feed_cursors": tuple(cursors[agent_id].to_payload() for agent_id in roster),
                "current_attempt_prefix": tuple(attempt_prefix),
            }
        )  # type: ignore[return-value]

    def assert_complete(self) -> None:
        self.verify_integrity()
        progress = self.progress
        event_count = self._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if (
            progress.next_event_ordinal != progress.expected_event_count
            or progress.succeeded_event_count != progress.expected_event_count
            or event_count != progress.expected_event_count
        ):
            raise ValueError("main-path complete requires all expected events succeeded")
        for ordinal in range(progress.expected_event_count):
            event = self.event_at(ordinal)
            if event is None or event.status is not EventStatus.SUCCEEDED:
                raise ValueError("main-path complete requires all expected events succeeded")

    def verify_integrity(self) -> None:
        binding_row = self._connection.execute(
            """SELECT schedule_payload_json, manifest_payload_json
               FROM binding WHERE singleton = 1"""
        ).fetchone()
        stored_schedule_payload = _load_canonical_json(binding_row[0], "frozen schedule")
        if stored_schedule_payload != self._schedule.to_payload() or (
            self._schedule.schedule_hash != self.binding.schedule_hash
            or self._schedule.count != self.binding.schedule_count
        ):
            raise ValueError("stored schedule payload does not match binding")
        manifest_payload = _load_canonical_json(binding_row[1], "baseline manifest")
        if canonical_payload_hash(manifest_payload) != self.binding.manifest_hash:
            raise ValueError("stored baseline manifest payload hash does not match")
        try:
            replayed_manifest = RunManifest.from_payload(manifest_payload, schedule=self._schedule)
        except (TypeError, ValueError) as error:
            raise ValueError("stored baseline manifest is invalid") from error
        if replayed_manifest.run_id != self.binding.run_id:
            raise ValueError("stored baseline manifest run does not match binding")
        if self.binding.round0_root is not None:
            replayed_round0_root = canonical_payload_hash(self._round0_entries(require_exact=True))
            if replayed_round0_root != self.binding.round0_root:
                raise ValueError("stored round-0 root does not replay from initial state")
        progress = self.progress
        if not (
            0 <= progress.next_event_ordinal <= progress.expected_event_count
            and progress.succeeded_event_count == progress.next_event_ordinal
            and progress.expected_event_count == self.binding.schedule_count
        ):
            raise ValueError("stored manifest progress is invalid")
        rows = self._connection.execute(
            "SELECT event_ordinal FROM events ORDER BY event_ordinal"
        ).fetchall()
        ordinals = tuple(row[0] for row in rows)
        if ordinals != tuple(range(progress.next_event_ordinal)):
            raise ValueError("stored succeeded event prefix has a gap or duplicate")
        self._verify_attempt_exact_cover(progress)
        initial_updates: dict[str, PrivateUpdate] = {}
        for update_id, agent_id, payload_json, payload_hash in self._connection.execute(
            """SELECT update_id, agent_id, payload_json, payload_hash FROM private_updates
               WHERE event_ordinal IS NULL"""
        ).fetchall():
            payload = _load_canonical_json(payload_json, "initial private update")
            if canonical_payload_hash(payload) != payload_hash:
                raise ValueError("stored initial private update payload hash does not match")
            update = PrivateUpdate.from_payload(payload)
            if update_id != update.update_id or agent_id != update.agent_id:
                raise ValueError(
                    "stored initial private update row identity does not match typed payload"
                )
            if update.agent_id in initial_updates:
                raise ValueError("stored initial private updates contain a duplicate agent")
            initial_updates[update.agent_id] = update
        topic_bindings = {
            (update.topic_package_id, update.topic_package_hash)
            for update in initial_updates.values()
        }
        if any(
            update.matched_seed != replayed_manifest.matched_seed
            or update.agent_id not in self.binding.expected_agent_ids
            for update in initial_updates.values()
        ):
            raise ValueError(
                "round-0 private update seed or agent provenance does not match manifest roster"
            )
        if len(topic_bindings) > 1:
            raise ValueError("round-0 topic provenance is inconsistent across agents")
        replayed_states = {
            agent_id: PrivateState.from_update(update, previous=None, mock_only=True)
            for agent_id, update in initial_updates.items()
        }
        expected_update_ids = {update.update_id for update in initial_updates.values()}
        expected_post_ids: set[str] = set()
        expected_pointers: dict[str, LatestPublicPointer] = {}
        round0_rows = self._connection.execute(
            """SELECT post_id, agent_id, payload_json, payload_hash FROM public_posts
               WHERE event_ordinal IS NULL"""
        ).fetchall()
        if len(round0_rows) != len(initial_updates):
            raise ValueError("round0 public posts are not exact-cover")
        for post_id, agent_id, payload_json, payload_hash in round0_rows:
            payload = _load_canonical_json(payload_json, "round-0 public post")
            if canonical_payload_hash(payload) != payload_hash:
                raise ValueError("stored round0 public post payload hash does not match")
            post = PublicPost.from_payload(payload)
            update = initial_updates.get(agent_id)
            if (
                update is None
                or post_id != post.post_id
                or post.author_agent_id != agent_id
                or post != PublicPost.from_private_update(update, mock_only=True)
            ):
                raise ValueError("round0 public post provenance is not exact-cover")
            expected_post_ids.add(post.post_id)
            expected_pointers[agent_id] = LatestPublicPointer.from_post(
                post, previous=None, mock_only=True
            )
        initialized_agents = set(initial_updates)
        current_state_agents = {
            row[0]
            for row in self._connection.execute("SELECT agent_id FROM private_states").fetchall()
        }
        cursor_agents = {
            row[0]
            for row in self._connection.execute("SELECT agent_id FROM feed_cursors").fetchall()
        }
        pointer_agents = {
            row[0]
            for row in self._connection.execute(
                "SELECT agent_id FROM latest_public_pointers"
            ).fetchall()
        }
        if not (current_state_agents == cursor_agents == pointer_agents == initialized_agents):
            raise ValueError("current private/public/cursor state is not exact-cover")
        initial_cursor_agents = {
            row[0]
            for row in self._connection.execute(
                "SELECT agent_id FROM initial_feed_cursors"
            ).fetchall()
        }
        if initial_cursor_agents != initialized_agents:
            raise ValueError("initial cursor evidence is not exact-cover")
        replayed_cursors: dict[str, FeedCursor] = {}
        for agent_id in sorted(initialized_agents):
            initial_cursor = self._read_typed_current("initial_feed_cursors", agent_id, FeedCursor)
            if not isinstance(initial_cursor, FeedCursor):
                raise ValueError("initial cursor evidence is missing")
            expected_cursor = FeedCursor.initial(
                matched_seed=replayed_manifest.matched_seed,
                receiver_agent_id=agent_id,
                exposure_mode=self.binding.expected_exposure_mode,
                exposure_graph_hash=self.binding.expected_exposure_graph_hash,
                mock_only=True,
            )
            if initial_cursor != expected_cursor:
                raise ValueError("initial cursor seed, agent, or provenance drifted")
            replayed_cursors[agent_id] = expected_cursor
        chain_head = self._event_chain_genesis(self.binding.round0_root)
        for ordinal in ordinals:
            event = self.event_at(ordinal)
            if event is None or event.status is not EventStatus.SUCCEEDED:
                raise ValueError("stored succeeded event prefix is invalid")
            attempts = self.attempts_for_event(event.event_id)
            if (
                not attempts
                or tuple(item.attempt_id for item in attempts) != event.attempt_ids
                or attempts[-1].status is not EventStatus.SUCCEEDED
                or any(item.status is not EventStatus.FAILED for item in attempts[:-1])
            ):
                raise ValueError("stored final-success attempt evidence is invalid")
            if any(item.exposure_id != event.exposure_id for item in attempts):
                raise ValueError("stored attempt exposure does not match event exposure_id")
            update_rows = self._connection.execute(
                """SELECT update_id, agent_id, payload_json, payload_hash FROM private_updates
                   WHERE event_ordinal = ?""",
                (ordinal,),
            ).fetchall()
            if len(update_rows) != 1:
                raise ValueError("successful event private update is not exact-cover")
            update_id, update_agent_id, update_json, update_hash = update_rows[0]
            update_payload = _load_canonical_json(update_json, "private update")
            if canonical_payload_hash(update_payload) != update_hash:
                raise ValueError("stored private update payload hash does not match")
            update = PrivateUpdate.from_payload(update_payload)
            if (
                update_id != update.update_id
                or update_agent_id != update.agent_id
                or update.event_id != event.event_id
                or update.event_ordinal != ordinal
                or update.agent_id != event.agent_id
            ):
                raise ValueError("successful event private update provenance drifted")
            expected_update_ids.add(update.update_id)
            previous_state = replayed_states.get(event.agent_id)
            previous_cursor = replayed_cursors.get(event.agent_id)
            previous_pointer = expected_pointers.get(event.agent_id)
            if previous_state is None or previous_cursor is None or previous_pointer is None:
                raise ValueError("stored successful event lacks initial agent state")
            state = PrivateState.from_update(update, previous=previous_state, mock_only=True)
            cursor = previous_cursor.advance(ordinal)
            replayed_states[event.agent_id] = state
            replayed_cursors[event.agent_id] = cursor
            post_rows = self._connection.execute(
                """SELECT post_id, agent_id, payload_json, payload_hash FROM public_posts
                   WHERE event_ordinal = ?""",
                (ordinal,),
            ).fetchall()
            if len(post_rows) > 1:
                raise ValueError("successful event public post is not exact-cover")
            post: PublicPost | None = None
            event_pointer: LatestPublicPointer | None = None
            if post_rows:
                post_id, post_agent_id, post_json, post_hash = post_rows[0]
                post_payload = _load_canonical_json(post_json, "public post")
                if canonical_payload_hash(post_payload) != post_hash:
                    raise ValueError("stored public post payload hash does not match")
                post = PublicPost.from_payload(post_payload)
                if (
                    post_id != post.post_id
                    or post_agent_id != post.author_agent_id
                    or post != PublicPost.from_private_update(update, mock_only=True)
                ):
                    raise ValueError("successful event public post provenance drifted")
                expected_post_ids.add(post.post_id)
                event_pointer = LatestPublicPointer.from_post(
                    post,
                    previous=previous_pointer,
                    mock_only=True,
                )
            if event.publish_flag != (post is not None):
                raise ValueError("stored public post does not match frozen publish flag")
            _validate_success_bundle(
                run_id=self.binding.run_id,
                slot=self.schedule_slot(ordinal),
                event=event,
                attempts=attempts,
                private_update=update,
                private_state=state,
                previous_private_state=previous_state,
                feed_cursor=cursor,
                previous_feed_cursor=previous_cursor,
                public_post=post,
                latest_public_pointer=event_pointer,
                previous_latest_public_pointer=previous_pointer,
            )
            attempt_chain_entries = self._attempt_chain_entries(event.event_id, attempts)
            if event_pointer is not None:
                expected_pointers[event.agent_id] = event_pointer
            chain_head = canonical_payload_hash(
                {
                    "previous": chain_head,
                    "event": event.to_payload(),
                    "attempts": attempt_chain_entries,
                    "private_update_hash": update.record_hash,
                    "private_state_hash": state.record_hash,
                    "public_post_hash": None if post is None else post.record_hash,
                    "cursor_hash": cursor.record_hash,
                }
            )
        if chain_head != progress.event_chain_head:
            raise ValueError("stored event chain head does not replay")
        stored_update_ids = {
            row[0]
            for row in self._connection.execute("SELECT update_id FROM private_updates").fetchall()
        }
        stored_post_ids = {
            row[0]
            for row in self._connection.execute("SELECT post_id FROM public_posts").fetchall()
        }
        if stored_update_ids != expected_update_ids:
            raise ValueError("private update history is not exact-cover")
        if stored_post_ids != expected_post_ids:
            raise ValueError("public post history is not exact-cover")
        for agent_id, state in replayed_states.items():
            if self.private_state(agent_id) != state:
                raise ValueError("stored current private state does not replay")
        for agent_id, cursor in replayed_cursors.items():
            if self.feed_cursor(agent_id) != cursor:
                raise ValueError("stored current feed cursor does not replay")
        for agent_id, pointer in expected_pointers.items():
            if self.latest_public_pointer(agent_id) != pointer:
                raise ValueError("stored latest public pointer does not replay")

    def _verify_attempt_exact_cover(self, progress: StorageProgress) -> None:
        transition_event_ids = {
            row[0]
            for row in self._connection.execute(
                "SELECT DISTINCT event_id FROM attempt_transitions"
            ).fetchall()
        }
        terminal_event_ids = {
            row[0]
            for row in self._connection.execute("SELECT DISTINCT event_id FROM attempts").fetchall()
        }
        allowed_ordinals = range(
            progress.next_event_ordinal
            + (progress.next_event_ordinal < progress.expected_event_count)
        )
        allowed_event_ids = {
            derive_event_id(self.binding.run_id, ordinal) for ordinal in allowed_ordinals
        }
        if (transition_event_ids | terminal_event_ids) - allowed_event_ids:
            raise ValueError("future or foreign attempt evidence is not allowed")
        if terminal_event_ids - transition_event_ids:
            raise ValueError("terminal attempt is orphaned from its transition journal")
        for ordinal in allowed_ordinals:
            event_id = derive_event_id(self.binding.run_id, ordinal)
            rows = self._connection.execute(
                """SELECT attempt_id, event_id, attempt_index, transition_index, status,
                          payload_json, payload_hash, raw_response_uri, raw_response_hash
                   FROM attempt_transitions WHERE event_id = ?
                   ORDER BY attempt_index, transition_index""",
                (event_id,),
            ).fetchall()
            if ordinal < progress.next_event_ordinal and not rows:
                raise ValueError("succeeded event lacks attempt transition evidence")
            grouped: dict[int, list[tuple[object, ...]]] = {}
            for row in rows:
                grouped.setdefault(row[2], []).append(row)
            if tuple(grouped) != tuple(range(1, len(grouped) + 1)):
                raise ValueError("attempt transition journal has an attempt-index gap")
            terminal_attempts = {
                value.attempt_id: value for value in self.attempts_for_event(event_id)
            }
            covered_terminal_ids: set[str] = set()
            terminal_values: list[GenerationAttempt] = []
            for attempt_index, transition_rows in grouped.items():
                if tuple(row[3] for row in transition_rows) != tuple(
                    range(1, len(transition_rows) + 1)
                ):
                    raise ValueError("attempt transition journal has a transition gap")
                statuses = tuple(row[4] for row in transition_rows)
                if statuses not in {
                    (EventStatus.PENDING.value,),
                    (EventStatus.PENDING.value, EventStatus.IN_PROGRESS.value),
                    (
                        EventStatus.PENDING.value,
                        EventStatus.IN_PROGRESS.value,
                        EventStatus.FAILED.value,
                    ),
                    (
                        EventStatus.PENDING.value,
                        EventStatus.IN_PROGRESS.value,
                        EventStatus.SUCCEEDED.value,
                    ),
                }:
                    raise ValueError("attempt transition journal lifecycle is invalid")
                replayed = tuple(
                    self._replay_attempt_payload(
                        row[5],
                        row[6],
                        row[7],
                        row[8],
                        attempt_id=row[0],
                        external_raw_responses=None,
                    )
                    for row in transition_rows
                )
                if any(
                    row[0] != item.attempt_id
                    or row[1] != item.event_id
                    or row[2] != item.attempt_index
                    or row[4] != item.status.value
                    for row, item in zip(transition_rows, replayed)
                ):
                    raise ValueError(
                        "attempt transition row identity or status does not match typed payload"
                    )
                if any(item.attempt_index != attempt_index for item in replayed):
                    raise ValueError("attempt transition index evidence drifted")
                if len(replayed) == 3 and replayed[2].started_at != replayed[1].started_at:
                    raise ValueError(
                        "terminal attempt started_at does not match IN_PROGRESS evidence"
                    )
                immutable = (
                    "attempt_id",
                    "event_id",
                    "attempt_index",
                    "request_id",
                    "exposure_id",
                    "rendered_messages",
                    "rendered_prompt_hash",
                    "request_parameters",
                    "request_parameters_hash",
                    "model_identity",
                    "model_identity_hash",
                    "model_seed",
                )
                if any(
                    getattr(item, name) != getattr(replayed[0], name)
                    for item in replayed[1:]
                    for name in immutable
                ):
                    raise ValueError("attempt transition immutable evidence drifted")
                for previous, current in zip(replayed, replayed[1:]):
                    _validate_provider_progression(previous, current)
                last = replayed[-1]
                if last.status in {EventStatus.FAILED, EventStatus.SUCCEEDED}:
                    if terminal_attempts.get(last.attempt_id) != last:
                        raise ValueError("terminal attempt does not match transition journal")
                    covered_terminal_ids.add(last.attempt_id)
                    terminal_values.append(last)
                elif last.attempt_id in terminal_attempts:
                    raise ValueError("nonterminal attempt has orphan terminal evidence")
            if set(terminal_attempts) != covered_terminal_ids:
                raise ValueError("attempt terminal evidence is not exact-cover")
            if any(item.status is not EventStatus.FAILED for item in terminal_values[:-1]):
                raise ValueError("only the final attempt may succeed")
            if any(
                rows_for_later
                for index, rows_for_later in grouped.items()
                if index < len(grouped) and rows_for_later[-1][4] != EventStatus.FAILED.value
            ):
                raise ValueError("only a failed terminal attempt may precede a retry")
            if ordinal < progress.next_event_ordinal:
                event = self.event_at(ordinal)
                assert event is not None
                if (
                    not terminal_values
                    or terminal_values[-1].status is not EventStatus.SUCCEEDED
                    or tuple(item.attempt_id for item in terminal_values) != event.attempt_ids
                ):
                    raise ValueError("succeeded event attempt journal is not exact-cover")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> RunStorage:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
