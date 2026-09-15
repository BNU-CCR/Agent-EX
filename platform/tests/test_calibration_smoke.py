"""The separately authorized ten-prompt real-model smoke gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agent_ex.calibration import smoke as smoke_module
from agent_ex.calibration.cloud import SmokeManifest
from agent_ex.calibration.contracts import ProbeRuntimePolicy
from agent_ex.calibration.environment import EnvironmentLock
from agent_ex.calibration.smoke import (
    SMOKE_PROMPT_SET_HASH,
    SmokeFailure,
    SmokeProgress,
    SmokeResult,
    ServiceStopEvidence,
    finalize_probe_smoke,
    mark_smoke_service_stopped,
    run_smoke_diagnostics,
    run_smoke_phase_one,
    run_smoke_phase_two,
    smoke_prompt_payload,
)
from agent_ex.calibration.store import ProbeRunStore
from agent_ex.calibration.transport_diagnostics import (
    DiagnosticCase,
    TransportDiagnosticEvidence,
)
from agent_ex.domain import canonical_payload_hash
from test_calibration_cloud import MODEL_REVISION, valid_preflight
from test_calibration_environment import valid_observation
from test_calibration_vllm_adapter import FakeVllmServer, adapter as vllm_adapter


SMOKE_DRAFT = Path(__file__).parents[1] / "configs" / "paper1" / "phase0a1-smoke.draft.yaml"


def runtime_policy() -> ProbeRuntimePolicy:
    retryable = ("provider_busy", "provider_unreachable", "timeout")
    nonretryable = (
        "oom",
        "provider_fatal",
        "provider_invalid_json",
        "provider_redirect",
        "provider_response_too_large",
        "provider_schema_error",
    )
    return ProbeRuntimePolicy.create(
        policy_id="phase0a1-smoke-runtime-v1",
        retryable_error_codes=retryable,
        nonretryable_error_codes=nonretryable,
        max_transport_attempts_by_code={code: 1 for code in retryable + nonretryable},
        timeout_seconds=3.0,
        obey_retry_after=False,
        backoff_seconds=(),
    )


def environment_lock_for_smoke(approved: SmokeManifest) -> EnvironmentLock:
    return EnvironmentLock.create(valid_observation(), authorization_hash=approved.record_hash)


@pytest.fixture(autouse=True)
def deterministic_smoke_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_diagnostics(**_: object) -> tuple[TransportDiagnosticEvidence, ...]:
        cases = (
            DiagnosticCase.closed_port(port=65431, timeout_seconds=3.0),
            DiagnosticCase.controlled_timeout(port=65432, timeout_seconds=3.0),
            DiagnosticCase.http_429(port=65433, timeout_seconds=3.0),
        )
        raw = (
            ({}, b"", "ConnectionRefusedError", None),
            ({}, b"", "TimeoutError", None),
            ({"retry-after": "17"}, b"busy", None, 429),
        )
        return tuple(
            TransportDiagnosticEvidence.create(
                case=case,
                actual_error_code=case.expected_error_code,
                started_at="2026-09-15T00:00:00Z",
                ended_at="2026-09-15T00:00:01Z",
                duration_seconds=1.0,
                response_headers=headers,
                raw_body=body,
                raw_error=error,
                http_status=status,
            )
            for case, (headers, body, error, status) in zip(cases, raw, strict=True)
        )

    monkeypatch.setattr(smoke_module, "run_transport_diagnostics", fake_diagnostics)


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


def valid_smoke_progress(
    *,
    sequence: int = 1,
    phase: str = "ready",
    completed_ordinals: tuple[int, ...] = (),
    manifest_hash: str = "a" * 64,
    environment_lock_hash: str = "b" * 64,
    previous_progress_hash: str | None = None,
) -> SmokeProgress:
    smoke_ids = tuple(item["smoke_id"] for item in smoke_prompt_payload())
    completed_count = len(completed_ordinals)
    stop_hash = (
        "d" * 64 if phase in {"service_stopped", "phase_two_complete", "finalized"} else None
    )
    return SmokeProgress.create(
        manifest_hash=manifest_hash,
        environment_lock_hash=environment_lock_hash,
        sequence=sequence,
        phase=phase,
        completed_ordinals=completed_ordinals,
        pending_smoke_ids=smoke_ids[completed_count:],
        attempt_hashes=tuple(f"{ordinal:x}" * 64 for ordinal in completed_ordinals),
        service_stop_evidence_hash=stop_hash,
        previous_progress_hash=(None if sequence == 1 else previous_progress_hash or "e" * 64),
    )


def valid_service_stop_evidence(
    *, manifest_hash: str = "a" * 64, environment_lock_hash: str = "b" * 64
) -> ServiceStopEvidence:
    return ServiceStopEvidence.create(
        manifest_hash=manifest_hash,
        environment_lock_hash=environment_lock_hash,
        service_start_identity_hash="c" * 64,
        pid=1234,
        process_exit_observed=True,
        loopback_listener_absent=True,
        stopped_at="2026-09-15T00:00:00Z",
    )


def test_smoke_progress_round_trip_is_strict_and_hash_chained() -> None:
    progress = valid_smoke_progress()

    assert SmokeProgress.from_payload(progress.to_payload()) == progress
    with pytest.raises(ValueError, match="phase shape"):
        SmokeProgress.create(
            manifest_hash="a" * 64,
            environment_lock_hash="b" * 64,
            sequence=1,
            phase="ready",
            completed_ordinals=(1,),
            pending_smoke_ids=tuple(item["smoke_id"] for item in smoke_prompt_payload())[1:],
            attempt_hashes=("1" * 64,),
            service_stop_evidence_hash=None,
            previous_progress_hash=None,
        )


def test_service_stop_evidence_requires_observed_stop_and_round_trips() -> None:
    evidence = valid_service_stop_evidence()

    assert ServiceStopEvidence.from_payload(evidence.to_payload()) == evidence
    with pytest.raises(ValueError, match="observed process exit"):
        ServiceStopEvidence.create(
            manifest_hash="a" * 64,
            environment_lock_hash="b" * 64,
            service_start_identity_hash="c" * 64,
            pid=1234,
            process_exit_observed=False,
            loopback_listener_absent=True,
            stopped_at="2026-09-15T00:00:00Z",
        )


def test_smoke_runs_nine_then_only_recovery_after_reopen(tmp_path: Path) -> None:
    run_root = tmp_path / "smoke"
    policy = runtime_policy()
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)

    diagnostics = run_smoke_diagnostics(
        approved,
        lock,
        run_root,
        policy,
        current_observation=valid_observation(),
    )
    assert diagnostics.phase == "diagnostics_complete"

    first_server = FakeVllmServer(port=8000)
    try:
        first = run_smoke_phase_one(
            approved,
            lock,
            vllm_adapter(first_server.endpoint),
            run_root,
            policy,
            current_observation=valid_observation(),
        )
    finally:
        first_server.close()
    assert len(first_server.requests) == 9
    assert first.phase == "phase_one_complete"

    stop_evidence = valid_service_stop_evidence(
        manifest_hash=approved.record_hash,
        environment_lock_hash=lock.record_hash,
    )
    stopped = mark_smoke_service_stopped(approved, lock, run_root, stop_evidence=stop_evidence)
    assert stopped.phase == "service_stopped"

    second_server = FakeVllmServer(port=8000)
    try:
        second = run_smoke_phase_two(
            approved,
            lock,
            vllm_adapter(second_server.endpoint),
            run_root,
            policy,
            current_observation=valid_observation(),
        )
        result = finalize_probe_smoke(
            approved,
            lock,
            run_root,
            current_observation=valid_observation(),
        )
    finally:
        second_server.close()

    assert second.phase == "phase_two_complete"
    assert len(second_server.requests) == 1
    request = second_server.requests[0]["body"]
    assert request["messages"][1]["content"].startswith("After the client recovery boundary")
    assert result.smoke_prompt_count == 10
    assert len(result.attempt_hashes) == 10
    assert not any(run_root.rglob("case-inventory.json"))
    store = ProbeRunStore.open(run_root)
    assert store.load_smoke_progress()[-1].phase == "finalized"


@pytest.mark.parametrize(
    "operation",
    ("phase_two_before_stop", "phase_one_twice", "stop_before_nine", "finalize_before_ten"),
)
def test_smoke_rejects_duplicate_skip_or_early_finalize(tmp_path: Path, operation: str) -> None:
    run_root = tmp_path / operation
    policy = runtime_policy()
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)
    run_smoke_diagnostics(approved, lock, run_root, policy, current_observation=valid_observation())

    if operation == "phase_one_twice":
        server = FakeVllmServer(port=8000)
        try:
            run_smoke_phase_one(
                approved,
                lock,
                vllm_adapter(server.endpoint),
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        finally:
            server.close()

    stop = valid_service_stop_evidence(
        manifest_hash=approved.record_hash,
        environment_lock_hash=lock.record_hash,
    )
    adapter = vllm_adapter(approved.endpoint)
    with pytest.raises((RuntimeError, ValueError), match="phase|attempt|stop|final"):
        if operation == "phase_two_before_stop":
            run_smoke_phase_two(
                approved,
                lock,
                adapter,
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        elif operation == "phase_one_twice":
            run_smoke_phase_one(
                approved,
                lock,
                adapter,
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        elif operation == "stop_before_nine":
            mark_smoke_service_stopped(approved, lock, run_root, stop_evidence=stop)
        else:
            finalize_probe_smoke(
                approved,
                lock,
                run_root,
                current_observation=valid_observation(),
            )


@pytest.mark.parametrize("operation", ("diagnostics", "phase_one", "mark", "phase_two", "finalize"))
def test_every_smoke_transition_rejects_wrong_authorization(tmp_path: Path, operation: str) -> None:
    run_root = tmp_path / operation
    policy = runtime_policy()
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)
    wrong_lock = EnvironmentLock.create(valid_observation(), authorization_hash="f" * 64)
    if operation != "diagnostics":
        run_smoke_diagnostics(
            approved, lock, run_root, policy, current_observation=valid_observation()
        )
    if operation in {"mark", "phase_two", "finalize"}:
        server = FakeVllmServer(port=8000)
        try:
            run_smoke_phase_one(
                approved,
                lock,
                vllm_adapter(server.endpoint),
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        finally:
            server.close()
    stop = valid_service_stop_evidence(
        manifest_hash=approved.record_hash,
        environment_lock_hash=lock.record_hash,
    )
    if operation in {"phase_two", "finalize"}:
        mark_smoke_service_stopped(approved, lock, run_root, stop_evidence=stop)
    if operation == "finalize":
        server = FakeVllmServer(port=8000)
        try:
            run_smoke_phase_two(
                approved,
                lock,
                vllm_adapter(server.endpoint),
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        finally:
            server.close()

    with pytest.raises(ValueError, match="authorization"):
        if operation == "diagnostics":
            run_smoke_diagnostics(
                approved,
                wrong_lock,
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        elif operation == "phase_one":
            run_smoke_phase_one(
                approved,
                wrong_lock,
                vllm_adapter(approved.endpoint),
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        elif operation == "mark":
            mark_smoke_service_stopped(approved, wrong_lock, run_root, stop_evidence=stop)
        elif operation == "phase_two":
            run_smoke_phase_two(
                approved,
                wrong_lock,
                vllm_adapter(approved.endpoint),
                run_root,
                policy,
                current_observation=valid_observation(),
            )
        else:
            finalize_probe_smoke(
                approved,
                wrong_lock,
                run_root,
                current_observation=valid_observation(),
            )


def test_one_shot_smoke_entry_point_is_disabled() -> None:
    with pytest.raises(RuntimeError, match="one-shot smoke is disabled"):
        smoke_module.run_probe_smoke(None, None, Path.cwd(), None)  # type: ignore[arg-type]


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


def test_smoke_fails_when_thinking_content_is_observed(tmp_path: Path) -> None:
    run_root = tmp_path / "smoke"
    policy = runtime_policy()
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)
    run_smoke_diagnostics(approved, lock, run_root, policy, current_observation=valid_observation())
    server = FakeVllmServer(port=8000)
    payload = json.loads(server.body)
    payload["choices"][0]["message"]["content"] = (
        '<think>hidden</think>{"stance":4,"confidence":3,"public_reason":"x"}'
    )
    server.body = json.dumps(payload).encode("utf-8")
    try:
        with pytest.raises(SmokeFailure, match="non-thinking"):
            run_smoke_phase_one(
                approved,
                lock,
                vllm_adapter(server.endpoint),
                run_root,
                policy,
                current_observation=valid_observation(),
            )
    finally:
        server.close()


def test_smoke_rejects_prompt_hash_or_archive_drift_before_call(tmp_path: Path) -> None:
    policy = runtime_policy()
    wrong_prompt = manifest(
        tmp_path / "smoke", prompt_hash="9" * 64, policy_hash=policy.record_hash
    )
    with pytest.raises(ValueError, match="prompt set hash"):
        run_smoke_diagnostics(
            wrong_prompt,
            environment_lock_for_smoke(wrong_prompt),
            tmp_path / "smoke",
            policy,
            current_observation=valid_observation(),
        )

    approved = manifest(tmp_path / "approved", policy_hash=policy.record_hash)
    with pytest.raises(ValueError, match="archive"):
        run_smoke_diagnostics(
            approved,
            environment_lock_for_smoke(approved),
            tmp_path / "different",
            policy,
            current_observation=valid_observation(),
        )


def test_smoke_rejects_runtime_policy_drift_before_call(tmp_path: Path) -> None:
    approved = manifest(tmp_path / "smoke", policy_hash="9" * 64)
    with pytest.raises(ValueError, match="runtime policy"):
        run_smoke_diagnostics(
            approved,
            environment_lock_for_smoke(approved),
            tmp_path / "smoke",
            runtime_policy(),
            current_observation=valid_observation(),
        )


def test_smoke_result_round_trip_is_strict(tmp_path: Path) -> None:
    attempts = tuple(f"{ordinal:x}" * 64 for ordinal in range(1, 11))
    observations = tuple({"smoke_id": item["smoke_id"]} for item in smoke_prompt_payload())
    content = {
        "schema_version": "paper1.calibration.smoke-result.v1",
        "status": "passed",
        "case_count": 0,
        "smoke_prompt_count": 10,
        "manifest_hash": "a" * 64,
        "prompt_set_hash": SMOKE_PROMPT_SET_HASH,
        "attempt_hashes": attempts,
        "observations": observations,
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    result = SmokeResult(
        status="passed",
        case_count=0,
        smoke_prompt_count=10,
        manifest_hash="a" * 64,
        prompt_set_hash=SMOKE_PROMPT_SET_HASH,
        attempt_hashes=attempts,
        observations=observations,
        record_hash=canonical_payload_hash(content),
    )

    assert SmokeResult.from_payload(result.to_payload()) == result
    payload = result.to_payload()
    payload["status"] = "failed"
    with pytest.raises(ValueError, match="status|record_hash"):
        SmokeResult.from_payload(payload)


def test_smoke_detects_reasoning_content_in_raw_transport(tmp_path: Path) -> None:
    run_root = tmp_path / "smoke"
    policy = runtime_policy()
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)
    run_smoke_diagnostics(approved, lock, run_root, policy, current_observation=valid_observation())
    server = FakeVllmServer(port=8000)
    payload = json.loads(server.body)
    payload["choices"][0]["message"]["reasoning_content"] = "hidden"
    server.body = json.dumps(payload).encode("utf-8")
    try:
        with pytest.raises(SmokeFailure, match="non-thinking"):
            run_smoke_phase_one(
                approved,
                lock,
                vllm_adapter(server.endpoint),
                run_root,
                policy,
                current_observation=valid_observation(),
            )
    finally:
        server.close()
