"""Deterministic non-model transport diagnostics for the real smoke gate."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest

from agent_ex.calibration.contracts import ProbeRuntimePolicy
from agent_ex.calibration.environment import EnvironmentLock
from agent_ex.calibration.transport_diagnostics import (
    DiagnosticCase,
    TransportDiagnosticEvidence,
    diagnostic_cases,
    run_transport_diagnostics,
)
from test_calibration_environment import valid_observation
from test_calibration_smoke import manifest


VLLM_ENDPOINT = "http://127.0.0.1:8000/v1/chat/completions"


def _runtime_policy(*, timeout_seconds: float = 0.02) -> ProbeRuntimePolicy:
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
        timeout_seconds=timeout_seconds,
        obey_retry_after=False,
        backoff_seconds=(),
    )


def test_diagnostic_cases_are_fixed_and_never_name_vllm() -> None:
    cases = diagnostic_cases(timeout_seconds=0.02)

    assert tuple(case.diagnostic_id for case in cases) == (
        "closed-port",
        "controlled-timeout",
        "http-429-retry-after",
    )
    assert tuple(case.expected_error_code for case in cases) == (
        "provider_unreachable",
        "timeout",
        "provider_busy",
    )
    assert all(case.endpoint != VLLM_ENDPOINT for case in cases)


def test_diagnostic_record_round_trip_rejects_classification_drift() -> None:
    case = DiagnosticCase.closed_port(port=65431)
    evidence = TransportDiagnosticEvidence.create(
        case=case,
        actual_error_code="provider_unreachable",
        started_at="2026-09-15T00:00:00Z",
        ended_at="2026-09-15T00:00:00Z",
        duration_seconds=0.0,
        response_headers={},
        raw_body=b"",
        raw_error="ConnectionRefusedError",
    )

    assert TransportDiagnosticEvidence.from_payload(evidence.to_payload()) == evidence
    with pytest.raises(ValueError, match="classification"):
        replace(evidence, actual_error_code="timeout")


def test_diagnostics_classify_once_without_model_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _runtime_policy()
    approved = manifest(tmp_path / "smoke", policy_hash=policy.record_hash)
    observation = valid_observation()
    lock = EnvironmentLock.create(observation, authorization_hash=approved.record_hash)

    if os.name == "nt":
        from agent_ex.calibration import transport_diagnostics

        real_connection = transport_diagnostics.HTTPConnection

        class WindowsClosedPortConnection:
            def __init__(self, host: str, port: int, timeout: float) -> None:
                self._delegate = real_connection(host, port, timeout=timeout)

            def request(self, method: str, path: str, **kwargs: object) -> None:
                if path == "/diagnostic/closed-port":
                    raise ConnectionRefusedError("controlled Windows closed-port refusal")
                self._delegate.request(method, path, **kwargs)

            def getresponse(self):  # type: ignore[no-untyped-def]
                return self._delegate.getresponse()

            def close(self) -> None:
                self._delegate.close()

        monkeypatch.setattr(transport_diagnostics, "HTTPConnection", WindowsClosedPortConnection)

    records = run_transport_diagnostics(
        manifest=approved,
        environment_lock=lock,
        current_observation=observation,
        policy=policy,
        vllm_endpoint=VLLM_ENDPOINT,
    )

    assert tuple(record.actual_error_code for record in records) == (
        "provider_unreachable",
        "timeout",
        "provider_busy",
    )
    assert records[2].http_status == 429
    assert records[2].response_headers["retry-after"] == "17"
    assert all(record.transport_attempt_count == 1 for record in records)
    assert all(record.model_request_count == 0 for record in records)


def test_diagnostics_reject_lock_not_authorized_by_manifest(tmp_path: Path) -> None:
    policy = _runtime_policy()
    approved = manifest(tmp_path / "smoke", policy_hash=policy.record_hash)
    observation = valid_observation()
    wrong_lock = EnvironmentLock.create(observation, authorization_hash="a" * 64)

    with pytest.raises(ValueError, match="authorization"):
        run_transport_diagnostics(
            manifest=approved,
            environment_lock=wrong_lock,
            current_observation=observation,
            policy=policy,
            vllm_endpoint=VLLM_ENDPOINT,
        )
