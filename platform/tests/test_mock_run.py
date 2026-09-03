from __future__ import annotations

from dataclasses import MISSING, fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import agent_ex
import agent_ex.pipeline as pipeline_module
import agent_ex.mock_run as mock_run_module
from agent_ex.adapters import MockAdapter, MockScriptStep
from agent_ex.domain import canonical_payload_hash, derive_event_id
from agent_ex.engine import AttemptExecutionEvidence, AttemptInvocationResult, AttemptOutcome
from agent_ex.feed import FeedCursor
from agent_ex.mock_matrix import MockScaleCase
from agent_ex.mock_run import (
    MockEventInvocation,
    MockRunControl,
    MockRunReport,
    execute_mock_run,
)
from agent_ex.pipeline import MockEventPipeline
from agent_ex.state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from helpers.mock_matrix import (
    MatrixCellFixture,
    MockClockLedger,
    build_mock_matrix_fixture,
    explicit_success_invocations,
    rebuild_mock_clock_ledger,
)
from test_pipeline import (
    _authorize_pipeline_retry,
    _fixture,
    _limits,
    _reopen_fixture,
)
from test_prompt import persona_template
from agent_ex.execution_evidence import MockAttemptPolicyBinding
from agent_ex.storage import RunStorage


def invocation(fixture, ordinal: int = 0) -> MockEventInvocation:
    values = fixture.execute_kwargs
    return MockEventInvocation(
        event_ordinal=ordinal,
        event_id=derive_event_id(fixture.store.binding.run_id, ordinal),
        feed_capacity=values["feed_capacity"],
        memory_window=values["memory_window"],
        parser_limits=values["parser_limits"],
        prompt_limits=values["prompt_limits"],
        policy=values["policy"],
        model_identity=values["model_identity"],
        request_parameters=values["request_parameters"],
        model_seed=values["model_seed"],
        adapter=values["adapter"],
        reconciliation=values["reconciliation"],
        http_status=values["http_status"],
        usage=values["usage"],
        finish_reason=values["finish_reason"],
    )


def control(tmp_path: Path, *, target: int = 1) -> MockRunControl:
    return MockRunControl(
        target_event_ordinal=target,
        checkpoint_ordinals=(target,),
        checkpoint_paths=(tmp_path / f"checkpoint-{target}.json",),
    )


def scale_case() -> MockScaleCase:
    return MockScaleCase(
        case_id="mock-task3-clock",
        population_size=20,
        stance_counts=(1, 2, 4, 6, 4, 2, 1),
        integration_sweeps=1,
        recovery_sweeps=1,
        shape_sweeps=1,
        full_matrix_execution=False,
        release_execution=False,
        stress_cell_id=None,
        mock_feed_capacity=6,
        mock_memory_window=3,
        mock_clock_start="2040-01-01T00:00:00Z",
        mock_clock_step_seconds=1,
    )


def cell_fixture(fixture, pipeline=None) -> MatrixCellFixture:
    values = fixture.execute_kwargs
    return MatrixCellFixture(
        pipeline=fixture.pipeline if pipeline is None else pipeline,
        storage=fixture.store,
        parser_limits=values["parser_limits"],
        prompt_limits=values["prompt_limits"],
        policy=values["policy"],
        model_identity=values["model_identity"],
        request_parameters=values["request_parameters"],
        http_status=values["http_status"],
        usage=values["usage"],
        finish_reason=values["finish_reason"],
        stance_label="label-4",
    )


def invocation_kwargs(item: MockEventInvocation) -> dict[str, object]:
    return {
        field.name: getattr(item, field.name)
        for field in fields(MockEventInvocation)
        if field.name not in {"event_ordinal", "event_id"}
    }


