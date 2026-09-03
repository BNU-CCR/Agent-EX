from __future__ import annotations

from dataclasses import MISSING, fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import pytest

from agent_ex.adapters import MockAdapter, MockScriptStep
from agent_ex.checkpoint import build_checkpoint
from agent_ex.domain import canonical_payload_hash, derive_event_id, derive_run_id
from agent_ex.mock_run import MockEventInvocation, MockRunControl, execute_mock_run
from agent_ex.parser import ParserLimits
from agent_ex.pipeline import MockEventPipeline
from agent_ex.prompt import PromptLimits
from agent_ex.process_audit import (
    ANALYSIS_LABEL,
    APPROVED_OUTCOME_LABELS,
    APPROVED_TERMINOLOGY_MAP,
    APPROVED_TERMINOLOGY_MAP_ID,
    ExposureProcessSummary,
    MockComparableRunProjection,
    MockProcessAudit,
    RoundZeroBaseline,
    SweepProcessAudit,
    build_mock_comparable_run_projection,
    build_mock_process_audit,
)
from agent_ex.storage import RunStorage
from agent_ex.domain import FrozenSchedule, ScheduleSlot
from test_pipeline import (
    NOW,
    _authorize_pipeline_retry,
    _fixture,
    _initial_records,
    _limits,
    _mapped_neighbors,
)
from test_prompt import persona_template
from test_storage import manifest


MODEL_PROVENANCE = {
    "provider": "deterministic-mock",
    "model": "deterministic-mock-model",
    "revision": "phase4b7-script-v1",
    "runtime": "1.0.0",
    "mode": "script_only_no_generation",
}
PROMPT_PROVENANCE = {
    "template_id": "paper1.mock_prompt_template",
    "template_version": "1.0.0",
    "prompt_limits_hash": _limits()[1].record_hash,
}
ROBUSTNESS_PROVENANCE = {"mock_only": True, "research_parameter_status": "not_frozen"}


def _audit_kwargs(fixture) -> dict[str, object]:
    return {
        "storage": fixture.store,
        "cell_id": fixture.pipeline_kwargs["manifest"].run_spec["cell_id"],
        "topic_package": fixture.pipeline_kwargs["topic_package"],
        "boundary_event_ordinal": fixture.store.progress.next_event_ordinal,
        "outcome_labels": APPROVED_OUTCOME_LABELS,
        "terminology_map_id": APPROVED_TERMINOLOGY_MAP_ID,
        "terminology_map": APPROVED_TERMINOLOGY_MAP,
        "model_provenance": MODEL_PROVENANCE,
        "prompt_provenance": PROMPT_PROVENANCE,
        "robustness_provenance": ROBUSTNESS_PROVENANCE,
    }


def _invocations(
    fixture,
    *,
    raw_reason_prefix: str,
    model_seed_offset: int = 0,
    prompt_limits_overrides: Mapping[int, PromptLimits] | None = None,
    parser_limits_overrides: Mapping[int, ParserLimits] | None = None,
    adapter: MockAdapter | None = None,
) -> tuple[MockEventInvocation, ...]:
    event_ids = tuple(
        derive_event_id(fixture.store.binding.run_id, ordinal)
        for ordinal in range(fixture.store.progress.expected_event_count)
    )
    if adapter is None:
        adapter = MockAdapter(
            script={
                event_id: (
                    MockScriptStep.success(
                        {
                            "stance": f"label-{2 + (ordinal % 3)}",
                            "confidence": 3,
                            "public_reason": f"{raw_reason_prefix}-{ordinal}",
                        }
                    ),
                )
                for ordinal, event_id in enumerate(event_ids)
            },
            mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
            mock_only=True,
        )
    values = fixture.execute_kwargs
    return tuple(
        MockEventInvocation(
            event_ordinal=ordinal,
            event_id=event_id,
            feed_capacity=4,
            memory_window=values["memory_window"],
            parser_limits=(parser_limits_overrides or {}).get(ordinal, values["parser_limits"]),
            prompt_limits=(prompt_limits_overrides or {}).get(ordinal, values["prompt_limits"]),
            policy=values["policy"],
            model_identity=adapter.execution_binding().model_identity,
            request_parameters=values["request_parameters"],
            model_seed=model_seed_offset + 10_000 + ordinal,
            adapter=adapter,
            reconciliation=None,
            http_status=values["http_status"],
            usage=values["usage"],
            finish_reason=values["finish_reason"],
        )
        for ordinal, event_id in enumerate(event_ids)
    )


