from dataclasses import FrozenInstanceError, replace
import json
from types import SimpleNamespace

import pytest

import agent_ex
from agent_ex.domain import (
    EventStatus,
    ExposureRecord,
    FrozenSchedule,
    GenerationAttempt,
    GenerationEvent,
    RunManifest,
    ScheduleSlot,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
    derive_run_id,
    evaluate_analysis_eligibility,
    validate_evidence_graph,
)
from agent_ex.state import PrivateUpdate, PublicPost
from agent_ex.topic import TopicPackage


SHA_A = "a" * 64
SHA_B = "b" * 64


def topic() -> TopicPackage:
    return TopicPackage.from_payload(
        {
            "schema_version": "paper1.topic-package.mock.v1",
            "package_version": "mock",
            "topic_id": "mock-topic",
            "construct": "mock",
            "target_population": "mock",
            "applicability": "mock",
            "fact_card": "mock",
            "core_statement": "mock",
            "paraphrases": ["mock"],
            "stance_labels": [f"label-{index}" for index in range(7)],
            "confidence_contract": {"minimum": 1, "maximum": 5, "analysis_only": True},
            "output_contract": ["stance", "confidence", "public_reason"],
            "argument_families": ["mock"],
            "round0_reason_library_artifact_id": "artifact-" + "a" * 64,
            "topic_extension_fields": [],
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        }
    )


def source_post(
    *,
    agent_id: str,
    event_id: str | None,
    event_ordinal: int | None,
    seed: int = 17,
) -> tuple[PrivateUpdate, PublicPost]:
    update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=seed,
        agent_id=agent_id,
        event_id=event_id,
        event_ordinal=event_ordinal,
        sequence_index=0 if event_ordinal is None else 1,
        stance_label="label-0",
        reason="typed source reason",
        confidence=None if event_ordinal is None else 3,
        published=True,
        source_attempt_id=(None if event_id is None else derive_attempt_id(event_id, 1)),
        mock_only=True,
    )
    return update, PublicPost.from_private_update(update, mock_only=True)


NOW = "2026-07-29T00:00:00Z"
LATER = "2026-07-29T00:00:01Z"


def make_schedule(
    *,
    population_size: int = 2,
    sweep_count: int = 2,
    agent_ids: tuple[str, ...] | None = None,
) -> FrozenSchedule:
    roster = agent_ids or tuple(f"agent-{index}" for index in range(population_size))
    slots = tuple(
        ScheduleSlot(
            event_ordinal=(sweep_index - 1) * population_size + draw_index,
            sweep_index=sweep_index,
            draw_index=draw_index,
            agent_id=roster[(draw_index + sweep_index - 1) % len(roster)],
            publish_flag=(draw_index % 2 == 0),
        )
        for sweep_index in range(1, sweep_count + 1)
        for draw_index in range(population_size)
    )
    return FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id="mock.weighted-with-replacement",
        algorithm_version="1.0.0",
        population_size=population_size,
        sweep_count=sweep_count,
        slots=slots,
    )


def make_run_spec(schedule: FrozenSchedule) -> dict[str, object]:
    return {
        "protocol_id": "paper1",
        "protocol_version": "draft",
        "protocol_hash": SHA_A,
        "schedule_hash": schedule.schedule_hash,
        "run_config": {
            "population": schedule.population_size,
            "sweep_count": schedule.sweep_count,
            "expected_event_count": schedule.count,
        },
        "request_parameters": {"temperature": 0.0},
    }


def make_manifest(
    schedule: FrozenSchedule,
    *,
    statuses: tuple[EventStatus, ...],
    recovery_cursor: dict[str, object] | None = None,
) -> RunManifest:
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, matched_seed=17, launch_nonce="launch-a")
    event_ids = tuple(derive_event_id(run_id, ordinal) for ordinal in range(len(statuses)))
    counts = {status.value: statuses.count(status) for status in EventStatus}
    complete = len(statuses) == schedule.count and all(
        status is EventStatus.SUCCEEDED for status in statuses
    )
    return RunManifest(
        run_id=run_id,
        run_spec=run_spec,
        run_spec_hash=canonical_payload_hash(run_spec),
        matched_seed=17,
        launch_nonce="launch-a",
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
        schedule=schedule,
        schedule_hash=schedule.schedule_hash,
        checkpoint_uri=None if recovery_cursor is None else "file:///tmp/checkpoint.json",
        checkpoint_hash=None if recovery_cursor is None else SHA_A,
        recovery_cursor=recovery_cursor,
        event_ids=event_ids,
        terminal_counts=counts,
        started_at=NOW,
        updated_at=LATER,
        archive=(
            {"status": "frozen", "uri": "file:///tmp/archive", "hash": SHA_B}
            if complete
            else {"status": "pending", "uri": None, "hash": None}
        ),
    )


def make_exposure(
    *,
    event_ordinal: int,
    receiver_agent_id: str,
    source_agent_ids: tuple[str, ...] = (),
    source_event_ids: tuple[str | None, ...] = (),
    matched_seed: int = 17,
    source_posts: tuple[PublicPost, ...] | None = None,
    expired_round0_posts: tuple[PublicPost, ...] = (),
    expired_event_posts: tuple[PublicPost, ...] = (),
) -> ExposureRecord:
    if source_posts is not None:
        source_agent_ids = tuple(post.author_agent_id for post in source_posts)
        source_event_ids = tuple(post.source_event_id for post in source_posts)
        post_ids = tuple(post.post_id for post in source_posts)
        post_hashes = tuple(post.record_hash for post in source_posts)
        update_ids = tuple(post.source_update_id for post in source_posts)
        update_hashes = tuple(post.source_update_hash for post in source_posts)
    else:
        post_ids = tuple(f"post-{event_ordinal}-{index}" for index in range(len(source_event_ids)))
        post_hashes = (SHA_A,) * len(post_ids)
        update_ids = tuple(f"update-{event_ordinal}-{index}" for index in range(len(post_ids)))
        update_hashes = (SHA_B,) * len(post_ids)
    expired_posts = expired_round0_posts + expired_event_posts
    expired_ids = tuple(post.post_id for post in expired_posts)
    candidate_ids = post_ids + expired_ids
    candidate_hashes = post_hashes + tuple(post.record_hash for post in expired_posts)
    rendered_texts = tuple(
        f"Member {agent_id} | mock stance | mock public reason" for agent_id in source_agent_ids
    )
    return ExposureRecord.create(
        matched_seed=matched_seed,
        event_ordinal=event_ordinal,
        receiver_agent_id=receiver_agent_id,
        exposure_mode="ws_neighbors",
        exposure_graph_hash=SHA_A,
        capacity=4,
        selection_id=f"selection-{event_ordinal}",
        selection_hash=SHA_A,
        cursor_before_id=f"cursor-before-{event_ordinal}",
        cursor_before_hash=SHA_A,
        cursor_after_id=f"cursor-after-{event_ordinal}",
        cursor_after_hash=SHA_B,
        candidate_post_ids=candidate_ids,
        candidate_post_hashes=candidate_hashes,
        selected_post_ids=post_ids,
        expired_post_ids=expired_ids,
        round0_candidate_post_ids=tuple(
            post_id
            for post_id, source_event_id in zip(post_ids, source_event_ids, strict=True)
            if source_event_id is None
        )
        + tuple(post.post_id for post in expired_round0_posts),
        source_post_ids=post_ids,
        source_post_hashes=post_hashes,
        source_update_ids=update_ids,
        source_update_hashes=update_hashes,
        source_agent_ids=source_agent_ids,
        source_event_ids=source_event_ids,
        message_ages=(1,) * len(post_ids),
        original_orders=tuple(range(len(post_ids))),
        display_slots=tuple(range(len(post_ids))),
        rendered_texts=rendered_texts,
        rendered_hashes=tuple(canonical_payload_hash(text) for text in rendered_texts),
        slot_rng_hash=SHA_A,
        round0_rng_hash=(
            SHA_A
            if any(value is None for value in source_event_ids) or expired_round0_posts
            else None
        ),
        mock_only=True,
    )


