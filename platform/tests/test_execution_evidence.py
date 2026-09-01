from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json

import pytest

from agent_ex import execution_evidence as execution_evidence_module
from agent_ex import (
    EventEvidenceReferences,
    EventInputEvidence,
    FinalizedAttemptEvidence,
    MockAdapterExecutionBinding,
    MockAttemptPolicyBinding,
    ParseNotApplicableEvidence,
    PersistedInvocationEvidence,
)
from agent_ex.adapters.mock import MockAdapter, MockScriptStep
from agent_ex.domain import ExposureRecord, GenerationAttempt, canonical_payload_hash
from agent_ex.engine import AttemptExecutionEvidence, AttemptInvocationResult
from agent_ex.feed import build_exposure_record, select_unread_feed
from agent_ex.memory import build_memory_view
from agent_ex.parser import ParserLimits, parse_agent_update
from agent_ex.storage import TerminalFailureEvidence
from test_engine import (
    NOW,
    adapter_for,
    prepared,
    response_metadata,
)
from test_parser import response as parser_response
from test_prompt import RUN_ID, build as build_prompt, topic


def policy() -> MockAttemptPolicyBinding:
    return MockAttemptPolicyBinding.create(
        allowed_difference_fields=(
            "model_seed",
            "request_parameters.temperature",
        ),
        mock_only=True,
        formal_eligible=False,
    )


def adapter_binding(adapter: MockAdapter) -> MockAdapterExecutionBinding:
    return adapter.execution_binding()


def parser_limits() -> ParserLimits:
    return ParserLimits.create(
        max_raw_chars=100_000,
        max_raw_bytes=100_000,
        max_json_depth=32,
        max_reason_chars=10_000,
        mock_only=True,
    )


def event_inputs() -> EventInputEvidence:
    prompt = build_prompt()
    # Rebuild the same typed inputs used by the mature prompt fixture.
    from test_prompt import exposure_inputs, updates

    source = exposure_inputs()
    prompt_selection = source["exposure_selection"]
    prompt_exposure = source["exposure"]
    return EventInputEvidence.create(
        exposure_selection=prompt_selection,
        exposure_record=prompt_exposure,
        memory_view=build_memory_view(
            private_updates=updates(),
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            window=3,
            mock_only=True,
        ),
        prompt_view=prompt,
        parser_limits=parser_limits(),
        state_context_hash=canonical_payload_hash({"successful_prefix": 9}),
        publish_flag=True,
    )


def success_chain() -> tuple[GenerationAttempt, object, object, object]:
    raw = '{"stance":"label-2","confidence":3,"public_reason":"reason"}'
    response, request, _ = parser_response(raw)
    execution = AttemptExecutionEvidence(
        started_at=NOW,
        finished_at=NOW,
        http_status=200,
        provider_metadata=response_metadata(response),
        usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        finish_reason="stop",
    )
    result = AttemptInvocationResult(response=response, evidence=execution)
    parse = parse_agent_update(result.response, topic_package=topic(), limits=parser_limits())
    parsed = parse.parsed
    assert parsed is not None
    payload = {
        "attempt_id": request.attempt_id,
        "event_id": request.event_id,
        "attempt_index": request.attempt_index,
        "status": "succeeded",
        "request_id": request.request_id,
        "exposure_id": build_prompt().exposure_id,
        "rendered_messages": request.to_payload()["rendered_messages"],
        "rendered_prompt_hash": request.rendered_messages_hash,
        "request_parameters": {"temperature": 0.0},
        "request_parameters_hash": canonical_payload_hash({"temperature": 0.0}),
        "model_identity": dict(response.model_identity),
        "model_identity_hash": response.model_identity_hash,
        "model_seed": request.mock_seed,
        "provider_request_id": result.response.provider_request_id,
        "provider_metadata": response_metadata(result.response),
        "provider_metadata_hash": canonical_payload_hash(response_metadata(result.response)),
        "http_status": result.evidence.http_status,
        "raw_response": result.response.raw_response,
        "raw_response_hash": result.response.raw_response_hash,
        "parsed_response": parsed.to_payload(),
        "parsed_response_hash": canonical_payload_hash(parsed.to_payload()),
        "usage": dict(result.evidence.usage),
        "usage_hash": canonical_payload_hash(result.evidence.usage),
        "finish_reason": result.evidence.finish_reason,
        "error": None,
        "started_at": result.evidence.started_at,
        "finished_at": result.evidence.finished_at,
    }
    return GenerationAttempt.from_payload(payload), parse, result, request


