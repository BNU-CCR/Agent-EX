"""The separately authorized ten-prompt real-model smoke gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agent_ex.calibration.cloud import SmokeManifest
from agent_ex.calibration.contracts import ProbeRuntimePolicy
from agent_ex.calibration.smoke import (
    SMOKE_PROMPT_SET_HASH,
    SmokeFailure,
    SmokeResult,
    run_probe_smoke,
    smoke_prompt_payload,
)
from agent_ex.domain import canonical_payload_hash
from test_calibration_cloud import MODEL_REVISION, valid_preflight
from test_calibration_vllm_adapter import FakeVllmServer, adapter as vllm_adapter


SMOKE_DRAFT = Path(__file__).parents[1] / "configs" / "paper1" / "phase0a1-smoke.draft.yaml"


def runtime_policy() -> ProbeRuntimePolicy:
    return ProbeRuntimePolicy.create(
        policy_id="phase0a1-smoke-runtime",
        retryable_error_codes=("connection_error", "timeout"),
        nonretryable_error_codes=("oom", "provider_fatal"),
        max_transport_attempts_by_code={
            "connection_error": 1,
            "timeout": 1,
            "oom": 1,
            "provider_fatal": 1,
        },
        timeout_seconds=3.0,
        obey_retry_after=False,
        backoff_seconds=(),
    )


def manifest(
    archive_root: Path,
    *,
    prompt_hash: str = SMOKE_PROMPT_SET_HASH,
    policy_hash: str | None = None,
) -> SmokeManifest:
    return SmokeManifest.create(
        preflight_hash=valid_preflight().record_hash,
        model_repository="Qwen/Qwen3-8B",
        model_revision_candidate=MODEL_REVISION,
        tokenizer_revision_candidate=MODEL_REVISION,
        vllm_version_candidate="0.23.0",
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        served_model_name="qwen3-8b-paper1",
        chat_template_hash=canonical_payload_hash("qwen3-non-thinking-chat-template"),
        runtime_policy_hash=policy_hash or runtime_policy().record_hash,
        smoke_prompt_set_hash=prompt_hash,
        credential_boundary_hash="4" * 64,
        archive_uri=archive_root.resolve().as_posix(),
    )


def test_smoke_prompt_set_is_exactly_ten_and_hash_bound() -> None:
    payload = smoke_prompt_payload()

    assert len(payload) == 10
    assert canonical_payload_hash(payload) == SMOKE_PROMPT_SET_HASH
    assert {item["smoke_id"] for item in payload} == {
        "valid-json-a",
        "valid-json-b",
        "field-order",
        "malformed-instruction",
        "neutral-refusal",
        "short-max-token",
        "seed-replay-a",
        "seed-replay-b",
        "unicode-chinese",
        "service-identity-recovery",
    }


def test_smoke_draft_retains_exact_fail_closed_markers() -> None:
    payload = yaml.safe_load(SMOKE_DRAFT.read_text(encoding="utf-8"))

    assert payload == {
        "schema_version": "paper1.calibration.smoke-manifest.v1",
        "metadata": {
            "calibration_only": True,
            "formal_parameter_authority": False,
        },
        "model_revision_candidate": MODEL_REVISION,
        "tokenizer_revision_candidate": MODEL_REVISION,
        "vllm_version_candidate": "0.23.0",
        "runtime_policy_hash": "UNRESOLVED[P1_TIMEOUT_RETRY]",
        "credential_boundary_hash": ("REPLACE_WITH_APPROVED_64_HEX_CREDENTIAL_BOUNDARY_HASH"),
        "archive_uri": "UNRESOLVED[P1_DATA_ARCHIVE_URI]",
    }


def test_smoke_never_loads_probe_case_inventory(tmp_path: Path) -> None:
    server = FakeVllmServer(port=8000)
    try:
        result = run_probe_smoke(
            manifest(tmp_path / "smoke"),
            vllm_adapter(server.endpoint),
            tmp_path / "smoke",
            runtime_policy(),
        )
    finally:
        server.close()

    assert result.case_count == 0
    assert result.smoke_prompt_count == 10
    assert result.status == "passed"
    assert not any((tmp_path / "smoke").rglob("case-inventory.json"))


def test_smoke_fails_when_thinking_content_is_observed(tmp_path: Path) -> None:
    server = FakeVllmServer(port=8000)
    payload = json.loads(server.body)
    payload["choices"][0]["message"]["content"] = (
        '<think>hidden</think>{"stance":4,"confidence":3,"public_reason":"x"}'
    )
    server.body = json.dumps(payload).encode("utf-8")
    try:
        with pytest.raises(SmokeFailure, match="non-thinking"):
            run_probe_smoke(
                manifest(tmp_path / "smoke"),
                vllm_adapter(server.endpoint),
                tmp_path / "smoke",
                runtime_policy(),
            )
    finally:
        server.close()


def test_smoke_rejects_prompt_hash_or_archive_drift_before_call(tmp_path: Path) -> None:
    server = FakeVllmServer(port=8000)
    try:
        with pytest.raises(ValueError, match="prompt set hash"):
            run_probe_smoke(
                manifest(tmp_path / "smoke", prompt_hash="9" * 64),
                vllm_adapter(server.endpoint),
                tmp_path / "smoke",
                runtime_policy(),
            )
        assert server.requests == []

        with pytest.raises(ValueError, match="archive"):
            run_probe_smoke(
                manifest(tmp_path / "approved"),
                vllm_adapter(server.endpoint),
                tmp_path / "different",
                runtime_policy(),
            )
        assert server.requests == []
    finally:
        server.close()


def test_smoke_rejects_runtime_policy_drift_before_call(tmp_path: Path) -> None:
    server = FakeVllmServer(port=8000)
    try:
        with pytest.raises(ValueError, match="runtime policy"):
            run_probe_smoke(
                manifest(tmp_path / "smoke", policy_hash="9" * 64),
                vllm_adapter(server.endpoint),
                tmp_path / "smoke",
                runtime_policy(),
            )
        assert server.requests == []
    finally:
        server.close()


def test_smoke_result_round_trip_is_strict(tmp_path: Path) -> None:
    server = FakeVllmServer(port=8000)
    try:
        result = run_probe_smoke(
            manifest(tmp_path / "smoke"),
            vllm_adapter(server.endpoint),
            tmp_path / "smoke",
            runtime_policy(),
        )
    finally:
        server.close()

    assert SmokeResult.from_payload(result.to_payload()) == result
    payload = result.to_payload()
    payload["status"] = "failed"
    with pytest.raises(ValueError, match="status|record_hash"):
        SmokeResult.from_payload(payload)


def test_smoke_detects_reasoning_content_in_raw_transport(tmp_path: Path) -> None:
    server = FakeVllmServer(port=8000)
    payload = json.loads(server.body)
    payload["choices"][0]["message"]["reasoning_content"] = "hidden"
    server.body = json.dumps(payload).encode("utf-8")
    try:
        with pytest.raises(SmokeFailure, match="non-thinking"):
            run_probe_smoke(
                manifest(tmp_path / "smoke"),
                vllm_adapter(server.endpoint),
                tmp_path / "smoke",
                runtime_policy(),
            )
    finally:
        server.close()