def make_attempt(
    event_id: str,
    exposure_id: str,
    *,
    attempt_index: int = 1,
    status: EventStatus = EventStatus.SUCCEEDED,
    model_seed: int = 123,
) -> GenerationAttempt:
    prompt = ({"role": "user", "content": "mock"},)
    params = {"temperature": 0.0}
    identity = {"provider": "mock", "model": "deterministic", "revision": "1"}
    provider_metadata = {"headers": {"x-request-id": f"provider-{attempt_index}"}}
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    raw = '{"stance": 4}'
    parsed = {"stance": 4, "reason": "mock"}
    terminal = status in {EventStatus.SUCCEEDED, EventStatus.FAILED}
    return GenerationAttempt(
        attempt_id=derive_attempt_id(event_id, attempt_index),
        event_id=event_id,
        attempt_index=attempt_index,
        status=status,
        request_id=f"request-{attempt_index}",
        exposure_id=exposure_id,
        rendered_messages=prompt,
        rendered_prompt_hash=canonical_payload_hash(prompt),
        request_parameters=params,
        request_parameters_hash=canonical_payload_hash(params),
        model_identity=identity,
        model_identity_hash=canonical_payload_hash(identity),
        model_seed=model_seed,
        provider_request_id=(f"provider-{attempt_index}" if terminal else None),
        provider_metadata=provider_metadata if terminal else {},
        provider_metadata_hash=canonical_payload_hash(provider_metadata if terminal else {}),
        http_status=200 if status is EventStatus.SUCCEEDED else (422 if terminal else None),
        raw_response=raw if status is EventStatus.SUCCEEDED else None,
        raw_response_hash=(
            canonical_payload_hash(raw) if status is EventStatus.SUCCEEDED else None
        ),
        parsed_response=parsed if status is EventStatus.SUCCEEDED else None,
        parsed_response_hash=(
            canonical_payload_hash(parsed) if status is EventStatus.SUCCEEDED else None
        ),
        usage=usage if status is EventStatus.SUCCEEDED else {},
        usage_hash=canonical_payload_hash(usage if status is EventStatus.SUCCEEDED else {}),
        finish_reason="stop" if status is EventStatus.SUCCEEDED else None,
        error={"code": "mock_failure"} if status is EventStatus.FAILED else None,
        started_at=None if status is EventStatus.PENDING else NOW,
        finished_at=LATER if terminal else None,
    )


def make_event(
    run_id: str,
    slot: ScheduleSlot,
    *,
    status: EventStatus = EventStatus.SUCCEEDED,
    attempt_count: int = 1,
) -> GenerationEvent:
    event_id = derive_event_id(run_id, slot.event_ordinal)
    return GenerationEvent(
        run_id=run_id,
        event_id=event_id,
        event_ordinal=slot.event_ordinal,
        sweep_index=slot.sweep_index,
        draw_index=slot.draw_index,
        agent_id=slot.agent_id,
        publish_flag=slot.publish_flag,
        exposure_id=f"exposure-{slot.event_ordinal}",
        status=status,
        attempt_ids=tuple(
            derive_attempt_id(event_id, index) for index in range(1, attempt_count + 1)
        ),
        failure_reason="retry budget exhausted" if status is EventStatus.FAILED else None,
    )


def test_event_id_uses_only_run_id_and_global_zero_based_ordinal() -> None:
    run_id = "run-stable"

    assert derive_event_id(run_id, 0) == derive_event_id(run_id, 0)
    assert derive_event_id(run_id, 0) != derive_event_id(run_id, 1)
    with pytest.raises(TypeError):
        derive_event_id(run_id, 1, "agent-1")  # type: ignore[call-arg]


def test_event_and_attempt_ids_reject_invalid_ordinals_and_indices() -> None:
    with pytest.raises(ValueError, match="event_ordinal"):
        derive_event_id("run-stable", -1)
    with pytest.raises(TypeError, match="event_ordinal"):
        derive_event_id("run-stable", True)
    with pytest.raises(ValueError, match="attempt_index"):
        derive_attempt_id("event-stable", 0)


def test_run_identity_rejects_whitespace_only_launch_nonce() -> None:
    with pytest.raises(ValueError, match="launch_nonce"):
        derive_run_id({"protocol_id": "paper1"}, 7, "   ")


def test_schedule_v2_supports_repeated_agent_within_same_sweep() -> None:
    schedule = make_schedule(agent_ids=("agent-repeated",))

    first, second = schedule.slots[:2]
    assert first.agent_id == second.agent_id
    assert first.sweep_index == second.sweep_index == 1
    assert first.event_ordinal != second.event_ordinal


def test_schedule_v2_round_trip_and_hash_cover_version_algorithm_and_order() -> None:
    schedule = make_schedule()
    payload = json.loads(json.dumps(schedule.to_payload()))

    restored = FrozenSchedule.from_payload(payload)

    assert restored == schedule
    assert restored.schedule_hash == schedule.schedule_hash
    assert payload["schema_version"] == "paper1.schedule.v2"
    assert payload["algorithm_id"] == "mock.weighted-with-replacement"
    assert payload["algorithm_version"] == "1.0.0"


def test_schedule_v1_is_explicitly_rejected() -> None:
    with pytest.raises(ValueError, match="v1|schema_version"):
        FrozenSchedule.from_payload(
            {"version": 1, "slots": [{"round_index": 1, "agent_id": "agent-1"}]}
        )


@pytest.mark.parametrize(
    "raw_slots, message",
    [
        (
            ((0, 1, 0, "agent-0", True), (2, 1, 1, "agent-1", False)),
            "event_ordinal",
        ),
        (
            ((0, 1, 0, "agent-0", True), (0, 1, 1, "agent-1", False)),
            "event_ordinal",
        ),
        (
            ((0, 1, 0, "agent-0", True), (1, 1, 2, "agent-1", False)),
            "draw_index",
        ),
        (((0, 3, 0, "agent-0", True),), "sweep_index"),
    ],
)
def test_schedule_rejects_ordinal_draw_and_sweep_gaps(
    raw_slots: tuple[tuple[object, ...], ...], message: str
) -> None:
    slots = tuple(ScheduleSlot(*values) for values in raw_slots)
    with pytest.raises(ValueError, match=message):
        FrozenSchedule(
            schema_version="paper1.schedule.v2",
            algorithm_id="mock.algorithm",
            algorithm_version="1",
            population_size=2,
            sweep_count=2,
            slots=slots,
        )


