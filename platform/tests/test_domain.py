from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

import agent_ex
from agent_ex import domain
from agent_ex.domain import (
    AgentState,
    EventStatus,
    ExposureRecord,
    GenerationAttempt,
    GenerationEvent,
    OpinionRecord,
    RunManifest,
)


SHA = "a" * 64
LATER_SHA = "b" * 64
STARTED = "2026-07-16T00:00:00Z"
FINISHED = "2026-07-16T00:00:01+00:00"
TERMINAL_COUNTS = {
    "succeeded": 1,
    "failed": 0,
    "excluded": 0,
    "imputed": 0,
    "fallback": 0,
}
STRICT_ELIGIBILITY_POLICY = {
    "failed": 0,
    "excluded": 0,
    "imputed": 0,
    "fallback": 0,
}


def schedule_slots(rounds: int, population: int) -> tuple[domain.ScheduleSlot, ...]:
    return tuple(
        domain.ScheduleSlot(round_index, f"agent-{agent_index}")
        for agent_index in range(1, population + 1)
        for round_index in range(1, rounds + 1)
    )


def freeze_schedule(
    slots: tuple[domain.ScheduleSlot | dict[str, object], ...],
) -> domain.FrozenSchedule:
    return domain.FrozenSchedule(
        tuple(
            slot
            if isinstance(slot, domain.ScheduleSlot)
            else domain.ScheduleSlot(int(slot["round_index"]), str(slot["agent_id"]))
            for slot in slots
        )
    )


def schedule_digest(
    slots: tuple[domain.ScheduleSlot | dict[str, object], ...],
) -> str:
    return freeze_schedule(slots).schedule_hash


def exposure_payload(exposure: ExposureRecord) -> dict[str, object]:
    return {
        "exposure_id": exposure.exposure_id,
        "agent_id": exposure.agent_id,
        "round_index": exposure.round_index,
        "exposure_mode": exposure.exposure_mode,
        "source_agent_ids": exposure.source_agent_ids,
        "source_event_ids": exposure.source_event_ids,
    }


def valid_exposure(**overrides: object) -> ExposureRecord:
    values: dict[str, object] = {
        "exposure_id": "exposure-1",
        "agent_id": "agent-1",
        "round_index": 1,
        "exposure_mode": "ws_neighbors",
        "source_agent_ids": ("agent-2",),
        "source_event_ids": ("event-2",),
    }
    values.update(overrides)
    return ExposureRecord(**values)  # type: ignore[arg-type]


def payload_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def default_run_spec() -> dict[str, object]:
    schedule = freeze_schedule(schedule_slots(1, 1))
    return {
        "protocol_id": "P1-LLM-OPINION-DYNAMICS",
        "protocol_version": "1.0.0",
        "protocol_hash": SHA,
        "schedule_hash": schedule.schedule_hash,
        "run_config": {
            "rounds": 1,
            "population": 1,
            "expected_event_count": 1,
        },
        "request_parameters": {
            "temperature": 0.7,
            "top_p": 0.8,
        },
        "model_identity": {
            "provider": "local",
            "model": "Qwen/Qwen3-8B",
            "revision": "rev-1",
            "runtime": "vllm-0.15",
        },
        "git_sha": "c" * 40,
        "dirty": False,
        "diff_hash": None,
        "environment_lock_hash": SHA,
        "prompt_template_hash": SHA,
    }


def default_run_id() -> str:
    return domain.derive_run_id(default_run_spec(), 7, "launch-20260716-001")


def default_event_id() -> str:
    return domain.derive_event_id(default_run_id(), 1, "agent-1")


def default_attempt_id() -> str:
    return domain.derive_attempt_id(default_event_id(), 1)


def valid_attempt_kwargs(**overrides: object) -> dict[str, object]:
    exposure = valid_exposure()
    request_params = {"temperature": 0.7, "top_p": 0.8}
    provider_metadata = {"provider": "local", "worker_id": "worker-1"}
    usage = {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
    values: dict[str, object] = {
        "attempt_id": default_attempt_id(),
        "event_id": default_event_id(),
        "sequence": 1,
        "status": EventStatus.SUCCEEDED,
        "request_id": "request-1",
        "provider_request_id": "provider-request-1",
        "exposure_ids": ("exposure-1",),
        "exposure_records": (exposure,),
        "rendered_messages": ({"role": "user", "content": "prompt"},),
        "request_params": request_params,
        "provider_metadata": provider_metadata,
        "rendered_prompt_hash": payload_hash(({"role": "user", "content": "prompt"},)),
        "exposure_hash": payload_hash((exposure_payload(exposure),)),
        "request_params_hash": payload_hash(request_params),
        "provider_metadata_hash": payload_hash(provider_metadata),
        "raw_response": "raw",
        "raw_response_hash": payload_hash("raw"),
        "parsed_response": {"stance": 0.2, "reason": "because"},
        "parsed_result_hash": payload_hash({"stance": 0.2, "reason": "because"}),
        "usage": usage,
        "usage_hash": payload_hash(usage),
        "finish_reason": "stop",
        "http_status": 200,
        "error": None,
        "started_at": STARTED,
        "finished_at": FINISHED,
    }
    values.update(overrides)
    if (
        ("event_id" in overrides or "sequence" in overrides)
        and "attempt_id" not in overrides
        and isinstance(values["sequence"], int)
        and values["sequence"] >= 1
    ):
        values["attempt_id"] = domain.derive_attempt_id(
            str(values["event_id"]), int(values["sequence"])
        )
    if "usage" in overrides and "usage_hash" not in overrides:
        values["usage_hash"] = payload_hash(overrides["usage"])
    if "request_params" in overrides and "request_params_hash" not in overrides:
        values["request_params_hash"] = payload_hash(overrides["request_params"])
    if "provider_metadata" in overrides and "provider_metadata_hash" not in overrides:
        values["provider_metadata_hash"] = payload_hash(overrides["provider_metadata"])
    if "exposure_records" in overrides and "exposure_hash" not in overrides:
        records = overrides["exposure_records"]
        assert isinstance(records, tuple)
        values["exposure_hash"] = payload_hash(
            tuple(exposure_payload(record) for record in records)
        )
    return values


def valid_manifest_kwargs(**overrides: object) -> dict[str, object]:
    overrides = dict(overrides)
    slot_override = overrides.pop("schedule_slots", None)
    run_spec = default_run_spec()
    if {"expected_event_count", "rounds"} & overrides.keys() and "run_spec" not in overrides:
        run_config = dict(run_spec["run_config"])  # type: ignore[arg-type]
        rounds = overrides.get("rounds", run_config["rounds"])
        expected = overrides.get(
            "expected_event_count",
            int(run_config["population"]) * int(rounds),
        )
        run_config["rounds"] = rounds
        run_config["expected_event_count"] = expected
        if (
            isinstance(rounds, int)
            and not isinstance(rounds, bool)
            and rounds > 0
            and isinstance(expected, int)
            and not isinstance(expected, bool)
            and expected > 0
            and expected % rounds == 0
        ):
            run_config["population"] = expected // rounds
        run_spec["run_config"] = run_config
    run_config = run_spec["run_config"]
    assert isinstance(run_config, dict)
    slots = (
        schedule_slots(
            int(run_config["rounds"]),
            int(run_config["population"]),
        )
        if slot_override is None
        else slot_override
    )
    assert isinstance(slots, tuple)
    schedule = freeze_schedule(slots)
    if "run_spec" not in overrides:
        run_spec["schedule_hash"] = schedule.schedule_hash
    run_spec_hash = payload_hash(run_spec)
    replicate_seed = 7
    launch_nonce = "launch-20260716-001"
    run_id = "run-" + payload_hash(
        {
            "run_spec_hash": run_spec_hash,
            "replicate_seed": replicate_seed,
            "launch_nonce": launch_nonce,
        }
    )
    values: dict[str, object] = {
        "run_id": run_id,
        "run_spec": run_spec,
        "run_spec_hash": run_spec_hash,
        "replicate_seed": replicate_seed,
        "launch_nonce": launch_nonce,
        "protocol_id": "P1-LLM-OPINION-DYNAMICS",
        "protocol_version": "1.0.0",
        "protocol_hash": SHA,
        "git_sha": "c" * 40,
        "dirty": False,
        "diff_hash": None,
        "environment_lock_hash": SHA,
        "prompt_template_hash": SHA,
        "model_identity": {
            "provider": "local",
            "model": "Qwen/Qwen3-8B",
            "revision": "rev-1",
            "runtime": "vllm-0.15",
        },
        "environment": {
            "python_version": "3.12.13",
            "dependency_lock_hash": SHA,
            "platform": "linux-x86_64",
        },
        "rounds": 1,
        "schedule_uri": "file:///runs/run-1/schedule.json",
        "schedule": schedule,
        "schedule_hash": schedule.schedule_hash,
        "checkpoint_uri": "file:///runs/run-1/checkpoint.json",
        "checkpoint_hash": SHA,
        "recovery_cursor": None,
        "expected_event_count": 1,
        "actual_event_count": 1,
        "event_ids": (domain.derive_event_id(run_id, 1, "agent-1"),),
        "terminal_counts": TERMINAL_COUNTS,
        "started_at": STARTED,
        "updated_at": FINISHED,
        "last_completed_round": 1,
        "failures": (),
        "archive": {
            "status": "frozen",
            "uri": "s3://bucket/run-1.tar.zst",
            "hash": SHA,
        },
    }
    values.update(overrides)
    if {"expected_event_count", "rounds"} & overrides.keys() and "run_spec" not in overrides:
        values["run_spec"] = run_spec
        values["run_spec_hash"] = run_spec_hash
        values["run_id"] = run_id
        if "event_ids" not in overrides:
            values["event_ids"] = (domain.derive_event_id(run_id, 1, "agent-1"),)
    return values


def valid_event_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "run_id": default_run_id(),
        "event_id": default_event_id(),
        "agent_id": "agent-1",
        "round_index": 1,
        "exposure_id": "exposure-1",
        "status": EventStatus.SUCCEEDED,
        "attempt_ids": (default_attempt_id(),),
        "disposition_reason": None,
        "source_event_id": None,
        "replacement_event_id": None,
    }
    values.update(overrides)
    if {"run_id", "agent_id", "round_index"} & overrides.keys() and "event_id" not in overrides:
        values["event_id"] = domain.derive_event_id(
            str(values["run_id"]), int(values["round_index"]), str(values["agent_id"])
        )
    return values


