"""Loopback-only vLLM adapter with immutable HTTP transport evidence."""

from __future__ import annotations

import base64
from dataclasses import dataclass, fields
from datetime import UTC, datetime
import hashlib
from http.client import HTTPConnection, HTTPResponse
import json
import math
import socket
from threading import Event, RLock, Timer
import time
from typing import Callable, Mapping
from urllib.parse import urlsplit

from ..domain import (
    _freeze,
    _json_ready,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    canonical_payload_hash,
)
from .adapters import ProbeAdapter
from .contracts import ProbeRequest, ProbeResponse


_CALIBRATION_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_ALLOWED_GENERATION_KEYS = {"temperature", "top_p", "max_tokens"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, slots=True)
class VllmTransportEvidence:
    """Exact request/response bytes and HTTP metadata for one adapter call."""

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
    duration_seconds: float
    outcome: str
    error_code: str | None
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.vllm-transport-evidence.v1"

    def __post_init__(self) -> None:
        _require_sha256("request_hash", self.request_hash)
        _require_sha256("request_body_sha256", self.request_body_sha256)
        _require_sha256("raw_body_sha256", self.raw_body_sha256)
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
        if type(self.duration_seconds) is not float or not math.isfinite(self.duration_seconds):
            raise ValueError("duration_seconds must be a finite float")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be nonnegative")
        if not isinstance(self.response_headers, Mapping):
            raise TypeError("response_headers must be a mapping")
        if any(
            type(key) is not str or type(value) is not str
            for key, value in self.response_headers.items()
        ):
            raise TypeError("response headers must contain strings")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "response_headers", _freeze(self.response_headers))

    @property
    def request_body(self) -> bytes:
        return base64.b64decode(self.request_body_base64, validate=True)

    @property
    def raw_body(self) -> bytes:
        return base64.b64decode(self.raw_body_base64, validate=True)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "endpoint": self.endpoint,
            "http_status": self.http_status,
            "response_headers": dict(self.response_headers),
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
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "metadata": dict(_CALIBRATION_METADATA),
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> VllmTransportEvidence:
        expected = {field.name for field in fields(cls)} | {"schema_version", "metadata"}
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("transport evidence payload must contain exact fields")
        _require_json_transport(payload, "transport evidence payload")
        if payload["schema_version"] != cls._SCHEMA_VERSION:
            raise ValueError("transport evidence schema is not supported")
        if payload["metadata"] != _CALIBRATION_METADATA:
            raise ValueError("transport evidence must remain calibration-only")
        if type(payload["response_headers"]) is not dict:
            raise TypeError("transport response_headers must use a JSON object")
        values = {field.name: payload[field.name] for field in fields(cls)}
        return cls(**values)  # type: ignore[arg-type]

    @classmethod
    def create(
        cls,
        *,
        request: ProbeRequest,
        endpoint: str,
        http_status: int | None,
        response_headers: Mapping[str, str],
        provider_request_id: str | None,
        request_body: bytes,
        raw_body: bytes,
        body_truncated: bool,
        started_at: str,
        ended_at: str,
        duration_seconds: float,
        outcome: str,
        error_code: str | None,
    ) -> VllmTransportEvidence:
        values: dict[str, object] = {
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "endpoint": endpoint,
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
            "duration_seconds": duration_seconds,
            "outcome": outcome,
            "error_code": error_code,
        }
        content = {
            "schema_version": cls._SCHEMA_VERSION,
            **values,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]


