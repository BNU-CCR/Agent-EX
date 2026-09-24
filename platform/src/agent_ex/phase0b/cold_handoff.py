"""Metadata-only observation of an old judge service absent after instance restart.

This contract validates a supplied observation; it does not observe a host or
prove when or how the previous process ended. It is never normal-stop evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
import re
from typing import ClassVar, Mapping
from uuid import UUID

from ..calibration.judge_contracts import JudgeExecutionManifest
from ..calibration.judge_runner import JudgeProjection
from ..domain import (
    _json_ready,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    canonical_payload_hash,
)
from .service_bridge import _JUDGE_START_FIELDS, _positive_int, _verified_record


_INSTANCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")
_UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_EMPTY_GPU_OBSERVATION_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@dataclass(frozen=True, slots=True)
class ColdPoweroffObservation:
    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    instance_id: str
    observed_boot_id: str
    observed_at: str
    old_service_start_identity_hash: str
    judge_terminal_projection_hash: str
    old_manifest_hash: str
    old_environment_lock_hash: str
    old_pid: int
    process_absent: bool
    loopback_listener_absent: bool
    gpu_compute_process_observation_hash: str
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.cold-poweroff-observation.v1"

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA:
            raise ValueError("cold observation schema differs")
        if (
            self.calibration_only is not True
            or self.formal_parameter_authority is not False
            or self.research_parameter_status != "not_frozen"
        ):
            raise ValueError("cold observation must remain preliminary and not frozen")
        if type(self.instance_id) is not str or _INSTANCE_ID.fullmatch(self.instance_id) is None:
            raise ValueError("instance_id must be a bounded host label")
        if type(self.observed_boot_id) is not str:
            raise ValueError("observed_boot_id must be a UUID")
        try:
            if str(UUID(self.observed_boot_id)) != self.observed_boot_id:
                raise ValueError("observed_boot_id must be a canonical UUID")
        except ValueError as exc:
            raise ValueError("observed_boot_id must be a canonical UUID") from exc
        if type(self.observed_at) is not str or _UTC_SECOND.fullmatch(self.observed_at) is None:
            raise ValueError("observed_at must be UTC to whole seconds")
        try:
            datetime.fromisoformat(self.observed_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError as exc:
            raise ValueError("observed_at must be a valid UTC timestamp") from exc
        for name in (
            "old_service_start_identity_hash",
            "judge_terminal_projection_hash",
            "old_manifest_hash",
            "old_environment_lock_hash",
            "gpu_compute_process_observation_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if type(self.old_pid) is not int or self.old_pid <= 0:
            raise ValueError("old_pid must be positive")
        if self.process_absent is not True or self.loopback_listener_absent is not True:
            raise ValueError("cold observation requires absent process and listener")
        if self.gpu_compute_process_observation_hash != _EMPTY_GPU_OBSERVATION_SHA256:
            raise ValueError("cold observation requires empty GPU compute-process evidence")
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
    def from_payload(cls, payload: Mapping[str, object]) -> ColdPoweroffObservation:
        if type(payload) is not dict or set(payload) != {field.name for field in fields(cls)}:
            raise ValueError("cold observation requires exact fields")
        _require_json_transport(payload, "cold observation")
        return cls(**payload)  # type: ignore[arg-type]

    @classmethod
    def create(
        cls,
        *,
        instance_id: str,
        observed_boot_id: str,
        observed_at: str,
        old_service_start_identity_hash: str,
        judge_terminal_projection_hash: str,
        old_manifest_hash: str,
        old_environment_lock_hash: str,
        old_pid: int,
        process_absent: bool,
        loopback_listener_absent: bool,
        gpu_compute_process_observation_hash: str,
    ) -> ColdPoweroffObservation:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "instance_id": instance_id,
            "observed_boot_id": observed_boot_id,
            "observed_at": observed_at,
            "old_service_start_identity_hash": old_service_start_identity_hash,
            "judge_terminal_projection_hash": judge_terminal_projection_hash,
            "old_manifest_hash": old_manifest_hash,
            "old_environment_lock_hash": old_environment_lock_hash,
            "old_pid": old_pid,
            "process_absent": process_absent,
            "loopback_listener_absent": loopback_listener_absent,
            "gpu_compute_process_observation_hash": gpu_compute_process_observation_hash,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]


def verify_cold_poweroff_handoff(
    *,
    observation: ColdPoweroffObservation,
    old_start: Mapping[str, object],
    old_manifest: Mapping[str, object],
    judge_projection: Mapping[str, object],
    replay_verified_projection_hash: str,
    old_manifest_hash: str,
    old_environment_lock_hash: str,
) -> ColdPoweroffObservation:
    """Bind a cold absence record to one independently replayed judge terminal run.

    The caller must obtain the observation from the retained host and independently
    replay its durable judge journal. No host observation is performed here.
    """

    if not isinstance(observation, ColdPoweroffObservation):
        raise TypeError("cold handoff requires a cold-poweroff observation")
    _require_sha256("replay_verified_projection_hash", replay_verified_projection_hash)
    _require_sha256("old_manifest_hash", old_manifest_hash)
    _require_sha256("old_environment_lock_hash", old_environment_lock_hash)
    old_start = _verified_record(
        "old judge start",
        old_start,
        _JUDGE_START_FIELDS,
        "paper1.calibration.judge-service-start-identity.v1",
        judge_metadata=True,
    )
    _require_sha256("old authorization hash", old_start["authorization_hash"])
    _positive_int("old PID", old_start["pid"])
    _positive_int("old process start time", old_start["proc_start_time"])
    _positive_int("old process group", old_start["process_group_id"])
    _positive_int("old session", old_start["session_id"])
    manifest = JudgeExecutionManifest.from_payload(old_manifest)
    if manifest.record_hash != old_manifest_hash:
        raise ValueError("old judge manifest hash differs")
    if manifest.authorization_hash != old_start["authorization_hash"]:
        raise ValueError("old judge manifest authorization differs from service start")
    if manifest.environment_lock_hash != old_environment_lock_hash:
        raise ValueError("old judge manifest environment lock differs")
    if manifest.service_start_identity_hash != old_start["record_hash"]:
        raise ValueError("old judge manifest service identity differs")
    projection = JudgeProjection.from_payload(judge_projection)
    if projection.record_hash != replay_verified_projection_hash:
        raise ValueError("judge replay hash differs from terminal projection")
    if projection.manifest_hash != manifest.record_hash:
        raise ValueError("judge projection manifest differs")
    if projection.preflight_hash != manifest.preflight_hash:
        raise ValueError("judge projection preflight differs from manifest")
    if projection.service_start_identity_hash != old_start["record_hash"]:
        raise ValueError("judge projection differs from old service identity")
    if (
        len(projection.item_order) != 797
        or len(projection.item_states) != 797
        or len(set(projection.item_order)) != 797
    ) or any(
        state.status != "coded"
        or state.unresolved_intent_hash is not None
        or state.completed_attempt_hash is None
        or state.resolution_hash is None
        for state in projection.item_states.values()
    ):
        raise ValueError("judge projection is not 797 coded terminal items")
    if (
        observation.old_service_start_identity_hash != old_start["record_hash"]
        or observation.judge_terminal_projection_hash != projection.record_hash
        or observation.old_manifest_hash != old_manifest_hash
        or observation.old_environment_lock_hash != old_environment_lock_hash
        or observation.old_pid != old_start["pid"]
    ):
        raise ValueError("cold observation differs from old judge identity chain")
    return observation
