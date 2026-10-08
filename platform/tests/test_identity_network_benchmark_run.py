"""Offline fake HTTP through the real adapter/store; no live service calls."""

import json
import sqlite3

import pytest

from test_identity_network_benchmark_transport import DATA
from test_identity_network_manipulation_lock import mock_syscalls  # noqa: F401
from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.benchmark_run import (
    build_bound_packet,
    run_benchmark,
    verify_benchmark,
    validate_runtime,
)


RUNTIME = {
    "model_id": "Qwen/Qwen3-8B",
    "model_revision": "a" * 40,
    "model_files_hash": "b" * 64,
    "tokenizer_hash": "c" * 64,
    "chat_template_hash": "d" * 64,
    "vllm_version": "synthetic-test",
    "dtype": "bfloat16",
    "enable_thinking": False,
    "served_model_name": "synthetic-model",
    "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
}


def context(mode="preflight"):
    benchmark = json.loads(DATA.read_text(encoding="utf-8"))
    packet = build_bound_packet(benchmark, RUNTIME, mode=mode)
    receipt = {
        "schema_version": "sis.stage-a.run-approval.v1",
        "packet_hash": packet.output_hash,
        "runtime_hash": canonical_payload_hash(RUNTIME),
        "source_commit": "e" * 40,
        "approved_by": "synthetic test operator",
        "decision": "approve",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "mode": mode,
    }
    return benchmark, packet, receipt


