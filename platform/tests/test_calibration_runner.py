from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
import math

import pytest

from agent_ex.calibration.adapters import ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.contracts import (
    ProbeAttempt,
    ProbeRunProjection,
    ProbeRuntimePolicy,
)
from agent_ex.calibration.runner import ProbeRunCrash, execute_probe_run, resume_probe_run
from agent_ex.calibration.specification import expand_probe_cases, load_probe_specification
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload


GENERATION_SETTINGS = {"temperature": 0.2, "top_p": 0.9, "max_tokens": 128}
RUNTIME_IDENTITY = {"provider": "scripted-probe", "runtime_version": "1.0.0"}
MODEL_IDENTITY = {"model": "synthetic", "revision": "offline-v1"}
TOKENIZER_IDENTITY = {"tokenizer": "synthetic", "revision": "offline-v1"}
CHAT_TEMPLATE_HASH = canonical_payload_hash("synthetic-chat-template-v1")


def specification_and_cases(count: int = 1):
    specification = load_probe_specification(probe_spec_payload())
    return specification, expand_probe_cases(specification)[:count]


def policy(*, timeout_budget: int = 2) -> ProbeRuntimePolicy:
    return ProbeRuntimePolicy.create(
        policy_id="phase0a-offline-runtime-v1",
        retryable_error_codes=("timeout", "provider_busy"),
        nonretryable_error_codes=("oom", "provider_fatal"),
        max_transport_attempts_by_code={
            "timeout": timeout_budget,
            "provider_busy": 2,
            "oom": 1,
            "provider_fatal": 1,
        },
        timeout_seconds=30.0,
        obey_retry_after=True,
        backoff_seconds=tuple(0.25 for _ in range(max(1, timeout_budget - 1))),
    )


def valid_raw(stance: int = 4) -> str:
    return json.dumps(
        {"stance": stance, "confidence": 3, "public_reason": "Synthetic reason."},
        separators=(",", ":"),
    )


def run(adapter, *, runtime_policy=None, count: int = 1):
    specification, cases = specification_and_cases(count)
    return execute_probe_run(
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy or policy(),
        adapter=adapter,
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )


def steps_for_first(*steps: ProbeScriptStep):
    _, cases = specification_and_cases()
    case_id = cases[0].probe_case_id
    return {(case_id, index): step for index, step in enumerate(steps, 1)}


def test_runtime_policy_is_strict_hash_bound_and_round_trips() -> None:
    record = policy()
    restored = ProbeRuntimePolicy.from_payload(json.loads(json.dumps(record.to_payload())))
    assert restored == record
    assert record.record_hash == canonical_payload_hash(record.content_payload())
    with pytest.raises(FrozenInstanceError):
        record.timeout_seconds = 10.0
    with pytest.raises((TypeError, ValueError)):
        replace(
            record,
            max_transport_attempts_by_code={
                **record.max_transport_attempts_by_code,
                "timeout": True,
            },
        )
    with pytest.raises(ValueError, match="partition|codes"):
        ProbeRuntimePolicy.create(
            policy_id="bad",
            retryable_error_codes=("same",),
            nonretryable_error_codes=("same",),
            max_transport_attempts_by_code={"same": 1},
            timeout_seconds=1.0,
            obey_retry_after=False,
            backoff_seconds=(0.0,),
        )
    for bad in ((math.nan,), (math.inf,), (-1.0,), (True,), (), [0.1]):
        with pytest.raises((TypeError, ValueError)):
            replace(record, backoff_seconds=bad)
    for bad in (math.nan, math.inf, -1.0, True):
        with pytest.raises((TypeError, ValueError)):
            replace(record, timeout_seconds=bad)
    with pytest.raises(ValueError, match="length|schedule"):
        ProbeRuntimePolicy.create(
            policy_id="wrong-schedule",
            retryable_error_codes=("timeout",),
            nonretryable_error_codes=("oom",),
            max_transport_attempts_by_code={"timeout": 3, "oom": 1},
            timeout_seconds=1.0,
            obey_retry_after=False,
            backoff_seconds=(0.1,),
        )