def failure_evidence(attempt: GenerationAttempt) -> TerminalFailureEvidence:
    return TerminalFailureEvidence(
        evidence_sequence=1,
        previous_evidence_hash=None,
        evidence_kind="failure",
        evidence_id="failure-evidence-1",
        run_id=RUN_ID,
        event_id=attempt.event_id,
        event_ordinal=9,
        attempt_id=attempt.attempt_id,
        attempt_index=attempt.attempt_index,
        terminal_transition_hash=canonical_payload_hash(attempt.to_payload()),
        terminal_attempt_hash=canonical_payload_hash(attempt.to_payload()),
        reason="adapter_timeout",
        policy_evidence={"policy_id": policy().policy_id, "policy_hash": policy().record_hash},
        recorded_at=NOW,
    )


def rehash_parse_payload(payload: dict[str, object]) -> dict[str, object]:
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    return payload


def test_mock_attempt_policy_is_stable_sorted_strict_and_formal_ineligible() -> None:
    value = policy()

    assert value.policy_id == "paper1.mock-attempt-policy.phase4b8c3"
    assert value.research_qa_ids == ("P1_MODEL_SEED_PAIRING", "P1_TIMEOUT_RETRY")
    assert value.allowed_difference_fields == (
        "model_seed",
        "request_parameters.temperature",
    )
    assert MockAttemptPolicyBinding.from_payload(value.to_payload()) == value
    with pytest.raises(ValueError, match="formal"):
        value.require_formal_eligible()
    with pytest.raises(ValueError, match="sorted"):
        MockAttemptPolicyBinding.create(
            allowed_difference_fields=("request_parameters.temperature", "model_seed"),
            mock_only=True,
            formal_eligible=False,
        )
    with pytest.raises(ValueError, match="allowed difference"):
        MockAttemptPolicyBinding.create(
            allowed_difference_fields=("prompt_view_hash",),
            mock_only=True,
            formal_eligible=False,
        )


def test_policy_and_adapter_binding_reject_extra_or_tampered_payload_fields() -> None:
    value = policy()
    extra = value.to_payload()
    extra["extra"] = True
    with pytest.raises(ValueError, match="fields"):
        MockAttemptPolicyBinding.from_payload(extra)
    tampered = value.to_payload()
    tampered["allowed_difference_fields"].append("request_parameters.top_p")
    with pytest.raises(ValueError, match="hash"):
        MockAttemptPolicyBinding.from_payload(tampered)

    value = prepared(RUN_ID, ordinal=9)
    adapter = adapter_for(value.authorization.event_id)
    binding = adapter_binding(adapter)
    assert binding.binding_id.startswith("adapter-execution-binding-")
    assert MockAdapterExecutionBinding.from_payload(binding.to_payload()) == binding
    with pytest.raises(ValueError, match="kind"):
        MockAdapterExecutionBinding.create(
            expected_adapter_kind="wrong_adapter",
            expected_adapter_version="1.0.0",
            runtime_identity=binding.runtime_identity,
            model_identity=binding.model_identity,
            script_step_hashes=binding.script_step_hashes,
            mock_only=True,
        )
    forged = binding.to_payload()
    forged["runtime_identity"]["provider"] = "changed"
    with pytest.raises(ValueError, match="hash"):
        MockAdapterExecutionBinding.from_payload(forged)


