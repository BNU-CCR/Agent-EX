"""Thin, deterministic orchestration for the Phase 0A offline dry run."""

from __future__ import annotations

from fractions import Fraction
from itertools import combinations
import json
import math
import re
from typing import Mapping, NoReturn

from ..artifacts import ArtifactEnvelope
from ..domain import canonical_payload_hash
from .adapters import ProbeAdapter
from .contracts import ProbeRequest, ProbeResponse, ProbeRuntimePolicy
from .gates import (
    GateAlgorithm,
    PairChallenge,
    TopicSelection,
    evaluate_quality_gates,
    select_topic,
)
from .report import ProbeReport, ProposalArtifact, build_probe_report
from .review import (
    CoderContract,
    IndependentCode,
    ReviewStratum,
    SemanticReviewPolicy,
    export_blind_review,
    import_review_codes,
    items_for_coder,
    to_semantic_gate_evidence,
)
from .runner import execute_probe_run
from .specification import expand_probe_cases


_TOPIC_ORDER = ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
_UNRESOLVED = re.compile(r"UNRESOLVED\[[^\]]+\]")
_GENERATION_SETTINGS = {"temperature": 0.2, "top_p": 0.9, "max_tokens": 128}
_RUNTIME_IDENTITY = {"provider": "scripted-probe", "runtime_version": "1.0.0"}
_MODEL_IDENTITY = {"model": "synthetic", "revision": "offline-v1"}
_TOKENIZER_IDENTITY = {"tokenizer": "synthetic", "revision": "offline-v1"}
_CHAT_TEMPLATE_HASH = canonical_payload_hash("synthetic-chat-template-v1")


def _runtime_policy() -> ProbeRuntimePolicy:
    return ProbeRuntimePolicy.create(
        policy_id="phase0a-offline-runtime-v1",
        retryable_error_codes=("provider_busy", "timeout"),
        nonretryable_error_codes=("oom", "provider_fatal"),
        max_transport_attempts_by_code={
            "provider_busy": 2,
            "timeout": 2,
            "oom": 1,
            "provider_fatal": 1,
        },
        timeout_seconds=30.0,
        obey_retry_after=True,
        backoff_seconds=(0.25,),
    )


def _required_challenges() -> tuple[PairChallenge, ...]:
    wording = tuple(
        PairChallenge(
            f"{scale}-wording-{left}-{right}",
            "topic_quality",
            scale,
            "variant_index",
            left,
            right,
        )
        for scale in ("stance-1-7", "stance-0-10")
        for left, right in combinations(range(3), 2)
    )
    field_order = tuple(
        PairChallenge(
            f"{scale}-field-order",
            "topic_quality",
            scale,
            "field_order_id",
            "reason-confidence-stance",
            "stance-confidence-reason",
        )
        for scale in ("stance-1-7", "stance-0-10")
    )
    return wording + field_order


def _gate_algorithm() -> GateAlgorithm:
    classifier_hash = canonical_payload_hash("phase0a-offline-semantic-classifier-v1")
    return GateAlgorithm(
        algorithm_id="phase0a-offline-quality-gates",
        algorithm_version="1.0.0",
        min_parse=Fraction(99, 100),
        max_refusal=Fraction(1, 100),
        min_main_categories=4,
        max_main_endpoint=Fraction(4, 5),
        max_abs_dz=Fraction(1, 5),
        max_contradiction=Fraction(1, 20),
        tv_threshold=None,
        minimum_distribution_n=1,
        classifier_id="phase0a-offline-semantic-classifier",
        classifier_version="1.0.0",
        classifier_hash=classifier_hash,
        challenges=_required_challenges(),
    )


