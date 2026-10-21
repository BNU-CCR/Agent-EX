"""Synthetic Stage-B requests/evidence only; never contact a model service."""

from copy import deepcopy
import json

import pytest

from test_identity_network_benchmark_transport import DATA
from test_identity_network_benchmark_run import RUNTIME
from test_identity_network_benchmark_run import FakeConnection, context
from test_identity_network_manipulation_lock import mock_syscalls  # noqa: F401
from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.benchmark_run import BENCHMARK_HASH, build_bound_packet
from agent_ex.identity_network.benchmark_run import run_benchmark, verify_benchmark
from agent_ex.identity_network.benchmark_trials import build_benchmark_trial_inventory


def benchmark():
    return json.loads(DATA.read_text(encoding="utf-8"))


def synthetic_a_report():
    """Not authenticated execution; pure gate fixture. Actual dispatch must cold-verify A."""
    return {
        "phase": "COMPLETE",
        "ordinal": 240,
        "valid_count": 240,
        "trial_count": 240,
        "transition_count": 480,
        "saved_response_pending": False,
        "mode": "stage-a",
        "transport_evidence_verified": True,
        "runtime_hash": canonical_payload_hash(RUNTIME),
        "packet_hash": build_bound_packet(benchmark(), RUNTIME, mode="stage-a").output_hash,
        "tail_hash": "a" * 64,
        "outcomes_hash": "b" * 64,
        "execution_approval_hash": "c" * 64,
        "analysis": {
            "valid_count": 240,
            "observed_count": 240,
            "execution_status": "NORMALIZED_COMPLETE_NOT_TRANSPORT_VERIFIED",
            "signal_status": "NO_SIGNAL",
            "primary_mean": 0.6,
            "ci95": [0.5, 0.7],
            "positive_cases": 15,
        },
    }


def test_stable_group_inventory_keeps_seeds_but_separates_identities():
    a = build_benchmark_trial_inventory(benchmark(), expected_hash=BENCHMARK_HASH)
    b = build_benchmark_trial_inventory(
        benchmark(), expected_hash=BENCHMARK_HASH, stage="stable_group"
    )
    assert a.output_hash == "6aba583ad74921a4a3d0e9822b985d6385176fd04e31e1db7eea901473336e6f"
    assert len(b.payload["trials"]) == 240
    assert {t["trial_id"] for t in a.payload["trials"]}.isdisjoint(
        t["trial_id"] for t in b.payload["trials"]
    )
    assert [t["sampling_seed"] for t in a.payload["trials"]] == [
        t["sampling_seed"] for t in b.payload["trials"]
    ]


def test_stage_b_wire_only_adds_fixed_frame_and_source_prefix():
    a = build_bound_packet(benchmark(), RUNTIME, mode="stage-a")
    b = build_bound_packet(
        benchmark(), RUNTIME, mode="stage-b", stage_a_report=synthetic_a_report()
    )
    pre = build_bound_packet(
        benchmark(), RUNTIME, mode="preflight-b", stage_a_report=synthetic_a_report()
    )
    assert len(b.payload["entries"]) == 240 and len(pre.payload["entries"]) == 2
    assert {e["trial_id"] for e in b.payload["entries"]}.isdisjoint(
        e["trial_id"] for e in pre.payload["entries"]
    )
    for ae, be in zip(a.payload["entries"], b.payload["entries"], strict=True):
        aw, bw = json.loads(ae["wire_body"]), json.loads(be["wire_body"])
        assert len({r["request_id"] for r in be["attempt_requests"]}) == 3
        assert ae["attempt_requests"][0]["event_id"] != be["attempt_requests"][0]["event_id"]
        av, bv = json.loads(aw["messages"][1]["content"]), json.loads(bw["messages"][1]["content"])
        color = "蓝" if bv["self_group"] == "Blue" else "绿"
        assert bv.pop("self_group_frame") == (
            f"你属于{color}组。{color}组是本次讨论中的一个固定讨论小组，"
            "你的组别在整个讨论过程中保持不变。"
        )
        source = bv["social_messages"][0]
        group = "蓝" if source["source_group"] == "Blue" else "绿"
        assert source["member_id"] == f"{group}组成员 {av['social_messages'][0]['member_id']}"
        source["member_id"] = av["social_messages"][0]["member_id"]
        assert av == bv
        aw["messages"], bw["messages"] = [], []
        assert aw == bw
    assert b.payload["stage"] == "stable_group"
    assert b.payload["dispatch_authorized"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("phase", "INCOMPLETE"),
        ("valid_count", 239),
        ("saved_response_pending", True),
        ("transport_evidence_verified", False),
        ("packet_hash", "0" * 64),
        ("runtime_hash", "0" * 64),
    ],
)
def test_bad_a_proof_cannot_construct_b(field, value):
    report = synthetic_a_report()
    report[field] = value
    with pytest.raises(ValueError):
        build_bound_packet(benchmark(), RUNTIME, mode="stage-b", stage_a_report=report)