def test_domain_objects_are_frozen_and_use_slots():
    opinion = OpinionRecord("agent-1", 0, 0.25, "initial reason")
    state = AgentState("agent-1", 0, 0.25, "initial reason", (opinion,), {"age": 30})
    assert "__dict__" not in dir(state)
    with pytest.raises(FrozenInstanceError):
        state.stance = 0.5


def test_json_like_values_are_deeply_copied_and_normalized():
    source = {
        "profile": {"roles": ["student"]},
        "flags": ["beta", "alpha"],
        "score": 0.5,
    }
    state = AgentState("agent-1", 0, 0.25, "reason", (), source)
    source["profile"]["roles"].append("changed")
    assert state.identity["profile"]["roles"] == ("student",)
    assert state.identity["flags"] == ("beta", "alpha")


@pytest.mark.parametrize(
    "value",
    [
        {"x"},
        frozenset({"x"}),
        b"abc",
        bytearray(b"abc"),
        float("nan"),
        float("inf"),
        float("-inf"),
        object(),
    ],
)
def test_json_like_freeze_rejects_unsupported_or_non_finite_leaves(value: object):
    with pytest.raises((TypeError, ValueError), match="JSON-like|finite"):
        AgentState("agent-1", 0, 0.25, "reason", (), {"invalid": value})


@pytest.mark.parametrize("key", ["", 1])
def test_json_like_freeze_rejects_invalid_mapping_keys(key: object):
    with pytest.raises((TypeError, ValueError), match="key"):
        AgentState("agent-1", 0, 0.25, "reason", (), {key: "value"})


def test_canonical_payload_hash_has_fixed_json_encoding():
    left = {"中文": [2, {"b": False, "a": None}]}
    right = {"中文": [2, {"a": None, "b": False}]}
    expected = hashlib.sha256('{"中文":[2,{"a":null,"b":false}]}'.encode()).hexdigest()
    assert domain.canonical_payload_hash(left) == expected
    assert domain.canonical_payload_hash(right) == expected


@pytest.mark.parametrize("value", [{1}, frozenset({1}), float("nan"), float("inf")])
def test_canonical_payload_hash_rejects_non_json_values(value: object):
    with pytest.raises((TypeError, ValueError), match="JSON-like|finite"):
        domain.canonical_payload_hash(value)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: OpinionRecord("", 0, 0.1, "reason"),
        lambda: OpinionRecord("agent-1", 0, "0.1", "reason"),
        lambda: AgentState("agent-1", 0, 0.1, 3, (), {}),
        lambda: ExposureRecord("x", "agent-1", 1, "ws_neighbors", ["agent-2"], ()),
    ],
)
def test_runtime_field_types_and_ids_are_validated(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_event_status_includes_lifecycle_and_all_terminal_states():
    assert {status.value for status in EventStatus} == {
        "pending",
        "in_progress",
        "succeeded",
        "failed",
        "excluded",
        "imputed",
        "fallback",
    }


def test_complete_attempt_event_and_manifest_graph_can_be_constructed():
    attempt = GenerationAttempt(**valid_attempt_kwargs())
    event = GenerationEvent(**valid_event_kwargs(attempt_ids=(attempt.attempt_id,)))
    manifest = RunManifest(**valid_manifest_kwargs())
    assert attempt.rendered_messages[0]["role"] == "user"
    assert event.attempt_ids == (default_attempt_id(),)
    assert manifest.is_complete is True
    assert domain.evaluate_analysis_eligibility(manifest, STRICT_ELIGIBILITY_POLICY) is True


def test_attempt_has_no_implicit_research_defaults():
    with pytest.raises(TypeError, match="missing"):
        GenerationAttempt()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "field",
    [
        "rendered_prompt_hash",
        "exposure_hash",
        "raw_response_hash",
        "parsed_result_hash",
    ],
)
@pytest.mark.parametrize("digest", ["a" * 63, "g" * 64, "A" * 64])
def test_attempt_rejects_noncanonical_sha256_fields(field: str, digest: str):
    with pytest.raises(ValueError, match=field):
        GenerationAttempt(**valid_attempt_kwargs(**{field: digest}))


@pytest.mark.parametrize(
    "field",
    [
        "rendered_prompt_hash",
        "exposure_hash",
        "raw_response_hash",
        "parsed_result_hash",
    ],
)
def test_attempt_rejects_well_formed_hash_for_wrong_payload(field: str):
    with pytest.raises(ValueError, match=field):
        GenerationAttempt(**valid_attempt_kwargs(**{field: SHA}))


@pytest.mark.parametrize("field", ["started_at", "finished_at"])
@pytest.mark.parametrize(
    "timestamp",
    ["2026-07-16", "2026-07-16T00:00:00", "2026-13-16T00:00:00Z", "2026-07-16T08:00:00+08:00"],
)
def test_attempt_rejects_non_utc_or_invalid_timestamps(field: str, timestamp: str):
    with pytest.raises(ValueError, match=field):
        GenerationAttempt(**valid_attempt_kwargs(**{field: timestamp}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"raw_response": None},
        {"raw_response_hash": None},
        {"parsed_response": None},
        {"parsed_result_hash": None},
        {"finish_reason": None},
        {"finished_at": None},
    ],
)
def test_succeeded_attempt_requires_complete_response_evidence(overrides: dict[str, object]):
    with pytest.raises(ValueError, match="succeeded"):
        GenerationAttempt(**valid_attempt_kwargs(**overrides))


def test_failed_attempt_requires_finished_timestamp_and_error():
    failed = valid_attempt_kwargs(
        status=EventStatus.FAILED,
        raw_response=None,
        raw_response_hash=None,
        parsed_response=None,
        parsed_result_hash=None,
        finish_reason=None,
        http_status=503,
        error={"type": "provider_error", "message": "unavailable"},
    )
    GenerationAttempt(**failed)
    for field in ("finished_at", "error"):
        with pytest.raises(ValueError, match="failed"):
            GenerationAttempt(**{**failed, field: None})


def test_failed_attempt_accepts_explicit_partial_response_when_hashes_match():
    failed = GenerationAttempt(
        **valid_attempt_kwargs(
            status=EventStatus.FAILED,
            parsed_response=None,
            parsed_result_hash=None,
            usage={},
            finish_reason=None,
            http_status=503,
            error={"type": "provider_error", "message": "unavailable"},
        )
    )
    assert failed.raw_response == "raw"


@pytest.mark.parametrize(
    "status,started_at",
    [(EventStatus.PENDING, None), (EventStatus.IN_PROGRESS, STARTED)],
)
def test_nonterminal_attempt_states_are_expressible(status: EventStatus, started_at: str | None):
    attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            status=status,
            provider_request_id=None,
            provider_metadata={} if status is EventStatus.PENDING else {"provider": "local"},
            raw_response=None,
            raw_response_hash=None,
            parsed_response=None,
            parsed_result_hash=None,
            usage={},
            finish_reason=None,
            http_status=None,
            error=None,
            started_at=started_at,
            finished_at=None,
        )
    )
    assert attempt.status is status


def test_pending_and_in_progress_attempts_reject_response_or_wrong_timestamps():
    with pytest.raises(ValueError, match="pending"):
        GenerationAttempt(**valid_attempt_kwargs(status=EventStatus.PENDING))
    with pytest.raises(ValueError, match="in_progress"):
        GenerationAttempt(
            **valid_attempt_kwargs(
                status=EventStatus.IN_PROGRESS,
                raw_response=None,
                raw_response_hash=None,
                parsed_response=None,
                parsed_result_hash=None,
                finish_reason=None,
                error=None,
                finished_at=FINISHED,
            )
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_request_id": "provider-1"},
        {"http_status": 102},
        {"usage": {"prompt_tokens": 1}},
        {"raw_response": "raw", "raw_response_hash": payload_hash("raw")},
        {
            "parsed_response": {"stance": 0.1},
            "parsed_result_hash": payload_hash({"stance": 0.1}),
        },
        {"finished_at": FINISHED},
    ],
)
def test_pending_attempt_rejects_all_execution_evidence(overrides: dict[str, object]):
    pending = valid_attempt_kwargs(
        status=EventStatus.PENDING,
        provider_request_id=None,
        raw_response=None,
        raw_response_hash=None,
        parsed_response=None,
        parsed_result_hash=None,
        usage={},
        finish_reason=None,
        http_status=None,
        error=None,
        started_at=None,
        finished_at=None,
    )
    with pytest.raises(ValueError, match="pending"):
        GenerationAttempt(**{**pending, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"http_status": 200},
        {"usage": {"prompt_tokens": 1}},
        {"raw_response": "raw", "raw_response_hash": payload_hash("raw")},
        {
            "parsed_response": {"stance": 0.1},
            "parsed_result_hash": payload_hash({"stance": 0.1}),
        },
        {"finished_at": FINISHED},
    ],
)
def test_in_progress_attempt_rejects_completed_evidence(overrides: dict[str, object]):
    in_progress = valid_attempt_kwargs(
        status=EventStatus.IN_PROGRESS,
        raw_response=None,
        raw_response_hash=None,
        parsed_response=None,
        parsed_result_hash=None,
        usage={},
        finish_reason=None,
        http_status=None,
        error=None,
        finished_at=None,
    )
    with pytest.raises(ValueError, match="in_progress"):
        GenerationAttempt(**{**in_progress, **overrides})


@pytest.mark.parametrize("http_status", [None, 199, 300, 599])
def test_succeeded_attempt_requires_http_success(http_status: int | None):
    with pytest.raises(ValueError, match="succeeded.*HTTP"):
        GenerationAttempt(**valid_attempt_kwargs(http_status=http_status))


@pytest.mark.parametrize("field", ["usage", "finish_reason"])
def test_succeeded_attempt_requires_nonempty_completion_metadata(field: str):
    value: object = {} if field == "usage" else None
    with pytest.raises(ValueError, match="succeeded"):
        GenerationAttempt(**valid_attempt_kwargs(**{field: value}))


def test_attempt_rejects_duplicate_exposures_negative_sequence_and_illegal_status():
    with pytest.raises(ValueError, match="exposure_ids"):
        GenerationAttempt(**valid_attempt_kwargs(exposure_ids=("exposure-1", "exposure-1")))
    with pytest.raises(ValueError, match="sequence"):
        GenerationAttempt(**valid_attempt_kwargs(sequence=-1))
    with pytest.raises(ValueError, match="attempt status"):
        GenerationAttempt(**valid_attempt_kwargs(status=EventStatus.IMPUTED))


