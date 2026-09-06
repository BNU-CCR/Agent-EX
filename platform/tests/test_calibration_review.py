from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import json

import pytest

from agent_ex.calibration.adapters import ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.gates import evaluate_quality_gates
from agent_ex.calibration.review import (
    Adjudication,
    CoderContract,
    IndependentCode,
    ReviewStratum,
    SemanticReviewPolicy,
    SemanticReviewBundle,
    append_adjudication,
    export_blind_review,
    import_review_codes,
    to_semantic_gate_evidence,
)
from agent_ex.calibration.runner import execute_probe_run
from agent_ex.calibration.specification import expand_probe_cases, load_probe_specification
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload
from test_calibration_gates import algorithm, required_challenges
from test_calibration_runner import (
    CHAT_TEMPLATE_HASH,
    GENERATION_SETTINGS,
    MODEL_IDENTITY,
    RUNTIME_IDENTITY,
    TOKENIZER_IDENTITY,
    policy as runtime_policy,
)


DIMENSIONS = {
    "refusal": ("answered", "refused"),
    "stance_consistency": ("consistent", "contradiction", "unclear"),
    "single_construct": ("yes", "no", "unclear"),
}
CODERS = (CoderContract("coder-a", "human"), CoderContract("coder-b", "judge"))


def review_policy(*, strata=None, threshold=Fraction(1, 1)):
    return SemanticReviewPolicy(
        policy_id="phase0a-semantic-review",
        policy_version="1.0.0",
        strata=(ReviewStratum("all", {}, 3),) if strata is None else strata,
        randomization_seed=8675309,
        visible_field_allowlist=(
            "topic_text",
            "history_text",
            "identity_text",
            "response_text",
        ),
        coder_contracts=CODERS,
        dimension_labels=DIMENSIONS,
        agreement_statistic="exact_item_dimension_agreement",
        agreement_threshold=threshold,
        judge_failure_rule="review_incomplete",
        adjudication_trigger="any_dimension_disagreement",
        aggregation_rule="unanimous_else_adjudication",
        classifier_id="phase0a-semantic-classifier",
        classifier_version="1.0.0",
        classifier_hash=canonical_payload_hash("phase0a-semantic-classifier-v1"),
        refusal_dimension="refusal",
        refusal_positive_labels=("refused",),
        contradiction_dimension="stance_consistency",
        contradiction_label_map={
            "consistent": "consistent",
            "contradiction": "contradiction",
            "unclear": "indeterminate",
        },
    )


