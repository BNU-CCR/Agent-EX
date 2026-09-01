from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import pytest
import agent_ex
import agent_ex.engine as engine_module

from agent_ex.adapters.base import AdapterRequest
from agent_ex.adapters.mock import MockAdapter, MockScriptStep
from agent_ex.checkpoint import load_checkpoint, validate_checkpoint
from agent_ex.domain import EventStatus, GenerationAttempt, canonical_payload_hash, derive_event_id
from agent_ex.engine import (
    AttemptAuthorization,
    AttemptExecutionEvidence,
    AttemptLifecycleFailure,
    AttemptInvocationResult,
    AttemptOutcome,
    PreparedAttempt,
    StrictSerialLifecycleEngine,
    SuccessfulEventCommit,
)
from agent_ex.execution_evidence import (
    AdapterRequestEvidence,
    FinalizedAttemptEvidence,
    PersistedInvocationEvidence,
)
from agent_ex.state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from agent_ex.storage import RunStorage
from test_storage import (
    attempt_transition,
    finalized_evidence,
    persisted_invocation,
    prepared_evidence_bundle,
    prompt_topic,
    successful_event,
)


NOW = "2026-08-18T00:00:00+00:00"


@dataclass(frozen=True, slots=True)
class _EvidenceContractFixture:
    authorization: AttemptAuthorization
    request: AdapterRequest
    pending_attempt: GenerationAttempt
    in_progress_attempt: GenerationAttempt


def adapter_for(
    event_id: str, *, reason: str = "reason-0-1", attempt_index: int = 1
) -> MockAdapter:
    steps = tuple(
        MockScriptStep.success(
            {
                "stance": "label-2",
                "confidence": 3,
                "public_reason": reason if index == attempt_index else "unused prior response",
            }
        )
        for index in range(1, attempt_index + 1)
    )
    return MockAdapter(
        script={event_id: steps},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )


def response_metadata(response: object) -> dict[str, object]:
    return {
        "adapter_response_id": response.response_id,
        "adapter_response_hash": response.record_hash,
        "adapter_outcome": response.outcome,
        "adapter_error": None if response.error is None else dict(response.error),
        "runtime_identity": dict(response.runtime_identity),
        "runtime_identity_hash": response.runtime_identity_hash,
        "script_hash": response.script_hash,
    }


def prepared(run_id: str, *, ordinal: int = 9, attempt_index: int = 1) -> _EvidenceContractFixture:
    """Cross-suite typed fixture; engine execution itself uses ``prepared_event``."""

    from test_prompt import build as build_prompt

    prompt = build_prompt()
    event_id = derive_event_id(run_id, ordinal)
    if prompt.event_id != event_id:
        raise ValueError("evidence contract fixture requires the matching prompt event")
    model_seed = 12345
    adapter_binding = adapter_for(event_id, attempt_index=attempt_index).execution_binding()
    request = AdapterRequest.create(
        prompt_view=prompt,
        attempt_index=attempt_index,
        mock_seed=model_seed,
        mock_only=True,
    )
    base = {
        "attempt_id": request.attempt_id,
        "event_id": event_id,
        "attempt_index": attempt_index,
        "request_id": request.request_id,
        "exposure_id": prompt.exposure_id,
        "rendered_messages": request.rendered_messages,
        "rendered_prompt_hash": request.rendered_messages_hash,
        "request_parameters": {"temperature": 0.0},
        "request_parameters_hash": canonical_payload_hash({"temperature": 0.0}),
        "model_identity": adapter_binding.model_identity,
        "model_identity_hash": adapter_binding.model_identity_hash,
        "model_seed": model_seed,
        "provider_request_id": None,
        "provider_metadata": {},
        "provider_metadata_hash": canonical_payload_hash({}),
        "http_status": None,
        "raw_response": None,
        "raw_response_hash": None,
        "parsed_response": None,
        "parsed_response_hash": None,
        "usage": {},
        "usage_hash": canonical_payload_hash({}),
        "finish_reason": None,
        "error": None,
        "finished_at": None,
    }
    pending = GenerationAttempt(status=EventStatus.PENDING, started_at=None, **base)
    in_progress = GenerationAttempt(status=EventStatus.IN_PROGRESS, started_at=NOW, **base)
    authorization = AttemptAuthorization(
        run_id=run_id,
        event_id=event_id,
        event_ordinal=ordinal,
        attempt_index=attempt_index,
        model_seed=model_seed,
        model_identity=adapter_binding.model_identity,
        model_identity_hash=adapter_binding.model_identity_hash,
        request_parameters={"temperature": 0.0},
        request_parameters_hash=canonical_payload_hash({"temperature": 0.0}),
        resume_authorization_hash=None,
        mock_only=True,
    )
    return _EvidenceContractFixture(authorization, request, pending, in_progress)