def test_exposure_requires_unique_paired_sources():
    for overrides in (
        {"source_agent_ids": ("agent-2", "agent-2")},
        {"source_event_ids": ("event-2", "event-2")},
        {"source_agent_ids": ("agent-2",), "source_event_ids": ()},
        {"source_agent_ids": ("agent-1",), "source_event_ids": ("event-2",)},
    ):
        values = {
            "exposure_id": "exposure-1",
            "agent_id": "agent-1",
            "round_index": 1,
            "exposure_mode": "ws_neighbors",
            "source_agent_ids": ("agent-2",),
            "source_event_ids": ("event-2",),
            **overrides,
        }
        with pytest.raises(ValueError, match="source"):
            ExposureRecord(**values)


def test_exposure_source_presence_matches_mode():
    with pytest.raises(ValueError, match="self_history_only"):
        ExposureRecord(
            "exposure-1",
            "agent-1",
            1,
            "self_history_only",
            ("agent-2",),
            ("event-2",),
        )
    with pytest.raises(ValueError, match="social"):
        ExposureRecord("exposure-1", "agent-1", 1, "ws_neighbors", (), ())


@pytest.mark.parametrize("status", list(EventStatus))
def test_all_event_states_are_expressible(status: EventStatus):
    overrides: dict[str, object] = {"status": status}
    if status is EventStatus.PENDING:
        overrides["attempt_ids"] = ()
    elif status is EventStatus.IN_PROGRESS:
        overrides["attempt_ids"] = ("attempt-1",)
    elif status is EventStatus.SUCCEEDED:
        pass
    elif status is EventStatus.FAILED:
        overrides["disposition_reason"] = "provider_error"
    elif status is EventStatus.EXCLUDED:
        overrides.update(attempt_ids=(), disposition_reason="protocol_exclusion")
    elif status is EventStatus.IMPUTED:
        overrides.update(
            attempt_ids=(),
            disposition_reason="pre_registered_imputation",
            source_event_id="event-2",
        )
    else:
        overrides.update(
            attempt_ids=(),
            disposition_reason="pre_registered_fallback",
            source_event_id="event-2",
            replacement_event_id="event-3",
        )
    event = GenerationEvent(**valid_event_kwargs(**overrides))
    assert event.status is status


def test_pending_event_can_reference_its_pending_attempt():
    event = GenerationEvent(
        **valid_event_kwargs(status=EventStatus.PENDING, attempt_ids=("attempt-1",))
    )
    assert event.attempt_ids == ("attempt-1",)


def test_event_rejects_duplicate_attempts_and_succeeded_without_attempt():
    with pytest.raises(ValueError, match="attempt_ids"):
        GenerationEvent(
            **valid_event_kwargs(
                status=EventStatus.FAILED,
                attempt_ids=("attempt-1", "attempt-1"),
                disposition_reason="provider_error",
            )
        )
    with pytest.raises(ValueError, match="succeeded"):
        GenerationEvent(**valid_event_kwargs(attempt_ids=()))


def test_failed_event_requires_attempt_and_reason():
    for overrides in (
        {"attempt_ids": (), "disposition_reason": "provider_error"},
        {"attempt_ids": ("attempt-1",), "disposition_reason": None},
    ):
        with pytest.raises(ValueError, match="failed"):
            GenerationEvent(**valid_event_kwargs(status=EventStatus.FAILED, **overrides))


@pytest.mark.parametrize(
    "status,overrides",
    [
        (EventStatus.EXCLUDED, {"attempt_ids": (), "disposition_reason": None}),
        (
            EventStatus.IMPUTED,
            {"attempt_ids": (), "disposition_reason": "imputed", "source_event_id": None},
        ),
        (
            EventStatus.FALLBACK,
            {
                "attempt_ids": (),
                "disposition_reason": "fallback",
                "source_event_id": "event-2",
                "replacement_event_id": None,
            },
        ),
    ],
)
def test_disposition_events_require_reason_and_provenance(
    status: EventStatus, overrides: dict[str, object]
):
    with pytest.raises(ValueError, match=status.value):
        GenerationEvent(**valid_event_kwargs(status=status, **overrides))


def test_manifest_supports_incomplete_recoverable_runs():
    manifest = RunManifest(
        **valid_manifest_kwargs(
            expected_event_count=3,
            actual_event_count=2,
            event_ids=("event-1", "event-2"),
            terminal_counts={**TERMINAL_COUNTS, "succeeded": 1},
            last_completed_round=None,
            failures=(
                {
                    "event_id": "event-2",
                    "code": "retry_scheduled",
                    "message": "recoverable provider error",
                },
            ),
            archive={"status": "pending", "uri": None, "hash": None},
        )
    )
    assert manifest.is_complete is False
    assert manifest.nonterminal_event_count == 1


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"expected_event_count": -1}, "expected_event_count"),
        ({"expected_event_count": 0}, "expected_event_count"),
        ({"actual_event_count": -1}, "actual_event_count"),
        ({"actual_event_count": 2}, "actual_event_count"),
        ({"event_ids": ("event-1", "event-1")}, "event_ids"),
        ({"terminal_counts": {**TERMINAL_COUNTS, "failed": -1}}, "terminal_counts"),
        ({"terminal_counts": {**TERMINAL_COUNTS, "succeeded": 2}}, "terminal_counts"),
        ({"model_identity": {}}, "model_identity"),
        (
            {
                "model_identity": {
                    "provider": "local",
                    "model": "Qwen/Qwen3-8B",
                    "revision": "",
                    "runtime": "vllm",
                }
            },
            "model_identity",
        ),
        ({"environment": {}}, "environment"),
        ({"environment_lock_hash": ""}, "environment_lock_hash"),
    ],
)
def test_manifest_rejects_invalid_counts_identity_and_environment(
    overrides: dict[str, object], match: str
):
    with pytest.raises((TypeError, ValueError), match=match):
        RunManifest(**valid_manifest_kwargs(**overrides))


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_spec_hash", "x" * 64),
        ("protocol_hash", "a" * 63),
        ("environment_lock_hash", "A" * 64),
        ("prompt_template_hash", "g" * 64),
        ("started_at", "2026-07-16T00:00:00"),
        ("updated_at", "2026-07-16T08:00:00+08:00"),
    ],
)
def test_manifest_rejects_invalid_hashes_and_timestamps(field: str, value: str):
    with pytest.raises(ValueError, match=field):
        RunManifest(**valid_manifest_kwargs(**{field: value}))


def test_manifest_rejects_non_json_evidence_and_incomplete_archive_contract():
    with pytest.raises(TypeError, match="JSON-like"):
        RunManifest(
            **valid_manifest_kwargs(
                failures=(
                    {
                        "event_id": default_event_id(),
                        "code": "provider_error",
                        "message": "failed",
                        "payload": b"not-json",
                    },
                )
            )
        )
    with pytest.raises(ValueError, match="archive"):
        RunManifest(**valid_manifest_kwargs(archive={}))


def test_manifest_requires_schedule_and_checkpoint_hash_pairs():
    for overrides in (
        {"schedule_uri": "", "schedule_hash": SHA},
        {"checkpoint_uri": None, "checkpoint_hash": SHA},
        {"checkpoint_uri": "file:///checkpoint.json", "checkpoint_hash": None},
    ):
        with pytest.raises(ValueError, match="schedule|checkpoint"):
            RunManifest(**valid_manifest_kwargs(**overrides))


def test_manifest_requires_failure_records_cover_failed_terminals():
    with pytest.raises(ValueError, match="failures"):
        RunManifest(
            **valid_manifest_kwargs(
                terminal_counts={**TERMINAL_COUNTS, "succeeded": 0, "failed": 1},
                failures=(),
            )
        )
    with pytest.raises(ValueError, match="failures"):
        RunManifest(
            **valid_manifest_kwargs(
                terminal_counts={**TERMINAL_COUNTS, "succeeded": 0, "failed": 1},
                failures=({"event_id": default_event_id(), "code": "provider_error"},),
            )
        )


def test_manifest_round_and_recovery_cursor_must_be_consistent():
    for overrides in (
        {"last_completed_round": 51},
        {"recovery_cursor": {"round_index": 0}},
        {"recovery_cursor": {"round_index": 51}, "last_completed_round": None},
    ):
        with pytest.raises(ValueError, match="round|recovery_cursor"):
            RunManifest(**valid_manifest_kwargs(**overrides))


def test_manifest_completion_requires_frozen_archive_and_exact_event_total():
    with pytest.raises(ValueError, match="archive"):
        RunManifest(
            **valid_manifest_kwargs(archive={"status": "pending", "uri": None, "hash": None})
        )
    empty_counts = {status: 0 for status in TERMINAL_COUNTS}
    with pytest.raises(ValueError, match="expected_event_count"):
        RunManifest(
            **valid_manifest_kwargs(
                expected_event_count=0,
                actual_event_count=0,
                event_ids=(),
                terminal_counts=empty_counts,
                last_completed_round=None,
                checkpoint_uri=None,
                checkpoint_hash=None,
                archive={"status": "frozen", "uri": "s3://bucket/empty", "hash": SHA},
            )
        )


def test_manifest_analysis_eligibility_uses_explicit_caller_policy():
    for status in ("failed", "excluded", "imputed", "fallback"):
        counts = {key: 0 for key in TERMINAL_COUNTS}
        counts[status] = 1
        failures = (
            (
                {
                    "event_id": default_event_id(),
                    "code": "provider_error",
                    "message": "failed",
                },
            )
            if status == "failed"
            else ()
        )
        manifest = RunManifest(**valid_manifest_kwargs(terminal_counts=counts, failures=failures))
        assert manifest.is_complete is True
        assert (
            domain.evaluate_analysis_eligibility(
                manifest,
                STRICT_ELIGIBILITY_POLICY,
            )
            is False
        )
        permissive = {**STRICT_ELIGIBILITY_POLICY, status: 1}
        assert domain.evaluate_analysis_eligibility(manifest, permissive) is True