def bound_matrix_cell_fixture(tmp_path: Path) -> tuple[MatrixCellFixture, object]:
    built = build_mock_matrix_fixture(tmp_path, case_id="mock-n20-fault-recovery", sweeps=2)
    family = built.family
    cell = next(value for value in built.matrix.cells if value.cell_id == "P1-I0-C0-E0")
    artifacts = {
        artifact.artifact_id: artifact.output_hash
        for artifact in (
            family.population_artifact,
            family.initial_stance_artifact,
            family.initial_reason_artifact,
            family.persona_template,
            family.ws_artifact,
            family.shadow_artifact,
            family.agent_node_mapping,
            family.structural_gate_artifact,
            family.attention_artifact,
            family.expression_artifact,
            family.activation_artifact,
            family.publish_artifact,
        )
    }
    store = RunStorage.create(
        tmp_path / "matrix-cell.sqlite",
        manifest=cell.manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=tuple(
            record["agent_id"] for record in family.population_artifact.payload["members"]
        ),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        expected_exposure_graph_artifact=None,
        expected_source_ws_artifact=None,
    )
    round0 = {
        record["agent_id"]: record
        for record in family.initial_reason_artifact.payload["round0_records"]
    }
    with store.acquire_run_lease():
        for agent_id in store.binding.expected_agent_ids:
            record = round0[agent_id]
            stance = record["private_state"]["stance"]
            update = PrivateUpdate.create(
                topic_package=family.topic_package,
                matched_seed=cell.manifest.matched_seed,
                agent_id=agent_id,
                event_id=None,
                event_ordinal=None,
                sequence_index=0,
                stance_label=family.topic_package.stance_labels[stance - 1],
                reason=record["private_state"]["reason"],
                confidence=None,
                published=True,
                source_attempt_id=None,
                mock_only=True,
            )
            state = PrivateState.from_update(update, previous=None, mock_only=True)
            post = PublicPost.from_private_update(update, mock_only=True)
            pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
            cursor = FeedCursor.initial(
                matched_seed=cell.manifest.matched_seed,
                receiver_agent_id=agent_id,
                exposure_mode="self_history_only",
                exposure_graph_hash=None,
                mock_only=True,
            )
            store.initialize_agent(update, state, post, pointer, cursor)
        store.seal_initial_state()
    parser_limits, prompt_limits = _limits()
    policy = MockAttemptPolicyBinding.create(
        allowed_difference_fields=("model_seed", "request_parameters.temperature"),
        mock_only=True,
        formal_eligible=False,
    )
    pipeline = MockEventPipeline(
        storage=store,
        manifest=cell.manifest,
        topic_package=family.topic_package,
        persona_template=persona_template(),
        population_artifact=family.population_artifact,
        exposure_graph_artifact=None,
        source_ws_artifact=None,
        agent_node_mapping_artifact=None,
        round0_initialization_artifact=None,
        frozen_neighbor_agent_ids={agent_id: () for agent_id in store.binding.expected_agent_ids},
        clock=built.clock,
    )
    return (
        MatrixCellFixture(
            pipeline=pipeline,
            storage=store,
            parser_limits=parser_limits,
            prompt_limits=prompt_limits,
            policy=policy,
            model_identity=cell.adapter_binding.model_identity,
            request_parameters={"temperature": 0.0},
            http_status=200,
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            finish_reason="stop",
            stance_label=family.topic_package.stance_labels[3],
        ),
        cell.manifest,
    )


def test_mock_run_contract_has_no_execution_policy_or_timestamp_defaults() -> None:
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in inspect.signature(execute_mock_run).parameters.values()
    )
    assert all(
        field.default is MISSING and field.default_factory is MISSING
        for field in fields(MockEventInvocation)
    )
    assert "timestamp" not in {field.name for field in fields(MockEventInvocation)}
    assert "clock" not in inspect.signature(execute_mock_run).parameters


def test_run_harness_delegates_event_and_writes_exact_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    writes: list[tuple[int, Path]] = []
    original_write = mock_run_module.write_checkpoint_atomic

    def tracked_write(path, checkpoint):
        writes.append((fixture.store.progress.next_event_ordinal, Path(path)))
        return original_write(path, checkpoint)

    monkeypatch.setattr(mock_run_module, "write_checkpoint_atomic", tracked_write)

    report = execute_mock_run(
        pipeline=fixture.pipeline,
        storage=fixture.store,
        invocations=(invocation(fixture),),
        control=control(tmp_path),
    )

    assert isinstance(report, MockRunReport)
    assert report.starting_event_ordinal == 0
    assert report.next_event_ordinal == 1
    assert report.executed_event_count == 1
    assert report.completed is True
    assert tuple(report.checkpoint_hashes) == (1,)
    assert writes == [(1, tmp_path / "checkpoint-1.json")]
    assert report.final_checkpoint_hash == report.checkpoint_hashes[1]
    assert len(report.final_storage_projection_hash) == 64


