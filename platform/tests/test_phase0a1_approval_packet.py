"""Checks for the proposal-only real Phase 0A-1 six-group packet."""

import json
import importlib.util
from pathlib import Path

from agent_ex.calibration.cloud_run import load_cloud_run_artifacts


PLATFORM_ROOT = Path(__file__).parents[1]
PACKET_DIR = PLATFORM_ROOT / "configs" / "paper1" / "phase0a1-approval-proposal-v2"


def fresh_packet() -> dict[str, object]:
    script_path = PLATFORM_ROOT / "scripts" / "materialize_phase0a1_approval_packet.py"
    spec = importlib.util.spec_from_file_location("phase0a1_packet_materializer", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the Phase 0A-1 packet materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_packet()


def test_proposal_packet_loads_with_exact_real_inventory_and_visible_anchors() -> None:
    packet = json.loads(
        (PACKET_DIR / "approved-cloud-artifacts.proposal.json").read_text(encoding="utf-8")
    )
    artifacts = load_cloud_run_artifacts(packet)

    assert len(artifacts.cases) == 816
    assert set(artifacts.approved_group_hashes) == {
        "archive_declaration",
        "candidate_manifest",
        "credential_boundary",
        "probe_specification",
        "runtime_policy",
        "semantic_review_policy",
    }
    user_texts = tuple(case.rendered_messages[1]["content"] for case in artifacts.cases)
    assert any("1 非常不支持" in text and "7 非常支持" in text for text in user_texts)
    assert any("0=完全不同意该陈述" in text and "10=完全同意该陈述" in text for text in user_texts)


def test_checked_in_v2_packet_equals_fresh_materializer_and_excludes_v1() -> None:
    packet = json.loads(
        (PACKET_DIR / "approved-cloud-artifacts.proposal.json").read_text(encoding="utf-8")
    )
    summary = json.loads((PACKET_DIR / "approval-summary.json").read_text(encoding="utf-8"))

    assert packet == fresh_packet()
    artifacts = load_cloud_run_artifacts(packet)
    assert len(artifacts.cases) == 816
    assert artifacts.archive_uri == "/root/autodl-tmp/agent-ex-phase0a1-probe-816-v2"
    assert artifacts.archive_uri != "/root/autodl-tmp/agent-ex-phase0a1-probe-816-v1"
    specification_group = packet["artifact_groups"]["probe_specification"]
    assert specification_group["response_contract_version"] == "2.0.0"
    assert len(specification_group["response_contract_hash"]) == 64
    assert len(specification_group["case_inventory_hash"]) == 64
    v1_packet = json.loads(
        (
            PLATFORM_ROOT
            / "configs"
            / "paper1"
            / "phase0a1-approval-proposal-v1"
            / "approved-cloud-artifacts.proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        packet["approved_group_hashes"]["probe_specification"]
        != v1_packet["approved_group_hashes"]["probe_specification"]
    )
    assert summary["packet_hash"] == packet["record_hash"]
    assert summary["group_hashes"] == packet["approved_group_hashes"]
    for case in artifacts.cases:
        text = case.rendered_messages[-1]["content"]
        assert "confidence is independent of the stance scale" in text
        assert "must be a JSON integer from 1 to 5" in text


def test_proposal_supporting_hashes_bind_the_judge_contract() -> None:
    packet = json.loads(
        (PACKET_DIR / "approved-cloud-artifacts.proposal.json").read_text(encoding="utf-8")
    )
    supporting = json.loads((PACKET_DIR / "supporting-material.json").read_text(encoding="utf-8"))
    policy = packet["artifact_groups"]["semantic_review_policy"]
    judge = next(item for item in policy["coder_contracts"] if item["role"] == "judge")

    assert judge["judge_prompt_hash"] == supporting["judge_prompt_hash"]
    assert judge["ordering_policy_hash"] == supporting["ordering_policy_hash"]
    assert policy["classifier_hash"] == supporting["classifier_contract_hash"]
