"""Fail-closed command line boundary for Phase 0A-1 cloud calibration."""

from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPConnection
import importlib.metadata
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
from typing import Mapping, Sequence
from urllib.parse import urlsplit

from .cloud import CloudPreflight, SmokeManifest
from .cloud_run import (
    CloudRunArtifacts,
    CloudRunManifest,
    build_cloud_run_manifest,
    build_cloud_probe_report,
    execute_cloud_probe,
    load_cloud_run_artifacts,
    reconstruct_cloud_projection,
    resume_cloud_probe,
    seal_cloud_probe_report,
)
from .bundle import load_probe_bundle
from .environment import (
    ArtifactEntry,
    EnvironmentLock,
    EnvironmentObservation,
    GpuObservation,
    HealthCheckEvidence,
    ImageIdentity,
    PackageEntry,
    VllmIdentity,
)
from .contracts import ProbeRunProjection, ProbeRuntimePolicy
from .runner import ProbeRunCrash
from .review import (
    Adjudication,
    IndependentCode,
    SemanticReviewBundle,
    append_adjudication,
    export_blind_review,
    import_review_codes,
    items_for_coder,
)
from .smoke import run_probe_smoke
from .store import ProbeRunStore
from .vllm_adapter import VllmProbeAdapter
from ..domain import canonical_payload_hash


_COMMANDS = (
    "preflight",
    "smoke",
    "lock",
    "manifest",
    "run",
    "resume",
    "review-export",
    "review-import",
    "seal",
    "verify",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_CONTROL_FILE_BYTES = 16 * 1024 * 1024


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _existing_regular_file(value: str) -> Path:
    path = _absolute_path(value)
    if not path.is_file() or path.is_symlink():
        raise argparse.ArgumentTypeError("path must be an existing regular file")
    if path.resolve(strict=True) != path.absolute():
        raise argparse.ArgumentTypeError("symlinked path components are forbidden")
    return path


def _archive_root(value: str) -> Path:
    path = _absolute_path(value)
    if not path.is_dir() or path.is_symlink():
        raise argparse.ArgumentTypeError("archive root must be an existing regular directory")
    if path.resolve(strict=True) != path.absolute():
        raise argparse.ArgumentTypeError("symlinked archive roots are forbidden")
    return path


def _output_path(value: str) -> Path:
    path = _absolute_path(value)
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise argparse.ArgumentTypeError("output parent must be an existing regular directory")
    if path.parent.resolve(strict=True) != path.parent.absolute():
        raise argparse.ArgumentTypeError("symlinked output parents are forbidden")
    if path.exists() or path.is_symlink():
        raise argparse.ArgumentTypeError("output path must not already exist")
    return path


def _existing_regular_directory(value: str) -> Path:
    path = _absolute_path(value)
    if not path.is_dir() or path.is_symlink():
        raise argparse.ArgumentTypeError("path must be an existing regular directory")
    if path.resolve(strict=True) != path.absolute():
        raise argparse.ArgumentTypeError("symlinked path components are forbidden")
    return path


def _new_directory(value: str) -> Path:
    path = _absolute_path(value)
    if path.exists() or path.is_symlink():
        raise argparse.ArgumentTypeError("new directory path must not already exist")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise argparse.ArgumentTypeError(
            "new directory parent must be an existing regular directory"
        )
    if path.parent.resolve(strict=True) != path.parent.absolute():
        raise argparse.ArgumentTypeError("symlinked directory parents are forbidden")
    return path


def _sha256(value: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("hash must be a lowercase SHA-256 digest")
    return value


def _add_archive_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--archive-root", required=True, type=_archive_root)


def _add_hashed_file(parser: argparse.ArgumentParser, name: str) -> None:
    option = name.replace("_", "-")
    parser.add_argument(f"--{option}", required=True, type=_existing_regular_file)
    parser.add_argument(f"--{option}-hash", required=True, type=_sha256)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-ex-phase0a1",
        description="Audited Phase 0A-1 calibration only; grants no formal-run authority.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight")
    preflight.add_argument("--output", required=True, type=_output_path)

    smoke = commands.add_parser("smoke")
    _add_archive_root(smoke)
    _add_hashed_file(smoke, "manifest")
    _add_hashed_file(smoke, "runtime_policy")
    smoke.add_argument("--output", required=True, type=_output_path)

    lock = commands.add_parser("lock")
    _add_archive_root(lock)
    _add_hashed_file(lock, "approved_artifacts")
    _add_hashed_file(lock, "inspection_inputs")
    lock.add_argument("--output", required=True, type=_output_path)

    manifest = commands.add_parser("manifest")
    _add_archive_root(manifest)
    _add_hashed_file(manifest, "approved_artifacts")
    _add_hashed_file(manifest, "environment_lock")
    manifest.add_argument("--output", required=True, type=_output_path)

    run = commands.add_parser("run")
    _add_archive_root(run)
    _add_hashed_file(run, "approved_artifacts")
    _add_hashed_file(run, "environment_lock")
    _add_hashed_file(run, "manifest")
    _add_hashed_file(run, "inspection_inputs")
    run.add_argument("--output", required=True, type=_output_path)
    run.add_argument("--stop-after-attempts", type=int)

    resume = commands.add_parser("resume")
    _add_archive_root(resume)
    _add_hashed_file(resume, "approved_artifacts")
    _add_hashed_file(resume, "environment_lock")
    _add_hashed_file(resume, "manifest")
    _add_hashed_file(resume, "inspection_inputs")
    resume.add_argument("--output", required=True, type=_output_path)
    resume.add_argument("--stop-after-attempts", type=int)

    review_export = commands.add_parser("review-export")
    _add_archive_root(review_export)
    _add_hashed_file(review_export, "manifest")
    _add_hashed_file(review_export, "approved_artifacts")
    _add_hashed_file(review_export, "projection")
    review_export.add_argument("--output", required=True, type=_output_path)
    review_export.add_argument("--coder-pack-root", required=True, type=_new_directory)

    review_import = commands.add_parser("review-import")
    _add_archive_root(review_import)
    _add_hashed_file(review_import, "manifest")
    _add_hashed_file(review_import, "approved_artifacts")
    _add_hashed_file(review_import, "review_bundle")
    _add_hashed_file(review_import, "review_records")
    review_import.add_argument("--output", required=True, type=_output_path)

    seal = commands.add_parser("seal")
    _add_archive_root(seal)
    _add_hashed_file(seal, "manifest")
    _add_hashed_file(seal, "approved_artifacts")
    seal.add_argument("--bundle", required=True, type=_existing_regular_directory)
    seal.add_argument("--bundle-hash", required=True, type=_sha256)

    verify = commands.add_parser("verify")
    _add_archive_root(verify)
    _add_hashed_file(verify, "manifest")
    _add_hashed_file(verify, "approved_artifacts")
    return parser


def _checked_run(command: list[str]) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local inspection commands only
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=15,
        shell=False,
    )
    return completed.stdout.strip()


