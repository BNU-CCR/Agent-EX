from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

import agent_ex.mock_run as mock_run_module
from agent_ex.adapters import MockAdapter, MockScriptStep
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.checkpoint import (
    Checkpoint,
    build_checkpoint,
    load_checkpoint,
    validate_checkpoint,
    write_checkpoint_atomic,
)
from agent_ex.domain import canonical_payload_hash, derive_event_id, derive_run_id
from agent_ex.mock_matrix import (
    CANONICAL_CELL_IDS,
    build_mock_matched_seed_matrix,
    validate_mock_matched_seed_matrix,
)
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
from agent_ex.persona import render_persona, validate_persona_factor_diff
from helpers.mock_matrix import (
    BoundMockMatrixCell,
    build_mock_matrix_fixture,
    build_mock_matrix_fixture_with_steps,
    create_mock_matrix_cell,
    execute_all_cells,
    explicit_success_invocations,
    open_completed_mock_matrix_cell,
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


def _mapping_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, dict):
        return tuple(str(key) for key in value) + tuple(
            key for item in value.values() for key in _mapping_keys(item)
        )
    if isinstance(value, (list, tuple)):
        return tuple(key for item in value for key in _mapping_keys(item))
    return ()


@pytest.mark.release_integration
def test_n100_executes_complete_twelve_cell_matrix_without_result_selection(
    tmp_path: Path,
) -> None:
    fixture = build_mock_matrix_fixture(
        tmp_path,
        case_id="mock-n100-full-matrix",
        sweeps=1,
    )

    results = execute_all_cells(fixture)

    assert tuple(results) == CANONICAL_CELL_IDS
    assert all(result.run_report.completed for result in results.values())
    assert all(result.run_report.executed_event_count == 100 for result in results.values())
    assert all(
        result.process_audit.outcome_labels == APPROVED_OUTCOME_LABELS
        for result in results.values()
    )
    assert len({cell.manifest.schedule_hash for cell in fixture.matrix.cells}) == 1
    assert len({tuple(sorted(cell.artifact_hashes.items())) for cell in fixture.matrix.cells}) == 1
    assert len({cell.manifest.run_id for cell in fixture.matrix.cells}) == 12
    expected_graphs = {
        "self_history_only": None,
        "shuffled_social": fixture.family.shadow_artifact.output_hash,
        "ws_neighbors": fixture.family.ws_artifact.output_hash,
    }
    assert all(
        cell.exposure_graph_hash == expected_graphs[cell.exposure_mode]
        for cell in fixture.matrix.cells
    )
    sqlite_paths = tuple(tmp_path.rglob("*.sqlite"))
    assert len(sqlite_paths) == len(set(path.resolve() for path in sqlite_paths)) == 12
    forbidden = ("ranking", "effect", "significance", "p_value", "selected_result")
    assert all(
        not any(token in key.casefold() for token in forbidden)
        for result in results.values()
        for key in _mapping_keys(result.process_audit.to_payload())
    )

    first_agent = fixture.matrix.cells[0].manifest.schedule.slots[0].agent_id
    member = next(
        value
        for value in fixture.family.population_artifact.payload["members"]
        if value["agent_id"] == first_agent
    )
    expected_personas = {
        (identity, continuity): render_persona(
            fixture.family.persona_template,
            member,
            {"identity_present": identity, "continuity_present": continuity},
        )
        for identity in (False, True)
        for continuity in (False, True)
    }
    assert validate_persona_factor_diff(tuple(expected_personas.values()))["valid"] is True
    observed_by_condition: dict[tuple[bool, bool], set[str]] = {
        condition: set() for condition in expected_personas
    }
    for cell in fixture.matrix.cells:
        opened = open_completed_mock_matrix_cell(fixture, cell_id=cell.cell_id)
        event_input = opened.cell.storage.event_input_evidence(
            derive_event_id(opened.manifest.run_id, 0)
        )
        assert event_input is not None
        condition = (cell.identity_present, cell.continuity_present)
        expected_text = expected_personas[condition].payload["rendered_text"]
        assert event_input.prompt_view.persona_text == expected_text
        observed_by_condition[condition].add(event_input.prompt_view.persona_text)
        opened.cell.storage.close()
    assert all(len(values) == 1 for values in observed_by_condition.values())


