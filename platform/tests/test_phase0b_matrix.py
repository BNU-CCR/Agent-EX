from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.mock_matrix import CANONICAL_CELL_IDS, load_mock_scale_cases
from agent_ex.phase0b import build_diagnostic_n20_matrix_candidate
from helpers.mock_matrix import build_mock_artifact_family


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper1"


def _scale_case(case_id: str = "mock-n20-fault-recovery"):
    artifact = ArtifactEnvelope.from_payload(
        json.loads((FIXTURE_DIR / "mock_scale_cases.artifact.json").read_text(encoding="utf-8"))
    )
    return next(case for case in load_mock_scale_cases(artifact) if case.case_id == case_id)


def _candidate():
    matched_seed = 20260920
    family = build_mock_artifact_family(n=20, sweeps=2, matched_seed=matched_seed)
    return build_diagnostic_n20_matrix_candidate(
        scale_case=_scale_case(),
        matched_seed=matched_seed,
        topic_package=family.topic_package,
        population_artifact=family.population_artifact,
        initial_stance_artifact=family.initial_stance_artifact,
        initial_reason_artifact=family.initial_reason_artifact,
        persona_template=family.persona_template,
        ws_artifact=family.ws_artifact,
        shadow_artifact=family.shadow_artifact,
        agent_node_mapping=family.agent_node_mapping,
        structural_gate_artifact=family.structural_gate_artifact,
        attention_artifact=family.attention_artifact,
        expression_artifact=family.expression_artifact,
        activation_artifact=family.activation_artifact,
        publish_artifact=family.publish_artifact,
        schedules_by_cell=family.schedules_by_cell,
        manifests_by_cell=family.manifests_by_cell,
        adapter_bindings_by_cell=family.adapter_bindings_by_cell,
    )


def test_diagnostic_matrix_candidate_binds_exact_n20_t2_inventory() -> None:
    candidate = _candidate()

    assert candidate.agent_count == 20
    assert candidate.sweep_count == 2
    assert candidate.cell_ids == CANONICAL_CELL_IDS
    assert candidate.expected_event_count == 480
    assert candidate.max_transport_count == 960
    assert sum(cell.manifest.schedule.count for cell in candidate.matrix.cells) == 480
    assert candidate.calibration_only is True
    assert candidate.formal_parameter_authority is False
    assert candidate.research_parameter_status == "not_frozen"
    assert candidate.to_payload()["record_hash"] == candidate.record_hash


def test_diagnostic_matrix_candidate_exposes_authorization_artifact_keys() -> None:
    candidate = _candidate()

    assert set(candidate.authorization_artifact_hashes) == {
        "topic",
        "population",
        "persona",
        "network",
        "shadow",
        "mapping",
        "attention",
        "expression",
        "activation",
        "publish",
        "schedule",
    }


def test_diagnostic_matrix_candidate_rejects_non_n20_case() -> None:
    scale_case = _scale_case("mock-n100-full-matrix")
    family = build_mock_artifact_family(n=20, sweeps=2, matched_seed=20260920)

    with pytest.raises(ValueError, match="population|20|scale"):
        build_diagnostic_n20_matrix_candidate(
            scale_case=scale_case,
            matched_seed=20260920,
            topic_package=family.topic_package,
            population_artifact=family.population_artifact,
            initial_stance_artifact=family.initial_stance_artifact,
            initial_reason_artifact=family.initial_reason_artifact,
            persona_template=family.persona_template,
            ws_artifact=family.ws_artifact,
            shadow_artifact=family.shadow_artifact,
            agent_node_mapping=family.agent_node_mapping,
            structural_gate_artifact=family.structural_gate_artifact,
            attention_artifact=family.attention_artifact,
            expression_artifact=family.expression_artifact,
            activation_artifact=family.activation_artifact,
            publish_artifact=family.publish_artifact,
            schedules_by_cell=family.schedules_by_cell,
            manifests_by_cell=family.manifests_by_cell,
            adapter_bindings_by_cell=family.adapter_bindings_by_cell,
        )


def test_phase0b_matrix_production_code_does_not_import_tests() -> None:
    source = (Path(__file__).parents[1] / "src" / "agent_ex" / "phase0b" / "matrix.py").read_text(
        encoding="utf-8"
    )

    assert "platform.tests" not in source
    assert "tests.helpers" not in source
    assert "from helpers" not in source