def _complete(
    fixture,
    tmp_path: Path,
    *,
    reason: str = "same",
    seed_offset: int = 0,
    prompt_limits_overrides: Mapping[int, PromptLimits] | None = None,
    parser_limits_overrides: Mapping[int, ParserLimits] | None = None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    count = fixture.store.progress.expected_event_count
    execute_mock_run(
        pipeline=fixture.pipeline,
        storage=fixture.store,
        invocations=_invocations(
            fixture,
            raw_reason_prefix=reason,
            model_seed_offset=seed_offset,
            prompt_limits_overrides=prompt_limits_overrides,
            parser_limits_overrides=parser_limits_overrides,
        ),
        control=MockRunControl(
            target_event_ordinal=count,
            checkpoint_ordinals=(count,),
            checkpoint_paths=(tmp_path / f"checkpoint-{reason}-{seed_offset}.json",),
        ),
    )
    return build_mock_process_audit(**_audit_kwargs(fixture))


def _two_sweep_e2_fixture(
    tmp_path: Path,
    *,
    launch_nonce: str = "launch-a",
    publish_event_four: bool = False,
    alternate_final_receiver: bool = False,
):
    """Create a real 4-agent/two-sweep E2 store from existing typed artifacts."""

    (tmp_path / "artifact-source").mkdir(parents=True, exist_ok=True)
    seed = _fixture(tmp_path / "artifact-source", exposure="E2")
    seed.store.close()
    assert seed.graph is not None and seed.mapping is not None
    receiver = _mapped_neighbors(seed.graph, seed.mapping)["agent-0000"][0]
    final_receiver = (
        next(
            agent_id
            for agent_id in (f"agent-{index:04d}" for index in range(4))
            if agent_id not in {"agent-0000", receiver}
        )
        if alternate_final_receiver
        else receiver
    )
    slots = tuple(ScheduleSlot(ordinal, 1, ordinal, "agent-0000", True) for ordinal in range(3)) + (
        ScheduleSlot(3, 1, 3, receiver, False),
        ScheduleSlot(4, 2, 0, "agent-0000", publish_event_four),
        ScheduleSlot(5, 2, 1, "agent-0000", False),
        ScheduleSlot(6, 2, 2, "agent-0000", False),
        ScheduleSlot(7, 2, 3, final_receiver, False),
    )
    schedule = FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id="mock.weighted-with-replacement",
        algorithm_version="1.0.0",
        population_size=4,
        sweep_count=2,
        slots=slots,
    )
    run_manifest = manifest(schedule, cell_id="P1-I0-C0-E2")
    run_manifest = replace(
        run_manifest,
        run_id=derive_run_id(run_manifest.run_spec, run_manifest.matched_seed, launch_nonce),
        launch_nonce=launch_nonce,
        model_identity=seed.pipeline_kwargs["manifest"].model_identity,
    )
    population = seed.pipeline_kwargs["population_artifact"]
    graph = seed.graph
    mapping = seed.mapping
    round0 = seed.round0
    assert graph is not None and mapping is not None
    topic_package = seed.pipeline_kwargs["topic_package"]
    artifacts = {
        population.artifact_id: population.output_hash,
        graph.artifact_id: graph.output_hash,
        mapping.artifact_id: mapping.output_hash,
        round0.artifact_id: round0.output_hash,
        topic_package.topic_id: topic_package.package_hash,
    }
    store = RunStorage.create(
        tmp_path / "two-sweep-e2.sqlite",
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=tuple(f"agent-{index:04d}" for index in range(4)),
        expected_exposure_mode="ws_neighbors",
        expected_exposure_graph_hash=graph.output_hash,
        expected_exposure_graph_artifact=graph,
        expected_source_ws_artifact=None,
    )
    round0_by_agent = {record["agent_id"]: record for record in round0.payload["round0_records"]}
    with store.acquire_run_lease():
        for agent_id in store.binding.expected_agent_ids:
            store.initialize_agent(
                *_initial_records(
                    round0_record=round0_by_agent[agent_id],
                    exposure_mode="ws_neighbors",
                    exposure_graph_hash=graph.output_hash,
                )
            )
        store.seal_initial_state()
    parser_limits, prompt_limits = _limits()
    adapter = MockAdapter(
        script={
            derive_event_id(run_manifest.run_id, ordinal): (
                MockScriptStep.success(
                    {
                        "stance": f"label-{2 + ordinal % 3}",
                        "confidence": 3,
                        "public_reason": f"two-sweep-{ordinal}",
                    }
                ),
            )
            for ordinal in range(8)
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    pipeline_kwargs = {
        "storage": store,
        "manifest": run_manifest,
        "topic_package": topic_package,
        "persona_template": persona_template(),
        "population_artifact": population,
        "exposure_graph_artifact": graph,
        "source_ws_artifact": None,
        "agent_node_mapping_artifact": mapping,
        "round0_initialization_artifact": round0,
        "frozen_neighbor_agent_ids": _mapped_neighbors(graph, mapping),
        "clock": lambda: NOW,
    }
    return SimpleNamespace(
        database_path=tmp_path / "two-sweep-e2.sqlite",
        store=store,
        pipeline=MockEventPipeline(**pipeline_kwargs),
        adapter=adapter,
        pipeline_kwargs=pipeline_kwargs,
        execute_kwargs={
            "feed_capacity": 4,
            "memory_window": 3,
            "parser_limits": parser_limits,
            "prompt_limits": prompt_limits,
            "policy": seed.execute_kwargs["policy"],
            "model_identity": adapter.execution_binding().model_identity,
            "request_parameters": {"temperature": 0.0},
            "model_seed": 10_000,
            "adapter": adapter,
            "reconciliation": None,
            "http_status": 200,
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            "finish_reason": "stop",
        },
    )


def test_process_audit_public_contract_has_only_explicit_required_inputs() -> None:
    assert tuple(inspect.signature(build_mock_process_audit).parameters) == (
        "storage",
        "cell_id",
        "topic_package",
        "boundary_event_ordinal",
        "outcome_labels",
        "terminology_map_id",
        "terminology_map",
        "model_provenance",
        "prompt_provenance",
        "robustness_provenance",
    )
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in inspect.signature(build_mock_process_audit).parameters.values()
    )
    assert all(
        field.default is MISSING and field.default_factory is MISSING
        for field in fields(MockProcessAudit)
        if field.name != "audit_hash"
    )


def test_comparable_projection_has_fixed_schema_and_no_ignore_fields_escape_hatch() -> None:
    assert tuple(inspect.signature(build_mock_comparable_run_projection).parameters) == (
        "storage",
        "audit",
    )
    assert tuple(field.name for field in fields(MockComparableRunProjection)) == (
        "schema_version",
        "matched_seed",
        "cell_id",
        "schedule_hash",
        "committed_event_semantics",
        "final_private_states",
        "final_public_stock",
        "final_feed_cursors",
        "process_audit_semantics",
        "projection_hash",
    )
    assert "ignore_fields" not in inspect.signature(build_mock_comparable_run_projection).parameters


def test_immutable_audit_types_expose_only_hash_bound_process_fields() -> None:
    assert tuple(field.name for field in fields(ExposureProcessSummary)) == (
        "analysis_label",
        "per_event_message_counts",
        "event_backed_message_ages",
        "round0_message_count",
        "unique_source_agent_ids",
        "repeated_source_message_count",
        "empty_feed_count",
        "expired_message_count",
        "sender_activity_counts",
    )
    assert tuple(field.name for field in fields(RoundZeroBaseline))[-1] == "baseline_hash"
    assert tuple(field.name for field in fields(SweepProcessAudit))[-1] == "sweep_hash"
    assert tuple(field.name for field in fields(MockProcessAudit))[-1] == "audit_hash"


def test_complete_social_sweep_builds_private_public_and_process_audit(tmp_path: Path) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    audit = _complete(fixture, tmp_path, reason="social")

    assert audit.round_zero.agent_count == len(fixture.store.binding.expected_agent_ids)
    assert tuple(item.sweep_index for item in audit.sweeps) == (1, 2)
    sweep = audit.sweeps[-1]
    assert sweep.boundary_event_ordinal == 8
    assert sweep.process.selected_message_count == sum(sweep.process.per_event_message_counts)
    assert audit.sweeps[0].process.repeated_source_message_count > 0
    assert audit.sweeps[0].process.expired_message_count > 0
    assert audit.sweeps[1].process.empty_feed_count == 4
    assert sweep.process.analysis_label == ANALYSIS_LABEL
    assert sweep.label_count_delta_analysis_label == ANALYSIS_LABEL
    assert set(sweep.private_label_count_delta) == set(
        fixture.pipeline_kwargs["topic_package"].stance_labels
    )
    assert all(type(value) is int for value in sweep.private_label_count_delta.values())
    assert audit.outcome_labels == APPROVED_OUTCOME_LABELS
    assert audit.terminology_map == APPROVED_TERMINOLOGY_MAP
    assert audit.terminology_map_hash == canonical_payload_hash(APPROVED_TERMINOLOGY_MAP)
    assert (
        audit.provenance["topic"]["package_hash"]
        == fixture.pipeline_kwargs["topic_package"].package_hash
    )
    payload = audit.to_payload()
    assert not any(
        forbidden in str(payload).lower() for forbidden in ("effect", "ranking", "significance")
    )


def test_unpublished_private_reason_never_enters_public_stock_or_flow(tmp_path: Path) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    audit = _complete(fixture, tmp_path, reason="PRIVATE_SECRET")
    unpublished_update = next(
        update
        for update in fixture.store.private_updates_for_agent("agent-0000")
        if update.event_ordinal == 4
    )
    assert unpublished_update.published is False
    assert "PRIVATE_SECRET-4" == unpublished_update.reason

    public_payload = {
        "stock": tuple(sweep.public_stock_snapshot for sweep in audit.sweeps),
        "flow": tuple(sweep.public_flow_snapshot for sweep in audit.sweeps),
    }
    assert "PRIVATE_SECRET-4" not in str(public_payload)


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"boundary_event_ordinal": 9}, "boundary|committed"),
        ({"boundary_event_ordinal": 7}, "sweep|multiple"),
        (
            {"outcome_labels": {**APPROVED_OUTCOME_LABELS, "private_state": "secondary"}},
            "outcome",
        ),
        (
            {"terminology_map_id": "paper1.phase4a1.terminology.v2"},
            "terminology",
        ),
        (
            {"terminology_map": {"identity": "身份"}},
            "terminology",
        ),
    ),
)
def test_audit_rejects_invalid_boundary_labels_and_terminology(
    tmp_path: Path, change: Mapping[str, object], message: str
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason="valid")
    kwargs = {**_audit_kwargs(fixture), **change}

    with pytest.raises((TypeError, ValueError), match=message):
        build_mock_process_audit(**kwargs)