def run_n100_t1_recovery_pair(root: Path) -> tuple[str, str, int]:
    cell_id = "P1-I1-C1-E2"

    uninterrupted_matrix = build_mock_matrix_fixture(
        root / "continuous",
        case_id="mock-n100-full-matrix",
        sweeps=1,
    )
    uninterrupted = create_mock_matrix_cell(
        root / "continuous" / cell_id,
        matrix_fixture=uninterrupted_matrix,
        cell_id=cell_id,
    )
    _execute_prefix(uninterrupted, root / "continuous", 100)
    uninterrupted.cell.storage.assert_complete()
    uninterrupted_hash = _audit_projection(uninterrupted).projection_hash
    uninterrupted.cell.storage.close()

    recovered_matrix = build_mock_matrix_fixture(
        root / "recovered",
        case_id="mock-n100-full-matrix",
        sweeps=1,
    )
    recovered = create_mock_matrix_cell(
        root / "recovered" / cell_id,
        matrix_fixture=recovered_matrix,
        cell_id=cell_id,
    )
    _execute_prefix(recovered, root / "recovered", 50)
    recovered = reopen_mock_matrix_cell(recovered, reconciliation=None)

    resumed = explicit_success_invocations(
        recovered.cell,
        start=50,
        stop=100,
        feed_capacity=6,
        memory_window=3,
    )
    resumed_adapter_calls = 0
    adapter = resumed[0].adapter
    original_generate = adapter.generate

    def counted_generate(request):
        nonlocal resumed_adapter_calls
        resumed_adapter_calls += 1
        return original_generate(request)

    adapter.generate = counted_generate  # type: ignore[method-assign]
    execute_mock_run(
        pipeline=recovered.cell.pipeline,
        storage=recovered.cell.storage,
        invocations=resumed,
        control=MockRunControl(100, (), ()),
    )
    recovered.cell.storage.assert_complete()
    recovered_hash = _audit_projection(recovered).projection_hash
    recovered.cell.storage.close()
    return uninterrupted_hash, recovered_hash, resumed_adapter_calls


def test_n100_t1_close_open_recovery_matches_uninterrupted_projection(tmp_path: Path) -> None:
    uninterrupted_hash, recovered_hash, resumed_adapter_calls = run_n100_t1_recovery_pair(tmp_path)

    assert recovered_hash == uninterrupted_hash
    assert resumed_adapter_calls == 50


def _rehash_artifact(artifact: ArtifactEnvelope, payload: dict[str, object]) -> ArtifactEnvelope:
    return ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        payload=payload,
        rng_provenance=artifact.rng_provenance,
    )


def _matrix_builder_inputs(fixture) -> dict[str, object]:
    family = fixture.family
    return {
        "scale_case": fixture.scale_case,
        "matched_seed": fixture.matrix.matched_seed,
        "topic_package": family.topic_package,
        "population_artifact": family.population_artifact,
        "initial_stance_artifact": family.initial_stance_artifact,
        "initial_reason_artifact": family.initial_reason_artifact,
        "persona_template": family.persona_template,
        "ws_artifact": family.ws_artifact,
        "shadow_artifact": family.shadow_artifact,
        "agent_node_mapping": family.agent_node_mapping,
        "structural_gate_artifact": family.structural_gate_artifact,
        "attention_artifact": family.attention_artifact,
        "expression_artifact": family.expression_artifact,
        "activation_artifact": family.activation_artifact,
        "publish_artifact": family.publish_artifact,
        "schedules_by_cell": family.schedules_by_cell,
        "manifests_by_cell": family.manifests_by_cell,
        "adapter_bindings_by_cell": family.adapter_bindings_by_cell,
    }


