"""Deeply immutable evidence records for reproducible simulation runs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlparse


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_TERMINAL_VALUES = {"succeeded", "failed", "excluded", "imputed", "fallback"}
_ATTEMPT_VALUES = {"pending", "in_progress", "succeeded", "failed"}
_EVIDENCE_URI_SCHEMES = {"s3", "gs", "az", "https", "file"}
_RUN_SPEC_REQUIRED_KEYS = {
    "protocol_id",
    "protocol_version",
    "protocol_hash",
    "schedule_hash",
    "run_config",
    "request_parameters",
    "model_identity",
    "git_sha",
    "dirty",
    "diff_hash",
    "environment_lock_hash",
    "prompt_template_hash",
}


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


def _require_json_transport(value: Any, field_name: str = "payload") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must contain finite JSON numbers")
        return
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} JSON object keys must be strings")
            _require_json_transport(item, f"{field_name}[{key}]")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _require_json_transport(item, f"{field_name}[{index}]")
        return
    raise TypeError(f"{field_name} must use strict JSON object and array containers")


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


def _require_evidence_uri(field_name: str, value: Any) -> None:
    _require_string(field_name, value)
    assert isinstance(value, str)
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return
    parsed = urlparse(value)
    if parsed.scheme not in _EVIDENCE_URI_SCHEMES:
        raise ValueError(
            f"{field_name} must use s3, gs, az, https, or file, or be an absolute path"
        )
    if parsed.scheme == "file":
        if not parsed.path.startswith("/") and not PureWindowsPath(parsed.path).is_absolute():
            raise ValueError(f"{field_name} file URI must identify an absolute path")
    elif not parsed.netloc:
        raise ValueError(f"{field_name} URI must include an authority")


def derive_run_id(run_spec: Mapping[str, object], replicate_seed: int, launch_nonce: str) -> str:
    """Derive a unique execution ID from an immutable spec and launch identity."""

    if not isinstance(run_spec, Mapping) or not run_spec:
        raise ValueError("run_spec must be a non-empty mapping")
    _require_int("replicate_seed", replicate_seed)
    _require_string("launch_nonce", launch_nonce)
    return "run-" + canonical_payload_hash(
        {
            "run_spec_hash": canonical_payload_hash(run_spec),
            "replicate_seed": replicate_seed,
            "launch_nonce": launch_nonce,
        }
    )


def derive_event_id(run_id: str, round_index: int, agent_id: str) -> str:
    """Derive an event ID from its unique run, round, and agent coordinates."""

    _require_id("run_id", run_id)
    _require_int("round_index", round_index)
    _require_id("agent_id", agent_id)
    return "event-" + canonical_payload_hash(
        {
            "run_id": run_id,
            "round_index": round_index,
            "agent_id": agent_id,
        }
    )


def derive_attempt_id(event_id: str, attempt_index: int) -> str:
    """Derive an attempt ID from its parent event and one-based attempt index."""

    _require_id("event_id", event_id)
    _require_int("attempt_index", attempt_index, minimum=1)
    return "attempt-" + canonical_payload_hash(
        {
            "event_id": event_id,
            "attempt_index": attempt_index,
        }
    )


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
        previous_round = -1
        for record in self.opinion_history:
            if record.agent_id != self.agent_id:
                raise ValueError("opinion_history agent_id must match AgentState agent_id")
            if record.round_index <= previous_round:
                raise ValueError("opinion_history rounds must be strictly increasing")
            if record.round_index > self.round_index:
                raise ValueError("opinion_history cannot contain a future round")
            previous_round = record.round_index
        if self.round_index > 0 and not self.opinion_history:
            raise ValueError("opinion_history is required after the initial round")
        if self.opinion_history:
            latest = self.opinion_history[-1]
            if (
                latest.round_index != self.round_index
                or latest.stance != self.stance
                or latest.reason != self.reason
            ):
                raise ValueError(
                    "opinion_history final record must match current round, stance, and reason"
                )
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


def _exposure_payload(exposure: ExposureRecord) -> Mapping[str, object]:
    return {
        "exposure_id": exposure.exposure_id,
        "agent_id": exposure.agent_id,
        "round_index": exposure.round_index,
        "exposure_mode": exposure.exposure_mode,
        "source_agent_ids": exposure.source_agent_ids,
        "source_event_ids": exposure.source_event_ids,
    }


@dataclass(frozen=True, slots=True)
class GenerationAttempt:
    attempt_id: str
    event_id: str
    sequence: int
    status: EventStatus
    request_id: str
    provider_request_id: str | None
    exposure_ids: tuple[str, ...]
    exposure_records: tuple[ExposureRecord, ...]
    rendered_messages: tuple[Mapping[str, object], ...]
    request_params: Mapping[str, object]
    provider_metadata: Mapping[str, object]
    rendered_prompt_hash: str
    exposure_hash: str
    request_params_hash: str
    provider_metadata_hash: str
    raw_response: str | None
    raw_response_hash: str | None
    parsed_response: Mapping[str, object] | None
    parsed_result_hash: str | None
    usage: Mapping[str, object]
    usage_hash: str
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
        object.__setattr__(self, "exposure_records", tuple(self.exposure_records))
        object.__setattr__(self, "rendered_messages", _freeze(self.rendered_messages))
        object.__setattr__(self, "request_params", _freeze(self.request_params))
        object.__setattr__(self, "provider_metadata", _freeze(self.provider_metadata))
        object.__setattr__(self, "parsed_response", _freeze(self.parsed_response))
        object.__setattr__(self, "usage", _freeze(self.usage))
        object.__setattr__(self, "error", _freeze(self.error))

    def _validate_common_fields(self) -> None:
        for field_name in ("attempt_id", "event_id", "request_id"):
            _require_id(field_name, getattr(self, field_name))
        if self.provider_request_id is not None:
            _require_id("provider_request_id", self.provider_request_id)
        _require_int("sequence", self.sequence, minimum=1)
        if self.attempt_id != derive_attempt_id(self.event_id, self.sequence):
            raise ValueError("attempt_id does not match event_id and sequence")
        if not isinstance(self.status, EventStatus):
            raise TypeError("status must be an EventStatus")
        if self.status.value not in _ATTEMPT_VALUES:
            raise ValueError("attempt status must be pending, in_progress, succeeded, or failed")
        _require_unique_ids("exposure_ids", self.exposure_ids)
        _require_tuple("exposure_records", self.exposure_records)
        if not all(isinstance(record, ExposureRecord) for record in self.exposure_records):
            raise TypeError("exposure_records must contain ExposureRecord values")
        record_ids = tuple(record.exposure_id for record in self.exposure_records)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("exposure_records must contain unique exposure IDs")
        if self.exposure_ids != record_ids:
            raise ValueError("exposure_ids must exactly match exposure_records")
        _require_tuple("rendered_messages", self.rendered_messages)
        if not all(isinstance(message, Mapping) for message in self.rendered_messages):
            raise TypeError("rendered_messages must contain mappings")
        for field_name in ("request_params", "provider_metadata", "usage"):
            if not isinstance(getattr(self, field_name), Mapping):
                raise TypeError(f"{field_name} must be a mapping")
        if self.parsed_response is not None and not isinstance(self.parsed_response, Mapping):
            raise TypeError("parsed_response must be a mapping or None")
        if self.error is not None and not isinstance(self.error, Mapping):
            raise TypeError("error must be a mapping or None")
        _require_sha256("rendered_prompt_hash", self.rendered_prompt_hash)
        _require_sha256("exposure_hash", self.exposure_hash)
        _require_sha256("request_params_hash", self.request_params_hash)
        _require_sha256("provider_metadata_hash", self.provider_metadata_hash)
        _require_sha256("raw_response_hash", self.raw_response_hash, optional=True)
        _require_sha256("parsed_result_hash", self.parsed_result_hash, optional=True)
        _require_sha256("usage_hash", self.usage_hash)
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
            if self.provider_request_id is None or not self.provider_metadata:
                raise ValueError(
                    "succeeded attempt requires provider request and metadata evidence"
                )
            if self.http_status is None or not 200 <= self.http_status < 300:
                raise ValueError("succeeded attempt requires a 2xx HTTP status")
            if not self.usage or not self.finish_reason:
                raise ValueError("succeeded attempt requires usage and finish_reason")
            self._validate_usage()
            if self.error is not None:
                raise ValueError("succeeded attempt cannot contain error evidence")
        elif self.status is EventStatus.FAILED:
            if self.started_at is None or self.finished_at is None or not self.error:
                raise ValueError("failed attempt requires started_at, finished_at, and error")
            if self.usage:
                self._validate_usage()
        elif self.status is EventStatus.PENDING:
            evidence = (
                *response_fields,
                self.provider_request_id,
                self.error,
                self.http_status,
                self.started_at,
            )
            if any(value is not None for value in evidence) or self.usage or self.provider_metadata:
                raise ValueError("pending attempt cannot contain execution or response evidence")
        elif self.status is EventStatus.IN_PROGRESS:
            if self.started_at is None or self.finished_at is not None:
                raise ValueError("in_progress attempt requires started_at and no finished_at")
            if (
                any(value is not None for value in (*response_fields[:-1], self.error))
                or self.usage
            ):
                raise ValueError("in_progress attempt cannot contain terminal response evidence")
            if self.http_status is not None:
                raise ValueError("in_progress attempt cannot contain HTTP response evidence")

    def _validate_usage(self) -> None:
        required = {"prompt_tokens", "completion_tokens", "total_tokens"}
        if not required.issubset(self.usage):
            raise ValueError(
                "usage must contain prompt_tokens, completion_tokens, and total_tokens"
            )
        for key in required:
            _require_int(f"usage[{key}]", self.usage[key])
        if (
            self.usage["total_tokens"]
            != self.usage["prompt_tokens"] + self.usage["completion_tokens"]
        ):
            raise ValueError("usage total_tokens must equal prompt plus completion tokens")

    def _validate_response_hash_pairs(self) -> None:
        if (self.raw_response is None) != (self.raw_response_hash is None):
            raise ValueError("raw_response and raw_response_hash must be recorded together")
        if (self.parsed_response is None) != (self.parsed_result_hash is None):
            raise ValueError("parsed_response and parsed_result_hash must be recorded together")

    def _validate_payload_hashes(self) -> None:
        _require_payload_hash(
            "rendered_prompt_hash", self.rendered_prompt_hash, self.rendered_messages
        )
        _require_payload_hash(
            "exposure_hash",
            self.exposure_hash,
            tuple(_exposure_payload(record) for record in self.exposure_records),
        )
        _require_payload_hash("request_params_hash", self.request_params_hash, self.request_params)
        _require_payload_hash(
            "provider_metadata_hash",
            self.provider_metadata_hash,
            self.provider_metadata,
        )
        _require_payload_hash("usage_hash", self.usage_hash, self.usage)
        if self.raw_response is not None:
            _require_payload_hash("raw_response_hash", self.raw_response_hash, self.raw_response)
        if self.parsed_response is not None:
            _require_payload_hash(
                "parsed_result_hash", self.parsed_result_hash, self.parsed_response
            )


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    run_id: str
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
        _require_id("run_id", self.run_id)
        _require_id("event_id", self.event_id)
        _require_id("agent_id", self.agent_id)
        _require_int("round_index", self.round_index)
        if self.event_id != derive_event_id(self.run_id, self.round_index, self.agent_id):
            raise ValueError("event_id does not match run_id, round_index, and agent_id")
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
        if self.source_event_id is not None and self.source_event_id == self.replacement_event_id:
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
            if self.source_event_id is not None or self.replacement_event_id is not None:
                raise ValueError("failed event cannot have source or replacement provenance")
        elif self.status is EventStatus.EXCLUDED:
            if not self.disposition_reason:
                raise ValueError("excluded event requires disposition_reason")
            if self.attempt_ids:
                raise ValueError("excluded event cannot have attempts")
            if self.source_event_id is not None or self.replacement_event_id is not None:
                raise ValueError("excluded event cannot have source or replacement provenance")
        elif self.status is EventStatus.IMPUTED:
            if not self.disposition_reason or self.source_event_id is None:
                raise ValueError("imputed event requires a reason and source_event_id")
            if self.attempt_ids:
                raise ValueError("imputed event cannot have attempts")
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
            if self.attempt_ids:
                raise ValueError("fallback event cannot have attempts")
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
class ScheduleSlot:
    round_index: int
    agent_id: str

    def __post_init__(self) -> None:
        _require_int("schedule slot round_index", self.round_index, minimum=1)
        _require_id("schedule slot agent_id", self.agent_id)


@dataclass(frozen=True, slots=True)
class FrozenSchedule:
    slots: tuple[ScheduleSlot, ...]
    schedule_hash: str = field(init=False)
    count: int = field(init=False)

    def __post_init__(self) -> None:
        _require_tuple("schedule slots", self.slots)
        if not all(isinstance(slot, ScheduleSlot) for slot in self.slots):
            raise TypeError("schedule slots must contain ScheduleSlot values")
        coordinates = tuple((slot.round_index, slot.agent_id) for slot in self.slots)
        if len(set(coordinates)) != len(coordinates):
            raise ValueError("schedule slot coordinates must be unique")
        object.__setattr__(self, "schedule_hash", canonical_payload_hash(self.to_payload()))
        object.__setattr__(self, "count", len(self.slots))

    def to_payload(self) -> dict[str, object]:
        """Return the versioned canonical schedule artifact; do not use asdict as a contract."""

        return {
            "version": 1,
            "slots": [
                {"round_index": slot.round_index, "agent_id": slot.agent_id} for slot in self.slots
            ],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FrozenSchedule:
        if type(payload) is not dict:
            raise TypeError("schedule payload must be a JSON object")
        if set(payload) != {"version", "slots"}:
            raise ValueError("schedule payload must contain exactly version and slots")
        version = payload["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise ValueError("schedule payload version must be 1")
        raw_slots = payload["slots"]
        if type(raw_slots) is not list:
            raise TypeError("schedule payload slots must be a list")
        slots: list[ScheduleSlot] = []
        for raw_slot in raw_slots:
            if type(raw_slot) is not dict or set(raw_slot) != {
                "round_index",
                "agent_id",
            }:
                raise ValueError(
                    "schedule payload slots must contain exact round_index and agent_id"
                )
            round_index = raw_slot["round_index"]
            agent_id = raw_slot["agent_id"]
            if not isinstance(round_index, int) or isinstance(round_index, bool):
                raise TypeError("schedule slot round_index must be an integer")
            if not isinstance(agent_id, str):
                raise TypeError("schedule slot agent_id must be a string")
            slots.append(
                ScheduleSlot(
                    round_index=round_index,
                    agent_id=agent_id,
                )
            )
        return cls(tuple(slots))


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    run_spec: Mapping[str, object]
    run_spec_hash: str
    replicate_seed: int
    launch_nonce: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    git_sha: str
    dirty: bool
    diff_hash: str | None
    environment_lock_hash: str
    prompt_template_hash: str
    model_identity: Mapping[str, object]
    environment: Mapping[str, object]
    rounds: int
    schedule_uri: str
    schedule: FrozenSchedule
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
        if not isinstance(self.run_spec, Mapping) or not self.run_spec:
            raise ValueError("run_spec must be a non-empty mapping")
        _require_int("replicate_seed", self.replicate_seed)
        _require_string("launch_nonce", self.launch_nonce)
        _require_id("protocol_id", self.protocol_id)
        _require_string("protocol_version", self.protocol_version)
        for field_name in (
            "run_spec_hash",
            "protocol_hash",
            "environment_lock_hash",
            "prompt_template_hash",
        ):
            _require_sha256(field_name, getattr(self, field_name))
        _require_payload_hash("run_spec_hash", self.run_spec_hash, self.run_spec)
        if self.run_id != derive_run_id(self.run_spec, self.replicate_seed, self.launch_nonce):
            raise ValueError("run_id does not match run_spec, replicate_seed, and launch_nonce")
        if not isinstance(self.git_sha, str) or _GIT_PATTERN.fullmatch(self.git_sha) is None:
            raise ValueError("git_sha must be a 40-character lowercase commit hash")
        if not isinstance(self.dirty, bool):
            raise TypeError("dirty must be a boolean")
        _require_sha256("diff_hash", self.diff_hash, optional=True)
        if self.dirty and self.diff_hash is None:
            raise ValueError("dirty manifest requires diff_hash")
        if not self.dirty and self.diff_hash is not None:
            raise ValueError("clean manifest requires diff_hash to be None")
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
        if self.environment_lock_hash != self.environment["dependency_lock_hash"]:
            raise ValueError("environment_lock_hash must equal environment dependency_lock_hash")
        _require_int("rounds", self.rounds, minimum=1)
        self._validate_run_spec_bindings()
        _require_evidence_uri("schedule_uri", self.schedule_uri)
        _require_sha256("schedule_hash", self.schedule_hash)
        if not isinstance(self.schedule, FrozenSchedule):
            raise TypeError("schedule must be a FrozenSchedule")
        self._validate_schedule()
        if self.checkpoint_uri is not None:
            _require_evidence_uri("checkpoint_uri", self.checkpoint_uri)
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
        self._validate_progress_state()
        _require_tuple("failures", self.failures)
        if not all(isinstance(failure, Mapping) for failure in self.failures):
            raise TypeError("failures must contain mappings")
        self._validate_failures()
        if not isinstance(self.archive, Mapping):
            raise TypeError("archive must be a mapping")
        self._validate_archive()
        self._validate_completion_state()
        object.__setattr__(self, "run_spec", _freeze(self.run_spec))
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

    def _validate_run_spec_bindings(self) -> None:
        missing = _RUN_SPEC_REQUIRED_KEYS - set(self.run_spec)
        if missing:
            raise ValueError("run_spec must contain " + ", ".join(sorted(_RUN_SPEC_REQUIRED_KEYS)))
        run_config = self.run_spec["run_config"]
        request_parameters = self.run_spec["request_parameters"]
        if not isinstance(run_config, Mapping):
            raise TypeError("run_spec[run_config] must be a mapping")
        if not isinstance(request_parameters, Mapping):
            raise TypeError("run_spec[request_parameters] must be a mapping")
        if "rounds" not in run_config or run_config["rounds"] != self.rounds:
            raise ValueError("run_spec run_config rounds must match manifest rounds")
        if "population" not in run_config:
            raise ValueError("run_spec run_config must contain population")
        population = run_config["population"]
        _require_int("run_spec[run_config][population]", population, minimum=1)
        if (
            "expected_event_count" not in run_config
            or run_config["expected_event_count"] != self.expected_event_count
        ):
            raise ValueError(
                "run_spec run_config expected_event_count must match manifest expected_event_count"
            )
        bindings = {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_hash": self.protocol_hash,
            "schedule_hash": self.schedule_hash,
            "model_identity": self.model_identity,
            "git_sha": self.git_sha,
            "dirty": self.dirty,
            "diff_hash": self.diff_hash,
            "environment_lock_hash": self.environment_lock_hash,
            "prompt_template_hash": self.prompt_template_hash,
        }
        for key, expected in bindings.items():
            if self.run_spec[key] != expected:
                raise ValueError(f"run_spec {key} must match manifest {key}")
        _freeze(run_config)
        _freeze(request_parameters)

    def _validate_schedule(self) -> None:
        population = self.run_spec["run_config"]["population"]
        assert isinstance(population, int)
        agents: set[str] = set()
        events_per_round = {round_index: 0 for round_index in range(1, self.rounds + 1)}
        for slot in self.schedule.slots:
            if slot.round_index > self.rounds:
                raise ValueError("schedule slot round must be within manifest rounds")
            agents.add(slot.agent_id)
            events_per_round[slot.round_index] += 1
        if len(agents) > population:
            raise ValueError("schedule agent roster cannot exceed run_config population")
        if any(count == 0 for count in events_per_round.values()):
            raise ValueError("schedule must activate at least one slot in every manifest round")
        if any(count > population for count in events_per_round.values()):
            raise ValueError("schedule round activation cannot exceed run_config population")
        if self.expected_event_count != self.schedule.count:
            raise ValueError("expected_event_count must equal the number of schedule slots")
        if self.schedule_hash != self.schedule.schedule_hash:
            raise ValueError("schedule_hash must match the frozen schedule")

    def _validate_recovery_cursor(self) -> None:
        if self.recovery_cursor is None:
            return
        if self.checkpoint_uri is None or self.checkpoint_hash is None:
            raise ValueError("recovery_cursor requires checkpoint evidence")
        required = {"round_index", "event_index"}
        if set(self.recovery_cursor) != required:
            raise ValueError("recovery_cursor must contain exactly round_index and event_index")
        round_index = self.recovery_cursor["round_index"]
        event_index = self.recovery_cursor["event_index"]
        _require_int("recovery_cursor[round_index]", round_index)
        _require_int("recovery_cursor[event_index]", event_index)
        if round_index > self.rounds:
            raise ValueError("recovery_cursor round_index cannot exceed rounds")
        if self.last_completed_round is not None and round_index <= self.last_completed_round:
            raise ValueError("recovery_cursor must follow last_completed_round")
        next_round = (self.last_completed_round or 0) + 1
        if round_index != next_round:
            raise ValueError("recovery_cursor must identify the current next round")
        round_slot_count = sum(1 for slot in self.schedule.slots if slot.round_index == round_index)
        if event_index > round_slot_count:
            raise ValueError(
                "recovery_cursor event_index must be within the next round schedule slots"
            )

    def _validate_progress_state(self) -> None:
        completed_round = self.last_completed_round or 0
        completed_slot_count = sum(
            1 for slot in self.schedule.slots if slot.round_index <= completed_round
        )
        next_round = completed_round + 1
        next_round_slot_count = sum(
            1 for slot in self.schedule.slots if slot.round_index == next_round
        )
        if self.actual_event_count < completed_slot_count:
            raise ValueError("progress cannot omit events from completed schedule rounds")
        if self.actual_event_count > completed_slot_count + next_round_slot_count:
            raise ValueError("progress cannot contain events beyond the current next round")
        terminal_count = sum(self.terminal_counts.values())
        if terminal_count < completed_slot_count:
            raise ValueError("completed schedule rounds require terminal events")

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
            _require_evidence_uri("archive[uri]", uri)
            _require_sha256("archive[hash]", digest)
        if self._counts_are_complete() and status != "frozen":
            raise ValueError("complete manifest requires a frozen archive")
        if not self._counts_are_complete() and status != "pending":
            raise ValueError("running manifest requires a pending archive")
        _freeze(self.archive)

    def _validate_completion_state(self) -> None:
        if self._counts_are_complete():
            if self.last_completed_round != self.rounds:
                raise ValueError("complete manifest requires last_completed_round to equal rounds")
            if self.recovery_cursor is not None:
                raise ValueError("complete manifest requires recovery_cursor to be None")
        elif self.last_completed_round == self.rounds:
            raise ValueError("incomplete manifest cannot report the final round as completed")

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

    def to_payload(self) -> dict[str, object]:
        """Return the persisted manifest boundary, excluding the runtime schedule object.

        The explicit projection is the serialization contract; ``dataclasses.asdict`` is not.
        """

        return _json_ready(
            {
                "run_id": self.run_id,
                "run_spec": self.run_spec,
                "run_spec_hash": self.run_spec_hash,
                "replicate_seed": self.replicate_seed,
                "launch_nonce": self.launch_nonce,
                "protocol_id": self.protocol_id,
                "protocol_version": self.protocol_version,
                "protocol_hash": self.protocol_hash,
                "git_sha": self.git_sha,
                "dirty": self.dirty,
                "diff_hash": self.diff_hash,
                "environment_lock_hash": self.environment_lock_hash,
                "prompt_template_hash": self.prompt_template_hash,
                "model_identity": self.model_identity,
                "environment": self.environment,
                "rounds": self.rounds,
                "schedule_uri": self.schedule_uri,
                "schedule_hash": self.schedule_hash,
                "schedule_count": self.schedule.count,
                "checkpoint_uri": self.checkpoint_uri,
                "checkpoint_hash": self.checkpoint_hash,
                "recovery_cursor": self.recovery_cursor,
                "expected_event_count": self.expected_event_count,
                "actual_event_count": self.actual_event_count,
                "event_ids": self.event_ids,
                "terminal_counts": self.terminal_counts,
                "started_at": self.started_at,
                "updated_at": self.updated_at,
                "last_completed_round": self.last_completed_round,
                "failures": self.failures,
                "archive": self.archive,
            }
        )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
        *,
        schedule: FrozenSchedule,
    ) -> RunManifest:
        if type(payload) is not dict:
            raise TypeError("manifest payload must be a JSON object")
        expected_fields = {
            "run_id",
            "run_spec",
            "run_spec_hash",
            "replicate_seed",
            "launch_nonce",
            "protocol_id",
            "protocol_version",
            "protocol_hash",
            "git_sha",
            "dirty",
            "diff_hash",
            "environment_lock_hash",
            "prompt_template_hash",
            "model_identity",
            "environment",
            "rounds",
            "schedule_uri",
            "schedule_hash",
            "schedule_count",
            "checkpoint_uri",
            "checkpoint_hash",
            "recovery_cursor",
            "expected_event_count",
            "actual_event_count",
            "event_ids",
            "terminal_counts",
            "started_at",
            "updated_at",
            "last_completed_round",
            "failures",
            "archive",
        }
        if set(payload) != expected_fields:
            raise ValueError("manifest payload fields do not match the persisted contract")
        for field_name in (
            "run_spec",
            "model_identity",
            "environment",
            "terminal_counts",
            "archive",
        ):
            if type(payload[field_name]) is not dict:
                raise TypeError(f"manifest payload {field_name} must be a JSON object")
        if payload["recovery_cursor"] is not None and type(payload["recovery_cursor"]) is not dict:
            raise TypeError("manifest payload recovery_cursor must be a JSON object or null")
        for field_name in ("event_ids", "failures"):
            if type(payload[field_name]) is not list:
                raise TypeError(f"manifest payload {field_name} must be a JSON array")
        if not all(type(failure) is dict for failure in payload["failures"]):
            raise TypeError("manifest payload failures must contain JSON objects")
        schedule_count = payload["schedule_count"]
        if not isinstance(schedule_count, int) or isinstance(schedule_count, bool):
            raise TypeError("manifest payload schedule_count must be an integer")
        _require_json_transport(payload, "manifest payload")
        if not isinstance(schedule, FrozenSchedule):
            raise TypeError("schedule must be a FrozenSchedule")
        if payload["schedule_hash"] != schedule.schedule_hash or schedule_count != schedule.count:
            raise ValueError("persisted manifest schedule binding does not match schedule")
        values = dict(payload)
        values.pop("schedule_count")
        values["schedule"] = schedule
        values["event_ids"] = tuple(values["event_ids"])  # type: ignore[arg-type]
        values["failures"] = tuple(values["failures"])  # type: ignore[arg-type]
        return cls(**values)  # type: ignore[arg-type]


def evaluate_analysis_eligibility(
    manifest: RunManifest,
    policy: Mapping[str, int],
) -> bool:
    """Evaluate a completed run against an explicit, caller-frozen threshold policy."""

    if not isinstance(manifest, RunManifest):
        raise TypeError("manifest must be a RunManifest")
    if not isinstance(policy, Mapping):
        raise TypeError("policy must be a mapping")
    policy_keys = {"failed", "excluded", "imputed", "fallback"}
    if set(policy) != policy_keys:
        raise ValueError(
            "policy must contain exactly failed, excluded, imputed, and fallback thresholds"
        )
    for status, threshold in policy.items():
        if not isinstance(threshold, int) or isinstance(threshold, bool):
            raise TypeError(f"policy[{status}] must be an integer")
        if threshold < 0:
            raise ValueError(f"policy[{status}] must be nonnegative")
    return manifest.is_complete and all(
        manifest.terminal_counts[status] <= policy[status] for status in policy_keys
    )


def validate_evidence_graph(
    manifest: RunManifest,
    events: tuple[GenerationEvent, ...],
    attempts: tuple[GenerationAttempt, ...],
    exposures: tuple[ExposureRecord, ...],
) -> None:
    """Validate exact cross-record integrity for a persisted run evidence graph."""

    if not isinstance(manifest, RunManifest):
        raise TypeError("manifest must be a RunManifest")
    for field_name, values, expected_type in (
        ("events", events, GenerationEvent),
        ("attempts", attempts, GenerationAttempt),
        ("exposures", exposures, ExposureRecord),
    ):
        _require_tuple(field_name, values)
        if not all(isinstance(value, expected_type) for value in values):
            raise TypeError(f"{field_name} contains an invalid record")

    def unique_index(field_name: str, values: tuple[Any, ...], id_name: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for value in values:
            record_id = getattr(value, id_name)
            if record_id in result:
                raise ValueError(f"{field_name} IDs must be unique")
            result[record_id] = value
        return result

    event_by_id = unique_index("event", events, "event_id")
    attempt_by_id = unique_index("attempt", attempts, "attempt_id")
    exposure_by_id = unique_index("exposure", exposures, "exposure_id")

    observed_event_ids = tuple(event.event_id for event in events)
    if manifest.event_ids != observed_event_ids:
        raise ValueError("manifest event_ids must exactly match events")
    if manifest.actual_event_count != len(events):
        raise ValueError("manifest actual_event_count must exactly match events")

    observed_counts = {status: 0 for status in _TERMINAL_VALUES}
    for event in events:
        if event.status.value in observed_counts:
            observed_counts[event.status.value] += 1
    if dict(manifest.terminal_counts) != observed_counts:
        raise ValueError("manifest terminal_counts must exactly match events")

    failed_event_ids = {event.event_id for event in events if event.status is EventStatus.FAILED}
    failure_event_ids = [str(failure["event_id"]) for failure in manifest.failures]
    if len(failure_event_ids) != len(set(failure_event_ids)):
        raise ValueError("manifest failures must identify failed events exactly once")
    if set(failure_event_ids) != failed_event_ids:
        raise ValueError("manifest failures must exactly match failed events")

    event_exposure_ids = tuple(event.exposure_id for event in events)
    if len(set(event_exposure_ids)) != len(event_exposure_ids):
        raise ValueError("event exposure IDs must be unique")
    if set(event_exposure_ids) != set(exposure_by_id):
        raise ValueError("exposure records must exactly match event exposures")

    referenced_attempt_ids: list[str] = []
    for event in events:
        if event.run_id != manifest.run_id:
            raise ValueError("event run_id must match manifest run_id")
        exposure = exposure_by_id[event.exposure_id]
        if not 1 <= event.round_index <= manifest.rounds:
            raise ValueError("event round must be within manifest rounds")
        if not 1 <= exposure.round_index <= manifest.rounds:
            raise ValueError("exposure round must be within manifest rounds")
        if exposure.agent_id != event.agent_id or exposure.round_index != event.round_index:
            raise ValueError("event and exposure agent/round evidence must match")
        for source_agent_id, source_event_id in zip(
            exposure.source_agent_ids,
            exposure.source_event_ids,
            strict=True,
        ):
            if source_event_id not in event_by_id:
                raise ValueError("exposure source_event_ids must identify graph events")
            source_event = event_by_id[source_event_id]
            if source_event.agent_id != source_agent_id:
                raise ValueError("exposure source agent must match the source event agent")
            if source_event.round_index != exposure.round_index - 1:
                raise ValueError("exposure source round must be exactly the previous round")
            if source_event.status is not EventStatus.SUCCEEDED:
                raise ValueError("exposure source event must be succeeded")

        event_attempts: list[GenerationAttempt] = []
        for attempt_id in event.attempt_ids:
            if attempt_id not in attempt_by_id:
                raise ValueError("event attempt_ids must identify graph attempts")
            attempt = attempt_by_id[attempt_id]
            if attempt.event_id != event.event_id:
                raise ValueError("attempt event_id must match its event")
            if attempt.exposure_ids != (event.exposure_id,):
                raise ValueError("attempt exposure IDs must exactly match its event exposure")
            if attempt.exposure_records != (exposure,):
                raise ValueError("attempt exposure content must match graph exposure evidence")
            if attempt.request_params != manifest.run_spec["request_parameters"]:
                raise ValueError(
                    "attempt request_params must exactly match run_spec request_parameters"
                )
            event_attempts.append(attempt)
            referenced_attempt_ids.append(attempt_id)

        expected_sequences = list(range(1, len(event_attempts) + 1))
        if [attempt.sequence for attempt in event_attempts] != expected_sequences:
            raise ValueError("event attempts must have contiguous ordered sequences")
        statuses = [attempt.status for attempt in event_attempts]
        if event.status is EventStatus.PENDING:
            if any(status is not EventStatus.PENDING for status in statuses):
                raise ValueError("pending event may only reference pending attempts")
        elif event.status is EventStatus.IN_PROGRESS:
            if not statuses or statuses[-1] is not EventStatus.IN_PROGRESS:
                raise ValueError("in_progress event requires a final in_progress attempt")
            if any(status is not EventStatus.FAILED for status in statuses[:-1]):
                raise ValueError("in_progress event prior attempts must be failed")
        elif event.status is EventStatus.SUCCEEDED:
            if not statuses or statuses[-1] is not EventStatus.SUCCEEDED:
                raise ValueError("succeeded event requires a final succeeded attempt")
            if any(status is not EventStatus.FAILED for status in statuses[:-1]):
                raise ValueError("succeeded event prior attempts must be failed")
        elif event.status is EventStatus.FAILED:
            if not statuses or any(status is not EventStatus.FAILED for status in statuses):
                raise ValueError("failed event may only reference failed attempts")

        for provenance_id in (event.source_event_id, event.replacement_event_id):
            if provenance_id is None:
                continue
            if provenance_id not in event_by_id:
                raise ValueError("event provenance must identify graph events")
            if event_by_id[provenance_id].round_index > event.round_index:
                raise ValueError("event provenance cannot reference a future event")

    if len(referenced_attempt_ids) != len(set(referenced_attempt_ids)):
        raise ValueError("attempts may be referenced by only one event")
    if set(referenced_attempt_ids) != set(attempt_by_id):
        raise ValueError("attempt records must exactly match event attempt_ids")

    provenance_edges = {
        event.event_id: tuple(
            provenance_id
            for provenance_id in (event.source_event_id, event.replacement_event_id)
            if provenance_id is not None
        )
        for event in events
    }
    incoming_edge_counts = {event_id: 0 for event_id in provenance_edges}
    for provenance_ids in provenance_edges.values():
        for provenance_id in provenance_ids:
            incoming_edge_counts[provenance_id] += 1
    ready = [event_id for event_id, edge_count in incoming_edge_counts.items() if edge_count == 0]
    visited_count = 0
    while ready:
        event_id = ready.pop()
        visited_count += 1
        for provenance_id in provenance_edges[event_id]:
            incoming_edge_counts[provenance_id] -= 1
            if incoming_edge_counts[provenance_id] == 0:
                ready.append(provenance_id)
    if visited_count != len(provenance_edges):
        raise ValueError("event provenance cannot contain a cycle")

    schedule_coordinates = {(slot.round_index, slot.agent_id) for slot in manifest.schedule.slots}
    observed_coordinates = {(event.round_index, event.agent_id) for event in events}
    if manifest.is_complete:
        if observed_coordinates != schedule_coordinates:
            raise ValueError("complete evidence graph must exactly match frozen schedule slots")
    else:
        if not observed_coordinates.issubset(schedule_coordinates):
            raise ValueError("incomplete evidence graph must be a subset of frozen schedule slots")
        completed_round = manifest.last_completed_round or 0
        completed_coordinates = {
            (slot.round_index, slot.agent_id)
            for slot in manifest.schedule.slots
            if slot.round_index <= completed_round
        }
        observed_completed = {
            coordinate for coordinate in observed_coordinates if coordinate[0] <= completed_round
        }
        if observed_completed != completed_coordinates:
            raise ValueError(
                "incomplete evidence graph must exactly cover completed schedule rounds"
            )
        for event in events:
            if event.round_index <= completed_round and event.status.value not in _TERMINAL_VALUES:
                raise ValueError("completed schedule round events must each be terminal")
        next_round = completed_round + 1
        if any(round_index > next_round for round_index, _ in observed_coordinates):
            raise ValueError("incomplete evidence graph cannot contain events beyond next round")
        if manifest.recovery_cursor is not None:
            event_index = manifest.recovery_cursor["event_index"]
            scheduled_prefix = tuple(
                (slot.round_index, slot.agent_id)
                for slot in manifest.schedule.slots
                if slot.round_index == next_round
            )[:event_index]
            observed_current = tuple(
                (event.round_index, event.agent_id)
                for event in events
                if event.round_index == next_round
            )
            if len(observed_current) != event_index or observed_current != scheduled_prefix:
                raise ValueError(
                    "recovery cursor event_index must equal the observed schedule prefix"
                )