def test_run_harness_delegates_every_event_with_deterministic_clock(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E1")
    ledger = MockClockLedger(scale_case=scale_case(), replay_values=(), next_sequence_index=0)
    pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": ledger})
    invocations = explicit_success_invocations(
        cell_fixture(fixture, pipeline),
        start=0,
        stop=40,
        feed_capacity=4,
        memory_window=3,
    )

    report = execute_mock_run(
        pipeline=pipeline,
        storage=fixture.store,
        invocations=invocations,
        control=MockRunControl(
            target_event_ordinal=40,
            checkpoint_ordinals=(20, 40),
            checkpoint_paths=(tmp_path / "checkpoint-20.json", tmp_path / "checkpoint-40.json"),
        ),
    )

    assert report.executed_event_count == 40
    assert tuple(report.checkpoint_hashes) == (20, 40)
    assert len(ledger.calls) == 80
    assert ledger.calls[0] == "2040-01-01T00:00:00Z"
    assert ledger.calls[-1] == "2040-01-01T00:01:19Z"


def test_matrix_adapter_script_is_bound_before_first_state_write(tmp_path: Path) -> None:
    fixture, manifest = bound_matrix_cell_fixture(tmp_path)
    item = explicit_success_invocations(
        fixture,
        start=0,
        stop=1,
        feed_capacity=6,
        memory_window=3,
    )[0]
    script = {
        derive_event_id(manifest.run_id, ordinal): (
            MockScriptStep.success(
                {
                    "stance": fixture.stance_label,
                    "confidence": 3,
                    "public_reason": (
                        "tampered matrix event" if ordinal == 0 else f"mock matrix event {ordinal}"
                    ),
                }
            ),
        )
        for ordinal in range(manifest.schedule.count)
    }
    tampered = MockAdapter(
        script=script,
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    before = canonical_payload_hash(fixture.storage.recovery_evidence())

    with pytest.raises(ValueError, match="adapter semantics|matrix"):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.storage,
            invocations=(
                replace(
                    item,
                    adapter=tampered,
                    model_identity=tampered.execution_binding().model_identity,
                ),
            ),
            control=control(tmp_path),
        )

    assert fixture.storage.progress.next_event_ordinal == 0
    assert fixture.storage.attempts_for_event(item.event_id) == ()
    assert canonical_payload_hash(fixture.storage.recovery_evidence()) == before


def test_matrix_adapter_binding_is_fully_checked_once_per_immutable_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, _ = bound_matrix_cell_fixture(tmp_path)
    items = explicit_success_invocations(
        fixture,
        start=0,
        stop=40,
        feed_capacity=6,
        memory_window=3,
    )
    calls = 0
    original = pipeline_module.mock_adapter_semantics_hash

    def counted(binding, event_ids):
        nonlocal calls
        calls += 1
        return original(binding, event_ids)

    monkeypatch.setattr(pipeline_module, "mock_adapter_semantics_hash", counted)
    for item in items:
        assert fixture.pipeline.execute(**invocation_kwargs(item)).lifecycle.state == "committed"

    assert calls == 1


def test_matrix_adapter_binding_is_rechecked_for_an_equal_distinct_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, manifest = bound_matrix_cell_fixture(tmp_path)
    items = explicit_success_invocations(
        fixture,
        start=0,
        stop=3,
        feed_capacity=6,
        memory_window=3,
    )
    clone = MockAdapter(
        script={
            derive_event_id(manifest.run_id, ordinal): (
                MockScriptStep.success(
                    {
                        "stance": fixture.stance_label,
                        "confidence": 3,
                        "public_reason": f"mock matrix event {ordinal}",
                    }
                ),
            )
            for ordinal in range(manifest.schedule.count)
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    assert clone.execution_binding() == items[0].adapter.execution_binding()
    assert clone.execution_binding() is not items[0].adapter.execution_binding()
    calls = 0
    original = pipeline_module.mock_adapter_semantics_hash

    def counted(binding, event_ids):
        nonlocal calls
        calls += 1
        return original(binding, event_ids)

    monkeypatch.setattr(pipeline_module, "mock_adapter_semantics_hash", counted)
    assert fixture.pipeline.execute(**invocation_kwargs(items[0])).lifecycle.state == "committed"
    assert fixture.pipeline.execute(**invocation_kwargs(items[1])).lifecycle.state == "committed"
    clone_item = replace(
        items[2], adapter=clone, model_identity=clone.execution_binding().model_identity
    )
    assert fixture.pipeline.execute(**invocation_kwargs(clone_item)).lifecycle.state == "committed"
    assert calls == 2


def test_reopened_committed_prefix_advances_clock_without_reading_public_reason(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        e0_script_steps=(
            MockScriptStep.success(
                {
                    "stance": "label-2",
                    "confidence": 3,
                    "public_reason": "untrusted 2040-01-01T00:15:00Z timestamp",
                }
            ),
        ),
    )
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    assert pipeline.execute(**invocation_kwargs(item)).lifecycle.state == "committed"
    reopened = _reopen_fixture(
        replace(
            fixture,
            pipeline=pipeline,
            pipeline_kwargs={**fixture.pipeline_kwargs, "clock": initial_clock},
        )
    )

    rebuilt = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=reopened.store,
        manifest=reopened.pipeline_kwargs["manifest"],
        reconciliation=None,
    )

    assert rebuilt() == "2040-01-01T00:00:02Z"


def test_clock_ledger_rejects_scale_case_drift_from_matrix_manifest(tmp_path: Path) -> None:
    fixture, manifest = bound_matrix_cell_fixture(tmp_path)
    drifted = replace(scale_case(), mock_clock_step_seconds=2)

    with pytest.raises(ValueError, match="clock.*binding|binding.*clock"):
        rebuild_mock_clock_ledger(
            scale_case=drifted,
            storage=fixture.storage,
            manifest=manifest,
            reconciliation=None,
        )


def test_failed_attempt_and_authorized_retry_consume_three_then_two_clock_values(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        e0_script_steps=(
            MockScriptStep.timeout("mock timeout"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "retry success"}
            ),
        ),
    )
    ledger = MockClockLedger(scale_case=scale_case(), replay_values=(), next_sequence_index=0)
    pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": ledger})
    first = invocation(fixture)

    with pytest.raises(RuntimeError, match="successful commit"):
        execute_mock_run(
            pipeline=pipeline,
            storage=fixture.store,
            invocations=(first,),
            control=control(tmp_path),
        )
    assert ledger.calls == [
        "2040-01-01T00:00:00Z",
        "2040-01-01T00:00:01Z",
        "2040-01-01T00:00:02Z",
    ]

    with fixture.store.acquire_run_lease():
        _authorize_pipeline_retry(fixture.store, suffix="mock-run")
    report = execute_mock_run(
        pipeline=pipeline,
        storage=fixture.store,
        invocations=(replace(first, model_seed=12346),),
        control=control(tmp_path),
    )
    assert report.completed is True
    assert ledger.calls[-2:] == [
        "2040-01-01T00:00:03Z",
        "2040-01-01T00:00:04Z",
    ]


def test_reopened_in_progress_replays_started_clock_only_for_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    initial_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    captured_request = None
    original_record = fixture.store.record_prepared_attempt
    original_append = fixture.store.append_attempt

    def capture(*args, **kwargs):
        nonlocal captured_request
        captured_request = kwargs["request_evidence"].request
        return original_record(*args, **kwargs)

    def append_then_crash(attempt):
        original_append(attempt)
        raise RuntimeError("after_in_progress")

    with monkeypatch.context() as scoped:
        scoped.setattr(fixture.store, "record_prepared_attempt", capture)
        scoped.setattr(fixture.store, "append_attempt", append_then_crash)
        with pytest.raises(RuntimeError, match="after_in_progress"):
            initial_pipeline.execute(**invocation_kwargs(item))
    assert initial_clock.calls == ["2040-01-01T00:00:00Z"]
    assert captured_request is not None
    response = item.adapter.generate(captured_request)
    reconciliation = AttemptInvocationResult(
        response=response,
        evidence=AttemptExecutionEvidence(
            started_at="2040-01-01T00:00:00Z",
            finished_at="2040-01-01T00:00:01Z",
            http_status=item.http_status,
            provider_metadata=MockEventPipeline._provider_metadata(response),
            usage=item.usage,
            finish_reason=item.finish_reason,
        ),
    )
    reopened = _reopen_fixture(
        replace(
            fixture,
            pipeline=initial_pipeline,
            pipeline_kwargs={**fixture.pipeline_kwargs, "clock": initial_clock},
        )
    )
    rebuilt_clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=reopened.store,
        manifest=reopened.pipeline_kwargs["manifest"],
        reconciliation=reconciliation,
    )
    recovered_pipeline = MockEventPipeline(**{**reopened.pipeline_kwargs, "clock": rebuilt_clock})
    monkeypatch.setattr(
        item.adapter,
        "generate",
        lambda request: (_ for _ in ()).throw(AssertionError(f"resent {request.request_id}")),
    )

    report = execute_mock_run(
        pipeline=recovered_pipeline,
        storage=reopened.store,
        invocations=(replace(item, reconciliation=reconciliation),),
        control=control(tmp_path),
    )

    assert report.completed is True
    assert rebuilt_clock.calls == ["2040-01-01T00:00:00Z"]
    assert rebuilt_clock() == "2040-01-01T00:00:02Z"


