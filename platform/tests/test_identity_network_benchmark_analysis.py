"""Entirely synthetic outcomes; no empirical results or automatic Stage-B transition."""

import json
from pathlib import Path

import pytest

HASH = "9c2345580024523794a2d433500229d55e166414f18f5c0bd06baba893c8eb10"


@pytest.fixture(scope="module")
def inputs():
    from agent_ex.identity_network.benchmark_trials import build_benchmark_trial_inventory

    path = (
        Path(__file__).parents[1]
        / "configs/identity-network/manipulation-retirement-20261008/benchmark.json"
    )
    benchmark = json.loads(path.read_text(encoding="utf-8"))
    inventory = build_benchmark_trial_inventory(benchmark, expected_hash=HASH)
    return benchmark, inventory


def synthetic_outcomes(inputs, positive=30):
    benchmark, inventory = inputs
    cases = {c["case_id"]: (i, c) for i, c in enumerate(benchmark["cases"])}
    outcomes = []
    for t in inventory.payload["trials"]:
        index, case = cases[t["case_id"]]
        move = (1 if case["source_stance"] > 4 else -1) if index < positive else 0
        post = 4 + move if t["variant"] in ("BB", "GG") else 4
        outcomes.append({"trial_id": t["trial_id"], "status": "VALID", "post_stance": post})
    return outcomes


def test_synthetic_positive_and_zero_signal(inputs):
    from agent_ex.identity_network.benchmark_analysis import analyze_benchmark_outcomes

    positive = analyze_benchmark_outcomes(*inputs, synthetic_outcomes(inputs), expected_hash=HASH)
    assert positive["signal_status"] == "PASS"
    assert positive["primary_mean"] == 1
    assert positive["ci95"] == (1, 1)
    assert positive["positive_cases"] == 30
    assert positive["stage_b_dispatch_authorized"] is False
    assert positive["transport_evidence_verified"] is False
    zero = analyze_benchmark_outcomes(*inputs, synthetic_outcomes(inputs, 0), expected_hash=HASH)
    assert zero["signal_status"] == "NO_SIGNAL"
    assert zero["primary_mean"] == 0
    assert zero["ci95"] == (0, 0)


@pytest.mark.parametrize("positive,expected", [(17, "NO_SIGNAL"), (18, "PASS")])
def test_positive_case_threshold_and_deterministic_bootstrap(inputs, positive, expected):
    from agent_ex.identity_network.benchmark_analysis import analyze_benchmark_outcomes

    outcomes = synthetic_outcomes(inputs, positive)
    first = analyze_benchmark_outcomes(*inputs, outcomes, expected_hash=HASH)
    assert first["signal_status"] == expected
    assert first["positive_cases"] == positive
    assert first["primary_mean"] == pytest.approx(positive / 30)
    assert first["ci95"][0] > 0
    assert first == analyze_benchmark_outcomes(
        *inputs, list(reversed(outcomes)), expected_hash=HASH
    )
    assert len(first["by_stratum"]) == 6
    assert set(first["by_distance"]) == {1, 2, 3}
    assert set(first["by_direction"]) == {"upward", "downward"}


@pytest.mark.parametrize("kind", ["missing", "invalid"])
def test_incomplete_cannot_make_substantive_decision(inputs, kind):
    from agent_ex.identity_network.benchmark_analysis import analyze_benchmark_outcomes

    outcomes = synthetic_outcomes(inputs)
    if kind == "missing":
        outcomes.pop()
    else:
        outcomes[0] = {**outcomes[0], "status": "INVALID", "post_stance": None}
    result = analyze_benchmark_outcomes(*inputs, outcomes, expected_hash=HASH)
    assert result["execution_status"] == "INCOMPLETE"
    assert result["signal_status"] is None
    assert "ci95" not in result
    assert result["stage_b_dispatch_authorized"] is False


@pytest.mark.parametrize("kind", ["duplicate", "unknown", "boolean", "range", "extra"])
def test_outcome_contract_drift_rejected(inputs, kind):
    from agent_ex.identity_network.benchmark_analysis import analyze_benchmark_outcomes

    outcomes = synthetic_outcomes(inputs)
    if kind == "duplicate":
        outcomes[1] = dict(outcomes[0])
    elif kind == "unknown":
        outcomes[0]["trial_id"] = "unknown"
    elif kind == "boolean":
        outcomes[0]["post_stance"] = True
    elif kind == "range":
        outcomes[0]["post_stance"] = 8
    else:
        outcomes[0]["extra"] = "field"
    with pytest.raises(ValueError):
        analyze_benchmark_outcomes(*inputs, outcomes, expected_hash=HASH)


def test_both_repeats_contribute_equally(inputs):
    from agent_ex.identity_network.benchmark_analysis import analyze_benchmark_outcomes

    outcomes = synthetic_outcomes(inputs, 0)
    for index in (0, 2):
        outcomes[index]["post_stance"] = 5
    result = analyze_benchmark_outcomes(*inputs, outcomes, expected_hash=HASH)
    assert result["case_effects"]["MC-D1-U-01"] == 0.5
    assert result["primary_mean"] == pytest.approx(0.5 / 30)


def test_ci_criterion_blocks_positive_mean_and_eighteen_positive_cases(inputs):
    from agent_ex.identity_network.benchmark_analysis import analyze_benchmark_outcomes

    benchmark, inventory = inputs
    sources = {c["case_id"]: (i, c["source_stance"]) for i, c in enumerate(benchmark["cases"])}
    outcomes = synthetic_outcomes(inputs, 0)
    for trial, outcome in zip(inventory.payload["trials"], outcomes, strict=True):
        index, source = sources[trial["case_id"]]
        direction = 1 if source > 4 else -1
        if trial["variant"] in ("BB", "GG"):
            outcome["post_stance"] = 4 + direction * (1 if index % 5 < 3 else -1)
    report = analyze_benchmark_outcomes(*inputs, outcomes, expected_hash=HASH)
    assert report["primary_mean"] == pytest.approx(0.2)
    assert report["positive_cases"] == 18
    assert report["ci95"][0] < 0 < report["ci95"][1]
    assert report["signal_status"] == "NO_SIGNAL"


def test_negative_effect_cannot_pass(inputs):
    from agent_ex.identity_network.benchmark_analysis import analyze_benchmark_outcomes

    outcomes = synthetic_outcomes(inputs)
    for trial, outcome in zip(inputs[1].payload["trials"], outcomes, strict=True):
        if trial["variant"] in ("BB", "GG"):
            outcome["post_stance"] = 8 - outcome["post_stance"]
    report = analyze_benchmark_outcomes(*inputs, outcomes, expected_hash=HASH)
    assert report["primary_mean"] == -1
    assert report["positive_cases"] == 0
    assert report["ci95"] == (-1, -1)
    assert report["signal_status"] == "NO_SIGNAL"
