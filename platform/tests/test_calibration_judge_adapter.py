from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import time

import pytest

from agent_ex.calibration.judge_adapter import (
    JudgeTransportLimits,
    JudgeVllmAdapter,
    canonical_json_bytes,
    parse_judge_response,
)
from agent_ex.calibration.judge_contracts import (
    DIMENSIONS,
    JudgeRequestEvidence,
    JudgeResponseEvidence,
    JudgeRequestRenderer,
)
from agent_ex.calibration.review import BlindReviewItem, SemanticReviewPolicy
from agent_ex.domain import canonical_payload_hash


POLICY_PATH = (
    Path(__file__).parents[1]
    / "configs"
    / "paper1"
    / "phase0a1-approval-proposal-v2"
    / "semantic_review_policy.json"
)
SHA_A = "a" * 64
LIMITS = JudgeTransportLimits(
    connect_timeout_seconds=0.25,
    read_timeout_seconds=0.25,
    total_timeout_seconds=0.35,
)


@pytest.fixture
def policy() -> SemanticReviewPolicy:
    return SemanticReviewPolicy.from_payload(json.loads(POLICY_PATH.read_text(encoding="utf-8")))


@pytest.fixture
def valid_request(policy: SemanticReviewPolicy) -> JudgeRequestEvidence:
    item = BlindReviewItem.create(
        item_id="blind-item-adapter-001",
        policy_hash=policy.record_hash,
        visible_payload={
            "topic_text": "测试议题",
            "history_text": "",
            "identity_text": "",
            "response_text": "我支持。",
        },
    )
    fixture_content = {
        "schema_version": "paper1.calibration.judge-rendered-request-golden-input.v1",
        "item": item.to_payload(),
        "attempt_index": 1,
        "repair": False,
    }
    renderer = JudgeRequestRenderer.create(
        policy,
        chat_template_hash=SHA_A,
        response_byte_ceiling=4096,
        generation_settings={"temperature": 0.0, "top_p": 1.0, "max_tokens": 512},
        golden_fixture_content=fixture_content,
    )
    return JudgeRequestEvidence.create(
        rendered_request=renderer.render(item, 1, repair=False),
        manifest_hash=SHA_A,
        order_index=0,
        model_id="qwen",
    )


@pytest.fixture
def valid_labels(policy: SemanticReviewPolicy) -> dict[str, str]:
    return {name: policy.dimension_labels[name][0] for name in DIMENSIONS}


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com/v1/chat/completions",
        "http://0.0.0.0:8000/v1/chat/completions",
        "https://127.0.0.1:8000/v1/chat/completions",
    ],
)
def test_adapter_rejects_non_loopback(endpoint: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        JudgeVllmAdapter(endpoint=endpoint, model_id="qwen", limits=LIMITS)


def test_request_and_parse_contracts_are_strict_hashed_and_immutable(
    valid_request: JudgeRequestEvidence,
    policy: SemanticReviewPolicy,
    valid_labels: dict[str, str],
) -> None:
    assert JudgeRequestEvidence.from_payload(valid_request.to_payload()) == valid_request
    with pytest.raises(TypeError):
        valid_request.generation_settings["temperature"] = 0.2  # type: ignore[index]

    parsed = parse_judge_response(canonical_json_bytes(valid_labels), policy)
    assert parsed.success is True
    assert parsed.failure_code is None
    assert dict(parsed.labels) == valid_labels
    assert parsed.record_hash == parsed.from_payload(parsed.to_payload()).record_hash
    with pytest.raises(TypeError):
        parsed.labels["refusal"] = "refused"  # type: ignore[index]


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    (
        (b"not-json", "parse_invalid_json"),
        (b"[]", "parse_invalid_json"),
    ),
)
def test_parser_rejects_invalid_json_object(
    raw: bytes, expected_code: str, policy: SemanticReviewPolicy
) -> None:
    evidence = parse_judge_response(raw, policy)
    assert evidence.success is False
    assert evidence.failure_code == expected_code
    assert evidence.raw_bytes == raw


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_parser_requires_exact_eight_dimensions(
    mutation: str,
    policy: SemanticReviewPolicy,
    valid_labels: dict[str, str],
) -> None:
    labels = dict(valid_labels)
    if mutation == "missing":
        labels.pop("information_fidelity")
        expected = "parse_missing_dimensions"
    else:
        labels["unexpected"] = "value"
        expected = "parse_extra_dimensions"
    evidence = parse_judge_response(canonical_json_bytes(labels), policy)
    assert evidence.success is False
    assert evidence.failure_code == expected


