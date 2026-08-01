"""Deterministic mock TRS population artifacts for Phase 4B-3."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Mapping, Sequence

from .artifacts import ArtifactEnvelope
from .domain import _freeze, _require_int, _require_sha256, canonical_payload_hash
from .rng import RNGProvenance


@dataclass(frozen=True, slots=True)
class TRSIntegerization:
    """Exact-size TRS output and source-level replication audit."""

    records: tuple[Mapping[str, object], ...]
    source_counts: Mapping[str, int]
    residual_draw_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(_freeze(record) for record in self.records))
        object.__setattr__(self, "source_counts", _freeze(self.source_counts))


def _validate_donors(donors: Sequence[Mapping[str, object]]) -> tuple[Mapping[str, object], ...]:
    if not isinstance(donors, (tuple, list)) or not donors:
        raise ValueError("donors must be a non-empty sequence")
    validated: list[Mapping[str, object]] = []
    donor_ids: set[str] = set()
    expected_field_names: set[str] | None = None
    for donor in donors:
        if not isinstance(donor, Mapping) or set(donor) != {"donor_id", "fields"}:
            raise ValueError("each donor must contain exactly donor_id and fields")
        donor_id = donor["donor_id"]
        fields = donor["fields"]
        if not isinstance(donor_id, str) or not donor_id.strip():
            raise ValueError("donor_id must be a non-empty string")
        if donor_id in donor_ids:
            raise ValueError("donor_id values must be unique")
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError("donor fields must be a non-empty mapping")
        field_names = set(fields)
        if expected_field_names is None:
            expected_field_names = field_names
        elif field_names != expected_field_names:
            missing = sorted(expected_field_names - field_names)
            extra = sorted(field_names - expected_field_names)
            raise ValueError(
                f"donor {donor_id} field schema mismatch: missing={missing}, extra={extra}"
            )
        missing_fields = sorted(
            field
            for field, value in fields.items()
            if value is None or (isinstance(value, str) and not value.strip())
        )
        if missing_fields:
            locations = ", ".join(f"{donor_id}.{field}" for field in missing_fields)
            raise ValueError(
                f"donor fields contain missing values: missing_count={len(missing_fields)}; "
                f"locations={locations}"
            )
        donor_ids.add(donor_id)
        validated.append(_freeze(donor))
    return tuple(validated)


def trs_integerize(
    donors: Sequence[Mapping[str, object]],
    weights: Sequence[float],
    n: int,
    rng_seed: int,
) -> TRSIntegerization:
    """Truncate, replicate, then sample fractional residuals to exactly ``n``."""

    donor_values = _validate_donors(donors)
    _require_int("n", n, minimum=1)
    _require_int("rng_seed", rng_seed)
    if not isinstance(weights, (tuple, list)) or len(weights) != len(donor_values):
        raise ValueError("weights must have one value per donor")
    clean_weights: list[float] = []
    for weight in weights:
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError("weights must contain finite numbers")
        numeric = float(weight)
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError("weights must be finite and non-negative")
        clean_weights.append(numeric)
    if not math.isclose(sum(clean_weights), n, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("TRS weights must already be scaled to sum exactly to n")

    integer_parts = [math.floor(weight) for weight in clean_weights]
    residual_count = n - sum(integer_parts)
    fractions = [
        weight - integer for weight, integer in zip(clean_weights, integer_parts, strict=True)
    ]
    eligible = [index for index, fraction in enumerate(fractions) if fraction > 1e-12]
    if residual_count < 0 or residual_count > len(eligible):
        raise ValueError("fractional TRS residual is not realizable")

    selected: list[int] = []
    available = eligible.copy()
    rng = random.Random(rng_seed)
    for _ in range(residual_count):
        total = sum(fractions[index] for index in available)
        if total <= 0:
            raise ValueError("fractional TRS residual is not realizable")
        draw = rng.random() * total
        cumulative = 0.0
        chosen = available[-1]
        for index in available:
            cumulative += fractions[index]
            if draw < cumulative:
                chosen = index
                break
        selected.append(chosen)
        available.remove(chosen)

    records: list[Mapping[str, object]] = []
    source_counts: dict[str, int] = {}
    for donor, count in zip(donor_values, integer_parts, strict=True):
        donor_id = donor["donor_id"]
        assert isinstance(donor_id, str)
        source_counts[donor_id] = count
        records.extend(donor for _ in range(count))
    for index in selected:
        donor = donor_values[index]
        donor_id = donor["donor_id"]
        assert isinstance(donor_id, str)
        source_counts[donor_id] += 1
        records.append(donor)
    if len(records) != n:
        raise ValueError("TRS did not produce exactly n records")
    return TRSIntegerization(
        records=tuple(records),
        source_counts=source_counts,
        residual_draw_count=residual_count,
    )


def _validate_constraints(
    constraints: Mapping[str, object], donors: tuple[Mapping[str, object], ...], n: int
) -> tuple[Mapping[str, Mapping[str, int]], tuple[Mapping[str, object], ...]]:
    if not isinstance(constraints, Mapping) or set(constraints) != {"marginals", "joints"}:
        raise ValueError("constraints must contain exactly marginals and joints")
    marginals = constraints["marginals"]
    joints = constraints["joints"]
    if not isinstance(marginals, Mapping) or not isinstance(joints, (tuple, list)):
        raise TypeError("constraint marginals/joints have invalid containers")
    donor_fields = [donor["fields"] for donor in donors]
    normalized_marginals: dict[str, Mapping[str, int]] = {}
    for field, targets in marginals.items():
        if not isinstance(field, str) or not isinstance(targets, Mapping):
            raise TypeError("marginal constraints must map field names to target mappings")
        if sum(targets.values()) != n:
            raise ValueError("each marginal target must sum to n")
        normalized: dict[str, int] = {}
        observed = {fields.get(field) for fields in donor_fields if isinstance(fields, Mapping)}
        for category, target in targets.items():
            _require_int(f"marginal target {field}/{category}", target)
            if category not in observed and target > 0:
                raise ValueError(f"structural zero for {field}={category}")
            normalized[str(category)] = target
        normalized_marginals[field] = normalized

    normalized_joints: list[Mapping[str, object]] = []
    for joint in joints:
        if not isinstance(joint, Mapping) or set(joint) != {"fields", "targets"}:
            raise ValueError("joint constraints require fields and targets")
        fields = joint["fields"]
        targets = joint["targets"]
        if not isinstance(fields, (tuple, list)) or not fields or not isinstance(targets, Mapping):
            raise TypeError("joint constraint fields/targets have invalid containers")
        if sum(targets.values()) != n:
            raise ValueError("each joint target must sum to n")
        observed_keys = {
            "|".join(str(donor_fields[index].get(field)) for field in fields)
            for index in range(len(donor_fields))
        }
        normalized_targets: dict[str, int] = {}
        for category, target in targets.items():
            _require_int(f"joint target {category}", target)
            if category not in observed_keys and target > 0:
                raise ValueError(f"structural zero for joint category {category}")
            normalized_targets[str(category)] = target
        normalized_joints.append({"fields": tuple(fields), "targets": normalized_targets})
    return normalized_marginals, tuple(normalized_joints)


def build_population_artifact(
    *,
    donors: Sequence[Mapping[str, object]],
    weights: Sequence[float],
    n: int,
    matched_seed: int,
    input_artifact_hash: str,
    constraints: Mapping[str, object],
    tolerance: int,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Build an audited common-scope mock population artifact."""

    if mock_only is not True:
        raise ValueError("Phase 4B-3 population artifacts must be mock_only")
    _require_sha256("input_artifact_hash", input_artifact_hash)
    _require_int("tolerance", tolerance, minimum=0)
    donor_values = _validate_donors(donors)
    marginals, joints = _validate_constraints(constraints, donor_values, n)
    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="population",
        coordinates={
            "artifact_kind": "mock_population_trs",
            "input_artifact_hash": input_artifact_hash,
            "population_size": n,
        },
    )
    integerized = trs_integerize(donor_values, weights, n, provenance.derived_seed)
    members = tuple(
        {
            "agent_id": f"agent-{index:04d}",
            "donor_id": record["donor_id"],
            "fields": record["fields"],
        }
        for index, record in enumerate(integerized.records)
    )

    target_marginals = {
        field: dict(sorted(targets.items())) for field, targets in sorted(marginals.items())
    }
    target_joints = {
        "+".join(joint["fields"]): dict(sorted(joint["targets"].items()))  # type: ignore[union-attr]
        for joint in joints
    }
    weighted_marginals: dict[str, dict[str, float]] = {}
    integerized_marginals: dict[str, dict[str, int]] = {}
    for field, targets in marginals.items():
        weighted_marginals[field] = {
            category: sum(
                float(weight)
                for donor, weight in zip(donor_values, weights, strict=True)
                if donor["fields"][field] == category  # type: ignore[index]
            )
            for category in targets
        }
        integerized_marginals[field] = {
            category: sum(member["fields"][field] == category for member in members)  # type: ignore[index]
            for category in targets
        }
    weighted_joints: dict[str, dict[str, float]] = {}
    integerized_joints: dict[str, dict[str, int]] = {}
    for joint in joints:
        fields = joint["fields"]
        targets = joint["targets"]
        assert isinstance(fields, tuple) and isinstance(targets, Mapping)
        label = "+".join(fields)
        weighted_joints[label] = {
            category: sum(
                float(weight)
                for donor, weight in zip(donor_values, weights, strict=True)
                if "|".join(str(donor["fields"][field]) for field in fields) == category  # type: ignore[index]
            )
            for category in targets
        }
        integerized_joints[label] = {
            category: sum(
                "|".join(str(member["fields"][field]) for field in fields) == category  # type: ignore[index]
                for member in members
            )
            for category in targets
        }

    def differences(
        left: Mapping[str, Mapping[str, int | float]],
        right: Mapping[str, Mapping[str, int | float]],
    ) -> dict[str, dict[str, int | float]]:
        return {
            field: {
                category: left[field][category] - right[field][category] for category in left[field]
            }
            for field in left
        }

    marginal_errors: dict[str, dict[str, int]] = {}
    for field, targets in marginals.items():
        errors: dict[str, int] = {}
        for category, target in targets.items():
            observed = sum(member["fields"][field] == category for member in members)  # type: ignore[index]
            errors[category] = observed - target
        marginal_errors[field] = dict(sorted(errors.items()))
    joint_errors: dict[str, dict[str, int]] = {}
    for joint in joints:
        fields = joint["fields"]
        targets = joint["targets"]
        assert isinstance(fields, tuple) and isinstance(targets, Mapping)
        errors = {}
        for category, target in targets.items():
            observed = sum(
                "|".join(str(member["fields"][field]) for field in fields) == category  # type: ignore[index]
                for member in members
            )
            errors[category] = observed - target
        joint_errors["+".join(fields)] = dict(sorted(errors.items()))
    all_errors = [
        abs(error)
        for report in (*marginal_errors.values(), *joint_errors.values())
        for error in report.values()
    ]
    if all_errors and max(all_errors) > tolerance:
        raise ValueError("population constraint error exceeds tolerance")

    payload = {
        "schema_version": "paper1.mock-population.v1",
        "matched_seed": matched_seed,
        "population_size": n,
        "members": members,
        "diagnostics": {
            "clone_count": n - len({member["donor_id"] for member in members}),
            "missing_count": sum(
                value is None or (isinstance(value, str) and not value.strip())
                for donor in donor_values
                for value in donor["fields"].values()  # type: ignore[union-attr]
            ),
            "structural_zeros": (),
            "source_counts": integerized.source_counts,
            "residual_draw_count": integerized.residual_draw_count,
            "tolerance": tolerance,
            "marginal_errors": dict(sorted(marginal_errors.items())),
            "joint_errors": dict(sorted(joint_errors.items())),
            "balance": {
                "target": {"marginals": target_marginals, "joints": target_joints},
                "weighted_donor": {
                    "marginals": weighted_marginals,
                    "joints": weighted_joints,
                },
                "integerized": {
                    "marginals": integerized_marginals,
                    "joints": integerized_joints,
                },
                "calibration_error": {
                    "marginals": differences(weighted_marginals, target_marginals),
                    "joints": differences(weighted_joints, target_joints),
                },
                "trs_error": {
                    "marginals": differences(integerized_marginals, weighted_marginals),
                    "joints": differences(integerized_joints, weighted_joints),
                },
            },
        },
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_population",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_trs",
        algorithm_version="1.0.0",
        input_hashes={
            "population_frame": input_artifact_hash,
            "constraints": canonical_payload_hash(constraints),
            "constraint_gate": canonical_payload_hash(
                {"constraints": constraints, "tolerance": tolerance}
            ),
        },
        payload=payload,
        rng_provenance=(provenance,),
    )
