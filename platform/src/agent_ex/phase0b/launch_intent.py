"""Pre-service, content-addressed intent for one preliminary Phase 0B launch.

The intent is deliberately independent of the service start identity and the
later run authorization. Its record hash is the manifest hash passed when the
dedicated Phase 0B vLLM service is started.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import PurePosixPath
import posixpath
import re
from typing import ClassVar, Mapping
from urllib.parse import urlparse

from ..domain import (
    _freeze,
    _json_ready,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    canonical_payload_hash,
)


_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_ARTIFACT_HASH_KEYS = frozenset(
    {
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
    }
)
_LOCAL_ARCHIVE_ROOT = PurePosixPath("/root/autodl-tmp")


def _archive_location(name: str, value: object) -> tuple[str, str, PurePosixPath]:
    if type(value) is not str or "UNRESOLVED[" in value or "\\" in value:
        raise ValueError(f"{name} must be a resolved external archive URI")
    parsed = urlparse(value)
    if parsed.scheme:
        hostname = parsed.hostname
        hostname_valid = (
            hostname is not None
            and len(hostname) <= 253
            and all(_HOST_LABEL.fullmatch(label) is not None for label in hostname.split("."))
        )
        if (
            parsed.scheme not in {"s3", "gs", "az"}
            or not hostname_valid
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.port is not None
            or parsed.path in {"", "/"}
            or posixpath.normpath(parsed.path) != parsed.path
        ):
            raise ValueError(f"{name} must point to an approved external archive")
        return parsed.scheme, hostname, PurePosixPath(parsed.path)
    if (
        value in {"", "/root/autodl-tmp"}
        or posixpath.normpath(value) != value
        or not PurePosixPath(value).is_relative_to(_LOCAL_ARCHIVE_ROOT)
    ):
        raise ValueError(f"{name} must be outside Git under /root/autodl-tmp")
    return "local", "", PurePosixPath(value)


@dataclass(frozen=True, slots=True)
class Phase0BLaunchIntent:
    """Immutable bridge from pinned inputs to a new service manifest hash."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    scope: str
    input_artifact_mode: str
    model_execution_mode: str
    source_commit: str
    source_bundle_hash: str
    candidate_config_hash: str
    artifact_hashes: Mapping[str, str]
    model_repository: str
    model_revision: str
    tokenizer_revision: str
    environment_lock_hash: str
    service_config_hash: str
    preflight_archive_uri: str
    full_run_archive_uri: str
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.launch-intent.v1"

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA:
            raise ValueError("schema_version is not supported")
        if self.calibration_only is not True or type(self.calibration_only) is not bool:
            raise ValueError("launch intent must remain calibration_only=true")
        if (
            self.formal_parameter_authority is not False
            or type(self.formal_parameter_authority) is not bool
        ):
            raise ValueError("launch intent must not grant formal parameter authority")
        if self.research_parameter_status != "not_frozen":
            raise ValueError("research_parameter_status must remain not_frozen")
        if self.scope != "phase0b_preliminary_diagnostic_n20_t2":
            raise ValueError("scope must remain the preliminary N=20/T=2 diagnostic")
        if self.input_artifact_mode != "synthetic_phase4b_candidate":
            raise ValueError("input artifacts must remain synthetic Phase 4B candidates")
        if self.model_execution_mode != "real_qwen_vllm":
            raise ValueError("model execution must declare real Qwen vLLM")
        if self.model_repository != "Qwen/Qwen3-8B":
            raise ValueError("model_repository must be exactly Qwen/Qwen3-8B")
        for name in ("source_commit", "model_revision", "tokenizer_revision"):
            value = getattr(self, name)
            if type(value) is not str or _GIT_COMMIT.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase 40-character revision")
        for name in (
            "source_bundle_hash",
            "candidate_config_hash",
            "environment_lock_hash",
            "service_config_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if type(self.artifact_hashes) is not dict or set(self.artifact_hashes) != (
            _ARTIFACT_HASH_KEYS
        ):
            raise ValueError("artifact hashes must contain the exact diagnostic inventory")
        for name, digest in self.artifact_hashes.items():
            if isinstance(digest, str) and "UNRESOLVED[" in digest:
                raise ValueError(f"artifact hash {name} must not contain UNRESOLVED markers")
            _require_sha256(f"artifact hash {name}", digest)
        preflight = _archive_location("preflight_archive_uri", self.preflight_archive_uri)
        full_run = _archive_location("full_run_archive_uri", self.full_run_archive_uri)
        if preflight[:2] == full_run[:2] and (
            preflight[2] == full_run[2]
            or preflight[2].is_relative_to(full_run[2])
            or full_run[2].is_relative_to(preflight[2])
        ):
            raise ValueError("preflight and full-run archive roots must be disjoint")
        object.__setattr__(self, "artifact_hashes", _freeze(self.artifact_hashes))
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def service_manifest_hash(self) -> str:
        """The hash to pass as phase0a1-service.sh's manifest_hash."""

        return self.record_hash

    def content_payload(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "record_hash"
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        source_commit: str,
        source_bundle_hash: str,
        candidate_config_hash: str,
        artifact_hashes: Mapping[str, str],
        model_repository: str,
        model_revision: str,
        tokenizer_revision: str,
        environment_lock_hash: str,
        service_config_hash: str,
        preflight_archive_uri: str,
        full_run_archive_uri: str,
    ) -> Phase0BLaunchIntent:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "scope": "phase0b_preliminary_diagnostic_n20_t2",
            "input_artifact_mode": "synthetic_phase4b_candidate",
            "model_execution_mode": "real_qwen_vllm",
            "source_commit": source_commit,
            "source_bundle_hash": source_bundle_hash,
            "candidate_config_hash": candidate_config_hash,
            "artifact_hashes": dict(artifact_hashes),
            "model_repository": model_repository,
            "model_revision": model_revision,
            "tokenizer_revision": tokenizer_revision,
            "environment_lock_hash": environment_lock_hash,
            "service_config_hash": service_config_hash,
            "preflight_archive_uri": preflight_archive_uri,
            "full_run_archive_uri": full_run_archive_uri,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Phase0BLaunchIntent:
        if type(payload) is not dict or set(payload) != {field.name for field in fields(cls)}:
            raise ValueError(
                "launch intent payload must contain exact fields including record_hash"
            )
        _require_json_transport(payload, "launch intent payload")
        if type(payload["artifact_hashes"]) is not dict:
            raise TypeError("artifact_hashes must use a JSON object")
        return cls(**payload)  # type: ignore[arg-type]