class VllmProbeAdapter(ProbeAdapter):
    """A no-redirect OpenAI-compatible client restricted to exact loopback."""

    def __init__(
        self,
        endpoint: str,
        *,
        expected_model: str,
        model_revision: str,
        tokenizer_repository: str,
        tokenizer_revision: str,
        runtime_version: str,
        chat_template_hash: str,
        max_response_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("vLLM endpoint must use exact HTTP loopback 127.0.0.1")
        if parsed.path != "/v1/chat/completions" or parsed.query or parsed.fragment:
            raise ValueError("vLLM endpoint path must be exactly /v1/chat/completions")
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("vLLM endpoint port is invalid") from error
        if port is None or not 1 <= port <= 65535:
            raise ValueError("vLLM endpoint must declare an explicit port")
        for name, value in (
            ("expected_model", expected_model),
            ("model_revision", model_revision),
            ("tokenizer_repository", tokenizer_repository),
            ("tokenizer_revision", tokenizer_revision),
            ("runtime_version", runtime_version),
        ):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        _require_sha256("chat_template_hash", chat_template_hash)
        if type(max_response_bytes) is not int or max_response_bytes < 1:
            raise ValueError("max_response_bytes must be a positive integer")
        self.endpoint = endpoint
        self._port = port
        self._expected_model = expected_model
        self._model_revision = model_revision
        self._tokenizer_repository = tokenizer_repository
        self._tokenizer_revision = tokenizer_revision
        self._runtime_version = runtime_version
        self._chat_template_hash = chat_template_hash
        self._max_response_bytes = max_response_bytes
        self._evidence: dict[str, VllmTransportEvidence] = {}
        self._in_flight: set[str] = set()
        self._before_dispatch: Callable[[ProbeRequest, bytes], None] | None = None
        self._lock = RLock()

    def bind_dispatch_journal(self, callback: Callable[[ProbeRequest, bytes], None]) -> None:
        """Bind a one-run durable journal hook before any HTTP bytes are sent."""
        if not callable(callback):
            raise TypeError("dispatch journal callback must be callable")
        with self._lock:
            if self._before_dispatch is not None:
                raise RuntimeError("dispatch journal is already bound")
            if self._evidence or self._in_flight:
                raise RuntimeError("dispatch journal must be bound before adapter use")
            self._before_dispatch = callback

    def evidence_for(self, request_id: str) -> VllmTransportEvidence:
        with self._lock:
            try:
                return self._evidence[request_id]
            except KeyError as error:
                raise KeyError("no transport evidence exists for request") from error

    def generate(
        self,
        request: ProbeRequest,
        *,
        timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> ProbeResponse:
        if not isinstance(request, ProbeRequest):
            raise TypeError("request must be a ProbeRequest")
        if type(timeout_seconds) is not float or not math.isfinite(timeout_seconds):
            raise TypeError("timeout_seconds must be a finite float")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for name, value in (
            ("connect_timeout_seconds", connect_timeout_seconds),
            ("read_timeout_seconds", read_timeout_seconds),
        ):
            if value is None:
                continue
            if type(value) is not float or not math.isfinite(value):
                raise TypeError(f"{name} must be a finite float or null")
            if value <= 0 or value > timeout_seconds:
                raise ValueError(f"{name} must be positive and not exceed timeout_seconds")
        connect_timeout = connect_timeout_seconds or timeout_seconds
        read_timeout = read_timeout_seconds or timeout_seconds
        settings = dict(request.generation_settings)
        if set(settings) != _ALLOWED_GENERATION_KEYS:
            raise ValueError("generation settings must contain only temperature/top_p/max_tokens")
        if type(settings["temperature"]) is not float or not math.isfinite(settings["temperature"]):
            raise ValueError("temperature must be a finite float")
        if type(settings["top_p"]) is not float or not math.isfinite(settings["top_p"]):
            raise ValueError("top_p must be a finite float")
        if type(settings["max_tokens"]) is not int or settings["max_tokens"] < 1:
            raise ValueError("max_tokens must be a positive integer")
        body_payload: dict[str, object] = {
            "model": self._expected_model,
            "messages": request.to_payload()["rendered_messages"],
            "temperature": settings["temperature"],
            "top_p": settings["top_p"],
            "max_tokens": settings["max_tokens"],
            "seed": request.requested_seed,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        _require_json_transport(body_payload, "vLLM request")
        request_body = json.dumps(
            body_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        with self._lock:
            if request.request_id in self._evidence or request.request_id in self._in_flight:
                raise RuntimeError("request already has transport evidence")
            self._in_flight.add(request.request_id)
            before_dispatch = self._before_dispatch
        if before_dispatch is not None:
            try:
                before_dispatch(request, request_body)
            except BaseException:
                with self._lock:
                    self._in_flight.remove(request.request_id)
                raise
        started_at = _utc_now()
        started_clock = time.monotonic()
        deadline = started_clock + timeout_seconds
        status: int | None = None
        headers: dict[str, str] = {}
        provider_request_id: str | None = None
        raw_body = b""
        truncated = False
        response_outcome = "provider_error"
        error_code: str | None = "provider_unreachable"
        retry_after: float | None = None
        parsed: Mapping[str, object] | None = None
        deadline_expired = Event()
        connection: HTTPConnection | None = None
        transport_socket: socket.socket | None = None

        def expire_transport() -> None:
            deadline_expired.set()
            if transport_socket is not None:
                try:
                    transport_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        deadline_timer = Timer(timeout_seconds, expire_transport)
        deadline_timer.daemon = True
        deadline_timer.start()
        try:
            connection = HTTPConnection(
                "127.0.0.1",
                self._port,
                timeout=min(connect_timeout, max(deadline - time.monotonic(), 1e-9)),
            )
            try:
                connection.connect()
                if connection.sock is None:
                    raise OSError("vLLM connection has no socket")
                transport_socket = connection.sock
                transport_socket.settimeout(
                    min(read_timeout, max(deadline - time.monotonic(), 1e-9))
                )
                connection.request(
                    "POST",
                    "/v1/chat/completions",
                    body=request_body,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-Request-Id": request.request_id,
                    },
                )
                transport_socket.settimeout(
                    min(read_timeout, max(deadline - time.monotonic(), 1e-9))
                )
                http_response = connection.getresponse()
                status, headers, provider_request_id = self._read_headers(http_response)
                chunks: list[bytes] = []
                remaining_bytes = self._max_response_bytes + 1
                while remaining_bytes:
                    remaining_seconds = deadline - time.monotonic()
                    if remaining_seconds <= 0:
                        raise TimeoutError("overall transport deadline exceeded")
                    transport_socket.settimeout(min(read_timeout, remaining_seconds))
                    chunk = http_response.read(min(64 * 1024, remaining_bytes))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining_bytes -= len(chunk)
                raw_body = b"".join(chunks)
                truncated = len(raw_body) > self._max_response_bytes
            finally:
                connection.close()
            if truncated:
                error_code = "provider_response_too_large"
            elif 300 <= status < 400:
                error_code = "provider_redirect"
            elif status == 429 or status == 503:
                error_code = "provider_busy"
                retry_after = self._retry_after(headers)
            elif status >= 400:
                if status >= 500 and b"out of memory" in raw_body.lower():
                    response_outcome = "oom"
                    error_code = "oom"
                else:
                    error_code = "provider_fatal"
            else:
                try:
                    candidate = json.loads(raw_body)
                except (UnicodeError, json.JSONDecodeError):
                    error_code = "provider_invalid_json"
                else:
                    if type(candidate) is not dict:
                        error_code = "provider_schema_error"
                    else:
                        parsed = candidate
                        error_code = self._validate_success_payload(
                            parsed, provider_request_id=provider_request_id
                        )
                        if error_code is None:
                            response_outcome = "response"
        except (TimeoutError, socket.timeout):
            response_outcome = "timeout"
            error_code = "timeout"
        except OSError:
            if deadline_expired.is_set() or time.monotonic() >= deadline:
                response_outcome = "timeout"
                error_code = "timeout"
            else:
                response_outcome = "provider_error"
                error_code = "provider_unreachable"
        finally:
            deadline_timer.cancel()
        ended_at = _utc_now()
        duration = float(time.monotonic() - started_clock)
        evidence = VllmTransportEvidence.create(
            request=request,
            endpoint=self.endpoint,
            http_status=status,
            response_headers=headers,
            provider_request_id=provider_request_id,
            request_body=request_body,
            raw_body=raw_body,
            body_truncated=truncated,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            outcome=response_outcome,
            error_code=error_code,
        )
        with self._lock:
            self._in_flight.remove(request.request_id)
            self._evidence[request.request_id] = evidence
        return self._make_response(
            request,
            parsed=parsed,
            provider_request_id=provider_request_id,
            started_at=started_at,
            ended_at=ended_at,
            outcome=response_outcome,
            error_code=error_code,
            retry_after=retry_after,
        )

    @staticmethod
    def _read_headers(response: HTTPResponse) -> tuple[int, dict[str, str], str | None]:
        headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, headers, headers.get("x-request-id")

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

    def _validate_success_payload(
        self, payload: Mapping[str, object], *, provider_request_id: str | None
    ) -> str | None:
        if provider_request_id is None or not provider_request_id.strip():
            return "provider_missing_request_id"
        if payload.get("model") != self._expected_model:
            return "provider_identity_mismatch"
        choices = payload.get("choices")
        usage = payload.get("usage")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            return "provider_schema_error"
        choice = choices[0]
        message = choice.get("message")
        if (
            type(message) is not dict
            or type(message.get("content")) is not str
            or type(choice.get("finish_reason")) is not str
            or type(usage) is not dict
            or type(usage.get("prompt_tokens")) is not int
            or type(usage.get("completion_tokens")) is not int
        ):
            return "provider_schema_error"
        return None

    def _make_response(
        self,
        request: ProbeRequest,
        *,
        parsed: Mapping[str, object] | None,
        provider_request_id: str | None,
        started_at: str,
        ended_at: str,
        outcome: str,
        error_code: str | None,
        retry_after: float | None,
    ) -> ProbeResponse:
        successful = outcome == "response" and error_code is None and parsed is not None
        if successful:
            choice = parsed["choices"][0]  # type: ignore[index]
            usage = parsed["usage"]  # type: ignore[index]
            raw_response = choice["message"]["content"]  # type: ignore[index]
            termination = choice["finish_reason"]  # type: ignore[index]
            input_tokens = usage["prompt_tokens"]  # type: ignore[index]
            output_tokens = usage["completion_tokens"]  # type: ignore[index]
        else:
            raw_response = None
            termination = error_code or outcome
            input_tokens = 0
            output_tokens = 0
        values: dict[str, object] = {
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "probe_case_id": request.probe_case_id,
            "probe_case_hash": request.probe_case_hash,
            "attempt_index": request.attempt_index,
            "attempt_kind": request.attempt_kind,
            "scale_id": request.scale_id,
            "field_order_id": request.field_order_id,
            "generation_settings": dict(request.generation_settings),
            "generation_settings_hash": request.generation_settings_hash,
            "requested_seed": request.requested_seed,
            "provider_seed_supported": successful and request.requested_seed is not None,
            "provider_seed_echo": None,
            "runtime_identity": {
                "provider": "vllm-openai-loopback",
                "runtime_version": self._runtime_version,
            },
            "model_identity": {
                "model": self._expected_model,
                "revision": self._model_revision,
            },
            "tokenizer_identity": {
                "tokenizer": self._tokenizer_repository,
                "revision": self._tokenizer_revision,
            },
            "chat_template_hash": self._chat_template_hash,
            "provider_request_id": provider_request_id
            or f"provider-request-id-unavailable-{request.request_id}",
            "started_at": started_at,
            "ended_at": ended_at,
            "outcome": outcome,
            "termination_reason": termination,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "raw_response": raw_response,
            "raw_response_hash": (
                None if raw_response is None else canonical_payload_hash(raw_response)
            ),
            "error_code": error_code,
            "retry_after_seconds": retry_after,
        }
        identity = {
            "schema_version": ProbeResponse._SCHEMA_VERSION,
            **values,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        response_id = ProbeResponse._ID_PREFIX + canonical_payload_hash(identity)
        content = {**identity, "response_id": response_id}
        return ProbeResponse(
            response_id=response_id,
            **values,
            record_hash=canonical_payload_hash(content),
        )  # type: ignore[arg-type]
