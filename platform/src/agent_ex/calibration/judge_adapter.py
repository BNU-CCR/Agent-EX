"""Single-dispatch loopback transport and strict parser for the Phase 0A-1 judge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPResponse
import json
import math
import socket
from threading import Event, Timer
import time
from typing import Mapping
from urllib.parse import urlsplit

from .judge_contracts import (
    DIMENSIONS,
    JudgeParseEvidence,
    JudgeRequestEvidence,
    JudgeResponseEvidence,
)
from .review import SemanticReviewPolicy


def canonical_json_bytes(value: object) -> bytes:
    """Encode a JSON value with the frozen compact UTF-8 transport representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class JudgeTransportLimits:
    connect_timeout_seconds: float
    read_timeout_seconds: float
    total_timeout_seconds: float

    def __post_init__(self) -> None:
        for name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "total_timeout_seconds",
        ):
            value = getattr(self, name)
            if type(value) is not float or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite float")
        if self.connect_timeout_seconds > self.total_timeout_seconds:
            raise ValueError("connect timeout cannot exceed the total timeout")
        if self.read_timeout_seconds > self.total_timeout_seconds:
            raise ValueError("read timeout cannot exceed the total timeout")


def _parse_json_object(raw_bytes: bytes) -> tuple[dict[str, object] | None, bool]:
    duplicate = False

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        nonlocal duplicate
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                duplicate = True
            result[key] = value
        return result

    try:
        parsed = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=pairs_hook)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, False
    if type(parsed) is not dict or duplicate:
        return None, False
    return parsed, True


def parse_judge_response(raw_bytes: bytes, policy: SemanticReviewPolicy) -> JudgeParseEvidence:
    """Return typed parse evidence; contract failures never escape as exceptions."""

    if type(raw_bytes) is not bytes:
        raise TypeError("judge parser input must be exact bytes")
    if not isinstance(policy, SemanticReviewPolicy):
        raise TypeError("judge parser policy must be SemanticReviewPolicy")
    parsed, is_object = _parse_json_object(raw_bytes)
    if not is_object or parsed is None:
        return JudgeParseEvidence.create(
            raw_bytes=raw_bytes,
            policy_hash=policy.record_hash,
            labels={},
            failure_code="parse_invalid_json",
        )
    actual = set(parsed)
    required = set(DIMENSIONS)
    if required - actual:
        failure_code = "parse_missing_dimensions"
    elif actual - required:
        failure_code = "parse_extra_dimensions"
    elif any(
        type(parsed[name]) is not str or parsed[name] not in policy.dimension_labels[name]
        for name in DIMENSIONS
    ):
        failure_code = "parse_illegal_label"
    else:
        failure_code = None
    labels = (
        {name: parsed[name] for name in DIMENSIONS}
        if failure_code is None
        else {name: value for name, value in parsed.items() if type(value) is str}
    )
    return JudgeParseEvidence.create(
        raw_bytes=raw_bytes,
        policy_hash=policy.record_hash,
        labels=labels,  # type: ignore[arg-type]
        failure_code=failure_code,
    )


