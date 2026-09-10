"""Strict Phase 0A-1 cloud authorization records."""

from __future__ import annotations

from copy import deepcopy

import pytest

from agent_ex.calibration.cloud import CloudPreflight, SmokeManifest


MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


def valid_preflight() -> CloudPreflight:
    return CloudPreflight.create(
        os_release="Ubuntu 22.04",
        kernel="5.15.0-78-generic",
        python_version="3.12.3",
        gpu_name="NVIDIA GeForce RTX 5090",
        gpu_memory_bytes=32_607 * 1024 * 1024,
        driver_version="595.71.05",
        reported_cuda_version="13.2",
        free_disk_bytes=150_000_000_000,
        git_commit="0" * 40,
        git_dirty=False,
    )


def valid_smoke_manifest() -> SmokeManifest:
    return SmokeManifest.create(
        preflight_hash=valid_preflight().record_hash,
        model_repository="Qwen/Qwen3-8B",
        model_revision_candidate=MODEL_REVISION,
        tokenizer_revision_candidate=MODEL_REVISION,
        vllm_version_candidate="0.23.0",
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        served_model_name="qwen3-8b-paper1",
        chat_template_hash="1" * 64,
        runtime_policy_hash="2" * 64,
        smoke_prompt_set_hash="3" * 64,
        credential_boundary_hash="4" * 64,
        archive_uri="/root/autodl-tmp/agent-ex/phase0a1/smoke",
    )


def test_cloud_preflight_round_trip_is_strict_and_non_authoritative() -> None:
    record = valid_preflight()

    assert CloudPreflight.from_payload(record.to_payload()) == record
    assert record.calibration_only is True
    assert record.formal_parameter_authority is False


def test_cloud_preflight_rejects_extra_fields_and_hash_drift() -> None:
    payload = valid_preflight().to_payload()
    payload["hostname"] = "unbound-host"
    with pytest.raises(ValueError, match="exact fields"):
        CloudPreflight.from_payload(payload)

    payload = valid_preflight().to_payload()
    payload["gpu_name"] = "different"
    with pytest.raises(ValueError, match="record_hash"):
        CloudPreflight.from_payload(payload)


@pytest.mark.parametrize("field", ["gpu_memory_bytes", "free_disk_bytes"])
def test_cloud_preflight_requires_positive_integer_sizes(field: str) -> None:
    payload = valid_preflight().to_payload()
    payload[field] = 0
    with pytest.raises(ValueError, match=field):
        CloudPreflight.from_payload(payload)


def test_smoke_manifest_round_trip_binds_candidates() -> None:
    manifest = valid_smoke_manifest()

    assert SmokeManifest.from_payload(manifest.to_payload()) == manifest
    assert manifest.calibration_only is True
    assert manifest.formal_parameter_authority is False


def test_smoke_manifest_cannot_reference_probe_inventory() -> None:
    payload = valid_smoke_manifest().to_payload()
    payload["case_inventory_hash"] = "0" * 64
    with pytest.raises(ValueError, match="exact fields"):
        SmokeManifest.from_payload(payload)


def test_smoke_manifest_binds_only_a_sanitized_credential_boundary_hash() -> None:
    payload = valid_smoke_manifest().to_payload()
    assert len(payload["credential_boundary_hash"]) == 64
    assert not ({"credential", "token", "api_key", "secret"} & payload.keys())
    payload["credential_boundary_hash"] = "not-a-hash"
    with pytest.raises(ValueError, match="credential_boundary_hash"):
        SmokeManifest.from_payload(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("endpoint", "http://0.0.0.0:8000/v1/chat/completions", "endpoint"),
        ("model_revision_candidate", "0" * 40, "model revision"),
        ("tokenizer_revision_candidate", "0" * 40, "tokenizer revision"),
        ("vllm_version_candidate", "0.22.0", "vLLM"),
    ],
)
def test_smoke_manifest_rejects_candidate_identity_drift(
    field: str, value: str, message: str
) -> None:
    payload = deepcopy(valid_smoke_manifest().to_payload())
    payload[field] = value
    payload["record_hash"] = "0" * 64
    with pytest.raises(ValueError, match=message):
        SmokeManifest.from_payload(payload)


def test_smoke_manifest_rejects_unresolved_executable_fields() -> None:
    payload = valid_smoke_manifest().to_payload()
    payload["archive_uri"] = "UNRESOLVED[P1_DATA_ARCHIVE_URI]"
    payload["record_hash"] = "0" * 64
    with pytest.raises(ValueError, match="UNRESOLVED"):
        SmokeManifest.from_payload(payload)