def test_policy_and_adapter_binding_are_deeply_immutable_and_isolated() -> None:
    runtime = {
        "adapter": "deterministic_mock",
        "adapter_version": "1.0.0",
        "provider": "deterministic-mock",
        "runtime_version": "1.0.0",
    }
    model = {"model": "mock", "revision": "r1", "mode": "script_only"}
    script_step_hashes = {"event-example": ("a" * 64,)}
    binding = MockAdapterExecutionBinding.create(
        expected_adapter_kind="deterministic_mock",
        expected_adapter_version="1.0.0",
        runtime_identity=runtime,
        model_identity=model,
        script_step_hashes=script_step_hashes,
        mock_only=True,
    )
    runtime["provider"] = "mutated"
    model["revision"] = "mutated"
    script_step_hashes["event-example"] = ("b" * 64,)

    assert binding.runtime_identity["provider"] == "deterministic-mock"
    assert binding.model_identity["revision"] == "r1"
    assert binding.script_step_hashes["event-example"] == ("a" * 64,)
    assert binding.script_hash == canonical_payload_hash({"event-example": ("a" * 64,)})
    with pytest.raises(TypeError):
        binding.runtime_identity["provider"] = "x"  # type: ignore[index]
    with pytest.raises(TypeError):
        binding.script_step_hashes["event-example"] = ("c" * 64,)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        binding.script_hash = "b" * 64  # type: ignore[misc]


def test_adapter_binding_capability_is_private_and_not_serialized() -> None:
    value = prepared(RUN_ID, ordinal=9)
    adapter = adapter_for(value.authorization.event_id)
    binding = adapter.execution_binding()

    assert execution_evidence_module._has_trusted_mock_adapter_execution_binding(binding)
    restored = MockAdapterExecutionBinding.from_payload(binding.to_payload())
    assert restored == binding
    assert not execution_evidence_module._has_trusted_mock_adapter_execution_binding(restored)
    assert not hasattr(execution_evidence_module, "seal_mock_adapter_execution_binding")


def test_public_adapter_binding_factory_is_structural_but_untrusted() -> None:
    trusted = adapter_for(prepared(RUN_ID, ordinal=9).authorization.event_id).execution_binding()
    public = MockAdapterExecutionBinding.create(
        expected_adapter_kind=trusted.expected_adapter_kind,
        expected_adapter_version=trusted.expected_adapter_version,
        runtime_identity=trusted.runtime_identity,
        model_identity=trusted.model_identity,
        script_step_hashes=trusted.script_step_hashes,
        mock_only=True,
    )

    assert public == trusted
    assert not execution_evidence_module._has_trusted_mock_adapter_execution_binding(public)


def test_event_input_evidence_round_trip_hash_binding_and_deep_immutability() -> None:
    value = event_inputs()

    assert value.event_id == value.prompt_view.event_id
    assert value.receiver_agent_id == value.prompt_view.agent_id
    assert value.exposure_selection.selection_id == value.exposure_record.selection_id
    assert EventInputEvidence.from_payload(value.to_payload()) == value
    payload = value.to_payload()
    payload["prompt_view"]["agent_id"] = "agent-other"
    with pytest.raises(ValueError):
        EventInputEvidence.from_payload(payload)
    with pytest.raises(FrozenInstanceError):
        value.publish_flag = False  # type: ignore[misc]


def test_event_input_rejects_cross_identity_and_non_boolean_publish_flag() -> None:
    value = event_inputs()
    with pytest.raises(ValueError, match="receiver|memory"):
        replace(value, receiver_agent_id="agent-other")
    with pytest.raises(TypeError, match="publish_flag"):
        replace(value, publish_flag=1)  # type: ignore[arg-type]


def test_event_input_rejects_rehashed_exposure_projection_semantic_drift() -> None:
    value = event_inputs()
    exposure_payload = value.exposure_record.to_payload()
    exposure_payload["cursor_before_hash"] = "f" * 64
    exposure_payload["record_hash"] = canonical_payload_hash(
        {name: item for name, item in exposure_payload.items() if name != "record_hash"}
    )
    exposure = ExposureRecord.from_payload(exposure_payload)
    prompt_payload = value.prompt_view.to_payload()
    prompt_payload["exposure_hash"] = exposure.record_hash
    prompt_payload["record_hash"] = canonical_payload_hash(
        {name: item for name, item in prompt_payload.items() if name != "record_hash"}
    )
    outer = value.to_payload()
    outer["exposure_record"] = exposure.to_payload()
    outer["prompt_view"] = prompt_payload
    outer["record_hash"] = canonical_payload_hash(
        {name: item for name, item in outer.items() if name != "record_hash"}
    )

    with pytest.raises(ValueError, match="projection|selection|cursor"):
        EventInputEvidence.from_payload(outer)


