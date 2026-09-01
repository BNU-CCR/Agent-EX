from __future__ import annotations

import json
from pathlib import Path

import pytest
import agent_ex.engine as engine_module
import agent_ex

from agent_ex.adapters.base import (
    AdapterRequest,
    _derive_request_id,
    _issue_request_seal,
)
from agent_ex.adapters.mock import MockAdapter, MockScriptStep
from agent_ex.domain import (
    EventStatus,
    GenerationAttempt,
    _json_ready,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
)
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
from agent_ex.storage import RunStorage
from agent_ex.checkpoint import load_checkpoint, validate_checkpoint
from test_storage import (
    expected_agent_ids,
    initial_records,
    manifest,
    schedule,
    seal_expected_initial_state,
    successful_event,
    successful_state_records,
)


NOW = "2026-09-01T00:00:00+00:00"
MODEL_IDENTITY = {
    "model": "deterministic-mock-model",
    "revision": "phase4b7-script-v1",
    "mode": "script_only_no_generation",
}
REQUEST_PARAMETERS = {"temperature": 0.0}


def create_store(
    path: Path, *, publish_flags: tuple[bool, ...] = (False,)
) -> tuple[RunStorage, object]:
    run_manifest = manifest(schedule(publish_flags=publish_flags))
    store = RunStorage.create(
        path,
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    with store.acquire_run_lease():
        for agent_id in expected_agent_ids(run_manifest):
            store.initialize_agent(*initial_records(agent_id))
        seal_expected_initial_state(store, run_manifest)
    return store, run_manifest


def sealed_request(event_id: str, attempt_index: int, model_seed: int) -> AdapterRequest:
    messages = ({"role": "user", "content": "mock lifecycle request"},)
    messages_hash = canonical_payload_hash(messages)
    topic_hash = "d" * 64
    prompt_hash = "e" * 64
    request_id = _derive_request_id(
        event_id=event_id,
        topic_package_id="mock-topic",
        topic_package_hash=topic_hash,
        attempt_index=attempt_index,
        prompt_view_id="prompt-view-engine",
        prompt_view_hash=prompt_hash,
        rendered_messages_hash=messages_hash,
        mock_seed=model_seed,
    )
    values = {
        "request_id": request_id,
        "event_id": event_id,
        "topic_package_id": "mock-topic",
        "topic_package_hash": topic_hash,
        "attempt_index": attempt_index,
        "attempt_id": derive_attempt_id(event_id, attempt_index),
        "prompt_view_id": "prompt-view-engine",
        "prompt_view_hash": prompt_hash,
        "rendered_messages": messages,
        "rendered_messages_hash": messages_hash,
        "mock_seed": model_seed,
    }
    content = {
        "schema_version": "paper1.mock-adapter-request.v1",
        **values,
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    record_hash = canonical_payload_hash(content)
    return AdapterRequest(
        **values,
        record_hash=record_hash,
        _factory_seal=_issue_request_seal(record_hash),
    )


def prepared(
    run_id: str,
    *,
    ordinal: int = 0,
    attempt_index: int = 1,
    resume_hash: str | None = None,
) -> PreparedAttempt:
    event_id = derive_event_id(run_id, ordinal)
    model_seed = 12345
    request = sealed_request(event_id, attempt_index, model_seed)
    base = {
        "attempt_id": request.attempt_id,
        "event_id": event_id,
        "attempt_index": attempt_index,
        "request_id": request.request_id,
        "exposure_id": f"exposure-{ordinal}",
        "rendered_messages": request.rendered_messages,
        "rendered_prompt_hash": request.rendered_messages_hash,
        "request_parameters": REQUEST_PARAMETERS,
        "request_parameters_hash": canonical_payload_hash(REQUEST_PARAMETERS),
        "model_identity": MODEL_IDENTITY,
        "model_identity_hash": canonical_payload_hash(MODEL_IDENTITY),
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
    return PreparedAttempt(
        authorization=AttemptAuthorization(
            run_id=run_id,
            event_id=event_id,
            event_ordinal=ordinal,
            attempt_index=attempt_index,
            model_seed=model_seed,
            model_identity=MODEL_IDENTITY,
            model_identity_hash=canonical_payload_hash(MODEL_IDENTITY),
            request_parameters=REQUEST_PARAMETERS,
            request_parameters_hash=canonical_payload_hash(REQUEST_PARAMETERS),
            resume_authorization_hash=resume_hash,
            mock_only=True,
        ),
        request=request,
        pending_attempt=pending,
        in_progress_attempt=in_progress,
        context_provenance={"phase": "4B-8C-2", "future_c3_persistence": True},
    )


def adapter_for(
    event_id: str, *, reason: str = "reason-0-1", attempt_index: int = 1
) -> MockAdapter:
    steps = tuple(
        MockScriptStep.success(
            {
                "stance": "neutral",
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


def invocation(value: PreparedAttempt, adapter: MockAdapter) -> AttemptInvocationResult:
    response = adapter.generate(value.request)
    return AttemptInvocationResult(
        response=response,
        evidence=AttemptExecutionEvidence(
            started_at=NOW,
            finished_at=NOW,
            http_status=200,
            provider_metadata=response_metadata(response),
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            finish_reason="stop",
        ),
    )


def timeout_invocation(value: PreparedAttempt) -> AttemptInvocationResult:
    adapter = MockAdapter(
        script={value.authorization.event_id: (MockScriptStep.timeout("provider timeout"),)},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    response = adapter.generate(value.request)
    return AttemptInvocationResult(
        response=response,
        evidence=AttemptExecutionEvidence(
            started_at=NOW,
            finished_at=NOW,
            http_status=200,
            provider_metadata=response_metadata(response),
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            finish_reason="stop",
        ),
    )


def finalize(value: PreparedAttempt, result: AttemptInvocationResult) -> GenerationAttempt:
    raw = result.response.raw_response
    assert raw is not None
    parsed = json.loads(raw)
    evidence = result.evidence
    payload = value.in_progress_attempt.to_payload()
    payload.update(
        {
            "status": "succeeded",
            "provider_request_id": result.response.provider_request_id,
            "provider_metadata": _json_ready(evidence.provider_metadata),
            "provider_metadata_hash": canonical_payload_hash(evidence.provider_metadata),
            "http_status": evidence.http_status,
            "raw_response": raw,
            "raw_response_hash": canonical_payload_hash(raw),
            "parsed_response": parsed,
            "parsed_response_hash": canonical_payload_hash(parsed),
            "usage": _json_ready(evidence.usage),
            "usage_hash": canonical_payload_hash(evidence.usage),
            "finish_reason": evidence.finish_reason,
            "error": None,
            "finished_at": evidence.finished_at,
        }
    )
    return GenerationAttempt.from_payload(payload)


def failed_attempt(
    value: PreparedAttempt,
    *,
    code: str = "mock_failure",
    result: AttemptInvocationResult | None = None,
) -> GenerationAttempt:
    payload = value.in_progress_attempt.to_payload()
    payload.update(
        {
            "status": "failed",
            "provider_request_id": (
                "provider-failed" if result is None else result.response.provider_request_id
            ),
            "provider_metadata": (
                {"provider": "deterministic-mock"}
                if result is None
                else _json_ready(result.evidence.provider_metadata)
            ),
            "provider_metadata_hash": canonical_payload_hash(
                {"provider": "deterministic-mock"}
                if result is None
                else result.evidence.provider_metadata
            ),
            "http_status": 500 if result is None else result.evidence.http_status,
            "raw_response": None if result is None else result.response.raw_response,
            "raw_response_hash": None if result is None else result.response.raw_response_hash,
            "parsed_response": None,
            "parsed_response_hash": None,
            "usage": {} if result is None else _json_ready(result.evidence.usage),
            "usage_hash": canonical_payload_hash({} if result is None else result.evidence.usage),
            "finish_reason": None if result is None else result.evidence.finish_reason,
            "error": {"code": code},
            "finished_at": NOW if result is None else result.evidence.finished_at,
        }
    )
    return GenerationAttempt.from_payload(payload)


def commit_for(store: RunStorage, run_manifest: object, terminal: GenerationAttempt):
    ordinal = store.progress.next_event_ordinal
    agent_id = run_manifest.schedule.slots[ordinal].agent_id
    records = successful_state_records(
        run_manifest,
        ordinal=ordinal,
        previous_state=store.private_state(agent_id),
        previous_cursor=store.feed_cursor(agent_id),
        previous_pointer=store.latest_public_pointer(agent_id),
        attempt_index=terminal.attempt_index,
    )
    return SuccessfulEventCommit(
        event=successful_event(run_manifest, ordinal=ordinal, attempt_count=terminal.attempt_index),
        private_update=records[0],
        private_state=records[1],
        feed_cursor=records[2],
        public_post=records[3],
        latest_public_pointer=records[4],
    )


def test_lifecycle_kernel_public_types_are_importable() -> None:
    assert AttemptAuthorization
    assert AttemptExecutionEvidence
    assert AttemptInvocationResult
    assert AttemptOutcome
    assert PreparedAttempt
    assert SuccessfulEventCommit
    assert StrictSerialLifecycleEngine
    assert agent_ex.StrictSerialLifecycleEngine is StrictSerialLifecycleEngine
    assert agent_ex.AttemptLifecycleFailure is AttemptLifecycleFailure


def test_attempt_outcome_rejects_unused_landed_state() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        AttemptOutcome("landed", None, None, False)


def test_new_attempt_runs_pending_in_progress_success_and_atomic_commit(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "run.sqlite3")
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    calls = 0

    def invoke(request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal calls
        calls += 1
        assert request is value.request
        return invocation(value, adapter)

    def commit(terminal: GenerationAttempt) -> SuccessfulEventCommit:
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=store.private_state("agent-0"),
            previous_cursor=store.feed_cursor("agent-0"),
            previous_pointer=store.latest_public_pointer("agent-0"),
        )
        return SuccessfulEventCommit(
            event=successful_event(run_manifest, ordinal=0),
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )

    with store, StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=invoke,
            finalize=finalize,
            build_commit=commit,
        )
        assert outcome.state == "committed"
        assert outcome.adapter_invoked is True
        assert calls == 1
        assert [item.status for item in store.attempt_transitions(value.request.attempt_id)] == [
            EventStatus.PENDING,
            EventStatus.IN_PROGRESS,
            EventStatus.SUCCEEDED,
        ]
        store.assert_complete()


def test_typed_invocation_failure_lands_failed_attempt_without_state_mutation(
    tmp_path: Path,
) -> None:
    store, run_manifest = create_store(tmp_path / "failed.sqlite3")
    value = prepared(run_manifest.run_id)
    before = store.recovery_evidence()
    with store, StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: (_ for _ in ()).throw(
                AttemptLifecycleFailure(failed_attempt(value))
            ),
            finalize=finalize,
            build_commit=lambda _terminal: (_ for _ in ()).throw(
                AssertionError("failed attempt must not build commit")
            ),
        )
        assert outcome.state == "failed"
        assert outcome.adapter_invoked is True
        after = store.recovery_evidence()
        for key in (
            "next_event_ordinal",
            "event_chain_head",
            "private_states",
            "public_stock",
            "latest_public_pointers",
            "feed_cursors",
        ):
            assert after[key] == before[key]
        assert store.current_event_journal().resume_state == (
            "failed_attempt_requires_external_authorization"
        )


def test_in_progress_recovery_requires_reconciliation_and_never_blindly_invokes(
    tmp_path: Path,
) -> None:
    store, run_manifest = create_store(tmp_path / "in-progress.sqlite3")
    value = prepared(run_manifest.run_id)
    with store.acquire_run_lease():
        store.append_attempt(value.pending_attempt)
        store.append_attempt(value.in_progress_attempt)
    calls = 0

    def forbidden(_request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal calls
        calls += 1
        raise AssertionError("in-progress recovery must not invoke")

    with store, StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(RuntimeError, match="reconciliation"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=forbidden,
                finalize=finalize,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )
        assert calls == 0
        assert store.current_event_journal().latest_transition == value.in_progress_attempt


def test_pending_recovery_rejects_request_hash_drift_before_invoke(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "pending.sqlite3")
    value = prepared(run_manifest.run_id)
    with store.acquire_run_lease():
        store.append_attempt(value.pending_attempt)
    drifted = prepared(run_manifest.run_id)
    payload = drifted.pending_attempt.to_payload()
    payload["request_id"] = "request-drifted"
    drifted_pending = GenerationAttempt.from_payload(payload)
    drifted_value = PreparedAttempt(
        authorization=drifted.authorization,
        request=drifted.request,
        pending_attempt=drifted_pending,
        in_progress_attempt=drifted.in_progress_attempt,
        context_provenance=drifted.context_provenance,
    )
    with store, StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="bind|drift|exact"):
            engine.execute(
                prepare=lambda _journal: drifted_value,
                invoke=lambda _request: (_ for _ in ()).throw(AssertionError()),
                finalize=finalize,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )
        assert store.current_event_journal().latest_transition == value.pending_attempt


def test_reconciled_in_progress_attempt_commits_without_adapter_call(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "reconciled.sqlite3")
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    reconciled = invocation(value, adapter)
    with store.acquire_run_lease():
        store.append_attempt(value.pending_attempt)
        store.append_attempt(value.in_progress_attempt)
    with store, StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: (_ for _ in ()).throw(AssertionError("blind invoke")),
            finalize=finalize,
            build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
            reconciliation=reconciled,
        )
        assert outcome.state == "committed"
        assert outcome.adapter_invoked is False
        store.assert_complete()


def test_landed_success_and_commit_fault_recover_without_adapter_call(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "landed.sqlite3")
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    with store.acquire_run_lease():
        store.append_attempt(value.pending_attempt)
        store.append_attempt(value.in_progress_attempt)
        store.append_attempt(finalize(value, invocation(value, adapter)))
    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(RuntimeError, match="commit fixture fault"):
            engine.execute(
                prepare=lambda _journal: (_ for _ in ()).throw(AssertionError()),
                invoke=lambda _request: (_ for _ in ()).throw(AssertionError()),
                finalize=finalize,
                build_commit=lambda _terminal: (_ for _ in ()).throw(
                    RuntimeError("commit fixture fault")
                ),
            )
        assert store.current_event_journal().resume_state == (
            "succeeded_attempt_requires_atomic_commit"
        )
    with store, StrictSerialLifecycleEngine(store) as recovered:
        outcome = recovered.execute(
            prepare=lambda _journal: (_ for _ in ()).throw(AssertionError()),
            invoke=lambda _request: (_ for _ in ()).throw(AssertionError()),
            finalize=finalize,
            build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
        )
        assert outcome.adapter_invoked is False
        assert outcome.state == "committed"


def test_retry_requires_exact_authorization_hash_and_next_attempt_index(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "retry.sqlite3")
    first = prepared(run_manifest.run_id)
    with store.acquire_run_lease():
        store.append_attempt(first.pending_attempt)
        store.append_attempt(first.in_progress_attempt)
        failed = failed_attempt(first)
        store.append_attempt(failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="explicit fixture halt",
            policy_evidence={"policy_id": "fixture-policy", "policy_hash": "a" * 64},
            recorded_at=NOW,
        )
        authorization = store.authorize_resume(
            authorization_id="resume-engine-fixture",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy-fixture",
            policy_evidence_hash="b" * 64,
            authorized_at=NOW,
        )
    wrong = prepared(run_manifest.run_id, attempt_index=2, resume_hash="f" * 64)
    with StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="exact resume"):
            engine.execute(
                prepare=lambda _journal: wrong,
                invoke=lambda _request: (_ for _ in ()).throw(AssertionError()),
                finalize=finalize,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )
        assert store.current_event_journal().next_attempt_index == 2
    second = prepared(
        run_manifest.run_id,
        attempt_index=2,
        resume_hash=authorization.payload_hash,
    )
    adapter = adapter_for(second.authorization.event_id, reason="reason-0-2", attempt_index=2)
    with store, StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: second,
            invoke=lambda _request: invocation(second, adapter),
            finalize=finalize,
            build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
        )
        assert outcome.state == "committed"
        assert outcome.attempt is not None and outcome.attempt.attempt_index == 2


def test_complete_is_noop_and_second_engine_is_rejected_until_release(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "complete.sqlite3")
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    first = StrictSerialLifecycleEngine(store)
    second = StrictSerialLifecycleEngine(store)
    with first:
        with pytest.raises(RuntimeError, match="lease|owned"):
            second.__enter__()
        first.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: invocation(value, adapter),
            finalize=finalize,
            build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
        )
    with store, second:
        outcome = second.execute(
            prepare=lambda _journal: (_ for _ in ()).throw(AssertionError()),
            invoke=lambda _request: (_ for _ in ()).throw(AssertionError()),
            finalize=finalize,
            build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
        )
        assert outcome == AttemptOutcome("complete", None, None, False)


def test_checkpoint_is_only_written_by_explicit_call_and_binds_sqlite_truth(
    tmp_path: Path,
) -> None:
    store, run_manifest = create_store(tmp_path / "checkpoint.sqlite3")
    checkpoint_path = tmp_path / "run.checkpoint.json"
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    with store, StrictSerialLifecycleEngine(store) as engine:
        engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: invocation(value, adapter),
            finalize=finalize,
            build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
        )
        assert not checkpoint_path.exists()
        written_hash = engine.write_checkpoint(checkpoint_path)
        checkpoint = load_checkpoint(checkpoint_path)
        assert checkpoint.checkpoint_hash == written_hash
        assert validate_checkpoint(checkpoint, store) == "current"


