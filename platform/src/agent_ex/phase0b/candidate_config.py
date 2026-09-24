"""Content-addressed, cold-reconstructable inputs for a preliminary Phase 0B family.

This is an explicit candidate, not a frozen Paper 1 parameter declaration.
No candidate values are selected by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar, Mapping, Sequence

from ..artifacts import ArtifactEnvelope
from ..domain import (
    _freeze,
    _json_ready,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    canonical_payload_hash,
)
from ..topic import TopicPackage
from .launch_intent import Phase0BLaunchIntent
from .matrix import DiagnosticN20ArtifactFamily, build_diagnostic_n20_artifact_family


def _reject_unresolved(value: object, name: str) -> None:
    if isinstance(value, str):
        if "UNRESOLVED[" in value:
            raise ValueError(f"{name} must not contain UNRESOLVED markers")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _reject_unresolved(key, name)
            _reject_unresolved(item, name)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _reject_unresolved(item, name)


@dataclass(frozen=True, slots=True)
class Phase0BCandidateConfig:
    """Exact source payloads and every explicit N=20 family-builder argument."""

    schema_version: str
    matched_seed: int
    population_frame_artifact: Mapping[str, object]
    population_weights: tuple[float, ...]
    population_constraints: Mapping[str, object]
    population_tolerance: int
    topic_package: Mapping[str, object]
    reason_library_artifact: Mapping[str, object]
    persona_template: Mapping[str, object]
    stance_orthogonal_fields: tuple[str, ...]
    stance_max_category_imbalance: float
    ws_k: int
    ws_rewire_probability: float
    shadow_max_attempts: int
    shadow_trial_budget_per_edge: int
    structural_null_replicates: int
    attention_family: str
    attention_parameters: Mapping[str, object]
    structural_lurker_probability: float
    expression_beta_alpha: float
    expression_beta_beta: float
    expression_max_beta_attempts_per_agent: int
    expression_correlation_mode: str
    sweep_count: int
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.candidate-config.v1"
    _ARTIFACT_FIELDS: ClassVar[tuple[str, ...]] = (
        "population_frame_artifact",
        "reason_library_artifact",
        "persona_template",
    )

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA:
            raise ValueError("candidate config schema is unsupported")
        if self.calibration_only is not True or type(self.calibration_only) is not bool:
            raise ValueError("candidate config must remain calibration_only=true")
        if (
            self.formal_parameter_authority is not False
            or type(self.formal_parameter_authority) is not bool
        ):
            raise ValueError("candidate config cannot grant formal parameter authority")
        if self.research_parameter_status != "not_frozen":
            raise ValueError("candidate config must remain not_frozen")
        for name in (
            "matched_seed",
            "population_tolerance",
            "ws_k",
            "shadow_max_attempts",
            "shadow_trial_budget_per_edge",
            "structural_null_replicates",
            "expression_max_beta_attempts_per_agent",
            "sweep_count",
        ):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"candidate config {name} must be a strict integer")
        for name in ("attention_family", "expression_correlation_mode"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"candidate config {name} must be a string")
        for name in (
            "stance_max_category_imbalance",
            "ws_rewire_probability",
            "structural_lurker_probability",
            "expression_beta_alpha",
            "expression_beta_beta",
        ):
            if type(getattr(self, name)) not in {int, float}:
                raise TypeError(f"candidate config {name} must be a JSON number")
        for name in ("population_weights", "stance_orthogonal_fields"):
            if not isinstance(getattr(self, name), tuple):
                raise TypeError(f"candidate config {name} must be an array")
        if any(type(weight) not in {int, float} for weight in self.population_weights):
            raise TypeError("candidate config population_weights must contain JSON numbers")
        if any(type(name) is not str for name in self.stance_orthogonal_fields):
            raise TypeError("candidate config stance_orthogonal_fields must contain strings")
        for name in (
            *self._ARTIFACT_FIELDS,
            "topic_package",
            "population_constraints",
            "attention_parameters",
        ):
            if not isinstance(getattr(self, name), Mapping):
                raise TypeError(f"candidate config {name} must be an object")
        _reject_unresolved(self.content_payload(), "candidate config")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        # Inner payloads have separate identities, which must survive cold transport.
        source_artifacts = {
            name: ArtifactEnvelope.from_payload(_json_ready(getattr(self, name)))
            for name in self._ARTIFACT_FIELDS
        }
        topic = TopicPackage.from_payload(_json_ready(self.topic_package))
        if (
            topic.round0_reason_library_artifact_id
            != source_artifacts["reason_library_artifact"].artifact_id
        ):
            raise ValueError("round0_reason_library_artifact_id does not match reason library")
        for name in (
            *self._ARTIFACT_FIELDS,
            "topic_package",
            "population_constraints",
            "attention_parameters",
            "population_weights",
            "stance_orthogonal_fields",
        ):
            object.__setattr__(self, name, _freeze(getattr(self, name)))

    def content_payload(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "record_hash"
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        matched_seed: int,
        population_frame_artifact: ArtifactEnvelope,
        population_weights: Sequence[float],
        population_constraints: Mapping[str, object],
        population_tolerance: int,
        topic_package: TopicPackage,
        reason_library_artifact: ArtifactEnvelope,
        persona_template: ArtifactEnvelope,
        stance_orthogonal_fields: tuple[str, ...],
        stance_max_category_imbalance: float,
        ws_k: int,
        ws_rewire_probability: float,
        shadow_max_attempts: int,
        shadow_trial_budget_per_edge: int,
        structural_null_replicates: int,
        attention_family: str,
        attention_parameters: Mapping[str, object],
        structural_lurker_probability: float,
        expression_beta_alpha: float,
        expression_beta_beta: float,
        expression_max_beta_attempts_per_agent: int,
        expression_correlation_mode: str,
        sweep_count: int,
        calibration_only: bool,
        formal_parameter_authority: bool,
        research_parameter_status: str,
    ) -> Phase0BCandidateConfig:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            "matched_seed": matched_seed,
            "population_frame_artifact": population_frame_artifact.to_payload(),
            "population_weights": list(population_weights),
            "population_constraints": _json_ready(population_constraints),
            "population_tolerance": population_tolerance,
            "topic_package": topic_package.to_payload(),
            "reason_library_artifact": reason_library_artifact.to_payload(),
            "persona_template": persona_template.to_payload(),
            "stance_orthogonal_fields": list(stance_orthogonal_fields),
            "stance_max_category_imbalance": stance_max_category_imbalance,
            "ws_k": ws_k,
            "ws_rewire_probability": ws_rewire_probability,
            "shadow_max_attempts": shadow_max_attempts,
            "shadow_trial_budget_per_edge": shadow_trial_budget_per_edge,
            "structural_null_replicates": structural_null_replicates,
            "attention_family": attention_family,
            "attention_parameters": _json_ready(attention_parameters),
            "structural_lurker_probability": structural_lurker_probability,
            "expression_beta_alpha": expression_beta_alpha,
            "expression_beta_beta": expression_beta_beta,
            "expression_max_beta_attempts_per_agent": expression_max_beta_attempts_per_agent,
            "expression_correlation_mode": expression_correlation_mode,
            "sweep_count": sweep_count,
            "calibration_only": calibration_only,
            "formal_parameter_authority": formal_parameter_authority,
            "research_parameter_status": research_parameter_status,
        }
        _require_json_transport(content, "candidate config")
        return cls.from_payload({**content, "record_hash": canonical_payload_hash(content)})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Phase0BCandidateConfig:
        if type(payload) is not dict or set(payload) != {field.name for field in fields(cls)}:
            raise ValueError("candidate config payload requires exact fields including record_hash")
        _require_json_transport(payload, "candidate config payload")
        for name in ("population_weights", "stance_orthogonal_fields"):
            if type(payload[name]) is not list:
                raise TypeError(f"candidate config {name} must use a JSON array")
        for name in (
            *cls._ARTIFACT_FIELDS,
            "topic_package",
            "population_constraints",
            "attention_parameters",
        ):
            if type(payload[name]) is not dict:
                raise TypeError(f"candidate config {name} must use a JSON object")
        content = dict(payload)
        content["population_weights"] = tuple(content["population_weights"])
        content["stance_orthogonal_fields"] = tuple(content["stance_orthogonal_fields"])
        return cls(**content)  # type: ignore[arg-type]

    def build_family(self) -> DiagnosticN20ArtifactFamily:
        """Recompute the family without process-local fixture objects."""

        return build_diagnostic_n20_artifact_family(
            matched_seed=self.matched_seed,
            population_frame_artifact=ArtifactEnvelope.from_payload(
                _json_ready(self.population_frame_artifact)
            ),
            population_weights=self.population_weights,
            population_constraints=self.population_constraints,
            population_tolerance=self.population_tolerance,
            topic_package=TopicPackage.from_payload(_json_ready(self.topic_package)),
            reason_library_artifact=ArtifactEnvelope.from_payload(
                _json_ready(self.reason_library_artifact)
            ),
            persona_template=ArtifactEnvelope.from_payload(_json_ready(self.persona_template)),
            stance_orthogonal_fields=self.stance_orthogonal_fields,
            stance_max_category_imbalance=self.stance_max_category_imbalance,
            ws_k=self.ws_k,
            ws_rewire_probability=self.ws_rewire_probability,
            shadow_max_attempts=self.shadow_max_attempts,
            shadow_trial_budget_per_edge=self.shadow_trial_budget_per_edge,
            structural_null_replicates=self.structural_null_replicates,
            attention_family=self.attention_family,
            attention_parameters=self.attention_parameters,
            structural_lurker_probability=self.structural_lurker_probability,
            expression_beta_alpha=self.expression_beta_alpha,
            expression_beta_beta=self.expression_beta_beta,
            expression_max_beta_attempts_per_agent=self.expression_max_beta_attempts_per_agent,
            expression_correlation_mode=self.expression_correlation_mode,
            sweep_count=self.sweep_count,
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
            research_parameter_status=self.research_parameter_status,
        )

    def verify_intent(self, intent: Phase0BLaunchIntent) -> None:
        if not isinstance(intent, Phase0BLaunchIntent):
            raise TypeError("launch intent must be a Phase0BLaunchIntent")
        if intent.candidate_config_hash != self.record_hash:
            raise ValueError("candidate_config_hash does not match candidate config")
        if dict(intent.artifact_hashes) != dict(self.build_family().authorization_artifact_hashes):
            raise ValueError("artifact_hashes do not match reconstructed candidate family")