def _semantic_review_policy() -> SemanticReviewPolicy:
    classifier = _gate_algorithm()
    coders = (
        CoderContract("offline-human", "human", "stratified_sample"),
        CoderContract(
            "offline-judge",
            "judge",
            "all_eligible",
            model_id="synthetic-judge",
            model_revision="offline-v1",
            judge_prompt_hash=canonical_payload_hash("phase0a-offline-judge-prompt-v1"),
            ordering_policy_id="phase0a-offline-judge-order",
            ordering_policy_hash=canonical_payload_hash("phase0a-offline-judge-order-v1"),
            runtime_provider="scripted-judge",
            runtime_version="1.0.0",
        ),
    )
    return SemanticReviewPolicy(
        policy_id="phase0a-offline-semantic-review",
        policy_version="1.0.0",
        strata=(ReviewStratum("all-eligible", {}, 3),),
        randomization_seed=8675309,
        randomization_domain="phase0a-offline-semantic-review",
        visible_field_allowlist=(
            "topic_text",
            "history_text",
            "identity_text",
            "response_text",
        ),
        coder_contracts=coders,
        required_human_coder_count=1,
        required_judge_coder_count=1,
        dimension_labels={
            "refusal": ("answered", "refused"),
            "stance_consistency": ("consistent", "contradiction", "unclear"),
            "single_construct": ("yes", "no", "unclear"),
        },
        agreement_statistic="exact_item_dimension_agreement",
        agreement_scope="all_assigned_codes_on_human_sample",
        agreement_threshold=Fraction(1, 1),
        judge_failure_rule="review_incomplete",
        adjudication_trigger="any_dimension_disagreement",
        aggregation_rule="unanimous_else_adjudication",
        classifier_id=classifier.classifier_id,
        classifier_version=classifier.classifier_version,
        classifier_hash=classifier.classifier_hash,
        refusal_dimension="refusal",
        refusal_positive_labels=("refused",),
        contradiction_dimension="stance_consistency",
        contradiction_label_map={
            "consistent": "consistent",
            "contradiction": "contradiction",
            "unclear": "indeterminate",
        },
    )


def _offline_policy_hashes() -> dict[str, str]:
    """Return the three fixture-policy bindings used by the offline facade."""
    return {
        "gate_algorithm": _gate_algorithm().record_hash,
        "semantic_review_policy": _semantic_review_policy().record_hash,
        "runtime_policy": _runtime_policy().record_hash,
    }


def _find_unresolved(value: object, active_container_ids: set[int] | None = None) -> str | None:
    if type(value) is str:
        match = _UNRESOLVED.search(value)
        return None if match is None else match.group(0)
    if type(value) not in {dict, list}:
        return None
    active = set() if active_container_ids is None else active_container_ids
    identity = id(value)
    if identity in active:
        raise ValueError("cyclic YAML alias in Phase 0A probe draft is forbidden")
    active.add(identity)
    try:
        children = (value[key] for key in sorted(value)) if type(value) is dict else iter(value)
        for child in children:
            found = _find_unresolved(child, active)
            if found is not None:
                return found
    finally:
        active.remove(identity)
    return None


def load_runnable_probe_specification(payload: Mapping[str, object]) -> NoReturn:
    """Fail closed: Phase 0A currently has only a draft, never a runnable formal loader."""
    if type(payload) is not dict:
        raise TypeError("runnable probe specification must be an exact mapping")
    unresolved = _find_unresolved(payload)
    if unresolved is not None:
        raise ValueError(f"Phase 0A draft is not runnable while it contains {unresolved}")
    raise ValueError(
        "Phase 0A draft-only guard: a runnable loader is not available before formal approval"
    )