@pytest.mark.parametrize(
    "raw_slot",
    [
        (0, 1, 2, "agent-0", True),
        (0, 3, 0, "agent-0", True),
    ],
)
def test_schedule_rejects_draw_or_sweep_out_of_bounds(
    raw_slot: tuple[object, ...],
) -> None:
    slot = ScheduleSlot(*raw_slot)
    with pytest.raises(ValueError, match="bounds"):
        FrozenSchedule(
            schema_version="paper1.schedule.v2",
            algorithm_id="mock.algorithm",
            algorithm_version="1",
            population_size=2,
            sweep_count=2,
            slots=(slot,),
        )


def test_formal_scale_schedule_is_lightweight_and_has_fifty_thousand_slots() -> None:
    schedule = make_schedule(population_size=1000, sweep_count=50)

    assert schedule.count == 50_000
    assert schedule.slots[0].event_ordinal == 0
    assert schedule.slots[-1].event_ordinal == 49_999


def test_schedule_and_records_are_frozen_and_deeply_immutable() -> None:
    from agent_ex.rng import RNGProvenance

    schedule = make_schedule()
    with pytest.raises(FrozenInstanceError):
        schedule.slots[0].agent_id = "changed"  # type: ignore[misc]

    provenance = RNGProvenance.create(
        matched_seed=9,
        namespace="publish",
        coordinates={
            "artifact_kind": "schedule",
            "event_ordinal": 0,
            "nested": {"cell_scope": "common"},
        },
    )
    with pytest.raises(TypeError):
        provenance.coordinates["nested"]["cell_scope"] = "changed"  # type: ignore[index]


def test_rng_derivation_is_deterministic_and_namespace_separated() -> None:
    from agent_ex.rng import derive_rng_seed

    coordinates = {"artifact_kind": "schedule", "event_ordinal": 7}

    first = derive_rng_seed(41, "publish", coordinates)
    assert first == derive_rng_seed(41, "publish", coordinates)
    assert first != derive_rng_seed(41, "message_slot", coordinates)
    assert first != derive_rng_seed(
        41, "publish", {"artifact_kind": "schedule", "event_ordinal": 8}
    )


def test_event_level_rng_requires_global_event_ordinal_and_rejects_attempt_index() -> None:
    from agent_ex.rng import RNGProvenance

    with pytest.raises(ValueError, match="event_ordinal"):
        RNGProvenance.create(
            matched_seed=9,
            namespace="model_sampling",
            coordinates={"artifact_kind": "request"},
        )
    with pytest.raises(ValueError, match="attempt_index"):
        RNGProvenance.create(
            matched_seed=9,
            namespace="model_sampling",
            coordinates={"artifact_kind": "request", "event_ordinal": 3, "attempt_index": 2},
        )


@pytest.mark.parametrize(
    "nested_coordinates",
    [
        {"retry": {"attempt_index": 2}},
        {"retry_history": [{"attempt_index": 2}]},
    ],
)
def test_rng_rejects_attempt_index_at_any_coordinate_depth(
    nested_coordinates: dict[str, object],
) -> None:
    from agent_ex.rng import RNGProvenance

    with pytest.raises(ValueError, match="attempt_index"):
        RNGProvenance.create(
            matched_seed=9,
            namespace="model_sampling",
            coordinates={
                "artifact_kind": "request",
                "event_ordinal": 3,
                **nested_coordinates,
            },
        )


def test_retry_provenance_reuses_model_seed_for_same_event() -> None:
    from agent_ex.rng import RNGProvenance

    first = RNGProvenance.create(
        matched_seed=9,
        namespace="model_sampling",
        coordinates={"artifact_kind": "request", "event_ordinal": 3},
    )
    retry = RNGProvenance.from_payload(first.to_payload())

    assert first.derived_seed == retry.derived_seed
    assert "attempt_index" not in retry.coordinates


def test_rng_typed_construction_accepts_its_own_frozen_coordinates() -> None:
    from agent_ex.rng import RNGProvenance

    provenance = RNGProvenance.create(
        matched_seed=9,
        namespace="model_sampling",
        coordinates={
            "artifact_kind": "request",
            "event_ordinal": 3,
            "nested": {"scope": ["common"]},
        },
    )

    recreated = RNGProvenance.create(
        matched_seed=provenance.matched_seed,
        namespace=provenance.namespace,
        coordinates=provenance.coordinates,
    )

    assert recreated == provenance
    assert replace(provenance) == provenance


def test_rng_rejects_unregistered_namespace() -> None:
    from agent_ex.rng import derive_rng_seed

    with pytest.raises(ValueError, match="namespace"):
        derive_rng_seed(1, "typo_namespace", {"artifact_kind": "test"})


def test_artifact_envelope_binds_payload_metadata_inputs_and_rng() -> None:
    from agent_ex.artifacts import ArtifactEnvelope
    from agent_ex.rng import RNGProvenance

    rng = RNGProvenance.create(
        matched_seed=5,
        namespace="population",
        coordinates={"artifact_kind": "population"},
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="population",
        schema_version="paper1.population.v1",
        algorithm_id="mock.population",
        algorithm_version="1.0.0",
        input_hashes={"protocol": SHA_A},
        payload={"members": [{"agent_id": "agent-0"}]},
        rng_provenance=(rng,),
    )

    restored = ArtifactEnvelope.from_payload(json.loads(json.dumps(envelope.to_payload())))

    assert restored == envelope
    assert restored.output_hash == canonical_payload_hash(restored.payload)
    assert restored.artifact_id.startswith("artifact-")


def test_artifact_envelope_fails_closed_on_payload_or_identity_hash_drift() -> None:
    from agent_ex.artifacts import ArtifactEnvelope

    envelope = ArtifactEnvelope.create(
        artifact_type="topic",
        schema_version="paper1.topic.v1",
        algorithm_id="mock.topic",
        algorithm_version="1",
        input_hashes={},
        payload={"topic_id": "topic-1"},
        rng_provenance=(),
    )
    payload = envelope.to_payload()
    payload["payload"]["topic_id"] = "tampered"  # type: ignore[index]
    with pytest.raises(ValueError, match="output_hash"):
        ArtifactEnvelope.from_payload(payload)

    payload = envelope.to_payload()
    payload["artifact_id"] = "artifact-forged"
    with pytest.raises(ValueError, match="artifact_id"):
        ArtifactEnvelope.from_payload(payload)


def test_artifact_envelope_rejects_noncanonical_hashes_and_unknown_fields() -> None:
    from agent_ex.artifacts import ArtifactEnvelope

    with pytest.raises(ValueError, match="input_hashes"):
        ArtifactEnvelope.create(
            artifact_type="topic",
            schema_version="v1",
            algorithm_id="mock",
            algorithm_version="1",
            input_hashes={"protocol": "not-a-hash"},
            payload={},
            rng_provenance=(),
        )

    envelope = ArtifactEnvelope.create(
        artifact_type="topic",
        schema_version="v1",
        algorithm_id="mock",
        algorithm_version="1",
        input_hashes={},
        payload={},
        rng_provenance=(),
    )
    payload = envelope.to_payload()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="fields"):
        ArtifactEnvelope.from_payload(payload)