def test_parser_rejects_illegal_label(
    policy: SemanticReviewPolicy, valid_labels: dict[str, str]
) -> None:
    valid_labels["refusal"] = "outside-policy"
    evidence = parse_judge_response(canonical_json_bytes(valid_labels), policy)
    assert evidence.success is False
    assert evidence.failure_code == "parse_illegal_label"


def test_valid_refusal_code_is_not_a_transport_failure(
    policy: SemanticReviewPolicy, valid_labels: dict[str, str]
) -> None:
    assert "refused" in policy.dimension_labels["refusal"]
    valid_labels["refusal"] = "refused"
    evidence = parse_judge_response(canonical_json_bytes(valid_labels), policy)
    assert evidence.success is True
    assert evidence.labels["refusal"] == "refused"


class _FakeJudgeServer:
    def __init__(self, outcome: str, labels: dict[str, str]) -> None:
        self.outcome = outcome
        self.labels = labels
        self.request_count = 0
        self.request_bodies: list[bytes] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                owner.request_count += 1
                body = self.rfile.read(int(self.headers["content-length"]))
                owner.request_bodies.append(body)
                if owner.outcome == "timeout":
                    time.sleep(0.7)
                    return
                status = 200
                headers = {"x-request-id": "provider-request-001"}
                model = "qwen"
                if owner.outcome == "invalid_provider_json":
                    response = b"not-json"
                elif owner.outcome == "http_429":
                    status = 429
                    headers["retry-after"] = "2.5"
                    response = b'{"error":"busy"}'
                elif owner.outcome == "http_500":
                    status = 500
                    response = b'{"error":"failed"}'
                elif owner.outcome == "oom":
                    status = 500
                    response = b'{"error":"CUDA out of memory"}'
                elif owner.outcome == "oversize":
                    response = b"x" * 5000
                else:
                    if owner.outcome == "missing_request_id":
                        headers = {}
                    if owner.outcome == "model_drift":
                        model = "other-model"
                    response = canonical_json_bytes(
                        {
                            "id": "completion-001",
                            "model": model,
                            "choices": [
                                {
                                    "message": {
                                        "role": "assistant",
                                        "content": canonical_json_bytes(owner.labels).decode(),
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {"prompt_tokens": 11, "completion_tokens": 8},
                        }
                    )
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("content-length", str(len(response)))
                self.end_headers()
                try:
                    self.wfile.write(response)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _FakeJudgeServer:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions"


def test_adapter_success_is_one_canonical_request_with_exact_raw_evidence(
    valid_request: JudgeRequestEvidence, valid_labels: dict[str, str]
) -> None:
    with _FakeJudgeServer("success", valid_labels) as fake:
        response = JudgeVllmAdapter(fake.endpoint, model_id="qwen", limits=LIMITS).generate(
            valid_request
        )
    assert response.success is True
    assert response.failure_code is None
    assert fake.request_count == 1
    assert fake.request_bodies == [canonical_json_bytes(valid_request.provider_payload())]
    assert response.raw_bytes.startswith(b'{"id":"completion-001"')
    assert response.output_bytes == canonical_json_bytes(valid_labels)
    assert JudgeResponseEvidence.from_payload(response.to_payload()) == response


@pytest.mark.parametrize(
    ("mutation", "expected_match"),
    (
        ("missing_request_id", "provider_request_id"),
        ("model_drift", "model"),
        ("unknown_failure", "failure code"),
    ),
)
def test_response_contract_rejects_rehashed_identity_or_failure_enum_tamper(
    mutation: str,
    expected_match: str,
    valid_request: JudgeRequestEvidence,
    valid_labels: dict[str, str],
) -> None:
    with _FakeJudgeServer("success", valid_labels) as fake:
        response = JudgeVllmAdapter(fake.endpoint, model_id="qwen", limits=LIMITS).generate(
            valid_request
        )
    payload = response.to_payload()
    if mutation == "missing_request_id":
        payload["provider_request_id"] = None
    elif mutation == "model_drift":
        payload["model_id"] = "other-model"
    else:
        payload["success"] = False
        payload["failure_code"] = "invented_failure"
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match=expected_match):
        JudgeResponseEvidence.from_payload(payload)


@pytest.mark.parametrize("mutation", ["missing_request_id", "model_drift"])
def test_response_create_rejects_success_identity_drift(
    mutation: str,
    valid_request: JudgeRequestEvidence,
) -> None:
    with pytest.raises(ValueError, match="provider_request_id|model"):
        JudgeResponseEvidence.create(
            request=valid_request,
            provider_request_id=(None if mutation == "missing_request_id" else "provider-1"),
            http_status=200,
            response_headers={},
            raw_bytes=b"{}",
            raw_bytes_complete=True,
            raw_bytes_total_lower_bound=2,
            output_bytes=b"{}",
            model_id=("other-model" if mutation == "model_drift" else "qwen"),
            termination="stop",
            input_tokens=1,
            output_tokens=1,
            failure_code=None,
            retry_after_seconds=None,
            started_at="2026-09-19T00:00:00Z",
            ended_at="2026-09-19T00:00:01Z",
            duration_seconds=1.0,
        )


@pytest.mark.parametrize(
    ("server_outcome", "expected_code"),
    (
        ("invalid_provider_json", "provider_invalid_json"),
        ("timeout", "timeout"),
        ("http_429", "http_429"),
        ("http_500", "http_5xx"),
        ("oom", "provider_oom"),
        ("oversize", "response_size_exceeded"),
        ("missing_request_id", "provider_request_identity_missing"),
        ("model_drift", "provider_model_identity_drift"),
    ),
)
def test_adapter_maps_one_typed_failure_without_internal_retry(
    valid_request: JudgeRequestEvidence,
    valid_labels: dict[str, str],
    server_outcome: str,
    expected_code: str,
) -> None:
    with _FakeJudgeServer(server_outcome, valid_labels) as fake:
        adapter = JudgeVllmAdapter(fake.endpoint, model_id="qwen", limits=LIMITS)
        response = adapter.generate(valid_request)
    assert response.success is False
    assert response.failure_code == expected_code
    assert fake.request_count == 1
    if server_outcome == "http_429":
        assert response.retry_after_seconds == 2.5
    if server_outcome == "oversize":
        assert response.raw_bytes_complete is False
        assert response.raw_bytes_count == valid_request.response_byte_ceiling + 1
        assert response.raw_bytes_total_lower_bound == response.raw_bytes_count
        assert response.raw_bytes == b"x" * (valid_request.response_byte_ceiling + 1)
        assert len(response.raw_bytes) < 5000
        assert JudgeResponseEvidence.from_payload(response.to_payload()) == response


def test_response_bytes_are_not_logged(
    caplog: pytest.LogCaptureFixture,
    valid_request: JudgeRequestEvidence,
    valid_labels: dict[str, str],
) -> None:
    secret = "RAW-BYTES-MUST-NOT-BE-LOGGED"
    labels = dict(valid_labels)
    labels["information_fidelity"] = secret
    with _FakeJudgeServer("success", labels) as fake:
        JudgeVllmAdapter(fake.endpoint, model_id="qwen", limits=LIMITS).generate(valid_request)
    assert secret not in caplog.text