def test_event_input_rejects_cross_ordinal_selection_exposure_and_prompt() -> None:
    value = event_inputs()
    from test_prompt import exposure_inputs

    sources = exposure_inputs()
    selection = select_unread_feed(
        unread_public_posts=sources["unread_public_posts"],
        topic_package=topic(),
        neighbor_agent_ids=sources["neighbor_agent_ids"],
        cursor=sources["feed_cursor"],
        receiver_event_id=value.event_id,
        receiver_event_ordinal=10,
        matched_seed=17,
        exposure_mode="ws_neighbors",
        exposure_graph_hash="b" * 64,
        capacity=4,
        mock_only=True,
    )
    exposure = build_exposure_record(selection, topic_package=topic(), mock_only=True)
    prompt_payload = value.prompt_view.to_payload()
    event_payload = dict(prompt_payload["event_payload"])
    event_payload["exposure_id"] = exposure.exposure_id
    prompt_payload["event_payload"] = event_payload
    prompt_payload["event_hash"] = canonical_payload_hash(event_payload)
    prompt_payload["exposure_id"] = exposure.exposure_id
    prompt_payload["exposure_hash"] = exposure.record_hash
    prompt_payload["record_hash"] = canonical_payload_hash(
        {name: item for name, item in prompt_payload.items() if name != "record_hash"}
    )
    prompt = type(value.prompt_view).from_payload(prompt_payload)

    with pytest.raises(ValueError, match="ordinal"):
        EventInputEvidence.create(
            exposure_selection=selection,
            exposure_record=exposure,
            memory_view=value.memory_view,
            prompt_view=prompt,
            parser_limits=value.parser_limits,
            state_context_hash=value.state_context_hash,
            publish_flag=value.publish_flag,
        )


def test_persisted_invocation_preserves_complete_response_and_execution_payload() -> None:
    _, _, result, request = success_chain()
    execution = {
        "started_at": result.evidence.started_at,
        "finished_at": result.evidence.finished_at,
        "http_status": result.evidence.http_status,
        "provider_metadata": dict(result.evidence.provider_metadata),
        "usage": dict(result.evidence.usage),
        "finish_reason": result.evidence.finish_reason,
    }
    evidence = PersistedInvocationEvidence.create(
        response=result.response,
        execution_payload=execution,
        request_hash=request.record_hash,
        parser_limits_hash=parser_limits().record_hash,
        attempt_policy_hash=policy().record_hash,
        adapter_execution_binding_hash=adapter_binding(adapter_for(request.event_id)).record_hash,
    )

    assert evidence.response.raw_response == result.response.raw_response
    assert evidence.execution_payload["usage"] == result.evidence.usage
    assert PersistedInvocationEvidence.from_payload(evidence.to_payload()) == evidence
    execution["usage"]["total_tokens"] = 999
    assert evidence.execution_payload["usage"]["total_tokens"] == 7
    with pytest.raises(TypeError):
        evidence.execution_payload["usage"]["total_tokens"] = 1  # type: ignore[index]
    assert replace(evidence) == evidence


def test_persisted_invocation_rejects_cross_bindings_and_payload_tamper() -> None:
    _, _, result, request = success_chain()
    execution = {
        "started_at": NOW,
        "finished_at": NOW,
        "http_status": 200,
        "provider_metadata": response_metadata(result.response),
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "finish_reason": "stop",
    }
    with pytest.raises(ValueError, match="request"):
        PersistedInvocationEvidence.create(
            response=result.response,
            execution_payload=execution,
            request_hash="f" * 64,
            parser_limits_hash=parser_limits().record_hash,
            attempt_policy_hash=policy().record_hash,
            adapter_execution_binding_hash="e" * 64,
        )