def test_artifact_typed_construction_accepts_its_own_frozen_values() -> None:
    from agent_ex.artifacts import ArtifactEnvelope
    from agent_ex.rng import RNGProvenance

    rng = RNGProvenance.create(
        matched_seed=5,
        namespace="population",
        coordinates={"artifact_kind": "population"},
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="population",
        schema_version="paper1.population.v1",
        algorithm_id="mock.population",
        algorithm_version="1.0.0",
        input_hashes={"protocol": SHA_A},
        payload={"members": [{"agent_id": "agent-0"}]},
        rng_provenance=(rng,),
    )

    recreated = ArtifactEnvelope.create(
        artifact_type=envelope.artifact_type,
        schema_version=envelope.schema_version,
        algorithm_id=envelope.algorithm_id,
        algorithm_version=envelope.algorithm_version,
        input_hashes=envelope.input_hashes,
        payload=envelope.payload,
        rng_provenance=envelope.rng_provenance,
    )

    assert recreated == envelope
    assert replace(envelope) == envelope


def test_artifact_create_rejects_invalid_rng_provenance_with_clear_type_error() -> None:
    from agent_ex.artifacts import ArtifactEnvelope

    with pytest.raises(TypeError, match="rng_provenance must be a tuple"):
        ArtifactEnvelope.create(
            artifact_type="topic",
            schema_version="v1",
            algorithm_id="mock",
            algorithm_version="1",
            input_hashes={},
            payload={},
            rng_provenance=[],  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="rng_provenance must contain RNGProvenance"):
        ArtifactEnvelope.create(
            artifact_type="topic",
            schema_version="v1",
            algorithm_id="mock",
            algorithm_version="1",
            input_hashes={},
            payload={},
            rng_provenance=("not-provenance",),  # type: ignore[arg-type]
        )


def test_event_status_contains_only_runtime_state_chain_values() -> None:
    assert {status.value for status in EventStatus} == {
        "pending",
        "in_progress",
        "succeeded",
        "failed",
    }


def test_generation_event_identity_uses_ordinal_and_schedule_coordinates_are_attributes() -> None:
    schedule = make_schedule(agent_ids=("agent-repeated",))
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 5, "nonce")
    first = make_event(run_id, schedule.slots[0])
    second = make_event(run_id, schedule.slots[1])

    assert first.agent_id == second.agent_id
    assert first.sweep_index == second.sweep_index
    assert first.event_id != second.event_id
    with pytest.raises(ValueError, match="event_id"):
        GenerationEvent(
            **{
                **first.to_payload(),
                "event_id": second.event_id,
                "status": EventStatus.SUCCEEDED,
                "attempt_ids": first.attempt_ids,
            }
        )


def test_generation_event_rejects_attempt_ids_not_derived_from_its_identity() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 5, "nonce")
    event = make_event(run_id, schedule.slots[0])

    with pytest.raises(ValueError, match="attempt_ids.*event_id"):
        GenerationEvent(
            **{
                **event.to_payload(),
                "status": EventStatus.SUCCEEDED,
                "attempt_ids": ("attempt-forged",),
            }
        )


def test_generation_attempt_retries_keep_event_identity_and_model_seed() -> None:
    event_id = derive_event_id("run-stable", 0)
    first = make_attempt(
        event_id,
        "exposure-0",
        attempt_index=1,
        status=EventStatus.FAILED,
        model_seed=99,
    )
    second = make_attempt(event_id, "exposure-0", attempt_index=2, model_seed=99)

    assert first.event_id == second.event_id
    assert first.model_seed == second.model_seed
    assert first.attempt_id != second.attempt_id


def test_generation_attempt_restores_provider_response_evidence_contract() -> None:
    attempt = make_attempt(derive_event_id("run-stable", 0), "exposure-0")
    payload = attempt.to_payload()

    assert payload["provider_metadata"] == {"headers": {"x-request-id": "provider-1"}}
    assert payload["provider_metadata_hash"] == canonical_payload_hash(payload["provider_metadata"])
    assert payload["http_status"] == 200
    assert payload["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    assert payload["usage_hash"] == canonical_payload_hash(payload["usage"])
    assert payload["finish_reason"] == "stop"


def test_generation_attempt_rejects_empty_model_identity() -> None:
    attempt = make_attempt(derive_event_id("run-stable", 0), "exposure-0")

    with pytest.raises(ValueError, match="model_identity"):
        replace(
            attempt,
            model_identity={},
            model_identity_hash=canonical_payload_hash({}),
        )


def test_failed_attempt_preserves_real_provider_response_without_parsed_success() -> None:
    succeeded = make_attempt(derive_event_id("run-stable", 0), "exposure-0")
    raw_error = '{"choices":[{"message":{"content":"not valid JSON contract"}}]}'
    failed = replace(
        succeeded,
        status=EventStatus.FAILED,
        raw_response=raw_error,
        raw_response_hash=canonical_payload_hash(raw_error),
        parsed_response=None,
        parsed_response_hash=None,
        finish_reason="stop",
        error={"code": "parse_error", "message": "response contract failed"},
    )

    restored = GenerationAttempt.from_payload(json.loads(json.dumps(failed.to_payload())))

    assert restored == failed
    assert restored.raw_response == raw_error
    assert restored.provider_metadata["headers"]["x-request-id"] == "provider-1"


def test_failed_attempt_rejects_parsed_success_content() -> None:
    succeeded = make_attempt(derive_event_id("run-stable", 0), "exposure-0")

    with pytest.raises(ValueError, match="failed attempt.*parsed"):
        replace(
            succeeded,
            status=EventStatus.FAILED,
            error={"code": "format_error"},
        )


def test_attempt_and_event_json_round_trip_are_strict() -> None:
    schedule = make_schedule()
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 5, "nonce")
    event = make_event(run_id, schedule.slots[0])
    attempt = make_attempt(event.event_id, event.exposure_id)

    restored_event = GenerationEvent.from_payload(json.loads(json.dumps(event.to_payload())))
    restored_attempt = GenerationAttempt.from_payload(json.loads(json.dumps(attempt.to_payload())))

    assert restored_event == event
    assert restored_attempt == attempt
    event_payload = event.to_payload()
    event_payload["round_index"] = 1
    with pytest.raises(ValueError, match="fields"):
        GenerationEvent.from_payload(event_payload)


