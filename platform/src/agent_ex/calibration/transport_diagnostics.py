"""Deterministic loopback-only transport diagnostics for Phase 0A-1 smoke."""

from __future__ import annotations

import base64
from dataclasses import dataclass, fields
from datetime import UTC, datetime
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
from threading import Thread
import time
from typing import ClassVar, Mapping
from urllib.parse import urlsplit

from ..domain import (
    _freeze,
    _json_ready,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    canonical_payload_hash,
)
from .cloud import SmokeManifest
from .contracts import ProbeRuntimePolicy
from .environment import EnvironmentLock, EnvironmentObservation, verify_current_environment


_VLLM_ENDPOINT = "http://127.0.0.1:8000/v1/chat/completions"
_DIAGNOSTIC_ORDER = (
    "closed-port",
    "controlled-timeout",
    "http-429-retry-after",
)


def _require_positive_float(name: str, value: object) -> None:
    if type(value) is not float:
        raise TypeError(f"{name} must be a float")
    if value <= 0 or not float(value) < float("inf"):
        raise ValueError(f"{name} must be finite and positive")


def _loopback_parts(endpoint: str) -> tuple[str, int, str]:
    if not isinstance(endpoint, str):
        raise TypeError("diagnostic endpoint must be a string")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/diagnostic/")
    ):
        raise ValueError("diagnostic endpoint must be an isolated loopback HTTP endpoint")
    if parsed.port == 8000 or endpoint == _VLLM_ENDPOINT:
        raise ValueError("diagnostic endpoint must not name the vLLM service")
    return parsed.hostname, parsed.port, parsed.path


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@dataclass(frozen=True, slots=True)
class DiagnosticCase:
    """One fixed non-model transport-classification challenge."""

    diagnostic_id: str
    endpoint: str
    expected_error_code: str
    timeout_seconds: float
    retry_after_header: str | None

    def __post_init__(self) -> None:
        if self.diagnostic_id not in _DIAGNOSTIC_ORDER:
            raise ValueError("diagnostic_id is not supported")
        _, _, path = _loopback_parts(self.endpoint)
        if path != f"/diagnostic/{self.diagnostic_id}":
            raise ValueError("diagnostic endpoint path does not match diagnostic_id")
        expected = {
            "closed-port": "provider_unreachable",
            "controlled-timeout": "timeout",
            "http-429-retry-after": "provider_busy",
        }[self.diagnostic_id]
        if self.expected_error_code != expected:
            raise ValueError("diagnostic classification does not match diagnostic_id")
        _require_positive_float("timeout_seconds", self.timeout_seconds)
        if self.diagnostic_id == "http-429-retry-after":
            if self.retry_after_header != "17":
                raise ValueError("HTTP 429 diagnostic requires Retry-After 17")
        elif self.retry_after_header is not None:
            raise ValueError("Retry-After is only valid for the HTTP 429 diagnostic")

    def content_payload(self) -> dict[str, object]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "endpoint": self.endpoint,
            "expected_error_code": self.expected_error_code,
            "timeout_seconds": self.timeout_seconds,
            "retry_after_header": self.retry_after_header,
        }

    @classmethod
    def closed_port(cls, *, port: int, timeout_seconds: float = 0.1) -> DiagnosticCase:
        return cls(
            diagnostic_id="closed-port",
            endpoint=f"http://127.0.0.1:{port}/diagnostic/closed-port",
            expected_error_code="provider_unreachable",
            timeout_seconds=timeout_seconds,
            retry_after_header=None,
        )

    @classmethod
    def controlled_timeout(cls, *, port: int, timeout_seconds: float) -> DiagnosticCase:
        return cls(
            diagnostic_id="controlled-timeout",
            endpoint=f"http://127.0.0.1:{port}/diagnostic/controlled-timeout",
            expected_error_code="timeout",
            timeout_seconds=timeout_seconds,
            retry_after_header=None,
        )

    @classmethod
    def http_429(
        cls, *, port: int, timeout_seconds: float = 0.1, retry_after_header: str = "17"
    ) -> DiagnosticCase:
        return cls(
            diagnostic_id="http-429-retry-after",
            endpoint=f"http://127.0.0.1:{port}/diagnostic/http-429-retry-after",
            expected_error_code="provider_busy",
            timeout_seconds=timeout_seconds,
            retry_after_header=retry_after_header,
        )