class JudgeVllmAdapter:
    """No-redirect OpenAI-compatible client restricted to exact HTTP loopback."""

    def __init__(
        self,
        endpoint: str,
        *,
        model_id: str,
        limits: JudgeTransportLimits,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("judge endpoint must use exact HTTP loopback 127.0.0.1")
        if parsed.path != "/v1/chat/completions" or parsed.query or parsed.fragment:
            raise ValueError("judge loopback endpoint path must be /v1/chat/completions")
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("judge loopback endpoint port is invalid") from error
        if port is None or not 1 <= port <= 65535:
            raise ValueError("judge loopback endpoint requires an explicit valid port")
        if type(model_id) is not str or not model_id.strip():
            raise ValueError("judge model_id must be nonempty")
        if not isinstance(limits, JudgeTransportLimits):
            raise TypeError("judge transport limits are required")
        self.endpoint = endpoint
        self._port = port
        self._model_id = model_id
        self._limits = limits

    def generate(self, request: JudgeRequestEvidence) -> JudgeResponseEvidence:
        """Dispatch one HTTP request exactly once and return immutable typed evidence."""

        if not isinstance(request, JudgeRequestEvidence):
            raise TypeError("judge request must be JudgeRequestEvidence")
        if request.model_id != self._model_id:
            raise ValueError("judge request model differs from adapter model")
        request_body = canonical_json_bytes(request.provider_payload())
        started_at = _utc_now()
        started_clock = time.monotonic()
        deadline = started_clock + self._limits.total_timeout_seconds
        status: int | None = None
        headers: dict[str, str] = {}
        raw_bytes = b""
        output_bytes: bytes | None = None
        provider_request_id: str | None = None
        response_model: str | None = None
        termination: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        failure_code: str | None = "provider_unreachable"
        retry_after: float | None = None
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

        timer = Timer(self._limits.total_timeout_seconds, expire_transport)
        timer.daemon = True
        timer.start()
        try:
            connection = HTTPConnection(
                "127.0.0.1",
                self._port,
                timeout=self._limits.connect_timeout_seconds,
            )
            connection.connect()
            if connection.sock is None:
                raise OSError("judge connection has no socket")
            transport_socket = connection.sock
            transport_socket.settimeout(
                min(self._limits.read_timeout_seconds, max(deadline - time.monotonic(), 1e-9))
            )
            connection.request(
                "POST",
                "/v1/chat/completions",
                body=request_body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-Id": request.request_id,
                    "Idempotency-Key": request.rendered_request.idempotency_key,
                },
            )
            response = connection.getresponse()
            status, headers = self._headers(response)
            provider_request_id = headers.get("x-request-id")
            raw_bytes, exceeded = self._read_body(
                response,
                deadline=deadline,
                ceiling=request.response_byte_ceiling,
            )
            if exceeded:
                failure_code = "response_size_exceeded"
            elif status == 429:
                failure_code = "http_429"
                retry_after = self._retry_after(headers)
            elif status >= 500 and b"out of memory" in raw_bytes.lower():
                failure_code = "provider_oom"
            elif status >= 500:
                failure_code = "http_5xx"
            elif status >= 400 or 300 <= status < 400:
                failure_code = "http_error"
            else:
                payload, valid_object = _parse_json_object(raw_bytes)
                if not valid_object or payload is None:
                    failure_code = "provider_invalid_json"
                elif provider_request_id is None or not provider_request_id.strip():
                    failure_code = "provider_request_identity_missing"
                elif payload.get("model") != self._model_id:
                    failure_code = "provider_model_identity_drift"
                    response_model = (
                        payload.get("model") if type(payload.get("model")) is str else None
                    )
                else:
                    (
                        failure_code,
                        output_bytes,
                        response_model,
                        termination,
                        input_tokens,
                        output_tokens,
                    ) = self._success_fields(payload)
        except (TimeoutError, socket.timeout):
            failure_code = "timeout"
        except OSError:
            failure_code = (
                "timeout"
                if deadline_expired.is_set() or time.monotonic() >= deadline
                else "provider_unreachable"
            )
        finally:
            timer.cancel()
            if connection is not None:
                connection.close()
        ended_at = _utc_now()
        return JudgeResponseEvidence.create(
            request=request,
            provider_request_id=provider_request_id,
            http_status=status,
            response_headers=headers,
            raw_bytes=raw_bytes,
            output_bytes=output_bytes,
            model_id=response_model,
            termination=termination,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            failure_code=failure_code,
            retry_after_seconds=retry_after,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=float(time.monotonic() - started_clock),
        )

    @staticmethod
    def _headers(response: HTTPResponse) -> tuple[int, dict[str, str]]:
        return response.status, {name.lower(): value for name, value in response.getheaders()}

    def _read_body(
        self,
        response: HTTPResponse,
        *,
        deadline: float,
        ceiling: int,
    ) -> tuple[bytes, bool]:
        chunks: list[bytes] = []
        remaining = ceiling + 1
        while remaining:
            time_left = deadline - time.monotonic()
            if time_left <= 0:
                raise TimeoutError("judge total transport deadline exceeded")
            chunk = response.read(min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        return raw, len(raw) > ceiling

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

    @staticmethod
    def _success_fields(
        payload: Mapping[str, object],
    ) -> tuple[str | None, bytes | None, str | None, str | None, int | None, int | None]:
        choices = payload.get("choices")
        usage = payload.get("usage")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            return "provider_invalid_json", None, None, None, None, None
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
            return "provider_invalid_json", None, None, None, None, None
        return (
            None,
            message["content"].encode("utf-8"),
            payload["model"],
            choice["finish_reason"],
            usage["prompt_tokens"],
            usage["completion_tokens"],
        )
