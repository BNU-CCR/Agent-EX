from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ex.mock_matrix import CANONICAL_CELL_IDS, validate_mock_matched_seed_matrix
from agent_ex.mock_run import MockRunControl, execute_mock_run
from agent_ex.process_audit import (
    APPROVED_OUTCOME_LABELS,
    APPROVED_TERMINOLOGY_MAP,
    APPROVED_TERMINOLOGY_MAP_ID,
    build_mock_comparable_run_projection,
    build_mock_process_audit,
)
from agent_ex.domain import derive_event_id
from helpers.mock_matrix import (
    build_mock_matrix_fixture,
    build_stress_cell_fixture,
    create_mock_matrix_cell,
    explicit_success_invocations,
    measure_mock_release_run,
    reopen_mock_matrix_cell,
)


def test_validated_commits_do_not_trigger_full_static_replay_per_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    matrix = build_mock_matrix_fixture(
        tmp_path,
        case_id="mock-n20-fault-recovery",
        sweeps=2,
    )
    fixture = create_mock_matrix_cell(
        tmp_path,
        matrix_fixture=matrix,
        cell_id="P1-I0-C0-E2",
    )
    calls = 0
    binding_reads = 0
    private_history_reads = 0
    full_public_history_reads = 0
    original = fixture.cell.storage._round0_entries
    original_evidence_reader = fixture.cell.storage._read_evidence_payload
    original_private_history_reader = fixture.cell.storage.private_updates_for_agent
    original_public_history_reader = fixture.cell.storage.public_posts_for_agent

    def counted_round0_entries(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    def counted_evidence_reader(table, *args, **kwargs):
        nonlocal binding_reads
        if table == "adapter_execution_bindings":
            binding_reads += 1
        return original_evidence_reader(table, *args, **kwargs)

    def counted_private_history_reader(*args, **kwargs):
        nonlocal private_history_reads
        private_history_reads += 1
        return original_private_history_reader(*args, **kwargs)

    def counted_public_history_reader(*args, **kwargs):
        nonlocal full_public_history_reads
        full_public_history_reads += 1
        return original_public_history_reader(*args, **kwargs)

    monkeypatch.setattr(fixture.cell.storage, "_round0_entries", counted_round0_entries)
    monkeypatch.setattr(fixture.cell.storage, "_read_evidence_payload", counted_evidence_reader)
    monkeypatch.setattr(
        fixture.cell.storage,
        "private_updates_for_agent",
        counted_private_history_reader,
    )
    monkeypatch.setattr(
        fixture.cell.storage,
        "public_posts_for_agent",
        counted_public_history_reader,
    )
    invocations = explicit_success_invocations(
        fixture.cell,
        start=0,
        stop=5,
        feed_capacity=6,
        memory_window=3,
    )
    execute_mock_run(
        pipeline=fixture.cell.pipeline,
        storage=fixture.cell.storage,
        invocations=invocations,
        control=MockRunControl(5, (), ()),
    )

    assert calls == 2
    assert binding_reads <= 1
    assert private_history_reads == 5
    assert full_public_history_reads == 0
    stored_payload = json.loads(
        fixture.cell.storage._connection.execute(
            "SELECT payload_json FROM execution_state WHERE singleton = 1"
        ).fetchone()[0]
    )
    assert stored_payload["storage_schema_version"] == ("paper1.execution-state-storage.v1")
    assert stored_payload["event_id_count"] == 5
    assert "event_ids" not in stored_payload
    assert fixture.cell.storage.execution_state().event_ids == tuple(
        derive_event_id(fixture.manifest.run_id, ordinal) for ordinal in range(5)
    )
    query_plan = fixture.cell.storage._connection.execute(
        """EXPLAIN QUERY PLAN
           SELECT event_ordinal, payload_json, payload_hash FROM private_updates
           WHERE agent_id = ?
           ORDER BY CASE WHEN event_ordinal IS NULL THEN -1 ELSE event_ordinal END""",
        (fixture.cell.storage.binding.expected_agent_ids[0],),
    ).fetchall()
    assert any(
        "idx_private_updates_agent_event" in str(detail) for row in query_plan for detail in row
    )
    fixture.cell.storage.close()


def test_n1000_t50_builds_twelve_bound_50000_event_shapes(tmp_path: Path) -> None:
    fixture = build_mock_matrix_fixture(
        tmp_path,
        case_id="mock-n1000-release-shape",
        sweeps=50,
    )

    assert validate_mock_matched_seed_matrix(fixture.matrix) is None
    assert tuple(cell.cell_id for cell in fixture.matrix.cells) == CANONICAL_CELL_IDS
    assert all(cell.manifest.schedule.count == 50_000 for cell in fixture.matrix.cells)
    assert all(
        cell.manifest.schedule.slots[0].event_ordinal == 0
        and cell.manifest.schedule.slots[-1].event_ordinal == 49_999
        and all(
            slot.event_ordinal == expected
            for expected, slot in enumerate(cell.manifest.schedule.slots)
        )
        for cell in fixture.matrix.cells
    )
    assert len({id(cell.manifest.schedule) for cell in fixture.matrix.cells}) == 1
    assert len({cell.manifest.schedule_hash for cell in fixture.matrix.cells}) == 1
    assert len({tuple(sorted(cell.artifact_hashes.items())) for cell in fixture.matrix.cells}) == 1
    assert len({cell.manifest.run_id for cell in fixture.matrix.cells}) == 12


def test_release_measurement_writes_final_sweep_checkpoint_and_reopens(
    tmp_path: Path,
) -> None:
    matrix = build_mock_matrix_fixture(
        tmp_path,
        case_id="mock-n20-fault-recovery",
        sweeps=2,
    )
    fixture = create_mock_matrix_cell(
        tmp_path,
        matrix_fixture=matrix,
        cell_id="P1-I1-C1-E2",
    )

    measurement = measure_mock_release_run(fixture)

    assert measurement.report.completed is True
    assert measurement.report.executed_event_count == 40
    assert measurement.adapter_calls == 40
    assert measurement.checkpoint_count == 1
    assert measurement.final_checkpoint.next_event_ordinal == 40
    assert measurement.audit.boundary_event_ordinal == 40
    fixture.cell.storage.close()


def _projection_hash(fixture) -> str:
    audit = build_mock_process_audit(
        storage=fixture.cell.storage,
        cell_id=fixture.cell_id,
        topic_package=fixture.matrix_fixture.family.topic_package,
        boundary_event_ordinal=fixture.cell.storage.progress.next_event_ordinal,
        outcome_labels=APPROVED_OUTCOME_LABELS,
        terminology_map_id=APPROVED_TERMINOLOGY_MAP_ID,
        terminology_map=APPROVED_TERMINOLOGY_MAP,
        model_provenance=fixture.manifest.model_identity,
        prompt_provenance={
            "template_id": "paper1.mock_prompt_template",
            "template_version": "1.0.0",
            "prompt_limits_hash": fixture.cell.prompt_limits.record_hash,
        },
        robustness_provenance={
            "mock_only": True,
            "research_parameter_status": "not_frozen",
        },
    )
    return build_mock_comparable_run_projection(fixture.cell.storage, audit).projection_hash


def _execute_prefix(fixture, start: int, stop: int) -> None:
    execute_mock_run(
        pipeline=fixture.cell.pipeline,
        storage=fixture.cell.storage,
        invocations=explicit_success_invocations(
            fixture.cell,
            start=start,
            stop=stop,
            feed_capacity=6,
            memory_window=3,
        ),
        control=MockRunControl(stop, (), ()),
    )


def test_n1000_t1_recovery_matches_uninterrupted_at_explicit_ordinals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_matrix = build_mock_matrix_fixture(
        tmp_path / "baseline",
        case_id="mock-n1000-release-shape",
        sweeps=1,
    )
    baseline = create_mock_matrix_cell(
        tmp_path / "baseline",
        matrix_fixture=baseline_matrix,
        cell_id="P1-I1-C1-E2",
    )
    _execute_prefix(baseline, 0, 1000)
    baseline_hash = _projection_hash(baseline)
    baseline.cell.storage.close()

    resumed_matrix = build_mock_matrix_fixture(
        tmp_path / "resumed",
        case_id="mock-n1000-release-shape",
        sweeps=1,
    )
    resumed = create_mock_matrix_cell(
        tmp_path / "resumed",
        matrix_fixture=resumed_matrix,
        cell_id="P1-I1-C1-E2",
    )
    _execute_prefix(resumed, 0, 1)
    resumed = reopen_mock_matrix_cell(resumed, reconciliation=None)
    _execute_prefix(resumed, 1, 500)

    post_invocation = explicit_success_invocations(
        resumed.cell,
        start=500,
        stop=501,
        feed_capacity=6,
        memory_window=3,
    )[0]
    with monkeypatch.context() as scoped:
        scoped.setattr(
            resumed.cell.storage,
            "record_finalized_attempt",
            lambda evidence: (_ for _ in ()).throw(RuntimeError("after invocation")),
        )
        with pytest.raises(RuntimeError, match="after invocation"):
            resumed.cell.pipeline.execute(
                feed_capacity=post_invocation.feed_capacity,
                memory_window=post_invocation.memory_window,
                parser_limits=post_invocation.parser_limits,
                prompt_limits=post_invocation.prompt_limits,
                policy=post_invocation.policy,
                model_identity=post_invocation.model_identity,
                request_parameters=post_invocation.request_parameters,
                model_seed=post_invocation.model_seed,
                adapter=post_invocation.adapter,
                reconciliation=None,
                http_status=post_invocation.http_status,
                usage=post_invocation.usage,
                finish_reason=post_invocation.finish_reason,
            )
    assert resumed.cell.storage.progress.next_event_ordinal == 500
    resumed = reopen_mock_matrix_cell(resumed, reconciliation=None)
    recovered = explicit_success_invocations(
        resumed.cell,
        start=500,
        stop=501,
        feed_capacity=6,
        memory_window=3,
    )[0]
    adapter_calls = 0

    def reject_resend(request):
        nonlocal adapter_calls
        adapter_calls += 1
        raise AssertionError(f"post-invocation recovery resent {request.request_id}")

    monkeypatch.setattr(recovered.adapter, "generate", reject_resend)
    execute_mock_run(
        pipeline=resumed.cell.pipeline,
        storage=resumed.cell.storage,
        invocations=(recovered,),
        control=MockRunControl(501, (), ()),
    )
    assert adapter_calls == 0
    _execute_prefix(resumed, 501, 1000)
    resumed = reopen_mock_matrix_cell(resumed, reconciliation=None)
    assert resumed.cell.storage.progress.next_event_ordinal == 1000
    assert _projection_hash(resumed) == baseline_hash
    resumed.cell.storage.close()


@pytest.mark.release_scale
def test_n1000_t50_stress_cell_executes_50000_real_mock_events(tmp_path: Path) -> None:
    fixture = build_stress_cell_fixture(
        tmp_path,
        case_id="mock-n1000-release-shape",
        cell_id="P1-I1-C1-E2",
    )
    try:
        measurement = measure_mock_release_run(fixture)
        assert measurement.report.completed is True
        assert measurement.report.executed_event_count == 50_000
        assert measurement.final_checkpoint.next_event_ordinal == 50_000
        assert measurement.final_checkpoint.resume_action == "complete"
        assert measurement.audit.boundary_event_ordinal == 50_000
        assert measurement.audit.outcome_labels == APPROVED_OUTCOME_LABELS
        assert measurement.audit.terminology_map_id == APPROVED_TERMINOLOGY_MAP_ID
        assert measurement.adapter_calls == 50_000
        assert measurement.checkpoint_count == 1
        print(
            "release-scale-measurement",
            {
                "events": measurement.report.executed_event_count,
                "elapsed_seconds": round(measurement.elapsed_seconds, 3),
                "peak_memory_bytes": measurement.peak_memory_bytes,
                "sqlite_bytes": measurement.sqlite_bytes,
                "checkpoint_count": measurement.checkpoint_count,
                "checkpoint_bytes": measurement.checkpoint_bytes,
                "audit_bytes": measurement.audit_bytes,
            },
        )
    finally:
        fixture.cell.storage.close()
