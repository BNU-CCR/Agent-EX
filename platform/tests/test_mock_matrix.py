from __future__ import annotations

from dataclasses import MISSING, fields, replace
import inspect
import json
from pathlib import Path

import pytest

import agent_ex
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import FrozenSchedule, canonical_payload_hash, derive_event_id, derive_run_id
from agent_ex.execution_evidence import MockAdapterExecutionBinding
from agent_ex.mock_matrix import (
    CANONICAL_CELL_IDS,
    MockCellBinding,
    MockMatchedSeedMatrix,
    MockScaleCase,
    build_mock_matched_seed_matrix,
    load_mock_scale_cases,
    validate_mock_matched_seed_matrix,
)
from helpers.mock_matrix import build_mock_artifact_family, build_mock_matrix_fixture


EXPECTED_CASES = (
    {
        "case_id": "mock-n20-fault-recovery",
        "population_size": 20,
        "stance_counts": [1, 2, 4, 6, 4, 2, 1],
        "integration_sweeps": 2,
        "recovery_sweeps": 2,
        "shape_sweeps": 2,
        "full_matrix_execution": False,
        "release_execution": False,
        "stress_cell_id": None,
        "mock_feed_capacity": 6,
        "mock_memory_window": 3,
        "mock_clock_start": "2040-01-01T00:00:00Z",
        "mock_clock_step_seconds": 1,
    },
    {
        "case_id": "mock-n100-full-matrix",
        "population_size": 100,
        "stance_counts": [5, 10, 20, 30, 20, 10, 5],
        "integration_sweeps": 1,
        "recovery_sweeps": 1,
        "shape_sweeps": 1,
        "full_matrix_execution": True,
        "release_execution": False,
        "stress_cell_id": None,
        "mock_feed_capacity": 6,
        "mock_memory_window": 3,
        "mock_clock_start": "2040-01-01T00:00:00Z",
        "mock_clock_step_seconds": 1,
    },
    {
        "case_id": "mock-n1000-release-shape",
        "population_size": 1000,
        "stance_counts": [50, 100, 200, 300, 200, 100, 50],
        "integration_sweeps": 1,
        "recovery_sweeps": 1,
        "shape_sweeps": 50,
        "full_matrix_execution": False,
        "release_execution": True,
        "stress_cell_id": "P1-I1-C1-E2",
        "mock_feed_capacity": 6,
        "mock_memory_window": 3,
        "mock_clock_start": "2040-01-01T00:00:00Z",
        "mock_clock_step_seconds": 1,
    },
)


def scale_artifact(cases: tuple[dict[str, object], ...] = EXPECTED_CASES) -> ArtifactEnvelope:
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_scale_cases",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": "4" * 64},
        payload={
            "schema_version": "paper1.mock-scale-cases.v2",
            "cases": [dict(case) for case in cases],
            "metadata": {
                "mock_only": True,
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
            },
        },
        rng_provenance=(),
    )


def test_scale_contract_round_trips_exact_explicit_cases() -> None:
    cases = load_mock_scale_cases(scale_artifact())

    assert tuple(case.to_payload() for case in cases) == EXPECTED_CASES
    assert all(type(value) is MockScaleCase for value in cases)
    assert all(
        field.default is MISSING and field.default_factory is MISSING
        for field in fields(MockScaleCase)
    )
    assert inspect.signature(load_mock_scale_cases).parameters["artifact"].default is (
        inspect.Parameter.empty
    )