def test_attempt_hashes_cover_full_exposure_and_all_provider_payloads():
    exposure = valid_exposure(source_agent_ids=("agent-3",), source_event_ids=("event-3",))
    wrong_hash = payload_hash(("exposure-1",))
    with pytest.raises(ValueError, match="exposure_hash"):
        GenerationAttempt(
            **valid_attempt_kwargs(
                exposure_records=(exposure,),
                exposure_hash=wrong_hash,
            )
        )
    for field in (
        "request_params_hash",
        "provider_metadata_hash",
        "usage_hash",
    ):
        with pytest.raises(ValueError, match=field):
            GenerationAttempt(**valid_attempt_kwargs(**{field: SHA}))


def test_attempt_exposure_ids_must_match_unique_embedded_records():
    exposure = valid_exposure()
    with pytest.raises(ValueError, match="exposure_ids"):
        GenerationAttempt(**valid_attempt_kwargs(exposure_ids=("other-exposure",)))
    with pytest.raises(ValueError, match="exposure_records"):
        GenerationAttempt(**valid_attempt_kwargs(exposure_records=(exposure, exposure)))


def test_succeeded_attempt_requires_provider_identity_and_exact_usage_totals():
    with pytest.raises(ValueError, match="succeeded.*provider"):
        GenerationAttempt(**valid_attempt_kwargs(provider_request_id=None))
    with pytest.raises(ValueError, match="usage"):
        GenerationAttempt(
            **valid_attempt_kwargs(
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 99,
                }
            )
        )


def test_pending_and_in_progress_attempts_reject_provider_and_http_evidence():
    pending = valid_attempt_kwargs(
        status=EventStatus.PENDING,
        provider_request_id=None,
        provider_metadata={},
        raw_response=None,
        raw_response_hash=None,
        parsed_response=None,
        parsed_result_hash=None,
        usage={},
        finish_reason=None,
        http_status=None,
        error=None,
        started_at=None,
        finished_at=None,
    )
    with pytest.raises(ValueError, match="pending"):
        GenerationAttempt(
            **{
                **pending,
                "provider_metadata": {"worker_id": "worker-1"},
                "provider_metadata_hash": payload_hash({"worker_id": "worker-1"}),
            }
        )
    in_progress = valid_attempt_kwargs(
        status=EventStatus.IN_PROGRESS,
        provider_request_id=None,
        provider_metadata={},
        raw_response=None,
        raw_response_hash=None,
        parsed_response=None,
        parsed_result_hash=None,
        usage={},
        finish_reason=None,
        http_status=None,
        error=None,
        finished_at=None,
    )
    with pytest.raises(ValueError, match="in_progress"):
        GenerationAttempt(**{**in_progress, "http_status": 102})


def test_manifest_binds_run_spec_run_id_seed_nonce_and_environment_lock():
    values = valid_manifest_kwargs()
    assert values["run_id"] == domain.derive_run_id(
        values["run_spec"], values["replicate_seed"], values["launch_nonce"]
    )
    for overrides, match in (
        ({"run_spec": {"different": True}}, "run_spec_hash"),
        ({"run_id": "run-forged"}, "run_id"),
        ({"environment_lock_hash": LATER_SHA}, "environment_lock_hash"),
    ):
        with pytest.raises(ValueError, match=match):
            RunManifest(**valid_manifest_kwargs(**overrides))


@pytest.mark.parametrize(
    "field,uri",
    [
        ("schedule_uri", "relative/schedule.json"),
        ("schedule_uri", "ftp://bucket/schedule.json"),
        ("checkpoint_uri", "garbage"),
    ],
)
def test_manifest_rejects_ambiguous_or_unsupported_evidence_uris(field: str, uri: str):
    with pytest.raises(ValueError, match=field):
        RunManifest(**valid_manifest_kwargs(**{field: uri}))


def test_recovery_cursor_requires_checkpoint_and_round_event_position():
    for overrides in (
        {
            "checkpoint_uri": None,
            "checkpoint_hash": None,
            "recovery_cursor": {"round_index": 1, "event_index": 0},
        },
        {"recovery_cursor": {"round_index": 1}},
        {"recovery_cursor": {"event_index": 0}},
    ):
        with pytest.raises(ValueError, match="recovery_cursor|checkpoint"):
            RunManifest(**valid_manifest_kwargs(**overrides))


@pytest.mark.parametrize(
    "status,overrides",
    [
        (
            EventStatus.FAILED,
            {
                "disposition_reason": "provider_error",
                "source_event_id": "event-2",
            },
        ),
        (
            EventStatus.EXCLUDED,
            {
                "attempt_ids": ("attempt-1",),
                "disposition_reason": "protocol_exclusion",
            },
        ),
        (
            EventStatus.IMPUTED,
            {
                "attempt_ids": ("attempt-1",),
                "disposition_reason": "imputed",
                "source_event_id": "event-2",
            },
        ),
        (
            EventStatus.FALLBACK,
            {
                "attempt_ids": ("attempt-1",),
                "disposition_reason": "fallback",
                "source_event_id": "event-2",
                "replacement_event_id": "event-3",
            },
        ),
    ],
)
def test_event_disposition_contract_rejects_forbidden_attempt_or_provenance(
    status: EventStatus, overrides: dict[str, object]
):
    with pytest.raises(ValueError, match=status.value):
        GenerationEvent(**valid_event_kwargs(status=status, **overrides))


def valid_evidence_graph():
    exposure = valid_exposure(
        exposure_mode="self_history_only",
        source_agent_ids=(),
        source_event_ids=(),
    )
    attempt = GenerationAttempt(**valid_attempt_kwargs(exposure_records=(exposure,)))
    event = GenerationEvent(**valid_event_kwargs())
    manifest = RunManifest(**valid_manifest_kwargs())
    return manifest, (event,), (attempt,), (exposure,)


def test_validate_evidence_graph_accepts_exact_complete_graph():
    domain.validate_evidence_graph(*valid_evidence_graph())


def test_validate_evidence_graph_rejects_failed_attempt_supporting_succeeded_event():
    manifest, events, _, exposures = valid_evidence_graph()
    failed = GenerationAttempt(
        **valid_attempt_kwargs(
            status=EventStatus.FAILED,
            exposure_records=exposures,
            provider_metadata={"provider": "local"},
            raw_response=None,
            raw_response_hash=None,
            parsed_response=None,
            parsed_result_hash=None,
            usage={},
            finish_reason=None,
            http_status=503,
            error={"type": "provider_error", "message": "unavailable"},
        )
    )
    with pytest.raises(ValueError, match="succeeded.*attempt"):
        domain.validate_evidence_graph(manifest, events, (failed,), exposures)


def test_validate_evidence_graph_rejects_manifest_and_cross_record_mismatches():
    manifest, events, attempts, exposures = valid_evidence_graph()
    forged_manifest = RunManifest(**valid_manifest_kwargs(event_ids=("other-event",)))
    with pytest.raises(ValueError, match="event_ids"):
        domain.validate_evidence_graph(forged_manifest, events, attempts, exposures)
    wrong_exposure = valid_exposure(
        exposure_id="exposure-1",
        agent_id="agent-9",
        exposure_mode="self_history_only",
        source_agent_ids=(),
        source_event_ids=(),
    )
    with pytest.raises(ValueError, match="exposure"):
        domain.validate_evidence_graph(manifest, events, attempts, (wrong_exposure,))


def test_validate_evidence_graph_rejects_duplicate_exposure_and_inexact_failures():
    manifest, events, attempts, exposures = valid_evidence_graph()
    with pytest.raises(ValueError, match="exposure.*unique"):
        domain.validate_evidence_graph(manifest, events, attempts, exposures + exposures)
    failed_event = GenerationEvent(
        **valid_event_kwargs(
            status=EventStatus.FAILED,
            disposition_reason="provider_error",
        )
    )
    failed_attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            status=EventStatus.FAILED,
            provider_metadata={"provider": "local"},
            raw_response=None,
            raw_response_hash=None,
            parsed_response=None,
            parsed_result_hash=None,
            usage={},
            finish_reason=None,
            http_status=503,
            error={"type": "provider_error", "message": "unavailable"},
        )
    )
    failed_manifest = RunManifest(
        **valid_manifest_kwargs(
            terminal_counts={**TERMINAL_COUNTS, "succeeded": 0, "failed": 1},
            failures=(
                {
                    "event_id": default_event_id(),
                    "code": "provider_error",
                    "message": "failed",
                },
                {
                    "event_id": default_event_id(),
                    "code": "duplicate",
                    "message": "duplicate failure",
                },
            ),
        )
    )
    with pytest.raises(ValueError, match="failures"):
        domain.validate_evidence_graph(
            failed_manifest, (failed_event,), (failed_attempt,), exposures
        )


def test_manifest_analysis_eligibility_has_no_implicit_default():
    counts = {key: 0 for key in TERMINAL_COUNTS}
    counts["excluded"] = 1
    manifest = RunManifest(**valid_manifest_kwargs(terminal_counts=counts))
    assert manifest.is_complete is True
    with pytest.raises(TypeError, match="missing"):
        domain.evaluate_analysis_eligibility(manifest)  # type: ignore[call-arg]
    assert not hasattr(manifest, "is_analysis_eligible")


def _manifest_kwargs_for_spec(run_spec: dict[str, object]) -> dict[str, object]:
    values = valid_manifest_kwargs()
    values["run_spec"] = run_spec
    values["run_spec_hash"] = payload_hash(run_spec)
    values["run_id"] = domain.derive_run_id(
        run_spec, int(values["replicate_seed"]), str(values["launch_nonce"])
    )
    values["event_ids"] = (domain.derive_event_id(str(values["run_id"]), 1, "agent-1"),)
    return values


def test_run_spec_requires_exact_execution_identity_structure():
    required = {
        "protocol_id",
        "protocol_version",
        "protocol_hash",
        "schedule_hash",
        "run_config",
        "request_parameters",
        "model_identity",
        "git_sha",
        "dirty",
        "diff_hash",
        "environment_lock_hash",
        "prompt_template_hash",
    }
    assert set(default_run_spec()) == required
    for missing_key in required:
        incomplete = default_run_spec()
        del incomplete[missing_key]
        with pytest.raises(ValueError, match="run_spec"):
            RunManifest(**_manifest_kwargs_for_spec(incomplete))