def create_evidence_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    **kwargs: object,
) -> tuple[RunStorage, dict[str, object]]:
    """Use the storage fixture builder while preserving explicit engine lease ownership."""

    original = RunStorage.create.__func__
    with monkeypatch.context() as lease_patch:

        def create_with_lease(
            cls: type[RunStorage], *args: object, **create_kwargs: object
        ) -> RunStorage:
            store = original(cls, *args, **create_kwargs)
            store.acquire_run_lease().acquire()
            return store

        lease_patch.setattr(RunStorage, "create", classmethod(create_with_lease))
        store, values = prepared_evidence_bundle(tmp_path, **kwargs)
    owned = store._owned_lease
    assert owned is not None
    owned.release()
    return store, values


def reopen_store(store: RunStorage, values: Mapping[str, object]) -> RunStorage:
    store.close()
    return RunStorage.open(
        values["path"],
        manifest=values["manifest"],
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=values["expected_agent_ids"],
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )


def prepared_event(
    values: Mapping[str, object],
    *,
    pending: GenerationAttempt | None = None,
    request_evidence: AdapterRequestEvidence | None = None,
    resume_hash: str | None = None,
) -> PreparedAttempt:
    pending_value = values["pending"] if pending is None else pending
    request_value = values["request_evidence"] if request_evidence is None else request_evidence
    assert isinstance(pending_value, GenerationAttempt)
    assert isinstance(request_value, AdapterRequestEvidence)
    run_manifest = values["manifest"]
    return PreparedAttempt(
        authorization=AttemptAuthorization(
            run_id=run_manifest.run_id,
            event_id=pending_value.event_id,
            event_ordinal=0,
            attempt_index=pending_value.attempt_index,
            model_seed=request_value.model_seed,
            model_identity=request_value.model_identity,
            model_identity_hash=request_value.model_identity_hash,
            request_parameters=request_value.request_parameters,
            request_parameters_hash=request_value.request_parameters_hash,
            resume_authorization_hash=resume_hash,
            mock_only=True,
        ),
        request=request_value.request,
        pending_attempt=pending_value,
        in_progress_attempt=attempt_transition(pending_value, EventStatus.IN_PROGRESS),
        context_provenance={"phase": "4B-8C-3", "evidence_pipeline": True},
        event_input=values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=request_value,
    )


def invoke(value: PreparedAttempt, adapter: MockAdapter) -> AttemptInvocationResult:
    response = adapter.generate(value.request)
    assert value.in_progress_attempt.started_at is not None
    return AttemptInvocationResult(
        response=response,
        evidence=AttemptExecutionEvidence(
            started_at=value.in_progress_attempt.started_at,
            finished_at=NOW,
            http_status=200,
            provider_metadata={
                "adapter_response_id": response.response_id,
                "adapter_response_hash": response.record_hash,
                "adapter_outcome": response.outcome,
                "adapter_error": None if response.error is None else dict(response.error),
                "runtime_identity": dict(response.runtime_identity),
                "runtime_identity_hash": response.runtime_identity_hash,
                "script_hash": response.script_hash,
            },
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            finish_reason="stop",
        ),
    )


