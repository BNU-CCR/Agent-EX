"""Mock-only, matched-seed initialization artifacts for Phase 4B-3."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
import random

from .artifacts import ArtifactEnvelope
from .domain import _require_int
from .rng import RNGProvenance


_APPROVED_COUNTS_N1000 = (50, 100, 200, 300, 200, 100, 50)


def _scaled_stance_counts(n: int) -> tuple[int, ...]:
    _require_int("population_size", n, minimum=1)
    if n == 1000:
        return _APPROVED_COUNTS_N1000
    desired = [n * count / 1000 for count in _APPROVED_COUNTS_N1000]
    counts = [math.floor(value) for value in desired]
    remaining = n - sum(counts)
    order = sorted(range(7), key=lambda index: (-(desired[index] - counts[index]), index))
    for index in order[:remaining]:
        counts[index] += 1
    return tuple(counts)


def _require_mock_artifact(artifact: ArtifactEnvelope, artifact_type: str) -> None:
    if not isinstance(artifact, ArtifactEnvelope) or artifact.artifact_type != artifact_type:
        raise TypeError(f"expected {artifact_type} ArtifactEnvelope")
    if artifact.payload["metadata"]["mock_only"] is not True:  # type: ignore[index]
        raise ValueError("Phase 4B-3 inputs must be explicitly mock_only")


def _rounded_stratum_allocations(
    sizes: tuple[int, ...], counts: tuple[int, ...], rng: random.Random
) -> tuple[tuple[int, ...], ...]:
    n = sum(sizes)
    desired = [[size * count / n for count in counts] for size in sizes]
    allocations = [[math.floor(value) for value in row] for row in desired]
    row_remaining = [size - sum(row) for size, row in zip(sizes, allocations, strict=True)]
    column_remaining = [
        count - sum(allocations[row][column] for row in range(len(sizes)))
        for column, count in enumerate(counts)
    ]
    tie_breaks = {
        (row, column): rng.random() for row in range(len(sizes)) for column in range(len(counts))
    }
    while sum(row_remaining):
        candidates = [
            (row, column)
            for row in range(len(sizes))
            for column in range(len(counts))
            if row_remaining[row] > 0 and column_remaining[column] > 0
        ]
        if not candidates:
            raise ValueError("initial stance orthogonality allocation is not realizable")
        row, column = max(
            candidates,
            key=lambda cell: (
                desired[cell[0]][cell[1]] - allocations[cell[0]][cell[1]],
                tie_breaks[cell],
            ),
        )
        allocations[row][column] += 1
        row_remaining[row] -= 1
        column_remaining[column] -= 1
    if any(column_remaining):
        raise ValueError("initial stance orthogonality allocation is not realizable")
    return tuple(tuple(row) for row in allocations)


def assign_initial_stances(
    *,
    population_artifact: ArtifactEnvelope,
    matched_seed: int,
    orthogonal_fields: tuple[str, ...],
    max_category_imbalance: float,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Assign the approved stance proportions within joint population strata."""

    if mock_only is not True:
        raise ValueError("Phase 4B-3 initialization artifacts must be mock_only")
    _require_mock_artifact(population_artifact, "paper1.mock_population")
    if population_artifact.payload["matched_seed"] != matched_seed:  # type: ignore[index]
        raise ValueError("matched_seed must match the population artifact")
    if (
        not isinstance(orthogonal_fields, tuple)
        or not orthogonal_fields
        or any(not isinstance(field, str) or not field for field in orthogonal_fields)
    ):
        raise ValueError("orthogonal_fields must be a non-empty tuple of field names")
    if isinstance(max_category_imbalance, bool) or not isinstance(
        max_category_imbalance, (int, float)
    ):
        raise TypeError("max_category_imbalance must be numeric")
    if not math.isfinite(max_category_imbalance) or max_category_imbalance < 0:
        raise ValueError("max_category_imbalance must be finite and non-negative")

    members = population_artifact.payload["members"]  # type: ignore[index]
    n = len(members)  # type: ignore[arg-type]
    counts = _scaled_stance_counts(n)
    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="initial_stance",
        coordinates={
            "artifact_kind": "mock_initial_stance_assignment",
            "population_artifact_id": population_artifact.artifact_id,
        },
    )
    rng = random.Random(provenance.derived_seed)
    strata: dict[tuple[object, ...], list[object]] = defaultdict(list)
    for member in members:  # type: ignore[union-attr]
        fields = member["fields"]
        try:
            key = tuple(fields[field] for field in orthogonal_fields)
        except KeyError as error:
            raise ValueError(f"orthogonality field is missing: {error.args[0]}") from error
        strata[key].append(member)
    ordered_keys = tuple(sorted(strata, key=lambda key: tuple(str(value) for value in key)))
    allocations = _rounded_stratum_allocations(
        tuple(len(strata[key]) for key in ordered_keys), counts, rng
    )
    assignments: list[dict[str, object]] = []
    for key, allocation in zip(ordered_keys, allocations, strict=True):
        stratum_members = list(strata[key])
        rng.shuffle(stratum_members)
        stances = [stance for stance, count in enumerate(allocation, start=1) for _ in range(count)]
        for member, stance in zip(stratum_members, stances, strict=True):
            assignments.append({"agent_id": member["agent_id"], "stance": stance})  # type: ignore[index]
    assignments.sort(key=lambda record: record["agent_id"])  # type: ignore[arg-type]

    maximum_error = 0.0
    field_reports: dict[str, dict[str, dict[str, float]]] = {}
    for field in orthogonal_fields:
        categories = sorted({str(member["fields"][field]) for member in members})  # type: ignore[index,union-attr]
        category_report: dict[str, dict[str, float]] = {}
        for category in categories:
            category_agent_ids = {
                member["agent_id"]
                for member in members  # type: ignore[union-attr]
                if str(member["fields"][field]) == category  # type: ignore[index]
            }
            observed = Counter(
                assignment["stance"]
                for assignment in assignments
                if assignment["agent_id"] in category_agent_ids
            )
            errors = {
                str(stance): observed[stance] - len(category_agent_ids) * counts[stance - 1] / n
                for stance in range(1, 8)
            }
            maximum_error = max(maximum_error, *(abs(value) for value in errors.values()))
            category_report[category] = errors
        field_reports[field] = category_report
    if maximum_error > max_category_imbalance + 1e-12:
        raise ValueError("initial stance orthogonality exceeds the supplied mock tolerance")

    payload = {
        "schema_version": "paper1.mock-initial-stance.v1",
        "matched_seed": matched_seed,
        "population_artifact_id": population_artifact.artifact_id,
        "population_size": n,
        "stance_counts": {str(stance): counts[stance - 1] for stance in range(1, 8)},
        "distribution_rule": (
            "approved_exact_n1000" if n == 1000 else "mock_largest_remainder_scaled"
        ),
        "assignments": tuple(assignments),
        "orthogonality_diagnostics": {
            "fields": orthogonal_fields,
            "maximum_absolute_count_error": maximum_error,
            "category_errors": field_reports,
        },
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_initial_stance",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_joint_stratum_rounding",
        algorithm_version="1.0.0",
        input_hashes={"population": population_artifact.output_hash},
        payload=payload,
        rng_provenance=(provenance,),
    )


