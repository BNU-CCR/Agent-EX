from __future__ import annotations

import inspect
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Mapping

import pytest
import agent_ex.storage as storage_module
from agent_ex import execution_evidence as execution_evidence_module

from agent_ex.adapters.base import AdapterRequest
from agent_ex.adapters.mock import MockAdapter, MockScriptStep
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import (
    EventStatus,
    FrozenSchedule,
    GenerationAttempt,
    GenerationEvent,
    RunManifest,
    ScheduleSlot,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
    derive_run_id,
)
from agent_ex.execution_evidence import (
    EventInputEvidence,
    FinalizedAttemptEvidence,
    MockAttemptPolicyBinding,
    ParseNotApplicableEvidence,
    PersistedInvocationEvidence,
)
from agent_ex.feed import FeedCursor, build_exposure_record, select_unread_feed
from agent_ex.memory import build_memory_view
from agent_ex.network import build_shadow_artifact, build_ws_artifact
from agent_ex.state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from agent_ex.storage import (
    EventJournalState,
    ExecutionState,
    ExecutionStatus,
    ExternalResponseReference,
    ResumeAuthorizationEvidence,
    RunStorage,
    StorageBinding,
    TerminalFailureEvidence,
    changed_request_parameter_paths,
)
from agent_ex.topic import TopicPackage
from agent_ex.engine import AttemptExecutionEvidence
from agent_ex.parser import ParserLimits, parse_agent_update
from agent_ex.persona import render_persona
from agent_ex.prompt import PromptLimits, build_prompt_view, validate_prompt_run_context
from test_prompt import member, persona_template, population_artifact, topic as prompt_topic


SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = "2026-08-18T00:00:00+00:00"


def test_changed_request_parameter_paths_reports_recursive_leaf_differences() -> None:
    signature = inspect.signature(changed_request_parameter_paths)
    assert tuple(signature.parameters) == ("before", "after")
    assert all(
        parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values()
    )
    before = {
        "sampling": {"temperature": 0.0, "top_p": 1.0},
        "legacy": {"penalty": 1},
        "scalar": 1,
    }
    after = {
        "sampling": {
            "temperature": 0.5,
            "top_p": 1.0,
            "new_group": {"weight": 2},
        },
        "scalar": 2,
    }

    assert changed_request_parameter_paths(before, after) == {
        "request_parameters.sampling.temperature",
        "request_parameters.sampling.new_group.weight",
        "request_parameters.legacy.penalty",
        "request_parameters.scalar",
    }
    assert changed_request_parameter_paths(
        {"sampling": {"temperature": 0.0}}, {"sampling": 0.5}
    ) == {"request_parameters.sampling"}
    with pytest.raises(ValueError, match="key|segment|path"):
        changed_request_parameter_paths({"sampling": {"bad.key": 0.0}}, {"sampling": 0.5})
    identical = {"sampling": {"temperature": 0.0, "top_p": 1.0}}
    assert changed_request_parameter_paths(identical, identical) == set()


@pytest.mark.parametrize(
    ("parameters", "error_type"),
    (
        ({"sampling.temperature": 0.5}, ValueError),
        ({"sampling": {"": 0.5}}, ValueError),
        ({"sampling": {"   ": 0.5}}, ValueError),
        ({"sampling": {1: 0.5}}, TypeError),
    ),
)
def test_changed_request_parameter_paths_rejects_ambiguous_key_segments(
    parameters: Mapping[object, object], error_type: type[Exception]
) -> None:
    with pytest.raises(error_type, match="key|segment|text"):
        changed_request_parameter_paths({}, parameters)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("parameters", "error_type"),
    (
        ({"groups": [{"sampling.temperature": 0.0}]}, ValueError),
        ({"groups": ({"": 0.0},)}, ValueError),
        ({"groups": ({1: 0.0},)}, TypeError),
    ),
)
def test_changed_request_parameter_paths_validates_mapping_keys_inside_arrays(
    parameters: Mapping[str, object], error_type: type[Exception]
) -> None:
    with pytest.raises(error_type, match="key|segment|text"):
        changed_request_parameter_paths(parameters, parameters)


def test_changed_request_parameter_paths_compares_arrays_canonically_at_parent_path() -> None:
    before = {"groups": [{"temperature": 0.0}, "stop"]}

    assert (
        changed_request_parameter_paths(before, {"groups": ({"temperature": 0.0}, "stop")}) == set()
    )
    assert changed_request_parameter_paths(before, {"groups": [{"temperature": 0.5}, "stop"]}) == {
        "request_parameters.groups"
    }


@pytest.fixture(autouse=True)
def explicitly_lease_created_test_stores(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
):
    """Most storage tests explicitly hold a lease for each created writer."""

    unleased_tests = {
        "test_halted_run_requires_canonical_append_only_resume_authorization",
        "test_reopen_fails_closed_on_resume_authorization_tamper",
        "test_every_mutator_requires_this_storage_instance_to_hold_run_lease",
        "test_run_lease_rejects_second_owner_and_releases_on_context_exit",
        "test_run_lease_is_exclusive_across_processes",
        "test_second_process_direct_mutator_is_rejected_and_crash_releases_lease",
        "test_hardlink_alias_blocks_every_preopened_writer_and_cross_process_owner",
        "test_hardlink_created_after_lease_blocks_mutation_until_alias_is_removed",
        "test_windows_lease_handle_prevents_sidecar_replacement_while_owned",
    }
    if any(
        request.node.name == name or request.node.name.startswith(name + "[")
        for name in unleased_tests
    ):
        yield
        return
    original = RunStorage.create.__func__

    def create_with_explicit_lease(cls, *args: object, **kwargs: object) -> RunStorage:
        store = original(cls, *args, **kwargs)
        store.acquire_run_lease().acquire()
        return store

    monkeypatch.setattr(RunStorage, "create", classmethod(create_with_explicit_lease))
    yield


@lru_cache(maxsize=2)
def real_network_artifacts(matched_seed: int = 17) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    ws = build_ws_artifact(n=40, k=4, p=0.05, matched_seed=matched_seed, mock_only=True)
    shadow = build_shadow_artifact(
        ws,
        matched_seed=matched_seed,
        max_attempts=3,
        trial_budget_per_edge=300,
        mock_only=True,
    )
    return ws, shadow


def storage_genesis(binding: StorageBinding) -> str:
    return canonical_payload_hash(
        {
            "schema_version": "paper1.run-storage.v6",
            "run_id": binding.run_id,
            "run_spec_hash": binding.run_spec_hash,
            "protocol_hash": binding.protocol_hash,
            "schedule_hash": binding.schedule_hash,
            "artifact_hashes": dict(binding.artifact_hashes),
            "expected_agent_ids_hash": binding.expected_agent_ids_hash,
            "expected_exposure_mode": binding.expected_exposure_mode,
            "expected_exposure_graph_hash": binding.expected_exposure_graph_hash,
            "expected_exposure_graph_artifact_id": binding.expected_exposure_graph_artifact_id,
            "expected_exposure_graph_artifact_type": (
                binding.expected_exposure_graph_artifact_type
            ),
            "expected_source_ws_artifact_hash": binding.expected_source_ws_artifact_hash,
            "expected_source_ws_artifact_id": binding.expected_source_ws_artifact_id,
            "expected_source_ws_artifact_type": binding.expected_source_ws_artifact_type,
            "round0_root": binding.round0_root,
        }
    )


def inline_attempt_chain_entry(value: GenerationAttempt) -> dict[str, object]:
    transitions = (
        attempt_transition(value, EventStatus.PENDING),
        attempt_transition(value, EventStatus.IN_PROGRESS),
        value,
    )
    return {
        "terminal_attempt": value.to_payload(),
        "terminal_row_envelope": {
            "attempt_id": value.attempt_id,
            "event_id": value.event_id,
            "attempt_index": value.attempt_index,
            "status": value.status.value,
            "payload_hash": canonical_payload_hash(value.to_payload()),
            "raw_response_uri": None,
            "raw_response_hash": None,
        },
        "transitions": [
            {
                "transition": transition.to_payload(),
                "row_envelope": {
                    "attempt_id": transition.attempt_id,
                    "event_id": transition.event_id,
                    "attempt_index": transition.attempt_index,
                    "transition_index": index,
                    "status": transition.status.value,
                    "payload_hash": canonical_payload_hash(transition.to_payload()),
                    "raw_response_uri": None,
                    "raw_response_hash": None,
                },
            }
            for index, transition in enumerate(transitions, start=1)
        ],
    }


def schedule(*, publish_flags: tuple[bool, ...] = (False, True)) -> FrozenSchedule:
    return FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id="mock.weighted-with-replacement",
        algorithm_version="1.0.0",
        population_size=len(publish_flags),
        sweep_count=1,
        slots=tuple(
            ScheduleSlot(
                event_ordinal=index,
                sweep_index=1,
                draw_index=index,
                agent_id=f"agent-{index}",
                publish_flag=flag,
            )
            for index, flag in enumerate(publish_flags)
        ),
    )


def manifest(
    frozen_schedule: FrozenSchedule | None = None,
    *,
    cell_id: str = "P1-I0-C0-E0",
) -> RunManifest:
    frozen_schedule = frozen_schedule or schedule()
    run_spec = {
        "protocol_id": "paper1",
        "protocol_version": "draft",
        "protocol_hash": SHA_A,
        "schedule_hash": frozen_schedule.schedule_hash,
        "cell_id": cell_id,
        "run_config": {
            "population": frozen_schedule.population_size,
            "sweep_count": frozen_schedule.sweep_count,
            "expected_event_count": frozen_schedule.count,
        },
        "request_parameters": {"temperature": 0.0},
    }
    run_id = derive_run_id(run_spec, matched_seed=17, launch_nonce="launch-storage")
    return RunManifest(
        run_id=run_id,
        run_spec=run_spec,
        run_spec_hash=canonical_payload_hash(run_spec),
        matched_seed=17,
        launch_nonce="launch-storage",
        protocol_id="paper1",
        protocol_version="draft",
        protocol_hash=SHA_A,
        git_sha="c" * 40,
        dirty=False,
        diff_hash=None,
        environment_lock_hash=SHA_B,
        model_identity={
            "provider": "mock",
            "model": "deterministic",
            "revision": "1",
            "runtime": "python",
        },
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": SHA_B,
            "platform": "test",
        },
        schedule_uri="file:///tmp/schedule.json",
        schedule=frozen_schedule,
        schedule_hash=frozen_schedule.schedule_hash,
        checkpoint_uri=None,
        checkpoint_hash=None,
        recovery_cursor=None,
        event_ids=(),
        terminal_counts={status.value: 0 for status in EventStatus},
        started_at=NOW,
        updated_at=NOW,
        archive={"status": "pending", "uri": None, "hash": None},
    )


def expected_agent_ids(run_manifest: RunManifest) -> tuple[str, ...]:
    return tuple(f"agent-{index}" for index in range(run_manifest.schedule.population_size))


def attempt(
    run_manifest: RunManifest,
    *,
    ordinal: int = 0,
    index: int = 1,
    status: EventStatus = EventStatus.FAILED,
) -> GenerationAttempt:
    event_id = derive_event_id(run_manifest.run_id, ordinal)
    prompt = ({"role": "user", "content": "mock"},)
    parameters = {"temperature": 0.0}
    identity = {"provider": "mock", "model": "deterministic", "revision": "1"}
    provider = {"headers": {"x-request-id": f"provider-{index}"}}
    parsed = {
        "stance": "neutral",
        "confidence": 3,
        "public_reason": f"reason-{ordinal}-{index}",
    }
    raw = json.dumps(parsed, separators=(",", ":"))
    usage = {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}
    succeeded = status is EventStatus.SUCCEEDED
    return GenerationAttempt(
        attempt_id=derive_attempt_id(event_id, index),
        event_id=event_id,
        attempt_index=index,
        status=status,
        request_id=f"request-{ordinal}-{index}",
        exposure_id=f"exposure-{ordinal}",
        rendered_messages=prompt,
        rendered_prompt_hash=canonical_payload_hash(prompt),
        request_parameters=parameters,
        request_parameters_hash=canonical_payload_hash(parameters),
        model_identity=identity,
        model_identity_hash=canonical_payload_hash(identity),
        model_seed=123,
        provider_request_id=f"provider-{ordinal}-{index}",
        provider_metadata=provider,
        provider_metadata_hash=canonical_payload_hash(provider),
        http_status=200 if succeeded else 500,
        raw_response=raw if succeeded else None,
        raw_response_hash=canonical_payload_hash(raw) if succeeded else None,
        parsed_response=parsed if succeeded else None,
        parsed_response_hash=canonical_payload_hash(parsed) if succeeded else None,
        usage=usage if succeeded else {},
        usage_hash=canonical_payload_hash(usage if succeeded else {}),
        finish_reason="stop" if succeeded else None,
        error=None if succeeded else {"code": "mock_failure"},
        started_at=NOW,
        finished_at=NOW,
    )


def attempt_transition(terminal: GenerationAttempt, status: EventStatus) -> GenerationAttempt:
    if status in {EventStatus.FAILED, EventStatus.SUCCEEDED}:
        if terminal.status is not status:
            raise ValueError("terminal fixture status mismatch")
        return terminal
    payload = terminal.to_payload()
    payload.update(
        {
            "status": status.value,
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
            "started_at": NOW if status is EventStatus.IN_PROGRESS else None,
            "finished_at": None,
        }
    )
    return GenerationAttempt.from_payload(payload)


def append_terminal_attempt(
    store: RunStorage,
    terminal: GenerationAttempt,
    *,
    external_response: ExternalResponseReference | None = None,
) -> None:
    store.append_attempt(attempt_transition(terminal, EventStatus.PENDING))
    store.append_attempt(attempt_transition(terminal, EventStatus.IN_PROGRESS))
    store.append_attempt(terminal, external_response=external_response)


def authorize_retry(store: RunStorage, failed: GenerationAttempt, suffix: str) -> None:
    failure = store.record_terminal_failure(
        event_id=failed.event_id,
        reason=f"test retry {suffix}",
        policy_evidence={"policy_id": f"halt-{suffix}", "policy_hash": SHA_A},
        recorded_at=NOW,
    )
    store.authorize_resume(
        authorization_id=f"resume-{suffix}",
        event_id=failed.event_id,
        previous_terminal_failure_hash=failure.payload_hash,
        policy_evidence_id=f"retry-{suffix}",
        policy_evidence_hash=SHA_B,
        authorized_at=NOW,
    )


