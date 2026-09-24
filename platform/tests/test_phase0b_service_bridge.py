from __future__ import annotations

from copy import deepcopy

import pytest

from agent_ex.calibration.environment import (
    PackageEntry,
    PreliminaryEnvironmentInspection,
    WheelEntry,
)
from agent_ex.calibration.judge_runner import JudgeItemState, JudgeProjection
from agent_ex.domain import canonical_payload_hash
from agent_ex.phase0b.launch_intent import Phase0BLaunchIntent
from agent_ex.phase0b.service_bridge import Phase0BServiceBridge


SHA = "a" * 64
EMPTY_GPU_OBSERVATION_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
OLD_MANIFEST = "b" * 64
OLD_LOCK = "c" * 64
OLD_AUTH = "d" * 64
ARTIFACT_KEYS = (
    "topic",
    "population",
    "persona",
    "network",
    "shadow",
    "mapping",
    "attention",
    "expression",
    "activation",
    "publish",
    "schedule",
)
METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}


def _record(schema: str, **fields: object) -> dict[str, object]:
    content = {
        "schema_version": schema,
        **fields,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "metadata": dict(METADATA),
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def _fixture() -> dict[str, object]:
    service_config = {
        "serve_script": "/root/autodl-tmp/phase0a1-serve.sh",
        "control_python": "/root/autodl-tmp/vllm/bin/python",
        "executable": "/root/autodl-tmp/vllm/bin/python3.12",
        "model_path": "/root/autodl-tmp/models/qwen3-8b",
        "cmdline_sha256": SHA,
    }
    intent = Phase0BLaunchIntent.create(
        source_commit="e" * 40,
        source_bundle_hash=SHA,
        candidate_config_hash=SHA,
        artifact_hashes={key: SHA for key in ARTIFACT_KEYS},
        model_repository="Qwen/Qwen3-8B",
        model_revision="f" * 40,
        tokenizer_revision="1" * 40,
        environment_lock_hash=SHA,
        service_config_hash=canonical_payload_hash(service_config),
        preflight_archive_uri="/root/autodl-tmp/phase0b-preflight",
        full_run_archive_uri="/root/autodl-tmp/phase0b-full",
    )
    inspection = PreliminaryEnvironmentInspection.create(
        python_version="3.12.3",
        package_lock=(PackageEntry(name="vllm", version="0.23.0"),),
        wheel_entries=(
            WheelEntry(name="vllm", version="0.23.0", sha256=SHA, source="official-cuda-12.9"),
        ),
        torch_source="fresh-vllm-environment",
    )
    old_start = _record(
        "paper1.calibration.judge-service-start-identity.v1",
        authorization_hash=OLD_AUTH,
        pid=101,
        executable=service_config["executable"],
        cmdline_sha256=SHA,
        serve_script=service_config["serve_script"],
        control_python=service_config["control_python"],
        model_path=service_config["model_path"],
        proc_start_time=123,
        process_group_id=101,
        session_id=101,
    )
    states = {}
    for index in range(797):
        item_id = f"judge-{index:04d}"
        states[item_id] = JudgeItemState(
            item_id=item_id,
            item_hash=SHA,
            order_index=index,
            status="coded",
            attempt_count=1,
            attempt_ids=(f"attempt-{index:04d}",),
            unresolved_intent_hash=None,
            last_reconciliation_hash=None,
            completed_attempt_hash=SHA,
            resolution_hash=SHA,
            last_error=None,
        )
    projection = JudgeProjection.create(
        manifest_hash=OLD_MANIFEST,
        preflight_hash=SHA,
        service_start_identity_hash=old_start["record_hash"],
        sequence=2391,
        previous_projection_hash=SHA,
        item_order=tuple(states),
        item_states=states,
    )
    old_stop = _record(
        "paper1.calibration.judge-service-stop-evidence.v1",
        manifest_hash=OLD_MANIFEST,
        environment_lock_hash=OLD_LOCK,
        service_start_identity_hash=old_start["record_hash"],
        pid=101,
        process_exit_observed=True,
        loopback_listener_absent=True,
        gpu_compute_process_observation_hash=EMPTY_GPU_OBSERVATION_SHA,
    )
    new_content = {
        "schema_version": "paper1.calibration.service-start-identity.v1",
        "generation": "0001",
        "mode": "start-first",
        "manifest_hash": intent.record_hash,
        "binding_kind": "preliminary-inspection",
        "binding_hash": inspection.record_hash,
        "pid": 202,
        "executable": service_config["executable"],
        "cmdline_sha256": SHA,
        "proc_start_time": "456",
        "serve_script": service_config["serve_script"],
        "control_python": service_config["control_python"],
        "model_path": service_config["model_path"],
        "started_at": "2026-09-24T00:00:00Z",
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    new_start = {**new_content, "record_hash": canonical_payload_hash(new_content)}
    return {
        "intent": intent,
        "inspection": inspection,
        "judge_projection": projection.to_payload(),
        "judge_replay_verified_projection_hash": projection.record_hash,
        "old_start": old_start,
        "old_stop": old_stop,
        "new_start": new_start,
        "service_config": service_config,
        "old_manifest_hash": OLD_MANIFEST,
        "old_environment_lock_hash": OLD_LOCK,
    }


def _rehash(payload: dict[str, object]) -> None:
    payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in payload.items() if key != "record_hash"}
    )


def test_bridge_binds_terminal_judge_stop_to_fresh_preliminary_service() -> None:
    bridge = Phase0BServiceBridge.create(**_fixture())

    assert bridge.old_judge_terminal_count == 797
    assert bridge.new_service_start_identity_hash != bridge.old_service_start_identity_hash
    assert bridge.new_service_start_identity_hash == _fixture()["new_start"]["record_hash"]
    assert Phase0BServiceBridge.from_payload(bridge.to_payload()) == bridge


@pytest.mark.parametrize(
    "record,field,value",
    [
        ("new_start", "manifest_hash", SHA),
        ("new_start", "binding_hash", SHA),
        ("new_start", "binding_kind", "environment-lock"),
        ("new_start", "mode", "start-recovery"),
        ("new_start", "pid", 101),
        ("new_start", "cmdline_sha256", "e" * 64),
        ("old_stop", "loopback_listener_absent", False),
        ("old_stop", "environment_lock_hash", SHA),
        ("old_stop", "gpu_compute_process_observation_hash", SHA),
    ],
)
def test_bridge_rejects_identity_or_handoff_drift(record: str, field: str, value: object) -> None:
    inputs = _fixture()
    payload = deepcopy(inputs[record])
    payload[field] = value
    _rehash(payload)
    inputs[record] = payload
    with pytest.raises((TypeError, ValueError)):
        Phase0BServiceBridge.create(**inputs)


def test_bridge_requires_verified_full_judge_replay_and_all_coded() -> None:
    inputs = _fixture()
    inputs["judge_replay_verified_projection_hash"] = SHA
    with pytest.raises(ValueError, match="replay"):
        Phase0BServiceBridge.create(**inputs)

    inputs = _fixture()
    projection = deepcopy(inputs["judge_projection"])
    item = projection["item_states"][projection["item_order"][0]]
    item["unresolved_intent_hash"] = SHA
    _rehash(projection)
    inputs["judge_projection"] = projection
    inputs["judge_replay_verified_projection_hash"] = projection["record_hash"]
    with pytest.raises(ValueError, match="terminal|coded|unresolved"):
        Phase0BServiceBridge.create(**inputs)
