import copy

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.network import (
    NETWORKX_VERSION,
    build_agent_node_mapping,
    build_structural_gate_artifact,
    build_shadow_artifact,
    build_ws_artifact,
    validate_shadow_artifact,
    validate_structural_gate_artifact,
    validate_ws_artifact,
)


def population_and_round0(n: int, matched_seed: int) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    agent_ids = tuple(f"agent-{index:04d}" for index in range(n))
    population = ArtifactEnvelope.create(
        artifact_type="paper1.mock_population",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.test_population",
        algorithm_version="1.0.0",
        input_hashes={"source": "1" * 64},
        payload={
            "matched_seed": matched_seed,
            "members": tuple({"agent_id": agent_id} for agent_id in agent_ids),
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        },
        rng_provenance=(),
    )
    round0 = ArtifactEnvelope.create(
        artifact_type="paper1.mock_round0_initialization",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.test_round0",
        algorithm_version="1.0.0",
        input_hashes={"source": "2" * 64},
        payload={
            "matched_seed": matched_seed,
            "round0_records": tuple({"agent_id": agent_id} for agent_id in agent_ids),
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        },
        rng_provenance=(),
    )
    return population, round0


def build_mapping(ws: ArtifactEnvelope, *, matched_seed: int) -> ArtifactEnvelope:
    population, round0 = population_and_round0(len(ws.payload["nodes"]), matched_seed)
    return build_agent_node_mapping(
        population_artifact=population,
        round0_initialization_artifact=round0,
        network_artifact=ws,
        matched_seed=matched_seed,
        mock_only=True,
    )


def edge_set(artifact: ArtifactEnvelope) -> set[tuple[int, int]]:
    return {tuple(edge) for edge in artifact.payload["edges"]}


def degrees(artifact: ArtifactEnvelope) -> tuple[int, ...]:
    return tuple(artifact.payload["structure_report"]["degree_sequence"])


def rebuild_with_payload(
    artifact: ArtifactEnvelope, payload: dict[str, object]
) -> ArtifactEnvelope:
    return ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        payload=payload,
        rng_provenance=artifact.rng_provenance,
    )


def test_ws_artifact_is_canonical_deterministic_and_auditable() -> None:
    arguments = {"n": 40, "k": 6, "p": 0.1, "matched_seed": 17, "mock_only": True}

    first = build_ws_artifact(**arguments)
    repeated = build_ws_artifact(**arguments)

    assert first == repeated
    assert first.artifact_type == "paper1.mock_ws_graph"
    assert first.payload["library"] == {
        "name": "networkx",
        "version": NETWORKX_VERSION,
        "generator": "networkx.generators.random_graphs.watts_strogatz_graph",
    }
    assert first.payload["metadata"] == {
        "mock_only": True,
        "research_parameter_status": "not_frozen",
    }
    assert first.rng_provenance[0].namespace == "ws_graph"
    assert "cell_id" not in first.rng_provenance[0].coordinates
    assert first.payload["nodes"] == tuple(range(40))
    assert first.payload["edges"] == tuple(sorted(edge_set(first)))
    assert all(left < right for left, right in edge_set(first))
    assert first.payload["structure_report"]["connected"] is True
    assert first.payload["structure_report"]["edge_count"] == 120
    assert validate_ws_artifact(first) == first.payload["structure_report"]


def test_ws_seed_changes_graph_but_same_seed_is_reused_across_cells() -> None:
    arguments = {"n": 80, "k": 10, "p": 0.1, "mock_only": True}
    seed_a = build_ws_artifact(matched_seed=101, **arguments)
    all_cells = tuple(build_ws_artifact(matched_seed=101, **arguments) for _ in range(12))
    seed_b = build_ws_artifact(matched_seed=102, **arguments)

    assert all(item == seed_a for item in all_cells)
    assert edge_set(seed_a) != edge_set(seed_b)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"n": True}, TypeError),
        ({"n": 2}, ValueError),
        ({"k": True}, TypeError),
        ({"k": 3}, ValueError),
        ({"k": 40}, ValueError),
        ({"p": True}, TypeError),
        ({"p": -0.01}, ValueError),
        ({"p": 1.01}, ValueError),
        ({"matched_seed": True}, TypeError),
        ({"mock_only": False}, ValueError),
    ],
)
def test_ws_parameters_fail_closed(overrides, error) -> None:
    arguments = {"n": 40, "k": 6, "p": 0.1, "matched_seed": 17, "mock_only": True}
    arguments.update(overrides)

    with pytest.raises(error):
        build_ws_artifact(**arguments)


