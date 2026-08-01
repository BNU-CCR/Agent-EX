from collections import Counter

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import canonical_payload_hash
from agent_ex.initialization import assign_initial_reasons, assign_initial_stances
from agent_ex.population import build_population_artifact


SHA = "2" * 64


def population(n: int, matched_seed: int = 7) -> ArtifactEnvelope:
    donors = tuple(
        {
            "donor_id": f"d{index}",
            "fields": {
                "gender": gender,
                "urban": urban,
                "education": education,
            },
        }
        for index, (gender, urban, education) in enumerate(
            (
                ("female", "urban", "higher"),
                ("female", "rural", "other"),
                ("male", "urban", "other"),
                ("male", "rural", "higher"),
            )
        )
    )
    return build_population_artifact(
        donors=donors,
        weights=(n / 4,) * 4,
        n=n,
        matched_seed=matched_seed,
        input_artifact_hash=SHA,
        constraints={"marginals": {}, "joints": []},
        tolerance=0,
        mock_only=True,
    )


def reason_library(variants_per_stance: int = 6) -> ArtifactEnvelope:
    entries = tuple(
        {
            "reason_id": f"reason-{stance}-{variant}",
            "stance": stance,
            "text": f"第{stance}档的测试理由变体{variant}。",
            "argument_family": f"mock-family-{variant}",
        }
        for stance in range(1, 8)
        for variant in range(variants_per_stance)
    )
    payload = {
        "schema_version": "paper1.mock-reason-library.v1",
        "entries": entries,
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_reason_library",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (20, [1, 2, 4, 6, 4, 2, 1]),
        (100, [5, 10, 20, 30, 20, 10, 5]),
        (1000, [50, 100, 200, 300, 200, 100, 50]),
    ],
)
def test_initial_stance_fixtures_use_approved_proportions(n, expected) -> None:
    artifact = assign_initial_stances(
        population_artifact=population(n),
        matched_seed=7,
        orthogonal_fields=("gender", "urban", "education"),
        max_category_imbalance=1.0,
        mock_only=True,
    )

    counts = Counter(record["stance"] for record in artifact.payload["assignments"])
    assert [counts[stance] for stance in range(1, 8)] == expected
    assert artifact.payload["metadata"]["mock_only"] is True
    assert artifact.payload["distribution_rule"] == (
        "approved_exact_n1000" if n == 1000 else "mock_largest_remainder_scaled"
    )
    assert artifact.rng_provenance[0].namespace == "initial_stance"
    assert "cell_id" not in artifact.rng_provenance[0].coordinates


def test_initial_stance_is_constrained_orthogonal_to_population_fields() -> None:
    artifact = assign_initial_stances(
        population_artifact=population(1000, matched_seed=91),
        matched_seed=91,
        orthogonal_fields=("gender", "urban", "education"),
        max_category_imbalance=1.0,
        mock_only=True,
    )

    diagnostics = artifact.payload["orthogonality_diagnostics"]
    assert diagnostics["maximum_absolute_count_error"] <= 1.0
    assert diagnostics["fields"] == ("gender", "urban", "education")


def test_initial_stance_fails_when_orthogonality_is_impossible() -> None:
    with pytest.raises(ValueError, match="orthogonality"):
        assign_initial_stances(
            population_artifact=population(20),
            matched_seed=7,
            orthogonal_fields=("gender",),
            max_category_imbalance=0.0,
            mock_only=True,
        )


def test_small_fixture_cannot_be_presented_as_formal_initialization() -> None:
    with pytest.raises(ValueError, match="mock_only"):
        assign_initial_stances(
            population_artifact=population(20),
            matched_seed=7,
            orthogonal_fields=("gender",),
            max_category_imbalance=1.0,
            mock_only=False,
        )