def test_audit_binds_cell_and_topic_to_committed_event_and_storage_evidence(
    tmp_path: Path,
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason="binding")
    kwargs = _audit_kwargs(fixture)
    with pytest.raises(ValueError, match="cell"):
        build_mock_process_audit(**{**kwargs, "cell_id": "P1-I1-C1-E2"})

    topic_package = fixture.pipeline_kwargs["topic_package"]
    changed_topic = replace(topic_package, topic_id="mock-topic-drift")
    with pytest.raises(ValueError, match="topic|artifact"):
        build_mock_process_audit(**{**kwargs, "topic_package": changed_topic})


@pytest.mark.parametrize(
    ("change", "message"),
    (
        (
            {"model_provenance": {**MODEL_PROVENANCE, "revision": "wrong-revision"}},
            "model|revision|committed",
        ),
        (
            {
                "model_provenance": {
                    **MODEL_PROVENANCE,
                    "provider": "wrong-provider",
                }
            },
            "model|provider|committed",
        ),
        (
            {
                "prompt_provenance": {
                    **PROMPT_PROVENANCE,
                    "template_id": "paper1.wrong-template",
                }
            },
            "prompt|template|committed",
        ),
        (
            {
                "prompt_provenance": {
                    **PROMPT_PROVENANCE,
                    "prompt_limits_hash": "0" * 64,
                }
            },
            "prompt|limits|committed",
        ),
    ),
)
def test_audit_binds_model_and_prompt_provenance_to_committed_evidence(
    tmp_path: Path, change: Mapping[str, object], message: str
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason="provenance-binding")

    with pytest.raises(ValueError, match=message):
        build_mock_process_audit(**{**_audit_kwargs(fixture), **change})