@pytest.mark.parametrize(
    ("spec_key", "spec_value", "match"),
    [
        ("protocol_hash", LATER_SHA, "protocol_hash"),
        (
            "model_identity",
            {
                "provider": "local",
                "model": "Qwen/Qwen3-14B",
                "revision": "rev-1",
                "runtime": "vllm-0.15",
            },
            "model_identity",
        ),
        ("git_sha", "d" * 40, "git_sha"),
        ("environment_lock_hash", LATER_SHA, "environment_lock_hash"),
        ("prompt_template_hash", LATER_SHA, "prompt_template_hash"),
        (
            "run_config",
            {"rounds": 2, "population": 1, "expected_event_count": 2},
            "run_config",
        ),
    ],
)
def test_manifest_rejects_run_spec_identity_mismatches(
    spec_key: str, spec_value: object, match: str
):
    run_spec = default_run_spec()
    run_spec[spec_key] = spec_value
    with pytest.raises(ValueError, match=match):
        RunManifest(**_manifest_kwargs_for_spec(run_spec))


def test_run_spec_hash_covers_request_parameters():
    values = valid_manifest_kwargs()
    changed = dict(values["run_spec"])
    changed["request_parameters"] = {"temperature": 0.1, "top_p": 0.8}
    with pytest.raises(ValueError, match="run_spec_hash"):
        RunManifest(**{**values, "run_spec": changed})


def test_dirty_manifest_requires_matching_diff_hash_and_clean_manifest_forbids_it():
    for dirty, diff_hash in ((False, SHA), (True, None), (True, "not-a-sha")):
        run_spec = default_run_spec()
        run_spec.update(dirty=dirty, diff_hash=diff_hash)
        values = _manifest_kwargs_for_spec(run_spec)
        values.update(dirty=dirty, diff_hash=diff_hash)
        with pytest.raises(ValueError, match="diff_hash"):
            RunManifest(**values)

    dirty_spec = default_run_spec()
    dirty_spec.update(dirty=True, diff_hash=LATER_SHA)
    dirty_values = _manifest_kwargs_for_spec(dirty_spec)
    dirty_values.update(dirty=True, diff_hash=LATER_SHA)
    assert RunManifest(**dirty_values).diff_hash == LATER_SHA


def test_event_and_attempt_ids_are_stable_derived_public_identifiers():
    run_id = default_run_id()
    event_id = domain.derive_event_id(run_id, 1, "agent-1")
    attempt_id = domain.derive_attempt_id(event_id, 1)
    assert event_id.startswith("event-")
    assert attempt_id.startswith("attempt-")
    assert event_id == domain.derive_event_id(run_id, 1, "agent-1")
    assert attempt_id == domain.derive_attempt_id(event_id, 1)
    assert domain.derive_event_id(run_id, 2, "agent-1") != event_id
    assert domain.derive_attempt_id(event_id, 2) != attempt_id

    for name in (
        "canonical_payload_hash",
        "derive_run_id",
        "derive_event_id",
        "derive_attempt_id",
        "validate_evidence_graph",
    ):
        assert name in agent_ex.__all__
        assert getattr(agent_ex, name) is getattr(domain, name)


def test_event_and_attempt_reject_forged_identifiers():
    with pytest.raises(ValueError, match="event_id"):
        GenerationEvent(**valid_event_kwargs(event_id="event-forged"))
    with pytest.raises(ValueError, match="attempt_id"):
        GenerationAttempt(**valid_attempt_kwargs(attempt_id="attempt-forged"))


def _two_event_run_spec() -> dict[str, object]:
    frozen_schedule = (
        {"round_index": 1, "agent_id": "agent-2"},
        {"round_index": 2, "agent_id": "agent-1"},
    )
    run_spec = default_run_spec()
    run_spec["run_config"] = {
        "rounds": 2,
        "population": 2,
        "expected_event_count": 2,
    }
    run_spec["schedule_hash"] = schedule_digest(frozen_schedule)
    return run_spec


def _two_event_graph(
    *,
    source_round: int = 1,
    source_agent_id: str = "agent-2",
    recorded_source_agent_id: str = "agent-2",
):
    frozen_schedule = (
        {"round_index": source_round, "agent_id": source_agent_id},
        {"round_index": 2, "agent_id": "agent-1"},
    )
    run_spec = _two_event_run_spec()
    run_spec["schedule_hash"] = schedule_digest(frozen_schedule)
    manifest_values = _manifest_kwargs_for_spec(run_spec)
    manifest_values.update(
        rounds=2,
        expected_event_count=2,
        actual_event_count=2,
        last_completed_round=2,
        terminal_counts={**TERMINAL_COUNTS, "succeeded": 2},
        schedule=freeze_schedule(frozen_schedule),
        schedule_hash=schedule_digest(frozen_schedule),
    )
    run_id = str(manifest_values["run_id"])
    source_event_id = domain.derive_event_id(run_id, source_round, source_agent_id)
    target_event_id = domain.derive_event_id(run_id, 2, "agent-1")
    source_exposure = valid_exposure(
        exposure_id="exposure-source",
        agent_id=source_agent_id,
        round_index=source_round,
        exposure_mode="self_history_only",
        source_agent_ids=(),
        source_event_ids=(),
    )
    target_exposure = valid_exposure(
        exposure_id="exposure-target",
        agent_id="agent-1",
        round_index=2,
        source_agent_ids=(recorded_source_agent_id,),
        source_event_ids=(source_event_id,),
    )
    source_attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            event_id=source_event_id,
            exposure_ids=("exposure-source",),
            exposure_records=(source_exposure,),
        )
    )
    target_attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            event_id=target_event_id,
            exposure_ids=("exposure-target",),
            exposure_records=(target_exposure,),
        )
    )
    source_event = GenerationEvent(
        **valid_event_kwargs(
            run_id=run_id,
            event_id=source_event_id,
            agent_id=source_agent_id,
            round_index=source_round,
            exposure_id="exposure-source",
            attempt_ids=(source_attempt.attempt_id,),
        )
    )
    target_event = GenerationEvent(
        **valid_event_kwargs(
            run_id=run_id,
            event_id=target_event_id,
            round_index=2,
            exposure_id="exposure-target",
            attempt_ids=(target_attempt.attempt_id,),
        )
    )
    manifest_values["event_ids"] = (source_event_id, target_event_id)
    manifest = RunManifest(**manifest_values)
    return (
        manifest,
        (source_event, target_event),
        (source_attempt, target_attempt),
        (source_exposure, target_exposure),
    )


def test_validate_evidence_graph_accepts_sources_from_exact_previous_round():
    domain.validate_evidence_graph(*_two_event_graph())


def test_validate_evidence_graph_rejects_wrong_source_agent_pair():
    with pytest.raises(ValueError, match="source.*agent"):
        domain.validate_evidence_graph(*_two_event_graph(recorded_source_agent_id="agent-3"))


@pytest.mark.parametrize("source_round", [2, 3])
def test_validate_evidence_graph_rejects_same_round_or_forward_sources(
    source_round: int,
):
    with pytest.raises(ValueError, match="round"):
        domain.validate_evidence_graph(*_two_event_graph(source_round=source_round))


def test_exposure_rejects_receiver_self_reference():
    with pytest.raises(ValueError, match="exposed agent"):
        valid_exposure(
            agent_id="agent-1",
            source_agent_ids=("agent-1",),
            source_event_ids=(domain.derive_event_id(default_run_id(), 0, "agent-1"),),
        )


@pytest.mark.parametrize(
    "history",
    [
        (OpinionRecord("agent-2", 1, 0.2, "other agent"),),
        (
            OpinionRecord("agent-1", 2, 0.2, "later"),
            OpinionRecord("agent-1", 1, 0.1, "earlier"),
        ),
        (OpinionRecord("agent-1", 3, 0.2, "future"),),
        (OpinionRecord("agent-1", 2, 0.1, "stale"),),
        (OpinionRecord("agent-1", 2, 0.2, "different reason"),),
    ],
)
def test_agent_state_history_is_a_consistent_ordered_snapshot(
    history: tuple[OpinionRecord, ...],
):
    with pytest.raises(ValueError, match="opinion_history"):
        AgentState("agent-1", 2, 0.2, "current", history, {})


def test_run_spec_binds_protocol_identity_and_expected_event_count():
    for spec_key, manifest_override in (
        ("protocol_id", {"protocol_id": "OTHER-PROTOCOL"}),
        ("protocol_version", {"protocol_version": "2.0.0"}),
    ):
        with pytest.raises(ValueError, match=spec_key):
            RunManifest(**valid_manifest_kwargs(**manifest_override))

    run_spec = default_run_spec()
    run_spec["run_config"] = {
        "rounds": 1,
        "population": 1,
        "expected_event_count": 2,
    }
    with pytest.raises(ValueError, match="expected_event_count"):
        RunManifest(**_manifest_kwargs_for_spec(run_spec))


def test_protocol_version_changes_run_spec_hash_and_run_id():
    original = default_run_spec()
    changed = default_run_spec()
    changed["protocol_version"] = "1.0.1"
    assert payload_hash(changed) != payload_hash(original)
    assert domain.derive_run_id(changed, 7, "launch") != domain.derive_run_id(
        original,
        7,
        "launch",
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"last_completed_round": 0},
        {
            "last_completed_round": 0,
            "recovery_cursor": {"round_index": 1, "event_index": 0},
        },
    ],
)
def test_complete_manifest_requires_final_round_and_no_recovery_cursor(
    overrides: dict[str, object],
):
    with pytest.raises(ValueError, match="complete.*round|recovery_cursor"):
        RunManifest(**valid_manifest_kwargs(**overrides))


def test_incomplete_manifest_accepts_consistent_checkpoint_cursor():
    manifest = RunManifest(
        **valid_manifest_kwargs(
            expected_event_count=2,
            actual_event_count=1,
            event_ids=(default_event_id(),),
            last_completed_round=0,
            recovery_cursor={"round_index": 1, "event_index": 1},
            archive={"status": "pending", "uri": None, "hash": None},
        )
    )
    assert manifest.is_complete is False


@pytest.mark.parametrize(
    "policy",
    [
        {"failed": 0, "excluded": 0, "imputed": 0},
        {**STRICT_ELIGIBILITY_POLICY, "unknown": 0},
        {**STRICT_ELIGIBILITY_POLICY, "failed": -1},
        {**STRICT_ELIGIBILITY_POLICY, "failed": True},
    ],
)
def test_analysis_eligibility_policy_requires_exact_nonnegative_thresholds(
    policy: dict[str, object],
):
    with pytest.raises((TypeError, ValueError), match="policy"):
        domain.evaluate_analysis_eligibility(RunManifest(**valid_manifest_kwargs()), policy)


