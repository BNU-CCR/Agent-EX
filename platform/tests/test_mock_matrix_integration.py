from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

import agent_ex.mock_run as mock_run_module
from agent_ex.adapters import MockAdapter, MockScriptStep
from agent_ex.checkpoint import (
    Checkpoint,
    build_checkpoint,
    load_checkpoint,
    validate_checkpoint,
    write_checkpoint_atomic,
)
from agent_ex.domain import derive_event_id
from agent_ex.engine import AttemptExecutionEvidence, AttemptInvocationResult
from agent_ex.mock_run import MockEventInvocation, MockRunControl, execute_mock_run
from agent_ex.process_audit import (
    APPROVED_OUTCOME_LABELS,
    APPROVED_TERMINOLOGY_MAP,
    APPROVED_TERMINOLOGY_MAP_ID,
    MockComparableRunProjection,
    build_mock_comparable_run_projection,
    build_mock_process_audit,
)
from helpers.mock_matrix import (
    BoundMockMatrixCell,
    build_mock_matrix_fixture,
    build_mock_matrix_fixture_with_steps,
    create_mock_matrix_cell,
    explicit_success_invocations,
    reopen_mock_matrix_cell,
)


@dataclass(frozen=True, slots=True)
class CompletedN20Run:
    run_id: str
    projection: MockComparableRunProjection
    final_checkpoint: Checkpoint


def _control(root: Path, start: int, stop: int) -> MockRunControl:
    checkpoints = (stop,) if stop == 40 else ()
    paths = (root / "checkpoint-40.json",) if checkpoints else ()
    return MockRunControl(stop, checkpoints, paths)


def _execute_prefix(fixture: BoundMockMatrixCell, root: Path, stop: int) -> None:
    start = fixture.cell.storage.progress.next_event_ordinal
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
        control=_control(root, start, stop),
    )


def _audit_projection(fixture: BoundMockMatrixCell) -> MockComparableRunProjection:
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
    return build_mock_comparable_run_projection(fixture.cell.storage, audit)


def _reconciliation(
    fixture: BoundMockMatrixCell,
    invocation: MockEventInvocation,
    request: object,
) -> AttemptInvocationResult:
    response = invocation.adapter.generate(request)
    journal = fixture.cell.storage.current_event_journal()
    assert journal.latest_transition is not None
    started_at = journal.latest_transition.started_at
    assert started_at is not None
    finished_at = (
        (
            datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            + timedelta(seconds=fixture.matrix_fixture.scale_case.mock_clock_step_seconds)
        )
        .isoformat()
        .replace("+00:00", "Z")
    )
    return AttemptInvocationResult(
        response=response,
        evidence=AttemptExecutionEvidence(
            started_at=started_at,
            finished_at=finished_at,
            http_status=invocation.http_status,
            provider_metadata=fixture.cell.pipeline._provider_metadata(response),
            usage=invocation.usage,
            finish_reason=invocation.finish_reason,
        ),
    )