def test_ws_validation_rejects_noncanonical_or_hash_consistent_drift() -> None:
    artifact = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=17, mock_only=True)
    payload = copy.deepcopy(artifact.to_payload()["payload"])
    payload["edges"][0] = [0, 0]
    drifted = rebuild_with_payload(artifact, payload)

    with pytest.raises(ValueError, match="self-loop|canonical|structure"):
        validate_ws_artifact(drifted)


@pytest.mark.parametrize("bad_node", [True, False])
def test_ws_validation_rejects_boolean_nodes_and_endpoints(bad_node: bool) -> None:
    artifact = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=17, mock_only=True)
    payload = copy.deepcopy(artifact.to_payload()["payload"])
    payload["nodes"][0] = bad_node
    with pytest.raises((TypeError, ValueError), match="integer|boolean|node"):
        validate_ws_artifact(rebuild_with_payload(artifact, payload))

    payload = copy.deepcopy(artifact.to_payload()["payload"])
    payload["edges"][0][0] = bad_node
    with pytest.raises((TypeError, ValueError), match="integer|boolean|endpoint"):
        validate_ws_artifact(rebuild_with_payload(artifact, payload))


def test_ws_validation_rejects_hash_consistent_rng_and_implementation_drift() -> None:
    artifact = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=17, mock_only=True)
    payload = copy.deepcopy(artifact.to_payload()["payload"])
    payload["rng_implementation"] = "drifted"
    with pytest.raises(ValueError, match="RNG implementation"):
        validate_ws_artifact(rebuild_with_payload(artifact, payload))

    provenance = artifact.rng_provenance[0]
    drifted_provenance = type(provenance).create(
        matched_seed=17,
        namespace="ws_graph",
        coordinates={**provenance.coordinates, "algorithm_version": "9.9.9"},
    )
    drifted = ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        payload=artifact.payload,
        rng_provenance=(drifted_provenance,),
    )
    with pytest.raises(ValueError, match="RNG provenance"):
        validate_ws_artifact(drifted)


def test_ws_validation_binds_parameters_to_input_hash() -> None:
    artifact = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=17, mock_only=True)
    payload = copy.deepcopy(artifact.to_payload()["payload"])
    payload["parameters"]["p"] = 0.2
    drifted = rebuild_with_payload(artifact, payload)

    with pytest.raises(ValueError, match="input hash"):
        validate_ws_artifact(drifted)


def test_ws_validation_rejects_graph_rebuilt_from_a_different_seed() -> None:
    declared = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=17, mock_only=True)
    wrong_seed = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=18, mock_only=True)
    payload = copy.deepcopy(wrong_seed.to_payload()["payload"])
    payload["matched_seed"] = 17
    disguised = rebuild_with_payload(declared, payload)

    with pytest.raises(ValueError, match="deterministic replay"):
        validate_ws_artifact(disguised)


def test_downstream_builders_reject_ws_parameter_hash_drift() -> None:
    artifact = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=17, mock_only=True)
    payload = copy.deepcopy(artifact.to_payload()["payload"])
    payload["parameters"]["p"] = 0.2
    drifted = rebuild_with_payload(artifact, payload)

    with pytest.raises(ValueError, match="input hash"):
        build_shadow_artifact(
            drifted,
            matched_seed=17,
            max_attempts=2,
            trial_budget_per_edge=200,
            mock_only=True,
        )
    with pytest.raises(ValueError, match="input hash"):
        population, round0 = population_and_round0(40, 17)
        build_agent_node_mapping(
            population_artifact=population,
            round0_initialization_artifact=round0,
            network_artifact=drifted,
            matched_seed=17,
            mock_only=True,
        )


def test_shadow_is_connected_disjoint_simple_and_degree_preserving() -> None:
    ws = build_ws_artifact(n=80, k=10, p=0.05, matched_seed=71, mock_only=True)

    shadow = build_shadow_artifact(
        ws, matched_seed=71, max_attempts=3, trial_budget_per_edge=400, mock_only=True
    )

    assert shadow.artifact_type == "paper1.mock_shadow_graph"
    assert edge_set(ws).isdisjoint(edge_set(shadow))
    assert degrees(ws) == degrees(shadow)
    assert shadow.payload["structure_report"]["connected"] is True
    assert shadow.payload["construction_audit"]["forbidden_edges_remaining"] == 0
    assert shadow.payload["construction_audit"]["trial_budget_per_edge"] == 400
    assert shadow.payload["construction_audit"]["max_candidate_trials_per_attempt"] == (
        shadow.payload["structure_report"]["edge_count"] * 400
    )
    assert (
        shadow.payload["construction_audit"]["connectivity_checks"]
        == shadow.payload["construction_audit"]["accepted_swaps"]
    )
    assert shadow.input_hashes["ws_graph"] == ws.output_hash
    assert shadow.rng_provenance[0].namespace == "shadow_graph"
    assert validate_shadow_artifact(shadow, ws) == shadow.payload["structure_report"]