def test_reopened_pending_reuses_unlanded_start_then_consumes_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    initial_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.store,
            "append_attempt",
            lambda attempt: (_ for _ in ()).throw(RuntimeError("after_pending")),
        )
        with pytest.raises(RuntimeError, match="after_pending"):
            initial_pipeline.execute(**invocation_kwargs(item))
    assert initial_clock.calls == ["2040-01-01T00:00:00Z"]
    reopened = _reopen_fixture(
        replace(
            fixture,
            pipeline=initial_pipeline,
            pipeline_kwargs={**fixture.pipeline_kwargs, "clock": initial_clock},
        )
    )
    rebuilt_clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=reopened.store,
        manifest=reopened.pipeline_kwargs["manifest"],
        reconciliation=None,
    )
    recovered_pipeline = MockEventPipeline(**{**reopened.pipeline_kwargs, "clock": rebuilt_clock})

    report = execute_mock_run(
        pipeline=recovered_pipeline,
        storage=reopened.store,
        invocations=(item,),
        control=control(tmp_path),
    )

    assert report.completed is True
    assert rebuilt_clock.calls == [
        "2040-01-01T00:00:00Z",
        "2040-01-01T00:00:01Z",
    ]


def test_reopened_persisted_invocation_replays_started_without_adapter_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    initial_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.store,
            "record_finalized_attempt",
            lambda evidence: (_ for _ in ()).throw(RuntimeError("after_invocation")),
        )
        with pytest.raises(RuntimeError, match="after_invocation"):
            initial_pipeline.execute(**invocation_kwargs(item))
    assert initial_clock.calls == [
        "2040-01-01T00:00:00Z",
        "2040-01-01T00:00:01Z",
    ]
    reopened = _reopen_fixture(
        replace(
            fixture,
            pipeline=initial_pipeline,
            pipeline_kwargs={**fixture.pipeline_kwargs, "clock": initial_clock},
        )
    )
    rebuilt_clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=reopened.store,
        manifest=reopened.pipeline_kwargs["manifest"],
        reconciliation=None,
    )
    recovered_pipeline = MockEventPipeline(**{**reopened.pipeline_kwargs, "clock": rebuilt_clock})
    monkeypatch.setattr(
        item.adapter,
        "generate",
        lambda request: (_ for _ in ()).throw(AssertionError(f"resent {request.request_id}")),
    )

    report = execute_mock_run(
        pipeline=recovered_pipeline,
        storage=reopened.store,
        invocations=(item,),
        control=control(tmp_path),
    )

    assert report.completed is True
    assert rebuilt_clock.calls == ["2040-01-01T00:00:00Z"]