def run_n20_fixture(
    root: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str | None,
) -> CompletedN20Run:
    matrix = build_mock_matrix_fixture(root, case_id="mock-n20-fault-recovery", sweeps=2)
    fixture = create_mock_matrix_cell(root, matrix_fixture=matrix, cell_id="P1-I0-C0-E0")
    if crash_point is None:
        _execute_prefix(fixture, root, 40)
    else:
        crash_ordinal = 7
        _execute_prefix(fixture, root, crash_ordinal)
        item = explicit_success_invocations(
            fixture.cell,
            start=crash_ordinal,
            stop=crash_ordinal + 1,
            feed_capacity=6,
            memory_window=3,
        )[0]
        reconciliation = None
        captured_request = None
        original_append = fixture.cell.storage.append_attempt
        original_write = mock_run_module.write_checkpoint_atomic

        def capture_prepared(*args, **kwargs):
            nonlocal captured_request
            captured_request = kwargs["request_evidence"].request
            return original_record_prepared(*args, **kwargs)

        def append_then_crash(attempt):
            original_append(attempt)
            raise RuntimeError(crash_point)

        def write_then_crash(path, checkpoint):
            original_write(path, checkpoint)
            raise RuntimeError(crash_point)

        original_record_prepared = fixture.cell.storage.record_prepared_attempt
        with monkeypatch.context() as scoped:
            if crash_point == "after_pending":
                scoped.setattr(
                    fixture.cell.storage,
                    "append_attempt",
                    lambda attempt: (_ for _ in ()).throw(RuntimeError(crash_point)),
                )
            elif crash_point == "after_in_progress_reconciled":
                scoped.setattr(fixture.cell.storage, "record_prepared_attempt", capture_prepared)
                scoped.setattr(fixture.cell.storage, "append_attempt", append_then_crash)
            elif crash_point == "after_invocation":
                scoped.setattr(
                    fixture.cell.storage,
                    "record_finalized_attempt",
                    lambda evidence: (_ for _ in ()).throw(RuntimeError(crash_point)),
                )
            elif crash_point == "after_terminal_success":
                scoped.setattr(
                    fixture.cell.storage,
                    "commit_success",
                    lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(crash_point)),
                )
            elif crash_point == "after_sqlite_commit_before_context":
                scoped.setattr(
                    fixture.cell.pipeline,
                    "_advance_run_context_after_commit",
                    lambda event_id: (_ for _ in ()).throw(RuntimeError(crash_point)),
                )
            elif crash_point == "after_checkpoint_write":
                scoped.setattr(mock_run_module, "write_checkpoint_atomic", write_then_crash)
            else:
                raise AssertionError(f"unsupported crash point: {crash_point}")
            with pytest.raises(RuntimeError, match=crash_point):
                if crash_point == "after_checkpoint_write":
                    execute_mock_run(
                        pipeline=fixture.cell.pipeline,
                        storage=fixture.cell.storage,
                        invocations=(item,),
                        control=MockRunControl(
                            crash_ordinal + 1,
                            (crash_ordinal + 1,),
                            (root / "crash-checkpoint.json",),
                        ),
                    )
                else:
                    fixture.cell.pipeline.execute(
                        feed_capacity=item.feed_capacity,
                        memory_window=item.memory_window,
                        parser_limits=item.parser_limits,
                        prompt_limits=item.prompt_limits,
                        policy=item.policy,
                        model_identity=item.model_identity,
                        request_parameters=item.request_parameters,
                        model_seed=item.model_seed,
                        adapter=item.adapter,
                        reconciliation=item.reconciliation,
                        http_status=item.http_status,
                        usage=item.usage,
                        finish_reason=item.finish_reason,
                    )

        if crash_point == "after_in_progress_reconciled":
            assert captured_request is not None
            reconciliation = _reconciliation(fixture, item, captured_request)
        fixture = reopen_mock_matrix_cell(fixture, reconciliation=reconciliation)
        if crash_point == "after_checkpoint_write":
            crash_checkpoint = load_checkpoint(root / "crash-checkpoint.json")
            assert crash_checkpoint.next_event_ordinal == crash_ordinal + 1
            assert validate_checkpoint(crash_checkpoint, fixture.cell.storage) == "current"
        progress = fixture.cell.storage.progress.next_event_ordinal
        if progress == crash_ordinal:
            recovered = replace(item, reconciliation=reconciliation)
            if crash_point not in {"after_pending"}:
                monkeypatch.setattr(
                    recovered.adapter,
                    "generate",
                    lambda request: (_ for _ in ()).throw(
                        AssertionError(f"recovery resent {request.request_id}")
                    ),
                )
            execute_mock_run(
                pipeline=fixture.cell.pipeline,
                storage=fixture.cell.storage,
                invocations=(recovered,),
                control=MockRunControl(crash_ordinal + 1, (), ()),
            )
        assert fixture.cell.storage.progress.next_event_ordinal == crash_ordinal + 1
        _execute_prefix(fixture, root, 40)

    fixture.cell.storage.assert_complete()
    result = CompletedN20Run(
        run_id=fixture.manifest.run_id,
        projection=_audit_projection(fixture),
        final_checkpoint=build_checkpoint(fixture.cell.storage),
    )
    fixture.cell.storage.close()
    return result