class FakeConnection:
    def __init__(self, root, content=None):
        self.root, self.content = root, content
        self.status = 200
        self.calls = 0

    def request(self, method, url, body, headers):
        with sqlite3.connect(self.root / "benchmark.sqlite3") as conn:
            last = json.loads(
                conn.execute(
                    "SELECT record_json FROM journal ORDER BY seq DESC LIMIT 1"
                ).fetchone()[0]
            )
            assert last["kind"] == "INTENT"
        self.calls += 1
        wire = json.loads(body)
        assert wire["top_k"] == 20 and wire["top_p"] == 0.8
        assert wire["chat_template_kwargs"]["enable_thinking"] is False
        self.raw = json.dumps(
            {
                "model": "synthetic-model",
                "choices": [
                    {
                        "message": {
                            "content": self.content
                            or '{"stance":"比较支持","confidence":3,"public_reason":"我觉得这个观点值得考虑。"}'
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode()

    def getresponse(self):
        return self

    def getheaders(self):
        return [("x-request-id", "synthetic")]

    def read(self, n):
        chunk, self.raw = self.raw[:n], self.raw[n:]
        return chunk

    def close(self):
        pass


def test_runtime_incomplete_and_receipt_mismatch_do_not_call_http(tmp_path):
    benchmark, packet, receipt = context()
    with pytest.raises(ValueError):
        validate_runtime({**RUNTIME, "model_revision": "UNRESOLVED[SIS_MODEL_RUNTIME]"})
    with pytest.raises(ValueError):
        run_benchmark(
            tmp_path,
            benchmark=benchmark,
            packet=packet,
            runtime=RUNTIME,
            receipt={**receipt, "packet_hash": "f" * 64},
            resume=False,
            connection_factory=lambda *a, **kw: pytest.fail("network called"),
        )
    assert not (tmp_path / "benchmark.sqlite3").exists()


def test_preflight_fake_http_complete_and_readonly_report(tmp_path, mock_syscalls, monkeypatch):  # noqa: F811
    benchmark, packet, receipt = context()
    import agent_ex.identity_network.benchmark_run as module

    monkeypatch.setattr(module, "_verify_source_checkout", lambda commit: None)
    fake = FakeConnection(tmp_path)
    result = run_benchmark(
        tmp_path,
        benchmark=benchmark,
        packet=packet,
        runtime=RUNTIME,
        receipt=receipt,
        resume=False,
        connection_factory=lambda *a, **kw: fake,
    )
    assert fake.calls == 2
    assert result["phase"] == "COMPLETE"
    report = verify_benchmark(tmp_path, benchmark=benchmark, packet=packet, runtime=RUNTIME)
    assert report["technical_preflight_passed"] is True
    assert "signal_status" not in report
    assert report["stage_b_dispatch_authorized"] is False
    assert report["execution_approval_hash"] == canonical_payload_hash(receipt)
    assert report["post_confidence_histogram"] == {"1": 0, "2": 0, "3": 2, "4": 0, "5": 0}


def test_crash_ambiguous_intent_resume_never_resends(tmp_path, mock_syscalls, monkeypatch):  # noqa: F811
    benchmark, packet, receipt = context()
    import agent_ex.identity_network.benchmark_run as module

    monkeypatch.setattr(module, "_verify_source_checkout", lambda commit: None)

    def crash(*a, **kw):
        raise RuntimeError("synthetic connection construction crash")

    with pytest.raises(RuntimeError):
        run_benchmark(
            tmp_path,
            benchmark=benchmark,
            packet=packet,
            runtime=RUNTIME,
            receipt=receipt,
            resume=False,
            connection_factory=crash,
        )
    result = run_benchmark(
        tmp_path,
        benchmark=benchmark,
        packet=packet,
        runtime=RUNTIME,
        receipt=receipt,
        resume=True,
        connection_factory=lambda *a, **kw: pytest.fail("resent"),
    )
    assert result["phase"] == "INTENT"
    assert result["valid_count"] == 0


def test_parse_invalid_retries_three_same_body_then_stops(tmp_path, mock_syscalls, monkeypatch):  # noqa: F811
    benchmark, packet, receipt = context()
    import agent_ex.identity_network.benchmark_run as module

    monkeypatch.setattr(module, "_verify_source_checkout", lambda commit: None)
    fake = FakeConnection(
        tmp_path, content='{"stance":"比较支持","confidence":true,"public_reason":"理由"}'
    )
    result = run_benchmark(
        tmp_path,
        benchmark=benchmark,
        packet=packet,
        runtime=RUNTIME,
        receipt=receipt,
        resume=False,
        connection_factory=lambda *a, **kw: fake,
    )
    assert fake.calls == 3
    assert result["phase"] == "INCOMPLETE"
    assert "signal_status" not in verify_benchmark(
        tmp_path, benchmark=benchmark, packet=packet, runtime=RUNTIME
    )


def test_expired_receipt_fails_before_archive_write(tmp_path):
    benchmark, packet, receipt = context()
    with pytest.raises(ValueError):
        run_benchmark(
            tmp_path,
            benchmark=benchmark,
            packet=packet,
            runtime=RUNTIME,
            receipt={**receipt, "expires_at": "2000-01-01T00:00:00+00:00"},
            resume=False,
        )


def test_complete_240_requires_preflight_and_hot_cold_counts_match(
    tmp_path,
    mock_syscalls,  # noqa: F811
    monkeypatch,  # noqa: F811
):  # noqa: F811
    import agent_ex.identity_network.benchmark_run as module

    monkeypatch.setattr(module, "_verify_source_checkout", lambda commit: None)
    cold_calls = []
    original = module.BenchmarkStore._cold_replay

    def counted(store):
        cold_calls.append(1)
        return original(store)

    monkeypatch.setattr(module.BenchmarkStore, "_cold_replay", counted)
    technical = tmp_path / "technical"
    technical.mkdir()
    formal = tmp_path / "formal"
    formal.mkdir()
    benchmark, preflight, receipt = context()
    fake = FakeConnection(technical)
    run_benchmark(
        technical,
        benchmark=benchmark,
        packet=preflight,
        runtime=RUNTIME,
        receipt=receipt,
        resume=False,
        connection_factory=lambda *a, **kw: fake,
    )
    benchmark, packet, receipt = context("stage-a")
    with pytest.raises(ValueError):
        run_benchmark(
            formal,
            benchmark=benchmark,
            packet=packet,
            runtime=RUNTIME,
            receipt=receipt,
            resume=False,
            connection_factory=lambda *a, **kw: pytest.fail("no preflight"),
        )
    fake = FakeConnection(formal)
    hot = run_benchmark(
        formal,
        benchmark=benchmark,
        packet=packet,
        runtime=RUNTIME,
        receipt=receipt,
        resume=False,
        preflight_root=technical,
        connection_factory=lambda *a, **kw: fake,
    )
    cold = verify_benchmark(formal, benchmark=benchmark, packet=packet, runtime=RUNTIME)
    assert fake.calls == 240
    assert hot["valid_count"] == cold["valid_count"] == 240
    assert hot["tail_hash"] == cold["tail_hash"]
    assert cold["analysis"]["signal_status"] == "NO_SIGNAL"
    assert cold["stage_b_dispatch_authorized"] is False
    assert len(cold_calls) <= 6  # Cold boundary audits, not O(events) full-prefix scans.


def test_renewed_approval_resumes_same_archive_preserving_original(
    tmp_path,
    mock_syscalls,  # noqa: F811
    monkeypatch,  # noqa: F811
):  # noqa: F811
    import agent_ex.identity_network.benchmark_run as module

    monkeypatch.setattr(module, "_verify_source_checkout", lambda commit: None)
    benchmark, packet, receipt = context()
    fake = FakeConnection(tmp_path)
    run_benchmark(
        tmp_path,
        benchmark=benchmark,
        packet=packet,
        runtime=RUNTIME,
        receipt=receipt,
        resume=False,
        connection_factory=lambda *a, **kw: fake,
    )
    renewed = {**receipt, "expires_at": "2099-02-01T00:00:00+00:00"}
    run_benchmark(
        tmp_path,
        benchmark=benchmark,
        packet=packet,
        runtime=RUNTIME,
        receipt=renewed,
        resume=True,
        connection_factory=lambda *a, **kw: pytest.fail("completed resent"),
    )
    with sqlite3.connect(tmp_path / "benchmark.sqlite3") as conn:
        original = json.loads(conn.execute("SELECT receipt_json FROM metadata").fetchone()[0])
        assert original == receipt
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 2
    report = verify_benchmark(tmp_path, benchmark=benchmark, packet=packet, runtime=RUNTIME)
    assert report["execution_approval_hash"] == canonical_payload_hash(renewed)
