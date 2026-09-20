from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from agent_ex.calibration.judge_runner import (
    AmbiguousJudgeDispatchError,
    JudgeAttemptResolution,
    JudgeCompletedAttempt,
    JudgeDispatchIntent,
    JudgeDispatchReconciliation,
    JudgeNegativeDispatchEvidence,
    JudgeNegativeVerifierContract,
    JudgeProviderNegativeLogArtifact,
    replay_judge_records,
    build_retry_after_not_sent,
    reconcile_from_provider_log,
    reconcile_proved_not_sent,
    reconstruct_judge_projection,
)
from agent_ex.calibration.judge_adapter import parse_judge_response
from agent_ex.calibration.judge_contracts import (
    JudgeRequestEvidence,
    JudgeRequestRenderer,
    JudgeResponseEvidence,
)
from agent_ex.calibration.review import BlindReviewItem, SemanticReviewPolicy
from agent_ex.calibration.judge_store import JudgeRunStore
from agent_ex.domain import canonical_payload_hash
from test_calibration_judge_store import context, intent


@pytest.fixture
def judge_store(tmp_path: Path) -> JudgeRunStore:
    manifest_value, _, _, _, preflight, start, pack, index = context()
    store = JudgeRunStore.create(tmp_path / "judge", manifest_value, pack, index)
    store.append_preflight(preflight)
    store.append_service_start(start)
    return store


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


def policy() -> SemanticReviewPolicy:
    return SemanticReviewPolicy.from_payload(
        json.loads(
            (
                Path(__file__).parents[1]
                / "configs"
                / "paper1"
                / "phase0a1-approval-proposal-v2"
                / "semantic_review_policy.json"
            ).read_text(encoding="utf-8")
        )
    )