def test_invalid_format_gets_exactly_one_repair_without_spending_transport_budget() -> None:
    adapter = ScriptedProbeAdapter(
        steps_for_first(
            ProbeScriptStep("response", "not-json", None, None),
            ProbeScriptStep("response", valid_raw(), None, None),
        )
    )
    projection = run(adapter)
    assert [attempt.attempt_kind for attempt in projection.attempts] == [
        "semantic",
        "format_repair",
    ]
    assert [attempt.transport_attempt_number_for_code for attempt in projection.attempts] == [
        None,
        None,
    ]
    assert projection.case_statuses == {projection.attempts[0].probe_case_id: "parsed"}
    assert projection.status == "complete"
    assert (
        projection.attempts[1].request.rendered_messages[:-1]
        == projection.attempts[0].request.rendered_messages
    )


def test_second_invalid_format_is_terminal_and_no_third_call_occurs() -> None:
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(
                ProbeScriptStep("response", "not-json", None, None),
                ProbeScriptStep("response", "still-not-json", None, None),
            )
        )
    )
    assert len(projection.attempts) == 2
    assert next(iter(projection.case_statuses.values())) == "parse_failed"
    assert projection.status == "complete"


def test_refusal_is_terminal_and_never_triggers_format_repair() -> None:
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(ProbeScriptStep("response", '{"refusal":true}', None, None))
        )
    )
    assert len(projection.attempts) == 1
    assert projection.attempts[0].parse_evidence is not None
    assert projection.attempts[0].parse_evidence.error["code"] == "refusal"
    assert next(iter(projection.case_statuses.values())) == "refused"


def test_retryable_transport_error_records_backoff_then_succeeds() -> None:
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(
                ProbeScriptStep("timeout", None, "timeout", None),
                ProbeScriptStep("response", valid_raw(), None, None),
            )
        )
    )
    first = projection.attempts[0]
    assert first.transport_attempt_number_for_code == 1
    assert first.retry_delay_seconds == 0.25
    assert first.retry_delay_source == "backoff"
    assert next(iter(projection.case_statuses.values())) == "parsed"


def test_retry_after_is_recorded_without_sleeping() -> None:
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(
                ProbeScriptStep("provider_error", None, "provider_busy", 1.5),
                ProbeScriptStep("response", valid_raw(), None, None),
            )
        )
    )
    assert projection.attempts[0].retry_delay_seconds == 1.5
    assert projection.attempts[0].retry_delay_source == "retry_after"


def test_attempt_replay_rejects_delay_not_bound_to_retry_after_response() -> None:
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(
                ProbeScriptStep("provider_error", None, "provider_busy", 1.5),
                ProbeScriptStep("response", valid_raw(), None, None),
            )
        )
    )
    attempt = projection.attempts[0]
    values = {
        name: getattr(attempt, name)
        for name in attempt.__dataclass_fields__
        if name not in {"attempt_id", "record_hash"}
    }
    values["retry_delay_seconds"] = 1.0
    with pytest.raises(ValueError, match="Retry-After|response evidence"):
        ProbeAttempt.create(**values)


def test_backoff_schedule_is_indexed_by_consumed_attempt_for_that_error() -> None:
    runtime_policy = ProbeRuntimePolicy.create(
        policy_id="three-timeout-attempts",
        retryable_error_codes=("timeout",),
        nonretryable_error_codes=("oom",),
        max_transport_attempts_by_code={"timeout": 3, "oom": 1},
        timeout_seconds=5.0,
        obey_retry_after=False,
        backoff_seconds=(0.1, 0.2),
    )
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(
                ProbeScriptStep("timeout", None, "timeout", None),
                ProbeScriptStep("timeout", None, "timeout", None),
                ProbeScriptStep("response", valid_raw(), None, None),
            )
        ),
        runtime_policy=runtime_policy,
    )
    assert [item.retry_delay_seconds for item in projection.attempts] == [0.1, 0.2, None]


@pytest.mark.parametrize("outcome,error", [("oom", "oom"), ("provider_error", "provider_fatal")])
def test_nonretryable_and_oom_fail_immediately(outcome: str, error: str) -> None:
    projection = run(
        ScriptedProbeAdapter(steps_for_first(ProbeScriptStep(outcome, None, error, None)))
    )
    assert len(projection.attempts) == 1
    assert next(iter(projection.case_statuses.values())) == "runtime_failed"
    assert projection.status == "incomplete"