def test_reopened_pending_failure_reuses_start_and_records_third_clock_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        e0_script_steps=(MockScriptStep.timeout("pending recovery timeout"),),
    )
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    initial_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.store,
            "append_attempt",
            lambda attempt: (_ for _ in ()).throw(RuntimeError("after_pending")),
        )
        with pytest.raises(RuntimeError, match="after_pending"):
            initial_pipeline.execute(**invocation_kwargs(item))
    reopened = _reopen_fixture(
        replace(
            fixture,
            pipeline=initial_pipeline,
            pipeline_kwargs={**fixture.pipeline_kwargs, "clock": initial_clock},
        )
    )
    clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=reopened.store,
        manifest=reopened.pipeline_kwargs["manifest"],
        reconciliation=None,
    )
    outcome = MockEventPipeline(**{**reopened.pipeline_kwargs, "clock": clock}).execute(
        **invocation_kwargs(item)
    )

    assert outcome.lifecycle.state == "failed"
    assert clock.calls == [
        "2040-01-01T00:00:00Z",
        "2040-01-01T00:00:01Z",
        "2040-01-01T00:00:02Z",
    ]
    failure = reopened.store.terminal_failure_evidence()
    assert failure is not None and failure.recorded_at == clock.calls[2]
    expected_payload, expected_hash = failure.to_payload(), failure.payload_hash
    reopened_again = _reopen_fixture(reopened)
    replayed = reopened_again.store.terminal_failure_evidence()
    assert replayed is not None
    assert (replayed.to_payload(), replayed.payload_hash) == (expected_payload, expected_hash)


