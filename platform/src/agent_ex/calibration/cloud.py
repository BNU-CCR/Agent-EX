"""Strict, non-authoritative records for the Phase 0A-1 cloud gate."""

from __future__ import annotations

from dataclasses import dataclass, fields
import re
from typing import ClassVar, Mapping

from ..domain import (
    _json_ready,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
)


_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


def _require_exact_payload(
    payload: Mapping[str, object], *, expected: set[str], record_name: str
) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError(f"{record_name} payload must contain exact fields")
    _require_json_transport(payload, f"{record_name} payload")


def _require_gate_metadata(
    *,
    schema_version: object,
    expected_schema: str,
    calibration_only: object,
    formal_parameter_authority: object,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("schema_version is not supported")
    if type(calibration_only) is not bool or calibration_only is not True:
        raise ValueError("cloud record must remain calibration-only")
    if type(formal_parameter_authority) is not bool or formal_parameter_authority is not False:
        raise ValueError("cloud record must not grant formal parameter authority")


def _require_resolved(field_name: str, value: str) -> None:
    if "UNRESOLVED[" in value:
        raise ValueError(f"{field_name} must not contain UNRESOLVED markers")


@dataclass(frozen=True, slots=True)
class CloudPreflight:
    """A sanitized, read-only observation that grants no run authority."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    os_release: str
    kernel: str
    python_version: str
    gpu_name: str
    gpu_memory_bytes: int
    driver_version: str
    reported_cuda_version: str
    free_disk_bytes: int
    git_commit: str
    git_dirty: bool
    record_hash: str

    _SCHEMA_VERSION: ClassVar[str] = "paper1.calibration.cloud-preflight.v1"

    def __post_init__(self) -> None:
        _require_gate_metadata(
            schema_version=self.schema_version,
            expected_schema=self._SCHEMA_VERSION,
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
        )
        for name in (
            "os_release",
            "kernel",
            "python_version",
            "gpu_name",
            "driver_version",
            "reported_cuda_version",
        ):
            _require_string(name, getattr(self, name))
        _require_int("gpu_memory_bytes", self.gpu_memory_bytes, minimum=1)
        _require_int("free_disk_bytes", self.free_disk_bytes, minimum=1)
        if not isinstance(self.git_commit, str) or _GIT_COMMIT.fullmatch(self.git_commit) is None:
            raise ValueError("git_commit must be a lowercase 40-character commit hash")
        if type(self.git_dirty) is not bool:
            raise TypeError("git_dirty must be a boolean")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calibration_only": self.calibration_only,
            "formal_parameter_authority": self.formal_parameter_authority,
            "os_release": self.os_release,
            "kernel": self.kernel,
            "python_version": self.python_version,
            "gpu_name": self.gpu_name,
            "gpu_memory_bytes": self.gpu_memory_bytes,
            "driver_version": self.driver_version,
            "reported_cuda_version": self.reported_cuda_version,
            "free_disk_bytes": self.free_disk_bytes,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        os_release: str,
        kernel: str,
        python_version: str,
        gpu_name: str,
        gpu_memory_bytes: int,
        driver_version: str,
        reported_cuda_version: str,
        free_disk_bytes: int,
        git_commit: str,
        git_dirty: bool,
    ) -> CloudPreflight:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA_VERSION,
            "calibration_only": True,
            "formal_parameter_authority": False,
            "os_release": os_release,
            "kernel": kernel,
            "python_version": python_version,
            "gpu_name": gpu_name,
            "gpu_memory_bytes": gpu_memory_bytes,
            "driver_version": driver_version,
            "reported_cuda_version": reported_cuda_version,
            "free_disk_bytes": free_disk_bytes,
            "git_commit": git_commit,
            "git_dirty": git_dirty,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> CloudPreflight:
        _require_exact_payload(
            payload,
            expected={field.name for field in fields(cls)},
            record_name="cloud preflight",
        )
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class SmokeManifest:
    """The sole authorization record for the isolated ten-prompt smoke."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    preflight_hash: str
    model_repository: str
    model_revision_candidate: str
    tokenizer_revision_candidate: str
    vllm_version_candidate: str
    endpoint: str
    served_model_name: str
    chat_template_hash: str
    runtime_policy_hash: str
    smoke_prompt_set_hash: str
    credential_boundary_hash: str
    archive_uri: str
    record_hash: str

    _SCHEMA_VERSION: ClassVar[str] = "paper1.calibration.smoke-manifest.v1"
    _MODEL_REPOSITORY: ClassVar[str] = "Qwen/Qwen3-8B"
    _VLLM_VERSION: ClassVar[str] = "0.23.0"
    _ENDPOINT: ClassVar[str] = "http://127.0.0.1:8000/v1/chat/completions"
    _SERVED_MODEL_NAME: ClassVar[str] = "qwen3-8b-paper1"

    def __post_init__(self) -> None:
        _require_gate_metadata(
            schema_version=self.schema_version,
            expected_schema=self._SCHEMA_VERSION,
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
        )
        for name in (
            "preflight_hash",
            "chat_template_hash",
            "runtime_policy_hash",
            "smoke_prompt_set_hash",
            "credential_boundary_hash",
        ):
            _require_sha256(name, getattr(self, name))
        for name in (
            "model_repository",
            "model_revision_candidate",
            "tokenizer_revision_candidate",
            "vllm_version_candidate",
            "endpoint",
            "served_model_name",
            "archive_uri",
        ):
            value = getattr(self, name)
            _require_string(name, value)
            _require_resolved(name, value)
        if self.model_repository != self._MODEL_REPOSITORY:
            raise ValueError("model repository is not the approved candidate")
        if self.model_revision_candidate != _MODEL_REVISION:
            raise ValueError("model revision is not the approved candidate")
        if self.tokenizer_revision_candidate != _MODEL_REVISION:
            raise ValueError("tokenizer revision is not the approved candidate")
        if self.vllm_version_candidate != self._VLLM_VERSION:
            raise ValueError("vLLM version is not the approved candidate")
        if self.endpoint != self._ENDPOINT:
            raise ValueError("endpoint must be the approved loopback endpoint")
        if self.served_model_name != self._SERVED_MODEL_NAME:
            raise ValueError("served model name is not the approved candidate")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in (field.name for field in fields(self))
            if name != "record_hash"
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        preflight_hash: str,
        model_repository: str,
        model_revision_candidate: str,
        tokenizer_revision_candidate: str,
        vllm_version_candidate: str,
        endpoint: str,
        served_model_name: str,
        chat_template_hash: str,
        runtime_policy_hash: str,
        smoke_prompt_set_hash: str,
        credential_boundary_hash: str,
        archive_uri: str,
    ) -> SmokeManifest:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA_VERSION,
            "calibration_only": True,
            "formal_parameter_authority": False,
            "preflight_hash": preflight_hash,
            "model_repository": model_repository,
            "model_revision_candidate": model_revision_candidate,
            "tokenizer_revision_candidate": tokenizer_revision_candidate,
            "vllm_version_candidate": vllm_version_candidate,
            "endpoint": endpoint,
            "served_model_name": served_model_name,
            "chat_template_hash": chat_template_hash,
            "runtime_policy_hash": runtime_policy_hash,
            "smoke_prompt_set_hash": smoke_prompt_set_hash,
            "credential_boundary_hash": credential_boundary_hash,
            "archive_uri": archive_uri,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> SmokeManifest:
        _require_exact_payload(
            payload,
            expected={field.name for field in fields(cls)},
            record_name="smoke manifest",
        )
        return cls(**payload)  # type: ignore[arg-type]