def _os_release() -> str:
    release_file = Path("/etc/os-release")
    if release_file.is_file() and not release_file.is_symlink():
        values: dict[str, str] = {}
        for line in release_file.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
        if values.get("PRETTY_NAME"):
            return values["PRETTY_NAME"]
    return platform.platform()


def _agent_ex_checkout_root() -> Path:
    for candidate in Path(__file__).resolve(strict=True).parents:
        if (candidate / ".git").exists() and (candidate / "platform" / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("the running Agent-EX code is not bound to a Git checkout")


def _git_identity() -> tuple[str, bool]:
    checkout = _agent_ex_checkout_root()
    prefix = ["git", "-C", str(checkout)]
    commit = _checked_run([*prefix, "rev-parse", "HEAD"])
    dirty = bool(_checked_run([*prefix, "status", "--porcelain=v1", "--untracked-files=all"]))
    return commit, dirty


def collect_cloud_preflight() -> CloudPreflight:
    """Collect a sanitized current-host observation without network or installation."""
    query = _checked_run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    rows = [line.strip() for line in query.splitlines() if line.strip()]
    if len(rows) != 1:
        raise RuntimeError("preflight requires exactly one visible GPU")
    fields = [item.strip() for item in rows[0].split(",")]
    if len(fields) != 3:
        raise RuntimeError("nvidia-smi GPU query returned an unexpected shape")
    gpu_name, memory_mib, driver_version = fields
    banner = _checked_run(["nvidia-smi"])
    cuda_match = re.search(r"CUDA Version:\s*([0-9.]+)", banner)
    if cuda_match is None:
        raise RuntimeError("nvidia-smi did not report a CUDA version")
    git_commit, git_dirty = _git_identity()
    free_disk = shutil.disk_usage(_agent_ex_checkout_root()).free
    return CloudPreflight.create(
        os_release=_os_release(),
        kernel=platform.release(),
        python_version=platform.python_version(),
        gpu_name=gpu_name,
        gpu_memory_bytes=int(memory_mib) * 1024 * 1024,
        driver_version=driver_version,
        reported_cuda_version=cuda_match.group(1),
        free_disk_bytes=free_disk,
        git_commit=git_commit,
        git_dirty=git_dirty,
    )


def _write_json_create_only(path: Path, payload: object) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"forbidden JSON constant: {value}")


