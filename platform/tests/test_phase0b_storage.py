from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from agent_ex.domain import EventStatus, GenerationAttempt, canonical_payload_hash
from agent_ex.execution_evidence import (
    DiagnosticAdapterRequestEvidence,
    DiagnosticParseEvidence,
    DiagnosticPersistedInvocationEvidence,
)
from agent_ex.phase0b.contracts import DiagnosticAdapterBinding, DiagnosticAttemptPolicy
from agent_ex.phase0b.real_pipeline import (
    PreparedRealDiagnosticEvent,
    dispatch_real_diagnostic_event_once,
)
from agent_ex.phase0b.vllm_event_adapter import (
    PHASE0B_VLLM_ENDPOINT,
    Phase0BDispatchJournal,
    Phase0BVllmEventRequest,
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
    Phase0BVllmEventAdapter,
)
from agent_ex.state import PrivateState, PrivateUpdate
from agent_ex.storage import RunStorage
from test_storage import (
    prepared_evidence_bundle,
    prompt_topic,
    reopen_evidence_store,
    successful_event,
)
from test_phase0b_vllm_event_adapter import FakeConnection


SHA = "a" * 64


@pytest.fixture(autouse=True)
def _lease_created_stores(monkeypatch: pytest.MonkeyPatch):
    original = RunStorage.create.__func__

    def create_with_lease(cls, *args: object, **kwargs: object) -> RunStorage:
        store = original(cls, *args, **kwargs)
        store.acquire_run_lease().acquire()
        return store

    monkeypatch.setattr(RunStorage, "create", classmethod(create_with_lease))


def _policy() -> DiagnosticAttemptPolicy:
    return DiagnosticAttemptPolicy.create(
        connect_timeout_seconds=10.0,
        read_timeout_seconds=120.0,
        total_timeout_seconds=180.0,
        retryable_error_codes=("provider_busy", "transport_timeout"),
        max_same_event_retries=1,
    )


def _binding() -> DiagnosticAdapterBinding:
    return DiagnosticAdapterBinding.create(
        model_repository="Qwen/Qwen3-8B",
        model_revision="b" * 40,
        tokenizer_revision="b" * 40,
        chat_template_hash=SHA,
        vllm_version="0.23.0",
        package_lock_hash=SHA,
        image_identity_hash=SHA,
        environment_lock_hash=SHA,
        service_start_identity_hash=SHA,
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        served_model_name="qwen3-8b-paper1",
    )


def _diagnostic_prefix(tmp_path: Path):
    store, values = prepared_evidence_bundle(tmp_path)
    policy = _policy()
    binding = _binding()
    event_input = values["event_input"]
    mock_request = values["request_evidence"].request
    request = Phase0BVllmEventRequest.create(
        event_id=event_input.event_id,
        attempt_index=1,
        prompt_hash=event_input.prompt_view.record_hash,
        rendered_messages=tuple(dict(message) for message in mock_request.rendered_messages),
        generation_settings={"temperature": 0.7, "top_p": 0.8, "max_tokens": 128},
        model_seed=12345,
        adapter_binding_hash=binding.record_hash,
    )
    request_evidence = DiagnosticAdapterRequestEvidence.create(
        request=request,
        run_authorization_hash="c" * 64,
        parser_limits_hash=event_input.parser_limits.record_hash,
        attempt_policy_hash=policy.record_hash,
        adapter_binding=binding,
    )
    base = values["pending"].to_payload()
    base.update(
        {
            "request_id": request.request_id,
            "rendered_messages": [dict(message) for message in request.rendered_messages],
            "rendered_prompt_hash": request.rendered_messages_hash,
            "request_parameters": dict(request.generation_settings),
            "request_parameters_hash": request.generation_settings_hash,
            "model_identity": dict(request_evidence.model_identity),
            "model_identity_hash": request_evidence.model_identity_hash,
            "model_seed": request.model_seed,
        }
    )
    pending = GenerationAttempt.from_payload(base)
    return store, values, policy, binding, request_evidence, pending


