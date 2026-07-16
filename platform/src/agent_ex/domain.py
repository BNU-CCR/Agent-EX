"""Deeply immutable evidence records for reproducible simulation runs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_TERMINAL_VALUES = {"succeeded", "failed", "excluded", "imputed", "fallback"}
_ATTEMPT_VALUES = {"pending", "in_progress", "succeeded", "failed"}


def _require_id(field_name: str, value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string ID")
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty ID")


def _require_string(field_name: str, value: Any, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str):
        suffix = " or None" if optional else ""
        raise TypeError(f"{field_name} must be a string{suffix}")
    if not value:
        raise ValueError(f"{field_name} must not be empty")


def _require_int(field_name: str, value: Any, *, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")


def _require_stance(value: Any) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError("stance must be a finite number")
    if not math.isfinite(value):
        raise ValueError("stance must be a finite number")


def _require_tuple(field_name: str, value: Any) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")


def _require_sha256(field_name: str, value: Any, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 digest")


def _require_timestamp(field_name: str, value: Any, *, optional: bool = False) -> datetime | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 UTC timestamp")
    if "T" not in value or not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValueError(f"{field_name} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO-8601 UTC timestamp") from error
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be an ISO-8601 UTC timestamp")
    return parsed


def _freeze(value: Any) -> Any:
    """Copy and normalize the supported JSON-like evidence value subset."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("evidence floats must be finite JSON-like numbers")
        return value
    if isinstance(value, (bytes, bytearray)):
        raise TypeError("evidence values must be JSON-like; bytes are not supported")
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON-like mapping keys must be strings")
            if not key:
                raise ValueError("JSON-like mapping keys must not be empty")
            frozen[key] = _freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise TypeError("evidence values must be JSON-like; sets are not supported")
    raise TypeError(f"evidence values must be JSON-like; got {type(value).__name__}")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value


