from fractions import Fraction
from dataclasses import replace

import pytest
from functools import lru_cache
from itertools import combinations

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
            review_policy_hash=spec.payload["policy_hashes"]["semantic_review_policy"],
            dimension_labels={
                "refusal": "answered",
                "single_construct": "yes",
                "stance_consistency": "consistent",
            },
            dimension_passes={
                "refusal": True,
                "single_construct": True,
                "stance_consistency": True,
            },
            semantic_passed=True,
            refusal=i in refusals,
            contradiction="contradiction" if i in contradictions else "consistent",
            review_complete=True,
            review_evidence_hash=canonical_payload_hash([i, "review"]),
        )
        for i, c in enumerate(cases)
        if folded[c.probe_case_id].final_parse is not None
    )
    return spec, cases, run, alg, reviews


def family_metric(args):
    """Exercise only the internal counting unit, never a candidate report."""
    from agent_ex.calibration.gates import _score_family

    _, cases, run, alg, reviews = args
    return _score_family(
        cases, fold_case_attempts(cases, run), {r.case_id: r for r in reviews}, run, alg
    )


@pytest.mark.parametrize("count,passed", [(1, True), (2, False)])
def test_parse_and_refusal_scheduled_denominators(count, passed):
    metric = family_metric(fixture([2, 3, 4, 5] * 25, bad=range(count)))
    assert metric["parse"]["passed"] is passed
    assert metric["parse"]["denominator"] == 100
    metric = family_metric(fixture([2, 3, 4, 5] * 25, refusals=range(count)))
    assert metric["refusal"]["passed"] is passed
    assert metric["distribution_count"] == 100 - count


@pytest.mark.parametrize("count,passed", [(80, True), (81, False)])
def test_endpoint_threshold_each_endpoint_separately(count, passed):
    metric = family_metric(fixture([1] * count + [2, 3, 4] + [4] * (97 - count)))
    assert metric["lower_endpoint"]["passed"] is passed


def test_combined_endpoint_share_is_only_diagnostic():
    metric = family_metric(fixture([1] * 45 + [7] * 45 + [2] * 5 + [3] * 5))
    assert metric["combined_endpoints"]["passed"] is None
    assert metric["lower_endpoint"]["passed"] is True
    assert metric["upper_endpoint"]["passed"] is True


def test_challenger_does_not_inherit_main_category_gate():
    assert family_metric(fixture([5] * 4, scale="stance-0-10"))["categories_passed"] is None


@pytest.mark.parametrize("count,passed", [(5, True), (6, False)])
def test_contradiction_boundary(count, passed):
    metric = family_metric(fixture([2, 3, 4, 5] * 25, contradictions=range(count)))
    assert metric["contradiction"]["passed"] is passed


def test_paired_dz_zero_variance_and_insufficient_pairs():
    assert paired_dz((0, 0)) == 0
    for values in ((1,), (1, 1)):
        with pytest.raises(GateFailure):
            paired_dz(values)


def test_exact_dz_boundary():
    from agent_ex.calibration.gates import _dz_passes

    assert paired_dz((1,) * 15 + (-1,) * 10) == pytest.approx(0.20)
    assert _dz_passes((1,) * 15 + (-1,) * 10, Fraction(1, 5))
    assert not _dz_passes((1,) * 16 + (-1,) * 9, Fraction(1, 5))


def test_total_variation_uses_full_scale_exactly():
    assert total_variation((1, 1, 7), (1, 7, 7), tuple(range(1, 8))) == Fraction(1, 3)
    with pytest.raises(GateFailure):
        total_variation((), (1,), tuple(range(1, 8)))
    with pytest.raises(ValueError):
        total_variation((8,), (1,), tuple(range(1, 8)))


def test_one_format_repair_retains_first_parse_provenance():
    args = fixture([2, 3, 4, 5], repaired=(0,))
    folded = fold_case_attempts(args[1], args[2])
    case = folded[args[1][0].probe_case_id]
    assert case.first_parse.success is False
    assert case.final_parse.success is True
    assert len(case.attempt_hashes) == 2
    metric = family_metric(args)
    assert metric["first_parse"]["numerator"] == 3
    assert metric["parse"]["numerator"] == 4