def test_diagnostic_prepared_prefix_reopens_without_mock_relabeling(tmp_path: Path) -> None:
    store, values, policy, binding, request_evidence, pending = _diagnostic_prefix(tmp_path)

    store.record_diagnostic_prepared_attempt(
        values["event_input"],
        policy=policy,
        adapter_binding=binding,
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    reopened = reopen_evidence_store(store, values)

    assert reopened.attempt_policy_evidence(pending.event_id) == policy
    assert reopened.adapter_execution_binding(pending.attempt_id) == binding
    assert reopened.adapter_request_evidence(pending.attempt_id) == request_evidence
    payload = reopened.adapter_request_evidence(pending.attempt_id).to_payload()
    assert payload["schema_version"] == "paper1.phase0b.diagnostic-adapter-request-evidence.v1"
    assert "mock_only" not in payload


def test_diagnostic_discriminator_tamper_fails_closed_before_attempt_mutation(
    tmp_path: Path,
) -> None:
    store, values, policy, binding, request_evidence, pending = _diagnostic_prefix(tmp_path)
    store.record_diagnostic_prepared_attempt(
        values["event_input"],
        policy=policy,
        adapter_binding=binding,
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    before = store.execution_state()
    before_transitions = store.attempt_transitions(pending.attempt_id)
    payload = request_evidence.to_payload()
    payload["schema_version"] = "paper1.unknown-request.v9"
    payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in payload.items() if key != "record_hash"}
    )
    store._connection.execute(
        "UPDATE adapter_requests SET payload = ?, record_hash = ? WHERE attempt_id = ?",
        (
            __import__("json").dumps(payload, sort_keys=True, separators=(",", ":")),
            payload["record_hash"],
            pending.attempt_id,
        ),
    )
    store._connection.commit()

    try:
        store.adapter_request_evidence(pending.attempt_id)
    except ValueError as error:
        assert "schema" in str(error) or "unsupported" in str(error)
    else:
        raise AssertionError("unknown diagnostic request discriminator was accepted")
    assert store.execution_state() == before
    assert store.attempt_transitions(pending.attempt_id) == before_transitions