def test_round0_artifact_contains_private_state_reason_and_public_post() -> None:
    stances = assign_initial_stances(
        population_artifact=population(20),
        matched_seed=7,
        orthogonal_fields=("gender", "urban", "education"),
        max_category_imbalance=1.0,
        mock_only=True,
    )
    artifact = assign_initial_reasons(
        stance_artifact=stances,
        reason_library_artifact=reason_library(),
        matched_seed=7,
        mock_only=True,
    )

    assert len(artifact.payload["round0_records"]) == 20
    for record in artifact.payload["round0_records"]:
        assert record["round_index"] == 0
        assert record["private_state"] == {
            "stance": record["public_post"]["stance"],
            "reason": record["public_post"]["public_reason"],
        }
        assert record["public_post"]["published"] is True
        assert "confidence" not in record["private_state"]
    assert artifact.rng_provenance[0].namespace == "initial_reason"
    assert artifact.input_hashes == {
        "reason_library": reason_library().output_hash,
        "stance_assignment": stances.output_hash,
    }
    reason_ids = [record["reason_id"] for record in artifact.payload["round0_records"]]
    reason_texts = [
        record["private_state"]["reason"] for record in artifact.payload["round0_records"]
    ]
    assert len(reason_ids) == len(set(reason_ids))
    assert len(reason_texts) == len(set(reason_texts))


def test_round0_reasons_are_shuffled_without_replacement_within_stance() -> None:
    stances = assign_initial_stances(
        population_artifact=population(20),
        matched_seed=7,
        orthogonal_fields=("gender", "urban", "education"),
        max_category_imbalance=1.0,
        mock_only=True,
    )

    first = assign_initial_reasons(
        stance_artifact=stances,
        reason_library_artifact=reason_library(),
        matched_seed=7,
        mock_only=True,
    )
    repeated = assign_initial_reasons(
        stance_artifact=stances,
        reason_library_artifact=reason_library(),
        matched_seed=7,
        mock_only=True,
    )

    assert first == repeated
    for stance in range(1, 8):
        records = [
            record
            for record in first.payload["round0_records"]
            if record["private_state"]["stance"] == stance
        ]
        assert len({record["reason_id"] for record in records}) == len(records)


def test_round0_reasons_fail_closed_when_a_stance_pool_is_too_small() -> None:
    stances = assign_initial_stances(
        population_artifact=population(20),
        matched_seed=7,
        orthogonal_fields=("gender", "urban", "education"),
        max_category_imbalance=1.0,
        mock_only=True,
    )

    with pytest.raises(ValueError, match="stance 4.*requires 6.*contains 5"):
        assign_initial_reasons(
            stance_artifact=stances,
            reason_library_artifact=reason_library(variants_per_stance=5),
            matched_seed=7,
            mock_only=True,
        )


def test_round0_assignment_is_reused_across_cells_and_changes_between_seeds() -> None:
    library = reason_library()

    def build(seed: int) -> ArtifactEnvelope:
        stance = assign_initial_stances(
            population_artifact=population(20, matched_seed=seed),
            matched_seed=seed,
            orthogonal_fields=("gender", "urban", "education"),
            max_category_imbalance=1.0,
            mock_only=True,
        )
        return assign_initial_reasons(
            stance_artifact=stance,
            reason_library_artifact=library,
            matched_seed=seed,
            mock_only=True,
        )

    seed_a = build(31)
    across_cells = tuple(build(31) for _ in range(12))
    seed_b = build(32)

    assert all(value == seed_a for value in across_cells)
    assert seed_b.output_hash != seed_a.output_hash


def test_reason_library_fails_closed_when_a_stance_has_no_reason() -> None:
    library = reason_library()
    broken_payload = library.to_payload()
    broken_payload["payload"]["entries"] = [
        entry for entry in broken_payload["payload"]["entries"] if entry["stance"] != 7
    ]
    broken = ArtifactEnvelope.create(
        artifact_type="paper1.mock_reason_library",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=broken_payload["payload"],
        rng_provenance=(),
    )
    stances = assign_initial_stances(
        population_artifact=population(20),
        matched_seed=7,
        orthogonal_fields=("gender",),
        max_category_imbalance=1.0,
        mock_only=True,
    )

    with pytest.raises(ValueError, match="stance 7"):
        assign_initial_reasons(
            stance_artifact=stances,
            reason_library_artifact=broken,
            matched_seed=7,
            mock_only=True,
        )


def test_initialization_hash_binds_population_and_reason_library() -> None:
    stance = assign_initial_stances(
        population_artifact=population(20),
        matched_seed=7,
        orthogonal_fields=("gender",),
        max_category_imbalance=1.0,
        mock_only=True,
    )
    initialized = assign_initial_reasons(
        stance_artifact=stance,
        reason_library_artifact=reason_library(),
        matched_seed=7,
        mock_only=True,
    )

    assert initialized.output_hash == canonical_payload_hash(initialized.payload)