@pytest.mark.parametrize(
    "crash_point",
    (
        "after_pending",
        "after_in_progress_reconciled",
        "after_invocation",
        "after_terminal_success",
        "after_sqlite_commit_before_context",
        "after_checkpoint_write",
    ),
)
def test_n20_recovery_matches_uninterrupted_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    uninterrupted = run_n20_fixture(
        tmp_path / "continuous", monkeypatch=monkeypatch, crash_point=None
    )
    resumed = run_n20_fixture(
        tmp_path / "resumed", monkeypatch=monkeypatch, crash_point=crash_point
    )

    assert resumed.run_id != uninterrupted.run_id
    assert resumed.final_checkpoint.checkpoint_hash != (
        uninterrupted.final_checkpoint.checkpoint_hash
    )
    assert resumed.projection.projection_hash == uninterrupted.projection.projection_hash
    assert resumed.final_checkpoint.next_event_ordinal == 40


def _success_step(ordinal: int) -> MockScriptStep:
    return MockScriptStep.success(
        {
            "stance": "L4",
            "confidence": 3,
            "public_reason": f"mock matrix event {ordinal}",
        }
    )


def _scripted_cell(
    root: Path, *, first_event_steps: tuple[MockScriptStep, ...]
) -> tuple[BoundMockMatrixCell, MockAdapter]:
    steps = (first_event_steps,) + tuple((_success_step(index),) for index in range(1, 40))
    matrix = build_mock_matrix_fixture_with_steps(
        root,
        case_id="mock-n20-fault-recovery",
        sweeps=2,
        steps_by_ordinal=steps,
    )
    fixture = create_mock_matrix_cell(root, matrix_fixture=matrix, cell_id="P1-I0-C0-E0")
    adapter = MockAdapter(
        script={
            derive_event_id(fixture.manifest.run_id, ordinal): event_steps
            for ordinal, event_steps in enumerate(steps)
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    return fixture, adapter


def _adapter_invocation(
    fixture: BoundMockMatrixCell, adapter: MockAdapter, *, model_seed: int = 10_000
) -> MockEventInvocation:
    return MockEventInvocation(
        event_ordinal=0,
        event_id=derive_event_id(fixture.manifest.run_id, 0),
        feed_capacity=6,
        memory_window=3,
        parser_limits=fixture.cell.parser_limits,
        prompt_limits=fixture.cell.prompt_limits,
        policy=fixture.cell.policy,
        model_identity=adapter.execution_binding().model_identity,
        request_parameters=fixture.cell.request_parameters,
        model_seed=model_seed,
        adapter=adapter,
        reconciliation=None,
        http_status=fixture.cell.http_status,
        usage=fixture.cell.usage,
        finish_reason=fixture.cell.finish_reason,
    )


def _execute_item(fixture: BoundMockMatrixCell, item: MockEventInvocation):
    return fixture.cell.pipeline.execute(
        feed_capacity=item.feed_capacity,
        memory_window=item.memory_window,
        parser_limits=item.parser_limits,
        prompt_limits=item.prompt_limits,
        policy=item.policy,
        model_identity=item.model_identity,
        request_parameters=item.request_parameters,
        model_seed=item.model_seed,
        adapter=item.adapter,
        reconciliation=item.reconciliation,
        http_status=item.http_status,
        usage=item.usage,
        finish_reason=item.finish_reason,
    )


def _research_snapshot(fixture: BoundMockMatrixCell) -> tuple[object, ...]:
    store = fixture.cell.storage
    roster = store.binding.expected_agent_ids
    return (
        store.progress,
        tuple(store.private_state(agent) for agent in roster),
        tuple(store.latest_public_pointer(agent) for agent in roster),
        tuple(store.feed_cursor(agent) for agent in roster),
        store.event_at(store.progress.next_event_ordinal),
    )


@pytest.mark.parametrize(
    ("failure_step", "expected_reason"),
    (
        (MockScriptStep.timeout("integration timeout"), "adapter_timeout"),
        (MockScriptStep.malformed("not-json"), "parse_failure"),
    ),
)
def test_n20_terminal_failure_is_atomic_and_never_auto_authorized(
    tmp_path: Path,
    failure_step: MockScriptStep,
    expected_reason: str,
) -> None:
    fixture, adapter = _scripted_cell(
        tmp_path,
        first_event_steps=(failure_step, _success_step(0)),
    )
    item = _adapter_invocation(fixture, adapter)
    before = _research_snapshot(fixture)

    outcome = _execute_item(fixture, item)

    assert outcome.lifecycle.state == "failed"
    assert _research_snapshot(fixture) == before
    failure = fixture.cell.storage.terminal_failure_evidence()
    assert failure is not None and failure.reason == expected_reason
    with pytest.raises(RuntimeError, match="explicit external authorization"):
        _execute_item(fixture, item)
    assert fixture.cell.storage.resume_authorization_evidence() is None

    with fixture.cell.storage.acquire_run_lease():
        fixture.cell.storage.authorize_resume(
            authorization_id=f"resume-{expected_reason}",
            event_id=failure.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id=f"policy-{expected_reason}",
            policy_evidence_hash="b" * 64,
            authorized_at="2040-01-01T00:00:10Z",
        )
    retried = _execute_item(fixture, replace(item, model_seed=10_001))
    assert retried.lifecycle.state == "committed"
    assert fixture.cell.storage.progress.next_event_ordinal == 1
    fixture.cell.storage.close()


def test_n20_request_parameter_drift_leaves_research_state_unchanged(
    tmp_path: Path,
) -> None:
    fixture, adapter = _scripted_cell(tmp_path, first_event_steps=(_success_step(0),))
    item = replace(_adapter_invocation(fixture, adapter), request_parameters={"temperature": 0.1})
    before = _research_snapshot(fixture)

    with pytest.raises(ValueError, match="first-attempt request parameters"):
        _execute_item(fixture, item)

    assert _research_snapshot(fixture) == before
    fixture.cell.storage.close()


def test_n20_pending_recovery_rejects_unauthorized_model_seed_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, adapter = _scripted_cell(tmp_path, first_event_steps=(_success_step(0),))
    item = _adapter_invocation(fixture, adapter)
    before = _research_snapshot(fixture)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.cell.storage,
            "append_attempt",
            lambda attempt: (_ for _ in ()).throw(RuntimeError("after_pending")),
        )
        with pytest.raises(RuntimeError, match="after_pending"):
            _execute_item(fixture, item)
    fixture = reopen_mock_matrix_cell(fixture, reconciliation=None)

    with pytest.raises(ValueError, match="exact transition|drift|persisted"):
        _execute_item(fixture, replace(item, model_seed=10_001))

    assert _research_snapshot(fixture) == before
    fixture.cell.storage.close()


def test_n20_finalization_mismatch_never_commits_research_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, adapter = _scripted_cell(tmp_path, first_event_steps=(_success_step(0),))
    item = _adapter_invocation(fixture, adapter)
    before = _research_snapshot(fixture)
    original_finalize = fixture.cell.pipeline._finalize

    def mismatched_finalize(prepared, result):
        return replace(original_finalize(prepared, result), request_hash="f" * 64)

    monkeypatch.setattr(fixture.cell.pipeline, "_finalize", mismatched_finalize)
    with pytest.raises(ValueError, match="request hash"):
        _execute_item(fixture, item)

    assert _research_snapshot(fixture) == before
    fixture.cell.storage.close()


def test_n20_checkpoint_tamper_fails_closed_without_changing_storage(
    tmp_path: Path,
) -> None:
    fixture, _ = _scripted_cell(tmp_path, first_event_steps=(_success_step(0),))
    checkpoint_path = tmp_path / "tampered-checkpoint.json"
    write_checkpoint_atomic(checkpoint_path, build_checkpoint(fixture.cell.storage))
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    payload["next_event_ordinal"] = 1
    checkpoint_path.write_text(json.dumps(payload), encoding="utf-8")
    before = _research_snapshot(fixture)

    with pytest.raises(ValueError, match="hash|checkpoint|progress"):
        load_checkpoint(checkpoint_path)

    assert _research_snapshot(fixture) == before
    fixture.cell.storage.close()