def canonical_payload_hash(value: Any) -> str:
    """Return the SHA-256 of a strictly JSON-like value's canonical encoding."""

    frozen = _freeze(value)
    encoded = json.dumps(
        _json_ready(frozen),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_payload_hash(field_name: str, digest: str | None, payload: Any) -> None:
    if digest != canonical_payload_hash(payload):
        raise ValueError(f"{field_name} does not match its canonical payload")


def _require_unique_ids(field_name: str, values: Any) -> None:
    _require_tuple(field_name, values)
    for value in values:
        _require_id(field_name[:-1] if field_name.endswith("s") else field_name, value)
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique IDs")


class EventStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXCLUDED = "excluded"
    IMPUTED = "imputed"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class OpinionRecord:
    agent_id: str
    round_index: int
    stance: float
    reason: str

    def __post_init__(self) -> None:
        _require_id("agent_id", self.agent_id)
        _require_int("round_index", self.round_index)
        _require_stance(self.stance)
        _require_string("reason", self.reason)


@dataclass(frozen=True, slots=True)
class AgentState:
    agent_id: str
    round_index: int
    stance: float
    reason: str
    opinion_history: tuple[OpinionRecord, ...]
    identity: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_id("agent_id", self.agent_id)
        _require_int("round_index", self.round_index)
        _require_stance(self.stance)
        _require_string("reason", self.reason)
        _require_tuple("opinion_history", self.opinion_history)
        if not all(isinstance(item, OpinionRecord) for item in self.opinion_history):
            raise TypeError("opinion_history must contain OpinionRecord values")
        if not isinstance(self.identity, Mapping):
            raise TypeError("identity must be a mapping")
        object.__setattr__(self, "opinion_history", tuple(self.opinion_history))
        object.__setattr__(self, "identity", _freeze(self.identity))


@dataclass(frozen=True, slots=True)
class ExposureRecord:
    exposure_id: str
    agent_id: str
    round_index: int
    exposure_mode: str
    source_agent_ids: tuple[str, ...]
    source_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_id("exposure_id", self.exposure_id)
        _require_id("agent_id", self.agent_id)
        _require_int("round_index", self.round_index)
        if self.exposure_mode not in {
            "self_history_only",
            "shuffled_social",
            "ws_neighbors",
        }:
            raise ValueError("exposure_mode is not a legal Paper 1 factor level")
        _require_unique_ids("source_agent_ids", self.source_agent_ids)
        _require_unique_ids("source_event_ids", self.source_event_ids)
        if len(self.source_agent_ids) != len(self.source_event_ids):
            raise ValueError("source_agent_ids and source_event_ids must be paired")
        if self.agent_id in self.source_agent_ids:
            raise ValueError("source_agent_ids cannot include the exposed agent")
        if self.exposure_mode == "self_history_only" and self.source_agent_ids:
            raise ValueError("self_history_only exposure cannot contain social sources")
        if self.exposure_mode != "self_history_only" and not self.source_agent_ids:
            raise ValueError("social exposure requires at least one paired source")


@dataclass(frozen=True, slots=True)
class GenerationAttempt:
    attempt_id: str
    event_id: str
    sequence: int
    status: EventStatus
    request_id: str
    provider_request_id: str | None
    exposure_ids: tuple[str, ...]
    rendered_messages: tuple[Mapping[str, object], ...]
    request_params: Mapping[str, object]
    rendered_prompt_hash: str
    exposure_hash: str
    raw_response: str | None
    raw_response_hash: str | None
    parsed_response: Mapping[str, object] | None
    parsed_result_hash: str | None
    usage: Mapping[str, object]
    finish_reason: str | None
    http_status: int | None
    error: Mapping[str, object] | None
    started_at: str | None
    finished_at: str | None

    def __post_init__(self) -> None:
        self._validate_common_fields()
        self._validate_status_contract()
        self._validate_response_hash_pairs()
        self._validate_payload_hashes()
        object.__setattr__(self, "exposure_ids", tuple(self.exposure_ids))
        object.__setattr__(self, "rendered_messages", _freeze(self.rendered_messages))
        object.__setattr__(self, "request_params", _freeze(self.request_params))
        object.__setattr__(self, "parsed_response", _freeze(self.parsed_response))
        object.__setattr__(self, "usage", _freeze(self.usage))
        object.__setattr__(self, "error", _freeze(self.error))

    def _validate_common_fields(self) -> None:
        for field_name in ("attempt_id", "event_id", "request_id"):
            _require_id(field_name, getattr(self, field_name))
        if self.provider_request_id is not None:
            _require_id("provider_request_id", self.provider_request_id)
        _require_int("sequence", self.sequence, minimum=1)
        if not isinstance(self.status, EventStatus):
            raise TypeError("status must be an EventStatus")
        if self.status.value not in _ATTEMPT_VALUES:
            raise ValueError("attempt status must be pending, in_progress, succeeded, or failed")
        _require_unique_ids("exposure_ids", self.exposure_ids)
        _require_tuple("rendered_messages", self.rendered_messages)
        if not all(isinstance(message, Mapping) for message in self.rendered_messages):
            raise TypeError("rendered_messages must contain mappings")
        for field_name in ("request_params", "usage"):
            if not isinstance(getattr(self, field_name), Mapping):
                raise TypeError(f"{field_name} must be a mapping")
        if self.parsed_response is not None and not isinstance(self.parsed_response, Mapping):
            raise TypeError("parsed_response must be a mapping or None")
        if self.error is not None and not isinstance(self.error, Mapping):
            raise TypeError("error must be a mapping or None")
        _require_sha256("rendered_prompt_hash", self.rendered_prompt_hash)
        _require_sha256("exposure_hash", self.exposure_hash)
        _require_sha256("raw_response_hash", self.raw_response_hash, optional=True)
        _require_sha256("parsed_result_hash", self.parsed_result_hash, optional=True)
        _require_string("raw_response", self.raw_response, optional=True)
        _require_string("finish_reason", self.finish_reason, optional=True)
        if self.http_status is not None:
            _require_int("http_status", self.http_status, minimum=100)
            if self.http_status > 599:
                raise ValueError("http_status must be at most 599")
        started = _require_timestamp("started_at", self.started_at, optional=True)
        finished = _require_timestamp("finished_at", self.finished_at, optional=True)
        if started is not None and finished is not None and finished < started:
            raise ValueError("finished_at cannot precede started_at")

    def _validate_status_contract(self) -> None:
        response_fields = (
            self.raw_response,
            self.raw_response_hash,
            self.parsed_response,
            self.parsed_result_hash,
            self.finish_reason,
            self.finished_at,
        )
        if self.status is EventStatus.SUCCEEDED:
            if any(value is None for value in response_fields):
                raise ValueError("succeeded attempt requires finished raw parsed response evidence")
            if self.started_at is None:
                raise ValueError("succeeded attempt requires started_at")
            if self.http_status is None or not 200 <= self.http_status < 300:
                raise ValueError("succeeded attempt requires a 2xx HTTP status")
            if not self.usage or not self.finish_reason:
                raise ValueError("succeeded attempt requires usage and finish_reason")
            if self.error is not None:
                raise ValueError("succeeded attempt cannot contain error evidence")
        elif self.status is EventStatus.FAILED:
            if self.started_at is None or self.finished_at is None or not self.error:
                raise ValueError("failed attempt requires started_at, finished_at, and error")
        elif self.status is EventStatus.PENDING:
            evidence = (
                *response_fields,
                self.provider_request_id,
                self.error,
                self.http_status,
                self.started_at,
            )
            if any(value is not None for value in evidence) or self.usage:
                raise ValueError("pending attempt cannot contain execution or response evidence")
        elif self.status is EventStatus.IN_PROGRESS:
            if self.started_at is None or self.finished_at is not None:
                raise ValueError("in_progress attempt requires started_at and no finished_at")
            if any(value is not None for value in (*response_fields[:-1], self.error)) or self.usage:
                raise ValueError("in_progress attempt cannot contain terminal response evidence")
            if self.http_status is not None and 200 <= self.http_status < 300:
                raise ValueError("in_progress attempt cannot contain a successful HTTP status")

    def _validate_response_hash_pairs(self) -> None:
        if (self.raw_response is None) != (self.raw_response_hash is None):
            raise ValueError("raw_response and raw_response_hash must be recorded together")
        if (self.parsed_response is None) != (self.parsed_result_hash is None):
            raise ValueError("parsed_response and parsed_result_hash must be recorded together")

    def _validate_payload_hashes(self) -> None:
        _require_payload_hash(
            "rendered_prompt_hash", self.rendered_prompt_hash, self.rendered_messages
        )
        _require_payload_hash("exposure_hash", self.exposure_hash, self.exposure_ids)
        if self.raw_response is not None:
            _require_payload_hash(
                "raw_response_hash", self.raw_response_hash, self.raw_response
            )
        if self.parsed_response is not None:
            _require_payload_hash(
                "parsed_result_hash", self.parsed_result_hash, self.parsed_response
            )


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    event_id: str
    agent_id: str
    round_index: int
    exposure_id: str
    status: EventStatus
    attempt_ids: tuple[str, ...]
    disposition_reason: str | None
    source_event_id: str | None
    replacement_event_id: str | None

    def __post_init__(self) -> None:
        _require_id("event_id", self.event_id)
        _require_id("agent_id", self.agent_id)
        _require_int("round_index", self.round_index)
        _require_id("exposure_id", self.exposure_id)
        if not isinstance(self.status, EventStatus):
            raise TypeError("status must be an EventStatus")
        _require_unique_ids("attempt_ids", self.attempt_ids)
        _require_string("disposition_reason", self.disposition_reason, optional=True)
        if self.source_event_id is not None:
            _require_id("source_event_id", self.source_event_id)
        if self.replacement_event_id is not None:
            _require_id("replacement_event_id", self.replacement_event_id)
        if self.event_id in {self.source_event_id, self.replacement_event_id}:
            raise ValueError("event provenance cannot reference the event itself")
        if (
            self.source_event_id is not None
            and self.source_event_id == self.replacement_event_id
        ):
            raise ValueError("source_event_id and replacement_event_id must differ")
        self._validate_status_contract()
        object.__setattr__(self, "attempt_ids", tuple(self.attempt_ids))

    def _validate_status_contract(self) -> None:
        if self.status is EventStatus.PENDING:
            pass
        elif self.status is EventStatus.IN_PROGRESS:
            if not self.attempt_ids:
                raise ValueError("in_progress event requires at least one attempt")
        elif self.status is EventStatus.SUCCEEDED:
            if not self.attempt_ids:
                raise ValueError("succeeded event requires at least one attempt")
        elif self.status is EventStatus.FAILED:
            if not self.attempt_ids or not self.disposition_reason:
                raise ValueError("failed event requires an attempt and disposition_reason")
        elif self.status is EventStatus.EXCLUDED:
            if not self.disposition_reason:
                raise ValueError("excluded event requires disposition_reason")
        elif self.status is EventStatus.IMPUTED:
            if not self.disposition_reason or self.source_event_id is None:
                raise ValueError("imputed event requires a reason and source_event_id")
            if self.replacement_event_id is not None:
                raise ValueError("imputed event cannot have replacement_event_id")
        elif self.status is EventStatus.FALLBACK:
            if (
                not self.disposition_reason
                or self.source_event_id is None
                or self.replacement_event_id is None
            ):
                raise ValueError(
                    "fallback event requires a reason, source_event_id, and replacement_event_id"
                )
        if self.status in {EventStatus.PENDING, EventStatus.IN_PROGRESS, EventStatus.SUCCEEDED}:
            if any(
                value is not None
                for value in (
                    self.disposition_reason,
                    self.source_event_id,
                    self.replacement_event_id,
                )
            ):
                raise ValueError(f"{self.status.value} event cannot have disposition evidence")


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    run_spec_hash: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    git_sha: str
    dirty: bool
    environment_lock_hash: str
    prompt_template_hash: str
    model_identity: Mapping[str, object]
    environment: Mapping[str, object]
    rounds: int
    schedule_uri: str
    schedule_hash: str
    checkpoint_uri: str | None
    checkpoint_hash: str | None
    recovery_cursor: Mapping[str, object] | None
    expected_event_count: int
    actual_event_count: int
    event_ids: tuple[str, ...]
    terminal_counts: Mapping[str, int]
    started_at: str
    updated_at: str
    last_completed_round: int | None
    failures: tuple[Mapping[str, object], ...]
    archive: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_id("run_id", self.run_id)
        _require_id("protocol_id", self.protocol_id)
        _require_string("protocol_version", self.protocol_version)
        for field_name in (
            "run_spec_hash",
            "protocol_hash",
            "environment_lock_hash",
            "prompt_template_hash",
        ):
            _require_sha256(field_name, getattr(self, field_name))
        if not isinstance(self.git_sha, str) or _GIT_PATTERN.fullmatch(self.git_sha) is None:
            raise ValueError("git_sha must be a 40-character lowercase commit hash")
        if not isinstance(self.dirty, bool):
            raise TypeError("dirty must be a boolean")
        if not isinstance(self.model_identity, Mapping) or not self.model_identity:
            raise ValueError("model_identity must be a non-empty mapping")
        self._validate_required_mapping(
            "model_identity", self.model_identity, ("provider", "model", "revision", "runtime")
        )
        if not isinstance(self.environment, Mapping):
            raise TypeError("environment must be a mapping")
        self._validate_required_mapping(
            "environment",
            self.environment,
            ("python_version", "dependency_lock_hash", "platform"),
        )
        _require_sha256(
            "environment[dependency_lock_hash]", self.environment["dependency_lock_hash"]
        )
        _require_int("rounds", self.rounds, minimum=1)
        _require_string("schedule_uri", self.schedule_uri)
        _require_sha256("schedule_hash", self.schedule_hash)
        _require_string("checkpoint_uri", self.checkpoint_uri, optional=True)
        _require_sha256("checkpoint_hash", self.checkpoint_hash, optional=True)
        if (self.checkpoint_uri is None) != (self.checkpoint_hash is None):
            raise ValueError("checkpoint_uri and checkpoint_hash must be recorded together")
        if self.recovery_cursor is not None and not isinstance(self.recovery_cursor, Mapping):
            raise TypeError("recovery_cursor must be a mapping or None")
        self._validate_progress()
        started = _require_timestamp("started_at", self.started_at)
        updated = _require_timestamp("updated_at", self.updated_at)
        if updated < started:
            raise ValueError("updated_at cannot precede started_at")
        if self.last_completed_round is not None:
            _require_int("last_completed_round", self.last_completed_round)
            if self.last_completed_round > self.rounds:
                raise ValueError("last_completed_round cannot exceed rounds")
        self._validate_recovery_cursor()
        _require_tuple("failures", self.failures)
        if not all(isinstance(failure, Mapping) for failure in self.failures):
            raise TypeError("failures must contain mappings")
        self._validate_failures()
        if not isinstance(self.archive, Mapping):
            raise TypeError("archive must be a mapping")
        self._validate_archive()
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))
        object.__setattr__(self, "environment", _freeze(self.environment))
        object.__setattr__(self, "recovery_cursor", _freeze(self.recovery_cursor))
        object.__setattr__(self, "event_ids", tuple(self.event_ids))
        object.__setattr__(self, "terminal_counts", _freeze(self.terminal_counts))
        object.__setattr__(self, "failures", _freeze(self.failures))
        object.__setattr__(self, "archive", _freeze(self.archive))

    def _validate_progress(self) -> None:
        _require_int("expected_event_count", self.expected_event_count, minimum=1)
        _require_int("actual_event_count", self.actual_event_count)
        if self.actual_event_count > self.expected_event_count:
            raise ValueError("actual_event_count cannot exceed expected_event_count")
        _require_unique_ids("event_ids", self.event_ids)
        if len(self.event_ids) != self.actual_event_count:
            raise ValueError("actual_event_count must equal the number of event_ids")
        if not isinstance(self.terminal_counts, Mapping):
            raise TypeError("terminal_counts must be a mapping")
        if set(self.terminal_counts) != _TERMINAL_VALUES:
            raise ValueError("terminal_counts must enumerate every terminal status")
        for status, count in self.terminal_counts.items():
            _require_int(f"terminal_counts[{status}]", count)
        if sum(self.terminal_counts.values()) > self.actual_event_count:
            raise ValueError("terminal_counts cannot exceed actual_event_count")

    @staticmethod
    def _validate_required_mapping(
        field_name: str, value: Mapping[str, object], required_keys: tuple[str, ...]
    ) -> None:
        missing = [key for key in required_keys if key not in value]
        if missing:
            raise ValueError(f"{field_name} must contain {', '.join(required_keys)}")
        for key in required_keys:
            _require_string(f"{field_name}[{key}]", value[key])

    def _validate_recovery_cursor(self) -> None:
        if self.recovery_cursor is None:
            return
        if "round_index" not in self.recovery_cursor:
            raise ValueError("recovery_cursor must contain round_index")
        round_index = self.recovery_cursor["round_index"]
        _require_int("recovery_cursor[round_index]", round_index)
        if round_index > self.rounds:
            raise ValueError("recovery_cursor round_index cannot exceed rounds")
        if self.last_completed_round is not None and round_index <= self.last_completed_round:
            raise ValueError("recovery_cursor must follow last_completed_round")

    def _validate_failures(self) -> None:
        for failure in self.failures:
            missing = {"event_id", "code", "message"} - set(failure)
            if missing:
                raise ValueError("failures must contain event_id, code, and message")
            for field_name in ("event_id", "code", "message"):
                _require_string(f"failures[{field_name}]", failure[field_name])
            if failure["event_id"] not in self.event_ids:
                raise ValueError("failures event_id must identify a manifest event")
            _freeze(failure)
        if len(self.failures) < self.terminal_counts["failed"]:
            raise ValueError("failures must cover every failed terminal event")

    def _validate_archive(self) -> None:
        required = {"status", "uri", "hash"}
        if not required.issubset(self.archive):
            raise ValueError("archive must contain status, uri, and hash")
        status = self.archive["status"]
        if status not in {"pending", "frozen"}:
            raise ValueError("archive status must be pending or frozen")
        uri = self.archive["uri"]
        digest = self.archive["hash"]
        if status == "pending":
            if uri is not None or digest is not None:
                raise ValueError("pending archive cannot have uri or hash")
        else:
            _require_string("archive[uri]", uri)
            _require_sha256("archive[hash]", digest)
        if self._counts_are_complete() and status != "frozen":
            raise ValueError("complete manifest requires a frozen archive")
        if not self._counts_are_complete() and status != "pending":
            raise ValueError("running manifest requires a pending archive")
        _freeze(self.archive)

    def _counts_are_complete(self) -> bool:
        return (
            self.actual_event_count == self.expected_event_count
            and self.nonterminal_event_count == 0
        )

    @property
    def nonterminal_event_count(self) -> int:
        return self.actual_event_count - sum(self.terminal_counts.values())

    @property
    def is_complete(self) -> bool:
        return self._counts_are_complete() and self.archive["status"] == "frozen"

    @property
    def is_analysis_eligible(self) -> bool:
        return self.is_complete and all(
            self.terminal_counts[status] == 0
            for status in ("failed", "imputed", "fallback")
        )
