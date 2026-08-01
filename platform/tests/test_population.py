import math

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.population import build_population_artifact, trs_integerize


INPUT_HASH = "1" * 64


def donors() -> tuple[dict[str, object], ...]:
    return (
        {"donor_id": "d0", "fields": {"gender": "female", "urban": "urban"}},
        {"donor_id": "d1", "fields": {"gender": "male", "urban": "urban"}},
        {"donor_id": "d2", "fields": {"gender": "female", "urban": "rural"}},
        {"donor_id": "d3", "fields": {"gender": "male", "urban": "rural"}},
    )


def test_trs_integerize_is_exact_deterministic_and_auditable() -> None:
    result = trs_integerize(donors(), (1.5, 1.5, 1.5, 1.5), 6, 123)

    assert len(result.records) == 6
    assert sum(result.source_counts.values()) == 6
    assert result.residual_draw_count == 2
    assert result == trs_integerize(donors(), (1.5, 1.5, 1.5, 1.5), 6, 123)
    assert result != trs_integerize(donors(), (1.5, 1.5, 1.5, 1.5), 6, 456)


@pytest.mark.parametrize(
    ("weights", "n", "error"),
    [
        ((1.0,), 4, ValueError),
        ((1.0, 1.0, 1.0, -1.0), 2, ValueError),
        ((1.0, 1.0, 1.0, math.nan), 3, ValueError),
        ((1.0, 1.0, 1.0, True), 4, TypeError),
        ((0.0, 0.0, 0.0, 0.0), 0, ValueError),
        ((1.0, 1.0, 1.0, 1.0), 5, ValueError),
    ],
)
def test_trs_integerize_rejects_illegal_or_unscaled_weights(weights, n, error) -> None:
    with pytest.raises(error):
        trs_integerize(donors(), weights, n, 1)


def test_population_artifact_uses_common_seed_scope_and_reports_balance() -> None:
    constraints = {
        "marginals": {
            "gender": {"female": 10, "male": 10},
            "urban": {"urban": 10, "rural": 10},
        },
        "joints": [
            {
                "fields": ["gender", "urban"],
                "targets": {
                    "female|urban": 5,
                    "male|urban": 5,
                    "female|rural": 5,
                    "male|rural": 5,
                },
            }
        ],
    }
    first = build_population_artifact(
        donors=donors(),
        weights=(5.0, 5.0, 5.0, 5.0),
        n=20,
        matched_seed=17,
        input_artifact_hash=INPUT_HASH,
        constraints=constraints,
        tolerance=0,
        mock_only=True,
    )
    repeated = build_population_artifact(
        donors=donors(),
        weights=(5.0, 5.0, 5.0, 5.0),
        n=20,
        matched_seed=17,
        input_artifact_hash=INPUT_HASH,
        constraints=constraints,
        tolerance=0,
        mock_only=True,
    )

    assert isinstance(first, ArtifactEnvelope)
    assert first == repeated
    assert first.artifact_type == "paper1.mock_population"
    assert len(first.payload["members"]) == 20
    assert first.payload["metadata"]["mock_only"] is True
    diagnostics = first.to_payload()["payload"]["diagnostics"]
    assert {key: value for key, value in diagnostics.items() if key != "balance"} == {
        "clone_count": 16,
        "missing_count": 0,
        "structural_zeros": [],
        "source_counts": {"d0": 5, "d1": 5, "d2": 5, "d3": 5},
        "residual_draw_count": 0,
        "tolerance": 0,
        "marginal_errors": {"gender": {"female": 0, "male": 0}, "urban": {"rural": 0, "urban": 0}},
        "joint_errors": {
            "gender+urban": {"female|rural": 0, "female|urban": 0, "male|rural": 0, "male|urban": 0}
        },
    }
    assert first.rng_provenance[0].namespace == "population"
    assert "cell_id" not in first.rng_provenance[0].coordinates


def test_population_artifact_round_trip_preserves_trs_audit_inputs() -> None:
    artifact = build_population_artifact(
        donors=donors(),
        weights=(5.5, 5.5, 4.5, 4.5),
        n=20,
        matched_seed=17,
        input_artifact_hash=INPUT_HASH,
        constraints={"marginals": {}, "joints": []},
        tolerance=2,
        mock_only=True,
    )

    restored = ArtifactEnvelope.from_payload(artifact.to_payload())

    assert restored == artifact
    assert (
        restored.payload["diagnostics"]["source_counts"]
        == artifact.payload["diagnostics"]["source_counts"]
    )
    assert restored.payload["diagnostics"]["residual_draw_count"] == 2
    assert restored.payload["diagnostics"]["tolerance"] == 2


