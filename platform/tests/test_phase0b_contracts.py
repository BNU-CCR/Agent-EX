from __future__ import annotations

from copy import deepcopy

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.mock_matrix import CANONICAL_CELL_IDS
from agent_ex.phase0b import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
    DiagnosticTerminalReport,
)


SHA = "a" * 64
ARTIFACT_KEYS = (
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
)


def _policy() -> DiagnosticAttemptPolicy:
    return DiagnosticAttemptPolicy.create(
        connect_timeout_seconds=10.0,
        read_timeout_seconds=120.0,
        total_timeout_seconds=180.0,
        retryable_error_codes=("provider_busy", "transport_timeout"),
        max_same_event_retries=1,
    )


def _binding() -> DiagnosticAdapterBinding:
    return DiagnosticAdapterBinding.create(
        model_repository="Qwen/Qwen3-8B",
        model_revision="b" * 40,
        tokenizer_revision="b" * 40,
        chat_template_hash=SHA,
        vllm_version="0.23.0",
        package_lock_hash=SHA,
        image_identity_hash=SHA,
        environment_lock_hash=SHA,
        service_start_identity_hash=SHA,
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        served_model_name="qwen3-8b-paper1",
    )


def _authorization() -> DiagnosticRunAuthorization:
    return DiagnosticRunAuthorization.create(
        cell_ids=CANONICAL_CELL_IDS,
        artifact_hashes={key: SHA for key in ARTIFACT_KEYS},
        feed_capacity_candidate=6,
        feed_capacity_research_qa_id="P1_MAX_NEIGHBORS",
        memory_window_candidate=3,
        memory_window_research_qa_id="P1_MEMORY_WINDOW",
        adapter_binding_hash=_binding().record_hash,
        attempt_policy_hash=_policy().record_hash,
        source_commit="c" * 40,
        source_dirty=False,
        source_diff_hash=None,
        temperature=0.7,
        top_p=0.8,
        max_tokens=128,
        enable_thinking=False,
        matched_seed=20260920,
        model_seed_pairing_rule="sha256-v1:matched-seed+cell-id+event-id",
        disk_budget_bytes=20_000_000_000,
        token_budget=200_000,
        wall_clock_limit_seconds=7200,
        checkpoint_cadence="completed_sweep_and_cell",
        archive_uri="/root/autodl-tmp/agent-ex-phase0b-n20-t2-v1",
        forbidden_claims=(
            "causal_estimate",
            "formal_experiment",
            "independent_agent_replicates",
            "inferential_statistics",
            "parameter_freeze",
            "primary_result",
        ),
    )


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    return payload


def test_contracts_round_trip_with_content_addresses() -> None:
    policy = _policy()
    binding = _binding()
    authorization = _authorization()

    assert DiagnosticAttemptPolicy.from_payload(policy.to_payload()) == policy
    assert DiagnosticAdapterBinding.from_payload(binding.to_payload()) == binding
    restored = DiagnosticRunAuthorization.from_payload(authorization.to_payload())
    assert restored == authorization
    assert restored.record_hash == canonical_payload_hash(restored.content_payload())
    assert restored.calibration_only is True
    assert restored.formal_parameter_authority is False
    assert restored.research_parameter_status == "not_frozen"
    assert restored.input_artifact_mode == "synthetic_phase4b_candidate"
    assert restored.model_execution_mode == "real_qwen_vllm"