def test_shadow_is_deterministic_for_seed_and_varies_between_seeds() -> None:
    ws = build_ws_artifact(n=60, k=6, p=0.05, matched_seed=7, mock_only=True)
    other_ws = build_ws_artifact(n=60, k=6, p=0.05, matched_seed=8, mock_only=True)
    arguments = {"max_attempts": 3, "trial_budget_per_edge": 300, "mock_only": True}

    first = build_shadow_artifact(ws, matched_seed=7, **arguments)
    repeated = build_shadow_artifact(ws, matched_seed=7, **arguments)
    other = build_shadow_artifact(other_ws, matched_seed=8, **arguments)

    assert first == repeated
    assert edge_set(first) != edge_set(other)


def test_shadow_build_budget_and_impossible_constraints_fail_closed() -> None:
    ws = build_ws_artifact(n=6, k=4, p=0.0, matched_seed=3, mock_only=True)

    with pytest.raises(ValueError, match="impossible|forbidden"):
        build_shadow_artifact(
            ws,
            matched_seed=3,
            max_attempts=2,
            trial_budget_per_edge=20,
            mock_only=True,
        )
    with pytest.raises(ValueError, match="max_attempts"):
        build_shadow_artifact(
            ws,
            matched_seed=3,
            max_attempts=0,
            trial_budget_per_edge=20,
            mock_only=True,
        )
    with pytest.raises(ValueError, match="trial_budget_per_edge"):
        build_shadow_artifact(
            ws,
            matched_seed=3,
            max_attempts=2,
            trial_budget_per_edge=0,
            mock_only=True,
        )


def test_shadow_and_mapping_reject_cross_matched_seed_inputs() -> None:
    ws = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=19, mock_only=True)

    with pytest.raises(ValueError, match="matched_seed"):
        build_shadow_artifact(
            ws,
            matched_seed=20,
            max_attempts=2,
            trial_budget_per_edge=200,
            mock_only=True,
        )
    with pytest.raises(ValueError, match="matched_seed"):
        population, round0 = population_and_round0(40, 20)
        build_agent_node_mapping(
            population_artifact=population,
            round0_initialization_artifact=round0,
            network_artifact=ws,
            matched_seed=20,
            mock_only=True,
        )


def test_shadow_validation_rejects_degree_and_forbidden_edge_drift() -> None:
    ws = build_ws_artifact(n=60, k=6, p=0.05, matched_seed=12, mock_only=True)
    shadow = build_shadow_artifact(
        ws, matched_seed=12, max_attempts=3, trial_budget_per_edge=300, mock_only=True
    )
    payload = copy.deepcopy(shadow.to_payload()["payload"])
    payload["edges"][0] = list(next(iter(edge_set(ws))))
    drifted = rebuild_with_payload(shadow, payload)

    with pytest.raises(ValueError, match="forbidden|degree|structure|canonical"):
        validate_shadow_artifact(drifted, ws)


def test_shadow_validation_binds_budget_to_input_hash() -> None:
    ws = build_ws_artifact(n=60, k=6, p=0.05, matched_seed=12, mock_only=True)
    shadow = build_shadow_artifact(
        ws, matched_seed=12, max_attempts=3, trial_budget_per_edge=300, mock_only=True
    )
    payload = copy.deepcopy(shadow.to_payload()["payload"])
    payload["construction_audit"]["max_attempts"] = 4
    drifted = rebuild_with_payload(shadow, payload)

    with pytest.raises(ValueError, match="input hash|budget"):
        validate_shadow_artifact(drifted, ws)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempts_used", True),
        ("attempts_used", 0),
        ("attempts_used", 4),
        ("candidate_trials", -1),
        ("candidate_trials", True),
        ("accepted_swaps", -1),
        ("accepted_swaps", 1.5),
        ("connectivity_checks", False),
    ],
)
def test_shadow_validation_rejects_invalid_audit_counts(field, value) -> None:
    ws = build_ws_artifact(n=60, k=6, p=0.05, matched_seed=12, mock_only=True)
    shadow = build_shadow_artifact(
        ws, matched_seed=12, max_attempts=3, trial_budget_per_edge=300, mock_only=True
    )
    payload = copy.deepcopy(shadow.to_payload()["payload"])
    payload["construction_audit"][field] = value
    with pytest.raises((TypeError, ValueError), match="audit|attempt|trial|swap|connectivity"):
        validate_shadow_artifact(rebuild_with_payload(shadow, payload), ws)