def test_attempt_round_trip_rejects_hash_and_attempt_identity_drift() -> None:
    event_id = derive_event_id("run-stable", 0)
    attempt = make_attempt(event_id, "exposure-0")
    payload = attempt.to_payload()
    payload["raw_response"] = '{"stance": 7}'
    with pytest.raises(ValueError, match="raw_response_hash"):
        GenerationAttempt.from_payload(payload)

    payload = attempt.to_payload()
    payload["attempt_id"] = "attempt-forged"
    with pytest.raises(ValueError, match="attempt_id"):
        GenerationAttempt.from_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "tampered_value", "hash_field"),
    [
        (
            "provider_metadata",
            {"headers": {"x-request-id": "tampered"}},
            "provider_metadata_hash",
        ),
        (
            "usage",
            {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
            "usage_hash",
        ),
    ],
)
def test_attempt_round_trip_rejects_provider_evidence_hash_drift(
    field_name: str,
    tampered_value: dict[str, object],
    hash_field: str,
) -> None:
    attempt = make_attempt(derive_event_id("run-stable", 0), "exposure-0")
    payload = attempt.to_payload()
    payload[field_name] = tampered_value

    with pytest.raises(ValueError, match=hash_field):
        GenerationAttempt.from_payload(payload)


def test_evidence_graph_retries_must_keep_model_seed() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 17, "launch-a")
    event_id = derive_event_id(run_id, 0)
    event = make_event(run_id, schedule.slots[0], attempt_count=2)
    exposure = make_exposure(event_ordinal=0, receiver_agent_id=event.agent_id)
    attempts = (
        make_attempt(
            event_id,
            exposure.exposure_id,
            attempt_index=1,
            status=EventStatus.FAILED,
            model_seed=101,
        ),
        make_attempt(
            event_id,
            exposure.exposure_id,
            attempt_index=2,
            model_seed=202,
        ),
    )
    manifest = make_manifest(schedule, statuses=(EventStatus.SUCCEEDED,))

    with pytest.raises(ValueError, match="model_seed"):
        validate_evidence_graph(manifest, (event,), attempts, (exposure,))


def test_exposure_allows_empty_social_feed_and_same_sender_multiple_events() -> None:
    empty = make_exposure(event_ordinal=0, receiver_agent_id="agent-0")
    repeated_sender = make_exposure(
        event_ordinal=3,
        receiver_agent_id="agent-0",
        source_agent_ids=("agent-1", "agent-1"),
        source_event_ids=("event-a", "event-b"),
    )

    assert empty.source_event_ids == ()
    assert repeated_sender.source_agent_ids == ("agent-1", "agent-1")


def test_manifest_complete_requires_all_expected_events_succeeded() -> None:
    schedule = make_schedule()
    complete = make_manifest(schedule, statuses=(EventStatus.SUCCEEDED,) * schedule.count)

    assert complete.is_complete
    assert complete.next_event_ordinal == schedule.count
    assert evaluate_analysis_eligibility(complete)

    with pytest.raises(ValueError, match="archive|complete|succeeded"):
        make_manifest(
            schedule,
            statuses=(
                EventStatus.SUCCEEDED,
                EventStatus.SUCCEEDED,
                EventStatus.SUCCEEDED,
                EventStatus.FAILED,
            ),
        )


def test_manifest_recovery_cursor_is_only_next_ordinal_and_current_event_identity() -> None:
    schedule = make_schedule()
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 17, "launch-a")
    cursor = {
        "next_event_ordinal": 2,
        "event_id": derive_event_id(run_id, 2),
    }
    manifest = make_manifest(
        schedule,
        statuses=(EventStatus.SUCCEEDED, EventStatus.SUCCEEDED, EventStatus.FAILED),
        recovery_cursor=cursor,
    )

    assert manifest.next_event_ordinal == 2
    with pytest.raises(ValueError, match="recovery_cursor"):
        make_manifest(
            schedule,
            statuses=(EventStatus.SUCCEEDED, EventStatus.FAILED),
            recovery_cursor={
                "next_event_ordinal": 1,
                "event_id": derive_event_id(run_id, 1),
                "round_index": 1,
            },
        )


def test_manifest_payload_round_trip_requires_external_schedule() -> None:
    schedule = make_schedule()
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 17, "launch-a")
    manifest = make_manifest(
        schedule,
        statuses=(EventStatus.SUCCEEDED, EventStatus.FAILED),
        recovery_cursor={
            "next_event_ordinal": 1,
            "event_id": derive_event_id(run_id, 1),
        },
    )
    payload = json.loads(json.dumps(manifest.to_payload()))

    assert "schedule" not in payload
    assert RunManifest.from_payload(payload, schedule=schedule) == manifest
    with pytest.raises(ValueError, match="schedule"):
        RunManifest.from_payload(payload, schedule=make_schedule(population_size=3))


def test_manifest_payload_rejects_boolean_schedule_count() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    manifest = make_manifest(schedule, statuses=(EventStatus.SUCCEEDED,))
    payload = json.loads(json.dumps(manifest.to_payload()))
    payload["schedule_count"] = True

    with pytest.raises(TypeError, match="schedule_count.*integer"):
        RunManifest.from_payload(payload, schedule=schedule)


def test_manifest_payload_rejects_object_encoded_event_ids() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    manifest = make_manifest(schedule, statuses=(EventStatus.SUCCEEDED,))
    payload = json.loads(json.dumps(manifest.to_payload()))
    payload["event_ids"] = {manifest.event_ids[0]: None}

    with pytest.raises(TypeError, match="event_ids.*JSON array"):
        RunManifest.from_payload(payload, schedule=schedule)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("model_identity", {"provider": "mock"}),
        (
            "environment",
            {
                "python_version": "",
                "dependency_lock_hash": SHA_B,
                "platform": "test",
            },
        ),
    ],
)
def test_manifest_reproducibility_identity_requires_all_nonempty_fields(
    field_name: str, invalid_value: dict[str, object]
) -> None:
    schedule = make_schedule()
    manifest = make_manifest(schedule, statuses=(EventStatus.SUCCEEDED,) * schedule.count)
    payload = json.loads(json.dumps(manifest.to_payload()))
    payload[field_name] = invalid_value

    with pytest.raises(ValueError, match=field_name):
        RunManifest.from_payload(payload, schedule=schedule)


def build_graph(
    schedule: FrozenSchedule,
    statuses: tuple[EventStatus, ...],
    *,
    source_at: dict[int, tuple[int, ...]] | None = None,
) -> tuple[
    RunManifest,
    tuple[GenerationEvent, ...],
    tuple[GenerationAttempt, ...],
    tuple[ExposureRecord, ...],
]:
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 17, "launch-a")
    source_at = source_at or {}
    events: list[GenerationEvent] = []
    attempts: list[GenerationAttempt] = []
    exposures: list[ExposureRecord] = []
    for ordinal, status in enumerate(statuses):
        slot = schedule.slots[ordinal]
        event = make_event(run_id, slot, status=status)
        sources = source_at.get(ordinal, ())
        exposures.append(
            make_exposure(
                event_ordinal=ordinal,
                receiver_agent_id=slot.agent_id,
                source_agent_ids=tuple(schedule.slots[source].agent_id for source in sources),
                source_event_ids=tuple(derive_event_id(run_id, source) for source in sources),
            )
        )
        attempts.append(
            make_attempt(
                event.event_id,
                event.exposure_id,
                status=status,
            )
        )
        events.append(event)
    recovery = None
    if statuses and not all(status is EventStatus.SUCCEEDED for status in statuses):
        next_ordinal = next(
            index for index, status in enumerate(statuses) if status is not EventStatus.SUCCEEDED
        )
        recovery = {
            "next_event_ordinal": next_ordinal,
            "event_id": derive_event_id(run_id, next_ordinal),
        }
    manifest = make_manifest(schedule, statuses=statuses, recovery_cursor=recovery)
    return manifest, tuple(events), tuple(attempts), tuple(exposures)


