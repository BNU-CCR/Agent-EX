"""Fail-closed Phase 0A reports and non-authoritative freeze proposals."""

from __future__ import annotations

from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import (
    _freeze,
    _json_ready,
    _require_evidence_uri,
    _require_id,
    _require_json_transport,
    _require_sha256,
    canonical_payload_hash,
)
from .contracts import ProbeCase, ProbeParseEvidence, ProbeRunProjection
from .gates import (
    TOPIC_ORDER,
    GateAlgorithm,
    GateReport,
    SemanticGateEvidence,
    TopicSelection,
    evaluate_quality_gates,
    fold_case_attempts,
    select_topic,
)
from .review import SemanticReviewBundle, to_semantic_gate_evidence
from .specification import ALLOWED_DECISION_IDS, expand_probe_cases, load_probe_specification


FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "polarization",
        "homogenization",
        "directional_drift",
        "two_tier_structure",
        "ws_shadow",
        "continuity_did",
        "primary_contrast",
        "confidence_interval",
        "p_value",
        "significance",
        "cell_mean",
    }
)

_FREE_FORM_IDENTITY_KEYS = frozenset(
    {
        "generation_event_id",
        "event_id",
        "cell_id",
        "feed_cursor",
        "private_state",
        "public_state",
        "public_stock",
        "public_flow",
    }
)

_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}


def _metadata() -> dict[str, object]:
    return dict(_METADATA)


