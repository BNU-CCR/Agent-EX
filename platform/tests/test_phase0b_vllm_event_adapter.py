"""Phase 0B real-vLLM event adapter contract tests."""

from __future__ import annotations

import json
import hashlib
from typing import Any

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.phase0b.vllm_event_adapter import (
    PHASE0B_VLLM_ENDPOINT,
    Phase0BVllmEventAdapter,
    Phase0BVllmEventRequest,
    Phase0BVllmTransportEvidence,
)


VALID_BODY = json.dumps(
    {
        "id": "chatcmpl-phase0b",
        "model": "qwen3-8b-paper1",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": '{"stance":4}'},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
    },
    separators=(",", ":"),
).encode("utf-8")


class FakeHTTPResponse:
    def __init__(self, *, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._headers = headers

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers.items())

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class FakeConnection:
    requests: list[dict[str, Any]] = []
    status = 200
    body = VALID_BODY
    headers = {"X-Request-Id": "provider-req-1", "Content-Type": "application/json"}

    def __init__(self, host: str, port: int, timeout: float) -> None:
        assert host == "127.0.0.1"
        assert port == 8000
        assert timeout > 0

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        self.requests.append(
            {
                "method": method,
                "path": path,
                "body": json.loads(body),
                "headers": dict(headers),
            }
        )

    def getresponse(self) -> FakeHTTPResponse:
        return FakeHTTPResponse(status=self.status, body=self.body, headers=self.headers)

    def close(self) -> None:
        return


@pytest.fixture(autouse=True)
def reset_fake_connection() -> None:
    FakeConnection.requests = []
    FakeConnection.status = 200
    FakeConnection.body = VALID_BODY
    FakeConnection.headers = {"X-Request-Id": "provider-req-1", "Content-Type": "application/json"}


def valid_request() -> Phase0BVllmEventRequest:
    return Phase0BVllmEventRequest.create(
        event_id="event-phase0b-0001",
        attempt_index=1,
        prompt_hash=canonical_payload_hash("prompt-view"),
        rendered_messages=(
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "event input"},
        ),
        generation_settings={"temperature": 0.7, "top_p": 0.8, "max_tokens": 128},
        model_seed=12345,
        adapter_binding_hash=canonical_payload_hash("adapter-binding"),
    )


def adapter() -> Phase0BVllmEventAdapter:
    instance = Phase0BVllmEventAdapter(
        PHASE0B_VLLM_ENDPOINT,
        served_model_name="qwen3-8b-paper1",
        max_response_bytes=1024 * 1024,
        connection_factory=FakeConnection,
    )
    instance.bind_dispatch_journal(lambda request, body: None)
    return instance


def test_adapter_preserves_success_identity_body_and_transport_evidence() -> None:
    request = valid_request()

    response = adapter().generate(
        request,
        timeout_seconds=3.0,
        connect_timeout_seconds=1.0,
        read_timeout_seconds=1.0,
    )

    sent = FakeConnection.requests[0]
    assert sent["method"] == "POST"
    assert sent["path"] == "/v1/chat/completions"
    assert sent["headers"]["X-Request-Id"] == request.request_id
    assert sent["body"] == {
        "model": "qwen3-8b-paper1",
        "messages": list(request.rendered_messages),
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": 128,
        "seed": 12345,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    assert response.outcome == "response"
    assert response.provider_request_id == "provider-req-1"
    assert response.raw_body == VALID_BODY
    assert response.raw_body_sha256 == hashlib.sha256(VALID_BODY).hexdigest()
    assert response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}
    assert Phase0BVllmTransportEvidence.from_payload(response.transport_evidence.to_payload())


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:8000/v1/chat/completions?x=1",
        "http://127.0.0.1:8000/v1/chat/completions#frag",
        "http://localhost:8000/v1/chat/completions",
        "http://127.0.0.1:8001/v1/chat/completions",
        "http://127.0.0.1:8000/v1/models",
        "https://127.0.0.1:8000/v1/chat/completions",
    ],
)
def test_adapter_rejects_any_non_exact_endpoint(endpoint: str) -> None:
    with pytest.raises(ValueError, match="exact"):
        Phase0BVllmEventAdapter(
            endpoint,
            served_model_name="qwen3-8b-paper1",
            connection_factory=FakeConnection,
        )