def test_audit_accepts_running_committed_sweep_prefix(tmp_path: Path) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    invocations = _invocations(fixture, raw_reason_prefix="running")[:4]
    execute_mock_run(
        pipeline=fixture.pipeline,
        storage=fixture.store,
        invocations=invocations,
        control=MockRunControl(
            target_event_ordinal=4,
            checkpoint_ordinals=(4,),
            checkpoint_paths=(tmp_path / "running-prefix.json",),
        ),
    )
    audit = build_mock_process_audit(**_audit_kwargs(fixture))
    assert fixture.store.execution_state().status.value == "running"
    assert audit.boundary_event_ordinal == 4
    assert tuple(item.sweep_index for item in audit.sweeps) == (1,)


def test_audit_rejects_current_nonterminal_attempt(tmp_path: Path, monkeypatch) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    original = fixture.store.record_prepared_attempt

    def stop_after_pending(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("stop-after-pending")

    monkeypatch.setattr(fixture.store, "record_prepared_attempt", stop_after_pending)
    with pytest.raises(RuntimeError, match="stop-after-pending"):
        fixture.pipeline.execute(**fixture.execute_kwargs)

    with pytest.raises(ValueError, match="nonterminal|RUNNING|boundary"):
        build_mock_process_audit(**_audit_kwargs(fixture))


def test_projection_rejects_audit_stale_at_same_committed_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    invocations = _invocations(fixture, raw_reason_prefix="stale")
    execute_mock_run(
        pipeline=fixture.pipeline,
        storage=fixture.store,
        invocations=invocations[:4],
        control=MockRunControl(
            target_event_ordinal=4,
            checkpoint_ordinals=(),
            checkpoint_paths=(),
        ),
    )
    audit = build_mock_process_audit(**_audit_kwargs(fixture))
    original = fixture.store.record_prepared_attempt

    def stop_after_pending(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("stop-after-pending")

    monkeypatch.setattr(fixture.store, "record_prepared_attempt", stop_after_pending)
    with pytest.raises(RuntimeError, match="stop-after-pending"):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.store,
            invocations=invocations[4:5],
            control=MockRunControl(
                target_event_ordinal=5,
                checkpoint_ordinals=(),
                checkpoint_paths=(),
            ),
        )

    assert fixture.store.progress.next_event_ordinal == audit.boundary_event_ordinal
    with pytest.raises(ValueError, match="checkpoint|audit"):
        build_mock_comparable_run_projection(fixture.store, audit)


def test_process_audit_rejects_noncanonical_checkpoint_hash(tmp_path: Path) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    audit = _complete(fixture, tmp_path, reason="hash")

    with pytest.raises(ValueError, match="SHA-256"):
        replace(audit, checkpoint_hash="g" * 64)


def test_projection_rejects_in_memory_audit_hash_tamper(tmp_path: Path) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    audit = _complete(fixture, tmp_path, reason="tamper-audit")
    object.__setattr__(audit, "cell_id", "P1-I1-C1-E2")

    with pytest.raises(ValueError, match="audit hash|integrity"):
        build_mock_comparable_run_projection(fixture.store, audit)


def test_projection_rejects_hash_consistent_reconstructed_audit(tmp_path: Path) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    audit = _complete(fixture, tmp_path, reason="reconstructed-audit")
    changed_delta = dict(audit.sweeps[-1].private_label_count_delta)
    changed_delta[next(iter(changed_delta))] += 999
    changed_sweep = replace(audit.sweeps[-1], private_label_count_delta=changed_delta)
    changed_cell = "P1-I1-C1-E2"
    forged_values = (
        replace(
            audit,
            cell_id=changed_cell,
            provenance={**dict(audit.provenance), "cell_id": changed_cell},
        ),
        replace(audit, sweeps=audit.sweeps[:-1] + (changed_sweep,)),
    )

    for forged in forged_values:
        assert forged.audit_hash != audit.audit_hash
        with pytest.raises(ValueError, match="builder|trusted|audit"):
            build_mock_comparable_run_projection(fixture.store, forged)


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"model_provenance": {}}, "model_provenance|required"),
        ({"prompt_provenance": {}}, "prompt_provenance|required"),
        ({"robustness_provenance": {}}, "robustness_provenance|required"),
        (
            {"model_provenance": {**MODEL_PROVENANCE, "unknown_semantic": "value"}},
            "unknown|field",
        ),
        (
            {"prompt_provenance": {**PROMPT_PROVENANCE, "unknown_semantic": "value"}},
            "unknown|field",
        ),
        (
            {
                "robustness_provenance": {
                    **ROBUSTNESS_PROVENANCE,
                    "unknown_semantic": "value",
                }
            },
            "unknown|field",
        ),
    ),
)
def test_audit_provenance_schema_is_explicit_and_fail_closed(
    tmp_path: Path, change: Mapping[str, object], message: str
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason="provenance-schema")

    with pytest.raises((TypeError, ValueError), match=message):
        build_mock_process_audit(**{**_audit_kwargs(fixture), **change})


