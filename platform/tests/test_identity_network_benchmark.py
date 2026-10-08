"""Frozen researcher-authored input checks; no inference or empirical outcomes."""

import copy
import json
from pathlib import Path

import pytest

from agent_ex.domain import canonical_payload_hash


@pytest.fixture
def benchmark():
    path = (
        Path(__file__).parents[1]
        / "configs/identity-network/manipulation-retirement-20261008/benchmark.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_approved_snapshot_has_only_safe_summary(benchmark):
    from agent_ex.identity_network.benchmark import validate_frozen_benchmark

    result = validate_frozen_benchmark(benchmark, expected_hash=canonical_payload_hash(benchmark))
    assert dict(result) == {
        "case_count": 30,
        "content_hash": canonical_payload_hash(benchmark),
        "research_content_status": "frozen",
        "dispatch_authorized": False,
    }
    with pytest.raises(TypeError):
        result["case_count"] = 31


def test_changed_text_cannot_use_original_approval_hash(benchmark):
    from agent_ex.identity_network.benchmark import validate_frozen_benchmark

    digest = canonical_payload_hash(benchmark)
    benchmark["cases"][0]["source_message"] += "tampered"
    with pytest.raises(ValueError, match="hash"):
        validate_frozen_benchmark(benchmark, expected_hash=digest)


def test_snapshot_matches_recorded_freeze_hash(benchmark):
    assert canonical_payload_hash(benchmark) == (
        "9c2345580024523794a2d433500229d55e166414f18f5c0bd06baba893c8eb10"
    )


@pytest.mark.parametrize(
    "name,digest",
    [
        (
            "stage-b-framing.json",
            "65a5707ca065bc719f747801231d919f8b5a0fa9c7c50041afa4d068f342f5bf",
        ),
        (
            "analysis-policy.json",
            "06cde384ae6bcd89f77deb628110dad5a8777f7bbdfc21e9f2505c5e894093c0",
        ),
    ],
)
def test_other_research_snapshots_match_recorded_hashes(name, digest):
    directory = (
        Path(__file__).parents[1] / "configs/identity-network/manipulation-retirement-20261008"
    )
    payload = json.loads((directory / name).read_text(encoding="utf-8"))
    assert canonical_payload_hash(payload) == digest
    assert payload["dispatch_authorized"] is False


def test_only_ad028_differs_from_approved_v3(benchmark):
    root = Path(__file__).parents[2]
    text = (root / "docs/benchmarks/retirement-30-case-draft-v3.md").read_text(encoding="utf-8")
    rows = [row for row in text.splitlines() if row.startswith("| MC-D")]
    assert len(rows) == 30
    changed = []
    for row, case in zip(rows, benchmark["cases"], strict=True):
        columns = [item.strip() for item in row.split("|")]
        assert columns[1] == f"{case['case_id']} / {case['content_unit_id']}"
        if columns[3] != case["source_message"] or columns[4] != case["source_reason"]:
            changed.append(case["content_unit_id"])
    assert changed == ["AD-028"]


@pytest.mark.parametrize(
    "mutation",
    [
        "count",
        "stance",
        "bool_stance",
        "case_id",
        "unit",
        "review",
        "history",
        "confidence",
        "dispatch",
        "independence",
        "reason",
        "shared",
        "extra",
        "persona",
    ],
)
def test_rehashed_structural_drift_is_rejected(benchmark, mutation):
    from agent_ex.identity_network.benchmark import validate_frozen_benchmark

    changed = copy.deepcopy(benchmark)
    case = changed["cases"][0]
    if mutation == "count":
        changed["cases"].pop()
    elif mutation == "stance":
        case["source_stance"] = 6
    elif mutation == "bool_stance":
        case["stance_distance"] = True
    elif mutation == "case_id":
        case["case_id"] = changed["cases"][1]["case_id"]
    elif mutation == "unit":
        case["content_unit_id"] = "AD-999"
    elif mutation == "review":
        case["human_review"] = "pending"
    elif mutation == "history":
        changed["self_history"] = ["invented"]
    elif mutation == "confidence":
        changed["pre_confidence"] = 3
    elif mutation == "dispatch":
        changed["dispatch_authorized"] = True
    elif mutation == "independence":
        changed["statistically_independent_arguments"] = True
    elif mutation == "reason":
        case["source_reason"] = "not the displayed reason"
    elif mutation == "shared":
        changed["cases"][3]["shared_reason_family_ids"] = []
    elif mutation == "extra":
        case["unapproved"] = "field"
    elif mutation == "persona":
        changed["persona_context"] += "年龄60"
    with pytest.raises(ValueError):
        validate_frozen_benchmark(changed, expected_hash=canonical_payload_hash(changed))