def test_reopened_reconciliation_failure_replays_start_and_records_next_clock_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        e0_script_steps=(MockScriptStep.malformed("not-json"),),
    )
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    initial_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    captured_request = None
    original_record = fixture.store.record_prepared_attempt
    original_append = fixture.store.append_attempt

    def capture(*args, **kwargs):
        nonlocal captured_request
        captured_request = kwargs["request_evidence"].request
        return original_record(*args, **kwargs)

    def append_then_crash(attempt):
        original_append(attempt)
        raise RuntimeError("after_in_progress")

    with monkeypatch.context() as scoped:
        scoped.setattr(fixture.store, "record_prepared_attempt", capture)
        scoped.setattr(fixture.store, "append_attempt", append_then_crash)
        with pytest.raises(RuntimeError, match="after_in_progress"):
            initial_pipeline.execute(**invocation_kwargs(item))
    assert captured_request is not None
    response = item.adapter.generate(captured_request)
    reconciliation = AttemptInvocationResult(
        response=response,
        evidence=AttemptExecutionEvidence(
            started_at="2040-01-01T00:00:00Z",
            finished_at="2040-01-01T00:00:01Z",
            http_status=item.http_status,
            provider_metadata=MockEventPipeline._provider_metadata(response),
            usage=item.usage,
            finish_reason=item.finish_reason,
        ),
    )
    reopened = _reopen_fixture(fixture)
    clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=reopened.store,
        manifest=reopened.pipeline_kwargs["manifest"],
        reconciliation=reconciliation,
    )
    monkeypatch.setattr(
        item.adapter,
        "generate",
        lambda request: (_ for _ in ()).throw(AssertionError(f"resent {request.request_id}")),
    )
    outcome = MockEventPipeline(**{**reopened.pipeline_kwargs, "clock": clock}).execute(
        **invocation_kwargs(replace(item, reconciliation=reconciliation))
    )

    assert outcome.lifecycle.state == "failed"
    assert clock.calls == ["2040-01-01T00:00:00Z", "2040-01-01T00:00:02Z"]
    failure = reopened.store.terminal_failure_evidence()
    assert failure is not None and failure.recorded_at == clock.calls[1]
    expected_payload, expected_hash = failure.to_payload(), failure.payload_hash
    reopened_again = _reopen_fixture(reopened)
    replayed = reopened_again.store.terminal_failure_evidence()
    assert replayed is not None
    assert (replayed.to_payload(), replayed.payload_hash) == (expected_payload, expected_hash)