def test_checked_scale_fixture_is_exact_v2_mock_only_non_authority() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "paper1" / "mock_scale_cases.artifact.json"
    artifact = ArtifactEnvelope.from_payload(json.loads(fixture_path.read_text(encoding="utf-8")))

    assert tuple(case.to_payload() for case in load_mock_scale_cases(artifact)) == EXPECTED_CASES
    assert artifact.payload["metadata"] == {
        "mock_only": True,
        "research_parameter_status": "not_frozen",
        "formal_parameter_authority": False,
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "extra",
        "bool_for_int",
        "short_stance_counts",
        "negative_stance_count",
        "wrong_stance_sum",
        "naive_clock",
        "non_utc_clock",
        "unknown_stress_cell",
    ),
)
def test_scale_case_rejects_malformed_or_noncanonical_payload(mutation: str) -> None:
    payload = dict(EXPECTED_CASES[0])
    if mutation == "missing":
        del payload["case_id"]
    elif mutation == "extra":
        payload["unexpected"] = True
    elif mutation == "bool_for_int":
        payload["population_size"] = True
    elif mutation == "short_stance_counts":
        payload["stance_counts"] = [1, 2, 4]
    elif mutation == "negative_stance_count":
        payload["stance_counts"] = [1, 2, 4, 7, 4, 2, -1]
    elif mutation == "wrong_stance_sum":
        payload["stance_counts"] = [1, 2, 4, 5, 4, 2, 1]
    elif mutation == "naive_clock":
        payload["mock_clock_start"] = "2040-01-01T00:00:00"
    elif mutation == "non_utc_clock":
        payload["mock_clock_start"] = "2040-01-01T08:00:00+08:00"
    else:
        payload["stress_cell_id"] = "P1-I2-C0-E0"

    with pytest.raises((TypeError, ValueError)):
        MockScaleCase.from_payload(payload)


def test_scale_loader_rejects_duplicate_cases_and_metadata_authority_drift() -> None:
    duplicate = tuple(dict(case) for case in EXPECTED_CASES)
    duplicate = (*duplicate[:-1], {**duplicate[-1], "case_id": duplicate[0]["case_id"]})
    with pytest.raises(ValueError, match="unique"):
        load_mock_scale_cases(scale_artifact(duplicate))

    payload = scale_artifact().to_payload()
    payload["payload"]["metadata"]["formal_parameter_authority"] = True
    forged = ArtifactEnvelope.create(
        artifact_type=payload["artifact_type"],
        schema_version=payload["schema_version"],
        algorithm_id=payload["algorithm_id"],
        algorithm_version=payload["algorithm_version"],
        input_hashes=payload["input_hashes"],
        payload=payload["payload"],
        rng_provenance=(),
    )
    with pytest.raises(ValueError, match="mock-only|not frozen|authority"):
        load_mock_scale_cases(forged)


@pytest.mark.parametrize(
    ("field", "integer_value"),
    (
        ("mock_only", 1),
        ("formal_parameter_authority", 0),
    ),
)
def test_scale_loader_rejects_integer_boolean_metadata(field: str, integer_value: int) -> None:
    payload = scale_artifact().to_payload()
    payload["payload"]["metadata"][field] = integer_value
    forged = ArtifactEnvelope.create(
        artifact_type=payload["artifact_type"],
        schema_version=payload["schema_version"],
        algorithm_id=payload["algorithm_id"],
        algorithm_version=payload["algorithm_version"],
        input_hashes=payload["input_hashes"],
        payload=payload["payload"],
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="mock-only|not frozen|authority"):
        load_mock_scale_cases(forged)


def test_scale_contract_is_exported_from_package_root() -> None:
    assert agent_ex.MockScaleCase is MockScaleCase
    assert agent_ex.load_mock_scale_cases is load_mock_scale_cases


def _build_kwargs(family, scale_case):
    return {
        "scale_case": scale_case,
        "matched_seed": 101,
        "topic_package": family.topic_package,
        "population_artifact": family.population_artifact,
        "initial_stance_artifact": family.initial_stance_artifact,
        "initial_reason_artifact": family.initial_reason_artifact,
        "persona_template": family.persona_template,
        "ws_artifact": family.ws_artifact,
        "shadow_artifact": family.shadow_artifact,
        "agent_node_mapping": family.agent_node_mapping,
        "structural_gate_artifact": family.structural_gate_artifact,
        "attention_artifact": family.attention_artifact,
        "expression_artifact": family.expression_artifact,
        "activation_artifact": family.activation_artifact,
        "publish_artifact": family.publish_artifact,
        "schedules_by_cell": family.schedules_by_cell,
        "manifests_by_cell": family.manifests_by_cell,
        "adapter_bindings_by_cell": family.adapter_bindings_by_cell,
    }