def test_validate_evidence_graph_rejects_attempt_request_parameter_drift():
    manifest, events, _, exposures = valid_evidence_graph()
    drifted_attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            exposure_records=exposures,
            request_params={"temperature": 0.1, "top_p": 0.8},
        )
    )
    with pytest.raises(ValueError, match="request_params"):
        domain.validate_evidence_graph(
            manifest,
            events,
            (drifted_attempt,),
            exposures,
        )


def test_validate_evidence_graph_rejects_failed_social_source_event():
    manifest, events, attempts, exposures = _two_event_graph()
    source_event, target_event = events
    source_attempt, target_attempt = attempts
    failed_source_attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            event_id=source_attempt.event_id,
            exposure_ids=source_attempt.exposure_ids,
            exposure_records=source_attempt.exposure_records,
            status=EventStatus.FAILED,
            raw_response=None,
            raw_response_hash=None,
            parsed_response=None,
            parsed_result_hash=None,
            usage={},
            finish_reason=None,
            http_status=503,
            error={"type": "provider_error", "message": "unavailable"},
        )
    )
    failed_source_event = GenerationEvent(
        **valid_event_kwargs(
            run_id=source_event.run_id,
            event_id=source_event.event_id,
            agent_id=source_event.agent_id,
            round_index=source_event.round_index,
            exposure_id=source_event.exposure_id,
            status=EventStatus.FAILED,
            attempt_ids=(failed_source_attempt.attempt_id,),
            disposition_reason="provider_error",
        )
    )
    manifest_values = _manifest_kwargs_for_spec(_two_event_run_spec())
    manifest_values.update(
        rounds=2,
        expected_event_count=2,
        actual_event_count=2,
        last_completed_round=2,
        event_ids=manifest.event_ids,
        terminal_counts={**TERMINAL_COUNTS, "succeeded": 1, "failed": 1},
        schedule=manifest.schedule,
        schedule_hash=manifest.schedule_hash,
        failures=(
            {
                "event_id": source_event.event_id,
                "code": "provider_error",
                "message": "unavailable",
            },
        ),
    )
    failed_source_manifest = RunManifest(**manifest_values)
    with pytest.raises(ValueError, match="source.*succeeded"):
        domain.validate_evidence_graph(
            failed_source_manifest,
            (failed_source_event, target_event),
            (failed_source_attempt, target_attempt),
            exposures,
        )


def test_analysis_eligibility_is_publicly_exported():
    assert "evaluate_analysis_eligibility" in agent_ex.__all__
    assert agent_ex.evaluate_analysis_eligibility is domain.evaluate_analysis_eligibility


def test_manifest_binds_expected_count_and_hash_to_exact_schedule_slots():
    slots = (
        {"round_index": 1, "agent_id": "agent-1"},
        {"round_index": 2, "agent_id": "agent-1"},
    )
    values = valid_manifest_kwargs(
        rounds=2,
        expected_event_count=2,
        schedule_slots=slots,
        actual_event_count=2,
        terminal_counts={**TERMINAL_COUNTS, "succeeded": 2},
        last_completed_round=2,
    )
    run_id = str(values["run_id"])
    values["event_ids"] = tuple(
        domain.derive_event_id(run_id, round_index, "agent-1") for round_index in (1, 2)
    )
    manifest = RunManifest(**values)
    assert manifest.expected_event_count == len(slots)
    assert manifest.schedule_hash == schedule_digest(slots)

    with pytest.raises(ValueError, match="schedule_hash"):
        RunManifest(
            **valid_manifest_kwargs(
                schedule_hash=SHA,
            )
        )


@pytest.mark.parametrize(
    "slots",
    [
        (
            {"round_index": 1, "agent_id": "agent-1"},
            {"round_index": 1, "agent_id": "agent-1"},
        ),
        ({"round_index": 0, "agent_id": "agent-1"},),
        (
            {"round_index": 1, "agent_id": "agent-1"},
            {"round_index": 1, "agent_id": "agent-2"},
        ),
    ],
)
def test_manifest_rejects_invalid_or_over_capacity_schedule_slots(
    slots: tuple[dict[str, object], ...],
):
    with pytest.raises(ValueError, match="schedule"):
        RunManifest(
            **valid_manifest_kwargs(
                schedule_slots=slots,
                schedule_hash=schedule_digest(slots),
            )
        )


def test_manifest_allows_frozen_subset_activation_instead_of_population_times_rounds():
    run_spec = default_run_spec()
    run_spec["run_config"] = {
        "rounds": 2,
        "population": 2,
        "expected_event_count": 2,
    }
    slots = (
        {"round_index": 1, "agent_id": "agent-1"},
        {"round_index": 2, "agent_id": "agent-2"},
    )
    run_spec["schedule_hash"] = schedule_digest(slots)
    values = _manifest_kwargs_for_spec(run_spec)
    values.update(
        rounds=2,
        schedule=freeze_schedule(slots),
        schedule_hash=schedule_digest(slots),
        expected_event_count=2,
        actual_event_count=1,
        event_ids=(domain.derive_event_id(str(values["run_id"]), 2, "agent-2"),),
        terminal_counts=TERMINAL_COUNTS,
        last_completed_round=0,
        archive={"status": "pending", "uri": None, "hash": None},
    )
    manifest = RunManifest(**values)
    assert manifest.expected_event_count == 2


def test_complete_graph_coordinates_must_exactly_match_frozen_schedule():
    base_manifest, _, _, _ = _two_event_graph()
    events: list[GenerationEvent] = []
    attempts: list[GenerationAttempt] = []
    exposures: list[ExposureRecord] = []
    for round_index in (1, 2):
        event_id = domain.derive_event_id(
            base_manifest.run_id,
            round_index,
            "agent-1",
        )
        exposure = valid_exposure(
            exposure_id=f"exposure-mismatch-{round_index}",
            agent_id="agent-1",
            round_index=round_index,
            exposure_mode="self_history_only",
            source_agent_ids=(),
            source_event_ids=(),
        )
        attempt = GenerationAttempt(
            **valid_attempt_kwargs(
                event_id=event_id,
                exposure_ids=(exposure.exposure_id,),
                exposure_records=(exposure,),
            )
        )
        event = GenerationEvent(
            **valid_event_kwargs(
                run_id=base_manifest.run_id,
                event_id=event_id,
                agent_id="agent-1",
                round_index=round_index,
                exposure_id=exposure.exposure_id,
                attempt_ids=(attempt.attempt_id,),
            )
        )
        events.append(event)
        attempts.append(attempt)
        exposures.append(exposure)
    values = _manifest_kwargs_for_spec(_two_event_run_spec())
    values.update(
        rounds=2,
        expected_event_count=2,
        actual_event_count=2,
        event_ids=tuple(event.event_id for event in events),
        terminal_counts={**TERMINAL_COUNTS, "succeeded": 2},
        last_completed_round=2,
        schedule=base_manifest.schedule,
        schedule_hash=base_manifest.schedule_hash,
    )
    mismatched_manifest = RunManifest(**values)
    with pytest.raises(ValueError, match="schedule"):
        domain.validate_evidence_graph(
            mismatched_manifest,
            tuple(events),
            tuple(attempts),
            tuple(exposures),
        )


def _incomplete_scheduled_graph(agent_id: str):
    run_spec = default_run_spec()
    run_spec["run_config"] = {
        "rounds": 2,
        "population": 1,
        "expected_event_count": 2,
    }
    frozen_schedule = schedule_slots(2, 1)
    run_spec["schedule_hash"] = schedule_digest(frozen_schedule)
    values = _manifest_kwargs_for_spec(run_spec)
    run_id = str(values["run_id"])
    event_id = domain.derive_event_id(run_id, 1, agent_id)
    exposure = valid_exposure(
        exposure_id="exposure-incomplete",
        agent_id=agent_id,
        round_index=1,
        exposure_mode="self_history_only",
        source_agent_ids=(),
        source_event_ids=(),
    )
    attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            event_id=event_id,
            exposure_ids=(exposure.exposure_id,),
            exposure_records=(exposure,),
        )
    )
    event = GenerationEvent(
        **valid_event_kwargs(
            run_id=run_id,
            event_id=event_id,
            agent_id=agent_id,
            exposure_id=exposure.exposure_id,
            attempt_ids=(attempt.attempt_id,),
        )
    )
    values.update(
        rounds=2,
        schedule=freeze_schedule(frozen_schedule),
        schedule_hash=schedule_digest(frozen_schedule),
        expected_event_count=2,
        actual_event_count=1,
        event_ids=(event_id,),
        last_completed_round=0,
        archive={"status": "pending", "uri": None, "hash": None},
    )
    return RunManifest(**values), (event,), (attempt,), (exposure,)


def test_incomplete_graph_accepts_any_observed_subset_of_frozen_schedule():
    domain.validate_evidence_graph(*_incomplete_scheduled_graph("agent-1"))


def test_incomplete_graph_rejects_coordinates_outside_frozen_schedule():
    with pytest.raises(ValueError, match="schedule"):
        domain.validate_evidence_graph(*_incomplete_scheduled_graph("agent-2"))


def test_frozen_schedule_is_lightweight_immutable_and_reusable_at_formal_scale():
    slots = tuple(
        domain.ScheduleSlot(round_index, f"agent-{agent_index}")
        for agent_index in range(1, 1001)
        for round_index in range(1, 51)
    )
    schedule = domain.FrozenSchedule(slots)
    assert schedule.slots is slots
    assert schedule.count == 50_000
    assert all(not isinstance(slot, MappingProxyType) for slot in schedule.slots)
    with pytest.raises(FrozenInstanceError):
        schedule.slots[0].agent_id = "forged"

    small_schedule = domain.FrozenSchedule((domain.ScheduleSlot(1, "agent-1"),))
    manifest = RunManifest(
        **valid_manifest_kwargs(
            schedule=small_schedule,
            schedule_hash=small_schedule.schedule_hash,
        )
    )
    assert manifest.schedule is small_schedule
    for name in ("ScheduleSlot", "FrozenSchedule"):
        assert name in agent_ex.__all__
        assert getattr(agent_ex, name) is getattr(domain, name)


