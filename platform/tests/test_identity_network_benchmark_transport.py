"""Offline candidate encoding only; parameters below are synthetic fixtures."""

import json
from pathlib import Path

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.benchmark_transport import build_benchmark_transport_candidate


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "platform/configs/identity-network/manipulation-retirement-20261008/benchmark.json"


def build(**changes):
    benchmark = json.loads(DATA.read_text(encoding="utf-8"))
    args = dict(
        benchmark=benchmark,
        expected_hash=canonical_payload_hash(benchmark),
        generation_settings={"temperature": 0.7, "top_p": 0.9, "max_tokens": 128},
        served_model_name="synthetic-model",
        adapter_binding_hash="a" * 64,
    )
    args.update(changes)
    return build_benchmark_transport_candidate(**args)


def test_candidate_240_trials_three_attempts_exact_wire_and_group_only_change():
    pack = build()
    assert len(pack.payload["entries"]) == 240
    assert pack.payload["dispatch_authorized"] is False
    assert pack.payload["cloud_launch_eligible"] is False
    first = pack.payload["entries"][:4]
    content = []
    for entry in first:
        requests = entry["attempt_requests"]
        assert [r["attempt_index"] for r in requests] == [1, 2, 3]
        assert len({r["request_id"] for r in requests}) == 3
        assert len({r["event_id"] for r in requests}) == 1
        body = json.loads(entry["wire_body"])
        visible = json.loads(body["messages"][1]["content"])
        assert visible["self_history"] == []
        assert "pre_confidence" not in visible
        assert "source_reason" not in visible["social_messages"][0]
        assert "source_message" in visible["social_messages"][0]
        assert visible["social_messages"][0]["member_id"].startswith("Member ")
        assert "MC-D" not in visible["social_messages"][0]["member_id"]
        visible.pop("self_group")
        visible["social_messages"][0].pop("source_group")
        content.append(visible)
    assert all(v == content[0] for v in content)


def test_explicit_parameters_and_strict_validation():
    for settings in (
        {},
        {"temperature": True, "top_p": 0.9, "max_tokens": 128},
        {"temperature": 0.7, "top_p": 0.9, "max_tokens": 128, "extra": 1},
    ):
        with pytest.raises((ValueError, TypeError)):
            build(generation_settings=settings)
    assert build() == build()


def test_model_change_cannot_alias_physical_request_identity():
    first = build(served_model_name="synthetic-model-A")
    second = build(served_model_name="synthetic-model-B")
    assert (
        first.payload["entries"][0]["attempt_requests"][0]["request_id"]
        != second.payload["entries"][0]["attempt_requests"][0]["request_id"]
    )
