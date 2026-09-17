from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import inspect
import json
import math

import pytest

import agent_ex.calibration.runner as runner_module
from agent_ex.calibration.adapters import ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.contracts import (
    CloudProbeRuntimePolicy,
    ProbeAttempt,
    ProbeRequest,
    ProbeResponse,
    ProbeRunProjection,
    ProbeRuntimePolicy,
)
from agent_ex.calibration.parser import parse_probe_response
from agent_ex.calibration.runner import ProbeRunCrash, execute_probe_run, resume_probe_run
from agent_ex.calibration.specification import expand_probe_cases, load_probe_specification
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload


GENERATION_SETTINGS = {"temperature": 0.2, "top_p": 0.9, "max_tokens": 128}
RUNTIME_IDENTITY = {"provider": "scripted-probe", "runtime_version": "1.0.0"}
MODEL_IDENTITY = {"model": "synthetic", "revision": "offline-v1"}
TOKENIZER_IDENTITY = {"tokenizer": "synthetic", "revision": "offline-v1"}
CHAT_TEMPLATE_HASH = canonical_payload_hash("synthetic-chat-template-v1")
RUN_INSTANCE_ID = "phase0a-test-run-001"


class CountingAdapter(ScriptedProbeAdapter):
    def __init__(self, steps):
        super().__init__(steps)
        self.calls = 0

    def generate(self, request, *, timeout_seconds=None):
        self.calls += 1
        return super().generate(request, timeout_seconds=timeout_seconds)


class TimeoutCapturingAdapter(ScriptedProbeAdapter):
    def __init__(self, steps):
        super().__init__(steps)
        self.timeouts = []

    def generate(self, request, *, timeout_seconds=None):
        self.timeouts.append(timeout_seconds)
        return super().generate(request, timeout_seconds=timeout_seconds)


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


def cloud_policy() -> CloudProbeRuntimePolicy:
    transport = policy()
    return CloudProbeRuntimePolicy.create(
        policy_id="phase0a-cloud-runner-test-v2",
        retryable_error_codes=(*transport.retryable_error_codes, "provider_unreachable"),
        nonretryable_error_codes=(
            *transport.nonretryable_error_codes,
            "provider_identity_mismatch",
            "provider_missing_request_id",
        ),
        max_transport_attempts_by_code={
            **transport.max_transport_attempts_by_code,
            "provider_identity_mismatch": 1,
            "provider_missing_request_id": 1,
            "provider_unreachable": 2,
        },
        timeout_seconds=transport.timeout_seconds,
        obey_retry_after=True,
        backoff_seconds=transport.backoff_seconds,
        connect_timeout_seconds=10.0,
        read_timeout_seconds=30.0,
        retry_after_min_seconds=0.0,
        retry_after_max_seconds=2.0,
        invalid_retry_after_action="use_deterministic_backoff",
        oom_action="terminal_incomplete",
        server_crash_action="retry_then_terminal_incomplete",
        model_identity_drift_action="terminal_incomplete",
        disk_below_threshold_action="terminal_incomplete",
        max_total_cases=816,
        max_total_transport_attempts=1632,
        dispatch_stop_cumulative_attempt_seconds=172800.0,
        dispatch_stop_input_tokens=2_000_000,
        dispatch_stop_output_tokens=250_000,
        minimum_free_disk_bytes=1,
    )


def valid_raw(stance: int = 4) -> str:
    return json.dumps(
        {"stance": stance, "confidence": 3, "public_reason": "Synthetic reason."},
        separators=(",", ":"),
    )


def rehash_payload(payload: dict[str, object], *, id_field: str, prefix: str) -> dict[str, object]:
    identity = {
        key: value for key, value in payload.items() if key not in {id_field, "record_hash"}
    }
    payload[id_field] = prefix + canonical_payload_hash(identity)
    payload["record_hash"] = canonical_payload_hash({**identity, id_field: payload[id_field]})
    return payload