class _OfflineScriptedProbeAdapter(ProbeAdapter):
    def __init__(
        self,
        *,
        mode: str,
        format_repair: bool,
        runtime_failure: bool,
        review_complete: bool,
        target_case_id: str | None = None,
    ) -> None:
        if mode not in {"all_pass", "partial_pass", "no_pass"}:
            raise ValueError("unsupported offline scripted mode")
        for name, value in (
            ("format_repair", format_repair),
            ("runtime_failure", runtime_failure),
            ("review_complete", review_complete),
        ):
            if type(value) is not bool:
                raise TypeError(f"{name} must be a boolean")
        self.mode = mode
        self.format_repair = format_repair
        self.runtime_failure = runtime_failure
        self.review_complete = review_complete
        if target_case_id is not None and (
            type(target_case_id) is not str or not target_case_id.strip()
        ):
            raise ValueError("target_case_id must be non-empty text or null")
        self._target_case_id = target_case_id

    def for_cases(self, cases) -> _OfflineScriptedProbeAdapter:
        """Return a per-run immutable binding without retaining cross-run case state."""
        case_ids = tuple(case.probe_case_id for case in cases)
        if not case_ids or len(set(case_ids)) != len(case_ids):
            raise ValueError("offline adapter requires a nonempty unique case inventory")
        return _OfflineScriptedProbeAdapter(
            mode=self.mode,
            format_repair=self.format_repair,
            runtime_failure=self.runtime_failure,
            review_complete=self.review_complete,
            target_case_id=min(case_ids),
        )

    @property
    def configuration_hash(self) -> str:
        return canonical_payload_hash(
            {
                "mode": self.mode,
                "format_repair": self.format_repair,
                "runtime_failure": self.runtime_failure,
                "review_complete": self.review_complete,
            }
        )

    @staticmethod
    def _topic_key(request: ProbeRequest) -> str:
        text = "\n".join(message["content"] for message in request.rendered_messages).casefold()
        matches = {
            "retirement-delay": "retirement" in text,
            "gm-soybean-oil": "soybean" in text,
            "ai-net-employment": "employment" in text,
        }
        selected = tuple(key for key, present in matches.items() if present)
        if len(selected) != 1:
            raise ValueError("scripted request does not identify exactly one synthetic topic")
        return selected[0]

    def _stance(self, request: ProbeRequest) -> int:
        topic = self._topic_key(request)
        failed = (
            set()
            if self.mode == "all_pass"
            else {"retirement-delay", "ai-net-employment"}
            if self.mode == "partial_pass"
            else set(_TOPIC_ORDER)
        )
        if topic in failed:
            return 7
        seed = request.requested_seed
        if type(seed) is not int:
            raise ValueError("offline passing fixtures require an explicit requested seed")
        return 2 + seed % 4

    def generate(
        self, request: ProbeRequest, *, timeout_seconds: float | None = None
    ) -> ProbeResponse:
        if not isinstance(request, ProbeRequest):
            raise TypeError("request must be a ProbeRequest")
        if timeout_seconds is not None:
            if type(timeout_seconds) is not float:
                raise TypeError("timeout_seconds must be a float or null")
            if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
                raise ValueError("timeout_seconds must be finite and positive")
        is_target = request.probe_case_id == self._target_case_id
        if self.runtime_failure and is_target and request.attempt_index == 1:
            outcome, raw, error = "provider_error", None, "provider_fatal"
        elif self.format_repair and is_target and request.attempt_index == 1:
            outcome, raw, error = "response", "not-json", None
        else:
            values = {
                "stance": self._stance(request),
                "confidence": 3,
                "public_reason": "Synthetic reason addressing the single mock construct.",
            }
            order = (
                ("stance", "confidence", "public_reason")
                if request.field_order_id == "stance-confidence-reason"
                else ("public_reason", "confidence", "stance")
            )
            outcome = "response"
            raw = json.dumps({name: values[name] for name in order}, separators=(",", ":"))
            error = None
        return ProbeResponse.from_script_step(
            request=request,
            outcome=outcome,
            raw_response=raw,
            error_code=error,
            adapter_identity=_RUNTIME_IDENTITY,
            model_identity=_MODEL_IDENTITY,
            tokenizer_identity=_TOKENIZER_IDENTITY,
            chat_template_hash=_CHAT_TEMPLATE_HASH,
            provider_request_id=f"scripted-{request.request_id}",
            provider_seed_supported=True,
            provider_seed_echo=request.requested_seed,
            retry_after_seconds=None,
        )


def scripted_probe_adapter(
    *,
    mode: str = "all_pass",
    format_repair: bool = False,
    runtime_failure: bool = False,
    review_complete: bool = True,
) -> ProbeAdapter:
    """Build a deterministic, synthetic-only adapter for an offline dry run."""
    return _OfflineScriptedProbeAdapter(
        mode=mode,
        format_repair=format_repair,
        runtime_failure=runtime_failure,
        review_complete=review_complete,
    )


def _scripted_codes(bundle) -> tuple[IndependentCode, ...]:
    labels = {
        "refusal": "answered",
        "single_construct": "yes",
        "stance_consistency": "consistent",
    }
    result = []
    contracts = {contract.coder_id: contract for contract in bundle.policy.coder_contracts}
    for coder_id in sorted(contracts):
        contract = contracts[coder_id]
        for item in items_for_coder(bundle, coder_id):
            is_judge = contract.role == "judge"
            result.append(
                IndependentCode.create(
                    item=item,
                    policy=bundle.policy,
                    export_hash=bundle.review_export.export_hash,
                    coder_id=coder_id,
                    timestamp="2026-09-05T00:00:00Z",
                    evidence_identity=f"offline-evidence-{coder_id}-{item.item_id}",
                    judge_request_id=(f"judge-request-{item.item_id}" if is_judge else None),
                    judge_order_id=(f"judge-order-{item.item_id}" if is_judge else None),
                    provider_output_artifact_id=(
                        f"judge-output-{item.item_id}" if is_judge else None
                    ),
                    provider_output_artifact_hash=(
                        canonical_payload_hash([item.item_id, coder_id, "output"])
                        if is_judge
                        else None
                    ),
                    labels=labels,
                    raw_evidence_hash=canonical_payload_hash([item.item_id, coder_id, labels]),
                    status="completed",
                    failure_code=None,
                )
            )
    return tuple(result)