def test_pending_exact_recovery_invokes_once_and_commits(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "pending-exact.sqlite3")
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    with store.acquire_run_lease():
        store.append_attempt(value.pending_attempt)
    calls = 0

    def invoke(_request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal calls
        calls += 1
        return invocation(value, adapter)

    with store, StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=invoke,
            finalize=finalize,
            build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
        )
        assert outcome.state == "committed"
        assert calls == 1


def test_typed_finalize_failure_lands_failed_attempt(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "finalize-failed.sqlite3")
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    result = invocation(value, adapter)
    with store, StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: result,
            finalize=lambda _value, _result: (_ for _ in ()).throw(
                AttemptLifecycleFailure(failed_attempt(value, code="parse_failure", result=result))
            ),
            build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
        )
        assert outcome.state == "failed"
        assert outcome.attempt is not None
        assert outcome.attempt.error == {"code": "parse_failure"}


def test_foreign_authorization_and_lease_loss_fail_before_invoke(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "identity.sqlite3")
    value = prepared(run_manifest.run_id)
    foreign_run = "foreign-run"
    foreign = PreparedAttempt(
        authorization=AttemptAuthorization(
            run_id=foreign_run,
            event_id=derive_event_id(foreign_run, 0),
            event_ordinal=0,
            attempt_index=1,
            model_seed=value.authorization.model_seed,
            model_identity=value.authorization.model_identity,
            model_identity_hash=value.authorization.model_identity_hash,
            request_parameters=value.authorization.request_parameters,
            request_parameters_hash=value.authorization.request_parameters_hash,
            resume_authorization_hash=None,
            mock_only=True,
        ),
        request=value.request,
        pending_attempt=value.pending_attempt,
        in_progress_attempt=value.in_progress_attempt,
        context_provenance=value.context_provenance,
    )
    calls = 0

    def invoke(_request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal calls
        calls += 1
        raise AssertionError("identity or lease failure must precede invoke")

    engine = StrictSerialLifecycleEngine(store)
    with engine:
        with pytest.raises(ValueError, match="exact current"):
            engine.execute(
                prepare=lambda _journal: foreign,
                invoke=invoke,
                finalize=finalize,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )
        assert store.current_event_journal().latest_transition is None

        def lose_lease(_journal: object) -> PreparedAttempt:
            engine.close()
            return value

        with pytest.raises(RuntimeError, match="lease"):
            engine.execute(
                prepare=lose_lease,
                invoke=invoke,
                finalize=finalize,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )
        assert calls == 0
        assert store.current_event_journal().latest_transition is None
    store.close()


def test_checkpoint_write_failure_preserves_old_stale_rebuildable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, run_manifest = create_store(tmp_path / "checkpoint-fault.sqlite3")
    checkpoint_path = tmp_path / "run.checkpoint.json"
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    with store, StrictSerialLifecycleEngine(store) as engine:
        engine.write_checkpoint(checkpoint_path)
        old_bytes = checkpoint_path.read_bytes()
        engine.execute(
            prepare=lambda _journal: value,
            invoke=lambda _request: invocation(value, adapter),
            finalize=finalize,
            build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
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


def test_finalize_success_must_bind_exact_actual_response_raw_text(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "response-binding.sqlite3")
    value = prepared(run_manifest.run_id)
    adapter = adapter_for(value.authorization.event_id)
    result = invocation(value, adapter)
    forged = finalize(value, result)
    forged_payload = forged.to_payload()
    forged_raw = json.dumps(
        {"stance": "neutral", "confidence": 3, "public_reason": "forged raw"},
        separators=(",", ":"),
    )
    forged_payload["raw_response"] = forged_raw
    forged_payload["raw_response_hash"] = canonical_payload_hash(forged_raw)
    forged_terminal = GenerationAttempt.from_payload(forged_payload)
    with store, StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="response|raw|evidence"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=lambda _request: result,
                finalize=lambda _value, _result: forged_terminal,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )
        assert store.current_event_journal().resume_state == (
            "in_progress_requires_provider_reconciliation"
        )


def test_finalize_typed_failure_must_preserve_actual_response_evidence(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "failure-response-binding.sqlite3")
    value = prepared(run_manifest.run_id)
    result = invocation(value, adapter_for(value.authorization.event_id))
    missing_raw = failed_attempt(value, code="parse_failure")
    with store, StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="response|raw|evidence"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=lambda _request: result,
                finalize=lambda _value, _result: (_ for _ in ()).throw(
                    AttemptLifecycleFailure(missing_raw)
                ),
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )
        assert store.current_event_journal().resume_state == (
            "in_progress_requires_provider_reconciliation"
        )