def persisted_from_result(
    value: PreparedAttempt, result: AttemptInvocationResult
) -> PersistedInvocationEvidence:
    execution = result.evidence
    return PersistedInvocationEvidence.create(
        response=result.response,
        execution_payload={
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
            "http_status": execution.http_status,
            "provider_metadata": dict(execution.provider_metadata),
            "usage": dict(execution.usage),
            "finish_reason": execution.finish_reason,
        },
        request_hash=value.request_evidence.request_hash,
        parser_limits_hash=value.request_evidence.parser_limits_hash,
        attempt_policy_hash=value.request_evidence.attempt_policy_hash,
        adapter_execution_binding_hash=value.request_evidence.adapter_execution_binding_hash,
    )


def finalize(
    store: RunStorage,
    values: Mapping[str, object],
    value: PreparedAttempt,
    result: AttemptInvocationResult,
) -> FinalizedAttemptEvidence:
    scoped = {
        **values,
        "pending": value.pending_attempt,
        "request_evidence": value.request_evidence,
    }
    return finalized_evidence(store, scoped, persisted_from_result(value, result))


def commit_for(
    store: RunStorage, values: Mapping[str, object], terminal: GenerationAttempt
) -> SuccessfulEventCommit:
    run_manifest = values["manifest"]
    ordinal = store.progress.next_event_ordinal
    agent_id = run_manifest.schedule.slots[ordinal].agent_id
    previous_state = store.private_state(agent_id)
    previous_cursor = store.feed_cursor(agent_id)
    previous_pointer = store.latest_public_pointer(agent_id)
    assert isinstance(previous_state, PrivateState)
    assert previous_cursor is not None
    parsed = terminal.parsed_response
    assert parsed is not None
    update = PrivateUpdate.create(
        topic_package=prompt_topic(),
        matched_seed=previous_state.matched_seed,
        agent_id=agent_id,
        event_id=terminal.event_id,
        event_ordinal=ordinal,
        sequence_index=previous_state.successful_update_count,
        stance_label=parsed["stance"],
        reason=parsed["public_reason"],
        confidence=parsed["confidence"],
        published=run_manifest.schedule.slots[ordinal].publish_flag,
        source_attempt_id=terminal.attempt_id,
        mock_only=True,
    )
    state = PrivateState.from_update(update, previous=previous_state, mock_only=True)
    cursor = previous_cursor.advance(ordinal)
    post = PublicPost.from_private_update(update, mock_only=True) if update.published else None
    pointer = (
        LatestPublicPointer.from_post(post, previous=previous_pointer, mock_only=True)
        if post is not None
        else None
    )
    return SuccessfulEventCommit(
        successful_event(run_manifest, ordinal=ordinal, attempt_count=terminal.attempt_index),
        update,
        state,
        cursor,
        post,
        pointer,
    )


def seed_prepared(store: RunStorage, value: PreparedAttempt) -> None:
    with store.acquire_run_lease():
        store.record_prepared_attempt(
            value.event_input,
            policy=value.policy,
            adapter_binding=value.adapter_binding,
            request_evidence=value.request_evidence,
            pending_attempt=value.pending_attempt,
        )


def seed_in_progress(store: RunStorage, value: PreparedAttempt) -> None:
    with store.acquire_run_lease():
        store.record_prepared_attempt(
            value.event_input,
            policy=value.policy,
            adapter_binding=value.adapter_binding,
            request_evidence=value.request_evidence,
            pending_attempt=value.pending_attempt,
        )
        store.append_attempt(value.in_progress_attempt)