@pytest.fixture(scope="module")
def matrix_fixture(tmp_path_factory):
    return build_mock_matrix_fixture(
        tmp_path_factory.mktemp("matrix"), case_id="mock-n20-fault-recovery", sweeps=2
    )


def test_matrix_is_canonical_exact_cover_and_binds_every_shared_input(matrix_fixture) -> None:
    matrix = matrix_fixture.matrix

    assert tuple(binding.cell_id for binding in matrix.cells) == CANONICAL_CELL_IDS
    assert len(matrix.cells) == 12
    assert validate_mock_matched_seed_matrix(matrix) is None
    expected_clock_hash = canonical_payload_hash(
        {
            "schema_version": "paper1.mock-clock-sequence.v1",
            "mock_clock_start": matrix.scale_case.mock_clock_start,
            "mock_clock_step_seconds": matrix.scale_case.mock_clock_step_seconds,
        }
    )
    assert {binding.clock_sequence_hash for binding in matrix.cells} == {expected_clock_hash}
    assert {binding.clock_sequence_id for binding in matrix.cells} == {
        "mock-clock-" + expected_clock_hash
    }
    assert all(
        field.default is MISSING and field.default_factory is MISSING
        for field in fields(MockCellBinding)
        if field.name != "matrix_hash"
    )
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in inspect.signature(build_mock_matched_seed_matrix).parameters.values()
    )
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in inspect.signature(validate_mock_matched_seed_matrix).parameters.values()
    )


def test_matrix_fixture_clock_replays_explicit_utc_start_and_step(matrix_fixture) -> None:
    assert matrix_fixture.clock() == "2040-01-01T00:00:00Z"
    assert matrix_fixture.clock() == "2040-01-01T00:00:01Z"


@pytest.mark.parametrize("attack", ("missing", "duplicate", "foreign_seed"))
def test_matrix_validator_rejects_cover_and_seed_attacks(matrix_fixture, attack: str) -> None:
    matrix = matrix_fixture.matrix
    if attack == "missing":
        cells = matrix.cells[:-1]
        attacked = replace(matrix, cells=cells)
    elif attack == "duplicate":
        cells = (*matrix.cells[:-1], matrix.cells[0])
        attacked = replace(matrix, cells=cells)
    else:
        attacked = replace(matrix, matched_seed=102)

    with pytest.raises(ValueError):
        validate_mock_matched_seed_matrix(attacked)


