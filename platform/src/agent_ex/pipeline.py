"""Mock-only composition of one complete, evidence-backed event lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .adapters.base import AdapterRequest, AdapterResponse
from .adapters.mock import MockAdapter
from .domain import (
    EventStatus,
    FrozenSchedule,
    GenerationAttempt,
    GenerationEvent,
    RunManifest,
    canonical_payload_hash,
    derive_event_id,
)
from .engine import (
    AttemptAuthorization,
    AttemptExecutionEvidence,
    AttemptInvocationResult,
    AttemptOutcome,
    PreparedAttempt,
    StrictSerialLifecycleEngine,
    SuccessfulEventCommit,
)
from .execution_evidence import (
    AdapterRequestEvidence,
    EventEvidenceReferences,
    EventInputEvidence,
    FinalizedAttemptEvidence,
    MockAdapterExecutionBinding,
    MockAttemptPolicyBinding,
    ParseNotApplicableEvidence,
)
from .feed import build_exposure_record, select_unread_feed
from .memory import build_memory_view
from .mock_matrix import mock_adapter_semantics_hash
from .network import (
    build_agent_node_mapping,
    validate_shadow_artifact,
    validate_ws_artifact,
)
from .parser import ParserLimits, parse_agent_update
from .persona import render_persona
from .prompt import (
    PromptLimits,
    ValidatedPromptRunContext,
    advance_validated_prompt_run_context,
    build_prompt_view,
    rebuild_validated_prompt_run_context,
    validate_prompt_run_context,
)
from .state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from .storage import (
    EventJournalState,
    RunStorage,
    TerminalFailureEvidence,
    changed_request_parameter_paths,
)
from .topic import TopicPackage
from .artifacts import ArtifactEnvelope


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class MockEventPipelineOutcome:
    """Lifecycle result paired with the persisted evidence-prefix projection."""

    lifecycle: AttemptOutcome
    evidence: EventEvidenceReferences


class MockEventPipeline:
    """Compose public Phase 4B factories without selecting research defaults."""

    def __init__(
        self,
        *,
        storage: RunStorage,
        manifest: RunManifest,
        topic_package: TopicPackage,
        persona_template: ArtifactEnvelope,
        population_artifact: ArtifactEnvelope,
        exposure_graph_artifact: ArtifactEnvelope | None,
        source_ws_artifact: ArtifactEnvelope | None,
        agent_node_mapping_artifact: ArtifactEnvelope | None,
        round0_initialization_artifact: ArtifactEnvelope | None,
        frozen_neighbor_agent_ids: Mapping[str, tuple[str, ...]],
        clock: Callable[[], str],
    ) -> None:
        if not isinstance(manifest, RunManifest):
            raise TypeError("manifest must be a typed RunManifest")
        try:
            replayed_schedule = FrozenSchedule.from_payload(manifest.schedule.to_payload())
            replayed_manifest = RunManifest.from_payload(
                manifest.to_payload(), schedule=replayed_schedule
            )
        except (TypeError, ValueError) as error:
            raise ValueError("manifest or schedule fails strict typed replay") from error
        if replayed_manifest != manifest:
            raise ValueError("manifest or schedule drifts from strict typed replay")
        binding = storage.binding
        manifest_hash = canonical_payload_hash(manifest.to_payload())
        if binding.run_id != manifest.run_id or binding.manifest_hash != manifest_hash:
            raise ValueError("manifest does not exactly match the persisted storage binding")
        if (
            binding.schedule_hash != manifest.schedule_hash
            or binding.schedule_hash != manifest.schedule.schedule_hash
            or binding.schedule_count != manifest.schedule.count
        ):
            raise ValueError("manifest schedule does not match the persisted storage binding")
        if set(frozen_neighbor_agent_ids) != set(storage.binding.expected_agent_ids):
            raise ValueError("frozen neighbor mapping must exactly cover the run population")
        if (
            population_artifact.artifact_id not in binding.artifact_hashes
            or binding.artifact_hashes[population_artifact.artifact_id]
            != population_artifact.output_hash
        ):
            raise ValueError("population artifact is not hash-bound by storage")
        matched_seed = manifest.matched_seed
        cell_id = manifest.run_spec.get("cell_id")
        if not isinstance(cell_id, str):
            raise ValueError("persisted manifest cell_id must be text")
        request_parameters = manifest.run_spec.get("request_parameters")
        if not isinstance(request_parameters, Mapping):
            raise ValueError("persisted manifest request parameters must be a mapping")
        baseline_request_parameters = dict(request_parameters)
        changed_request_parameter_paths(baseline_request_parameters, baseline_request_parameters)
        neighbors = self._validate_frozen_neighbors(
            storage=storage,
            matched_seed=matched_seed,
            population_artifact=population_artifact,
            exposure_graph_artifact=exposure_graph_artifact,
            source_ws_artifact=source_ws_artifact,
            agent_node_mapping_artifact=agent_node_mapping_artifact,
            round0_initialization_artifact=round0_initialization_artifact,
            frozen_neighbor_agent_ids=frozen_neighbor_agent_ids,
        )
        self._storage = storage
        self._manifest = manifest
        self._matched_seed = matched_seed
        self._cell_id = cell_id
        self._manifest_model_identity = dict(manifest.model_identity)
        self._baseline_request_parameters = baseline_request_parameters
        self._topic_package = topic_package
        self._persona_template = persona_template
        self._population_artifact = population_artifact
        self._frozen_neighbor_agent_ids = neighbors
        self._clock = clock
        self._run_context: ValidatedPromptRunContext | None = None
        self._run_context_ordinal = -1
        self._source_events_by_id: dict[str, GenerationEvent] = {}
        self._source_attempts_by_id: dict[str, GenerationAttempt] = {}
        self._source_index_ordinal = 0
        self._validated_matrix_adapter_binding: MockAdapterExecutionBinding | None = None
        matrix_binding = manifest.run_spec.get("mock_matrix_binding")
        if matrix_binding is None:
            self._matrix_adapter_semantics_hash = None
            self._matrix_expected_event_ids: tuple[str, ...] = ()
        else:
            if not isinstance(matrix_binding, Mapping):
                raise TypeError("mock matrix binding must be a mapping")
            semantics_hash = matrix_binding.get("adapter_semantics_hash")
            if type(semantics_hash) is not str:
                raise ValueError("mock matrix adapter semantics hash must be text")
            self._matrix_adapter_semantics_hash = semantics_hash
            self._matrix_expected_event_ids = tuple(
                derive_event_id(manifest.run_id, ordinal)
                for ordinal in range(manifest.schedule.count)
            )

    @property
    def run_id(self) -> str:
        """Return the immutable constructor-bound run identity."""

        return self._manifest.run_id

    def execute(
        self,
        *,
        feed_capacity: int,
        memory_window: int,
        parser_limits: ParserLimits,
        prompt_limits: PromptLimits,
        policy: MockAttemptPolicyBinding,
        model_identity: Mapping[str, str],
        request_parameters: Mapping[str, object],
        model_seed: int,
        adapter: MockAdapter,
        http_status: int | None,
        usage: Mapping[str, object],
        finish_reason: str | None,
        reconciliation: AttemptInvocationResult | None,
    ) -> MockEventPipelineOutcome:
        binding = adapter.execution_binding()
        if (
            self._matrix_adapter_semantics_hash is not None
            and binding is not self._validated_matrix_adapter_binding
        ):
            if (
                mock_adapter_semantics_hash(binding, self._matrix_expected_event_ids)
                != self._matrix_adapter_semantics_hash
            ):
                raise ValueError(
                    "runtime adapter semantics do not match the frozen mock matrix binding"
                )
            self._validated_matrix_adapter_binding = binding
        if dict(model_identity) != dict(binding.model_identity):
            raise ValueError("explicit model identity must exactly match the adapter binding")
        complete_adapter_identity = {
            "provider": binding.runtime_identity["provider"],
            "model": binding.model_identity["model"],
            "revision": binding.model_identity["revision"],
            "runtime": binding.runtime_identity["runtime_version"],
            "mode": binding.model_identity["mode"],
        }
        if self._manifest_model_identity != complete_adapter_identity:
            raise ValueError(
                "persisted manifest model identity does not match the complete adapter binding"
            )

        prepared_by_attempt: dict[str, PreparedAttempt] = {}

        def prepare(journal: EventJournalState) -> PreparedAttempt:
            value = self._prepare(
                journal=journal,
                feed_capacity=feed_capacity,
                memory_window=memory_window,
                parser_limits=parser_limits,
                prompt_limits=prompt_limits,
                policy=policy,
                model_identity=model_identity,
                request_parameters=request_parameters,
                model_seed=model_seed,
                adapter_binding=binding,
            )
            prepared_by_attempt[value.request.attempt_id] = value
            return value

        def invoke(request: AdapterRequest) -> AttemptInvocationResult:
            response = adapter.generate(request)
            prepared = prepared_by_attempt[request.attempt_id]
            started_at = prepared.in_progress_attempt.started_at
            if started_at is None:
                raise ValueError("in-progress attempt is missing its explicit start time")
            return AttemptInvocationResult(
                response=response,
                evidence=AttemptExecutionEvidence(
                    started_at=started_at,
                    finished_at=self._clock(),
                    http_status=http_status,
                    provider_metadata=self._provider_metadata(response),
                    usage=usage,
                    finish_reason=finish_reason,
                ),
            )

        def finalize(
            prepared: PreparedAttempt, result: AttemptInvocationResult
        ) -> FinalizedAttemptEvidence:
            return self._finalize(prepared, result)

        with StrictSerialLifecycleEngine(self._storage) as engine:
            lifecycle = engine.execute(
                prepare=prepare,
                invoke=invoke,
                finalize=finalize,
                build_commit=self._build_commit,
                reconciliation=reconciliation,
            )

        if lifecycle.state == "committed" and lifecycle.event_id is not None:
            self._advance_run_context_after_commit(lifecycle.event_id)
        evidence = (
            self._storage.evidence_references(lifecycle.event_id)
            if lifecycle.event_id is not None
            else EventEvidenceReferences.create(
                event_input_evidence_id=None,
                event_input_evidence_hash=None,
                request_id=None,
                request_hash=None,
                invocation_evidence_id=None,
                invocation_evidence_hash=None,
                parse_evidence_id=None,
                parse_evidence_hash=None,
                terminal_attempt_id=None,
                terminal_attempt_hash=None,
                committed_event_id=None,
                committed_event_hash=None,
            )
        )
        return MockEventPipelineOutcome(lifecycle=lifecycle, evidence=evidence)

    def _prepare(
        self,
        *,
        journal: EventJournalState,
        feed_capacity: int,
        memory_window: int,
        parser_limits: ParserLimits,
        prompt_limits: PromptLimits,
        policy: MockAttemptPolicyBinding,
        model_identity: Mapping[str, str],
        request_parameters: Mapping[str, object],
        model_seed: int,
        adapter_binding: MockAdapterExecutionBinding,
    ) -> PreparedAttempt:
        ordinal = journal.event_ordinal
        if ordinal is None or journal.event_id is None:
            raise ValueError("preparation requires the current journal event")
        self._validate_request_parameters(
            journal=journal,
            request_parameters=request_parameters,
            policy=policy,
        )
        slot = self._storage.schedule_slot(ordinal)
        event = GenerationEvent(
            run_id=self._storage.binding.run_id,
            event_id=journal.event_id,
            event_ordinal=ordinal,
            sweep_index=slot.sweep_index,
            draw_index=slot.draw_index,
            agent_id=slot.agent_id,
            publish_flag=slot.publish_flag,
            exposure_id=f"exposure-{ordinal}",
            status=EventStatus.PENDING,
            attempt_ids=(),
            failure_reason=None,
        )
        state = self._storage.private_state(slot.agent_id)
        cursor = self._storage.feed_cursor(slot.agent_id)
        if state is None or cursor is None:
            raise ValueError("receiver state and feed cursor must be initialized")
        private_updates = self._storage.private_updates_for_agent(slot.agent_id)
        neighbors = self._frozen_neighbor_agent_ids[slot.agent_id]
        unread_posts = self._unread_public_posts(neighbors, cursor.last_scanned_event_ordinal)
        selection = select_unread_feed(
            unread_public_posts=unread_posts,
            topic_package=self._topic_package,
            neighbor_agent_ids=neighbors,
            cursor=cursor,
            receiver_event_id=event.event_id,
            receiver_event_ordinal=ordinal,
            matched_seed=self._matched_seed,
            exposure_mode=self._storage.binding.expected_exposure_mode,
            exposure_graph_hash=self._storage.binding.expected_exposure_graph_hash,
            capacity=feed_capacity,
            mock_only=True,
        )
        exposure = build_exposure_record(
            selection, topic_package=self._topic_package, mock_only=True
        )
        memory = build_memory_view(
            private_updates=private_updates,
            topic_package=self._topic_package,
            matched_seed=self._matched_seed,
            agent_id=slot.agent_id,
            window=memory_window,
            mock_only=True,
        )
        member = self._population_member(slot.agent_id)
        identity_present, continuity_present = self._persona_condition()
        persona = render_persona(
            self._persona_template,
            member,
            {
                "identity_present": identity_present,
                "continuity_present": continuity_present,
            },
        )
        source_events, source_attempts = self._source_indexes(ordinal)
        context = self._ensure_run_context(ordinal, source_events, source_attempts)
        public_posts_by_id = {post.post_id: post for post in unread_posts}
        all_neighbor_updates = {
            update.update_id: update
            for neighbor in neighbors
            for update in self._storage.private_updates_for_agent(neighbor)
            if update.published
        }
        candidate_update_ids = {candidate.source_update_id for candidate in selection.candidates}
        source_updates_by_id = {
            update_id: all_neighbor_updates[update_id] for update_id in candidate_update_ids
        }
        evidence_event_ids = {
            update.event_id for update in private_updates if update.event_id is not None
        } | {
            candidate.source_event_id
            for candidate in selection.candidates
            if candidate.source_event_id is not None
        }
        prompt_source_events = {
            event_id: source_events[event_id] for event_id in evidence_event_ids
        }
        evidence_attempt_ids = {
            attempt_id
            for event in prompt_source_events.values()
            for attempt_id in event.attempt_ids
        }
        prompt_source_attempts = {
            attempt_id: source_attempts[attempt_id] for attempt_id in evidence_attempt_ids
        }
        prompt = build_prompt_view(
            run_context=context,
            topic=self._topic_package,
            persona=persona,
            persona_template=self._persona_template,
            population_artifact=self._population_artifact,
            population_member=member,
            private_state=state,
            private_updates=private_updates,
            memory=memory,
            exposure=exposure,
            exposure_selection=selection,
            unread_public_posts=unread_posts,
            neighbor_agent_ids=neighbors,
            feed_cursor=cursor,
            public_posts_by_id=public_posts_by_id,
            source_private_updates_by_id=source_updates_by_id,
            source_events_by_id=prompt_source_events,
            source_attempts_by_id=prompt_source_attempts,
            event=event,
            matched_seed=self._matched_seed,
            cell_id=self._cell_id,
            limits=prompt_limits,
            mock_only=True,
        )
        request = AdapterRequest.create(
            prompt_view=prompt,
            attempt_index=journal.next_attempt_index,
            mock_seed=model_seed,
            mock_only=True,
        )
        request_evidence = AdapterRequestEvidence.create(
            request=request,
            model_identity=model_identity,
            request_parameters=request_parameters,
            model_seed=model_seed,
            prompt_limits_hash=prompt_limits.record_hash,
            parser_limits_hash=parser_limits.record_hash,
            attempt_policy_hash=policy.record_hash,
            adapter_execution_binding_hash=adapter_binding.record_hash,
        )
        event_input = EventInputEvidence.create(
            exposure_selection=selection,
            exposure_record=exposure,
            memory_view=memory,
            prompt_view=prompt,
            parser_limits=parser_limits,
            state_context_hash=canonical_payload_hash(
                {
                    "private_state": state.to_payload(),
                    "private_updates": tuple(item.to_payload() for item in private_updates),
                    "feed_cursor": cursor.to_payload(),
                }
            ),
            publish_flag=slot.publish_flag,
        )
        base = {
            "attempt_id": request.attempt_id,
            "event_id": event.event_id,
            "attempt_index": journal.next_attempt_index,
            "request_id": request.request_id,
            "exposure_id": exposure.exposure_id,
            "rendered_messages": request.rendered_messages,
            "rendered_prompt_hash": request.rendered_messages_hash,
            "request_parameters": request_parameters,
            "request_parameters_hash": canonical_payload_hash(request_parameters),
            "model_identity": model_identity,
            "model_identity_hash": canonical_payload_hash(model_identity),
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
        in_progress = GenerationAttempt(
            status=EventStatus.IN_PROGRESS, started_at=self._clock(), **base
        )
        authorization = self._storage.resume_authorization_evidence()
        return PreparedAttempt(
            authorization=AttemptAuthorization(
                run_id=self._storage.binding.run_id,
                event_id=event.event_id,
                event_ordinal=ordinal,
                attempt_index=journal.next_attempt_index,
                model_seed=model_seed,
                model_identity=model_identity,
                model_identity_hash=canonical_payload_hash(model_identity),
                request_parameters=request_parameters,
                request_parameters_hash=canonical_payload_hash(request_parameters),
                resume_authorization_hash=(
                    authorization.payload_hash
                    if journal.resume_state == "retry_same_event"
                    else None
                ),
                mock_only=True,
            ),
            request=request,
            pending_attempt=pending,
            in_progress_attempt=in_progress,
            context_provenance={
                "phase": "4B-8C-3",
                "event_input_evidence_hash": event_input.record_hash,
            },
            event_input=event_input,
            policy=policy,
            adapter_binding=adapter_binding,
            request_evidence=request_evidence,
        )

    def _finalize(
        self, prepared: PreparedAttempt, result: AttemptInvocationResult
    ) -> FinalizedAttemptEvidence:
        response = result.response
        execution = result.evidence
        payload = prepared.pending_attempt.to_payload()
        payload.update(
            {
                "provider_request_id": response.provider_request_id,
                "provider_metadata": _plain_json(execution.provider_metadata),
                "provider_metadata_hash": canonical_payload_hash(execution.provider_metadata),
                "http_status": execution.http_status,
                "usage": _plain_json(execution.usage),
                "usage_hash": canonical_payload_hash(execution.usage),
                "finish_reason": execution.finish_reason,
                "started_at": execution.started_at,
                "finished_at": execution.finished_at,
            }
        )
        if response.outcome == "timeout":
            parse = ParseNotApplicableEvidence.create(
                response=response,
                parser_limits_hash=prepared.event_input.parser_limits.record_hash,
            )
            payload.update(
                {
                    "status": EventStatus.FAILED.value,
                    "raw_response": None,
                    "raw_response_hash": None,
                    "parsed_response": None,
                    "parsed_response_hash": None,
                    "error": dict(response.error or {}),
                }
            )
            reason = "adapter_timeout"
        else:
            parse = parse_agent_update(
                response,
                topic_package=self._topic_package,
                limits=prepared.event_input.parser_limits,
            )
            payload["raw_response"] = response.raw_response
            payload["raw_response_hash"] = response.raw_response_hash
            if parse.success:
                if parse.parsed is None:
                    raise ValueError("successful parse lacks a typed parsed update")
                parsed = parse.parsed.to_payload()
                payload.update(
                    {
                        "status": EventStatus.SUCCEEDED.value,
                        "parsed_response": parsed,
                        "parsed_response_hash": canonical_payload_hash(parsed),
                        "error": None,
                    }
                )
                reason = None
            else:
                payload.update(
                    {
                        "status": EventStatus.FAILED.value,
                        "parsed_response": None,
                        "parsed_response_hash": None,
                        "error": dict(parse.error or {}),
                    }
                )
                reason = "parse_failure"
        terminal = GenerationAttempt.from_payload(payload)
        failure = (
            None if reason is None else self._failure_evidence(terminal, prepared.policy, reason)
        )
        return FinalizedAttemptEvidence.create(
            request_hash=prepared.request_evidence.request_hash,
            attempt=terminal,
            parse_evidence=parse,
            terminal_failure_evidence=failure,
        )

    def _build_commit(self, terminal: GenerationAttempt) -> SuccessfulEventCommit:
        ordinal = self._storage.progress.next_event_ordinal
        slot = self._storage.schedule_slot(ordinal)
        event_input = self._storage.event_input_evidence(terminal.event_id)
        if event_input is None:
            raise ValueError("commit reconstruction requires persisted event input evidence")
        parsed = terminal.parsed_response
        if parsed is None:
            raise ValueError("successful commit requires persisted parsed response")
        previous_state = self._storage.private_state(slot.agent_id)
        previous_pointer = self._storage.latest_public_pointer(slot.agent_id)
        if previous_state is None:
            raise ValueError("commit receiver private state is missing")
        update = PrivateUpdate.create(
            topic_package=self._topic_package,
            matched_seed=self._matched_seed,
            agent_id=slot.agent_id,
            event_id=terminal.event_id,
            event_ordinal=ordinal,
            sequence_index=previous_state.successful_update_count,
            stance_label=parsed["stance"],
            reason=parsed["public_reason"],
            confidence=parsed["confidence"],
            published=slot.publish_flag,
            source_attempt_id=terminal.attempt_id,
            mock_only=True,
        )
        state = PrivateState.from_update(update, previous=previous_state, mock_only=True)
        post = PublicPost.from_private_update(update, mock_only=True) if slot.publish_flag else None
        pointer = (
            LatestPublicPointer.from_post(post, previous=previous_pointer, mock_only=True)
            if post is not None
            else None
        )
        attempts = self._storage.attempts_for_event(terminal.event_id)
        attempt_ids = tuple(item.attempt_id for item in attempts)
        if terminal.attempt_id not in attempt_ids:
            attempt_ids = (*attempt_ids, terminal.attempt_id)
        event = GenerationEvent(
            run_id=self._storage.binding.run_id,
            event_id=terminal.event_id,
            event_ordinal=ordinal,
            sweep_index=slot.sweep_index,
            draw_index=slot.draw_index,
            agent_id=slot.agent_id,
            publish_flag=slot.publish_flag,
            exposure_id=event_input.exposure_record.exposure_id,
            status=EventStatus.SUCCEEDED,
            attempt_ids=attempt_ids,
            failure_reason=None,
        )
        return SuccessfulEventCommit(
            event=event,
            private_update=update,
            private_state=state,
            feed_cursor=event_input.exposure_selection.cursor_after,
            public_post=post,
            latest_public_pointer=pointer,
        )

    def _source_indexes(
        self, ordinal: int
    ) -> tuple[dict[str, GenerationEvent], dict[str, GenerationAttempt]]:
        if ordinal != self._storage.progress.next_event_ordinal:
            raise ValueError("source index ordinal drifts from persisted storage progress")
        self._extend_source_indexes(ordinal)
        return self._source_events_by_id, self._source_attempts_by_id

    def _extend_source_indexes(self, target_ordinal: int) -> None:
        persisted_ordinal = self._storage.progress.next_event_ordinal
        if target_ordinal > persisted_ordinal:
            raise ValueError("source index target exceeds persisted storage progress")
        if target_ordinal < self._source_index_ordinal:
            raise ValueError("source index ordinal moved behind the verified cache prefix")
        for prior in range(self._source_index_ordinal, target_ordinal):
            event = self._storage.event_at(prior)
            if event is None:
                raise ValueError("committed event prefix is incomplete")
            if event.event_ordinal != prior or event.event_id != derive_event_id(
                self._storage.binding.run_id, prior
            ):
                raise ValueError("committed event prefix identity drifts from storage ordinal")
            if event.event_id in self._source_events_by_id:
                raise ValueError("committed event prefix contains a duplicate event identity")
            event_attempts = self._storage.attempts_for_event(event.event_id)
            for attempt in event_attempts:
                if attempt.attempt_id in self._source_attempts_by_id:
                    raise ValueError("committed event prefix contains a duplicate attempt identity")
            self._source_events_by_id[event.event_id] = event
            for attempt in event_attempts:
                self._source_attempts_by_id[attempt.attempt_id] = attempt
            self._source_index_ordinal = prior + 1

    def _ensure_run_context(
        self,
        ordinal: int,
        events: Mapping[str, GenerationEvent],
        attempts: Mapping[str, GenerationAttempt],
    ) -> ValidatedPromptRunContext:
        if self._run_context is not None and self._run_context_ordinal == ordinal:
            return self._run_context
        if self._run_context is not None:
            self._run_context = None
            self._run_context_ordinal = -1
        baseline_ordinal = self._manifest.next_event_ordinal
        if baseline_ordinal == ordinal:
            self._run_context = validate_prompt_run_context(
                self._manifest,
                source_events_by_id=events,
                source_attempts_by_id=attempts,
            )
            self._run_context_ordinal = ordinal
            return self._run_context
        if baseline_ordinal != 0:
            raise ValueError("manifest recovery cursor does not match storage progress")
        self._run_context = validate_prompt_run_context(
            self._manifest,
            source_events_by_id={},
            source_attempts_by_id={},
        )
        self._run_context_ordinal = 0
        succeeded_events: list[GenerationEvent] = []
        for prior in range(ordinal):
            event = events.get(derive_event_id(self._manifest.run_id, prior))
            if event is None:
                raise ValueError("storage recovery prefix is missing a committed event")
            succeeded_events.append(event)
        self._run_context = rebuild_validated_prompt_run_context(
            initial_context=self._run_context,
            succeeded_events=tuple(succeeded_events),
            source_attempts_by_id=attempts,
        )
        self._run_context_ordinal = ordinal
        return self._run_context

    def _advance_run_context_after_commit(self, event_id: str) -> None:
        persisted_ordinal = self._storage.progress.next_event_ordinal
        if persisted_ordinal < 1 or self._source_index_ordinal > persisted_ordinal:
            raise ValueError("source index cache is ahead of persisted storage progress")
        self._extend_source_indexes(persisted_ordinal)
        committed_ordinal = persisted_ordinal - 1
        event = self._source_events_by_id.get(
            derive_event_id(self._storage.binding.run_id, committed_ordinal)
        )
        if event is None or event.event_id != event_id:
            raise ValueError("committed event cannot be reloaded for prompt context")
        if self._run_context is None:
            return
        if not 0 <= self._run_context_ordinal <= committed_ordinal:
            raise ValueError("validated prompt context is ahead of the committed event prefix")
        for ordinal in range(self._run_context_ordinal, persisted_ordinal):
            source_event = self._source_events_by_id.get(
                derive_event_id(self._storage.binding.run_id, ordinal)
            )
            if source_event is None:
                raise ValueError("committed prompt context prefix is incomplete")
            attempts = {
                attempt_id: self._source_attempts_by_id[attempt_id]
                for attempt_id in source_event.attempt_ids
            }
            self._run_context = advance_validated_prompt_run_context(
                self._run_context,
                event=source_event,
                source_attempts_by_id=attempts,
            )
            self._run_context_ordinal = ordinal + 1

    def _validate_request_parameters(
        self,
        *,
        journal: EventJournalState,
        request_parameters: Mapping[str, object],
        policy: MockAttemptPolicyBinding,
    ) -> None:
        supplied = dict(request_parameters)
        changed = changed_request_parameter_paths(self._baseline_request_parameters, supplied)
        if journal.next_attempt_index == 1:
            if changed:
                raise ValueError(
                    "first-attempt request parameters must exactly match the persisted manifest"
                )
            return
        unauthorized = changed - set(policy.allowed_difference_fields)
        if unauthorized:
            raise ValueError("retry request parameters differ outside the frozen attempt policy")

    def _unread_public_posts(
        self, neighbors: tuple[str, ...], last_scanned: int | None
    ) -> tuple[PublicPost, ...]:
        posts = tuple(
            post
            for neighbor in neighbors
            for post in self._storage.public_posts_for_agent(neighbor)
            if last_scanned is None
            or (
                post.published_event_ordinal is not None
                and post.published_event_ordinal > last_scanned
            )
        )
        return tuple(
            sorted(
                posts,
                key=lambda post: (
                    -1 if post.published_event_ordinal is None else post.published_event_ordinal,
                    post.post_id,
                ),
            )
        )

    @staticmethod
    def _validate_frozen_neighbors(
        *,
        storage: RunStorage,
        matched_seed: int,
        population_artifact: ArtifactEnvelope,
        exposure_graph_artifact: ArtifactEnvelope | None,
        source_ws_artifact: ArtifactEnvelope | None,
        agent_node_mapping_artifact: ArtifactEnvelope | None,
        round0_initialization_artifact: ArtifactEnvelope | None,
        frozen_neighbor_agent_ids: Mapping[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        binding = storage.binding
        roster = binding.expected_agent_ids
        mode = binding.expected_exposure_mode
        supplied = {
            agent_id: tuple(neighbors) for agent_id, neighbors in frozen_neighbor_agent_ids.items()
        }

        if mode == "self_history_only":
            if any(
                artifact is not None
                for artifact in (
                    exposure_graph_artifact,
                    source_ws_artifact,
                    agent_node_mapping_artifact,
                    round0_initialization_artifact,
                )
            ):
                raise ValueError("E0 forbids graph and agent-node mapping artifacts")
            if binding.expected_exposure_graph_hash is not None or any(supplied.values()):
                raise ValueError("E0 requires an explicit empty neighbor mapping and no graph")
            return supplied

        if mode not in {"ws_neighbors", "shuffled_social"}:
            raise ValueError("pipeline exposure mode is unsupported")
        if any(
            artifact is None
            for artifact in (
                exposure_graph_artifact,
                agent_node_mapping_artifact,
                round0_initialization_artifact,
            )
        ):
            raise ValueError("social exposure requires graph, mapping, and round-0 artifacts")
        assert exposure_graph_artifact is not None
        assert agent_node_mapping_artifact is not None
        assert round0_initialization_artifact is not None

        def require_bound(artifact: ArtifactEnvelope, label: str) -> None:
            if binding.artifact_hashes.get(artifact.artifact_id) != artifact.output_hash:
                raise ValueError(f"{label} artifact is not hash-bound by storage")

        require_bound(exposure_graph_artifact, "exposure graph")
        require_bound(agent_node_mapping_artifact, "agent-node mapping")
        require_bound(round0_initialization_artifact, "round-0 initialization")
        if (
            binding.expected_exposure_graph_hash != exposure_graph_artifact.output_hash
            or binding.expected_exposure_graph_artifact_id != exposure_graph_artifact.artifact_id
            or binding.expected_exposure_graph_artifact_type
            != exposure_graph_artifact.artifact_type
        ):
            raise ValueError("exposure graph artifact drifts from the persisted binding")

        if mode == "ws_neighbors":
            if source_ws_artifact is not None:
                raise ValueError("E2 uses its exposure WS graph as the position frame")
            validate_ws_artifact(exposure_graph_artifact)
            position_graph = exposure_graph_artifact
        else:
            if source_ws_artifact is None:
                raise ValueError("E1 requires the frozen source WS graph artifact")
            require_bound(source_ws_artifact, "source WS graph")
            if (
                binding.expected_source_ws_artifact_hash != source_ws_artifact.output_hash
                or binding.expected_source_ws_artifact_id != source_ws_artifact.artifact_id
                or binding.expected_source_ws_artifact_type != source_ws_artifact.artifact_type
            ):
                raise ValueError("source WS graph artifact drifts from the persisted binding")
            validate_shadow_artifact(exposure_graph_artifact, source_ws_artifact)
            position_graph = source_ws_artifact

        for label, artifact in (
            ("exposure graph", exposure_graph_artifact),
            ("position graph", position_graph),
            ("agent-node mapping", agent_node_mapping_artifact),
            ("round-0 initialization", round0_initialization_artifact),
        ):
            payload = artifact.payload
            if not isinstance(payload, Mapping) or payload.get("matched_seed") != matched_seed:
                raise ValueError(f"{label} matched seed drifts from the persisted manifest")

        replayed_mapping = build_agent_node_mapping(
            population_artifact=population_artifact,
            round0_initialization_artifact=round0_initialization_artifact,
            network_artifact=position_graph,
            matched_seed=matched_seed,
            mock_only=True,
        )
        if agent_node_mapping_artifact != replayed_mapping:
            raise ValueError("agent-node mapping does not match deterministic artifact replay")

        assignments = agent_node_mapping_artifact.payload.get("assignments")
        edges = exposure_graph_artifact.payload.get("edges")
        if not isinstance(assignments, tuple) or not isinstance(edges, tuple):
            raise ValueError("graph or agent-node mapping payload is malformed")
        agent_by_node = {
            assignment["node_id"]: assignment["agent_id"] for assignment in assignments
        }
        if set(agent_by_node.values()) != set(roster) or set(agent_by_node) != set(
            range(len(roster))
        ):
            raise ValueError("agent-node mapping does not exactly cover roster and graph nodes")
        derived: dict[str, set[str]] = {agent_id: set() for agent_id in roster}
        for left, right in edges:
            left_agent = agent_by_node[left]
            right_agent = agent_by_node[right]
            derived[left_agent].add(right_agent)
            derived[right_agent].add(left_agent)
        expected = {agent_id: tuple(sorted(derived[agent_id])) for agent_id in roster}
        if supplied != expected:
            raise ValueError("neighbor mapping drifts from the frozen graph and agent-node mapping")
        return expected

    def _population_member(self, agent_id: str) -> Mapping[str, object]:
        members = self._population_artifact.payload.get("members")
        if not isinstance(members, tuple):
            raise ValueError("population artifact members are malformed")
        matches = tuple(
            member
            for member in members
            if isinstance(member, Mapping) and member.get("agent_id") == agent_id
        )
        if len(matches) != 1:
            raise ValueError("population artifact must contain the receiver exactly once")
        member = matches[0]
        fields = member.get("fields")
        if not isinstance(fields, Mapping):
            raise ValueError("population member fields are malformed")
        return {
            "agent_id": member.get("agent_id"),
            "donor_id": member.get("donor_id"),
            "fields": dict(fields),
        }

    def _persona_condition(self) -> tuple[bool, bool]:
        pieces = self._cell_id.split("-")
        if (
            len(pieces) != 4
            or pieces[1] not in {"I0", "I1"}
            or pieces[2]
            not in {
                "C0",
                "C1",
            }
        ):
            raise ValueError("manifest cell_id does not encode frozen persona factors")
        return pieces[1] == "I1", pieces[2] == "C1"

    def _failure_evidence(
        self, terminal: GenerationAttempt, policy: MockAttemptPolicyBinding, reason: str
    ) -> TerminalFailureEvidence:
        chain = self._storage.causal_evidence_prefix()
        terminal_hash = canonical_payload_hash(terminal.to_payload())
        values = {
            "evidence_sequence": len(chain) + 1,
            "previous_evidence_hash": None if not chain else chain[-1].payload_hash,
            "evidence_kind": "failure",
            "run_id": self._storage.binding.run_id,
            "event_id": terminal.event_id,
            "event_ordinal": self._storage.progress.next_event_ordinal,
            "attempt_id": terminal.attempt_id,
            "attempt_index": terminal.attempt_index,
            "terminal_transition_hash": terminal_hash,
            "terminal_attempt_hash": terminal_hash,
            "reason": reason,
            "policy_evidence": {
                "policy_id": policy.policy_id,
                "policy_hash": policy.record_hash,
            },
            "recorded_at": self._clock(),
        }
        return TerminalFailureEvidence(
            evidence_id="halt-" + canonical_payload_hash(values), **values
        )

    @staticmethod
    def _provider_metadata(response: AdapterResponse) -> dict[str, object]:
        return {
            "adapter_response_id": response.response_id,
            "adapter_response_hash": response.record_hash,
            "adapter_outcome": response.outcome,
            "adapter_error": None if response.error is None else dict(response.error),
            "runtime_identity": dict(response.runtime_identity),
            "runtime_identity_hash": response.runtime_identity_hash,
            "script_hash": response.script_hash,
        }