def test_evidence_graph_accepts_same_sweep_earlier_source_and_succeeded_prefix() -> None:
    schedule = make_schedule()
    manifest, events, attempts, exposures = build_graph(
        schedule, (EventStatus.SUCCEEDED,) * schedule.count
    )
    updates_and_posts = tuple(
        source_post(
            agent_id=events[index].agent_id,
            event_id=events[index].event_id,
            event_ordinal=events[index].event_ordinal,
        )
        for index in (0, 2)
    )
    records = list(exposures)
    records[1] = make_exposure(
        event_ordinal=1,
        receiver_agent_id=events[1].agent_id,
        source_posts=(updates_and_posts[0][1],),
    )
    records[3] = make_exposure(
        event_ordinal=3,
        receiver_agent_id=events[3].agent_id,
        source_posts=(updates_and_posts[1][1],),
    )
    validate_evidence_graph(
        manifest,
        events,
        attempts,
        tuple(records),
        public_posts_by_id={post.post_id: post for _, post in updates_and_posts},
        private_updates_by_id={update.update_id: update for update, _ in updates_and_posts},
        topic_package=topic(),
    )


def test_evidence_graph_rejects_future_source_without_previous_round_rule() -> None:
    schedule = make_schedule()
    manifest, events, attempts, exposures = build_graph(
        schedule, (EventStatus.SUCCEEDED,) * schedule.count
    )
    update, post = source_post(
        agent_id=events[3].agent_id,
        event_id=events[3].event_id,
        event_ordinal=events[3].event_ordinal,
    )
    tampered = list(exposures)
    tampered[1] = make_exposure(
        event_ordinal=1,
        receiver_agent_id=schedule.slots[1].agent_id,
        source_posts=(post,),
    )

    with pytest.raises(ValueError, match="earlier|future"):
        validate_evidence_graph(
            manifest,
            events,
            attempts,
            tuple(tampered),
            public_posts_by_id={post.post_id: post},
            private_updates_by_id={update.update_id: update},
            topic_package=topic(),
        )


def test_evidence_graph_rejects_exposure_seed_drift() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    manifest, events, attempts, exposures = build_graph(schedule, (EventStatus.SUCCEEDED,))
    forged = make_exposure(
        event_ordinal=0,
        receiver_agent_id=events[0].agent_id,
        matched_seed=18,
    )
    with pytest.raises(ValueError, match="exposure.*seed|seed.*manifest"):
        validate_evidence_graph(manifest, events, attempts, (forged,))


def test_evidence_graph_round0_source_requires_trusted_post_update_maps() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    manifest, events, attempts, _ = build_graph(schedule, (EventStatus.SUCCEEDED,))
    update, post = source_post(agent_id="agent-round0", event_id=None, event_ordinal=None)
    round0 = make_exposure(
        event_ordinal=0,
        receiver_agent_id=events[0].agent_id,
        source_posts=(post,),
    )
    with pytest.raises(ValueError, match="round-0.*trusted|trusted.*round-0"):
        validate_evidence_graph(manifest, events, attempts, (round0,))

    validate_evidence_graph(
        manifest,
        events,
        attempts,
        (round0,),
        public_posts_by_id={post.post_id: post},
        private_updates_by_id={update.update_id: update},
        topic_package=topic(),
    )

    payload = round0.to_payload()
    payload["round0_rng_hash"] = None
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match="round-0.*RNG|RNG.*round-0"):
        ExposureRecord.from_payload(payload)


def test_evidence_graph_requires_trusted_sources_for_selected_and_expired_round0() -> None:
    schedule = make_schedule(population_size=2, sweep_count=1)
    manifest, events, attempts, exposures = build_graph(
        schedule, (EventStatus.SUCCEEDED, EventStatus.SUCCEEDED)
    )
    _, event_post = source_post(
        agent_id=events[0].agent_id,
        event_id=events[0].event_id,
        event_ordinal=events[0].event_ordinal,
    )
    selected = list(exposures)
    selected[1] = make_exposure(
        event_ordinal=1,
        receiver_agent_id=events[1].agent_id,
        source_posts=(event_post,),
    )
    with pytest.raises(ValueError, match="trusted.*source|source.*trusted"):
        validate_evidence_graph(manifest, events, attempts, tuple(selected))

    _, round0_post = source_post(agent_id="agent-round0", event_id=None, event_ordinal=None)
    expired = list(exposures)
    expired[0] = make_exposure(
        event_ordinal=0,
        receiver_agent_id=events[0].agent_id,
        expired_round0_posts=(round0_post,),
    )
    with pytest.raises(ValueError, match="trusted.*source|source.*trusted"):
        validate_evidence_graph(manifest, events, attempts, tuple(expired))


def test_evidence_graph_rejects_cross_seed_event_drift_and_fake_typed_sources() -> None:
    schedule = make_schedule(population_size=2, sweep_count=1)
    manifest, events, attempts, exposures = build_graph(
        schedule, (EventStatus.SUCCEEDED, EventStatus.SUCCEEDED)
    )
    for seed, ordinal, match in (
        (18, events[0].event_ordinal, "seed"),
        (17, events[0].event_ordinal + 99, "ordinal"),
    ):
        update, post = source_post(
            agent_id=events[0].agent_id,
            event_id=events[0].event_id,
            event_ordinal=ordinal,
            seed=seed,
        )
        records = list(exposures)
        records[1] = make_exposure(
            event_ordinal=1,
            receiver_agent_id=events[1].agent_id,
            source_posts=(post,),
        )
        with pytest.raises(ValueError, match=match):
            validate_evidence_graph(
                manifest,
                events,
                attempts,
                tuple(records),
                public_posts_by_id={post.post_id: post},
                private_updates_by_id={update.update_id: update},
                topic_package=topic(),
            )

    good_update, good_post = source_post(
        agent_id=events[0].agent_id,
        event_id=events[0].event_id,
        event_ordinal=events[0].event_ordinal,
    )
    records = list(exposures)
    records[1] = make_exposure(
        event_ordinal=1,
        receiver_agent_id=events[1].agent_id,
        source_posts=(good_post,),
    )
    fake_post = SimpleNamespace(**good_post.to_payload())
    fake_update = SimpleNamespace(**good_update.to_payload())
    with pytest.raises(TypeError, match="PublicPost|PrivateUpdate|typed"):
        validate_evidence_graph(
            manifest,
            events,
            attempts,
            tuple(records),
            public_posts_by_id={good_post.post_id: fake_post},
            private_updates_by_id={good_update.update_id: fake_update},
            topic_package=topic(),
        )