def test_passing_a_or_false_no_signal_label_cannot_activate_b():
    for status in ("PASS", "NO_SIGNAL"):
        report = deepcopy(synthetic_a_report())
        report["analysis"].update(positive_cases=18, signal_status=status)
        with pytest.raises(ValueError):
            build_bound_packet(benchmark(), RUNTIME, mode="stage-b", stage_a_report=report)


@pytest.fixture
def complete_a(tmp_path, mock_syscalls, monkeypatch):  # noqa: F811
    import agent_ex.identity_network.benchmark_run as module

    monkeypatch.setattr(module, "_verify_source_checkout", lambda commit: None)
    tech, aroot = tmp_path / "a-tech", tmp_path / "a-run"
    tech.mkdir()
    aroot.mkdir()
    for mode, root in (("preflight", tech), ("stage-a", aroot)):
        bench, pack, receipt = context(mode)
        fake = FakeConnection(root)
        result = run_benchmark(
            root,
            benchmark=bench,
            packet=pack,
            runtime=RUNTIME,
            receipt=receipt,
            resume=False,
            preflight_root=tech if mode == "stage-a" else None,
            connection_factory=lambda *args, **kwargs: fake,
        )
        assert result["phase"] == "COMPLETE"
    report = verify_benchmark(aroot, benchmark=bench, packet=pack, runtime=RUNTIME)
    assert report["analysis"]["signal_status"] == "NO_SIGNAL"
    return aroot, tech, report


def b_context(report, mode):
    bench = benchmark()
    pack = build_bound_packet(bench, RUNTIME, mode=mode, stage_a_report=report)
    _, _, receipt = context()
    receipt.update(packet_hash=pack.output_hash, mode=mode)
    return bench, pack, receipt


def test_b_requires_actual_a_store_before_any_http(tmp_path):
    bench, pack, receipt = b_context(synthetic_a_report(), "preflight-b")
    with pytest.raises(ValueError, match="Stage-A"):
        run_benchmark(
            tmp_path,
            benchmark=bench,
            packet=pack,
            runtime=RUNTIME,
            receipt=receipt,
            resume=False,
            stage_a_root=None,
            connection_factory=lambda *args, **kwargs: pytest.fail("network called"),
        )
    assert not (tmp_path / "benchmark.sqlite3").exists()


def test_b_preflight_full_run_and_cold_replay_are_independent(tmp_path, complete_a):
    aroot, atech, a_report = complete_a
    btech, broot = tmp_path / "b-tech", tmp_path / "b-run"
    btech.mkdir()
    broot.mkdir()
    for mode, root in (("preflight-b", btech), ("stage-b", broot)):
        bench, pack, receipt = b_context(a_report, mode)
        fake = FakeConnection(root)
        result = run_benchmark(
            root,
            benchmark=bench,
            packet=pack,
            runtime=RUNTIME,
            receipt=receipt,
            resume=False,
            preflight_root=btech if mode == "stage-b" else None,
            stage_a_root=aroot,
            connection_factory=lambda *args, **kwargs: fake,
        )
        assert result["phase"] == "COMPLETE"
        assert fake.calls == (2 if mode == "preflight-b" else 240)
        verified = verify_benchmark(
            root, benchmark=bench, packet=pack, runtime=RUNTIME, stage_a_root=aroot
        )
        assert verified["transport_evidence_verified"] is True
        assert verified["stage"] == "stable_group"
    assert verified["analysis"]["valid_count"] == 240
    assert verified["analysis"]["signal_status"] == "NO_SIGNAL"
    assert verified["stage_c_dispatch_authorized"] is False
    with pytest.raises(ValueError):
        run_benchmark(
            broot,
            benchmark=bench,
            packet=pack,
            runtime=RUNTIME,
            receipt=receipt,
            resume=True,
            preflight_root=atech,
            stage_a_root=aroot,
            connection_factory=lambda *args, **kwargs: pytest.fail("borrowed A preflight"),
        )


