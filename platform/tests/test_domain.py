from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

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


def payload_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def valid_attempt_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "attempt_id": "attempt-1",
        "event_id": "event-1",
        "sequence": 1,
        "status": EventStatus.SUCCEEDED,
        "request_id": "request-1",
        "provider_request_id": "provider-request-1",
        "exposure_ids": ("exposure-1",),
        "rendered_messages": ({"role": "user", "content": "prompt"},),
        "request_params": {"temperature": 0.7, "stop": ["END"]},
        "rendered_prompt_hash": payload_hash(
            ({"role": "user", "content": "prompt"},)
        ),
        "exposure_hash": payload_hash(("exposure-1",)),
        "raw_response": "raw",
        "raw_response_hash": payload_hash("raw"),
        "parsed_response": {"stance": 0.2, "reason": "because"},
        "parsed_result_hash": payload_hash({"stance": 0.2, "reason": "because"}),
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        "finish_reason": "stop",
        "http_status": 200,
        "error": None,
        "started_at": STARTED,
        "finished_at": FINISHED,
    }
    values.update(overrides)
    return values


def valid_manifest_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "run_id": "run-1",
        "run_spec_hash": SHA,
        "protocol_id": "P1-LLM-OPINION-DYNAMICS",
        "protocol_version": "1.0.0",
        "protocol_hash": SHA,
        "git_sha": "c" * 40,
        "dirty": False,
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
        "rounds": 50,
        "schedule_uri": "file:///runs/run-1/schedule.json",
        "schedule_hash": SHA,
        "checkpoint_uri": "file:///runs/run-1/checkpoint.json",
        "checkpoint_hash": SHA,
        "recovery_cursor": None,
        "expected_event_count": 1,
        "actual_event_count": 1,
        "event_ids": ("event-1",),
        "terminal_counts": TERMINAL_COUNTS,
        "started_at": STARTED,
        "updated_at": FINISHED,
        "last_completed_round": 0,
        "failures": (),
        "archive": {
            "status": "frozen",
            "uri": "s3://bucket/run-1.tar.zst",
            "hash": SHA,
        },
    }
    values.update(overrides)
    return values


def valid_event_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "event_id": "event-1",
        "agent_id": "agent-1",
        "round_index": 1,
        "exposure_id": "exposure-1",
        "status": EventStatus.SUCCEEDED,
        "attempt_ids": ("attempt-1",),
        "disposition_reason": None,
        "source_event_id": None,
        "replacement_event_id": None,
    }
    values.update(overrides)
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
    expected = hashlib.sha256(
        '{"中文":[2,{"a":null,"b":false}]}'.encode()
    ).hexdigest()
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
    assert event.attempt_ids == ("attempt-1",)
    assert manifest.is_complete is True
    assert manifest.is_analysis_eligible is True


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
            attempt_ids=(), disposition_reason="pre_registered_imputation", source_event_id="event-2"
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
            GenerationEvent(
                **valid_event_kwargs(status=EventStatus.FAILED, **overrides)
            )


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
                        "event_id": "event-1",
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
                failures=({"event_id": "event-1", "code": "provider_error"},),
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
            **valid_manifest_kwargs(
                archive={"status": "pending", "uri": None, "hash": None}
            )
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


def test_manifest_analysis_eligibility_excludes_failed_imputed_or_fallback_runs():
    for status in ("failed", "imputed", "fallback"):
        counts = {key: 0 for key in TERMINAL_COUNTS}
        counts[status] = 1
        failures = (
            {"event_id": "event-1", "code": "provider_error", "message": "failed"},
        ) if status == "failed" else ()
        manifest = RunManifest(
            **valid_manifest_kwargs(terminal_counts=counts, failures=failures)
        )
        assert manifest.is_complete is True
        assert manifest.is_analysis_eligible is False
