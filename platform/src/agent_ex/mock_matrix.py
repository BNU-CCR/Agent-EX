"""Explicit mock-only scale contracts for Phase 4B integration gates."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import Mapping

from .artifacts import ArtifactEnvelope


_SCALE_SCHEMA_VERSION = "paper1.mock-scale-cases.v2"
_SCALE_ARTIFACT_TYPE = "paper1.mock_scale_cases"
_SCALE_ALGORITHM_ID = "paper1.mock_fixture"
_SCALE_METADATA = {
    "mock_only": True,
    "research_parameter_status": "not_frozen",
    "formal_parameter_authority": False,
}


def _strict_positive_integer(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive strict integer")
    return value


def _validate_utc_timestamp(value: object) -> str:
    if type(value) is not str or not value:
        raise TypeError("mock clock start must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("mock clock start must be a parseable UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("mock clock start must include an explicit UTC offset")
    return value


def _validate_cell_id(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise TypeError("mock stress cell ID must be text or null")
    pieces = value.split("-")
    if (
        len(pieces) != 4
        or pieces[0] != "P1"
        or pieces[1] not in {"I0", "I1"}
        or pieces[2] not in {"C0", "C1"}
        or pieces[3] not in {"E0", "E1", "E2"}
    ):
        raise ValueError("mock stress cell ID must be a canonical Paper 1 cell")
    return value


@dataclass(frozen=True, slots=True)
class MockScaleCase:
    """One fully explicit mock-only integration scale; never a formal default."""

    case_id: str
    population_size: int
    stance_counts: tuple[int, ...]
    integration_sweeps: int
    recovery_sweeps: int
    shape_sweeps: int
    full_matrix_execution: bool
    release_execution: bool
    stress_cell_id: str | None
    mock_feed_capacity: int
    mock_memory_window: int
    mock_clock_start: str
    mock_clock_step_seconds: int

    def __post_init__(self) -> None:
        if type(self.case_id) is not str or not self.case_id:
            raise ValueError("mock scale case_id must be non-empty text")
        for name in (
            "population_size",
            "integration_sweeps",
            "recovery_sweeps",
            "shape_sweeps",
            "mock_feed_capacity",
            "mock_memory_window",
            "mock_clock_step_seconds",
        ):
            _strict_positive_integer(name, getattr(self, name))
        if (
            type(self.stance_counts) is not tuple
            or len(self.stance_counts) != 7
            or any(type(value) is not int or value < 0 for value in self.stance_counts)
            or sum(self.stance_counts) != self.population_size
        ):
            raise ValueError("mock stance counts must be seven strict counts summing to population")
        if type(self.full_matrix_execution) is not bool:
            raise TypeError("full matrix execution flag must be boolean")
        if type(self.release_execution) is not bool:
            raise TypeError("release execution flag must be boolean")
        _validate_cell_id(self.stress_cell_id)
        _validate_utc_timestamp(self.mock_clock_start)

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> MockScaleCase:
        expected = {field.name for field in fields(cls)}
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("mock scale case fields do not match v2")
        stance_counts = payload["stance_counts"]
        if type(stance_counts) is not list:
            raise TypeError("mock stance counts must be a JSON array")
        return cls(
            **{
                **payload,
                "stance_counts": tuple(stance_counts),
            }
        )  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        payload = {field.name: getattr(self, field.name) for field in fields(self)}
        payload["stance_counts"] = list(self.stance_counts)
        return payload


def load_mock_scale_cases(artifact: ArtifactEnvelope) -> tuple[MockScaleCase, ...]:
    """Load the exact checked mock scale artifact without supplying defaults."""

    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("mock scale cases require an ArtifactEnvelope")
    if artifact.artifact_type != _SCALE_ARTIFACT_TYPE:
        raise ValueError("scale cases must use the paper1 mock scale artifact type")
    if artifact.algorithm_id != _SCALE_ALGORITHM_ID:
        raise ValueError("scale cases must use the checked mock fixture algorithm")
    payload = artifact.payload
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version",
        "cases",
        "metadata",
    }:
        raise ValueError("scale case artifact must contain the exact v2 fields")
    if payload["schema_version"] != _SCALE_SCHEMA_VERSION:
        raise ValueError("scale case artifact must use schema v2")
    metadata = payload["metadata"]
    if (
        not isinstance(metadata, Mapping)
        or set(metadata) != set(_SCALE_METADATA)
        or metadata["mock_only"] is not True
        or type(metadata["research_parameter_status"]) is not str
        or metadata["research_parameter_status"] != "not_frozen"
        or metadata["formal_parameter_authority"] is not False
    ):
        raise ValueError("scale cases must remain mock-only, not frozen, and non-authoritative")
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, tuple):
        raise TypeError("scale case artifact cases must be a frozen JSON array")
    case_payloads: list[dict[str, object]] = []
    for item in raw_cases:
        if not isinstance(item, Mapping):
            raise TypeError("scale case artifact cases must contain JSON objects")
        case_payload = dict(item)
        frozen_counts = case_payload.get("stance_counts")
        if not isinstance(frozen_counts, tuple):
            raise TypeError("frozen mock stance counts must be a tuple")
        case_payload["stance_counts"] = list(frozen_counts)
        case_payloads.append(case_payload)
    cases = tuple(MockScaleCase.from_payload(item) for item in case_payloads)
    if len(cases) != 3 or len({case.case_id for case in cases}) != 3:
        raise ValueError("scale cases must have three unique case IDs")
    if {case.population_size for case in cases} != {20, 100, 1000}:
        raise ValueError("scale cases must exactly cover N=20/100/1000")
    return cases