def successful_response(
    dispatch: JudgeDispatchIntent, *, raw_override: bytes | None = None
) -> tuple[JudgeResponseEvidence, object]:
    review_policy = policy()
    labels = {
        name: review_policy.dimension_labels[name][0] for name in review_policy.dimension_labels
    }
    output = json.dumps(labels, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    raw = raw_override or json.dumps(
        {
            "model": dispatch.request.model_id,
            "choices": [
                {
                    "message": {"content": output.decode("utf-8")},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    response = JudgeResponseEvidence.create(
        request=dispatch.request,
        provider_request_id="provider-request-001",
        http_status=200,
        response_headers={"x-request-id": "provider-request-001"},
        response_header_items=(("x-request-id", "provider-request-001"),),
        duplicate_critical_header_names=(),
        raw_bytes=raw,
        raw_bytes_complete=True,
        raw_bytes_total_lower_bound=len(raw),
        output_bytes=output,
        model_id=dispatch.request.model_id,
        termination="stop",
        input_tokens=10,
        output_tokens=20,
        failure_code=None,
        retry_after_seconds=None,
        started_at="2026-09-19T00:01:00Z",
        ended_at="2026-09-19T00:01:01Z",
        duration_seconds=1.0,
    )
    return response, parse_judge_response(output, review_policy)


def parse_failed_attempt(
    dispatch: JudgeDispatchIntent, *, failure_code: str = "parse_invalid_json"
) -> JudgeCompletedAttempt:
    review_policy = policy()
    if failure_code == "parse_invalid_json":
        output = b"not-json"
    elif failure_code == "parse_illegal_label":
        labels = {
            name: review_policy.dimension_labels[name][0] for name in review_policy.dimension_labels
        }
        labels[next(iter(labels))] = "not-an-approved-label"
        output = json.dumps(labels, separators=(",", ":")).encode("utf-8")
    else:
        raise ValueError("unsupported test failure code")
    raw = json.dumps(
        {
            "model": dispatch.request.model_id,
            "choices": [
                {
                    "message": {"content": output.decode("utf-8")},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    response = JudgeResponseEvidence.create(
        request=dispatch.request,
        provider_request_id=f"provider-{dispatch.request_id}",
        http_status=200,
        response_headers={"x-request-id": f"provider-{dispatch.request_id}"},
        response_header_items=(("x-request-id", f"provider-{dispatch.request_id}"),),
        duplicate_critical_header_names=(),
        raw_bytes=raw,
        raw_bytes_complete=True,
        raw_bytes_total_lower_bound=len(raw),
        output_bytes=output,
        model_id=dispatch.request.model_id,
        termination="stop",
        input_tokens=10,
        output_tokens=20,
        failure_code=None,
        retry_after_seconds=None,
        started_at="2026-09-19T00:01:00Z",
        ended_at="2026-09-19T00:01:01Z",
        duration_seconds=1.0,
    )
    return JudgeCompletedAttempt.create(
        dispatch,
        response,
        parse_judge_response(output, review_policy),
    )


def negative_evidence(
    dispatch: JudgeDispatchIntent,
    *,
    observation_id: str,
) -> JudgeNegativeDispatchEvidence:
    manifest_value = context()[0]
    verifier = JudgeNegativeVerifierContract.create(manifest_value)
    provider_log = json.dumps(
        {
            "schema_version": "paper1.calibration.provider-negative-log.v1",
            "request_id": dispatch.request_id,
            "observation_id": observation_id,
            "dispatch_found": False,
            "verifier_contract_hash": verifier.record_hash,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    artifact = JudgeProviderNegativeLogArtifact.create(
        dispatch,
        verifier=verifier,
        observation_id=observation_id,
        provider_log_bytes=provider_log,
        observed_at="2026-09-19T00:01:00Z",
    )
    return JudgeNegativeDispatchEvidence.create(
        dispatch,
        manifest=manifest_value,
        verifier=verifier,
        provider_log_artifact=artifact,
    )


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
    provider_audit["request_id"] = dispatch.request_id
    if crash_point == "after_raw":
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
    provider_audit["request_id"] = dispatch.request_id
    recovered = reconcile_from_provider_log(judge_store, dispatch, provider_audit)
    assert recovered.decision == "recovered_response"
    assert recovered.response_bytes_hash == provider_audit["response_bytes_hash"]
    projection = judge_store.current_projection
    assert projection.item_states[dispatch.item_id].status == "recovered_response"
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        reconstruct_judge_projection(judge_store)


def test_proved_not_sent_retry_is_disabled_without_external_authentication(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    negative = negative_evidence(dispatch, observation_id="provider-observation-001")
    with pytest.raises(ValueError, match="disabled|authenticated provider attestation"):
        reconcile_proved_not_sent(judge_store, dispatch, negative)


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
        judge_store.append_intent(intent(order_index=1))


def test_projection_refuses_next_item_while_prior_dispatch_is_unresolved(
    judge_store: JudgeRunStore,
) -> None:
    judge_store.append_intent(intent())
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        judge_store.append_intent(intent(order_index=1))


def test_locally_constructed_proved_not_sent_cannot_authorize_retry(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    negative = negative_evidence(dispatch, observation_id="provider-observation-002")
    reconciliation = JudgeDispatchReconciliation.create(
        dispatch,
        "proved_not_sent",
        {
            "provider_audit_hash": negative.record_hash,
            "checked_at": negative.observed_at,
        },
    )
    with pytest.raises(ValueError, match="disabled|authenticated provider attestation"):
        build_retry_after_not_sent(dispatch, reconciliation, intent(attempt_index=2).request)


def test_dispatch_intent_round_trip_is_exact() -> None:
    dispatch = intent()
    assert JudgeDispatchIntent.from_payload(dispatch.to_payload()) == dispatch


def test_real_response_replays_through_request_hash_without_manifest_field(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    response, parse = successful_response(dispatch)
    judge_store.append_intent(dispatch)
    judge_store.append_response(response)
    judge_store.append_completed_attempt(JudgeCompletedAttempt.create(dispatch, response, parse))
    assert judge_store.current_projection.item_states[dispatch.item_id].completed_attempt_hash


def test_recovered_response_requires_subsequent_raw_bytes_hash_match(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    response, _ = successful_response(dispatch)
    judge_store.append_intent(dispatch)
    audit = {
        "provider_audit_hash": "b" * 64,
        "request_id": dispatch.request_id,
        "response_bytes_base64": base64.b64encode(response.raw_bytes).decode("ascii"),
        "response_bytes_hash": response.raw_bytes_sha256,
        "checked_at": "2026-09-19T00:01:00Z",
    }
    reconcile_from_provider_log(judge_store, dispatch, audit)
    other_response, _ = successful_response(intent(order_index=0, attempt_index=1))
    payload = other_response.to_payload()
    different_raw = response.raw_bytes + b" "
    payload["raw_bytes_base64"] = base64.b64encode(different_raw).decode("ascii")
    payload["raw_bytes_sha256"] = hashlib.sha256(different_raw).hexdigest()
    payload["raw_bytes_count"] = len(different_raw)
    payload["raw_bytes_total_lower_bound"] = len(different_raw)
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    mismatched = JudgeResponseEvidence.from_payload(payload)
    with pytest.raises(ValueError, match="recovered response.*bytes|raw bytes.*recovered"):
        judge_store.append_response(mismatched)


def test_recovered_response_accepts_exact_reconstructed_response(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    response, parse = successful_response(dispatch)
    judge_store.append_intent(dispatch)
    reconcile_from_provider_log(
        judge_store,
        dispatch,
        {
            "provider_audit_hash": "b" * 64,
            "request_id": dispatch.request_id,
            "response_bytes_base64": base64.b64encode(response.raw_bytes).decode("ascii"),
            "response_bytes_hash": response.raw_bytes_sha256,
            "checked_at": "2026-09-19T00:01:00Z",
        },
    )
    judge_store.append_response(response)
    judge_store.append_completed_attempt(JudgeCompletedAttempt.create(dispatch, response, parse))
    assert judge_store.current_projection.item_states[dispatch.item_id].completed_attempt_hash


def test_rehashed_coded_resolution_on_failed_parse_is_rejected() -> None:
    dispatch = intent()
    response, _ = successful_response(dispatch)
    failed_parse = parse_judge_response(b"not-json", policy())
    # A transport success whose provider output is invalid judge JSON is still a completed parse failure.
    failed_output = failed_parse.raw_bytes
    provider = json.loads(response.raw_bytes)
    provider["choices"][0]["message"]["content"] = failed_output.decode("utf-8")
    raw = json.dumps(provider, separators=(",", ":")).encode("utf-8")
    failed_response = JudgeResponseEvidence.create(
        request=dispatch.request,
        provider_request_id="provider-request-001",
        http_status=200,
        response_headers={"x-request-id": "provider-request-001"},
        response_header_items=(("x-request-id", "provider-request-001"),),
        duplicate_critical_header_names=(),
        raw_bytes=raw,
        raw_bytes_complete=True,
        raw_bytes_total_lower_bound=len(raw),
        output_bytes=failed_output,
        model_id=dispatch.request.model_id,
        termination="stop",
        input_tokens=10,
        output_tokens=20,
        failure_code=None,
        retry_after_seconds=None,
        started_at="2026-09-19T00:01:00Z",
        ended_at="2026-09-19T00:01:01Z",
        duration_seconds=1.0,
    )
    attempt = JudgeCompletedAttempt.create(dispatch, failed_response, failed_parse)
    valid = JudgeAttemptResolution.create(
        attempt, outcome="retryable_failed", failure_code="parse_invalid_json"
    )
    payload = valid.to_payload()
    payload["outcome"] = "coded"
    payload["failure_code"] = None
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match="coded.*successful exact parse|resolution.*attempt"):
        JudgeAttemptResolution.from_payload(payload)


def test_completed_parse_must_match_request_response_schema_policy() -> None:
    original_policy = policy()
    drifted_dimensions = {
        name: tuple(labels) for name, labels in original_policy.dimension_labels.items()
    }
    first_dimension = next(iter(drifted_dimensions))
    drifted_dimensions[first_dimension] = (*drifted_dimensions[first_dimension], "drifted-label")
    drifted_policy = replace(original_policy, dimension_labels=drifted_dimensions)
    item = BlindReviewItem.create(
        item_id="blind-item-schema-drift",
        policy_hash=drifted_policy.record_hash,
        visible_payload={
            "topic_text": "测试议题",
            "history_text": "",
            "identity_text": "",
            "response_text": "响应",
        },
    )
    renderer = JudgeRequestRenderer.create(
        drifted_policy,
        chat_template_hash="a" * 64,
        response_byte_ceiling=4096,
        generation_settings={"temperature": 0.0, "top_p": 1.0, "max_tokens": 512},
        golden_fixture_content={
            "schema_version": "paper1.calibration.judge-rendered-request-golden-input.v1",
            "item": item.to_payload(),
            "attempt_index": 1,
            "repair": False,
        },
    )
    request = JudgeRequestEvidence.create(
        rendered_request=renderer.render(item, 1, repair=False),
        manifest_hash="a" * 64,
        order_index=0,
        model_id="Qwen/Qwen3-8B",
    )
    dispatch = JudgeDispatchIntent.create(request=request, created_at="2026-09-19T00:00:00Z")
    response, parse = successful_response(dispatch)
    with pytest.raises(ValueError, match="response schema|label policy"):
        JudgeCompletedAttempt.create(dispatch, response, parse)


def test_approved_order_preserves_exact_item_policy_hash() -> None:
    approved = context()[1]
    assert approved.items[0].policy_hash == policy().record_hash


def test_replay_rejects_parse_from_different_policy_with_same_labels(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    response, _ = successful_response(dispatch)
    drifted_policy = replace(policy(), policy_version="drifted-but-same-labels")
    drifted_parse = parse_judge_response(response.output_bytes, drifted_policy)
    attempt = JudgeCompletedAttempt.create(dispatch, response, drifted_parse)
    judge_store.append_intent(dispatch)
    judge_store.append_response(response)
    with pytest.raises(ValueError, match="policy.*approved|approved.*policy"):
        judge_store.append_completed_attempt(attempt)


def test_replay_rejects_terminal_failure_while_retryable_budget_remains(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    attempt = parse_failed_attempt(dispatch)
    judge_store.append_intent(dispatch)
    judge_store.append_response(attempt.response)
    judge_store.append_completed_attempt(attempt)
    resolution = JudgeAttemptResolution.create(
        attempt,
        outcome="terminal_failed",
        failure_code="parse_invalid_json",
    )
    with pytest.raises(ValueError, match="retry policy|retryable"):
        judge_store.append_attempt_resolution(resolution)


def test_replay_rejects_retry_for_nonretryable_failure(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    attempt = parse_failed_attempt(dispatch, failure_code="parse_illegal_label")
    judge_store.append_intent(dispatch)
    judge_store.append_response(attempt.response)
    judge_store.append_completed_attempt(attempt)
    resolution = JudgeAttemptResolution.create(
        attempt,
        outcome="retryable_failed",
        failure_code="parse_illegal_label",
    )
    with pytest.raises(ValueError, match="retry policy|nonretryable"):
        judge_store.append_attempt_resolution(resolution)


def test_replay_requires_terminal_failure_when_retry_budget_is_exhausted(
    judge_store: JudgeRunStore,
) -> None:
    for attempt_index in (1, 2):
        dispatch = intent(attempt_index=attempt_index)
        attempt = parse_failed_attempt(dispatch)
        judge_store.append_intent(dispatch)
        judge_store.append_response(attempt.response)
        judge_store.append_completed_attempt(attempt)
        judge_store.append_attempt_resolution(
            JudgeAttemptResolution.create(
                attempt,
                outcome="retryable_failed",
                failure_code="parse_invalid_json",
            )
        )
    dispatch = intent(attempt_index=3)
    attempt = parse_failed_attempt(dispatch)
    judge_store.append_intent(dispatch)
    judge_store.append_response(attempt.response)
    judge_store.append_completed_attempt(attempt)
    resolution = JudgeAttemptResolution.create(
        attempt,
        outcome="retryable_failed",
        failure_code="parse_invalid_json",
    )
    with pytest.raises(ValueError, match="retry policy|budget"):
        judge_store.append_attempt_resolution(resolution)


def test_service_start_cannot_precede_exact_preflight() -> None:
    manifest_value, approved, _, _, preflight, start, _, _ = context()
    with pytest.raises(ValueError, match="preflight.*before.*start|lifecycle order"):
        replay_judge_records(manifest_value, approved, (start, preflight))


def test_response_lane_rejects_incomplete_marker(judge_store: JudgeRunStore) -> None:
    dispatch = intent()
    response, _ = successful_response(dispatch)
    judge_store.append_intent(dispatch)
    judge_store.append_response(response)
    with pytest.raises(ValueError, match="evidence lane|contradict"):
        judge_store.append_incomplete_attempt_marker(dispatch)


def test_ambiguous_lane_rejects_subsequent_response(judge_store: JudgeRunStore) -> None:
    dispatch = intent()
    response, _ = successful_response(dispatch)
    judge_store.append_intent(dispatch)
    judge_store.append_reconciliation(
        JudgeDispatchReconciliation.create(
            dispatch,
            "ambiguous",
            {"provider_audit_hash": "b" * 64, "checked_at": "2026-09-19T00:01:00Z"},
        )
    )
    with pytest.raises(ValueError, match="evidence lane|unresolved dispatch"):
        judge_store.append_response(response)


def test_negative_lane_rejects_response(judge_store: JudgeRunStore) -> None:
    dispatch = intent()
    response, _ = successful_response(dispatch)
    judge_store.append_intent(dispatch)
    judge_store.append_negative_dispatch_evidence(
        negative_evidence(dispatch, observation_id="provider-observation-lane")
    )
    with pytest.raises(ValueError, match="evidence lane|contradict"):
        judge_store.append_response(response)


def test_provider_audit_lane_rejects_negative_evidence(
    judge_store: JudgeRunStore, provider_audit: dict[str, object]
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    provider_audit["request_id"] = dispatch.request_id
    judge_store.append_raw_provider_audit(dispatch, provider_audit)
    with pytest.raises(ValueError, match="evidence lane|contradict"):
        judge_store.append_negative_dispatch_evidence(
            negative_evidence(dispatch, observation_id="provider-observation-audit-lane")
        )


def test_incomplete_lane_allows_only_ambiguous_reconciliation(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    judge_store.append_incomplete_attempt_marker(dispatch)
    ambiguous = JudgeDispatchReconciliation.create(
        dispatch,
        "ambiguous",
        {"provider_audit_hash": "b" * 64, "checked_at": "2026-09-19T00:01:00Z"},
    )
    judge_store.append_reconciliation(ambiguous)
    state = judge_store.current_projection.item_states[dispatch.item_id]
    assert state.status == "ambiguous_incomplete"
    assert state.unresolved_intent_hash is None


def test_negative_dispatch_requires_manifest_authorized_verifier_and_log_artifact() -> None:
    dispatch = intent()
    evidence = negative_evidence(dispatch, observation_id="provider-observation-contract")
    assert evidence.verifier.manifest_hash == dispatch.manifest_hash
    assert (
        evidence.provider_log_artifact.raw_bytes_sha256
        == hashlib.sha256(evidence.provider_log_artifact.raw_bytes).hexdigest()
    )
    assert JudgeNegativeDispatchEvidence.from_payload(evidence.to_payload()) == evidence

    payload = evidence.to_payload()
    payload["verifier"]["authorization_hash"] = "b" * 64
    verifier_content = {
        name: value for name, value in payload["verifier"].items() if name != "record_hash"
    }
    payload["verifier"]["record_hash"] = canonical_payload_hash(verifier_content)
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match="manifest-authorized|authorization"):
        JudgeNegativeDispatchEvidence.from_payload(payload)