def assign_initial_reasons(
    *,
    stance_artifact: ArtifactEnvelope,
    reason_library_artifact: ArtifactEnvelope,
    matched_seed: int,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Assign frozen mock reasons and emit matched private/public round-0 records."""

    if mock_only is not True:
        raise ValueError("Phase 4B-3 initialization artifacts must be mock_only")
    _require_mock_artifact(stance_artifact, "paper1.mock_initial_stance")
    _require_mock_artifact(reason_library_artifact, "paper1.mock_reason_library")
    if stance_artifact.payload["matched_seed"] != matched_seed:  # type: ignore[index]
        raise ValueError("matched_seed must match the stance artifact")
    entries = reason_library_artifact.payload["entries"]  # type: ignore[index]
    by_stance: dict[int, list[object]] = defaultdict(list)
    seen_reason_ids: set[str] = set()
    seen_reason_texts: set[str] = set()
    for entry in entries:  # type: ignore[union-attr]
        if set(entry) != {"reason_id", "stance", "text", "argument_family"}:  # type: ignore[arg-type]
            raise ValueError("reason library entry fields do not match the mock contract")
        stance = entry["stance"]  # type: ignore[index]
        _require_int("reason stance", stance, minimum=1)
        if stance > 7:
            raise ValueError("reason stance must be between 1 and 7")
        reason_id = entry["reason_id"]  # type: ignore[index]
        text = entry["text"]  # type: ignore[index]
        if not isinstance(reason_id, str) or not reason_id or reason_id in seen_reason_ids:
            raise ValueError("reason IDs must be non-empty and unique")
        if not isinstance(text, str) or not text.strip() or text in seen_reason_texts:
            raise ValueError("reason texts must be non-empty and unique")
        seen_reason_ids.add(reason_id)
        seen_reason_texts.add(text)
        by_stance[stance].append(entry)
    for stance in range(1, 8):
        if not by_stance[stance]:
            raise ValueError(f"reason library has no entry for stance {stance}")

    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="initial_reason",
        coordinates={
            "artifact_kind": "mock_round0_reason_assignment",
            "stance_artifact_id": stance_artifact.artifact_id,
            "reason_library_artifact_id": reason_library_artifact.artifact_id,
        },
    )
    rng = random.Random(provenance.derived_seed)
    assignment_counts = Counter(
        assignment["stance"]
        for assignment in stance_artifact.payload["assignments"]  # type: ignore[index,union-attr]
    )
    shuffled_pools: dict[int, list[object]] = {}
    for stance in range(1, 8):
        required = assignment_counts[stance]
        available = len(by_stance[stance])
        if available < required:
            raise ValueError(
                f"reason library stance {stance} requires {required} unique entries "
                f"but contains {available}"
            )
        pool = list(by_stance[stance])
        rng.shuffle(pool)
        shuffled_pools[stance] = pool
    next_index = Counter()
    records = []
    for assignment in stance_artifact.payload["assignments"]:  # type: ignore[index,union-attr]
        stance = assignment["stance"]
        entry = shuffled_pools[stance][next_index[stance]]  # type: ignore[index]
        next_index[stance] += 1
        reason = entry["text"]  # type: ignore[index]
        records.append(
            {
                "agent_id": assignment["agent_id"],
                "round_index": 0,
                "reason_id": entry["reason_id"],  # type: ignore[index]
                "private_state": {"stance": stance, "reason": reason},
                "public_post": {
                    "stance": stance,
                    "public_reason": reason,
                    "published": True,
                },
            }
        )
    payload = {
        "schema_version": "paper1.mock-round0-initialization.v1",
        "matched_seed": matched_seed,
        "stance_artifact_id": stance_artifact.artifact_id,
        "reason_library_artifact_id": reason_library_artifact.artifact_id,
        "round0_records": tuple(records),
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_round0_initialization",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_round0_reason_assignment",
        algorithm_version="1.0.0",
        input_hashes={
            "reason_library": reason_library_artifact.output_hash,
            "stance_assignment": stance_artifact.output_hash,
        },
        payload=payload,
        rng_provenance=(provenance,),
    )
