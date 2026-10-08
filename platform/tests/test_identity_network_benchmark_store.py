"""Actual SQLite and typed synthetic HTTP evidence; Windows lease syscall simulation."""

import json
import sqlite3

import pytest

from test_identity_network_benchmark_transport import build
from test_identity_network_manipulation_lock import mock_syscalls  # noqa: F401
from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.benchmark_adapter import BenchmarkVllmAdapter, reconstruct_request
from agent_ex.identity_network.benchmark_store import BenchmarkStore
from agent_ex.identity_network.benchmark_response import classify_benchmark_response
from agent_ex.phase0b.vllm_event_adapter import (
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
)


def response(pack, state, *, content=None, status=200):
    entry = pack.payload["entries"][state["ordinal"]]
    request = reconstruct_request(entry["attempt_requests"][state["attempt_index"] - 1])
    adapter = BenchmarkVllmAdapter(
        "http://127.0.0.1:8000/v1/chat/completions",
        served_model_name=pack.payload["served_model_name"],
    )
    raw = json.dumps(
        {
            "model": pack.payload["served_model_name"],
            "choices": [
                {
                    "message": {
                        "content": content
                        or '{"stance":"比较支持","confidence":3,"public_reason":"我认为这样的安排可以讨论。"}'
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    ).encode()
    outcome, error, retry, usage, finish = adapter._classify(
        status=status,
        headers={"x-request-id": "synthetic"},
        raw_body=raw,
        truncated=False,
        provider_request_id="synthetic",
    )
    evidence = Phase0BVllmTransportEvidence.create(
        request=request,
        http_status=status,
        response_headers={"x-request-id": "synthetic"},
        provider_request_id="synthetic",
        request_body=entry["wire_body"].encode(),
        raw_body=raw,
        body_truncated=False,
        started_at="2026-10-08T01:00:00Z",
        ended_at="2026-10-08T01:00:01Z",
        latency_seconds=1.0,
        outcome=outcome,
        error_code=error,
    )
    return Phase0BVllmEventResponse.create(
        request=request,
        outcome=outcome,
        error_code=error,
        retry_after_seconds=retry,
        provider_request_id="synthetic",
        usage=usage,
        finish_reason=finish,
        raw_body=raw,
        transport_evidence=evidence,
    )


@pytest.fixture
def archive(tmp_path, mock_syscalls):  # noqa: F811
    lock, _ = mock_syscalls
    pack = build(mode="preflight")
    with lock.acquire(tmp_path) as lease:
        yield tmp_path, pack, lease


def test_intent_crash_blocks_resend_and_saved_response_resume_without_dispatch(archive):
    root, pack, lease = archive
    with BenchmarkStore.create(root, pack=pack, lease=lease) as store:
        request = store.current_request()
        store.record_before_dispatch(request, pack.payload["entries"][0]["wire_body"].encode())
        with pytest.raises(ValueError):
            store.record_before_dispatch(request, pack.payload["entries"][0]["wire_body"].encode())
        saved = response(pack, store.summary())
        store.save_response(saved)
    with BenchmarkStore.open(root, pack=pack, lease=lease) as store:
        assert store.summary()["saved_response_pending"] is True
        store.resolve_saved_response()
        assert store.summary()["valid_count"] == 1
    assert BenchmarkStore.verify(root, pack=pack)["valid_count"] == 1


def test_three_invalid_responses_incomplete_and_schema_tamper(archive):
    root, pack, lease = archive
    with BenchmarkStore.create(root, pack=pack, lease=lease) as store:
        for _ in range(3):
            store.record_before_dispatch(
                store.current_request(), pack.payload["entries"][0]["wire_body"].encode()
            )
            store.save_response(
                response(
                    pack,
                    store.summary(),
                    content='{"stance":"比较支持","confidence":true,"public_reason":"无效"}',
                )
            )
            store.resolve_saved_response()
        assert store.summary()["phase"] == "INCOMPLETE"
        assert store.summary()["valid_count"] == 0
    with sqlite3.connect(root / "benchmark.sqlite3") as conn:
        conn.execute("CREATE TABLE unwanted (x TEXT)")
    with pytest.raises(ValueError):
        BenchmarkStore.verify(root, pack=pack)


@pytest.mark.parametrize(
    "content",
    [
        'prefix {"stance":"比较支持","confidence":3,"public_reason":"理由"}',
        '{"stance":"比较支持","stance":"支持","confidence":3,"public_reason":"理由"}',
        '{"confidence":3,"stance":"比较支持","public_reason":"理由"}',
        '{"stance":"比较支持","confidence":3,"public_reason":"理由","extra":1}',
        '{"stance":"not-label","confidence":3,"public_reason":"理由"}',
        '{"stance":"比较支持","confidence":0,"public_reason":"理由"}',
    ],
)
def test_strict_json_failure(content):
    pack = build(mode="preflight")
    result = classify_benchmark_response(
        pack, 0, 1, response(pack, {"ordinal": 0, "attempt_index": 1}, content=content)
    )
    assert result["classification"] == "PARSE_INVALID"


def test_5xx_is_ambiguous_not_retry(archive):
    root, pack, lease = archive
    with BenchmarkStore.create(root, pack=pack, lease=lease) as store:
        store.record_before_dispatch(
            store.current_request(), pack.payload["entries"][0]["wire_body"].encode()
        )
        store.save_response(response(pack, store.summary(), status=503))
        store.resolve_saved_response()
        assert store.summary()["phase"] == "BLOCKED_AMBIGUOUS"


def test_429_retry_then_valid_preserves_request_body(archive):
    root, pack, lease = archive
    with BenchmarkStore.create(root, pack=pack, lease=lease) as store:
        wire = pack.payload["entries"][0]["wire_body"].encode()
        store.record_before_dispatch(store.current_request(), wire)
        store.save_response(response(pack, store.summary(), status=429))
        store.resolve_saved_response()
        assert store.summary()["attempt_index"] == 2
        assert store.summary()["phase"] == "RETRY_READY"
        store.record_before_dispatch(store.current_request(), wire)
        store.save_response(response(pack, store.summary()))
        store.resolve_saved_response()
        assert store.summary()["valid_count"] == 1
    assert BenchmarkStore.verify(root, pack=pack)["valid_count"] == 1


def test_external_schema_change_on_open_handle_is_not_blessed(archive):
    root, pack, lease = archive
    with BenchmarkStore.create(root, pack=pack, lease=lease) as store:
        with sqlite3.connect(root / "benchmark.sqlite3") as conn:
            conn.execute("CREATE TABLE changed (x TEXT)")
        with pytest.raises(ValueError):
            store.summary()


def test_response_hash_tamper_and_wrong_wire_fail(archive):
    root, pack, lease = archive
    with BenchmarkStore.create(root, pack=pack, lease=lease) as store:
        with pytest.raises(ValueError):
            store.record_before_dispatch(store.current_request(), b"wrong")
        store.record_before_dispatch(
            store.current_request(), pack.payload["entries"][0]["wire_body"].encode()
        )
        store.save_response(response(pack, store.summary()))
        store.resolve_saved_response()
    with sqlite3.connect(root / "benchmark.sqlite3") as conn:
        conn.execute("UPDATE responses SET response_hash=?", (canonical_payload_hash({}),))
    with pytest.raises(ValueError):
        BenchmarkStore.verify(root, pack=pack)


def test_response_is_durable_before_parse_can_crash(archive, monkeypatch):
    root, pack, lease = archive
    import agent_ex.identity_network.benchmark_store as module

    with BenchmarkStore.create(root, pack=pack, lease=lease) as store:
        store.record_before_dispatch(
            store.current_request(), pack.payload["entries"][0]["wire_body"].encode()
        )

        def crash(*args):
            raise RuntimeError("synthetic parser crash")

        with monkeypatch.context() as context:
            context.setattr(module, "classify_benchmark_response", crash)
            with pytest.raises(RuntimeError):
                store.save_response(response(pack, store.summary()))
        with sqlite3.connect(root / "benchmark.sqlite3") as conn:
            assert conn.execute("SELECT count(*) FROM responses").fetchone()[0] == 1
    with BenchmarkStore.open(root, pack=pack, lease=lease) as store:
        store.resolve_saved_response()
        assert store.summary()["valid_count"] == 1