def retry_prepared(
    values: Mapping[str, object], authorization_hash: str
) -> tuple[PreparedAttempt, dict[str, object]]:
    event_input = values["event_input"]
    policy = values["policy"]
    binding = values["binding"]
    first_pending = values["pending"]
    request = AdapterRequest.create(
        prompt_view=event_input.prompt_view,
        attempt_index=2,
        mock_seed=12345,
        mock_only=True,
    )
    request_evidence = AdapterRequestEvidence.create(
        request=request,
        model_identity=binding.model_identity,
        request_parameters={"temperature": 0.0},
        model_seed=12345,
        prompt_limits_hash=event_input.prompt_view.limits_hash,
        parser_limits_hash=event_input.parser_limits.record_hash,
        attempt_policy_hash=policy.record_hash,
        adapter_execution_binding_hash=binding.record_hash,
    )
    payload = first_pending.to_payload()
    payload.update(
        {
            "attempt_id": request.attempt_id,
            "attempt_index": 2,
            "request_id": request.request_id,
            "model_seed": request.mock_seed,
        }
    )
    pending = GenerationAttempt.from_payload(payload)
    scoped = {**values, "pending": pending, "request_evidence": request_evidence}
    return prepared_event(
        scoped,
        pending=pending,
        request_evidence=request_evidence,
        resume_hash=authorization_hash,
    ), scoped


def test_lifecycle_kernel_public_types_are_importable() -> None:
    assert agent_ex.StrictSerialLifecycleEngine is StrictSerialLifecycleEngine
    assert agent_ex.AttemptLifecycleFailure is AttemptLifecycleFailure
    with pytest.raises(ValueError, match="unsupported"):
        AttemptOutcome("landed", None, None, False)


def test_new_attempt_persists_complete_evidence_and_commits_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    calls = {"prepare": 0, "invoke": 0, "finalize": 0, "commit": 0}

    def prepare_once(_journal: object) -> PreparedAttempt:
        calls["prepare"] += 1
        return value

    def invoke_once(_request: AdapterRequest) -> AttemptInvocationResult:
        calls["invoke"] += 1
        return invoke(value, values["adapter"])

    def finalize_once(
        item: PreparedAttempt, result: AttemptInvocationResult
    ) -> FinalizedAttemptEvidence:
        calls["finalize"] += 1
        return finalize(store, values, item, result)

    def commit_once(terminal: GenerationAttempt) -> SuccessfulEventCommit:
        calls["commit"] += 1
        return commit_for(store, values, terminal)

    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=prepare_once,
            invoke=invoke_once,
            finalize=finalize_once,
            build_commit=commit_once,
        )

    assert outcome.state == "committed"
    assert outcome.adapter_invoked is True
    assert calls == {"prepare": 1, "invoke": 1, "finalize": 1, "commit": 1}
    references = store.evidence_references(value.authorization.event_id)
    assert references.event_input_evidence_id == value.event_input.evidence_id
    assert references.request_id == value.request.request_id
    assert references.invocation_evidence_id is not None
    assert references.parse_evidence_id is not None
    assert references.terminal_attempt_id == value.pending_attempt.attempt_id
    assert references.committed_event_id == value.authorization.event_id
    store.assert_complete()
    store.close()


def test_pending_prefix_reopens_with_same_identity_and_invokes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    seed_prepared(store, value)
    store = reopen_store(store, values)
    calls = 0

    def invoke_once(_request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal calls
        calls += 1
        return invoke(value, values["adapter"])

    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=invoke_once,
            finalize=lambda item, result: finalize(store, values, item, result),
            build_commit=lambda terminal: commit_for(store, values, terminal),
        )

    assert outcome.state == "committed"
    assert calls == 1
    assert outcome.attempt is not None
    assert outcome.attempt.event_id == value.authorization.event_id
    assert outcome.attempt.attempt_id == value.pending_attempt.attempt_id
    store.close()


def test_pending_recovery_rejects_transition_drift_before_invoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    seed_prepared(store, value)
    store = reopen_store(store, values)
    drifted_pending = replace(value.pending_attempt, exposure_id="drifted-exposure")
    drifted = replace(
        value,
        pending_attempt=drifted_pending,
        in_progress_attempt=attempt_transition(drifted_pending, EventStatus.IN_PROGRESS),
    )
    invoke_calls = 0

    def forbidden(_request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal invoke_calls
        invoke_calls += 1
        raise AssertionError("drifted pending prefix invoked")

    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="pending recovery requires the exact transition"):
            engine.execute(
                prepare=lambda _journal: drifted,
                invoke=forbidden,
                finalize=lambda _item, _result: pytest.fail("unexpected finalize"),
                build_commit=lambda _terminal: pytest.fail("unexpected commit"),
            )
    assert invoke_calls == 0
    assert store.current_event_journal().latest_transition == value.pending_attempt
    store.close()


