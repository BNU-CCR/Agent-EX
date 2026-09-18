"""Loopback-only vLLM transport and evidence tests."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
from typing import Any

import pytest

from agent_ex.calibration.adapters import ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.contracts import ProbeRequest
from agent_ex.calibration.vllm_adapter import VllmProbeAdapter, VllmTransportEvidence
from agent_ex.domain import canonical_payload_hash
from test_calibration_runner import run, specification_and_cases, steps_for_first, valid_raw


MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CHAT_TEMPLATE_HASH = canonical_payload_hash("qwen3-non-thinking-chat-template")
ANSWER = '{"stance":4,"confidence":3,"public_reason":"Synthetic reason."}'
VALID_RAW_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-test-1",
        "model": "qwen3-8b-paper1",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ANSWER},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21},
    },
    separators=(",", ":"),
).encode("utf-8")


class FakeVllmServer:
    def __init__(self, *, port: int = 0) -> None:
        self.status = 200
        self.body = VALID_RAW_RESPONSE
        self.headers: dict[str, str] = {"X-Request-Id": "req-test-1"}
        self.delay_seconds = 0.0
        self.trickle_chunk_bytes = 0
        self.trickle_delay_seconds = 0.0
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                request_body = json.loads(raw)
                owner.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": request_body,
                    }
                )
                if owner.delay_seconds:
                    time.sleep(owner.delay_seconds)
                self.send_response(owner.status)
                for name, value in owner.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                try:
                    response_body = owner.body
                    if owner.body == VALID_RAW_RESPONSE:
                        prompt = request_body["messages"][-1]["content"]
                        if "exact field order: public_reason,confidence,stance" in prompt:
                            payload = json.loads(VALID_RAW_RESPONSE)
                            payload["choices"][0]["message"]["content"] = (
                                '{"public_reason":"Synthetic reason.","confidence":3,"stance":4}'
                            )
                            response_body = json.dumps(payload, separators=(",", ":")).encode(
                                "utf-8"
                            )
                    if owner.trickle_chunk_bytes:
                        for offset in range(0, len(response_body), owner.trickle_chunk_bytes):
                            self.wfile.write(
                                response_body[offset : offset + owner.trickle_chunk_bytes]
                            )
                            self.wfile.flush()
                            time.sleep(owner.trickle_delay_seconds)
                    else:
                        self.wfile.write(response_body)
                except OSError:
                    pass

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1/chat/completions"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


@pytest.fixture
def fake_vllm_server() -> FakeVllmServer:
    server = FakeVllmServer()
    try:
        yield server
    finally:
        server.close()


def valid_request(*, generation_settings: dict[str, object] | None = None) -> ProbeRequest:
    _, cases = specification_and_cases()
    return ProbeRequest.create(
        cases[0],
        attempt_index=1,
        attempt_kind="semantic",
        generation_settings=generation_settings
        or {"temperature": 0.7, "top_p": 0.8, "max_tokens": 128},
    )


def adapter(endpoint: str, *, max_response_bytes: int = 1024 * 1024) -> VllmProbeAdapter:
    return VllmProbeAdapter(
        endpoint,
        expected_model="qwen3-8b-paper1",
        model_revision=MODEL_REVISION,
        tokenizer_repository="Qwen/Qwen3-8B",
        tokenizer_revision=MODEL_REVISION,
        runtime_version="0.23.0",
        chat_template_hash=CHAT_TEMPLATE_HASH,
        max_response_bytes=max_response_bytes,
    )


def test_adapter_preserves_raw_success_and_identity(fake_vllm_server: FakeVllmServer) -> None:
    probe = adapter(fake_vllm_server.endpoint)
    request = valid_request()

    response = probe.generate(request, timeout_seconds=3.0)
    evidence = probe.evidence_for(request.request_id)

    assert response.outcome == "response"
    assert response.provider_request_id == "req-test-1"
    assert response.model_identity["revision"] == MODEL_REVISION
    assert response.raw_response == ANSWER
    assert evidence.raw_body == VALID_RAW_RESPONSE
    assert evidence.http_status == 200
    assert evidence.raw_body_bytes == len(VALID_RAW_RESPONSE)
    assert evidence.request_hash == request.record_hash
    sent = fake_vllm_server.requests[0]["body"]
    assert sent == {
        "model": "qwen3-8b-paper1",
        "messages": request.to_payload()["rendered_messages"],
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": 128,
        "seed": request.requested_seed,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def test_adapter_sends_exact_bound_four_message_repair_history(
    fake_vllm_server: FakeVllmServer,
) -> None:
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(
                ProbeScriptStep("response", "not-json", None, None),
                ProbeScriptStep("response", valid_raw(), None, None),
            )
        )
    )
    request = projection.attempts[-1].request

    response = adapter(fake_vllm_server.endpoint).generate(request, timeout_seconds=3.0)

    assert response.outcome == "response"
    sent_messages = fake_vllm_server.requests[0]["body"]["messages"]
    assert sent_messages == request.to_payload()["rendered_messages"]
    assert [message["role"] for message in sent_messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert sent_messages[2]["content"] == "not-json"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:8000/v1/chat/completions",
        "http://localhost:8000/v1/chat/completions",
        "http://0.0.0.0:8000/v1/chat/completions",
        "http://127.0.0.1:8000/v1/models",
        "http://127.0.0.1/v1/chat/completions",
    ],
)
def test_adapter_rejects_non_exact_loopback_endpoint(endpoint: str) -> None:
    with pytest.raises(ValueError, match="loopback|endpoint|port"):
        adapter(endpoint)


def test_adapter_maps_timeout_without_internal_retry(fake_vllm_server: FakeVllmServer) -> None:
    fake_vllm_server.delay_seconds = 0.2
    probe = adapter(fake_vllm_server.endpoint)
    request = valid_request()

    response = probe.generate(request, timeout_seconds=0.05)

    assert response.outcome == "timeout"
    assert response.error_code == "timeout"
    assert response.provider_seed_supported is False
    assert response.provider_seed_echo is None
    assert len(fake_vllm_server.requests) == 1
    assert probe.evidence_for(request.request_id).outcome == "timeout"


def test_adapter_enforces_read_timeout_separately_from_overall_timeout(
    fake_vllm_server: FakeVllmServer,
) -> None:
    fake_vllm_server.delay_seconds = 0.2
    probe = adapter(fake_vllm_server.endpoint)
    request = valid_request()

    response = probe.generate(
        request,
        timeout_seconds=3.0,
        connect_timeout_seconds=1.0,
        read_timeout_seconds=0.05,
    )

    assert response.outcome == "timeout"
    assert response.error_code == "timeout"
    assert probe.evidence_for(request.request_id).outcome == "timeout"


def test_adapter_overall_deadline_stops_trickled_body_before_read_timeout(
    fake_vllm_server: FakeVllmServer,
) -> None:
    fake_vllm_server.trickle_chunk_bytes = 16
    fake_vllm_server.trickle_delay_seconds = 0.04
    probe = adapter(fake_vllm_server.endpoint)
    request = valid_request()

    started = time.monotonic()
    response = probe.generate(
        request,
        timeout_seconds=0.12,
        connect_timeout_seconds=0.1,
        read_timeout_seconds=0.1,
    )
    elapsed = time.monotonic() - started

    assert response.outcome == "timeout"
    assert response.error_code == "timeout"
    assert elapsed < 0.4


def test_adapter_uses_connect_timeout_when_opening_socket(monkeypatch) -> None:
    observed: list[float] = []

    class RefusingConnection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            assert host == "127.0.0.1"
            assert port == 8000
            observed.append(timeout)

        def connect(self) -> None:
            raise OSError("synthetic refusal")

        def close(self) -> None:
            return

    monkeypatch.setattr("agent_ex.calibration.vllm_adapter.HTTPConnection", RefusingConnection)
    response = adapter("http://127.0.0.1:8000/v1/chat/completions").generate(
        valid_request(),
        timeout_seconds=3.0,
        connect_timeout_seconds=0.25,
        read_timeout_seconds=2.0,
    )

    assert response.error_code == "provider_unreachable"
    assert observed == [0.25]


def test_adapter_maps_invalid_json_and_preserves_bytes(fake_vllm_server: FakeVllmServer) -> None:
    fake_vllm_server.body = b"not-json"
    probe = adapter(fake_vllm_server.endpoint)
    request = valid_request()

    response = probe.generate(request, timeout_seconds=3.0)

    assert response.outcome == "provider_error"
    assert response.error_code == "provider_invalid_json"
    assert probe.evidence_for(request.request_id).raw_body == b"not-json"


def test_adapter_maps_429_and_retry_after(fake_vllm_server: FakeVllmServer) -> None:
    fake_vllm_server.status = 429
    fake_vllm_server.headers["Retry-After"] = "1.5"
    fake_vllm_server.body = b'{"error":"busy"}'
    response = adapter(fake_vllm_server.endpoint).generate(valid_request(), timeout_seconds=3.0)

    assert response.outcome == "provider_error"
    assert response.error_code == "provider_busy"
    assert response.retry_after_seconds == 1.5


def test_adapter_maps_http_500_and_oom(fake_vllm_server: FakeVllmServer) -> None:
    fake_vllm_server.status = 500
    fake_vllm_server.body = b'{"error":"internal"}'
    response = adapter(fake_vllm_server.endpoint).generate(valid_request(), timeout_seconds=3.0)
    assert response.outcome == "provider_error"
    assert response.error_code == "provider_fatal"

    second = FakeVllmServer()
    try:
        second.status = 500
        second.body = b'{"error":"CUDA out of memory"}'
        response = adapter(second.endpoint).generate(valid_request(), timeout_seconds=3.0)
        assert response.outcome == "oom"
        assert response.error_code == "oom"
    finally:
        second.close()


def test_adapter_does_not_follow_redirects(fake_vllm_server: FakeVllmServer) -> None:
    fake_vllm_server.status = 302
    fake_vllm_server.headers["Location"] = "/redirected"
    fake_vllm_server.body = b""
    response = adapter(fake_vllm_server.endpoint).generate(valid_request(), timeout_seconds=3.0)

    assert response.error_code == "provider_redirect"
    assert [item["path"] for item in fake_vllm_server.requests] == ["/v1/chat/completions"]


def test_adapter_rejects_wrong_model_and_missing_request_id(
    fake_vllm_server: FakeVllmServer,
) -> None:
    wrong = json.loads(VALID_RAW_RESPONSE)
    wrong["model"] = "wrong-model"
    fake_vllm_server.body = json.dumps(wrong).encode("utf-8")
    response = adapter(fake_vllm_server.endpoint).generate(valid_request(), timeout_seconds=3.0)
    assert response.error_code == "provider_identity_mismatch"

    second = FakeVllmServer()
    try:
        second.headers.clear()
        response = adapter(second.endpoint).generate(valid_request(), timeout_seconds=3.0)
        assert response.error_code == "provider_missing_request_id"
    finally:
        second.close()


def test_adapter_enforces_response_size_limit(fake_vllm_server: FakeVllmServer) -> None:
    fake_vllm_server.body = VALID_RAW_RESPONSE + b" " * 128
    probe = adapter(fake_vllm_server.endpoint, max_response_bytes=len(VALID_RAW_RESPONSE))
    request = valid_request()

    response = probe.generate(request, timeout_seconds=3.0)

    assert response.error_code == "provider_response_too_large"
    assert probe.evidence_for(request.request_id).raw_body_bytes == len(VALID_RAW_RESPONSE) + 1


def test_adapter_rejects_unregistered_generation_keys_before_network(
    fake_vllm_server: FakeVllmServer,
) -> None:
    request = valid_request(
        generation_settings={
            "temperature": 0.7,
            "top_p": 0.8,
            "max_tokens": 128,
            "top_k": 20,
        }
    )

    with pytest.raises(ValueError, match="generation settings"):
        adapter(fake_vllm_server.endpoint).generate(request, timeout_seconds=3.0)
    assert fake_vllm_server.requests == []


def test_transport_evidence_is_append_only(fake_vllm_server: FakeVllmServer) -> None:
    probe = adapter(fake_vllm_server.endpoint)
    request = valid_request()
    probe.generate(request, timeout_seconds=3.0)

    with pytest.raises(RuntimeError, match="already has transport evidence"):
        probe.generate(request, timeout_seconds=3.0)


def test_transport_evidence_round_trips_and_rejects_byte_drift(
    fake_vllm_server: FakeVllmServer,
) -> None:
    probe = adapter(fake_vllm_server.endpoint)
    request = valid_request()
    probe.generate(request, timeout_seconds=3.0)
    evidence = probe.evidence_for(request.request_id)

    assert VllmTransportEvidence.from_payload(evidence.to_payload()) == evidence

    payload = evidence.to_payload()
    payload["raw_body_base64"] = "dGFtcGVyZWQ="
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    with pytest.raises(ValueError, match="raw body byte hash drift"):
        VllmTransportEvidence.from_payload(payload)
