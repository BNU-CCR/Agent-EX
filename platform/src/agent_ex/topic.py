"""Strict mock-only topic package records for Phase 4B-3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .domain import (
    _freeze,
    _json_ready,
    _require_id,
    _require_json_transport,
    _require_string,
    canonical_payload_hash,
)


_TOPIC_FIELDS = {
    "schema_version",
    "package_version",
    "topic_id",
    "construct",
    "target_population",
    "applicability",
    "fact_card",
    "core_statement",
    "paraphrases",
    "stance_labels",
    "confidence_contract",
    "output_contract",
    "argument_families",
    "round0_reason_library_artifact_id",
    "topic_extension_fields",
    "metadata",
}


@dataclass(frozen=True, slots=True)
class TopicPackage:
    """A versioned topic input; Phase 4B-3 permits explicit mock packages only."""

    schema_version: str
    package_version: str
    topic_id: str
    construct: str
    target_population: str
    applicability: str
    fact_card: str
    core_statement: str
    paraphrases: tuple[str, ...]
    stance_labels: tuple[str, ...]
    confidence_contract: Mapping[str, object]
    output_contract: tuple[str, ...]
    argument_families: tuple[str, ...]
    round0_reason_library_artifact_id: str
    topic_extension_fields: tuple[str, ...]
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.schema_version != "paper1.topic-package.mock.v1":
            raise ValueError("Phase 4B-3 accepts only paper1.topic-package.mock.v1")
        for name in (
            "package_version",
            "construct",
            "target_population",
            "applicability",
            "fact_card",
            "core_statement",
        ):
            _require_string(name, getattr(self, name))
        _require_id("topic_id", self.topic_id)
        _require_id("round0_reason_library_artifact_id", self.round0_reason_library_artifact_id)
        for name in (
            "paraphrases",
            "stance_labels",
            "output_contract",
            "argument_families",
            "topic_extension_fields",
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple")
            for item in value:
                _require_string(name, item)
        if len(self.stance_labels) != 7 or len(set(self.stance_labels)) != 7:
            raise ValueError("stance_labels must contain seven unique labels")
        if self.output_contract != ("stance", "confidence", "public_reason"):
            raise ValueError("output_contract must preserve the approved field order")
        if not self.paraphrases or not self.argument_families:
            raise ValueError("topic package requires paraphrases and argument families")
        if not isinstance(self.confidence_contract, Mapping):
            raise TypeError("confidence_contract must be a mapping")
        if dict(self.confidence_contract) != {
            "minimum": 1,
            "maximum": 5,
            "analysis_only": True,
        }:
            raise ValueError("confidence_contract must preserve the approved audit-only scale")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        if self.metadata.get("mock_only") is not True:
            raise ValueError("Phase 4B-3 topic packages must be explicitly mock_only")
        if self.metadata.get("research_parameter_status") != "not_frozen":
            raise ValueError(
                "mock topic package must state that research parameters are not frozen"
            )
        object.__setattr__(self, "confidence_contract", _freeze(self.confidence_contract))
        object.__setattr__(self, "metadata", _freeze(self.metadata))

    @property
    def package_hash(self) -> str:
        return canonical_payload_hash(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return _json_ready(
            {
                "schema_version": self.schema_version,
                "package_version": self.package_version,
                "topic_id": self.topic_id,
                "construct": self.construct,
                "target_population": self.target_population,
                "applicability": self.applicability,
                "fact_card": self.fact_card,
                "core_statement": self.core_statement,
                "paraphrases": self.paraphrases,
                "stance_labels": self.stance_labels,
                "confidence_contract": self.confidence_contract,
                "output_contract": self.output_contract,
                "argument_families": self.argument_families,
                "round0_reason_library_artifact_id": self.round0_reason_library_artifact_id,
                "topic_extension_fields": self.topic_extension_fields,
                "metadata": self.metadata,
            }
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> TopicPackage:
        if type(payload) is not dict:
            raise TypeError("topic package payload must be a JSON object")
        if set(payload) != _TOPIC_FIELDS:
            raise ValueError("topic package payload fields do not match the contract")
        for name in (
            "paraphrases",
            "stance_labels",
            "output_contract",
            "argument_families",
            "topic_extension_fields",
        ):
            if type(payload[name]) is not list:
                raise TypeError(f"topic package {name} must be a JSON array")
        if (
            type(payload["confidence_contract"]) is not dict
            or type(payload["metadata"]) is not dict
        ):
            raise TypeError("topic package contracts and metadata must be JSON objects")
        _require_json_transport(payload, "topic package payload")
        return cls(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            package_version=payload["package_version"],  # type: ignore[arg-type]
            topic_id=payload["topic_id"],  # type: ignore[arg-type]
            construct=payload["construct"],  # type: ignore[arg-type]
            target_population=payload["target_population"],  # type: ignore[arg-type]
            applicability=payload["applicability"],  # type: ignore[arg-type]
            fact_card=payload["fact_card"],  # type: ignore[arg-type]
            core_statement=payload["core_statement"],  # type: ignore[arg-type]
            paraphrases=tuple(payload["paraphrases"]),  # type: ignore[arg-type]
            stance_labels=tuple(payload["stance_labels"]),  # type: ignore[arg-type]
            confidence_contract=payload["confidence_contract"],  # type: ignore[arg-type]
            output_contract=tuple(payload["output_contract"]),  # type: ignore[arg-type]
            argument_families=tuple(payload["argument_families"]),  # type: ignore[arg-type]
            round0_reason_library_artifact_id=payload["round0_reason_library_artifact_id"],  # type: ignore[arg-type]
            topic_extension_fields=tuple(payload["topic_extension_fields"]),  # type: ignore[arg-type]
            metadata=payload["metadata"],  # type: ignore[arg-type]
        )