def run(adapter, *, runtime_policy=None, count: int = 1):
    specification, cases = specification_and_cases(count)
    return execute_probe_run(
        run_instance_id=RUN_INSTANCE_ID,
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


def test_cloud_runtime_policy_and_projection_round_trip_with_whole_run_budgets() -> None:
    runtime = cloud_policy()
    assert runtime.max_transport_attempts_by_code["provider_unreachable"] == 2
    assert "provider_identity_mismatch" in runtime.nonretryable_error_codes
    assert "provider_missing_request_id" in runtime.nonretryable_error_codes
    restored_runtime = CloudProbeRuntimePolicy.from_payload(
        json.loads(json.dumps(runtime.to_payload()))
    )
    assert restored_runtime == runtime

    projection = run(
        ScriptedProbeAdapter(steps_for_first(ProbeScriptStep("response", valid_raw(), None, None))),
        runtime_policy=runtime,
    )
    restored_projection = ProbeRunProjection.from_payload(
        json.loads(json.dumps(projection.to_payload()))
    )
    assert restored_projection == projection


def test_backoff_schedule_may_be_empty_only_when_no_retry_transition_exists() -> None:
    record = policy()
    no_retry = ProbeRuntimePolicy.create(
        policy_id="one-attempt-only",
        retryable_error_codes=("timeout",),
        nonretryable_error_codes=("oom",),
        max_transport_attempts_by_code={"timeout": 1, "oom": 1},
        timeout_seconds=1.0,
        obey_retry_after=False,
        backoff_seconds=(),
    )
    assert no_retry.backoff_seconds == ()
    with pytest.raises(ValueError, match="length|schedule|retry"):
        ProbeRuntimePolicy.create(
            policy_id="missing-transition",
            retryable_error_codes=("timeout",),
            nonretryable_error_codes=("oom",),
            max_transport_attempts_by_code={"timeout": 2, "oom": 1},
            timeout_seconds=1.0,
            obey_retry_after=False,
            backoff_seconds=(),
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


def test_runtime_timeout_is_applied_at_the_adapter_boundary() -> None:
    adapter = TimeoutCapturingAdapter(
        steps_for_first(ProbeScriptStep("response", valid_raw(), None, None))
    )
    run(adapter)
    assert adapter.timeouts == [30.0]


def test_retry_after_is_executed_and_recorded(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr(runner_module.time, "sleep", sleeps.append)
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
    assert sleeps == [1.5]


def test_cloud_policy_replaces_out_of_range_retry_after_with_bound_backoff(
    monkeypatch,
) -> None:
    sleeps = []
    monkeypatch.setattr(runner_module.time, "sleep", sleeps.append)
    projection = run(
        ScriptedProbeAdapter(
            steps_for_first(
                ProbeScriptStep("provider_error", None, "provider_busy", 30.0),
                ProbeScriptStep("response", valid_raw(), None, None),
            )
        ),
        runtime_policy=cloud_policy(),
    )
    assert projection.attempts[0].retry_delay_seconds == 0.25
    assert projection.attempts[0].retry_delay_source == "backoff"
    assert sleeps == [0.25]


def test_backoff_is_executed_before_the_next_adapter_call(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(runner_module.time, "sleep", lambda delay: events.append(("sleep", delay)))

    class OrderedAdapter(ScriptedProbeAdapter):
        def generate(self, request, *, timeout_seconds=None):
            events.append(("call", request.attempt_index))
            return super().generate(request, timeout_seconds=timeout_seconds)

    run(
        OrderedAdapter(
            steps_for_first(
                ProbeScriptStep("timeout", None, "timeout", None),
                ProbeScriptStep("response", valid_raw(), None, None),
            )
        )
    )
    assert events == [("call", 1), ("sleep", 0.25), ("call", 2)]


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
    with pytest.raises(ProbeRunCrash) as raised:
        run(
            ScriptedProbeAdapter(steps_for_first(ProbeScriptStep("oom", None, "oom", None))),
            runtime_policy=bad_policy,
        )
    assert isinstance(raised.value.__cause__, ValueError)
    assert "nonretryable" in str(raised.value.__cause__)


def test_adapter_crash_exposes_hash_bound_projection_snapshot() -> None:
    class CrashingAdapter(ScriptedProbeAdapter):
        def generate(self, request, *, timeout_seconds=None):
            raise RuntimeError("synthetic crash")

    with pytest.raises(ProbeRunCrash) as raised:
        run(CrashingAdapter({}))
    snapshot = raised.value.snapshot
    assert snapshot.status == "incomplete"
    assert snapshot.attempts == ()
    assert set(snapshot.case_statuses.values()) == {"unstarted"}
    assert snapshot.run_evidence_hash == canonical_payload_hash([])


@pytest.mark.parametrize("failure_stage", ["provenance", "parse", "attempt"])
def test_post_adapter_failures_expose_last_valid_snapshot_and_resume(
    monkeypatch, failure_stage: str
) -> None:
    specification, cases = specification_and_cases(2)
    first, second = cases
    steps = {
        (first.probe_case_id, 1): ProbeScriptStep("response", valid_raw(), None, None),
        (second.probe_case_id, 1): ProbeScriptStep("response", valid_raw(), None, None),
    }

    if failure_stage == "provenance":

        class FaultyAdapter(ScriptedProbeAdapter):
            def generate(self, request, *, timeout_seconds=None):
                response = super().generate(request, timeout_seconds=timeout_seconds)
                if request.probe_case_id == second.probe_case_id:
                    payload = response.to_payload()
                    payload["runtime_identity"] = {
                        "provider": "drift",
                        "runtime_version": "1.0.0",
                    }
                    return ProbeResponse.from_payload(
                        rehash_payload(
                            payload,
                            id_field="response_id",
                            prefix="probe-response-",
                        )
                    )
                return response

        adapter = FaultyAdapter(steps)
    else:
        adapter = ScriptedProbeAdapter(steps)
        target = "parse_probe_response" if failure_stage == "parse" else "_make_attempt"
        original = getattr(runner_module, target)
        calls = 0

        def fail_on_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError(f"synthetic {failure_stage} failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(runner_module, target, fail_on_second)

    with pytest.raises(ProbeRunCrash) as raised:
        execute_probe_run(
            run_instance_id=RUN_INSTANCE_ID,
            specification_hash=specification.output_hash,
            cases=cases,
            runtime_policy=policy(),
            adapter=adapter,
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
        )
    assert raised.value.__cause__ is not None
    assert [item.probe_case_id for item in raised.value.snapshot.attempts] == [first.probe_case_id]

    if failure_stage != "provenance":
        monkeypatch.setattr(runner_module, target, original)
    resumed = resume_probe_run(
        projection=raised.value.snapshot,
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=policy(),
        adapter=ScriptedProbeAdapter(
            {(second.probe_case_id, 1): ProbeScriptStep("response", valid_raw(), None, None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    assert resumed.status == "complete"


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
        backoff_seconds=(),
    )
    partial = execute_probe_run(
        run_instance_id=RUN_INSTANCE_ID,
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


@pytest.mark.parametrize(
    "changed",
    [
        {"generation_settings": {"temperature": 0.9, "top_p": 0.9, "max_tokens": 128}},
        {"model_identity": {"model": "other", "revision": "offline-v1"}},
    ],
)
def test_zero_attempt_snapshot_freezes_full_execution_context_before_resume_call(changed) -> None:
    specification, cases = specification_and_cases()
    runtime_policy = policy()
    original = execute_probe_run(
        run_instance_id=RUN_INSTANCE_ID,
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter({}),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        stop_after_attempts=0,
    )
    arguments = {
        "projection": original,
        "specification_hash": specification.output_hash,
        "cases": cases,
        "runtime_policy": runtime_policy,
        "adapter": CountingAdapter({}),
        "generation_settings": GENERATION_SETTINGS,
        "runtime_identity": RUNTIME_IDENTITY,
        "model_identity": MODEL_IDENTITY,
        "tokenizer_identity": TOKENIZER_IDENTITY,
        "chat_template_hash": CHAT_TEMPLATE_HASH,
        **changed,
    }
    changed_projection = execute_probe_run(
        run_instance_id=RUN_INSTANCE_ID,
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter({}),
        generation_settings=arguments["generation_settings"],
        runtime_identity=arguments["runtime_identity"],
        model_identity=arguments["model_identity"],
        tokenizer_identity=arguments["tokenizer_identity"],
        chat_template_hash=arguments["chat_template_hash"],
        stop_after_attempts=0,
    )
    assert changed_projection.probe_run_id != original.probe_run_id
    with pytest.raises(ValueError, match="context|drift|run"):
        resume_probe_run(**arguments)
    assert arguments["adapter"].calls == 0


def test_run_instance_id_is_required_and_distinguishes_otherwise_identical_runs() -> None:
    assert (
        inspect.signature(execute_probe_run).parameters["run_instance_id"].default is inspect._empty
    )
    specification, cases = specification_and_cases()

    def snapshot(instance_id: str):
        return execute_probe_run(
            run_instance_id=instance_id,
            specification_hash=specification.output_hash,
            cases=cases,
            runtime_policy=policy(),
            adapter=ScriptedProbeAdapter({}),
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
            stop_after_attempts=0,
        )

    first = snapshot("run-instance-a")
    repeated = snapshot("run-instance-a")
    second = snapshot("run-instance-b")
    assert first.probe_run_id == repeated.probe_run_id
    assert first.probe_run_id != second.probe_run_id
    assert first.run_instance_id == "run-instance-a"


@pytest.mark.parametrize("bad_id", ["", "   ", None, 1, True])
def test_run_instance_id_rejects_empty_and_non_string_values(bad_id: object) -> None:
    specification, cases = specification_and_cases()
    with pytest.raises((TypeError, ValueError), match="run_instance_id|instance"):
        execute_probe_run(
            run_instance_id=bad_id,
            specification_hash=specification.output_hash,
            cases=cases,
            runtime_policy=policy(),
            adapter=ScriptedProbeAdapter({}),
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
            stop_after_attempts=0,
        )


def test_resume_preserves_consumed_budget_and_continues_budget_remaining_case() -> None:
    specification, cases = specification_and_cases()
    runtime_policy = policy(timeout_budget=2)
    case = cases[0]
    partial = execute_probe_run(
        run_instance_id=RUN_INSTANCE_ID,
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
        run_instance_id=RUN_INSTANCE_ID,
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
        run_instance_id=RUN_INSTANCE_ID,
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
        run_instance_id=RUN_INSTANCE_ID,
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


def test_projection_replay_rejects_forged_transport_ordinal_before_third_call() -> None:
    specification, cases = specification_and_cases()
    case = cases[0]
    runtime_policy = policy(timeout_budget=2)
    first_projection = execute_probe_run(
        run_instance_id=RUN_INSTANCE_ID,
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
    second_request = ProbeRequest.create(
        case,
        attempt_index=2,
        attempt_kind="semantic",
        generation_settings=GENERATION_SETTINGS,
    )
    second_response = ScriptedProbeAdapter(
        {(case.probe_case_id, 2): ProbeScriptStep("timeout", None, "timeout", None)}
    ).generate(second_request)
    forged_second = ProbeAttempt.create(
        probe_run_id=first_projection.probe_run_id,
        run_instance_id=first_projection.run_instance_id,
        specification_hash=specification.output_hash,
        case_inventory_hash=first_projection.case_inventory_hash,
        runtime_policy_hash=runtime_policy.record_hash,
        probe_case_id=case.probe_case_id,
        probe_case_hash=case.record_hash,
        attempt_index=2,
        attempt_kind="semantic",
        request=second_request,
        request_hash=second_request.record_hash,
        response=second_response,
        response_hash=second_response.record_hash,
        parse_evidence=None,
        parse_evidence_hash=None,
        transport_error_code="timeout",
        transport_retryable=True,
        transport_attempt_number_for_code=1,
        transport_budget_for_code=2,
        retry_delay_seconds=0.25,
        retry_delay_source="backoff",
        case_status_after="pending",
    )
    adapter = CountingAdapter(
        {(case.probe_case_id, 3): ProbeScriptStep("response", valid_raw(), None, None)}
    )
    with pytest.raises(ValueError, match="ordinal|budget|replay|status"):
        forged_projection = ProbeRunProjection.create(
            run_instance_id=first_projection.run_instance_id,
            specification_hash=specification.output_hash,
            case_inventory_hash=first_projection.case_inventory_hash,
            runtime_policy=runtime_policy,
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
            case_ids=(case.probe_case_id,),
            attempts=(first_projection.attempts[0], forged_second),
        )
        resume_probe_run(
            projection=forged_projection,
            specification_hash=specification.output_hash,
            cases=cases,
            runtime_policy=runtime_policy,
            adapter=adapter,
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
        )
    assert adapter.calls == 0


def test_attempt_rejects_independently_hash_valid_response_with_changed_scale() -> None:
    projection = run(
        ScriptedProbeAdapter(steps_for_first(ProbeScriptStep("response", valid_raw(), None, None)))
    )
    honest = projection.attempts[0]
    payload = honest.response.to_payload()
    payload["scale_id"] = (
        "stance-0-10" if honest.response.scale_id == "stance-1-7" else "stance-1-7"
    )
    malicious_response = ProbeResponse.from_payload(
        rehash_payload(payload, id_field="response_id", prefix="probe-response-")
    )
    malicious_parse = parse_probe_response(malicious_response)
    values = {
        name: getattr(honest, name)
        for name in honest.__dataclass_fields__
        if name not in {"attempt_id", "record_hash"}
    }
    values.update(
        response=malicious_response,
        response_hash=malicious_response.record_hash,
        parse_evidence=malicious_parse,
        parse_evidence_hash=malicious_parse.record_hash,
    )
    with pytest.raises(ValueError, match="scale|declaration|request|binding"):
        ProbeAttempt.create(**values)


def test_attempt_rejects_hash_valid_parse_evidence_claiming_another_request() -> None:
    projection = run(
        ScriptedProbeAdapter(steps_for_first(ProbeScriptStep("response", valid_raw(), None, None)))
    )
    honest = projection.attempts[0]
    payload = honest.parse_evidence.to_payload()
    payload["request_id"] = "probe-request-malicious"
    payload["request_hash"] = canonical_payload_hash("malicious-request")
    malicious_parse = type(honest.parse_evidence).from_payload(
        rehash_payload(payload, id_field="parse_evidence_id", prefix="probe-parse-")
    )
    values = {
        name: getattr(honest, name)
        for name in honest.__dataclass_fields__
        if name not in {"attempt_id", "record_hash"}
    }
    values.update(
        parse_evidence=malicious_parse,
        parse_evidence_hash=malicious_parse.record_hash,
    )
    with pytest.raises(ValueError, match="parse|request|binding"):
        ProbeAttempt.create(**values)


def test_projection_rejects_cross_instance_attempt_with_recomputed_hashes() -> None:
    specification, cases = specification_and_cases()
    case = cases[0]
    runtime_policy = policy()
    run_a = execute_probe_run(
        run_instance_id="run-instance-a",
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter(
            {(case.probe_case_id, 1): ProbeScriptStep("response", valid_raw(), None, None)}
        ),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    run_b = execute_probe_run(
        run_instance_id="run-instance-b",
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=ScriptedProbeAdapter({}),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        stop_after_attempts=0,
    )
    original = run_a.attempts[0]
    values = {
        name: getattr(original, name)
        for name in original.__dataclass_fields__
        if name not in {"attempt_id", "record_hash"}
    }
    values["run_instance_id"] = run_b.run_instance_id
    values["probe_run_id"] = run_b.probe_run_id
    injected = ProbeAttempt.create(**values)
    with pytest.raises(ValueError, match="instance|mixed|run"):
        ProbeRunProjection.create(
            run_instance_id=run_a.run_instance_id,
            specification_hash=specification.output_hash,
            case_inventory_hash=run_a.case_inventory_hash,
            runtime_policy=runtime_policy,
            generation_settings=GENERATION_SETTINGS,
            runtime_identity=RUNTIME_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
            case_ids=(case.probe_case_id,),
            attempts=(injected,),
        )