def test_evidence_graph_source_update_must_bind_final_successful_attempt() -> None:
    schedule = make_schedule(population_size=2, sweep_count=1)
    manifest, events, _, exposures = build_graph(
        schedule, (EventStatus.SUCCEEDED, EventStatus.SUCCEEDED)
    )
    source_event = make_event(
        manifest.run_id, schedule.slots[0], status=EventStatus.SUCCEEDED, attempt_count=2
    )
    receiver_event = events[1]
    failed = make_attempt(
        source_event.event_id,
        source_event.exposure_id,
        attempt_index=1,
        status=EventStatus.FAILED,
    )
    succeeded = make_attempt(
        source_event.event_id,
        source_event.exposure_id,
        attempt_index=2,
        status=EventStatus.SUCCEEDED,
    )
    update, post = source_post(
        agent_id=source_event.agent_id,
        event_id=source_event.event_id,
        event_ordinal=source_event.event_ordinal,
    )
    records = list(exposures)
    records[1] = make_exposure(
        event_ordinal=1,
        receiver_agent_id=receiver_event.agent_id,
        source_posts=(post,),
    )
    receiver_attempt = make_attempt(receiver_event.event_id, receiver_event.exposure_id)
    with pytest.raises(ValueError, match="final|successful.*attempt|attempt.*succeeded"):
        validate_evidence_graph(
            manifest,
            (source_event, receiver_event),
            (failed, succeeded, receiver_attempt),
            tuple(records),
            public_posts_by_id={post.post_id: post},
            private_updates_by_id={update.update_id: update},
            topic_package=topic(),
        )


def test_expired_round0_candidate_hash_rejects_same_id_content_replacement() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    manifest, events, attempts, exposures = build_graph(schedule, (EventStatus.SUCCEEDED,))
    original_update, original_post = source_post(
        agent_id="agent-round0", event_id=None, event_ordinal=None
    )
    replacement_update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-round0",
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label="label-1",
        reason="replacement content",
        confidence=None,
        published=True,
        source_attempt_id=None,
        mock_only=True,
    )
    replacement_post = PublicPost.from_private_update(replacement_update, mock_only=True)
    assert replacement_post.post_id == original_post.post_id
    assert replacement_post.record_hash != original_post.record_hash
    records = list(exposures)
    records[0] = make_exposure(
        event_ordinal=0,
        receiver_agent_id=events[0].agent_id,
        expired_round0_posts=(original_post,),
    )
    with pytest.raises(ValueError, match="candidate.*hash|hash.*candidate"):
        validate_evidence_graph(
            manifest,
            events,
            attempts,
            tuple(records),
            public_posts_by_id={replacement_post.post_id: replacement_post},
            private_updates_by_id={replacement_update.update_id: replacement_update},
            topic_package=topic(),
        )


def test_exposure_candidate_hashes_reject_missing_wrong_order_hash_and_bool() -> None:
    first_update, first_post = source_post(agent_id="agent-a", event_id="event-a", event_ordinal=1)
    second_update, second_post = source_post(
        agent_id="agent-b", event_id="event-b", event_ordinal=2
    )
    assert first_update.update_id != second_update.update_id
    record = make_exposure(
        event_ordinal=3,
        receiver_agent_id="agent-r",
        source_posts=(first_post, second_post),
    )
    missing = record.to_payload()
    missing.pop("candidate_post_hashes")
    with pytest.raises(ValueError, match="fields"):
        ExposureRecord.from_payload(missing)

    for values in (
        list(reversed(record.candidate_post_hashes)),
        ["f" * 64, record.candidate_post_hashes[1]],
        [True, record.candidate_post_hashes[1]],
    ):
        payload = record.to_payload()
        payload["candidate_post_hashes"] = values
        payload["record_hash"] = canonical_payload_hash(
            {name: value for name, value in payload.items() if name != "record_hash"}
        )
        with pytest.raises((TypeError, ValueError), match="candidate|hash"):
            ExposureRecord.from_payload(payload)


def test_expired_event_candidate_requires_typed_exact_seeded_source() -> None:
    schedule = make_schedule(population_size=3, sweep_count=2)
    manifest, events, attempts, exposures = build_graph(schedule, (EventStatus.SUCCEEDED,) * 6)
    expired_update, expired_post = source_post(
        agent_id=events[2].agent_id,
        event_id=events[2].event_id,
        event_ordinal=events[2].event_ordinal,
    )
    selected_update, selected_post = source_post(
        agent_id=events[3].agent_id,
        event_id=events[3].event_id,
        event_ordinal=events[3].event_ordinal,
    )
    records = list(exposures)
    records[5] = make_exposure(
        event_ordinal=5,
        receiver_agent_id=events[5].agent_id,
        source_posts=(selected_post,),
        expired_event_posts=(expired_post,),
    )
    base_posts = {selected_post.post_id: selected_post}
    base_updates = {selected_update.update_id: selected_update}
    with pytest.raises((TypeError, ValueError), match="candidate|trusted|source"):
        validate_evidence_graph(
            manifest,
            events,
            attempts,
            tuple(records),
            public_posts_by_id=base_posts,
            private_updates_by_id=base_updates,
            topic_package=topic(),
        )

    for seed, reason in ((17, "replacement"), (18, "cross seed")):
        replacement_update = PrivateUpdate.create(
            topic_package=topic(),
            matched_seed=seed,
            agent_id=events[2].agent_id,
            event_id=events[2].event_id,
            event_ordinal=events[2].event_ordinal,
            sequence_index=1,
            stance_label="label-1",
            reason=reason,
            confidence=3,
            published=True,
            source_attempt_id=events[2].attempt_ids[-1],
            mock_only=True,
        )
        replacement_post = PublicPost.from_private_update(replacement_update, mock_only=True)
        with pytest.raises(ValueError, match="candidate|hash|seed"):
            validate_evidence_graph(
                manifest,
                events,
                attempts,
                tuple(records),
                public_posts_by_id={**base_posts, expired_post.post_id: replacement_post},
                private_updates_by_id={
                    **base_updates,
                    replacement_update.update_id: replacement_update,
                },
                topic_package=topic(),
            )


def test_expired_event_candidate_rejects_failed_source_attempt() -> None:
    schedule = make_schedule(population_size=3, sweep_count=2)
    manifest, events, _, exposures = build_graph(schedule, (EventStatus.SUCCEEDED,) * 6)
    source_event = make_event(manifest.run_id, schedule.slots[2], attempt_count=2)
    events = events[:2] + (source_event,) + events[3:]
    failed = make_attempt(
        source_event.event_id, source_event.exposure_id, attempt_index=1, status=EventStatus.FAILED
    )
    succeeded = make_attempt(source_event.event_id, source_event.exposure_id, attempt_index=2)
    other_attempts = tuple(
        make_attempt(event.event_id, event.exposure_id)
        for index, event in enumerate(events)
        if index != 2
    )
    expired_update, expired_post = source_post(
        agent_id=source_event.agent_id,
        event_id=source_event.event_id,
        event_ordinal=source_event.event_ordinal,
    )
    selected_update, selected_post = source_post(
        agent_id=events[3].agent_id,
        event_id=events[3].event_id,
        event_ordinal=events[3].event_ordinal,
    )
    records = list(exposures)
    records[5] = make_exposure(
        event_ordinal=5,
        receiver_agent_id=events[5].agent_id,
        source_posts=(selected_post,),
        expired_event_posts=(expired_post,),
    )
    with pytest.raises(ValueError, match="attempt|successful"):
        validate_evidence_graph(
            manifest,
            events,
            (failed, succeeded) + other_attempts,
            tuple(records),
            public_posts_by_id={
                expired_post.post_id: expired_post,
                selected_post.post_id: selected_post,
            },
            private_updates_by_id={
                expired_update.update_id: expired_update,
                selected_update.update_id: selected_update,
            },
            topic_package=topic(),
        )


