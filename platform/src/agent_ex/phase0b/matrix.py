"""Diagnostic Phase 0B matrix binding for the N=20/T=2 fast track."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar, Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import FrozenSchedule, RunManifest, _json_ready, canonical_payload_hash
from ..execution_evidence import MockAdapterExecutionBinding
from ..mock_matrix import (
    CANONICAL_CELL_IDS,
    MockMatchedSeedMatrix,
    MockScaleCase,
    build_mock_matched_seed_matrix,
    validate_mock_matched_seed_matrix,
)
from ..topic import TopicPackage


_DIAGNOSTIC_MATRIX_SCHEMA = "paper1.phase0b.diagnostic-n20-t2-matrix.v1"
_AUTHORIZATION_ARTIFACT_KEYS = frozenset(
    {
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
)


def _strict_hash_mapping(value: Mapping[str, object]) -> dict[str, str]:
    if type(value) is not dict or set(value) != _AUTHORIZATION_ARTIFACT_KEYS:
        raise ValueError("diagnostic matrix artifact hashes must exactly match authorization keys")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if (
            type(item) is not str
            or len(item) != 64
            or any(ch not in "0123456789abcdef" for ch in item)
        ):
            raise ValueError(f"diagnostic matrix artifact hash {key} must be lowercase sha256")
        normalized[key] = item
    return normalized


def _content_payload(value: object) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in fields(value)  # type: ignore[arg-type]
        if field.name not in {"matrix", "record_hash"}
    }


@dataclass(frozen=True, slots=True)
class DiagnosticMatrixCandidate:
    """Outcome-free binding between synthetic Phase 4B inputs and a real-Qwen diagnostic."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    input_artifact_mode: str
    agent_count: int
    sweep_count: int
    matched_seed: int
    cell_ids: tuple[str, ...]
    expected_event_count: int
    max_transport_count: int
    authorization_artifact_hashes: Mapping[str, str]
    matrix_hash: str
    matrix: MockMatchedSeedMatrix
    record_hash: str

    _SCHEMA: ClassVar[str] = _DIAGNOSTIC_MATRIX_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA:
            raise ValueError("diagnostic matrix schema is unsupported")
        if self.calibration_only is not True or type(self.calibration_only) is not bool:
            raise ValueError("diagnostic matrix must remain calibration_only=true")
        if (
            self.formal_parameter_authority is not False
            or type(self.formal_parameter_authority) is not bool
        ):
            raise ValueError("diagnostic matrix must not grant formal parameter authority")
        if self.research_parameter_status != "not_frozen":
            raise ValueError("diagnostic matrix must remain not_frozen")
        if self.input_artifact_mode != "synthetic_phase4b_candidate":
            raise ValueError("diagnostic matrix inputs must remain synthetic candidates")
        if type(self.agent_count) is not int or self.agent_count != 20:
            raise ValueError("diagnostic matrix requires exactly 20 agents")
        if type(self.sweep_count) is not int or self.sweep_count != 2:
            raise ValueError("diagnostic matrix requires exactly 2 sweeps")
        if type(self.matched_seed) is not int:
            raise TypeError("diagnostic matrix matched seed must be a strict integer")
        if self.cell_ids != CANONICAL_CELL_IDS:
            raise ValueError("diagnostic matrix cells must be the canonical exact cover")
        if self.expected_event_count != 480:
            raise ValueError("diagnostic matrix requires exactly 480 logical events")
        if self.max_transport_count != 960:
            raise ValueError("diagnostic matrix hard ceiling must be 960 transports")
        validate_mock_matched_seed_matrix(self.matrix)
        if self.matrix.matched_seed != self.matched_seed:
            raise ValueError("diagnostic matrix matched seed drifted")
        if self.matrix.scale_case.population_size != self.agent_count:
            raise ValueError("diagnostic matrix population drifted from N=20")
        if self.matrix.scale_case.recovery_sweeps != self.sweep_count:
            raise ValueError("diagnostic matrix sweep count drifted from T=2")
        event_count = sum(cell.manifest.schedule.count for cell in self.matrix.cells)
        if event_count != self.expected_event_count:
            raise ValueError("diagnostic matrix event inventory is not 480")
        if self.matrix_hash != self.matrix.matrix_hash:
            raise ValueError("diagnostic matrix hash does not bind the matrix payload")
        hashes = _strict_hash_mapping(self.authorization_artifact_hashes)
        object.__setattr__(self, "authorization_artifact_hashes", hashes)
        expected_hashes = self.matrix.cells[0].artifact_hashes
        mapped = {
            "topic": expected_hashes["topic"],
            "population": expected_hashes["population"],
            "persona": expected_hashes["persona_template"],
            "network": expected_hashes["ws"],
            "shadow": expected_hashes["shadow"],
            "mapping": expected_hashes["mapping"],
            "attention": expected_hashes["attention"],
            "expression": expected_hashes["expression"],
            "activation": expected_hashes["activation"],
            "publish": expected_hashes["publish"],
            "schedule": expected_hashes["schedule"],
        }
        if hashes != mapped:
            raise ValueError("diagnostic matrix artifact hashes drifted from the validated matrix")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("diagnostic matrix record_hash does not match content")

    def content_payload(self) -> dict[str, object]:
        return _json_ready(_content_payload(self))

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})


def build_diagnostic_n20_matrix_candidate(
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
) -> DiagnosticMatrixCandidate:
    """Build the outcome-free N=20/T=2 diagnostic matrix candidate."""

    matrix = build_mock_matched_seed_matrix(
        scale_case=scale_case,
        matched_seed=matched_seed,
        topic_package=topic_package,
        population_artifact=population_artifact,
        initial_stance_artifact=initial_stance_artifact,
        initial_reason_artifact=initial_reason_artifact,
        persona_template=persona_template,
        ws_artifact=ws_artifact,
        shadow_artifact=shadow_artifact,
        agent_node_mapping=agent_node_mapping,
        structural_gate_artifact=structural_gate_artifact,
        attention_artifact=attention_artifact,
        expression_artifact=expression_artifact,
        activation_artifact=activation_artifact,
        publish_artifact=publish_artifact,
        schedules_by_cell=schedules_by_cell,
        manifests_by_cell=manifests_by_cell,
        adapter_bindings_by_cell=adapter_bindings_by_cell,
    )
    matrix_hash = matrix.matrix_hash
    source_hashes = matrix.cells[0].artifact_hashes
    authorization_hashes = {
        "topic": source_hashes["topic"],
        "population": source_hashes["population"],
        "persona": source_hashes["persona_template"],
        "network": source_hashes["ws"],
        "shadow": source_hashes["shadow"],
        "mapping": source_hashes["mapping"],
        "attention": source_hashes["attention"],
        "expression": source_hashes["expression"],
        "activation": source_hashes["activation"],
        "publish": source_hashes["publish"],
        "schedule": source_hashes["schedule"],
    }
    content: dict[str, object] = {
        "schema_version": _DIAGNOSTIC_MATRIX_SCHEMA,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "input_artifact_mode": "synthetic_phase4b_candidate",
        "agent_count": 20,
        "sweep_count": 2,
        "matched_seed": matched_seed,
        "cell_ids": CANONICAL_CELL_IDS,
        "expected_event_count": 480,
        "max_transport_count": 960,
        "authorization_artifact_hashes": authorization_hashes,
        "matrix_hash": matrix_hash,
    }
    return DiagnosticMatrixCandidate(
        **content,
        matrix=matrix,
        record_hash=canonical_payload_hash(_json_ready(content)),
    )  # type: ignore[arg-type]