def test_reopened_persisted_invocation_failure_rehydrates_finish_and_records_next_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        e0_script_steps=(MockScriptStep.malformed("not-json"),),
    )
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    initial_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.store,
            "record_finalized_attempt",
            lambda evidence: (_ for _ in ()).throw(RuntimeError("after_invocation")),
        )
        with pytest.raises(RuntimeError, match="after_invocation"):
            initial_pipeline.execute(**invocation_kwargs(item))
    reopened = _reopen_fixture(fixture)
    journal = reopened.store.current_event_journal()
    assert journal.event_ordinal == 0 and journal.latest_transition is not None
    persisted = reopened.store.invocation_evidence(journal.latest_transition.attempt_id)
    assert persisted is not None
    assert persisted.execution_payload["finished_at"] == "2040-01-01T00:00:01Z"
    clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=reopened.store,
        manifest=reopened.pipeline_kwargs["manifest"],
        reconciliation=None,
    )
    monkeypatch.setattr(
        item.adapter,
        "generate",
        lambda request: (_ for _ in ()).throw(AssertionError(f"resent {request.request_id}")),
    )
    outcome = MockEventPipeline(**{**reopened.pipeline_kwargs, "clock": clock}).execute(
        **invocation_kwargs(item)
    )

    assert outcome.lifecycle.state == "failed"
    assert clock.calls == ["2040-01-01T00:00:00Z", "2040-01-01T00:00:02Z"]
    failure = reopened.store.terminal_failure_evidence()
    assert failure is not None and failure.recorded_at == clock.calls[1]
    expected_payload, expected_hash = failure.to_payload(), failure.payload_hash
    reopened_again = _reopen_fixture(reopened)
    replayed = reopened_again.store.terminal_failure_evidence()
    assert replayed is not None
    assert (replayed.to_payload(), replayed.payload_hash) == (expected_payload, expected_hash)


def test_landed_success_and_already_complete_consume_no_clock_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    initial_clock = MockClockLedger(
        scale_case=scale_case(), replay_values=(), next_sequence_index=0
    )
    initial_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": initial_clock})
    item = invocation(fixture)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.store,
            "commit_success",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("after-finalize")),
        )
        with pytest.raises(RuntimeError, match="after-finalize"):
            initial_pipeline.execute(**invocation_kwargs(item))
    recovery_clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=fixture.store,
        manifest=fixture.pipeline_kwargs["manifest"],
        reconciliation=None,
    )
    recovery_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": recovery_clock})
    report = execute_mock_run(
        pipeline=recovery_pipeline,
        storage=fixture.store,
        invocations=(item,),
        control=control(tmp_path),
    )
    assert report.completed is True
    assert recovery_clock.calls == []

    complete_clock = rebuild_mock_clock_ledger(
        scale_case=scale_case(),
        storage=fixture.store,
        manifest=fixture.pipeline_kwargs["manifest"],
        reconciliation=None,
    )
    complete_pipeline = MockEventPipeline(**{**fixture.pipeline_kwargs, "clock": complete_clock})
    complete = execute_mock_run(
        pipeline=complete_pipeline,
        storage=fixture.store,
        invocations=(),
        control=MockRunControl(1, (), ()),
    )
    assert complete.completed is True
    assert complete_clock.calls == []