def _semantic_artifact_attack(fixture, attack: str) -> tuple[str, ArtifactEnvelope]:
    family = fixture.family
    field, artifact = {
        "population": ("population_artifact", family.population_artifact),
        "stance": ("initial_stance_artifact", family.initial_stance_artifact),
        "reason": ("initial_reason_artifact", family.initial_reason_artifact),
        "mapping": ("agent_node_mapping", family.agent_node_mapping),
        "attention": ("attention_artifact", family.attention_artifact),
        "expression": ("expression_artifact", family.expression_artifact),
        "activation": ("activation_artifact", family.activation_artifact),
        "publish": ("publish_artifact", family.publish_artifact),
    }[attack]
    payload = artifact.to_payload()["payload"]
    if attack == "population":
        payload["members"][0]["fields"]["occupation"] += "-changed"
    elif attack == "stance":
        assignments = payload["assignments"]
        assignments[0]["stance"], assignments[1]["stance"] = (
            assignments[1]["stance"],
            assignments[0]["stance"],
        )
    elif attack == "reason":
        payload["round0_records"][0]["private_state"]["reason"] += " changed"
    elif attack == "mapping":
        assignments = payload["assignments"]
        assignments[0]["node_id"], assignments[1]["node_id"] = (
            assignments[1]["node_id"],
            assignments[0]["node_id"],
        )
    elif attack == "attention":
        payload["agents"][0]["raw_weight"] = payload["agents"][0]["weight"] = 1.1
        payload["agents"][1]["raw_weight"] = payload["agents"][1]["weight"] = 0.9
    elif attack == "expression":
        agent = payload["agents"][0]
        agent["structural_lurker"] = not agent["structural_lurker"]
        agent["publish_probability"] = 0.0 if agent["structural_lurker"] else 0.5
    elif attack == "activation":
        slots = payload["slots"]
        slots[0]["agent_id"], slots[1]["agent_id"] = (
            slots[1]["agent_id"],
            slots[0]["agent_id"],
        )
    else:
        slot = payload["frozen_schedule"]["slots"][0]
        slot["publish_flag"] = not slot["publish_flag"]
    changed = _rehash_artifact(artifact, payload)
    assert changed.output_hash != artifact.output_hash
    return field, changed


@pytest.mark.parametrize(
    "attack",
    (
        "population",
        "stance",
        "reason",
        "mapping",
        "attention",
        "expression",
        "activation",
        "publish",
        "graph",
        "manifest",
        "script",
    ),
)
def test_n100_cross_cell_attack_fails_before_first_execution(tmp_path: Path, attack: str) -> None:
    fixture = build_mock_matrix_fixture(
        tmp_path,
        case_id="mock-n100-full-matrix",
        sweeps=1,
    )
    cells = list(fixture.matrix.cells)
    target_index = 1 if attack == "graph" else 0
    target = cells[target_index]
    if attack in {
        "population",
        "stance",
        "reason",
        "mapping",
        "attention",
        "expression",
        "activation",
        "publish",
    }:
        field, artifact = _semantic_artifact_attack(fixture, attack)
        with pytest.raises(ValueError):
            build_mock_matched_seed_matrix(**{**_matrix_builder_inputs(fixture), field: artifact})
    elif attack == "graph":
        cells[target_index] = replace(target, exposure_graph_hash="f" * 64)
    elif attack == "manifest":
        changed_spec = {**target.manifest.run_spec, "cell_id": "P1-I1-C0-E0"}
        cells[target_index] = replace(
            target,
            manifest=replace(
                target.manifest,
                run_id=derive_run_id(
                    changed_spec,
                    target.manifest.matched_seed,
                    target.manifest.launch_nonce,
                ),
                run_spec=changed_spec,
                run_spec_hash=canonical_payload_hash(changed_spec),
            ),
        )
    else:
        changed_adapter = MockAdapter(
            script={
                derive_event_id(target.manifest.run_id, ordinal): (
                    MockScriptStep.success(
                        {
                            "stance": "L4",
                            "confidence": 3,
                            "public_reason": (
                                "changed mock script"
                                if ordinal == 0
                                else f"mock matrix event {ordinal}"
                            ),
                        }
                    ),
                )
                for ordinal in range(target.manifest.schedule.count)
            },
            mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
            mock_only=True,
        )
        assert changed_adapter.execution_binding() != target.adapter_binding
        cells[target_index] = replace(
            target,
            adapter_binding=changed_adapter.execution_binding(),
        )
    if attack not in {
        "population",
        "stance",
        "reason",
        "mapping",
        "attention",
        "expression",
        "activation",
        "publish",
    }:
        attacked = replace(fixture.matrix, cells=tuple(cells))
        with pytest.raises(ValueError):
            validate_mock_matched_seed_matrix(attacked)

    assert not tuple(tmp_path.rglob("*.sqlite"))