def test_in_progress_without_invocation_blocks_blind_resend_and_preserves_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    seed_in_progress(store, value)
    store = reopen_store(store, values)
    before = (
        store.progress,
        store.private_state("agent-0001"),
        store.feed_cursor("agent-0001"),
        store.latest_public_pointer("agent-0001"),
    )
    invoke_calls = 0

    def forbidden(_request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal invoke_calls
        invoke_calls += 1
        raise AssertionError("blind resend")

    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(RuntimeError, match="provider reconciliation"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=forbidden,
                finalize=lambda _item, _result: pytest.fail("unexpected finalize"),
                build_commit=lambda _terminal: pytest.fail("unexpected commit"),
            )

    assert invoke_calls == 0
    assert store.invocation_evidence(value.request.attempt_id) is None
    assert store.current_event_journal().latest_transition == value.in_progress_attempt
    assert before == (
        store.progress,
        store.private_state("agent-0001"),
        store.feed_cursor("agent-0001"),
        store.latest_public_pointer("agent-0001"),
    )
    store.close()


def test_explicit_reconciliation_is_persisted_before_finalize_without_invoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    reconciled = invoke(value, values["adapter"])
    seed_in_progress(store, value)
    store = reopen_store(store, values)

    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: pytest.fail("reconciliation resent request"),
            finalize=lambda item, result: finalize(store, values, item, result),
            build_commit=lambda terminal: commit_for(store, values, terminal),
            reconciliation=reconciled,
        )

    assert outcome.state == "committed"
    assert outcome.adapter_invoked is False
    assert store.evidence_references(value.authorization.event_id).invocation_evidence_id
    store.close()


def test_invocation_landed_recovery_finalizes_and_commits_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    with store.acquire_run_lease():
        store.record_prepared_attempt(
            value.event_input,
            policy=value.policy,
            adapter_binding=value.adapter_binding,
            request_evidence=value.request_evidence,
            pending_attempt=value.pending_attempt,
        )
        store.append_attempt(value.in_progress_attempt)
        landed = persisted_invocation(values)
        store.record_invocation_evidence(landed)
    store = reopen_store(store, values)
    generate_calls = 0

    def forbidden_generate(_request: AdapterRequest) -> object:
        nonlocal generate_calls
        generate_calls += 1
        raise AssertionError("persisted invocation recovery resent the adapter request")

    monkeypatch.setattr(values["adapter"], "generate", forbidden_generate)
    finalize_calls = 0

    def finalize_landed(
        item: PreparedAttempt, result: AttemptInvocationResult
    ) -> FinalizedAttemptEvidence:
        nonlocal finalize_calls
        finalize_calls += 1
        assert result.response.record_hash == landed.response_hash
        return finalize(store, values, item, result)

    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: pytest.fail("persisted invocation was resent"),
            finalize=finalize_landed,
            build_commit=lambda terminal: commit_for(store, values, terminal),
        )

    assert outcome.state == "committed"
    assert outcome.adapter_invoked is False
    assert generate_calls == 0
    assert finalize_calls == 1
    store.close()


def test_invoke_exception_leaves_only_in_progress_prefix_and_research_state_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    before = (
        store.progress,
        store.private_state("agent-0001"),
        store.feed_cursor("agent-0001"),
        store.latest_public_pointer("agent-0001"),
    )

    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(RuntimeError, match="provider crashed"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=lambda _request: (_ for _ in ()).throw(RuntimeError("provider crashed")),
                finalize=lambda _item, _result: pytest.fail("unexpected finalize"),
                build_commit=lambda _terminal: pytest.fail("unexpected commit"),
            )

    assert store.current_event_journal().latest_transition == value.in_progress_attempt
    assert store.invocation_evidence(value.request.attempt_id) is None
    assert before == (
        store.progress,
        store.private_state("agent-0001"),
        store.feed_cursor("agent-0001"),
        store.latest_public_pointer("agent-0001"),
    )
    store.close()


