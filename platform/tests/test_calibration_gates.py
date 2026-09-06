from fractions import Fraction
from dataclasses import replace

import pytest

from agent_ex.calibration.gates import (
    GateAlgorithm,
    GateFailure,
    PairChallenge,
    SemanticGateEvidence,
    evaluate_quality_gates,
    fold_case_attempts,
    paired_dz,
    select_topic,
    total_variation,
)
from agent_ex.calibration.contracts import ProbeCase, ProbeResponse
from agent_ex.calibration.adapters import ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.runner import execute_probe_run
from agent_ex.calibration.specification import load_probe_specification, expand_probe_cases
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload
from test_calibration_runner import (
    policy,
    GENERATION_SETTINGS,
    RUNTIME_IDENTITY,
    MODEL_IDENTITY,
    TOKENIZER_IDENTITY,
    CHAT_TEMPLATE_HASH,
    valid_raw,
    rehash_payload,
)


def algorithm(challenges=()):
    return GateAlgorithm(
        algorithm_id="synthetic-quality",
        algorithm_version="1",
        min_parse=Fraction(99, 100),
        max_refusal=Fraction(1, 100),
        min_main_categories=4,
        max_main_endpoint=Fraction(4, 5),
        max_abs_dz=Fraction(1, 5),
        max_contradiction=Fraction(1, 20),
        tv_threshold=None,
        minimum_distribution_n=1,
        classifier_id="synthetic-review",
        classifier_version="1",
        classifier_hash=canonical_payload_hash("synthetic-review-1"),
        challenges=challenges,
    )


