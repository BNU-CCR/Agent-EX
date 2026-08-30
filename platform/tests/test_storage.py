from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

import pytest
import agent_ex.storage as storage_module

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
from agent_ex.feed import FeedCursor
from agent_ex.network import build_shadow_artifact, build_ws_artifact
from agent_ex.state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from agent_ex.storage import ExternalResponseReference, RunStorage, StorageBinding
from agent_ex.topic import TopicPackage


SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = "2026-08-18T00:00:00+00:00"


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
            "schema_version": "paper1.run-storage.v2",
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
        assert binding.schema_version == "paper1.run-storage.v2"
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
