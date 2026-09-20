"""Real vLLM event adapter boundary for the Phase 0B diagnostic fast track."""

from __future__ import annotations

import base64
from dataclasses import dataclass, fields
from datetime import UTC, datetime
import hashlib
from http.client import HTTPConnection
import json
import math
import time
from typing import Callable, Mapping
from urllib.parse import urlsplit

from ..domain import (
    _freeze,
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
    derive_attempt_id,
)


PHASE0B_VLLM_ENDPOINT = "http://127.0.0.1:8000/v1/chat/completions"
_REQUEST_SCHEMA = "paper1.phase0b.vllm-event-request.v1"
_TRANSPORT_SCHEMA = "paper1.phase0b.vllm-transport-evidence.v1"
_RESPONSE_SCHEMA = "paper1.phase0b.vllm-event-response.v1"
_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_ALLOWED_GENERATION_KEYS = {"temperature", "top_p", "max_tokens"}
_ALLOWED_BODY_KEYS = {
    "model",
    "messages",
    "temperature",
    "top_p",
    "max_tokens",
    "seed",
    "chat_template_kwargs",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_float(name: str, value: object) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise TypeError(f"{name} must be a finite float")
    return value


def _strict_body(payload: Mapping[str, object]) -> None:
    if type(payload) is not dict or set(payload) != _ALLOWED_BODY_KEYS:
        raise ValueError("vLLM event body must contain exactly the allowed keys")
    template_kwargs = payload.get("chat_template_kwargs")
    if template_kwargs != {"enable_thinking": False}:
        raise ValueError("vLLM event body must set enable_thinking=false")
    _require_json_transport(payload, "vLLM event body")


@dataclass(frozen=True, slots=True)
class Phase0BVllmEventRequest:
    """One event-level provider request, separate from mock adapter records."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    request_id: str
    event_id: str
    attempt_index: int
    attempt_id: str
    prompt_hash: str
    rendered_messages: tuple[Mapping[str, str], ...]
    rendered_messages_hash: str
    generation_settings: Mapping[str, object]
    generation_settings_hash: str
    model_seed: int
    adapter_binding_hash: str
    record_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != _REQUEST_SCHEMA:
            raise ValueError("Phase 0B vLLM request schema is unsupported")
        if self.calibration_only is not True or type(self.calibration_only) is not bool:
            raise ValueError("Phase 0B vLLM request must remain calibration_only=true")
        if (
            self.formal_parameter_authority is not False
            or type(self.formal_parameter_authority) is not bool
        ):
            raise ValueError("Phase 0B vLLM request cannot grant formal authority")
        if self.research_parameter_status != "not_frozen":
            raise ValueError("Phase 0B vLLM request must remain not_frozen")
        for name in ("request_id", "event_id", "attempt_id"):
            _require_id(name, getattr(self, name))
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if self.attempt_id != derive_attempt_id(self.event_id, self.attempt_index):
            raise ValueError("attempt_id does not match event and attempt index")
        _require_sha256("prompt_hash", self.prompt_hash)
        if type(self.rendered_messages) is not tuple or not self.rendered_messages:
            raise ValueError("rendered_messages must be a non-empty tuple")
        for message in self.rendered_messages:
            if type(message) is not dict or set(message) != {"role", "content"}:
                raise ValueError("each rendered message must contain exact role/content fields")
            if message["role"] not in {"system", "user", "assistant"}:
                raise ValueError("rendered message role is unsupported")
            _require_string("rendered message content", message["content"])
        _require_sha256("rendered_messages_hash", self.rendered_messages_hash)
        _require_payload_hash(
            "rendered_messages_hash", self.rendered_messages_hash, self.rendered_messages
        )
        self._validate_generation_settings()
        _require_sha256("generation_settings_hash", self.generation_settings_hash)
        _require_payload_hash(
            "generation_settings_hash",
            self.generation_settings_hash,
            dict(self.generation_settings),
        )
        _require_int("model_seed", self.model_seed)
        _require_sha256("adapter_binding_hash", self.adapter_binding_hash)
        expected_request_id = "phase0b-vllm-request-" + canonical_payload_hash(
            {
                "event_id": self.event_id,
                "attempt_index": self.attempt_index,
                "prompt_hash": self.prompt_hash,
                "rendered_messages_hash": self.rendered_messages_hash,
                "generation_settings_hash": self.generation_settings_hash,
                "model_seed": self.model_seed,
                "adapter_binding_hash": self.adapter_binding_hash,
            }
        )
        if self.request_id != expected_request_id:
            raise ValueError("request_id does not match Phase 0B vLLM request identity")
        object.__setattr__(self, "rendered_messages", _freeze(self.rendered_messages))
        object.__setattr__(self, "generation_settings", _freeze(self.generation_settings))
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def _validate_generation_settings(self) -> None:
        if type(self.generation_settings) is not dict:
            raise TypeError("generation_settings must be a strict mapping")
        if set(self.generation_settings) != _ALLOWED_GENERATION_KEYS:
            raise ValueError("request uses non-allowed generation settings")
        _strict_float("temperature", self.generation_settings["temperature"])
        _strict_float("top_p", self.generation_settings["top_p"])
        max_tokens = self.generation_settings["max_tokens"]
        if type(max_tokens) is not int or max_tokens < 1:
            raise ValueError("max_tokens must be a positive strict integer")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calibration_only": self.calibration_only,
            "formal_parameter_authority": self.formal_parameter_authority,
            "research_parameter_status": self.research_parameter_status,
            "request_id": self.request_id,
            "event_id": self.event_id,
            "attempt_index": self.attempt_index,
            "attempt_id": self.attempt_id,
            "prompt_hash": self.prompt_hash,
            "rendered_messages": self.rendered_messages,
            "rendered_messages_hash": self.rendered_messages_hash,
            "generation_settings": self.generation_settings,
            "generation_settings_hash": self.generation_settings_hash,
            "model_seed": self.model_seed,
            "adapter_binding_hash": self.adapter_binding_hash,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        attempt_index: int,
        prompt_hash: str,
        rendered_messages: tuple[Mapping[str, str], ...],
        generation_settings: Mapping[str, object],
        model_seed: int,
        adapter_binding_hash: str,
    ) -> Phase0BVllmEventRequest:
        messages_hash = canonical_payload_hash(rendered_messages)
        settings_hash = canonical_payload_hash(dict(generation_settings))
        attempt_id = derive_attempt_id(event_id, attempt_index)
        request_id = "phase0b-vllm-request-" + canonical_payload_hash(
            {
                "event_id": event_id,
                "attempt_index": attempt_index,
                "prompt_hash": prompt_hash,
                "rendered_messages_hash": messages_hash,
                "generation_settings_hash": settings_hash,
                "model_seed": model_seed,
                "adapter_binding_hash": adapter_binding_hash,
            }
        )
        content = {
            "schema_version": _REQUEST_SCHEMA,
            **_METADATA,
            "request_id": request_id,
            "event_id": event_id,
            "attempt_index": attempt_index,
            "attempt_id": attempt_id,
            "prompt_hash": prompt_hash,
            "rendered_messages": rendered_messages,
            "rendered_messages_hash": messages_hash,
            "generation_settings": dict(generation_settings),
            "generation_settings_hash": settings_hash,
            "model_seed": model_seed,
            "adapter_binding_hash": adapter_binding_hash,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Phase0BVllmTransportEvidence:
    """Immutable HTTP evidence for exactly one Phase 0B event transport."""

    schema_version: str
    request_id: str
    request_hash: str
    endpoint: str
    http_status: int | None
    response_headers: Mapping[str, str]
    provider_request_id: str | None
    request_body_base64: str
    request_body_sha256: str
    request_body_bytes: int
    raw_body_base64: str
    raw_body_sha256: str
    raw_body_bytes: int
    body_truncated: bool
    started_at: str
    ended_at: str
    latency_seconds: float
    outcome: str
    error_code: str | None
    record_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != _TRANSPORT_SCHEMA:
            raise ValueError("Phase 0B transport evidence schema is unsupported")
        _require_id("request_id", self.request_id)
        _require_sha256("request_hash", self.request_hash)
        if self.endpoint != PHASE0B_VLLM_ENDPOINT:
            raise ValueError("Phase 0B transport evidence endpoint drifted")
        if self.http_status is not None:
            _require_int("http_status", self.http_status, minimum=100)
        if type(self.response_headers) is not dict:
            raise TypeError("response_headers must be a strict mapping")
        for key, value in self.response_headers.items():
            _require_string("response header name", key)
            _require_string("response header value", value)
        if self.provider_request_id is not None:
            _require_string("provider_request_id", self.provider_request_id)
        if self.request_body_sha256 != _sha256_bytes(self.request_body):
            raise ValueError("request body byte hash drift")
        if self.raw_body_sha256 != _sha256_bytes(self.raw_body):
            raise ValueError("raw body byte hash drift")
        if self.request_body_bytes != len(self.request_body):
            raise ValueError("request body byte count drift")
        if self.raw_body_bytes != len(self.raw_body):
            raise ValueError("raw body byte count drift")
        if type(self.body_truncated) is not bool:
            raise TypeError("body_truncated must be a boolean")
        _strict_float("latency_seconds", self.latency_seconds)
        if self.latency_seconds < 0:
            raise ValueError("latency_seconds must be nonnegative")
        _require_string("outcome", self.outcome)
        if self.error_code is not None:
            _require_string("error_code", self.error_code)
        object.__setattr__(self, "response_headers", _freeze(self.response_headers))
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def request_body(self) -> bytes:
        return base64.b64decode(self.request_body_base64, validate=True)

    @property
    def raw_body(self) -> bytes:
        return base64.b64decode(self.raw_body_base64, validate=True)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "endpoint": self.endpoint,
            "http_status": self.http_status,
            "response_headers": self.response_headers,
            "provider_request_id": self.provider_request_id,
            "request_body_base64": self.request_body_base64,
            "request_body_sha256": self.request_body_sha256,
            "request_body_bytes": self.request_body_bytes,
            "raw_body_base64": self.raw_body_base64,
            "raw_body_sha256": self.raw_body_sha256,
            "raw_body_bytes": self.raw_body_bytes,
            "body_truncated": self.body_truncated,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "latency_seconds": self.latency_seconds,
            "outcome": self.outcome,
            "error_code": self.error_code,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Phase0BVllmTransportEvidence:
        expected = {field.name for field in fields(cls)}
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("Phase 0B transport evidence payload fields do not match")
        _require_json_transport(payload, "Phase 0B transport evidence")
        return cls(**payload)  # type: ignore[arg-type]

    @classmethod
    def create(
        cls,
        *,
        request: Phase0BVllmEventRequest,
        http_status: int | None,
        response_headers: Mapping[str, str],
        provider_request_id: str | None,
        request_body: bytes,
        raw_body: bytes,
        body_truncated: bool,
        started_at: str,
        ended_at: str,
        latency_seconds: float,
        outcome: str,
        error_code: str | None,
    ) -> Phase0BVllmTransportEvidence:
        content = {
            "schema_version": _TRANSPORT_SCHEMA,
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "endpoint": PHASE0B_VLLM_ENDPOINT,
            "http_status": http_status,
            "response_headers": dict(sorted(response_headers.items())),
            "provider_request_id": provider_request_id,
            "request_body_base64": base64.b64encode(request_body).decode("ascii"),
            "request_body_sha256": _sha256_bytes(request_body),
            "request_body_bytes": len(request_body),
            "raw_body_base64": base64.b64encode(raw_body).decode("ascii"),
            "raw_body_sha256": _sha256_bytes(raw_body),
            "raw_body_bytes": len(raw_body),
            "body_truncated": body_truncated,
            "started_at": started_at,
            "ended_at": ended_at,
            "latency_seconds": latency_seconds,
            "outcome": outcome,
            "error_code": error_code,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Phase0BVllmEventResponse:
    """Sanitized event response wrapper plus immutable raw transport evidence."""

    schema_version: str
    request_id: str
    request_hash: str
    event_id: str
    attempt_index: int
    attempt_id: str
    outcome: str
    error_code: str | None
    retry_after_seconds: float | None
    provider_request_id: str | None
    usage: Mapping[str, int]
    finish_reason: str | None
    raw_body_base64: str
    raw_body_sha256: str
    transport_evidence: Phase0BVllmTransportEvidence
    record_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != _RESPONSE_SCHEMA:
            raise ValueError("Phase 0B vLLM response schema is unsupported")
        for name in ("request_id", "event_id", "attempt_id"):
            _require_id(name, getattr(self, name))
        _require_sha256("request_hash", self.request_hash)
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if self.attempt_id != derive_attempt_id(self.event_id, self.attempt_index):
            raise ValueError("attempt_id does not match event and attempt index")
        _require_string("outcome", self.outcome)
        if self.error_code is not None:
            _require_string("error_code", self.error_code)
        if self.retry_after_seconds is not None:
            _strict_float("retry_after_seconds", self.retry_after_seconds)
        if self.provider_request_id is not None:
            _require_string("provider_request_id", self.provider_request_id)
        if type(self.usage) is not dict or set(self.usage) != {
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        }:
            raise ValueError("usage must contain prompt/completion/total token counts")
        for key, value in self.usage.items():
            _require_int(f"usage.{key}", value)
        if self.finish_reason is not None:
            _require_string("finish_reason", self.finish_reason)
        if self.raw_body_sha256 != _sha256_bytes(self.raw_body):
            raise ValueError("raw body hash drift")
        if not isinstance(self.transport_evidence, Phase0BVllmTransportEvidence):
            raise TypeError("transport_evidence must be typed evidence")
        object.__setattr__(self, "usage", _freeze(self.usage))
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def raw_body(self) -> bytes:
        return base64.b64decode(self.raw_body_base64, validate=True)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "event_id": self.event_id,
            "attempt_index": self.attempt_index,
            "attempt_id": self.attempt_id,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "retry_after_seconds": self.retry_after_seconds,
            "provider_request_id": self.provider_request_id,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "raw_body_base64": self.raw_body_base64,
            "raw_body_sha256": self.raw_body_sha256,
            "transport_evidence": self.transport_evidence.to_payload(),
        }

    @classmethod
    def create(
        cls,
        *,
        request: Phase0BVllmEventRequest,
        outcome: str,
        error_code: str | None,
        retry_after_seconds: float | None,
        provider_request_id: str | None,
        usage: Mapping[str, int],
        finish_reason: str | None,
        raw_body: bytes,
        transport_evidence: Phase0BVllmTransportEvidence,
    ) -> Phase0BVllmEventResponse:
        content = {
            "schema_version": _RESPONSE_SCHEMA,
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "event_id": request.event_id,
            "attempt_index": request.attempt_index,
            "attempt_id": request.attempt_id,
            "outcome": outcome,
            "error_code": error_code,
            "retry_after_seconds": retry_after_seconds,
            "provider_request_id": provider_request_id,
            "usage": dict(usage),
            "finish_reason": finish_reason,
            "raw_body_base64": base64.b64encode(raw_body).decode("ascii"),
            "raw_body_sha256": _sha256_bytes(raw_body),
            "transport_evidence": transport_evidence,
        }
        hash_content = {
            **content,
            "transport_evidence": transport_evidence.to_payload(),
        }
        return cls(
            **content,
            record_hash=canonical_payload_hash(hash_content),
        )  # type: ignore[arg-type]


class Phase0BVllmEventAdapter:
    """A no-redirect event adapter restricted to the approved loopback endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        served_model_name: str,
        max_response_bytes: int = 16 * 1024 * 1024,
        connection_factory: type[HTTPConnection] = HTTPConnection,
    ) -> None:
        if endpoint != PHASE0B_VLLM_ENDPOINT:
            raise ValueError("Phase 0B vLLM endpoint must be the exact approved endpoint")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != 8000
            or parsed.path != "/v1/chat/completions"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Phase 0B vLLM endpoint must be exact")
        _require_string("served_model_name", served_model_name)
        if type(max_response_bytes) is not int or max_response_bytes < 1:
            raise ValueError("max_response_bytes must be a positive strict integer")
        self.endpoint = endpoint
        self._served_model_name = served_model_name
        self._max_response_bytes = max_response_bytes
        self._connection_factory = connection_factory
        self._before_dispatch: Callable[[Phase0BVllmEventRequest, bytes], None] | None = None
        self._evidence: dict[str, Phase0BVllmTransportEvidence] = {}

    def bind_dispatch_journal(
        self,
        callback: Callable[[Phase0BVllmEventRequest, bytes], None],
    ) -> None:
        if not callable(callback):
            raise TypeError("dispatch journal callback must be callable")
        if self._before_dispatch is not None:
            raise RuntimeError("dispatch journal is already bound")
        if self._evidence:
            raise RuntimeError("dispatch journal must be bound before adapter use")
        self._before_dispatch = callback

    def evidence_for(self, request_id: str) -> Phase0BVllmTransportEvidence:
        try:
            return self._evidence[request_id]
        except KeyError as error:
            raise KeyError("no Phase 0B transport evidence exists for request") from error

    def generate(
        self,
        request: Phase0BVllmEventRequest,
        *,
        timeout_seconds: float,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> Phase0BVllmEventResponse:
        if not isinstance(request, Phase0BVllmEventRequest):
            raise TypeError("request must be a Phase0BVllmEventRequest")
        timeout_seconds = _strict_float("timeout_seconds", timeout_seconds)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for name, value in (
            ("connect_timeout_seconds", connect_timeout_seconds),
            ("read_timeout_seconds", read_timeout_seconds),
        ):
            if value is None:
                continue
            parsed_timeout = _strict_float(name, value)
            if parsed_timeout <= 0 or parsed_timeout > timeout_seconds:
                raise ValueError(f"{name} must be positive and not exceed total timeout")
        if self._before_dispatch is None:
            raise RuntimeError("durable dispatch journal must be bound before network dispatch")
        if request.request_id in self._evidence:
            raise RuntimeError("request already has Phase 0B transport evidence")
        body = self._request_body(request)
        self._before_dispatch(request, body)
        started_at = _utc_now()
        start = time.monotonic()
        status: int | None = None
        headers: dict[str, str] = {}
        provider_request_id: str | None = None
        raw_body = b""
        truncated = False
        outcome = "provider_error"
        error_code: str | None = "provider_unreachable"
        retry_after: float | None = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        finish_reason: str | None = None
        connection = self._connection_factory(
            "127.0.0.1",
            8000,
            timeout=connect_timeout_seconds or timeout_seconds,
        )
        try:
            connection.request(
                "POST",
                "/v1/chat/completions",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-Request-Id": request.request_id,
                },
            )
            response = connection.getresponse()
            status, headers, provider_request_id = self._read_headers(response)
            chunks: list[bytes] = []
            remaining = self._max_response_bytes + 1
            while remaining:
                chunk = response.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw_body = b"".join(chunks)
            truncated = len(raw_body) > self._max_response_bytes
        except TimeoutError:
            outcome = "timeout"
            error_code = "timeout"
        except OSError:
            outcome = "provider_error"
            error_code = "provider_unreachable"
        finally:
            connection.close()
        if raw_body or status is not None:
            outcome, error_code, retry_after, usage, finish_reason = self._classify(
                status=status,
                headers=headers,
                raw_body=raw_body,
                truncated=truncated,
                provider_request_id=provider_request_id,
            )
        ended_at = _utc_now()
        evidence = Phase0BVllmTransportEvidence.create(
            request=request,
            http_status=status,
            response_headers=headers,
            provider_request_id=provider_request_id,
            request_body=body,
            raw_body=raw_body,
            body_truncated=truncated,
            started_at=started_at,
            ended_at=ended_at,
            latency_seconds=float(time.monotonic() - start),
            outcome=outcome,
            error_code=error_code,
        )
        self._evidence[request.request_id] = evidence
        return Phase0BVllmEventResponse.create(
            request=request,
            outcome=outcome,
            error_code=error_code,
            retry_after_seconds=retry_after,
            provider_request_id=provider_request_id,
            usage=usage,
            finish_reason=finish_reason,
            raw_body=raw_body,
            transport_evidence=evidence,
        )

    def _request_body(self, request: Phase0BVllmEventRequest) -> bytes:
        settings = dict(request.generation_settings)
        body = {
            "model": self._served_model_name,
            "messages": [dict(message) for message in request.rendered_messages],
            "temperature": settings["temperature"],
            "top_p": settings["top_p"],
            "max_tokens": settings["max_tokens"],
            "seed": request.model_seed,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        _strict_body(body)
        return json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @staticmethod
    def _read_headers(response: object) -> tuple[int, dict[str, str], str | None]:
        headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, headers, headers.get("x-request-id")

    def _classify(
        self,
        *,
        status: int | None,
        headers: Mapping[str, str],
        raw_body: bytes,
        truncated: bool,
        provider_request_id: str | None,
    ) -> tuple[str, str | None, float | None, dict[str, int], str | None]:
        empty_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if truncated:
            return "provider_error", "provider_response_too_large", None, empty_usage, None
        if status is None:
            return "provider_error", "provider_unreachable", None, empty_usage, None
        if 300 <= status < 400:
            return "provider_error", "provider_redirect", None, empty_usage, None
        if status in {429, 503}:
            return "provider_error", "provider_busy", self._retry_after(headers), empty_usage, None
        if status >= 400:
            if status >= 500 and b"out of memory" in raw_body.lower():
                return "oom", "oom", None, empty_usage, None
            return "provider_error", "provider_fatal", None, empty_usage, None
        try:
            payload = json.loads(raw_body)
        except (UnicodeError, json.JSONDecodeError):
            return "provider_error", "provider_invalid_json", None, empty_usage, None
        if type(payload) is not dict:
            return "provider_error", "provider_schema_error", None, empty_usage, None
        if provider_request_id is None or not provider_request_id.strip():
            return "provider_error", "provider_missing_request_id", None, empty_usage, None
        if payload.get("model") != self._served_model_name:
            return "provider_error", "provider_identity_mismatch", None, empty_usage, None
        choices = payload.get("choices")
        usage = payload.get("usage")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            return "provider_error", "provider_schema_error", None, empty_usage, None
        choice = choices[0]
        message = choice.get("message")
        if (
            type(message) is not dict
            or type(message.get("content")) is not str
            or type(choice.get("finish_reason")) is not str
            or type(usage) is not dict
        ):
            return "provider_error", "provider_schema_error", None, empty_usage, None
        parsed_usage = self._usage(usage)
        if parsed_usage is None:
            return "provider_error", "provider_schema_error", None, empty_usage, None
        return "response", None, None, parsed_usage, choice["finish_reason"]

    @staticmethod
    def _usage(usage: Mapping[str, object]) -> dict[str, int] | None:
        values: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if type(value) is not int or value < 0:
                return None
            values[key] = value
        return values

    @staticmethod
    def _retry_after(headers: Mapping[str, str]) -> float | None:
        value = headers.get("retry-after")
        if value is None:
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) and parsed >= 0 else None
