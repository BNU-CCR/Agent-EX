"""Explicit mock-only scale contracts for Phase 4B integration gates."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from typing import Mapping

from .artifacts import ArtifactEnvelope
from .domain import FrozenSchedule, RunManifest, _freeze, canonical_payload_hash, derive_event_id
from .execution_evidence import MockAdapterExecutionBinding
from .network import (
    build_agent_node_mapping,
    validate_shadow_artifact,
    validate_structural_gate_artifact,
    validate_ws_artifact,
)
from .persona import render_persona, validate_persona_factor_diff
from .schedule import validate_matched_schedule_reuse
from .topic import TopicPackage


_SCALE_SCHEMA_VERSION = "paper1.mock-scale-cases.v2"
_SCALE_ARTIFACT_TYPE = "paper1.mock_scale_cases"
_SCALE_ALGORITHM_ID = "paper1.mock_fixture"
_SCALE_METADATA = {
    "mock_only": True,
    "research_parameter_status": "not_frozen",
    "formal_parameter_authority": False,
}

CANONICAL_CELL_IDS = tuple(
    f"P1-I{identity}-C{continuity}-E{exposure}"
    for identity in range(2)
    for continuity in range(2)
    for exposure in range(3)
)
_MATRIX_SCHEMA_VERSION = "paper1.mock-matched-seed-matrix.v1"
_EXPOSURE_MODES = {
    "E0": "self_history_only",
    "E1": "shuffled_social",
    "E2": "ws_neighbors",
}
_ARTIFACT_HASH_KEYS = {
    "topic",
    "population",
    "stance",
    "reason",
    "persona_template",
    "ws",
    "shadow",
    "mapping",
    "structural_gate",
    "attention",
    "expression",
    "activation",
    "publish",
    "schedule",
}
_RUN_SPEC_FIELDS = {
    "protocol_id",
    "protocol_version",
    "protocol_hash",
    "schedule_hash",
    "cell_id",
    "run_config",
    "request_parameters",
    "mock_matrix_binding",
}
_RUN_BINDING_FIELDS = {
    "schema_version",
    "scale_case_id",
    "scale_case_hash",
    "cell_id",
    "identity_present",
    "continuity_present",
    "exposure_mode",
    "exposure_graph_hash",
    "artifact_hashes",
    "clock_sequence_id",
    "clock_sequence_hash",
    "adapter_semantics_hash",
}
_RUN_BINDING_SCHEMA_VERSION = "paper1.mock-cell-run-binding.v1"


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


def _cell_factors(cell_id: str) -> tuple[bool, bool, str]:
    _validate_cell_id(cell_id)
    pieces = cell_id.split("-")
    return pieces[1] == "I1", pieces[2] == "C1", _EXPOSURE_MODES[pieces[3]]


def _require_hash(name: str, value: object) -> str:
    if type(value) is not str or len(value) != 64:
        raise ValueError(f"{name} must be a canonical SHA-256")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be a canonical SHA-256") from error
    if value != value.lower():
        raise ValueError(f"{name} must be a canonical SHA-256")
    return value


def mock_clock_sequence_binding(scale_case: MockScaleCase) -> tuple[str, str]:
    """Derive the explicit deterministic clock identity for one mock scale case."""

    if not isinstance(scale_case, MockScaleCase):
        raise TypeError("mock clock binding requires a MockScaleCase")
    payload = {
        "schema_version": "paper1.mock-clock-sequence.v1",
        "mock_clock_start": scale_case.mock_clock_start,
        "mock_clock_step_seconds": scale_case.mock_clock_step_seconds,
    }
    digest = canonical_payload_hash(payload)
    return "mock-clock-" + digest, digest


def mock_adapter_semantics_hash(
    binding: MockAdapterExecutionBinding,
    expected_event_ids: tuple[str, ...],
) -> str:
    """Bind a complete ordered mock script to its runtime and model identity."""

    if not isinstance(binding, MockAdapterExecutionBinding):
        raise TypeError("mock adapter semantics require a typed execution binding")
    if (
        type(expected_event_ids) is not tuple
        or any(type(event_id) is not str or not event_id for event_id in expected_event_ids)
        or len(set(expected_event_ids)) != len(expected_event_ids)
    ):
        raise ValueError("expected mock event IDs must be a unique ordered tuple")
    if set(binding.script_step_hashes) != set(expected_event_ids):
        raise ValueError("mock adapter script must exactly cover the expected event IDs")
    return canonical_payload_hash(
        {
            "expected_adapter_kind": binding.expected_adapter_kind,
            "expected_adapter_version": binding.expected_adapter_version,
            "runtime_identity_hash": binding.runtime_identity_hash,
            "model_identity_hash": binding.model_identity_hash,
            "ordered_script_step_hashes": tuple(
                binding.script_step_hashes[event_id] for event_id in expected_event_ids
            ),
        }
    )


def _expected_run_binding(
    *,
    scale_case: MockScaleCase,
    cell_id: str,
    artifact_hashes: Mapping[str, str],
    exposure_graph_hash: str | None,
    clock_sequence_id: str,
    clock_sequence_hash: str,
    adapter_binding: MockAdapterExecutionBinding,
    expected_event_ids: tuple[str, ...],
) -> dict[str, object]:
    identity, continuity, exposure_mode = _cell_factors(cell_id)
    return {
        "schema_version": _RUN_BINDING_SCHEMA_VERSION,
        "scale_case_id": scale_case.case_id,
        "scale_case_hash": canonical_payload_hash(scale_case.to_payload()),
        "cell_id": cell_id,
        "identity_present": identity,
        "continuity_present": continuity,
        "exposure_mode": exposure_mode,
        "exposure_graph_hash": exposure_graph_hash,
        "artifact_hashes": dict(artifact_hashes),
        "clock_sequence_id": clock_sequence_id,
        "clock_sequence_hash": clock_sequence_hash,
        "adapter_semantics_hash": mock_adapter_semantics_hash(adapter_binding, expected_event_ids),
    }


def _validate_manifest_contract(
    *,
    scale_case: MockScaleCase,
    manifest: RunManifest,
    cell_id: str,
    artifact_hashes: Mapping[str, str],
    exposure_graph_hash: str | None,
    clock_sequence_id: str,
    clock_sequence_hash: str,
    adapter_binding: MockAdapterExecutionBinding,
    expected_event_ids: tuple[str, ...],
) -> str:
    run_spec = manifest.run_spec
    if not isinstance(run_spec, Mapping) or set(run_spec) != _RUN_SPEC_FIELDS:
        raise ValueError("mock manifest run spec fields do not match the strict matrix contract")
    if (
        run_spec["protocol_id"] != manifest.protocol_id
        or run_spec["protocol_version"] != manifest.protocol_version
        or run_spec["protocol_hash"] != manifest.protocol_hash
        or run_spec["schedule_hash"] != manifest.schedule_hash
        or run_spec["cell_id"] != cell_id
    ):
        raise ValueError("mock manifest protocol, schedule, or cell binding drifts")
    expected_run_config = {
        "population": manifest.schedule.population_size,
        "sweep_count": manifest.schedule.sweep_count,
        "expected_event_count": manifest.schedule.count,
    }
    run_config = run_spec["run_config"]
    if not isinstance(run_config, Mapping) or canonical_payload_hash(
        run_config
    ) != canonical_payload_hash(expected_run_config):
        raise ValueError("mock manifest run configuration drifts from its schedule")
    request_parameters = run_spec["request_parameters"]
    if not isinstance(request_parameters, Mapping):
        raise TypeError("mock manifest request parameters must be a mapping")
    binding_payload = run_spec["mock_matrix_binding"]
    expected_binding = _expected_run_binding(
        scale_case=scale_case,
        cell_id=cell_id,
        artifact_hashes=artifact_hashes,
        exposure_graph_hash=exposure_graph_hash,
        clock_sequence_id=clock_sequence_id,
        clock_sequence_hash=clock_sequence_hash,
        adapter_binding=adapter_binding,
        expected_event_ids=expected_event_ids,
    )
    if (
        not isinstance(binding_payload, Mapping)
        or set(binding_payload) != _RUN_BINDING_FIELDS
        or canonical_payload_hash(binding_payload) != canonical_payload_hash(expected_binding)
    ):
        raise ValueError(
            "mock manifest cell factor, graph, artifact, clock, or adapter binding drifts"
        )
    return canonical_payload_hash(request_parameters)


@dataclass(frozen=True, slots=True)
class MockCellBinding:
    """One outcome-free cell binding in a canonical matched-seed matrix."""

    cell_id: str
    identity_present: bool
    continuity_present: bool
    exposure_mode: str
    exposure_graph_hash: str | None
    artifact_hashes: Mapping[str, str]
    manifest: RunManifest
    adapter_binding: MockAdapterExecutionBinding
    clock_sequence_id: str
    clock_sequence_hash: str

    def __post_init__(self) -> None:
        if type(self.cell_id) is not str:
            raise TypeError("matrix cell_id must be text")
        if type(self.identity_present) is not bool or type(self.continuity_present) is not bool:
            raise TypeError("matrix persona factors must be booleans")
        if type(self.exposure_mode) is not str:
            raise TypeError("matrix exposure mode must be text")
        if self.exposure_graph_hash is not None:
            _require_hash("exposure graph hash", self.exposure_graph_hash)
        if not isinstance(self.artifact_hashes, Mapping):
            raise TypeError("matrix artifact hashes must be a mapping")
        for name, digest in self.artifact_hashes.items():
            if type(name) is not str:
                raise TypeError("matrix artifact hash names must be text")
            _require_hash(f"artifact hash {name}", digest)
        if not isinstance(self.manifest, RunManifest):
            raise TypeError("matrix manifest must be a RunManifest")
        if not isinstance(self.adapter_binding, MockAdapterExecutionBinding):
            raise TypeError("matrix adapter binding must be typed")
        if type(self.clock_sequence_id) is not str or not self.clock_sequence_id:
            raise ValueError("clock sequence ID must be non-empty text")
        _require_hash("clock sequence hash", self.clock_sequence_hash)
        object.__setattr__(self, "artifact_hashes", _freeze(self.artifact_hashes))

    def _hash_payload(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "identity_present": self.identity_present,
            "continuity_present": self.continuity_present,
            "exposure_mode": self.exposure_mode,
            "exposure_graph_hash": self.exposure_graph_hash,
            "artifact_hashes": self.artifact_hashes,
            "manifest": self.manifest.to_payload(),
            "adapter_binding": self.adapter_binding.to_payload(),
            "clock_sequence_id": self.clock_sequence_id,
            "clock_sequence_hash": self.clock_sequence_hash,
        }


@dataclass(frozen=True, slots=True)
class MockMatchedSeedMatrix:
    """Immutable exact-cover binding for one mock matched seed."""

    schema_version: str
    matched_seed: int
    scale_case: MockScaleCase
    cells: tuple[MockCellBinding, ...]
    matrix_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.schema_version) is not str:
            raise TypeError("matrix schema version must be text")
        if type(self.matched_seed) is not int:
            raise TypeError("matrix matched seed must be a strict integer")
        if not isinstance(self.scale_case, MockScaleCase):
            raise TypeError("matrix scale case must be a MockScaleCase")
        if not isinstance(self.cells, tuple) or not all(
            isinstance(cell, MockCellBinding) for cell in self.cells
        ):
            raise TypeError("matrix cells must be a tuple of MockCellBinding values")
        object.__setattr__(
            self,
            "matrix_hash",
            canonical_payload_hash(
                {
                    "schema_version": self.schema_version,
                    "matched_seed": self.matched_seed,
                    "scale_case": self.scale_case.to_payload(),
                    "cells": tuple(cell._hash_payload() for cell in self.cells),
                }
            ),
        )


def _require_artifact(name: str, artifact: object, artifact_type: str) -> ArtifactEnvelope:
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError(f"{name} must be an ArtifactEnvelope")
    if artifact.artifact_type != artifact_type:
        raise ValueError(f"{name} artifact type does not match the matrix contract")
    if ArtifactEnvelope.from_payload(artifact.to_payload()) != artifact:
        raise ValueError(f"{name} artifact does not round-trip exactly")
    payload = artifact.payload
    metadata = payload.get("metadata") if isinstance(payload, Mapping) else None
    if (
        not isinstance(metadata, Mapping)
        or set(metadata) != {"mock_only", "research_parameter_status"}
        or metadata["mock_only"] is not True
        or type(metadata["research_parameter_status"]) is not str
        or metadata["research_parameter_status"] != "not_frozen"
    ):
        raise ValueError(f"{name} artifact must remain mock-only and not frozen")
    return artifact


def _payload_seed(name: str, artifact: ArtifactEnvelope, matched_seed: int) -> None:
    if (
        not isinstance(artifact.payload, Mapping)
        or artifact.payload.get("matched_seed") != matched_seed
    ):
        raise ValueError(f"{name} matched seed does not match the matrix")


def build_mock_matched_seed_matrix(
    *,
    scale_case: MockScaleCase,
    matched_seed: int,
    topic_package: TopicPackage,
    population_artifact: ArtifactEnvelope,
    initial_stance_artifact: ArtifactEnvelope,
    initial_reason_artifact: ArtifactEnvelope,
    persona_template: ArtifactEnvelope,
    ws_artifact: ArtifactEnvelope,
    shadow_artifact: ArtifactEnvelope,
    agent_node_mapping: ArtifactEnvelope,
    structural_gate_artifact: ArtifactEnvelope,
    attention_artifact: ArtifactEnvelope,
    expression_artifact: ArtifactEnvelope,
    activation_artifact: ArtifactEnvelope,
    publish_artifact: ArtifactEnvelope,
    schedules_by_cell: Mapping[str, FrozenSchedule],
    manifests_by_cell: Mapping[str, RunManifest],
    adapter_bindings_by_cell: Mapping[str, MockAdapterExecutionBinding],
) -> MockMatchedSeedMatrix:
    """Build and audit one canonical mock matrix without touching causal storage."""

    if not isinstance(scale_case, MockScaleCase):
        raise TypeError("scale_case must be a MockScaleCase")
    if type(matched_seed) is not int:
        raise TypeError("matched_seed must be a strict integer")
    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be a TopicPackage")
    if TopicPackage.from_payload(topic_package.to_payload()) != topic_package:
        raise ValueError("topic package does not round-trip exactly")
    artifacts = {
        "population": _require_artifact(
            "population", population_artifact, "paper1.mock_population"
        ),
        "stance": _require_artifact(
            "stance", initial_stance_artifact, "paper1.mock_initial_stance"
        ),
        "reason": _require_artifact(
            "reason", initial_reason_artifact, "paper1.mock_round0_initialization"
        ),
        "persona_template": _require_artifact(
            "persona template", persona_template, "paper1.mock_persona_template"
        ),
        "ws": _require_artifact("WS", ws_artifact, "paper1.mock_ws_graph"),
        "shadow": _require_artifact("shadow", shadow_artifact, "paper1.mock_shadow_graph"),
        "mapping": _require_artifact(
            "agent-node mapping", agent_node_mapping, "paper1.mock_agent_node_mapping"
        ),
        "structural_gate": _require_artifact(
            "structural gate",
            structural_gate_artifact,
            "paper1.mock_pure_structure_gate",
        ),
        "attention": _require_artifact("attention", attention_artifact, "paper1.mock_attention"),
        "expression": _require_artifact(
            "expression", expression_artifact, "paper1.mock_expression"
        ),
        "activation": _require_artifact(
            "activation", activation_artifact, "paper1.mock_activation_schedule"
        ),
        "publish": _require_artifact("publish", publish_artifact, "paper1.mock_publish_schedule"),
    }
    for name in (
        "population",
        "stance",
        "reason",
        "ws",
        "shadow",
        "mapping",
        "structural_gate",
        "attention",
        "expression",
        "activation",
        "publish",
    ):
        _payload_seed(name, artifacts[name], matched_seed)
    population_payload = population_artifact.payload
    stance_payload = initial_stance_artifact.payload
    assert isinstance(population_payload, Mapping) and isinstance(stance_payload, Mapping)
    if population_payload.get("population_size") != scale_case.population_size:
        raise ValueError("population size does not match the explicit scale case")
    observed_counts = stance_payload.get("stance_counts")
    if (
        not isinstance(observed_counts, Mapping)
        or tuple(observed_counts.get(str(index)) for index in range(1, 8))
        != scale_case.stance_counts
    ):
        raise ValueError("initial stance counts do not match the explicit scale case")
    if initial_stance_artifact.input_hashes.get("population") != population_artifact.output_hash:
        raise ValueError("stance artifact is not bound to the matrix population")
    if (
        initial_reason_artifact.input_hashes.get("stance_assignment")
        != initial_stance_artifact.output_hash
    ):
        raise ValueError("reason artifact is not bound to the matrix stance assignment")
    reason_payload = initial_reason_artifact.payload
    assert isinstance(reason_payload, Mapping)
    if (
        reason_payload.get("reason_library_artifact_id")
        != topic_package.round0_reason_library_artifact_id
    ):
        raise ValueError("round-zero reasons drift from the topic package reason library")
    expected_mapping_inputs = {
        "network_graph": ws_artifact.output_hash,
        "population": population_artifact.output_hash,
        "round0_initialization": initial_reason_artifact.output_hash,
    }
    if dict(agent_node_mapping.input_hashes) != expected_mapping_inputs:
        raise ValueError("agent-node mapping is not bound to the shared artifact family")
    expected_mapping = build_agent_node_mapping(
        population_artifact=population_artifact,
        round0_initialization_artifact=initial_reason_artifact,
        network_artifact=ws_artifact,
        matched_seed=matched_seed,
        mock_only=True,
    )
    if agent_node_mapping != expected_mapping:
        raise ValueError("agent-node mapping does not match deterministic bijective replay")
    validate_ws_artifact(ws_artifact)
    validate_shadow_artifact(shadow_artifact, ws_artifact)
    validate_structural_gate_artifact(structural_gate_artifact, ws_artifact)
    members = population_payload.get("members")
    if not isinstance(members, tuple) or not members:
        raise ValueError("population must contain typed members")
    rendered = tuple(
        render_persona(
            persona_template,
            members[0],
            {"identity_present": identity, "continuity_present": continuity},
        )
        for identity in (False, True)
        for continuity in (False, True)
    )
    validate_persona_factor_diff(rendered)
    population_agent_ids = tuple(member["agent_id"] for member in members)  # type: ignore[index]
    for name in ("attention", "expression"):
        records = artifacts[name].payload["agents"]  # type: ignore[index]
        if tuple(record["agent_id"] for record in records) != population_agent_ids:  # type: ignore[index,union-attr]
            raise ValueError(f"{name} agent roster drifts from the shared population")
    for name, values in (
        ("schedules", schedules_by_cell),
        ("manifests", manifests_by_cell),
        ("adapter bindings", adapter_bindings_by_cell),
    ):
        if not isinstance(values, Mapping):
            raise TypeError(f"{name} must be a mapping")
    if set(schedules_by_cell) != set(CANONICAL_CELL_IDS):
        raise ValueError("schedules must exactly cover the canonical 12 cells")
    if set(manifests_by_cell) != set(CANONICAL_CELL_IDS):
        raise ValueError("manifests must exactly cover the canonical 12 cells")
    if set(adapter_bindings_by_cell) != set(CANONICAL_CELL_IDS):
        raise ValueError("adapter bindings must exactly cover the canonical 12 cells")
    schedule_hashes = validate_matched_schedule_reuse(
        cell_artifacts={
            cell_id: (
                attention_artifact,
                expression_artifact,
                activation_artifact,
                publish_artifact,
            )
            for cell_id in CANONICAL_CELL_IDS
        },
        expected_matched_seed=matched_seed,
    )
    expected_schedule_hash = schedule_hashes["frozen_schedule"]
    clock_id, clock_hash = mock_clock_sequence_binding(scale_case)
    artifact_hashes = {
        "topic": topic_package.package_hash,
        **{name: artifact.output_hash for name, artifact in artifacts.items()},
        "schedule": expected_schedule_hash,
    }
    cells = []
    reference_runtime: tuple[object, ...] | None = None
    reference_request_parameters_hash: str | None = None
    for cell_id in CANONICAL_CELL_IDS:
        schedule = schedules_by_cell[cell_id]
        manifest = manifests_by_cell[cell_id]
        binding = adapter_bindings_by_cell[cell_id]
        if not isinstance(schedule, FrozenSchedule):
            raise TypeError("cell schedules must be FrozenSchedule values")
        if schedule.schedule_hash != expected_schedule_hash:
            raise ValueError("cell schedule drifts from the frozen publish schedule")
        if not isinstance(manifest, RunManifest) or manifest.matched_seed != matched_seed:
            raise ValueError("cell manifest matched seed does not match the matrix")
        if manifest.run_spec.get("cell_id") != cell_id:
            raise ValueError("manifest cell identity drifts from its matrix key")
        if manifest.schedule != schedule or manifest.schedule_hash != expected_schedule_hash:
            raise ValueError("manifest schedule drifts from the shared frozen schedule")
        if not isinstance(binding, MockAdapterExecutionBinding):
            raise TypeError("adapter bindings must be typed")
        if (
            manifest.model_identity["provider"] != binding.runtime_identity.get("provider")
            or manifest.model_identity["runtime"] != binding.runtime_identity.get("runtime_version")
            or manifest.model_identity["model"] != binding.model_identity.get("model")
            or manifest.model_identity["revision"] != binding.model_identity.get("revision")
        ):
            raise ValueError("manifest model identity drifts from its adapter binding")
        expected_event_ids = tuple(
            derive_event_id(manifest.run_id, ordinal) for ordinal in range(schedule.count)
        )
        if set(binding.script_step_hashes) != set(expected_event_ids):
            raise ValueError("adapter script does not exactly cover the cell event identities")
        runtime = (
            binding.expected_adapter_kind,
            binding.expected_adapter_version,
            binding.runtime_identity_hash,
            binding.model_identity_hash,
            tuple(binding.script_step_hashes[event_id] for event_id in expected_event_ids),
        )
        if reference_runtime is None:
            reference_runtime = runtime
        elif runtime != reference_runtime:
            raise ValueError("adapter runtime, model, or ordered script drifts across cells")
        identity, continuity, exposure_mode = _cell_factors(cell_id)
        graph_hash = (
            None
            if exposure_mode == "self_history_only"
            else shadow_artifact.output_hash
            if exposure_mode == "shuffled_social"
            else ws_artifact.output_hash
        )
        request_parameters_hash = _validate_manifest_contract(
            scale_case=scale_case,
            manifest=manifest,
            cell_id=cell_id,
            artifact_hashes=artifact_hashes,
            exposure_graph_hash=graph_hash,
            clock_sequence_id=clock_id,
            clock_sequence_hash=clock_hash,
            adapter_binding=binding,
            expected_event_ids=expected_event_ids,
        )
        if reference_request_parameters_hash is None:
            reference_request_parameters_hash = request_parameters_hash
        elif request_parameters_hash != reference_request_parameters_hash:
            raise ValueError("mock request parameters drift across matched cells")
        cells.append(
            MockCellBinding(
                cell_id=cell_id,
                identity_present=identity,
                continuity_present=continuity,
                exposure_mode=exposure_mode,
                exposure_graph_hash=graph_hash,
                artifact_hashes=artifact_hashes,
                manifest=manifest,
                adapter_binding=binding,
                clock_sequence_id=clock_id,
                clock_sequence_hash=clock_hash,
            )
        )
    matrix = MockMatchedSeedMatrix(
        schema_version=_MATRIX_SCHEMA_VERSION,
        matched_seed=matched_seed,
        scale_case=scale_case,
        cells=tuple(cells),
    )
    validate_mock_matched_seed_matrix(matrix)
    return matrix


def validate_mock_matched_seed_matrix(matrix: MockMatchedSeedMatrix) -> None:
    """Fail closed on any outcome-free matrix binding drift."""

    if not isinstance(matrix, MockMatchedSeedMatrix):
        raise TypeError("matrix must be a MockMatchedSeedMatrix")
    if matrix.schema_version != _MATRIX_SCHEMA_VERSION:
        raise ValueError("matrix schema version is unsupported")
    if type(matrix.matched_seed) is not int:
        raise TypeError("matrix matched seed must be a strict integer")
    if tuple(cell.cell_id for cell in matrix.cells) != CANONICAL_CELL_IDS:
        raise ValueError("matrix cells must be the canonical ordered exact cover")
    clock_id, clock_hash = mock_clock_sequence_binding(matrix.scale_case)
    allowed_sweep_counts = {
        matrix.scale_case.integration_sweeps,
        matrix.scale_case.recovery_sweeps,
        matrix.scale_case.shape_sweeps,
    }
    shared_hashes: Mapping[str, str] | None = None
    shared_schedule: FrozenSchedule | None = None
    reference_runtime: tuple[object, ...] | None = None
    reference_request_parameters_hash: str | None = None
    for cell in matrix.cells:
        identity, continuity, exposure_mode = _cell_factors(cell.cell_id)
        if (cell.identity_present, cell.continuity_present, cell.exposure_mode) != (
            identity,
            continuity,
            exposure_mode,
        ):
            raise ValueError("matrix persona or exposure factors drift from cell identity")
        if set(cell.artifact_hashes) != _ARTIFACT_HASH_KEYS:
            raise ValueError("matrix artifact hashes do not have exact cover")
        if shared_hashes is None:
            shared_hashes = cell.artifact_hashes
        elif cell.artifact_hashes != shared_hashes:
            raise ValueError("shared artifact hash drifts across matrix cells")
        expected_graph = (
            None
            if exposure_mode == "self_history_only"
            else cell.artifact_hashes["shadow"]
            if exposure_mode == "shuffled_social"
            else cell.artifact_hashes["ws"]
        )
        if cell.exposure_graph_hash != expected_graph:
            raise ValueError("exposure graph does not match the canonical factor level")
        if cell.clock_sequence_id != clock_id or cell.clock_sequence_hash != clock_hash:
            raise ValueError("cell clock binding drifts from the explicit scale clock")
        manifest = cell.manifest
        if (
            manifest.schedule.population_size != matrix.scale_case.population_size
            or manifest.schedule.sweep_count not in allowed_sweep_counts
        ):
            raise ValueError("matrix schedule population or sweep count drifts from scale case")
        if manifest.matched_seed != matrix.matched_seed:
            raise ValueError("manifest matched seed drifts from matrix")
        if manifest.run_spec.get("cell_id") != cell.cell_id:
            raise ValueError("manifest cell identity drifts from matrix")
        if manifest.schedule_hash != cell.artifact_hashes["schedule"]:
            raise ValueError("manifest schedule hash drifts from matrix")
        if shared_schedule is None:
            shared_schedule = manifest.schedule
        elif manifest.schedule != shared_schedule:
            raise ValueError("manifest publish schedule drifts across cells")
        binding = cell.adapter_binding
        if (
            manifest.model_identity["provider"] != binding.runtime_identity.get("provider")
            or manifest.model_identity["runtime"] != binding.runtime_identity.get("runtime_version")
            or manifest.model_identity["model"] != binding.model_identity.get("model")
            or manifest.model_identity["revision"] != binding.model_identity.get("revision")
        ):
            raise ValueError("manifest model identity drifts from its adapter binding")
        expected_event_ids = tuple(
            derive_event_id(manifest.run_id, ordinal) for ordinal in range(manifest.schedule.count)
        )
        if set(binding.script_step_hashes) != set(expected_event_ids):
            raise ValueError("adapter script does not exactly cover the cell event identities")
        request_parameters_hash = _validate_manifest_contract(
            scale_case=matrix.scale_case,
            manifest=manifest,
            cell_id=cell.cell_id,
            artifact_hashes=cell.artifact_hashes,
            exposure_graph_hash=cell.exposure_graph_hash,
            clock_sequence_id=cell.clock_sequence_id,
            clock_sequence_hash=cell.clock_sequence_hash,
            adapter_binding=binding,
            expected_event_ids=expected_event_ids,
        )
        if reference_request_parameters_hash is None:
            reference_request_parameters_hash = request_parameters_hash
        elif request_parameters_hash != reference_request_parameters_hash:
            raise ValueError("mock request parameters drift across matched cells")
        runtime = (
            binding.expected_adapter_kind,
            binding.expected_adapter_version,
            binding.runtime_identity_hash,
            binding.model_identity_hash,
            tuple(binding.script_step_hashes[event_id] for event_id in expected_event_ids),
        )
        if reference_runtime is None:
            reference_runtime = runtime
        elif runtime != reference_runtime:
            raise ValueError("adapter runtime, model, or ordered script drifts across cells")
    expected_matrix_hash = canonical_payload_hash(
        {
            "schema_version": matrix.schema_version,
            "matched_seed": matrix.matched_seed,
            "scale_case": matrix.scale_case.to_payload(),
            "cells": tuple(cell._hash_payload() for cell in matrix.cells),
        }
    )
    if matrix.matrix_hash != expected_matrix_hash:
        raise ValueError("matrix hash does not match its canonical payload")
    return None
