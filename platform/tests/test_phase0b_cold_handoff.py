"""Cold-poweroff evidence is not judge-service normal-stop evidence."""

from __future__ import annotations

from copy import deepcopy

import pytest

from agent_ex.calibration.judge_contracts import JudgeExecutionManifest
from agent_ex.calibration.judge_runner import JudgeProjection
from agent_ex.domain import canonical_payload_hash
from agent_ex.phase0b.cold_handoff import (
    ColdPoweroffObservation,
    verify_cold_poweroff_handoff,
)
from test_calibration_judge_store import _manifest
from test_phase0b_service_bridge import EMPTY_GPU_OBSERVATION_SHA, OLD_LOCK, _fixture


def _linked_inputs() -> dict[str, object]:
    inputs = _fixture()
    old_start = inputs["old_start"]
    manifest = _manifest(
        pack_hash="a" * 64,
        index_hash="a" * 64,
        renderer_hash="a" * 64,
        preflight_hash="a" * 64,
    ).to_payload()
    manifest["authorization_hash"] = old_start["authorization_hash"]
    manifest["environment_lock_hash"] = OLD_LOCK
    manifest["service_start_identity_hash"] = old_start["record_hash"]
    manifest["record_hash"] = canonical_payload_hash(
        {key: item for key, item in manifest.items() if key != "record_hash"}
    )
    manifest = JudgeExecutionManifest.from_payload(manifest)
    old_projection = JudgeProjection.from_payload(inputs["judge_projection"])
    projection = JudgeProjection.create(
        manifest_hash=manifest.record_hash,
        preflight_hash=old_projection.preflight_hash,
        service_start_identity_hash=old_start["record_hash"],
        sequence=old_projection.sequence,
        previous_projection_hash=old_projection.previous_projection_hash,
        item_order=old_projection.item_order,
        item_states=old_projection.item_states,
    )
    inputs["old_manifest"] = manifest.to_payload()
    inputs["old_manifest_hash"] = manifest.record_hash
    inputs["judge_projection"] = projection.to_payload()
    inputs["judge_replay_verified_projection_hash"] = projection.record_hash
    return inputs


def _observation(inputs: dict[str, object] | None = None) -> ColdPoweroffObservation:
    inputs = _linked_inputs() if inputs is None else inputs
    return ColdPoweroffObservation.create(
        instance_id="autodl-retained-instance-1",
        observed_boot_id="57347cd2-7491-4125-b65b-8c7fe86d908e",
        observed_at="2026-09-24T08:00:00Z",
        old_service_start_identity_hash=inputs["old_start"]["record_hash"],
        judge_terminal_projection_hash=inputs["judge_projection"]["record_hash"],
        old_manifest_hash=inputs["old_manifest_hash"],
        old_environment_lock_hash=OLD_LOCK,
        old_pid=inputs["old_start"]["pid"],
        process_absent=True,
        loopback_listener_absent=True,
        gpu_compute_process_observation_hash=EMPTY_GPU_OBSERVATION_SHA,
    )


def _verify(inputs: dict[str, object], observation: object) -> ColdPoweroffObservation:
    return verify_cold_poweroff_handoff(
        observation=observation,
        old_start=inputs["old_start"],
        old_manifest=inputs["old_manifest"],
        judge_projection=inputs["judge_projection"],
        replay_verified_projection_hash=inputs["judge_replay_verified_projection_hash"],
        old_manifest_hash=inputs["old_manifest_hash"],
        old_environment_lock_hash=inputs["old_environment_lock_hash"],
    )


def test_cold_observation_round_trip_is_distinct_from_normal_stop() -> None:
    observation = _observation()
    assert observation.schema_version == "paper1.phase0b.cold-poweroff-observation.v1"
    assert observation.schema_version != "paper1.calibration.judge-service-stop-evidence.v1"
    assert observation.calibration_only is True
    assert observation.formal_parameter_authority is False
    assert observation.research_parameter_status == "not_frozen"
    assert ColdPoweroffObservation.from_payload(observation.to_payload()) == observation


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("process_absent", False),
        ("loopback_listener_absent", False),
        ("gpu_compute_process_observation_hash", "a" * 64),
        ("old_pid", 0),
        ("observed_boot_id", "not-a-boot-id"),
        ("observed_at", "2026-09-24 08:00:00"),
        ("observed_at", "2026-99-99T08:00:00Z"),
        ("instance_id", ""),
        ("old_manifest_hash", "not-a-hash"),
    ],
)
def test_cold_observation_rejects_invalid_or_occupied_state(field: str, value: object) -> None:
    payload = _observation().to_payload()
    payload[field] = value
    payload["record_hash"] = canonical_payload_hash(
        {key: item for key, item in payload.items() if key != "record_hash"}
    )
    with pytest.raises((TypeError, ValueError)):
        ColdPoweroffObservation.from_payload(payload)