@pytest.mark.parametrize("contract", [_policy, _binding, _authorization])
def test_contracts_reject_missing_record_hash(contract: object) -> None:
    value = contract()  # type: ignore[operator]
    payload = value.to_payload()
    payload.pop("record_hash")

    with pytest.raises(ValueError, match="exact fields|record_hash"):
        type(value).from_payload(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("cell_ids", list(reversed(CANONICAL_CELL_IDS)), "canonical.*12|cell"),
        ("expected_event_count", 479, "480"),
        ("max_transport_count", 961, "960"),
        ("formal_parameter_authority", True, "formal parameter authority"),
        ("research_parameter_status", "frozen", "not_frozen"),
        ("feed_capacity_candidate", 5, "approved.*B|feed capacity"),
        ("memory_window_candidate", 4, "approved.*K|memory window"),
        ("archive_uri", "platform/results/run-1", "outside Git|archive"),
        ("model_seed_pairing_rule", "UNRESOLVED[P1_MODEL_SEED]", "UNRESOLVED"),
    ],
)
def test_authorization_rejects_non_diagnostic_or_unapproved_values(
    field: str, value: object, message: str
) -> None:
    payload = deepcopy(_authorization().to_payload())
    payload[field] = value
    _rehash(payload)

    with pytest.raises(ValueError, match=message):
        DiagnosticRunAuthorization.from_payload(payload)


def test_authorization_rejects_missing_artifact_hash() -> None:
    payload = deepcopy(_authorization().to_payload())
    artifact_hashes = payload["artifact_hashes"]
    assert isinstance(artifact_hashes, dict)
    artifact_hashes.pop("schedule")
    _rehash(payload)

    with pytest.raises(ValueError, match="artifact hashes"):
        DiagnosticRunAuthorization.from_payload(payload)


def test_authorization_rejects_unresolved_nested_value() -> None:
    payload = deepcopy(_authorization().to_payload())
    artifact_hashes = payload["artifact_hashes"]
    assert isinstance(artifact_hashes, dict)
    artifact_hashes["topic"] = "UNRESOLVED[P1_TOPIC]"
    _rehash(payload)

    with pytest.raises(ValueError, match="UNRESOLVED"):
        DiagnosticRunAuthorization.from_payload(payload)


def test_authorization_rejects_archive_path_traversal() -> None:
    payload = deepcopy(_authorization().to_payload())
    payload["archive_uri"] = "/root/autodl-tmp/../Agent ex/platform/results"
    _rehash(payload)

    with pytest.raises(ValueError, match="archive.*normalized|outside Git"):
        DiagnosticRunAuthorization.from_payload(payload)


@pytest.mark.parametrize("field", ["matched_seed_count", "agent_count", "sweep_count"])
def test_authorization_rejects_boolean_inventory_counts(field: str) -> None:
    payload = deepcopy(_authorization().to_payload())
    payload[field] = True
    _rehash(payload)

    with pytest.raises((TypeError, ValueError), match="strict integer|inventory"):
        DiagnosticRunAuthorization.from_payload(payload)


@pytest.mark.parametrize(
    "archive_uri",
    [
        "s3://user:secret@agent-ex-results/runs/run-1",
        "s3://agent-ex-results",
    ],
)
def test_authorization_rejects_unsafe_external_archive_uri(archive_uri: str) -> None:
    payload = deepcopy(_authorization().to_payload())
    payload["archive_uri"] = archive_uri
    _rehash(payload)

    with pytest.raises(ValueError, match="external archive"):
        DiagnosticRunAuthorization.from_payload(payload)


def test_attempt_policy_rejects_boolean_retry_count() -> None:
    payload = deepcopy(_policy().to_payload())
    payload["max_same_event_retries"] = True
    _rehash(payload)

    with pytest.raises((TypeError, ValueError), match="integer|retry"):
        DiagnosticAttemptPolicy.from_payload(payload)


def test_adapter_binding_rejects_endpoint_query() -> None:
    payload = deepcopy(_binding().to_payload())
    payload["endpoint"] += "?token=secret"
    _rehash(payload)

    with pytest.raises(ValueError, match="exact loopback"):
        DiagnosticAdapterBinding.from_payload(payload)


def test_adapter_binding_rejects_other_model_repository() -> None:
    payload = deepcopy(_binding().to_payload())
    payload["model_repository"] = "Other/Qwen3-8B"
    _rehash(payload)

    with pytest.raises(ValueError, match="model_repository|Qwen/Qwen3-8B"):
        DiagnosticAdapterBinding.from_payload(payload)