def test_rehashed_report_must_match_actual_cold_a_store(tmp_path, complete_a):
    aroot, _, a_report = complete_a
    forged = deepcopy(a_report)
    forged["analysis"]["primary_mean"] = 0.123
    bench, pack, receipt = b_context(forged, "preflight-b")
    root = tmp_path / "forged-b"
    root.mkdir()
    with pytest.raises(ValueError, match="Stage-A"):
        run_benchmark(
            root,
            benchmark=bench,
            packet=pack,
            runtime=RUNTIME,
            receipt=receipt,
            resume=False,
            stage_a_root=aroot,
            connection_factory=lambda *args, **kwargs: pytest.fail("forged evidence sent"),
        )
    assert not (root / "benchmark.sqlite3").exists()


def test_cli_b_materialize_inspect_requires_actual_a(tmp_path, complete_a, capsys):
    from agent_ex.identity_network.benchmark_cli import main

    aroot, _, _ = complete_a
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps(RUNTIME), encoding="utf-8")
    out = tmp_path / "b-packet.json"
    common = ["--benchmark", str(DATA), "--runtime", str(runtime)]
    args = ["materialize", *common, "--mode", "preflight-b", "--out", str(out)]
    assert main(args) == 2
    assert not out.exists()
    assert main([*args, "--stage-a-root", str(aroot)]) == 0
    assert main(["inspect", *common, "--packet", str(out)]) == 2
    assert main(["inspect", *common, "--packet", str(out), "--stage-a-root", str(aroot)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["payload"]["mode"] == "preflight-b"
    assert result["payload"]["dispatch_authorized"] is False
    assert "self_group_frame" in capsys.readouterr().out


@pytest.mark.parametrize("failure", ("ambiguous", "invalid"))
def test_b_reopen_never_resends_ambiguous_or_exhausted_request(tmp_path, complete_a, failure):
    aroot, _, report = complete_a
    root = tmp_path / "b-failure"
    root.mkdir()
    bench, pack, receipt = b_context(report, "preflight-b")
    kwargs = dict(
        benchmark=bench, packet=pack, runtime=RUNTIME, receipt=receipt, stage_a_root=aroot
    )
    if failure == "ambiguous":

        def crash(*args, **kw):
            raise RuntimeError("synthetic disconnect after durable intent")

        with pytest.raises(RuntimeError):
            run_benchmark(root, **kwargs, resume=False, connection_factory=crash)
    else:
        fake = FakeConnection(
            root, content='{"stance":"比较支持","confidence":true,"public_reason":"合成"}'
        )
        state = run_benchmark(
            root, **kwargs, resume=False, connection_factory=lambda *args, **kw: fake
        )
        assert fake.calls == 3
        assert state["phase"] == "INCOMPLETE"
    result = run_benchmark(
        root,
        **kwargs,
        resume=True,
        connection_factory=lambda *args, **kw: pytest.fail("unexpected repeat send"),
    )
    assert result["valid_count"] == 0
    assert result["phase"] == ("INTENT" if failure == "ambiguous" else "INCOMPLETE")
    verified = verify_benchmark(
        root, benchmark=bench, packet=pack, runtime=RUNTIME, stage_a_root=aroot
    )
    assert verified["technical_preflight_passed"] is False


def test_real_stage_a_packet_golden_hashes_unchanged():
    runtime = {
        **RUNTIME,
        "model_revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "model_files_hash": "f17ee1a31beb2f31426551664e884485df6569377c81ab59be49127ae1dd7066",
        "tokenizer_hash": "90a2903e36317f2a873560235218be86367fa0ed4209f53096b6d59325fed333",
        "chat_template_hash": "a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8",
        "vllm_version": "0.23.0",
        "served_model_name": "Qwen3-8B",
    }
    assert build_bound_packet(benchmark(), runtime, mode="stage-a").output_hash == (
        "1ee01aeee8fed0162d1f47b26652f8d80c363df960630fff81d642c8d1d9d328"
    )
    assert build_bound_packet(benchmark(), runtime, mode="preflight").output_hash == (
        "426775642e1861d6a76184eb76c3396111898918497e539f7b0163b15d14ac7b"
    )