def test_timeout_response_cannot_be_finalized_as_success(tmp_path: Path) -> None:
    store, run_manifest = create_store(tmp_path / "timeout-success.sqlite3")
    value = prepared(run_manifest.run_id)
    result = timeout_invocation(value)
    forged_payload = value.in_progress_attempt.to_payload()
    forged_raw = json.dumps(
        {"stance": "neutral", "confidence": 3, "public_reason": "forged timeout"},
        separators=(",", ":"),
    )
    forged_parsed = json.loads(forged_raw)
    forged_payload.update(
        {
            "status": "succeeded",
            "provider_request_id": result.response.provider_request_id,
            "provider_metadata": _json_ready(result.evidence.provider_metadata),
            "provider_metadata_hash": canonical_payload_hash(result.evidence.provider_metadata),
            "http_status": result.evidence.http_status,
            "raw_response": forged_raw,
            "raw_response_hash": canonical_payload_hash(forged_raw),
            "parsed_response": forged_parsed,
            "parsed_response_hash": canonical_payload_hash(forged_parsed),
            "usage": _json_ready(result.evidence.usage),
            "usage_hash": canonical_payload_hash(result.evidence.usage),
            "finish_reason": result.evidence.finish_reason,
            "error": None,
            "finished_at": result.evidence.finished_at,
        }
    )
    forged = GenerationAttempt.from_payload(forged_payload)
    with store, StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="timeout|outcome|response"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=lambda _request: result,
                finalize=lambda _value, _result: forged,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
            )