def test_population_diagnostics_preserve_target_weighted_and_integerized_balance() -> None:
    constraints = {
        "marginals": {"gender": {"female": 10, "male": 10}},
        "joints": [
            {
                "fields": ["gender", "urban"],
                "targets": {
                    "female|urban": 5,
                    "male|urban": 5,
                    "female|rural": 5,
                    "male|rural": 5,
                },
            }
        ],
    }
    artifact = build_population_artifact(
        donors=donors(),
        weights=(5.5, 4.5, 4.5, 5.5),
        n=20,
        matched_seed=17,
        input_artifact_hash=INPUT_HASH,
        constraints=constraints,
        tolerance=1,
        mock_only=True,
    )
    balance = artifact.payload["diagnostics"]["balance"]

    assert balance["target"]["marginals"]["gender"] == {"female": 10, "male": 10}
    assert balance["weighted_donor"]["marginals"]["gender"] == {
        "female": 10.0,
        "male": 10.0,
    }
    assert balance["integerized"]["marginals"]["gender"] == {
        "female": 9,
        "male": 11,
    }
    assert balance["calibration_error"]["joints"]["gender+urban"] == {
        "female|rural": -0.5,
        "female|urban": 0.5,
        "male|rural": 0.5,
        "male|urban": -0.5,
    }
    assert balance["trs_error"]["marginals"]["gender"] == {
        "female": -1.0,
        "male": 1.0,
    }
    assert ArtifactEnvelope.from_payload(artifact.to_payload()) == artifact


@pytest.mark.parametrize(
    ("broken_fields", "match"),
    [
        ({"gender": "male"}, r"d1.*missing=\['urban'\].*extra=\[\]"),
        (
            {"gender": "male", "urban": "urban", "education": "higher"},
            r"d1.*missing=\[\].*extra=\['education'\]",
        ),
    ],
)
def test_population_rejects_nonisomorphic_donor_field_schema(broken_fields, match) -> None:
    donor_values = list(donors())
    donor_values[1] = {"donor_id": "d1", "fields": broken_fields}

    with pytest.raises(ValueError, match=match):
        build_population_artifact(
            donors=tuple(donor_values),
            weights=(5.0, 5.0, 5.0, 5.0),
            n=20,
            matched_seed=17,
            input_artifact_hash=INPUT_HASH,
            constraints={"marginals": {}, "joints": []},
            tolerance=0,
            mock_only=True,
        )


def test_population_artifact_identity_binds_constraint_tolerance() -> None:
    arguments = {
        "donors": donors(),
        "weights": (5.0, 5.0, 5.0, 5.0),
        "n": 20,
        "matched_seed": 17,
        "input_artifact_hash": INPUT_HASH,
        "constraints": {"marginals": {}, "joints": []},
        "mock_only": True,
    }

    exact = build_population_artifact(tolerance=0, **arguments)
    relaxed = build_population_artifact(tolerance=1, **arguments)

    assert exact.payload["members"] == relaxed.payload["members"]
    assert exact.output_hash != relaxed.output_hash
    assert exact.artifact_id != relaxed.artifact_id
    assert exact.input_hashes["constraint_gate"] != relaxed.input_hashes["constraint_gate"]


def test_population_is_reused_without_cell_identity_but_resampled_between_seeds() -> None:
    arguments = {
        "donors": donors(),
        "weights": (5.5, 5.5, 4.5, 4.5),
        "n": 20,
        "input_artifact_hash": INPUT_HASH,
        "constraints": {"marginals": {}, "joints": []},
        "tolerance": 0,
        "mock_only": True,
    }

    seed_a = build_population_artifact(matched_seed=11, **arguments)
    same_seed_for_all_twelve_cells = tuple(
        build_population_artifact(matched_seed=11, **arguments) for _ in range(12)
    )
    seed_b = build_population_artifact(matched_seed=12, **arguments)

    assert all(artifact == seed_a for artifact in same_seed_for_all_twelve_cells)
    assert seed_b.payload["members"] != seed_a.payload["members"]


@pytest.mark.parametrize(
    ("donor_values", "constraints", "tolerance", "match"),
    [
        (
            donors(),
            {"marginals": {"gender": {"female": 10, "nonbinary": 10}}, "joints": []},
            0,
            "structural zero",
        ),
        (
            donors(),
            {"marginals": {"gender": {"female": 9, "male": 9}}, "joints": []},
            0,
            "sum to n",
        ),
        (
            donors(),
            {"marginals": {"gender": {"female": 11, "male": 9}}, "joints": []},
            0,
            "tolerance",
        ),
        (
            (
                {"donor_id": "d0", "fields": {"gender": None, "urban": "urban"}},
                *donors()[1:],
            ),
            {"marginals": {}, "joints": []},
            0,
            r"missing_count=1.*d0.gender",
        ),
    ],
)
def test_population_constraints_fail_closed(donor_values, constraints, tolerance, match) -> None:
    with pytest.raises(ValueError, match=match):
        build_population_artifact(
            donors=donor_values,
            weights=(5.0, 5.0, 5.0, 5.0),
            n=20,
            matched_seed=17,
            input_artifact_hash=INPUT_HASH,
            constraints=constraints,
            tolerance=tolerance,
            mock_only=True,
        )


def test_population_cannot_be_mislabeled_as_formal() -> None:
    with pytest.raises(ValueError, match="mock_only"):
        build_population_artifact(
            donors=donors(),
            weights=(5.0, 5.0, 5.0, 5.0),
            n=20,
            matched_seed=17,
            input_artifact_hash=INPUT_HASH,
            constraints={"marginals": {}, "joints": []},
            tolerance=0,
            mock_only=False,
        )
