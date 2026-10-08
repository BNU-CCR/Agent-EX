"""Offline approved-input tests, not inference or experimental measurements."""

import copy
import json
from pathlib import Path

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import _json_ready, canonical_payload_hash

BENCHMARK_HASH = "9c2345580024523794a2d433500229d55e166414f18f5c0bd06baba893c8eb10"


@pytest.fixture
def benchmark():
    path = (
        Path(__file__).parents[1]
        / "configs/identity-network/manipulation-retirement-20261008/benchmark.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_inventory_preserves_all_cases_and_only_varies_groups_and_repeat(benchmark):
    from agent_ex.identity_network.benchmark_trials import build_benchmark_trial_inventory

    original = copy.deepcopy(benchmark)
    plan = build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH)
    assert benchmark == original
    payload = _json_ready(plan.payload)
    assert payload["trial_count"] == 240
    assert len(payload["cases"]) == 30
    assert payload["dispatch_authorized"] is False
    assert payload["cloud_launch_eligible"] is False
    assert payload["stage"] == "pure_label"
    pairs = set()
    identities = set()
    for index, case in enumerate(payload["cases"]):
        fixed = case["fixed_content"]
        assert fixed["source_message"] == benchmark["cases"][index]["source_message"]
        assert fixed["source_reason"] == benchmark["cases"][index]["source_reason"]
        assert fixed["self_history"] == []
        assert fixed["pre_confidence"] is None
        assert fixed["persona_context"] == benchmark["persona_context"]
        trials = payload["trials"][index * 8 : index * 8 + 8]
        for repeat in (1, 2):
            quartet = trials[(repeat - 1) * 4 : repeat * 4]
            assert [t["variant"] for t in quartet] == ["BB", "BG", "GG", "GB"]
            assert len({t["sampling_seed"] for t in quartet}) == 1
            pairs.add(quartet[0]["sampling_seed"])
            for trial in quartet:
                assert trial["case_id"] == case["case_id"]
                assert trial["repeat_id"] == repeat
                assert trial["fixed_content_hash"] == canonical_payload_hash(fixed)
                assert trial["source_id"] == case["case_id"]
                assert trial["focal_group"] == {"B": "Blue", "G": "Green"}[trial["variant"][0]]
                assert trial["source_group"] == {"B": "Blue", "G": "Green"}[trial["variant"][1]]
                identities.add(trial["trial_id"])
    assert len(pairs) == 60
    assert len(identities) == 240
    with pytest.raises(TypeError):
        plan.payload["trials"][0]["sampling_seed"] = 0


def test_seed_recipe_exact_and_strict():
    from agent_ex.identity_network.benchmark_trials import derive_generation_seed

    digest = canonical_payload_hash(
        {
            "namespace": "sis-mc-stage-a-v1",
            "case_id": "MC-D1-U-01",
            "repeat_id": 1,
        }
    )
    assert derive_generation_seed("MC-D1-U-01", 1) == int(digest[:8], 16) & 0x7FFFFFFF
    for case, repeat in [("bad", 1), ("MC-D1-U-01", True), ("MC-D1-U-01", 0), ("MC-D1-U-01", 3)]:
        with pytest.raises(ValueError):
            derive_generation_seed(case, repeat)


def test_saved_seed_table_and_inventory_hash_cold_replay(benchmark):
    from agent_ex.identity_network.benchmark_trials import build_benchmark_trial_inventory

    directory = (
        Path(__file__).parents[1] / "configs/identity-network/manipulation-retirement-20261008"
    )
    saved = json.loads(
        (directory / "seed-analysis-implementation-v1.json").read_text(encoding="utf-8")
    )
    plan = build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH)
    assert saved["inventory_payload_hash"] == plan.output_hash
    assert saved["inventory_artifact_id"] == plan.artifact_id
    assert saved["seed_table"] == [
        {"case_id": t["case_id"], "repeat_id": t["repeat_id"], "seed": t["sampling_seed"]}
        for t in plan.payload["trials"]
        if t["variant"] == "BB"
    ]
    assert saved["dispatch_authorized"] is False


def test_inventory_deterministic_and_approval_bound(benchmark):
    from agent_ex.identity_network.benchmark_trials import build_benchmark_trial_inventory

    first = build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH)
    second = build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH)
    assert first == second
    with pytest.raises(ValueError, match="hash"):
        build_benchmark_trial_inventory(benchmark, expected_hash="0" * 64)


def test_collision_stops_without_changing_seed(benchmark, monkeypatch):
    from agent_ex.identity_network import benchmark_trials

    monkeypatch.setattr(benchmark_trials, "derive_generation_seed", lambda *_: 11)
    with pytest.raises(ValueError, match="collision"):
        benchmark_trials.build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH)


@pytest.mark.parametrize(
    "field,value", [("sampling_seed", 0), ("focal_group", "Green"), ("repeat_id", 2)]
)
def test_cold_replay_rejects_rehashed_trial_drift(benchmark, field, value):
    from agent_ex.identity_network.benchmark_trials import (
        build_benchmark_trial_inventory,
        replay_benchmark_trial_inventory,
    )

    plan = build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH)
    payload = _json_ready(plan.payload)
    payload["trials"][0][field] = value
    forged = ArtifactEnvelope.create(
        artifact_type=plan.artifact_type,
        schema_version=plan.schema_version,
        algorithm_id=plan.algorithm_id,
        algorithm_version=plan.algorithm_version,
        input_hashes=dict(plan.input_hashes),
        rng_provenance=plan.rng_provenance,
        payload=payload,
    )
    with pytest.raises(ValueError, match="replay"):
        replay_benchmark_trial_inventory(forged, benchmark, expected_hash=BENCHMARK_HASH)
    assert replay_benchmark_trial_inventory(plan, benchmark, expected_hash=BENCHMARK_HASH) == plan
