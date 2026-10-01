import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.network import build_ws_artifact
from agent_ex.identity_network.networks import (
    build_randomized_counterpart,
    validate_randomized_counterpart,
)


def test_degree_preserving_connected_replay_with_overlap_allowed():
    ws = build_ws_artifact(n=20, k=4, p=0, matched_seed=7, mock_only=True)
    result = build_randomized_counterpart(ws, matched_seed=7, swap_target=10, max_trials=1000)
    assert result == build_randomized_counterpart(
        ws, matched_seed=7, swap_target=10, max_trials=1000
    )
    report = validate_randomized_counterpart(result, ws)
    assert report["connected"]
    assert report["degree_sequence"] == ws.payload["structure_report"]["degree_sequence"]
    assert result.payload["accepted_swaps"] == 10
    assert result.input_hashes["ws"] == ws.output_hash
    assert set(result.payload["edges"]) != set(ws.payload["edges"])
    assert set(result.payload["edges"]) & set(ws.payload["edges"])
    assert "average_shortest_path_length" in report
    assert "average_clustering" in report


def test_mismatched_seed_and_impossible_budget_fail():
    ws = build_ws_artifact(n=20, k=4, p=0, matched_seed=7, mock_only=True)
    with pytest.raises(ValueError, match="matched"):
        build_randomized_counterpart(ws, matched_seed=8, swap_target=1, max_trials=20)
    with pytest.raises(ValueError, match="budget"):
        build_randomized_counterpart(ws, matched_seed=7, swap_target=10, max_trials=1)
    complete = build_ws_artifact(n=5, k=4, p=0, matched_seed=7, mock_only=True)
    with pytest.raises(ValueError, match="budget"):
        build_randomized_counterpart(complete, matched_seed=7, swap_target=1, max_trials=20)


def test_rehashed_diagnostics_drift_is_rejected():
    ws = build_ws_artifact(n=20, k=4, p=0, matched_seed=7, mock_only=True)
    result = build_randomized_counterpart(ws, matched_seed=7, swap_target=3, max_trials=1000)
    payload = result.to_payload()["payload"]
    payload["structure_report"]["average_clustering"] = 0
    tampered = ArtifactEnvelope.create(
        artifact_type=result.artifact_type,
        schema_version=result.schema_version,
        algorithm_id=result.algorithm_id,
        algorithm_version=result.algorithm_version,
        input_hashes=result.input_hashes,
        payload=payload,
        rng_provenance=result.rng_provenance,
    )
    with pytest.raises(ValueError, match="replay"):
        validate_randomized_counterpart(tampered, ws)