@pytest.mark.parametrize("change", ["missing", "indeterminate", "hash", "incomplete"])
def test_review_missing_or_unbound_suppresses_pass(change):
    spec, cases, run, alg, reviews = complete_fixture()
    if change == "missing":
        reviews = reviews[:-1]
    elif change == "indeterminate":
        reviews = (replace(reviews[0], contradiction="indeterminate"),) + reviews[1:]
    elif change == "hash":
        reviews = (replace(reviews[0], parse_hash="f" * 64),) + reviews[1:]
    else:
        reviews = (
            replace(
                reviews[0],
                review_complete=False,
                dimension_labels={},
                dimension_passes={},
                semantic_passed=False,
            ),
        ) + reviews[1:]
    report = evaluate_quality_gates(
        spec, cases, run, alg, reviews, candidate_key="retirement-delay"
    )
    assert report.status == "review_incomplete"
    assert report.passed is None


def test_complete_inventory_can_pass_with_all_required_challenges():
    report = evaluate_quality_gates(*complete_fixture(), candidate_key="retirement-delay")
    assert report.status == "complete" and report.passed is True
    assert len(report.challenges) == 8
    assert all(c["passed"] for c in report.challenges)
    assert all(c["tv"] == {"numerator": 0, "denominator": 1} for c in report.challenges)


@pytest.mark.parametrize(
    "failed,primary,robustness",
    [
        ((), "retirement-delay", "gm-soybean-oil"),
        ((0,), "gm-soybean-oil", "ai-net-employment"),
        ((0, 1, 2), None, None),
    ],
)
def test_fixed_selection_order(failed, primary, robustness):
    spec, cases, run, alg, reviews = complete_fixture()
    keys = ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
    # Contradictions fail registered semantic quality gates, never outcome effects.
    ids = {
        c.probe_case_id for c in cases if any(c.scenario_id == "topic-" + keys[i] for i in failed)
    }
    reviews = tuple(
        replace(r, contradiction="contradiction") if r.case_id in ids else r for r in reviews
    )
    reports = tuple(
        evaluate_quality_gates(spec, cases, run, alg, reviews, candidate_key=k) for k in keys
    )
    selected = select_topic(tuple(reversed(reports)))
    assert (selected.primary, selected.robustness) == (primary, robustness)
    assert selected.status == ("no_candidate" if primary is None else "proposal_only")


def test_selection_rejects_nested_forbidden_metrics():
    args = complete_fixture()
    keys = ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
    reports = tuple(evaluate_quality_gates(*args, candidate_key=k) for k in keys)
    tampered = replace(reports[0], metrics=({"nested": {"p_value": 0.1}},))
    with pytest.raises(ValueError, match="differs"):
        select_topic((tampered,) + reports[1:])
    with pytest.raises(TypeError):
        select_topic(({"nested": {"p_value": 0.1}},))


def test_selection_rejects_incomplete_review():
    spec, cases, run, alg, reviews = complete_fixture()
    reports = tuple(
        evaluate_quality_gates(spec, cases, run, alg, reviews[:-1], candidate_key=k)
        for k in ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
    )
    with pytest.raises(ValueError, match="incomplete"):
        select_topic(reports)