@dataclass(frozen=True, slots=True)
class TransportDiagnosticEvidence:
    """Canonical evidence from one non-model loopback diagnostic."""

    schema_version: str
    diagnostic_id: str
    endpoint: str
    endpoint_identity_hash: str
    input_hash: str
    expected_error_code: str
    actual_error_code: str
    timeout_seconds: float
    retry_after_header: str | None
    transport_attempt_count: int
    started_at: str
    ended_at: str
    duration_seconds: float
    http_status: int | None
    response_headers: Mapping[str, str]
    raw_body_base64: str
    raw_body_sha256: str
    raw_error: str | None
    model_request_count: int
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    _SCHEMA_VERSION: ClassVar[str] = "paper1.calibration.transport-diagnostic.v1"

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA_VERSION:
            raise ValueError("transport diagnostic schema_version is not supported")
        case = DiagnosticCase(
            diagnostic_id=self.diagnostic_id,
            endpoint=self.endpoint,
            expected_error_code=self.expected_error_code,
            timeout_seconds=self.timeout_seconds,
            retry_after_header=self.retry_after_header,
        )
        _require_sha256("endpoint_identity_hash", self.endpoint_identity_hash)
        _require_payload_hash("endpoint_identity_hash", self.endpoint_identity_hash, self.endpoint)
        _require_sha256("input_hash", self.input_hash)
        _require_payload_hash("input_hash", self.input_hash, case.content_payload())
        if self.actual_error_code != self.expected_error_code:
            raise ValueError("transport diagnostic classification does not match expectation")
        _require_int("transport_attempt_count", self.transport_attempt_count, minimum=1)
        if self.transport_attempt_count != 1:
            raise ValueError("transport diagnostic must use exactly one attempt")
        _require_int("model_request_count", self.model_request_count, minimum=0)
        if self.model_request_count != 0:
            raise ValueError("transport diagnostics must not issue model requests")
        if not isinstance(self.started_at, str) or not self.started_at:
            raise TypeError("started_at must be a non-empty string")
        if not isinstance(self.ended_at, str) or not self.ended_at:
            raise TypeError("ended_at must be a non-empty string")
        if type(self.duration_seconds) is not float or self.duration_seconds < 0:
            raise ValueError("duration_seconds must be a nonnegative float")
        if self.http_status is not None and type(self.http_status) is not int:
            raise TypeError("http_status must be an integer or null")
        if type(self.response_headers) is not dict:
            raise TypeError("response_headers must be an exact mapping")
        for name, value in self.response_headers.items():
            if not isinstance(name, str) or name != name.lower() or not isinstance(value, str):
                raise ValueError("response headers must use lowercase string names and values")
        try:
            raw_body = base64.b64decode(self.raw_body_base64, validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("raw_body_base64 is invalid") from error
        _require_sha256("raw_body_sha256", self.raw_body_sha256)
        if hashlib.sha256(raw_body).hexdigest() != self.raw_body_sha256:
            raise ValueError("raw body hash does not match bytes")
        if self.raw_error is not None and not isinstance(self.raw_error, str):
            raise TypeError("raw_error must be a string or null")
        if self.calibration_only is not True or self.formal_parameter_authority is not False:
            raise ValueError("transport diagnostics must remain calibration-only")
        object.__setattr__(self, "response_headers", _freeze(dict(self.response_headers)))
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in (field.name for field in fields(self))
            if name != "record_hash"
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        case: DiagnosticCase,
        actual_error_code: str,
        started_at: str,
        ended_at: str,
        duration_seconds: float,
        response_headers: Mapping[str, str],
        raw_body: bytes,
        raw_error: str | None,
        http_status: int | None = None,
    ) -> TransportDiagnosticEvidence:
        if not isinstance(case, DiagnosticCase):
            raise TypeError("transport diagnostic requires a DiagnosticCase")
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA_VERSION,
            "diagnostic_id": case.diagnostic_id,
            "endpoint": case.endpoint,
            "endpoint_identity_hash": canonical_payload_hash(case.endpoint),
            "input_hash": canonical_payload_hash(case.content_payload()),
            "expected_error_code": case.expected_error_code,
            "actual_error_code": actual_error_code,
            "timeout_seconds": case.timeout_seconds,
            "retry_after_header": case.retry_after_header,
            "transport_attempt_count": 1,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "http_status": http_status,
            "response_headers": dict(sorted(response_headers.items())),
            "raw_body_base64": base64.b64encode(raw_body).decode("ascii"),
            "raw_body_sha256": hashlib.sha256(raw_body).hexdigest(),
            "raw_error": raw_error,
            "model_request_count": 0,
            "calibration_only": True,
            "formal_parameter_authority": False,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> TransportDiagnosticEvidence:
        expected = {field.name for field in fields(cls)}
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("transport diagnostic payload must contain exact fields")
        _require_json_transport(payload, "transport diagnostic payload")
        if type(payload["response_headers"]) is not dict:
            raise TypeError("response_headers must use a JSON object")
        return cls(**payload)  # type: ignore[arg-type]


def diagnostic_cases(*, timeout_seconds: float) -> tuple[DiagnosticCase, ...]:
    """Materialize the fixed diagnostics on isolated ephemeral loopback ports."""
    _require_positive_float("timeout_seconds", timeout_seconds)
    ports: list[int] = []
    while len(ports) < 3:
        candidate = _reserve_port()
        if candidate != 8000 and candidate not in ports:
            ports.append(candidate)
    return (
        DiagnosticCase.closed_port(port=ports[0], timeout_seconds=timeout_seconds),
        DiagnosticCase.controlled_timeout(port=ports[1], timeout_seconds=timeout_seconds),
        DiagnosticCase.http_429(port=ports[2], timeout_seconds=timeout_seconds),
    )