def _read_json_record(path: Path, *, affirmative_hash: str) -> dict[str, object]:
    if path.stat().st_size > _MAX_CONTROL_FILE_BYTES:
        raise ValueError("control file exceeds maximum size")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("control file is not strict UTF-8 JSON") from error
    if type(payload) is not dict:
        raise TypeError("control file must contain one JSON object")
    if payload.get("record_hash") != affirmative_hash:
        raise ValueError("control file does not match its affirmative hash")
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    if canonical_payload_hash(content) != affirmative_hash:
        raise ValueError("control file record hash does not bind its content")
    return payload


def _read_json_payload(path: Path, *, affirmative_hash: str) -> dict[str, object]:
    if path.stat().st_size > _MAX_CONTROL_FILE_BYTES:
        raise ValueError("control file exceeds maximum size")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("control file is not strict UTF-8 JSON") from error
    if type(payload) is not dict:
        raise TypeError("control file must contain one JSON object")
    if canonical_payload_hash(payload) != affirmative_hash:
        raise ValueError("control file does not match its affirmative payload hash")
    return payload


def _require_within_archive(path: Path, archive_root: Path) -> None:
    checked = path.resolve(strict=path.exists())
    root = archive_root.resolve(strict=True)
    if not checked.is_relative_to(root):
        raise ValueError("evidence path is outside the explicit archive root")


def _manifest_command(args: argparse.Namespace) -> int:
    for path in (args.approved_artifacts, args.environment_lock, args.output):
        _require_within_archive(path, args.archive_root)
    approved_payload = _read_json_record(
        args.approved_artifacts,
        affirmative_hash=args.approved_artifacts_hash,
    )
    lock_payload = _read_json_record(
        args.environment_lock,
        affirmative_hash=args.environment_lock_hash,
    )
    artifacts = load_cloud_run_artifacts(approved_payload)
    environment_lock = EnvironmentLock.from_payload(lock_payload)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=environment_lock)
    _write_json_create_only(args.output, manifest.to_payload())
    return 0


