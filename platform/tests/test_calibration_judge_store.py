from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from agent_ex.calibration.judge_contracts import JudgeExecutionManifest
from agent_ex.calibration.judge_runner import (
    AmbiguousJudgeDispatchError,
    JudgeDispatchIntent,
    JudgeDispatchReconciliation,
    reconstruct_judge_projection,
)
from agent_ex.calibration.judge_store import JudgeRunStore
from agent_ex.domain import canonical_payload_hash


SHA = "a" * 64


def manifest() -> JudgeExecutionManifest:
    values: dict[str, object] = {
        "run_id": "judge-run-test",
        "authorization_hash": SHA,
        "review_bundle_hash": SHA,
        "export_hash": SHA,
        "judge_pack_hash": SHA,
        "judge_pack_index_hash": SHA,
        "judge_coder_contract_hash": SHA,
        "old_judge_prompt_hash": SHA,
        "renderer_hash": SHA,
        "ordering_policy_hash": SHA,
        "classifier_contract_hash": SHA,
        "environment_lock_hash": SHA,
        "preflight_hash": SHA,
        "service_start_identity_hash": SHA,
        "runner_view_hash": SHA,
        "old_environment_lock_hash": SHA,
        "model_id": "Qwen/Qwen3-8B",
        "model_revision": "revision",
        "model_artifacts_hash": SHA,
        "tokenizer_hash": SHA,
        "tokenizer_id": "Qwen/Qwen3-8B",
        "tokenizer_revision": "revision",
        "tokenizer_artifacts_hash": SHA,
        "chat_template_hash": SHA,
        "runtime_version": "0.10.2",
        "non_thinking": True,
        "generation_settings": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 512},
        "connect_timeout_seconds": 10.0,
        "read_timeout_seconds": 120.0,
        "total_timeout_seconds": 120.0,
        "retryable_codes": ["timeout", "parse_invalid_json"],
        "retry_backoff_seconds": [0.0, 1.0],
        "max_attempts_per_item": 3,
        "one_item_per_request": True,
        "strict_approved_order": True,
        "archive_uri": "file:///root/autodl-tmp/phase0a1/judge-test",
        "source_commit": "1" * 40,
        "expected_item_count": 797,
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    content = {
        "schema_version": JudgeExecutionManifest._SCHEMA,
        **values,
        "metadata": {
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
        },
    }
    return JudgeExecutionManifest.from_payload(
        {**content, "record_hash": canonical_payload_hash(content)}
    )


def intent(*, item_id: str = "blind-item-001", order_index: int = 0) -> JudgeDispatchIntent:
    return JudgeDispatchIntent.create(
        manifest_hash=manifest().record_hash,
        item_id=item_id,
        item_hash=SHA,
        order_index=order_index,
        attempt_index=1,
        request_hash=SHA,
        request_id=f"judge-request-{item_id}",
        idempotency_key=f"judge-idempotency-{item_id}",
        created_at="2026-09-19T00:00:00Z",
    )


@pytest.fixture
def judge_store(tmp_path: Path) -> JudgeRunStore:
    return JudgeRunStore.create(tmp_path / "judge", manifest())


def test_store_creates_exact_append_only_layout_and_initial_projection(
    judge_store: JudgeRunStore,
) -> None:
    assert (judge_store.root / "staging" / "manifest.json").is_file()
    for relative in (
        "attempts",
        "dispatch",
        "reconciliation",
        "raw",
        "service/preflight",
        "service/start",
        "service/stop",
        "journal",
        "projections",
    ):
        assert (judge_store.root / "staging" / relative).is_dir()
    snapshots = tuple((judge_store.root / "staging" / "projections").iterdir())
    assert len(snapshots) == 1
    assert snapshots[0].name.startswith("000000000000-")


def test_store_creation_and_record_append_are_create_only(
    judge_store: JudgeRunStore,
) -> None:
    with pytest.raises(FileExistsError):
        JudgeRunStore.create(judge_store.root, manifest())
    record = intent()
    judge_store.append_intent(record)
    with pytest.raises(FileExistsError):
        judge_store.append_intent(record)


def test_unresolved_dispatch_requires_typed_reconciliation(judge_store: JudgeRunStore) -> None:
    judge_store.append_intent(intent())
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        reconstruct_judge_projection(judge_store)


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("recovered_response", "recovered_response"),
        ("proved_not_sent", "pending_retry"),
        ("ambiguous", "ambiguous_incomplete"),
    ],
)
def test_reconciliation_has_only_three_outcomes(
    judge_store: JudgeRunStore, decision: str, expected_status: str
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    evidence: dict[str, object] = {
        "provider_audit_hash": SHA,
        "checked_at": "2026-09-19T00:01:00Z",
    }
    if decision == "recovered_response":
        response = b"recovered"
        response_hash = hashlib.sha256(response).hexdigest()
        provider_audit = {
            "provider_audit_hash": SHA,
            "request_id": dispatch.request_id,
            "response_bytes_base64": base64.b64encode(response).decode("ascii"),
            "response_bytes_hash": response_hash,
            "checked_at": "2026-09-19T00:01:00Z",
        }
        judge_store.append_raw_provider_audit(dispatch, provider_audit)
        evidence["response_bytes_hash"] = response_hash
    record = JudgeDispatchReconciliation.create(dispatch, decision, evidence)
    judge_store.append_reconciliation(record)
    projection = reconstruct_judge_projection(judge_store)
    assert projection.item_states[dispatch.item_id].status == expected_status


def test_open_replays_and_rejects_a_tampered_projection_chain(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    judge_store.append_reconciliation(
        JudgeDispatchReconciliation.create(
            dispatch,
            "proved_not_sent",
            {"provider_audit_hash": SHA, "checked_at": "2026-09-19T00:01:00Z"},
        )
    )
    reopened = JudgeRunStore.open(judge_store.root)
    assert reopened.current_projection.record_hash == judge_store.current_projection.record_hash

    latest = sorted((judge_store.root / "staging" / "projections").iterdir())[-1]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    payload["previous_projection_hash"] = "b" * 64
    latest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="projection|hash chain"):
        JudgeRunStore.open(judge_store.root)


def test_append_refuses_to_extend_a_tampered_projection_chain(
    judge_store: JudgeRunStore,
) -> None:
    latest = next((judge_store.root / "staging" / "projections").iterdir())
    payload = json.loads(latest.read_text(encoding="utf-8"))
    payload["record_hash"] = "b" * 64
    latest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="projection|hash"):
        judge_store.append_intent(intent())