def rewrite_causal_identity(
    store: RunStorage,
    *,
    failure_run_id: str | None = None,
    authorization_run_id: str | None = None,
    event_ordinal: int | None = None,
) -> None:
    """Rewrite a causal pair self-consistently to exercise typed identity replay."""

    failure_row = store._connection.execute(
        "SELECT evidence_id, payload_json FROM terminal_failures"
    ).fetchone()
    authorization_row = store._connection.execute(
        "SELECT authorization_id, payload_json FROM resume_authorizations"
    ).fetchone()
    assert failure_row is not None and authorization_row is not None
    failure = json.loads(failure_row[1])
    authorization = json.loads(authorization_row[1])
    if failure_run_id is not None:
        failure["run_id"] = failure_run_id
    if authorization_run_id is not None:
        authorization["run_id"] = authorization_run_id
    if event_ordinal is not None:
        failure["event_ordinal"] = event_ordinal
        authorization["event_ordinal"] = event_ordinal
    failure_hash = canonical_payload_hash(failure)
    authorization["previous_evidence_hash"] = failure_hash
    authorization["previous_terminal_failure_hash"] = failure_hash
    authorization_hash = canonical_payload_hash(authorization)
    store._connection.execute(
        """UPDATE terminal_failures
           SET event_ordinal = ?, payload_json = ?, payload_hash = ?
           WHERE evidence_id = ?""",
        (
            failure["event_ordinal"],
            json.dumps(failure, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            failure_hash,
            failure_row[0],
        ),
    )
    store._connection.execute(
        """UPDATE resume_authorizations
           SET event_ordinal = ?, previous_evidence_hash = ?,
               previous_terminal_failure_hash = ?, payload_json = ?, payload_hash = ?
           WHERE authorization_id = ?""",
        (
            authorization["event_ordinal"],
            failure_hash,
            failure_hash,
            json.dumps(authorization, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            authorization_hash,
            authorization_row[0],
        ),
    )


def seal_expected_initial_state(store: RunStorage, run_manifest: RunManifest) -> None:
    if store.binding.round0_root is not None:
        return
    for agent_id in expected_agent_ids(run_manifest):
        if store.private_state(agent_id) is None:
            store.initialize_agent(*initial_records(agent_id))
    store.seal_initial_state()


def topic() -> TopicPackage:
    return TopicPackage.from_payload(
        {
            "schema_version": "paper1.topic-package.mock.v1",
            "package_version": "0.0.1-mock",
            "topic_id": "mock-topic",
            "construct": "mock construct",
            "target_population": "mock population",
            "applicability": "mock only",
            "fact_card": "mock fact card",
            "core_statement": "mock statement",
            "paraphrases": ["mock paraphrase"],
            "stance_labels": [
                "strongly oppose",
                "oppose",
                "somewhat oppose",
                "neutral",
                "somewhat support",
                "support",
                "strongly support",
            ],
            "confidence_contract": {"minimum": 1, "maximum": 5, "analysis_only": True},
            "output_contract": ["stance", "confidence", "public_reason"],
            "argument_families": ["mock-family"],
            "round0_reason_library_artifact_id": "artifact-" + SHA_A,
            "topic_extension_fields": [],
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        }
    )


def initial_records(
    agent_id: str,
) -> tuple[PrivateUpdate, PrivateState, PublicPost, LatestPublicPointer, FeedCursor]:
    update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id=agent_id,
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label="neutral",
        reason="round zero",
        confidence=None,
        published=True,
        source_attempt_id=None,
        mock_only=True,
    )
    state = PrivateState.from_update(update, previous=None, mock_only=True)
    post = PublicPost.from_private_update(update, mock_only=True)
    pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
    cursor = FeedCursor.initial(
        matched_seed=17,
        receiver_agent_id=agent_id,
        exposure_mode="self_history_only",
        exposure_graph_hash=None,
        mock_only=True,
    )
    return update, state, post, pointer, cursor


def prepared_evidence_bundle(
    tmp_path: Path,
    *,
    script_step: MockScriptStep | None = None,
    script_steps: tuple[MockScriptStep, ...] | None = None,
    single_event: bool = False,
    request_parameters: Mapping[str, object] | None = None,
    allowed_difference_fields: tuple[str, ...] | None = None,
) -> tuple[RunStorage, dict[str, object]]:
    agent_ids = ("agent-0001",) if single_event else ("agent-0001", "agent-0002")
    frozen_schedule = FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id="mock.weighted-with-replacement",
        algorithm_version="1.0.0",
        population_size=len(agent_ids),
        sweep_count=1,
        slots=(ScheduleSlot(0, 1, 0, "agent-0001", False),)
        if single_event
        else (
            ScheduleSlot(0, 1, 0, "agent-0001", False),
            ScheduleSlot(1, 1, 1, "agent-0002", False),
        ),
    )
    run_manifest = manifest(frozen_schedule, cell_id="P1-I0-C0-E0")
    store = RunStorage.create(
        tmp_path / "evidence.sqlite",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=agent_ids,
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    round0: dict[
        str, tuple[PrivateUpdate, PrivateState, PublicPost, LatestPublicPointer, FeedCursor]
    ] = {}
    for agent_id in agent_ids:
        update = PrivateUpdate.create(
            topic_package=prompt_topic(),
            matched_seed=17,
            agent_id=agent_id,
            event_id=None,
            event_ordinal=None,
            sequence_index=0,
            stance_label="label-1",
            reason="private round zero",
            confidence=None,
            published=True,
            source_attempt_id=None,
            mock_only=True,
        )
        state = PrivateState.from_update(update, previous=None, mock_only=True)
        post = PublicPost.from_private_update(update, mock_only=True)
        pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
        cursor = FeedCursor.initial(
            matched_seed=17,
            receiver_agent_id=agent_id,
            exposure_mode="self_history_only",
            exposure_graph_hash=None,
            mock_only=True,
        )
        round0[agent_id] = (update, state, post, pointer, cursor)
        store.initialize_agent(update, state, post, pointer, cursor)
    store.seal_initial_state()

    update, state, _post, _pointer, cursor = round0["agent-0001"]
    event_id = derive_event_id(run_manifest.run_id, 0)
    selection = select_unread_feed(
        unread_public_posts=(),
        topic_package=prompt_topic(),
        neighbor_agent_ids=(),
        cursor=cursor,
        receiver_event_id=event_id,
        receiver_event_ordinal=0,
        matched_seed=17,
        exposure_mode="self_history_only",
        exposure_graph_hash=None,
        capacity=4,
        mock_only=True,
    )
    exposure = build_exposure_record(selection, topic_package=prompt_topic(), mock_only=True)
    memory = build_memory_view(
        private_updates=(update,),
        topic_package=prompt_topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=3,
        mock_only=True,
    )
    event = GenerationEvent(
        run_id=run_manifest.run_id,
        event_id=event_id,
        event_ordinal=0,
        sweep_index=1,
        draw_index=0,
        agent_id="agent-0001",
        publish_flag=False,
        exposure_id="exposure-0",
        status=EventStatus.PENDING,
        attempt_ids=(),
        failure_reason=None,
    )
    prompt_limits = PromptLimits.create(
        max_persona_chars=10_000,
        max_string_chars=50_000,
        max_memory_items=10,
        max_social_messages=10,
        max_data_chars=100_000,
        max_total_chars=120_000,
        mock_only=True,
    )
    prompt = build_prompt_view(
        run_context=validate_prompt_run_context(
            run_manifest, source_events_by_id={}, source_attempts_by_id={}
        ),
        topic=prompt_topic(),
        persona=render_persona(
            persona_template(),
            member(),
            {"identity_present": False, "continuity_present": False},
        ),
        persona_template=persona_template(),
        population_artifact=population_artifact(),
        population_member=member(),
        private_state=state,
        private_updates=(update,),
        memory=memory,
        exposure=exposure,
        exposure_selection=selection,
        unread_public_posts=(),
        neighbor_agent_ids=(),
        feed_cursor=cursor,
        public_posts_by_id={},
        source_private_updates_by_id={},
        source_events_by_id={},
        source_attempts_by_id={},
        event=event,
        matched_seed=17,
        cell_id="P1-I0-C0-E0",
        limits=prompt_limits,
        mock_only=True,
    )
    parser_limits = ParserLimits.create(
        max_raw_chars=100_000,
        max_raw_bytes=100_000,
        max_json_depth=32,
        max_reason_chars=10_000,
        mock_only=True,
    )
    event_input = EventInputEvidence.create(
        exposure_selection=selection,
        exposure_record=exposure,
        memory_view=memory,
        prompt_view=prompt,
        parser_limits=parser_limits,
        state_context_hash=canonical_payload_hash({"successful_prefix": 0}),
        publish_flag=False,
    )
    policy = MockAttemptPolicyBinding.create(
        allowed_difference_fields=(
            ("model_seed", "request_parameters.temperature")
            if allowed_difference_fields is None
            else allowed_difference_fields
        ),
        mock_only=True,
        formal_eligible=False,
    )
    adapter = MockAdapter(
        script={
            event_id: script_steps
            or (
                script_step
                or MockScriptStep.success(
                    {"stance": "label-2", "confidence": 3, "public_reason": "reason"}
                ),
            )
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    binding = adapter.execution_binding()
    request = AdapterRequest.create(
        prompt_view=prompt, attempt_index=1, mock_seed=12345, mock_only=True
    )
    request_evidence = execution_evidence_module.AdapterRequestEvidence.create(
        request=request,
        model_identity=binding.model_identity,
        request_parameters=(
            {"temperature": 0.0} if request_parameters is None else dict(request_parameters)
        ),
        model_seed=12345,
        prompt_limits_hash=prompt.limits_hash,
        parser_limits_hash=parser_limits.record_hash,
        attempt_policy_hash=policy.record_hash,
        adapter_execution_binding_hash=binding.record_hash,
    )
    pending = GenerationAttempt(
        attempt_id=request.attempt_id,
        event_id=event_id,
        attempt_index=1,
        status=EventStatus.PENDING,
        request_id=request.request_id,
        exposure_id=exposure.exposure_id,
        rendered_messages=request.rendered_messages,
        rendered_prompt_hash=request.rendered_messages_hash,
        request_parameters=request_evidence.request_parameters,
        request_parameters_hash=request_evidence.request_parameters_hash,
        model_identity=request_evidence.model_identity,
        model_identity_hash=request_evidence.model_identity_hash,
        model_seed=request_evidence.model_seed,
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
    return store, {
        "path": tmp_path / "evidence.sqlite",
        "expected_agent_ids": agent_ids,
        "manifest": run_manifest,
        "event_input": event_input,
        "policy": policy,
        "binding": binding,
        "request_evidence": request_evidence,
        "pending": pending,
        "adapter": adapter,
        "parser_limits": parser_limits,
    }


def reopen_evidence_store(store: RunStorage, values: Mapping[str, object]) -> RunStorage:
    store.close()
    reopened = RunStorage.open(
        values["path"],
        manifest=values["manifest"],
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=values.get("expected_agent_ids", ("agent-0001", "agent-0002")),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    reopened.acquire_run_lease().acquire()
    return reopened


def test_record_prepared_attempt_writes_typed_evidence_and_pending_once(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(tmp_path)

    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )

    assert store.event_input_evidence(values["event_input"].event_id) == values["event_input"]
    assert store.attempt_policy_evidence(values["event_input"].event_id) == values["policy"]
    assert store.adapter_execution_binding(values["binding"].binding_id) == values["binding"]
    assert (
        store.adapter_request_evidence(values["pending"].attempt_id) == values["request_evidence"]
    )
    assert store.attempt_transitions(values["pending"].attempt_id) == (values["pending"],)


@pytest.mark.parametrize(
    "request_parameters",
    (
        {"sampling.temperature": 0.0},
        {"sampling": {"   ": 0.0}},
        {"groups": [{"sampling.temperature": 0.0}]},
    ),
)
def test_first_prepared_attempt_rejects_invalid_parameter_paths_without_rows(
    tmp_path: Path, request_parameters: dict[str, object]
) -> None:
    store, values = prepared_evidence_bundle(tmp_path, request_parameters=request_parameters)

    with pytest.raises(ValueError, match="key|segment|path|request parameter"):
        store.record_prepared_attempt(
            values["event_input"],
            policy=values["policy"],
            adapter_binding=values["binding"],
            request_evidence=values["request_evidence"],
            pending_attempt=values["pending"],
        )

    for table in (
        "event_input_evidence",
        "attempt_policy_evidence",
        "adapter_execution_bindings",
        "adapter_requests",
        "attempt_transitions",
    ):
        count = store._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == 0


@pytest.mark.parametrize(
    ("column", "replacement"),
    (
        ("event_id", "event-tampered"),
        ("adapter_binding_hash", SHA_A),
        ("parser_limits_hash", SHA_A),
        ("policy_hash", SHA_A),
    ),
)
def test_prepared_replay_rejects_adapter_request_row_envelope_drift_atomically(
    tmp_path: Path, column: str, replacement: str
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )
    attempt_id = values["pending"].attempt_id
    store._connection.execute("PRAGMA foreign_keys = OFF")
    store._connection.execute(
        f"UPDATE adapter_requests SET {column} = ? WHERE attempt_id = ?",
        (replacement, attempt_id),
    )
    store._connection.commit()
    store._connection.execute("PRAGMA foreign_keys = ON")
    before_row = store._connection.execute(
        """SELECT event_id, adapter_binding_hash, parser_limits_hash, policy_hash,
                  payload, record_hash
           FROM adapter_requests WHERE attempt_id = ?""",
        (attempt_id,),
    ).fetchone()
    before_attempts = store.attempt_transitions(attempt_id)
    before_execution = store.execution_state()

    with pytest.raises(ValueError, match="conflicting immutable adapter_requests replay"):
        store.record_prepared_attempt(
            values["event_input"],
            policy=values["policy"],
            adapter_binding=values["binding"],
            request_evidence=values["request_evidence"],
            pending_attempt=values["pending"],
        )

    assert (
        store._connection.execute(
            """SELECT event_id, adapter_binding_hash, parser_limits_hash, policy_hash,
                  payload, record_hash
           FROM adapter_requests WHERE attempt_id = ?""",
            (attempt_id,),
        ).fetchone()
        == before_row
    )
    assert store.attempt_transitions(attempt_id) == before_attempts == (values["pending"],)
    assert store.execution_state() == before_execution


def test_run_rejects_second_adapter_attestation_before_request_or_pending_write(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )
    other = MockAdapter(
        script={
            values["pending"].event_id: (MockScriptStep.malformed("different run attestation"),)
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    other_binding = other.execution_binding()
    other_request = execution_evidence_module.AdapterRequestEvidence.create(
        request=values["request_evidence"].request,
        model_identity=other_binding.model_identity,
        request_parameters=values["request_evidence"].request_parameters,
        model_seed=values["request_evidence"].model_seed,
        prompt_limits_hash=values["request_evidence"].prompt_limits_hash,
        parser_limits_hash=values["request_evidence"].parser_limits_hash,
        attempt_policy_hash=values["policy"].record_hash,
        adapter_execution_binding_hash=other_binding.record_hash,
    )

    with pytest.raises(ValueError, match="single|sole|run adapter|attestation"):
        store.record_prepared_attempt(
            values["event_input"],
            policy=values["policy"],
            adapter_binding=other_binding,
            request_evidence=other_request,
            pending_attempt=values["pending"],
        )

    assert (
        store._connection.execute("SELECT COUNT(*) FROM adapter_execution_bindings").fetchone()[0]
        == 1
    )
    assert (
        store.adapter_request_evidence(values["pending"].attempt_id) == values["request_evidence"]
    )


@pytest.mark.parametrize(
    "table",
    (
        "event_input_evidence",
        "attempt_policy_evidence",
        "adapter_execution_bindings",
        "adapter_requests",
        "attempt_transitions",
    ),
)
def test_record_prepared_attempt_sql_failure_rolls_back_all_evidence_and_state(
    tmp_path: Path,
    table: str,
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    before = store.execution_state()
    store._connection.execute(
        f"""CREATE TRIGGER fail_prepared_insert BEFORE INSERT ON {table}
            BEGIN SELECT RAISE(ABORT, 'injected prepared failure'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="injected prepared"):
        store.record_prepared_attempt(
            values["event_input"],
            policy=values["policy"],
            adapter_binding=values["binding"],
            request_evidence=values["request_evidence"],
            pending_attempt=values["pending"],
        )

    assert store.event_input_evidence(values["event_input"].event_id) is None
    assert store.attempt_policy_evidence(values["event_input"].event_id) is None
    assert store.adapter_request_evidence(values["pending"].attempt_id) is None
    assert (
        store._connection.execute(
            "SELECT COUNT(*) FROM attempt_transitions WHERE attempt_id = ?",
            (values["pending"].attempt_id,),
        ).fetchone()[0]
        == 0
    )
    assert store.execution_state() == before


def test_prepare_state_dependent_validation_runs_inside_guarded_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    before = store.execution_state()

    def fail_inside_transaction(_ordinal: int) -> object:
        assert store._connection.in_transaction is True
        raise RuntimeError("injected validation failure")

    monkeypatch.setattr(store, "schedule_slot", fail_inside_transaction)
    with pytest.raises(RuntimeError, match="validation failure"):
        store.record_prepared_attempt(
            values["event_input"],
            policy=values["policy"],
            adapter_binding=values["binding"],
            request_evidence=values["request_evidence"],
            pending_attempt=values["pending"],
        )

    assert store._connection.in_transaction is False
    assert store.event_input_evidence(values["event_input"].event_id) is None
    assert store.execution_state() == before


def persisted_invocation(values: Mapping[str, object]) -> PersistedInvocationEvidence:
    request_evidence = values["request_evidence"]
    response = values["adapter"].generate(request_evidence.request)
    metadata = {
        "adapter_response_id": response.response_id,
        "adapter_response_hash": response.record_hash,
        "adapter_outcome": response.outcome,
        "adapter_error": None if response.error is None else dict(response.error),
        "runtime_identity": dict(response.runtime_identity),
        "runtime_identity_hash": response.runtime_identity_hash,
        "script_hash": response.script_hash,
    }
    execution = AttemptExecutionEvidence(
        started_at=NOW,
        finished_at=NOW,
        http_status=200,
        provider_metadata=metadata,
        usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        finish_reason="stop",
    )
    return PersistedInvocationEvidence.create(
        response=response,
        execution_payload={
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
            "http_status": execution.http_status,
            "provider_metadata": dict(execution.provider_metadata),
            "usage": dict(execution.usage),
            "finish_reason": execution.finish_reason,
        },
        request_hash=request_evidence.request_hash,
        parser_limits_hash=values["parser_limits"].record_hash,
        attempt_policy_hash=values["policy"].record_hash,
        adapter_execution_binding_hash=values["binding"].record_hash,
    )


def test_invocation_evidence_requires_current_in_progress_and_is_idempotent(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    evidence = persisted_invocation(values)
    with pytest.raises(ValueError, match="IN_PROGRESS"):
        store.record_invocation_evidence(evidence)
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )
    store.append_attempt(attempt_transition(values["pending"], EventStatus.IN_PROGRESS))

    store.record_invocation_evidence(evidence)
    store.record_invocation_evidence(evidence)

    assert store.invocation_evidence(values["pending"].attempt_id) == evidence
    assert store.parse_evidence(values["pending"].attempt_id) is None
    assert store.current_event_journal().latest_transition.status is EventStatus.IN_PROGRESS


@pytest.mark.parametrize(
    "step",
    (
        MockScriptStep.malformed("different raw response"),
        MockScriptStep.timeout("different timeout"),
    ),
)
def test_invocation_rejects_sealed_response_outside_persisted_script_commitment(
    tmp_path: Path, step: MockScriptStep
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )
    store.append_attempt(attempt_transition(values["pending"], EventStatus.IN_PROGRESS))
    event_id = values["pending"].event_id
    other = MockAdapter(
        script={event_id: (step,)},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    response = other.generate(values["request_evidence"].request)
    execution_payload = {
        "started_at": NOW,
        "finished_at": NOW,
        "http_status": None,
        "provider_metadata": {
            "adapter_response_id": response.response_id,
            "adapter_response_hash": response.record_hash,
            "adapter_outcome": response.outcome,
            "adapter_error": None if response.error is None else dict(response.error),
            "runtime_identity": dict(response.runtime_identity),
            "runtime_identity_hash": response.runtime_identity_hash,
            "script_hash": response.script_hash,
        },
        "usage": {},
        "finish_reason": None,
    }
    forged = PersistedInvocationEvidence.create(
        response=response,
        execution_payload=execution_payload,
        request_hash=values["request_evidence"].request_hash,
        parser_limits_hash=values["parser_limits"].record_hash,
        attempt_policy_hash=values["policy"].record_hash,
        adapter_execution_binding_hash=values["binding"].record_hash,
    )

    with pytest.raises(ValueError, match="script|step|commit|binding"):
        store.record_invocation_evidence(forged)

    assert store.invocation_evidence(values["pending"].attempt_id) is None


def land_invocation(store: RunStorage, values: Mapping[str, object]) -> PersistedInvocationEvidence:
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )
    store.append_attempt(attempt_transition(values["pending"], EventStatus.IN_PROGRESS))
    evidence = persisted_invocation(values)
    store.record_invocation_evidence(evidence)
    return evidence


def finalized_evidence(
    store: RunStorage,
    values: Mapping[str, object],
    invocation_value: PersistedInvocationEvidence,
) -> FinalizedAttemptEvidence:
    pending = values["pending"]
    response = invocation_value.response
    execution = invocation_value.to_payload()["execution_payload"]
    payload = pending.to_payload()
    payload.update(
        {
            "provider_request_id": response.provider_request_id,
            "provider_metadata": dict(execution["provider_metadata"]),
            "provider_metadata_hash": canonical_payload_hash(execution["provider_metadata"]),
            "http_status": execution["http_status"],
            "usage": dict(execution["usage"]),
            "usage_hash": canonical_payload_hash(execution["usage"]),
            "finish_reason": execution["finish_reason"],
            "started_at": execution["started_at"],
            "finished_at": execution["finished_at"],
        }
    )
    if response.outcome == "timeout":
        parse = ParseNotApplicableEvidence.create(
            response=response, parser_limits_hash=values["parser_limits"].record_hash
        )
        payload.update(
            {
                "status": EventStatus.FAILED.value,
                "raw_response": None,
                "raw_response_hash": None,
                "parsed_response": None,
                "parsed_response_hash": None,
                "error": dict(response.error),
            }
        )
        terminal = GenerationAttempt.from_payload(payload)
        terminal_hash = canonical_payload_hash(terminal.to_payload())
        failure_without_id = {
            "evidence_sequence": len(store.causal_evidence_prefix()) + 1,
            "previous_evidence_hash": None,
            "evidence_kind": "failure",
            "run_id": store.binding.run_id,
            "event_id": terminal.event_id,
            "event_ordinal": store.progress.next_event_ordinal,
            "attempt_id": terminal.attempt_id,
            "attempt_index": terminal.attempt_index,
            "terminal_transition_hash": terminal_hash,
            "terminal_attempt_hash": terminal_hash,
            "reason": "adapter_timeout",
            "policy_evidence": {
                "policy_id": values["policy"].policy_id,
                "policy_hash": values["policy"].record_hash,
            },
            "recorded_at": NOW,
        }
        failure = TerminalFailureEvidence(
            evidence_id="halt-" + canonical_payload_hash(failure_without_id),
            **failure_without_id,
        )
    else:
        parse = parse_agent_update(
            response, topic_package=prompt_topic(), limits=values["parser_limits"]
        )
        if parse.parsed is not None:
            parsed_payload = parse.parsed.to_payload()
            payload.update(
                {
                    "status": EventStatus.SUCCEEDED.value,
                    "raw_response": response.raw_response,
                    "raw_response_hash": response.raw_response_hash,
                    "parsed_response": parsed_payload,
                    "parsed_response_hash": canonical_payload_hash(parsed_payload),
                    "error": None,
                }
            )
            terminal = GenerationAttempt.from_payload(payload)
            failure = None
        else:
            payload.update(
                {
                    "status": EventStatus.FAILED.value,
                    "raw_response": response.raw_response,
                    "raw_response_hash": response.raw_response_hash,
                    "parsed_response": None,
                    "parsed_response_hash": None,
                    "error": dict(parse.error),
                }
            )
            terminal = GenerationAttempt.from_payload(payload)
            terminal_hash = canonical_payload_hash(terminal.to_payload())
            failure_without_id = {
                "evidence_sequence": len(store.causal_evidence_prefix()) + 1,
                "previous_evidence_hash": None,
                "evidence_kind": "failure",
                "run_id": store.binding.run_id,
                "event_id": terminal.event_id,
                "event_ordinal": store.progress.next_event_ordinal,
                "attempt_id": terminal.attempt_id,
                "attempt_index": terminal.attempt_index,
                "terminal_transition_hash": terminal_hash,
                "terminal_attempt_hash": terminal_hash,
                "reason": "parse_failure",
                "policy_evidence": {
                    "policy_id": values["policy"].policy_id,
                    "policy_hash": values["policy"].record_hash,
                },
                "recorded_at": NOW,
            }
            failure = TerminalFailureEvidence(
                evidence_id="halt-" + canonical_payload_hash(failure_without_id),
                **failure_without_id,
            )
    return FinalizedAttemptEvidence.create(
        request_hash=values["request_evidence"].request_hash,
        attempt=terminal,
        parse_evidence=parse,
        terminal_failure_evidence=failure,
    )


def test_finalized_attempt_atomically_lands_parse_and_terminal_transition(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)

    store.record_finalized_attempt(finalized)
    store.record_finalized_attempt(finalized)

    assert store.parse_evidence(finalized.attempt.attempt_id) == finalized.parse_evidence
    assert store.current_event_journal().latest_transition == finalized.attempt
    assert store.terminal_failure_evidence() is None
    references = store.evidence_references(finalized.attempt.event_id)
    assert references.event_input_evidence_id == values["event_input"].evidence_id
    assert references.request_id == values["request_evidence"].request_id
    assert references.invocation_evidence_id == invocation_value.evidence_id
    assert references.parse_evidence_id == finalized.parse_evidence.attempt_id
    assert references.terminal_attempt_id == finalized.attempt.attempt_id
    assert references.committed_event_id is None


@pytest.mark.parametrize(
    "field",
    (
        "started_at",
        "finished_at",
        "provider_request_id",
        "provider_metadata",
        "http_status",
        "usage",
        "finish_reason",
    ),
)
def test_finalization_rejects_every_forged_execution_projection(tmp_path: Path, field: str) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    payload = finalized.attempt.to_payload()
    if field == "started_at":
        payload[field] = "2026-08-17T23:59:59+00:00"
    elif field == "finished_at":
        payload[field] = "2026-08-18T00:00:01+00:00"
    elif field == "provider_request_id":
        payload[field] = "provider-forged"
    elif field == "provider_metadata":
        metadata = dict(payload[field])
        metadata["extra"] = "forged"
        payload[field] = metadata
        payload["provider_metadata_hash"] = canonical_payload_hash(metadata)
    elif field == "http_status":
        payload[field] = 201
    elif field == "usage":
        payload[field] = {"prompt_tokens": 30, "completion_tokens": 4, "total_tokens": 34}
        payload["usage_hash"] = canonical_payload_hash(payload[field])
    else:
        payload[field] = "length"
    forged_attempt = GenerationAttempt.from_payload(payload)
    forged = FinalizedAttemptEvidence.create(
        request_hash=finalized.request_hash,
        attempt=forged_attempt,
        parse_evidence=finalized.parse_evidence,
        terminal_failure_evidence=None,
    )

    with pytest.raises(ValueError, match="execution|response|invocation|terminal"):
        store.record_finalized_attempt(forged)

    assert store.parse_evidence(forged_attempt.attempt_id) is None
    assert store.current_event_journal().latest_transition.status is EventStatus.IN_PROGRESS


def test_failed_finalization_atomically_lands_parse_na_terminal_and_failure(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(
        tmp_path, script_step=MockScriptStep.timeout("provider timeout")
    )
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)

    store.record_finalized_attempt(finalized)

    assert store.parse_evidence(finalized.attempt.attempt_id) == finalized.parse_evidence
    assert store.current_event_journal().latest_transition == finalized.attempt
    assert store.terminal_failure_evidence() == finalized.terminal_failure_evidence
    assert store.execution_state().status is ExecutionStatus.FAILED


def test_finalized_replay_scopes_historical_failure_to_its_attempt(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(
        tmp_path,
        script_steps=(
            MockScriptStep.timeout("provider timeout"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "retry"}
            ),
        ),
    )
    first_invocation = land_invocation(store, values)
    failed = finalized_evidence(store, values, first_invocation)
    store.record_finalized_attempt(failed)
    store.record_finalized_attempt(failed)
    first_transitions = store.attempt_transitions(failed.attempt.attempt_id)
    failure = failed.terminal_failure_evidence
    assert failure is not None
    assert store.terminal_failure_evidence() == failure
    assert len(first_transitions) == 3

    store.authorize_resume(
        authorization_id="resume-finalized-replay-scope",
        event_id=failed.attempt.event_id,
        previous_terminal_failure_hash=failure.payload_hash,
        policy_evidence_id=values["policy"].policy_id,
        policy_evidence_hash=values["policy"].record_hash,
        authorized_at=NOW,
    )
    retry_request = AdapterRequest.create(
        prompt_view=values["event_input"].prompt_view,
        attempt_index=2,
        mock_seed=12345,
        mock_only=True,
    )
    retry_request_evidence = execution_evidence_module.AdapterRequestEvidence.create(
        request=retry_request,
        model_identity=values["binding"].model_identity,
        request_parameters={"temperature": 0.0},
        model_seed=12345,
        prompt_limits_hash=values["event_input"].prompt_view.limits_hash,
        parser_limits_hash=values["parser_limits"].record_hash,
        attempt_policy_hash=values["policy"].record_hash,
        adapter_execution_binding_hash=values["binding"].record_hash,
    )
    retry_payload = values["pending"].to_payload()
    retry_payload.update(
        {
            "attempt_id": retry_request.attempt_id,
            "attempt_index": 2,
            "request_id": retry_request.request_id,
            "model_seed": retry_request.mock_seed,
        }
    )
    retry_pending = GenerationAttempt.from_payload(retry_payload)
    retry_values = {
        **values,
        "request_evidence": retry_request_evidence,
        "pending": retry_pending,
    }
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=retry_request_evidence,
        pending_attempt=retry_pending,
    )
    store.append_attempt(attempt_transition(retry_pending, EventStatus.IN_PROGRESS))
    retry_invocation = persisted_invocation(retry_values)
    store.record_invocation_evidence(retry_invocation)
    succeeded = finalized_evidence(store, retry_values, retry_invocation)
    store.record_finalized_attempt(succeeded)
    before_transitions = store.attempt_transitions(succeeded.attempt.attempt_id)
    before_execution = store.execution_state()

    store.record_finalized_attempt(succeeded)

    assert store.attempt_transitions(failed.attempt.attempt_id) == first_transitions
    assert store.attempt_transitions(succeeded.attempt.attempt_id) == before_transitions
    assert len(before_transitions) == 3
    assert store.terminal_failure_evidence() == failure
    assert store._connection.execute("SELECT COUNT(*) FROM terminal_failures").fetchone()[0] == 1
    assert store.execution_state() == before_execution


def test_storage_retry_rejects_dotted_key_alias_without_pending_write(tmp_path: Path) -> None:
    baseline = {"sampling": {"temperature": 0.0, "top_p": 1.0}}
    store, values = prepared_evidence_bundle(
        tmp_path,
        script_steps=(
            MockScriptStep.timeout("reject dotted alias"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "must not land"}
            ),
        ),
        request_parameters=baseline,
        allowed_difference_fields=(
            "model_seed",
            "request_parameters.sampling.temperature",
        ),
    )
    first_invocation = land_invocation(store, values)
    failed = finalized_evidence(store, values, first_invocation)
    store.record_finalized_attempt(failed)
    failure = failed.terminal_failure_evidence
    assert failure is not None
    store.authorize_resume(
        authorization_id="resume-storage-dotted-alias",
        event_id=failed.attempt.event_id,
        previous_terminal_failure_hash=failure.payload_hash,
        policy_evidence_id=values["policy"].policy_id,
        policy_evidence_hash=values["policy"].record_hash,
        authorized_at=NOW,
    )
    retry_request = AdapterRequest.create(
        prompt_view=values["event_input"].prompt_view,
        attempt_index=2,
        mock_seed=12345,
        mock_only=True,
    )
    alias = {
        "sampling": {"top_p": 1.0},
        "sampling.temperature": 0.5,
    }
    retry_request_evidence = execution_evidence_module.AdapterRequestEvidence.create(
        request=retry_request,
        model_identity=values["binding"].model_identity,
        request_parameters=alias,
        model_seed=12345,
        prompt_limits_hash=values["event_input"].prompt_view.limits_hash,
        parser_limits_hash=values["parser_limits"].record_hash,
        attempt_policy_hash=values["policy"].record_hash,
        adapter_execution_binding_hash=values["binding"].record_hash,
    )
    retry_payload = values["pending"].to_payload()
    retry_payload.update(
        {
            "attempt_id": retry_request.attempt_id,
            "attempt_index": 2,
            "request_id": retry_request.request_id,
            "request_parameters": alias,
            "request_parameters_hash": canonical_payload_hash(alias),
        }
    )
    retry_pending = GenerationAttempt.from_payload(retry_payload)
    before = (store.current_event_journal(), store.attempts_for_event(failed.attempt.event_id))

    with pytest.raises(ValueError, match="key|segment|path|request parameters"):
        store.record_prepared_attempt(
            values["event_input"],
            policy=values["policy"],
            adapter_binding=values["binding"],
            request_evidence=retry_request_evidence,
            pending_attempt=retry_pending,
        )

    assert (
        store.current_event_journal(),
        store.attempts_for_event(failed.attempt.event_id),
    ) == before


def test_retry_references_follow_only_current_attempt_across_reopen_boundaries(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(
        tmp_path,
        script_steps=(
            MockScriptStep.timeout("provider timeout"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "retry"}
            ),
        ),
    )
    invocation_value = land_invocation(store, values)
    failed = finalized_evidence(store, values, invocation_value)
    store.record_finalized_attempt(failed)
    failure = store.terminal_failure_evidence()
    assert failure is not None
    authorization = store.authorize_resume(
        authorization_id="resume-current-prefix",
        event_id=failed.attempt.event_id,
        previous_terminal_failure_hash=failure.payload_hash,
        policy_evidence_id=values["policy"].policy_id,
        policy_evidence_hash=values["policy"].record_hash,
        authorized_at=NOW,
    )
    store = reopen_evidence_store(store, values)
    after_authorization = store.evidence_references(failed.attempt.event_id)
    assert after_authorization.terminal_attempt_id == failed.attempt.attempt_id

    request = AdapterRequest.create(
        prompt_view=values["event_input"].prompt_view,
        attempt_index=2,
        mock_seed=12345,
        mock_only=True,
    )
    request_evidence = execution_evidence_module.AdapterRequestEvidence.create(
        request=request,
        model_identity=values["binding"].model_identity,
        request_parameters={"temperature": 0.0},
        model_seed=12345,
        prompt_limits_hash=values["event_input"].prompt_view.limits_hash,
        parser_limits_hash=values["parser_limits"].record_hash,
        attempt_policy_hash=values["policy"].record_hash,
        adapter_execution_binding_hash=values["binding"].record_hash,
    )
    payload = values["pending"].to_payload()
    payload.update(
        {
            "attempt_id": request.attempt_id,
            "attempt_index": 2,
            "request_id": request.request_id,
            "model_seed": request.mock_seed,
        }
    )
    pending = GenerationAttempt.from_payload(payload)
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=request_evidence,
        pending_attempt=pending,
    )
    store = reopen_evidence_store(store, values)
    retry_pending = store.evidence_references(pending.event_id)
    assert retry_pending.request_id == request.request_id
    assert retry_pending.invocation_evidence_id is None
    assert retry_pending.parse_evidence_id is None
    assert retry_pending.terminal_attempt_id is None

    in_progress = attempt_transition(pending, EventStatus.IN_PROGRESS)
    store.append_attempt(in_progress)
    store = reopen_evidence_store(store, values)
    retry_running = store.evidence_references(pending.event_id)
    assert retry_running.request_id == request.request_id
    assert retry_running.invocation_evidence_id is None
    assert retry_running.parse_evidence_id is None
    assert retry_running.terminal_attempt_id is None
    assert store.terminal_failure_evidence_prefix() == (failure,)
    assert store.resume_authorization_evidence_prefix() == (authorization,)

    retry_values = {**values, "request_evidence": request_evidence, "pending": pending}
    retry_invocation = persisted_invocation(retry_values)
    store.record_invocation_evidence(retry_invocation)
    store = reopen_evidence_store(store, values)
    assert store.invocation_evidence(pending.attempt_id) == retry_invocation
    succeeded = finalized_evidence(store, retry_values, retry_invocation)
    store.record_finalized_attempt(succeeded)
    store = reopen_evidence_store(store, values)
    assert store.parse_evidence(pending.attempt_id) == succeeded.parse_evidence
    assert store.current_event_journal().latest_transition == succeeded.attempt


def test_finalized_failure_sql_error_rolls_back_parse_terminal_failure_and_execution(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(
        tmp_path, script_step=MockScriptStep.timeout("provider timeout")
    )
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    before = store.execution_state()
    store._connection.execute(
        """CREATE TRIGGER fail_terminal_failure BEFORE INSERT ON terminal_failures
           BEGIN SELECT RAISE(ABORT, 'injected terminal failure'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="injected terminal"):
        store.record_finalized_attempt(finalized)

    assert store.parse_evidence(finalized.attempt.attempt_id) is None
    assert store.current_event_journal().latest_transition.status is EventStatus.IN_PROGRESS
    assert store.terminal_failure_evidence() is None
    assert store.execution_state() == before


@pytest.mark.parametrize(
    ("table", "column", "reader"),
    (
        ("event_input_evidence", "record_hash", "event_input"),
        ("attempt_policy_evidence", "record_hash", "policy"),
        ("adapter_execution_bindings", "binding_id", "binding"),
        ("adapter_requests", "parser_limits_hash", "request"),
        ("invocation_evidence", "record_hash", "invocation"),
        ("parse_evidence", "kind", "parse"),
    ),
)
def test_typed_evidence_readers_reject_redundant_row_envelope_tamper(
    tmp_path: Path, table: str, column: str, reader: str
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    store.record_finalized_attempt(finalized)
    attempt_id = finalized.attempt.attempt_id
    event_id = finalized.attempt.event_id
    store._connection.execute("PRAGMA foreign_keys = OFF")
    if column == "kind":
        replacement = "not_applicable"
    elif column == "binding_id":
        replacement = "adapter-execution-binding-tampered"
    else:
        replacement = "f" * 64
    store._connection.execute(f"UPDATE {table} SET {column} = ?", (replacement,))
    store._connection.execute("PRAGMA foreign_keys = ON")

    with pytest.raises(ValueError, match="row|envelope|hash|kind|binding|column|key"):
        if reader == "event_input":
            store.event_input_evidence(event_id)
        elif reader == "policy":
            store.attempt_policy_evidence(event_id)
        elif reader == "binding":
            store.adapter_execution_binding(attempt_id)
        elif reader == "request":
            store.adapter_request_evidence(attempt_id)
        elif reader == "invocation":
            store.invocation_evidence(attempt_id)
        else:
            store.parse_evidence(attempt_id)


@pytest.mark.parametrize(
    "prefix",
    ("pending", "in_progress", "invocation", "terminal"),
)
def test_integrity_accepts_every_v6_evidence_durable_prefix(tmp_path: Path, prefix: str) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    store.record_prepared_attempt(
        values["event_input"],
        policy=values["policy"],
        adapter_binding=values["binding"],
        request_evidence=values["request_evidence"],
        pending_attempt=values["pending"],
    )
    if prefix != "pending":
        store.append_attempt(attempt_transition(values["pending"], EventStatus.IN_PROGRESS))
    if prefix in {"invocation", "terminal"}:
        invocation_value = persisted_invocation(values)
        store.record_invocation_evidence(invocation_value)
    if prefix == "terminal":
        store.record_finalized_attempt(finalized_evidence(store, values, invocation_value))

    store.verify_integrity()


@pytest.mark.parametrize(
    "step",
    (
        MockScriptStep.malformed("not-json"),
        MockScriptStep.timeout("provider timeout"),
    ),
)
def test_integrity_accepts_response_and_timeout_failed_v6_prefixes(
    tmp_path: Path, step: MockScriptStep
) -> None:
    store, values = prepared_evidence_bundle(tmp_path, script_step=step)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    store.record_finalized_attempt(finalized)

    store.verify_integrity()


@pytest.mark.parametrize(
    "table",
    (
        "event_input_evidence",
        "attempt_policy_evidence",
        "adapter_execution_bindings",
        "adapter_requests",
        "invocation_evidence",
        "parse_evidence",
    ),
)
def test_integrity_rejects_missing_v6_evidence_after_reopen(tmp_path: Path, table: str) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation_value = land_invocation(store, values)
    store.record_finalized_attempt(finalized_evidence(store, values, invocation_value))
    store.close()
    connection = sqlite3.connect(values["path"])
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(f"DELETE FROM {table}")
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="evidence|cover|binding|request|invocation|parse"):
        RunStorage.open(
            values["path"],
            manifest=values["manifest"],
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0001", "agent-0002"),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_integrity_rejects_hash_consistent_terminal_projection_tamper(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    store.record_finalized_attempt(finalized)
    payload = finalized.attempt.to_payload()
    parsed = dict(payload["parsed_response"])
    parsed["public_reason"] = "coordinated terminal tamper"
    payload["parsed_response"] = parsed
    payload["parsed_response_hash"] = canonical_payload_hash(parsed)
    encoded = storage_module._canonical_json(payload)
    payload_hash = canonical_payload_hash(payload)
    store._connection.execute(
        "UPDATE attempts SET payload_json = ?, payload_hash = ? WHERE attempt_id = ?",
        (encoded, payload_hash, finalized.attempt.attempt_id),
    )
    store._connection.execute(
        """UPDATE attempt_transitions SET payload_json = ?, payload_hash = ?
           WHERE attempt_id = ? AND status = ?""",
        (encoded, payload_hash, finalized.attempt.attempt_id, EventStatus.SUCCEEDED.value),
    )
    store._connection.commit()

    with pytest.raises(ValueError, match="parse|terminal|payload|response|evidence"):
        store.verify_integrity()


def test_integrity_rejects_unknown_nested_parse_payload_field(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    store.record_finalized_attempt(finalized)
    row = store._connection.execute(
        "SELECT payload FROM parse_evidence WHERE attempt_id = ?",
        (finalized.attempt.attempt_id,),
    ).fetchone()
    payload = json.loads(row[0])
    payload["parsed"]["forged_extra_field"] = "must not be normalized away"
    store._connection.execute(
        "UPDATE parse_evidence SET payload = ? WHERE attempt_id = ?",
        (storage_module._canonical_json(payload), finalized.attempt.attempt_id),
    )
    store._connection.commit()

    with pytest.raises(ValueError, match="parse evidence row envelope|hash"):
        store.verify_integrity()


@pytest.mark.parametrize("table", ("event_input_evidence", "adapter_requests"))
def test_integrity_hashes_raw_nested_v6_payload_before_normalization(
    tmp_path: Path, table: str
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    land_invocation(store, values)
    key = (
        values["pending"].event_id
        if table == "event_input_evidence"
        else values["pending"].attempt_id
    )
    key_column = "event_id" if table == "event_input_evidence" else "attempt_id"
    row = store._connection.execute(
        f"SELECT payload FROM {table} WHERE {key_column} = ?", (key,)
    ).fetchone()
    payload = json.loads(row[0])
    if table == "event_input_evidence":
        payload["prompt_view"]["current_private"]["forged_extra_field"] = True
    else:
        payload["request"]["rendered_messages"][0]["forged_extra_field"] = True
    store._connection.execute(
        f"UPDATE {table} SET payload = ? WHERE {key_column} = ?",
        (storage_module._canonical_json(payload), key),
    )
    store._connection.commit()

    with pytest.raises(ValueError, match="hash|row|payload"):
        store.verify_integrity()


def test_integrity_rejects_rehashed_request_prompt_limits_drift(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    land_invocation(store, values)
    attempt_id = values["pending"].attempt_id
    row = store._connection.execute(
        "SELECT payload FROM adapter_requests WHERE attempt_id = ?", (attempt_id,)
    ).fetchone()
    payload = json.loads(row[0])
    payload["prompt_limits_hash"] = "f" * 64
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    store._connection.execute(
        "UPDATE adapter_requests SET payload = ?, record_hash = ? WHERE attempt_id = ?",
        (storage_module._canonical_json(payload), payload["record_hash"], attempt_id),
    )
    store._connection.commit()

    with pytest.raises(ValueError, match="prompt|binding|drift"):
        store.verify_integrity()


def test_reopen_rejects_rehashed_first_request_with_ambiguous_parameter_key(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    land_invocation(store, values)
    attempt_id = values["pending"].attempt_id
    row = store._connection.execute(
        "SELECT payload FROM adapter_requests WHERE attempt_id = ?", (attempt_id,)
    ).fetchone()
    payload = json.loads(row[0])
    request_parameters = {"sampling.temperature": 0.0}
    payload["request_parameters"] = request_parameters
    payload["request_parameters_hash"] = canonical_payload_hash(request_parameters)
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    store._connection.execute(
        "UPDATE adapter_requests SET payload = ?, record_hash = ? WHERE attempt_id = ?",
        (storage_module._canonical_json(payload), payload["record_hash"], attempt_id),
    )
    store._connection.commit()

    with pytest.raises(ValueError, match="key|segment|path|request parameter"):
        reopen_evidence_store(store, values)


def test_reopen_rejects_rehashed_first_request_with_ambiguous_array_mapping_key(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    land_invocation(store, values)
    attempt_id = values["pending"].attempt_id
    row = store._connection.execute(
        "SELECT payload FROM adapter_requests WHERE attempt_id = ?", (attempt_id,)
    ).fetchone()
    payload = json.loads(row[0])
    request_parameters = {"groups": [{"sampling.temperature": 0.0}]}
    payload["request_parameters"] = request_parameters
    payload["request_parameters_hash"] = canonical_payload_hash(request_parameters)
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    store._connection.execute(
        "UPDATE adapter_requests SET payload = ?, record_hash = ? WHERE attempt_id = ?",
        (storage_module._canonical_json(payload), payload["record_hash"], attempt_id),
    )
    store._connection.commit()

    with pytest.raises(ValueError, match="key|segment|path|request parameter"):
        reopen_evidence_store(store, values)


@pytest.mark.parametrize(
    "field",
    (
        "started_at",
        "finished_at",
        "provider_request_id",
        "provider_metadata",
        "http_status",
        "usage",
        "finish_reason",
    ),
)
def test_integrity_rejects_hash_consistent_terminal_execution_tamper(
    tmp_path: Path, field: str
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    store.record_finalized_attempt(finalized)
    payload = finalized.attempt.to_payload()
    if field == "started_at":
        payload[field] = "2026-08-17T23:59:59+00:00"
    elif field == "finished_at":
        payload[field] = "2026-08-18T00:00:01+00:00"
    elif field == "provider_request_id":
        payload[field] = "provider-request-tampered"
    elif field == "provider_metadata":
        payload[field] = {**payload[field], "forged_execution_field": True}
        payload["provider_metadata_hash"] = canonical_payload_hash(payload[field])
    elif field == "http_status":
        payload[field] = 201
    elif field == "usage":
        payload[field] = {"prompt_tokens": 30, "completion_tokens": 4, "total_tokens": 34}
        payload["usage_hash"] = canonical_payload_hash(payload[field])
    else:
        payload[field] = "length"
    encoded = storage_module._canonical_json(payload)
    payload_hash = canonical_payload_hash(payload)
    store._connection.execute(
        "UPDATE attempts SET payload_json = ?, payload_hash = ? WHERE attempt_id = ?",
        (encoded, payload_hash, finalized.attempt.attempt_id),
    )
    store._connection.execute(
        """UPDATE attempt_transitions SET payload_json = ?, payload_hash = ?
           WHERE attempt_id = ? AND status = ?""",
        (encoded, payload_hash, finalized.attempt.attempt_id, EventStatus.SUCCEEDED.value),
    )
    store._connection.commit()

    with pytest.raises(ValueError, match="terminal|execution projection|invocation|IN_PROGRESS"):
        store.verify_integrity()


def test_integrity_accepts_committed_v6_success_history(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(tmp_path, single_event=True)
    invocation_value = land_invocation(store, values)
    finalized = finalized_evidence(store, values, invocation_value)
    store.record_finalized_attempt(finalized)
    run_manifest = values["manifest"]
    agent_id = run_manifest.schedule.slots[0].agent_id
    previous_state = store.private_state(agent_id)
    previous_cursor = store.feed_cursor(agent_id)
    previous_pointer = store.latest_public_pointer(agent_id)
    update = PrivateUpdate.create(
        topic_package=prompt_topic(),
        matched_seed=previous_state.matched_seed,
        agent_id=agent_id,
        event_id=finalized.attempt.event_id,
        event_ordinal=0,
        sequence_index=previous_state.successful_update_count,
        stance_label=finalized.attempt.parsed_response["stance"],
        reason=finalized.attempt.parsed_response["public_reason"],
        confidence=finalized.attempt.parsed_response["confidence"],
        published=run_manifest.schedule.slots[0].publish_flag,
        source_attempt_id=finalized.attempt.attempt_id,
        mock_only=True,
    )
    state = PrivateState.from_update(update, previous=previous_state, mock_only=True)
    cursor = previous_cursor.advance(0)
    post = PublicPost.from_private_update(update, mock_only=True) if update.published else None
    pointer = (
        LatestPublicPointer.from_post(post, previous=previous_pointer, mock_only=True)
        if post is not None
        else None
    )
    store.commit_success(
        successful_event(run_manifest, ordinal=0),
        final_attempt=finalized.attempt,
        private_update=update,
        private_state=state,
        feed_cursor=cursor,
        public_post=post,
        latest_public_pointer=pointer,
    )

    store.verify_integrity()
    store.assert_complete()


def successful_event(
    run_manifest: RunManifest, *, ordinal: int, attempt_count: int = 1
) -> GenerationEvent:
    slot = run_manifest.schedule.slots[ordinal]
    event_id = derive_event_id(run_manifest.run_id, ordinal)
    return GenerationEvent(
        run_id=run_manifest.run_id,
        event_id=event_id,
        event_ordinal=ordinal,
        sweep_index=slot.sweep_index,
        draw_index=slot.draw_index,
        agent_id=slot.agent_id,
        publish_flag=slot.publish_flag,
        exposure_id=f"exposure-{ordinal}",
        status=EventStatus.SUCCEEDED,
        attempt_ids=tuple(
            derive_attempt_id(event_id, index) for index in range(1, attempt_count + 1)
        ),
        failure_reason=None,
    )


def successful_state_records(
    run_manifest: RunManifest,
    *,
    ordinal: int,
    previous_state: PrivateState,
    previous_cursor: FeedCursor,
    previous_pointer: LatestPublicPointer | None = None,
    attempt_index: int = 1,
) -> tuple[PrivateUpdate, PrivateState, FeedCursor, PublicPost | None, LatestPublicPointer | None]:
    slot = run_manifest.schedule.slots[ordinal]
    event_id = derive_event_id(run_manifest.run_id, ordinal)
    update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id=slot.agent_id,
        event_id=event_id,
        event_ordinal=ordinal,
        sequence_index=previous_state.successful_update_count,
        stance_label="neutral",
        reason=f"reason-{ordinal}-{attempt_index}",
        confidence=3,
        published=slot.publish_flag,
        source_attempt_id=derive_attempt_id(event_id, attempt_index),
        mock_only=True,
    )
    state = PrivateState.from_update(update, previous=previous_state, mock_only=True)
    cursor = previous_cursor.advance(ordinal)
    post = PublicPost.from_private_update(update, mock_only=True) if slot.publish_flag else None
    pointer = (
        LatestPublicPointer.from_post(post, previous=previous_pointer, mock_only=True)
        if post is not None
        else None
    )
    return update, state, cursor, post, pointer


def commit_fixture_event(store: RunStorage, run_manifest: RunManifest, ordinal: int) -> None:
    final_attempt = attempt(run_manifest, ordinal=ordinal, status=EventStatus.SUCCEEDED)
    append_terminal_attempt(store, final_attempt)
    agent_id = run_manifest.schedule.slots[ordinal].agent_id
    update, state, cursor, post, pointer = successful_state_records(
        run_manifest,
        ordinal=ordinal,
        previous_state=store.private_state(agent_id),  # type: ignore[arg-type]
        previous_cursor=store.feed_cursor(agent_id),  # type: ignore[arg-type]
        previous_pointer=store.latest_public_pointer(agent_id),
    )
    store.commit_success(
        successful_event(run_manifest, ordinal=ordinal),
        final_attempt=final_attempt,
        private_update=update,
        private_state=state,
        feed_cursor=cursor,
        public_post=post,
        latest_public_pointer=pointer,
    )


def test_create_close_and_reopen_binds_run_protocol_schedule_and_artifacts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    artifacts = {"population": "d" * 64, "network": "e" * 64}

    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        binding = store.binding
        assert binding.schema_version == "paper1.run-storage.v6"
        assert binding.run_id == run_manifest.run_id
        assert binding.run_spec_hash == run_manifest.run_spec_hash
        assert binding.protocol_hash == run_manifest.protocol_hash
        assert binding.schedule_hash == run_manifest.schedule_hash
        assert dict(binding.artifact_hashes) == artifacts

    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as reopened:
        assert reopened.binding == binding
        assert reopened.progress.next_event_ordinal == 0
        assert reopened.progress.expected_event_count == run_manifest.schedule.count

    with pytest.raises(ValueError, match="artifact"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={**artifacts, "network": "f" * 64},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_new_store_has_v6_evidence_schema_and_constraints(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        assert store.binding.schema_version == "paper1.run-storage.v6"

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "event_input_evidence",
            "attempt_policy_evidence",
            "adapter_execution_bindings",
            "adapter_requests",
            "invocation_evidence",
            "parse_evidence",
        } <= tables

        expected_columns = {
            "event_input_evidence": {"event_id", "payload", "record_hash"},
            "attempt_policy_evidence": {"event_id", "payload", "record_hash"},
            "adapter_execution_bindings": {"binding_id", "payload", "record_hash"},
            "adapter_requests": {
                "attempt_id",
                "event_id",
                "adapter_binding_hash",
                "parser_limits_hash",
                "policy_hash",
                "payload",
                "record_hash",
            },
            "invocation_evidence": {
                "attempt_id",
                "response_payload",
                "execution_payload",
                "record_hash",
            },
            "parse_evidence": {"attempt_id", "kind", "payload", "record_hash"},
        }
        for table, columns in expected_columns.items():
            observed = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert observed == columns

        expected_foreign_keys = {
            "attempt_policy_evidence": {("event_id", "event_input_evidence", "event_id")},
            "adapter_requests": {
                ("event_id", "event_input_evidence", "event_id"),
                ("adapter_binding_hash", "adapter_execution_bindings", "record_hash"),
                ("event_id", "attempt_policy_evidence", "event_id"),
                ("policy_hash", "attempt_policy_evidence", "record_hash"),
            },
            "invocation_evidence": {("attempt_id", "adapter_requests", "attempt_id")},
            "parse_evidence": {("attempt_id", "adapter_requests", "attempt_id")},
        }
        for table, expected in expected_foreign_keys.items():
            observed = {
                (row[3], row[2], row[4])
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")
            }
            assert observed == expected

        for table in (
            "event_input_evidence",
            "adapter_execution_bindings",
            "adapter_requests",
            "invocation_evidence",
            "parse_evidence",
        ):
            unique_indexes = {
                tuple(column[2] for column in connection.execute(f"PRAGMA index_info({index[1]})"))
                for index in connection.execute(f"PRAGMA index_list({table})")
                if index[2]
            }
            assert ("record_hash",) in unique_indexes

        policy_unique_indexes = {
            tuple(column[2] for column in connection.execute(f"PRAGMA index_info({index[1]})"))
            for index in connection.execute("PRAGMA index_list(attempt_policy_evidence)")
            if index[2]
        }
        assert ("event_id", "record_hash") in policy_unique_indexes
        assert ("record_hash",) not in policy_unique_indexes

        request_indexes = {
            tuple(column[2] for column in connection.execute(f"PRAGMA index_info({index[1]})"))
            for index in connection.execute("PRAGMA index_list(adapter_requests)")
        }
        assert {
            ("event_id",),
            ("adapter_binding_hash",),
            ("parser_limits_hash",),
            ("policy_hash",),
        } <= request_indexes

        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO event_input_evidence VALUES (?, ?, ?)",
            ("event-1", "{}", "a" * 64),
        )
        connection.execute(
            "INSERT INTO attempt_policy_evidence VALUES (?, ?, ?)",
            ("event-1", "{}", "b" * 64),
        )
        connection.execute(
            "INSERT INTO event_input_evidence VALUES (?, ?, ?)",
            ("event-2", '{"event":2}', "3" * 64),
        )
        connection.execute(
            "INSERT INTO attempt_policy_evidence VALUES (?, ?, ?)",
            ("event-2", "{}", "b" * 64),
        )
        connection.execute(
            "INSERT INTO adapter_execution_bindings VALUES (?, ?, ?)",
            ("binding-1", "{}", "c" * 64),
        )
        connection.execute(
            "INSERT INTO adapter_requests VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("attempt-1", "event-1", "c" * 64, "d" * 64, "b" * 64, "{}", "e" * 64),
        )
        connection.execute(
            "INSERT INTO adapter_requests VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("attempt-2", "event-2", "c" * 64, "d" * 64, "b" * 64, "{}", "4" * 64),
        )
        connection.execute(
            "INSERT INTO invocation_evidence VALUES (?, ?, ?, ?)",
            ("attempt-1", "{}", "{}", "f" * 64),
        )
        connection.execute(
            "INSERT INTO parse_evidence VALUES (?, ?, ?, ?)",
            ("attempt-1", "parsed", "{}", "0" * 64),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO parse_evidence VALUES (?, ?, ?, ?)",
                ("attempt-2", "invalid", "{}", "1" * 64),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO invocation_evidence VALUES (?, ?, ?, ?)",
                ("missing-attempt", "{}", "{}", "2" * 64),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO adapter_requests VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "attempt-3",
                    "event-1",
                    "c" * 64,
                    "d" * 64,
                    "b" * 64,
                    "{}",
                    "e" * 64,
                ),
            )
        connection.execute(
            "INSERT INTO event_input_evidence VALUES (?, ?, ?)",
            ("event-3", '{"event":3}', "5" * 64),
        )
        connection.execute(
            "INSERT INTO attempt_policy_evidence VALUES (?, ?, ?)",
            ("event-3", '{"policy":3}', "6" * 64),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO adapter_requests VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "attempt-3",
                    "event-3",
                    "c" * 64,
                    "d" * 64,
                    "b" * 64,
                    "{}",
                    "7" * 64,
                ),
            )


@pytest.mark.parametrize("user_version", (5, 999))
def test_open_rejects_wrong_user_version_without_any_file_or_sidecar_mutation(
    tmp_path: Path, user_version: int
) -> None:
    database = tmp_path / f"run-v{user_version}.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA user_version = {user_version}")
        connection.execute(
            "CREATE TABLE binding (singleton INTEGER PRIMARY KEY, schema_version TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO binding VALUES (1, ?)",
            (f"paper1.run-storage.v{user_version}",),
        )

    before_bytes = database.read_bytes()
    before_directory = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    run_manifest = manifest()
    with pytest.raises(ValueError, match="storage schema version.*unsupported"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )

    assert database.read_bytes() == before_bytes
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before_directory


@pytest.mark.parametrize("user_version", (5, 999))
def test_read_only_wrong_version_reaches_version_gate_without_mutation(
    tmp_path: Path, user_version: int
) -> None:
    database = tmp_path / f"read-only-v{user_version}.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA user_version = {user_version}")
        connection.execute("CREATE TABLE legacy_fixture (value TEXT NOT NULL)")

    original_mode = stat.S_IMODE(database.stat().st_mode)
    os.chmod(database, stat.S_IREAD)
    before_bytes = database.read_bytes()
    before_directory = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    run_manifest = manifest()
    try:
        with pytest.raises(ValueError, match="storage schema version.*unsupported"):
            RunStorage.open(
                database,
                manifest=run_manifest,
                artifact_hashes={"population": SHA_B},
                expected_agent_ids=expected_agent_ids(run_manifest),
                expected_exposure_mode="self_history_only",
                expected_exposure_graph_hash=None,
            )
        assert database.read_bytes() == before_bytes
        assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before_directory
    finally:
        os.chmod(database, original_mode | stat.S_IWRITE)


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_open_rejects_any_sqlite_sidecar_without_mutation(tmp_path: Path, suffix: str) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    Path(f"{database}{suffix}").write_bytes(b"stale-sidecar-fixture")
    before_directory = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    with pytest.raises(ValueError, match="sidecar|rollback image"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before_directory


def test_open_rechecks_sidecars_immediately_before_read_write_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    before_bytes = database.read_bytes()
    sidecar = Path(f"{database}-wal")
    real_connect = sqlite3.connect
    connect_uris: list[str] = []

    class RacingVersionConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(self, statement: str) -> sqlite3.Cursor:
            return self._connection.execute(statement)

        def close(self) -> None:
            self._connection.close()
            sidecar.write_bytes(b"appeared-after-version-probe")

    def racing_connect(database_uri: str, **kwargs: object) -> RacingVersionConnection:
        connect_uris.append(database_uri)
        if "immutable=1" not in database_uri:
            pytest.fail("read-write SQLite connection opened after a sidecar appeared")
        return RacingVersionConnection(real_connect(database_uri, **kwargs))

    monkeypatch.setattr(storage_module.sqlite3, "connect", racing_connect)
    with pytest.raises(ValueError, match="sidecar|rollback image"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )

    assert connect_uris == [database.absolute().as_uri() + "?mode=ro&immutable=1"]
    assert database.read_bytes() == before_bytes
    assert sidecar.read_bytes() == b"appeared-after-version-probe"


def test_normal_connection_rechecks_version_before_mutable_pragmas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    real_connect = sqlite3.connect
    read_write_statements: list[str] = []

    class RacingVersionConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(self, statement: str) -> sqlite3.Cursor:
            return self._connection.execute(statement)

        def close(self) -> None:
            self._connection.close()
            with real_connect(database) as drift_connection:
                drift_connection.execute("PRAGMA user_version = 5")

    class TrackingReadWriteConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(self, statement: str) -> sqlite3.Cursor:
            read_write_statements.append(statement)
            return self._connection.execute(statement)

        def close(self) -> None:
            self._connection.close()

    def racing_connect(
        database_uri: str, **kwargs: object
    ) -> RacingVersionConnection | TrackingReadWriteConnection:
        connection = real_connect(database_uri, **kwargs)
        if "immutable=1" in database_uri:
            return RacingVersionConnection(connection)
        return TrackingReadWriteConnection(connection)

    monkeypatch.setattr(storage_module.sqlite3, "connect", racing_connect)
    with pytest.raises(ValueError, match="storage schema version.*unsupported.*found 5"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )

    assert read_write_statements == ["PRAGMA user_version"]


@pytest.mark.parametrize(("main_version", "wal_version"), ((5, 6), (6, 5)))
def test_open_rejects_committed_wal_before_immutable_version_probe(
    tmp_path: Path, main_version: int, wal_version: int
) -> None:
    database = tmp_path / "wal-backed.sqlite3"
    writer = sqlite3.connect(database)
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("CREATE TABLE wal_fixture (value TEXT NOT NULL)")
        writer.execute(f"PRAGMA user_version = {main_version}")
        writer.commit()
        assert writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        assert int.from_bytes(database.read_bytes()[60:64], "big") == main_version

        writer.execute(f"PRAGMA user_version = {wal_version}")
        writer.execute("INSERT INTO wal_fixture VALUES ('committed-in-wal')")
        writer.commit()
        assert writer.execute("PRAGMA user_version").fetchone() == (wal_version,)
        assert Path(f"{database}-wal").exists()
        before_directory = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
        run_manifest = manifest()

        with pytest.raises(ValueError, match="sidecar|rollback image"):
            RunStorage.open(
                database,
                manifest=run_manifest,
                artifact_hashes={"population": SHA_B},
                expected_agent_ids=expected_agent_ids(run_manifest),
                expected_exposure_mode="self_history_only",
                expected_exposure_graph_hash=None,
            )

        assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before_directory
    finally:
        writer.close()


def test_failed_attempt_is_append_only_and_does_not_mutate_research_state(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        failed = attempt(run_manifest)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, failed)

        assert store.attempts_for_event(failed.event_id) == (failed,)
        assert store.progress.next_event_ordinal == 0
        assert store.progress.succeeded_event_count == 0
        assert store.event_at(0) is None
        assert store.private_state("agent-0") == initial_records("agent-0")[1]
        assert store.latest_public_pointer("agent-0") == initial_records("agent-0")[3]
        assert store.feed_cursor("agent-0") == initial_records("agent-0")[4]

        with pytest.raises(ValueError, match="append-only|terminal attempt"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(failed)


def test_attempts_reject_gaps_future_events_and_cross_run_identity(tmp_path: Path) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with pytest.raises(ValueError, match="attempt index"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(
                attempt_transition(attempt(run_manifest, index=2), EventStatus.PENDING)
            )
        with pytest.raises(ValueError, match="next event"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(
                attempt_transition(attempt(run_manifest, ordinal=1), EventStatus.PENDING)
            )

        foreign = manifest(schedule(publish_flags=(True, True)))
        with pytest.raises(ValueError, match="run"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(attempt_transition(attempt(foreign), EventStatus.PENDING))


def test_success_commit_is_atomic_and_publish_false_preserves_latest_public(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    initial = initial_records("agent-0")
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        final_attempt = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, final_attempt)
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
        )
        before_chain = store.progress.event_chain_head

        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=final_attempt,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )

        assert store.event_at(0) == successful_event(run_manifest, ordinal=0)
        assert store.private_state("agent-0") == state
        assert store.feed_cursor("agent-0") == cursor
        assert store.latest_public_pointer("agent-0") == initial[3]
        assert store.public_posts_for_agent("agent-0") == (initial[2],)
        assert store.progress.next_event_ordinal == 1
        assert store.progress.succeeded_event_count == 1
        assert store.progress.event_chain_head != before_chain


def test_publish_true_appends_post_and_replaces_latest_pointer(tmp_path: Path) -> None:
    run_manifest = manifest()
    first_initial = initial_records("agent-0")
    second_initial = initial_records("agent-1")
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*first_initial)
        store.initialize_agent(*second_initial)

        first_attempt = attempt(run_manifest, ordinal=0, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, first_attempt)
        first_records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=first_initial[1],
            previous_cursor=first_initial[4],
            previous_pointer=first_initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=first_attempt,
            private_update=first_records[0],
            private_state=first_records[1],
            feed_cursor=first_records[2],
            public_post=first_records[3],
            latest_public_pointer=first_records[4],
        )

        second_attempt = attempt(run_manifest, ordinal=1, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, second_attempt)
        second_records = successful_state_records(
            run_manifest,
            ordinal=1,
            previous_state=second_initial[1],
            previous_cursor=second_initial[4],
            previous_pointer=second_initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=1),
            final_attempt=second_attempt,
            private_update=second_records[0],
            private_state=second_records[1],
            feed_cursor=second_records[2],
            public_post=second_records[3],
            latest_public_pointer=second_records[4],
        )

        assert second_records[3] is not None
        assert second_records[4] is not None
        assert store.public_posts_for_agent("agent-1") == (second_initial[2], second_records[3])
        assert store.latest_public_pointer("agent-1") == second_records[4]
        assert store.assert_complete() is None


def test_complete_rejects_incomplete_run(tmp_path: Path) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with pytest.raises(ValueError, match="all expected events"):
            store.assert_complete()


@pytest.mark.parametrize(
    ("table", "operation"),
    (
        ("private_states", "UPDATE"),
        ("public_posts", "INSERT"),
        ("feed_cursors", "UPDATE"),
        ("progress", "UPDATE"),
    ),
)
def test_success_transaction_rolls_back_every_research_state_on_mid_commit_failure(
    tmp_path: Path, table: str, operation: str
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(True,)))
    initial = initial_records("agent-0")
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        final_attempt = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, final_attempt)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        with sqlite3.connect(database) as injector:
            injector.execute(
                f"""CREATE TRIGGER fail_mid_commit BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT, 'injected failure'); END"""
            )

        with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
            store.commit_success(
                successful_event(run_manifest, ordinal=0),
                final_attempt=final_attempt,
                private_update=records[0],
                private_state=records[1],
                feed_cursor=records[2],
                public_post=records[3],
                latest_public_pointer=records[4],
            )

        assert store.event_at(0) is None
        assert store.private_state("agent-0") == initial[1]
        assert store.latest_public_pointer("agent-0") == initial[3]
        assert store.feed_cursor("agent-0") == initial[4]
        assert store.public_posts_for_agent("agent-0") == (initial[2],)
        assert store.progress.next_event_ordinal == 0
        assert store.attempts_for_event(final_attempt.event_id) == (final_attempt,)

        with sqlite3.connect(database) as injector:
            injector.execute("DROP TRIGGER fail_mid_commit")
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=final_attempt,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        store.assert_complete()


def test_private_updates_for_agent_replays_round0_and_continuous_history(tmp_path: Path) -> None:
    run_manifest = manifest(schedule(publish_flags=(False, False)))
    with RunStorage.create(
        tmp_path / "history.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        commit_fixture_event(store, run_manifest, 0)
        history = store.private_updates_for_agent("agent-0")
        assert isinstance(history, tuple)
        assert tuple(item.sequence_index for item in history) == (0, 1)
        assert history[-1].record_hash == store.private_state("agent-0").latest_update_hash  # type: ignore[union-attr]
        store._connection.execute(
            "UPDATE private_updates SET payload_hash = ? WHERE agent_id = ? AND event_ordinal = ?",
            (SHA_A, "agent-0", 0),
        )
        with pytest.raises(ValueError, match="hash"):
            store.private_updates_for_agent("agent-0")


def test_current_event_journal_is_typed_and_never_chooses_retry_policy(tmp_path: Path) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "journal.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        initial = store.current_event_journal()
        assert isinstance(initial, EventJournalState)
        assert initial.event_id == derive_event_id(run_manifest.run_id, 0)
        assert initial.next_attempt_index == 1
        assert initial.latest_transition is None
        assert initial.resume_state == "new_attempt"
        failed = attempt(run_manifest)
        append_terminal_attempt(store, failed)
        resumed = store.current_event_journal()
        assert resumed.next_attempt_index == 2
        assert resumed.latest_transition == failed
        assert resumed.resume_state == "failed_attempt_requires_external_authorization"
        assert not hasattr(resumed, "max_attempts")
        projected = store.execution_state()
        assert projected.event_ids == (failed.event_id,)
        assert projected.status_counts[EventStatus.FAILED.value] == 1
        assert projected.status is ExecutionStatus.RUNNING


def test_current_event_journal_never_reuses_prior_event_halt_authorization(
    tmp_path: Path,
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False, False)))
    database = tmp_path / "cross-event-journal.sqlite3"
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        failed0 = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed0)
        failure0 = store.record_terminal_failure(
            event_id=failed0.event_id,
            reason="event zero halt",
            policy_evidence={"policy_id": "halt-0", "policy_hash": SHA_A},
            recorded_at=NOW,
        )
        store.authorize_resume(
            authorization_id="resume-event-0",
            event_id=failed0.event_id,
            previous_terminal_failure_hash=failure0.payload_hash,
            policy_evidence_id="retry-0",
            policy_evidence_hash=SHA_B,
            authorized_at="2026-08-30T01:00:00+00:00",
        )
        succeeded0 = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, succeeded0)
        records0 = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=store.private_state("agent-0"),  # type: ignore[arg-type]
            previous_cursor=store.feed_cursor("agent-0"),  # type: ignore[arg-type]
            previous_pointer=store.latest_public_pointer("agent-0"),
            attempt_index=2,
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=2),
            final_attempt=succeeded0,
            private_update=records0[0],
            private_state=records0[1],
            feed_cursor=records0[2],
            public_post=records0[3],
            latest_public_pointer=records0[4],
        )
        failed1 = attempt(run_manifest, ordinal=1, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed1)
        journal = store.current_event_journal()
        assert journal.event_id == failed1.event_id
        assert journal.latest_transition == failed1
        assert journal.resume_state == "failed_attempt_requires_external_authorization"

    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as reopened:
        journal = reopened.current_event_journal()
        assert journal.event_id == derive_event_id(run_manifest.run_id, 1)
        assert journal.resume_state == "failed_attempt_requires_external_authorization"


def test_execution_state_is_separate_hash_bound_projection_and_updates_with_success(
    tmp_path: Path,
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    with RunStorage.create(
        tmp_path / "execution.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        baseline_hash = store.binding.manifest_hash
        seal_expected_initial_state(store, run_manifest)
        before = store.execution_state()
        assert before.status is ExecutionStatus.RUNNING
        assert before.event_ids == ()
        assert before.payload_hash == canonical_payload_hash(before.to_payload())
        commit_fixture_event(store, run_manifest, 0)
        after = store.execution_state()
        assert after.status is ExecutionStatus.COMPLETE
        assert after.event_ids == (derive_event_id(run_manifest.run_id, 0),)
        assert after.status_counts[EventStatus.SUCCEEDED.value] == 1
        assert store.binding.manifest_hash == baseline_hash


def test_terminal_halt_is_append_only_explicit_and_never_advances_research_state(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "halt.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        failed = attempt(run_manifest)
        append_terminal_attempt(store, failed)
        before = store.progress
        evidence = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="caller-authorized terminal stop",
            policy_evidence={"policy_id": "frozen-policy", "policy_hash": SHA_A},
            recorded_at=NOW,
        )
        assert evidence.event_id == failed.event_id
        assert store.terminal_failure_evidence() == evidence
        assert store.execution_state().status is ExecutionStatus.FAILED
        assert store.progress == before
        assert store.event_at(0) is None
        with pytest.raises(ValueError, match="already halted|append-only"):
            store.record_terminal_failure(
                event_id=failed.event_id,
                reason="second decision",
                policy_evidence={"policy_id": "other", "policy_hash": SHA_B},
                recorded_at=NOW,
            )
        with pytest.raises(ValueError, match="halted"):
            store.append_attempt(
                attempt_transition(attempt(run_manifest, index=2), EventStatus.PENDING)
            )


def test_execution_state_constructor_deeply_normalizes_mutable_inputs() -> None:
    event_ids = ["event-0"]
    failed_ids = ["event-0"]
    counts = {status.value: 0 for status in EventStatus}
    counts[EventStatus.FAILED.value] = 1
    value = ExecutionState(
        schema_version="paper1.execution-state.v1",
        run_id="run-immutable",
        baseline_manifest_hash=SHA_A,
        status=ExecutionStatus.FAILED,
        next_event_ordinal=0,
        expected_event_count=1,
        current_event_id="event-0",
        event_ids=event_ids,  # type: ignore[arg-type]
        status_counts=counts,
        failed_event_ids=failed_ids,  # type: ignore[arg-type]
    )
    event_ids.append("event-forged")
    failed_ids.clear()
    counts[EventStatus.FAILED.value] = 0
    assert value.event_ids == ("event-0",)
    assert value.failed_event_ids == ("event-0",)
    assert value.status_counts[EventStatus.FAILED.value] == 1
    with pytest.raises(TypeError):
        value.status_counts[EventStatus.FAILED.value] = 0  # type: ignore[index]


def test_halted_run_requires_canonical_append_only_resume_authorization(tmp_path: Path) -> None:
    run_manifest = manifest()
    database = tmp_path / "authorized-resume.sqlite3"
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with store.acquire_run_lease():
            seal_expected_initial_state(store, run_manifest)
            failed = attempt(run_manifest)
            append_terminal_attempt(store, failed)
            failure = store.record_terminal_failure(
                event_id=failed.event_id,
                reason="caller-authorized terminal stop",
                policy_evidence={"policy_id": "frozen-policy", "policy_hash": SHA_A},
                recorded_at=NOW,
            )
            before = store.recovery_evidence()
            with pytest.raises(ValueError, match="halted|authorization"):
                store.append_attempt(
                    attempt_transition(attempt(run_manifest, index=2), EventStatus.PENDING)
                )
            with pytest.raises(ValueError, match="bind"):
                store.authorize_resume(
                    authorization_id="wrong-event-authorization",
                    event_id="event-forged",
                    previous_terminal_failure_hash=failure.payload_hash,
                    policy_evidence_id="external-retry-policy",
                    policy_evidence_hash=SHA_B,
                    authorized_at="2026-08-30T01:00:00+00:00",
                )
            authorization = store.authorize_resume(
                authorization_id="resume-authorization-1",
                event_id=failed.event_id,
                previous_terminal_failure_hash=failure.payload_hash,
                policy_evidence_id="external-retry-policy",
                policy_evidence_hash=SHA_B,
                authorized_at="2026-08-30T01:00:00+00:00",
            )
            assert isinstance(authorization, ResumeAuthorizationEvidence)
            assert store.execution_state().status is ExecutionStatus.RUNNING
            assert store.current_event_journal().resume_state == "retry_same_event"
            retry_pending = attempt_transition(attempt(run_manifest, index=2), EventStatus.PENDING)
            store.append_attempt(retry_pending)
            assert store.current_event_journal().latest_transition == retry_pending
            assert store.recovery_evidence()["next_event_ordinal"] == before["next_event_ordinal"]
            after = store.recovery_evidence()
            for name in (
                "next_event_ordinal",
                "private_states",
                "public_stock",
                "latest_public_pointers",
                "feed_cursors",
                "event_chain_head",
            ):
                assert after[name] == before[name]
            with pytest.raises(ValueError, match="duplicate|append-only|already"):
                store.authorize_resume(
                    authorization_id="resume-authorization-1",
                    event_id=failed.event_id,
                    previous_terminal_failure_hash=failure.payload_hash,
                    policy_evidence_id="external-retry-policy",
                    policy_evidence_hash=SHA_B,
                    authorized_at="2026-08-30T01:00:00+00:00",
                )
            with pytest.raises(ValueError, match="append-only|already"):
                store.authorize_resume(
                    authorization_id="forked-authorization",
                    event_id=failed.event_id,
                    previous_terminal_failure_hash=failure.payload_hash,
                    policy_evidence_id="different-policy",
                    policy_evidence_hash=SHA_A,
                    authorized_at="2026-08-30T02:00:00+00:00",
                )

    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as reopened:
        assert reopened.execution_state().status is ExecutionStatus.RUNNING
        assert reopened.current_event_journal().resume_state == (
            "pending_attempt_requires_same_request"
        )
        assert reopened.resume_authorization_evidence().authorization_id == (
            "resume-authorization-1"
        )


@pytest.mark.parametrize("tamper", ["delete", "row-event", "payload"])
def test_reopen_fails_closed_on_resume_authorization_tamper(tmp_path: Path, tamper: str) -> None:
    run_manifest = manifest()
    database = tmp_path / f"authorization-{tamper}.sqlite3"
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with store.acquire_run_lease():
            seal_expected_initial_state(store, run_manifest)
            failed = attempt(run_manifest)
            append_terminal_attempt(store, failed)
            failure = store.record_terminal_failure(
                event_id=failed.event_id,
                reason="halt",
                policy_evidence={"policy_id": "halt-policy", "policy_hash": SHA_A},
                recorded_at=NOW,
            )
            store.authorize_resume(
                authorization_id="resume-tamper-test",
                event_id=failed.event_id,
                previous_terminal_failure_hash=failure.payload_hash,
                policy_evidence_id="retry-policy",
                policy_evidence_hash=SHA_B,
                authorized_at="2026-08-30T01:00:00+00:00",
            )
    with sqlite3.connect(database) as connection:
        if tamper == "delete":
            connection.execute("DELETE FROM resume_authorizations")
        elif tamper == "row-event":
            connection.execute("UPDATE resume_authorizations SET event_id = ?", ("event-forged",))
        else:
            connection.execute("UPDATE resume_authorizations SET payload_json = '{}' ")
    with pytest.raises(ValueError, match="authorization|execution state"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_same_event_supports_multiple_append_only_halt_authorization_cycles(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "multiple-halts.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        for index in (1, 2):
            failed = attempt(run_manifest, index=index)
            append_terminal_attempt(store, failed)
            failure = store.record_terminal_failure(
                event_id=failed.event_id,
                reason=f"external halt {index}",
                policy_evidence={"policy_id": f"halt-policy-{index}", "policy_hash": SHA_A},
                recorded_at=f"2026-08-30T0{index}:00:00+00:00",
            )
            store.authorize_resume(
                authorization_id=f"resume-{index}",
                event_id=failed.event_id,
                previous_terminal_failure_hash=failure.payload_hash,
                policy_evidence_id=f"retry-policy-{index}",
                policy_evidence_hash=SHA_B,
                authorized_at=f"2026-08-30T1{index}:00:00+00:00",
            )
        assert len(store.terminal_failure_evidence_prefix()) == 2
        assert len(store.resume_authorization_evidence_prefix()) == 2
        assert store.execution_state().status is ExecutionStatus.RUNNING
        store.verify_integrity()


def test_halt_authorization_cycles_form_one_explicit_canonical_causal_chain(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "causal-chain.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        previous_hash = None
        for cycle, attempt_index in enumerate((1, 2), start=1):
            failed = attempt(run_manifest, index=attempt_index)
            append_terminal_attempt(store, failed)
            failure = store.record_terminal_failure(
                event_id=failed.event_id,
                reason=f"halt {cycle}",
                policy_evidence={"policy_id": f"halt-{cycle}", "policy_hash": SHA_A},
                recorded_at=f"2026-08-30T0{cycle}:00:00+00:00",
            )
            assert failure.evidence_sequence == cycle * 2 - 1
            assert failure.previous_evidence_hash == previous_hash
            assert failure.evidence_kind == "failure"
            assert failure.attempt_id == failed.attempt_id
            assert failure.attempt_index == attempt_index
            assert failure.terminal_transition_hash == canonical_payload_hash(failed.to_payload())
            authorization = store.authorize_resume(
                authorization_id=f"resume-causal-{cycle}",
                event_id=failed.event_id,
                previous_terminal_failure_hash=failure.payload_hash,
                policy_evidence_id=f"retry-{cycle}",
                policy_evidence_hash=SHA_B,
                authorized_at=f"2026-08-30T1{cycle}:00:00+00:00",
            )
            assert authorization.evidence_sequence == cycle * 2
            assert authorization.previous_evidence_hash == failure.payload_hash
            assert authorization.evidence_kind == "authorization"
            assert store.execution_state().failed_event_ids == ()
            if cycle == 1:
                with pytest.raises(ValueError, match="already bound|attempt"):
                    store.record_terminal_failure(
                        event_id=failed.event_id,
                        reason="illegal second halt for same attempt",
                        policy_evidence={"policy_id": "halt-again", "policy_hash": SHA_A},
                        recorded_at="2026-08-30T11:30:00+00:00",
                    )
            previous_hash = authorization.payload_hash

        assert tuple(item.payload_hash for item in store.causal_evidence_prefix()) == tuple(
            item.payload_hash
            for pair in zip(
                store.terminal_failure_evidence_prefix(),
                store.resume_authorization_evidence_prefix(),
            )
            for item in pair
        )


@pytest.mark.parametrize(
    ("failure_run_id", "authorization_run_id", "foreign_ordinal"),
    [
        ("run-foreign", None, None),
        (None, "run-foreign", None),
        ("run-foreign", "run-foreign", None),
        (None, None, 1),
    ],
    ids=(
        "failure-foreign-run",
        "authorization-foreign-run",
        "pair-foreign-run-rehashed",
        "pair-foreign-ordinal-rehashed",
    ),
)
def test_foreign_causal_identity_never_authorizes_current_retry(
    tmp_path: Path,
    failure_run_id: str | None,
    authorization_run_id: str | None,
    foreign_ordinal: int | None,
) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "foreign-causal-identity.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        failed = attempt(run_manifest)
        append_terminal_attempt(store, failed)
        authorize_retry(store, failed, "foreign-causal-identity")
        rewrite_causal_identity(
            store,
            failure_run_id=failure_run_id,
            authorization_run_id=authorization_run_id,
            event_ordinal=foreign_ordinal,
        )

        journal = store.current_event_journal()
        assert journal.resume_state != "retry_same_event"
        pending_retry = attempt_transition(attempt(run_manifest, index=2), EventStatus.PENDING)
        with pytest.raises(ValueError, match="identity|run|ordinal|failure|authorization|causal"):
            store.append_attempt(pending_retry)
        assert (
            store._connection.execute(
                "SELECT COUNT(*) FROM attempt_transitions WHERE attempt_index = 2"
            ).fetchone()[0]
            == 0
        )
        with pytest.raises(ValueError, match="identity|run|event|failure|authorization|causal"):
            store.verify_integrity()


@pytest.mark.parametrize(
    "tamper",
    [
        "delete-failure",
        "delete-authorization",
        "skip-sequence",
        "wrong-event",
        "fork-chain",
        "wrong-attempt",
        "reinsert-with-wrong-sequence",
    ],
)
def test_reopen_fails_closed_on_causal_chain_tamper(tmp_path: Path, tamper: str) -> None:
    run_manifest = manifest()
    database = tmp_path / f"causal-tamper-{tamper}.sqlite3"
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        failed = attempt(run_manifest)
        append_terminal_attempt(store, failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="halt",
            policy_evidence={"policy_id": "halt-policy", "policy_hash": SHA_A},
            recorded_at=NOW,
        )
        store.authorize_resume(
            authorization_id="resume-tamper-chain",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash=SHA_B,
            authorized_at="2026-08-30T01:00:00+00:00",
        )

    with sqlite3.connect(database) as connection:
        if tamper == "delete-failure":
            connection.execute("DELETE FROM terminal_failures")
        elif tamper == "delete-authorization":
            connection.execute("DELETE FROM resume_authorizations")
        elif tamper == "skip-sequence":
            connection.execute("UPDATE resume_authorizations SET evidence_sequence = 9")
        elif tamper == "wrong-event":
            connection.execute("UPDATE terminal_failures SET event_id = 'event-forged'")
        elif tamper == "fork-chain":
            connection.execute(
                "UPDATE resume_authorizations SET previous_evidence_hash = ?", (SHA_B,)
            )
        elif tamper == "wrong-attempt":
            connection.execute("UPDATE terminal_failures SET attempt_index = 99")
        else:
            row = connection.execute("SELECT * FROM resume_authorizations").fetchone()
            assert row is not None
            connection.execute("DELETE FROM resume_authorizations")
            values = list(row)
            values[1] = 7
            connection.execute(
                "INSERT INTO resume_authorizations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

    with pytest.raises(ValueError, match="causal|evidence|execution|failure|authorization"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_every_mutator_requires_this_storage_instance_to_hold_run_lease(tmp_path: Path) -> None:
    run_manifest = manifest()
    database = tmp_path / "mutator-lease.sqlite3"
    with (
        RunStorage.create(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        ) as owner,
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        ) as intruder,
    ):
        with pytest.raises(RuntimeError, match="lease"):
            intruder.initialize_agent(*initial_records("agent-0"))
        with owner.acquire_run_lease():
            owner.initialize_agent(*initial_records("agent-0"))
            with pytest.raises(RuntimeError, match="lease"):
                intruder.initialize_agent(*initial_records("agent-1"))


def test_run_lease_rejects_second_owner_and_releases_on_context_exit(tmp_path: Path) -> None:
    run_manifest = manifest()
    database = tmp_path / "leased.sqlite3"
    with (
        RunStorage.create(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        ) as first,
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        ) as second,
    ):
        with first.acquire_run_lease():
            first.assert_run_lease_owned()
            with pytest.raises(RuntimeError, match="lease"):
                with second.acquire_run_lease():
                    pass
        with second.acquire_run_lease():
            second.assert_run_lease_owned()


def test_posix_lease_branch_opens_and_keys_the_real_database_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Portable structural probe only; Windows CI does not claim a real fcntl run."""

    database = tmp_path / "posix-branch.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with monkeypatch.context() as patcher:
            patcher.setattr(storage_module.os, "name", "posix")
            lease = store.acquire_run_lease()
            handle, key = lease._open_stable_handle()
            try:
                value = os.fstat(handle.fileno())
                assert lease._path == database.resolve()
                assert key == ("db-inode", value.st_dev, value.st_ino)
                assert (value.st_dev, value.st_ino) == store._database_identity
                assert value.st_nlink == 1
            finally:
                handle.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows handle deletion semantics")
def test_windows_lease_handle_prevents_sidecar_replacement_while_owned(tmp_path: Path) -> None:
    database = tmp_path / "windows-stable-lease.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        lease = store.acquire_run_lease()
        with lease:
            with pytest.raises(PermissionError):
                lease._path.unlink()
            assert lease._path.exists()


def test_run_lease_is_exclusive_across_processes(tmp_path: Path) -> None:
    run_manifest = manifest()
    database = tmp_path / "cross-process.sqlite3"
    script = (
        "import os,sys\n"
        "p=sys.argv[1]\n"
        "f=open(p,'r+b')\n"
        "try:\n"
        "  if os.name=='nt':\n"
        "    import msvcrt; msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)\n"
        "  else:\n"
        "    import fcntl; fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
        "except (OSError,BlockingIOError): sys.exit(73)\n"
        "sys.exit(0)\n"
    )
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        lease_path = (
            database.with_suffix(database.suffix + ".lease") if os.name == "nt" else database
        )
        with store.acquire_run_lease():
            blocked = subprocess.run([sys.executable, "-c", script, str(lease_path)], check=False)
            assert blocked.returncode == 73
        released = subprocess.run([sys.executable, "-c", script, str(lease_path)], check=False)
        assert released.returncode == 0


def test_second_process_direct_mutator_is_rejected_and_crash_releases_lease(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    database = tmp_path / "process-mutator.sqlite3"
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        tests_path = str(Path(__file__).resolve().parent)
        direct_mutator = (
            "import sys\n"
            f"sys.path.insert(0, {tests_path!r})\n"
            "from test_storage import manifest,expected_agent_ids,initial_records,SHA_B\n"
            "from agent_ex.storage import RunStorage\n"
            "m=manifest(); s=RunStorage.open(sys.argv[1],manifest=m,artifact_hashes={'population':SHA_B},expected_agent_ids=expected_agent_ids(m),expected_exposure_mode='self_history_only',expected_exposure_graph_hash=None)\n"
            "try: s.initialize_agent(*initial_records('agent-0'))\n"
            "except RuntimeError: sys.exit(73)\n"
            "sys.exit(0)\n"
        )
        blocked = subprocess.run([sys.executable, "-c", direct_mutator, str(database)], check=False)
        assert blocked.returncode == 73

        crash_owner = (
            "import os,sys\n"
            f"sys.path.insert(0, {tests_path!r})\n"
            "from test_storage import manifest,expected_agent_ids,SHA_B\n"
            "from agent_ex.storage import RunStorage\n"
            "m=manifest(); s=RunStorage.open(sys.argv[1],manifest=m,artifact_hashes={'population':SHA_B},expected_agent_ids=expected_agent_ids(m),expected_exposure_mode='self_history_only',expected_exposure_graph_hash=None)\n"
            "s.acquire_run_lease().acquire(); os._exit(91)\n"
        )
        crashed = subprocess.run([sys.executable, "-c", crash_owner, str(database)], check=False)
        assert crashed.returncode == 91
        with store.acquire_run_lease():
            store.initialize_agent(*initial_records("agent-0"))


def test_hardlink_alias_blocks_every_preopened_writer_and_cross_process_owner(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    database = tmp_path / "original" / "run.sqlite3"
    database.parent.mkdir()
    alias = tmp_path / "alias" / "same-run.sqlite3"
    alias.parent.mkdir()
    first = RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    second = RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    try:
        os.link(database, alias)
        for store in (first, second):
            with pytest.raises(RuntimeError, match="hard.?link|link count"):
                store.acquire_run_lease().acquire()

        tests_path = str(Path(__file__).resolve().parent)
        script = (
            "import sys\n"
            f"sys.path.insert(0, {tests_path!r})\n"
            "from test_storage import manifest,expected_agent_ids,SHA_B\n"
            "from agent_ex.storage import RunStorage\n"
            "m=manifest()\n"
            "try:\n"
            " s=RunStorage.open(sys.argv[1],manifest=m,artifact_hashes={'population':SHA_B},expected_agent_ids=expected_agent_ids(m),expected_exposure_mode='self_history_only',expected_exposure_graph_hash=None)\n"
            " s.acquire_run_lease().acquire()\n"
            "except RuntimeError: sys.exit(73)\n"
            "sys.exit(0)\n"
        )
        blocked = subprocess.run([sys.executable, "-c", script, str(alias)], check=False)
        assert blocked.returncode == 73
    finally:
        second.close()
        first.close()


def test_hardlink_created_after_lease_blocks_mutation_until_alias_is_removed(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    database = tmp_path / "run.sqlite3"
    alias = tmp_path / "other" / "run-alias.sqlite3"
    alias.parent.mkdir()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with store.acquire_run_lease():
            os.link(database, alias)
            with pytest.raises(RuntimeError, match="hard.?link|link count"):
                store.initialize_agent(*initial_records("agent-0"))
            assert store.private_state("agent-0") is None
            alias.unlink()
            store.initialize_agent(*initial_records("agent-0"))
            assert store.private_state("agent-0") is not None


def test_reopen_fails_closed_on_tampered_event_payload(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        final_attempt = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, final_attempt)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=final_attempt,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE events SET payload_json = '{}' WHERE event_ordinal = 0")

    with pytest.raises(ValueError, match="event payload hash"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_large_raw_response_can_store_only_explicit_uri_and_hash(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    assert succeeded.raw_response is not None and succeeded.raw_response_hash is not None
    reference = ExternalResponseReference(
        uri="file:///archive/raw/event-0-attempt-1.json",
        sha256=succeeded.raw_response_hash,
    )
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded, external_response=reference)
        assert store.external_response_reference(succeeded.attempt_id) == reference
        with pytest.raises(ValueError, match="external raw response"):
            store.attempts_for_event(succeeded.event_id)
        assert store.attempts_for_event(
            succeeded.event_id,
            external_raw_responses={succeeded.attempt_id: succeeded.raw_response},
        ) == (succeeded,)

    with sqlite3.connect(database) as connection:
        stored_payload = connection.execute(
            "SELECT payload_json FROM attempts WHERE attempt_id = ?", (succeeded.attempt_id,)
        ).fetchone()[0]
    assert succeeded.raw_response not in stored_payload
    assert json.loads(stored_payload)["raw_response"] is None


def test_failed_then_success_attempt_chain_requires_matching_final_evidence(
    tmp_path: Path,
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        failed = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        succeeded = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, failed)
        authorize_retry(store, failed, "matching-final-evidence")
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
            attempt_index=2,
        )

        with pytest.raises(ValueError, match="final-success"):
            store.commit_success(
                successful_event(run_manifest, ordinal=0, attempt_count=1),
                final_attempt=succeeded,
                private_update=records[0],
                private_state=records[1],
                feed_cursor=records[2],
                public_post=records[3],
                latest_public_pointer=records[4],
            )
        assert store.progress.next_event_ordinal == 0

        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=2),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        store.assert_complete()


def test_closed_connection_reopens_and_recovers_typed_committed_state(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        event = successful_event(run_manifest, ordinal=0)
        store.commit_success(
            event,
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )

    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as recovered:
        assert recovered.event_at(0) == event
        assert recovered.attempts_for_event(event.event_id) == (succeeded,)
        assert recovered.private_state("agent-0") == records[1]
        assert recovered.feed_cursor("agent-0") == records[2]
        recovered.assert_complete()


@pytest.mark.parametrize(
    "statement",
    (
        "UPDATE binding SET schedule_payload_json = '{}' WHERE singleton = 1",
        f"UPDATE progress SET event_chain_head = '{'0' * 64}' WHERE singleton = 1",
    ),
)
def test_reopen_rejects_schedule_or_event_chain_tamper(tmp_path: Path, statement: str) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
    with sqlite3.connect(database) as connection:
        connection.execute(statement)

    with pytest.raises(ValueError):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_create_independently_replays_manifest_and_schedule_before_writing(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    forged_slots = list(run_manifest.schedule.slots)
    original = forged_slots[0]
    forged_slots[0] = ScheduleSlot(
        event_ordinal=original.event_ordinal,
        sweep_index=original.sweep_index,
        draw_index=original.draw_index,
        agent_id="forged-agent",
        publish_flag=original.publish_flag,
    )
    object.__setattr__(run_manifest.schedule, "slots", tuple(forged_slots))
    database = tmp_path / "forged.sqlite3"

    with pytest.raises(ValueError, match="schedule"):
        RunStorage.create(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    assert not database.exists()


def test_open_rejects_drifted_storage_schema_version(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE binding SET schema_version = 'paper1.run-storage.v999' WHERE singleton = 1"
        )

    with pytest.raises(ValueError, match="schema version"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_open_missing_path_fails_without_creating_database(tmp_path: Path) -> None:
    database = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        RunStorage.open(
            database,
            manifest=manifest(),
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(manifest()),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    assert not database.exists()


def test_external_response_commit_reopens_only_with_explicit_hash_checked_resolver(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    assert succeeded.raw_response is not None and succeeded.raw_response_hash is not None
    reference = ExternalResponseReference(
        uri="file:///archive/raw/event-0-attempt-1.json",
        sha256=succeeded.raw_response_hash,
    )
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded, external_response=reference)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )

    with pytest.raises(ValueError, match="resolver"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    with pytest.raises(ValueError, match="hash"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
            raw_response_resolver=lambda _: "forged body",
        )

    seen: list[ExternalResponseReference] = []

    def resolve(value: ExternalResponseReference) -> str:
        seen.append(value)
        return succeeded.raw_response  # type: ignore[return-value]

    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        raw_response_resolver=resolve,
    ) as reopened:
        assert reopened.attempts_for_event(succeeded.event_id) == (succeeded,)
        reopened.assert_complete()
    assert seen and set(seen) == {reference}


def test_attempt_transition_journal_is_monotonic_append_only_and_terminal(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    terminal = attempt(run_manifest, status=EventStatus.FAILED)
    pending = attempt_transition(terminal, EventStatus.PENDING)
    in_progress = attempt_transition(terminal, EventStatus.IN_PROGRESS)
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with pytest.raises(ValueError, match="PENDING"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(in_progress)
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(pending)
        with pytest.raises(ValueError, match="transition"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(terminal)
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(in_progress)
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(terminal)

        assert store.attempt_transitions(terminal.attempt_id) == (
            pending,
            in_progress,
            terminal,
        )
        assert store.attempts_for_event(terminal.event_id) == (terminal,)
        succeeded = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
        authorize_retry(store, terminal, "transition-journal")
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        assert store.attempts_for_event(terminal.event_id) == (terminal, succeeded)
        with pytest.raises(ValueError, match="terminal success"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(
                attempt_transition(
                    attempt(run_manifest, index=3, status=EventStatus.FAILED),
                    EventStatus.PENDING,
                )
            )


def test_reopen_rejects_orphan_terminal_attempt_not_covered_by_transition_journal(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    orphan = attempt(run_manifest, status=EventStatus.FAILED)
    payload = orphan.to_payload()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO attempts
               (attempt_id, event_id, attempt_index, status, payload_json, payload_hash,
                raw_response_uri, raw_response_hash)
               VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)""",
            (
                orphan.attempt_id,
                orphan.event_id,
                orphan.attempt_index,
                orphan.status.value,
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                canonical_payload_hash(payload),
            ),
        )

    with pytest.raises(ValueError, match="attempt|transition"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_reopen_rejects_gap_in_current_event_attempt_transition_prefix(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    failed = attempt(run_manifest, status=EventStatus.FAILED)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, failed)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM attempt_transitions WHERE attempt_id = ? AND transition_index = 2",
            (failed.attempt_id,),
        )

    with pytest.raises(ValueError, match="attempt|transition"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_initialize_agent_rejects_cursor_seed_drift_from_run(tmp_path: Path) -> None:
    run_manifest = manifest()
    initial = initial_records("agent-0")
    forged_cursor = FeedCursor.initial(
        matched_seed=18,
        receiver_agent_id="agent-0",
        exposure_mode="self_history_only",
        exposure_graph_hash=None,
        mock_only=True,
    )
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with pytest.raises(ValueError, match="seed"):
            store.initialize_agent(*initial[:4], forged_cursor)


def test_success_commit_rejects_attempt_exposure_drift_from_event(tmp_path: Path) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    event = successful_event(run_manifest, ordinal=0)
    drifted_event = GenerationEvent(
        **{
            **event.to_payload(),
            "status": EventStatus.SUCCEEDED,
            "attempt_ids": event.attempt_ids,
            "exposure_id": "different-exposure",
        }
    )
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        with pytest.raises(ValueError, match="exposure"):
            store.commit_success(
                drifted_event,
                final_attempt=succeeded,
                private_update=records[0],
                private_state=records[1],
                feed_cursor=records[2],
                public_post=records[3],
                latest_public_pointer=records[4],
            )


@pytest.mark.parametrize(
    "tamper",
    (
        "DELETE FROM public_posts WHERE event_ordinal IS NULL",
        "DELETE FROM latest_public_pointers",
        """INSERT INTO public_posts
           SELECT 'orphan-post', agent_id, event_ordinal, payload_json, payload_hash
           FROM public_posts WHERE event_ordinal = 0""",
        """INSERT INTO private_states
           SELECT 'orphan-agent', payload_json, payload_hash
           FROM private_states LIMIT 1""",
    ),
)
def test_reopen_requires_exact_cover_of_round0_public_latest_and_current_state(
    tmp_path: Path, tamper: str
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(True,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(tamper)
    except sqlite3.IntegrityError:
        return

    with pytest.raises(ValueError, match="exact|public|state|pointer"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_assert_complete_runs_full_integrity_replay_before_accepting_counts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM latest_public_pointers")
        with pytest.raises(ValueError, match="exact|pointer"):
            store.assert_complete()


def test_n50000_schedule_slot_is_cached_and_recovery_queries_use_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen_schedule = schedule(publish_flags=(False,) * 50_000)
    run_manifest = manifest(frozen_schedule)
    database = tmp_path / "n50000.sqlite3"
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        monkeypatch.setattr(
            storage_module.json,
            "loads",
            lambda _: (_ for _ in ()).throw(AssertionError("slot lookup parsed JSON")),
        )
        assert store.schedule_slot(49_999) == frozen_schedule.slots[49_999]

    with sqlite3.connect(database) as connection:
        private_plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM private_updates WHERE event_ordinal = ?",
            (49_999,),
        ).fetchall()
        public_plan = connection.execute(
            """EXPLAIN QUERY PLAN SELECT * FROM public_posts
               WHERE agent_id = ? AND event_ordinal = ?""",
            ("agent-49999", 49_999),
        ).fetchall()
    assert any("INDEX" in row[3].upper() for row in private_plan)
    assert any("INDEX" in row[3].upper() for row in public_plan)


def test_landed_success_attempt_reopens_and_commits_without_reissuing_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)

    records = successful_state_records(
        run_manifest,
        ordinal=0,
        previous_state=initial[1],
        previous_cursor=initial[4],
        previous_pointer=initial[3],
    )
    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as recovered:
        assert recovered.attempts_for_event(succeeded.event_id) == (succeeded,)
        with recovered.acquire_run_lease():
            recovered.commit_success(
                successful_event(run_manifest, ordinal=0),
                final_attempt=succeeded,
                private_update=records[0],
                private_state=records[1],
                feed_cursor=records[2],
                public_post=records[3],
                latest_public_pointer=records[4],
            )
        recovered.assert_complete()


def test_reopen_rejects_exposure_drift_even_when_row_and_chain_hashes_are_recomputed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    records = successful_state_records(
        run_manifest,
        ordinal=0,
        previous_state=initial[1],
        previous_cursor=initial[4],
        previous_pointer=initial[3],
    )
    event = successful_event(run_manifest, ordinal=0)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        store.commit_success(
            event,
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        binding = store.binding
    drifted_event = event.to_payload()
    drifted_event["exposure_id"] = "forged-exposure"
    genesis = storage_genesis(binding)
    drifted_chain = canonical_payload_hash(
        {
            "previous": genesis,
            "event": drifted_event,
            "attempts": [inline_attempt_chain_entry(succeeded)],
            "private_update_hash": records[0].record_hash,
            "private_state_hash": records[1].record_hash,
            "public_post_hash": None,
            "cursor_hash": records[2].record_hash,
        }
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE events SET payload_json = ?, payload_hash = ? WHERE event_ordinal = 0",
            (
                json.dumps(
                    drifted_event,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                canonical_payload_hash(drifted_event),
            ),
        )
        connection.execute(
            "UPDATE progress SET event_chain_head = ? WHERE singleton = 1",
            (drifted_chain,),
        )

    with pytest.raises(ValueError, match="exposure"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_live_create_resolver_replays_external_failed_prefix_before_success_commit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    failed_payload = attempt(run_manifest, index=1, status=EventStatus.FAILED).to_payload()
    failed_raw = "provider returned a retryable invalid body"
    failed_payload["raw_response"] = failed_raw
    failed_payload["raw_response_hash"] = canonical_payload_hash(failed_raw)
    failed = GenerationAttempt.from_payload(failed_payload)
    succeeded = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
    assert succeeded.raw_response is not None and succeeded.raw_response_hash is not None
    failed_ref = ExternalResponseReference(
        uri="file:///archive/raw/failed-1.json", sha256=canonical_payload_hash(failed_raw)
    )
    success_ref = ExternalResponseReference(
        uri="file:///archive/raw/success-2.json", sha256=succeeded.raw_response_hash
    )
    bodies = {failed_ref.uri: failed_raw, success_ref.uri: succeeded.raw_response}

    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        raw_response_resolver=lambda reference: bodies[reference.uri],
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, failed, external_response=failed_ref)
        authorize_retry(store, failed, "external-failed-prefix")
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded, external_response=success_ref)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
            attempt_index=2,
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=2),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        store.assert_complete()

    with sqlite3.connect(database) as connection:
        stored = "".join(
            row[0]
            for row in connection.execute(
                "SELECT payload_json FROM attempt_transitions ORDER BY attempt_index"
            ).fetchall()
        )
    assert failed_raw not in stored
    assert succeeded.raw_response not in stored


def test_append_rejects_next_attempt_until_prior_terminal_and_after_complete(
    tmp_path: Path,
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    failed = attempt(run_manifest, index=1, status=EventStatus.FAILED)
    second = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
    pending_first = attempt_transition(failed, EventStatus.PENDING)
    pending_second = attempt_transition(second, EventStatus.PENDING)
    initial = initial_records("agent-0")
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(pending_first)
        with pytest.raises(ValueError, match="unfinished|terminal FAILED"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(pending_second)
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(attempt_transition(failed, EventStatus.IN_PROGRESS))
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(failed)
        with pytest.raises(ValueError, match="authorization|failure evidence"):
            store.append_attempt(pending_second)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="explicit retry gate",
            policy_evidence={"policy_id": "halt", "policy_hash": SHA_A},
            recorded_at=NOW,
        )
        store.authorize_resume(
            authorization_id="resume-explicit-retry",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash=SHA_B,
            authorized_at=NOW,
        )
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, second)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
            attempt_index=2,
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=2),
            final_attempt=second,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        with pytest.raises(ValueError, match="complete|schedule"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(
                attempt_transition(
                    attempt(run_manifest, ordinal=1, status=EventStatus.FAILED),
                    EventStatus.PENDING,
                )
            )
        with pytest.raises(TypeError):
            store.schedule_slot(True)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            store.schedule_slot(-1)
        with pytest.raises(ValueError):
            store.schedule_slot(1)


def test_verify_integrity_requires_exact_failure_authorization_pair_for_every_retry(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    failed = attempt(run_manifest, index=1, status=EventStatus.FAILED)
    second = attempt_transition(
        attempt(run_manifest, index=2, status=EventStatus.FAILED), EventStatus.PENDING
    )
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="retry gate",
            policy_evidence={"policy_id": "halt", "policy_hash": SHA_A},
            recorded_at=NOW,
        )
        store.authorize_resume(
            authorization_id="resume-exact-cover",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash=SHA_B,
            authorized_at=NOW,
        )
        store.append_attempt(second)
        store._connection.execute("DELETE FROM resume_authorizations")
        with pytest.raises(ValueError, match="authoriz|exact-cover|causal"):
            store.verify_integrity()


def test_mutator_rolls_back_if_hardlink_appears_after_transaction_entry(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    alias = tmp_path / "late-alias.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    pending = attempt_transition(attempt(run_manifest), EventStatus.PENDING)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        fired = False

        def create_alias(statement: str) -> None:
            nonlocal fired
            if not fired and statement.lstrip().startswith("INSERT INTO attempt_transitions"):
                fired = True
                os.link(database, alias)

        store._connection.set_trace_callback(create_alias)
        try:
            with pytest.raises(RuntimeError, match="hard-link|identity"):
                store.append_attempt(pending)
        finally:
            store._connection.set_trace_callback(None)
            if alias.exists():
                alias.unlink()
        assert fired is True
        assert (
            store._connection.execute("SELECT COUNT(*) FROM attempt_transitions").fetchone()[0] == 0
        )
        assert store.execution_state().event_ids == ()


def test_open_closes_connection_when_pragma_initialization_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    real_connection = sqlite3.connect(database)

    class FailingConnection:
        closed = False

        def execute(self, *_: object) -> object:
            raise sqlite3.OperationalError("injected pragma failure")

        def close(self) -> None:
            self.closed = True
            real_connection.close()

    failing = FailingConnection()
    monkeypatch.setattr(storage_module.sqlite3, "connect", lambda *args, **kwargs: failing)
    with pytest.raises(sqlite3.OperationalError, match="pragma"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    assert failing.closed is True


def test_create_rejects_dangling_symlink_without_creating_its_target(tmp_path: Path) -> None:
    database = tmp_path / "dangling.sqlite3"
    missing_target = tmp_path / "must-remain-missing.sqlite3"
    try:
        database.symlink_to(missing_target)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")
    run_manifest = manifest()
    with pytest.raises((FileExistsError, RuntimeError), match="exist|link|target"):
        RunStorage.create(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    assert database.is_symlink()
    assert not missing_target.exists()


def test_create_no_replace_install_loses_race_without_overwriting_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "raced.sqlite3"
    sentinel = b"competitor-won"
    run_manifest = manifest()
    real_link = os.link
    hook_called = False

    def competing_link(source: object, target: object, **kwargs: object) -> None:
        nonlocal hook_called
        hook_called = True
        Path(target).write_bytes(sentinel)
        real_link(source, target, **kwargs)

    monkeypatch.setattr(storage_module.os, "link", competing_link)
    with pytest.raises(FileExistsError):
        RunStorage.create(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    assert hook_called is True
    assert database.read_bytes() == sentinel
    assert not tuple(tmp_path.glob(f".{database.name}.*.tmp"))


def test_create_binds_installed_inode_through_unified_hardened_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "installed.sqlite3"
    replacement = tmp_path / "installed-copy.sqlite3"
    displaced = tmp_path / "installed-original.sqlite3"
    run_manifest = manifest()
    real_open = RunStorage.open.__func__

    def racing_open(cls: type[RunStorage], path: object, **kwargs: object) -> RunStorage:
        shutil.copy2(database, replacement)
        database.replace(displaced)
        replacement.replace(database)
        return real_open(cls, path, **kwargs)

    monkeypatch.setattr(RunStorage, "open", classmethod(racing_open))
    with pytest.raises(RuntimeError, match="identity|installed"):
        RunStorage.create(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    assert database.exists()
    assert displaced.exists()


def test_open_detects_path_swap_between_identity_capture_and_sqlite_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "stable-open.sqlite3"
    replacement = tmp_path / "replacement.sqlite3"
    displaced = tmp_path / "displaced.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    shutil.copy2(database, replacement)
    real_connect = sqlite3.connect
    hook_called = False

    def racing_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal hook_called
        hook_called = True
        try:
            database.replace(displaced)
            replacement.replace(database)
        except PermissionError as error:
            raise RuntimeError("stable identity handle blocked path replacement") from error
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(storage_module.sqlite3, "connect", racing_connect)
    with pytest.raises(RuntimeError, match="identity|replacement|stable"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )
    assert hook_called is True
    assert database.exists()
    assert displaced.exists() or os.name == "nt"


@pytest.mark.skipif(os.name == "nt", reason="real POSIX no-follow identity smoke")
def test_posix_open_identity_smoke_holds_original_inode_until_close(tmp_path: Path) -> None:
    database = tmp_path / "posix-open-identity.sqlite3"
    run_manifest = manifest()
    store = RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    try:
        assert store._database_identity_handle is not None
        handle_stat = os.fstat(store._database_identity_handle.fileno())
        assert (handle_stat.st_dev, handle_stat.st_ino) == store._database_identity
        assert handle_stat.st_nlink == 1
    finally:
        store.close()


def test_repeated_failed_open_releases_database_for_replace_and_unlink(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    moved = tmp_path / "moved.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE binding SET schema_version = 'forged-schema'")
        connection.commit()

    for _ in range(3):
        with pytest.raises(ValueError, match="schema"):
            RunStorage.open(
                database,
                manifest=run_manifest,
                artifact_hashes={"population": SHA_B},
                expected_agent_ids=expected_agent_ids(run_manifest),
                expected_exposure_mode="self_history_only",
                expected_exposure_graph_hash=None,
            )
        database.replace(moved)
        moved.replace(database)

    database.unlink()
    assert not database.exists()


def test_reopen_derives_cursor_seed_from_manifest_not_stored_cursor(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    initial = initial_records("agent-0")
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
    forged = FeedCursor.initial(
        matched_seed=18,
        receiver_agent_id="agent-0",
        exposure_mode="self_history_only",
        exposure_graph_hash=None,
        mock_only=True,
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE feed_cursors SET payload_json = ?, payload_hash = ? WHERE agent_id = ?",
            (
                json.dumps(
                    forged.to_payload(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                canonical_payload_hash(forged.to_payload()),
                "agent-0",
            ),
        )
    with pytest.raises(ValueError, match="seed|cursor"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_initialize_agent_rejects_round0_seed_not_bound_to_manifest(tmp_path: Path) -> None:
    run_manifest = manifest()
    update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=18,
        agent_id="agent-0",
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label="neutral",
        reason="round zero",
        confidence=None,
        published=True,
        source_attempt_id=None,
        mock_only=True,
    )
    state = PrivateState.from_update(update, previous=None, mock_only=True)
    post = PublicPost.from_private_update(update, mock_only=True)
    pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
    cursor = FeedCursor.initial(
        matched_seed=18,
        receiver_agent_id="agent-0",
        exposure_mode="self_history_only",
        exposure_graph_hash=None,
        mock_only=True,
    )
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with pytest.raises(ValueError, match="seed|manifest"):
            store.initialize_agent(update, state, post, pointer, cursor)


def test_reopen_exact_binds_initial_private_update_agent_column(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE private_updates SET agent_id = 'forged-agent' WHERE event_ordinal IS NULL"
        )
    with pytest.raises(ValueError, match="private update|agent|exact"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


@pytest.mark.parametrize(
    "tamper",
    (
        "UPDATE attempts SET status = 'failed'",
        "UPDATE events SET event_id = 'forged-event'",
        "UPDATE attempt_transitions SET attempt_id = 'forged-attempt'",
    ),
)
def test_reopen_exact_binds_redundant_row_identity_and_status_columns(
    tmp_path: Path, tamper: str
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
    with sqlite3.connect(database) as connection:
        connection.execute(tamper)
    with pytest.raises(ValueError, match="identity|status|exact|attempt|event"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_reopen_exact_binds_event_run_id_column(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE events SET run_id = 'foreign-run'")
    with pytest.raises(ValueError, match="run|identity"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_attempt_terminal_started_at_must_equal_in_progress_started_at(tmp_path: Path) -> None:
    run_manifest = manifest()
    terminal = attempt(run_manifest, status=EventStatus.FAILED)
    pending = attempt_transition(terminal, EventStatus.PENDING)
    in_progress = attempt_transition(terminal, EventStatus.IN_PROGRESS)
    drifted_payload = terminal.to_payload()
    drifted_payload["started_at"] = "2026-08-18T00:00:01+00:00"
    drifted_payload["finished_at"] = "2026-08-18T00:00:02+00:00"
    drifted_terminal = GenerationAttempt.from_payload(drifted_payload)
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(pending)
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(in_progress)
        with pytest.raises(ValueError, match="started_at"):
            seal_expected_initial_state(store, run_manifest)
            store.append_attempt(drifted_terminal)


def test_reopen_replays_every_frozen_schedule_slot_field_after_hash_recompute(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    records = successful_state_records(
        run_manifest,
        ordinal=0,
        previous_state=initial[1],
        previous_cursor=initial[4],
        previous_pointer=initial[3],
    )
    event = successful_event(run_manifest, ordinal=0)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        store.commit_success(
            event,
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        binding = store.binding
    drifted_event = event.to_payload()
    drifted_event["sweep_index"] = 2
    genesis = storage_genesis(binding)
    drifted_chain = canonical_payload_hash(
        {
            "previous": genesis,
            "event": drifted_event,
            "attempts": [inline_attempt_chain_entry(succeeded)],
            "private_update_hash": records[0].record_hash,
            "private_state_hash": records[1].record_hash,
            "public_post_hash": None,
            "cursor_hash": records[2].record_hash,
        }
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE events SET payload_json = ?, payload_hash = ? WHERE event_ordinal = 0",
            (
                json.dumps(
                    drifted_event,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                canonical_payload_hash(drifted_event),
            ),
        )
        connection.execute(
            "UPDATE progress SET event_chain_head = ? WHERE singleton = 1",
            (drifted_chain,),
        )
    with pytest.raises(ValueError, match="schedule|slot|sweep"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_reopen_revalidates_final_attempt_content_against_private_update(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    records = successful_state_records(
        run_manifest,
        ordinal=0,
        previous_state=initial[1],
        previous_cursor=initial[4],
        previous_pointer=initial[3],
    )
    event = successful_event(run_manifest, ordinal=0)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded)
        store.commit_success(
            event,
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        binding = store.binding
    forged_update_payload = records[0].to_payload()
    forged_update_payload["reason"] = "forged reason unrelated to final attempt"
    forged_update_payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in forged_update_payload.items() if key != "record_hash"}
    )
    forged_update = PrivateUpdate.from_payload(forged_update_payload)
    forged_state_payload = records[1].to_payload()
    forged_state_payload["latest_update_hash"] = forged_update.record_hash
    forged_state_payload["reason"] = forged_update.reason
    forged_state_payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in forged_state_payload.items() if key != "record_hash"}
    )
    forged_state = PrivateState.from_payload(forged_state_payload)
    genesis = storage_genesis(binding)
    forged_chain = canonical_payload_hash(
        {
            "previous": genesis,
            "event": event.to_payload(),
            "attempts": [inline_attempt_chain_entry(succeeded)],
            "private_update_hash": forged_update.record_hash,
            "private_state_hash": forged_state.record_hash,
            "public_post_hash": None,
            "cursor_hash": records[2].record_hash,
        }
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE private_updates SET payload_json = ?, payload_hash = ? WHERE event_ordinal = 0",
            (
                json.dumps(
                    forged_update.to_payload(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                canonical_payload_hash(forged_update.to_payload()),
            ),
        )
        connection.execute(
            "UPDATE private_states SET payload_json = ?, payload_hash = ? WHERE agent_id = 'agent-0'",
            (
                json.dumps(
                    forged_state.to_payload(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                canonical_payload_hash(forged_state.to_payload()),
            ),
        )
        connection.execute(
            "UPDATE progress SET event_chain_head = ? WHERE singleton = 1",
            (forged_chain,),
        )
    with pytest.raises(ValueError, match="attempt|private update|content"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_reopen_rejects_terminal_external_uri_drift_between_journal_and_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    assert succeeded.raw_response is not None and succeeded.raw_response_hash is not None
    original = ExternalResponseReference(
        uri="file:///archive/raw/original.json", sha256=succeeded.raw_response_hash
    )
    drifted_uri = "file:///archive/raw/drifted-location.json"
    bodies = {original.uri: succeeded.raw_response, drifted_uri: succeeded.raw_response}
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        raw_response_resolver=lambda reference: bodies[reference.uri],
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded, external_response=original)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE attempts SET raw_response_uri = ? WHERE attempt_id = ?",
            (drifted_uri, succeeded.attempt_id),
        )
    with pytest.raises(ValueError, match="URI|external|attempt|chain"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
            raw_response_resolver=lambda reference: bodies[reference.uri],
        )


def test_reopen_rejects_coordinated_external_uri_drift_without_chain_reseal(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    assert succeeded.raw_response is not None and succeeded.raw_response_hash is not None
    original = ExternalResponseReference(
        uri="file:///archive/raw/original.json", sha256=succeeded.raw_response_hash
    )
    drifted_uri = "file:///archive/raw/coordinated-drift.json"
    bodies = {original.uri: succeeded.raw_response, drifted_uri: succeeded.raw_response}
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        raw_response_resolver=lambda reference: bodies[reference.uri],
    ) as store:
        store.initialize_agent(*initial)
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, succeeded, external_response=original)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=initial[1],
            previous_cursor=initial[4],
            previous_pointer=initial[3],
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE attempts SET raw_response_uri = ? WHERE attempt_id = ?",
            (drifted_uri, succeeded.attempt_id),
        )
        connection.execute(
            """UPDATE attempt_transitions SET raw_response_uri = ?
               WHERE attempt_id = ? AND status = ?""",
            (drifted_uri, succeeded.attempt_id, EventStatus.SUCCEEDED.value),
        )
    with pytest.raises(ValueError, match="chain|URI|external"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
            raw_response_resolver=lambda reference: bodies[reference.uri],
        )


def test_reopen_rejects_self_consistent_round0_bundle_with_foreign_seed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    original = initial_records("agent-0")
    forged_update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=run_manifest.matched_seed + 1,
        agent_id="agent-0",
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label="neutral",
        reason="round zero",
        confidence=None,
        published=True,
        source_attempt_id=None,
        mock_only=True,
    )
    forged_state = PrivateState.from_update(forged_update, previous=None, mock_only=True)
    forged_post = PublicPost.from_private_update(forged_update, mock_only=True)
    forged_pointer = LatestPublicPointer.from_post(forged_post, previous=None, mock_only=True)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*original)
    with sqlite3.connect(database) as connection:
        for table, id_column, identity, value in (
            ("private_updates", "update_id", forged_update.update_id, forged_update),
            ("public_posts", "post_id", forged_post.post_id, forged_post),
        ):
            payload = value.to_payload()
            connection.execute(
                f"UPDATE {table} SET {id_column} = ?, payload_json = ?, payload_hash = ?",
                (
                    identity,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    canonical_payload_hash(payload),
                ),
            )
        for table, value in (
            ("private_states", forged_state),
            ("latest_public_pointers", forged_pointer),
        ):
            payload = value.to_payload()
            connection.execute(
                f"UPDATE {table} SET payload_json = ?, payload_hash = ? WHERE agent_id = 'agent-0'",
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    canonical_payload_hash(payload),
                ),
            )
    with pytest.raises(ValueError, match="round-0|seed|manifest|provenance"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_reopen_rejects_transition_row_event_id_different_from_typed_payload(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest()
    current = attempt_transition(attempt(run_manifest), EventStatus.PENDING)
    future_event_id = derive_event_id(run_manifest.run_id, 1)
    forged_payload = current.to_payload()
    forged_payload["event_id"] = future_event_id
    forged_payload["attempt_id"] = derive_attempt_id(future_event_id, 1)
    forged = GenerationAttempt.from_payload(forged_payload)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        store.append_attempt(current)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE attempt_transitions
               SET attempt_id = ?, payload_json = ?, payload_hash = ?
               WHERE attempt_id = ?""",
            (
                forged.attempt_id,
                json.dumps(
                    forged.to_payload(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                canonical_payload_hash(forged.to_payload()),
                current.attempt_id,
            ),
        )
    with pytest.raises(ValueError, match="event|identity|transition"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_population_roster_is_explicit_when_schedule_draws_one_agent_twice(
    tmp_path: Path,
) -> None:
    frozen_schedule = FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id="mock.with-replacement",
        algorithm_version="1.0.0",
        population_size=2,
        sweep_count=1,
        slots=(
            ScheduleSlot(0, 1, 0, "agent-0", False),
            ScheduleSlot(1, 1, 1, "agent-0", False),
        ),
    )
    run_manifest = manifest(frozen_schedule)
    roster = ("agent-1", "agent-0")
    database = tmp_path / "run.sqlite3"
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=roster,
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
        store.initialize_agent(*initial_records("agent-1"))
        store.seal_initial_state()
    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0", "agent-1"),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as reopened:
        assert reopened.binding.expected_agent_ids == ("agent-0", "agent-1")
    with pytest.raises(ValueError, match="expected agent|roster|binding"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0", "agent-2"),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_initial_state_seal_requires_exact_roster_and_forbids_extra_agent(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0", "agent-1"),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
        with pytest.raises(ValueError, match="roster|exact|missing"):
            store.seal_initial_state()
        store.initialize_agent(*initial_records("agent-1"))
        with pytest.raises(ValueError, match="roster|expected|agent"):
            store.initialize_agent(*initial_records("agent-2"))
        store.seal_initial_state()
        with pytest.raises(ValueError, match="sealed|initial"):
            store.initialize_agent(*initial_records("agent-0"))


def test_population_roster_rejects_duplicate_agent_ids(tmp_path: Path) -> None:
    run_manifest = manifest()
    with pytest.raises(ValueError, match="duplicate"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0", "agent-1", "agent-1"),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_population_roster_cardinality_must_match_frozen_population(tmp_path: Path) -> None:
    run_manifest = manifest()
    with pytest.raises(ValueError, match="population|roster|cardinality"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0", "agent-1", "agent-2"),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_attempt_append_requires_explicit_initial_state_seal(tmp_path: Path) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
        pending = attempt_transition(attempt(run_manifest), EventStatus.PENDING)
        with pytest.raises(ValueError, match="seal|initial state"):
            store.append_attempt(pending)
        store.seal_initial_state()
        store.append_attempt(pending)


def test_round0_root_rejects_self_consistent_content_replacement(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    original = initial_records("agent-0")
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*original)
        store.seal_initial_state()
    forged_update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=run_manifest.matched_seed,
        agent_id="agent-0",
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label="support",
        reason="coordinated round-zero content replacement",
        confidence=None,
        published=True,
        source_attempt_id=None,
        mock_only=True,
    )
    forged_state = PrivateState.from_update(forged_update, previous=None, mock_only=True)
    forged_post = PublicPost.from_private_update(forged_update, mock_only=True)
    forged_pointer = LatestPublicPointer.from_post(forged_post, previous=None, mock_only=True)
    with sqlite3.connect(database) as connection:
        for table, id_column, identity, value in (
            ("private_updates", "update_id", forged_update.update_id, forged_update),
            ("public_posts", "post_id", forged_post.post_id, forged_post),
        ):
            payload = value.to_payload()
            connection.execute(
                f"UPDATE {table} SET {id_column} = ?, payload_json = ?, payload_hash = ?",
                (
                    identity,
                    storage_module._canonical_json(payload),
                    canonical_payload_hash(payload),
                ),
            )
        for table, value in (
            ("private_states", forged_state),
            ("latest_public_pointers", forged_pointer),
        ):
            payload = value.to_payload()
            connection.execute(
                f"UPDATE {table} SET payload_json = ?, payload_hash = ? WHERE agent_id = ?",
                (
                    storage_module._canonical_json(payload),
                    canonical_payload_hash(payload),
                    "agent-0",
                ),
            )
    with pytest.raises(ValueError, match="round-0|root|initial"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0",),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


@pytest.mark.parametrize("tamper_kind", ("whitespace", "key_order", "duplicate_key"))
def test_reopen_rejects_noncanonical_or_duplicate_json_bytes(
    tmp_path: Path, tamper_kind: str
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ):
        pass
    with sqlite3.connect(database) as connection:
        payload_json = connection.execute(
            "SELECT manifest_payload_json FROM binding WHERE singleton = 1"
        ).fetchone()[0]
        if tamper_kind == "whitespace":
            forged = " " + payload_json
        elif tamper_kind == "key_order":
            payload = json.loads(payload_json)
            forged = json.dumps(
                dict(reversed(tuple(payload.items()))),
                ensure_ascii=False,
                sort_keys=False,
                separators=(",", ":"),
            )
        else:
            forged = '{"matched_seed":17,' + payload_json[1:]
        connection.execute(
            "UPDATE binding SET manifest_payload_json = ? WHERE singleton = 1", (forged,)
        )
    with pytest.raises(ValueError, match="canonical|duplicate|JSON"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0",),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


@pytest.mark.parametrize("drift", ("provider_request_id", "provider_metadata"))
def test_append_rejects_provider_evidence_drift_after_first_observation(
    tmp_path: Path, drift: str
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    terminal = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    pending = attempt_transition(terminal, EventStatus.PENDING)
    in_progress_payload = attempt_transition(terminal, EventStatus.IN_PROGRESS).to_payload()
    in_progress_payload["provider_request_id"] = terminal.provider_request_id
    in_progress_payload["provider_metadata"] = {"phase": "accepted"}
    in_progress_payload["provider_metadata_hash"] = canonical_payload_hash(
        in_progress_payload["provider_metadata"]
    )
    in_progress = GenerationAttempt.from_payload(in_progress_payload)
    terminal_payload = terminal.to_payload()
    if drift == "provider_request_id":
        terminal_payload["provider_request_id"] = "provider-drifted"
    else:
        terminal_payload["provider_metadata"] = {"phase": "changed", "headers": {}}
        terminal_payload["provider_metadata_hash"] = canonical_payload_hash(
            terminal_payload["provider_metadata"]
        )
    drifted_terminal = GenerationAttempt.from_payload(terminal_payload)
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
        store.seal_initial_state()
        store.append_attempt(pending)
        store.append_attempt(in_progress)
        with pytest.raises(ValueError, match="provider|metadata|request"):
            store.append_attempt(drifted_terminal)


def test_reopen_rejects_provider_metadata_rewrite_in_transition_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    terminal = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
        store.seal_initial_state()
        store.append_attempt(attempt_transition(terminal, EventStatus.PENDING))
        in_progress_payload = attempt_transition(terminal, EventStatus.IN_PROGRESS).to_payload()
        in_progress_payload["provider_request_id"] = terminal.provider_request_id
        in_progress_payload["provider_metadata"] = terminal.to_payload()["provider_metadata"]
        in_progress_payload["provider_metadata_hash"] = canonical_payload_hash(
            in_progress_payload["provider_metadata"]
        )
        store.append_attempt(GenerationAttempt.from_payload(in_progress_payload))
        store.append_attempt(terminal)
    with sqlite3.connect(database) as connection:
        payload_json = connection.execute(
            """SELECT payload_json FROM attempt_transitions
               WHERE attempt_id = ? AND status = ?""",
            (terminal.attempt_id, EventStatus.SUCCEEDED.value),
        ).fetchone()[0]
        payload = json.loads(payload_json)
        payload["provider_metadata"] = {"headers": {"x-request-id": "rewritten"}}
        payload["provider_metadata_hash"] = canonical_payload_hash(payload["provider_metadata"])
        connection.execute(
            """UPDATE attempt_transitions SET payload_json = ?, payload_hash = ?
               WHERE attempt_id = ? AND status = ?""",
            (
                storage_module._canonical_json(payload),
                canonical_payload_hash(payload),
                terminal.attempt_id,
                EventStatus.SUCCEEDED.value,
            ),
        )
    with pytest.raises(ValueError, match="provider|metadata"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0",),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


def test_e0_storage_rejects_ws_cursor_provenance_before_seal(tmp_path: Path) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    forged_cursor = FeedCursor.initial(
        matched_seed=run_manifest.matched_seed,
        receiver_agent_id="agent-0",
        exposure_mode="ws_neighbors",
        exposure_graph_hash=SHA_A,
        mock_only=True,
    )
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        with pytest.raises(ValueError, match="exposure|cursor|mode|graph"):
            store.initialize_agent(*initial[:4], forged_cursor)


def test_attempt_transitions_rejects_row_envelope_tamper_immediately(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    pending = attempt_transition(attempt(run_manifest), EventStatus.PENDING)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
        store.seal_initial_state()
        store.append_attempt(pending)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE attempt_transitions SET event_id = 'forged-event' WHERE attempt_id = ?",
                (pending.attempt_id,),
            )
        with pytest.raises(ValueError, match="transition|event|identity|envelope"):
            store.attempt_transitions(pending.attempt_id)


@pytest.mark.parametrize(
    ("forged_mode", "forged_hash"),
    (("self_history_only", None), ("ws_neighbors", SHA_B)),
)
def test_social_run_rejects_multiagent_cursor_provenance_drift(
    tmp_path: Path, forged_mode: str, forged_hash: str | None
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,) * 4), cell_id="P1-I0-C0-E2")
    ws = build_ws_artifact(n=4, k=2, p=0.05, matched_seed=17, mock_only=True)
    artifacts = {"population": SHA_B, ws.artifact_id: ws.output_hash}
    agent_zero = initial_records("agent-0")
    agent_one = initial_records("agent-1")
    cursor_zero = FeedCursor.initial(
        matched_seed=run_manifest.matched_seed,
        receiver_agent_id="agent-0",
        exposure_mode="ws_neighbors",
        exposure_graph_hash=ws.output_hash,
        mock_only=True,
    )
    forged_cursor = FeedCursor.initial(
        matched_seed=run_manifest.matched_seed,
        receiver_agent_id="agent-1",
        exposure_mode=forged_mode,
        exposure_graph_hash=forged_hash,
        mock_only=True,
    )
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="ws_neighbors",
        expected_exposure_graph_hash=ws.output_hash,
        expected_exposure_graph_artifact=ws,
    ) as store:
        store.initialize_agent(*agent_zero[:4], cursor_zero)
        with pytest.raises(ValueError, match="exposure|cursor|mode|graph"):
            store.initialize_agent(*agent_one[:4], forged_cursor)


def test_social_run_reopen_rejects_alternate_bound_graph_hash(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,) * 4), cell_id="P1-I0-C0-E2")
    ws = build_ws_artifact(n=4, k=2, p=0.05, matched_seed=17, mock_only=True)
    alternate = build_ws_artifact(n=4, k=2, p=0.10, matched_seed=17, mock_only=True)
    artifacts = {
        "population": SHA_B,
        ws.artifact_id: ws.output_hash,
        alternate.artifact_id: alternate.output_hash,
    }
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="ws_neighbors",
        expected_exposure_graph_hash=ws.output_hash,
        expected_exposure_graph_artifact=ws,
    ) as store:
        for agent_id in expected_agent_ids(run_manifest):
            initial = initial_records(agent_id)
            agent_cursor = FeedCursor.initial(
                matched_seed=run_manifest.matched_seed,
                receiver_agent_id=agent_id,
                exposure_mode="ws_neighbors",
                exposure_graph_hash=ws.output_hash,
                mock_only=True,
            )
            store.initialize_agent(*initial[:4], agent_cursor)
        store.seal_initial_state()
    with pytest.raises(ValueError, match="binding|exposure|graph"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes=artifacts,
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=alternate.output_hash,
            expected_exposure_graph_artifact=alternate,
        )


@pytest.mark.parametrize(
    ("forged_mode", "forged_hash"),
    (("self_history_only", None), ("ws_neighbors", SHA_B)),
)
def test_social_run_reopen_rejects_stored_cursor_provenance_drift(
    tmp_path: Path, forged_mode: str, forged_hash: str | None
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,) * 4), cell_id="P1-I0-C0-E2")
    ws = build_ws_artifact(n=4, k=2, p=0.05, matched_seed=17, mock_only=True)
    artifacts = {"population": SHA_B, ws.artifact_id: ws.output_hash}
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="ws_neighbors",
        expected_exposure_graph_hash=ws.output_hash,
        expected_exposure_graph_artifact=ws,
    ) as store:
        for agent_id in expected_agent_ids(run_manifest):
            initial = initial_records(agent_id)
            agent_cursor = FeedCursor.initial(
                matched_seed=run_manifest.matched_seed,
                receiver_agent_id=agent_id,
                exposure_mode="ws_neighbors",
                exposure_graph_hash=ws.output_hash,
                mock_only=True,
            )
            store.initialize_agent(*initial[:4], agent_cursor)
        store.seal_initial_state()
    forged_cursor = FeedCursor.initial(
        matched_seed=run_manifest.matched_seed,
        receiver_agent_id="agent-0",
        exposure_mode=forged_mode,
        exposure_graph_hash=forged_hash,
        mock_only=True,
    )
    payload = forged_cursor.to_payload()
    with sqlite3.connect(database) as connection:
        for table in ("feed_cursors", "initial_feed_cursors"):
            connection.execute(
                f"UPDATE {table} SET payload_json = ?, payload_hash = ? WHERE agent_id = ?",
                (
                    storage_module._canonical_json(payload),
                    canonical_payload_hash(payload),
                    "agent-0",
                ),
            )
    with pytest.raises(ValueError, match="exposure|cursor|round-0|root"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes=artifacts,
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=ws.output_hash,
            expected_exposure_graph_artifact=ws,
        )


def test_e2_rejects_population_artifact_hash_without_network_envelope(
    tmp_path: Path,
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)), cell_id="P1-I0-C0-E2")
    with pytest.raises((TypeError, ValueError), match="network|graph|artifact|envelope"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0",),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=SHA_B,
        )


def test_attempt_transitions_rejects_single_in_progress_prefix_tamper(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    terminal = attempt(run_manifest)
    pending = attempt_transition(terminal, EventStatus.PENDING)
    in_progress = attempt_transition(terminal, EventStatus.IN_PROGRESS)
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial_records("agent-0"))
        store.seal_initial_state()
        store.append_attempt(pending)
        payload = in_progress.to_payload()
        with sqlite3.connect(database) as connection:
            connection.execute(
                """UPDATE attempt_transitions
                   SET status = ?, payload_json = ?, payload_hash = ?
                   WHERE attempt_id = ?""",
                (
                    EventStatus.IN_PROGRESS.value,
                    storage_module._canonical_json(payload),
                    canonical_payload_hash(payload),
                    pending.attempt_id,
                ),
            )
        with pytest.raises(ValueError, match="lifecycle|prefix|PENDING"):
            store.attempt_transitions(pending.attempt_id)


@pytest.mark.parametrize(
    ("cell_id", "mode", "artifact_index"),
    (("P1-I0-C0-E1", "shuffled_social", 1), ("P1-I0-C0-E2", "ws_neighbors", 0)),
)
def test_social_storage_accepts_real_typed_network_artifact(
    tmp_path: Path, cell_id: str, mode: str, artifact_index: int
) -> None:
    ws, shadow = real_network_artifacts()
    artifact = (ws, shadow)[artifact_index]
    run_manifest = social_manifest(cell_id=cell_id)
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={
            ws.artifact_id: ws.output_hash,
            artifact.artifact_id: artifact.output_hash,
        },
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode=mode,
        expected_exposure_graph_hash=artifact.output_hash,
        expected_exposure_graph_artifact=artifact,
        expected_source_ws_artifact=ws if mode == "shuffled_social" else None,
    ) as store:
        assert store.binding.expected_exposure_graph_artifact_id == artifact.artifact_id
        assert store.binding.expected_exposure_graph_artifact_type == artifact.artifact_type


def test_social_storage_rejects_wrong_typed_network_artifact(tmp_path: Path) -> None:
    _, shadow = real_network_artifacts()
    run_manifest = manifest(schedule(publish_flags=(False,)), cell_id="P1-I0-C0-E2")
    with pytest.raises(ValueError, match="artifact.*type|graph.*type|ws_graph"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={shadow.artifact_id: shadow.output_hash},
            expected_agent_ids=("agent-0",),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=shadow.output_hash,
            expected_exposure_graph_artifact=shadow,
        )


@pytest.mark.parametrize("mismatch", ("id", "hash"))
def test_social_storage_rejects_graph_artifact_map_mismatch(tmp_path: Path, mismatch: str) -> None:
    ws, _ = real_network_artifacts()
    run_manifest = manifest(schedule(publish_flags=(False,)), cell_id="P1-I0-C0-E2")
    artifacts = (
        {"artifact-" + SHA_B: ws.output_hash} if mismatch == "id" else {ws.artifact_id: SHA_B}
    )
    with pytest.raises(ValueError, match="artifact.*(ID|id|hash)|binding|output"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes=artifacts,
            expected_agent_ids=("agent-0",),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=ws.output_hash,
            expected_exposure_graph_artifact=ws,
        )


def test_social_storage_rejects_reflection_tampered_network_envelope(
    tmp_path: Path,
) -> None:
    ws, _ = real_network_artifacts()
    object.__setattr__(ws, "artifact_id", "artifact-" + SHA_B)
    try:
        run_manifest = manifest(schedule(publish_flags=(False,)), cell_id="P1-I0-C0-E2")
        with pytest.raises(ValueError, match="artifact|envelope|identity"):
            RunStorage.create(
                tmp_path / "run.sqlite3",
                manifest=run_manifest,
                artifact_hashes={ws.artifact_id: ws.output_hash},
                expected_agent_ids=("agent-0",),
                expected_exposure_mode="ws_neighbors",
                expected_exposure_graph_hash=ws.output_hash,
                expected_exposure_graph_artifact=ws,
            )
    finally:
        real_network_artifacts.cache_clear()


def test_social_storage_open_rejects_alternate_typed_network_artifact(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    ws, _ = real_network_artifacts(17)
    alternate = build_ws_artifact(n=40, k=6, p=0.05, matched_seed=17, mock_only=True)
    run_manifest = social_manifest(cell_id="P1-I0-C0-E2")
    artifacts = {
        ws.artifact_id: ws.output_hash,
        alternate.artifact_id: alternate.output_hash,
    }
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="ws_neighbors",
        expected_exposure_graph_hash=ws.output_hash,
        expected_exposure_graph_artifact=ws,
    ):
        pass
    with pytest.raises(ValueError, match="binding|artifact|graph"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes=artifacts,
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=alternate.output_hash,
            expected_exposure_graph_artifact=alternate,
        )


def social_manifest(*, cell_id: str, population_size: int = 40) -> RunManifest:
    return manifest(schedule(publish_flags=(False,) * population_size), cell_id=cell_id)


def test_e2_rejects_ws_labeled_envelope_with_non_network_payload(tmp_path: Path) -> None:
    run_manifest = social_manifest(cell_id="P1-I0-C0-E2")
    fake = ArtifactEnvelope.create(
        artifact_type="paper1.mock_ws_graph",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="mock.not-a-network",
        algorithm_version="1.0.0",
        input_hashes={"fake": SHA_A},
        payload={"matched_seed": 17, "not_a_graph": True},
        rng_provenance=(),
    )
    with pytest.raises((TypeError, ValueError), match="network|graph|WS|algorithm|payload"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B, fake.artifact_id: fake.output_hash},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=fake.output_hash,
            expected_exposure_graph_artifact=fake,
        )


def test_e2_rejects_valid_ws_from_foreign_matched_seed(tmp_path: Path) -> None:
    run_manifest = social_manifest(cell_id="P1-I0-C0-E2")
    foreign_ws, _ = real_network_artifacts(18)
    with pytest.raises(ValueError, match="seed|matched"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={
                "population": SHA_B,
                foreign_ws.artifact_id: foreign_ws.output_hash,
            },
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=foreign_ws.output_hash,
            expected_exposure_graph_artifact=foreign_ws,
        )


def test_e2_rejects_valid_ws_node_count_different_from_population(tmp_path: Path) -> None:
    run_manifest = social_manifest(cell_id="P1-I0-C0-E2", population_size=42)
    ws, _ = real_network_artifacts(17)
    with pytest.raises(ValueError, match="node|population|roster|size"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B, ws.artifact_id: ws.output_hash},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="ws_neighbors",
            expected_exposure_graph_hash=ws.output_hash,
            expected_exposure_graph_artifact=ws,
        )


def test_e1_requires_explicit_source_ws_artifact(tmp_path: Path) -> None:
    run_manifest = social_manifest(cell_id="P1-I0-C0-E1")
    _, shadow = real_network_artifacts()
    with pytest.raises((TypeError, ValueError), match="source|WS|ws"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B, shadow.artifact_id: shadow.output_hash},
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="shuffled_social",
            expected_exposure_graph_hash=shadow.output_hash,
            expected_exposure_graph_artifact=shadow,
        )


def test_e1_rejects_wrong_source_ws_artifact(tmp_path: Path) -> None:
    run_manifest = social_manifest(cell_id="P1-I0-C0-E1")
    ws, shadow = real_network_artifacts()
    wrong_source = build_ws_artifact(n=40, k=6, p=0.05, matched_seed=17, mock_only=True)
    artifacts = {
        "population": SHA_B,
        ws.artifact_id: ws.output_hash,
        shadow.artifact_id: shadow.output_hash,
        wrong_source.artifact_id: wrong_source.output_hash,
    }
    with pytest.raises(ValueError, match="source|input|WS|ws"):
        RunStorage.create(
            tmp_path / "run.sqlite3",
            manifest=run_manifest,
            artifact_hashes=artifacts,
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="shuffled_social",
            expected_exposure_graph_hash=shadow.output_hash,
            expected_exposure_graph_artifact=shadow,
            expected_source_ws_artifact=wrong_source,
        )


@pytest.mark.parametrize(
    ("cell_id", "mode", "artifact_index"),
    (("P1-I0-C0-E1", "shuffled_social", 1), ("P1-I0-C0-E2", "ws_neighbors", 0)),
)
def test_social_storage_accepts_strict_validated_graph_bindings(
    tmp_path: Path, cell_id: str, mode: str, artifact_index: int
) -> None:
    ws, shadow = real_network_artifacts()
    exposure = (ws, shadow)[artifact_index]
    run_manifest = social_manifest(cell_id=cell_id)
    artifacts = {
        "population": SHA_B,
        ws.artifact_id: ws.output_hash,
        exposure.artifact_id: exposure.output_hash,
    }
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode=mode,
        expected_exposure_graph_hash=exposure.output_hash,
        expected_exposure_graph_artifact=exposure,
        expected_source_ws_artifact=ws if mode == "shuffled_social" else None,
    ) as store:
        assert store.binding.expected_exposure_graph_artifact_id == exposure.artifact_id
        assert store.binding.expected_source_ws_artifact_id == ws.artifact_id


def test_e1_open_rejects_alternate_or_reflection_tampered_source_ws(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = social_manifest(cell_id="P1-I0-C0-E1")
    ws, shadow = real_network_artifacts()
    alternate = build_ws_artifact(n=40, k=6, p=0.05, matched_seed=17, mock_only=True)
    artifacts = {
        "population": SHA_B,
        ws.artifact_id: ws.output_hash,
        shadow.artifact_id: shadow.output_hash,
        alternate.artifact_id: alternate.output_hash,
    }
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="shuffled_social",
        expected_exposure_graph_hash=shadow.output_hash,
        expected_exposure_graph_artifact=shadow,
        expected_source_ws_artifact=ws,
    ):
        pass
    with pytest.raises(ValueError, match="source|input|binding|WS|ws"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes=artifacts,
            expected_agent_ids=expected_agent_ids(run_manifest),
            expected_exposure_mode="shuffled_social",
            expected_exposure_graph_hash=shadow.output_hash,
            expected_exposure_graph_artifact=shadow,
            expected_source_ws_artifact=alternate,
        )
    object.__setattr__(ws, "artifact_id", "artifact-" + SHA_B)
    try:
        with pytest.raises(ValueError, match="artifact|identity|source|envelope"):
            RunStorage.open(
                database,
                manifest=run_manifest,
                artifact_hashes={**artifacts, ws.artifact_id: ws.output_hash},
                expected_agent_ids=expected_agent_ids(run_manifest),
                expected_exposure_mode="shuffled_social",
                expected_exposure_graph_hash=shadow.output_hash,
                expected_exposure_graph_artifact=shadow,
                expected_source_ws_artifact=ws,
            )
    finally:
        real_network_artifacts.cache_clear()


def test_success_event_chain_binds_full_provider_transition_history(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    pending = attempt_transition(succeeded, EventStatus.PENDING)
    in_progress_payload = attempt_transition(succeeded, EventStatus.IN_PROGRESS).to_payload()
    in_progress_payload["provider_request_id"] = succeeded.provider_request_id
    in_progress_payload["provider_metadata"] = succeeded.to_payload()["provider_metadata"]
    in_progress_payload["provider_metadata_hash"] = canonical_payload_hash(
        in_progress_payload["provider_metadata"]
    )
    in_progress = GenerationAttempt.from_payload(in_progress_payload)
    records = successful_state_records(
        run_manifest,
        ordinal=0,
        previous_state=initial[1],
        previous_cursor=initial[4],
        previous_pointer=initial[3],
    )
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        store.seal_initial_state()
        store.append_attempt(pending)
        store.append_attempt(in_progress)
        store.append_attempt(succeeded)
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
    forged = in_progress.to_payload()
    forged["provider_request_id"] = None
    forged["provider_metadata"] = {}
    forged["provider_metadata_hash"] = canonical_payload_hash({})
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE attempt_transitions SET payload_json = ?, payload_hash = ?
               WHERE attempt_id = ? AND status = ?""",
            (
                storage_module._canonical_json(forged),
                canonical_payload_hash(forged),
                succeeded.attempt_id,
                EventStatus.IN_PROGRESS.value,
            ),
        )
    with pytest.raises(ValueError, match="chain|transition|provider|integrity"):
        RunStorage.open(
            database,
            manifest=run_manifest,
            artifact_hashes={"population": SHA_B},
            expected_agent_ids=("agent-0",),
            expected_exposure_mode="self_history_only",
            expected_exposure_graph_hash=None,
        )


@pytest.mark.parametrize("tamper", ("attempt_only_valid_drift", "coordinated_invalid_uri"))
def test_commit_rejects_external_terminal_uri_tamper_without_state_advance(
    tmp_path: Path, tamper: str
) -> None:
    database = tmp_path / "run.sqlite3"
    run_manifest = manifest(schedule(publish_flags=(False,)))
    initial = initial_records("agent-0")
    succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    assert succeeded.raw_response is not None and succeeded.raw_response_hash is not None
    original = ExternalResponseReference(
        uri="file:///archive/raw/original-before-commit.json",
        sha256=succeeded.raw_response_hash,
    )
    records = successful_state_records(
        run_manifest,
        ordinal=0,
        previous_state=initial[1],
        previous_cursor=initial[4],
        previous_pointer=initial[3],
    )
    with RunStorage.create(
        database,
        manifest=run_manifest,
        artifact_hashes={"population": SHA_B},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        store.initialize_agent(*initial)
        store.seal_initial_state()
        append_terminal_attempt(store, succeeded, external_response=original)
        before = store.progress
        forged_uri = (
            "file:///archive/raw/drifted-before-commit.json"
            if tamper == "attempt_only_valid_drift"
            else "relative/raw-response.json"
        )
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE attempts SET raw_response_uri = ? WHERE attempt_id = ?",
                (forged_uri, succeeded.attempt_id),
            )
            if tamper == "coordinated_invalid_uri":
                connection.execute(
                    """UPDATE attempt_transitions SET raw_response_uri = ?
                       WHERE attempt_id = ? AND status = ?""",
                    (forged_uri, succeeded.attempt_id, EventStatus.SUCCEEDED.value),
                )
        with pytest.raises(ValueError, match="URI|external|terminal|transition|attempt"):
            store.commit_success(
                successful_event(run_manifest, ordinal=0),
                final_attempt=succeeded,
                private_update=records[0],
                private_state=records[1],
                feed_cursor=records[2],
                public_post=records[3],
                latest_public_pointer=records[4],
            )
        assert store.progress == before
        assert store.event_at(0) is None
        assert store.private_state("agent-0") == initial[1]
        assert store.latest_public_pointer("agent-0") == initial[3]
        assert store.feed_cursor("agent-0") == initial[4]