def test_adapter_requires_durable_dispatch_hook_before_network() -> None:
    instance = Phase0BVllmEventAdapter(
        PHASE0B_VLLM_ENDPOINT,
        served_model_name="qwen3-8b-paper1",
        connection_factory=FakeConnection,
    )

    with pytest.raises(RuntimeError, match="dispatch journal"):
        instance.generate(valid_request(), timeout_seconds=3.0)
    assert FakeConnection.requests == []


def test_dispatch_hook_runs_before_http_bytes_are_sent() -> None:
    observed: list[tuple[str, int]] = []

    instance = Phase0BVllmEventAdapter(
        PHASE0B_VLLM_ENDPOINT,
        served_model_name="qwen3-8b-paper1",
        connection_factory=FakeConnection,
    )

    def before_dispatch(request: Phase0BVllmEventRequest, body: bytes) -> None:
        observed.append((request.request_id, len(body)))
        assert FakeConnection.requests == []

    instance.bind_dispatch_journal(before_dispatch)
    instance.generate(valid_request(), timeout_seconds=3.0)

    assert observed and len(FakeConnection.requests) == 1


def test_request_rejects_unallowed_generation_keys_before_network() -> None:
    with pytest.raises(ValueError, match="allowed generation settings"):
        Phase0BVllmEventRequest.create(
            event_id="event-phase0b-0001",
            attempt_index=1,
            prompt_hash=canonical_payload_hash("prompt-view"),
            rendered_messages=({"role": "user", "content": "event input"},),
            generation_settings={
                "temperature": 0.7,
                "top_p": 0.8,
                "max_tokens": 128,
                "presence_penalty": 0.0,
            },
            model_seed=12345,
            adapter_binding_hash=canonical_payload_hash("adapter-binding"),
        )
    assert FakeConnection.requests == []


def test_adapter_maps_invalid_json_429_500_oom_and_response_size_limit() -> None:
    FakeConnection.body = b"not-json"
    invalid = adapter().generate(valid_request(), timeout_seconds=3.0)
    assert invalid.error_code == "provider_invalid_json"

    FakeConnection.status = 429
    FakeConnection.body = b'{"error":"busy"}'
    FakeConnection.headers = {"X-Request-Id": "provider-req-2", "Retry-After": "2.5"}
    busy = adapter().generate(valid_request(), timeout_seconds=3.0)
    assert busy.error_code == "provider_busy"
    assert busy.retry_after_seconds == 2.5

    FakeConnection.status = 500
    FakeConnection.body = b'{"error":"internal"}'
    fatal = adapter().generate(valid_request(), timeout_seconds=3.0)
    assert fatal.error_code == "provider_fatal"

    FakeConnection.status = 500
    FakeConnection.body = b'{"error":"CUDA out of memory"}'
    oom = adapter().generate(valid_request(), timeout_seconds=3.0)
    assert oom.outcome == "oom"
    assert oom.error_code == "oom"

    FakeConnection.status = 200
    FakeConnection.body = VALID_BODY + b" " * 128
    too_large = Phase0BVllmEventAdapter(
        PHASE0B_VLLM_ENDPOINT,
        served_model_name="qwen3-8b-paper1",
        max_response_bytes=len(VALID_BODY),
        connection_factory=FakeConnection,
    )
    too_large.bind_dispatch_journal(lambda request, body: None)
    response = too_large.generate(valid_request(), timeout_seconds=3.0)
    assert response.error_code == "provider_response_too_large"
    assert response.transport_evidence.raw_body_bytes == len(VALID_BODY) + 1


def test_adapter_does_not_follow_redirects() -> None:
    FakeConnection.status = 302
    FakeConnection.headers = {"X-Request-Id": "provider-req-redirect", "Location": "/other"}
    FakeConnection.body = b""

    response = adapter().generate(valid_request(), timeout_seconds=3.0)

    assert response.error_code == "provider_redirect"
    assert [item["path"] for item in FakeConnection.requests] == ["/v1/chat/completions"]
