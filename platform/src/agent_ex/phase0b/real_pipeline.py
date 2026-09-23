"""Shared network-event input bridged to diagnostic-v2 real-provider evidence."""

from __future__ import annotations

from contextlib import ExitStack, nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping

from ..checkpoint import (
    build_checkpoint,
    load_checkpoint,
    validate_checkpoint,
    write_checkpoint_atomic,
)
from ..domain import EventStatus, GenerationAttempt, RunManifest, canonical_payload_hash
from ..execution_evidence import (
    DiagnosticAdapterRequestEvidence,
    DiagnosticParseEvidence,
    DiagnosticPersistedInvocationEvidence,
    EventInputEvidence,
)
from ..mock_matrix import CANONICAL_CELL_IDS
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
from .matrix import (
    DiagnosticCellInputBundle,
    DiagnosticN20ArtifactFamily,
    DiagnosticN20MaterializedMatrix,
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


@dataclass(frozen=True, slots=True)
class RealDiagnosticMatrixSummary:
    """Sanitized inventory only; not a formal result or inferential analysis."""

    authorization_hash: str
    matrix_hash: str
    completed_cell_ids: tuple[str, ...]
    committed_event_count: int
    transport_count: int
    record_hash: str


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
        complete_parsed = {
            "topic_package_id": parsed.topic_package_id,
            "topic_package_hash": parsed.topic_package_hash,
            **dict(parsed.parsed_response or {}),
        }
        values.update(
            {
                "status": EventStatus.SUCCEEDED,
                "parsed_response": complete_parsed,
                "parsed_response_hash": canonical_payload_hash(complete_parsed),
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


def _build_real_input_pipeline(
    *,
    storage: RunStorage,
    cell: DiagnosticCellInputBundle,
    family: DiagnosticN20ArtifactFamily,
    clock: Callable[[], str],
) -> MockEventPipeline:
    return MockEventPipeline(
        storage=storage,
        manifest=cell.manifest,
        topic_package=family.topic_package,
        persona_template=family.persona_template,
        population_artifact=family.population_artifact,
        exposure_graph_artifact=cell.exposure_graph_artifact,
        source_ws_artifact=cell.source_ws_artifact,
        agent_node_mapping_artifact=cell.agent_node_mapping_artifact,
        round0_initialization_artifact=cell.round0_initialization_artifact,
        frozen_neighbor_agent_ids=cell.frozen_neighbor_agent_ids,
        clock=clock,
    )


def run_real_diagnostic_cell_events(
    *,
    storage: RunStorage,
    cell: DiagnosticCellInputBundle,
    family: DiagnosticN20ArtifactFamily,
    authorization: DiagnosticRunAuthorization,
    policy: DiagnosticAttemptPolicy,
    adapter_binding: DiagnosticAdapterBinding,
    parser_limits: ParserLimits,
    prompt_limits: PromptLimits,
    adapter_factory: Callable[[], Phase0BVllmEventAdapter],
    dispatch_journal: Phase0BDispatchJournal,
    checkpoint_root: Path,
    clock: Callable[[], str],
    start_ordinal: int,
    event_count: int,
    lease_already_owned: bool = False,
    before_event: Callable[[int], None] | None = None,
) -> tuple[GenerationAttempt, ...]:
    """Execute a bounded, strictly serial cell prefix; stop at first failure.

    This is an execution primitive, not the terminal 12-cell verifier or a
    resume policy. The caller must supply a fresh archive for each launch.
    """

    if (
        type(start_ordinal) is not int
        or type(event_count) is not int
        or event_count < 1
        or start_ordinal < 0
        or start_ordinal + event_count > 40
        or cell.manifest.schedule.count != 40
    ):
        raise ValueError("diagnostic cell prefix must fit exactly within its 40-event schedule")
    if storage.progress.next_event_ordinal != start_ordinal:
        raise ValueError("diagnostic cell storage cursor does not match requested prefix")
    if cell.manifest.run_id != storage.binding.run_id:
        raise ValueError("diagnostic cell manifest does not match its SQLite run")
    if authorization.artifact_hashes != family.authorization_artifact_hashes:
        raise ValueError("diagnostic artifact family differs from authorization")
    dispatch_journal.assert_no_unresolved_dispatches()
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    input_pipeline = _build_real_input_pipeline(
        storage=storage, cell=cell, family=family, clock=clock
    )
    terminals: list[GenerationAttempt] = []
    if lease_already_owned:
        storage.assert_run_lease_owned()
    with nullcontext() if lease_already_owned else storage.acquire_run_lease():
        for ordinal in range(start_ordinal, start_ordinal + event_count):
            if before_event is not None:
                before_event(ordinal)
            if storage.progress.next_event_ordinal != ordinal:
                raise ValueError("diagnostic event ordinal changed outside serial execution")
            prepared = prepare_real_diagnostic_event(
                storage=storage,
                input_pipeline=input_pipeline,
                manifest=cell.manifest,
                authorization=authorization,
                policy=policy,
                adapter_binding=adapter_binding,
                parser_limits=parser_limits,
                prompt_limits=prompt_limits,
            )
            adapter = adapter_factory()
            if not isinstance(adapter, Phase0BVllmEventAdapter):
                raise TypeError("diagnostic adapter factory must return a real vLLM adapter")
            if adapter.endpoint != adapter_binding.endpoint:
                raise ValueError("diagnostic adapter endpoint differs from authorization")
            terminal = dispatch_real_diagnostic_event_once(
                storage=storage,
                input_pipeline=input_pipeline,
                prepared=prepared,
                adapter=adapter,
                policy=policy,
                topic_package=family.topic_package,
                dispatch_journal=dispatch_journal,
                clock=clock,
            )
            terminals.append(terminal)
            if terminal.status is not EventStatus.SUCCEEDED:
                raise RuntimeError("diagnostic cell stopped at a failed real response")
            next_ordinal = storage.progress.next_event_ordinal
            if next_ordinal % 20 == 0:
                checkpoint_path = (
                    checkpoint_root / f"{cell.cell_id}-{next_ordinal:05d}.checkpoint.json"
                )
                if checkpoint_path.exists():
                    raise FileExistsError("diagnostic checkpoint target already exists")
                write_checkpoint_atomic(checkpoint_path, build_checkpoint(storage))
    return tuple(terminals)


def _verify_clean_diagnostic_cell_prefix(
    *,
    storage: RunStorage,
    cell: DiagnosticCellInputBundle,
    family: DiagnosticN20ArtifactFamily,
    authorization: DiagnosticRunAuthorization,
    policy: DiagnosticAttemptPolicy,
    adapter_binding: DiagnosticAdapterBinding,
    dispatch_journal: Phase0BDispatchJournal,
    checkpoint_root: Path,
    verify_storage_integrity: bool = True,
) -> int:
    """Refuse any prefix that cannot be proven committed exactly once."""

    if (
        authorization.artifact_hashes != family.authorization_artifact_hashes
        or authorization.matched_seed != family.matched_seed
        or authorization.adapter_binding_hash != adapter_binding.record_hash
        or authorization.attempt_policy_hash != policy.record_hash
        or cell.cell_id not in authorization.cell_ids
        or cell.manifest.run_spec.get("cell_id") != cell.cell_id
        or cell.manifest.run_spec.get("diagnostic_authorization_hash") != authorization.record_hash
        or cell.manifest.run_spec.get("adapter_binding_hash") != adapter_binding.record_hash
        or storage.binding.run_id != cell.manifest.run_id
        or storage.binding.manifest_hash != canonical_payload_hash(cell.manifest.to_payload())
    ):
        raise ValueError(
            "diagnostic resume authorization, matrix, binding, or run identity drifted"
        )
    if verify_storage_integrity:
        storage.verify_integrity()
    progress = storage.progress
    cursor = progress.next_event_ordinal
    if progress.expected_event_count != 40 or not 0 <= cursor <= 40:
        raise ValueError("diagnostic resume cursor differs from the 40-event schedule")
    current = storage.current_event_journal()
    if cursor < 40 and (current.latest_transition is not None or current.next_attempt_index != 1):
        raise RuntimeError("diagnostic resume refuses pending, IN_PROGRESS, or failed attempt")
    records = dispatch_journal._records()
    dispatch_journal.assert_no_unresolved_dispatches()
    if len(records["intents"]) != cursor or len(records["resolutions"]) != cursor:
        raise ValueError("diagnostic dispatch journal does not exact-cover committed prefix")
    expected_requests: set[str] = set()
    for ordinal in range(cursor):
        event = storage.event_at(ordinal)
        if (
            event is None
            or event.status is not EventStatus.SUCCEEDED
            or event.agent_id != cell.manifest.schedule.slots[ordinal].agent_id
        ):
            raise ValueError("diagnostic committed prefix differs from frozen schedule")
        attempts = storage.attempts_for_event(event.event_id)
        if len(attempts) != 1 or attempts[0].status is not EventStatus.SUCCEEDED:
            raise ValueError("diagnostic resume requires one successful attempt per event")
        attempt = attempts[0]
        request = storage.adapter_request_evidence(attempt.attempt_id)
        invocation = storage.invocation_evidence(attempt.attempt_id)
        parsed = storage.parse_evidence(attempt.attempt_id)
        if (
            not isinstance(request, DiagnosticAdapterRequestEvidence)
            or not isinstance(invocation, DiagnosticPersistedInvocationEvidence)
            or not isinstance(parsed, DiagnosticParseEvidence)
            or not parsed.success
            or request.run_authorization_hash != authorization.record_hash
            or request.adapter_execution_binding_hash != adapter_binding.record_hash
            or request.attempt_policy_hash != policy.record_hash
        ):
            raise ValueError("diagnostic committed prefix execution evidence drifted")
        intent = records["intents"].get(request.request_id)
        resolution = records["resolutions"].get(request.request_id)
        if (
            intent is None
            or resolution is None
            or intent["request_hash"] != request.request_hash
            or resolution["response_hash"] != invocation.response_hash
        ):
            raise ValueError("diagnostic dispatch evidence differs from committed prefix")
        expected_requests.add(request.request_id)
    if (
        set(records["intents"]) != expected_requests
        or set(records["resolutions"]) != expected_requests
    ):
        raise ValueError("diagnostic dispatch journal contains foreign requests")
    expected_checkpoints = {
        f"{cell.cell_id}-{ordinal:05d}.checkpoint.json" for ordinal in (20, 40) if ordinal <= cursor
    }
    actual_checkpoints = (
        {
            path.name
            for path in checkpoint_root.iterdir()
            if path.name.startswith(f"{cell.cell_id}-")
        }
        if checkpoint_root.is_dir()
        else set()
    )
    if actual_checkpoints != expected_checkpoints:
        raise ValueError("diagnostic checkpoint inventory differs from committed prefix")
    for name in expected_checkpoints:
        checkpoint = load_checkpoint(checkpoint_root / name)
        if (
            checkpoint.run_id != cell.manifest.run_id
            or checkpoint.next_event_ordinal != int(name.rsplit("-", 1)[1].split(".", 1)[0])
            or checkpoint.baseline_manifest_hash != storage.binding.manifest_hash
        ):
            raise ValueError("diagnostic checkpoint identity differs from committed prefix")
        freshness = validate_checkpoint(checkpoint, storage)
        if freshness != ("current" if checkpoint.next_event_ordinal == cursor else "stale"):
            raise ValueError("diagnostic checkpoint freshness differs from committed prefix")
    return cursor


def resume_real_diagnostic_cell_events(
    *,
    storage: RunStorage,
    cell: DiagnosticCellInputBundle,
    family: DiagnosticN20ArtifactFamily,
    authorization: DiagnosticRunAuthorization,
    policy: DiagnosticAttemptPolicy,
    adapter_binding: DiagnosticAdapterBinding,
    parser_limits: ParserLimits,
    prompt_limits: PromptLimits,
    adapter_factory: Callable[[], Phase0BVllmEventAdapter],
    dispatch_journal: Phase0BDispatchJournal,
    checkpoint_root: Path,
    clock: Callable[[], str],
    event_count: int,
) -> tuple[GenerationAttempt, ...]:
    """Resume only a fully evidenced success prefix; never retry ambiguity."""

    with storage.acquire_run_lease():
        cursor = _verify_clean_diagnostic_cell_prefix(
            storage=storage,
            cell=cell,
            family=family,
            authorization=authorization,
            policy=policy,
            adapter_binding=adapter_binding,
            dispatch_journal=dispatch_journal,
            checkpoint_root=checkpoint_root,
        )
        if cursor == 0:
            raise ValueError("diagnostic resume requires a known committed prefix")

        def before_event(ordinal: int) -> None:
            verified_cursor = _verify_clean_diagnostic_cell_prefix(
                storage=storage,
                cell=cell,
                family=family,
                authorization=authorization,
                policy=policy,
                adapter_binding=adapter_binding,
                dispatch_journal=dispatch_journal,
                checkpoint_root=checkpoint_root,
                verify_storage_integrity=False,
            )
            if verified_cursor != ordinal:
                raise ValueError("diagnostic cell cursor changed before dispatch")

        return run_real_diagnostic_cell_events(
            storage=storage,
            cell=cell,
            family=family,
            authorization=authorization,
            policy=policy,
            adapter_binding=adapter_binding,
            parser_limits=parser_limits,
            prompt_limits=prompt_limits,
            adapter_factory=adapter_factory,
            dispatch_journal=dispatch_journal,
            checkpoint_root=checkpoint_root,
            clock=clock,
            start_ordinal=cursor,
            event_count=event_count,
            lease_already_owned=True,
            before_event=before_event,
        )


def run_real_diagnostic_matrix_once(
    *,
    matrix: DiagnosticN20MaterializedMatrix,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    policy: DiagnosticAttemptPolicy,
    stores: Mapping[str, RunStorage],
    parser_limits: ParserLimits,
    prompt_limits: PromptLimits,
    adapter_factory: Callable[[str], Phase0BVllmEventAdapter],
    run_root: Path,
    clock: Callable[[], str],
) -> RealDiagnosticMatrixSummary:
    """Execute one fresh 12-cell N=20/T=2 run, stopping on any ambiguity.

    This one-shot primitive does not authorize a cloud launch, retry, or resume.
    Its archives remain preliminary and must pass a separate durable verifier.
    """

    if matrix.authorization_hash != authorization.record_hash:
        raise ValueError("diagnostic matrix authorization hash drifted")
    if matrix.adapter_binding_hash != adapter_binding.record_hash:
        raise ValueError("diagnostic matrix adapter binding hash drifted")
    if authorization.attempt_policy_hash != policy.record_hash:
        raise ValueError("diagnostic matrix policy hash drifted")
    if tuple(stores) != CANONICAL_CELL_IDS:
        raise ValueError("diagnostic matrix stores do not exact-cover the canonical cells")
    if any(stores[cell.cell_id].progress.next_event_ordinal != 0 for cell in matrix.cells):
        raise ValueError("diagnostic matrix one-shot run requires fresh SQLite cursors")
    if run_root.exists():
        raise FileExistsError("diagnostic matrix archive root already exists")
    run_root.mkdir(parents=True, exist_ok=False)
    checkpoints = run_root / "checkpoints"
    completed: list[str] = []
    for cell in matrix.cells:
        storage = stores[cell.cell_id]
        journal = Phase0BDispatchJournal(run_root / f"{cell.cell_id}.dispatch.jsonl")
        run_real_diagnostic_cell_events(
            storage=storage,
            cell=cell,
            family=matrix.family,
            authorization=authorization,
            policy=policy,
            adapter_binding=adapter_binding,
            parser_limits=parser_limits,
            prompt_limits=prompt_limits,
            adapter_factory=lambda cell_id=cell.cell_id: adapter_factory(cell_id),
            dispatch_journal=journal,
            checkpoint_root=checkpoints,
            clock=clock,
            start_ordinal=0,
            event_count=40,
        )
        if storage.progress.next_event_ordinal != 40 or journal.unresolved_request_ids():
            raise ValueError("diagnostic cell did not reach its verified terminal prefix")
        completed.append(cell.cell_id)
    content = {
        "authorization_hash": authorization.record_hash,
        "matrix_hash": matrix.matrix_hash,
        "completed_cell_ids": tuple(completed),
        "committed_event_count": 480,
        "transport_count": 480,
    }
    return RealDiagnosticMatrixSummary(
        **content,
        record_hash=canonical_payload_hash(content),
    )


def _canonical_materialized_matrix_hash(
    matrix: DiagnosticN20MaterializedMatrix,
) -> str:
    return canonical_payload_hash(
        {
            "authorization_hash": matrix.authorization_hash,
            "adapter_binding_hash": matrix.adapter_binding_hash,
            "cells": tuple(
                {
                    "cell_id": cell.cell_id,
                    "manifest_hash": canonical_payload_hash(cell.manifest.to_payload()),
                    "persona_hashes": tuple(
                        (agent_id, persona.output_hash)
                        for agent_id, persona in cell.rendered_personas.items()
                    ),
                    "neighbor_wiring": tuple(cell.frozen_neighbor_agent_ids.items()),
                }
                for cell in matrix.cells
            ),
        }
    )


def _resume_real_diagnostic_matrix_with_leases(
    *,
    matrix: DiagnosticN20MaterializedMatrix,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    policy: DiagnosticAttemptPolicy,
    stores: Mapping[str, RunStorage],
    parser_limits: ParserLimits,
    prompt_limits: PromptLimits,
    adapter_factory: Callable[[str], Phase0BVllmEventAdapter],
    run_root: Path,
    clock: Callable[[], str],
) -> RealDiagnosticMatrixSummary:
    """Resume a known clean matrix prefix after preflighting every cell.

    No request is sent until every durable store, journal and checkpoint is
    checked. Failed, pending and post-invocation attempts remain manual stops.
    """

    if matrix.matrix_hash != _canonical_materialized_matrix_hash(matrix):
        raise ValueError("diagnostic matrix hash differs from materialized cells")
    if (
        matrix.authorization_hash != authorization.record_hash
        or matrix.adapter_binding_hash != adapter_binding.record_hash
        or authorization.attempt_policy_hash != policy.record_hash
        or tuple(stores) != CANONICAL_CELL_IDS
        or not run_root.is_dir()
    ):
        raise ValueError("diagnostic resume matrix authority or archive differs")
    checkpoints = run_root / "checkpoints"
    cursors: dict[str, int] = {}
    for cell in matrix.cells:
        cursors[cell.cell_id] = _verify_clean_diagnostic_cell_prefix(
            storage=stores[cell.cell_id],
            cell=cell,
            family=matrix.family,
            authorization=authorization,
            policy=policy,
            adapter_binding=adapter_binding,
            dispatch_journal=Phase0BDispatchJournal(run_root / f"{cell.cell_id}.dispatch.jsonl"),
            checkpoint_root=checkpoints,
        )
    if not any(cursors.values()):
        raise ValueError("diagnostic resume requires a known committed matrix prefix")
    seen_incomplete = False
    for cell_id in CANONICAL_CELL_IDS:
        cursor = cursors[cell_id]
        if seen_incomplete and cursor:
            raise ValueError("diagnostic matrix cells are not a serial committed prefix")
        if cursor < 40:
            seen_incomplete = True
    expected_root = {f"{cell_id}.dispatch.jsonl" for cell_id, cursor in cursors.items() if cursor}
    if checkpoints.is_dir():
        expected_root.add("checkpoints")
    if {path.name for path in run_root.iterdir()} != expected_root:
        raise ValueError("diagnostic resume archive contains unexpected or missing outputs")
    expected_checkpoint_names = {
        f"{cell_id}-{ordinal:05d}.checkpoint.json"
        for cell_id, cursor in cursors.items()
        for ordinal in (20, 40)
        if ordinal <= cursor
    }
    if (
        checkpoints.is_dir()
        and {path.name for path in checkpoints.iterdir()} != expected_checkpoint_names
    ):
        raise ValueError("diagnostic resume checkpoint archive contains foreign outputs")

    # Constructor validates immutable manifest, graph, and neighbor wiring. Do
    # this for all cells before the first resumed provider invocation.
    for cell in matrix.cells:
        _build_real_input_pipeline(
            storage=stores[cell.cell_id], cell=cell, family=matrix.family, clock=clock
        )

    for cell in matrix.cells:
        cursor = cursors[cell.cell_id]
        if cursor == 40:
            continue
        storage = stores[cell.cell_id]
        journal = Phase0BDispatchJournal(run_root / f"{cell.cell_id}.dispatch.jsonl")

        def before_event(ordinal: int) -> None:
            verified_cursor = _verify_clean_diagnostic_cell_prefix(
                storage=storage,
                cell=cell,
                family=matrix.family,
                authorization=authorization,
                policy=policy,
                adapter_binding=adapter_binding,
                dispatch_journal=journal,
                checkpoint_root=checkpoints,
                verify_storage_integrity=False,
            )
            if verified_cursor != ordinal:
                raise ValueError("diagnostic cell cursor changed before dispatch")

        run_real_diagnostic_cell_events(
            storage=storage,
            cell=cell,
            family=matrix.family,
            authorization=authorization,
            policy=policy,
            adapter_binding=adapter_binding,
            parser_limits=parser_limits,
            prompt_limits=prompt_limits,
            adapter_factory=lambda cell_id=cell.cell_id: adapter_factory(cell_id),
            dispatch_journal=journal,
            checkpoint_root=checkpoints,
            clock=clock,
            start_ordinal=cursor,
            event_count=40 - cursor,
            lease_already_owned=True,
            before_event=before_event,
        )
    return verify_real_diagnostic_matrix(
        matrix=matrix,
        authorization=authorization,
        adapter_binding=adapter_binding,
        policy=policy,
        stores=stores,
        run_root=run_root,
    )


def resume_real_diagnostic_matrix(
    *,
    matrix: DiagnosticN20MaterializedMatrix,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    policy: DiagnosticAttemptPolicy,
    stores: Mapping[str, RunStorage],
    parser_limits: ParserLimits,
    prompt_limits: PromptLimits,
    adapter_factory: Callable[[str], Phase0BVllmEventAdapter],
    run_root: Path,
    clock: Callable[[], str],
) -> RealDiagnosticMatrixSummary:
    """Hold all twelve exclusive writer leases through preflight and execution."""

    if tuple(stores) != CANONICAL_CELL_IDS:
        raise ValueError("diagnostic matrix stores do not exact-cover canonical cells")
    if matrix.matrix_hash != _canonical_materialized_matrix_hash(matrix):
        raise ValueError("diagnostic matrix hash differs from materialized cells")
    with ExitStack() as leases:
        for cell_id in CANONICAL_CELL_IDS:
            leases.enter_context(stores[cell_id].acquire_run_lease())
        return _resume_real_diagnostic_matrix_with_leases(
            matrix=matrix,
            authorization=authorization,
            adapter_binding=adapter_binding,
            policy=policy,
            stores=stores,
            parser_limits=parser_limits,
            prompt_limits=prompt_limits,
            adapter_factory=adapter_factory,
            run_root=run_root,
            clock=clock,
        )


def verify_real_diagnostic_matrix(
    *,
    matrix: DiagnosticN20MaterializedMatrix,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    policy: DiagnosticAttemptPolicy,
    stores: Mapping[str, RunStorage],
    run_root: Path,
) -> RealDiagnosticMatrixSummary:
    """Recompute completion only from reopened SQLite and dispatch/checkpoint files."""

    if (
        matrix.authorization_hash != authorization.record_hash
        or matrix.adapter_binding_hash != adapter_binding.record_hash
        or authorization.attempt_policy_hash != policy.record_hash
        or tuple(stores) != CANONICAL_CELL_IDS
        or not run_root.is_dir()
    ):
        raise ValueError("diagnostic matrix verification authority or archive differs")
    for cell in matrix.cells:
        storage = stores[cell.cell_id]
        if (
            storage.binding.run_id != cell.manifest.run_id
            or storage.progress.next_event_ordinal != 40
        ):
            raise ValueError("diagnostic cell durable cursor or run identity is incomplete")
        journal = Phase0BDispatchJournal(run_root / f"{cell.cell_id}.dispatch.jsonl")
        records = journal._records()
        if (
            journal.unresolved_request_ids()
            or len(records["intents"]) != 40
            or len(records["resolutions"]) != 40
        ):
            raise ValueError("diagnostic dispatch journal does not exact-cover 40 events")
        for ordinal in range(40):
            event = storage.event_at(ordinal)
            if (
                event is None
                or event.status is not EventStatus.SUCCEEDED
                or event.agent_id != cell.manifest.schedule.slots[ordinal].agent_id
            ):
                raise ValueError("diagnostic event does not match successful schedule prefix")
            attempts = storage.attempts_for_event(event.event_id)
            if len(attempts) != 1 or attempts[0].status is not EventStatus.SUCCEEDED:
                raise ValueError("diagnostic one-shot event must have one successful attempt")
            attempt = attempts[0]
            request = storage.adapter_request_evidence(attempt.attempt_id)
            invocation = storage.invocation_evidence(attempt.attempt_id)
            parsed = storage.parse_evidence(attempt.attempt_id)
            if (
                not isinstance(request, DiagnosticAdapterRequestEvidence)
                or not isinstance(invocation, DiagnosticPersistedInvocationEvidence)
                or not isinstance(parsed, DiagnosticParseEvidence)
                or not parsed.success
                or request.run_authorization_hash != authorization.record_hash
                or request.adapter_execution_binding_hash != adapter_binding.record_hash
                or request.attempt_policy_hash != policy.record_hash
            ):
                raise ValueError("diagnostic durable execution evidence is incomplete")
            intent = records["intents"].get(request.request_id)
            resolution = records["resolutions"].get(request.request_id)
            if (
                intent is None
                or resolution is None
                or intent["request_hash"] != request.request_hash
                or resolution["response_hash"] != invocation.response_hash
            ):
                raise ValueError("diagnostic dispatch evidence differs from durable response")
        for ordinal in (20, 40):
            checkpoint = load_checkpoint(
                run_root / "checkpoints" / f"{cell.cell_id}-{ordinal:05d}.checkpoint.json"
            )
            if (
                checkpoint.run_id != cell.manifest.run_id
                or checkpoint.next_event_ordinal != ordinal
            ):
                raise ValueError("diagnostic checkpoint differs from cell schedule prefix")
    content = {
        "authorization_hash": authorization.record_hash,
        "matrix_hash": matrix.matrix_hash,
        "completed_cell_ids": CANONICAL_CELL_IDS,
        "committed_event_count": 480,
        "transport_count": 480,
    }
    return RealDiagnosticMatrixSummary(**content, record_hash=canonical_payload_hash(content))
