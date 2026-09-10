"""Strict, reproducible environment-lock behavior for cloud calibration."""

from __future__ import annotations

from dataclasses import replace

import pytest

from agent_ex.calibration.environment import (
    ArtifactEntry,
    EnvironmentDriftError,
    EnvironmentLock,
    EnvironmentObservation,
    GpuObservation,
    HealthCheckEvidence,
    ImageIdentity,
    PackageEntry,
    VllmIdentity,
    verify_current_environment,
)
from agent_ex.domain import canonical_payload_hash


REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


def valid_observation() -> EnvironmentObservation:
    chat_template_text = "{% if not enable_thinking %}{{ messages }}{% endif %}"
    return EnvironmentObservation(
        inspection_algorithm="agent-ex.environment-inspection.v1",
        git_commit="7" * 40,
        git_dirty=False,
        archived_diff_hash=None,
        os_release="Ubuntu 22.04.5 LTS",
        kernel="5.15.0-119-generic",
        gpu=GpuObservation(name="NVIDIA GeForce RTX 5090", memory_bytes=32_607 * 2**20),
        driver_version="580.105.08",
        reported_cuda_version="12.8",
        python_version="3.12.3",
        package_lock=(
            PackageEntry(name="vllm", version="0.23.0"),
            PackageEntry(name="torch", version="2.8.0"),
        ),
        model_repository="Qwen/Qwen3-8B",
        model_revision=REVISION,
        model_artifacts=(
            ArtifactEntry(
                relative_path="model-00002-of-00005.safetensors",
                byte_size=2,
                sha256="2" * 64,
            ),
            ArtifactEntry(
                relative_path="model-00001-of-00005.safetensors",
                byte_size=1,
                sha256="1" * 64,
            ),
        ),
        tokenizer_repository="Qwen/Qwen3-8B",
        tokenizer_revision=REVISION,
        tokenizer_artifacts=(
            ArtifactEntry(relative_path="tokenizer.json", byte_size=3, sha256="3" * 64),
        ),
        chat_template_text=chat_template_text,
        chat_template_hash=canonical_payload_hash(chat_template_text),
        rendered_non_thinking_hash="4" * 64,
        vllm_identity=VllmIdentity(version="0.23.0", wheel_hash="5" * 64),
        image_identity=ImageIdentity(
            repository="docker.io/vllm/vllm-openai",
            digest="sha256:" + "6" * 64,
        ),
        serve_arguments=(
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--served-model-name",
            "qwen3-8b-paper1",
        ),
        health_check=HealthCheckEvidence(
            endpoint="http://127.0.0.1:8000/health",
            status_code=200,
            response_hash="8" * 64,
        ),
    )


def valid_environment_lock_and_observation() -> tuple[EnvironmentLock, EnvironmentObservation]:
    observed = valid_observation()
    return EnvironmentLock.create(observed), observed


def mutate_observation(
    observed: EnvironmentObservation, changed_field: str
) -> EnvironmentObservation:
    if changed_field == "git_commit":
        return replace(observed, git_commit="9" * 40)
    if changed_field == "git_dirty":
        return replace(observed, git_dirty=True, archived_diff_hash="a" * 64)
    if changed_field == "os_release":
        return replace(observed, os_release="Ubuntu 24.04")
    if changed_field == "kernel":
        return replace(observed, kernel="6.8.0")
    if changed_field == "gpu":
        return replace(observed, gpu=replace(observed.gpu, memory_bytes=31_000 * 2**20))
    if changed_field == "driver_version":
        return replace(observed, driver_version="581.0")
    if changed_field == "reported_cuda_version":
        return replace(observed, reported_cuda_version="12.9")
    if changed_field == "python_version":
        return replace(observed, python_version="3.12.4")
    if changed_field == "package_lock":
        return replace(
            observed,
            package_lock=observed.package_lock + (PackageEntry(name="httpx", version="0.28.1"),),
        )
    if changed_field == "model_artifacts":
        changed = replace(observed.model_artifacts[0], sha256="a" * 64)
        return replace(observed, model_artifacts=(changed, *observed.model_artifacts[1:]))
    if changed_field == "tokenizer_artifacts":
        changed = replace(observed.tokenizer_artifacts[0], byte_size=4)
        return replace(observed, tokenizer_artifacts=(changed,))
    if changed_field == "chat_template_text":
        text = observed.chat_template_text + "\n"
        return replace(
            observed,
            chat_template_text=text,
            chat_template_hash=canonical_payload_hash(text),
        )
    if changed_field == "rendered_non_thinking_hash":
        return replace(observed, rendered_non_thinking_hash="b" * 64)
    if changed_field == "vllm_identity":
        return replace(observed, vllm_identity=replace(observed.vllm_identity, wheel_hash="c" * 64))
    if changed_field == "image_identity":
        return replace(
            observed,
            image_identity=replace(observed.image_identity, digest="sha256:" + "d" * 64),
        )
    if changed_field == "serve_arguments":
        return replace(
            observed, serve_arguments=observed.serve_arguments + ("--disable-log-stats",)
        )
    if changed_field == "health_check":
        return replace(
            observed,
            health_check=replace(observed.health_check, response_hash="e" * 64),
        )
    raise AssertionError(f"unknown changed field: {changed_field}")