@pytest.mark.parametrize("attack", ("gap", "duplicate", "foreign"))
def test_invocation_ledger_must_exact_cover_current_prefix(tmp_path: Path, attack: str) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    item = invocation(fixture)
    invocations = {
        "gap": (),
        "duplicate": (item, item),
        "foreign": (replace(item, event_id="event-" + "f" * 64),),
    }[attack]

    with pytest.raises(ValueError, match="invocation|event identity|exact-cover"):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.store,
            invocations=invocations,
            control=control(tmp_path),
        )
    assert fixture.store.progress.next_event_ordinal == 0


@pytest.mark.parametrize("target", (-1, 2))
def test_target_must_be_within_current_storage_bounds(tmp_path: Path, target: int) -> None:
    fixture = _fixture(tmp_path, exposure="E0")

    with pytest.raises(ValueError, match="target"):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.store,
            invocations=(),
            control=MockRunControl(target, (), ()),
        )


@pytest.mark.parametrize(
    ("ordinals", "paths", "match"),
    (
        ((1,), (), "equal length"),
        ((1, 1), ("a", "b"), "strictly increasing"),
        ((1, 0), ("a", "b"), "strictly increasing"),
        ((0,), ("a",), "newly executed prefix"),
        ((2,), ("a",), "newly executed prefix"),
    ),
)
def test_checkpoint_plan_rejects_non_bijective_or_out_of_range_entries(
    tmp_path: Path,
    ordinals: tuple[int, ...],
    paths: tuple[str, ...],
    match: str,
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    checkpoint_paths = tuple(tmp_path / value for value in paths)

    with pytest.raises(ValueError, match=match):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.store,
            invocations=(invocation(fixture),),
            control=MockRunControl(1, ordinals, checkpoint_paths),
        )


def test_checkpoint_paths_are_unique_after_resolution(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    same = tmp_path / "nested" / ".." / "checkpoint.json"

    with pytest.raises(ValueError, match="paths.*unique|unique.*paths"):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.store,
            invocations=(invocation(fixture), invocation(fixture, 1)),
            control=MockRunControl(
                2,
                (1, 2),
                (same, tmp_path / "checkpoint.json"),
            ),
        )


def test_pipeline_and_storage_run_identity_must_match(tmp_path: Path) -> None:
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    first = _fixture(first_path, exposure="E0")
    second = _fixture(second_path, exposure="E2")

    with pytest.raises(ValueError, match="same run"):
        execute_mock_run(
            pipeline=first.pipeline,
            storage=second.store,
            invocations=(),
            control=MockRunControl(0, (), ()),
        )


def test_noncommitted_outcome_stops_without_consuming_next_invocation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E2")

    class StopPipeline:
        run_id = fixture.store.binding.run_id

        def __init__(self) -> None:
            self.calls = 0

        def execute(self, **kwargs):
            del kwargs
            self.calls += 1
            return SimpleNamespace(lifecycle=AttemptOutcome("failed", None, None, False))

    pipeline = StopPipeline()
    first = invocation(fixture)
    second = invocation(fixture, 1)

    with pytest.raises(RuntimeError, match="successful commit"):
        execute_mock_run(
            pipeline=pipeline,
            storage=fixture.store,
            invocations=(first, second),
            control=MockRunControl(2, (), ()),
        )
    assert pipeline.calls == 1
    assert fixture.store.progress.next_event_ordinal == 0


def test_pipeline_lifecycle_exception_propagates_without_retry(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E0")

    class RaisingPipeline:
        run_id = fixture.store.binding.run_id

        def __init__(self) -> None:
            self.calls = 0

        def execute(self, **kwargs):
            del kwargs
            self.calls += 1
            raise RuntimeError("typed lifecycle failure")

    pipeline = RaisingPipeline()
    with pytest.raises(RuntimeError, match="typed lifecycle failure"):
        execute_mock_run(
            pipeline=pipeline,
            storage=fixture.store,
            invocations=(invocation(fixture),),
            control=control(tmp_path),
        )
    assert pipeline.calls == 1


def test_mock_run_public_api_is_exactly_exported() -> None:
    assert agent_ex.MockEventInvocation is MockEventInvocation
    assert agent_ex.MockRunControl is MockRunControl
    assert agent_ex.MockRunReport is MockRunReport
    assert agent_ex.execute_mock_run is execute_mock_run