def prepared(*, policy=None, count=6):
    policy = policy or review_policy()
    payload = probe_spec_payload()
    payload["policy_hashes"]["semantic_review_policy"] = policy.record_hash
    specification = load_probe_specification(payload)
    expanded = expand_probe_cases(specification)
    families = [
        "topic_quality",
        "topic_quality",
        "topic_quality",
        "identity",
        "identity",
        "continuity",
    ]
    selected = []
    for family in families[:count]:
        selected.append(next(c for c in expanded if c.case_family == family and c not in selected))
    cases = tuple(sorted(selected, key=lambda item: item.probe_case_id))
    steps = {
        (case.probe_case_id, 1): ProbeScriptStep("response", raw_for(case), None, None)
        for case in cases
    }
    run = execute_probe_run(
        run_instance_id="review-test",
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy(),
        adapter=ScriptedProbeAdapter(steps),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    return specification, cases, run, policy


def raw_for(case):
    values = {"stance": 4, "confidence": 3, "public_reason": "Synthetic reason."}
    order = (
        ("stance", "confidence", "public_reason")
        if case.field_order_id == "stance-confidence-reason"
        else ("public_reason", "confidence", "stance")
    )
    return json.dumps({name: values[name] for name in order}, separators=(",", ":"))


def labels(*, contradiction="consistent"):
    return {
        "refusal": "answered",
        "stance_consistency": contradiction,
        "single_construct": "yes",
    }


def code(bundle, item, coder, *, values=None, status="completed", failure_code=None):
    return IndependentCode.create(
        item=item,
        policy=bundle.policy,
        export_hash=bundle.review_export.export_hash,
        coder_id=coder,
        timestamp="2026-09-06T00:00:00Z",
        evidence_identity=f"evidence-{coder}",
        labels={} if values is None and status == "failed" else (values or labels()),
        raw_evidence_hash=canonical_payload_hash([item.item_id, coder, status]),
        status=status,
        failure_code=failure_code,
    )


def complete_codes(bundle, *, disagreement_item=None):
    result = []
    for item in bundle.review_export.items:
        for coder in ("coder-a", "coder-b"):
            values = labels(
                contradiction="contradiction"
                if item.item_id == disagreement_item and coder == "coder-b"
                else "consistent"
            )
            result.append(code(bundle, item, coder, values=values))
    return tuple(result)


def test_policy_and_records_are_frozen_hash_bound_and_json_safe():
    p = review_policy()
    restored = SemanticReviewPolicy.from_payload(json.loads(json.dumps(p.to_payload())))
    assert restored == p
    assert p.metadata == {
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
    }
    with pytest.raises(FrozenInstanceError):
        p.policy_id = "changed"
    with pytest.raises(ValueError, match="hash"):
        SemanticReviewPolicy.from_payload({**p.to_payload(), "record_hash": "f" * 64})

    bundle = export_blind_review(*prepared(policy=p))
    transported = json.loads(json.dumps(bundle.to_payload()))
    assert SemanticReviewBundle.from_payload(transported) == bundle
    with pytest.raises(ValueError, match="fields|exact"):
        SemanticReviewBundle.from_payload({**transported, "formal_decision": True})


def test_blind_export_has_exact_allowlist_and_separate_hidden_bindings():
    bundle = export_blind_review(*prepared())
    assert bundle.review_export.items
    for item in bundle.review_export.items:
        assert tuple(item.visible_payload) == bundle.policy.visible_field_allowlist
        assert set(item.visible_payload) == {
            "topic_text",
            "history_text",
            "identity_text",
            "response_text",
        }
        payload = item.to_payload()
        forbidden = {
            "condition",
            "candidate_id",
            "stratum_id",
            "requested_seed",
            "generation_settings",
            "aggregate_result",
            "probe_case_id",
            "parse_hash",
        }
        assert forbidden.isdisjoint(payload) and forbidden.isdisjoint(payload["visible_payload"])
    assert all(binding.probe_case_id for binding in bundle.hidden_bindings)


def test_export_ids_and_order_are_stable_under_input_reordering():
    specification, cases, run, policy = prepared()
    first = export_blind_review(specification, cases, run, policy)
    second = export_blind_review(specification, tuple(reversed(cases)), run, policy)
    assert first.review_export.to_payload() == second.review_export.to_payload()
    assert first.hidden_bindings == second.hidden_bindings


def test_strata_are_complete_exact_and_insufficient_fails_closed():
    strata = (
        ReviewStratum("topic", {"case_family": "topic_quality"}, 2),
        ReviewStratum("identity", {"case_family": "identity"}, 1),
    )
    bundle = export_blind_review(*prepared(policy=review_policy(strata=strata)))
    assert [item.stratum_id for item in bundle.hidden_bindings].count("topic") == 2
    assert [item.stratum_id for item in bundle.hidden_bindings].count("identity") == 1
    bad = review_policy(strata=(ReviewStratum("identity", {"case_family": "identity"}, 3),))
    with pytest.raises(ValueError, match="insufficient"):
        export_blind_review(*prepared(policy=bad))


def test_visible_payload_rejects_nested_or_extra_fields_and_hash_drift():
    bundle = export_blind_review(*prepared())
    item = bundle.review_export.items[0]
    with pytest.raises((TypeError, ValueError), match="visible|allowlist"):
        replace(
            item, visible_payload={**dict(item.visible_payload), "response_text": {"nested": "x"}}
        )
    with pytest.raises((TypeError, ValueError), match="visible|allowlist"):
        replace(item, visible_payload={**dict(item.visible_payload), "condition_name": "hidden"})
    with pytest.raises(ValueError, match="hash"):
        replace(item, visible_payload_hash="f" * 64)


def test_import_marks_judge_failure_and_missing_coder_incomplete():
    bundle = export_blind_review(*prepared())
    item = bundle.review_export.items[0]
    failed = code(bundle, item, "coder-b", status="failed", failure_code="provider_timeout")
    partial = tuple(code(bundle, x, "coder-a") for x in bundle.review_export.items) + (failed,)
    imported = import_review_codes(bundle, partial)
    assert imported.status == "review_incomplete"
    assert imported.final_labels == ()
    with pytest.raises(ValueError, match="complete|final|status"):
        replace(imported, status="complete")


def test_import_rejects_duplicate_unexpected_coder_item_dimension_and_invalid_types():
    bundle = export_blind_review(*prepared())
    codes = complete_codes(bundle)
    with pytest.raises(ValueError, match="duplicate"):
        import_review_codes(bundle, codes + (codes[0],))
    from copy import copy

    unexpected_coder = copy(codes[0])
    object.__setattr__(unexpected_coder, "coder_id", "coder-z")
    with pytest.raises(ValueError, match="coder"):
        import_review_codes(bundle, (unexpected_coder,) + codes[1:])
    unexpected_item = copy(codes[0])
    object.__setattr__(unexpected_item, "item_id", "blind-item-" + "f" * 64)
    with pytest.raises(ValueError, match="item"):
        import_review_codes(bundle, (unexpected_item,) + codes[1:])
    with pytest.raises(ValueError, match="dimension|label"):
        IndependentCode.create(
            item=bundle.review_export.items[0],
            policy=bundle.policy,
            export_hash=bundle.review_export.export_hash,
            coder_id="coder-a",
            timestamp="2026-09-06T00:00:00Z",
            evidence_identity="bad-dimension",
            labels={**labels(), "extra": "yes"},
            raw_evidence_hash="f" * 64,
            status="completed",
            failure_code=None,
        )
    with pytest.raises((TypeError, ValueError), match="label"):
        IndependentCode.create(
            item=bundle.review_export.items[0],
            policy=bundle.policy,
            export_hash=bundle.review_export.export_hash,
            coder_id="coder-a",
            timestamp="2026-09-06T00:00:00Z",
            evidence_identity="bad-label",
            labels={**labels(), "refusal": True},
            raw_evidence_hash="f" * 64,
            status="completed",
            failure_code=None,
        )


@pytest.mark.parametrize(
    "threshold,expected",
    [(Fraction(8, 9), "adjudication_required"), (Fraction(9, 10), "review_incomplete")],
)
def test_exact_agreement_boundary_and_disagreement_trigger(threshold, expected):
    bundle = export_blind_review(*prepared(policy=review_policy(threshold=threshold)))
    disputed = bundle.review_export.items[0].item_id
    imported = import_review_codes(bundle, complete_codes(bundle, disagreement_item=disputed))
    assert imported.agreement == Fraction(8, 9)
    assert imported.status == expected


def test_adjudication_is_append_only_required_only_and_final_aggregation_is_bound():
    bundle = export_blind_review(*prepared(policy=review_policy(threshold=Fraction(8, 9))))
    disputed = bundle.review_export.items[0]
    imported = import_review_codes(
        bundle, complete_codes(bundle, disagreement_item=disputed.item_id)
    )
    before = json.dumps([c.to_payload() for c in imported.independent_codes], sort_keys=True)
    adjudication = Adjudication.create(
        bundle=imported,
        item_id=disputed.item_id,
        adjudicator_id="adjudicator-a",
        timestamp="2026-09-06T01:00:00Z",
        labels=labels(contradiction="contradiction"),
        reason="Independent coders disagreed on stance consistency.",
        evidence_hash=canonical_payload_hash("adjudication-evidence"),
    )
    completed = append_adjudication(imported, adjudication)
    after = json.dumps([c.to_payload() for c in completed.independent_codes], sort_keys=True)
    assert before == after
    assert completed.status == "complete"
    assert (
        next(x for x in completed.final_labels if x.item_id == disputed.item_id).labels[
            "stance_consistency"
        ]
        == "contradiction"
    )
    with pytest.raises(ValueError, match="disputed|required"):
        Adjudication.create(
            bundle=imported,
            item_id=imported.review_export.items[1].item_id,
            adjudicator_id="adjudicator-a",
            timestamp="2026-09-06T01:00:00Z",
            labels=labels(),
            reason="Not disputed.",
            evidence_hash="f" * 64,
        )
    with pytest.raises(ValueError, match="duplicate|already"):
        append_adjudication(completed, adjudication)


def test_upstream_policy_and_parse_hash_mismatch_are_rejected():
    args = prepared()
    specification, cases, run, policy = args
    with pytest.raises(ValueError, match="policy"):
        export_blind_review(specification, cases, run, replace(policy, policy_version="2.0.0"))
    bundle = export_blind_review(*args)
    binding = bundle.hidden_bindings[0]
    with pytest.raises(ValueError, match="hash|binding"):
        replace(binding, parse_hash="f" * 64)


def test_bridge_uses_only_authorized_labels_and_incomplete_review_suppresses_gates():
    specification, cases, run, policy = prepared()
    bundle = export_blind_review(specification, cases, run, policy)
    imported = import_review_codes(bundle, ())
    parses = tuple(a.parse_evidence for a in run.attempts if a.parse_evidence is not None)
    evidence = to_semantic_gate_evidence(imported, cases, parses)
    assert evidence and all(not item.review_complete for item in evidence)
    assert all(item.contradiction == "indeterminate" for item in evidence)

    gate_algorithm = algorithm(required_challenges())
    full_policy = review_policy(strata=(ReviewStratum("one", {}, 1),))
    payload = probe_spec_payload()
    payload["policy_hashes"]["semantic_review_policy"] = full_policy.record_hash
    payload["policy_hashes"]["gate_algorithm"] = gate_algorithm.record_hash
    full_spec = load_probe_specification(payload)
    full_cases = expand_probe_cases(full_spec)
    steps = {
        (case.probe_case_id, 1): ProbeScriptStep("response", raw_for(case), None, None)
        for case in full_cases
    }
    full_run = execute_probe_run(
        run_instance_id="review-gate-test",
        specification_hash=full_spec.output_hash,
        cases=full_cases,
        runtime_policy=runtime_policy(),
        adapter=ScriptedProbeAdapter(steps),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    incomplete = import_review_codes(
        export_blind_review(full_spec, full_cases, full_run, full_policy), ()
    )
    full_parses = tuple(a.parse_evidence for a in full_run.attempts if a.parse_evidence is not None)
    bridge = to_semantic_gate_evidence(incomplete, full_cases, full_parses)
    report = evaluate_quality_gates(
        full_spec,
        full_cases,
        full_run,
        gate_algorithm,
        bridge,
        candidate_key="retirement-delay",
    )
    assert report.status == "review_incomplete" and report.passed is None
