"""Synthetic provider responses; never contacts a model or cloud service."""

from dataclasses import replace
import json
import sqlite3

import pytest

from agent_ex.domain import EventStatus, canonical_payload_hash
from agent_ex.execution_evidence import DiagnosticPersistedInvocationEvidence
from agent_ex.execution_evidence import DiagnosticParseEvidence
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.execution import finalize_study_response, prepare_study_event
from agent_ex.phase0b.vllm_event_adapter import (
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
)
from agent_ex.storage import _canonical_json
from test_identity_network_prefix import prefix_store


def response_for(
    stored,
    kwargs,
    *,
    content=None,
    wrong_wire=False,
    model="qwen3-8b-paper1",
    response_model="same",
):
    evidence = kwargs["request_evidence"]
    request = evidence.request
    content = (
        content
        if content is not None
        else json.dumps(
            {"stance": "label-5", "confidence": 3, "public_reason": "Synthetic test reason."}
        )
    )
    envelope = {"choices": [{"message": {"content": content}}]}
    if response_model is not None:
        envelope["model"] = model if response_model == "same" else response_model
    body = json.dumps(envelope).encode()
    wire = {
        "model": model,
        "messages": [dict(m) for m in request.rendered_messages],
        **dict(request.generation_settings),
        "seed": request.model_seed,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if wrong_wire:
        wire["seed"] += 1
    transport = Phase0BVllmTransportEvidence.create(
        request=request,
        http_status=200,
        response_headers={},
        provider_request_id="synthetic-1",
        request_body=json.dumps(wire).encode(),
        raw_body=body,
        body_truncated=False,
        started_at="2026-10-01T00:00:00.100000Z",
        ended_at="2026-10-01T00:00:01Z",
        latency_seconds=0.9,
        outcome="response",
        error_code=None,
    )
    response = Phase0BVllmEventResponse.create(
        request=request,
        outcome="response",
        error_code=None,
        retry_after_seconds=None,
        provider_request_id="synthetic-1",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        finish_reason="stop",
        raw_body=body,
        transport_evidence=transport,
    )
    invocation = DiagnosticPersistedInvocationEvidence.create(
        response=response, request_evidence=evidence
    )
    i = stored.input
    prepared = prepare_study_event(
        run_id=i.run_id,
        event_ordinal=i.event_ordinal,
        attempt_index=request.attempt_index,
        previous_event_hash=i.previous_event_hash,
        publish_flag=i.publish_flag,
        prompt=i.prompt,
        private_state=i.private_state,
        topic_package=i.topic_package,
        parser_limits=i.parser_limits,
        model_seed=request.model_seed,
        generation_settings=dict(request.generation_settings),
        adapter_binding_hash=request.adapter_binding_hash,
    )
    return invocation, prepared


def terminal_for(in_progress, invocation, parsed):
    response = invocation.response
    raw = response.raw_body.decode()
    metadata = {"diagnostic_response_hash": response.record_hash}
    parsed_payload = (
        None
        if not parsed.success
        else {
            "topic_package_id": parsed.topic_package_id,
            "topic_package_hash": parsed.topic_package_hash,
            **dict(parsed.parsed_response),
        }
    )
    return replace(
        in_progress,
        status=EventStatus.SUCCEEDED if parsed.success else EventStatus.FAILED,
        provider_request_id=response.provider_request_id,
        provider_metadata=metadata,
        provider_metadata_hash=canonical_payload_hash(metadata),
        http_status=response.transport_evidence.http_status,
        raw_response=raw,
        raw_response_hash=canonical_payload_hash(raw),
        parsed_response=parsed_payload,
        parsed_response_hash=None
        if parsed_payload is None
        else canonical_payload_hash(parsed_payload),
        usage=dict(response.usage),
        usage_hash=canonical_payload_hash(response.usage),
        finish_reason=response.finish_reason,
        finished_at=response.transport_evidence.ended_at,
        error=None if parsed.success else {"code": parsed.error_code},
    )


@pytest.mark.parametrize("cell", study_cells())
@pytest.mark.parametrize("valid", [True, False])
def test_sis_response_terminal_reopens_without_state_commit(tmp_path, cell, valid):
    store, cls, binding, manifest, path, stored, kwargs = prefix_store(tmp_path, cell)
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        in_progress = store.start_diagnostic_attempt(
            kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z"
        )
        invocation, prepared = response_for(stored, kwargs, content=None if valid else "not JSON")
        parsed = finalize_study_response(prepared=prepared, response=invocation.response).parse
        store.record_diagnostic_invocation_evidence(invocation)
        store.record_diagnostic_invocation_evidence(invocation)
        store.close()
        store = cls.open(path, manifest=manifest, **binding.storage_arguments())
        assert store.invocation_evidence(in_progress.attempt_id) == invocation
        assert store.current_event_journal().latest_transition == in_progress
        with store.acquire_run_lease():
            terminal = terminal_for(in_progress, invocation, parsed)
            store.record_diagnostic_finalized_attempt(terminal, parsed)
        store.close()
        store = cls.open(path, manifest=manifest, **binding.storage_arguments())
        assert store.parse_evidence(terminal.attempt_id) == parsed
        assert store.current_event_journal().latest_transition == terminal
        assert store.progress.next_event_ordinal == 0
        assert store.private_state(binding.node_agent_ids[0]) == stored.input.private_state
        assert store.feed_cursor(binding.node_agent_ids[0]).activation_count == 0
    finally:
        store.close()


def test_wrong_wire_response_rejected_before_landing(tmp_path):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        store.start_diagnostic_attempt(kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z")
        invocation, _ = response_for(stored, kwargs, wrong_wire=True)
        with pytest.raises(ValueError, match="wire"):
            store.record_diagnostic_invocation_evidence(invocation)
        assert store.invocation_evidence(invocation.attempt_id) is None
    finally:
        store.close()


def test_terminal_insert_interruption_rolls_back_parse(tmp_path):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        progress = store.start_diagnostic_attempt(
            kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z"
        )
        invocation, prepared = response_for(stored, kwargs)
        parsed = finalize_study_response(prepared=prepared, response=invocation.response).parse
        store.record_diagnostic_invocation_evidence(invocation)
        store._connection.execute(
            "CREATE TRIGGER fail_terminal BEFORE INSERT ON attempts BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected"):
            store.record_diagnostic_finalized_attempt(
                terminal_for(progress, invocation, parsed), parsed
            )
        assert store.parse_evidence(progress.attempt_id) is None
        assert store.current_event_journal().latest_transition == progress
        assert not store._connection.in_transaction
    finally:
        store.close()


def test_unbounded_parse_cannot_bypass_bound_limits(tmp_path):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        progress = store.start_diagnostic_attempt(
            kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z"
        )
        content = json.dumps(
            {
                "stance": "label-5",
                "confidence": 3,
                "public_reason": "x" * (stored.input.parser_limits.max_reason_chars + 1),
            }
        )
        invocation, prepared = response_for(stored, kwargs, content=content)
        bounded = finalize_study_response(prepared=prepared, response=invocation.response).parse
        assert not bounded.success
        store.record_diagnostic_invocation_evidence(invocation)
        loose = DiagnosticParseEvidence.create(
            response=invocation.response,
            topic_package=stored.input.topic_package,
            parser_limits_hash=stored.input.parser_limits.record_hash,
        )
        assert loose.success
        with pytest.raises(ValueError, match="bounded response replay"):
            store.record_diagnostic_finalized_attempt(
                terminal_for(progress, invocation, loose), loose
            )
        assert store.parse_evidence(progress.attempt_id) is None
        store.record_diagnostic_finalized_attempt(
            terminal_for(progress, invocation, bounded), bounded
        )
        assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


def test_cold_reopen_rejects_rehashed_wrong_wire_invocation(tmp_path):
    store, cls, binding, manifest, path, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    store.record_diagnostic_prepared_attempt(stored, **kwargs)
    store.start_diagnostic_attempt(kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z")
    good, _ = response_for(stored, kwargs)
    store.record_diagnostic_invocation_evidence(good)
    store.close()
    bad, _ = response_for(stored, kwargs, wrong_wire=True)
    encoded = _canonical_json(bad.to_payload())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE invocation_evidence SET response_payload=?, execution_payload=?, record_hash=?",
            (encoded, encoded, bad.record_hash),
        )
    with pytest.raises(ValueError, match="wire"):
        reopened = cls.open(path, manifest=manifest, **binding.storage_arguments())
        reopened.close()


@pytest.mark.parametrize("field", ["model", "authorization"])
def test_invocation_model_and_authorization_bind_live_and_cold(tmp_path, field):
    store, cls, binding, manifest, path, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        store.start_diagnostic_attempt(kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z")
        good, _ = response_for(stored, kwargs)
        if field == "model":
            bad, _ = response_for(stored, kwargs, model="different-model")
        else:
            payload = good.to_payload()
            payload["run_authorization_hash"] = "f" * 64
            payload["record_hash"] = canonical_payload_hash(
                {k: v for k, v in payload.items() if k != "record_hash"}
            )
            bad = DiagnosticPersistedInvocationEvidence.from_payload(payload)
        with pytest.raises(ValueError, match="model|authorization"):
            store.record_diagnostic_invocation_evidence(bad)
        assert store.invocation_evidence(bad.attempt_id) is None
        store.record_diagnostic_invocation_evidence(good)
    finally:
        store.close()
    encoded = _canonical_json(bad.to_payload())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE invocation_evidence SET response_payload=?, execution_payload=?, record_hash=?",
            (encoded, encoded, bad.record_hash),
        )
    with pytest.raises(ValueError, match="model|authorization"):
        reopened = cls.open(path, manifest=manifest, **binding.storage_arguments())
        reopened.close()


@pytest.mark.parametrize("response_model", [None, "different-provider-model"])
def test_success_requires_bound_provider_model(tmp_path, response_model):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        store.start_diagnostic_attempt(kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z")
        invocation, _ = response_for(stored, kwargs, response_model=response_model)
        with pytest.raises(ValueError, match="model"):
            store.record_diagnostic_invocation_evidence(invocation)
        assert store.invocation_evidence(invocation.attempt_id) is None
    finally:
        store.close()