def test_diagnostic_post_response_prefix_reopens_without_resend(tmp_path: Path) -> None:
    store, values, policy, binding, request_evidence, pending = _diagnostic_prefix(tmp_path)
    store.record_diagnostic_prepared_attempt(
        values["event_input"],
        policy=policy,
        adapter_binding=binding,
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    in_progress = replace(
        pending,
        status=EventStatus.IN_PROGRESS,
        started_at="2026-09-20T00:00:00Z",
    )
    store.append_attempt(in_progress)
    body = b'{"id":"provider-1","model":"qwen3-8b-paper1","choices":[],"usage":{}}'
    transport = Phase0BVllmTransportEvidence.create(
        request=request_evidence.request,
        http_status=200,
        response_headers={"x-request-id": "provider-1"},
        provider_request_id="provider-1",
        request_body=b"{}",
        raw_body=body,
        body_truncated=False,
        started_at="2026-09-20T00:00:00Z",
        ended_at="2026-09-20T00:00:01Z",
        latency_seconds=1.0,
        outcome="response",
        error_code=None,
    )
    response = Phase0BVllmEventResponse.create(
        request=request_evidence.request,
        outcome="response",
        error_code=None,
        retry_after_seconds=None,
        provider_request_id="provider-1",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        finish_reason="stop",
        raw_body=body,
        transport_evidence=transport,
    )
    invocation = DiagnosticPersistedInvocationEvidence.create(
        response=response,
        request_evidence=request_evidence,
    )

    store.record_diagnostic_invocation_evidence(invocation)
    reopened = reopen_evidence_store(store, values)

    assert reopened.invocation_evidence(pending.attempt_id) == invocation
    assert reopened.current_event_journal().latest_transition.status.value == "in_progress"
    assert reopened.progress.next_event_ordinal == 0


def test_diagnostic_parse_evidence_replays_response_without_mock_schema(tmp_path: Path) -> None:
    _store, values, _policy, _binding, request_evidence, _pending = _diagnostic_prefix(tmp_path)
    content = b'{"stance":"label-2","confidence":3,"public_reason":"short reason"}'
    body = (
        b'{"choices":[{"message":{"content":'
        + json.dumps(content.decode("utf-8")).encode("utf-8")
        + b"}}]}"
    )
    transport = Phase0BVllmTransportEvidence.create(
        request=request_evidence.request,
        http_status=200,
        response_headers={},
        provider_request_id="provider-1",
        request_body=b"{}",
        raw_body=body,
        body_truncated=False,
        started_at="2026-09-20T00:00:00Z",
        ended_at="2026-09-20T00:00:01Z",
        latency_seconds=1.0,
        outcome="response",
        error_code=None,
    )
    response = Phase0BVllmEventResponse.create(
        request=request_evidence.request,
        outcome="response",
        error_code=None,
        retry_after_seconds=None,
        provider_request_id="provider-1",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        finish_reason="stop",
        raw_body=body,
        transport_evidence=transport,
    )
    parsed = DiagnosticParseEvidence.create(
        response=response,
        topic_package=prompt_topic(),
        parser_limits_hash=values["event_input"].parser_limits.record_hash,
    )

    assert parsed.success is True
    assert parsed.parsed_response == {
        "stance": "label-2",
        "confidence": 3,
        "public_reason": "short reason",
    }
    assert DiagnosticParseEvidence.from_payload(parsed.to_payload()) == parsed
    assert parsed.to_payload()["schema_version"] == "paper1.phase0b.diagnostic-parse-evidence.v1"

    tampered = parsed.to_payload()
    tampered["parsed_response"]["stance"] = "label-1"
    with pytest.raises(ValueError, match="record_hash"):
        DiagnosticParseEvidence.from_payload(tampered)

    invalid_body = b'{"choices":[{"message":{"content":"not-json"}}]}'
    invalid_transport = Phase0BVllmTransportEvidence.create(
        request=request_evidence.request,
        http_status=200,
        response_headers={},
        provider_request_id="provider-1",
        request_body=b"{}",
        raw_body=invalid_body,
        body_truncated=False,
        started_at="2026-09-20T00:00:00Z",
        ended_at="2026-09-20T00:00:01Z",
        latency_seconds=1.0,
        outcome="response",
        error_code=None,
    )
    invalid_response = Phase0BVllmEventResponse.create(
        request=request_evidence.request,
        outcome="response",
        error_code=None,
        retry_after_seconds=None,
        provider_request_id="provider-1",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        finish_reason="stop",
        raw_body=invalid_body,
        transport_evidence=invalid_transport,
    )
    failed = DiagnosticParseEvidence.create(
        response=invalid_response,
        topic_package=prompt_topic(),
        parser_limits_hash=values["event_input"].parser_limits.record_hash,
    )
    assert failed.success is False
    assert failed.parsed_response is None
    assert failed.error_code == "json"
    assert DiagnosticParseEvidence.from_payload(failed.to_payload()) == failed


def test_diagnostic_success_terminal_reopens_without_mock_parse(tmp_path: Path) -> None:
    store, values, policy, binding, request_evidence, pending = _diagnostic_prefix(tmp_path)
    store.record_diagnostic_prepared_attempt(
        values["event_input"],
        policy=policy,
        adapter_binding=binding,
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    in_progress = replace(
        pending, status=EventStatus.IN_PROGRESS, started_at="2026-09-20T00:00:00Z"
    )
    store.append_attempt(in_progress)
    body = (
        b'{"choices":[{"message":{"content":'
        + json.dumps('{"stance":"label-2","confidence":3,"public_reason":"reason"}').encode()
        + b"}}]}"
    )
    transport = Phase0BVllmTransportEvidence.create(
        request=request_evidence.request,
        http_status=200,
        response_headers={},
        provider_request_id="provider-1",
        request_body=b"{}",
        raw_body=body,
        body_truncated=False,
        started_at="2026-09-20T00:00:00.100000Z",
        ended_at="2026-09-20T00:00:01Z",
        latency_seconds=1.0,
        outcome="response",
        error_code=None,
    )
    response = Phase0BVllmEventResponse.create(
        request=request_evidence.request,
        outcome="response",
        error_code=None,
        retry_after_seconds=None,
        provider_request_id="provider-1",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        finish_reason="stop",
        raw_body=body,
        transport_evidence=transport,
    )
    store.record_diagnostic_invocation_evidence(
        DiagnosticPersistedInvocationEvidence.create(
            response=response, request_evidence=request_evidence
        )
    )
    parsed = DiagnosticParseEvidence.create(
        response=response,
        topic_package=prompt_topic(),
        parser_limits_hash=values["event_input"].parser_limits.record_hash,
    )
    metadata = {"diagnostic_response_hash": response.record_hash}
    raw_text = body.decode("utf-8")
    terminal = replace(
        in_progress,
        status=EventStatus.SUCCEEDED,
        provider_request_id=response.provider_request_id,
        provider_metadata=metadata,
        provider_metadata_hash=canonical_payload_hash(metadata),
        http_status=200,
        raw_response=raw_text,
        raw_response_hash=canonical_payload_hash(raw_text),
        parsed_response=parsed.parsed_response,
        parsed_response_hash=canonical_payload_hash(parsed.parsed_response),
        usage=dict(response.usage),
        usage_hash=canonical_payload_hash(response.usage),
        finish_reason="stop",
        finished_at="2026-09-20T00:00:01Z",
    )
    wrong_metadata = {"diagnostic_response_hash": "f" * 64}
    with pytest.raises(ValueError, match="projection"):
        store.record_diagnostic_finalized_attempt(
            replace(
                terminal,
                provider_metadata=wrong_metadata,
                provider_metadata_hash=canonical_payload_hash(wrong_metadata),
            ),
            parsed,
        )
    assert store.parse_evidence(terminal.attempt_id) is None
    assert store.current_event_journal().latest_transition == in_progress
    store.record_diagnostic_finalized_attempt(terminal, parsed)
    reopened = reopen_evidence_store(store, values)

    assert reopened.parse_evidence(terminal.attempt_id) == parsed
    assert reopened.attempts_for_event(terminal.event_id) == (terminal,)
    assert reopened.progress.next_event_ordinal == 0

    previous_state = reopened.private_state("agent-0001")
    previous_cursor = reopened.feed_cursor("agent-0001")
    assert previous_state is not None and previous_cursor is not None
    update = PrivateUpdate.create(
        topic_package=prompt_topic(),
        matched_seed=previous_state.matched_seed,
        agent_id="agent-0001",
        event_id=terminal.event_id,
        event_ordinal=0,
        sequence_index=previous_state.successful_update_count,
        stance_label=parsed.parsed_response["stance"],
        reason=parsed.parsed_response["public_reason"],
        confidence=parsed.parsed_response["confidence"],
        published=False,
        source_attempt_id=terminal.attempt_id,
        mock_only=True,
    )
    reopened.commit_success(
        successful_event(values["manifest"], ordinal=0),
        final_attempt=terminal,
        private_update=update,
        private_state=PrivateState.from_update(update, previous=previous_state, mock_only=True),
        feed_cursor=previous_cursor.advance(0),
        public_post=None,
        latest_public_pointer=None,
    )
    committed = reopen_evidence_store(reopened, values)
    assert committed.progress.next_event_ordinal == 1
    assert committed.private_state("agent-0001").stance_label == "label-2"
    assert committed.feed_cursor("agent-0001").last_scanned_event_ordinal == 0


def test_diagnostic_malformed_response_records_failed_terminal_without_state_advance(
    tmp_path: Path,
) -> None:
    store, values, policy, binding, request_evidence, pending = _diagnostic_prefix(tmp_path)
    before_state = store.private_state("agent-0001")
    before_cursor = store.feed_cursor("agent-0001")
    store.record_diagnostic_prepared_attempt(
        values["event_input"],
        policy=policy,
        adapter_binding=binding,
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    in_progress = replace(
        pending, status=EventStatus.IN_PROGRESS, started_at="2026-09-20T00:00:00Z"
    )
    store.append_attempt(in_progress)
    body = b'{"choices":[{"message":{"content":"not-json"}}]}'
    transport = Phase0BVllmTransportEvidence.create(
        request=request_evidence.request,
        http_status=200,
        response_headers={},
        provider_request_id="provider-1",
        request_body=b"{}",
        raw_body=body,
        body_truncated=False,
        started_at="2026-09-20T00:00:00Z",
        ended_at="2026-09-20T00:00:01Z",
        latency_seconds=1.0,
        outcome="response",
        error_code=None,
    )
    response = Phase0BVllmEventResponse.create(
        request=request_evidence.request,
        outcome="response",
        error_code=None,
        retry_after_seconds=None,
        provider_request_id="provider-1",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        finish_reason="stop",
        raw_body=body,
        transport_evidence=transport,
    )
    store.record_diagnostic_invocation_evidence(
        DiagnosticPersistedInvocationEvidence.create(
            response=response, request_evidence=request_evidence
        )
    )
    parsed = DiagnosticParseEvidence.create(
        response=response,
        topic_package=prompt_topic(),
        parser_limits_hash=values["event_input"].parser_limits.record_hash,
    )
    assert parsed.error_code == "json"
    metadata = {"diagnostic_response_hash": response.record_hash}
    terminal = replace(
        in_progress,
        status=EventStatus.FAILED,
        provider_request_id=response.provider_request_id,
        provider_metadata=metadata,
        provider_metadata_hash=canonical_payload_hash(metadata),
        http_status=200,
        raw_response=body.decode(),
        raw_response_hash=canonical_payload_hash(body.decode()),
        usage=dict(response.usage),
        usage_hash=canonical_payload_hash(response.usage),
        finish_reason="stop",
        error={"code": "json"},
        finished_at="2026-09-20T00:00:01Z",
    )
    store.record_diagnostic_finalized_attempt(terminal, parsed)
    reopened = reopen_evidence_store(store, values)
    assert reopened.parse_evidence(terminal.attempt_id) == parsed
    assert reopened.attempts_for_event(terminal.event_id) == (terminal,)
    assert reopened.private_state("agent-0001") == before_state
    assert reopened.feed_cursor("agent-0001") == before_cursor
    assert reopened.progress.next_event_ordinal == 0
    stopped = reopened.record_terminal_failure(
        event_id=terminal.event_id,
        reason="diagnostic_parse_failed",
        policy_evidence={
            "policy_id": "phase0b-diagnostic-attempt-policy-v1",
            "policy_hash": policy.record_hash,
        },
        recorded_at="2026-09-20T00:00:02Z",
    )
    halted = reopen_evidence_store(reopened, values)
    assert halted.terminal_failure_evidence_prefix() == (stopped,)
    assert halted.private_state("agent-0001") == before_state
    assert halted.progress.next_event_ordinal == 0


def test_real_dispatch_records_intent_before_http_and_halts_on_bad_json(
    tmp_path: Path,
) -> None:
    store, values, policy, binding, request_evidence, pending = _diagnostic_prefix(tmp_path)
    store.record_diagnostic_prepared_attempt(
        values["event_input"],
        policy=policy,
        adapter_binding=binding,
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    prepared = PreparedRealDiagnosticEvent(
        values["event_input"], request_evidence.request, request_evidence, pending
    )
    FakeConnection.requests = []
    FakeConnection.body = (
        b'{"id":"provider-req-1","model":"qwen3-8b-paper1",'
        b'"choices":[{"message":{"content":"not-json"},"finish_reason":"stop"}],'
        b'"usage":{"prompt_tokens":2,"completion_tokens":1,"total_tokens":3}}'
    )
    FakeConnection.headers = {"X-Request-Id": "provider-req-1"}
    adapter = Phase0BVllmEventAdapter(
        PHASE0B_VLLM_ENDPOINT,
        served_model_name=binding.served_model_name,
        connection_factory=FakeConnection,
    )
    journal = Phase0BDispatchJournal(tmp_path / "dispatch.jsonl")

    class InputOnly:
        run_id = store.binding.run_id

    terminal = dispatch_real_diagnostic_event_once(
        storage=store,
        input_pipeline=InputOnly(),
        prepared=prepared,
        adapter=adapter,
        policy=policy,
        topic_package=prompt_topic(),
        dispatch_journal=journal,
        clock=lambda: "2026-09-20T00:00:00Z",
    )
    assert terminal.status is EventStatus.FAILED
    assert terminal.error == {"code": "json"}
    assert len(FakeConnection.requests) == 1
    assert journal.unresolved_request_ids() == ()
    assert store.progress.next_event_ordinal == 0
    assert len(store.terminal_failure_evidence_prefix()) == 1
