"""Checks for the proposal-only real Phase 0A-1 six-group packet."""

import json
from pathlib import Path

from agent_ex.calibration.cloud_run import load_cloud_run_artifacts


PACKET_DIR = Path(__file__).parents[1] / "configs" / "paper1" / "phase0a1-approval-proposal-v1"


def test_proposal_packet_loads_with_exact_real_inventory_and_visible_anchors() -> None:
    packet = json.loads(
        (PACKET_DIR / "approved-cloud-artifacts.proposal.json").read_text(encoding="utf-8")
    )
    artifacts = load_cloud_run_artifacts(packet)

    assert artifacts.record_hash == (
        "8467cc55fee0600e0f165531f1de0731dd5a09c3536ab4f70ce2f469e8937002"
    )
    assert len(artifacts.cases) == 816
    assert artifacts.approved_group_hashes == {
        "archive_declaration": ("ec7178c9ed68d9f3ff182cbe337e8a91192334fd069b68c951d7101785945342"),
        "candidate_manifest": ("479fc2e5cb1864a04bb3c155abc00d56683de5b3125b6c4b3337c824e8b118a1"),
        "credential_boundary": ("595a19eb5f33ab0357177f30a233e54b6bfbc6608789fb765793cb3bf9cd3105"),
        "probe_specification": ("89da9f9b1a9272773deab90456e45eca75b0ba40cfa90c5804b61c9a721ce1a2"),
        "runtime_policy": ("fd0b257747525dc79bd634ace413698ebfc1e95653b687c13c26dadf00e9d896"),
        "semantic_review_policy": (
            "12012960c93b9c55c3ddeff0d7075d0bb5faec5e29b7a35bed7dbb13e2b4e6f9"
        ),
    }
    user_texts = tuple(case.rendered_messages[1]["content"] for case in artifacts.cases)
    assert any("1 非常不支持" in text and "7 非常支持" in text for text in user_texts)
    assert any("0=完全不同意该陈述" in text and "10=完全同意该陈述" in text for text in user_texts)


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