def test_finalize_exception_reopens_from_invocation_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(RuntimeError, match="parser crashed"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=lambda _request: invoke(value, values["adapter"]),
                finalize=lambda _item, _result: (_ for _ in ()).throw(
                    RuntimeError("parser crashed")
                ),
                build_commit=lambda _terminal: pytest.fail("unexpected commit"),
            )
    assert store.invocation_evidence(value.request.attempt_id) is not None
    assert store.parse_evidence(value.request.attempt_id) is None
    store = reopen_store(store, values)
    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: pytest.fail("invocation-landed prefix resent"),
            finalize=lambda item, result: finalize(store, values, item, result),
            build_commit=lambda terminal: commit_for(store, values, terminal),
        )
    assert outcome.state == "committed"
    assert outcome.adapter_invoked is False
    store.close()


def test_failed_finalization_persists_parse_terminal_and_failure_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(
        tmp_path,
        monkeypatch,
        script_step=MockScriptStep.malformed("not-json"),
        single_event=True,
    )
    value = prepared_event(values)
    before = (
        store.progress,
        store.private_state("agent-0001"),
        store.feed_cursor("agent-0001"),
        store.latest_public_pointer("agent-0001"),
    )
    calls = {"invoke": 0, "finalize": 0}

    def invoke_once(_request: AdapterRequest) -> AttemptInvocationResult:
        calls["invoke"] += 1
        return invoke(value, values["adapter"])

    def fail_typed(
        item: PreparedAttempt, result: AttemptInvocationResult
    ) -> FinalizedAttemptEvidence:
        calls["finalize"] += 1
        raise AttemptLifecycleFailure(finalize(store, values, item, result))

    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=invoke_once,
            finalize=fail_typed,
            build_commit=lambda _terminal: pytest.fail("FAILED attempt was committed"),
        )

    attempt_id = value.pending_attempt.attempt_id
    parsed = store.parse_evidence(attempt_id)
    terminal = store.current_event_journal().latest_transition
    failure = store.terminal_failure_evidence()
    assert outcome.state == "failed"
    assert parsed is not None and parsed.parsed is None
    assert terminal is not None and terminal.status is EventStatus.FAILED
    assert failure is not None and failure.attempt_id == attempt_id
    assert calls == {"invoke": 1, "finalize": 1}
    assert before == (
        store.progress,
        store.private_state("agent-0001"),
        store.feed_cursor("agent-0001"),
        store.latest_public_pointer("agent-0001"),
    )
    store.close()


def test_failed_prefix_blocks_callbacks_until_exact_retry_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(
        tmp_path,
        monkeypatch,
        script_steps=(
            MockScriptStep.malformed("not-json"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "retry"}
            ),
        ),
        single_event=True,
    )
    first = prepared_event(values)
    with StrictSerialLifecycleEngine(store) as engine:
        failed = engine.execute(
            prepare=lambda _journal: first,
            invoke=lambda _request: invoke(first, values["adapter"]),
            finalize=lambda item, result: finalize(store, values, item, result),
            build_commit=lambda _terminal: pytest.fail("FAILED attempt was committed"),
        )
    assert failed.state == "failed"
    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(RuntimeError, match="external authorization"):
            engine.execute(
                prepare=lambda _journal: pytest.fail("failed prefix prepared retry"),
                invoke=lambda _request: pytest.fail("failed prefix invoked"),
                finalize=lambda _item, _result: pytest.fail("failed prefix finalized"),
                build_commit=lambda _terminal: pytest.fail("failed prefix committed"),
            )
    failure = store.terminal_failure_evidence()
    assert failure is not None
    with store.acquire_run_lease():
        authorization = store.authorize_resume(
            authorization_id="resume-engine-v6",
            event_id=first.authorization.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id=values["policy"].policy_id,
            policy_evidence_hash=values["policy"].record_hash,
            authorized_at=NOW,
        )
    store = reopen_store(store, values)
    wrong, _ = retry_prepared(values, "f" * 64)
    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="exact resume"):
            engine.execute(
                prepare=lambda _journal: wrong,
                invoke=lambda _request: pytest.fail("wrong authorization invoked"),
                finalize=lambda _item, _result: pytest.fail("wrong authorization finalized"),
                build_commit=lambda _terminal: pytest.fail("wrong authorization committed"),
            )
    assert store.adapter_request_evidence(wrong.request.attempt_id) is None
    second, retry_values = retry_prepared(values, authorization.payload_hash)
    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: second,
            invoke=lambda _request: invoke(second, values["adapter"]),
            finalize=lambda item, result: finalize(store, retry_values, item, result),
            build_commit=lambda terminal: commit_for(store, values, terminal),
        )
    assert outcome.state == "committed"
    assert outcome.attempt is not None and outcome.attempt.attempt_index == 2
    assert outcome.attempt.event_id == first.authorization.event_id
    assert store.event_input_evidence(first.authorization.event_id) == first.event_input
    store.close()


