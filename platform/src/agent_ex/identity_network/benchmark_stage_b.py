"""Frozen Stage-B framing and report gate; reports alone never authorize HTTP."""

from collections.abc import Mapping
import json
import math
from pathlib import Path

from ..domain import canonical_payload_hash, _require_sha256, _json_ready
from .manipulation_store import file_signature

FRAMING_HASH = "65a5707ca065bc719f747801231d919f8b5a0fa9c7c50041afa4d068f342f5bf"
FRAMING_PATH = (
    Path(__file__).resolve().parents[4]
    / "platform/configs/identity-network/manipulation-retirement-20261008/stage-b-framing.json"
)
B_MODES = frozenset({"stage-b", "preflight-b"})


def stage_a_report_payload(report):
    """Use the same JSON form as the CLI (distance keys and version arrays included)."""
    return json.loads(json.dumps(_json_ready(report), ensure_ascii=False, allow_nan=False))


def load_frozen_framing():
    before = file_signature(FRAMING_PATH)
    if before[2] > 8192:
        raise ValueError("bounded frozen framing required")
    result = json.loads(FRAMING_PATH.read_text(encoding="utf-8"))
    if file_signature(FRAMING_PATH) != before or canonical_payload_hash(result) != FRAMING_HASH:
        raise ValueError("Stage-B framing differs from frozen text")
    return result


def validate_stage_a_report(report, *, runtime_hash, packet_hash=None):
    """Structure gate only. Runner must independently cold-verify the actual A store."""
    if not isinstance(report, Mapping):
        raise ValueError("complete Stage-A execution report required")
    if (
        report.get("phase") != "COMPLETE"
        or report.get("mode") != "stage-a"
        or report.get("transport_evidence_verified") is not True
        or report.get("saved_response_pending") is not False
        or report.get("runtime_hash") != runtime_hash
        or any(
            type(report.get(k)) is not int or report[k] != 240
            for k in ("ordinal", "valid_count", "trial_count")
        )
        or type(report.get("transition_count")) is not int
        or report["transition_count"] < 480
    ):
        raise ValueError("complete transport-verified matching Stage-A required")
    for field in ("packet_hash", "tail_hash", "outcomes_hash", "execution_approval_hash"):
        _require_sha256(field, report.get(field))
    if packet_hash is not None and report["packet_hash"] != packet_hash:
        raise ValueError("Stage-A packet differs from current benchmark/runtime")
    a = report.get("analysis")
    if (
        not isinstance(a, Mapping)
        or a.get("execution_status") != "NORMALIZED_COMPLETE_NOT_TRANSPORT_VERIFIED"
        or any(type(a.get(k)) is not int or a[k] != 240 for k in ("valid_count", "observed_count"))
        or a.get("signal_status") != "NO_SIGNAL"
    ):
        raise ValueError("complete no-signal Stage-A analysis required")
    ci, mean, positive = a.get("ci95"), a.get("primary_mean"), a.get("positive_cases")
    if (
        not isinstance(ci, (list, tuple))
        or len(ci) != 2
        or any(type(x) not in (int, float) or not math.isfinite(x) for x in (*ci, mean))
        or ci[0] > ci[1]
        or type(positive) is not int
        or not 0 <= positive <= 30
    ):
        raise ValueError("valid frozen Stage-A criteria required")
    if mean > 0 and ci[0] > 0 and positive >= 18:
        raise ValueError("passing Stage-A cannot activate Stage-B")