def test_audit_rejects_failed_execution_state(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        e0_script_steps=(MockScriptStep.timeout("audit timeout"),),
    )
    values = fixture.execute_kwargs
    item = MockEventInvocation(
        event_ordinal=0,
        event_id=derive_event_id(fixture.store.binding.run_id, 0),
        feed_capacity=values["feed_capacity"],
        memory_window=values["memory_window"],
        parser_limits=values["parser_limits"],
        prompt_limits=values["prompt_limits"],
        policy=values["policy"],
        model_identity=fixture.adapter.execution_binding().model_identity,
        request_parameters=values["request_parameters"],
        model_seed=values["model_seed"],
        adapter=fixture.adapter,
        reconciliation=None,
        http_status=values["http_status"],
        usage=values["usage"],
        finish_reason=values["finish_reason"],
    )
    with pytest.raises(RuntimeError):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.store,
            invocations=(item,),
            control=MockRunControl(
                target_event_ordinal=1,
                checkpoint_ordinals=(1,),
                checkpoint_paths=(tmp_path / "failed.json",),
            ),
        )
    with pytest.raises(ValueError, match="FAILED|failed"):
        build_mock_process_audit(**_audit_kwargs(fixture))


def test_audit_rejects_missing_or_tampered_event_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason="evidence")
    original = fixture.store.event_input_evidence

    monkeypatch.setattr(
        fixture.store,
        "event_input_evidence",
        lambda event_id: (
            None
            if event_id == derive_event_id(fixture.store.binding.run_id, 1)
            else original(event_id)
        ),
    )
    with pytest.raises(ValueError, match="evidence|missing"):
        build_mock_process_audit(**_audit_kwargs(fixture))


