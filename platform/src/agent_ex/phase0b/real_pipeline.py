"""Shared network-event input bridged to diagnostic-v2 real-provider evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from ..domain import EventStatus, GenerationAttempt, RunManifest, canonical_payload_hash
from ..execution_evidence import (
    DiagnosticAdapterRequestEvidence,
    DiagnosticParseEvidence,
    DiagnosticPersistedInvocationEvidence,
    EventInputEvidence,
)
from ..parser import ParserLimits
from ..pipeline import MockEventPipeline
from ..prompt import PromptLimits, render_messages
from ..storage import RunStorage
from ..topic import TopicPackage
from .contracts import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
)
from .vllm_event_adapter import (
    Phase0BDispatchJournal,
    Phase0BVllmEventAdapter,
    Phase0BVllmEventRequest,
    Phase0BVllmEventResponse,
)


@dataclass(frozen=True, slots=True)
class PreparedRealDiagnosticEvent:
    """A durable PENDING request for one actually scheduled N=20 agent."""

    event_input: EventInputEvidence
    request: Phase0BVllmEventRequest
    request_evidence: DiagnosticAdapterRequestEvidence
    pending_attempt: GenerationAttempt


def prepare_real_diagnostic_event(
    *,
    storage: RunStorage,
    input_pipeline: MockEventPipeline,
    manifest: RunManifest,
    authorization: DiagnosticRunAuthorization,
    policy: DiagnosticAttemptPolicy,
    adapter_binding: DiagnosticAdapterBinding,
    parser_limits: ParserLimits,
    prompt_limits: PromptLimits,
) -> PreparedRealDiagnosticEvent:
    """Persist one real request without dispatching or advancing dynamics.

    The shared input builder uses synthetic/not-frozen Phase 4B research
    artifacts. The request and execution evidence are diagnostic-v2, never
    scripted mock-adapter records.
    """

    if input_pipeline.run_id != storage.binding.run_id or manifest.run_id != storage.binding.run_id:
        raise ValueError("diagnostic input pipeline, manifest, and storage run IDs differ")
    if manifest.run_spec.get("diagnostic_authorization_hash") != authorization.record_hash:
        raise ValueError("diagnostic manifest authorization hash drifted")
    if manifest.run_spec.get("adapter_binding_hash") != adapter_binding.record_hash:
        raise ValueError("diagnostic manifest adapter binding hash drifted")
    if authorization.adapter_binding_hash != adapter_binding.record_hash:
        raise ValueError("diagnostic authorization adapter binding hash drifted")
    if authorization.attempt_policy_hash != policy.record_hash:
        raise ValueError("diagnostic authorization attempt policy hash drifted")
    if authorization.model_seed_pairing_rule != "sha256-v1:matched-seed+cell-id+event-id":
        raise ValueError("diagnostic model-seed pairing rule is unsupported")
    if manifest.matched_seed != authorization.matched_seed:
        raise ValueError("diagnostic manifest matched seed drifted")
    if manifest.model_identity.get("revision") != adapter_binding.model_revision or (
        manifest.model_identity.get("served_model_name") != adapter_binding.served_model_name
    ):
        raise ValueError("diagnostic manifest model identity drifted")
    expected_settings = {
        "temperature": authorization.temperature,
        "top_p": authorization.top_p,
        "max_tokens": authorization.max_tokens,
    }
    if manifest.run_spec.get("request_parameters") != {
        **expected_settings,
        "enable_thinking": False,
    }:
        raise ValueError("diagnostic manifest generation settings drifted")

    journal = storage.current_event_journal()
    if journal.event_id is None or journal.event_ordinal is None:
        raise ValueError("diagnostic run has no next event")
    if journal.next_attempt_index != 1 or journal.latest_transition is not None:
        raise ValueError("diagnostic preparation requires a fresh, unattempted event")
    event_input = input_pipeline.prepare_event_input(
        journal=journal,
        feed_capacity=authorization.feed_capacity_candidate,
        memory_window=authorization.memory_window_candidate,
        parser_limits=parser_limits,
        prompt_limits=prompt_limits,
    )
    cell_id = manifest.run_spec.get("cell_id")
    if not isinstance(cell_id, str) or cell_id not in authorization.cell_ids:
        raise ValueError("diagnostic manifest cell is not authorized")
    model_seed = int(
        canonical_payload_hash(
            {
                "matched_seed": authorization.matched_seed,
                "cell_id": cell_id,
                "event_id": journal.event_id,
                "rule": authorization.model_seed_pairing_rule,
            }
        )[:15],
        16,
    )
    request = Phase0BVllmEventRequest.create(
        event_id=journal.event_id,
        attempt_index=1,
        prompt_hash=event_input.prompt_view.record_hash,
        rendered_messages=render_messages(event_input.prompt_view),
        generation_settings=expected_settings,
        model_seed=model_seed,
        adapter_binding_hash=adapter_binding.record_hash,
    )
    request_evidence = DiagnosticAdapterRequestEvidence.create(
        request=request,
        run_authorization_hash=authorization.record_hash,
        parser_limits_hash=parser_limits.record_hash,
        attempt_policy_hash=policy.record_hash,
        adapter_binding=adapter_binding,
    )
    pending = GenerationAttempt(
        attempt_id=request.attempt_id,
        event_id=request.event_id,
        attempt_index=request.attempt_index,
        status=EventStatus.PENDING,
        request_id=request.request_id,
        exposure_id=event_input.exposure_record.exposure_id,
        rendered_messages=request.rendered_messages,
        rendered_prompt_hash=request.rendered_messages_hash,
        request_parameters=request.generation_settings,
        request_parameters_hash=request.generation_settings_hash,
        model_identity=request_evidence.model_identity,
        model_identity_hash=request_evidence.model_identity_hash,
        model_seed=model_seed,
        provider_request_id=None,
        provider_metadata={},
        provider_metadata_hash=canonical_payload_hash({}),
        http_status=None,
        raw_response=None,
        raw_response_hash=None,
        parsed_response=None,
        parsed_response_hash=None,
        usage={},
        usage_hash=canonical_payload_hash({}),
        finish_reason=None,
        error=None,
        started_at=None,
        finished_at=None,
    )
    storage.record_diagnostic_prepared_attempt(
        event_input,
        policy=policy,
        adapter_binding=adapter_binding,
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    return PreparedRealDiagnosticEvent(event_input, request, request_evidence, pending)


def finalize_real_diagnostic_response(
    *,
    storage: RunStorage,
    input_pipeline: MockEventPipeline,
    prepared: PreparedRealDiagnosticEvent,
    in_progress: GenerationAttempt,
    response: Phase0BVllmEventResponse,
    topic_package: TopicPackage,
) -> GenerationAttempt:
    """Persist one response and commit only a valid parsed network event.

    The caller must have recorded IN_PROGRESS and a pre-dispatch intent before
    invoking the real adapter. This function never sends or retries a request.
    """

    if not isinstance(response, Phase0BVllmEventResponse):
        raise TypeError("diagnostic response must be typed real-provider evidence")
    if (
        response.request_id != prepared.request.request_id
        or response.request_hash != prepared.request.record_hash
        or in_progress.attempt_id != prepared.request.attempt_id
        or in_progress.status is not EventStatus.IN_PROGRESS
        or storage.current_event_journal().latest_transition != in_progress
        or input_pipeline.run_id != storage.binding.run_id
    ):
        raise ValueError("diagnostic response does not bind the current IN_PROGRESS event")
    invocation = DiagnosticPersistedInvocationEvidence.create(
        response=response, request_evidence=prepared.request_evidence
    )
    storage.record_diagnostic_invocation_evidence(invocation)
    parsed = DiagnosticParseEvidence.create(
        response=response,
        topic_package=topic_package,
        parser_limits_hash=prepared.event_input.parser_limits.record_hash,
    )
    raw_text = response.raw_body.decode("utf-8", errors="replace")
    metadata = {"diagnostic_response_hash": response.record_hash}
    values: dict[str, object] = {
        "provider_request_id": response.provider_request_id,
        "provider_metadata": metadata,
        "provider_metadata_hash": canonical_payload_hash(metadata),
        "http_status": response.transport_evidence.http_status,
        "raw_response": raw_text,
        "raw_response_hash": canonical_payload_hash(raw_text),
        "usage": dict(response.usage),
        "usage_hash": canonical_payload_hash(response.usage),
        "finish_reason": response.finish_reason,
        "finished_at": response.transport_evidence.ended_at,
    }
    if parsed.success:
        values.update(
            {
                "status": EventStatus.SUCCEEDED,
                "parsed_response": dict(parsed.parsed_response or {}),
                "parsed_response_hash": canonical_payload_hash(parsed.parsed_response),
                "error": None,
            }
        )
    else:
        values.update(
            {
                "status": EventStatus.FAILED,
                "parsed_response": None,
                "parsed_response_hash": None,
                "error": {"code": parsed.error_code},
            }
        )
    terminal = replace(in_progress, **values)
    storage.record_diagnostic_finalized_attempt(terminal, parsed)
    if terminal.status is EventStatus.FAILED:
        policy = storage.attempt_policy_evidence(terminal.event_id)
        if not isinstance(policy, DiagnosticAttemptPolicy):
            raise ValueError("diagnostic failure lacks its bound attempt policy")
        storage.record_terminal_failure(
            event_id=terminal.event_id,
            reason="diagnostic_response_failed",
            policy_evidence={
                "policy_id": "phase0b-diagnostic-attempt-policy-v1",
                "policy_hash": policy.record_hash,
            },
            recorded_at=response.transport_evidence.ended_at,
        )
        return terminal
    commit = input_pipeline._build_commit(terminal)
    storage.commit_success(
        commit.event,
        final_attempt=terminal,
        private_update=commit.private_update,
        private_state=commit.private_state,
        feed_cursor=commit.feed_cursor,
        public_post=commit.public_post,
        latest_public_pointer=commit.latest_public_pointer,
    )
    input_pipeline._advance_run_context_after_commit(terminal.event_id)
    return terminal


def dispatch_real_diagnostic_event_once(
    *,
    storage: RunStorage,
    input_pipeline: MockEventPipeline,
    prepared: PreparedRealDiagnosticEvent,
    adapter: Phase0BVllmEventAdapter,
    policy: DiagnosticAttemptPolicy,
    topic_package: TopicPackage,
    dispatch_journal: Phase0BDispatchJournal,
    clock: Callable[[], str],
) -> GenerationAttempt:
    """Send exactly one prepared request; never auto-resend after uncertainty."""

    if not isinstance(adapter, Phase0BVllmEventAdapter):
        raise TypeError("real diagnostic dispatch requires a vLLM event adapter")
    dispatch_journal.assert_no_unresolved_dispatches()
    if storage.current_event_journal().latest_transition != prepared.pending_attempt:
        raise ValueError("diagnostic dispatch requires the exact durable PENDING attempt")
    in_progress = replace(
        prepared.pending_attempt,
        status=EventStatus.IN_PROGRESS,
        started_at=clock(),
    )
    storage.append_attempt(in_progress)
    adapter.bind_dispatch_journal(dispatch_journal.record_before_dispatch)
    response = adapter.generate(
        prepared.request,
        timeout_seconds=policy.total_timeout_seconds,
        connect_timeout_seconds=policy.connect_timeout_seconds,
        read_timeout_seconds=policy.read_timeout_seconds,
    )
    terminal = finalize_real_diagnostic_response(
        storage=storage,
        input_pipeline=input_pipeline,
        prepared=prepared,
        in_progress=in_progress,
        response=response,
        topic_package=topic_package,
    )
    dispatch_journal.record_resolution(response)
    return terminal