def test_nonretryable_error_ignores_a_larger_bound_budget() -> None:
    runtime_policy = ProbeRuntimePolicy.create(
        policy_id="nonretryable-large-budget",
        retryable_error_codes=("timeout",),
        nonretryable_error_codes=("provider_fatal",),
        max_transport_attempts_by_code={"timeout": 2, "provider_fatal": 3},
        timeout_seconds=5.0,
        obey_retry_after=False,
        backoff_seconds=(0.0,),
    )
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(ProbeScriptStep("provider_error", None, "provider_fatal", None))
        ),
        runtime_policy=runtime_policy,
    )
    assert projection.attempts[0].transport_retryable is False
    assert next(iter(projection.case_statuses.values())) == "runtime_failed"


def test_oom_code_must_be_declared_nonretryable() -> None:
    bad_policy = ProbeRuntimePolicy.create(
        policy_id="bad-oom-policy",
        retryable_error_codes=("oom",),
        nonretryable_error_codes=("provider_fatal",),
        max_transport_attempts_by_code={"oom": 2, "provider_fatal": 1},
        timeout_seconds=5.0,
        obey_retry_after=False,
        backoff_seconds=(0.0,),
    )
    with pytest.raises(ValueError, match="OOM|oom|nonretryable"):
        run(
            ScriptedProbeAdapter(steps_for_first(ProbeScriptStep("oom", None, "oom", None))),
            runtime_policy=bad_policy,
        )


def test_adapter_crash_exposes_hash_bound_projection_snapshot() -> None:
    class CrashingAdapter(ScriptedProbeAdapter):
        def generate(self, request):
            raise RuntimeError("synthetic crash")

    with pytest.raises(ProbeRunCrash) as raised:
        run(CrashingAdapter({}))
    snapshot = raised.value.snapshot
    assert snapshot.status == "incomplete"
    assert snapshot.attempts == ()
    assert set(snapshot.case_statuses.values()) == {"unstarted"}
    assert snapshot.run_evidence_hash == canonical_payload_hash([])


def test_exhausted_runtime_failure_is_irreversible_on_resume() -> None:
    specification, cases = specification_and_cases()
    runtime_policy = policy(timeout_budget=1)
    projection = run(
        ScriptedProbeAdapter(steps_for_first(ProbeScriptStep("timeout", None, "timeout", None))),
        runtime_policy=runtime_policy,
    )
    with pytest.raises(ValueError, match="runtime_failed|irreversible"):
        resume_probe_run(
            projection=projection,
            specification_hash=specification.output_hash,
            cases=cases,
            runtime_policy=runtime_policy,
            adapter=ScriptedProbeAdapter(
                steps_for_first(ProbeScriptStep("response", valid_raw(), None, None))
            ),
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
        )