def test_shadow_validation_rejects_hash_consistent_library_and_rng_drift() -> None:
    ws = build_ws_artifact(n=60, k=6, p=0.05, matched_seed=12, mock_only=True)
    shadow = build_shadow_artifact(
        ws, matched_seed=12, max_attempts=3, trial_budget_per_edge=300, mock_only=True
    )
    payload = copy.deepcopy(shadow.to_payload()["payload"])
    payload["library"]["version"] = "0.0.0"
    with pytest.raises(ValueError, match="library"):
        validate_shadow_artifact(rebuild_with_payload(shadow, payload), ws)

    payload = copy.deepcopy(shadow.to_payload()["payload"])
    payload["rng_implementation"] = "drifted"
    with pytest.raises(ValueError, match="RNG implementation"):
        validate_shadow_artifact(rebuild_with_payload(shadow, payload), ws)


def test_shadow_validation_rejects_hash_consistent_zeroed_audit() -> None:
    ws = build_ws_artifact(n=60, k=6, p=0.05, matched_seed=12, mock_only=True)
    shadow = build_shadow_artifact(
        ws, matched_seed=12, max_attempts=3, trial_budget_per_edge=300, mock_only=True
    )
    payload = copy.deepcopy(shadow.to_payload()["payload"])
    payload["construction_audit"]["accepted_swaps"] = 0
    payload["construction_audit"]["connectivity_checks"] = 0
    payload["construction_audit"]["candidate_trials"] = 0

    with pytest.raises(ValueError, match="deterministic replay"):
        validate_shadow_artifact(rebuild_with_payload(shadow, payload), ws)


def test_shadow_validation_accepts_audit_with_connectivity_rollbacks() -> None:
    ws = build_ws_artifact(n=10, k=2, p=0.05, matched_seed=1, mock_only=True)

    shadow = build_shadow_artifact(
        ws, matched_seed=1, max_attempts=5, trial_budget_per_edge=100, mock_only=True
    )

    assert (
        shadow.payload["construction_audit"]["connectivity_checks"]
        > shadow.payload["construction_audit"]["accepted_swaps"]
    )
    assert validate_shadow_artifact(shadow, ws) == shadow.payload["structure_report"]


def test_shadow_audit_accounts_for_every_failed_attempt_before_success() -> None:
    ws = build_ws_artifact(n=10, k=2, p=0.05, matched_seed=15, mock_only=True)

    shadow = build_shadow_artifact(
        ws, matched_seed=15, max_attempts=10, trial_budget_per_edge=1, mock_only=True
    )
    audit = shadow.payload["construction_audit"]

    assert "attempt_audits" in audit
    attempts = audit["attempt_audits"]
    assert audit["attempts_used"] == 9
    assert len(attempts) == audit["attempts_used"]
    assert tuple(item["attempt_index"] for item in attempts) == tuple(
        range(1, audit["attempts_used"] + 1)
    )
    assert all(item["succeeded"] is False for item in attempts[:-1])
    assert attempts[-1]["succeeded"] is True
    assert all(item["forbidden_edges_remaining"] > 0 for item in attempts[:-1])
    assert attempts[-1]["forbidden_edges_remaining"] == 0
    for field in ("accepted_swaps", "connectivity_checks", "candidate_trials"):
        assert audit[field] == sum(item[field] for item in attempts)
    assert validate_shadow_artifact(shadow, ws) == shadow.payload["structure_report"]