@pytest.mark.parametrize(
    "attack",
    (
        "population",
        "stance",
        "reason",
        "mapping",
        "schedule",
        "swapped_graph",
        "e0_graph",
        "persona",
        "publish_flag",
        "runtime",
        "script",
        "manifest_cell",
        "clock",
    ),
)
def test_matrix_rejects_each_invariant_attack_before_sqlite_creation(
    matrix_fixture, tmp_path: Path, attack: str
) -> None:
    matrix = matrix_fixture.matrix
    family = matrix_fixture.family
    cells = list(matrix.cells)
    target = cells[0]
    if attack in {"population", "stance", "reason", "mapping"}:
        hashes = dict(target.artifact_hashes)
        hashes[attack] = "f" * 64
        cells[0] = replace(target, artifact_hashes=hashes)
    elif attack == "schedule":
        cells[0] = replace(target, artifact_hashes={**target.artifact_hashes, "schedule": "f" * 64})
    elif attack == "swapped_graph":
        e1_index = CANONICAL_CELL_IDS.index("P1-I0-C0-E1")
        e2_index = CANONICAL_CELL_IDS.index("P1-I0-C0-E2")
        cells[e1_index] = replace(
            cells[e1_index], exposure_graph_hash=family.ws_artifact.output_hash
        )
        cells[e2_index] = replace(
            cells[e2_index], exposure_graph_hash=family.shadow_artifact.output_hash
        )
    elif attack == "e0_graph":
        cells[0] = replace(target, exposure_graph_hash=family.ws_artifact.output_hash)
    elif attack == "persona":
        cells[0] = replace(target, identity_present=True)
    elif attack == "publish_flag":
        schedule = target.manifest.schedule
        first = schedule.slots[0]
        changed = FrozenSchedule(
            schema_version=schedule.schema_version,
            algorithm_id=schedule.algorithm_id,
            algorithm_version=schedule.algorithm_version,
            population_size=schedule.population_size,
            sweep_count=schedule.sweep_count,
            slots=(replace(first, publish_flag=not first.publish_flag), *schedule.slots[1:]),
        )
        changed_spec = {**target.manifest.run_spec, "schedule_hash": changed.schedule_hash}
        cells[0] = replace(
            target,
            manifest=replace(
                target.manifest,
                run_id=derive_run_id(
                    changed_spec, target.manifest.matched_seed, target.manifest.launch_nonce
                ),
                schedule=changed,
                schedule_hash=changed.schedule_hash,
                run_spec=changed_spec,
                run_spec_hash=canonical_payload_hash(changed_spec),
            ),
        )
    elif attack in {"runtime", "script"}:
        binding = target.adapter_binding
        script_step_hashes = dict(binding.script_step_hashes)
        if attack == "script":
            first_event_id = next(iter(script_step_hashes))
            script_step_hashes[first_event_id] = ("e" * 64,)
        cells[0] = replace(
            target,
            adapter_binding=MockAdapterExecutionBinding.create(
                expected_adapter_kind="mock",
                expected_adapter_version="2.0.0" if attack == "runtime" else "1.0.0",
                runtime_identity={
                    "adapter": "mock",
                    "adapter_version": "2.0.0" if attack == "runtime" else "1.0.0",
                },
                model_identity=binding.model_identity,
                script_step_hashes=script_step_hashes,
                mock_only=True,
            ),
        )
    elif attack == "manifest_cell":
        changed_spec = {**target.manifest.run_spec, "cell_id": "P1-I1-C0-E0"}
        cells[0] = replace(
            target,
            manifest=replace(
                target.manifest,
                run_id=derive_run_id(
                    changed_spec, target.manifest.matched_seed, target.manifest.launch_nonce
                ),
                run_spec=changed_spec,
                run_spec_hash=canonical_payload_hash(changed_spec),
            ),
        )
    else:
        cells[0] = replace(target, clock_sequence_hash="d" * 64)
    attacked = replace(matrix, cells=tuple(cells))

    with pytest.raises(ValueError):
        validate_mock_matched_seed_matrix(attacked)
    assert not tuple(tmp_path.glob("*.sqlite"))


def test_builder_rejects_drifted_shared_inputs_before_matrix_construction(matrix_fixture) -> None:
    family = matrix_fixture.family
    kwargs = _build_kwargs(family, matrix_fixture.scale_case)
    other = build_mock_artifact_family(n=20, sweeps=2, matched_seed=102)

    for name in (
        "population_artifact",
        "initial_stance_artifact",
        "initial_reason_artifact",
        "agent_node_mapping",
    ):
        with pytest.raises(ValueError):
            build_mock_matched_seed_matrix(**{**kwargs, name: getattr(other, name)})


def test_builder_rejects_hash_consistent_non_bijective_mapping(matrix_fixture) -> None:
    family = matrix_fixture.family
    kwargs = _build_kwargs(family, matrix_fixture.scale_case)
    payload = family.agent_node_mapping.to_payload()
    assignments = payload["payload"]["assignments"]
    assignments[1]["node_id"] = assignments[0]["node_id"]
    forged = ArtifactEnvelope.create(
        artifact_type=payload["artifact_type"],
        schema_version=payload["schema_version"],
        algorithm_id=payload["algorithm_id"],
        algorithm_version=payload["algorithm_version"],
        input_hashes=payload["input_hashes"],
        payload=payload["payload"],
        rng_provenance=family.agent_node_mapping.rng_provenance,
    )

    with pytest.raises(ValueError, match="mapping|replay|bijective"):
        build_mock_matched_seed_matrix(**{**kwargs, "agent_node_mapping": forged})