@pytest.mark.parametrize("field", ("message_ages", "source_agent_ids"))
def test_audit_rejects_invalid_age_or_sender_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason=f"invalid-{field}")
    original = fixture.store.event_input_evidence
    evidence = next(
        value
        for ordinal in range(fixture.store.progress.next_event_ordinal)
        if (value := original(derive_event_id(fixture.store.binding.run_id, ordinal))) is not None
        and any(item is not None for item in value.exposure_record.source_event_ids)
    )
    exposure = replace(evidence.exposure_record)
    if field == "message_ages":
        object.__setattr__(
            exposure,
            field,
            (0,) + exposure.message_ages[1:],
        )
    else:
        object.__setattr__(
            exposure,
            field,
            ("agent-outside-roster",) + exposure.source_agent_ids[1:],
        )
    changed = replace(evidence)
    object.__setattr__(changed, "exposure_record", exposure)
    monkeypatch.setattr(
        fixture.store,
        "event_input_evidence",
        lambda event_id: changed if event_id == evidence.event_id else original(event_id),
    )

    with pytest.raises(ValueError):
        build_mock_process_audit(**_audit_kwargs(fixture))


def test_audit_rejects_reordered_event_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason="reordered")
    original = fixture.store.event_input_evidence
    first_id = derive_event_id(fixture.store.binding.run_id, 1)
    second_id = derive_event_id(fixture.store.binding.run_id, 2)
    first = original(first_id)
    second = original(second_id)
    assert first is not None and second is not None
    monkeypatch.setattr(
        fixture.store,
        "event_input_evidence",
        lambda event_id: (
            second
            if event_id == first_id
            else first
            if event_id == second_id
            else original(event_id)
        ),
    )

    with pytest.raises(ValueError, match="reordered|evidence|identity"):
        build_mock_process_audit(**_audit_kwargs(fixture))


def test_audit_rejects_sqlite_tamper_before_emitting_snapshot(tmp_path: Path) -> None:
    import sqlite3

    fixture = _two_sweep_e2_fixture(tmp_path)
    _complete(fixture, tmp_path, reason="tamper")
    fixture.store.close()
    connection = sqlite3.connect(fixture.database_path)
    connection.execute("UPDATE events SET payload_hash = ? WHERE event_ordinal = 1", ("0" * 64,))
    connection.commit()
    connection.close()
    with pytest.raises(ValueError):
        RunStorage.open(
            fixture.database_path,
            manifest=fixture.pipeline_kwargs["manifest"],
            artifact_hashes=dict(fixture.store.binding.artifact_hashes),
            expected_agent_ids=fixture.store.binding.expected_agent_ids,
            expected_exposure_mode=fixture.store.binding.expected_exposure_mode,
            expected_exposure_graph_hash=(fixture.store.binding.expected_exposure_graph_hash),
            expected_exposure_graph_artifact=fixture.pipeline_kwargs["exposure_graph_artifact"],
            expected_source_ws_artifact=None,
        )


