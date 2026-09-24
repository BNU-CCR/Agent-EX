"""Metadata-only handoff proof from the completed judge to a fresh Phase 0B service.

This record does not prove the journal replay by itself: the caller must perform
that independent replay and supply its verified terminal projection hash.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar, Mapping

from ..calibration.environment import PreliminaryEnvironmentInspection
from ..calibration.judge_runner import JudgeProjection
from ..domain import (
    _json_ready,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    canonical_payload_hash,
)
from .launch_intent import Phase0BLaunchIntent


_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_EMPTY_GPU_OBSERVATION_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_SERVICE_CONFIG_PATHS = {"serve_script", "control_python", "executable", "model_path"}
_SERVICE_CONFIG_FIELDS = _SERVICE_CONFIG_PATHS | {"cmdline_sha256"}
_JUDGE_START_FIELDS = {
    "schema_version",
    "authorization_hash",
    "pid",
    "executable",
    "cmdline_sha256",
    "serve_script",
    "control_python",
    "model_path",
    "proc_start_time",
    "process_group_id",
    "session_id",
    "calibration_only",
    "formal_parameter_authority",
    "metadata",
    "record_hash",
}
_JUDGE_STOP_FIELDS = {
    "schema_version",
    "manifest_hash",
    "environment_lock_hash",
    "service_start_identity_hash",
    "pid",
    "process_exit_observed",
    "loopback_listener_absent",
    "gpu_compute_process_observation_hash",
    "calibration_only",
    "formal_parameter_authority",
    "metadata",
    "record_hash",
}
_SERVICE_START_FIELDS = {
    "schema_version",
    "generation",
    "mode",
    "manifest_hash",
    "binding_kind",
    "binding_hash",
    "pid",
    "executable",
    "cmdline_sha256",
    "proc_start_time",
    "serve_script",
    "control_python",
    "model_path",
    "started_at",
    "calibration_only",
    "formal_parameter_authority",
    "record_hash",
}


def _verified_record(
    name: str,
    payload: Mapping[str, object],
    fields: set[str],
    schema: str,
    *,
    judge_metadata: bool,
) -> dict[str, object]:
    if type(payload) is not dict or set(payload) != fields:
        raise ValueError(f"{name} must contain exact evidence fields")
    _require_json_transport(payload, name)
    if payload["schema_version"] != schema:
        raise ValueError(f"{name} schema differs")
    if (
        payload["calibration_only"] is not True
        or payload["formal_parameter_authority"] is not False
    ):
        raise ValueError(f"{name} must remain preliminary")
    if judge_metadata and payload["metadata"] != _METADATA:
        raise ValueError(f"{name} metadata differs")
    digest = payload["record_hash"]
    _require_sha256(f"{name} record_hash", digest)
    _require_payload_hash(
        f"{name} record_hash",
        digest,
        {key: value for key, value in payload.items() if key != "record_hash"},
    )
    return dict(payload)


def _positive_int(name: str, value: object) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _absolute_path(name: str, value: object) -> None:
    if (
        type(value) is not str
        or not value.startswith("/")
        or value == "/"
        or ".." in value.split("/")
    ):
        raise ValueError(f"{name} must be a canonical absolute path")


@dataclass(frozen=True, slots=True)
class Phase0BServiceBridge:
    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    launch_intent_hash: str
    inspection_hash: str
    judge_terminal_projection_hash: str
    judge_replay_verified_projection_hash: str
    old_judge_manifest_hash: str
    old_judge_environment_lock_hash: str
    old_judge_terminal_count: int
    old_service_start_identity_hash: str
    old_service_stop_evidence_hash: str
    new_service_start_identity_hash: str
    service_config_hash: str
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.service-bridge.v1"

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA:
            raise ValueError("bridge schema differs")
        if (
            self.calibration_only is not True
            or self.formal_parameter_authority is not False
            or self.research_parameter_status != "not_frozen"
        ):
            raise ValueError("bridge must remain preliminary and not frozen")
        for field in fields(self):
            if field.name.endswith("_hash") and field.name != "record_hash":
                _require_sha256(field.name, getattr(self, field.name))
        if self.old_judge_terminal_count != 797 or type(self.old_judge_terminal_count) is not int:
            raise ValueError("bridge requires exactly 797 terminal judge items")
        if self.judge_terminal_projection_hash != self.judge_replay_verified_projection_hash:
            raise ValueError("judge replay must verify the same terminal projection")
        if self.old_service_start_identity_hash == self.new_service_start_identity_hash:
            raise ValueError("new service must have its own start identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "record_hash"
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Phase0BServiceBridge:
        if type(payload) is not dict or set(payload) != {field.name for field in fields(cls)}:
            raise ValueError("service bridge requires exact fields")
        _require_json_transport(payload, "service bridge")
        return cls(**payload)  # type: ignore[arg-type]

    @classmethod
    def create(
        cls,
        *,
        intent: Phase0BLaunchIntent,
        inspection: PreliminaryEnvironmentInspection,
        judge_projection: Mapping[str, object],
        judge_replay_verified_projection_hash: str,
        old_start: Mapping[str, object],
        old_stop: Mapping[str, object],
        new_start: Mapping[str, object],
        service_config: Mapping[str, object],
        old_manifest_hash: str,
        old_environment_lock_hash: str,
    ) -> Phase0BServiceBridge:
        if not isinstance(intent, Phase0BLaunchIntent) or not isinstance(
            inspection, PreliminaryEnvironmentInspection
        ):
            raise TypeError("bridge requires typed intent and fresh inspection")
        if type(service_config) is not dict or set(service_config) != _SERVICE_CONFIG_FIELDS:
            raise ValueError("service config must contain exact fields")
        _require_json_transport(service_config, "service config")
        for key in _SERVICE_CONFIG_PATHS:
            _absolute_path(f"service config {key}", service_config[key])
        _require_sha256("service config cmdline_sha256", service_config["cmdline_sha256"])
        if canonical_payload_hash(service_config) != intent.service_config_hash:
            raise ValueError("service config hash differs from launch intent")
        _require_sha256("old_manifest_hash", old_manifest_hash)
        _require_sha256("old_environment_lock_hash", old_environment_lock_hash)
        _require_sha256(
            "judge_replay_verified_projection_hash", judge_replay_verified_projection_hash
        )

        projection = JudgeProjection.from_payload(judge_projection)
        if projection.record_hash != judge_replay_verified_projection_hash:
            raise ValueError("judge replay hash differs from terminal projection")
        if projection.manifest_hash != old_manifest_hash:
            raise ValueError("judge projection manifest differs")
        if len(projection.item_order) != 797 or any(
            state.status != "coded"
            or state.unresolved_intent_hash is not None
            or state.completed_attempt_hash is None
            or state.resolution_hash is None
            for state in projection.item_states.values()
        ):
            raise ValueError(
                "judge projection is not 797 coded terminal items with zero unresolved intents"
            )

        old_start = _verified_record(
            "old judge start",
            old_start,
            _JUDGE_START_FIELDS,
            "paper1.calibration.judge-service-start-identity.v1",
            judge_metadata=True,
        )
        old_stop = _verified_record(
            "old judge stop",
            old_stop,
            _JUDGE_STOP_FIELDS,
            "paper1.calibration.judge-service-stop-evidence.v1",
            judge_metadata=True,
        )
        new_start = _verified_record(
            "new service start",
            new_start,
            _SERVICE_START_FIELDS,
            "paper1.calibration.service-start-identity.v1",
            judge_metadata=False,
        )
        for name, value in (
            ("old authorization hash", old_start["authorization_hash"]),
            ("old cmdline hash", old_start["cmdline_sha256"]),
            ("new cmdline hash", new_start["cmdline_sha256"]),
            ("GPU stop observation hash", old_stop["gpu_compute_process_observation_hash"]),
        ):
            _require_sha256(name, value)
        for name, value in (
            ("old PID", old_start["pid"]),
            ("old process start time", old_start["proc_start_time"]),
            ("old process group", old_start["process_group_id"]),
            ("old session", old_start["session_id"]),
            ("new PID", new_start["pid"]),
        ):
            _positive_int(name, value)
        if projection.service_start_identity_hash != old_start["record_hash"]:
            raise ValueError("judge projection differs from old service identity")
        if (
            old_stop["manifest_hash"] != old_manifest_hash
            or old_stop["environment_lock_hash"] != old_environment_lock_hash
            or old_stop["service_start_identity_hash"] != old_start["record_hash"]
            or old_stop["pid"] != old_start["pid"]
            or old_stop["process_exit_observed"] is not True
            or old_stop["loopback_listener_absent"] is not True
            or old_stop["gpu_compute_process_observation_hash"] != _EMPTY_GPU_OBSERVATION_SHA256
        ):
            raise ValueError("judge stop evidence does not safely close the old service")
        if (
            new_start["generation"] != "0001"
            or new_start["mode"] != "start-first"
            or new_start["manifest_hash"] != intent.service_manifest_hash
            or new_start["binding_kind"] != "preliminary-inspection"
            or new_start["binding_hash"] != inspection.record_hash
            or new_start["pid"] == old_start["pid"]
            or new_start["record_hash"] == old_start["record_hash"]
        ):
            raise ValueError("new service start does not bind the fresh intent and inspection")
        for key in _SERVICE_CONFIG_FIELDS:
            if new_start[key] != service_config[key]:
                raise ValueError(f"new service {key} differs from pinned service config")
        if (
            type(new_start["proc_start_time"]) is not str
            or not new_start["proc_start_time"].isdigit()
            or int(new_start["proc_start_time"]) <= 0
        ):
            raise ValueError("new process start time must be a proc tick string")
        if type(new_start["started_at"]) is not str or not new_start["started_at"].endswith("Z"):
            raise ValueError("new service start time must be UTC")

        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "launch_intent_hash": intent.record_hash,
            "inspection_hash": inspection.record_hash,
            "judge_terminal_projection_hash": projection.record_hash,
            "judge_replay_verified_projection_hash": judge_replay_verified_projection_hash,
            "old_judge_manifest_hash": old_manifest_hash,
            "old_judge_environment_lock_hash": old_environment_lock_hash,
            "old_judge_terminal_count": len(projection.item_order),
            "old_service_start_identity_hash": old_start["record_hash"],
            "old_service_stop_evidence_hash": old_stop["record_hash"],
            "new_service_start_identity_hash": new_start["record_hash"],
            "service_config_hash": intent.service_config_hash,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]
