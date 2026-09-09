from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import json

import pytest

import agent_ex.calibration.review as review_module
from agent_ex.calibration.adapters import ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.gates import evaluate_quality_gates
from agent_ex.calibration.review import (
    Adjudication,
    BlindReviewExport,
    CoderContract,
    HiddenReviewBinding,
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
PASSING_LABELS = {
    "refusal": ("answered",),
    "stance_consistency": ("consistent",),
    "single_construct": ("yes",),
}
CODERS = (
    CoderContract("coder-a", "human", "stratified_sample"),
    CoderContract(
        "coder-b",
        "judge",
        "all_eligible",
        model_id="synthetic-judge",
        model_revision="offline-v1",
        judge_prompt_hash=canonical_payload_hash("synthetic-judge-prompt"),
        ordering_policy_id="synthetic-ordering",
        ordering_policy_hash=canonical_payload_hash("synthetic-ordering-v1"),
        runtime_provider="scripted-judge",
        runtime_version="1.0.0",
    ),
)


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
        required_human_coder_count=1,
        required_judge_coder_count=1,
        randomization_domain="phase0a-synthetic-semantic-review",
        dimension_labels=DIMENSIONS,
        passing_labels=PASSING_LABELS,
        agreement_statistic="exact_item_dimension_agreement",
        agreement_scope="all_assigned_codes_on_human_sample",
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


def prepared_exact(policy, scenario_ids):
    payload = probe_spec_payload()
    payload["policy_hashes"]["semantic_review_policy"] = policy.record_hash
    specification = load_probe_specification(payload)
    expanded = expand_probe_cases(specification)
    cases = tuple(
        sorted(
            (
                next(case for case in expanded if case.scenario_id == scenario_id)
                for scenario_id in scenario_ids
            ),
            key=lambda item: item.probe_case_id,
        )
    )
    steps = {
        (case.probe_case_id, 1): ProbeScriptStep("response", raw_for(case), None, None)
        for case in cases
    }
    run = execute_probe_run(
        run_instance_id="review-exact-test",
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


def labels(*, contradiction="consistent", single_construct="yes"):
    return {
        "refusal": "answered",
        "stance_consistency": contradiction,
        "single_construct": single_construct,
    }


def code(bundle, item, coder, *, values=None, status="completed", failure_code=None):
    is_judge = next(x.role for x in bundle.policy.coder_contracts if x.coder_id == coder) == "judge"
    return IndependentCode.create(
        item=item,
        policy=bundle.policy,
        export_hash=bundle.review_export.export_hash,
        coder_id=coder,
        timestamp="2026-09-06T00:00:00Z",
        evidence_identity=f"evidence-{coder}",
        judge_request_id=f"judge-request-{coder}" if is_judge else None,
        judge_order_id=f"judge-order-{coder}" if is_judge else None,
        provider_output_artifact_id=f"provider-output-{coder}" if is_judge else None,
        provider_output_artifact_hash=(
            canonical_payload_hash([item.item_id, coder, "provider-output"]) if is_judge else None
        ),
        labels={} if values is None and status == "failed" else (values or labels()),
        raw_evidence_hash=canonical_payload_hash([item.item_id, coder, status]),
        status=status,
        failure_code=failure_code,
    )


def complete_codes(bundle, *, disagreement_item=None):
    result = []
    for contract in bundle.policy.coder_contracts:
        coder = contract.coder_id
        for item in review_module.items_for_coder(bundle, coder):
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

    for field in ("dimension_labels", "passing_labels"):
        for invalid in ({"answered": None}, "answered"):
            malformed = json.loads(json.dumps(p.to_payload()))
            malformed[field]["refusal"] = invalid
            with pytest.raises(TypeError, match="arrays"):
                SemanticReviewPolicy.from_payload(malformed)

    bundle = export_blind_review(*prepared(policy=p))
    transported = json.loads(json.dumps(bundle.to_payload()))
    assert SemanticReviewBundle.from_payload(transported) == bundle
    with pytest.raises(ValueError, match="fields|exact"):
        SemanticReviewBundle.from_payload({**transported, "formal_decision": True})


def test_all_review_records_accept_canonical_sorted_json_object_keys():
    specification, cases, run, policy = prepared(policy=review_policy(threshold=Fraction(8, 9)))
    awaiting = export_blind_review(specification, cases, run, policy)
    disputed = review_module.items_for_coder(awaiting, "coder-a")[0].item_id
    coded = import_review_codes(awaiting, complete_codes(awaiting, disagreement_item=disputed))
    item = awaiting.review_export.items[0]
    adjudication = Adjudication.create(
        bundle=coded,
        item_id=item.item_id,
        adjudicator_id="adjudicator-sorted-json",
        timestamp="2026-09-06T01:00:00Z",
        labels=labels(contradiction="consistent"),
        reason="synthetic disagreement resolution",
        evidence_hash=canonical_payload_hash("synthetic-adjudication-evidence"),
    )
    completed = append_adjudication(coded, adjudication)
    canonical_json = json.loads(json.dumps(completed.to_payload(), sort_keys=True))
    assert SemanticReviewBundle.from_payload(canonical_json) == completed


def test_policy_rejects_bare_judge_and_human_only_completion_contract():
    with pytest.raises(ValueError, match="scope|assignment"):
        CoderContract("bad-human-scope", "human", "all_eligible")
    with pytest.raises(ValueError, match="scope|assignment"):
        CoderContract("bad-judge-scope", "judge", "stratified_sample")
    with pytest.raises(ValueError, match="judge|provenance|model|prompt"):
        CoderContract("bare-judge", "judge", "all_eligible")
    base = review_policy()
    with pytest.raises(ValueError, match="judge|human|role|coder"):
        replace(
            base,
            coder_contracts=(CoderContract("only-human", "human", "stratified_sample"),),
        )


def test_judge_reviews_all_eligible_cases_while_human_sees_only_stratified_sample():
    scoped_coders = (
        CoderContract("coder-a", "human", assignment_scope="stratified_sample"),
        CoderContract(
            "coder-b",
            "judge",
            assignment_scope="all_eligible",
            model_id="synthetic-judge",
            model_revision="offline-v1",
            judge_prompt_hash=canonical_payload_hash("synthetic-judge-prompt"),
            ordering_policy_id="synthetic-ordering",
            ordering_policy_hash=canonical_payload_hash("synthetic-ordering-v1"),
            runtime_provider="scripted-judge",
            runtime_version="1.0.0",
        ),
    )
    policy = replace(
        review_policy(),
        coder_contracts=scoped_coders,
        agreement_scope="all_assigned_codes_on_human_sample",
    )
    specification, cases, run, _ = prepared(policy=policy)
    awaiting = export_blind_review(specification, cases, run, policy)
    judge_items = review_module.items_for_coder(awaiting, "coder-b")
    human_items = review_module.items_for_coder(awaiting, "coder-a")
    assert len(awaiting.review_export.items) == len(cases) == 6
    assert len(judge_items) == 6
    assert len(human_items) == 3
    judge_only_ids = {item.item_id for item in judge_items} - {item.item_id for item in human_items}
    assert len(judge_only_ids) == 3
    assert all(item.item_id not in judge_only_ids for item in human_items)
    codes = tuple(
        code(awaiting, item, coder.coder_id)
        for coder in policy.coder_contracts
        for item in review_module.items_for_coder(awaiting, coder.coder_id)
    )
    assert sum(code_record.coder_role == "judge" for code_record in codes) == 6
    assert sum(code_record.coder_role == "human" for code_record in codes) == 3
    completed = import_review_codes(awaiting, codes)
    assert completed.status == "complete"
    parses = tuple(a.parse_evidence for a in run.attempts if a.parse_evidence is not None)
    bridge = to_semantic_gate_evidence(completed, specification, cases, run, parses)
    assert len(bridge) == 6 and all(item.review_complete for item in bridge)
    unsampled = next(item for item in judge_items if item not in human_items)
    with pytest.raises(ValueError, match="assigned|unexpected|scope"):
        import_review_codes(awaiting, codes + (code(awaiting, unsampled, "coder-a"),))


def test_judge_code_binds_contract_request_order_provider_and_raw_artifact():
    bundle = export_blind_review(*prepared())
    item = bundle.review_export.items[0]
    judge_code = code(bundle, item, "coder-b")
    judge_contract = next(x for x in bundle.policy.coder_contracts if x.role == "judge")
    assert judge_code.coder_contract_hash == judge_contract.record_hash
    assert judge_code.judge_request_id == "judge-request-coder-b"
    assert judge_code.judge_order_id == "judge-order-coder-b"
    assert judge_code.provider_output_artifact_id == "provider-output-coder-b"
    assert judge_code.provider_output_artifact_hash == canonical_payload_hash(
        [item.item_id, "coder-b", "provider-output"]
    )
    from copy import copy

    drifted = copy(judge_code)
    object.__setattr__(drifted, "coder_contract_hash", "f" * 64)
    codes = list(complete_codes(bundle))
    codes[
        codes.index(next(x for x in codes if x.item_id == item.item_id and x.coder_id == "coder-b"))
    ] = drifted
    with pytest.raises(ValueError, match="contract|judge|provenance|hash"):
        import_review_codes(bundle, tuple(codes))

    raw_drifted = copy(judge_code)
    object.__setattr__(raw_drifted, "provider_output_artifact_hash", "e" * 64)
    codes = list(complete_codes(bundle))
    codes[
        codes.index(next(x for x in codes if x.item_id == item.item_id and x.coder_id == "coder-b"))
    ] = raw_drifted
    with pytest.raises(ValueError, match="judge|provenance|artifact|record|hash"):
        import_review_codes(bundle, tuple(codes))

    with pytest.raises(ValueError, match="judge|provenance|request|provider"):
        IndependentCode.create(
            item=item,
            policy=bundle.policy,
            export_hash=bundle.review_export.export_hash,
            coder_id="coder-b",
            timestamp="2026-09-06T00:00:00Z",
            evidence_identity="missing-judge-provider-output",
            judge_request_id=None,
            judge_order_id="judge-order-coder-b",
            provider_output_artifact_id="provider-output-coder-b",
            provider_output_artifact_hash="f" * 64,
            labels=labels(),
            raw_evidence_hash="f" * 64,
            status="completed",
            failure_code=None,
        )


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


def test_visible_fields_are_exact_semantic_blocks_without_factor_crosstalk():
    scenario_ids = (
        "topic-retirement-delay",
        "identity-i0-c1-identity-continuity",
        "identity-i1-c0-identity-continuity",
        "continuity-i0-c1-continuity-balanced-a-identity-continuity-warranted-update",
    )
    strata = tuple(
        ReviewStratum(f"semantic-{index}", {"scenario_id": scenario_id}, 1)
        for index, scenario_id in enumerate(scenario_ids)
    )
    policy = review_policy(strata=strata)
    specification, cases, run, _ = prepared_exact(policy, scenario_ids)
    bundle = export_blind_review(specification, cases, run, policy)
    by_scenario = {
        next(
            case.scenario_id for case in cases if case.probe_case_id == binding.probe_case_id
        ): next(
            item.visible_payload
            for item in bundle.review_export.items
            if item.item_id == binding.item_id
        )
        for binding in bundle.hidden_bindings
    }
    identity_block = specification.payload["persona"]["identity_block"]
    history = next(
        item["history"]
        for item in specification.payload["continuity_scenarios"]
        if item["scenario_id"] == "warranted-update"
    )
    assert by_scenario[scenario_ids[0]]["identity_text"] == ""
    assert by_scenario[scenario_ids[0]]["history_text"] == ""
    assert by_scenario[scenario_ids[1]]["identity_text"] == ""
    assert by_scenario[scenario_ids[1]]["history_text"] == ""
    assert by_scenario[scenario_ids[2]]["identity_text"] == identity_block
    assert by_scenario[scenario_ids[2]]["history_text"] == ""
    assert by_scenario[scenario_ids[3]]["identity_text"] == ""
    assert by_scenario[scenario_ids[3]]["history_text"] == history
    for visible in by_scenario.values():
        assert identity_block not in visible["topic_text"]
        assert history not in visible["identity_text"]


def test_export_ids_and_order_are_stable_under_input_reordering():
    specification, cases, run, policy = prepared()
    first = export_blind_review(specification, cases, run, policy)
    second = export_blind_review(specification, tuple(reversed(cases)), run, policy)
    assert first.review_export.to_payload() == second.review_export.to_payload()
    assert first.hidden_bindings == second.hidden_bindings


def test_sampling_membership_and_order_do_not_depend_on_successful_response_content():
    specification, cases, run_a, policy = prepared()
    steps = {
        (case.probe_case_id, 1): ProbeScriptStep(
            "response",
            raw_for(case).replace("Synthetic reason.", "Completely different evidence."),
            None,
            None,
        )
        for case in cases
    }
    run_b = execute_probe_run(
        run_instance_id="review-response-independent-sampling",
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
    export_a = export_blind_review(specification, cases, run_a, policy)
    export_b = export_blind_review(specification, cases, run_b, policy)
    assert [binding.probe_case_id for binding in export_a.hidden_bindings] == [
        binding.probe_case_id for binding in export_b.hidden_bindings
    ]
    assert [
        binding.probe_case_id
        for binding in export_a.hidden_bindings
        if binding.human_audit_selected
    ] == [
        binding.probe_case_id
        for binding in export_b.hidden_bindings
        if binding.human_audit_selected
    ]
    assert export_a.review_export.export_hash != export_b.review_export.export_hash
    changed_domain = replace(policy, randomization_domain="different-randomization-domain")
    assert changed_domain.record_hash != policy.record_hash
    assert review_module._sampling_rank(changed_domain, changed_domain.strata[0], cases[0]) != (
        review_module._sampling_rank(policy, policy.strata[0], cases[0])
    )


def test_sampling_rank_ignores_non_sampling_policy_fields_and_sample_count():
    _, cases, _, policy = prepared()

    def logical_key(case):
        return (
            case.candidate_id,
            case.case_family,
            case.scenario_id,
            case.variant_index,
            case.scale_id,
            case.field_order_id,
            case.replicate_id,
            case.requested_seed,
            case.persona_view_id,
            case.rendered_messages_hash,
        )

    def rebuilt_human_order(candidate_policy):
        payload = probe_spec_payload()
        payload["policy_hashes"]["semantic_review_policy"] = candidate_policy.record_hash
        specification = load_probe_specification(payload)
        rebuilt_cases = expand_probe_cases(specification)
        steps = {
            (case.probe_case_id, 1): ProbeScriptStep("response", raw_for(case), None, None)
            for case in rebuilt_cases
        }
        run = execute_probe_run(
            run_instance_id="logical-sampling-" + candidate_policy.record_hash[:12],
            specification_hash=specification.output_hash,
            cases=rebuilt_cases,
            runtime_policy=runtime_policy(),
            adapter=ScriptedProbeAdapter(steps),
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
        )
        bundle = export_blind_review(specification, rebuilt_cases, run, candidate_policy)
        by_id = {case.probe_case_id: case for case in rebuilt_cases}
        return [
            logical_key(by_id[binding.probe_case_id])
            for binding in bundle.hidden_bindings
            if binding.human_audit_selected
        ]

    changed_judge = replace(
        CODERS[1],
        model_revision="offline-v2",
        judge_prompt_hash=canonical_payload_hash("different-judge-prompt"),
    )
    non_sampling_change = replace(
        policy,
        agreement_threshold=Fraction(1, 2),
        coder_contracts=(CODERS[0], changed_judge),
        classifier_version="2.0.0",
        classifier_hash=canonical_payload_hash("different-classifier"),
    )
    base_order = rebuilt_human_order(policy)
    assert rebuilt_human_order(non_sampling_change) == base_order

    larger_sample = replace(
        policy,
        strata=(
            ReviewStratum(
                policy.strata[0].stratum_id,
                dict(policy.strata[0].selectors),
                4,
            ),
        ),
    )
    assert rebuilt_human_order(larger_sample)[:3] == base_order
    assert review_module._sampling_rank(
        replace(policy, randomization_seed=policy.randomization_seed + 1),
        policy.strata[0],
        cases[0],
    ) != review_module._sampling_rank(policy, policy.strata[0], cases[0])
    changed_selector = ReviewStratum(
        policy.strata[0].stratum_id, {"case_family": cases[0].case_family}, 3
    )
    assert review_module._sampling_rank(policy, changed_selector, cases[0]) != (
        review_module._sampling_rank(policy, policy.strata[0], cases[0])
    )
    original = cases[0]
    changed_messages = tuple(dict(message) for message in original.rendered_messages)
    changed_messages[-1]["content"] += "\nSynthetic semantic prompt change."
    changed_logical_case = type(original).create(
        specification_hash=original.specification_hash,
        candidate_id=original.candidate_id,
        case_family=original.case_family,
        scenario_id=original.scenario_id,
        variant_index=original.variant_index,
        scale_id=original.scale_id,
        field_order_id=original.field_order_id,
        replicate_id=original.replicate_id,
        requested_seed=original.requested_seed,
        persona_view_id=original.persona_view_id,
        rendered_messages=changed_messages,
    )
    assert review_module._logical_case_sampling_hash(changed_logical_case) != (
        review_module._logical_case_sampling_hash(original)
    )
    assert review_module._sampling_rank(
        policy, policy.strata[0], changed_logical_case
    ) != review_module._sampling_rank(policy, policy.strata[0], original)


def test_strata_are_complete_exact_and_insufficient_fails_closed():
    strata = (
        ReviewStratum("topic", {"case_family": "topic_quality"}, 2),
        ReviewStratum("identity", {"case_family": "identity"}, 1),
        ReviewStratum("continuity", {"case_family": "continuity"}, 1),
    )
    bundle = export_blind_review(*prepared(policy=review_policy(strata=strata)))
    assert (
        sum(
            item.stratum_id == "topic" and item.human_audit_selected
            for item in bundle.hidden_bindings
        )
        == 2
    )
    assert (
        sum(
            item.stratum_id == "identity" and item.human_audit_selected
            for item in bundle.hidden_bindings
        )
        == 1
    )
    bad = review_policy(strata=(ReviewStratum("all", {}, 7),))
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
    specification, cases, run, policy = prepared()
    bundle = export_blind_review(specification, cases, run, policy)
    item = bundle.review_export.items[0]
    failed = code(bundle, item, "coder-b", status="failed", failure_code="provider_timeout")
    partial = tuple(
        code(bundle, x, "coder-a") for x in review_module.items_for_coder(bundle, "coder-a")
    ) + (failed,)
    imported = import_review_codes(bundle, partial)
    assert imported.status == "review_incomplete"
    assert imported.final_labels == ()
    parses = tuple(a.parse_evidence for a in run.attempts if a.parse_evidence is not None)
    bridge = to_semantic_gate_evidence(imported, specification, cases, run, parses)
    assert bridge and all(not evidence.review_complete for evidence in bridge)
    assert all(evidence.contradiction == "indeterminate" for evidence in bridge)
    judge_only = tuple(
        code(bundle, item, "coder-b") for item in review_module.items_for_coder(bundle, "coder-b")
    )
    missing_human = import_review_codes(bundle, judge_only)
    assert missing_human.status == "review_incomplete"
    assert all(
        not evidence.review_complete
        for evidence in to_semantic_gate_evidence(missing_human, specification, cases, run, parses)
    )
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
            judge_request_id=None,
            judge_order_id=None,
            provider_output_artifact_id=None,
            provider_output_artifact_hash=None,
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
            judge_request_id=None,
            judge_order_id=None,
            provider_output_artifact_id=None,
            provider_output_artifact_hash=None,
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
    disputed = review_module.items_for_coder(bundle, "coder-a")[0].item_id
    imported = import_review_codes(bundle, complete_codes(bundle, disagreement_item=disputed))
    assert imported.agreement == Fraction(8, 9)
    assert imported.status == expected


def test_adjudication_is_append_only_required_only_and_final_aggregation_is_bound():
    bundle = export_blind_review(*prepared(policy=review_policy(threshold=Fraction(8, 9))))
    disputed = review_module.items_for_coder(bundle, "coder-a")[0]
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


def test_hash_valid_hidden_binding_swap_and_refusal_transfer_fail_closed():
    bundle = export_blind_review(*prepared())
    completed = import_review_codes(bundle, complete_codes(bundle))
    first, second = completed.hidden_bindings[:2]
    forged_payload = first.to_payload()
    second_payload = second.to_payload()
    for name in (
        "probe_case_id",
        "probe_case_hash",
        "request_id",
        "request_hash",
        "response_id",
        "response_hash",
        "parse_id",
        "parse_hash",
    ):
        forged_payload[name] = second_payload[name]
    forged_payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in forged_payload.items() if key != "record_hash"}
    )
    with pytest.raises(ValueError, match="item|binding|opaque|upstream"):
        forged = HiddenReviewBinding.from_payload(forged_payload)
        replace(completed, hidden_bindings=(forged,) + completed.hidden_bindings[1:])


def test_bridge_rejects_hash_valid_replacement_of_sampled_human_assignment():
    specification, cases, run, policy = prepared()
    original = export_blind_review(specification, cases, run, policy)
    victim_binding = next(x for x in original.hidden_bindings if x.human_audit_selected)
    replacement_binding = next(x for x in original.hidden_bindings if not x.human_audit_selected)
    bindings = list(original.hidden_bindings)
    for binding, selected in ((victim_binding, False), (replacement_binding, True)):
        payload = binding.to_payload()
        payload["human_audit_selected"] = selected
        payload["assigned_coder_ids"] = ["coder-b", "coder-a"] if selected else ["coder-b"]
        payload["record_hash"] = canonical_payload_hash(
            {key: value for key, value in payload.items() if key != "record_hash"}
        )
        bindings[bindings.index(binding)] = HiddenReviewBinding.from_payload(payload)
    awaiting = SemanticReviewBundle(
        policy,
        original.review_export,
        tuple(bindings),
        (),
        (),
        None,
        "awaiting_codes",
        (),
    )
    forged = import_review_codes(awaiting, complete_codes(awaiting))
    assert forged.status == "complete"
    parses = tuple(a.parse_evidence for a in run.attempts if a.parse_evidence is not None)
    with pytest.raises(ValueError, match="sample|export|selection|expected"):
        to_semantic_gate_evidence(forged, specification, cases, run, parses)

    reordered_payload = original.review_export.to_payload()
    reordered_payload["items"] = [
        item.to_payload() for item in reversed(original.review_export.items)
    ]
    reordered_payload["export_hash"] = canonical_payload_hash(
        {key: value for key, value in reordered_payload.items() if key != "export_hash"}
    )
    reordered = SemanticReviewBundle(
        policy,
        BlindReviewExport.from_payload(reordered_payload),
        tuple(reversed(original.hidden_bindings)),
        (),
        (),
        None,
        "awaiting_codes",
        (),
    )
    with pytest.raises(ValueError, match="sample|export|selection|expected"):
        to_semantic_gate_evidence(reordered, specification, cases, run, parses)


def test_bridge_rebuilds_request_response_and_visible_payload_before_labels_transfer():
    specification, cases, run, policy = prepared()
    bundle = import_review_codes(
        export_blind_review(specification, cases, run, policy),
        complete_codes(export_blind_review(specification, cases, run, policy)),
    )
    parses = tuple(a.parse_evidence for a in run.attempts if a.parse_evidence is not None)
    assert all(
        item.review_complete
        for item in to_semantic_gate_evidence(bundle, specification, cases, run, parses)
        if item.case_id in {binding.probe_case_id for binding in bundle.hidden_bindings}
    )

    attacked = bundle.review_export.items[0]
    original_visible_payload = attacked.visible_payload
    object.__setattr__(
        attacked,
        "visible_payload",
        {**attacked.visible_payload, "response_text": "transferred refusal"},
    )
    with pytest.raises(ValueError, match="visible|upstream|binding|hash"):
        to_semantic_gate_evidence(bundle, specification, cases, run, parses)
    object.__setattr__(attacked, "visible_payload", original_visible_payload)

    attacked_binding = bundle.hidden_bindings[0]
    object.__setattr__(attacked_binding, "policy_id", "transferred-policy")
    with pytest.raises(ValueError, match="policy|binding|hash"):
        to_semantic_gate_evidence(bundle, specification, cases, run, parses)


def test_bridge_selects_final_successful_parse_after_format_repair():
    policy = review_policy(strata=(ReviewStratum("all", {}, 1),))
    payload = probe_spec_payload()
    payload["policy_hashes"]["semantic_review_policy"] = policy.record_hash
    specification = load_probe_specification(payload)
    case = expand_probe_cases(specification)[0]
    cases = (case,)
    run = execute_probe_run(
        run_instance_id="review-format-repair-test",
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy(),
        adapter=ScriptedProbeAdapter(
            {
                (case.probe_case_id, 1): ProbeScriptStep("response", "not-json", None, None),
                (case.probe_case_id, 2): ProbeScriptStep("response", raw_for(case), None, None),
            }
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    awaiting = export_blind_review(specification, cases, run, policy)
    completed = import_review_codes(awaiting, complete_codes(awaiting))
    parses = tuple(
        attempt.parse_evidence for attempt in run.attempts if attempt.parse_evidence is not None
    )

    assert [parse.success for parse in parses] == [False, True]
    bridge = to_semantic_gate_evidence(completed, specification, cases, run, parses)
    assert len(bridge) == 1
    assert bridge[0].case_id == case.probe_case_id
    assert bridge[0].parse_hash == parses[-1].record_hash
    assert bridge[0].review_complete is True
    assert (
        to_semantic_gate_evidence(completed, specification, cases, run, tuple(reversed(parses)))
        == bridge
    )
    with pytest.raises(ValueError, match="parse|duplicate|missing|extra"):
        to_semantic_gate_evidence(completed, specification, cases, run, parses + (parses[-1],))
    with pytest.raises(ValueError, match="parse|duplicate|missing|extra"):
        to_semantic_gate_evidence(completed, specification, cases, run, parses[1:])


def test_bridge_omits_nonterminal_failed_parse_and_rejects_cross_run_parse():
    policy = review_policy(strata=(ReviewStratum("all", {}, 1),))
    payload = probe_spec_payload()
    payload["policy_hashes"]["semantic_review_policy"] = policy.record_hash
    specification = load_probe_specification(payload)
    cases = tuple(sorted(expand_probe_cases(specification)[:2], key=lambda x: x.probe_case_id))
    successful, nonterminal = cases
    run = execute_probe_run(
        run_instance_id="review-nonterminal-parse-test",
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy(),
        adapter=ScriptedProbeAdapter(
            {
                (successful.probe_case_id, 1): ProbeScriptStep(
                    "response", raw_for(successful), None, None
                ),
                (nonterminal.probe_case_id, 1): ProbeScriptStep("response", "not-json", None, None),
            }
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        stop_after_attempts=2,
    )
    assert run.status == "incomplete"
    assert run.case_statuses[nonterminal.probe_case_id] == "format_pending"
    awaiting = export_blind_review(specification, cases, run, policy)
    completed = import_review_codes(awaiting, complete_codes(awaiting))
    parses = tuple(
        attempt.parse_evidence for attempt in run.attempts if attempt.parse_evidence is not None
    )

    bridge = to_semantic_gate_evidence(completed, specification, cases, run, parses)
    assert tuple(item.case_id for item in bridge) == (successful.probe_case_id,)
    assert bridge[0].parse_hash == next(parse.record_hash for parse in parses if parse.success)

    alien_case = next(
        case
        for case in expand_probe_cases(specification)
        if case.probe_case_id not in set(run.case_statuses)
    )
    alien_run = execute_probe_run(
        run_instance_id="review-alien-parse-test",
        specification_hash=specification.output_hash,
        cases=(alien_case,),
        runtime_policy=runtime_policy(),
        adapter=ScriptedProbeAdapter(
            {
                (alien_case.probe_case_id, 1): ProbeScriptStep(
                    "response", raw_for(alien_case), None, None
                )
            }
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    alien_parse = alien_run.attempts[0].parse_evidence
    assert alien_parse is not None
    with pytest.raises(ValueError, match="parse|missing|extra|run"):
        to_semantic_gate_evidence(
            completed,
            specification,
            cases,
            run,
            (alien_parse,) + parses[1:],
        )


def test_bridge_uses_only_authorized_labels_and_incomplete_review_suppresses_gates():
    specification, cases, run, policy = prepared()
    bundle = export_blind_review(specification, cases, run, policy)
    imported = import_review_codes(bundle, ())
    parses = tuple(a.parse_evidence for a in run.attempts if a.parse_evidence is not None)
    evidence = to_semantic_gate_evidence(imported, specification, cases, run, parses)
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
    bridge = to_semantic_gate_evidence(incomplete, full_spec, full_cases, full_run, full_parses)
    report = evaluate_quality_gates(
        full_spec,
        full_cases,
        full_run,
        gate_algorithm,
        bridge,
        candidate_key="retirement-delay",
    )
    assert report.status == "review_incomplete" and report.passed is None


def test_bridge_preserves_every_policy_dimension_and_marks_adverse_labels() -> None:
    specification, cases, run, policy = prepared()
    pending = export_blind_review(specification, cases, run, policy)
    target = pending.review_export.items[0]
    codes = []
    for contract in pending.policy.coder_contracts:
        for item in review_module.items_for_coder(pending, contract.coder_id):
            values = labels(single_construct="no") if item.item_id == target.item_id else labels()
            codes.append(code(pending, item, contract.coder_id, values=values))
    completed = import_review_codes(pending, tuple(codes))
    parses = tuple(a.parse_evidence for a in run.attempts if a.parse_evidence is not None)
    bridge = to_semantic_gate_evidence(completed, specification, cases, run, parses)
    target_case_id = next(
        item.probe_case_id for item in completed.hidden_bindings if item.item_id == target.item_id
    )
    evidence = next(item for item in bridge if item.case_id == target_case_id)
    assert dict(evidence.dimension_labels) == {
        "refusal": "answered",
        "single_construct": "no",
        "stance_consistency": "consistent",
    }
    assert dict(evidence.dimension_passes) == {
        "refusal": True,
        "single_construct": False,
        "stance_consistency": True,
    }
    assert evidence.semantic_passed is False
