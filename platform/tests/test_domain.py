from dataclasses import FrozenInstanceError, replace
import json

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


SHA_A = "a" * 64
SHA_B = "b" * 64
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
    source_event_ids: tuple[str, ...] = (),
) -> ExposureRecord:
    return ExposureRecord(
        exposure_id=f"exposure-{event_ordinal}",
        event_ordinal=event_ordinal,
        receiver_agent_id=receiver_agent_id,
        exposure_mode="ws_neighbors",
        source_agent_ids=source_agent_ids,
        source_event_ids=source_event_ids,
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
        schedule,
        (EventStatus.SUCCEEDED,) * schedule.count,
        source_at={1: (0,), 3: (1, 2)},
    )

    validate_evidence_graph(manifest, events, attempts, exposures)


def test_evidence_graph_rejects_future_source_without_previous_round_rule() -> None:
    schedule = make_schedule()
    manifest, events, attempts, exposures = build_graph(
        schedule,
        (EventStatus.SUCCEEDED,) * schedule.count,
        source_at={1: (0,)},
    )
    tampered = list(exposures)
    tampered[1] = make_exposure(
        event_ordinal=1,
        receiver_agent_id=schedule.slots[1].agent_id,
        source_agent_ids=(schedule.slots[3].agent_id,),
        source_event_ids=(events[3].event_id,),
    )

    with pytest.raises(ValueError, match="earlier|future"):
        validate_evidence_graph(manifest, events, attempts, tuple(tampered))


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
        "ExposureRecord",
        "FrozenSchedule",
        "GenerationAttempt",
        "GenerationEvent",
        "RNGProvenance",
        "RunManifest",
        "ScheduleSlot",
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
        "update_human_protocol_summary",
        "validate_evidence_graph",
        "validate_human_protocol_reference",
        "validate_human_protocol_sync",
        "validate_protocol",
    }

    assert set(agent_ex.__all__) == expected
    assert not hasattr(agent_ex, "AgentState")
    assert not hasattr(agent_ex, "OpinionRecord")