def test_landed_success_recovery_only_rebuilds_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(RuntimeError, match="commit crashed"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=lambda _request: invoke(value, values["adapter"]),
                finalize=lambda item, result: finalize(store, values, item, result),
                build_commit=lambda _terminal: (_ for _ in ()).throw(
                    RuntimeError("commit crashed")
                ),
            )
    assert store.current_event_journal().resume_state == (
        "succeeded_attempt_requires_atomic_commit"
    )
    store = reopen_store(store, values)
    commit_calls = 0

    def commit_once(terminal: GenerationAttempt) -> SuccessfulEventCommit:
        nonlocal commit_calls
        commit_calls += 1
        return commit_for(store, values, terminal)

    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: pytest.fail("landed success prepared"),
            invoke=lambda _request: pytest.fail("landed success invoked"),
            finalize=lambda _item, _result: pytest.fail("landed success finalized"),
            build_commit=commit_once,
        )
    assert outcome.state == "committed"
    assert outcome.adapter_invoked is False
    assert commit_calls == 1
    store.close()


def test_foreign_authorization_and_reconciliation_outside_in_progress_do_not_mutate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    foreign_run = "foreign-run"
    foreign = replace(
        value,
        authorization=replace(
            value.authorization,
            run_id=foreign_run,
            event_id=derive_event_id(foreign_run, 0),
        ),
    )
    result = invoke(value, values["adapter"])
    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="reconciliation"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=lambda _request: pytest.fail("misplaced reconciliation invoked"),
                finalize=lambda _item, _result: pytest.fail("unexpected finalize"),
                build_commit=lambda _terminal: pytest.fail("unexpected commit"),
                reconciliation=result,
            )
        with pytest.raises(ValueError, match="exact current"):
            engine.execute(
                prepare=lambda _journal: foreign,
                invoke=lambda _request: pytest.fail("foreign authorization invoked"),
                finalize=lambda _item, _result: pytest.fail("unexpected finalize"),
                build_commit=lambda _terminal: pytest.fail("unexpected commit"),
            )
    assert store.current_event_journal().latest_transition is None
    assert store.evidence_references(value.authorization.event_id).request_id is None
    store.close()


def test_complete_is_noop_and_full_integrity_replay_is_not_per_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    original = store.verify_integrity
    integrity_calls = 0

    def counted() -> None:
        nonlocal integrity_calls
        integrity_calls += 1
        original()

    monkeypatch.setattr(store, "verify_integrity", counted)
    checkpoint_path = tmp_path / "run.checkpoint.json"
    with StrictSerialLifecycleEngine(store) as engine:
        engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: invoke(value, values["adapter"]),
            finalize=lambda item, result: finalize(store, values, item, result),
            build_commit=lambda terminal: commit_for(store, values, terminal),
        )
        assert integrity_calls == 1
        written_hash = engine.write_checkpoint(checkpoint_path)
        assert integrity_calls == 2
    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: pytest.fail("complete run prepared"),
            invoke=lambda _request: pytest.fail("complete run invoked"),
            finalize=lambda _item, _result: pytest.fail("complete run finalized"),
            build_commit=lambda _terminal: pytest.fail("complete run committed"),
        )
        assert integrity_calls == 3
    assert outcome == AttemptOutcome("complete", None, None, False)
    checkpoint = load_checkpoint(checkpoint_path)
    assert checkpoint.checkpoint_hash == written_hash
    assert validate_checkpoint(checkpoint, store) == "current"
    store.close()