def test_schedule_identity_changes_hash_run_id_and_event_id():
    first = domain.FrozenSchedule((domain.ScheduleSlot(1, "agent-1"),))
    second = domain.FrozenSchedule((domain.ScheduleSlot(1, "agent-2"),))
    assert first.schedule_hash != second.schedule_hash

    first_spec = default_run_spec()
    second_spec = default_run_spec()
    first_spec["schedule_hash"] = first.schedule_hash
    second_spec["schedule_hash"] = second.schedule_hash
    first_run_id = domain.derive_run_id(first_spec, 7, "launch")
    second_run_id = domain.derive_run_id(second_spec, 7, "launch")
    assert first_run_id != second_run_id
    assert domain.derive_event_id(first_run_id, 1, "agent-1") != domain.derive_event_id(
        second_run_id,
        1,
        "agent-1",
    )


def test_schedule_requires_at_least_one_activation_in_every_manifest_round():
    frozen_schedule = domain.FrozenSchedule((domain.ScheduleSlot(1, "agent-1"),))
    run_spec = default_run_spec()
    run_spec["run_config"] = {
        "rounds": 2,
        "population": 1,
        "expected_event_count": 1,
    }
    run_spec["schedule_hash"] = frozen_schedule.schedule_hash
    values = _manifest_kwargs_for_spec(run_spec)
    values.update(
        rounds=2,
        schedule=frozen_schedule,
        schedule_hash=frozen_schedule.schedule_hash,
        expected_event_count=1,
        actual_event_count=0,
        event_ids=(),
        terminal_counts={key: 0 for key in TERMINAL_COUNTS},
        last_completed_round=None,
        archive={"status": "pending", "uri": None, "hash": None},
    )
    with pytest.raises(ValueError, match="schedule.*round"):
        RunManifest(**values)


def _progress_graph(
    coordinates: tuple[tuple[int, str], ...],
    *,
    last_completed_round: int | None,
    recovery_cursor: dict[str, int] | None = None,
):
    frozen_schedule = domain.FrozenSchedule(
        (
            domain.ScheduleSlot(1, "agent-1"),
            domain.ScheduleSlot(1, "agent-2"),
            domain.ScheduleSlot(2, "agent-1"),
            domain.ScheduleSlot(2, "agent-2"),
            domain.ScheduleSlot(3, "agent-1"),
        )
    )
    run_spec = default_run_spec()
    run_spec["run_config"] = {
        "rounds": 3,
        "population": 2,
        "expected_event_count": frozen_schedule.count,
    }
    run_spec["schedule_hash"] = frozen_schedule.schedule_hash
    values = _manifest_kwargs_for_spec(run_spec)
    run_id = str(values["run_id"])
    events: list[GenerationEvent] = []
    attempts: list[GenerationAttempt] = []
    exposures: list[ExposureRecord] = []
    for index, (round_index, agent_id) in enumerate(coordinates, start=1):
        event_id = domain.derive_event_id(run_id, round_index, agent_id)
        exposure = valid_exposure(
            exposure_id=f"exposure-progress-{index}",
            agent_id=agent_id,
            round_index=round_index,
            exposure_mode="self_history_only",
            source_agent_ids=(),
            source_event_ids=(),
        )
        attempt = GenerationAttempt(
            **valid_attempt_kwargs(
                event_id=event_id,
                exposure_ids=(exposure.exposure_id,),
                exposure_records=(exposure,),
            )
        )
        event = GenerationEvent(
            **valid_event_kwargs(
                run_id=run_id,
                event_id=event_id,
                agent_id=agent_id,
                round_index=round_index,
                exposure_id=exposure.exposure_id,
                attempt_ids=(attempt.attempt_id,),
            )
        )
        events.append(event)
        attempts.append(attempt)
        exposures.append(exposure)
    values.update(
        rounds=3,
        schedule=frozen_schedule,
        schedule_hash=frozen_schedule.schedule_hash,
        expected_event_count=frozen_schedule.count,
        actual_event_count=len(events),
        event_ids=tuple(event.event_id for event in events),
        terminal_counts={**TERMINAL_COUNTS, "succeeded": len(events)},
        last_completed_round=last_completed_round,
        recovery_cursor=recovery_cursor,
        archive={"status": "pending", "uri": None, "hash": None},
    )
    return RunManifest(**values), tuple(events), tuple(attempts), tuple(exposures)


def test_incomplete_graph_covers_completed_rounds_and_only_current_round_subset():
    graph = _progress_graph(
        ((1, "agent-1"), (1, "agent-2"), (2, "agent-1")),
        last_completed_round=1,
    )
    domain.validate_evidence_graph(*graph)


@pytest.mark.parametrize("last_completed_round", [None, 0])
def test_no_completed_round_marker_allows_only_first_round_subset(
    last_completed_round: int | None,
):
    graph = _progress_graph(
        ((1, "agent-1"),),
        last_completed_round=last_completed_round,
    )
    domain.validate_evidence_graph(*graph)


def test_incomplete_graph_rejects_missing_completed_round_schedule_slot():
    graph = _progress_graph(
        ((1, "agent-1"), (2, "agent-1")),
        last_completed_round=1,
    )
    with pytest.raises(ValueError, match="completed.*schedule"):
        domain.validate_evidence_graph(*graph)


def test_incomplete_graph_rejects_events_beyond_current_next_round():
    graph = _progress_graph(
        ((1, "agent-1"), (1, "agent-2"), (3, "agent-1")),
        last_completed_round=1,
    )
    with pytest.raises(ValueError, match="future|next round"):
        domain.validate_evidence_graph(*graph)


@pytest.mark.parametrize(
    ("actual_event_count", "terminal_count"),
    [
        (1, 1),
        (5, 5),
        (2, 1),
    ],
)
def test_manifest_rejects_progress_counts_inconsistent_with_completed_and_next_round(
    actual_event_count: int,
    terminal_count: int,
):
    frozen_schedule = domain.FrozenSchedule(
        (
            domain.ScheduleSlot(1, "agent-1"),
            domain.ScheduleSlot(1, "agent-2"),
            domain.ScheduleSlot(2, "agent-1"),
            domain.ScheduleSlot(2, "agent-2"),
            domain.ScheduleSlot(3, "agent-1"),
        )
    )
    run_spec = default_run_spec()
    run_spec["run_config"] = {
        "rounds": 3,
        "population": 2,
        "expected_event_count": frozen_schedule.count,
    }
    run_spec["schedule_hash"] = frozen_schedule.schedule_hash
    values = _manifest_kwargs_for_spec(run_spec)
    run_id = str(values["run_id"])
    event_ids = tuple(
        domain.derive_event_id(run_id, index + 1, f"record-{index}")
        for index in range(actual_event_count)
    )
    values.update(
        rounds=3,
        schedule=frozen_schedule,
        schedule_hash=frozen_schedule.schedule_hash,
        expected_event_count=frozen_schedule.count,
        actual_event_count=actual_event_count,
        event_ids=event_ids,
        terminal_counts={**TERMINAL_COUNTS, "succeeded": terminal_count},
        last_completed_round=1,
        archive={"status": "pending", "uri": None, "hash": None},
    )
    with pytest.raises(ValueError, match="progress|completed|next round"):
        RunManifest(**values)


def test_completed_round_event_must_itself_be_terminal():
    manifest, events, attempts, exposures = _progress_graph(
        ((1, "agent-1"), (1, "agent-2"), (2, "agent-1")),
        last_completed_round=1,
    )
    first_event = events[0]
    first_attempt = attempts[0]
    in_progress_attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            event_id=first_attempt.event_id,
            exposure_ids=first_attempt.exposure_ids,
            exposure_records=first_attempt.exposure_records,
            status=EventStatus.IN_PROGRESS,
            provider_request_id=None,
            provider_metadata={},
            raw_response=None,
            raw_response_hash=None,
            parsed_response=None,
            parsed_result_hash=None,
            usage={},
            finish_reason=None,
            http_status=None,
            error=None,
            finished_at=None,
        )
    )
    in_progress_event = GenerationEvent(
        **valid_event_kwargs(
            run_id=first_event.run_id,
            event_id=first_event.event_id,
            agent_id=first_event.agent_id,
            round_index=first_event.round_index,
            exposure_id=first_event.exposure_id,
            status=EventStatus.IN_PROGRESS,
            attempt_ids=(in_progress_attempt.attempt_id,),
        )
    )
    values = _manifest_kwargs_for_spec(dict(_json_ready_for_test(manifest.run_spec)))
    values.update(
        rounds=manifest.rounds,
        schedule=manifest.schedule,
        schedule_hash=manifest.schedule_hash,
        expected_event_count=manifest.expected_event_count,
        actual_event_count=manifest.actual_event_count,
        event_ids=manifest.event_ids,
        terminal_counts={**TERMINAL_COUNTS, "succeeded": 2},
        last_completed_round=1,
        archive={"status": "pending", "uri": None, "hash": None},
    )
    compensated_manifest = RunManifest(**values)
    with pytest.raises(ValueError, match="completed.*terminal"):
        domain.validate_evidence_graph(
            compensated_manifest,
            (in_progress_event, *events[1:]),
            (in_progress_attempt, *attempts[1:]),
            exposures,
        )


