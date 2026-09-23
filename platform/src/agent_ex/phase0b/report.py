"""Sanitized preliminary Phase 0B report export."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..domain import canonical_payload_hash
from ..mock_matrix import CANONICAL_CELL_IDS
from ..state import PrivateUpdate, PublicPost
from ..storage import RunStorage
from .contracts import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
)
from .matrix import DiagnosticMatrixCandidate, DiagnosticN20MaterializedMatrix
from .real_pipeline import verify_real_diagnostic_matrix
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


def _verified_public_posts(
    updates: tuple[PrivateUpdate, ...], posts: tuple[PublicPost, ...]
) -> tuple[PublicPost, ...]:
    """Require the exact public history implied by successfully published updates."""

    expected = tuple(
        PublicPost.from_private_update(update, mock_only=True)
        for update in updates
        if update.published
    )
    if not updates or updates[0].event_ordinal is not None or posts != expected:
        raise ValueError("diagnostic public posts differ from published private updates")
    return posts


def build_real_diagnostic_sqlite_report(
    *,
    matrix: DiagnosticN20MaterializedMatrix,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    policy: DiagnosticAttemptPolicy,
    stores: Mapping[str, RunStorage],
    run_root: Path,
) -> dict[str, object]:
    """Build a text-free descriptive report from verified committed SQLite states."""

    source = verify_real_diagnostic_matrix(
        matrix=matrix,
        authorization=authorization,
        adapter_binding=adapter_binding,
        policy=policy,
        stores=stores,
        run_root=run_root,
    )
    stance_labels = matrix.family.topic_package.stance_labels
    label_scores = {label: index + 1 for index, label in enumerate(stance_labels)}
    cells: list[dict[str, object]] = []
    source_cells: list[dict[str, object]] = []
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for cell in matrix.cells:
        storage = stores[cell.cell_id]
        updates_by_agent = {
            agent_id: storage.private_updates_for_agent(agent_id)
            for agent_id in matrix.family.agent_ids
        }
        posts_by_agent = {
            agent_id: _verified_public_posts(
                updates_by_agent[agent_id], storage.public_posts_for_agent(agent_id)
            )
            for agent_id in matrix.family.agent_ids
        }
        source_events: list[dict[str, object]] = []
        source_cells.append(
            {
                "cell_id": cell.cell_id,
                "private_update_hashes": [
                    [update.record_hash for update in updates_by_agent[agent_id]]
                    for agent_id in matrix.family.agent_ids
                ],
                "public_post_hashes": [
                    [post.record_hash for post in posts_by_agent[agent_id]]
                    for agent_id in matrix.family.agent_ids
                ],
                "committed_events": source_events,
            }
        )
        sweeps: list[dict[str, object]] = []
        cell_publication_count = 0
        for sweep_index in range(2):
            start, end = sweep_index * 20, (sweep_index + 1) * 20
            private_stock = {label: 0 for label in stance_labels}
            public_stock = {label: 0 for label in stance_labels}
            public_flow = {label: 0 for label in stance_labels}
            changes: list[int] = []
            for agent_id, updates in updates_by_agent.items():
                through_end = [
                    item
                    for item in updates
                    if item.event_ordinal is None or item.event_ordinal < end
                ]
                if not through_end:
                    raise ValueError("diagnostic report lacks an agent round-zero update")
                through_start = [
                    item
                    for item in through_end
                    if item.event_ordinal is None or item.event_ordinal < start
                ]
                if not through_start:
                    raise ValueError("diagnostic report lacks a previous sweep boundary")
                changes.append(
                    abs(
                        label_scores[through_end[-1].stance_label]
                        - label_scores[through_start[-1].stance_label]
                    )
                )
                private_stock[through_end[-1].stance_label] += 1
                public_posts = [
                    post
                    for post in posts_by_agent[agent_id]
                    if post.published_event_ordinal is None or post.published_event_ordinal < end
                ]
                public_stock[public_posts[-1].stance_label] += 1
                for post in public_posts:
                    if (
                        post.published_event_ordinal is not None
                        and start <= post.published_event_ordinal
                    ):
                        public_flow[post.stance_label] += 1
            selected_message_count = 0
            empty_feed_count = 0
            expired_message_count = 0
            publication_count = 0
            unique_source_ids: set[str] = set()
            for ordinal in range(start, end):
                event = storage.event_at(ordinal)
                if event is None:
                    raise ValueError("diagnostic report event prefix is incomplete")
                event_input = storage.event_input_evidence(event.event_id)
                if event_input is None:
                    raise ValueError("diagnostic report lacks event input evidence")
                source_ids = event_input.exposure_record.source_agent_ids
                selected_message_count += len(source_ids)
                empty_feed_count += len(source_ids) == 0
                expired_message_count += len(event_input.exposure_record.expired_post_ids)
                publication_count += int(event.publish_flag)
                unique_source_ids.update(source_ids)
                attempts = storage.attempts_for_event(event.event_id)
                source_events.append(
                    {
                        "event_hash": canonical_payload_hash(event.to_payload()),
                        "event_input_hash": event_input.record_hash,
                        "exposure_hash": event_input.exposure_record.record_hash,
                        "attempt_hashes": [
                            canonical_payload_hash(attempt.to_payload()) for attempt in attempts
                        ],
                        "usage_hashes": [attempt.usage_hash for attempt in attempts],
                    }
                )
                for attempt in attempts:
                    for key in usage_totals:
                        value = attempt.usage.get(key)
                        if type(value) is not int or value < 0:
                            raise ValueError("diagnostic committed attempt has invalid usage")
                        usage_totals[key] += value
            if sum(public_flow.values()) != publication_count:
                raise ValueError("diagnostic publication flow differs from committed events")
            cell_publication_count += publication_count
            scores = [
                label_scores[label] for label, count in private_stock.items() for _ in range(count)
            ]
            mean = sum(scores) / len(scores)
            sweeps.append(
                {
                    "sweep_index": sweep_index,
                    "private_stock": private_stock,
                    "private_mean": mean,
                    "private_variance": sum((value - mean) ** 2 for value in scores) / len(scores),
                    "mean_absolute_change": sum(changes) / len(changes),
                    "fraction_changing_stance": sum(value > 0 for value in changes) / len(changes),
                    "public_stock": public_stock,
                    "public_flow": public_flow,
                    "publication_count": publication_count,
                    "selected_message_count": selected_message_count,
                    "empty_feed_event_count": empty_feed_count,
                    "expired_message_count": expired_message_count,
                    "unique_source_count": len(unique_source_ids),
                }
            )
        cells.append(
            {"cell_id": cell.cell_id, "publication_count": cell_publication_count, "sweeps": sweeps}
        )
    content: dict[str, object] = {
        "schema_version": "paper1.phase0b.real-sqlite-preliminary-report.v1",
        "labels": ["preliminary", "diagnostic", "not_frozen"],
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "interpretation_label": "preliminary_descriptive_feasibility_only",
        "metric_definitions": {
            "stance_score": "topic stance-label order mapped to integers 1 through 7",
            "private_variance": "population variance of the 20 private scores at the sweep boundary",
            "mean_absolute_change": "mean absolute agent-level score change since the previous sweep boundary",
            "fraction_changing_stance": "fraction of agents whose score differs from the previous sweep boundary",
            "public_flow": "post counts from successful events within this sweep; excludes round zero",
        },
        "source_projection_hash": canonical_payload_hash(
            {
                "schema_version": "paper1.phase0b.real-sqlite-source-projection.v1",
                "completion_summary_hash": source.record_hash,
                "cells": source_cells,
            }
        ),
        "completion_summary_hash": source.record_hash,
        "authorization_hash": authorization.record_hash,
        "matrix_hash": matrix.matrix_hash,
        "committed_event_count": source.committed_event_count,
        "transport_count": source.transport_count,
        "retry_count": source.transport_count - source.committed_event_count,
        "unresolved_dispatch_count": 0,
        "parse_failure_count": 0,
        "provider_failure_count": 0,
        "usage_totals": usage_totals,
        "unavailable_metrics": {
            "refusal_proxy": "not_recorded_as_structured_evidence",
            "request_latency": "not_derived_from_verified_committed_projection",
            "requests_per_minute": "not_derived_from_verified_committed_projection",
            "wall_clock": "not_derived_from_verified_committed_projection",
            "gpu_service_identity": "not_in_verified_committed_projection",
            "sqlite_checkpoint_size": "not_in_verified_committed_projection",
        },
        "cells": cells,
        "forbidden_claims": authorization.forbidden_claims,
    }
    return {**content, "record_hash": canonical_payload_hash(content)}