def _build_report_from_projection(
    *,
    specification: ArtifactEnvelope,
    cases,
    projection,
    adapter: ProbeAdapter,
) -> ProbeReport:
    if type(adapter) is not _OfflineScriptedProbeAdapter:
        raise TypeError("offline facade accepts only its deterministic scripted adapter")
    gate_algorithm = _gate_algorithm()
    review_policy = _semantic_review_policy()
    pending_review = export_blind_review(specification, cases, projection, review_policy)
    review = import_review_codes(
        pending_review,
        _scripted_codes(pending_review) if adapter.review_complete else (),
    )
    parses = tuple(
        attempt.parse_evidence
        for attempt in projection.attempts
        if attempt.parse_evidence is not None
    )
    semantic_evidence = to_semantic_gate_evidence(review, specification, cases, projection, parses)
    reports = tuple(
        evaluate_quality_gates(
            specification,
            cases,
            projection,
            gate_algorithm,
            semantic_evidence,
            candidate_key=key,
        )
        for key in _TOPIC_ORDER
    )
    complete = (
        projection.status == "complete"
        and review.status == "complete"
        and all(item.status == "complete" for item in reports)
    )
    selection = (
        select_topic(reports)
        if complete
        else TopicSelection(
            "suppressed",
            None,
            None,
            tuple(item.record_hash for item in reports),
        )
    )
    registered = tuple(specification.payload["decision_ids"])
    if complete and selection.status == "proposal_only":
        proposed_values = {"P1_TOPIC_PRIMARY": selection.primary}
        selected_report = next(item for item in reports if item.candidate_key == selection.primary)
        artifacts = (
            ProposalArtifact(
                "P1_TOPIC_PRIMARY",
                "phase0a-offline-topic-selection",
                selected_report.record_hash,
                "file:///phase0a/offline/gate-report.json",
            ),
        )
        unresolved = tuple(sorted(set(registered) - {"P1_TOPIC_PRIMARY"}))
    else:
        proposed_values = {}
        artifacts = ()
        unresolved = tuple(sorted(registered))
    return build_probe_report(
        specification=specification,
        cases=cases,
        projection=projection,
        parse_evidence=parses,
        semantic_review=review,
        semantic_gate_evidence=semantic_evidence,
        gate_algorithm=gate_algorithm,
        gate_reports=reports,
        topic_selection=selection,
        proposed_values=proposed_values,
        proposal_artifacts=artifacts,
        unresolved_decision_ids=unresolved,
    )


def run_offline_probe(
    specification: ArtifactEnvelope,
    adapter: ProbeAdapter,
) -> ProbeReport:
    """Execute the complete Phase 0A dry-run evidence pipeline without external I/O."""
    if type(adapter) is not _OfflineScriptedProbeAdapter:
        raise TypeError("offline facade accepts only scripted_probe_adapter output")
    if not isinstance(specification, ArtifactEnvelope):
        raise TypeError("specification must be a validated ArtifactEnvelope")
    expected_hashes = _offline_policy_hashes()
    if dict(specification.payload["policy_hashes"]) != expected_hashes:
        raise ValueError("specification policy hashes do not bind the offline policy records")
    cases = expand_probe_cases(specification)
    execution_adapter = adapter.for_cases(cases)
    projection = execute_probe_run(
        run_instance_id="phase0a-offline-" + adapter.configuration_hash,
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=_runtime_policy(),
        adapter=execution_adapter,
        generation_settings=_GENERATION_SETTINGS,
        runtime_identity=_RUNTIME_IDENTITY,
        model_identity=_MODEL_IDENTITY,
        tokenizer_identity=_TOKENIZER_IDENTITY,
        chat_template_hash=_CHAT_TEMPLATE_HASH,
    )
    return _build_report_from_projection(
        specification=specification,
        cases=cases,
        projection=projection,
        adapter=execution_adapter,
    )


__all__ = [
    "load_runnable_probe_specification",
    "run_offline_probe",
    "scripted_probe_adapter",
]