def test_resume_skips_runtime_failed_case_and_runs_unstarted_case() -> None:
    specification, cases = specification_and_cases(2)
    failed, unstarted = cases
    runtime_policy = ProbeRuntimePolicy.create(
        policy_id="single-timeout-attempt",
        retryable_error_codes=("timeout",),
        nonretryable_error_codes=("oom",),
        max_transport_attempts_by_code={"timeout": 1, "oom": 1},
        timeout_seconds=5.0,
        obey_retry_after=False,
        backoff_seconds=(0.0,),
    )
    partial = execute_probe_run(
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter(
            {(failed.probe_case_id, 1): ProbeScriptStep("timeout", None, "timeout", None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        stop_after_attempts=1,
    )
    resumed = resume_probe_run(
        projection=partial,
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter(
            {(unstarted.probe_case_id, 1): ProbeScriptStep("response", valid_raw(), None, None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    assert resumed.case_statuses[failed.probe_case_id] == "runtime_failed"
    assert resumed.case_statuses[unstarted.probe_case_id] == "parsed"
    assert resumed.status == "incomplete"


def test_resume_preserves_consumed_budget_and_continues_budget_remaining_case() -> None:
    specification, cases = specification_and_cases()
    runtime_policy = policy(timeout_budget=2)
    case = cases[0]
    partial = execute_probe_run(
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter(
            {(case.probe_case_id, 1): ProbeScriptStep("timeout", None, "timeout", None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        stop_after_attempts=1,
    )
    resumed = resume_probe_run(
        projection=partial,
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter(
            {(case.probe_case_id, 2): ProbeScriptStep("response", valid_raw(), None, None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    assert [item.attempt_index for item in resumed.attempts] == [1, 2]
    assert resumed.attempts[0].transport_attempt_number_for_code == 1
    assert next(iter(resumed.case_statuses.values())) == "parsed"


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("specification_hash", canonical_payload_hash("other-spec")),
        ("runtime_policy", policy(timeout_budget=3)),
        ("runtime_identity", {"provider": "other", "runtime_version": "1.0.0"}),
        ("model_identity", {"model": "other", "revision": "offline-v1"}),
        ("tokenizer_identity", {"tokenizer": "other", "revision": "offline-v1"}),
        ("chat_template_hash", canonical_payload_hash("other-template")),
        ("generation_settings", {"temperature": 0.3, "top_p": 0.9, "max_tokens": 128}),
    ],
)
def test_resume_rejects_all_bound_drift_before_adapter_call(
    field: str, replacement: object
) -> None:
    specification, cases = specification_and_cases()
    case = cases[0]
    runtime_policy = policy()
    partial = execute_probe_run(
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter(
            {(case.probe_case_id, 1): ProbeScriptStep("timeout", None, "timeout", None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        stop_after_attempts=1,
    )
    arguments = {
        "projection": partial,
        "specification_hash": specification.output_hash,
        "cases": cases,
        "runtime_policy": runtime_policy,
        "adapter": ScriptedProbeAdapter(
            {(case.probe_case_id, 2): ProbeScriptStep("response", valid_raw(), None, None)}
        ),
        "generation_settings": GENERATION_SETTINGS,
        "runtime_identity": RUNTIME_IDENTITY,
        "model_identity": MODEL_IDENTITY,
        "tokenizer_identity": TOKENIZER_IDENTITY,
        "chat_template_hash": CHAT_TEMPLATE_HASH,
    }
    arguments[field] = replacement
    with pytest.raises(ValueError, match="drift|hash|identity|run"):
        resume_probe_run(**arguments)


def test_resume_rejects_case_inventory_drift_and_cross_run_evidence() -> None:
    specification, cases = specification_and_cases(2)
    first = cases[0]
    partial = execute_probe_run(
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=policy(),
        adapter=ScriptedProbeAdapter(
            {(first.probe_case_id, 1): ProbeScriptStep("timeout", None, "timeout", None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        stop_after_attempts=1,
    )
    with pytest.raises(ValueError, match="inventory|run"):
        resume_probe_run(
            projection=partial,
            specification_hash=specification.output_hash,
            cases=cases[:1],
            runtime_policy=policy(),
            adapter=ScriptedProbeAdapter({}),
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
        )
    with pytest.raises(ValueError, match="derived|attempt|status|identity"):
        replace(partial, probe_run_id="other-run")


def test_projection_round_trip_canonicalizes_cases_and_attempts() -> None:
    specification, cases = specification_and_cases(2)
    steps = {}
    for case in reversed(cases):
        steps[(case.probe_case_id, 1)] = ProbeScriptStep("response", valid_raw(), None, None)
    projection = execute_probe_run(
        specification_hash=specification.output_hash,
        cases=tuple(reversed(cases)),
        runtime_policy=policy(),
        adapter=ScriptedProbeAdapter(steps),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    restored = ProbeRunProjection.from_payload(json.loads(json.dumps(projection.to_payload())))
    assert restored == projection
    assert list(projection.case_statuses) == sorted(projection.case_statuses)
    assert [(a.probe_case_id, a.attempt_index) for a in projection.attempts] == sorted(
        (a.probe_case_id, a.attempt_index) for a in projection.attempts
    )
    with pytest.raises(ValueError, match="derived|attempt|status"):
        replace(
            projection, case_statuses={key: "runtime_failed" for key in projection.case_statuses}
        )


def test_attempt_contract_rejects_hash_tampering() -> None:
    projection = run(
        ScriptedProbeAdapter(steps_for_first(ProbeScriptStep("response", valid_raw(), None, None)))
    )
    attempt = projection.attempts[0]
    restored = ProbeAttempt.from_payload(json.loads(json.dumps(attempt.to_payload())))
    assert restored == attempt
    with pytest.raises(ValueError, match="hash"):
        replace(attempt, response_hash=canonical_payload_hash("tampered"))