def test_builder_rejects_integer_mock_only_metadata_before_matrix_construction(
    matrix_fixture,
) -> None:
    family = matrix_fixture.family
    kwargs = _build_kwargs(family, matrix_fixture.scale_case)
    payload = family.persona_template.to_payload()
    payload["payload"]["metadata"]["mock_only"] = 1
    forged = ArtifactEnvelope.create(
        artifact_type=payload["artifact_type"],
        schema_version=payload["schema_version"],
        algorithm_id=payload["algorithm_id"],
        algorithm_version=payload["algorithm_version"],
        input_hashes=payload["input_hashes"],
        payload=payload["payload"],
        rng_provenance=family.persona_template.rng_provenance,
    )

    with pytest.raises(ValueError, match="mock-only|not frozen"):
        build_mock_matched_seed_matrix(**{**kwargs, "persona_template": forged})


def test_validator_rejects_rehashed_manifest_with_contradictory_cell_binding(
    matrix_fixture,
) -> None:
    matrix = matrix_fixture.matrix
    index = CANONICAL_CELL_IDS.index("P1-I0-C0-E1")
    target = matrix.cells[index]
    manifest = target.manifest
    changed_spec = {
        **manifest.run_spec,
        "identity_present": True,
        "exposure_graph_hash": target.artifact_hashes["ws"],
    }
    changed_run_id = derive_run_id(changed_spec, manifest.matched_seed, manifest.launch_nonce)
    changed_manifest = replace(
        manifest,
        run_id=changed_run_id,
        run_spec=changed_spec,
        run_spec_hash=canonical_payload_hash(changed_spec),
    )
    old_event_ids = tuple(
        derive_event_id(manifest.run_id, ordinal) for ordinal in range(manifest.schedule.count)
    )
    new_event_ids = tuple(
        derive_event_id(changed_run_id, ordinal) for ordinal in range(manifest.schedule.count)
    )
    binding = target.adapter_binding
    changed_binding = MockAdapterExecutionBinding.create(
        expected_adapter_kind=binding.expected_adapter_kind,
        expected_adapter_version=binding.expected_adapter_version,
        runtime_identity=binding.runtime_identity,
        model_identity=binding.model_identity,
        script_step_hashes={
            new_event_id: binding.script_step_hashes[old_event_id]
            for old_event_id, new_event_id in zip(old_event_ids, new_event_ids, strict=True)
        },
        mock_only=True,
    )
    cells = list(matrix.cells)
    cells[index] = replace(
        target,
        manifest=changed_manifest,
        adapter_binding=changed_binding,
    )

    with pytest.raises(ValueError, match="manifest|cell|factor|graph"):
        validate_mock_matched_seed_matrix(replace(matrix, cells=tuple(cells)))


def test_validator_rejects_scale_case_relabeling(matrix_fixture) -> None:
    n100_case = next(
        case
        for case in load_mock_scale_cases(scale_artifact())
        if case.case_id == "mock-n100-full-matrix"
    )

    with pytest.raises(ValueError, match="scale|population|sweep|binding"):
        validate_mock_matched_seed_matrix(replace(matrix_fixture.matrix, scale_case=n100_case))


def test_matrix_contract_is_exported_from_package_root() -> None:
    assert agent_ex.MockCellBinding is MockCellBinding
    assert agent_ex.MockMatchedSeedMatrix is MockMatchedSeedMatrix
    assert agent_ex.CANONICAL_CELL_IDS is CANONICAL_CELL_IDS
    assert agent_ex.build_mock_matched_seed_matrix is build_mock_matched_seed_matrix
    assert agent_ex.validate_mock_matched_seed_matrix is validate_mock_matched_seed_matrix