def test_terminal_report_skeleton_is_content_addressed_and_fail_closed() -> None:
    authorization = _authorization()
    report = DiagnosticTerminalReport.create(
        authorization_hash=authorization.record_hash,
        terminal_status="complete",
        completed_cell_ids=CANONICAL_CELL_IDS,
        committed_event_count=480,
        transport_count=480,
        unresolved_dispatch_count=0,
        final_projection_hash=SHA,
    )

    assert DiagnosticTerminalReport.from_payload(report.to_payload()) == report
    assert report.record_hash == canonical_payload_hash(report.content_payload())

    payload = report.to_payload()
    payload["committed_event_count"] = 479
    _rehash(payload)
    with pytest.raises(ValueError, match="complete.*480|480.*complete"):
        DiagnosticTerminalReport.from_payload(payload)


def test_complete_terminal_report_requires_one_transport_per_commit() -> None:
    report = DiagnosticTerminalReport.create(
        authorization_hash=_authorization().record_hash,
        terminal_status="complete",
        completed_cell_ids=CANONICAL_CELL_IDS,
        committed_event_count=480,
        transport_count=480,
        unresolved_dispatch_count=0,
        final_projection_hash=SHA,
    )
    payload = report.to_payload()
    payload["transport_count"] = 479
    _rehash(payload)

    with pytest.raises(ValueError, match="transport_count.*committed"):
        DiagnosticTerminalReport.from_payload(payload)


def test_incomplete_terminal_report_requires_one_transport_per_commit() -> None:
    report = DiagnosticTerminalReport.create(
        authorization_hash=_authorization().record_hash,
        terminal_status="terminal_incomplete",
        completed_cell_ids=CANONICAL_CELL_IDS[:2],
        committed_event_count=80,
        transport_count=80,
        unresolved_dispatch_count=1,
        final_projection_hash=SHA,
    )
    payload = report.to_payload()
    payload["transport_count"] = 79
    _rehash(payload)

    with pytest.raises(ValueError, match="transport_count.*committed"):
        DiagnosticTerminalReport.from_payload(payload)


def test_incomplete_terminal_report_requires_canonical_cell_prefix() -> None:
    with pytest.raises(ValueError, match="canonical.*prefix"):
        DiagnosticTerminalReport.create(
            authorization_hash=_authorization().record_hash,
            terminal_status="terminal_incomplete",
            completed_cell_ids=(CANONICAL_CELL_IDS[1],),
            committed_event_count=40,
            transport_count=40,
            unresolved_dispatch_count=0,
            final_projection_hash=SHA,
        )


@pytest.mark.parametrize("committed_event_count", [79, 120])
def test_incomplete_terminal_report_binds_forty_events_per_completed_cell(
    committed_event_count: int,
) -> None:
    with pytest.raises(ValueError, match="40.*completed cell|completed cell.*40"):
        DiagnosticTerminalReport.create(
            authorization_hash=_authorization().record_hash,
            terminal_status="terminal_incomplete",
            completed_cell_ids=CANONICAL_CELL_IDS[:2],
            committed_event_count=committed_event_count,
            transport_count=committed_event_count,
            unresolved_dispatch_count=0,
            final_projection_hash=SHA,
        )


def test_incomplete_terminal_report_rejects_all_twelve_completed_cells() -> None:
    with pytest.raises(ValueError, match="incomplete.*12|12.*incomplete"):
        DiagnosticTerminalReport.create(
            authorization_hash=_authorization().record_hash,
            terminal_status="terminal_incomplete",
            completed_cell_ids=CANONICAL_CELL_IDS,
            committed_event_count=480,
            transport_count=480,
            unresolved_dispatch_count=0,
            final_projection_hash=SHA,
        )


def test_incomplete_terminal_report_rejects_multiple_unresolved_dispatches() -> None:
    with pytest.raises(ValueError, match="unresolved_dispatch_count|single"):
        DiagnosticTerminalReport.create(
            authorization_hash=_authorization().record_hash,
            terminal_status="terminal_incomplete",
            completed_cell_ids=CANONICAL_CELL_IDS[:2],
            committed_event_count=80,
            transport_count=82,
            unresolved_dispatch_count=2,
            final_projection_hash=SHA,
        )
