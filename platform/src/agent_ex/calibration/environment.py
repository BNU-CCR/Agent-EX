"""Immutable environment identity for controlled cloud calibration runs."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING, ClassVar, Mapping
from urllib.parse import urlparse

from ..domain import (
    _json_ready,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    _require_tuple,
    canonical_payload_hash,
)

if TYPE_CHECKING:
    from .cloud import SmokeManifest


_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET = re.compile(
    r"(?i)(?:^|[\s_-])(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
    r"(?:\s*(?:=|:)\s*|\s+)\S+"
    r"|hf_[A-Za-z0-9]{8,}|BEGIN [A-Z ]*PRIVATE KEY"
)


def _exact(payload: Mapping[str, object], expected: set[str], name: str) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError(f"{name} payload must contain exact fields")
    _require_json_transport(payload, f"{name} payload")


def _git_commit(name: str, value: object) -> None:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise ValueError(f"{name} must be an exact lowercase 40-character revision")


def _no_secret(name: str, value: str) -> None:
    if _SECRET.search(value):
        raise ValueError(f"{name} must not contain a secret")


@dataclass(frozen=True, slots=True)
class PackageEntry:
    name: str
    version: str

    def __post_init__(self) -> None:
        _require_string("package name", self.name)
        _require_string("package version", self.version)
        if self.name != self.name.strip() or self.version != self.version.strip():
            raise ValueError("package fields must be canonical strings")
        _no_secret("package entry", f"{self.name}=={self.version}")

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "version": self.version}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PackageEntry:
        _exact(payload, {"name", "version"}, "package entry")
        return cls(name=payload["name"], version=payload["version"])  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class WheelEntry:
    name: str
    version: str
    sha256: str
    source: str

    def __post_init__(self) -> None:
        for label, value in (
            ("wheel name", self.name),
            ("wheel version", self.version),
            ("wheel source", self.source),
        ):
            _require_string(label, value)
            if value != value.strip():
                raise ValueError(f"{label} must be canonical")
            _no_secret(label, value)
        _require_sha256("wheel sha256", self.sha256)

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "sha256": self.sha256,
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> WheelEntry:
        _exact(payload, {"name", "version", "sha256", "source"}, "wheel entry")
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class PreliminaryEnvironmentInspection:
    schema_version: str
    python_version: str
    package_lock: tuple[PackageEntry, ...]
    wheel_entries: tuple[WheelEntry, ...]
    torch_source: str
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    _SCHEMA_VERSION: ClassVar[str] = "paper1.calibration.preliminary-environment-inspection.v1"

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA_VERSION:
            raise ValueError("preliminary inspection schema_version is not supported")
        if re.fullmatch(r"3\.12\.\d+", self.python_version) is None:
            raise ValueError("preliminary inspection requires Python 3.12.x")
        _require_tuple("package_lock", self.package_lock)
        _require_tuple("wheel_entries", self.wheel_entries)
        if not self.package_lock or not all(
            isinstance(item, PackageEntry) for item in self.package_lock
        ):
            raise TypeError("preliminary package_lock requires PackageEntry values")
        if not self.wheel_entries or not all(
            isinstance(item, WheelEntry) for item in self.wheel_entries
        ):
            raise TypeError("preliminary wheel_entries requires WheelEntry values")
        if self.package_lock != tuple(
            sorted(self.package_lock, key=lambda item: item.name.casefold())
        ):
            raise ValueError("preliminary package_lock must be canonically sorted")
        if self.wheel_entries != tuple(
            sorted(self.wheel_entries, key=lambda item: item.name.casefold())
        ):
            raise ValueError("preliminary wheel_entries must be canonically sorted")
        vllm = tuple(item for item in self.wheel_entries if item.name.casefold() == "vllm")
        if len(vllm) != 1 or vllm[0].version != "0.23.0":
            raise ValueError("preliminary inspection requires exactly one vLLM 0.23.0 wheel")
        if vllm[0].source != "official-cuda-12.9":
            raise ValueError("vLLM wheel must use the official CUDA 12.9 source")
        if self.torch_source != "fresh-vllm-environment":
            raise ValueError("torch must come from the fresh vLLM environment")
        _no_secret("torch source", self.torch_source)
        if self.calibration_only is not True or self.formal_parameter_authority is not False:
            raise ValueError("preliminary inspection must remain calibration-only")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "python_version": self.python_version,
            "package_lock": tuple(item.to_payload() for item in self.package_lock),
            "wheel_entries": tuple(item.to_payload() for item in self.wheel_entries),
            "torch_source": self.torch_source,
            "calibration_only": self.calibration_only,
            "formal_parameter_authority": self.formal_parameter_authority,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        python_version: str,
        package_lock: tuple[PackageEntry, ...],
        wheel_entries: tuple[WheelEntry, ...],
        torch_source: str,
    ) -> PreliminaryEnvironmentInspection:
        packages = tuple(sorted(package_lock, key=lambda item: item.name.casefold()))
        wheels = tuple(sorted(wheel_entries, key=lambda item: item.name.casefold()))
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA_VERSION,
            "python_version": python_version,
            "package_lock": packages,
            "wheel_entries": wheels,
            "torch_source": torch_source,
            "calibration_only": True,
            "formal_parameter_authority": False,
        }
        hash_content = dict(content)
        hash_content["package_lock"] = tuple(item.to_payload() for item in packages)
        hash_content["wheel_entries"] = tuple(item.to_payload() for item in wheels)
        return cls(**content, record_hash=canonical_payload_hash(hash_content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PreliminaryEnvironmentInspection:
        expected = {field.name for field in fields(cls)}
        _exact(payload, expected, "preliminary environment inspection")
        values = dict(payload)
        values["package_lock"] = tuple(
            PackageEntry.from_payload(item)
            for item in payload["package_lock"]  # type: ignore[union-attr]
        )
        values["wheel_entries"] = tuple(
            WheelEntry.from_payload(item)
            for item in payload["wheel_entries"]  # type: ignore[union-attr]
        )
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ArtifactEntry:
    relative_path: str
    byte_size: int
    sha256: str
    is_symlink: bool = False

    def __post_init__(self) -> None:
        _require_string("artifact relative_path", self.relative_path)
        path = PurePosixPath(self.relative_path)
        if (
            path.is_absolute()
            or "\\" in self.relative_path
            or self.relative_path != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("artifact relative_path must be a normalized relative POSIX path")
        _require_int("artifact byte_size", self.byte_size, minimum=1)
        _require_sha256("artifact sha256", self.sha256)
        if type(self.is_symlink) is not bool:
            raise TypeError("artifact is_symlink must be a boolean")
        if self.is_symlink:
            raise ValueError("artifact symlink entries are forbidden")

    def to_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "is_symlink": self.is_symlink,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ArtifactEntry:
        _exact(payload, {"relative_path", "byte_size", "sha256", "is_symlink"}, "artifact")
        return cls(
            relative_path=payload["relative_path"],  # type: ignore[arg-type]
            byte_size=payload["byte_size"],  # type: ignore[arg-type]
            sha256=payload["sha256"],  # type: ignore[arg-type]
            is_symlink=payload["is_symlink"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class GpuObservation:
    name: str
    memory_bytes: int

    def __post_init__(self) -> None:
        _require_string("gpu name", self.name)
        _require_int("gpu memory_bytes", self.memory_bytes, minimum=1)

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "memory_bytes": self.memory_bytes}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> GpuObservation:
        _exact(payload, {"name", "memory_bytes"}, "gpu")
        return cls(name=payload["name"], memory_bytes=payload["memory_bytes"])  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class VllmIdentity:
    version: str
    wheel_hash: str

    def __post_init__(self) -> None:
        _require_string("vLLM version", self.version)
        _require_sha256("vLLM wheel_hash", self.wheel_hash)

    def to_payload(self) -> dict[str, object]:
        return {"version": self.version, "wheel_hash": self.wheel_hash}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> VllmIdentity:
        _exact(payload, {"version", "wheel_hash"}, "vLLM identity")
        return cls(version=payload["version"], wheel_hash=payload["wheel_hash"])  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ImageIdentity:
    repository: str
    digest: str

    def __post_init__(self) -> None:
        _require_string("image repository", self.repository)
        if not isinstance(self.digest, str) or _IMAGE_DIGEST.fullmatch(self.digest) is None:
            raise ValueError("image digest must be an immutable sha256 digest")
        _no_secret("image identity", f"{self.repository}@{self.digest}")

    def to_payload(self) -> dict[str, object]:
        return {"repository": self.repository, "digest": self.digest}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ImageIdentity:
        _exact(payload, {"repository", "digest"}, "image identity")
        return cls(repository=payload["repository"], digest=payload["digest"])  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class HealthCheckEvidence:
    endpoint: str
    status_code: int
    response_hash: str

    def __post_init__(self) -> None:
        _require_string("health_check endpoint", self.endpoint)
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
            raise ValueError("health_check endpoint must be an explicit loopback HTTP endpoint")
        _require_int("health_check status_code", self.status_code, minimum=100)
        if self.status_code > 599:
            raise ValueError("health_check status_code must be an HTTP status")
        if self.status_code != 200:
            raise ValueError("health_check requires a healthy HTTP 200 response")
        _require_sha256("health_check response_hash", self.response_hash)

    def to_payload(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "response_hash": self.response_hash,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> HealthCheckEvidence:
        _exact(payload, {"endpoint", "status_code", "response_hash"}, "health check")
        return cls(
            endpoint=payload["endpoint"],  # type: ignore[arg-type]
            status_code=payload["status_code"],  # type: ignore[arg-type]
            response_hash=payload["response_hash"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class EnvironmentObservation:
    """Typed output of the versioned, current-host inspection algorithm."""

    inspection_algorithm: str
    git_commit: str
    git_dirty: bool
    archived_diff_hash: str | None
    os_release: str
    kernel: str
    gpu: GpuObservation
    driver_version: str
    reported_cuda_version: str
    python_version: str
    package_lock: tuple[PackageEntry, ...]
    model_repository: str
    model_revision: str
    model_artifacts: tuple[ArtifactEntry, ...]
    tokenizer_repository: str
    tokenizer_revision: str
    tokenizer_artifacts: tuple[ArtifactEntry, ...]
    chat_template_text: str
    chat_template_hash: str
    rendered_non_thinking_hash: str
    vllm_identity: VllmIdentity
    image_identity: ImageIdentity
    serve_arguments: tuple[str, ...]
    health_check: HealthCheckEvidence

    _ALGORITHM: ClassVar[str] = "agent-ex.environment-inspection.v1"

    def __post_init__(self) -> None:
        if self.inspection_algorithm != self._ALGORITHM:
            raise ValueError("inspection_algorithm is not supported")
        _git_commit("git_commit", self.git_commit)
        if type(self.git_dirty) is not bool:
            raise TypeError("git_dirty must be a boolean")
        _require_sha256("archived_diff_hash", self.archived_diff_hash, optional=True)
        if self.git_dirty and self.archived_diff_hash is None:
            raise ValueError("dirty Git requires an approved archived_diff_hash")
        if not self.git_dirty and self.archived_diff_hash is not None:
            raise ValueError("archived_diff_hash is allowed only for dirty Git")
        for name in (
            "os_release",
            "kernel",
            "driver_version",
            "reported_cuda_version",
            "python_version",
            "model_repository",
            "tokenizer_repository",
            "chat_template_text",
        ):
            _require_string(name, getattr(self, name))
            _no_secret(name, getattr(self, name))
        if not isinstance(self.gpu, GpuObservation):
            raise TypeError("gpu must be GpuObservation")
        _git_commit("model_revision exact revision", self.model_revision)
        _git_commit("tokenizer_revision exact revision", self.tokenizer_revision)
        self._validate_packages()
        self._validate_artifacts("model_artifacts", self.model_artifacts)
        self._validate_artifacts("tokenizer_artifacts", self.tokenizer_artifacts)
        _require_sha256("chat_template_hash", self.chat_template_hash)
        _require_payload_hash(
            "chat_template_hash", self.chat_template_hash, self.chat_template_text
        )
        _require_sha256("rendered_non_thinking_hash", self.rendered_non_thinking_hash)
        if not isinstance(self.vllm_identity, VllmIdentity):
            raise TypeError("vllm_identity must be VllmIdentity")
        if not isinstance(self.image_identity, ImageIdentity):
            raise TypeError("image_identity must be ImageIdentity")
        _require_tuple("serve_arguments", self.serve_arguments)
        if not self.serve_arguments:
            raise ValueError("serve_arguments must not be empty")
        for argument in self.serve_arguments:
            _require_string("serve argument", argument)
        _no_secret("serve_arguments", " ".join(self.serve_arguments))
        host_positions = tuple(
            index for index, argument in enumerate(self.serve_arguments) if argument == "--host"
        )
        if len(host_positions) != 1 or host_positions[0] + 1 >= len(self.serve_arguments):
            raise ValueError("serve_arguments must bind one explicit loopback host")
        if self.serve_arguments[host_positions[0] + 1] != "127.0.0.1":
            raise ValueError("serve_arguments must bind the loopback host")
        if not isinstance(self.health_check, HealthCheckEvidence):
            raise TypeError("health_check must be HealthCheckEvidence")

    def _validate_packages(self) -> None:
        _require_tuple("package_lock", self.package_lock)
        if not self.package_lock:
            raise ValueError("package_lock must not be empty")
        if not all(isinstance(item, PackageEntry) for item in self.package_lock):
            raise TypeError("package_lock entries must be PackageEntry")
        names = tuple(item.name.casefold() for item in self.package_lock)
        if len(set(names)) != len(names):
            raise ValueError("duplicate package names are forbidden")

    @staticmethod
    def _validate_artifacts(name: str, values: tuple[ArtifactEntry, ...]) -> None:
        _require_tuple(name, values)
        if not values:
            raise ValueError(f"{name} must not be empty")
        if not all(isinstance(item, ArtifactEntry) for item in values):
            raise TypeError(f"{name} entries must be ArtifactEntry")
        paths = tuple(item.relative_path for item in values)
        if len(set(paths)) != len(paths):
            raise ValueError("duplicate artifact paths are forbidden")


@dataclass(frozen=True, slots=True)
class EnvironmentLock:
    """Canonical, immutable binding to one inspected execution environment."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    authorization_hash: str
    inspection_algorithm: str
    git_commit: str
    git_dirty: bool
    archived_diff_hash: str | None
    os_release: str
    kernel: str
    gpu: GpuObservation
    gpu_hash: str
    driver_version: str
    reported_cuda_version: str
    python_version: str
    package_lock: tuple[PackageEntry, ...]
    package_lock_hash: str
    model_repository: str
    model_revision: str
    model_artifacts: tuple[ArtifactEntry, ...]
    model_artifacts_hash: str
    tokenizer_repository: str
    tokenizer_revision: str
    tokenizer_artifacts: tuple[ArtifactEntry, ...]
    tokenizer_artifacts_hash: str
    chat_template_text: str
    chat_template_hash: str
    rendered_non_thinking_hash: str
    vllm_identity: VllmIdentity
    vllm_identity_hash: str
    image_identity: ImageIdentity
    image_identity_hash: str
    serve_arguments: tuple[str, ...]
    serve_arguments_hash: str
    health_check: HealthCheckEvidence
    health_check_hash: str
    record_hash: str

    _SCHEMA_VERSION: ClassVar[str] = "paper1.calibration.environment-lock.v1"

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA_VERSION:
            raise ValueError("schema_version is not supported")
        if self.calibration_only is not True or type(self.calibration_only) is not bool:
            raise ValueError("environment lock must remain calibration-only")
        if (
            self.formal_parameter_authority is not False
            or type(self.formal_parameter_authority) is not bool
        ):
            raise ValueError("environment lock must not grant formal parameter authority")
        _require_sha256("authorization_hash", self.authorization_hash)
        observation = self._observation()
        package_payload = tuple(item.to_payload() for item in self.package_lock)
        model_payload = tuple(item.to_payload() for item in self.model_artifacts)
        tokenizer_payload = tuple(item.to_payload() for item in self.tokenizer_artifacts)
        nested = {
            "gpu_hash": self.gpu.to_payload(),
            "package_lock_hash": package_payload,
            "model_artifacts_hash": model_payload,
            "tokenizer_artifacts_hash": tokenizer_payload,
            "vllm_identity_hash": self.vllm_identity.to_payload(),
            "image_identity_hash": self.image_identity.to_payload(),
            "serve_arguments_hash": self.serve_arguments,
            "health_check_hash": self.health_check.to_payload(),
        }
        for name, payload in nested.items():
            _require_sha256(name, getattr(self, name))
            _require_payload_hash(name, getattr(self, name), payload)
        expected_packages = tuple(
            sorted(observation.package_lock, key=lambda item: item.name.casefold())
        )
        expected_model = tuple(
            sorted(observation.model_artifacts, key=lambda item: item.relative_path)
        )
        expected_tokenizer = tuple(
            sorted(observation.tokenizer_artifacts, key=lambda item: item.relative_path)
        )
        if self.package_lock != expected_packages:
            raise ValueError("package_lock must be canonically sorted")
        if self.model_artifacts != expected_model:
            raise ValueError("model_artifacts must be canonically sorted")
        if self.tokenizer_artifacts != expected_tokenizer:
            raise ValueError("tokenizer_artifacts must be canonically sorted")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.payload_without_record_hash())

    def _observation(self) -> EnvironmentObservation:
        return EnvironmentObservation(
            inspection_algorithm=self.inspection_algorithm,
            git_commit=self.git_commit,
            git_dirty=self.git_dirty,
            archived_diff_hash=self.archived_diff_hash,
            os_release=self.os_release,
            kernel=self.kernel,
            gpu=self.gpu,
            driver_version=self.driver_version,
            reported_cuda_version=self.reported_cuda_version,
            python_version=self.python_version,
            package_lock=self.package_lock,
            model_repository=self.model_repository,
            model_revision=self.model_revision,
            model_artifacts=self.model_artifacts,
            tokenizer_repository=self.tokenizer_repository,
            tokenizer_revision=self.tokenizer_revision,
            tokenizer_artifacts=self.tokenizer_artifacts,
            chat_template_text=self.chat_template_text,
            chat_template_hash=self.chat_template_hash,
            rendered_non_thinking_hash=self.rendered_non_thinking_hash,
            vllm_identity=self.vllm_identity,
            image_identity=self.image_identity,
            serve_arguments=self.serve_arguments,
            health_check=self.health_check,
        )

    def payload_without_record_hash(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calibration_only": self.calibration_only,
            "formal_parameter_authority": self.formal_parameter_authority,
            "authorization_hash": self.authorization_hash,
            "inspection_algorithm": self.inspection_algorithm,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "archived_diff_hash": self.archived_diff_hash,
            "os_release": self.os_release,
            "kernel": self.kernel,
            "gpu": self.gpu.to_payload(),
            "gpu_hash": self.gpu_hash,
            "driver_version": self.driver_version,
            "reported_cuda_version": self.reported_cuda_version,
            "python_version": self.python_version,
            "package_lock": tuple(item.to_payload() for item in self.package_lock),
            "package_lock_hash": self.package_lock_hash,
            "model_repository": self.model_repository,
            "model_revision": self.model_revision,
            "model_artifacts": tuple(item.to_payload() for item in self.model_artifacts),
            "model_artifacts_hash": self.model_artifacts_hash,
            "tokenizer_repository": self.tokenizer_repository,
            "tokenizer_revision": self.tokenizer_revision,
            "tokenizer_artifacts": tuple(item.to_payload() for item in self.tokenizer_artifacts),
            "tokenizer_artifacts_hash": self.tokenizer_artifacts_hash,
            "chat_template_text": self.chat_template_text,
            "chat_template_hash": self.chat_template_hash,
            "rendered_non_thinking_hash": self.rendered_non_thinking_hash,
            "vllm_identity": self.vllm_identity.to_payload(),
            "vllm_identity_hash": self.vllm_identity_hash,
            "image_identity": self.image_identity.to_payload(),
            "image_identity_hash": self.image_identity_hash,
            "serve_arguments": self.serve_arguments,
            "serve_arguments_hash": self.serve_arguments_hash,
            "health_check": self.health_check.to_payload(),
            "health_check_hash": self.health_check_hash,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.payload_without_record_hash(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls, observation: EnvironmentObservation, *, authorization_hash: str
    ) -> EnvironmentLock:
        if not isinstance(observation, EnvironmentObservation):
            raise TypeError("environment lock requires EnvironmentObservation")
        _require_sha256("authorization_hash", authorization_hash)
        packages = tuple(sorted(observation.package_lock, key=lambda item: item.name.casefold()))
        model_artifacts = tuple(
            sorted(observation.model_artifacts, key=lambda item: item.relative_path)
        )
        tokenizer_artifacts = tuple(
            sorted(observation.tokenizer_artifacts, key=lambda item: item.relative_path)
        )
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA_VERSION,
            "calibration_only": True,
            "formal_parameter_authority": False,
            "authorization_hash": authorization_hash,
            "inspection_algorithm": observation.inspection_algorithm,
            "git_commit": observation.git_commit,
            "git_dirty": observation.git_dirty,
            "archived_diff_hash": observation.archived_diff_hash,
            "os_release": observation.os_release,
            "kernel": observation.kernel,
            "gpu": observation.gpu,
            "gpu_hash": canonical_payload_hash(observation.gpu.to_payload()),
            "driver_version": observation.driver_version,
            "reported_cuda_version": observation.reported_cuda_version,
            "python_version": observation.python_version,
            "package_lock": packages,
            "package_lock_hash": canonical_payload_hash(
                tuple(item.to_payload() for item in packages)
            ),
            "model_repository": observation.model_repository,
            "model_revision": observation.model_revision,
            "model_artifacts": model_artifacts,
            "model_artifacts_hash": canonical_payload_hash(
                tuple(item.to_payload() for item in model_artifacts)
            ),
            "tokenizer_repository": observation.tokenizer_repository,
            "tokenizer_revision": observation.tokenizer_revision,
            "tokenizer_artifacts": tokenizer_artifacts,
            "tokenizer_artifacts_hash": canonical_payload_hash(
                tuple(item.to_payload() for item in tokenizer_artifacts)
            ),
            "chat_template_text": observation.chat_template_text,
            "chat_template_hash": observation.chat_template_hash,
            "rendered_non_thinking_hash": observation.rendered_non_thinking_hash,
            "vllm_identity": observation.vllm_identity,
            "vllm_identity_hash": canonical_payload_hash(observation.vllm_identity.to_payload()),
            "image_identity": observation.image_identity,
            "image_identity_hash": canonical_payload_hash(observation.image_identity.to_payload()),
            "serve_arguments": observation.serve_arguments,
            "serve_arguments_hash": canonical_payload_hash(observation.serve_arguments),
            "health_check": observation.health_check,
            "health_check_hash": canonical_payload_hash(observation.health_check.to_payload()),
        }
        hash_payload = _content_payload(content)
        return cls(**content, record_hash=canonical_payload_hash(hash_payload))  # type: ignore[arg-type]

    @classmethod
    def create_for_smoke(
        cls,
        observation: EnvironmentObservation,
        *,
        manifest: SmokeManifest,
        authorization_hash: str,
    ) -> EnvironmentLock:
        from .cloud import SmokeManifest

        if not isinstance(manifest, SmokeManifest):
            raise TypeError("smoke lock requires a strict SmokeManifest")
        if authorization_hash != manifest.record_hash:
            raise ValueError(
                "authorization_hash must equal the owner-approved manifest record_hash"
            )
        return cls.create(observation, authorization_hash=authorization_hash)

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> EnvironmentLock:
        expected = {field.name for field in fields(cls)}
        _exact(payload, expected, "environment lock")
        values = dict(payload)
        values["gpu"] = GpuObservation.from_payload(values["gpu"])  # type: ignore[arg-type]
        values["package_lock"] = tuple(
            PackageEntry.from_payload(item)
            for item in values["package_lock"]  # type: ignore[union-attr]
        )
        values["model_artifacts"] = tuple(
            ArtifactEntry.from_payload(item)
            for item in values["model_artifacts"]  # type: ignore[union-attr]
        )
        values["tokenizer_artifacts"] = tuple(
            ArtifactEntry.from_payload(item)
            for item in values["tokenizer_artifacts"]  # type: ignore[union-attr]
        )
        values["vllm_identity"] = VllmIdentity.from_payload(values["vllm_identity"])  # type: ignore[arg-type]
        values["image_identity"] = ImageIdentity.from_payload(values["image_identity"])  # type: ignore[arg-type]
        values["serve_arguments"] = tuple(values["serve_arguments"])  # type: ignore[arg-type]
        values["health_check"] = HealthCheckEvidence.from_payload(values["health_check"])  # type: ignore[arg-type]
        return cls(**values)  # type: ignore[arg-type]