def test_nested_public_mapping_inputs_are_recursively_frozen() -> None:
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
    evidence_source = {"nested": {"ids": ["provider-1"]}}
    evidence = AttemptExecutionEvidence(
        started_at=NOW,
        finished_at=NOW,
        http_status=200,
        provider_metadata=evidence_source,
        usage={"nested": {"counts": [1, 2]}},
        finish_reason="stop",
    )
    model["nested"]["tags"].append("mutated")
    parameters["sampling"]["stops"].append("mutated")
    evidence_source["nested"]["ids"].append("mutated")
    assert authorization.model_identity["nested"]["tags"] == ("a", "b")
    assert authorization.request_parameters["sampling"]["stops"] == ("END",)
    assert evidence.provider_metadata["nested"]["ids"] == ("provider-1",)


def test_reconciliation_is_rejected_outside_in_progress_without_mutation(
    tmp_path: Path,
) -> None:
    store, run_manifest = create_store(tmp_path / "misplaced-reconciliation.sqlite3")
    value = prepared(run_manifest.run_id)
    result = invocation(value, adapter_for(value.authorization.event_id))
    calls = 0

    def invoke(_request: AdapterRequest) -> AttemptInvocationResult:
        nonlocal calls
        calls += 1
        return result

    with store, StrictSerialLifecycleEngine(store) as engine:
        with pytest.raises(ValueError, match="reconciliation"):
            engine.execute(
                prepare=lambda _journal: value,
                invoke=invoke,
                finalize=finalize,
                build_commit=lambda _terminal: (_ for _ in ()).throw(AssertionError()),
                reconciliation=result,
            )
        assert calls == 0
        assert store.current_event_journal().latest_transition is None


def test_full_integrity_replay_occurs_once_per_engine_open_not_per_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, run_manifest = create_store(
        tmp_path / "integrity-count.sqlite3", publish_flags=(False, False)
    )
    original = store.verify_integrity
    calls = 0

    def counted() -> None:
        nonlocal calls
        calls += 1
        original()

    monkeypatch.setattr(store, "verify_integrity", counted)
    with StrictSerialLifecycleEngine(store) as engine:
        for ordinal in range(2):
            value = prepared(run_manifest.run_id, ordinal=ordinal)
            adapter = adapter_for(value.authorization.event_id, reason=f"reason-{ordinal}-1")
            engine.execute(
                prepare=lambda _journal, item=value: item,
                invoke=lambda _request, item=value, source=adapter: invocation(item, source),
                finalize=finalize,
                build_commit=lambda terminal: commit_for(store, run_manifest, terminal),
            )
        assert calls == 1
        engine.write_checkpoint(tmp_path / "integrity-count.checkpoint.json")
        assert calls == 2
    with StrictSerialLifecycleEngine(store):
        assert calls == 3
    store.close()