class _QuietHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


class _DiagnosticServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def _serve_case(case: DiagnosticCase) -> tuple[_DiagnosticServer, Thread]:
    _, port, _ = _loopback_parts(case.endpoint)

    if case.diagnostic_id == "controlled-timeout":

        class Handler(_QuietHandler):
            def do_POST(self) -> None:  # noqa: N802
                time.sleep(case.timeout_seconds + 0.05)
                try:
                    self.send_response(204)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError):
                    return

    else:

        class Handler(_QuietHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = b"busy"
                self.send_response(429)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Retry-After", "17")
                self.end_headers()
                self.wfile.write(body)

    server = _DiagnosticServer(("127.0.0.1", port), Handler)
    thread = Thread(target=server.serve_forever, name=f"diagnostic-{case.diagnostic_id}")
    thread.start()
    return server, thread


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _verify_closed_port(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as verifier:
        try:
            verifier.bind((host, port))
        except OSError as error:
            raise RuntimeError("closed-port diagnostic endpoint is already in use") from error


def _execute_case(case: DiagnosticCase) -> TransportDiagnosticEvidence:
    host, port, path = _loopback_parts(case.endpoint)
    server: _DiagnosticServer | None = None
    thread: Thread | None = None
    if case.diagnostic_id == "closed-port":
        _verify_closed_port(host, port)
    else:
        server, thread = _serve_case(case)
    started_at = _utc_now()
    start = time.perf_counter()
    actual_error_code: str | None = None
    raw_error: str | None = None
    raw_body = b""
    response_headers: dict[str, str] = {}
    http_status: int | None = None
    connection = HTTPConnection(host, port, timeout=case.timeout_seconds)
    try:
        connection.request("POST", path, body=b"{}", headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        http_status = response.status
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        raw_body = response.read()
        if response.status == 429:
            actual_error_code = "provider_busy"
    except (TimeoutError, socket.timeout) as error:
        actual_error_code = "timeout"
        raw_error = type(error).__name__
    except OSError as error:
        actual_error_code = "provider_unreachable"
        raw_error = type(error).__name__
    finally:
        connection.close()
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=1.0)
    if actual_error_code is None:
        raise RuntimeError("controlled transport diagnostic produced no classified outcome")
    return TransportDiagnosticEvidence.create(
        case=case,
        actual_error_code=actual_error_code,
        started_at=started_at,
        ended_at=_utc_now(),
        duration_seconds=float(time.perf_counter() - start),
        response_headers=response_headers,
        raw_body=raw_body,
        raw_error=raw_error,
        http_status=http_status,
    )


def run_transport_diagnostics(
    *,
    manifest: SmokeManifest,
    environment_lock: EnvironmentLock,
    current_observation: EnvironmentObservation,
    policy: ProbeRuntimePolicy,
    vllm_endpoint: str,
) -> tuple[TransportDiagnosticEvidence, ...]:
    """Run the three non-model diagnostics under an approved environment lock."""
    if not isinstance(manifest, SmokeManifest):
        raise TypeError("transport diagnostics require a strict SmokeManifest")
    if not isinstance(environment_lock, EnvironmentLock):
        raise TypeError("transport diagnostics require an EnvironmentLock")
    if not isinstance(current_observation, EnvironmentObservation):
        raise TypeError("transport diagnostics require an EnvironmentObservation")
    if not isinstance(policy, ProbeRuntimePolicy):
        raise TypeError("transport diagnostics require a ProbeRuntimePolicy")
    if vllm_endpoint != manifest.endpoint or vllm_endpoint != _VLLM_ENDPOINT:
        raise ValueError("transport diagnostics require the approved vLLM identity boundary")
    if environment_lock.authorization_hash != manifest.record_hash:
        raise ValueError("environment lock authorization does not match smoke manifest")
    if manifest.runtime_policy_hash != policy.record_hash:
        raise ValueError("transport diagnostics runtime policy does not match smoke manifest")
    required = {"provider_busy", "provider_unreachable", "timeout"}
    if not required.issubset(policy.retryable_error_codes):
        raise ValueError("transport diagnostics require all controlled retryable error codes")
    if any(policy.max_transport_attempts_by_code[code] != 1 for code in required):
        raise ValueError("transport diagnostics require one attempt per controlled error code")
    if policy.obey_retry_after or policy.backoff_seconds:
        raise ValueError("transport diagnostics require no retry-after or backoff execution")

    verify_current_environment(environment_lock, current_observation)
    records: list[TransportDiagnosticEvidence] = []
    for case in diagnostic_cases(timeout_seconds=policy.timeout_seconds):
        verify_current_environment(environment_lock, current_observation)
        records.append(_execute_case(case))
        verify_current_environment(environment_lock, current_observation)
    return tuple(records)
