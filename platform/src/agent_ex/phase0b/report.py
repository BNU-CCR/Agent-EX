"""Sanitized preliminary Phase 0B report export."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..domain import canonical_payload_hash
from ..mock_matrix import CANONICAL_CELL_IDS
from .contracts import DiagnosticRunAuthorization
from .matrix import DiagnosticMatrixCandidate
from .run import Phase0BJsonlStagingStore, verify_diagnostic_matrix_run


def build_phase0b_preliminary_report(
    *,
    run_root: str | Path,
    authorization: DiagnosticRunAuthorization,
    matrix_candidate: DiagnosticMatrixCandidate,
) -> dict[str, object]:
    """Build a safe preliminary report from committed diagnostic staging only."""

    terminal = verify_diagnostic_matrix_run(
        run_root=run_root,
        authorization=authorization,
        matrix_candidate=matrix_candidate,
    )
    store = Phase0BJsonlStagingStore(Path(run_root) / "staging")
    projection = store.read_json("projection.json")
    attempts = store.read_jsonl("attempts.jsonl")

    per_cell_committed_counts = {cell_id: 0 for cell_id in CANONICAL_CELL_IDS}
    per_cell_transport_counts = {cell_id: 0 for cell_id in CANONICAL_CELL_IDS}
    outcome_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    provider_failure_count = 0

    for record in attempts:
        cell_id = record["cell_id"]
        if cell_id not in per_cell_committed_counts:
            raise ValueError("attempt record contains unknown cell")
        per_cell_committed_counts[cell_id] += 1  # type: ignore[index]
        per_cell_transport_counts[cell_id] += 1  # type: ignore[index]
        outcome = _string(record.get("outcome"), "outcome")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        error_code = record.get("error_code")
        if error_code is not None:
            error = _string(error_code, "error_code")
            error_counts[error] = error_counts.get(error, 0) + 1
        if outcome != "response":
            provider_failure_count += 1
        usage = record.get("usage")
        if not isinstance(usage, Mapping):
            raise ValueError("attempt record usage must be a mapping")
        for key in usage_totals:
            value = usage.get(key, 0)
            if type(value) is not int or value < 0:
                raise ValueError("attempt usage token counts must be non-negative integers")
            usage_totals[key] += value

    if any(value != 40 for value in per_cell_committed_counts.values()):
        raise ValueError("report requires exactly 40 attempts per cell")

    content: dict[str, object] = {
        "schema_version": "paper1.phase0b.preliminary-report.v1",
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "interpretation_label": "preliminary_descriptive_feasibility_only",
        "authorization_hash": authorization.record_hash,
        "matrix_hash": matrix_candidate.matrix_hash,
        "terminal_report_hash": terminal.record_hash,
        "projection_hash": projection["record_hash"],
        "terminal_status": terminal.terminal_status,
        "completed_cell_ids": terminal.completed_cell_ids,
        "committed_event_count": terminal.committed_event_count,
        "transport_count": terminal.transport_count,
        "unresolved_dispatch_count": terminal.unresolved_dispatch_count,
        "parse_failure_count": 0,
        "provider_failure_count": provider_failure_count,
        "retry_count": terminal.transport_count - terminal.committed_event_count,
        "outcome_counts": outcome_counts,
        "error_counts": error_counts,
        "usage_totals": usage_totals,
        "per_cell_committed_counts": per_cell_committed_counts,
        "per_cell_transport_counts": per_cell_transport_counts,
        "forbidden_claims": authorization.forbidden_claims,
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def _string(value: object, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value
