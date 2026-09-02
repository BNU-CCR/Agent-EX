from __future__ import annotations

from dataclasses import MISSING, fields
import inspect
import json
from pathlib import Path

import pytest

import agent_ex
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.mock_matrix import MockScaleCase, load_mock_scale_cases


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