def test_comparable_projection_ignores_path_and_wall_clock_but_not_response_or_seed(
    tmp_path: Path,
) -> None:
    for name in ("left", "right", "response", "seed"):
        (tmp_path / name).mkdir()
    left_fixture = _two_sweep_e2_fixture(tmp_path / "left", launch_nonce="left-launch")
    right_fixture = _two_sweep_e2_fixture(tmp_path / "right", launch_nonce="right-launch")
    left_fixture.pipeline = type(left_fixture.pipeline)(
        **{**left_fixture.pipeline_kwargs, "clock": lambda: "2040-01-01T00:00:00Z"}
    )
    right_fixture.pipeline = type(right_fixture.pipeline)(
        **{**right_fixture.pipeline_kwargs, "clock": lambda: "2050-01-01T00:00:00Z"}
    )
    left_audit = _complete(left_fixture, tmp_path / "left", reason="same")
    right_audit = _complete(right_fixture, tmp_path / "right", reason="same")
    left_audit = build_mock_process_audit(
        **{
            **_audit_kwargs(left_fixture),
            "model_provenance": {**MODEL_PROVENANCE, "local_path": "C:/left"},
            "prompt_provenance": {
                **PROMPT_PROVENANCE,
                "started_at": "2040-01-01T00:00:00Z",
            },
            "robustness_provenance": {
                **ROBUSTNESS_PROVENANCE,
                "launch_nonce": "left-nonce",
            },
        }
    )
    right_audit = build_mock_process_audit(
        **{
            **_audit_kwargs(right_fixture),
            "model_provenance": {**MODEL_PROVENANCE, "local_path": "D:/right"},
            "prompt_provenance": {
                **PROMPT_PROVENANCE,
                "started_at": "2050-01-01T00:00:00Z",
            },
            "robustness_provenance": {
                **ROBUSTNESS_PROVENANCE,
                "launch_nonce": "right-nonce",
            },
        }
    )

    assert (
        build_checkpoint(left_fixture.store).checkpoint_hash
        != build_checkpoint(right_fixture.store).checkpoint_hash
    )
    left = build_mock_comparable_run_projection(left_fixture.store, left_audit)
    right = build_mock_comparable_run_projection(right_fixture.store, right_audit)
    assert left.projection_hash == right.projection_hash
    assert "run_id" not in str(left.to_payload())
    assert "launch_nonce" not in str(left.to_payload())
    assert "timestamp" not in str(left.to_payload())

    changed_response_fixture = _two_sweep_e2_fixture(tmp_path / "response")
    changed_response = _complete(changed_response_fixture, tmp_path / "response", reason="changed")
    assert (
        build_mock_comparable_run_projection(
            changed_response_fixture.store, changed_response
        ).projection_hash
        != left.projection_hash
    )

    changed_seed_fixture = _two_sweep_e2_fixture(tmp_path / "seed")
    changed_seed = _complete(changed_seed_fixture, tmp_path / "seed", reason="same", seed_offset=1)
    assert (
        build_mock_comparable_run_projection(
            changed_seed_fixture.store, changed_seed
        ).projection_hash
        != left.projection_hash
    )