def timeout_chain() -> tuple[object, object, GenerationAttempt]:
    value = prepared(RUN_ID, ordinal=9)
    adapter = MockAdapter(
        script={value.authorization.event_id: (MockScriptStep.timeout("provider timeout"),)},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    response = adapter.generate(value.request)
    payload = value.in_progress_attempt.to_payload()
    payload.update(
        {
            "status": "failed",
            "provider_request_id": response.provider_request_id,
            "provider_metadata": response_metadata(response),
            "provider_metadata_hash": canonical_payload_hash(response_metadata(response)),
            "http_status": None,
            "raw_response": None,
            "raw_response_hash": None,
            "parsed_response": None,
            "parsed_response_hash": None,
            "usage": {},
            "usage_hash": canonical_payload_hash({}),
            "finish_reason": None,
            "error": dict(response.error),
            "finished_at": NOW,
        }
    )
    attempt = GenerationAttempt.from_payload(payload)
    return value, response, attempt


def test_timeout_parse_not_applicable_is_explicit_hash_bound_and_strict() -> None:
    value, response, _ = timeout_chain()
    evidence = ParseNotApplicableEvidence.create(
        response=response,
        parser_limits_hash=parser_limits().record_hash,
    )

    assert evidence.outcome == "timeout"
    assert evidence.reason == "adapter_timeout_no_response"
    assert evidence.error_hash == canonical_payload_hash(response.error)
    assert evidence.attempt_id == value.request.attempt_id
    assert ParseNotApplicableEvidence.from_payload(evidence.to_payload()) == evidence
    assert replace(evidence) == evidence
    mutable_error = dict(evidence.error)
    copied = ParseNotApplicableEvidence(
        evidence_id=evidence.evidence_id,
        attempt_id=evidence.attempt_id,
        request_id=evidence.request_id,
        request_hash=evidence.request_hash,
        response_id=evidence.response_id,
        response_hash=evidence.response_hash,
        outcome=evidence.outcome,
        error=mutable_error,
        error_hash=evidence.error_hash,
        parser_limits_hash=evidence.parser_limits_hash,
        reason=evidence.reason,
        record_hash=evidence.record_hash,
    )
    mutable_error["message"] = "mutated after construction"
    assert copied.error == evidence.error
    tampered = evidence.to_payload()
    tampered["reason"] = "different"
    with pytest.raises(ValueError):
        ParseNotApplicableEvidence.from_payload(tampered)


def test_finalized_attempt_enforces_success_failure_and_timeout_consistency() -> None:
    succeeded, parse, _, _ = success_chain()
    success = FinalizedAttemptEvidence.create(
        request_hash=parse.request_hash,
        attempt=succeeded,
        parse_evidence=parse,
        terminal_failure_evidence=None,
    )
    assert FinalizedAttemptEvidence.from_payload(success.to_payload()) == success
    with pytest.raises(ValueError, match="failure"):
        replace(success, terminal_failure_evidence=failure_evidence(succeeded))

    _, response, failed = timeout_chain()
    not_applicable = ParseNotApplicableEvidence.create(
        response=response,
        parser_limits_hash=parser_limits().record_hash,
    )
    failure = FinalizedAttemptEvidence.create(
        request_hash=not_applicable.request_hash,
        attempt=failed,
        parse_evidence=not_applicable,
        terminal_failure_evidence=failure_evidence(failed),
    )
    assert FinalizedAttemptEvidence.from_payload(failure.to_payload()) == failure
    with pytest.raises(ValueError, match="failure"):
        FinalizedAttemptEvidence.create(
            request_hash=not_applicable.request_hash,
            attempt=failed,
            parse_evidence=not_applicable,
            terminal_failure_evidence=None,
        )
    with pytest.raises(ValueError, match="timeout|parse"):
        FinalizedAttemptEvidence.create(
            request_hash=not_applicable.request_hash,
            attempt=succeeded,
            parse_evidence=not_applicable,
            terminal_failure_evidence=None,
        )
    forged_payload = failed.to_payload()
    forged_metadata = dict(forged_payload["provider_metadata"])
    forged_metadata["adapter_response_hash"] = "f" * 64
    forged_payload["provider_metadata"] = forged_metadata
    forged_payload["provider_metadata_hash"] = canonical_payload_hash(forged_metadata)
    forged = GenerationAttempt.from_payload(forged_payload)
    with pytest.raises(ValueError, match="response"):
        FinalizedAttemptEvidence.create(
            request_hash=not_applicable.request_hash,
            attempt=forged,
            parse_evidence=not_applicable,
            terminal_failure_evidence=failure_evidence(forged),
        )


@pytest.mark.parametrize("kind", ("response", "timeout"))
def test_finalized_attempt_rejects_rehashed_contradictory_request_hash(kind: str) -> None:
    if kind == "response":
        attempt, parse, _, _ = success_chain()
        payload = parse.to_payload()
        authoritative_request_hash = parse.request_hash
        payload["request_hash"] = "f" * 64
        drifted = type(parse).from_payload(rehash_parse_payload(payload))
        failure = None
    else:
        _, response, attempt = timeout_chain()
        parse = ParseNotApplicableEvidence.create(
            response=response,
            parser_limits_hash=parser_limits().record_hash,
        )
        authoritative_request_hash = parse.request_hash
        payload = parse.to_payload()
        payload["request_hash"] = "f" * 64
        payload["record_hash"] = canonical_payload_hash(
            {name: value for name, value in payload.items() if name != "record_hash"}
        )
        drifted = ParseNotApplicableEvidence.from_payload(payload)
        failure = failure_evidence(attempt)

    with pytest.raises(ValueError, match="request_hash|request hash"):
        FinalizedAttemptEvidence.create(
            request_hash=authoritative_request_hash,
            attempt=attempt,
            parse_evidence=drifted,
            terminal_failure_evidence=failure,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (("event_id", "event-other"), ("attempt_index", 2)),
)
def test_finalized_attempt_rejects_parse_event_and_attempt_index_mismatch(
    field: str, value: object
) -> None:
    succeeded, parse, _, _ = success_chain()
    payload = parse.to_payload()
    payload[field] = value
    drifted = type(parse).from_payload(rehash_parse_payload(payload))

    with pytest.raises(ValueError, match="event|index"):
        FinalizedAttemptEvidence.create(
            request_hash=drifted.request_hash,
            attempt=succeeded,
            parse_evidence=drifted,
            terminal_failure_evidence=None,
        )


def test_finalized_attempt_rejects_timeout_error_message_or_hash_mismatch() -> None:
    _, response, failed = timeout_chain()
    not_applicable = ParseNotApplicableEvidence.create(
        response=response,
        parser_limits_hash=parser_limits().record_hash,
    )
    payload = failed.to_payload()
    payload["error"] = {"code": "timeout", "message": "different timeout"}
    drifted = GenerationAttempt.from_payload(payload)

    with pytest.raises(ValueError, match="timeout.*error|error.*timeout"):
        FinalizedAttemptEvidence.create(
            request_hash=not_applicable.request_hash,
            attempt=drifted,
            parse_evidence=not_applicable,
            terminal_failure_evidence=failure_evidence(drifted),
        )


def test_finalized_attempt_rejects_failed_parse_structured_error_mismatch() -> None:
    raw = '{"stance":"label-2","confidence":3}'
    response, request, _ = parser_response(raw)
    parse = parse_agent_update(response, topic_package=topic(), limits=parser_limits())
    assert parse.success is False and parse.error is not None
    payload = {
        "attempt_id": request.attempt_id,
        "event_id": request.event_id,
        "attempt_index": request.attempt_index,
        "status": "failed",
        "request_id": request.request_id,
        "exposure_id": build_prompt().exposure_id,
        "rendered_messages": request.to_payload()["rendered_messages"],
        "rendered_prompt_hash": request.rendered_messages_hash,
        "request_parameters": {"temperature": 0.0},
        "request_parameters_hash": canonical_payload_hash({"temperature": 0.0}),
        "model_identity": dict(response.model_identity),
        "model_identity_hash": response.model_identity_hash,
        "model_seed": request.mock_seed,
        "provider_request_id": response.provider_request_id,
        "provider_metadata": response_metadata(response),
        "provider_metadata_hash": canonical_payload_hash(response_metadata(response)),
        "http_status": 200,
        "raw_response": response.raw_response,
        "raw_response_hash": response.raw_response_hash,
        "parsed_response": None,
        "parsed_response_hash": None,
        "usage": {},
        "usage_hash": canonical_payload_hash({}),
        "finish_reason": "stop",
        "error": dict(parse.error),
        "started_at": NOW,
        "finished_at": NOW,
    }
    failed = GenerationAttempt.from_payload(payload)
    exact = FinalizedAttemptEvidence.create(
        request_hash=parse.request_hash,
        attempt=failed,
        parse_evidence=parse,
        terminal_failure_evidence=failure_evidence(failed),
    )
    assert FinalizedAttemptEvidence.from_payload(exact.to_payload()) == exact

    payload["error"] = {"code": "different", "message": "different parse failure"}
    failed = GenerationAttempt.from_payload(payload)

    with pytest.raises(ValueError, match="parse.*error|error.*parse"):
        FinalizedAttemptEvidence.create(
            request_hash=parse.request_hash,
            attempt=failed,
            parse_evidence=parse,
            terminal_failure_evidence=failure_evidence(failed),
        )


@pytest.mark.parametrize("field", ("terminal_transition_hash", "terminal_attempt_hash"))
def test_finalized_attempt_rejects_terminal_failure_hash_mismatch(field: str) -> None:
    _, response, failed = timeout_chain()
    not_applicable = ParseNotApplicableEvidence.create(
        response=response,
        parser_limits_hash=parser_limits().record_hash,
    )
    evidence = failure_evidence(failed)
    payload = evidence.to_payload()
    payload[field] = "f" * 64
    drifted = TerminalFailureEvidence.from_payload(payload)

    with pytest.raises(ValueError, match="terminal failure|transition|attempt"):
        FinalizedAttemptEvidence.create(
            request_hash=not_applicable.request_hash,
            attempt=failed,
            parse_evidence=not_applicable,
            terminal_failure_evidence=drifted,
        )


def test_event_evidence_references_validate_pairs_prefixes_round_trip_and_strict_fields() -> None:
    refs = EventEvidenceReferences.create(
        event_input_evidence_id="event-input-1",
        event_input_evidence_hash="a" * 64,
        request_id="adapter-request-1",
        request_hash="b" * 64,
        invocation_evidence_id="invocation-evidence-1",
        invocation_evidence_hash="c" * 64,
        parse_evidence_id=None,
        parse_evidence_hash=None,
        terminal_attempt_id=None,
        terminal_attempt_hash=None,
        committed_event_id=None,
        committed_event_hash=None,
    )
    assert EventEvidenceReferences.from_payload(refs.to_payload()) == refs
    with pytest.raises(FrozenInstanceError):
        refs.request_id = "adapter-request-other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="paired"):
        replace(refs, invocation_evidence_hash=None)
    with pytest.raises(ValueError, match="prefix"):
        replace(refs, event_input_evidence_id=None, event_input_evidence_hash=None)
    payload = refs.to_payload()
    payload["extra"] = None
    with pytest.raises(ValueError, match="fields"):
        EventEvidenceReferences.from_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    (("request_id", "adapter-request-tampered"), ("request_hash", "f" * 64)),
)
def test_event_evidence_references_reject_tamper_without_root_rehash(
    field: str, value: str
) -> None:
    refs = EventEvidenceReferences.create(
        event_input_evidence_id="event-input-1",
        event_input_evidence_hash="a" * 64,
        request_id="adapter-request-1",
        request_hash="b" * 64,
        invocation_evidence_id=None,
        invocation_evidence_hash=None,
        parse_evidence_id=None,
        parse_evidence_hash=None,
        terminal_attempt_id=None,
        terminal_attempt_hash=None,
        committed_event_id=None,
        committed_event_hash=None,
    )
    payload = refs.to_payload()
    payload[field] = value

    with pytest.raises(ValueError, match="record_hash|canonical"):
        EventEvidenceReferences.from_payload(payload)


def test_json_round_trips_use_strict_transport_payloads() -> None:
    values = [policy(), event_inputs()]
    for value in values:
        payload = json.loads(json.dumps(value.to_payload()))
        assert type(value).from_payload(payload) == value