def required_challenges():
    return tuple(
        PairChallenge(f"{scale}-wording-{a}-{b}", "topic_quality", scale, "variant_index", a, b)
        for scale in ("stance-1-7", "stance-0-10")
        for a, b in combinations(range(3), 2)
    ) + tuple(
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


@lru_cache(maxsize=8)
def complete_fixture(challenges=None, replicates=4):
    alg = algorithm(required_challenges() if challenges is None else challenges)
    payload = probe_spec_payload()
    payload["policy_hashes"]["gate_algorithm"] = alg.record_hash
    payload["replicates"] = [
        {"replicate_id": i, "requested_seed": 100 + i} for i in range(replicates)
    ]
    spec = load_probe_specification(payload)
    cases = expand_probe_cases(spec)
    steps = {}
    for c in cases:
        values = {
            "stance": 2 + c.replicate_id % 4,
            "confidence": 3,
            "public_reason": "Synthetic reason.",
        }
        order = (
            ("stance", "confidence", "public_reason")
            if c.field_order_id == "stance-confidence-reason"
            else ("public_reason", "confidence", "stance")
        )
        import json

        steps[c.probe_case_id, 1] = ProbeScriptStep(
            "response", json.dumps({k: values[k] for k in order}), None, None
        )
    run = execute_probe_run(
        run_instance_id="complete-gates",
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
    case_map = {c.probe_case_id: c for c in cases}
    reviews = tuple(
        SemanticGateEvidence(
            case_id=a.probe_case_id,
            case_hash=case_map[a.probe_case_id].record_hash,
            parse_hash=a.parse_evidence_hash,
            classifier_id=alg.classifier_id,
            classifier_version=alg.classifier_version,
            classifier_hash=alg.classifier_hash,
            review_policy_hash=spec.payload["policy_hashes"]["semantic_review_policy"],
            dimension_labels={
                "refusal": "answered",
                "single_construct": "yes",
                "stance_consistency": "consistent",
            },
            dimension_passes={
                "refusal": True,
                "single_construct": True,
                "stance_consistency": True,
            },
            semantic_passed=True,
            refusal=False,
            contradiction="consistent",
            review_complete=True,
            review_evidence_hash=canonical_payload_hash([a.probe_case_id, "review"]),
        )
        for a in run.attempts
    )
    return spec, cases, run, alg, reviews


def test_any_adverse_semantic_dimension_fails_candidate_gate() -> None:
    spec, cases, run, alg, reviews = complete_fixture()
    retirement_id = next(
        case.candidate_id for case in cases if case.scenario_id == "topic-retirement-delay"
    )
    case_by_id = {case.probe_case_id: case for case in cases}
    target_index = next(
        index
        for index, review in enumerate(reviews)
        if case_by_id[review.case_id].candidate_id == retirement_id
    )
    target = reviews[target_index]
    adverse = replace(
        target,
        dimension_labels={**dict(target.dimension_labels), "single_construct": "no"},
        dimension_passes={**dict(target.dimension_passes), "single_construct": False},
        semantic_passed=False,
    )
    changed_reviews = list(reviews)
    changed_reviews[target_index] = adverse
    report = evaluate_quality_gates(
        spec,
        cases,
        run,
        alg,
        tuple(changed_reviews),
        candidate_key="retirement-delay",
    )
    assert report.status == "complete"
    assert report.passed is False
    semantic = [
        item
        for metric in report.metrics
        for item in metric["semantic_dimensions"]
        if item["dimension"] == "single_construct"
    ]
    assert any(item["passed"] is False for item in semantic)
    assert any(target.case_id in item["failed_case_ids"] for item in semantic)


@pytest.mark.parametrize("omission", ["family", "scale", "both-sides"])
def test_public_scoring_rejects_incomplete_authoritative_inventory(omission):
    spec, cases, run, alg, reviews = complete_fixture()
    if omission == "family":
        supplied = tuple(c for c in cases if c.case_family != "identity")
    elif omission == "scale":
        supplied = tuple(c for c in cases if c.scale_id != "stance-0-10")
    else:
        supplied = tuple(c for c in cases if c.replicate_id != 0)
    # A newly complete run over the subset cannot redefine the scheduled inventory.
    from agent_ex.calibration.contracts import ProbeRunProjection

    subset_run = ProbeRunProjection.create(
        run_instance_id="subset",
        specification_hash=spec.output_hash,
        case_inventory_hash=canonical_payload_hash([c.to_payload() for c in supplied]),
        runtime_policy=policy(),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        case_ids=tuple(c.probe_case_id for c in supplied),
        attempts=(),
    )
    with pytest.raises(ValueError, match="authoritative inventory"):
        evaluate_quality_gates(
            spec, supplied, subset_run, alg, (), candidate_key="retirement-delay"
        )


@pytest.mark.parametrize(
    "challenges",
    [
        (),
        required_challenges()[:6],
        required_challenges()[6:],
        (PairChallenge("wrong-level", "topic_quality", "stance-1-7", "variant_index", 0, 7),)
        + required_challenges()[1:],
    ],
)
def test_public_scoring_rejects_incomplete_required_challenges(challenges):
    with pytest.raises(ValueError, match="required challenge"):
        evaluate_quality_gates(*complete_fixture(challenges), candidate_key="retirement-delay")


def test_12_self_consistent_cases_cannot_replace_2448_registered_cases(monkeypatch):
    args = fixture(
        [2, 3, 4, 5] * 3,
        keys=["retirement-delay"] * 4 + ["gm-soybean-oil"] * 4 + ["ai-net-employment"] * 4,
        alg=algorithm(required_challenges()),
    )
    assert len(args[1]) == 12 and args[2].status == "complete"
    assert len(expand_probe_cases(args[0])) == 2448

    def never_score(*args, **kwargs):
        raise AssertionError("inventory must fail before any favorable metrics")

    monkeypatch.setattr("agent_ex.calibration.gates._score_family", never_score)
    with pytest.raises(ValueError, match="authoritative inventory"):
        evaluate_quality_gates(*args, candidate_key="retirement-delay")


def test_three_favorable_same_source_partial_reports_cannot_select():
    complete = complete_fixture()
    keys = ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
    good = tuple(evaluate_quality_gates(*complete, candidate_key=k) for k in keys)
    partial = fixture(
        [2, 3, 4, 5] * 3,
        keys=[k for k in keys for _ in range(4)],
        alg=algorithm(required_challenges()),
    )
    forged = tuple(replace(r, source=partial) for r in good)
    with pytest.raises(ValueError, match="authoritative inventory"):
        select_topic(forged)


@pytest.mark.parametrize(
    "mutation", ["extra", "duplicate", "replaced", "hash-drift", "content-drift"]
)
def test_authoritative_inventory_rejects_add_duplicate_replace_and_hash_drift(mutation):
    spec, cases, run, alg, reviews = complete_fixture()
    if mutation == "extra":
        supplied = cases + (cases[0],)
    elif mutation == "duplicate":
        supplied = (cases[1],) + cases[1:]
    else:
        c = cases[0]
        if mutation in {"hash-drift", "content-drift"}:
            from copy import copy

            changed = copy(c)
            object.__setattr__(
                changed,
                "record_hash" if mutation == "hash-drift" else "variant_index",
                "f" * 64 if mutation == "hash-drift" else 999,
            )
        else:
            payload = c.to_payload()
            payload["replicate_id"] = 999
            changed = ProbeCase.from_payload(
                rehash_payload(payload, id_field="probe_case_id", prefix="probe-case-")
            )
        supplied = (changed,) + cases[1:]
    with pytest.raises(ValueError, match="authoritative inventory"):
        evaluate_quality_gates(spec, supplied, run, alg, reviews, candidate_key="retirement-delay")


@pytest.mark.parametrize("mutation", ["duplicate", "wrong-family", "wrong-scale", "reverse"])
def test_required_challenges_reject_wrong_scope_and_duplicate_comparison(mutation):
    challenges = required_challenges()
    if mutation == "duplicate":
        challenges = challenges + (replace(challenges[0], challenge_id="duplicate-comparison"),)
    elif mutation == "wrong-family":
        challenges = (replace(challenges[0], case_family="identity"),) + challenges[1:]
    elif mutation == "wrong-scale":
        challenges = (replace(challenges[0], scale_id="stance-0-10"),) + challenges[1:]
    else:
        challenges = (replace(challenges[0], left=1, right=0),) + challenges[1:]
    with pytest.raises(ValueError, match="required challenge"):
        evaluate_quality_gates(*complete_fixture(challenges), candidate_key="retirement-delay")


def test_complete_inventory_with_no_runtime_attempts_suppresses_pass():
    from agent_ex.calibration.contracts import ProbeRunProjection

    spec, cases, run, alg, _ = complete_fixture()
    empty = ProbeRunProjection.create(
        run_instance_id="empty",
        specification_hash=spec.output_hash,
        case_inventory_hash=run.case_inventory_hash,
        runtime_policy=policy(),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        case_ids=tuple(c.probe_case_id for c in cases),
        attempts=(),
    )
    report = evaluate_quality_gates(spec, cases, empty, alg, (), candidate_key="retirement-delay")
    assert report.status == "runtime_incomplete" and report.passed is None


def test_provider_unsupported_seed_is_reported_without_fake_guarantee(monkeypatch):
    original = ScriptedProbeAdapter.generate

    def unsupported(self, request, *, timeout_seconds=None):
        payload = original(self, request, timeout_seconds=timeout_seconds).to_payload()
        payload["provider_seed_supported"] = False
        payload["provider_seed_echo"] = None
        return ProbeResponse.from_payload(
            rehash_payload(payload, id_field="response_id", prefix="probe-response-")
        )

    monkeypatch.setattr(ScriptedProbeAdapter, "generate", unsupported)
    report = evaluate_quality_gates(
        *complete_fixture.__wrapped__(), candidate_key="retirement-delay"
    )
    assert report.passed is True
    assert all(c["provider_seed_guaranteed"] is False for c in report.challenges)


def test_projection_inventory_hash_cannot_substitute_for_authoritative_cases():
    from copy import copy

    spec, cases, run, alg, reviews = complete_fixture()
    changed = copy(run)
    object.__setattr__(changed, "case_inventory_hash", "f" * 64)
    with pytest.raises(ValueError):
        evaluate_quality_gates(spec, cases, changed, alg, reviews, candidate_key="retirement-delay")


def test_algorithm_hash_must_bind_coverage_policy_before_run():
    spec, cases, run, alg, reviews = complete_fixture()
    with pytest.raises(ValueError, match="algorithm"):
        evaluate_quality_gates(
            spec,
            cases,
            run,
            replace(alg, max_refusal=Fraction(1, 2)),
            reviews,
            candidate_key="retirement-delay",
        )