def test_agent_node_mapping_is_random_fixed_and_not_cell_conditioned() -> None:
    ws = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=19, mock_only=True)
    agent_ids = tuple(f"agent-{index:04d}" for index in range(40))

    mapping = build_mapping(ws, matched_seed=19)
    all_cells = tuple(build_mapping(ws, matched_seed=19) for _ in range(12))
    other_seed = build_mapping(
        build_ws_artifact(n=40, k=6, p=0.1, matched_seed=20, mock_only=True),
        matched_seed=20,
    )

    assignments = mapping.payload["assignments"]
    assert all(item == mapping for item in all_cells)
    assert tuple(item["agent_id"] for item in assignments) == agent_ids
    assert tuple(item["node_id"] for item in assignments) != tuple(range(40))
    assert {item["node_id"] for item in assignments} == set(range(40))
    assert other_seed.payload["assignments"] != assignments
    assert mapping.rng_provenance[0].namespace == "agent_node_mapping"
    assert "cell_id" not in mapping.rng_provenance[0].coordinates
    assert set(mapping.input_hashes) == {"population", "round0_initialization", "network_graph"}


def test_agent_node_mapping_rejects_cross_seed_or_agent_mixture() -> None:
    ws = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=19, mock_only=True)
    population, round0 = population_and_round0(40, 19)
    _, other_round0 = population_and_round0(40, 20)
    with pytest.raises(ValueError, match="matched_seed"):
        build_agent_node_mapping(
            population_artifact=population,
            round0_initialization_artifact=other_round0,
            network_artifact=ws,
            matched_seed=19,
            mock_only=True,
        )

    payload = copy.deepcopy(round0.to_payload()["payload"])
    payload["round0_records"][0]["agent_id"] = "agent-foreign"
    mixed = rebuild_with_payload(round0, payload)
    with pytest.raises(ValueError, match="agent IDs|population"):
        build_agent_node_mapping(
            population_artifact=population,
            round0_initialization_artifact=mixed,
            network_artifact=ws,
            matched_seed=19,
            mock_only=True,
        )


def test_agent_node_mapping_uses_validated_ws_as_the_single_position_frame() -> None:
    ws = build_ws_artifact(n=40, k=6, p=0.1, matched_seed=19, mock_only=True)
    shadow = build_shadow_artifact(
        ws, matched_seed=19, max_attempts=3, trial_budget_per_edge=200, mock_only=True
    )

    with pytest.raises(ValueError, match="WS graph"):
        build_agent_node_mapping(
            population_artifact=population_and_round0(40, 19)[0],
            round0_initialization_artifact=population_and_round0(40, 19)[1],
            network_artifact=shadow,
            matched_seed=19,
            mock_only=True,
        )


def test_structural_gate_uses_independent_nulls_and_records_relative_metrics() -> None:
    ws = build_ws_artifact(n=80, k=10, p=0.05, matched_seed=71, mock_only=True)
    gate = build_structural_gate_artifact(
        ws, matched_seed=71, random_null_replicates=3, mock_only=True
    )

    assert gate.payload["opinion_inputs_read"] == ()
    assert {item.namespace for item in gate.rng_provenance} == {
        "structure_ring_lattice",
        "structure_random_null",
    }
    assert len(gate.payload["baselines"]["random_graphs"]) == 3
    metrics = gate.payload["relative_metrics"]
    assert metrics["clustering_vs_random"] > 0
    assert metrics["path_length_vs_random"] > 0
    assert metrics["small_world_coefficient"] == pytest.approx(
        metrics["clustering_vs_random"] / metrics["path_length_vs_random"]
    )
    assert validate_structural_gate_artifact(gate, ws) == metrics


def test_structural_gate_validation_rejects_opinion_or_hash_consistent_audit_drift() -> None:
    ws = build_ws_artifact(n=80, k=10, p=0.05, matched_seed=71, mock_only=True)
    gate = build_structural_gate_artifact(
        ws, matched_seed=71, random_null_replicates=3, mock_only=True
    )
    payload = copy.deepcopy(gate.to_payload()["payload"])
    payload["opinion_inputs_read"] = ["private_state"]
    with pytest.raises(ValueError, match="opinion"):
        validate_structural_gate_artifact(rebuild_with_payload(gate, payload), ws)


def test_n1000_structural_build_does_not_require_an_llm() -> None:
    ws = build_ws_artifact(n=1000, k=10, p=0.05, matched_seed=20260729, mock_only=True)
    shadow = build_shadow_artifact(
        ws,
        matched_seed=20260729,
        max_attempts=3,
        trial_budget_per_edge=1000,
        mock_only=True,
    )

    assert ws.payload["structure_report"]["node_count"] == 1000
    assert ws.payload["structure_report"]["edge_count"] == 5000
    assert degrees(ws) == degrees(shadow)
    assert edge_set(ws).isdisjoint(edge_set(shadow))