def _inspection_inputs(payload: Mapping[str, object]) -> dict[str, object]:
    expected = {
        "schema_version",
        "artifact_root",
        "model_files",
        "tokenizer_files",
        "chat_template_file",
        "rendered_non_thinking_file",
        "vllm_wheel_file",
        "image_repository",
        "image_digest",
        "serve_arguments",
        "health_endpoint",
        "archived_diff_file",
        "record_hash",
    }
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError("inspection inputs must contain exact fields")
    if payload["schema_version"] != "paper1.calibration.environment-inspection-inputs.v1":
        raise ValueError("inspection input schema is not supported")
    for name in (
        "artifact_root",
        "chat_template_file",
        "rendered_non_thinking_file",
        "vllm_wheel_file",
        "image_repository",
        "image_digest",
        "health_endpoint",
    ):
        if type(payload[name]) is not str or not payload[name].strip():
            raise ValueError(f"inspection input {name} must be a nonempty string")
    for name in ("model_files", "tokenizer_files", "serve_arguments"):
        value = payload[name]
        if type(value) is not list or not value or any(type(item) is not str for item in value):
            raise TypeError(f"inspection input {name} must be a nonempty JSON array of strings")
        if len(set(value)) != len(value):
            raise ValueError(f"inspection input {name} contains duplicates")
    archived_diff = payload["archived_diff_file"]
    if archived_diff is not None and (type(archived_diff) is not str or not archived_diff.strip()):
        raise TypeError("archived_diff_file must be a nonempty string or null")
    if payload["health_endpoint"] != "http://127.0.0.1:8000/health":
        raise ValueError("inspection health endpoint must be the exact loopback vLLM health URL")
    for name in (
        *payload["model_files"],  # type: ignore[misc]
        *payload["tokenizer_files"],  # type: ignore[misc]
        payload["chat_template_file"],
        payload["rendered_non_thinking_file"],
        payload["vllm_wheel_file"],
        *(() if archived_diff is None else (archived_diff,)),
    ):
        path = PurePosixPath(name)  # type: ignore[arg-type]
        if (
            path.is_absolute()
            or "\\" in str(name)
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("inspection artifact paths must be normalized relative POSIX paths")
    return dict(payload)


def _artifact_path(root: Path, relative_path: str) -> Path:
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    if not path.is_file() or path.is_symlink() or path.resolve(strict=True) != path.absolute():
        raise ValueError("inspection artifact must be a regular file without symlinks")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_entries(root: Path, names: list[str]) -> tuple[ArtifactEntry, ...]:
    result = []
    for name in names:
        path = _artifact_path(root, name)
        result.append(
            ArtifactEntry(
                relative_path=name,
                byte_size=path.stat().st_size,
                sha256=_file_sha256(path),
            )
        )
    return tuple(result)


def _single_gpu_observation() -> tuple[GpuObservation, str, str]:
    query = _checked_run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    rows = [line.strip() for line in query.splitlines() if line.strip()]
    if len(rows) != 1:
        raise RuntimeError("environment inspection requires exactly one visible GPU")
    fields = [item.strip() for item in rows[0].split(",")]
    if len(fields) != 3:
        raise RuntimeError("nvidia-smi GPU query returned an unexpected shape")
    gpu_name, memory_mib, driver_version = fields
    banner = _checked_run(["nvidia-smi"])
    cuda_match = re.search(r"CUDA Version:\s*([0-9.]+)", banner)
    if cuda_match is None:
        raise RuntimeError("nvidia-smi did not report a CUDA version")
    return (
        GpuObservation(name=gpu_name, memory_bytes=int(memory_mib) * 1024 * 1024),
        driver_version,
        cuda_match.group(1),
    )


def _package_lock() -> tuple[PackageEntry, ...]:
    entries = {
        (distribution.metadata["Name"], distribution.version)
        for distribution in importlib.metadata.distributions()
        if distribution.metadata["Name"]
    }
    return tuple(
        PackageEntry(name=name, version=version)
        for name, version in sorted(entries, key=lambda item: item[0].casefold())
    )


def _health_check(endpoint: str) -> HealthCheckEvidence:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("health endpoint must be explicit loopback HTTP")
    connection = HTTPConnection("127.0.0.1", parsed.port, timeout=10.0)
    try:
        connection.request("GET", parsed.path or "/", headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("health response exceeds maximum size")
        status = response.status
    finally:
        connection.close()
    return HealthCheckEvidence(
        endpoint=endpoint,
        status_code=status,
        response_hash=hashlib.sha256(body).hexdigest(),
    )


def collect_environment_observation(
    artifacts: CloudRunArtifacts,
    inputs: Mapping[str, object],
    archive_root: Path,
) -> EnvironmentObservation:
    """Freshly inspect the current host and hash every approved runtime artifact."""
    if not isinstance(artifacts, CloudRunArtifacts):
        raise TypeError("environment inspection requires approved cloud artifacts")
    checked = _inspection_inputs(inputs)
    artifact_root = Path(checked["artifact_root"])  # type: ignore[arg-type]
    if not artifact_root.is_absolute() or not artifact_root.is_dir() or artifact_root.is_symlink():
        raise ValueError("inspection artifact_root must be an existing absolute directory")
    if artifact_root.resolve(strict=True) != artifact_root.absolute():
        raise ValueError("inspection artifact_root must not traverse symlinks")
    _require_within_archive(artifact_root, archive_root)
    model_files = checked["model_files"]
    tokenizer_files = checked["tokenizer_files"]
    model_artifacts = _artifact_entries(artifact_root, model_files)  # type: ignore[arg-type]
    tokenizer_artifacts = _artifact_entries(artifact_root, tokenizer_files)  # type: ignore[arg-type]
    chat_path = _artifact_path(artifact_root, checked["chat_template_file"])  # type: ignore[arg-type]
    rendered_path = _artifact_path(
        artifact_root,
        checked["rendered_non_thinking_file"],  # type: ignore[arg-type]
    )
    wheel_path = _artifact_path(artifact_root, checked["vllm_wheel_file"])  # type: ignore[arg-type]
    chat_template = chat_path.read_text(encoding="utf-8")
    rendered = rendered_path.read_text(encoding="utf-8")
    packages = _package_lock()
    vllm_versions = {item.version for item in packages if item.name.casefold() == "vllm"}
    if len(vllm_versions) != 1:
        raise ValueError("environment must contain exactly one installed vLLM distribution")
    git_commit, git_dirty = _git_identity()
    archived_diff_file = checked["archived_diff_file"]
    archived_diff_hash = None
    if git_dirty:
        if archived_diff_file is None:
            raise ValueError("dirty Git requires an explicitly archived diff file")
        archived_diff_hash = _file_sha256(
            _artifact_path(artifact_root, archived_diff_file)  # type: ignore[arg-type]
        )
    elif archived_diff_file is not None:
        raise ValueError("archived diff is forbidden for a clean Git checkout")
    gpu, driver, cuda = _single_gpu_observation()
    candidate = artifacts.candidate_manifest
    return EnvironmentObservation(
        inspection_algorithm="agent-ex.environment-inspection.v1",
        git_commit=git_commit,
        git_dirty=git_dirty,
        archived_diff_hash=archived_diff_hash,
        os_release=_os_release(),
        kernel=platform.release(),
        gpu=gpu,
        driver_version=driver,
        reported_cuda_version=cuda,
        python_version=platform.python_version(),
        package_lock=packages,
        model_repository=candidate["model_repository"],  # type: ignore[arg-type]
        model_revision=candidate["model_revision"],  # type: ignore[arg-type]
        model_artifacts=model_artifacts,
        tokenizer_repository=candidate["tokenizer_repository"],  # type: ignore[arg-type]
        tokenizer_revision=candidate["tokenizer_revision"],  # type: ignore[arg-type]
        tokenizer_artifacts=tokenizer_artifacts,
        chat_template_text=chat_template,
        chat_template_hash=canonical_payload_hash(chat_template),
        rendered_non_thinking_hash=canonical_payload_hash(rendered),
        vllm_identity=VllmIdentity(
            version=next(iter(vllm_versions)),
            wheel_hash=_file_sha256(wheel_path),
        ),
        image_identity=ImageIdentity(
            repository=checked["image_repository"],  # type: ignore[arg-type]
            digest=checked["image_digest"],  # type: ignore[arg-type]
        ),
        serve_arguments=tuple(checked["serve_arguments"]),  # type: ignore[arg-type]
        health_check=_health_check(checked["health_endpoint"]),  # type: ignore[arg-type]
    )


def _lock_command(args: argparse.Namespace) -> int:
    for path in (args.approved_artifacts, args.inspection_inputs, args.output):
        _require_within_archive(path, args.archive_root)
    approved_payload = _read_json_record(
        args.approved_artifacts,
        affirmative_hash=args.approved_artifacts_hash,
    )
    inspection_payload = _read_json_record(
        args.inspection_inputs,
        affirmative_hash=args.inspection_inputs_hash,
    )
    artifacts = load_cloud_run_artifacts(approved_payload)
    observation = collect_environment_observation(
        artifacts,
        _inspection_inputs(inspection_payload),
        args.archive_root,
    )
    environment_lock = EnvironmentLock.create(
        observation,
        authorization_hash=artifacts.record_hash,
    )
    build_cloud_run_manifest(artifacts, environment_lock=environment_lock)
    _write_json_create_only(args.output, environment_lock.to_payload())
    return 0


def _run_archive_path(archive_uri: str, archive_root: Path, *, must_exist: bool) -> Path:
    path = Path(archive_uri)
    if not path.is_absolute():
        raise ValueError("manifest archive URI must resolve to an absolute host path")
    if must_exist:
        if not path.is_dir() or path.is_symlink():
            raise ValueError("run archive must be an existing regular directory")
        resolved = path.resolve(strict=True)
    else:
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise ValueError("run archive parent must be an existing regular directory")
        resolved = path.parent.resolve(strict=True) / path.name
    if not resolved.is_relative_to(archive_root.resolve(strict=True)):
        raise ValueError("manifest run archive is outside the explicit archive root")
    return resolved


def _smoke_command(args: argparse.Namespace) -> int:
    for path in (args.manifest, args.runtime_policy, args.output):
        _require_within_archive(path, args.archive_root)
    manifest_payload = _read_json_record(args.manifest, affirmative_hash=args.manifest_hash)
    policy_payload = _read_json_record(
        args.runtime_policy,
        affirmative_hash=args.runtime_policy_hash,
    )
    manifest = SmokeManifest.from_payload(manifest_payload)
    policy = ProbeRuntimePolicy.from_payload(policy_payload)
    run_root = _run_archive_path(manifest.archive_uri, args.archive_root, must_exist=False)
    adapter = VllmProbeAdapter(
        manifest.endpoint,
        expected_model=manifest.served_model_name,
        model_revision=manifest.model_revision_candidate,
        tokenizer_repository=manifest.model_repository,
        tokenizer_revision=manifest.tokenizer_revision_candidate,
        runtime_version=manifest.vllm_version_candidate,
        chat_template_hash=manifest.chat_template_hash,
    )
    result = run_probe_smoke(manifest, adapter, run_root, policy)
    _write_json_create_only(args.output, result.to_payload())
    return 0


def _adapter_for_artifacts(artifacts: CloudRunArtifacts) -> VllmProbeAdapter:
    candidate = artifacts.candidate_manifest
    return VllmProbeAdapter(
        candidate["endpoint"],  # type: ignore[arg-type]
        expected_model=candidate["served_model_name"],  # type: ignore[arg-type]
        model_revision=candidate["model_revision"],  # type: ignore[arg-type]
        tokenizer_repository=candidate["tokenizer_repository"],  # type: ignore[arg-type]
        tokenizer_revision=candidate["tokenizer_revision"],  # type: ignore[arg-type]
        runtime_version=candidate["vllm_version"],  # type: ignore[arg-type]
        chat_template_hash=candidate["chat_template_hash"],  # type: ignore[arg-type]
    )


def _load_cloud_execution(
    args: argparse.Namespace,
) -> tuple[CloudRunArtifacts, EnvironmentLock, CloudRunManifest, EnvironmentObservation]:
    paths = (
        args.approved_artifacts,
        args.environment_lock,
        args.manifest,
        args.inspection_inputs,
        args.output,
    )
    for path in paths:
        _require_within_archive(path, args.archive_root)
    approved_payload = _read_json_record(
        args.approved_artifacts,
        affirmative_hash=args.approved_artifacts_hash,
    )
    lock_payload = _read_json_record(
        args.environment_lock,
        affirmative_hash=args.environment_lock_hash,
    )
    manifest_payload = _read_json_record(args.manifest, affirmative_hash=args.manifest_hash)
    inspection_payload = _read_json_record(
        args.inspection_inputs,
        affirmative_hash=args.inspection_inputs_hash,
    )
    artifacts = load_cloud_run_artifacts(approved_payload)
    environment_lock = EnvironmentLock.from_payload(lock_payload)
    manifest = CloudRunManifest.from_payload(manifest_payload)
    expected = build_cloud_run_manifest(artifacts, environment_lock=environment_lock)
    if manifest != expected:
        raise ValueError("run manifest differs from approved artifacts and environment lock")
    current = collect_environment_observation(
        artifacts,
        _inspection_inputs(inspection_payload),
        args.archive_root,
    )
    return artifacts, environment_lock, manifest, current


def _run_command(args: argparse.Namespace) -> int:
    artifacts, environment_lock, manifest, current = _load_cloud_execution(args)
    run_root = _run_archive_path(artifacts.archive_uri, args.archive_root, must_exist=False)
    store = ProbeRunStore.create(run_root, manifest=manifest.to_payload())
    adapter = _adapter_for_artifacts(artifacts)
    try:
        projection = execute_cloud_probe(
            run_artifacts=artifacts,
            adapter=adapter,
            environment_lock=environment_lock,
            current_environment=current,
            manifest=manifest,
            store=store,
            stop_after_attempts=args.stop_after_attempts,
        )
    except ProbeRunCrash as error:
        _write_json_create_only(args.output, error.snapshot.to_payload())
        raise
    _write_json_create_only(args.output, projection.to_payload())
    return 0


def _resume_command(args: argparse.Namespace) -> int:
    artifacts, environment_lock, manifest, current = _load_cloud_execution(args)
    run_root = _run_archive_path(artifacts.archive_uri, args.archive_root, must_exist=True)
    store = ProbeRunStore.open(run_root)
    projection = reconstruct_cloud_projection(
        store,
        run_artifacts=artifacts,
        manifest=manifest,
    )
    adapter = _adapter_for_artifacts(artifacts)
    try:
        resumed = resume_cloud_probe(
            manifest=manifest,
            run_artifacts=artifacts,
            environment_lock=environment_lock,
            current_environment=current,
            projection=projection,
            adapter=adapter,
            store=store,
            stop_after_attempts=args.stop_after_attempts,
        )
    except ProbeRunCrash as error:
        _write_json_create_only(args.output, error.snapshot.to_payload())
        raise
    _write_json_create_only(args.output, resumed.to_payload())
    return 0


def _load_manifest_for_store(args: argparse.Namespace) -> CloudRunManifest:
    _require_within_archive(args.manifest, args.archive_root)
    payload = _read_json_record(args.manifest, affirmative_hash=args.manifest_hash)
    return CloudRunManifest.from_payload(payload)


def _verify_command(args: argparse.Namespace) -> int:
    manifest = _load_manifest_for_store(args)
    _require_within_archive(args.approved_artifacts, args.archive_root)
    artifacts = load_cloud_run_artifacts(
        _read_json_record(
            args.approved_artifacts,
            affirmative_hash=args.approved_artifacts_hash,
        )
    )
    if manifest.approved_artifacts_hash != artifacts.record_hash:
        raise ValueError("verify artifacts differ from the run manifest")
    run_root = _run_archive_path(manifest.archive_uri, args.archive_root, must_exist=True)
    store = ProbeRunStore.open(run_root)
    if store.manifest_hash != manifest.record_hash:
        raise ValueError("archive store does not bind the affirmative run manifest")
    reconstructed = reconstruct_cloud_projection(
        store,
        run_artifacts=artifacts,
        manifest=manifest,
    )
    if store._sealed:  # noqa: SLF001 - verification intentionally inspects sealed evidence
        bundle = load_probe_bundle(run_root / "sealed" / "files")
        if bundle.report.source.projection.to_payload() != reconstructed.to_payload():
            raise ValueError("sealed bundle differs from durable append-only evidence")
    else:
        build_cloud_probe_report(store)
    return 0


def _seal_command(args: argparse.Namespace) -> int:
    for path in (args.bundle, args.approved_artifacts):
        _require_within_archive(path, args.archive_root)
    manifest = _load_manifest_for_store(args)
    artifacts = load_cloud_run_artifacts(
        _read_json_record(
            args.approved_artifacts,
            affirmative_hash=args.approved_artifacts_hash,
        )
    )
    if manifest.approved_artifacts_hash != artifacts.record_hash:
        raise ValueError("seal artifacts differ from the run manifest")
    run_root = _run_archive_path(manifest.archive_uri, args.archive_root, must_exist=True)
    store = ProbeRunStore.open(run_root)
    if store.manifest_hash != manifest.record_hash:
        raise ValueError("archive store does not bind the affirmative run manifest")
    bundle = load_probe_bundle(args.bundle)
    if canonical_payload_hash(bundle.to_payloads()) != args.bundle_hash:
        raise ValueError("probe bundle does not match its affirmative payload hash")
    bundle_manifest = bundle.to_payloads()["manifest.json"]
    if (
        bundle.specification_hash != artifacts.specification.output_hash
        or bundle.case_inventory_hash != manifest.case_inventory_hash
        or not isinstance(bundle_manifest, Mapping)
        or bundle_manifest.get("external_archive_locator") != manifest.archive_uri
    ):
        raise ValueError("probe bundle differs from the authorized cloud run")
    seal_cloud_probe_report(
        store,
        bundle=bundle,
        run_artifacts=artifacts,
        manifest=manifest,
    )
    return 0


def _load_projection(path: Path, affirmative_hash: str) -> ProbeRunProjection:
    return ProbeRunProjection.from_payload(
        _read_json_payload(path, affirmative_hash=affirmative_hash)
    )


def _append_review_once(store: ProbeRunStore, payload: Mapping[str, object]) -> None:
    digest = payload.get("record_hash")
    if not isinstance(digest, str):
        raise ValueError("review evidence must contain record_hash")
    if digest in store.review_hashes:
        records = store._load_records(store.root / "staging" / "reviews", "review")  # noqa: SLF001
        if records.get(digest) != payload:
            raise ValueError("existing review evidence hash has different content")
        return
    store.append_review(payload)


def _review_export_command(args: argparse.Namespace) -> int:
    paths = (
        args.manifest,
        args.approved_artifacts,
        args.projection,
        args.output,
        args.coder_pack_root,
    )
    for path in paths:
        _require_within_archive(path, args.archive_root)
    manifest = _load_manifest_for_store(args)
    approved_payload = _read_json_record(
        args.approved_artifacts,
        affirmative_hash=args.approved_artifacts_hash,
    )
    artifacts = load_cloud_run_artifacts(approved_payload)
    if manifest.approved_artifacts_hash != artifacts.record_hash:
        raise ValueError("review export artifacts differ from the run manifest")
    projection = _load_projection(args.projection, args.projection_hash)
    if (
        projection.specification_hash != artifacts.specification.output_hash
        or projection.case_inventory_hash != manifest.case_inventory_hash
        or projection.runtime_policy_hash != artifacts.runtime_policy.record_hash
    ):
        raise ValueError("review export projection differs from the authorized run")
    run_root = _run_archive_path(manifest.archive_uri, args.archive_root, must_exist=True)
    store = ProbeRunStore.open(run_root)
    if store.manifest_hash != manifest.record_hash:
        raise ValueError("review export store differs from the run manifest")
    durable_projection = reconstruct_cloud_projection(
        store,
        run_artifacts=artifacts,
        manifest=manifest,
    )
    if projection.to_payload() != durable_projection.to_payload():
        raise ValueError("review export projection is not the durable cloud run")
    bundle = export_blind_review(
        artifacts.specification,
        artifacts.cases,
        projection,
        artifacts.semantic_review_policy,
    )
    _append_review_once(store, bundle.review_export.to_payload())
    _append_review_once(store, bundle.to_payload())
    args.coder_pack_root.mkdir(mode=0o700)
    created = True
    try:
        index_entries: list[dict[str, object]] = []
        for contract in bundle.policy.coder_contracts:
            items = items_for_coder(bundle, contract.coder_id)
            name_hash = canonical_payload_hash(contract.coder_id)[:20]
            filename = f"coder-{name_hash}.json"
            content: dict[str, object] = {
                "schema_version": "paper1.calibration.blind-coder-pack.v1",
                "coder_id": contract.coder_id,
                "coder_role": contract.role,
                "coder_contract_hash": contract.record_hash,
                "policy_id": bundle.policy.policy_id,
                "policy_hash": bundle.policy.record_hash,
                "export_hash": bundle.review_export.export_hash,
                "items": [item.to_payload() for item in items],
                "calibration_only": True,
                "formal_parameter_authority": False,
            }
            payload = {**content, "record_hash": canonical_payload_hash(content)}
            _write_json_create_only(args.coder_pack_root / filename, payload)
            index_entries.append(
                {
                    "coder_id": contract.coder_id,
                    "filename": filename,
                    "record_hash": payload["record_hash"],
                }
            )
        index_content: dict[str, object] = {
            "schema_version": "paper1.calibration.blind-coder-pack-index.v1",
            "review_bundle_hash": bundle.record_hash,
            "packs": index_entries,
            "calibration_only": True,
            "formal_parameter_authority": False,
        }
        _write_json_create_only(
            args.coder_pack_root / "index.json",
            {**index_content, "record_hash": canonical_payload_hash(index_content)},
        )
        created = False
    finally:
        if created:
            shutil.rmtree(args.coder_pack_root)
    _write_json_create_only(args.output, bundle.to_payload())
    return 0


def _review_import_command(args: argparse.Namespace) -> int:
    for path in (
        args.manifest,
        args.approved_artifacts,
        args.review_bundle,
        args.review_records,
        args.output,
    ):
        _require_within_archive(path, args.archive_root)
    manifest = _load_manifest_for_store(args)
    artifacts = load_cloud_run_artifacts(
        _read_json_record(
            args.approved_artifacts,
            affirmative_hash=args.approved_artifacts_hash,
        )
    )
    if manifest.approved_artifacts_hash != artifacts.record_hash:
        raise ValueError("review import artifacts differ from the run manifest")
    bundle_payload = _read_json_record(
        args.review_bundle,
        affirmative_hash=args.review_bundle_hash,
    )
    bundle = SemanticReviewBundle.from_payload(bundle_payload)
    if (
        bundle.review_export.specification_hash != artifacts.specification.output_hash
        or bundle.policy.record_hash != artifacts.semantic_review_policy.record_hash
    ):
        raise ValueError("review bundle differs from the authorized specification or policy")
    records = _read_json_record(
        args.review_records,
        affirmative_hash=args.review_records_hash,
    )
    if records.get("review_bundle_hash") != bundle.record_hash:
        raise ValueError("review records do not bind the input review bundle")
    values = records.get("records")
    if type(values) is not list:
        raise TypeError("review records must contain a JSON records array")
    schema = records.get("schema_version")
    common_fields = {
        "schema_version",
        "review_bundle_hash",
        "records",
        "calibration_only",
        "formal_parameter_authority",
        "record_hash",
    }
    if set(records) != common_fields:
        raise ValueError("review record set must contain exact fields")
    if (
        records.get("calibration_only") is not True
        or records.get("formal_parameter_authority") is not False
    ):
        raise ValueError("review records must remain calibration-only and non-authoritative")
    if schema == "paper1.calibration.independent-code-set.v1":
        updated = import_review_codes(
            bundle,
            tuple(IndependentCode.from_payload(item) for item in values),
        )
    elif schema == "paper1.calibration.adjudication-set.v1":
        updated = bundle
        for item in values:
            updated = append_adjudication(updated, Adjudication.from_payload(item))
    else:
        raise ValueError("review record set schema is not supported")
    run_root = _run_archive_path(manifest.archive_uri, args.archive_root, must_exist=True)
    store = ProbeRunStore.open(run_root)
    if store.manifest_hash != manifest.record_hash:
        raise ValueError("review import store differs from the run manifest")
    durable_projection = reconstruct_cloud_projection(
        store,
        run_artifacts=artifacts,
        manifest=manifest,
    )
    if bundle.review_export.run_evidence_hash != durable_projection.run_evidence_hash:
        raise ValueError("review import bundle is not bound to the durable cloud run")
    durable_reviews = store._load_records(  # noqa: SLF001
        store.root / "staging" / "reviews", "review"
    )
    export_payload = bundle.review_export.to_payload()
    if (
        durable_reviews.get(export_payload["record_hash"]) != export_payload
        or durable_reviews.get(bundle.record_hash) != bundle.to_payload()
    ):
        raise ValueError("review import lacks the store's durable blind export evidence")
    _append_review_once(store, records)
    _append_review_once(store, updated.to_payload())
    _write_json_create_only(args.output, updated.to_payload())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "preflight":
        result = collect_cloud_preflight()
        _write_json_create_only(args.output, result.to_payload())
        return 0
    if args.command == "manifest":
        return _manifest_command(args)
    if args.command == "lock":
        return _lock_command(args)
    if args.command == "smoke":
        return _smoke_command(args)
    if args.command == "run":
        return _run_command(args)
    if args.command == "resume":
        return _resume_command(args)
    if args.command == "verify":
        return _verify_command(args)
    if args.command == "seal":
        return _seal_command(args)
    if args.command == "review-export":
        return _review_export_command(args)
    if args.command == "review-import":
        return _review_import_command(args)
    raise RuntimeError(f"{args.command} execution handler is not implemented")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