@pytest.mark.parametrize(
    "changed_field",
    [
        "git_commit",
        "git_dirty",
        "os_release",
        "kernel",
        "gpu",
        "driver_version",
        "reported_cuda_version",
        "python_version",
        "package_lock",
        "model_artifacts",
        "tokenizer_artifacts",
        "chat_template_text",
        "rendered_non_thinking_hash",
        "vllm_identity",
        "image_identity",
        "serve_arguments",
        "health_check",
    ],
)
def test_environment_lock_rejects_every_observed_drift(changed_field: str) -> None:
    lock, observed = valid_environment_lock_and_observation()
    changed = mutate_observation(observed, changed_field)

    with pytest.raises(EnvironmentDriftError, match=changed_field):
        verify_current_environment(lock, changed)


def test_environment_lock_round_trip_recomputes_nested_hashes() -> None:
    lock, _ = valid_environment_lock_and_observation()

    assert EnvironmentLock.from_payload(lock.to_payload()) == lock
    assert lock.record_hash == canonical_payload_hash(lock.payload_without_record_hash())

    payload = lock.to_payload()
    payload["package_lock_hash"] = "f" * 64
    payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in payload.items() if key != "record_hash"}
    )
    with pytest.raises(ValueError, match="package_lock_hash"):
        EnvironmentLock.from_payload(payload)


def test_environment_lock_canonicalizes_unordered_collections() -> None:
    observed = valid_observation()
    reversed_observation = replace(
        observed,
        package_lock=tuple(reversed(observed.package_lock)),
        model_artifacts=tuple(reversed(observed.model_artifacts)),
    )

    assert EnvironmentLock.create(reversed_observation) == EnvironmentLock.create(observed)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: replace(
                value,
                package_lock=value.package_lock + (PackageEntry(name="Torch", version="2.8.0"),),
            ),
            "duplicate package",
        ),
        (
            lambda value: replace(
                value,
                model_artifacts=value.model_artifacts
                + (
                    ArtifactEntry(
                        relative_path="model-00001-of-00005.safetensors",
                        byte_size=1,
                        sha256="1" * 64,
                    ),
                ),
            ),
            "duplicate artifact",
        ),
        (
            lambda value: replace(
                value,
                model_artifacts=(
                    ArtifactEntry(
                        relative_path="linked.safetensors",
                        byte_size=1,
                        sha256="1" * 64,
                        is_symlink=True,
                    ),
                ),
            ),
            "symlink",
        ),
        (lambda value: replace(value, model_revision="main"), "exact revision"),
        (
            lambda value: replace(
                value,
                serve_arguments=value.serve_arguments + ("--api-key=hf_secret",),
            ),
            "secret",
        ),
        (
            lambda value: replace(
                value,
                health_check=replace(
                    value.health_check,
                    endpoint="http://0.0.0.0:8000/health",
                ),
            ),
            "loopback",
        ),
        (
            lambda value: replace(
                value,
                health_check=replace(value.health_check, status_code=500),
            ),
            "healthy HTTP 200",
        ),
        (
            lambda value: replace(value, git_dirty=True, archived_diff_hash=None),
            "archived_diff_hash",
        ),
    ],
)
def test_environment_lock_rejects_unsafe_observations(mutation, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        EnvironmentLock.create(mutation(valid_observation()))


def test_environment_lock_rejects_secret_in_any_bound_text() -> None:
    observed = valid_observation()
    text = "{{ messages }} api_key=do-not-archive"

    with pytest.raises(ValueError, match="secret"):
        EnvironmentLock.create(
            replace(
                observed,
                chat_template_text=text,
                chat_template_hash=canonical_payload_hash(text),
            )
        )


def test_environment_lock_requires_typed_observation_and_exact_payload() -> None:
    with pytest.raises(TypeError, match="EnvironmentObservation"):
        EnvironmentLock.create({})  # type: ignore[arg-type]

    payload = EnvironmentLock.create(valid_observation()).to_payload()
    payload["extra"] = "not allowed"
    with pytest.raises(ValueError, match="exact fields"):
        EnvironmentLock.from_payload(payload)