def _content_payload(content: Mapping[str, object]) -> dict[str, object]:
    payload = dict(content)
    payload["gpu"] = content["gpu"].to_payload()  # type: ignore[union-attr]
    payload["package_lock"] = tuple(item.to_payload() for item in content["package_lock"])  # type: ignore[union-attr]
    payload["model_artifacts"] = tuple(
        item.to_payload()
        for item in content["model_artifacts"]  # type: ignore[union-attr]
    )
    payload["tokenizer_artifacts"] = tuple(
        item.to_payload()
        for item in content["tokenizer_artifacts"]  # type: ignore[union-attr]
    )
    payload["vllm_identity"] = content["vllm_identity"].to_payload()  # type: ignore[union-attr]
    payload["image_identity"] = content["image_identity"].to_payload()  # type: ignore[union-attr]
    payload["health_check"] = content["health_check"].to_payload()  # type: ignore[union-attr]
    return payload


class EnvironmentDriftError(RuntimeError):
    """Raised when the current host no longer matches an immutable lock."""


def verify_current_environment(lock: EnvironmentLock, current: EnvironmentObservation) -> None:
    if not isinstance(lock, EnvironmentLock):
        raise TypeError("lock must be EnvironmentLock")
    if not isinstance(current, EnvironmentObservation):
        raise TypeError("current must be EnvironmentObservation")
    candidate = EnvironmentLock.create(current, authorization_hash=lock.authorization_hash)
    drift_fields = (
        "inspection_algorithm",
        "git_commit",
        "git_dirty",
        "archived_diff_hash",
        "os_release",
        "kernel",
        "gpu",
        "driver_version",
        "reported_cuda_version",
        "python_version",
        "package_lock",
        "model_repository",
        "model_revision",
        "model_artifacts",
        "tokenizer_repository",
        "tokenizer_revision",
        "tokenizer_artifacts",
        "chat_template_text",
        "chat_template_hash",
        "rendered_non_thinking_hash",
        "vllm_identity",
        "image_identity",
        "serve_arguments",
        "health_check",
    )
    for field_name in drift_fields:
        if getattr(lock, field_name) != getattr(candidate, field_name):
            raise EnvironmentDriftError(f"{field_name} drift invalidates environment lock")
