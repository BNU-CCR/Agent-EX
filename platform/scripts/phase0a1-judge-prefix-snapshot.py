#!/usr/bin/env python3
"""Create a contract-validated metadata snapshot without opening raw-bearing evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, TypeVar

from agent_ex.calibration.judge_contracts import (
    JudgeExecutionManifest,
    JudgeRequestRenderer,
)
from agent_ex.calibration.judge_runner import JudgeItemState, JudgeProjection
from agent_ex.calibration.review import SemanticReviewPolicy
from agent_ex.domain import canonical_payload_hash


SCHEMA = "paper1.calibration.judge-prefix-metadata-snapshot.v1"
METHOD_ID = "phase0a1-judge-prefix-metadata-only-v1"
RAW_BEARING_MARKERS = (
    b'"raw_bytes',
    b'"output_bytes',
    b'"response_bytes',
    b'"provider_output',
)
T = TypeVar("T")


def _require_sha256(name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _read_contract(
    path: Path,
    parser: Callable[[dict[str, object]], T],
    *,
    label: str,
) -> tuple[T, str, dict[str, Any]]:
    encoded = path.read_bytes()
    if any(marker in encoded for marker in RAW_BEARING_MARKERS):
        raise ValueError(f"{label} is raw-bearing and is forbidden for metadata snapshots")
    decoded = json.loads(encoded)
    if type(decoded) is not dict:
        raise ValueError(f"{label} must contain one JSON object")
    if label == "projection":
        raw_order = decoded.get("item_order")
        if (
            type(raw_order) is not list
            or any(type(item_id) is not str or not item_id for item_id in raw_order)
            or len(raw_order) != len(set(raw_order))
        ):
            raise ValueError("projection item_order must contain unique nonempty string IDs")
    return parser(decoded), hashlib.sha256(encoded).hexdigest(), decoded


def _validate_item_state(
    state: JudgeItemState,
    item_id: str,
    order_index: int,
    manifest: JudgeExecutionManifest,
) -> None:
    if type(item_id) is not str or not item_id or state.item_id != item_id:
        raise ValueError("projection item state identity differs from item_order")
    _require_sha256("item_hash", state.item_hash)
    if type(state.order_index) is not int or state.order_index != order_index:
        raise ValueError("projection state order_index differs from item_order")
    if type(state.status) is not str or not state.status:
        raise ValueError("projection item status must be nonempty text")
    if type(state.attempt_count) is not int or state.attempt_count < 0:
        raise ValueError("projection attempt_count must be a nonnegative integer")
    if (
        type(state.attempt_ids) is not tuple
        or len(state.attempt_ids) != len(set(state.attempt_ids))
        or any(type(value) is not str or not value for value in state.attempt_ids)
    ):
        raise ValueError("projection attempt IDs must be unique nonempty strings")
    if state.attempt_count != len(state.attempt_ids):
        raise ValueError("projection attempt_count differs from attempt IDs")
    for name in (
        "unresolved_intent_hash",
        "last_reconciliation_hash",
        "completed_attempt_hash",
        "resolution_hash",
    ):
        value = getattr(state, name)
        if value is not None:
            _require_sha256(name, value)
    if state.last_error is not None and type(state.last_error) is not str:
        raise ValueError("projection last_error must be text or null")
    allowed_statuses = {
        "dispatch_unresolved",
        "recovered_response",
        "ambiguous_incomplete",
        "coded",
        "pending_retry",
        "terminal_failed",
    }
    if state.status not in allowed_statuses:
        raise ValueError("projection item status is outside the formal replay state enum")
    if state.status in {"dispatch_unresolved", "recovered_response"}:
        if (
            state.unresolved_intent_hash is None
            or state.resolution_hash is not None
            or state.last_error is not None
        ):
            raise ValueError("unresolved/recovered state violates formal replay invariants")
        if state.status == "recovered_response" and state.last_reconciliation_hash is None:
            raise ValueError("recovered response requires reconciliation evidence")
    elif state.status == "ambiguous_incomplete":
        if (
            state.unresolved_intent_hash is not None
            or state.last_reconciliation_hash is None
            or state.completed_attempt_hash is not None
            or state.resolution_hash is not None
            or state.last_error is not None
        ):
            raise ValueError("ambiguous state violates formal replay invariants")
    elif state.status == "coded":
        if (
            state.unresolved_intent_hash is not None
            or state.completed_attempt_hash is None
            or state.resolution_hash is None
            or state.last_error is not None
        ):
            raise ValueError("coded state violates formal replay invariants")
    else:
        if (
            state.unresolved_intent_hash is not None
            or state.completed_attempt_hash is None
            or state.resolution_hash is None
            or state.last_error is None
        ):
            raise ValueError("failed/retry state violates formal replay invariants")
        retry_authorized = (
            state.last_error in manifest.retryable_codes
            and state.attempt_count < manifest.max_attempts_per_item
        )
        if (state.status == "pending_retry") != retry_authorized:
            raise ValueError("failed/retry state differs from manifest retry policy")


def build_snapshot(
    *,
    projection_path: Path,
    manifest_path: Path,
    policy_path: Path,
    renderer_path: Path,
    approved_manifest_hash: str,
    approved_policy_hash: str,
    approved_renderer_hash: str,
    cutoff: int,
    captured_at: str,
    source_locator: str,
    script_path: Path,
) -> dict[str, object]:
    approved_manifest_hash = _require_sha256("approved manifest hash", approved_manifest_hash)
    approved_policy_hash = _require_sha256("approved policy hash", approved_policy_hash)
    approved_renderer_hash = _require_sha256("approved renderer hash", approved_renderer_hash)
    projection, projection_file_hash, projection_payload = _read_contract(
        projection_path, JudgeProjection.from_payload, label="projection"
    )
    manifest, manifest_file_hash, _ = _read_contract(
        manifest_path, JudgeExecutionManifest.from_payload, label="manifest"
    )
    policy, policy_file_hash, _ = _read_contract(
        policy_path, SemanticReviewPolicy.from_payload, label="policy"
    )
    renderer, renderer_file_hash, _ = _read_contract(
        renderer_path, JudgeRequestRenderer.from_payload, label="renderer"
    )
    if manifest.record_hash != approved_manifest_hash:
        raise ValueError("manifest differs from the approved manifest hash")
    if policy.record_hash != approved_policy_hash:
        raise ValueError("policy differs from the approved policy hash")
    if renderer.record_hash != approved_renderer_hash:
        raise ValueError("renderer differs from the approved renderer hash")
    if projection.manifest_hash != manifest.record_hash:
        raise ValueError("projection differs from the approved manifest")
    if manifest.renderer_hash != renderer.record_hash:
        raise ValueError("manifest differs from the approved renderer")
    if renderer.policy_hash != policy.record_hash:
        raise ValueError("renderer differs from the approved policy hash")
    if (
        projection.preflight_hash != manifest.preflight_hash
        or projection.service_start_identity_hash != manifest.service_start_identity_hash
    ):
        raise ValueError("projection runtime identity differs from the approved manifest")

    raw_order = projection_payload.get("item_order")
    if (
        type(raw_order) is not list
        or any(type(item_id) is not str or not item_id for item_id in raw_order)
        or len(raw_order) != len(set(raw_order))
    ):
        raise ValueError("projection item_order must contain unique nonempty string IDs")
    if tuple(raw_order) != projection.item_order:
        raise ValueError("typed projection order differs from source payload")
    if len(projection.item_order) > manifest.expected_item_count:
        raise ValueError("projection inventory exceeds the approved manifest")
    for order_index, item_id in enumerate(projection.item_order):
        _validate_item_state(projection.item_states[item_id], item_id, order_index, manifest)

    observed_cutoff = 0
    for item_id in projection.item_order:
        if projection.item_states[item_id].status != "coded":
            break
        observed_cutoff += 1
    if any(
        projection.item_states[item_id].status == "coded"
        for item_id in projection.item_order[observed_cutoff:]
    ):
        raise ValueError("coded item appears after the contiguous completed prefix")
    if type(cutoff) is not int or cutoff != observed_cutoff:
        raise ValueError("requested cutoff differs from the contiguous coded prefix")
    if cutoff > manifest.expected_item_count:
        raise ValueError("cutoff exceeds the approved manifest item count")
    complete = cutoff == manifest.expected_item_count
    if complete and (
        len(projection.item_order) != manifest.expected_item_count
        or any(state.status != "coded" for state in projection.item_states.values())
    ):
        raise ValueError("complete cutoff requires the exact terminal coded inventory")
    if type(captured_at) is not str or not captured_at:
        raise ValueError("captured_at must be nonempty text")
    if type(source_locator) is not str or not source_locator:
        raise ValueError("source locator must be nonempty text")

    script_sha256 = hashlib.sha256(script_path.read_bytes()).hexdigest()
    labels = {
        "preliminary": True,
        "incomplete": not complete,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
    }
    status_counts = Counter(
        projection.item_states[item_id].status for item_id in projection.item_order
    )
    prefix_binding = [
        {
            "order_index": state.order_index,
            "item_id": item_id,
            "item_hash": state.item_hash,
            "resolution_hash": state.resolution_hash,
        }
        for item_id in projection.item_order[:cutoff]
        for state in (projection.item_states[item_id],)
    ]
    content: dict[str, object] = {
        "schema_version": SCHEMA,
        "labels": labels,
        "analysis_method": {
            "method_id": METHOD_ID,
            "script_sha256": script_sha256,
            "semantic_statistics_available": False,
            "blocking_reason": (
                "no approved raw-free label export is present; raw-bearing reconciliation "
                "records were not opened"
            ),
        },
        "source": {
            "locator": source_locator,
            "projection_file_sha256": projection_file_hash,
            "manifest_file_sha256": manifest_file_hash,
            "policy_file_sha256": policy_file_hash,
            "renderer_file_sha256": renderer_file_hash,
            "projection_record_hash": projection.record_hash,
            "manifest_record_hash": manifest.record_hash,
            "policy_record_hash": policy.record_hash,
            "renderer_record_hash": renderer.record_hash,
        },
        "snapshot": {
            "captured_at": captured_at,
            "cutoff": cutoff,
            "observed_item_count": len(projection.item_order),
            "expected_total": manifest.expected_item_count,
            "source_projection_sequence": projection.sequence,
            "status_counts": dict(sorted(status_counts.items())),
            "prefix_binding_hash": canonical_payload_hash(prefix_binding),
        },
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--renderer", type=Path, required=True)
    parser.add_argument("--approved-manifest-hash", required=True)
    parser.add_argument("--approved-policy-hash", required=True)
    parser.add_argument("--approved-renderer-hash", required=True)
    parser.add_argument("--cutoff", type=int, required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--source-locator", required=True)
    args = parser.parse_args()
    payload = build_snapshot(
        projection_path=args.projection,
        manifest_path=args.manifest,
        policy_path=args.policy,
        renderer_path=args.renderer,
        approved_manifest_hash=args.approved_manifest_hash,
        approved_policy_hash=args.approved_policy_hash,
        approved_renderer_hash=args.approved_renderer_hash,
        cutoff=args.cutoff,
        captured_at=args.captured_at,
        source_locator=args.source_locator,
        script_path=Path(__file__),
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, allow_nan=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