def fixture(
    stances,
    *,
    refusals=(),
    contradictions=(),
    bad=(),
    runtime=(),
    scale="stance-1-7",
    variants=None,
    keys=None,
    alg=None,
    extra_replicate=False,
    repaired=(),
):
    alg = alg or algorithm()
    payload = probe_spec_payload()
    expanded = expand_probe_cases(load_probe_specification(payload))
    payload["replicates"] = [
        {"replicate_id": i, "requested_seed": i}
        for i in range((len(stances) + 1) // 2 if variants else len(stances))
    ]
    if extra_replicate:
        payload["replicates"].append({"replicate_id": 999, "requested_seed": 999})
    payload["policy_hashes"]["gate_algorithm"] = alg.record_hash
    spec = load_probe_specification(payload)
    cases = []
    for i in range(len(stances)):
        key = keys[i] if keys else "retirement-delay"
        original = next(c for c in expanded if c.scenario_id == "topic-" + key)
        rep = i // 2 if variants else i
        cases.append(
            ProbeCase.create(
                specification_hash=spec.output_hash,
                candidate_id=original.candidate_id,
                case_family="topic_quality",
                scenario_id=original.scenario_id,
                variant_index=variants[i] if variants else 0,
                scale_id=scale,
                field_order_id="stance-confidence-reason",
                replicate_id=rep,
                requested_seed=rep,
                persona_view_id=original.persona_view_id,
                rendered_messages=original.rendered_messages,
            )
        )
    cases = tuple(cases)
    steps = {}
    for i, c in enumerate(cases):
        if i in runtime:
            steps[c.probe_case_id, 1] = ProbeScriptStep("oom", None, "oom", None)
        elif i in bad or i in repaired:
            steps[c.probe_case_id, 1] = ProbeScriptStep("response", "bad", None, None)
            steps[c.probe_case_id, 2] = ProbeScriptStep(
                "response", valid_raw(stances[i]) if i in repaired else "bad", None, None
            )
        else:
            steps[c.probe_case_id, 1] = ProbeScriptStep(
                "response", valid_raw(stances[i]), None, None
            )
    run = execute_probe_run(
        run_instance_id="gates-test",
        specification_hash=spec.output_hash,
        cases=cases,
        runtime_policy=policy(),
        adapter=ScriptedProbeAdapter(steps),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    folded = fold_case_attempts(cases, run)
    reviews = tuple(
        SemanticGateEvidence(
            case_id=c.probe_case_id,
            case_hash=c.record_hash,
            parse_hash=folded[c.probe_case_id].final_parse.record_hash,
            classifier_id=alg.classifier_id,
            classifier_version=alg.classifier_version,
            classifier_hash=alg.classifier_hash,
            refusal=i in refusals,
            contradiction="contradiction" if i in contradictions else "consistent",
            review_complete=True,
            review_evidence_hash=canonical_payload_hash([i, "review"]),
        )
        for i, c in enumerate(cases)
        if folded[c.probe_case_id].final_parse is not None
    )
    return spec, cases, run, alg, reviews


def score(args):
    return evaluate_quality_gates(*args, candidate_key="retirement-delay")


@pytest.mark.parametrize("count,passed", [(1, True), (2, False)])
def test_parse_and_refusal_scheduled_denominators(count, passed):
    report = score(fixture([2, 3, 4, 5] * 25, bad=range(count)))
    assert report.metrics[0]["parse"]["passed"] is passed
    assert report.metrics[0]["parse"]["denominator"] == 100
    report = score(fixture([2, 3, 4, 5] * 25, refusals=range(count)))
    assert report.metrics[0]["refusal"]["passed"] is passed
    assert report.metrics[0]["distribution_count"] == 100 - count


@pytest.mark.parametrize("count,passed", [(80, True), (81, False)])
def test_endpoint_threshold_each_endpoint_separately(count, passed):
    report = score(fixture([1] * count + [2, 3, 4] + [4] * (97 - count)))
    assert report.metrics[0]["lower_endpoint"]["passed"] is passed


def test_combined_endpoint_share_is_only_diagnostic():
    report = score(fixture([1] * 45 + [7] * 45 + [2] * 5 + [3] * 5))
    metric = report.metrics[0]
    assert metric["combined_endpoints"]["passed"] is None
    assert metric["lower_endpoint"]["passed"] is True
    assert metric["upper_endpoint"]["passed"] is True


def test_challenger_does_not_inherit_main_category_gate():
    report = score(fixture([5] * 4, scale="stance-0-10"))
    assert report.metrics[0]["categories_passed"] is None


@pytest.mark.parametrize("count,passed", [(5, True), (6, False)])
def test_contradiction_boundary(count, passed):
    report = score(fixture([2, 3, 4, 5] * 25, contradictions=range(count)))
    assert report.metrics[0]["contradiction"]["passed"] is passed


@pytest.mark.parametrize("change", ["missing", "indeterminate", "hash", "incomplete"])
def test_review_missing_or_unbound_suppresses_pass(change):
    spec, cases, run, alg, reviews = fixture([2, 3, 4, 5])
    if change == "missing":
        reviews = reviews[:-1]
    elif change == "indeterminate":
        reviews = (replace(reviews[0], contradiction="indeterminate"),) + reviews[1:]
    elif change == "hash":
        reviews = (replace(reviews[0], parse_hash="f" * 64),) + reviews[1:]
    else:
        reviews = (replace(reviews[0], review_complete=False),) + reviews[1:]
    report = score((spec, cases, run, alg, reviews))
    assert report.status == "review_incomplete"
    assert report.passed is None


def test_runtime_incomplete_suppresses_pass():
    report = score(fixture([2, 3, 4, 5], runtime=(0,)))
    assert report.status == "runtime_incomplete"
    assert report.passed is None


def test_algorithm_must_be_bound_before_scoring():
    spec, cases, run, alg, reviews = fixture([2, 3, 4, 5])
    with pytest.raises(ValueError, match="algorithm"):
        score((spec, cases, run, replace(alg, max_refusal=Fraction(1, 2)), reviews))


def test_selection_rejects_summaries_and_nested_forbidden_inputs():
    with pytest.raises((TypeError, ValueError)):
        select_topic(({"candidate_key": "retirement-delay", "nested": {"p_value": 0.01}},))
    with pytest.raises(ValueError):
        select_topic((score(fixture([2, 3, 4, 5])),))


def test_exact_dz_boundary():
    from agent_ex.calibration.gates import _dz_passes

    assert paired_dz((1,) * 15 + (-1,) * 10) == pytest.approx(0.2)
    assert _dz_passes((1,) * 15 + (-1,) * 10, Fraction(1, 5))
    assert not _dz_passes((1,) * 16 + (-1,) * 9, Fraction(1, 5))


def test_paired_challenge_completeness_and_tv_reporting():
    alg = algorithm(
        (PairChallenge("wording", "topic_quality", "stance-1-7", "variant_index", 0, 1),)
    )
    args = fixture([2, 2, 3, 3, 4, 4, 5, 5], variants=[0, 1] * 4, alg=alg)
    report = score(args)
    assert report.challenges[0]["passed"] is True
    assert report.challenges[0]["valid_pairs"] == 4
    assert report.challenges[0]["tv"] == {"numerator": 0, "denominator": 1}
    report = score(fixture([2, 2, 3, 3, 4, 4, 5], variants=[0, 1] * 3 + [0], alg=alg))
    assert report.challenges[0]["passed"] is False
    assert "pairing incomplete" in report.challenges[0]["failure_reason"]


def test_failed_dz_still_reports_complete_distributions():
    alg = algorithm(
        (PairChallenge("wording", "topic_quality", "stance-1-7", "variant_index", 0, 1),)
    )
    report = score(fixture([3, 2, 4, 3, 5, 4, 6, 5], variants=[0, 1] * 4, alg=alg))
    challenge = report.challenges[0]
    assert challenge["passed"] is False
    assert challenge["tv"] == {"numerator": 1, "denominator": 4}
    assert set(challenge["left_distribution"]) == set(map(str, range(1, 8)))


def test_paired_scope_missing_from_both_sides_cannot_pass():
    alg = algorithm(
        (PairChallenge("wording", "topic_quality", "stance-1-7", "variant_index", 0, 1),)
    )
    report = score(
        fixture([2, 2, 3, 3, 4, 4, 5, 5], variants=[0, 1] * 4, alg=alg, extra_replicate=True)
    )
    assert report.challenges[0]["passed"] is False


def test_one_format_repair_is_folded_with_first_response_provenance():
    args = fixture([2, 3, 4, 5], repaired=(0,))
    folded = fold_case_attempts(args[1], args[2])
    repaired = folded[args[1][0].probe_case_id]
    assert repaired.first_parse.success is False
    assert repaired.final_parse.success is True
    assert len(repaired.attempt_hashes) == 2
    report = score(args)
    assert report.metrics[0]["first_parse"]["numerator"] == 3
    assert report.metrics[0]["parse"]["numerator"] == 4


def test_provider_unsupported_seed_is_reported_without_fake_guarantee(monkeypatch):
    original = ScriptedProbeAdapter.generate

    def unsupported(self, request):
        payload = original(self, request).to_payload()
        payload["provider_seed_supported"] = False
        payload["provider_seed_echo"] = None
        return ProbeResponse.from_payload(
            rehash_payload(payload, id_field="response_id", prefix="probe-response-")
        )

    monkeypatch.setattr(ScriptedProbeAdapter, "generate", unsupported)
    alg = algorithm(
        (PairChallenge("wording", "topic_quality", "stance-1-7", "variant_index", 0, 1),)
    )
    report = score(fixture([2, 2, 3, 3, 4, 4, 5, 5], variants=[0, 1] * 4, alg=alg))
    assert report.challenges[0]["passed"] is True
    assert report.challenges[0]["provider_seed_guaranteed"] is False


@pytest.mark.parametrize(
    "fail_indices,primary,robustness",
    [
        ((), "retirement-delay", "gm-soybean-oil"),
        ((0,), "gm-soybean-oil", "ai-net-employment"),
        ((0, 1, 2), None, None),
    ],
)
def test_fixed_selection_order(fail_indices, primary, robustness):
    keys = ["retirement-delay"] * 4 + ["gm-soybean-oil"] * 4 + ["ai-net-employment"] * 4
    values = []
    for i in range(3):
        values += [4] * 4 if i in fail_indices else [2, 3, 4, 5]
    args = fixture(values, keys=keys)
    reports = tuple(
        evaluate_quality_gates(*args, candidate_key=k) for k in reversed(tuple(dict.fromkeys(keys)))
    )
    selected = select_topic(reports)
    assert (selected.primary, selected.robustness) == (primary, robustness)
    assert selected.status == ("no_candidate" if primary is None else "proposal_only")
    assert selected.to_payload()["formal_parameter_authority"] is False


def test_selection_rejects_tampered_nested_metrics_and_incomplete_review():
    keys = ["retirement-delay"] * 4 + ["gm-soybean-oil"] * 4 + ["ai-net-employment"] * 4
    args = fixture([2, 3, 4, 5] * 3, keys=keys)
    reports = tuple(evaluate_quality_gates(*args, candidate_key=k) for k in dict.fromkeys(keys))
    tampered = replace(reports[0], metrics=({"nested": {"p_value": 0.1}},))
    with pytest.raises(ValueError, match="differs"):
        select_topic((tampered,) + reports[1:])
    args = args[:-1] + (args[-1][:-1],)
    reports = tuple(evaluate_quality_gates(*args, candidate_key=k) for k in dict.fromkeys(keys))
    with pytest.raises(ValueError, match="incomplete"):
        select_topic(reports)


def test_paired_dz_zero_variance_and_insufficient_pairs():
    assert paired_dz((0, 0)) == 0
    for values in ((1,), (1, 1)):
        with pytest.raises(GateFailure):
            paired_dz(values)


def test_paired_dz_uses_sample_standard_deviation():
    assert paired_dz((-1, 1, 1, 1)) == pytest.approx(0.5)


def test_total_variation_uses_full_scale_exactly():
    assert total_variation((1, 1, 7), (1, 7, 7), tuple(range(1, 8))) == Fraction(1, 3)
    with pytest.raises(GateFailure):
        total_variation((), (1,), tuple(range(1, 8)))
    with pytest.raises(ValueError):
        total_variation((8,), (1,), tuple(range(1, 8)))