def test_cold_observation_rejects_extra_fields_and_tampering() -> None:
    payload = _observation().to_payload()
    payload["process_exit_observed"] = True
    with pytest.raises(ValueError, match="exact|fields"):
        ColdPoweroffObservation.from_payload(payload)

    payload = deepcopy(_observation().to_payload())
    payload["instance_id"] = "other-instance"
    with pytest.raises(ValueError, match="hash"):
        ColdPoweroffObservation.from_payload(payload)


def test_cold_handoff_verifies_same_terminal_judge_run() -> None:
    inputs = _linked_inputs()
    observation = _observation(inputs)
    assert _verify(inputs, observation) == observation


def test_cold_handoff_rejects_unrelated_old_start_even_if_observation_rehashed() -> None:
    inputs = _linked_inputs()
    old_start = deepcopy(inputs["old_start"])
    old_start["authorization_hash"] = "f" * 64
    old_start["record_hash"] = canonical_payload_hash(
        {key: item for key, item in old_start.items() if key != "record_hash"}
    )
    inputs["old_start"] = old_start
    observation = _observation(inputs)
    with pytest.raises(ValueError, match="authorization|identity|projection"):
        _verify(inputs, observation)


def test_cold_handoff_rejects_unverified_replay_or_manifest() -> None:
    inputs = _linked_inputs()
    inputs["judge_replay_verified_projection_hash"] = "e" * 64
    with pytest.raises(ValueError, match="replay"):
        _verify(inputs, _observation(inputs))

    inputs = _linked_inputs()
    inputs["old_manifest_hash"] = "e" * 64
    with pytest.raises(ValueError, match="manifest"):
        _verify(inputs, _observation(inputs))


def test_cold_handoff_rejects_normal_stop_or_unresolved_dispatch() -> None:
    inputs = _linked_inputs()
    with pytest.raises((TypeError, ValueError)):
        _verify(inputs, inputs["old_stop"])

    projection = deepcopy(inputs["judge_projection"])
    first_item = projection["item_order"][0]
    projection["item_states"][first_item]["unresolved_intent_hash"] = "a" * 64
    projection["record_hash"] = canonical_payload_hash(
        {key: item for key, item in projection.items() if key != "record_hash"}
    )
    inputs["judge_projection"] = projection
    inputs["judge_replay_verified_projection_hash"] = projection["record_hash"]
    with pytest.raises(ValueError, match="terminal|unresolved|coded"):
        _verify(inputs, _observation(inputs))


def test_cold_handoff_rejects_manifest_authorization_or_lock_drift() -> None:
    for field in ("authorization_hash", "environment_lock_hash"):
        inputs = _linked_inputs()
        manifest = deepcopy(inputs["old_manifest"])
        manifest[field] = "e" * 64
        manifest["record_hash"] = canonical_payload_hash(
            {key: item for key, item in manifest.items() if key != "record_hash"}
        )
        inputs["old_manifest"] = manifest
        with pytest.raises(ValueError, match="authorization|lock|manifest"):
            _verify(inputs, _observation(inputs))


def test_cold_handoff_rejects_797_positions_with_duplicate_item_id() -> None:
    inputs = _linked_inputs()
    projection = deepcopy(inputs["judge_projection"])
    dropped_id = projection["item_order"][-1]
    projection["item_order"][-1] = projection["item_order"][0]
    del projection["item_states"][dropped_id]
    projection["record_hash"] = canonical_payload_hash(
        {key: item for key, item in projection.items() if key != "record_hash"}
    )
    inputs["judge_projection"] = projection
    inputs["judge_replay_verified_projection_hash"] = projection["record_hash"]
    with pytest.raises(ValueError, match="797|unique|terminal"):
        _verify(inputs, _observation(inputs))
