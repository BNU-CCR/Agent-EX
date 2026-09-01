"""Per-run SQLite transaction storage for Paper 1 mock execution."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, BinaryIO, Callable, Mapping

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
    _require_timestamp,
    canonical_payload_hash,
    derive_event_id,
)
from .feed import FeedCursor
from .network import validate_shadow_artifact, validate_ws_artifact
from .state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost

if TYPE_CHECKING:
    from .execution_evidence import (
        AdapterRequestEvidence,
        EventEvidenceReferences,
        EventInputEvidence,
        FinalizedAttemptEvidence,
        MockAdapterExecutionBinding,
        MockAttemptPolicyBinding,
        ParseNotApplicableEvidence,
        PersistedInvocationEvidence,
    )
    from .parser import ParseEvidence


_SCHEMA_VERSION = "paper1.run-storage.v6"
_SQLITE_USER_VERSION = 6
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def _quote_sql_identifier(identifier: str) -> str:
    if (
        type(identifier) is not str
        or not identifier
        or not identifier.isascii()
        or not (identifier[0].isalpha() or identifier[0] == "_")
        or not all(character.isalnum() or character == "_" for character in identifier)
    ):
        raise ValueError("internal SQLite identifier is invalid")
    return f'"{identifier}"'


class ExecutionStatus(StrEnum):
    """Observed run lifecycle; this is not a frozen retry policy."""

    RUNNING = "running"
    FAILED = "failed"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class EventJournalState:
    event_id: str | None
    event_ordinal: int
    next_attempt_index: int
    latest_transition: GenerationAttempt | None
    resume_state: str


@dataclass(frozen=True, slots=True)
class ExecutionState:
    schema_version: str
    run_id: str
    baseline_manifest_hash: str
    status: ExecutionStatus
    next_event_ordinal: int
    expected_event_count: int
    current_event_id: str | None
    event_ids: tuple[str, ...]
    status_counts: Mapping[str, int]
    failed_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.event_ids, (tuple, list)) or not isinstance(
            self.failed_event_ids, (tuple, list)
        ):
            raise TypeError("execution event IDs must be tuples or lists")
        if not isinstance(self.status_counts, Mapping):
            raise TypeError("execution status counts must be a mapping")
        object.__setattr__(self, "event_ids", tuple(self.event_ids))
        object.__setattr__(self, "failed_event_ids", tuple(self.failed_event_ids))
        normalized_counts = dict(self.status_counts)
        if self.schema_version != "paper1.execution-state.v1":
            raise ValueError("execution state schema version is unsupported")
        _require_id("execution state run_id", self.run_id)
        _require_sha256("execution state baseline_manifest_hash", self.baseline_manifest_hash)
        if not isinstance(self.status, ExecutionStatus):
            raise TypeError("execution status must be typed")
        _require_int("execution next_event_ordinal", self.next_event_ordinal)
        _require_int("execution expected_event_count", self.expected_event_count, minimum=1)
        if self.next_event_ordinal > self.expected_event_count:
            raise ValueError("execution ordinal exceeds expected event count")
        if self.current_event_id is not None:
            _require_id("execution current_event_id", self.current_event_id)
        expected_statuses = {status.value for status in EventStatus}
        if set(normalized_counts) != expected_statuses:
            raise ValueError("execution status counts must enumerate runtime statuses")
        for label, count in normalized_counts.items():
            _require_int(f"execution status_counts[{label}]", count)
        for event_id in (*self.event_ids, *self.failed_event_ids):
            _require_id("execution event_id", event_id)
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError("execution event IDs must be unique")
        if any(event_id not in self.event_ids for event_id in self.failed_event_ids):
            raise ValueError("failed event IDs must be included in execution event IDs")
        if sum(normalized_counts.values()) != len(self.event_ids):
            raise ValueError("execution status counts must count event IDs exactly")
        object.__setattr__(self, "status_counts", MappingProxyType(normalized_counts))

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "baseline_manifest_hash": self.baseline_manifest_hash,
            "status": self.status.value,
            "next_event_ordinal": self.next_event_ordinal,
            "expected_event_count": self.expected_event_count,
            "current_event_id": self.current_event_id,
            "event_ids": list(self.event_ids),
            "status_counts": dict(self.status_counts),
            "failed_event_ids": list(self.failed_event_ids),
        }

    @property
    def payload_hash(self) -> str:
        return canonical_payload_hash(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ExecutionState:
        fields = {
            "schema_version",
            "run_id",
            "baseline_manifest_hash",
            "status",
            "next_event_ordinal",
            "expected_event_count",
            "current_event_id",
            "event_ids",
            "status_counts",
            "failed_event_ids",
        }
        if type(payload) is not dict or set(payload) != fields:
            raise ValueError("execution state payload fields do not match")
        if type(payload["event_ids"]) is not list or type(payload["failed_event_ids"]) is not list:
            raise TypeError("execution state event IDs must be arrays")
        if type(payload["status_counts"]) is not dict:
            raise TypeError("execution state status_counts must be a mapping")
        return cls(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            run_id=payload["run_id"],  # type: ignore[arg-type]
            baseline_manifest_hash=payload["baseline_manifest_hash"],  # type: ignore[arg-type]
            status=ExecutionStatus(payload["status"]),  # type: ignore[arg-type]
            next_event_ordinal=payload["next_event_ordinal"],  # type: ignore[arg-type]
            expected_event_count=payload["expected_event_count"],  # type: ignore[arg-type]
            current_event_id=payload["current_event_id"],  # type: ignore[arg-type]
            event_ids=tuple(payload["event_ids"]),  # type: ignore[arg-type]
            status_counts=payload["status_counts"],  # type: ignore[arg-type]
            failed_event_ids=tuple(payload["failed_event_ids"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class TerminalFailureEvidence:
    evidence_sequence: int
    previous_evidence_hash: str | None
    evidence_kind: str
    evidence_id: str
    run_id: str
    event_id: str
    event_ordinal: int
    attempt_id: str
    attempt_index: int
    terminal_transition_hash: str
    terminal_attempt_hash: str
    reason: str
    policy_evidence: Mapping[str, object]
    recorded_at: str

    def __post_init__(self) -> None:
        _require_int("evidence_sequence", self.evidence_sequence, minimum=1)
        if self.previous_evidence_hash is not None:
            _require_sha256("previous_evidence_hash", self.previous_evidence_hash)
        if self.evidence_kind != "failure":
            raise ValueError("terminal failure evidence kind must be failure")
        _require_id("evidence_id", self.evidence_id)
        _require_id("run_id", self.run_id)
        _require_id("event_id", self.event_id)
        _require_int("event_ordinal", self.event_ordinal)
        _require_id("attempt_id", self.attempt_id)
        _require_int("attempt_index", self.attempt_index, minimum=1)
        _require_sha256("terminal_transition_hash", self.terminal_transition_hash)
        _require_sha256("terminal_attempt_hash", self.terminal_attempt_hash)
        if type(self.reason) is not str or not self.reason.strip():
            raise ValueError("terminal failure reason must be non-empty")
        if type(self.policy_evidence) is not dict or not {
            "policy_id",
            "policy_hash",
        } <= set(self.policy_evidence):
            raise ValueError("terminal failure requires external policy evidence")
        _require_id("policy_evidence[policy_id]", self.policy_evidence["policy_id"])
        _require_sha256("policy_evidence[policy_hash]", self.policy_evidence["policy_hash"])
        _require_timestamp("recorded_at", self.recorded_at)
        object.__setattr__(self, "policy_evidence", _freeze_recovery_evidence(self.policy_evidence))

    def to_payload(self) -> dict[str, object]:
        return {
            "evidence_sequence": self.evidence_sequence,
            "previous_evidence_hash": self.previous_evidence_hash,
            "evidence_kind": self.evidence_kind,
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "event_id": self.event_id,
            "event_ordinal": self.event_ordinal,
            "attempt_id": self.attempt_id,
            "attempt_index": self.attempt_index,
            "terminal_transition_hash": self.terminal_transition_hash,
            "terminal_attempt_hash": self.terminal_attempt_hash,
            "reason": self.reason,
            "policy_evidence": _plain_evidence(self.policy_evidence),
            "recorded_at": self.recorded_at,
        }

    @property
    def payload_hash(self) -> str:
        return canonical_payload_hash(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> TerminalFailureEvidence:
        if type(payload) is not dict or set(payload) != {
            "evidence_sequence",
            "previous_evidence_hash",
            "evidence_kind",
            "evidence_id",
            "run_id",
            "event_id",
            "event_ordinal",
            "attempt_id",
            "attempt_index",
            "terminal_transition_hash",
            "terminal_attempt_hash",
            "reason",
            "policy_evidence",
            "recorded_at",
        }:
            raise ValueError("terminal failure payload fields do not match")
        return cls(**dict(payload))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ResumeAuthorizationEvidence:
    """External, explicit permission to retry one already halted event."""

    evidence_sequence: int
    previous_evidence_hash: str
    evidence_kind: str
    authorization_id: str
    run_id: str
    event_id: str
    event_ordinal: int
    previous_terminal_failure_hash: str
    policy_evidence_id: str
    policy_evidence_hash: str
    authorized_at: str

    def __post_init__(self) -> None:
        _require_int("evidence_sequence", self.evidence_sequence, minimum=1)
        _require_sha256("previous_evidence_hash", self.previous_evidence_hash)
        if self.evidence_kind != "authorization":
            raise ValueError("resume authorization evidence kind must be authorization")
        _require_id("authorization_id", self.authorization_id)
        _require_id("run_id", self.run_id)
        _require_id("event_id", self.event_id)
        _require_int("event_ordinal", self.event_ordinal)
        _require_sha256("previous_terminal_failure_hash", self.previous_terminal_failure_hash)
        _require_id("policy_evidence_id", self.policy_evidence_id)
        _require_sha256("policy_evidence_hash", self.policy_evidence_hash)
        _require_timestamp("authorized_at", self.authorized_at)

    def to_payload(self) -> dict[str, object]:
        return {
            "evidence_sequence": self.evidence_sequence,
            "previous_evidence_hash": self.previous_evidence_hash,
            "evidence_kind": self.evidence_kind,
            "authorization_id": self.authorization_id,
            "run_id": self.run_id,
            "event_id": self.event_id,
            "event_ordinal": self.event_ordinal,
            "previous_terminal_failure_hash": self.previous_terminal_failure_hash,
            "policy_evidence_id": self.policy_evidence_id,
            "policy_evidence_hash": self.policy_evidence_hash,
            "authorized_at": self.authorized_at,
        }

    @property
    def payload_hash(self) -> str:
        return canonical_payload_hash(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ResumeAuthorizationEvidence:
        if type(payload) is not dict or set(payload) != {
            "evidence_sequence",
            "previous_evidence_hash",
            "evidence_kind",
            "authorization_id",
            "run_id",
            "event_id",
            "event_ordinal",
            "previous_terminal_failure_hash",
            "policy_evidence_id",
            "policy_evidence_hash",
            "authorized_at",
        }:
            raise ValueError("resume authorization payload fields do not match")
        return cls(**dict(payload))  # type: ignore[arg-type]


_LEASE_REGISTRY: set[object] = set()
_LEASE_REGISTRY_GUARD = threading.Lock()


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


def _plain_evidence(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_evidence(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_evidence(item) for item in value]
    if isinstance(value, (set, frozenset)):
        raise TypeError("evidence payload cannot contain sets")
    return value


def _validate_terminal_execution_projection(
    terminal: GenerationAttempt,
    invocation: PersistedInvocationEvidence,
    parsed: ParseEvidence | ParseNotApplicableEvidence,
) -> None:
    """Bind every terminal execution field to persisted adapter evidence."""

    response = invocation.response
    execution = invocation.to_payload()["execution_payload"]
    expected_error = (
        response.error
        if response.outcome == "timeout"
        else (parsed.error if terminal.status is EventStatus.FAILED else None)
    )
    expected = (
        execution["started_at"],
        execution["finished_at"],
        response.provider_request_id,
        execution["provider_metadata"],
        canonical_payload_hash(execution["provider_metadata"]),
        execution["http_status"],
        execution["usage"],
        canonical_payload_hash(execution["usage"]),
        execution["finish_reason"],
        response.raw_response,
        response.raw_response_hash,
        expected_error,
    )
    actual = (
        terminal.started_at,
        terminal.finished_at,
        terminal.provider_request_id,
        terminal.provider_metadata,
        terminal.provider_metadata_hash,
        terminal.http_status,
        terminal.usage,
        terminal.usage_hash,
        terminal.finish_reason,
        terminal.raw_response,
        terminal.raw_response_hash,
        terminal.error,
    )
    if actual != expected:
        raise ValueError("terminal execution projection does not match persisted invocation")


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


class RunLease:
    """Process-lifetime exclusive writer lease, released automatically on crash/close."""

    def __init__(self, store: RunStorage) -> None:
        self._store = store
        database = store._path.resolve()
        self._path = (
            database.with_suffix(database.suffix + ".lease") if os.name == "nt" else database
        )
        self._handle: BinaryIO | None = None
        self._registry_key: object | None = None

    @staticmethod
    def _is_reparse_point(value: os.stat_result) -> bool:
        return bool(getattr(value, "st_file_attributes", 0) & 0x400)

    def _open_stable_handle(self) -> tuple[BinaryIO, object]:
        if os.name != "nt":
            flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self._store._path, flags)
            value = os.fstat(descriptor)
            identity = (value.st_dev, value.st_ino)
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_nlink != 1
                or identity != self._store._database_identity
            ):
                os.close(descriptor)
                raise RuntimeError("run database lease identity is not stable")
            return os.fdopen(descriptor, "r+b", buffering=0), ("db-inode", *identity)

        if self._path.exists() or self._path.is_symlink():
            before = os.lstat(self._path)
            if not stat.S_ISREG(before.st_mode) or self._is_reparse_point(before):
                raise RuntimeError("Windows run lease sidecar must not be a reparse point")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
        descriptor = os.open(self._path, flags, 0o600)
        handle_value = os.fstat(descriptor)
        path_value = os.lstat(self._path)
        handle_identity = (handle_value.st_dev, handle_value.st_ino)
        path_identity = (path_value.st_dev, path_value.st_ino)
        if (
            not stat.S_ISREG(handle_value.st_mode)
            or handle_value.st_nlink != 1
            or self._is_reparse_point(path_value)
            or handle_identity != path_identity
        ):
            os.close(descriptor)
            raise RuntimeError("Windows run lease sidecar identity is not stable")
        return os.fdopen(descriptor, "r+b", buffering=0), ("sidecar", *handle_identity)

    def acquire(self) -> RunLease:
        if self._handle is not None:
            raise RuntimeError("run lease is already acquired by this owner")
        self._store._assert_database_single_link()
        with _LEASE_REGISTRY_GUARD:
            handle, registry_key = self._open_stable_handle()
            if registry_key in _LEASE_REGISTRY:
                handle.close()
                raise RuntimeError("run lease is already owned in this process")
            locked = False
            try:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                self._store._assert_database_single_link()
            except (OSError, BlockingIOError) as error:
                handle.close()
                raise RuntimeError("run lease is already owned by another process") from error
            except BaseException:
                if locked:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
                raise
            _LEASE_REGISTRY.add(registry_key)
            self._handle = handle
            self._registry_key = registry_key
            self._store._owned_lease = self
        return self

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            with _LEASE_REGISTRY_GUARD:
                _LEASE_REGISTRY.discard(self._registry_key)
            if self._store._owned_lease is self:
                self._store._owned_lease = None
            self._handle = None
            self._registry_key = None

    def __enter__(self) -> RunLease:
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


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
        database_identity_handle: BinaryIO,
        raw_response_resolver: Callable[[ExternalResponseReference], str] | None = None,
    ) -> None:
        self._path = path
        self._connection = connection
        self._schedule = schedule
        self._raw_response_resolver = raw_response_resolver
        self._owned_lease: RunLease | None = None
        self._database_identity_handle: BinaryIO | None = database_identity_handle
        identity_value = os.fstat(database_identity_handle.fileno())
        self._database_identity: tuple[int, int] | None = (
            identity_value.st_dev,
            identity_value.st_ino,
        )
        self._assert_database_single_link(capture_identity=True)
        self._binding = self._read_binding()

    @staticmethod
    def _open_database_identity_handle(database: Path) -> BinaryIO:
        """Open one no-follow handle whose identity remains authoritative until close."""

        try:
            before = os.lstat(database)
        except FileNotFoundError:
            raise FileNotFoundError(f"run database does not exist: {database}") from None
        if not stat.S_ISREG(before.st_mode) or bool(
            getattr(before, "st_file_attributes", 0) & 0x400
        ):
            raise RuntimeError("run database path must name a regular non-reparse file")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
        if os.name != "nt":
            flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(database, flags)
        try:
            value = os.fstat(descriptor)
            after = os.lstat(database)
            identity = (value.st_dev, value.st_ino)
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_nlink != 1
                or identity != (after.st_dev, after.st_ino)
                or not stat.S_ISREG(after.st_mode)
                or bool(getattr(after, "st_file_attributes", 0) & 0x400)
            ):
                raise RuntimeError("run database identity is not stable")
            return os.fdopen(descriptor, "rb", buffering=0)
        except BaseException:
            os.close(descriptor)
            raise

    @staticmethod
    def _assert_sqlite_sidecar_free(database: Path) -> None:
        """Require one stable rollback image before immutable version inspection."""

        for suffix in _SQLITE_SIDECAR_SUFFIXES:
            sidecar = Path(f"{database}{suffix}")
            if sidecar.exists() or sidecar.is_symlink():
                raise ValueError(
                    "storage open requires a sidecar-free rollback image; "
                    f"found SQLite sidecar {sidecar.name}"
                )

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
        if database.exists() or database.is_symlink():
            raise FileExistsError(f"run database already exists: {database}")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=database.parent,
            prefix=f".{database.name}.",
            suffix=".tmp",
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        temporary_uri = temporary.absolute().as_uri() + "?mode=rw"
        connection: sqlite3.Connection | None = sqlite3.connect(
            temporary_uri, isolation_level=None, uri=True
        )
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
                CREATE TABLE execution_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE terminal_failures (
                    evidence_id TEXT PRIMARY KEY,
                    evidence_sequence INTEGER NOT NULL UNIQUE,
                    previous_evidence_hash TEXT,
                    evidence_kind TEXT NOT NULL CHECK (evidence_kind = 'failure'),
                    event_id TEXT NOT NULL,
                    event_ordinal INTEGER NOT NULL,
                    attempt_id TEXT NOT NULL UNIQUE,
                    attempt_index INTEGER NOT NULL,
                    terminal_transition_hash TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE resume_authorizations (
                    authorization_id TEXT PRIMARY KEY,
                    evidence_sequence INTEGER NOT NULL UNIQUE,
                    previous_evidence_hash TEXT NOT NULL UNIQUE,
                    evidence_kind TEXT NOT NULL CHECK (evidence_kind = 'authorization'),
                    event_id TEXT NOT NULL,
                    event_ordinal INTEGER NOT NULL,
                    previous_terminal_failure_hash TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );
                CREATE TABLE event_input_evidence (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE
                );
                CREATE TABLE attempt_policy_evidence (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    UNIQUE (event_id, record_hash),
                    FOREIGN KEY (event_id) REFERENCES event_input_evidence(event_id)
                );
                CREATE TABLE adapter_execution_bindings (
                    binding_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE
                );
                CREATE TABLE adapter_requests (
                    attempt_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    adapter_binding_hash TEXT NOT NULL,
                    parser_limits_hash TEXT NOT NULL,
                    policy_hash TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE,
                    FOREIGN KEY (event_id) REFERENCES event_input_evidence(event_id),
                    FOREIGN KEY (adapter_binding_hash)
                        REFERENCES adapter_execution_bindings(record_hash),
                    FOREIGN KEY (event_id, policy_hash)
                        REFERENCES attempt_policy_evidence(event_id, record_hash)
                );
                CREATE INDEX idx_adapter_requests_event
                    ON adapter_requests(event_id);
                CREATE INDEX idx_adapter_requests_binding
                    ON adapter_requests(adapter_binding_hash);
                CREATE INDEX idx_adapter_requests_parser_limits
                    ON adapter_requests(parser_limits_hash);
                CREATE INDEX idx_adapter_requests_policy
                    ON adapter_requests(policy_hash);
                CREATE TABLE invocation_evidence (
                    attempt_id TEXT PRIMARY KEY,
                    response_payload TEXT NOT NULL,
                    execution_payload TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE,
                    FOREIGN KEY (attempt_id) REFERENCES adapter_requests(attempt_id)
                );
                CREATE TABLE parse_evidence (
                    attempt_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('parsed', 'not_applicable')),
                    payload TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE,
                    FOREIGN KEY (attempt_id) REFERENCES adapter_requests(attempt_id)
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
            initial_execution = ExecutionState(
                schema_version="paper1.execution-state.v1",
                run_id=manifest.run_id,
                baseline_manifest_hash=canonical_payload_hash(manifest_payload),
                status=ExecutionStatus.RUNNING,
                next_event_ordinal=0,
                expected_event_count=manifest.schedule.count,
                current_event_id=derive_event_id(manifest.run_id, 0),
                event_ids=(),
                status_counts={status.value: 0 for status in EventStatus},
                failed_event_ids=(),
            )
            connection.execute(
                "INSERT INTO execution_state VALUES (1, ?, ?)",
                (_canonical_json(initial_execution.to_payload()), initial_execution.payload_hash),
            )
            connection.commit()
            connection.close()
            connection = None
            os.link(temporary, database, follow_symlinks=False)
            temporary_identity = os.stat(temporary, follow_symlinks=False)
            installed_identity = os.stat(database, follow_symlinks=False)
            if (temporary_identity.st_dev, temporary_identity.st_ino) != (
                installed_identity.st_dev,
                installed_identity.st_ino,
            ) or installed_identity.st_nlink != 2:
                raise RuntimeError("installed run database identity does not match temporary file")
            temporary.unlink()
            installed_identity = os.stat(database, follow_symlinks=False)
            if installed_identity.st_nlink != 1:
                raise RuntimeError("installed run database link count is not one")
            expected_database_identity = (installed_identity.st_dev, installed_identity.st_ino)
            return cls.open(
                database,
                manifest=manifest,
                artifact_hashes=artifacts,
                expected_agent_ids=roster,
                expected_exposure_mode=exposure_mode,
                expected_exposure_graph_hash=exposure_graph_hash,
                expected_exposure_graph_artifact=expected_exposure_graph_artifact,
                expected_source_ws_artifact=expected_source_ws_artifact,
                raw_response_resolver=raw_response_resolver,
                _expected_database_identity=expected_database_identity,
            )
        except BaseException:
            if connection is not None:
                connection.rollback()
                connection.close()
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
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
        _expected_database_identity: tuple[int, int] | None = None,
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
        identity_handle = cls._open_database_identity_handle(database)
        opened_identity_value = os.fstat(identity_handle.fileno())
        opened_identity = (opened_identity_value.st_dev, opened_identity_value.st_ino)
        if (
            _expected_database_identity is not None
            and opened_identity != _expected_database_identity
        ):
            identity_handle.close()
            raise RuntimeError("installed run database identity changed before hardened open")
        database_uri = database.absolute().as_uri() + "?mode=rw"
        connection: sqlite3.Connection | None = None
        try:
            cls._assert_sqlite_sidecar_free(database)
            read_only_uri = database.absolute().as_uri() + "?mode=ro&immutable=1"
            version_connection = sqlite3.connect(read_only_uri, uri=True)
            try:
                observed_user_version = version_connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
            finally:
                version_connection.close()
            if observed_user_version != _SQLITE_USER_VERSION:
                raise ValueError(
                    "storage schema version is unsupported: "
                    f"expected SQLite user_version {_SQLITE_USER_VERSION}, "
                    f"found {observed_user_version}"
                )
            cls._assert_sqlite_sidecar_free(database)
            connection = sqlite3.connect(database_uri, isolation_level=None, uri=True)
            observed_user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if observed_user_version != _SQLITE_USER_VERSION:
                raise ValueError(
                    "storage schema version is unsupported: "
                    f"expected SQLite user_version {_SQLITE_USER_VERSION}, "
                    f"found {observed_user_version}"
                )
            connection.execute("PRAGMA foreign_keys = ON")
            store = cls(
                database,
                connection,
                replayed_schedule,
                identity_handle,
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
            if connection is not None:
                connection.close()
            identity_handle.close()
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

    def acquire_run_lease(self) -> RunLease:
        """Return an unacquired lease context for a future engine run lifecycle."""

        return RunLease(self)

    def _assert_database_single_link(self, *, capture_identity: bool = False) -> None:
        """Fail closed unless the database path names one stable regular file."""

        handle = self._database_identity_handle
        if handle is None or handle.closed:
            raise RuntimeError("run database stable identity handle is closed")
        try:
            path_value = os.stat(self._path, follow_symlinks=False)
            handle_value = os.fstat(handle.fileno())
        except OSError as error:
            raise RuntimeError("run database file identity cannot be verified") from error
        link_count = getattr(handle_value, "st_nlink", None)
        device = getattr(handle_value, "st_dev", None)
        inode = getattr(handle_value, "st_ino", None)
        path_identity = (getattr(path_value, "st_dev", None), getattr(path_value, "st_ino", None))
        if (
            not stat.S_ISREG(handle_value.st_mode)
            or not stat.S_ISREG(path_value.st_mode)
            or bool(getattr(path_value, "st_file_attributes", 0) & 0x400)
            or type(link_count) is not int
            or link_count != 1
            or type(device) is not int
            or type(inode) is not int
            or inode <= 0
            or path_identity != (device, inode)
        ):
            raise RuntimeError("run database hard-link or stable identity check failed")
        identity = (device, inode)
        if capture_identity:
            self._database_identity = identity
        elif self._database_identity != identity:
            raise RuntimeError("run database file identity changed after open")

    def assert_run_lease_owned(self) -> None:
        lease = self._owned_lease
        if lease is None or lease._handle is None:
            raise RuntimeError("run lease is not owned by this storage instance")
        self._assert_database_single_link()

    def _begin_write(self) -> None:
        """Open a write transaction only after revalidating the writer capability."""

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self.assert_run_lease_owned()
        except BaseException:
            self._connection.rollback()
            raise

    def _commit_write(self) -> None:
        """Revalidate DB identity/link count at the last point before COMMIT."""

        self.assert_run_lease_owned()
        self._connection.commit()

    def _assert_retry_authorized(self, event_id: str, attempt_index: int) -> None:
        """Require the immediately preceding FAILED attempt's exact causal pair."""

        if attempt_index <= 1:
            return
        progress = self.progress
        expected_event_id = derive_event_id(self.binding.run_id, progress.next_event_ordinal)
        if event_id != expected_event_id:
            raise ValueError("retry authorization must bind the current run event identity")
        previous = self._connection.execute(
            """SELECT attempt_id, payload_hash FROM attempts
               WHERE event_id = ? AND attempt_index = ? AND status = ?""",
            (event_id, attempt_index - 1, EventStatus.FAILED.value),
        ).fetchone()
        if previous is None:
            raise ValueError("next attempt requires the prior attempt to be terminal FAILED")
        chain = self.causal_evidence_prefix()
        if len(chain) < 2:
            raise ValueError("next attempt requires explicit failure evidence and authorization")
        failure, authorization = chain[-2:]
        if (
            not isinstance(failure, TerminalFailureEvidence)
            or not isinstance(authorization, ResumeAuthorizationEvidence)
            or failure.run_id != self.binding.run_id
            or authorization.run_id != self.binding.run_id
            or failure.event_id != event_id
            or failure.event_ordinal != progress.next_event_ordinal
            or failure.attempt_index != attempt_index - 1
            or failure.attempt_id != previous[0]
            or failure.terminal_attempt_hash != previous[1]
            or failure.terminal_transition_hash != previous[1]
            or authorization.event_id != event_id
            or authorization.event_ordinal != failure.event_ordinal
            or authorization.run_id != failure.run_id
            or authorization.previous_terminal_failure_hash != failure.payload_hash
            or authorization.previous_evidence_hash != failure.payload_hash
        ):
            raise ValueError(
                "next attempt requires the prior FAILED attempt's exact failure/authorization pair"
            )

    def _verify_retry_authorization_exact_cover(self) -> None:
        """Replay every retry edge against one unique adjacent failure/auth pair."""

        failures = self.terminal_failure_evidence_prefix()
        authorizations = self.resume_authorization_evidence_prefix()
        failure_by_attempt = {(item.event_id, item.attempt_index): item for item in failures}
        if len(failure_by_attempt) != len(failures):
            raise ValueError("retry failure evidence is duplicate or forked")
        authorization_by_failure = {
            item.previous_terminal_failure_hash: item for item in authorizations
        }
        if len(authorization_by_failure) != len(authorizations):
            raise ValueError("retry authorization evidence is duplicate or forked")
        rows = self._connection.execute(
            """SELECT event_id, attempt_index FROM attempt_transitions
               WHERE transition_index = 1 ORDER BY event_id, attempt_index"""
        ).fetchall()
        for event_id, attempt_index in rows:
            if attempt_index == 1:
                continue
            previous = self._connection.execute(
                """SELECT attempt_id, payload_hash, status FROM attempts
                   WHERE event_id = ? AND attempt_index = ?""",
                (event_id, attempt_index - 1),
            ).fetchone()
            failure = failure_by_attempt.get((event_id, attempt_index - 1))
            authorization = (
                None if failure is None else authorization_by_failure.get(failure.payload_hash)
            )
            if (
                previous is None
                or previous[2] != EventStatus.FAILED.value
                or failure is None
                or authorization is None
                or failure.attempt_id != previous[0]
                or failure.terminal_attempt_hash != previous[1]
                or failure.terminal_transition_hash != previous[1]
                or authorization.event_id != event_id
                or authorization.event_ordinal != failure.event_ordinal
                or authorization.previous_evidence_hash != failure.payload_hash
            ):
                raise ValueError(
                    "retry attempt lacks exact-cover failure and authorization evidence"
                )

    def execution_state(self) -> ExecutionState:
        row = self._connection.execute(
            "SELECT payload_json, payload_hash FROM execution_state WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise ValueError("execution state is missing")
        payload = _load_canonical_json(row[0], "execution state")
        if canonical_payload_hash(payload) != row[1]:
            raise ValueError("stored execution state payload hash does not match")
        value = ExecutionState.from_payload(payload)  # type: ignore[arg-type]
        if value.payload_hash != row[1] or value.run_id != self.binding.run_id:
            raise ValueError("stored execution state identity does not match")
        return value

    def current_event_journal(self) -> EventJournalState:
        progress = self.progress
        if progress.next_event_ordinal == progress.expected_event_count:
            return EventJournalState(None, progress.next_event_ordinal, 1, None, "complete")
        event_id = derive_event_id(self.binding.run_id, progress.next_event_ordinal)
        rows = self._connection.execute(
            """SELECT attempt_id, attempt_index FROM attempt_transitions
               WHERE event_id = ? ORDER BY attempt_index, transition_index""",
            (event_id,),
        ).fetchall()
        if not rows:
            return EventJournalState(event_id, progress.next_event_ordinal, 1, None, "new_attempt")
        latest_attempt_id, latest_index = rows[-1]
        latest = self.attempt_transitions(latest_attempt_id)[-1]
        states = {
            EventStatus.PENDING: "pending_attempt_requires_same_request",
            EventStatus.IN_PROGRESS: "in_progress_requires_provider_reconciliation",
            EventStatus.FAILED: "failed_attempt_requires_external_authorization",
            EventStatus.SUCCEEDED: "succeeded_attempt_requires_atomic_commit",
        }
        if latest.status is EventStatus.FAILED:
            failure = next(
                (
                    item
                    for item in reversed(self.terminal_failure_evidence_prefix())
                    if item.run_id == self.binding.run_id
                    and item.event_id == event_id
                    and item.event_ordinal == progress.next_event_ordinal
                    and item.attempt_id == latest.attempt_id
                    and item.attempt_index == latest.attempt_index
                ),
                None,
            )
            authorization = (
                None
                if failure is None
                else next(
                    (
                        item
                        for item in reversed(self.resume_authorization_evidence_prefix())
                        if item.run_id == self.binding.run_id
                        and item.run_id == failure.run_id
                        and item.event_id == event_id
                        and item.event_ordinal == progress.next_event_ordinal
                        and item.previous_terminal_failure_hash == failure.payload_hash
                    ),
                    None,
                )
            )
            if failure is not None:
                states[EventStatus.FAILED] = (
                    "retry_same_event"
                    if authorization is not None
                    and authorization.previous_terminal_failure_hash == failure.payload_hash
                    else "halted_current_event"
                )
        next_index = latest_index + 1 if latest.status is EventStatus.FAILED else latest_index
        return EventJournalState(
            event_id,
            progress.next_event_ordinal,
            next_index,
            latest,
            states[latest.status],
        )

    def _replace_execution_state(self, value: ExecutionState) -> None:
        self._connection.execute(
            "UPDATE execution_state SET payload_json = ?, payload_hash = ? WHERE singleton = 1",
            (_canonical_json(value.to_payload()), value.payload_hash),
        )

    def append_attempt(
        self,
        attempt: GenerationAttempt,
        *,
        external_response: ExternalResponseReference | None = None,
    ) -> None:
        self._assert_not_halted()
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
        self._begin_write()
        try:
            self._append_attempt_in_transaction(replayed, external_response=external_response)
            self._commit_write()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            raise ValueError("attempt records are append-only") from error
        except BaseException:
            self._connection.rollback()
            raise

    def _append_attempt_in_transaction(
        self,
        replayed: GenerationAttempt,
        *,
        external_response: ExternalResponseReference | None = None,
    ) -> None:
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
        prior_execution = self.execution_state()
        counts = dict(prior_execution.status_counts)
        if replayed.event_id in prior_execution.event_ids:
            prior_statuses = [
                status.value
                for status in EventStatus
                if status is not EventStatus.SUCCEEDED and counts[status.value] > 0
            ]
            if len(prior_statuses) != 1:
                raise ValueError("execution state current attempt status is ambiguous")
            counts[prior_statuses[0]] -= 1
            event_ids = prior_execution.event_ids
        else:
            event_ids = prior_execution.event_ids + (replayed.event_id,)
        counts[replayed.status.value] += 1
        transition_execution = ExecutionState(
            schema_version=prior_execution.schema_version,
            run_id=prior_execution.run_id,
            baseline_manifest_hash=prior_execution.baseline_manifest_hash,
            status=ExecutionStatus.RUNNING,
            next_event_ordinal=prior_execution.next_event_ordinal,
            expected_event_count=prior_execution.expected_event_count,
            current_event_id=replayed.event_id,
            event_ids=event_ids,
            status_counts=counts,
            failed_event_ids=(),
        )
        if transition_index == 1:
            self._assert_retry_authorized(replayed.event_id, replayed.attempt_index)
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
        self._replace_execution_state(transition_execution)
        if replayed.status not in {EventStatus.FAILED, EventStatus.SUCCEEDED}:
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

    @staticmethod
    def _changed_request_parameter_paths(
        before: Mapping[str, object],
        after: Mapping[str, object],
        prefix: str = "request_parameters",
    ) -> set[str]:
        changed: set[str] = set()
        for key in set(before) | set(after):
            path = f"{prefix}.{key}"
            left = before.get(key, object())
            right = after.get(key, object())
            if isinstance(left, Mapping) and isinstance(right, Mapping):
                changed.update(RunStorage._changed_request_parameter_paths(left, right, path))
            elif left != right:
                changed.add(path)
        return changed

    def _insert_or_exact_match_evidence(
        self,
        table: str,
        key_name: str,
        key: str,
        payload: Mapping[str, object],
        record_hash: str,
        *,
        extra_columns: tuple[str, ...] = (),
        extra_values: tuple[object, ...] = (),
    ) -> None:
        if len(extra_columns) != len(extra_values):
            raise ValueError("evidence extra columns and values must have equal lengths")
        quoted_table = _quote_sql_identifier(table)
        quoted_key = _quote_sql_identifier(key_name)
        quoted_extras = tuple(_quote_sql_identifier(name) for name in extra_columns)
        selected = (*quoted_extras, '"payload"', '"record_hash"')
        existing = self._connection.execute(
            f"SELECT {', '.join(selected)} FROM {quoted_table} WHERE {quoted_key} = ?",
            (key,),
        ).fetchone()
        encoded = _canonical_json(payload)
        expected = (*extra_values, encoded, record_hash)
        if existing is not None:
            if existing != expected:
                raise ValueError(f"conflicting immutable {table} replay")
            return
        columns = (quoted_key, *quoted_extras, '"payload"', '"record_hash"')
        placeholders = ", ".join("?" for _ in columns)
        self._connection.execute(
            f"INSERT INTO {quoted_table} ({', '.join(columns)}) VALUES ({placeholders})",
            (key, *expected),
        )

    def record_prepared_attempt(
        self,
        event_input: EventInputEvidence,
        *,
        policy: MockAttemptPolicyBinding,
        adapter_binding: MockAdapterExecutionBinding,
        request_evidence: AdapterRequestEvidence,
        pending_attempt: GenerationAttempt,
    ) -> None:
        """Atomically land the immutable input/request prefix and one PENDING transition."""

        self._begin_write()
        try:
            self._record_prepared_attempt_in_transaction(
                event_input,
                policy=policy,
                adapter_binding=adapter_binding,
                request_evidence=request_evidence,
                pending_attempt=pending_attempt,
            )
            self._commit_write()
        except BaseException:
            self._connection.rollback()
            raise

    def _record_prepared_attempt_in_transaction(
        self,
        event_input: EventInputEvidence,
        *,
        policy: MockAttemptPolicyBinding,
        adapter_binding: MockAdapterExecutionBinding,
        request_evidence: AdapterRequestEvidence,
        pending_attempt: GenerationAttempt,
    ) -> None:

        from .execution_evidence import (
            AdapterRequestEvidence,
            EventInputEvidence,
            MockAttemptPolicyBinding,
            _has_trusted_adapter_request_evidence,
            _has_trusted_mock_adapter_execution_binding,
        )

        self._assert_not_halted()
        if self.binding.round0_root is None:
            raise ValueError("initial state must be sealed before preparing attempts")
        if not isinstance(event_input, EventInputEvidence):
            raise TypeError("event_input must be typed EventInputEvidence")
        if not isinstance(policy, MockAttemptPolicyBinding):
            raise TypeError("policy must be typed MockAttemptPolicyBinding")
        if not _has_trusted_mock_adapter_execution_binding(adapter_binding):
            raise ValueError("adapter binding must be a trusted pre-invocation capability")
        if not _has_trusted_adapter_request_evidence(request_evidence):
            raise ValueError("request evidence must preserve a trusted sealed request")
        if not isinstance(pending_attempt, GenerationAttempt):
            raise TypeError("pending_attempt must be typed GenerationAttempt")
        pending = GenerationAttempt.from_payload(pending_attempt.to_payload())
        if pending.status is not EventStatus.PENDING:
            raise ValueError("prepared attempt must be PENDING")
        journal = self.current_event_journal()
        slot = self.schedule_slot(journal.event_ordinal)
        request = request_evidence.request
        if (
            journal.event_id is None
            or journal.event_id != event_input.event_id
            or journal.event_id != request_evidence.event_id
            or journal.next_attempt_index != request_evidence.attempt_index
            or event_input.receiver_agent_id != slot.agent_id
            or event_input.publish_flag != slot.publish_flag
            or event_input.exposure_record.exposure_mode != self.binding.expected_exposure_mode
            or event_input.exposure_record.exposure_graph_hash
            != self.binding.expected_exposure_graph_hash
        ):
            raise ValueError("prepared evidence does not bind the current journal and schedule")
        if (
            request.prompt_view_id != event_input.prompt_view.view_id
            or request.prompt_view_hash != event_input.prompt_view.record_hash
            or request.rendered_messages_hash != pending.rendered_prompt_hash
            or request.rendered_messages != pending.rendered_messages
            or pending.exposure_id != event_input.exposure_record.exposure_id
            or request_evidence.prompt_limits_hash != event_input.prompt_view.limits_hash
            or request_evidence.parser_limits_hash != event_input.parser_limits.record_hash
            or request_evidence.attempt_policy_hash != policy.record_hash
            or request_evidence.adapter_execution_binding_hash != adapter_binding.record_hash
            or request_evidence.model_identity_hash != adapter_binding.model_identity_hash
        ):
            raise ValueError("prepared event, prompt, parser, policy, or binding hash drifted")
        pending_links = (
            pending.event_id,
            pending.attempt_id,
            pending.attempt_index,
            pending.request_id,
            pending.request_parameters,
            pending.request_parameters_hash,
            pending.model_identity,
            pending.model_identity_hash,
            pending.model_seed,
        )
        request_links = (
            request_evidence.event_id,
            request_evidence.attempt_id,
            request_evidence.attempt_index,
            request_evidence.request_id,
            request_evidence.request_parameters,
            request_evidence.request_parameters_hash,
            request_evidence.model_identity,
            request_evidence.model_identity_hash,
            request_evidence.model_seed,
        )
        if pending_links != request_links:
            raise ValueError("PENDING attempt does not exactly bind request authorization")
        binding_rows = self._connection.execute(
            "SELECT binding_id, payload, record_hash FROM adapter_execution_bindings"
        ).fetchall()
        expected_binding_row = (
            adapter_binding.binding_id,
            _canonical_json(adapter_binding.to_payload()),
            adapter_binding.record_hash,
        )
        if binding_rows and (len(binding_rows) != 1 or binding_rows[0] != expected_binding_row):
            raise ValueError("one run requires one exact adapter attestation")
        prior_row = self._connection.execute(
            """SELECT payload FROM adapter_requests
               WHERE event_id = ? ORDER BY rowid DESC LIMIT 1""",
            (event_input.event_id,),
        ).fetchone()
        if prior_row is not None:
            prior = AdapterRequestEvidence.from_payload(
                _load_canonical_json(prior_row[0], "adapter request evidence")
            )
            invariant = (
                prior.request.topic_package_id,
                prior.request.topic_package_hash,
                prior.request.prompt_view_id,
                prior.request.prompt_view_hash,
                prior.request.rendered_messages,
                prior.request.rendered_messages_hash,
                prior.model_identity,
                prior.model_identity_hash,
                prior.prompt_limits_hash,
                prior.parser_limits_hash,
                prior.attempt_policy_hash,
                prior.adapter_execution_binding_hash,
            )
            current = (
                request.topic_package_id,
                request.topic_package_hash,
                request.prompt_view_id,
                request.prompt_view_hash,
                request.rendered_messages,
                request.rendered_messages_hash,
                request_evidence.model_identity,
                request_evidence.model_identity_hash,
                request_evidence.prompt_limits_hash,
                request_evidence.parser_limits_hash,
                request_evidence.attempt_policy_hash,
                request_evidence.adapter_execution_binding_hash,
            )
            if invariant != current:
                raise ValueError("retry request changed invariant evidence")
            changed = self._changed_request_parameter_paths(
                prior.request_parameters, request_evidence.request_parameters
            )
            if prior.model_seed != request_evidence.model_seed:
                changed.add("model_seed")
            if not changed.issubset(set(policy.allowed_difference_fields)):
                raise ValueError("retry request changed an unauthorized field")
        self._insert_or_exact_match_evidence(
            "event_input_evidence",
            "event_id",
            event_input.event_id,
            event_input.to_payload(),
            event_input.record_hash,
        )
        self._insert_or_exact_match_evidence(
            "attempt_policy_evidence",
            "event_id",
            event_input.event_id,
            policy.to_payload(),
            policy.record_hash,
        )
        self._insert_or_exact_match_evidence(
            "adapter_execution_bindings",
            "binding_id",
            adapter_binding.binding_id,
            adapter_binding.to_payload(),
            adapter_binding.record_hash,
        )
        self._insert_or_exact_match_evidence(
            "adapter_requests",
            "attempt_id",
            request_evidence.attempt_id,
            request_evidence.to_payload(),
            request_evidence.record_hash,
            extra_columns=(
                "event_id",
                "adapter_binding_hash",
                "parser_limits_hash",
                "policy_hash",
            ),
            extra_values=(
                event_input.event_id,
                adapter_binding.record_hash,
                event_input.parser_limits.record_hash,
                policy.record_hash,
            ),
        )
        has_landed = self._connection.execute(
            "SELECT 1 FROM attempt_transitions WHERE attempt_id = ?",
            (pending.attempt_id,),
        ).fetchone()
        if has_landed:
            landed = self.attempt_transitions(pending.attempt_id)
            if landed != (pending,):
                raise ValueError("conflicting PENDING attempt replay")
        else:
            self._append_attempt_in_transaction(pending)

    def _read_evidence_payload(
        self,
        table: str,
        key_name: str,
        key: str,
        *,
        payload_key: str | None = None,
    ) -> tuple[dict[str, object], str] | None:
        row = self._connection.execute(
            f"SELECT {key_name}, payload, record_hash FROM {table} WHERE {key_name} = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        payload = _load_canonical_json(row[1], table)
        if (
            row[0] != key
            or payload.get("record_hash") != row[2]
            or (payload_key is not None and payload.get(payload_key) != row[0])
        ):
            raise ValueError(f"{table} row key or hash does not match typed payload")
        return payload, row[2]

    def event_input_evidence(self, event_id: str) -> EventInputEvidence | None:
        from .execution_evidence import EventInputEvidence

        _require_id("event_id", event_id)
        row = self._read_evidence_payload(
            "event_input_evidence", "event_id", event_id, payload_key="event_id"
        )
        return None if row is None else EventInputEvidence.from_payload(row[0])

    def attempt_policy_evidence(self, event_id: str) -> MockAttemptPolicyBinding | None:
        from .execution_evidence import MockAttemptPolicyBinding

        _require_id("event_id", event_id)
        row = self._read_evidence_payload("attempt_policy_evidence", "event_id", event_id)
        return None if row is None else MockAttemptPolicyBinding.from_payload(row[0])

    def adapter_execution_binding(
        self, binding_id_or_attempt_id: str
    ) -> MockAdapterExecutionBinding | None:
        from .execution_evidence import MockAdapterExecutionBinding

        _require_id("binding_id_or_attempt_id", binding_id_or_attempt_id)
        row = self._read_evidence_payload(
            "adapter_execution_bindings",
            "binding_id",
            binding_id_or_attempt_id,
            payload_key="binding_id",
        )
        if row is None:
            linked = self._connection.execute(
                "SELECT adapter_binding_hash FROM adapter_requests WHERE attempt_id = ?",
                (binding_id_or_attempt_id,),
            ).fetchone()
            if linked is None:
                return None
            raw = self._connection.execute(
                """SELECT binding_id, payload, record_hash
                   FROM adapter_execution_bindings WHERE record_hash = ?""",
                (linked[0],),
            ).fetchone()
            if raw is None:
                raise ValueError("adapter request binding row is missing")
            payload = _load_canonical_json(raw[1], "adapter execution binding")
            if (
                payload.get("binding_id") != raw[0]
                or payload.get("record_hash") != raw[2]
                or raw[2] != linked[0]
            ):
                raise ValueError("adapter execution binding row envelope mismatch")
            row = (payload, raw[2])
        return MockAdapterExecutionBinding.from_payload(row[0])

    def adapter_request_evidence(self, attempt_id: str) -> AdapterRequestEvidence | None:
        from .execution_evidence import AdapterRequestEvidence

        _require_id("attempt_id", attempt_id)
        row = self._connection.execute(
            """SELECT attempt_id, event_id, adapter_binding_hash, parser_limits_hash,
                      policy_hash, payload, record_hash
               FROM adapter_requests WHERE attempt_id = ?""",
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        payload = _load_canonical_json(row[5], "adapter request evidence")
        value = AdapterRequestEvidence.from_payload(payload)
        if (
            row[0] != attempt_id
            or value.attempt_id != row[0]
            or value.event_id != row[1]
            or value.adapter_execution_binding_hash != row[2]
            or value.parser_limits_hash != row[3]
            or value.attempt_policy_hash != row[4]
            or value.record_hash != row[6]
        ):
            raise ValueError("adapter request row envelope columns drifted")
        return value

    def record_invocation_evidence(self, evidence: PersistedInvocationEvidence) -> None:
        from .adapters.base import _has_trusted_response_seal
        from .adapters.mock import _validate_mock_response_against_binding
        from .execution_evidence import PersistedInvocationEvidence

        self._assert_not_halted()
        if not isinstance(evidence, PersistedInvocationEvidence):
            raise TypeError("invocation evidence must be typed PersistedInvocationEvidence")
        if not _has_trusted_response_seal(evidence.response):
            raise ValueError("invocation evidence requires a trusted sealed adapter response")
        journal = self.current_event_journal()
        if (
            journal.latest_transition is None
            or journal.latest_transition.status is not EventStatus.IN_PROGRESS
            or journal.latest_transition.attempt_id != evidence.attempt_id
        ):
            raise ValueError("invocation evidence requires the current IN_PROGRESS attempt")
        request = self.adapter_request_evidence(evidence.attempt_id)
        binding = self.adapter_execution_binding(evidence.attempt_id)
        if request is None or binding is None:
            raise ValueError("invocation evidence requires persisted request and binding evidence")
        if (
            evidence.request_id != request.request_id
            or evidence.request_hash != request.request_hash
            or evidence.parser_limits_hash != request.parser_limits_hash
            or evidence.attempt_policy_hash != request.attempt_policy_hash
            or evidence.adapter_execution_binding_hash != request.adapter_execution_binding_hash
            or evidence.response.event_id != request.event_id
            or evidence.response.attempt_index != request.attempt_index
            or evidence.response.model_identity_hash != request.model_identity_hash
            or evidence.response.mock_seed != request.model_seed
        ):
            raise ValueError("invocation request, policy, parser, or binding evidence drifted")
        _validate_mock_response_against_binding(
            request=request.request,
            response=evidence.response,
            binding=binding,
        )
        evidence_payload = evidence.to_payload()
        encoded = _canonical_json(evidence_payload)
        execution = _canonical_json(evidence_payload["execution_payload"])
        self._begin_write()
        try:
            existing = self._connection.execute(
                """SELECT response_payload, execution_payload, record_hash
                   FROM invocation_evidence WHERE attempt_id = ?""",
                (evidence.attempt_id,),
            ).fetchone()
            expected = (encoded, execution, evidence.record_hash)
            if existing is None:
                self._connection.execute(
                    """INSERT INTO invocation_evidence
                       (attempt_id, response_payload, execution_payload, record_hash)
                       VALUES (?, ?, ?, ?)""",
                    (evidence.attempt_id, *expected),
                )
            elif existing != expected:
                raise ValueError("conflicting immutable invocation evidence replay")
            self._commit_write()
        except BaseException:
            self._connection.rollback()
            raise

    def invocation_evidence(self, attempt_id: str) -> PersistedInvocationEvidence | None:
        from .execution_evidence import PersistedInvocationEvidence

        _require_id("attempt_id", attempt_id)
        row = self._connection.execute(
            """SELECT attempt_id, response_payload, execution_payload, record_hash
               FROM invocation_evidence WHERE attempt_id = ?""",
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        payload = _load_canonical_json(row[1], "invocation evidence")
        execution = _load_canonical_json(row[2], "invocation execution evidence")
        if (
            row[0] != attempt_id
            or payload.get("attempt_id") != row[0]
            or payload.get("record_hash") != row[3]
            or payload.get("execution_payload") != execution
        ):
            raise ValueError("invocation evidence row envelope is inconsistent")
        return PersistedInvocationEvidence.from_payload(payload)

    def parse_evidence(self, attempt_id: str) -> ParseEvidence | ParseNotApplicableEvidence | None:
        from .execution_evidence import ParseNotApplicableEvidence
        from .parser import ParseEvidence

        _require_id("attempt_id", attempt_id)
        row = self._connection.execute(
            """SELECT attempt_id, kind, payload, record_hash
               FROM parse_evidence WHERE attempt_id = ?""",
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        payload = _load_canonical_json(row[2], "parse evidence")
        if (
            row[0] != attempt_id
            or payload.get("attempt_id") != row[0]
            or payload.get("record_hash") != row[3]
        ):
            raise ValueError("parse evidence row envelope mismatch")
        if row[1] == "parsed":
            parsed = payload.get("parsed")
            if parsed is not None:
                if type(parsed) is not dict:
                    raise TypeError("parsed response evidence must be a JSON object")
                payload["parsed"] = {
                    name: parsed.get(name)
                    for name in (
                        "topic_package_id",
                        "topic_package_hash",
                        "stance",
                        "confidence",
                        "public_reason",
                    )
                }
            return ParseEvidence.from_payload(payload)
        if row[1] == "not_applicable":
            if payload.get("schema_version") != "paper1.parse-not-applicable-evidence.v1":
                raise ValueError("parse evidence row kind does not match typed payload")
            return ParseNotApplicableEvidence.from_payload(payload)
        raise ValueError("parse evidence row kind is unsupported")

    def _insert_terminal_failure_in_transaction(
        self, evidence: TerminalFailureEvidence, terminal: GenerationAttempt
    ) -> None:
        if not isinstance(evidence, TerminalFailureEvidence):
            raise TypeError("terminal failure evidence must be typed")
        chain = self.causal_evidence_prefix()
        expected_previous = None if not chain else chain[-1].payload_hash
        expected_id_payload = {
            key: value for key, value in evidence.to_payload().items() if key != "evidence_id"
        }
        if (
            evidence.evidence_sequence != len(chain) + 1
            or evidence.previous_evidence_hash != expected_previous
            or evidence.evidence_kind != "failure"
            or evidence.run_id != self.binding.run_id
            or evidence.event_id != terminal.event_id
            or evidence.event_ordinal != self.progress.next_event_ordinal
            or evidence.attempt_id != terminal.attempt_id
            or evidence.attempt_index != terminal.attempt_index
            or evidence.terminal_transition_hash != canonical_payload_hash(terminal.to_payload())
            or evidence.terminal_attempt_hash != evidence.terminal_transition_hash
            or evidence.evidence_id != "halt-" + canonical_payload_hash(expected_id_payload)
        ):
            raise ValueError("terminal failure evidence causal envelope is inconsistent")
        self._insert_payload(
            "terminal_failures",
            (
                "evidence_id",
                "evidence_sequence",
                "previous_evidence_hash",
                "evidence_kind",
                "event_id",
                "event_ordinal",
                "attempt_id",
                "attempt_index",
                "terminal_transition_hash",
            ),
            (
                evidence.evidence_id,
                evidence.evidence_sequence,
                evidence.previous_evidence_hash,
                evidence.evidence_kind,
                evidence.event_id,
                evidence.event_ordinal,
                evidence.attempt_id,
                evidence.attempt_index,
                evidence.terminal_transition_hash,
            ),
            evidence.to_payload(),
        )
        prior = self.execution_state()
        if (
            prior.current_event_id != terminal.event_id
            or prior.status_counts[EventStatus.FAILED.value] != 1
        ):
            raise ValueError("execution state does not bind failed terminal attempt")
        self._replace_execution_state(
            ExecutionState(
                schema_version=prior.schema_version,
                run_id=prior.run_id,
                baseline_manifest_hash=prior.baseline_manifest_hash,
                status=ExecutionStatus.FAILED,
                next_event_ordinal=prior.next_event_ordinal,
                expected_event_count=prior.expected_event_count,
                current_event_id=prior.current_event_id,
                event_ids=prior.event_ids,
                status_counts=prior.status_counts,
                failed_event_ids=(terminal.event_id,),
            )
        )

    def record_finalized_attempt(self, evidence: FinalizedAttemptEvidence) -> None:
        from .execution_evidence import (
            FinalizedAttemptEvidence,
            ParseNotApplicableEvidence,
        )

        if not isinstance(evidence, FinalizedAttemptEvidence):
            raise TypeError("finalized evidence must be typed FinalizedAttemptEvidence")
        terminal = GenerationAttempt.from_payload(evidence.attempt.to_payload())
        journal = self.current_event_journal()
        invocation = self.invocation_evidence(terminal.attempt_id)
        request = self.adapter_request_evidence(terminal.attempt_id)
        if invocation is None or request is None:
            raise ValueError("finalization requires request and invocation evidence")
        already_terminal = journal.latest_transition == terminal
        if not already_terminal and (
            journal.latest_transition is None
            or journal.latest_transition.status is not EventStatus.IN_PROGRESS
            or journal.latest_transition.attempt_id != terminal.attempt_id
        ):
            raise ValueError("finalization requires the current exact IN_PROGRESS attempt")
        parse = evidence.parse_evidence
        if (
            evidence.request_hash != request.request_hash
            or invocation.request_hash != request.request_hash
            or invocation.response_id != parse.response_id
            or invocation.response_hash != parse.response_hash
            or parse.request_id != request.request_id
            or parse.request_hash != request.request_hash
            or parse.parser_limits_hash != request.parser_limits_hash
        ):
            raise ValueError("finalized request, response, parse, or parser links drifted")
        _validate_terminal_execution_projection(terminal, invocation, parse)
        if already_terminal:
            landed_parse = self.parse_evidence(terminal.attempt_id)
            failure_row = self._connection.execute(
                """SELECT attempt_id, payload_json, payload_hash FROM terminal_failures
                   WHERE attempt_id = ?""",
                (terminal.attempt_id,),
            ).fetchone()
            landed_failure = None
            if failure_row is not None:
                failure_payload = _load_canonical_json(failure_row[1], "terminal failure replay")
                if (
                    failure_row[0] != terminal.attempt_id
                    or canonical_payload_hash(failure_payload) != failure_row[2]
                ):
                    raise ValueError("terminal failure replay row envelope is inconsistent")
                landed_failure = TerminalFailureEvidence.from_payload(failure_payload)
                if landed_failure.attempt_id != failure_row[0]:
                    raise ValueError("terminal failure replay attempt identity drifted")
            if landed_parse != parse or landed_failure != evidence.terminal_failure_evidence:
                raise ValueError("conflicting finalized attempt replay")
            return
        kind = "not_applicable" if isinstance(parse, ParseNotApplicableEvidence) else "parsed"
        parse_payload = parse.to_payload()
        self._begin_write()
        try:
            existing = self._connection.execute(
                "SELECT kind, payload, record_hash FROM parse_evidence WHERE attempt_id = ?",
                (terminal.attempt_id,),
            ).fetchone()
            expected = (kind, _canonical_json(parse_payload), parse.record_hash)
            if existing is None:
                self._connection.execute(
                    """INSERT INTO parse_evidence (attempt_id, kind, payload, record_hash)
                       VALUES (?, ?, ?, ?)""",
                    (terminal.attempt_id, *expected),
                )
            elif existing != expected:
                raise ValueError("conflicting immutable parse evidence replay")
            self._append_attempt_in_transaction(terminal)
            if terminal.status is EventStatus.FAILED:
                failure = evidence.terminal_failure_evidence
                if failure is None:
                    raise ValueError("FAILED finalization requires terminal failure evidence")
                self._insert_terminal_failure_in_transaction(failure, terminal)
            elif evidence.terminal_failure_evidence is not None:
                raise ValueError("SUCCEEDED finalization forbids failure evidence")
            self._commit_write()
        except BaseException:
            self._connection.rollback()
            raise

    def evidence_references(self, event_id: str) -> EventEvidenceReferences:
        from .execution_evidence import EventEvidenceReferences

        _require_id("event_id", event_id)
        event_input = self.event_input_evidence(event_id)
        request_row = self._connection.execute(
            """SELECT ar.attempt_id FROM adapter_requests ar
               JOIN attempt_transitions at ON at.attempt_id = ar.attempt_id
               WHERE ar.event_id = ?
               ORDER BY at.attempt_index DESC LIMIT 1""",
            (event_id,),
        ).fetchone()
        request = None if request_row is None else self.adapter_request_evidence(request_row[0])
        invocation = None if request is None else self.invocation_evidence(request.attempt_id)
        parsed = None if request is None else self.parse_evidence(request.attempt_id)
        terminal_row = (
            None
            if request is None
            else self._connection.execute(
                """SELECT attempt_id, payload_json, payload_hash FROM attempts
                   WHERE event_id = ? AND attempt_id = ?""",
                (event_id, request.attempt_id),
            ).fetchone()
        )
        terminal = None
        terminal_hash = None
        if terminal_row is not None:
            terminal = GenerationAttempt.from_payload(
                _load_canonical_json(terminal_row[1], "terminal attempt")
            )
            terminal_hash = terminal_row[2]
            if (
                terminal.attempt_id != terminal_row[0]
                or canonical_payload_hash(terminal.to_payload()) != terminal_hash
            ):
                raise ValueError("terminal attempt row envelope is inconsistent")
        committed_row = self._connection.execute(
            "SELECT event_id, payload_json, payload_hash FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        committed = None
        committed_hash = None
        if committed_row is not None:
            committed = GenerationEvent.from_payload(
                _load_canonical_json(committed_row[1], "committed event")
            )
            committed_hash = committed_row[2]
            if (
                committed.event_id != committed_row[0]
                or canonical_payload_hash(committed.to_payload()) != committed_hash
            ):
                raise ValueError("committed event row envelope is inconsistent")
        return EventEvidenceReferences.create(
            event_input_evidence_id=(None if event_input is None else event_input.evidence_id),
            event_input_evidence_hash=(None if event_input is None else event_input.record_hash),
            request_id=None if request is None else request.request_id,
            request_hash=None if request is None else request.request_hash,
            invocation_evidence_id=(None if invocation is None else invocation.evidence_id),
            invocation_evidence_hash=(None if invocation is None else invocation.record_hash),
            parse_evidence_id=(
                None if parsed is None else getattr(parsed, "evidence_id", parsed.attempt_id)
            ),
            parse_evidence_hash=None if parsed is None else parsed.record_hash,
            terminal_attempt_id=None if terminal is None else terminal.attempt_id,
            terminal_attempt_hash=terminal_hash,
            committed_event_id=None if committed is None else committed.event_id,
            committed_event_hash=committed_hash,
        )

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
        self._begin_write()
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
            self._commit_write()
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
        self._begin_write()
        try:
            self._connection.execute(
                "UPDATE binding SET round0_root = ? WHERE singleton = 1 AND round0_root IS NULL",
                (round0_root,),
            )
            self._connection.execute(
                "UPDATE progress SET event_chain_head = ? WHERE singleton = 1",
                (genesis,),
            )
            self._commit_write()
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
        self._assert_not_halted()
        records = (event, final_attempt, private_update, private_state, feed_cursor)
        types = (GenerationEvent, GenerationAttempt, PrivateUpdate, PrivateState, FeedCursor)
        if any(not isinstance(value, expected) for value, expected in zip(records, types)):
            raise TypeError("success commit requires typed event, attempt, and state records")
        replayed_event = GenerationEvent.from_payload(event.to_payload())
        replayed_attempt = GenerationAttempt.from_payload(final_attempt.to_payload())
        replayed_update = PrivateUpdate.from_payload(private_update.to_payload())
        replayed_state = PrivateState.from_payload(private_state.to_payload())
        replayed_cursor = FeedCursor.from_payload(feed_cursor.to_payload())
        progress = self.progress
        ordinal = progress.next_event_ordinal
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
        prior_execution = self.execution_state()
        counts = dict(prior_execution.status_counts)
        if (
            prior_execution.event_ids[-1:] != (replayed_event.event_id,)
            or counts[EventStatus.SUCCEEDED.value] != ordinal + 1
        ):
            raise ValueError("execution state does not bind succeeded attempt before commit")
        new_ordinal = ordinal + 1
        execution = ExecutionState(
            schema_version=prior_execution.schema_version,
            run_id=prior_execution.run_id,
            baseline_manifest_hash=prior_execution.baseline_manifest_hash,
            status=(
                ExecutionStatus.COMPLETE
                if new_ordinal == progress.expected_event_count
                else ExecutionStatus.RUNNING
            ),
            next_event_ordinal=new_ordinal,
            expected_event_count=progress.expected_event_count,
            current_event_id=(
                None
                if new_ordinal == progress.expected_event_count
                else derive_event_id(self.binding.run_id, new_ordinal)
            ),
            event_ids=prior_execution.event_ids,
            status_counts=counts,
            failed_event_ids=prior_execution.failed_event_ids,
        )
        self._begin_write()
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
            self._replace_execution_state(execution)
            self._commit_write()
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

    def private_updates_for_agent(self, agent_id: str) -> tuple[PrivateUpdate, ...]:
        """Strictly replay one agent's full private history, including round 0."""

        _require_id("agent_id", agent_id)
        rows = self._connection.execute(
            """SELECT event_ordinal, payload_json, payload_hash FROM private_updates
               WHERE agent_id = ?
               ORDER BY CASE WHEN event_ordinal IS NULL THEN -1 ELSE event_ordinal END""",
            (agent_id,),
        ).fetchall()
        if not rows:
            raise ValueError("agent has no round-0 private update")
        values: list[PrivateUpdate] = []
        previous_state: PrivateState | None = None
        for index, (event_ordinal, payload_json, payload_hash) in enumerate(rows):
            payload = _load_canonical_json(payload_json, "private update history")
            if canonical_payload_hash(payload) != payload_hash:
                raise ValueError("stored private update history hash does not match")
            value = PrivateUpdate.from_payload(payload)
            if value.agent_id != agent_id or value.sequence_index != index:
                raise ValueError("private update sequence is not strictly continuous")
            if index == 0:
                if event_ordinal is not None or value.event_ordinal is not None:
                    raise ValueError("private update history must begin at round 0")
            else:
                event = self.event_at(event_ordinal)
                if (
                    event_ordinal != value.event_ordinal
                    or event is None
                    or event.event_id != value.event_id
                    or event.agent_id != value.agent_id
                ):
                    raise ValueError("private update history lacks a committed event")
            previous_state = PrivateState.from_update(
                value, previous=previous_state, mock_only=True
            )
            values.append(value)
        current = self.private_state(agent_id)
        if current != previous_state:
            raise ValueError("private update history does not replay current private state")
        return tuple(values)

    def _assert_not_halted(self) -> None:
        chain = self.causal_evidence_prefix()
        if chain and isinstance(chain[-1], TerminalFailureEvidence):
            raise ValueError("run is halted by append-only terminal failure evidence")

    def terminal_failure_evidence(self) -> TerminalFailureEvidence | None:
        prefix = self.terminal_failure_evidence_prefix()
        return None if not prefix else prefix[-1]

    def terminal_failure_evidence_prefix(self) -> tuple[TerminalFailureEvidence, ...]:
        rows = self._connection.execute(
            """SELECT payload_json, payload_hash FROM terminal_failures
               ORDER BY evidence_sequence"""
        ).fetchall()
        values: list[TerminalFailureEvidence] = []
        for row in rows:
            payload = _load_canonical_json(row[0], "terminal failure")
            if canonical_payload_hash(payload) != row[1]:
                raise ValueError("terminal failure payload hash does not match")
            values.append(TerminalFailureEvidence.from_payload(payload))  # type: ignore[arg-type]
        return tuple(values)

    def resume_authorization_evidence(self) -> ResumeAuthorizationEvidence | None:
        prefix = self.resume_authorization_evidence_prefix()
        return None if not prefix else prefix[-1]

    def resume_authorization_evidence_prefix(
        self,
    ) -> tuple[ResumeAuthorizationEvidence, ...]:
        rows = self._connection.execute(
            """SELECT payload_json, payload_hash FROM resume_authorizations
               ORDER BY evidence_sequence"""
        ).fetchall()
        values: list[ResumeAuthorizationEvidence] = []
        for row in rows:
            payload = _load_canonical_json(row[0], "resume authorization")
            if canonical_payload_hash(payload) != row[1]:
                raise ValueError("resume authorization payload hash does not match")
            values.append(ResumeAuthorizationEvidence.from_payload(payload))  # type: ignore[arg-type]
        return tuple(values)

    def causal_evidence_prefix(
        self,
    ) -> tuple[TerminalFailureEvidence | ResumeAuthorizationEvidence, ...]:
        """Return the single hash-linked failure/authorization evidence chain."""

        values: list[TerminalFailureEvidence | ResumeAuthorizationEvidence] = [
            *self.terminal_failure_evidence_prefix(),
            *self.resume_authorization_evidence_prefix(),
        ]
        values.sort(key=lambda item: item.evidence_sequence)
        previous_hash: str | None = None
        for expected_sequence, item in enumerate(values, start=1):
            expected_type = (
                TerminalFailureEvidence
                if expected_sequence % 2 == 1
                else ResumeAuthorizationEvidence
            )
            if (
                item.evidence_sequence != expected_sequence
                or not isinstance(item, expected_type)
                or item.previous_evidence_hash != previous_hash
                or item.run_id != self.binding.run_id
                or item.event_id != derive_event_id(self.binding.run_id, item.event_ordinal)
            ):
                raise ValueError("causal evidence chain is discontinuous, forked, or reordered")
            if isinstance(item, ResumeAuthorizationEvidence) and (
                item.previous_terminal_failure_hash != item.previous_evidence_hash
                or expected_sequence < 2
                or not isinstance(values[expected_sequence - 2], TerminalFailureEvidence)
                or item.run_id != values[expected_sequence - 2].run_id
                or item.event_id != values[expected_sequence - 2].event_id
                or item.event_ordinal != values[expected_sequence - 2].event_ordinal
            ):
                raise ValueError("resume authorization does not bind preceding failure")
            previous_hash = item.payload_hash
        return tuple(values)

    def record_terminal_failure(
        self,
        *,
        event_id: str,
        reason: str,
        policy_evidence: Mapping[str, object],
        recorded_at: str,
    ) -> TerminalFailureEvidence:
        """Record a caller-authorized stop without choosing retry/timeout policy."""

        self._assert_not_halted()
        journal = self.current_event_journal()
        if journal.event_id != event_id or journal.latest_transition is None:
            raise ValueError("terminal failure must bind the current event attempt evidence")
        if journal.latest_transition.status is not EventStatus.FAILED:
            raise ValueError("terminal failure requires a failed terminal attempt")
        chain = self.causal_evidence_prefix()
        if chain and isinstance(chain[-1], TerminalFailureEvidence):
            raise ValueError("run is already halted by append-only failure evidence")
        if any(
            isinstance(item, TerminalFailureEvidence)
            and item.attempt_id == journal.latest_transition.attempt_id
            for item in chain
        ):
            raise ValueError("the failed attempt is already bound to terminal failure evidence")
        terminal_hash = canonical_payload_hash(journal.latest_transition.to_payload())
        payload_without_id = {
            "evidence_sequence": len(chain) + 1,
            "previous_evidence_hash": None if not chain else chain[-1].payload_hash,
            "evidence_kind": "failure",
            "run_id": self.binding.run_id,
            "event_id": event_id,
            "event_ordinal": journal.event_ordinal,
            "attempt_id": journal.latest_transition.attempt_id,
            "attempt_index": journal.latest_transition.attempt_index,
            "terminal_transition_hash": terminal_hash,
            "terminal_attempt_hash": terminal_hash,
            "reason": reason,
            "policy_evidence": dict(policy_evidence),
            "recorded_at": recorded_at,
        }
        evidence = TerminalFailureEvidence(
            evidence_id="halt-" + canonical_payload_hash(payload_without_id),
            **payload_without_id,  # type: ignore[arg-type]
        )
        previous = self.execution_state()
        counts = dict(previous.status_counts)
        if previous.event_ids[-1:] != (event_id,) or counts[EventStatus.FAILED.value] != 1:
            raise ValueError("execution state does not bind the failed current attempt")
        failed = ExecutionState(
            schema_version=previous.schema_version,
            run_id=previous.run_id,
            baseline_manifest_hash=previous.baseline_manifest_hash,
            status=ExecutionStatus.FAILED,
            next_event_ordinal=previous.next_event_ordinal,
            expected_event_count=previous.expected_event_count,
            current_event_id=event_id,
            event_ids=previous.event_ids,
            status_counts=counts,
            failed_event_ids=(event_id,),
        )
        self._begin_write()
        try:
            self._insert_payload(
                "terminal_failures",
                (
                    "evidence_id",
                    "evidence_sequence",
                    "previous_evidence_hash",
                    "evidence_kind",
                    "event_id",
                    "event_ordinal",
                    "attempt_id",
                    "attempt_index",
                    "terminal_transition_hash",
                ),
                (
                    evidence.evidence_id,
                    evidence.evidence_sequence,
                    evidence.previous_evidence_hash,
                    evidence.evidence_kind,
                    evidence.event_id,
                    evidence.event_ordinal,
                    evidence.attempt_id,
                    evidence.attempt_index,
                    evidence.terminal_transition_hash,
                ),
                evidence.to_payload(),
            )
            self._replace_execution_state(failed)
            self._commit_write()
        except BaseException:
            self._connection.rollback()
            raise
        return evidence

    def authorize_resume(
        self,
        *,
        authorization_id: str,
        event_id: str,
        previous_terminal_failure_hash: str,
        policy_evidence_id: str,
        policy_evidence_hash: str,
        authorized_at: str,
    ) -> ResumeAuthorizationEvidence:
        """Append external retry authorization without selecting retry policy."""

        failure = self.terminal_failure_evidence()
        if failure is None:
            raise ValueError("resume authorization requires terminal failure evidence")
        prior_authorization = self.resume_authorization_evidence()
        if (
            prior_authorization is not None
            and prior_authorization.previous_terminal_failure_hash == failure.payload_hash
        ):
            raise ValueError("resume authorization is append-only and already recorded")
        if event_id != failure.event_id or previous_terminal_failure_hash != failure.payload_hash:
            raise ValueError("resume authorization does not bind the terminal failure")
        chain = self.causal_evidence_prefix()
        if not chain or chain[-1].payload_hash != failure.payload_hash:
            raise ValueError("resume authorization must immediately follow terminal failure")
        evidence = ResumeAuthorizationEvidence(
            evidence_sequence=len(chain) + 1,
            previous_evidence_hash=failure.payload_hash,
            evidence_kind="authorization",
            authorization_id=authorization_id,
            run_id=self.binding.run_id,
            event_id=event_id,
            event_ordinal=failure.event_ordinal,
            previous_terminal_failure_hash=previous_terminal_failure_hash,
            policy_evidence_id=policy_evidence_id,
            policy_evidence_hash=policy_evidence_hash,
            authorized_at=authorized_at,
        )
        previous = self.execution_state()
        if (
            previous.status is not ExecutionStatus.FAILED
            or previous.current_event_id != event_id
            or previous.next_event_ordinal != failure.event_ordinal
            or previous.failed_event_ids != (event_id,)
        ):
            raise ValueError("execution state does not bind the halted event")
        resumed = ExecutionState(
            schema_version=previous.schema_version,
            run_id=previous.run_id,
            baseline_manifest_hash=previous.baseline_manifest_hash,
            status=ExecutionStatus.RUNNING,
            next_event_ordinal=previous.next_event_ordinal,
            expected_event_count=previous.expected_event_count,
            current_event_id=previous.current_event_id,
            event_ids=previous.event_ids,
            status_counts=previous.status_counts,
            failed_event_ids=(),
        )
        self._begin_write()
        try:
            self._insert_payload(
                "resume_authorizations",
                (
                    "authorization_id",
                    "evidence_sequence",
                    "previous_evidence_hash",
                    "evidence_kind",
                    "event_id",
                    "event_ordinal",
                    "previous_terminal_failure_hash",
                ),
                (
                    evidence.authorization_id,
                    evidence.evidence_sequence,
                    evidence.previous_evidence_hash,
                    evidence.evidence_kind,
                    evidence.event_id,
                    evidence.event_ordinal,
                    evidence.previous_terminal_failure_hash,
                ),
                evidence.to_payload(),
            )
            self._replace_execution_state(resumed)
            self._commit_write()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            raise ValueError("resume authorization is duplicate, forked, or append-only") from error
        except BaseException:
            self._connection.rollback()
            raise
        return evidence

    @contextmanager
    def consistent_read(self):  # type: ignore[no-untyped-def]
        """Pin all reads to one SQLite snapshot; never hold this across model calls."""

        owns_transaction = not self._connection.in_transaction
        if owns_transaction:
            self._connection.execute("BEGIN")
        try:
            yield self
        finally:
            if owns_transaction and self._connection.in_transaction:
                self._connection.rollback()

    def recovery_evidence(self, next_event_ordinal: int | None = None) -> Mapping[str, object]:
        with self.consistent_read():
            return self._recovery_evidence_snapshot(next_event_ordinal)

    def _recovery_evidence_snapshot(
        self, next_event_ordinal: int | None = None
    ) -> Mapping[str, object]:
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
        current_projection = ordinal == progress.next_event_ordinal
        execution_payload = self.execution_state().to_payload() if current_projection else None
        failure_prefix = tuple(
            item
            for item in self.terminal_failure_evidence_prefix()
            if item.event_ordinal <= ordinal
        )
        failure_hashes = {item.payload_hash for item in failure_prefix}
        authorization_prefix = tuple(
            item
            for item in self.resume_authorization_evidence_prefix()
            if item.previous_terminal_failure_hash in failure_hashes
        )
        causal_prefix = tuple(
            item for item in self.causal_evidence_prefix() if item.event_ordinal <= ordinal
        )
        terminal_item = causal_prefix[-1] if causal_prefix else None
        failure = (
            terminal_item
            if isinstance(terminal_item, TerminalFailureEvidence)
            and terminal_item.event_ordinal == ordinal
            else None
        )
        authorization = (
            terminal_item
            if isinstance(terminal_item, ResumeAuthorizationEvidence)
            and terminal_item.event_ordinal == ordinal
            else None
        )
        v6_evidence_hashes = self._v6_evidence_hashes_snapshot(ordinal)
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
                "execution_state": execution_payload,
                "terminal_failure": None if failure is None else failure.to_payload(),
                "resume_authorization": (
                    None if authorization is None else authorization.to_payload()
                ),
                "terminal_failure_prefix": tuple(item.to_payload() for item in failure_prefix),
                "resume_authorization_prefix": tuple(
                    item.to_payload() for item in authorization_prefix
                ),
                "causal_evidence_prefix": tuple(item.to_payload() for item in causal_prefix),
                "v6_evidence_hashes": v6_evidence_hashes,
                "v6_evidence_root": canonical_payload_hash(v6_evidence_hashes),
            }
        )  # type: ignore[return-value]

    def _v6_evidence_hashes_snapshot(self, ordinal: int) -> dict[str, tuple[str, ...]]:
        """Hash ordered v6 row hashes visible to a recovery projection."""

        event_ids = tuple(
            derive_event_id(self.binding.run_id, index)
            for index in range(
                min(ordinal + (ordinal < self.binding.schedule_count), self.binding.schedule_count)
            )
        )
        if not event_ids:
            selected: dict[str, list[str]] = {
                name: []
                for name in (
                    "event_input_evidence",
                    "attempt_policy_evidence",
                    "adapter_execution_bindings",
                    "adapter_requests",
                    "invocation_evidence",
                    "parse_evidence",
                )
            }
        else:
            selected = {}
            for table in ("event_input_evidence", "attempt_policy_evidence"):
                selected[table] = []
                for event_id in event_ids:
                    row = self._connection.execute(
                        f"""SELECT record_hash FROM {_quote_sql_identifier(table)}
                            WHERE event_id = ?""",
                        (event_id,),
                    ).fetchone()
                    if row is not None:
                        selected[table].append(row[0])
            request_rows: list[tuple[str, str, str]] = []
            for event_id in event_ids:
                request_rows.extend(
                    self._connection.execute(
                        """SELECT ar.attempt_id, ar.adapter_binding_hash, ar.record_hash
                           FROM adapter_requests ar
                           JOIN attempt_transitions at ON at.attempt_id = ar.attempt_id
                           WHERE ar.event_id = ? AND at.transition_index = 1
                           ORDER BY at.attempt_index""",
                        (event_id,),
                    ).fetchall()
                )
            attempt_ids = tuple(row[0] for row in request_rows)
            selected["adapter_requests"] = [row[2] for row in request_rows]
            binding_hashes = tuple(sorted({row[1] for row in request_rows}))
            selected["adapter_execution_bindings"] = (
                []
                if not binding_hashes
                else [
                    row[0]
                    for row in self._connection.execute(
                        f"""SELECT record_hash FROM adapter_execution_bindings
                            WHERE record_hash IN ({','.join('?' for _ in binding_hashes)})
                            ORDER BY binding_id""",
                        binding_hashes,
                    ).fetchall()
                ]
            )
            for table in ("invocation_evidence", "parse_evidence"):
                selected[table] = (
                    []
                    if not attempt_ids
                    else [
                        row[0]
                        for row in self._connection.execute(
                            f"""SELECT record_hash FROM {_quote_sql_identifier(table)}
                                WHERE attempt_id IN ({','.join('?' for _ in attempt_ids)})
                                ORDER BY attempt_id""",
                            attempt_ids,
                        ).fetchall()
                    ]
                )
        return {name: tuple(hashes) for name, hashes in selected.items()}

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
        execution = self.execution_state()
        failure_rows = self._connection.execute(
            """SELECT evidence_id, evidence_sequence, previous_evidence_hash, evidence_kind,
                      event_id, event_ordinal, attempt_id, attempt_index,
                      terminal_transition_hash, payload_json, payload_hash
               FROM terminal_failures ORDER BY evidence_sequence"""
        ).fetchall()
        failures: list[TerminalFailureEvidence] = []
        for row in failure_rows:
            (
                evidence_id,
                evidence_sequence,
                previous_evidence_hash,
                evidence_kind,
                event_id,
                event_ordinal,
                attempt_id,
                attempt_index,
                terminal_transition_hash,
                payload_json,
                payload_hash,
            ) = row
            payload = _load_canonical_json(payload_json, "terminal failure")
            if canonical_payload_hash(payload) != payload_hash:
                raise ValueError("terminal failure payload hash does not match")
            value = TerminalFailureEvidence.from_payload(payload)  # type: ignore[arg-type]
            if (
                evidence_id,
                evidence_sequence,
                previous_evidence_hash,
                evidence_kind,
                event_id,
                event_ordinal,
                attempt_id,
                attempt_index,
                terminal_transition_hash,
            ) != (
                value.evidence_id,
                value.evidence_sequence,
                value.previous_evidence_hash,
                value.evidence_kind,
                value.event_id,
                value.event_ordinal,
                value.attempt_id,
                value.attempt_index,
                value.terminal_transition_hash,
            ):
                raise ValueError("terminal failure row identity does not match typed payload")
            failures.append(value)
        authorization_rows = self._connection.execute(
            """SELECT authorization_id, evidence_sequence, previous_evidence_hash,
                      evidence_kind, event_id, event_ordinal,
                      previous_terminal_failure_hash, payload_json, payload_hash
               FROM resume_authorizations ORDER BY evidence_sequence"""
        ).fetchall()
        authorizations: list[ResumeAuthorizationEvidence] = []
        for (
            authorization_id,
            evidence_sequence,
            previous_evidence_hash,
            evidence_kind,
            event_id,
            event_ordinal,
            failure_hash,
            payload_json,
            payload_hash,
        ) in authorization_rows:
            payload = _load_canonical_json(payload_json, "resume authorization")
            if canonical_payload_hash(payload) != payload_hash:
                raise ValueError("resume authorization payload hash does not match")
            value = ResumeAuthorizationEvidence.from_payload(payload)  # type: ignore[arg-type]
            if (
                authorization_id,
                evidence_sequence,
                previous_evidence_hash,
                evidence_kind,
                event_id,
                event_ordinal,
                failure_hash,
            ) != (
                value.authorization_id,
                value.evidence_sequence,
                value.previous_evidence_hash,
                value.evidence_kind,
                value.event_id,
                value.event_ordinal,
                value.previous_terminal_failure_hash,
            ):
                raise ValueError("resume authorization row identity does not match typed payload")
            authorizations.append(value)
        causal_chain = self.causal_evidence_prefix()
        if tuple(
            item for item in causal_chain if isinstance(item, TerminalFailureEvidence)
        ) != tuple(failures) or tuple(
            item for item in causal_chain if isinstance(item, ResumeAuthorizationEvidence)
        ) != tuple(authorizations):
            raise ValueError("causal evidence chain does not exact-cover stored evidence")
        failure_by_hash = {value.payload_hash: value for value in failures}
        if len(failure_by_hash) != len(failures):
            raise ValueError("terminal failure evidence contains a duplicate or fork")
        authorization_by_failure: dict[str, ResumeAuthorizationEvidence] = {}
        for authorization in authorizations:
            failure = failure_by_hash.get(authorization.previous_terminal_failure_hash)
            if failure is None or (
                authorization.run_id != self.binding.run_id
                or authorization.event_id != failure.event_id
                or authorization.event_ordinal != failure.event_ordinal
                or authorization.previous_terminal_failure_hash in authorization_by_failure
            ):
                raise ValueError("resume authorization evidence is forked or lacks failure")
            authorization_by_failure[authorization.previous_terminal_failure_hash] = authorization
        last_halted_attempt_index: dict[str, int] = {}
        for failure in failures:
            if failure.run_id != self.binding.run_id or failure.event_id != derive_event_id(
                self.binding.run_id, failure.event_ordinal
            ):
                raise ValueError("terminal failure run does not match storage")
            attempt_match = self._connection.execute(
                """SELECT attempt_id, attempt_index, payload_hash FROM attempts
                   WHERE event_id = ? AND status = ? AND attempt_id = ?
                         AND attempt_index = ? AND payload_hash = ?""",
                (
                    failure.event_id,
                    EventStatus.FAILED.value,
                    failure.attempt_id,
                    failure.attempt_index,
                    failure.terminal_attempt_hash,
                ),
            ).fetchone()
            if (
                attempt_match is None
                or failure.terminal_transition_hash != failure.terminal_attempt_hash
            ):
                raise ValueError("terminal failure does not bind a failed attempt")
            if failure.attempt_index <= last_halted_attempt_index.get(failure.event_id, 0):
                raise ValueError("terminal failure attempt indexes are not strictly increasing")
            last_halted_attempt_index[failure.event_id] = failure.attempt_index
            if failure.event_ordinal < progress.next_event_ordinal and (
                failure.payload_hash not in authorization_by_failure
            ):
                raise ValueError("committed progress crossed an unauthorized terminal failure")
            if failure.event_ordinal > progress.next_event_ordinal:
                raise ValueError("terminal failure is ahead of committed progress")
        succeeded_ids = tuple(
            derive_event_id(self.binding.run_id, index)
            for index in range(progress.next_event_ordinal)
        )
        expected_counts = {status.value: 0 for status in EventStatus}
        expected_counts[EventStatus.SUCCEEDED.value] = progress.succeeded_event_count
        expected_status = (
            ExecutionStatus.COMPLETE
            if progress.next_event_ordinal == progress.expected_event_count
            else ExecutionStatus.RUNNING
        )
        current_attempt_status = None
        current_event_id = None
        if expected_status is ExecutionStatus.RUNNING:
            current_event_id = derive_event_id(self.binding.run_id, progress.next_event_ordinal)
            latest_row = self._connection.execute(
                """SELECT status FROM attempt_transitions WHERE event_id = ?
                   ORDER BY attempt_index DESC, transition_index DESC LIMIT 1""",
                (current_event_id,),
            ).fetchone()
            if latest_row is not None:
                current_attempt_status = EventStatus(latest_row[0])
        current_failure = (
            causal_chain[-1]
            if causal_chain and isinstance(causal_chain[-1], TerminalFailureEvidence)
            else None
        )
        if current_failure is not None and (
            current_failure.event_id != current_event_id or current_attempt_status is None
        ):
            raise ValueError("terminal failure does not bind current event")
        if current_failure is not None and (
            current_failure.payload_hash not in authorization_by_failure
        ):
            if current_attempt_status is not EventStatus.FAILED:
                raise ValueError("unauthorized terminal failure was advanced")
            expected_status = ExecutionStatus.FAILED
        expected_ids = (
            succeeded_ids if current_attempt_status is None else succeeded_ids + (current_event_id,)  # type: ignore[arg-type]
        )
        if current_attempt_status is not None:
            expected_counts[current_attempt_status.value] += 1
        expected_failed_ids = (
            (current_event_id,)
            if current_failure is not None
            and current_failure.event_ordinal == progress.next_event_ordinal
            and current_attempt_status is EventStatus.FAILED
            else ()
        )
        expected_current = None if expected_status is ExecutionStatus.COMPLETE else current_event_id
        if (
            execution.schema_version != "paper1.execution-state.v1"
            or execution.baseline_manifest_hash != self.binding.manifest_hash
            or execution.next_event_ordinal != progress.next_event_ordinal
            or execution.expected_event_count != progress.expected_event_count
            or execution.status is not expected_status
            or execution.current_event_id != expected_current
            or execution.event_ids != expected_ids
            or dict(execution.status_counts) != expected_counts
            or execution.failed_event_ids != expected_failed_ids
        ):
            raise ValueError("execution state does not replay from SQLite truth")
        rows = self._connection.execute(
            "SELECT event_ordinal FROM events ORDER BY event_ordinal"
        ).fetchall()
        ordinals = tuple(row[0] for row in rows)
        if ordinals != tuple(range(progress.next_event_ordinal)):
            raise ValueError("stored succeeded event prefix has a gap or duplicate")
        self._verify_attempt_exact_cover(progress)
        self._verify_retry_authorization_exact_cover()
        self._verify_v6_evidence_exact_cover()
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

    def _verify_v6_evidence_exact_cover(self) -> None:
        """Replay the opt-in v6 execution-evidence prefix from SQLite truth.

        Task 6 migrates the legacy lifecycle entry point to these tables.  Until
        then, a store with no v6 rows remains a valid legacy prefix; once any v6
        row lands, however, all six tables are an indivisible exact-cover graph.
        """

        tables = (
            "event_input_evidence",
            "attempt_policy_evidence",
            "adapter_execution_bindings",
            "adapter_requests",
            "invocation_evidence",
            "parse_evidence",
        )
        counts = {
            table: self._connection.execute(
                f"SELECT COUNT(*) FROM {_quote_sql_identifier(table)}"
            ).fetchone()[0]
            for table in tables
        }
        if not any(counts.values()):
            return

        transition_rows = self._connection.execute(
            """SELECT attempt_id, event_id, attempt_index, status
               FROM attempt_transitions
               ORDER BY event_id, attempt_index, transition_index"""
        ).fetchall()
        latest: dict[str, tuple[str, int, EventStatus]] = {}
        for attempt_id, event_id, attempt_index, status in transition_rows:
            latest[attempt_id] = (event_id, attempt_index, EventStatus(status))
        if not latest:
            raise ValueError("v6 evidence is orphaned from attempt transitions")
        expected_event_ids = {item[0] for item in latest.values()}
        event_ids = {
            row[0]
            for row in self._connection.execute(
                "SELECT event_id FROM event_input_evidence"
            ).fetchall()
        }
        policy_event_ids = {
            row[0]
            for row in self._connection.execute(
                "SELECT event_id FROM attempt_policy_evidence"
            ).fetchall()
        }
        request_attempt_ids = {
            row[0]
            for row in self._connection.execute("SELECT attempt_id FROM adapter_requests").fetchall()
        }
        if event_ids != expected_event_ids or policy_event_ids != expected_event_ids:
            raise ValueError("v6 event input and policy evidence are not exact-cover")
        if request_attempt_ids != set(latest):
            raise ValueError("v6 adapter request evidence is not exact-cover")
        if counts["adapter_execution_bindings"] != 1:
            raise ValueError("v6 adapter execution binding is not sole and exact-cover")

        binding_id = self._connection.execute(
            "SELECT binding_id FROM adapter_execution_bindings"
        ).fetchone()[0]
        binding = self.adapter_execution_binding(binding_id)
        if binding is None:
            raise ValueError("v6 adapter execution binding is missing")

        invocation_ids = {
            row[0]
            for row in self._connection.execute(
                "SELECT attempt_id FROM invocation_evidence"
            ).fetchall()
        }
        parse_ids = {
            row[0]
            for row in self._connection.execute("SELECT attempt_id FROM parse_evidence").fetchall()
        }
        if invocation_ids - request_attempt_ids or parse_ids - invocation_ids:
            raise ValueError("v6 invocation or parse evidence is orphaned")

        for event_id in sorted(expected_event_ids):
            event_input = self.event_input_evidence(event_id)
            policy = self.attempt_policy_evidence(event_id)
            if event_input is None or policy is None:
                raise ValueError("v6 event evidence cover is incomplete")
            if event_input.event_id != event_id:
                raise ValueError("v6 event input identity drifted")

        from .execution_evidence import FinalizedAttemptEvidence

        terminal_by_id: dict[str, GenerationAttempt] = {}
        for event_id in expected_event_ids:
            terminal_by_id.update(
                {item.attempt_id: item for item in self.attempts_for_event(event_id)}
            )
        failure_by_attempt = {
            item.attempt_id: item for item in self.terminal_failure_evidence_prefix()
        }
        for attempt_id, (event_id, attempt_index, status) in latest.items():
            request = self.adapter_request_evidence(attempt_id)
            event_input = self.event_input_evidence(event_id)
            policy = self.attempt_policy_evidence(event_id)
            if request is None or event_input is None or policy is None:
                raise ValueError("v6 request evidence cover is incomplete")
            if (
                request.event_id != event_id
                or request.attempt_index != attempt_index
                or request.attempt_policy_hash != policy.record_hash
                or request.parser_limits_hash != event_input.parser_limits.record_hash
                or request.adapter_execution_binding_hash != binding.record_hash
                or request.model_identity_hash != binding.model_identity_hash
            ):
                raise ValueError("v6 request evidence binding drifted")
            invocation = self.invocation_evidence(attempt_id)
            parsed = self.parse_evidence(attempt_id)
            terminal = terminal_by_id.get(attempt_id)
            if status is EventStatus.PENDING:
                if invocation is not None or parsed is not None or terminal is not None:
                    raise ValueError("PENDING v6 evidence prefix has future evidence")
                continue
            if status is EventStatus.IN_PROGRESS:
                if parsed is not None or terminal is not None:
                    raise ValueError("IN_PROGRESS v6 evidence prefix has terminal evidence")
                if invocation is None:
                    continue
            elif invocation is None or parsed is None or terminal is None:
                raise ValueError("terminal v6 evidence prefix is incomplete")
            if invocation is None:
                continue
            if (
                invocation.attempt_id != attempt_id
                or invocation.request_id != request.request_id
                or invocation.request_hash != request.request_hash
                or invocation.parser_limits_hash != request.parser_limits_hash
                or invocation.attempt_policy_hash != request.attempt_policy_hash
                or invocation.adapter_execution_binding_hash
                != request.adapter_execution_binding_hash
            ):
                raise ValueError("v6 invocation evidence binding drifted")
            if parsed is not None and (
                parsed.attempt_id != attempt_id
                or parsed.request_id != request.request_id
                or parsed.request_hash != request.request_hash
                or parsed.response_id != invocation.response_id
                or parsed.response_hash != invocation.response_hash
                or parsed.parser_limits_hash != request.parser_limits_hash
            ):
                raise ValueError("v6 parse evidence binding drifted")
            if terminal is not None and parsed is not None:
                _validate_terminal_execution_projection(terminal, invocation, parsed)
                failure = failure_by_attempt.get(attempt_id)
                FinalizedAttemptEvidence.create(
                    request_hash=request.request_hash,
                    attempt=terminal,
                    parse_evidence=parsed,
                    terminal_failure_evidence=failure,
                )

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
        if self._owned_lease is not None:
            self._owned_lease.release()
        self._connection.close()
        if self._database_identity_handle is not None:
            self._database_identity_handle.close()
            self._database_identity_handle = None

    def __enter__(self) -> RunStorage:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