def test_second_engine_is_rejected_until_lease_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    first = StrictSerialLifecycleEngine(store)
    second = StrictSerialLifecycleEngine(store)
    with first:
        with pytest.raises(RuntimeError, match="lease|owned"):
            second.__enter__()
    with second:
        pass
    store.close()


def test_lease_loss_during_prepare_fails_before_any_evidence_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    engine = StrictSerialLifecycleEngine(store)
    with engine:

        def lose_lease(_journal: object) -> PreparedAttempt:
            engine.close()
            return value

        with pytest.raises(RuntimeError, match="lease"):
            engine.execute(
                prepare=lose_lease,
                invoke=lambda _request: pytest.fail("lease loss invoked"),
                finalize=lambda _item, _result: pytest.fail("lease loss finalized"),
                build_commit=lambda _terminal: pytest.fail("lease loss committed"),
            )
    references = store.evidence_references(value.authorization.event_id)
    assert references.event_input_evidence_id is None
    assert references.request_id is None
    assert store.current_event_journal().latest_transition is None
    store.close()


def test_checkpoint_write_failure_preserves_prior_stale_rebuildable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = create_evidence_bundle(tmp_path, monkeypatch, single_event=True)
    value = prepared_event(values)
    checkpoint_path = tmp_path / "run.checkpoint.json"
    with StrictSerialLifecycleEngine(store) as engine:
        engine.write_checkpoint(checkpoint_path)
        old_bytes = checkpoint_path.read_bytes()
        engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: invoke(value, values["adapter"]),
            finalize=lambda item, result: finalize(store, values, item, result),
            build_commit=lambda terminal: commit_for(store, values, terminal),
        )
        monkeypatch.setattr(
            engine_module,
            "write_checkpoint_atomic",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("atomic write fault")),
        )
        with pytest.raises(OSError, match="atomic write fault"):
            engine.write_checkpoint(checkpoint_path)
    assert checkpoint_path.read_bytes() == old_bytes
    assert validate_checkpoint(load_checkpoint(checkpoint_path), store) == "stale"
    store.close()


def test_nested_authorization_and_execution_inputs_are_recursively_frozen() -> None:
    model = {"model": "mock", "nested": {"tags": ["a", "b"]}}
    parameters = {"sampling": {"stops": ["END"]}}
    authorization = AttemptAuthorization(
        run_id="run-freeze",
        event_id=derive_event_id("run-freeze", 0),
        event_ordinal=0,
        attempt_index=1,
        model_seed=7,
        model_identity=model,
        model_identity_hash=canonical_payload_hash(model),
        request_parameters=parameters,
        request_parameters_hash=canonical_payload_hash(parameters),
        resume_authorization_hash=None,
        mock_only=True,
    )
    source = {"nested": {"ids": ["provider-1"]}}
    evidence = AttemptExecutionEvidence(
        started_at=NOW,
        finished_at=NOW,
        http_status=200,
        provider_metadata=source,
        usage={"nested": {"counts": [1, 2]}},
        finish_reason="stop",
    )
    model["nested"]["tags"].append("mutated")
    parameters["sampling"]["stops"].append("mutated")
    source["nested"]["ids"].append("mutated")
    assert authorization.model_identity["nested"]["tags"] == ("a", "b")
    assert authorization.request_parameters["sampling"]["stops"] == ("END",)
    assert evidence.provider_metadata["nested"]["ids"] == ("provider-1",)