def _json_ready_for_test(value: object) -> object:
    if isinstance(value, dict) or isinstance(value, MappingProxyType):
        return {key: _json_ready_for_test(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready_for_test(item) for item in value]
    return value


def test_recovery_cursor_event_index_is_bounded_by_next_round_slots():
    with pytest.raises(ValueError, match="event_index"):
        _progress_graph(
            ((1, "agent-1"), (1, "agent-2")),
            last_completed_round=1,
            recovery_cursor={"round_index": 2, "event_index": 3},
        )


def test_recovery_cursor_requires_observed_current_round_schedule_prefix():
    graph = _progress_graph(
        ((1, "agent-1"), (1, "agent-2"), (2, "agent-2")),
        last_completed_round=1,
        recovery_cursor={"round_index": 2, "event_index": 1},
    )
    with pytest.raises(ValueError, match="cursor|prefix"):
        domain.validate_evidence_graph(*graph)


def test_frozen_schedule_payload_round_trip_defines_hash_artifact():
    schedule = domain.FrozenSchedule(
        (
            domain.ScheduleSlot(1, "agent-1"),
            domain.ScheduleSlot(2, "agent-2"),
        )
    )
    payload = schedule.to_payload()
    assert payload == {
        "version": 1,
        "slots": [
            {"round_index": 1, "agent_id": "agent-1"},
            {"round_index": 2, "agent_id": "agent-2"},
        ],
    }
    restored = domain.FrozenSchedule.from_payload(payload)
    assert restored == schedule
    assert restored.schedule_hash == domain.canonical_payload_hash(payload)


def test_run_manifest_payload_round_trip_requires_external_frozen_schedule():
    manifest = RunManifest(**valid_manifest_kwargs())
    payload = manifest.to_payload()
    assert "schedule" not in payload
    assert payload["schedule_count"] == manifest.schedule.count
    restored = RunManifest.from_payload(payload, schedule=manifest.schedule)
    assert restored == manifest
    with pytest.raises(ValueError, match="schedule"):
        RunManifest.from_payload(
            payload,
            schedule=domain.FrozenSchedule((domain.ScheduleSlot(1, "agent-2"),)),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"version": True, "slots": []},
        {"version": 1.0, "slots": []},
        {"version": "1", "slots": []},
        {"version": 1, "slots": ()},
        {
            "version": 1,
            "slots": [MappingProxyType({"round_index": 1, "agent_id": "agent-1"})],
        },
        {"version": 1, "slots": [{"round_index": True, "agent_id": "agent-1"}]},
        {"version": 1, "slots": [{"round_index": 1.0, "agent_id": "agent-1"}]},
        {"version": 1, "slots": [{"round_index": "1", "agent_id": "agent-1"}]},
        {"version": 1, "slots": [{"round_index": 1, "agent_id": 1}]},
    ],
)
def test_frozen_schedule_from_payload_requires_strict_json_shape(
    payload: dict[str, object],
):
    with pytest.raises((TypeError, ValueError)):
        domain.FrozenSchedule.from_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("run_spec", MappingProxyType({})),
        ("model_identity", MappingProxyType({})),
        ("environment", MappingProxyType({})),
        ("terminal_counts", MappingProxyType({})),
        ("archive", MappingProxyType({})),
        ("event_ids", ()),
        ("event_ids", "event-1"),
        ("event_ids", None),
        ("failures", ()),
        ("failures", {}),
        ("failures", None),
        ("schedule_count", True),
        ("schedule_count", 1.0),
        ("schedule_count", "1"),
    ],
)
def test_run_manifest_from_payload_rejects_non_json_container_and_count_types(
    field_name: str,
    replacement: object,
):
    manifest = RunManifest(**valid_manifest_kwargs())
    payload = manifest.to_payload()
    payload[field_name] = replacement
    with pytest.raises((TypeError, ValueError)):
        RunManifest.from_payload(payload, schedule=manifest.schedule)


def test_run_manifest_from_payload_rejects_non_dict_root_and_failure_objects():
    manifest = RunManifest(**valid_manifest_kwargs())
    payload = manifest.to_payload()
    with pytest.raises(TypeError):
        RunManifest.from_payload(
            MappingProxyType(payload),
            schedule=manifest.schedule,
        )

    payload["failures"] = [MappingProxyType({})]
    with pytest.raises(TypeError, match="failures"):
        RunManifest.from_payload(payload, schedule=manifest.schedule)


def test_runtime_recovery_cursor_rejects_additional_keys():
    with pytest.raises(ValueError, match="recovery_cursor"):
        _progress_graph(
            ((1, "agent-1"), (1, "agent-2")),
            last_completed_round=1,
            recovery_cursor={
                "round_index": 2,
                "event_index": 0,
                "worker_offset": 0,
            },
        )


def test_manifest_payload_recovery_cursor_rejects_additional_keys():
    manifest, _, _, _ = _progress_graph(
        ((1, "agent-1"), (1, "agent-2")),
        last_completed_round=1,
        recovery_cursor={"round_index": 2, "event_index": 0},
    )
    payload = manifest.to_payload()
    payload["recovery_cursor"] = {
        "round_index": 2,
        "event_index": 0,
        "worker_offset": 0,
    }
    with pytest.raises(ValueError, match="recovery_cursor"):
        RunManifest.from_payload(payload, schedule=manifest.schedule)


@pytest.mark.parametrize("population", [0, -1, True, 1.5])
def test_manifest_requires_a_strictly_positive_integer_population(population: object):
    run_spec = default_run_spec()
    run_config = dict(run_spec["run_config"])  # type: ignore[arg-type]
    run_config["population"] = population
    run_spec["run_config"] = run_config
    with pytest.raises((TypeError, ValueError), match="population"):
        RunManifest(**_manifest_kwargs_for_spec(run_spec))


def test_manifest_rejects_self_reported_count_that_differs_from_schedule():
    run_spec = default_run_spec()
    run_config = dict(run_spec["run_config"])  # type: ignore[arg-type]
    run_config["expected_event_count"] = 2
    run_spec["run_config"] = run_config
    with pytest.raises(ValueError, match="expected_event_count"):
        RunManifest(**_manifest_kwargs_for_spec(run_spec))


def test_agent_state_after_initial_round_requires_current_history_record():
    with pytest.raises(ValueError, match="opinion_history"):
        AgentState("agent-1", 1, 0.2, "current", (), {})


def test_validate_evidence_graph_rejects_records_outside_manifest_rounds():
    manifest, events, attempts, exposures = valid_evidence_graph()
    event = events[0]
    exposure = exposures[0]
    out_of_range_exposure = valid_exposure(
        exposure_id=exposure.exposure_id,
        agent_id=exposure.agent_id,
        round_index=0,
        exposure_mode="self_history_only",
        source_agent_ids=(),
        source_event_ids=(),
    )
    out_of_range_attempt = GenerationAttempt(
        **valid_attempt_kwargs(
            event_id=domain.derive_event_id(manifest.run_id, 0, event.agent_id),
            exposure_records=(out_of_range_exposure,),
        )
    )
    out_of_range_event = GenerationEvent(
        **valid_event_kwargs(
            run_id=manifest.run_id,
            round_index=0,
            exposure_id=out_of_range_exposure.exposure_id,
            attempt_ids=(out_of_range_attempt.attempt_id,),
        )
    )
    graph_manifest = RunManifest(**valid_manifest_kwargs(event_ids=(out_of_range_event.event_id,)))
    with pytest.raises(ValueError, match="round"):
        domain.validate_evidence_graph(
            graph_manifest,
            (out_of_range_event,),
            (out_of_range_attempt,),
            (out_of_range_exposure,),
        )


def test_complete_evidence_graph_requires_every_round_schedule_slot():
    manifest_values = valid_manifest_kwargs(
        rounds=2,
        expected_event_count=2,
        actual_event_count=2,
        last_completed_round=2,
        terminal_counts={**TERMINAL_COUNTS, "succeeded": 2},
    )
    run_id = str(manifest_values["run_id"])
    events: list[GenerationEvent] = []
    attempts: list[GenerationAttempt] = []
    exposures: list[ExposureRecord] = []
    for agent_id in ("agent-1", "agent-2"):
        event_id = domain.derive_event_id(run_id, 1, agent_id)
        exposure = valid_exposure(
            exposure_id=f"exposure-{agent_id}",
            agent_id=agent_id,
            round_index=1,
            exposure_mode="self_history_only",
            source_agent_ids=(),
            source_event_ids=(),
        )
        attempt = GenerationAttempt(
            **valid_attempt_kwargs(
                event_id=event_id,
                exposure_ids=(exposure.exposure_id,),
                exposure_records=(exposure,),
            )
        )
        event = GenerationEvent(
            **valid_event_kwargs(
                run_id=run_id,
                event_id=event_id,
                agent_id=agent_id,
                round_index=1,
                exposure_id=exposure.exposure_id,
                attempt_ids=(attempt.attempt_id,),
            )
        )
        events.append(event)
        attempts.append(attempt)
        exposures.append(exposure)
    manifest_values["event_ids"] = tuple(event.event_id for event in events)
    manifest = RunManifest(**manifest_values)
    with pytest.raises(ValueError, match="schedule|final round|round"):
        domain.validate_evidence_graph(
            manifest,
            tuple(events),
            tuple(attempts),
            tuple(exposures),
        )


def _provenance_graph(
    *,
    first_round: int,
    second_round: int,
    first_source: str | None,
    second_source: str | None,
):
    manifest_values = valid_manifest_kwargs(
        rounds=2,
        expected_event_count=2,
        actual_event_count=2,
        last_completed_round=2,
        terminal_counts={**TERMINAL_COUNTS, "succeeded": 0, "imputed": 2},
    )
    run_id = str(manifest_values["run_id"])
    first_id = domain.derive_event_id(run_id, first_round, "agent-1")
    second_id = domain.derive_event_id(run_id, second_round, "agent-2")
    source_ids = {
        "first": first_id,
        "second": second_id,
    }
    events = (
        GenerationEvent(
            **valid_event_kwargs(
                run_id=run_id,
                event_id=first_id,
                agent_id="agent-1",
                round_index=first_round,
                exposure_id="exposure-first",
                status=EventStatus.IMPUTED,
                attempt_ids=(),
                disposition_reason="imputed",
                source_event_id=source_ids.get(first_source),
            )
        ),
        GenerationEvent(
            **valid_event_kwargs(
                run_id=run_id,
                event_id=second_id,
                agent_id="agent-2",
                round_index=second_round,
                exposure_id="exposure-second",
                status=EventStatus.IMPUTED,
                attempt_ids=(),
                disposition_reason="imputed",
                source_event_id=source_ids.get(second_source),
            )
        ),
    )
    exposures = (
        valid_exposure(
            exposure_id="exposure-first",
            agent_id="agent-1",
            round_index=first_round,
            exposure_mode="self_history_only",
            source_agent_ids=(),
            source_event_ids=(),
        ),
        valid_exposure(
            exposure_id="exposure-second",
            agent_id="agent-2",
            round_index=second_round,
            exposure_mode="self_history_only",
            source_agent_ids=(),
            source_event_ids=(),
        ),
    )
    manifest_values["event_ids"] = tuple(event.event_id for event in events)
    return RunManifest(**manifest_values), events, (), exposures


def test_validate_evidence_graph_rejects_future_event_provenance():
    graph = _provenance_graph(
        first_round=1,
        second_round=2,
        first_source="second",
        second_source="first",
    )
    with pytest.raises(ValueError, match="provenance.*future"):
        domain.validate_evidence_graph(*graph)


def test_validate_evidence_graph_rejects_event_provenance_cycles():
    graph = _provenance_graph(
        first_round=1,
        second_round=1,
        first_source="second",
        second_source="first",
    )
    with pytest.raises(ValueError, match="provenance.*cycle"):
        domain.validate_evidence_graph(*graph)