def _reject_forbidden(value: object, *, free_form: bool = False) -> None:
    """Reject prohibited outcomes at every nesting level before hashing or export."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("report mappings require string keys")
            if key.casefold() in FORBIDDEN_REPORT_KEYS:
                raise ValueError(f"forbidden report field: {key}")
            if free_form and key.casefold() in _FREE_FORM_IDENTITY_KEYS:
                raise ValueError(f"forbidden formal identity outside provenance: {key}")
            _reject_forbidden(item, free_form=free_form)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _reject_forbidden(item, free_form=free_form)


def _require_exact_metadata(value: object) -> None:
    if type(value) is not dict or set(value) != set(_METADATA):
        raise ValueError("report metadata fields do not match the calibration-only contract")
    if any(
        type(value[key]) is not type(expected) or value[key] != expected
        for key, expected in _METADATA.items()
    ):
        raise ValueError("report metadata must remain calibration-only without formal authority")


def _require_exact_payload(payload: Mapping[str, object], expected: set[str], schema: str) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError("report payload fields do not match the exact contract")
    _require_json_transport(payload, "report payload")
    if payload.get("schema_version") != schema:
        raise ValueError("report schema_version is unsupported")
    _require_exact_metadata(payload.get("metadata"))
    _reject_forbidden(payload)


@dataclass(frozen=True, slots=True)
class ProposalArtifact:
    """One explicit decision-to-artifact evidence binding."""

    decision_id: str
    artifact_id: str
    artifact_hash: str
    evidence_uri: str

    def __post_init__(self) -> None:
        if self.decision_id not in ALLOWED_DECISION_IDS or not self.decision_id.startswith("P1_"):
            raise ValueError("proposal artifact decision_id is not a registered P1 decision")
        _require_id("artifact_id", self.artifact_id)
        _require_sha256("artifact_hash", self.artifact_hash)
        _require_evidence_uri("evidence_uri", self.evidence_uri)

    def to_payload(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProposalArtifact:
        if type(payload) is not dict or set(payload) != {field.name for field in fields(cls)}:
            raise ValueError("proposal artifact payload fields do not match the contract")
        _require_json_transport(payload, "proposal artifact")
        _reject_forbidden(payload, free_form=True)
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeCompletenessReport:
    status: str
    expected_case_count: int
    actual_case_count: int
    expected_attempt_case_ids: tuple[str, ...]
    actual_attempt_case_ids: tuple[str, ...]
    expected_request_ids: tuple[str, ...]
    actual_request_ids: tuple[str, ...]
    expected_response_ids: tuple[str, ...]
    actual_response_ids: tuple[str, ...]
    expected_parse_ids: tuple[str, ...]
    actual_parse_ids: tuple[str, ...]
    expected_review_item_ids: tuple[str, ...]
    actual_review_item_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    extra_ids: tuple[str, ...]
    specification_hash: str
    case_inventory_hash: str
    projection_run_evidence_hash: str
    semantic_review_hash: str
    record_hash: str

    _SCHEMA = "paper1.calibration.probe-completeness-report.v1"

    def __post_init__(self) -> None:
        if self.status not in {"complete", "incomplete"}:
            raise ValueError("completeness status must be complete or incomplete")
        for name in ("expected_case_count", "actual_case_count"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in (
            "expected_attempt_case_ids",
            "actual_attempt_case_ids",
            "expected_request_ids",
            "actual_request_ids",
            "expected_response_ids",
            "actual_response_ids",
            "expected_parse_ids",
            "actual_parse_ids",
            "expected_review_item_ids",
            "actual_review_item_ids",
            "missing_ids",
            "extra_ids",
        ):
            value = getattr(self, name)
            if type(value) is not tuple or tuple(sorted(value)) != value:
                raise ValueError(f"{name} must use canonical sorted tuple order")
            if len(value) != len(set(value)):
                raise ValueError(f"{name} must not contain duplicate identities")
            for item in value:
                _require_id(name, item)
        for name in (
            "specification_hash",
            "case_inventory_hash",
            "projection_run_evidence_hash",
            "semantic_review_hash",
            "record_hash",
        ):
            _require_sha256(name, getattr(self, name))
        expected = canonical_payload_hash(self.content_payload())
        if self.record_hash != expected:
            raise ValueError("completeness record_hash differs from canonical content")

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            **{
                field.name: getattr(self, field.name)
                for field in fields(self)
                if field.name != "record_hash"
            },
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(cls, **values: object) -> ProbeCompletenessReport:
        content = {"schema_version": cls._SCHEMA, **values, "metadata": _metadata()}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeCompletenessReport:
        expected = {field.name for field in fields(cls)} | {"schema_version", "metadata"}
        _require_exact_payload(payload, expected, cls._SCHEMA)
        values = {field.name: payload[field.name] for field in fields(cls)}
        for name in (
            "expected_attempt_case_ids",
            "actual_attempt_case_ids",
            "expected_request_ids",
            "actual_request_ids",
            "expected_response_ids",
            "actual_response_ids",
            "expected_parse_ids",
            "actual_parse_ids",
            "expected_review_item_ids",
            "actual_review_item_ids",
            "missing_ids",
            "extra_ids",
        ):
            if type(values[name]) is not list:
                raise TypeError(f"{name} must use a JSON array")
            values[name] = tuple(values[name])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeGateReport:
    status: str
    candidate_report_hashes: tuple[str, ...]
    algorithm_hash: str
    selection_hash: str
    record_hash: str

    _SCHEMA = "paper1.calibration.probe-gate-report.v1"

    def __post_init__(self) -> None:
        if self.status not in {"complete", "incomplete"}:
            raise ValueError("probe gate report status is invalid")
        if (
            type(self.candidate_report_hashes) is not tuple
            or len(self.candidate_report_hashes) != 3
        ):
            raise ValueError("probe gate report requires three candidate report hashes")
        for digest in self.candidate_report_hashes + (
            self.algorithm_hash,
            self.selection_hash,
            self.record_hash,
        ):
            _require_sha256("probe gate report hash", digest)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("probe gate report hash differs from content")

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "status": self.status,
            "candidate_report_hashes": self.candidate_report_hashes,
            "algorithm_hash": self.algorithm_hash,
            "selection_hash": self.selection_hash,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        reports: tuple[GateReport, ...],
        algorithm: GateAlgorithm,
        selection: TopicSelection,
    ) -> ProbeGateReport:
        ordered = tuple(
            next(report for report in reports if report.candidate_key == key) for key in TOPIC_ORDER
        )
        values = {
            "status": "complete"
            if all(report.status == "complete" for report in ordered)
            else "incomplete",
            "candidate_report_hashes": tuple(report.record_hash for report in ordered),
            "algorithm_hash": algorithm.record_hash,
            "selection_hash": canonical_payload_hash(selection.to_payload()),
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": _metadata()}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeGateReport:
        expected = {field.name for field in fields(cls)} | {"schema_version", "metadata"}
        _require_exact_payload(payload, expected, cls._SCHEMA)
        if type(payload["candidate_report_hashes"]) is not list:
            raise TypeError("candidate report hashes must use a JSON array")
        return cls(
            status=payload["status"],
            candidate_report_hashes=tuple(payload["candidate_report_hashes"]),
            algorithm_hash=payload["algorithm_hash"],
            selection_hash=payload["selection_hash"],
            record_hash=payload["record_hash"],
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class FreezeProposal:
    status: str
    specification_hash: str
    case_inventory_hash: str
    run_evidence_hash: str
    gate_report_hash: str
    selection_hash: str
    proposed_values: Mapping[str, object]
    supporting_artifacts: tuple[ProposalArtifact, ...]
    unresolved_decision_ids: tuple[str, ...]
    record_hash: str

    _SCHEMA = "paper1.calibration.freeze-proposal.v1"

    def __post_init__(self) -> None:
        if self.status not in {"proposal_only", "incomplete"}:
            raise ValueError("freeze proposal status must be proposal_only or incomplete")
        for name in (
            "specification_hash",
            "case_inventory_hash",
            "run_evidence_hash",
            "gate_report_hash",
            "selection_hash",
            "record_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if not isinstance(self.proposed_values, Mapping):
            raise TypeError("proposed_values must be an explicit mapping")
        _reject_forbidden(self.proposed_values, free_form=True)
        if tuple(self.proposed_values) != tuple(sorted(self.proposed_values)):
            raise ValueError("proposed values must use canonical decision order")
        if type(self.supporting_artifacts) is not tuple or any(
            type(item) is not ProposalArtifact for item in self.supporting_artifacts
        ):
            raise TypeError("supporting_artifacts must be ProposalArtifact records")
        artifact_keys = tuple(
            (item.decision_id, item.artifact_id) for item in self.supporting_artifacts
        )
        if artifact_keys != tuple(sorted(artifact_keys)) or len(artifact_keys) != len(
            set(artifact_keys)
        ):
            raise ValueError("supporting artifacts must be unique and canonical")
        artifact_ids = tuple(item.artifact_id for item in self.supporting_artifacts)
        artifact_hashes = tuple(item.artifact_hash for item in self.supporting_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)) or len(artifact_hashes) != len(
            set(artifact_hashes)
        ):
            raise ValueError("supporting artifact IDs and hashes must be globally unique")
        if (
            type(self.unresolved_decision_ids) is not tuple
            or tuple(sorted(self.unresolved_decision_ids)) != self.unresolved_decision_ids
        ):
            raise ValueError("unresolved decisions must use canonical order")
        if len(set(self.unresolved_decision_ids)) != len(self.unresolved_decision_ids):
            raise ValueError("duplicate unresolved decision IDs")
        proposed = set(self.proposed_values)
        unresolved = set(self.unresolved_decision_ids)
        if (
            proposed & unresolved
            or not proposed <= ALLOWED_DECISION_IDS
            or not unresolved <= ALLOWED_DECISION_IDS
        ):
            raise ValueError("proposal contains unknown, duplicate, or conflicting decision IDs")
        if {item.decision_id for item in self.supporting_artifacts} != proposed:
            raise ValueError("every proposed decision requires supporting artifact evidence")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("freeze proposal record_hash differs from content")
        object.__setattr__(self, "proposed_values", _freeze(self.proposed_values))

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "status": self.status,
            "specification_hash": self.specification_hash,
            "case_inventory_hash": self.case_inventory_hash,
            "run_evidence_hash": self.run_evidence_hash,
            "gate_report_hash": self.gate_report_hash,
            "selection_hash": self.selection_hash,
            "proposed_values": self.proposed_values,
            "supporting_artifacts": tuple(item.to_payload() for item in self.supporting_artifacts),
            "unresolved_decision_ids": self.unresolved_decision_ids,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(cls, **values: object) -> FreezeProposal:
        content = {
            "schema_version": cls._SCHEMA,
            **{
                key: tuple(item.to_payload() for item in value)
                if key == "supporting_artifacts"
                else value
                for key, value in values.items()
            },
            "metadata": _metadata(),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FreezeProposal:
        expected = {field.name for field in fields(cls)} | {"schema_version", "metadata"}
        _require_exact_payload(payload, expected, cls._SCHEMA)
        if (
            type(payload["proposed_values"]) is not dict
            or type(payload["supporting_artifacts"]) is not list
            or type(payload["unresolved_decision_ids"]) is not list
        ):
            raise TypeError("freeze proposal repeated fields require JSON objects/arrays")
        return cls(
            status=payload["status"],
            specification_hash=payload["specification_hash"],
            case_inventory_hash=payload["case_inventory_hash"],
            run_evidence_hash=payload["run_evidence_hash"],
            gate_report_hash=payload["gate_report_hash"],
            selection_hash=payload["selection_hash"],
            proposed_values=payload["proposed_values"],
            supporting_artifacts=tuple(
                ProposalArtifact.from_payload(item) for item in payload["supporting_artifacts"]
            ),
            unresolved_decision_ids=tuple(payload["unresolved_decision_ids"]),
            record_hash=payload["record_hash"],
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeReportSource:
    specification: ArtifactEnvelope
    cases: tuple[ProbeCase, ...]
    projection: ProbeRunProjection
    parse_evidence: tuple[ProbeParseEvidence, ...]
    semantic_review: SemanticReviewBundle
    semantic_gate_evidence: tuple[SemanticGateEvidence, ...]
    gate_algorithm: GateAlgorithm
    gate_reports: tuple[GateReport, ...]
    topic_selection: TopicSelection
    proposed_values: Mapping[str, object]
    proposal_artifacts: tuple[ProposalArtifact, ...]
    unresolved_decision_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProbeReport:
    status: str
    specification_hash: str
    case_inventory_hash: str
    report_projection_hash: str
    run_evidence_hash: str
    completeness: ProbeCompletenessReport
    gate_report: ProbeGateReport
    gate_reports: tuple[GateReport, ...]
    topic_selection: TopicSelection
    freeze_proposal: FreezeProposal
    source: ProbeReportSource
    record_hash: str

    _SCHEMA = "paper1.calibration.probe-report.v1"

    def __post_init__(self) -> None:
        if self.status not in {"proposal_only", "no_candidate", "incomplete"}:
            raise ValueError("probe report status is invalid")
        for name in (
            "specification_hash",
            "case_inventory_hash",
            "report_projection_hash",
            "run_evidence_hash",
            "record_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if (
            type(self.completeness) is not ProbeCompletenessReport
            or type(self.gate_report) is not ProbeGateReport
        ):
            raise TypeError("probe report requires exact completeness and gate report records")
        if type(self.gate_reports) is not tuple or len(self.gate_reports) != 3:
            raise ValueError("probe report requires three candidate gate reports")
        if (
            type(self.topic_selection) is not TopicSelection
            or type(self.freeze_proposal) is not FreezeProposal
        ):
            raise TypeError("probe report selection/proposal types are invalid")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("probe report record_hash differs from canonical content")

    @property
    def metadata(self) -> dict[str, object]:
        return _metadata()

    def projection_payload(self) -> dict[str, object]:
        return {
            "completeness": self.completeness.to_payload(),
            "gate_report": self.gate_report.to_payload(),
            "gate_reports": tuple(report.to_payload() for report in self.gate_reports),
            "topic_selection": self.topic_selection.to_payload(),
            "freeze_proposal": self.freeze_proposal.to_payload(),
        }

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "status": self.status,
            "specification_hash": self.specification_hash,
            "case_inventory_hash": self.case_inventory_hash,
            "report_projection_hash": self.report_projection_hash,
            "run_evidence_hash": self.run_evidence_hash,
            **self.projection_payload(),
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})


def compute_run_evidence_hash(
    projection: ProbeRunProjection,
    semantic_review: SemanticReviewBundle | None,
) -> str:
    """Bind actual attempt order and optional blind-review causal evidence."""
    if type(projection) is not ProbeRunProjection:
        raise TypeError("run evidence requires a ProbeRunProjection")
    checked = ProbeRunProjection.from_payload(projection.to_payload())
    if semantic_review is not None:
        if type(semantic_review) is not SemanticReviewBundle:
            raise TypeError("semantic review evidence has the wrong type")
        checked_review = SemanticReviewBundle.from_payload(semantic_review.to_payload())
        review_payload: object = checked_review.to_payload()
    else:
        review_payload = None
    payload = {
        "schema_version": "paper1.calibration.full-run-evidence.v1",
        "probe_run_id": checked.probe_run_id,
        "attempts_in_causal_order": [attempt.to_payload() for attempt in checked.attempts],
        "semantic_review_import": review_payload,
    }
    _reject_forbidden(payload)
    return canonical_payload_hash(payload)


def build_freeze_proposal(
    *,
    completeness: ProbeCompletenessReport,
    specification_hash: str,
    case_inventory_hash: str,
    run_evidence_hash: str,
    gate_report: ProbeGateReport,
    topic_selection: TopicSelection,
    proposed_values: Mapping[str, object],
    proposal_artifacts: tuple[ProposalArtifact, ...],
    unresolved_decision_ids: tuple[str, ...],
    registered_decision_ids: tuple[str, ...],
) -> FreezeProposal:
    """Build an explicit proposal that cannot confer formal decision authority."""
    if (
        type(completeness) is not ProbeCompletenessReport
        or type(gate_report) is not ProbeGateReport
    ):
        raise TypeError("freeze proposal requires reviewed completeness and gate reports")
    if type(topic_selection) is not TopicSelection:
        raise TypeError("freeze proposal requires the precommitted topic selection")
    for name, digest in (
        ("specification_hash", specification_hash),
        ("case_inventory_hash", case_inventory_hash),
        ("run_evidence_hash", run_evidence_hash),
    ):
        _require_sha256(name, digest)
    if (
        completeness.specification_hash != specification_hash
        or completeness.case_inventory_hash != case_inventory_hash
    ):
        raise ValueError("freeze proposal completeness provenance hash drift")
    if type(registered_decision_ids) is not tuple or len(set(registered_decision_ids)) != len(
        registered_decision_ids
    ):
        raise ValueError("registered decision IDs must be an explicit unique tuple")
    registered = set(registered_decision_ids)
    if not registered <= ALLOWED_DECISION_IDS or any(
        type(item) is not str or not item.startswith("P1_") for item in registered_decision_ids
    ):
        raise ValueError("freeze proposal contains an unknown registered decision ID")
    if set(proposed_values) | set(unresolved_decision_ids) != registered:
        raise ValueError("freeze proposal decision coverage is incomplete")
    ordered_proposals = dict(sorted(proposed_values.items()))
    ordered_artifacts = tuple(
        sorted(proposal_artifacts, key=lambda item: (item.decision_id, item.artifact_id))
    )
    ordered_unresolved = tuple(sorted(unresolved_decision_ids))
    if completeness.status != "complete" and (
        topic_selection.primary is not None or ordered_proposals
    ):
        raise ValueError("incomplete evidence cannot produce favorable selection or proposals")
    return FreezeProposal.create(
        status="proposal_only" if completeness.status == "complete" else "incomplete",
        specification_hash=specification_hash,
        case_inventory_hash=case_inventory_hash,
        run_evidence_hash=run_evidence_hash,
        gate_report_hash=gate_report.record_hash,
        selection_hash=canonical_payload_hash(topic_selection.to_payload()),
        proposed_values=ordered_proposals,
        supporting_artifacts=ordered_artifacts,
        unresolved_decision_ids=ordered_unresolved,
    )


def _canonical_gate_reports(reports: tuple[GateReport, ...]) -> tuple[GateReport, ...]:
    if (
        type(reports) is not tuple
        or len(reports) != 3
        or any(type(item) is not GateReport for item in reports)
    ):
        raise ValueError("exactly three candidate GateReport records are required")
    if {item.candidate_key for item in reports} != set(TOPIC_ORDER):
        raise ValueError("gate reports contain missing, duplicate, or unknown candidates")
    return tuple(next(item for item in reports if item.candidate_key == key) for key in TOPIC_ORDER)


def build_probe_report(
    *,
    specification: ArtifactEnvelope,
    cases: tuple[ProbeCase, ...],
    projection: ProbeRunProjection,
    parse_evidence: tuple[ProbeParseEvidence, ...],
    semantic_review: SemanticReviewBundle,
    semantic_gate_evidence: tuple[SemanticGateEvidence, ...],
    gate_algorithm: GateAlgorithm,
    gate_reports: tuple[GateReport, ...],
    topic_selection: TopicSelection,
    proposed_values: Mapping[str, object],
    proposal_artifacts: tuple[ProposalArtifact, ...],
    unresolved_decision_ids: tuple[str, ...],
) -> ProbeReport:
    """Replay all upstream layers and build a canonical, non-authoritative report."""
    if type(specification) is not ArtifactEnvelope:
        raise TypeError("a validated specification envelope is required")
    validated = load_probe_specification(specification.to_payload()["payload"])
    if validated.to_payload() != specification.to_payload():
        raise ValueError("specification differs from strict canonical validation")
    _reject_forbidden(proposed_values, free_form=True)
    if type(proposal_artifacts) is not tuple or any(
        type(item) is not ProposalArtifact for item in proposal_artifacts
    ):
        raise TypeError("proposal_artifacts must use exact ProposalArtifact records")
    if type(unresolved_decision_ids) is not tuple:
        raise TypeError("unresolved_decision_ids must be a tuple")
    registered = set(validated.payload["decision_ids"])
    if set(proposed_values) | set(unresolved_decision_ids) != registered:
        raise ValueError("proposal decision coverage must exactly match specification decisions")
    authoritative = expand_probe_cases(validated)
    if type(cases) is not tuple or any(type(item) is not ProbeCase for item in cases):
        raise TypeError("cases must be an exact ProbeCase tuple")
    expected_cases = {item.probe_case_id: item.to_payload() for item in authoritative}
    supplied_cases = {item.probe_case_id: item.to_payload() for item in cases}
    if len(cases) != len(authoritative) or supplied_cases != expected_cases:
        raise ValueError("case inventory differs from authoritative specification expansion")
    ordered_cases = tuple(sorted(cases, key=lambda item: item.probe_case_id))
    case_inventory_hash = canonical_payload_hash([item.to_payload() for item in ordered_cases])
    checked_projection = ProbeRunProjection.from_payload(projection.to_payload())
    if (
        checked_projection.specification_hash != validated.output_hash
        or checked_projection.case_inventory_hash != case_inventory_hash
        or set(checked_projection.case_statuses) != set(expected_cases)
    ):
        raise ValueError("projection specification or case inventory hash drift")
    fold_case_attempts(ordered_cases, checked_projection)
    if type(parse_evidence) is not tuple or any(
        type(item) is not ProbeParseEvidence for item in parse_evidence
    ):
        raise TypeError("parse_evidence must be exact ProbeParseEvidence records")
    expected_parses = tuple(
        attempt.parse_evidence
        for attempt in checked_projection.attempts
        if attempt.parse_evidence is not None
    )
    supplied_parse_map = {item.parse_evidence_id: item.to_payload() for item in parse_evidence}
    expected_parse_map = {item.parse_evidence_id: item.to_payload() for item in expected_parses}
    if len(supplied_parse_map) != len(parse_evidence) or supplied_parse_map != expected_parse_map:
        raise ValueError("parse evidence is missing, duplicated, extra, or hash-drifted")
    ordered_parses = tuple(sorted(parse_evidence, key=lambda item: item.parse_evidence_id))
    if type(semantic_review) is not SemanticReviewBundle:
        raise TypeError("semantic_review must be a SemanticReviewBundle")
    checked_review = semantic_review
    if (
        validated.payload["policy_hashes"]["semantic_review_policy"]
        != checked_review.policy.record_hash
    ):
        raise ValueError("semantic review policy was not bound by the specification")
    expected_bridge = to_semantic_gate_evidence(
        checked_review, validated, ordered_cases, checked_projection, ordered_parses
    )
    if type(semantic_gate_evidence) is not tuple or any(
        type(item) is not SemanticGateEvidence for item in semantic_gate_evidence
    ):
        raise TypeError("semantic gate evidence must use exact records")
    supplied_bridge = {item.case_id: item.to_payload() for item in semantic_gate_evidence}
    expected_bridge_map = {item.case_id: item.to_payload() for item in expected_bridge}
    if (
        len(supplied_bridge) != len(semantic_gate_evidence)
        or supplied_bridge != expected_bridge_map
    ):
        raise ValueError("semantic review bridge is missing, duplicated, or hash-drifted")
    ordered_bridge = tuple(sorted(semantic_gate_evidence, key=lambda item: item.case_id))
    if (
        type(gate_algorithm) is not GateAlgorithm
        or validated.payload["policy_hashes"]["gate_algorithm"] != gate_algorithm.record_hash
    ):
        raise ValueError("gate algorithm was not bound before execution")
    ordered_reports = _canonical_gate_reports(gate_reports)
    expected_reports = tuple(
        evaluate_quality_gates(
            validated,
            ordered_cases,
            checked_projection,
            gate_algorithm,
            ordered_bridge,
            candidate_key=key,
        )
        for key in TOPIC_ORDER
    )
    if [item.to_payload() for item in ordered_reports] != [
        item.to_payload() for item in expected_reports
    ]:
        raise ValueError("gate report differs from deterministic replay")
    expected_selection = select_topic(expected_reports)
    if (
        type(topic_selection) is not TopicSelection
        or topic_selection.to_payload() != expected_selection.to_payload()
    ):
        raise ValueError("topic selection differs from precommitted deterministic selection")
    ordered_artifacts = tuple(
        sorted(proposal_artifacts, key=lambda item: (item.decision_id, item.artifact_id))
    )
    ordered_unresolved = tuple(sorted(unresolved_decision_ids))
    ordered_proposals = dict(sorted(proposed_values.items()))
    attempts = checked_projection.attempts
    actual_attempt_cases = tuple(sorted({attempt.probe_case_id for attempt in attempts}))
    expected_attempt_cases = tuple(sorted(expected_cases))
    expected_request_ids = tuple(sorted(attempt.request.request_id for attempt in attempts))
    expected_response_ids = tuple(sorted(attempt.response.response_id for attempt in attempts))
    expected_parse_ids = tuple(sorted(item.parse_evidence_id for item in expected_parses))
    expected_review_ids = tuple(sorted(item.item_id for item in checked_review.review_export.items))
    missing = tuple(sorted(set(expected_attempt_cases) - set(actual_attempt_cases)))
    completeness_status = (
        "complete"
        if checked_projection.status == "complete"
        and checked_review.status == "complete"
        and not missing
        and all(report.status == "complete" for report in ordered_reports)
        else "incomplete"
    )
    completeness = ProbeCompletenessReport.create(
        status=completeness_status,
        expected_case_count=len(authoritative),
        actual_case_count=len(checked_projection.case_statuses),
        expected_attempt_case_ids=expected_attempt_cases,
        actual_attempt_case_ids=actual_attempt_cases,
        expected_request_ids=expected_request_ids,
        actual_request_ids=expected_request_ids,
        expected_response_ids=expected_response_ids,
        actual_response_ids=expected_response_ids,
        expected_parse_ids=expected_parse_ids,
        actual_parse_ids=tuple(sorted(supplied_parse_map)),
        expected_review_item_ids=expected_review_ids,
        actual_review_item_ids=tuple(
            sorted(item.item_id for item in checked_review.review_export.items)
        ),
        missing_ids=missing,
        extra_ids=(),
        specification_hash=validated.output_hash,
        case_inventory_hash=case_inventory_hash,
        projection_run_evidence_hash=checked_projection.run_evidence_hash,
        semantic_review_hash=checked_review.record_hash,
    )
    gate_report = ProbeGateReport.create(ordered_reports, gate_algorithm, expected_selection)
    full_run_hash = compute_run_evidence_hash(checked_projection, checked_review)
    proposal = build_freeze_proposal(
        completeness=completeness,
        specification_hash=validated.output_hash,
        case_inventory_hash=case_inventory_hash,
        run_evidence_hash=full_run_hash,
        gate_report=gate_report,
        topic_selection=expected_selection,
        proposed_values=ordered_proposals,
        proposal_artifacts=ordered_artifacts,
        unresolved_decision_ids=ordered_unresolved,
        registered_decision_ids=tuple(validated.payload["decision_ids"]),
    )
    projection_payload = {
        "completeness": completeness.to_payload(),
        "gate_report": gate_report.to_payload(),
        "gate_reports": tuple(item.to_payload() for item in ordered_reports),
        "topic_selection": expected_selection.to_payload(),
        "freeze_proposal": proposal.to_payload(),
    }
    _reject_forbidden(projection_payload)
    report_projection_hash = canonical_payload_hash(projection_payload)
    status = (
        "incomplete"
        if completeness_status != "complete"
        else "proposal_only"
        if expected_selection.status == "proposal_only"
        else "no_candidate"
    )
    source = ProbeReportSource(
        validated,
        ordered_cases,
        checked_projection,
        ordered_parses,
        checked_review,
        ordered_bridge,
        gate_algorithm,
        ordered_reports,
        expected_selection,
        MappingProxyType(ordered_proposals),
        ordered_artifacts,
        ordered_unresolved,
    )
    values = {
        "status": status,
        "specification_hash": validated.output_hash,
        "case_inventory_hash": case_inventory_hash,
        "report_projection_hash": report_projection_hash,
        "run_evidence_hash": full_run_hash,
        "completeness": completeness,
        "gate_report": gate_report,
        "gate_reports": ordered_reports,
        "topic_selection": expected_selection,
        "freeze_proposal": proposal,
        "source": source,
    }
    content = {
        "schema_version": ProbeReport._SCHEMA,
        "status": status,
        "specification_hash": validated.output_hash,
        "case_inventory_hash": case_inventory_hash,
        "report_projection_hash": report_projection_hash,
        "run_evidence_hash": full_run_hash,
        **projection_payload,
        "metadata": _metadata(),
    }
    return ProbeReport(**values, record_hash=canonical_payload_hash(content))


__all__ = [
    "FORBIDDEN_REPORT_KEYS",
    "FreezeProposal",
    "ProbeCompletenessReport",
    "ProbeGateReport",
    "ProbeReport",
    "ProbeReportSource",
    "ProposalArtifact",
    "build_freeze_proposal",
    "build_probe_report",
    "compute_run_evidence_hash",
]