def test_comparable_projection_retains_publish_cursor_and_parse_semantics_end_to_end(
    tmp_path: Path,
) -> None:
    for name in (
        "baseline",
        "publish",
        "cursor",
        "parsed",
        "prompt-limits",
        "parser-limits",
    ):
        (tmp_path / name).mkdir()
    baseline_fixture = _two_sweep_e2_fixture(tmp_path / "baseline")
    publish_fixture = _two_sweep_e2_fixture(tmp_path / "publish", publish_event_four=True)
    cursor_fixture = _two_sweep_e2_fixture(tmp_path / "cursor", alternate_final_receiver=True)
    parsed_fixture = _two_sweep_e2_fixture(tmp_path / "parsed")
    prompt_limits_fixture = _two_sweep_e2_fixture(tmp_path / "prompt-limits")
    parser_limits_fixture = _two_sweep_e2_fixture(tmp_path / "parser-limits")
    base_parser_limits, base_prompt_limits = _limits()
    changed_prompt_limits = PromptLimits.create(
        max_persona_chars=base_prompt_limits.max_persona_chars,
        max_string_chars=base_prompt_limits.max_string_chars,
        max_memory_items=base_prompt_limits.max_memory_items,
        max_social_messages=base_prompt_limits.max_social_messages,
        max_data_chars=base_prompt_limits.max_data_chars,
        max_total_chars=base_prompt_limits.max_total_chars + 1,
        mock_only=True,
    )
    changed_parser_limits = ParserLimits.create(
        max_raw_chars=base_parser_limits.max_raw_chars + 1,
        max_raw_bytes=base_parser_limits.max_raw_bytes,
        max_json_depth=base_parser_limits.max_json_depth,
        max_reason_chars=base_parser_limits.max_reason_chars,
        mock_only=True,
    )
    fixture_values = (
        (baseline_fixture, "same", {}),
        (publish_fixture, "same", {}),
        (cursor_fixture, "same", {}),
        (parsed_fixture, "changed-parse", {}),
        (
            prompt_limits_fixture,
            "same",
            {"prompt_limits_overrides": {4: changed_prompt_limits}},
        ),
        (
            parser_limits_fixture,
            "same",
            {"parser_limits_overrides": {4: changed_parser_limits}},
        ),
    )
    projections = []
    for index, (fixture, reason, overrides) in enumerate(fixture_values):
        audit = _complete(
            fixture,
            tmp_path / f"projection-{index}",
            reason=reason,
            **overrides,
        )
        projections.append(build_mock_comparable_run_projection(fixture.store, audit))
    baseline, publish, cursor, parsed, prompt_limits, parser_limits = projections

    assert (
        baseline.committed_event_semantics[4]["publish_flag"]
        != publish.committed_event_semantics[4]["publish_flag"]
    )
    assert baseline.final_feed_cursors != cursor.final_feed_cursors
    assert (
        baseline.committed_event_semantics[0]["attempts"][0]["parse_semantic_hash"]
        != parsed.committed_event_semantics[0]["attempts"][0]["parse_semantic_hash"]
    )
    baseline_attempt = baseline.committed_event_semantics[4]["attempts"][0]
    assert (
        baseline_attempt["prompt_limits_hash"]
        != prompt_limits.committed_event_semantics[4]["attempts"][0]["prompt_limits_hash"]
    )
    assert (
        baseline_attempt["parser_limits_hash"]
        != parser_limits.committed_event_semantics[4]["attempts"][0]["parser_limits_hash"]
    )
    assert all(
        changed.projection_hash != baseline.projection_hash
        for changed in (publish, cursor, parsed, prompt_limits, parser_limits)
    )


def test_projection_encodes_timeout_then_authorized_successful_retry(tmp_path: Path) -> None:
    fixture = _two_sweep_e2_fixture(tmp_path)
    event_ids = tuple(
        derive_event_id(fixture.store.binding.run_id, ordinal) for ordinal in range(8)
    )
    retry_adapter = MockAdapter(
        script={
            event_id: (
                (
                    MockScriptStep.timeout("projection timeout"),
                    MockScriptStep.success(
                        {
                            "stance": "label-2",
                            "confidence": 3,
                            "public_reason": "retry success",
                        }
                    ),
                )
                if ordinal == 0
                else (
                    MockScriptStep.success(
                        {
                            "stance": f"label-{2 + ordinal % 3}",
                            "confidence": 3,
                            "public_reason": f"after-retry-{ordinal}",
                        }
                    ),
                )
            )
            for ordinal, event_id in enumerate(event_ids)
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    invocations = _invocations(
        fixture,
        raw_reason_prefix="unused",
        adapter=retry_adapter,
    )
    first_control = MockRunControl(
        target_event_ordinal=1,
        checkpoint_ordinals=(),
        checkpoint_paths=(),
    )
    with pytest.raises(RuntimeError, match="successful commit"):
        execute_mock_run(
            pipeline=fixture.pipeline,
            storage=fixture.store,
            invocations=invocations[:1],
            control=first_control,
        )
    with fixture.store.acquire_run_lease():
        _authorize_pipeline_retry(fixture.store, suffix="process-audit-projection")
    execute_mock_run(
        pipeline=fixture.pipeline,
        storage=fixture.store,
        invocations=(replace(invocations[0], model_seed=invocations[0].model_seed + 1),),
        control=first_control,
    )
    report = execute_mock_run(
        pipeline=fixture.pipeline,
        storage=fixture.store,
        invocations=invocations[1:],
        control=MockRunControl(
            target_event_ordinal=8,
            checkpoint_ordinals=(),
            checkpoint_paths=(),
        ),
    )
    assert report.completed is True

    audit = build_mock_process_audit(**_audit_kwargs(fixture))
    projection = build_mock_comparable_run_projection(fixture.store, audit)
    attempts = projection.committed_event_semantics[0]["attempts"]
    assert tuple(value["parse_kind"] for value in attempts) == (
        "not_applicable",
        "parsed",
    )
    assert attempts[0]["parser_id"] is None
    assert attempts[0]["parser_version"] is None
    assert attempts[0]["outcome"] == "timeout"
    assert attempts[0]["parse_semantic_hash"] != attempts[1]["parse_semantic_hash"]
