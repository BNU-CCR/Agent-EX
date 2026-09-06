"""Deterministic, blinded Phase 0A semantic-review evidence.

The records in this module have calibration-only authority.  They bind reviewer-visible
material to hidden upstream evidence without exposing experimental conditions to coders.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from fractions import Fraction
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import (
    _freeze,
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    _require_timestamp,
    canonical_payload_hash,
)
from .contracts import (
    ProbeCase,
    ProbeParseEvidence,
    ProbeRequest,
    ProbeRunProjection,
    ProbeTopicCandidate,
)
from .gates import SemanticGateEvidence, fold_case_attempts
from .specification import expand_probe_cases, load_probe_specification


_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_VISIBLE_FIELDS = ("topic_text", "history_text", "identity_text", "response_text")
_SELECTOR_FIELDS = {
    "candidate_id",
    "case_family",
    "scenario_id",
    "variant_index",
    "scale_id",
    "field_order_id",
    "replicate_id",
    "persona_view_id",
}
_DIRECT_CONTRADICTION = {"consistent", "contradiction", "indeterminate"}


def _metadata() -> dict[str, object]:
    return dict(_METADATA)


def _require_metadata(value: object) -> None:
    if type(value) is not dict or set(value) != set(_METADATA):
        raise ValueError("semantic-review metadata fields differ from calibration contract")
    for key, expected in _METADATA.items():
        if type(value[key]) is not type(expected) or value[key] != expected:
            raise ValueError("semantic-review metadata must remain calibration-only/not-frozen")


def _exact_payload(payload: Mapping[str, object], expected: set[str], schema: str) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError("semantic-review payload fields do not match the exact contract")
    _require_json_transport(payload, "semantic-review payload")
    if payload["schema_version"] != schema:
        raise ValueError("semantic-review schema version is unsupported")
    _require_metadata(payload["metadata"])


def _require_fraction(name: str, value: object) -> None:
    if type(value) is not Fraction or not 0 <= value <= 1:
        raise ValueError(f"{name} must be an exact Fraction in [0,1]")


def _fraction_payload(value: Fraction | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def _fraction_from_payload(value: object) -> Fraction | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != {"numerator", "denominator"}:
        raise ValueError("fraction payload must contain exact numerator/denominator fields")
    if type(value["numerator"]) is not int or type(value["denominator"]) is not int:
        raise TypeError("fraction numerator and denominator must be integers")
    return Fraction(value["numerator"], value["denominator"])


def _record_payload(
    record: object, schema: str, *, omit: set[str] | None = None
) -> dict[str, object]:
    omitted = {"record_hash"} | (omit or set())
    return {
        "schema_version": schema,
        **{f.name: getattr(record, f.name) for f in fields(record) if f.name not in omitted},
        "metadata": _metadata(),
    }


def _validate_record_hash(record: object, schema: str) -> None:
    _require_sha256("record_hash", getattr(record, "record_hash"))
    _require_payload_hash(
        "record_hash", getattr(record, "record_hash"), _record_payload(record, schema)
    )


@dataclass(frozen=True, slots=True)
class ReviewStratum:
    stratum_id: str
    selectors: Mapping[str, str | int]
    sample_count: int

    def __post_init__(self) -> None:
        _require_id("stratum_id", self.stratum_id)
        if type(self.selectors) is not dict:
            raise TypeError("stratum selectors must be an exact mapping")
        if not set(self.selectors) <= _SELECTOR_FIELDS:
            raise ValueError("stratum selectors contain an unsupported case field")
        for name, value in self.selectors.items():
            if type(value) not in {str, int}:
                raise TypeError(f"stratum selector {name} must be str or int")
        _require_int("sample_count", self.sample_count, minimum=1)
        object.__setattr__(self, "selectors", _freeze(dict(sorted(self.selectors.items()))))

    def to_payload(self) -> dict[str, object]:
        return _json_ready({f.name: getattr(self, f.name) for f in fields(self)})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReviewStratum:
        if type(payload) is not dict or set(payload) != {"stratum_id", "selectors", "sample_count"}:
            raise ValueError("review stratum requires exact fields")
        if type(payload["selectors"]) is not dict:
            raise TypeError("review stratum selectors must use a JSON object")
        return cls(payload["stratum_id"], payload["selectors"], payload["sample_count"])  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class CoderContract:
    coder_id: str
    role: str
    assignment_scope: str
    model_id: str | None = None
    model_revision: str | None = None
    judge_prompt_hash: str | None = None
    ordering_policy_id: str | None = None
    ordering_policy_hash: str | None = None
    runtime_provider: str | None = None
    runtime_version: str | None = None

    _SCHEMA = "paper1.calibration.coder-contract.v1"

    def __post_init__(self) -> None:
        _require_id("coder_id", self.coder_id)
        if self.role not in {"human", "judge"}:
            raise ValueError("coder role must be explicitly human or judge")
        expected_scope = "all_eligible" if self.role == "judge" else "stratified_sample"
        if self.assignment_scope != expected_scope:
            raise ValueError("coder role assignment scope is invalid")
        provenance_fields = (
            "model_id",
            "model_revision",
            "judge_prompt_hash",
            "ordering_policy_id",
            "ordering_policy_hash",
            "runtime_provider",
            "runtime_version",
        )
        if self.role == "human":
            if any(getattr(self, name) is not None for name in provenance_fields):
                raise ValueError("human coder judge-provenance fields must be explicitly null")
        else:
            if any(getattr(self, name) is None for name in provenance_fields):
                raise ValueError(
                    "judge coder requires complete model/prompt/order/runtime provenance"
                )
            for name in (
                "model_id",
                "model_revision",
                "ordering_policy_id",
                "runtime_provider",
                "runtime_version",
            ):
                _require_id(name, getattr(self, name))
            for name in ("judge_prompt_hash", "ordering_policy_hash"):
                _require_sha256(name, getattr(self, name))

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    def content_payload(self) -> dict[str, object]:
        return _record_payload(self, self._SCHEMA)

    @property
    def record_hash(self) -> str:
        return canonical_payload_hash(self.content_payload())

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> CoderContract:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata", "record_hash"}
        _exact_payload(payload, expected, cls._SCHEMA)
        value = cls(**{name: payload[name] for name in cls.__dataclass_fields__})  # type: ignore[arg-type]
        if payload["record_hash"] != value.record_hash:
            raise ValueError("coder contract record hash differs from content")
        return value


@dataclass(frozen=True, slots=True)
class SemanticReviewPolicy:
    policy_id: str
    policy_version: str
    strata: tuple[ReviewStratum, ...]
    randomization_seed: int
    randomization_domain: str
    visible_field_allowlist: tuple[str, ...]
    coder_contracts: tuple[CoderContract, ...]
    required_human_coder_count: int
    required_judge_coder_count: int
    dimension_labels: Mapping[str, tuple[str, ...]]
    agreement_statistic: str
    agreement_scope: str
    agreement_threshold: Fraction
    judge_failure_rule: str
    adjudication_trigger: str
    aggregation_rule: str
    classifier_id: str
    classifier_version: str
    classifier_hash: str
    refusal_dimension: str
    refusal_positive_labels: tuple[str, ...]
    contradiction_dimension: str
    contradiction_label_map: Mapping[str, str]

    _SCHEMA = "paper1.calibration.semantic-review-policy.v1"

    def __post_init__(self) -> None:
        for name in ("policy_id", "policy_version", "classifier_id", "classifier_version"):
            _require_id(name, getattr(self, name))
        _require_sha256("classifier_hash", self.classifier_hash)
        if (
            type(self.strata) is not tuple
            or not self.strata
            or any(type(value) is not ReviewStratum for value in self.strata)
        ):
            raise TypeError("strata must be a nonempty tuple of ReviewStratum")
        if len({value.stratum_id for value in self.strata}) != len(self.strata):
            raise ValueError("duplicate semantic-review stratum IDs")
        _require_int("randomization_seed", self.randomization_seed)
        _require_id("randomization_domain", self.randomization_domain)
        if self.visible_field_allowlist != _VISIBLE_FIELDS:
            raise ValueError("visible field allowlist must exactly match the blinded contract")
        if (
            type(self.coder_contracts) is not tuple
            or not self.coder_contracts
            or any(type(value) is not CoderContract for value in self.coder_contracts)
        ):
            raise TypeError("coder_contracts must be an explicit nonempty tuple")
        if len({value.coder_id for value in self.coder_contracts}) != len(self.coder_contracts):
            raise ValueError("duplicate required coder identities")
        _require_int("required_human_coder_count", self.required_human_coder_count, minimum=1)
        _require_int("required_judge_coder_count", self.required_judge_coder_count, minimum=1)
        if (
            sum(value.role == "human" for value in self.coder_contracts)
            != self.required_human_coder_count
            or sum(value.role == "judge" for value in self.coder_contracts)
            != self.required_judge_coder_count
            or len(self.coder_contracts) < 2
        ):
            raise ValueError("coder contracts do not match required independent human/judge roles")
        if not isinstance(self.dimension_labels, Mapping) or not self.dimension_labels:
            raise ValueError("dimension_labels must be an explicit nonempty mapping")
        normalized_dimensions: dict[str, tuple[str, ...]] = {}
        for dimension, labels in self.dimension_labels.items():
            _require_id("review dimension", dimension)
            if type(labels) is not tuple or len(labels) < 2:
                raise ValueError("each review dimension needs an explicit label tuple")
            for label in labels:
                _require_id("review label", label)
            if len(set(labels)) != len(labels):
                raise ValueError("review labels must be unique within each dimension")
            normalized_dimensions[dimension] = labels
        if self.agreement_statistic != "exact_item_dimension_agreement":
            raise ValueError("unsupported agreement statistic")
        if self.agreement_scope != "all_assigned_codes_on_human_sample":
            raise ValueError("unsupported agreement scope")
        _require_fraction("agreement_threshold", self.agreement_threshold)
        if self.judge_failure_rule != "review_incomplete":
            raise ValueError("judge failure rule must fail closed as review_incomplete")
        if self.adjudication_trigger != "any_dimension_disagreement":
            raise ValueError("unsupported adjudication trigger")
        if self.aggregation_rule != "unanimous_else_adjudication":
            raise ValueError("unsupported final aggregation rule")
        if self.refusal_dimension not in normalized_dimensions:
            raise ValueError("refusal dimension is not registered")
        if type(self.refusal_positive_labels) is not tuple or not self.refusal_positive_labels:
            raise ValueError("refusal positive labels must be explicit")
        if not set(self.refusal_positive_labels) <= set(
            normalized_dimensions[self.refusal_dimension]
        ):
            raise ValueError("refusal labels are outside their authorized dimension")
        if self.contradiction_dimension not in normalized_dimensions:
            raise ValueError("contradiction dimension is not registered")
        if not isinstance(self.contradiction_label_map, Mapping) or set(
            self.contradiction_label_map
        ) != set(normalized_dimensions[self.contradiction_dimension]):
            raise ValueError("contradiction map must cover exactly its authorized labels")
        if any(
            value not in _DIRECT_CONTRADICTION for value in self.contradiction_label_map.values()
        ):
            raise ValueError("contradiction map contains an invalid direct gate label")
        object.__setattr__(
            self, "dimension_labels", _freeze(dict(sorted(normalized_dimensions.items())))
        )
        object.__setattr__(
            self,
            "contradiction_label_map",
            _freeze(dict(sorted(self.contradiction_label_map.items()))),
        )

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    def content_payload(self) -> dict[str, object]:
        payload = _record_payload(self, self._SCHEMA)
        payload["strata"] = [value.to_payload() for value in self.strata]
        payload["coder_contracts"] = [value.to_payload() for value in self.coder_contracts]
        payload["agreement_threshold"] = _fraction_payload(self.agreement_threshold)
        return payload

    @property
    def record_hash(self) -> str:
        return canonical_payload_hash(self.content_payload())

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> SemanticReviewPolicy:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata", "record_hash"}
        _exact_payload(payload, expected, cls._SCHEMA)
        if type(payload["strata"]) is not list or type(payload["coder_contracts"]) is not list:
            raise TypeError("policy repeated records must use JSON arrays")
        if (
            type(payload["dimension_labels"]) is not dict
            or type(payload["contradiction_label_map"]) is not dict
        ):
            raise TypeError("policy label declarations must use JSON objects")
        value = cls(
            policy_id=payload["policy_id"],
            policy_version=payload["policy_version"],
            strata=tuple(ReviewStratum.from_payload(x) for x in payload["strata"]),
            randomization_seed=payload["randomization_seed"],
            randomization_domain=payload["randomization_domain"],
            visible_field_allowlist=tuple(payload["visible_field_allowlist"]),
            coder_contracts=tuple(
                CoderContract.from_payload(x) for x in payload["coder_contracts"]
            ),
            required_human_coder_count=payload["required_human_coder_count"],
            required_judge_coder_count=payload["required_judge_coder_count"],
            dimension_labels={k: tuple(v) for k, v in payload["dimension_labels"].items()},
            agreement_statistic=payload["agreement_statistic"],
            agreement_scope=payload["agreement_scope"],
            agreement_threshold=_fraction_from_payload(payload["agreement_threshold"]),
            judge_failure_rule=payload["judge_failure_rule"],
            adjudication_trigger=payload["adjudication_trigger"],
            aggregation_rule=payload["aggregation_rule"],
            classifier_id=payload["classifier_id"],
            classifier_version=payload["classifier_version"],
            classifier_hash=payload["classifier_hash"],
            refusal_dimension=payload["refusal_dimension"],
            refusal_positive_labels=tuple(payload["refusal_positive_labels"]),
            contradiction_dimension=payload["contradiction_dimension"],
            contradiction_label_map=payload["contradiction_label_map"],
        )  # type: ignore[arg-type]
        if payload["record_hash"] != value.record_hash:
            raise ValueError("semantic-review policy record hash differs from content")
        return value


def _require_visible_payload(payload: object, policy: SemanticReviewPolicy) -> None:
    if type(payload) is not dict or set(payload) != set(policy.visible_field_allowlist):
        raise ValueError("visible payload keys must equal the exact blind allowlist")
    for name, value in payload.items():
        if type(value) is not str:
            raise TypeError(
                f"visible field {name} must be scalar text; nested values are forbidden"
            )


def _opaque_item_id(
    *,
    policy_id: str,
    policy_hash: str,
    randomization_seed: int,
    randomization_domain: str,
    stratum_id: str,
    probe_case_id: str,
    probe_case_hash: str,
    request_id: str,
    request_hash: str,
    response_id: str,
    response_hash: str,
    raw_response_hash: str,
    parse_id: str,
    parse_hash: str,
    visible_payload_hash: str,
) -> str:
    """Derive the one opaque identity shared by export, bindings and bridge."""
    return "blind-item-" + canonical_payload_hash(
        {
            "identity_domain": "paper1.calibration.blind-review-item.v2",
            "policy_id": policy_id,
            "policy_hash": policy_hash,
            "randomization_seed": randomization_seed,
            "randomization_domain": randomization_domain,
            "stratum_id": stratum_id,
            "probe_case_id": probe_case_id,
            "probe_case_hash": probe_case_hash,
            "request_id": request_id,
            "request_hash": request_hash,
            "response_id": response_id,
            "response_hash": response_hash,
            "raw_response_hash": raw_response_hash,
            "parse_id": parse_id,
            "parse_hash": parse_hash,
            "visible_payload_hash": visible_payload_hash,
        }
    )


@dataclass(frozen=True, slots=True)
class BlindReviewItem:
    item_id: str
    policy_hash: str
    visible_payload: Mapping[str, str]
    visible_payload_hash: str
    record_hash: str

    _SCHEMA = "paper1.calibration.blind-review-item.v1"

    def __post_init__(self) -> None:
        _require_id("item_id", self.item_id)
        _require_sha256("policy_hash", self.policy_hash)
        if not isinstance(self.visible_payload, Mapping) or set(self.visible_payload) != set(
            _VISIBLE_FIELDS
        ):
            raise ValueError("visible payload does not match exact allowlist")
        for value in self.visible_payload.values():
            if type(value) is not str:
                raise TypeError(
                    "visible payload values must be scalar text; nested fields are forbidden"
                )
        _require_sha256("visible_payload_hash", self.visible_payload_hash)
        _require_payload_hash(
            "visible_payload_hash", self.visible_payload_hash, self.visible_payload
        )
        _validate_record_hash(self, self._SCHEMA)
        object.__setattr__(
            self,
            "visible_payload",
            _freeze({name: self.visible_payload[name] for name in _VISIBLE_FIELDS}),
        )

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    @classmethod
    def create(
        cls, *, item_id: str, policy_hash: str, visible_payload: dict[str, str]
    ) -> BlindReviewItem:
        visible_hash = canonical_payload_hash(visible_payload)
        values = {
            "item_id": item_id,
            "policy_hash": policy_hash,
            "visible_payload": visible_payload,
            "visible_payload_hash": visible_hash,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": _metadata()}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**_record_payload(self, self._SCHEMA), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> BlindReviewItem:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata"}
        _exact_payload(payload, expected, cls._SCHEMA)
        if type(payload["visible_payload"]) is not dict:
            raise TypeError("blind review visible payload must use a JSON object")
        return cls(**{name: payload[name] for name in cls.__dataclass_fields__})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class HiddenReviewBinding:
    item_id: str
    item_hash: str
    policy_id: str
    policy_hash: str
    randomization_seed: int
    randomization_domain: str
    stratum_id: str
    sampling_rank_hash: str
    human_audit_selected: bool
    assigned_coder_ids: tuple[str, ...]
    probe_case_id: str
    probe_case_hash: str
    request_id: str
    request_hash: str
    response_id: str
    response_hash: str
    raw_response_hash: str
    parse_id: str
    parse_hash: str
    visible_payload_hash: str
    record_hash: str

    _SCHEMA = "paper1.calibration.hidden-review-binding.v3"

    def __post_init__(self) -> None:
        for name in (
            "item_id",
            "policy_id",
            "randomization_domain",
            "stratum_id",
            "probe_case_id",
            "request_id",
            "response_id",
            "parse_id",
        ):
            _require_id(name, getattr(self, name))
        _require_int("randomization_seed", self.randomization_seed)
        for name in (
            "item_hash",
            "policy_hash",
            "probe_case_hash",
            "request_hash",
            "response_hash",
            "raw_response_hash",
            "parse_hash",
            "visible_payload_hash",
            "sampling_rank_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if type(self.human_audit_selected) is not bool:
            raise TypeError("human_audit_selected must be a boolean")
        if (
            type(self.assigned_coder_ids) is not tuple
            or not self.assigned_coder_ids
            or any(type(value) is not str for value in self.assigned_coder_ids)
            or len(set(self.assigned_coder_ids)) != len(self.assigned_coder_ids)
        ):
            raise ValueError("assigned_coder_ids must be an exact unique tuple")
        for coder_id in self.assigned_coder_ids:
            _require_id("assigned_coder_id", coder_id)
        expected_item_id = _opaque_item_id(
            **{
                name: getattr(self, name)
                for name in (
                    "policy_id",
                    "policy_hash",
                    "randomization_seed",
                    "randomization_domain",
                    "stratum_id",
                    "probe_case_id",
                    "probe_case_hash",
                    "request_id",
                    "request_hash",
                    "response_id",
                    "response_hash",
                    "raw_response_hash",
                    "parse_id",
                    "parse_hash",
                    "visible_payload_hash",
                )
            }
        )
        if self.item_id != expected_item_id:
            raise ValueError("opaque item identity does not bind hidden upstream hash evidence")
        _validate_record_hash(self, self._SCHEMA)

    @classmethod
    def create(
        cls,
        policy: SemanticReviewPolicy,
        item: BlindReviewItem,
        stratum_id: str,
        case: ProbeCase,
        parse: ProbeParseEvidence,
        *,
        human_audit_selected: bool,
    ) -> HiddenReviewBinding:
        stratum = next((value for value in policy.strata if value.stratum_id == stratum_id), None)
        if stratum is None:
            raise ValueError("hidden binding stratum is outside policy")
        judge_ids = tuple(
            contract.coder_id for contract in policy.coder_contracts if contract.role == "judge"
        )
        human_ids = tuple(
            contract.coder_id for contract in policy.coder_contracts if contract.role == "human"
        )
        assigned_coder_ids = judge_ids + (human_ids if human_audit_selected else ())
        values = {
            "item_id": item.item_id,
            "item_hash": item.record_hash,
            "policy_id": policy.policy_id,
            "policy_hash": policy.record_hash,
            "randomization_seed": policy.randomization_seed,
            "randomization_domain": policy.randomization_domain,
            "stratum_id": stratum_id,
            "sampling_rank_hash": _sampling_rank(policy, stratum, case),
            "human_audit_selected": human_audit_selected,
            "assigned_coder_ids": assigned_coder_ids,
            "probe_case_id": case.probe_case_id,
            "probe_case_hash": case.record_hash,
            "request_id": parse.request_id,
            "request_hash": parse.request_hash,
            "response_id": parse.response_id,
            "response_hash": parse.response_hash,
            "raw_response_hash": parse.raw_response_hash,
            "parse_id": parse.parse_evidence_id,
            "parse_hash": parse.record_hash,
            "visible_payload_hash": item.visible_payload_hash,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": _metadata()}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**_record_payload(self, self._SCHEMA), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> HiddenReviewBinding:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata"}
        _exact_payload(payload, expected, cls._SCHEMA)
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        if type(payload["assigned_coder_ids"]) is not list:
            raise TypeError("assigned_coder_ids must use a JSON array")
        values["assigned_coder_ids"] = tuple(payload["assigned_coder_ids"])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class BlindReviewExport:
    policy_id: str
    policy_version: str
    policy_hash: str
    specification_hash: str
    specification_semantic_review_policy_hash: str
    run_id: str
    run_evidence_hash: str
    items: tuple[BlindReviewItem, ...]
    export_hash: str

    _SCHEMA = "paper1.calibration.blind-review-export.v1"

    def __post_init__(self) -> None:
        for name in ("policy_id", "policy_version", "run_id"):
            _require_id(name, getattr(self, name))
        for name in (
            "policy_hash",
            "specification_hash",
            "specification_semantic_review_policy_hash",
            "run_evidence_hash",
            "export_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if self.policy_hash != self.specification_semantic_review_policy_hash:
            raise ValueError("policy hash differs from specification semantic-review policy hash")
        if (
            type(self.items) is not tuple
            or not self.items
            or any(type(x) is not BlindReviewItem for x in self.items)
        ):
            raise TypeError("blind review export needs a nonempty item tuple")
        if len({x.item_id for x in self.items}) != len(self.items):
            raise ValueError("duplicate blind review items")
        if any(x.policy_hash != self.policy_hash for x in self.items):
            raise ValueError("blind review item policy hash drift")
        _require_payload_hash("export_hash", self.export_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    def content_payload(self) -> dict[str, object]:
        payload = _record_payload(self, self._SCHEMA, omit={"export_hash"})
        payload["items"] = [item.to_payload() for item in self.items]
        return payload

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "export_hash": self.export_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> BlindReviewExport:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata"}
        _exact_payload(payload, expected, cls._SCHEMA)
        if type(payload["items"]) is not list:
            raise TypeError("blind review export items must use a JSON array")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["items"] = tuple(BlindReviewItem.from_payload(x) for x in payload["items"])
        return cls(**values)  # type: ignore[arg-type]


def _validate_labels(
    policy: SemanticReviewPolicy, labels: object, *, allow_empty: bool = False
) -> None:
    if not isinstance(labels, Mapping):
        raise TypeError("review labels must use an exact mapping")
    if allow_empty and not labels:
        return
    if set(labels) != set(policy.dimension_labels):
        raise ValueError("review label dimensions differ from policy")
    for dimension, value in labels.items():
        if type(value) is not str:
            raise TypeError("review label values must be strings")
        if value not in policy.dimension_labels[dimension]:
            raise ValueError("review label is outside the policy label set")


@dataclass(frozen=True, slots=True)
class IndependentCode:
    code_id: str
    item_id: str
    item_hash: str
    policy_id: str
    policy_hash: str
    export_hash: str
    coder_id: str
    coder_role: str
    coder_contract_hash: str
    timestamp: str
    evidence_identity: str
    judge_request_id: str | None
    judge_order_id: str | None
    provider_output_artifact_id: str | None
    provider_output_artifact_hash: str | None
    labels: Mapping[str, str]
    raw_evidence_hash: str
    status: str
    failure_code: str | None
    record_hash: str

    _SCHEMA = "paper1.calibration.independent-code.v1"

    def __post_init__(self) -> None:
        for name in ("code_id", "item_id", "policy_id", "coder_id", "evidence_identity"):
            _require_id(name, getattr(self, name))
        for name in (
            "item_hash",
            "policy_hash",
            "export_hash",
            "coder_contract_hash",
            "raw_evidence_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if self.coder_role not in {"human", "judge"}:
            raise ValueError("independent code role must be human or judge")
        judge_fields = (
            "judge_request_id",
            "judge_order_id",
            "provider_output_artifact_id",
            "provider_output_artifact_hash",
        )
        if self.coder_role == "human":
            if any(getattr(self, name) is not None for name in judge_fields):
                raise ValueError("human code judge provenance must be explicitly null")
        else:
            if any(getattr(self, name) is None for name in judge_fields):
                raise ValueError("judge code requires request/order/provider-output provenance")
            for name in (
                "judge_request_id",
                "judge_order_id",
                "provider_output_artifact_id",
            ):
                _require_id(name, getattr(self, name))
            _require_sha256("provider_output_artifact_hash", self.provider_output_artifact_hash)
        _require_timestamp("timestamp", self.timestamp)
        if not isinstance(self.labels, Mapping):
            raise TypeError("independent labels must be an exact mapping")
        if any(type(k) is not str or type(v) is not str for k, v in self.labels.items()):
            raise TypeError("independent dimension labels must be strings")
        if self.status not in {"completed", "failed"}:
            raise ValueError("independent code status must be completed or failed")
        if self.status == "completed":
            if not self.labels or self.failure_code is not None:
                raise ValueError("completed independent code requires labels without failure")
        else:
            if self.labels or not self.failure_code:
                raise ValueError("failed independent code requires only a failure code")
            _require_id("failure_code", self.failure_code)
        _validate_record_hash(self, self._SCHEMA)
        object.__setattr__(self, "labels", _freeze(dict(sorted(self.labels.items()))))

    @classmethod
    def create(
        cls,
        *,
        item: BlindReviewItem,
        policy: SemanticReviewPolicy,
        export_hash: str,
        coder_id: str,
        timestamp: str,
        evidence_identity: str,
        judge_request_id: str | None,
        judge_order_id: str | None,
        provider_output_artifact_id: str | None,
        provider_output_artifact_hash: str | None,
        labels: Mapping[str, str],
        raw_evidence_hash: str,
        status: str,
        failure_code: str | None,
    ) -> IndependentCode:
        contracts = {x.coder_id: x for x in policy.coder_contracts}
        if coder_id not in contracts:
            raise ValueError("coder is outside the required coder contract")
        contract = contracts[coder_id]
        if item.policy_hash != policy.record_hash:
            raise ValueError("item/policy hash mismatch")
        _validate_labels(policy, labels, allow_empty=status == "failed")
        identity = {
            "item_id": item.item_id,
            "item_hash": item.record_hash,
            "policy_id": policy.policy_id,
            "policy_hash": policy.record_hash,
            "export_hash": export_hash,
            "coder_id": coder_id,
            "coder_role": contract.role,
            "coder_contract_hash": contract.record_hash,
            "timestamp": timestamp,
            "evidence_identity": evidence_identity,
            "judge_request_id": judge_request_id,
            "judge_order_id": judge_order_id,
            "provider_output_artifact_id": provider_output_artifact_id,
            "provider_output_artifact_hash": provider_output_artifact_hash,
            "labels": dict(sorted(labels.items())),
            "raw_evidence_hash": raw_evidence_hash,
            "status": status,
            "failure_code": failure_code,
        }
        code_id = "independent-code-" + canonical_payload_hash(identity)
        values = {"code_id": code_id, **identity}
        content = {"schema_version": cls._SCHEMA, **values, "metadata": _metadata()}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**_record_payload(self, self._SCHEMA), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> IndependentCode:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata"}
        _exact_payload(payload, expected, cls._SCHEMA)
        if type(payload["labels"]) is not dict:
            raise TypeError("independent labels must use a JSON object")
        return cls(**{name: payload[name] for name in cls.__dataclass_fields__})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Adjudication:
    adjudication_id: str
    item_id: str
    item_hash: str
    policy_hash: str
    export_hash: str
    independent_code_hashes: tuple[str, ...]
    adjudicator_id: str
    timestamp: str
    labels: Mapping[str, str]
    reason: str
    evidence_hash: str
    record_hash: str

    _SCHEMA = "paper1.calibration.adjudication.v1"

    def __post_init__(self) -> None:
        for name in ("adjudication_id", "item_id", "adjudicator_id"):
            _require_id(name, getattr(self, name))
        for name in ("item_hash", "policy_hash", "export_hash", "evidence_hash"):
            _require_sha256(name, getattr(self, name))
        if type(self.independent_code_hashes) is not tuple or not self.independent_code_hashes:
            raise ValueError("adjudication must bind all independent code hashes")
        for digest in self.independent_code_hashes:
            _require_sha256("independent_code_hash", digest)
        _require_timestamp("timestamp", self.timestamp)
        _require_string("adjudication reason", self.reason)
        if not isinstance(self.labels, Mapping) or not self.labels:
            raise ValueError("adjudication requires exact final labels")
        _validate_record_hash(self, self._SCHEMA)
        object.__setattr__(self, "labels", _freeze(dict(sorted(self.labels.items()))))

    @classmethod
    def create(
        cls,
        *,
        bundle: SemanticReviewBundle,
        item_id: str,
        adjudicator_id: str,
        timestamp: str,
        labels: Mapping[str, str],
        reason: str,
        evidence_hash: str,
    ) -> Adjudication:
        disputed = _disputed_items(bundle)
        if item_id not in disputed:
            raise ValueError("adjudication is accepted only for a required disputed item")
        _validate_labels(bundle.policy, labels)
        item = next(x for x in bundle.review_export.items if x.item_id == item_id)
        code_hashes = tuple(
            sorted(x.record_hash for x in bundle.independent_codes if x.item_id == item_id)
        )
        identity = {
            "item_id": item_id,
            "item_hash": item.record_hash,
            "policy_hash": bundle.policy.record_hash,
            "export_hash": bundle.review_export.export_hash,
            "independent_code_hashes": code_hashes,
            "adjudicator_id": adjudicator_id,
            "timestamp": timestamp,
            "labels": dict(sorted(labels.items())),
            "reason": reason,
            "evidence_hash": evidence_hash,
        }
        adjudication_id = "adjudication-" + canonical_payload_hash(identity)
        values = {"adjudication_id": adjudication_id, **identity}
        content = {"schema_version": cls._SCHEMA, **values, "metadata": _metadata()}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**_record_payload(self, self._SCHEMA), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Adjudication:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata"}
        _exact_payload(payload, expected, cls._SCHEMA)
        if (
            type(payload["independent_code_hashes"]) is not list
            or type(payload["labels"]) is not dict
        ):
            raise TypeError("adjudication repeated fields require JSON arrays/objects")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["independent_code_hashes"] = tuple(payload["independent_code_hashes"])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class FinalSemanticLabel:
    item_id: str
    item_hash: str
    source_hashes: tuple[str, ...]
    labels: Mapping[str, str]
    record_hash: str

    _SCHEMA = "paper1.calibration.final-semantic-label.v1"

    def __post_init__(self) -> None:
        _require_id("item_id", self.item_id)
        _require_sha256("item_hash", self.item_hash)
        if type(self.source_hashes) is not tuple or not self.source_hashes:
            raise ValueError("final semantic label requires source hashes")
        for digest in self.source_hashes:
            _require_sha256("source_hash", digest)
        if not isinstance(self.labels, Mapping) or not self.labels:
            raise ValueError("final semantic label requires labels")
        _validate_record_hash(self, self._SCHEMA)
        object.__setattr__(self, "labels", _freeze(dict(sorted(self.labels.items()))))

    @classmethod
    def create(
        cls, item: BlindReviewItem, sources: tuple[str, ...], labels: Mapping[str, str]
    ) -> FinalSemanticLabel:
        values = {
            "item_id": item.item_id,
            "item_hash": item.record_hash,
            "source_hashes": tuple(sorted(sources)),
            "labels": dict(sorted(labels.items())),
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": _metadata()}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**_record_payload(self, self._SCHEMA), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FinalSemanticLabel:
        expected = {f.name for f in fields(cls)} | {"schema_version", "metadata"}
        _exact_payload(payload, expected, cls._SCHEMA)
        if type(payload["source_hashes"]) is not list or type(payload["labels"]) is not dict:
            raise TypeError("final semantic label repeated fields require JSON arrays/objects")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["source_hashes"] = tuple(payload["source_hashes"])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class SemanticReviewBundle:
    policy: SemanticReviewPolicy
    review_export: BlindReviewExport
    hidden_bindings: tuple[HiddenReviewBinding, ...]
    independent_codes: tuple[IndependentCode, ...]
    adjudications: tuple[Adjudication, ...]
    agreement: Fraction | None
    status: str
    final_labels: tuple[FinalSemanticLabel, ...]

    _SCHEMA = "paper1.calibration.semantic-review-bundle.v1"

    def __post_init__(self) -> None:
        if (
            type(self.policy) is not SemanticReviewPolicy
            or type(self.review_export) is not BlindReviewExport
        ):
            raise TypeError("semantic review bundle requires exact policy and export records")
        if self.review_export.policy_hash != self.policy.record_hash:
            raise ValueError("semantic review bundle policy/export hash drift")
        for name, record_type in (
            ("hidden_bindings", HiddenReviewBinding),
            ("independent_codes", IndependentCode),
            ("adjudications", Adjudication),
            ("final_labels", FinalSemanticLabel),
        ):
            value = getattr(self, name)
            if type(value) is not tuple or any(type(x) is not record_type for x in value):
                raise TypeError(f"{name} must be an exact record tuple")
        item_ids = {x.item_id for x in self.review_export.items}
        if {x.item_id for x in self.hidden_bindings} != item_ids or len(
            self.hidden_bindings
        ) != len(item_ids):
            raise ValueError("hidden bindings must cover every exported item exactly once")
        if self.agreement is not None:
            _require_fraction("agreement", self.agreement)
        if self.status not in {
            "awaiting_codes",
            "review_incomplete",
            "adjudication_required",
            "complete",
        }:
            raise ValueError("invalid semantic review bundle status")
        item_map = {item.item_id: item for item in self.review_export.items}
        stratum_map = {stratum.stratum_id: stratum for stratum in self.policy.strata}
        judge_ids = tuple(
            contract.coder_id
            for contract in self.policy.coder_contracts
            if contract.role == "judge"
        )
        human_ids = tuple(
            contract.coder_id
            for contract in self.policy.coder_contracts
            if contract.role == "human"
        )
        if any(
            binding.item_hash != item_map[binding.item_id].record_hash
            or binding.policy_id != self.policy.policy_id
            or binding.policy_hash != self.policy.record_hash
            or binding.randomization_seed != self.policy.randomization_seed
            or binding.randomization_domain != self.policy.randomization_domain
            or binding.visible_payload_hash != item_map[binding.item_id].visible_payload_hash
            or binding.stratum_id not in stratum_map
            or binding.sampling_rank_hash
            != _sampling_rank_fields(
                self.policy,
                stratum_map[binding.stratum_id],
                binding.probe_case_id,
                binding.probe_case_hash,
            )
            or binding.assigned_coder_ids
            != judge_ids + (human_ids if binding.human_audit_selected else ())
            for binding in self.hidden_bindings
        ):
            raise ValueError("hidden binding item/policy/sampling/assignment hash drift")
        stratum_counts = {
            stratum.stratum_id: sum(
                binding.stratum_id == stratum.stratum_id and binding.human_audit_selected
                for binding in self.hidden_bindings
            )
            for stratum in self.policy.strata
        }
        if set(binding.stratum_id for binding in self.hidden_bindings) != set(
            stratum_counts
        ) or any(
            stratum_counts[stratum.stratum_id] != stratum.sample_count
            for stratum in self.policy.strata
        ):
            raise ValueError("human audit assignments differ from the frozen sampling policy")
        coder_contracts = {contract.coder_id: contract for contract in self.policy.coder_contracts}
        coder_ids = set(coder_contracts)
        code_pairs: set[tuple[str, str]] = set()
        for code in self.independent_codes:
            IndependentCode.from_payload(code.to_payload())
            pair = (code.item_id, code.coder_id)
            if pair in code_pairs:
                raise ValueError("duplicate independent coder/item binding")
            code_pairs.add(pair)
            if code.item_id not in item_map or code.coder_id not in coder_ids:
                raise ValueError("independent code has unexpected item or coder")
            contract = coder_contracts[code.coder_id]
            if (
                code.item_hash != item_map[code.item_id].record_hash
                or code.policy_id != self.policy.policy_id
                or code.policy_hash != self.policy.record_hash
                or code.export_hash != self.review_export.export_hash
                or code.coder_role != contract.role
                or code.coder_contract_hash != contract.record_hash
            ):
                raise ValueError("independent code item/policy/coder contract hash drift")
            _validate_labels(self.policy, code.labels, allow_empty=code.status == "failed")
        expected_pairs = {
            (binding.item_id, coder_id)
            for binding in self.hidden_bindings
            for coder_id in binding.assigned_coder_ids
        }
        codes_complete = code_pairs == expected_pairs and all(
            code.status == "completed" for code in self.independent_codes
        )
        derived_agreement: Fraction | None = None
        disputed: set[str] = set()
        if codes_complete:
            numerator = 0
            audited_item_ids = {
                binding.item_id for binding in self.hidden_bindings if binding.human_audit_selected
            }
            denominator = len(audited_item_ids) * len(self.policy.dimension_labels)
            for item_id in item_map:
                item_codes = [code for code in self.independent_codes if code.item_id == item_id]
                for dimension in self.policy.dimension_labels:
                    labels = {code.labels[dimension] for code in item_codes}
                    if len(labels) > 1:
                        disputed.add(item_id)
                    if item_id in audited_item_ids:
                        numerator += len(labels) == 1
            derived_agreement = Fraction(numerator, denominator)
        if self.agreement != derived_agreement:
            raise ValueError("agreement does not match exact independent codes")
        adjudication_map: dict[str, Adjudication] = {}
        for adjudication in self.adjudications:
            if adjudication.item_id in adjudication_map:
                raise ValueError("duplicate adjudication item")
            adjudication_map[adjudication.item_id] = adjudication
            if adjudication.item_id not in disputed:
                raise ValueError("adjudication is not bound to a disputed item")
            expected_hashes = tuple(
                sorted(
                    code.record_hash
                    for code in self.independent_codes
                    if code.item_id == adjudication.item_id
                )
            )
            if (
                adjudication.item_hash != item_map[adjudication.item_id].record_hash
                or adjudication.policy_hash != self.policy.record_hash
                or adjudication.export_hash != self.review_export.export_hash
                or adjudication.independent_code_hashes != expected_hashes
            ):
                raise ValueError("adjudication hash binding drift")
            _validate_labels(self.policy, adjudication.labels)
        if self.status == "awaiting_codes":
            if self.independent_codes or self.adjudications or self.final_labels:
                raise ValueError("awaiting_codes status cannot contain review results")
        elif self.status == "review_incomplete":
            if self.adjudications or self.final_labels:
                raise ValueError("review_incomplete cannot contain adjudication or final labels")
        elif self.status == "adjudication_required":
            if (
                not codes_complete
                or derived_agreement is None
                or derived_agreement < self.policy.agreement_threshold
                or not (disputed - set(adjudication_map))
                or self.final_labels
            ):
                raise ValueError("adjudication_required status differs from review evidence")
        else:
            if (
                not codes_complete
                or derived_agreement is None
                or derived_agreement < self.policy.agreement_threshold
                or disputed != set(adjudication_map)
                or set(label.item_id for label in self.final_labels) != set(item_map)
                or len(self.final_labels) != len(item_map)
            ):
                raise ValueError("complete status lacks complete, adjudicated final evidence")
            for final in self.final_labels:
                item = item_map[final.item_id]
                if final.item_hash != item.record_hash:
                    raise ValueError("final semantic label item hash drift")
                _validate_labels(self.policy, final.labels)
                item_codes = tuple(
                    code for code in self.independent_codes if code.item_id == final.item_id
                )
                if final.item_id in adjudication_map:
                    source = adjudication_map[final.item_id]
                    expected_sources = (source.record_hash,)
                    expected_labels = source.labels
                else:
                    expected_sources = tuple(sorted(code.record_hash for code in item_codes))
                    expected_labels = {
                        dimension: item_codes[0].labels[dimension]
                        for dimension in self.policy.dimension_labels
                    }
                if final.source_hashes != expected_sources or final.labels != expected_labels:
                    raise ValueError("final semantic label differs from deterministic aggregation")

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    @property
    def record_hash(self) -> str:
        return canonical_payload_hash(self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "policy": self.policy.to_payload(),
            "review_export": self.review_export.to_payload(),
            "hidden_bindings": [x.to_payload() for x in self.hidden_bindings],
            "independent_codes": [x.to_payload() for x in self.independent_codes],
            "adjudications": [x.to_payload() for x in self.adjudications],
            "agreement": _fraction_payload(self.agreement),
            "status": self.status,
            "final_labels": [x.to_payload() for x in self.final_labels],
            "metadata": _metadata(),
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> SemanticReviewBundle:
        expected = {
            "schema_version",
            "policy",
            "review_export",
            "hidden_bindings",
            "independent_codes",
            "adjudications",
            "agreement",
            "status",
            "final_labels",
            "metadata",
            "record_hash",
        }
        _exact_payload(payload, expected, cls._SCHEMA)
        for name in ("hidden_bindings", "independent_codes", "adjudications", "final_labels"):
            if type(payload[name]) is not list:
                raise TypeError(f"semantic review bundle {name} must use a JSON array")
        value = cls(
            policy=SemanticReviewPolicy.from_payload(payload["policy"]),
            review_export=BlindReviewExport.from_payload(payload["review_export"]),
            hidden_bindings=tuple(
                HiddenReviewBinding.from_payload(x) for x in payload["hidden_bindings"]
            ),
            independent_codes=tuple(
                IndependentCode.from_payload(x) for x in payload["independent_codes"]
            ),
            adjudications=tuple(Adjudication.from_payload(x) for x in payload["adjudications"]),
            agreement=_fraction_from_payload(payload["agreement"]),
            status=payload["status"],
            final_labels=tuple(FinalSemanticLabel.from_payload(x) for x in payload["final_labels"]),
        )  # type: ignore[arg-type]
        if payload["record_hash"] != value.record_hash:
            raise ValueError("semantic review bundle record hash differs from content")
        return value


def _case_matches(case: ProbeCase, stratum: ReviewStratum) -> bool:
    return all(getattr(case, key) == value for key, value in stratum.selectors.items())


def _sampling_rank_fields(
    policy: SemanticReviewPolicy,
    stratum: ReviewStratum,
    probe_case_id: str,
    probe_case_hash: str,
) -> str:
    """Return a pre-execution-only deterministic sampling and assignment rank."""
    return canonical_payload_hash(
        {
            "schema_version": "paper1.calibration.review-sampling-rank.v1",
            "randomization_domain": policy.randomization_domain,
            "randomization_seed": policy.randomization_seed,
            "policy_id": policy.policy_id,
            "policy_hash": policy.record_hash,
            "stratum_id": stratum.stratum_id,
            "probe_case_id": probe_case_id,
            "probe_case_hash": probe_case_hash,
        }
    )


def _sampling_rank(policy: SemanticReviewPolicy, stratum: ReviewStratum, case: ProbeCase) -> str:
    return _sampling_rank_fields(policy, stratum, case.probe_case_id, case.record_hash)


def _topic_text(spec: Mapping[str, object], case: ProbeCase) -> str:
    for raw in spec["topic_candidates"]:  # type: ignore[union-attr]
        topic = ProbeTopicCandidate.create(
            construct=raw["construct"],
            fact_card=raw["fact_card"],
            statements=tuple(raw["statements"]),
            stance_labels_1_7=tuple(raw["stance_labels_1_7"]),
        )
        if topic.candidate_id == case.candidate_id:
            return raw["fact_card"] + "\n" + raw["statements"][case.variant_index]
    raise ValueError("case candidate does not bind a specification topic")


def _semantic_visible_blocks(spec: Mapping[str, object], case: ProbeCase) -> tuple[str, str]:
    """Resolve exact identity/history blocks from frozen semantic declarations."""
    if case.case_family == "topic_quality":
        if not any(
            case.scenario_id == "topic-" + raw["candidate_key"]
            for raw in spec["topic_candidates"]  # type: ignore[union-attr]
        ):
            raise ValueError("topic case semantic identity is not declared")
        return "", ""
    conditions = spec["persona_conditions"]
    factor_orders = spec["factor_orders"]
    if case.case_family == "identity":
        for condition in conditions:  # type: ignore[union-attr]
            for factor_order in factor_orders:  # type: ignore[union-attr]
                expected = f"identity-{condition['condition_id']}-{factor_order['factor_order_id']}"
                if case.scenario_id == expected:
                    identity = (
                        spec["persona"]["identity_block"]  # type: ignore[index]
                        if condition["identity_present"]
                        else ""
                    )
                    return identity, ""
        raise ValueError("identity case semantic identity is not declared")
    if case.case_family == "continuity":
        for condition in conditions:  # type: ignore[union-attr]
            for wording in spec["persona"]["continuity_blocks"]:  # type: ignore[index,union-attr]
                for factor_order in factor_orders:  # type: ignore[union-attr]
                    for scenario in spec["continuity_scenarios"]:  # type: ignore[union-attr]
                        expected = (
                            f"continuity-{condition['condition_id']}-{wording['wording_id']}-"
                            f"{factor_order['factor_order_id']}-{scenario['scenario_id']}"
                        )
                        if case.scenario_id == expected:
                            identity = (
                                spec["persona"]["identity_block"]  # type: ignore[index]
                                if condition["identity_present"]
                                else ""
                            )
                            return identity, scenario["history"]
        raise ValueError("continuity case semantic identity is not declared")
    raise ValueError("case family has no semantic-review visible declaration")


def _build_expected_review_export(
    specification: ArtifactEnvelope,
    cases: tuple[ProbeCase, ...],
    run: ProbeRunProjection,
    policy: SemanticReviewPolicy,
) -> tuple[BlindReviewExport, tuple[HiddenReviewBinding, ...]]:
    """Replay the sole deterministic sampling/export algorithm from upstream evidence."""
    if type(policy) is not SemanticReviewPolicy:
        raise TypeError("policy must be a SemanticReviewPolicy")
    if not isinstance(specification, ArtifactEnvelope):
        raise TypeError("specification must be an ArtifactEnvelope")
    validated = load_probe_specification(specification.to_payload()["payload"])
    if validated.output_hash != specification.output_hash:
        raise ValueError("specification hash drift")
    if specification.payload["policy_hashes"]["semantic_review_policy"] != policy.record_hash:
        raise ValueError("semantic-review policy does not match the specification policy hash")
    if type(cases) is not tuple or not cases or any(type(x) is not ProbeCase for x in cases):
        raise TypeError("cases must be a nonempty tuple of ProbeCase")
    authoritative = {x.probe_case_id: x for x in expand_probe_cases(validated)}
    if len({x.probe_case_id for x in cases}) != len(cases):
        raise ValueError("duplicate input cases")
    for case in cases:
        if (
            case.probe_case_id not in authoritative
            or case.to_payload() != authoritative[case.probe_case_id].to_payload()
        ):
            raise ValueError("case differs from validated specification expansion")
    folded = fold_case_attempts(cases, run)
    eligible = [(case, folded[case.probe_case_id].final_parse) for case in cases]
    eligible = [(case, parse) for case, parse in eligible if parse is not None and parse.success]
    classified: list[tuple[ReviewStratum, ProbeCase, ProbeParseEvidence]] = []
    for case, parse in eligible:
        matches = tuple(stratum for stratum in policy.strata if _case_matches(case, stratum))
        if len(matches) != 1:
            raise ValueError("every eligible case must match exactly one review stratum")
        classified.append((matches[0], case, parse))
    human_selected: set[str] = set()
    for stratum in policy.strata:
        pool = [(case, parse) for assigned, case, parse in classified if assigned == stratum]
        pool.sort(key=lambda pair: _sampling_rank(policy, stratum, pair[0]))
        if len(pool) < stratum.sample_count:
            raise ValueError(f"insufficient eligible items for stratum {stratum.stratum_id}")
        human_selected.update(case.probe_case_id for case, _ in pool[: stratum.sample_count])
    items_and_bindings: list[tuple[BlindReviewItem, HiddenReviewBinding]] = []
    for stratum, case, parse in classified:
        attempt = next(
            a
            for a in run.attempts
            if a.probe_case_id == case.probe_case_id
            and a.parse_evidence is not None
            and a.parse_evidence.record_hash == parse.record_hash
        )
        if attempt.response.raw_response is None:
            raise ValueError("review-eligible parse lacks bound response text")
        identity_text, history_text = _semantic_visible_blocks(specification.payload, case)
        visible = {
            "topic_text": _topic_text(specification.payload, case),
            "history_text": history_text,
            "identity_text": identity_text,
            "response_text": attempt.response.raw_response,
        }
        _require_visible_payload(visible, policy)
        visible_payload_hash = canonical_payload_hash(visible)
        item_id = _opaque_item_id(
            policy_id=policy.policy_id,
            policy_hash=policy.record_hash,
            randomization_seed=policy.randomization_seed,
            randomization_domain=policy.randomization_domain,
            stratum_id=stratum.stratum_id,
            probe_case_id=case.probe_case_id,
            probe_case_hash=case.record_hash,
            request_id=parse.request_id,
            request_hash=parse.request_hash,
            response_id=parse.response_id,
            response_hash=parse.response_hash,
            raw_response_hash=parse.raw_response_hash,
            parse_id=parse.parse_evidence_id,
            parse_hash=parse.record_hash,
            visible_payload_hash=visible_payload_hash,
        )
        item = BlindReviewItem.create(
            item_id=item_id,
            policy_hash=policy.record_hash,
            visible_payload=visible,
        )
        items_and_bindings.append(
            (
                item,
                HiddenReviewBinding.create(
                    policy,
                    item,
                    stratum.stratum_id,
                    case,
                    parse,
                    human_audit_selected=case.probe_case_id in human_selected,
                ),
            )
        )
    binding_by_item = {binding.item_id: binding for _, binding in items_and_bindings}
    items_and_bindings.sort(key=lambda pair: binding_by_item[pair[0].item_id].sampling_rank_hash)
    items = tuple(pair[0] for pair in items_and_bindings)
    bindings = tuple(pair[1] for pair in items_and_bindings)
    export_values = {
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "policy_hash": policy.record_hash,
        "specification_hash": specification.output_hash,
        "specification_semantic_review_policy_hash": specification.payload["policy_hashes"][
            "semantic_review_policy"
        ],
        "run_id": run.probe_run_id,
        "run_evidence_hash": run.run_evidence_hash,
        "items": items,
    }
    export_content = {
        "schema_version": BlindReviewExport._SCHEMA,
        **{**export_values, "items": [item.to_payload() for item in items]},
        "metadata": _metadata(),
    }
    review_export = BlindReviewExport(
        **export_values,
        export_hash=canonical_payload_hash(export_content),  # type: ignore[arg-type]
    )
    return review_export, bindings


def export_blind_review(
    specification: ArtifactEnvelope,
    cases: tuple[ProbeCase, ...],
    run: ProbeRunProjection,
    policy: SemanticReviewPolicy,
) -> SemanticReviewBundle:
    """Validate upstream evidence and create a deterministic, strictly blinded export."""
    review_export, bindings = _build_expected_review_export(specification, cases, run, policy)
    return SemanticReviewBundle(policy, review_export, bindings, (), (), None, "awaiting_codes", ())


def _disputed_items(bundle: SemanticReviewBundle) -> set[str]:
    assigned = {
        binding.item_id: set(binding.assigned_coder_ids) for binding in bundle.hidden_bindings
    }
    result: set[str] = set()
    for item in bundle.review_export.items:
        codes = [
            x
            for x in bundle.independent_codes
            if x.item_id == item.item_id and x.status == "completed"
        ]
        if {x.coder_id for x in codes} != assigned[item.item_id]:
            continue
        if any(len({x.labels[d] for x in codes}) > 1 for d in bundle.policy.dimension_labels):
            result.add(item.item_id)
    return result


def _final_labels(
    bundle: SemanticReviewBundle, adjudications: tuple[Adjudication, ...]
) -> tuple[FinalSemanticLabel, ...]:
    adjudicated = {x.item_id: x for x in adjudications}
    result = []
    for item in bundle.review_export.items:
        codes = tuple(x for x in bundle.independent_codes if x.item_id == item.item_id)
        if item.item_id in adjudicated:
            decision = adjudicated[item.item_id]
            result.append(FinalSemanticLabel.create(item, (decision.record_hash,), decision.labels))
        else:
            result.append(
                FinalSemanticLabel.create(
                    item,
                    tuple(x.record_hash for x in codes),
                    {d: codes[0].labels[d] for d in bundle.policy.dimension_labels},
                )
            )
    return tuple(result)


def items_for_coder(bundle: SemanticReviewBundle, coder_id: str) -> tuple[BlindReviewItem, ...]:
    """Return only the blinded items assigned to one registered independent coder."""
    if type(bundle) is not SemanticReviewBundle:
        raise TypeError("bundle must be a SemanticReviewBundle")
    _require_id("coder_id", coder_id)
    if coder_id not in {contract.coder_id for contract in bundle.policy.coder_contracts}:
        raise ValueError("coder is outside the review policy")
    assigned = {
        binding.item_id
        for binding in bundle.hidden_bindings
        if coder_id in binding.assigned_coder_ids
    }
    return tuple(item for item in bundle.review_export.items if item.item_id in assigned)


def import_review_codes(
    bundle: SemanticReviewBundle, codes: tuple[IndependentCode, ...]
) -> SemanticReviewBundle:
    """Import isolated coder records and derive agreement without favorable imputation."""
    if type(bundle) is not SemanticReviewBundle or bundle.status != "awaiting_codes":
        raise ValueError("codes can only be imported into an awaiting semantic-review bundle")
    if type(codes) is not tuple or any(type(x) is not IndependentCode for x in codes):
        raise TypeError("codes must be an exact IndependentCode tuple")
    item_map = {x.item_id: x for x in bundle.review_export.items}
    coder_ids = {x.coder_id for x in bundle.policy.coder_contracts}
    expected = {
        (binding.item_id, coder_id)
        for binding in bundle.hidden_bindings
        for coder_id in binding.assigned_coder_ids
    }
    pairs: set[tuple[str, str]] = set()
    for code in codes:
        if code.item_id not in item_map:
            raise ValueError("unexpected item in independent codes")
        if code.coder_id not in coder_ids:
            raise ValueError("unexpected coder in independent codes")
        if (code.item_id, code.coder_id) in pairs:
            raise ValueError("duplicate coder/item independent code")
        if (code.item_id, code.coder_id) not in expected:
            raise ValueError("independent code is outside its assigned coder scope")
        pairs.add((code.item_id, code.coder_id))
        if (
            code.item_hash != item_map[code.item_id].record_hash
            or code.policy_id != bundle.policy.policy_id
            or code.policy_hash != bundle.policy.record_hash
            or code.export_hash != bundle.review_export.export_hash
        ):
            raise ValueError("independent code item/policy/export hash drift")
        _validate_labels(bundle.policy, code.labels, allow_empty=code.status == "failed")
    complete = pairs == expected and all(x.status == "completed" for x in codes)
    ordered = tuple(sorted(codes, key=lambda x: (x.item_id, x.coder_id)))
    if not complete:
        return SemanticReviewBundle(
            bundle.policy,
            bundle.review_export,
            bundle.hidden_bindings,
            ordered,
            (),
            None,
            "review_incomplete",
            (),
        )
    numerator = 0
    audited_item_ids = {
        binding.item_id for binding in bundle.hidden_bindings if binding.human_audit_selected
    }
    denominator = len(audited_item_ids) * len(bundle.policy.dimension_labels)
    for item_id in audited_item_ids:
        item_codes = [x for x in ordered if x.item_id == item_id]
        numerator += sum(
            len({x.labels[dimension] for x in item_codes}) == 1
            for dimension in bundle.policy.dimension_labels
        )
    agreement = Fraction(numerator, denominator)
    staged = SemanticReviewBundle(
        bundle.policy,
        bundle.review_export,
        bundle.hidden_bindings,
        ordered,
        (),
        agreement,
        "review_incomplete",
        (),
    )
    if agreement < bundle.policy.agreement_threshold:
        return staged
    if _disputed_items(staged):
        return SemanticReviewBundle(
            bundle.policy,
            bundle.review_export,
            bundle.hidden_bindings,
            ordered,
            (),
            agreement,
            "adjudication_required",
            (),
        )
    final = _final_labels(staged, ())
    return SemanticReviewBundle(
        bundle.policy,
        bundle.review_export,
        bundle.hidden_bindings,
        ordered,
        (),
        agreement,
        "complete",
        final,
    )


def append_adjudication(
    bundle: SemanticReviewBundle, adjudication: Adjudication
) -> SemanticReviewBundle:
    """Append one required adjudication while preserving all independent codes byte-for-byte."""
    if type(bundle) is not SemanticReviewBundle:
        raise TypeError("bundle must be a SemanticReviewBundle")
    if type(adjudication) is not Adjudication:
        raise TypeError("adjudication must be an Adjudication record")
    if any(x.item_id == adjudication.item_id for x in bundle.adjudications):
        raise ValueError("duplicate adjudication: item is already adjudicated")
    if bundle.status != "adjudication_required":
        raise ValueError("adjudication can only be appended while required")
    if adjudication.item_id not in _disputed_items(bundle):
        raise ValueError("adjudication item is not a required disputed item")
    item = next(x for x in bundle.review_export.items if x.item_id == adjudication.item_id)
    expected_hashes = tuple(
        sorted(x.record_hash for x in bundle.independent_codes if x.item_id == item.item_id)
    )
    if (
        adjudication.item_hash != item.record_hash
        or adjudication.policy_hash != bundle.policy.record_hash
        or adjudication.export_hash != bundle.review_export.export_hash
        or adjudication.independent_code_hashes != expected_hashes
    ):
        raise ValueError("adjudication hash bindings differ from independent evidence")
    _validate_labels(bundle.policy, adjudication.labels)
    adjudications = bundle.adjudications + (adjudication,)
    outstanding = _disputed_items(bundle) - {x.item_id for x in adjudications}
    if outstanding:
        return SemanticReviewBundle(
            bundle.policy,
            bundle.review_export,
            bundle.hidden_bindings,
            bundle.independent_codes,
            adjudications,
            bundle.agreement,
            "adjudication_required",
            (),
        )
    final = _final_labels(bundle, adjudications)
    return SemanticReviewBundle(
        bundle.policy,
        bundle.review_export,
        bundle.hidden_bindings,
        bundle.independent_codes,
        adjudications,
        bundle.agreement,
        "complete",
        final,
    )


def to_semantic_gate_evidence(
    bundle: SemanticReviewBundle,
    specification: ArtifactEnvelope,
    cases: tuple[ProbeCase, ...],
    run: ProbeRunProjection,
    parses: tuple[ProbeParseEvidence, ...],
) -> tuple[SemanticGateEvidence, ...]:
    """Project verified review labels into Task 5 gate evidence without semantic guesses."""
    if type(bundle) is not SemanticReviewBundle:
        raise TypeError("bundle must be a SemanticReviewBundle")
    if not isinstance(specification, ArtifactEnvelope):
        raise TypeError("specification must be an ArtifactEnvelope")
    if type(cases) is not tuple or any(type(x) is not ProbeCase for x in cases):
        raise TypeError("cases must be a ProbeCase tuple")
    if type(run) is not ProbeRunProjection:
        raise TypeError("run must be a ProbeRunProjection")
    if type(parses) is not tuple or any(type(x) is not ProbeParseEvidence for x in parses):
        raise TypeError("parses must be a ProbeParseEvidence tuple")
    expected_export, expected_bindings = _build_expected_review_export(
        specification, cases, run, bundle.policy
    )
    if bundle.review_export.to_payload() != expected_export.to_payload() or tuple(
        binding.to_payload() for binding in bundle.hidden_bindings
    ) != tuple(binding.to_payload() for binding in expected_bindings):
        raise ValueError(
            "review export/sample selection/visible binding differs from deterministic replay"
        )
    SemanticReviewBundle.from_payload(bundle.to_payload())
    validated = load_probe_specification(specification.to_payload()["payload"])
    if validated.output_hash != specification.output_hash:
        raise ValueError("bridge specification hash drift")
    if (
        specification.payload["policy_hashes"]["semantic_review_policy"]
        != bundle.policy.record_hash
        or bundle.review_export.specification_hash != specification.output_hash
        or bundle.review_export.specification_semantic_review_policy_hash
        != bundle.policy.record_hash
        or bundle.review_export.run_id != run.probe_run_id
        or bundle.review_export.run_evidence_hash != run.run_evidence_hash
    ):
        raise ValueError("bridge specification/run/policy hash binding mismatch")
    authoritative = {case.probe_case_id: case for case in expand_probe_cases(validated)}
    for case in cases:
        if (
            case.probe_case_id not in authoritative
            or case.to_payload() != authoritative[case.probe_case_id].to_payload()
        ):
            raise ValueError("bridge case differs from specification expansion")
    folded = fold_case_attempts(cases, run)
    case_map = {x.probe_case_id: x for x in cases}
    if len(case_map) != len(cases):
        raise ValueError("duplicate bridge cases")
    parse_map = {x.probe_case_id: x for x in parses}
    if len(parse_map) != len(parses):
        raise ValueError("duplicate bridge parses")
    attempts_by_parse = {
        attempt.parse_evidence.record_hash: attempt
        for attempt in run.attempts
        if attempt.parse_evidence is not None
    }
    for case_id, parse in parse_map.items():
        ProbeParseEvidence.from_payload(parse.to_payload())
        case = case_map.get(case_id)
        if (
            case is None
            or parse.probe_case_hash != case.record_hash
            or folded[case_id].final_parse is None
            or parse.record_hash != folded[case_id].final_parse.record_hash
            or parse.record_hash not in attempts_by_parse
        ):
            raise ValueError("bridge parse is not the final run-bound case evidence")
        attempt = attempts_by_parse[parse.record_hash]
        expected_request = ProbeRequest.create(
            case,
            attempt_index=attempt.attempt_index,
            attempt_kind=attempt.attempt_kind,
            generation_settings=attempt.request.generation_settings,
        )
        if expected_request.to_payload() != attempt.request.to_payload():
            raise ValueError("bridge rendered request differs from the authoritative case")
        response = attempt.response
        if (
            parse.request_id != attempt.request.request_id
            or parse.request_hash != attempt.request.record_hash
            or parse.response_id != response.response_id
            or parse.response_hash != response.record_hash
            or parse.raw_response_hash != response.raw_response_hash
            or parse.scale_id != case.scale_id
            or parse.field_order_id != case.field_order_id
        ):
            raise ValueError("bridge parse request/response/declaration chain mismatch")
    binding_by_case = {x.probe_case_id: x for x in bundle.hidden_bindings}
    item_by_id = {x.item_id: x for x in bundle.review_export.items}
    final_by_item = {x.item_id: x for x in bundle.final_labels}
    for binding in bundle.hidden_bindings:
        case = case_map.get(binding.probe_case_id)
        parse = parse_map.get(binding.probe_case_id)
        item = item_by_id.get(binding.item_id)
        if case is None or parse is None or item is None:
            raise ValueError("bridge hidden binding has no authoritative upstream evidence")
        attempt = attempts_by_parse[parse.record_hash]
        if attempt.response.raw_response is None:
            raise ValueError("bridge review item lacks a response text artifact")
        identity_text, history_text = _semantic_visible_blocks(specification.payload, case)
        visible = {
            "topic_text": _topic_text(specification.payload, case),
            "history_text": history_text,
            "identity_text": identity_text,
            "response_text": attempt.response.raw_response,
        }
        _require_visible_payload(visible, bundle.policy)
        visible_hash = canonical_payload_hash(visible)
        expected_item_id = _opaque_item_id(
            policy_id=bundle.policy.policy_id,
            policy_hash=bundle.policy.record_hash,
            randomization_seed=bundle.policy.randomization_seed,
            randomization_domain=bundle.policy.randomization_domain,
            stratum_id=binding.stratum_id,
            probe_case_id=case.probe_case_id,
            probe_case_hash=case.record_hash,
            request_id=parse.request_id,
            request_hash=parse.request_hash,
            response_id=parse.response_id,
            response_hash=parse.response_hash,
            raw_response_hash=parse.raw_response_hash,
            parse_id=parse.parse_evidence_id,
            parse_hash=parse.record_hash,
            visible_payload_hash=visible_hash,
        )
        if (
            item.item_id != expected_item_id
            or binding.item_id != expected_item_id
            or dict(item.visible_payload) != visible
            or item.visible_payload_hash != visible_hash
            or binding.visible_payload_hash != visible_hash
            or binding.probe_case_hash != case.record_hash
            or binding.request_id != parse.request_id
            or binding.request_hash != parse.request_hash
            or binding.response_id != parse.response_id
            or binding.response_hash != parse.response_hash
            or binding.raw_response_hash != parse.raw_response_hash
            or binding.parse_id != parse.parse_evidence_id
            or binding.parse_hash != parse.record_hash
        ):
            raise ValueError("bridge item/visible/hidden upstream binding mismatch")
    result = []
    for case_id in sorted(parse_map):
        parse = parse_map[case_id]
        case = case_map.get(case_id)
        if case is None or parse.probe_case_hash != case.record_hash:
            raise ValueError("bridge parse/case upstream mismatch")
        binding = binding_by_case.get(case_id)
        complete = bundle.status == "complete" and binding is not None
        final = None if binding is None else final_by_item.get(binding.item_id)
        if binding is not None and (
            binding.probe_case_hash != case.record_hash
            or binding.parse_id != parse.parse_evidence_id
            or binding.parse_hash != parse.record_hash
        ):
            raise ValueError("bridge hidden binding hash drift")
        complete = complete and final is not None
        if complete:
            assert final is not None
            refusal_label = final.labels[bundle.policy.refusal_dimension]
            contradiction_label = final.labels[bundle.policy.contradiction_dimension]
            refusal = refusal_label in bundle.policy.refusal_positive_labels
            contradiction = bundle.policy.contradiction_label_map[contradiction_label]
            evidence_hash = canonical_payload_hash(
                [
                    bundle.record_hash,
                    binding.record_hash,
                    final.record_hash,
                    bundle.policy.classifier_hash,
                ]
            )
        else:
            refusal = False
            contradiction = "indeterminate"
            evidence_hash = canonical_payload_hash(
                [bundle.record_hash, case.record_hash, parse.record_hash, "review_incomplete"]
            )
        result.append(
            SemanticGateEvidence(
                case_id=case_id,
                case_hash=case.record_hash,
                parse_hash=parse.record_hash,
                classifier_id=bundle.policy.classifier_id,
                classifier_version=bundle.policy.classifier_version,
                classifier_hash=bundle.policy.classifier_hash,
                refusal=refusal,
                contradiction=contradiction,
                review_complete=bool(complete),
                review_evidence_hash=evidence_hash,
            )
        )
    return tuple(result)


__all__ = [
    "Adjudication",
    "BlindReviewExport",
    "BlindReviewItem",
    "CoderContract",
    "FinalSemanticLabel",
    "HiddenReviewBinding",
    "IndependentCode",
    "ReviewStratum",
    "SemanticReviewBundle",
    "SemanticReviewPolicy",
    "append_adjudication",
    "export_blind_review",
    "import_review_codes",
    "items_for_coder",
    "to_semantic_gate_evidence",
]
