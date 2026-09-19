from __future__ import annotations

import base64
from pathlib import Path

import pytest

from agent_ex.calibration.judge_runner import (
    AmbiguousJudgeDispatchError,
    JudgeDispatchIntent,
    build_retry_after_not_sent,
    reconcile_from_provider_log,
    reconcile_proved_not_sent,
    reconstruct_judge_projection,
)
from agent_ex.calibration.judge_store import JudgeRunStore
from agent_ex.domain import canonical_payload_hash
from test_calibration_judge_store import intent, manifest


@pytest.fixture
def judge_store(tmp_path: Path) -> JudgeRunStore:
    return JudgeRunStore.create(tmp_path / "judge", manifest())


@pytest.fixture
def provider_audit() -> dict[str, object]:
    response = b'{"provider":"exact bytes"}'
    return {
        "provider_audit_hash": canonical_payload_hash(
            {"request_id": "judge-request-blind-item-001", "response": response.hex()}
        ),
        "request_id": "judge-request-blind-item-001",
        "response_bytes_base64": base64.b64encode(response).decode("ascii"),
        "response_bytes_hash": __import__("hashlib").sha256(response).hexdigest(),
        "checked_at": "2026-09-19T00:01:00Z",
    }


@pytest.mark.parametrize(
    "crash_point", ("after_intent", "after_provider_response", "after_raw", "after_attempt")
)
def test_each_dispatch_crash_window_fails_closed(
    judge_store: JudgeRunStore,
    provider_audit: dict[str, object],
    crash_point: str,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    if crash_point in {"after_raw", "after_attempt"}:
        judge_store.append_raw_provider_audit(dispatch, provider_audit)
    if crash_point == "after_attempt":
        judge_store.append_incomplete_attempt_marker(dispatch)
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        reconstruct_judge_projection(judge_store)


def test_provider_log_recovery_preserves_exact_bytes(
    judge_store: JudgeRunStore, provider_audit: dict[str, object]
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    recovered = reconcile_from_provider_log(judge_store, dispatch, provider_audit)
    assert recovered.decision == "recovered_response"
    assert recovered.response_bytes_hash == provider_audit["response_bytes_hash"]
    projection = reconstruct_judge_projection(judge_store)
    assert projection.item_states[dispatch.item_id].status == "recovered_response"


def test_proved_not_sent_retry_gets_new_attempt_but_same_item_identity(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    reconciliation = reconcile_proved_not_sent(judge_store, dispatch)
    retry = build_retry_after_not_sent(dispatch, reconciliation)
    assert retry.item_id == dispatch.item_id
    assert retry.item_hash == dispatch.item_hash
    assert retry.attempt_id != dispatch.attempt_id
    assert retry.idempotency_key != dispatch.idempotency_key
    assert retry.attempt_index == 2


def test_reconciliation_rejects_wrong_provider_request_identity(
    judge_store: JudgeRunStore, provider_audit: dict[str, object]
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    provider_audit["request_id"] = "judge-request-other"
    with pytest.raises(ValueError, match="request identity"):
        reconcile_from_provider_log(judge_store, dispatch, provider_audit)


def test_projection_rejects_noncontiguous_first_item_order(judge_store: JudgeRunStore) -> None:
    with pytest.raises(ValueError, match="contiguous approved item order"):
        judge_store.append_intent(intent(item_id="blind-item-002", order_index=1))


def test_projection_refuses_next_item_while_prior_dispatch_is_unresolved(
    judge_store: JudgeRunStore,
) -> None:
    judge_store.append_intent(intent())
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        judge_store.append_intent(intent(item_id="blind-item-002", order_index=1))


def test_proved_not_sent_reconciliation_allows_exact_next_attempt(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    reconciliation = reconcile_proved_not_sent(judge_store, dispatch)
    retry = build_retry_after_not_sent(dispatch, reconciliation)
    judge_store.append_intent(retry)
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        reconstruct_judge_projection(judge_store)


def test_dispatch_intent_round_trip_is_exact() -> None:
    dispatch = intent()
    assert JudgeDispatchIntent.from_payload(dispatch.to_payload()) == dispatch
