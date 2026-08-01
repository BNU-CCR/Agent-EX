"""Immutable ordinal-based evidence records for reproducible simulation runs."""

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
_EVIDENCE_URI_SCHEMES = {"s3", "gs", "az", "https", "file"}


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
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_int(field_name: str, value: Any, *, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")


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
    """Return the SHA-256 of a JSON-like value's canonical encoding."""

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


def _require_mapping_fields(
    field_name: str,
    value: Any,
    required_fields: tuple[str, ...],
) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    missing = tuple(
        required_field for required_field in required_fields if required_field not in value
    )
    if missing:
        raise ValueError(f"{field_name} must contain {', '.join(required_fields)}")
    for required_field in required_fields:
        _require_string(f"{field_name}[{required_field}]", value[required_field])


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


def derive_run_id(run_spec: Mapping[str, object], matched_seed: int, launch_nonce: str) -> str:
    """Derive a run ID from an immutable spec and matched-seed launch identity."""

    if not isinstance(run_spec, Mapping) or not run_spec:
        raise ValueError("run_spec must be a non-empty mapping")
    _require_int("matched_seed", matched_seed)
    _require_string("launch_nonce", launch_nonce)
    return "run-" + canonical_payload_hash(
        {
            "run_spec_hash": canonical_payload_hash(run_spec),
            "matched_seed": matched_seed,
            "launch_nonce": launch_nonce,
        }
    )


def derive_event_id(run_id: str, event_ordinal: int) -> str:
    """Derive an event ID from its run and zero-based global activation ordinal."""

    _require_id("run_id", run_id)
    _require_int("event_ordinal", event_ordinal)
    return "event-" + canonical_payload_hash({"run_id": run_id, "event_ordinal": event_ordinal})


def derive_attempt_id(event_id: str, attempt_index: int) -> str:
    """Derive an attempt ID from its parent event and one-based attempt index."""

    _require_id("event_id", event_id)
    _require_int("attempt_index", attempt_index, minimum=1)
    return "attempt-" + canonical_payload_hash(
        {"event_id": event_id, "attempt_index": attempt_index}
    )


class EventStatus(StrEnum):
    """Runtime state-chain values; analysis exclusions are not event states."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExposureRecord:
    """Minimal 4B-2 exposure boundary, pending feed expansion in 4B-6."""

    exposure_id: str
    event_ordinal: int
    receiver_agent_id: str
    exposure_mode: str
    source_agent_ids: tuple[str, ...]
    source_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_id("exposure_id", self.exposure_id)
        _require_int("event_ordinal", self.event_ordinal)
        _require_id("receiver_agent_id", self.receiver_agent_id)
        if self.exposure_mode not in {
            "self_history_only",
            "shuffled_social",
            "ws_neighbors",
        }:
            raise ValueError("exposure_mode is not a legal Paper 1 factor level")
        _require_tuple("source_agent_ids", self.source_agent_ids)
        for source_agent_id in self.source_agent_ids:
            _require_id("source_agent_id", source_agent_id)
            if source_agent_id == self.receiver_agent_id:
                raise ValueError("exposure cannot use the receiver as a social source")
        _require_unique_ids("source_event_ids", self.source_event_ids)
        if len(self.source_agent_ids) != len(self.source_event_ids):
            raise ValueError("source_agent_ids and source_event_ids must be paired")
        if self.exposure_mode == "self_history_only" and self.source_event_ids:
            raise ValueError("self_history_only exposure cannot contain social sources")
        object.__setattr__(self, "source_agent_ids", tuple(self.source_agent_ids))
        object.__setattr__(self, "source_event_ids", tuple(self.source_event_ids))

    def to_payload(self) -> dict[str, object]:
        return {
            "exposure_id": self.exposure_id,
            "event_ordinal": self.event_ordinal,
            "receiver_agent_id": self.receiver_agent_id,
            "exposure_mode": self.exposure_mode,
            "source_agent_ids": list(self.source_agent_ids),
            "source_event_ids": list(self.source_event_ids),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ExposureRecord:
        expected = {
            "exposure_id",
            "event_ordinal",
            "receiver_agent_id",
            "exposure_mode",
            "source_agent_ids",
            "source_event_ids",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("exposure payload fields do not match the v2 contract")
        if (
            type(payload["source_agent_ids"]) is not list
            or type(payload["source_event_ids"]) is not list
        ):
            raise TypeError("exposure source IDs must be JSON arrays")
        _require_json_transport(payload, "exposure payload")
        return cls(
            exposure_id=payload["exposure_id"],  # type: ignore[arg-type]
            event_ordinal=payload["event_ordinal"],  # type: ignore[arg-type]
            receiver_agent_id=payload["receiver_agent_id"],  # type: ignore[arg-type]
            exposure_mode=payload["exposure_mode"],  # type: ignore[arg-type]
            source_agent_ids=tuple(payload["source_agent_ids"]),  # type: ignore[arg-type]
            source_event_ids=tuple(payload["source_event_ids"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class GenerationAttempt:
    attempt_id: str
    event_id: str
    attempt_index: int
    status: EventStatus
    request_id: str
    exposure_id: str
    rendered_messages: tuple[Mapping[str, object], ...]
    rendered_prompt_hash: str
    request_parameters: Mapping[str, object]
    request_parameters_hash: str
    model_identity: Mapping[str, object]
    model_identity_hash: str
    model_seed: int
    provider_request_id: str | None
    provider_metadata: Mapping[str, object]
    provider_metadata_hash: str
    http_status: int | None
    raw_response: str | None
    raw_response_hash: str | None
    parsed_response: Mapping[str, object] | None
    parsed_response_hash: str | None
    usage: Mapping[str, object]
    usage_hash: str
    finish_reason: str | None
    error: Mapping[str, object] | None
    started_at: str | None
    finished_at: str | None

    def __post_init__(self) -> None:
        for field_name in ("attempt_id", "event_id", "request_id", "exposure_id"):
            _require_id(field_name, getattr(self, field_name))
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if self.attempt_id != derive_attempt_id(self.event_id, self.attempt_index):
            raise ValueError("attempt_id does not match event_id and attempt_index")
        if not isinstance(self.status, EventStatus):
            raise TypeError("status must be an EventStatus")
        _require_tuple("rendered_messages", self.rendered_messages)
        if not all(isinstance(message, Mapping) for message in self.rendered_messages):
            raise TypeError("rendered_messages must contain mappings")
        for field_name in ("request_parameters", "model_identity", "provider_metadata", "usage"):
            if not isinstance(getattr(self, field_name), Mapping):
                raise TypeError(f"{field_name} must be a mapping")
        if not self.model_identity:
            raise ValueError("model_identity must be a non-empty mapping")
        _require_int("model_seed", self.model_seed)
        if self.provider_request_id is not None:
            _require_id("provider_request_id", self.provider_request_id)
        _require_string("raw_response", self.raw_response, optional=True)
        _require_string("finish_reason", self.finish_reason, optional=True)
        if self.http_status is not None:
            _require_int("http_status", self.http_status, minimum=100)
            if self.http_status > 599:
                raise ValueError("http_status must be at most 599")
        if self.parsed_response is not None and not isinstance(self.parsed_response, Mapping):
            raise TypeError("parsed_response must be a mapping or None")
        if self.error is not None and not isinstance(self.error, Mapping):
            raise TypeError("error must be a mapping or None")
        for field_name in (
            "rendered_prompt_hash",
            "request_parameters_hash",
            "model_identity_hash",
            "provider_metadata_hash",
            "usage_hash",
        ):
            _require_sha256(field_name, getattr(self, field_name))
        _require_sha256("raw_response_hash", self.raw_response_hash, optional=True)
        _require_sha256("parsed_response_hash", self.parsed_response_hash, optional=True)
        _require_payload_hash(
            "rendered_prompt_hash", self.rendered_prompt_hash, self.rendered_messages
        )
        _require_payload_hash(
            "request_parameters_hash",
            self.request_parameters_hash,
            self.request_parameters,
        )
        _require_payload_hash("model_identity_hash", self.model_identity_hash, self.model_identity)
        _require_payload_hash(
            "provider_metadata_hash", self.provider_metadata_hash, self.provider_metadata
        )
        _require_payload_hash("usage_hash", self.usage_hash, self.usage)
        if (self.raw_response is None) != (self.raw_response_hash is None):
            raise ValueError("raw_response and raw_response_hash must be paired")
        if (self.parsed_response is None) != (self.parsed_response_hash is None):
            raise ValueError("parsed_response and parsed_response_hash must be paired")
        if self.raw_response is not None:
            _require_payload_hash("raw_response_hash", self.raw_response_hash, self.raw_response)
        if self.parsed_response is not None:
            _require_payload_hash(
                "parsed_response_hash", self.parsed_response_hash, self.parsed_response
            )
        started = _require_timestamp("started_at", self.started_at, optional=True)
        finished = _require_timestamp("finished_at", self.finished_at, optional=True)
        if started is not None and finished is not None and finished < started:
            raise ValueError("finished_at cannot precede started_at")
        self._validate_status_contract()
        object.__setattr__(self, "rendered_messages", _freeze(self.rendered_messages))
        object.__setattr__(self, "request_parameters", _freeze(self.request_parameters))
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))
        object.__setattr__(self, "provider_metadata", _freeze(self.provider_metadata))
        object.__setattr__(self, "parsed_response", _freeze(self.parsed_response))
        object.__setattr__(self, "usage", _freeze(self.usage))
        object.__setattr__(self, "error", _freeze(self.error))

    def _validate_status_contract(self) -> None:
        if self.status is EventStatus.PENDING:
            if (
                any(
                    value is not None
                    for value in (
                        self.provider_request_id,
                        self.http_status,
                        self.raw_response,
                        self.parsed_response,
                        self.finish_reason,
                        self.error,
                        self.started_at,
                        self.finished_at,
                    )
                )
                or self.provider_metadata
                or self.usage
            ):
                raise ValueError("pending attempt cannot contain execution evidence")
        elif self.status is EventStatus.IN_PROGRESS:
            if (
                self.started_at is None
                or any(
                    value is not None
                    for value in (
                        self.raw_response,
                        self.parsed_response,
                        self.finish_reason,
                        self.error,
                        self.finished_at,
                    )
                )
                or self.usage
                or self.http_status is not None
            ):
                raise ValueError("in_progress attempt requires only started execution")
        elif self.status is EventStatus.SUCCEEDED:
            required = (
                self.provider_request_id,
                self.raw_response,
                self.parsed_response,
                self.finish_reason,
                self.started_at,
                self.finished_at,
            )
            if (
                any(value is None for value in required)
                or self.error is not None
                or not self.provider_metadata
                or not self.usage
            ):
                raise ValueError("succeeded attempt requires complete response evidence")
            if self.http_status is None or not 200 <= self.http_status < 300:
                raise ValueError("succeeded attempt requires a 2xx HTTP status")
            self._validate_usage()
        elif self.status is EventStatus.FAILED:
            if (
                self.started_at is None
                or self.finished_at is None
                or not self.error
                or self.parsed_response is not None
            ):
                raise ValueError(
                    "failed attempt requires timestamps and error without parsed success content"
                )
            if self.usage:
                self._validate_usage()

    def _validate_usage(self) -> None:
        required = {"prompt_tokens", "completion_tokens", "total_tokens"}
        if not required.issubset(self.usage):
            raise ValueError(
                "usage must contain prompt_tokens, completion_tokens, and total_tokens"
            )
        for key in required:
            _require_int(f"usage[{key}]", self.usage[key])
        if self.usage["total_tokens"] != (
            self.usage["prompt_tokens"] + self.usage["completion_tokens"]
        ):
            raise ValueError("usage total_tokens must equal prompt plus completion tokens")

    def to_payload(self) -> dict[str, object]:
        return _json_ready(
            {
                "attempt_id": self.attempt_id,
                "event_id": self.event_id,
                "attempt_index": self.attempt_index,
                "status": self.status.value,
                "request_id": self.request_id,
                "exposure_id": self.exposure_id,
                "rendered_messages": self.rendered_messages,
                "rendered_prompt_hash": self.rendered_prompt_hash,
                "request_parameters": self.request_parameters,
                "request_parameters_hash": self.request_parameters_hash,
                "model_identity": self.model_identity,
                "model_identity_hash": self.model_identity_hash,
                "model_seed": self.model_seed,
                "provider_request_id": self.provider_request_id,
                "provider_metadata": self.provider_metadata,
                "provider_metadata_hash": self.provider_metadata_hash,
                "http_status": self.http_status,
                "raw_response": self.raw_response,
                "raw_response_hash": self.raw_response_hash,
                "parsed_response": self.parsed_response,
                "parsed_response_hash": self.parsed_response_hash,
                "usage": self.usage,
                "usage_hash": self.usage_hash,
                "finish_reason": self.finish_reason,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> GenerationAttempt:
        expected_fields = {
            "attempt_id",
            "event_id",
            "attempt_index",
            "status",
            "request_id",
            "exposure_id",
            "rendered_messages",
            "rendered_prompt_hash",
            "request_parameters",
            "request_parameters_hash",
            "model_identity",
            "model_identity_hash",
            "model_seed",
            "provider_request_id",
            "provider_metadata",
            "provider_metadata_hash",
            "http_status",
            "raw_response",
            "raw_response_hash",
            "parsed_response",
            "parsed_response_hash",
            "usage",
            "usage_hash",
            "finish_reason",
            "error",
            "started_at",
            "finished_at",
        }
        if type(payload) is not dict or set(payload) != expected_fields:
            raise ValueError("attempt payload fields do not match the v2 contract")
        if type(payload["rendered_messages"]) is not list:
            raise TypeError("attempt rendered_messages must be a JSON array")
        for field_name in ("request_parameters", "model_identity", "provider_metadata", "usage"):
            if type(payload[field_name]) is not dict:
                raise TypeError(f"attempt {field_name} must be a JSON object")
        for field_name in ("parsed_response", "error"):
            if payload[field_name] is not None and type(payload[field_name]) is not dict:
                raise TypeError(f"attempt {field_name} must be a JSON object or null")
        _require_json_transport(payload, "attempt payload")
        try:
            status = EventStatus(payload["status"])
        except (TypeError, ValueError) as error:
            raise ValueError("attempt status is not a runtime EventStatus") from error
        return cls(
            **{
                **payload,
                "status": status,
                "rendered_messages": tuple(payload["rendered_messages"]),  # type: ignore[arg-type]
            }
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    run_id: str
    event_id: str
    event_ordinal: int
    sweep_index: int
    draw_index: int
    agent_id: str
    publish_flag: bool
    exposure_id: str
    status: EventStatus
    attempt_ids: tuple[str, ...]
    failure_reason: str | None

    def __post_init__(self) -> None:
        _require_id("run_id", self.run_id)
        _require_id("event_id", self.event_id)
        _require_int("event_ordinal", self.event_ordinal)
        if self.event_id != derive_event_id(self.run_id, self.event_ordinal):
            raise ValueError("event_id does not match run_id and event_ordinal")
        _require_int("sweep_index", self.sweep_index, minimum=1)
        _require_int("draw_index", self.draw_index)
        _require_id("agent_id", self.agent_id)
        if not isinstance(self.publish_flag, bool):
            raise TypeError("publish_flag must be a boolean")
        _require_id("exposure_id", self.exposure_id)
        if not isinstance(self.status, EventStatus):
            raise TypeError("status must be an EventStatus")
        _require_unique_ids("attempt_ids", self.attempt_ids)
        expected_attempt_ids = tuple(
            derive_attempt_id(self.event_id, attempt_index)
            for attempt_index in range(1, len(self.attempt_ids) + 1)
        )
        if self.attempt_ids != expected_attempt_ids:
            raise ValueError("attempt_ids must be derived from event_id in one-based order")
        _require_string("failure_reason", self.failure_reason, optional=True)
        if self.status is EventStatus.PENDING and len(self.attempt_ids) > 1:
            raise ValueError("pending event may reference at most one pending attempt")
        if (
            self.status
            in {
                EventStatus.IN_PROGRESS,
                EventStatus.SUCCEEDED,
                EventStatus.FAILED,
            }
            and not self.attempt_ids
        ):
            raise ValueError(f"{self.status.value} event requires an attempt")
        if self.status is EventStatus.FAILED:
            if self.failure_reason is None:
                raise ValueError("failed event requires failure_reason")
        elif self.failure_reason is not None:
            raise ValueError("only failed events may have failure_reason")
        object.__setattr__(self, "attempt_ids", tuple(self.attempt_ids))

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "event_id": self.event_id,
            "event_ordinal": self.event_ordinal,
            "sweep_index": self.sweep_index,
            "draw_index": self.draw_index,
            "agent_id": self.agent_id,
            "publish_flag": self.publish_flag,
            "exposure_id": self.exposure_id,
            "status": self.status.value,
            "attempt_ids": list(self.attempt_ids),
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> GenerationEvent:
        expected_fields = {
            "run_id",
            "event_id",
            "event_ordinal",
            "sweep_index",
            "draw_index",
            "agent_id",
            "publish_flag",
            "exposure_id",
            "status",
            "attempt_ids",
            "failure_reason",
        }
        if type(payload) is not dict or set(payload) != expected_fields:
            raise ValueError("event payload fields do not match the v2 contract")
        if type(payload["attempt_ids"]) is not list:
            raise TypeError("event attempt_ids must be a JSON array")
        _require_json_transport(payload, "event payload")
        try:
            status = EventStatus(payload["status"])
        except (TypeError, ValueError) as error:
            raise ValueError("event status is not a runtime EventStatus") from error
        return cls(
            **{
                **payload,
                "status": status,
                "attempt_ids": tuple(payload["attempt_ids"]),  # type: ignore[arg-type]
            }
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ScheduleSlot:
    event_ordinal: int
    sweep_index: int
    draw_index: int
    agent_id: str
    publish_flag: bool

    def __post_init__(self) -> None:
        _require_int("schedule slot event_ordinal", self.event_ordinal)
        _require_int("schedule slot sweep_index", self.sweep_index, minimum=1)
        _require_int("schedule slot draw_index", self.draw_index)
        _require_id("schedule slot agent_id", self.agent_id)
        if not isinstance(self.publish_flag, bool):
            raise TypeError("schedule slot publish_flag must be a boolean")


@dataclass(frozen=True, slots=True)
class FrozenSchedule:
    schema_version: str
    algorithm_id: str
    algorithm_version: str
    population_size: int
    sweep_count: int
    slots: tuple[ScheduleSlot, ...]
    schedule_hash: str = field(init=False)
    count: int = field(init=False)

    def __post_init__(self) -> None:
        _require_string("schedule schema_version", self.schema_version)
        if self.schema_version != "paper1.schedule.v2":
            raise ValueError("schedule schema_version must be paper1.schedule.v2")
        _require_id("schedule algorithm_id", self.algorithm_id)
        _require_string("schedule algorithm_version", self.algorithm_version)
        _require_int("schedule population_size", self.population_size, minimum=1)
        _require_int("schedule sweep_count", self.sweep_count, minimum=1)
        _require_tuple("schedule slots", self.slots)
        if not all(isinstance(slot, ScheduleSlot) for slot in self.slots):
            raise TypeError("schedule slots must contain ScheduleSlot values")
        ordinals = tuple(slot.event_ordinal for slot in self.slots)
        if ordinals != tuple(range(len(self.slots))):
            raise ValueError(
                "schedule event_ordinal values must be a continuous zero-based sequence"
            )
        for slot in self.slots:
            if not 1 <= slot.sweep_index <= self.sweep_count:
                raise ValueError("schedule sweep_index is outside artifact bounds")
            if not 0 <= slot.draw_index < self.population_size:
                raise ValueError("schedule draw_index is outside artifact bounds")
            expected_sweep = slot.event_ordinal // self.population_size + 1
            expected_draw = slot.event_ordinal % self.population_size
            if slot.sweep_index != expected_sweep:
                raise ValueError("schedule sweep_index sequence has a gap or drift")
            if slot.draw_index != expected_draw:
                raise ValueError("schedule draw_index sequence has a gap or drift")
        if len(self.slots) != self.population_size * self.sweep_count:
            raise ValueError("schedule slots must cover population_size draws in every sweep")
        object.__setattr__(self, "schedule_hash", canonical_payload_hash(self.to_payload()))
        object.__setattr__(self, "count", len(self.slots))

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "algorithm_id": self.algorithm_id,
            "algorithm_version": self.algorithm_version,
            "population_size": self.population_size,
            "sweep_count": self.sweep_count,
            "slots": [
                {
                    "event_ordinal": slot.event_ordinal,
                    "sweep_index": slot.sweep_index,
                    "draw_index": slot.draw_index,
                    "agent_id": slot.agent_id,
                    "publish_flag": slot.publish_flag,
                }
                for slot in self.slots
            ],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FrozenSchedule:
        expected_fields = {
            "schema_version",
            "algorithm_id",
            "algorithm_version",
            "population_size",
            "sweep_count",
            "slots",
        }
        if type(payload) is not dict or set(payload) != expected_fields:
            raise ValueError("schedule v1 is unsupported; payload must contain the exact v2 fields")
        raw_slots = payload["slots"]
        if type(raw_slots) is not list:
            raise TypeError("schedule payload slots must be a list")
        slots: list[ScheduleSlot] = []
        slot_fields = {
            "event_ordinal",
            "sweep_index",
            "draw_index",
            "agent_id",
            "publish_flag",
        }
        for raw_slot in raw_slots:
            if type(raw_slot) is not dict or set(raw_slot) != slot_fields:
                raise ValueError("schedule payload slots must contain the exact v2 fields")
            slots.append(ScheduleSlot(**raw_slot))  # type: ignore[arg-type]
        _require_json_transport(payload, "schedule payload")
        return cls(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            algorithm_id=payload["algorithm_id"],  # type: ignore[arg-type]
            algorithm_version=payload["algorithm_version"],  # type: ignore[arg-type]
            population_size=payload["population_size"],  # type: ignore[arg-type]
            sweep_count=payload["sweep_count"],  # type: ignore[arg-type]
            slots=tuple(slots),
        )


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    run_spec: Mapping[str, object]
    run_spec_hash: str
    matched_seed: int
    launch_nonce: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    git_sha: str
    dirty: bool
    diff_hash: str | None
    environment_lock_hash: str
    model_identity: Mapping[str, object]
    environment: Mapping[str, object]
    schedule_uri: str
    schedule: FrozenSchedule
    schedule_hash: str
    checkpoint_uri: str | None
    checkpoint_hash: str | None
    recovery_cursor: Mapping[str, object] | None
    event_ids: tuple[str, ...]
    terminal_counts: Mapping[str, int]
    started_at: str
    updated_at: str
    archive: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_id("run_id", self.run_id)
        if not isinstance(self.run_spec, Mapping) or not self.run_spec:
            raise ValueError("run_spec must be a non-empty mapping")
        _require_sha256("run_spec_hash", self.run_spec_hash)
        _require_payload_hash("run_spec_hash", self.run_spec_hash, self.run_spec)
        _require_int("matched_seed", self.matched_seed)
        _require_string("launch_nonce", self.launch_nonce)
        if self.run_id != derive_run_id(self.run_spec, self.matched_seed, self.launch_nonce):
            raise ValueError("run_id does not match run_spec and launch identity")
        _require_id("protocol_id", self.protocol_id)
        _require_string("protocol_version", self.protocol_version)
        _require_sha256("protocol_hash", self.protocol_hash)
        for key, value in {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_hash": self.protocol_hash,
            "schedule_hash": self.schedule_hash,
        }.items():
            if self.run_spec.get(key) != value:
                raise ValueError(f"run_spec {key} must match manifest")
        if not isinstance(self.git_sha, str) or _GIT_PATTERN.fullmatch(self.git_sha) is None:
            raise ValueError("git_sha must be a 40-character lowercase commit hash")
        if not isinstance(self.dirty, bool):
            raise TypeError("dirty must be a boolean")
        _require_sha256("diff_hash", self.diff_hash, optional=True)
        if self.dirty != (self.diff_hash is not None):
            raise ValueError("dirty and diff_hash must be recorded consistently")
        _require_sha256("environment_lock_hash", self.environment_lock_hash)
        _require_mapping_fields(
            "model_identity",
            self.model_identity,
            ("provider", "model", "revision", "runtime"),
        )
        _require_mapping_fields(
            "environment",
            self.environment,
            ("python_version", "dependency_lock_hash", "platform"),
        )
        _require_sha256(
            "environment[dependency_lock_hash]",
            self.environment["dependency_lock_hash"],
        )
        if self.environment["dependency_lock_hash"] != self.environment_lock_hash:
            raise ValueError("environment lock hashes must match")
        _require_evidence_uri("schedule_uri", self.schedule_uri)
        if not isinstance(self.schedule, FrozenSchedule):
            raise TypeError("schedule must be a FrozenSchedule")
        _require_sha256("schedule_hash", self.schedule_hash)
        if self.schedule_hash != self.schedule.schedule_hash:
            raise ValueError("schedule_hash must match the external frozen schedule")
        self._validate_run_config()
        if self.checkpoint_uri is not None:
            _require_evidence_uri("checkpoint_uri", self.checkpoint_uri)
        _require_sha256("checkpoint_hash", self.checkpoint_hash, optional=True)
        if (self.checkpoint_uri is None) != (self.checkpoint_hash is None):
            raise ValueError("checkpoint_uri and checkpoint_hash must be paired")
        _require_unique_ids("event_ids", self.event_ids)
        expected_ids = tuple(
            derive_event_id(self.run_id, ordinal) for ordinal in range(len(self.event_ids))
        )
        if self.event_ids != expected_ids:
            raise ValueError("event_ids must be the continuous global ordinal prefix")
        self._validate_status_counts()
        self._validate_recovery_cursor()
        started = _require_timestamp("started_at", self.started_at)
        updated = _require_timestamp("updated_at", self.updated_at)
        assert started is not None and updated is not None
        if updated < started:
            raise ValueError("updated_at cannot precede started_at")
        self._validate_archive()
        object.__setattr__(self, "run_spec", _freeze(self.run_spec))
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))
        object.__setattr__(self, "environment", _freeze(self.environment))
        object.__setattr__(self, "recovery_cursor", _freeze(self.recovery_cursor))
        object.__setattr__(self, "event_ids", tuple(self.event_ids))
        object.__setattr__(self, "terminal_counts", _freeze(self.terminal_counts))
        object.__setattr__(self, "archive", _freeze(self.archive))

    def _validate_run_config(self) -> None:
        run_config = self.run_spec.get("run_config")
        if not isinstance(run_config, Mapping):
            raise TypeError("run_spec run_config must be a mapping")
        expected = {
            "population": self.schedule.population_size,
            "sweep_count": self.schedule.sweep_count,
            "expected_event_count": self.schedule.count,
        }
        for key, value in expected.items():
            if run_config.get(key) != value:
                raise ValueError(f"run_spec run_config {key} must match schedule")

    def _validate_status_counts(self) -> None:
        if not isinstance(self.terminal_counts, Mapping):
            raise TypeError("terminal_counts must be a mapping")
        expected_keys = {status.value for status in EventStatus}
        if set(self.terminal_counts) != expected_keys:
            raise ValueError("terminal_counts must enumerate runtime event statuses")
        for status, count in self.terminal_counts.items():
            _require_int(f"terminal_counts[{status}]", count)
        if sum(self.terminal_counts.values()) != len(self.event_ids):
            raise ValueError("terminal_counts must exactly count manifest event_ids")

    def _validate_recovery_cursor(self) -> None:
        if self.recovery_cursor is None:
            if self.is_complete:
                return
            if self.event_ids:
                raise ValueError(
                    "incomplete manifest with observed events requires a recovery_cursor"
                )
            return
        if self.checkpoint_uri is None or self.checkpoint_hash is None:
            raise ValueError("recovery_cursor requires checkpoint evidence")
        if set(self.recovery_cursor) != {"next_event_ordinal", "event_id"}:
            raise ValueError("recovery_cursor must contain only next_event_ordinal and event_id")
        next_ordinal = self.recovery_cursor["next_event_ordinal"]
        _require_int("recovery_cursor[next_event_ordinal]", next_ordinal)
        if next_ordinal >= self.schedule.count:
            raise ValueError("recovery_cursor next_event_ordinal is outside schedule bounds")
        if self.recovery_cursor["event_id"] != derive_event_id(self.run_id, next_ordinal):
            raise ValueError("recovery_cursor event_id does not match next_event_ordinal")
        if self.terminal_counts["succeeded"] != next_ordinal:
            raise ValueError("recovery_cursor must follow the succeeded event prefix")
        if len(self.event_ids) not in {next_ordinal, next_ordinal + 1}:
            raise ValueError("recovery_cursor permits only the current blocking event")
        nonsucceeded = len(self.event_ids) - next_ordinal
        if (
            self.terminal_counts["failed"]
            + self.terminal_counts["pending"]
            + self.terminal_counts["in_progress"]
            != nonsucceeded
        ):
            raise ValueError("recovery_cursor status counts do not match blocking event")

    def _validate_archive(self) -> None:
        if not isinstance(self.archive, Mapping):
            raise TypeError("archive must be a mapping")
        if set(self.archive) != {"status", "uri", "hash"}:
            raise ValueError("archive must contain exactly status, uri, and hash")
        if self.archive["status"] == "pending":
            if self.archive["uri"] is not None or self.archive["hash"] is not None:
                raise ValueError("pending archive cannot have uri or hash")
            if self.is_complete:
                raise ValueError("complete manifest requires a frozen archive")
        elif self.archive["status"] == "frozen":
            _require_evidence_uri("archive[uri]", self.archive["uri"])
            _require_sha256("archive[hash]", self.archive["hash"])
            if not self._all_expected_succeeded:
                raise ValueError("frozen archive requires all expected events succeeded")
        else:
            raise ValueError("archive status must be pending or frozen")

    @property
    def _all_expected_succeeded(self) -> bool:
        return (
            len(self.event_ids) == self.schedule.count
            and self.terminal_counts["succeeded"] == self.schedule.count
            and all(
                self.terminal_counts[status] == 0 for status in ("pending", "in_progress", "failed")
            )
        )

    @property
    def is_complete(self) -> bool:
        return self._all_expected_succeeded and self.archive.get("status") == "frozen"

    @property
    def next_event_ordinal(self) -> int:
        if self.recovery_cursor is None:
            return self.schedule.count if self.is_complete else 0
        value = self.recovery_cursor["next_event_ordinal"]
        assert isinstance(value, int)
        return value

    def to_payload(self) -> dict[str, object]:
        return _json_ready(
            {
                "run_id": self.run_id,
                "run_spec": self.run_spec,
                "run_spec_hash": self.run_spec_hash,
                "matched_seed": self.matched_seed,
                "launch_nonce": self.launch_nonce,
                "protocol_id": self.protocol_id,
                "protocol_version": self.protocol_version,
                "protocol_hash": self.protocol_hash,
                "git_sha": self.git_sha,
                "dirty": self.dirty,
                "diff_hash": self.diff_hash,
                "environment_lock_hash": self.environment_lock_hash,
                "model_identity": self.model_identity,
                "environment": self.environment,
                "schedule_uri": self.schedule_uri,
                "schedule_hash": self.schedule_hash,
                "schedule_count": self.schedule.count,
                "checkpoint_uri": self.checkpoint_uri,
                "checkpoint_hash": self.checkpoint_hash,
                "recovery_cursor": self.recovery_cursor,
                "event_ids": self.event_ids,
                "terminal_counts": self.terminal_counts,
                "started_at": self.started_at,
                "updated_at": self.updated_at,
                "archive": self.archive,
            }
        )

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, object], *, schedule: FrozenSchedule
    ) -> RunManifest:
        expected_fields = {
            "run_id",
            "run_spec",
            "run_spec_hash",
            "matched_seed",
            "launch_nonce",
            "protocol_id",
            "protocol_version",
            "protocol_hash",
            "git_sha",
            "dirty",
            "diff_hash",
            "environment_lock_hash",
            "model_identity",
            "environment",
            "schedule_uri",
            "schedule_hash",
            "schedule_count",
            "checkpoint_uri",
            "checkpoint_hash",
            "recovery_cursor",
            "event_ids",
            "terminal_counts",
            "started_at",
            "updated_at",
            "archive",
        }
        if type(payload) is not dict or set(payload) != expected_fields:
            raise ValueError("manifest payload fields do not match the v2 contract")
        if type(payload["event_ids"]) is not list:
            raise TypeError("manifest payload event_ids must be a JSON array")
        _require_json_transport(payload, "manifest payload")
        _require_int("manifest payload schedule_count", payload["schedule_count"], minimum=1)
        if (
            payload["schedule_hash"] != schedule.schedule_hash
            or payload["schedule_count"] != schedule.count
        ):
            raise ValueError("persisted manifest schedule binding does not match schedule")
        values = dict(payload)
        values.pop("schedule_count")
        values["schedule"] = schedule
        values["event_ids"] = tuple(values["event_ids"])  # type: ignore[arg-type]
        return cls(**values)  # type: ignore[arg-type]


def evaluate_analysis_eligibility(manifest: RunManifest) -> bool:
    """Paper 1 main analysis accepts only runs with every expected event succeeded."""

    if not isinstance(manifest, RunManifest):
        raise TypeError("manifest must be a RunManifest")
    return manifest.is_complete


def validate_evidence_graph(
    manifest: RunManifest,
    events: tuple[GenerationEvent, ...],
    attempts: tuple[GenerationAttempt, ...],
    exposures: tuple[ExposureRecord, ...],
) -> None:
    """Validate an ordinal event chain and its exact immutable evidence."""

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

    ordinals = tuple(event.event_ordinal for event in events)
    if ordinals != tuple(range(len(events))):
        raise ValueError("events must form a continuous zero-based ordinal prefix")
    if tuple(event.event_id for event in events) != manifest.event_ids:
        raise ValueError("manifest event_ids must exactly match the event prefix")
    observed_counts = {
        status.value: sum(event.status is status for event in events) for status in EventStatus
    }
    if dict(manifest.terminal_counts) != observed_counts:
        raise ValueError("manifest terminal_counts must exactly match events")

    first_blocking = next(
        (index for index, event in enumerate(events) if event.status is not EventStatus.SUCCEEDED),
        len(events),
    )
    if any(event.status is EventStatus.SUCCEEDED for event in events[first_blocking:]):
        raise ValueError("no event may succeed after the first failed or nonterminal event")
    if len(events) > first_blocking + 1:
        raise ValueError("evidence may contain only the current event after succeeded prefix")
    if manifest.is_complete and first_blocking != manifest.schedule.count:
        raise ValueError("complete main-path graph requires every event succeeded")
    if not manifest.is_complete and manifest.recovery_cursor is not None:
        if manifest.next_event_ordinal != first_blocking:
            raise ValueError("recovery cursor must identify the first nonsucceeded event")

    referenced_attempt_ids: list[str] = []
    for event in events:
        if event.run_id != manifest.run_id:
            raise ValueError("event run_id must match manifest")
        slot = manifest.schedule.slots[event.event_ordinal]
        if (
            event.sweep_index,
            event.draw_index,
            event.agent_id,
            event.publish_flag,
        ) != (
            slot.sweep_index,
            slot.draw_index,
            slot.agent_id,
            slot.publish_flag,
        ):
            raise ValueError("event attributes must exactly match its schedule slot")
        if event.exposure_id not in exposure_by_id:
            raise ValueError("event exposure_id must identify exposure evidence")
        exposure = exposure_by_id[event.exposure_id]
        if (
            exposure.event_ordinal != event.event_ordinal
            or exposure.receiver_agent_id != event.agent_id
        ):
            raise ValueError("event and exposure ordinal/receiver must match")
        for source_agent_id, source_event_id in zip(
            exposure.source_agent_ids,
            exposure.source_event_ids,
            strict=True,
        ):
            source = event_by_id.get(source_event_id)
            if source is None:
                raise ValueError("exposure source_event_id must identify graph evidence")
            if source.event_ordinal >= event.event_ordinal:
                raise ValueError("exposure sources must be earlier, never future events")
            if source.agent_id != source_agent_id:
                raise ValueError("exposure source agent must match source event")
            if source.status is not EventStatus.SUCCEEDED:
                raise ValueError("exposure source event must be succeeded")

        event_attempts: list[GenerationAttempt] = []
        for attempt_id in event.attempt_ids:
            attempt = attempt_by_id.get(attempt_id)
            if attempt is None:
                raise ValueError("event attempt_ids must identify attempt evidence")
            if attempt.event_id != event.event_id:
                raise ValueError("attempt event_id must match event")
            if attempt.exposure_id != event.exposure_id:
                raise ValueError("attempt exposure_id must match event")
            event_attempts.append(attempt)
            referenced_attempt_ids.append(attempt_id)
        if [attempt.attempt_index for attempt in event_attempts] != list(
            range(1, len(event_attempts) + 1)
        ):
            raise ValueError("attempt_index values must be contiguous and one-based")
        if len({attempt.model_seed for attempt in event_attempts}) > 1:
            raise ValueError("retries must preserve the event model_seed")
        attempt_statuses = [attempt.status for attempt in event_attempts]
        if event.status is EventStatus.SUCCEEDED:
            if (
                not attempt_statuses
                or attempt_statuses[-1] is not EventStatus.SUCCEEDED
                or any(status is not EventStatus.FAILED for status in attempt_statuses[:-1])
            ):
                raise ValueError("succeeded event requires failed retries then success")
        elif event.status is EventStatus.FAILED:
            if not attempt_statuses or any(
                status is not EventStatus.FAILED for status in attempt_statuses
            ):
                raise ValueError("failed event may contain only failed attempts")
        elif event.status is EventStatus.IN_PROGRESS:
            if (
                not attempt_statuses
                or attempt_statuses[-1] is not EventStatus.IN_PROGRESS
                or any(status is not EventStatus.FAILED for status in attempt_statuses[:-1])
            ):
                raise ValueError("in_progress event requires failed retries then current attempt")
        elif event.status is EventStatus.PENDING:
            if any(status is not EventStatus.PENDING for status in attempt_statuses):
                raise ValueError("pending event may contain only a pending attempt")

    if len(referenced_attempt_ids) != len(set(referenced_attempt_ids)):
        raise ValueError("attempt may be referenced by only one event")
    if set(referenced_attempt_ids) != set(attempt_by_id):
        raise ValueError("attempt records must exactly match event references")
    if {event.exposure_id for event in events} != set(exposure_by_id):
        raise ValueError("exposure records must exactly match events")