def test_evidence_graph_rebuilds_exact_round0_candidate_classification() -> None:
    schedule = make_schedule(population_size=1, sweep_count=1)
    manifest, events, attempts, exposures = build_graph(schedule, (EventStatus.SUCCEEDED,))
    update, post = source_post(agent_id="agent-round0", event_id=None, event_ordinal=None)
    valid = make_exposure(
        event_ordinal=0,
        receiver_agent_id=events[0].agent_id,
        expired_round0_posts=(post,),
    )
    payload = valid.to_payload()
    payload["round0_candidate_post_ids"] = []
    payload["round0_rng_hash"] = None
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    hidden_round0 = ExposureRecord.from_payload(payload)
    with pytest.raises(ValueError, match="round-0.*candidate|candidate.*round-0"):
        validate_evidence_graph(
            manifest,
            events,
            attempts,
            (hidden_round0,),
            public_posts_by_id={post.post_id: post},
            private_updates_by_id={update.update_id: update},
            topic_package=topic(),
        )


def test_expired_event_candidate_rejects_receiver_as_source() -> None:
    schedule = make_schedule(population_size=3, sweep_count=2)
    manifest, events, attempts, exposures = build_graph(schedule, (EventStatus.SUCCEEDED,) * 6)
    assert events[0].agent_id == events[5].agent_id
    expired_update, expired_post = source_post(
        agent_id=events[0].agent_id,
        event_id=events[0].event_id,
        event_ordinal=events[0].event_ordinal,
    )
    selected_update, selected_post = source_post(
        agent_id=events[3].agent_id,
        event_id=events[3].event_id,
        event_ordinal=events[3].event_ordinal,
    )
    records = list(exposures)
    records[5] = make_exposure(
        event_ordinal=5,
        receiver_agent_id=events[5].agent_id,
        source_posts=(selected_post,),
        expired_event_posts=(expired_post,),
    )
    with pytest.raises(ValueError, match="receiver|self"):
        validate_evidence_graph(
            manifest,
            events,
            attempts,
            tuple(records),
            public_posts_by_id={
                expired_post.post_id: expired_post,
                selected_post.post_id: selected_post,
            },
            private_updates_by_id={
                expired_update.update_id: expired_update,
                selected_update.update_id: selected_update,
            },
            topic_package=topic(),
        )

    event_update, event_post = source_post(
        agent_id=events[0].agent_id,
        event_id=events[0].event_id,
        event_ordinal=events[0].event_ordinal,
    )
    mislabeled = make_exposure(
        event_ordinal=1,
        receiver_agent_id=events[1].agent_id,
        expired_round0_posts=(event_post,),
    )
    with pytest.raises(ValueError, match="round-0|earlier"):
        validate_evidence_graph(
            manifest,
            events,
            attempts,
            (exposures[0], mislabeled),
            public_posts_by_id={event_post.post_id: event_post},
            private_updates_by_id={event_update.update_id: event_update},
            topic_package=topic(),
        )


def test_evidence_graph_rejects_ordinal_gap_forged_id_and_schedule_drift() -> None:
    schedule = make_schedule()
    manifest, events, attempts, exposures = build_graph(
        schedule, (EventStatus.SUCCEEDED,) * schedule.count
    )

    with pytest.raises(ValueError, match="ordinal|prefix"):
        validate_evidence_graph(manifest, events[1:], attempts[1:], exposures[1:])

    forged = list(events)
    forged[1] = GenerationEvent(
        **{
            **events[1].to_payload(),
            "agent_id": "agent-forged",
            "status": EventStatus.SUCCEEDED,
            "attempt_ids": events[1].attempt_ids,
        }
    )
    with pytest.raises(ValueError, match="schedule"):
        validate_evidence_graph(manifest, tuple(forged), attempts, exposures)


def test_manifest_rejects_events_after_first_failed_event() -> None:
    schedule = make_schedule()
    statuses = (
        EventStatus.SUCCEEDED,
        EventStatus.FAILED,
        EventStatus.SUCCEEDED,
    )
    run_spec = make_run_spec(schedule)
    run_id = derive_run_id(run_spec, 17, "launch-a")
    with pytest.raises(ValueError, match="failed|prefix|after"):
        make_manifest(
            schedule,
            statuses=statuses,
            recovery_cursor={
                "next_event_ordinal": 1,
                "event_id": derive_event_id(run_id, 1),
            },
        )


def test_public_api_exports_only_v2_domain_and_artifact_rng_boundaries() -> None:
    expected = {
        "ArtifactEnvelope",
        "EventStatus",
        "ExposureSelection",
        "FeedCandidate",
        "FeedCursor",
        "ExposureRecord",
        "FrozenSchedule",
        "GenerationAttempt",
        "GenerationEvent",
        "LatestPublicPointer",
        "MemoryItem",
        "MemoryView",
        "PrivateState",
        "PrivateUpdate",
        "PublicPost",
        "RNGProvenance",
        "RunManifest",
        "ScheduleSlot",
        "TRSIntegerization",
        "TopicPackage",
        "assign_initial_reasons",
        "assign_initial_stances",
        "build_agent_node_mapping",
        "build_activation_schedule",
        "build_attention_artifact",
        "build_expression_artifact",
        "build_exposure_record",
        "build_memory_view",
        "build_population_artifact",
        "build_publish_schedule",
        "build_shadow_artifact",
        "build_structural_gate_artifact",
        "build_ws_artifact",
        "canonical_payload_hash",
        "canonical_protocol_hash",
        "derive_attempt_id",
        "derive_event_id",
        "derive_rng_seed",
        "derive_run_id",
        "evaluate_analysis_eligibility",
        "execution_projection",
        "load_protocol",
        "render_human_protocol_summary",
        "reconstruct_event_rng_provenance",
        "render_persona",
        "select_unread_feed",
        "trs_integerize",
        "update_human_protocol_summary",
        "validate_evidence_graph",
        "validate_exposure_record",
        "validate_exposure_selection",
        "validate_event_rng_ledger",
        "validate_human_protocol_reference",
        "validate_human_protocol_sync",
        "validate_matched_schedule_reuse",
        "validate_latest_public_pointer",
        "validate_memory_view",
        "validate_private_state",
        "validate_public_post",
        "validate_persona_factor_diff",
        "validate_shadow_artifact",
        "validate_structural_gate_artifact",
        "validate_ws_artifact",
        "validate_protocol",
    }

    assert set(agent_ex.__all__) == expected
    assert not hasattr(agent_ex, "AgentState")
    assert not hasattr(agent_ex, "OpinionRecord")
