from __future__ import annotations

import copy
import inspect
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import pytest
import agent_ex
import agent_ex.pipeline as pipeline_module

from agent_ex.adapters.mock import MockAdapter, MockScriptStep
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import (
    FrozenSchedule,
    RunManifest,
    ScheduleSlot,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
    derive_run_id,
)
from agent_ex.execution_evidence import (
    FinalizedAttemptEvidence,
    MockAttemptPolicyBinding,
    ParseNotApplicableEvidence,
)
from agent_ex.engine import AttemptExecutionEvidence, AttemptInvocationResult
from agent_ex.feed import FeedCursor
from agent_ex.initialization import assign_initial_reasons, assign_initial_stances
from agent_ex.network import build_agent_node_mapping, build_shadow_artifact, build_ws_artifact
from agent_ex.parser import ParseEvidence, ParserLimits
from agent_ex.pipeline import MockEventPipeline, MockEventPipelineOutcome
from agent_ex.population import build_population_artifact
from agent_ex.prompt import PromptLimits
from agent_ex.state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from agent_ex.storage import RunStorage, changed_request_parameter_paths
from test_prompt import member, persona_template, topic
from test_storage import manifest


NOW = "2026-09-01T00:00:00+00:00"


@dataclass(frozen=True, slots=True)
class PipelineFixture:
    database_path: Path
    store: RunStorage
    pipeline: MockEventPipeline
    adapter: MockAdapter
    execute_kwargs: Mapping[str, object]
    pipeline_kwargs: Mapping[str, object]
    graph: ArtifactEnvelope | None
    mapping: ArtifactEnvelope | None
    round0: ArtifactEnvelope


def _population(size: int):
    return build_population_artifact(
        donors=({"donor_id": "donor-1", "fields": member()["fields"]},),
        weights=(float(size),),
        n=size,
        matched_seed=17,
        input_artifact_hash="9" * 64,
        constraints={"marginals": {}, "joints": []},
        tolerance=0,
        mock_only=True,
    )


def _limits() -> tuple[ParserLimits, PromptLimits]:
    return (
        ParserLimits.create(
            max_raw_chars=10_000,
            max_raw_bytes=20_000,
            max_json_depth=16,
            max_reason_chars=2_000,
            mock_only=True,
        ),
        PromptLimits.create(
            max_persona_chars=10_000,
            max_string_chars=20_000,
            max_memory_items=10,
            max_social_messages=10,
            max_data_chars=80_000,
            max_total_chars=100_000,
            mock_only=True,
        ),
    )


def _round0_artifacts(
    population: ArtifactEnvelope,
) -> tuple[ArtifactEnvelope, ArtifactEnvelope, ArtifactEnvelope]:
    stances = assign_initial_stances(
        population_artifact=population,
        matched_seed=17,
        orthogonal_fields=("gender", "urban", "education"),
        max_category_imbalance=float(len(population.payload["members"])),
        mock_only=True,
    )
    entries = tuple(
        {
            "reason_id": f"pipeline-reason-{stance}-{variant}",
            "stance": stance,
            "text": f"Pipeline round-zero reason {stance}-{variant}.",
            "argument_family": f"pipeline-family-{variant}",
        }
        for stance in range(1, 8)
        for variant in range(len(population.payload["members"]))
    )
    reason_library = ArtifactEnvelope.create(
        artifact_type="paper1.mock_reason_library",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"population": population.output_hash},
        payload={
            "schema_version": "paper1.mock-reason-library.v1",
            "entries": entries,
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        },
        rng_provenance=(),
    )
    round0 = assign_initial_reasons(
        stance_artifact=stances,
        reason_library_artifact=reason_library,
        matched_seed=17,
        mock_only=True,
    )
    return round0, stances, reason_library


def _mapped_neighbors(
    graph: ArtifactEnvelope, mapping: ArtifactEnvelope
) -> dict[str, tuple[str, ...]]:
    agent_by_node = {
        assignment["node_id"]: assignment["agent_id"]
        for assignment in mapping.payload["assignments"]
    }
    values = {agent_id: set() for agent_id in agent_by_node.values()}
    for left, right in graph.payload["edges"]:
        left_agent = agent_by_node[left]
        right_agent = agent_by_node[right]
        values[left_agent].add(right_agent)
        values[right_agent].add(left_agent)
    return {
        agent_id: tuple(sorted(agent_neighbors)) for agent_id, agent_neighbors in values.items()
    }


def _initial_records(
    *,
    round0_record: Mapping[str, object],
    exposure_mode: str,
    exposure_graph_hash: str | None,
) -> tuple[PrivateUpdate, PrivateState, PublicPost, LatestPublicPointer, FeedCursor]:
    agent_id = round0_record["agent_id"]
    private_state = round0_record["private_state"]
    public_record = round0_record["public_post"]
    if not isinstance(agent_id, str):
        raise TypeError("round-zero agent_id must be text")
    if not isinstance(private_state, Mapping) or not isinstance(public_record, Mapping):
        raise TypeError("round-zero private/public records must be mappings")
    stance = private_state.get("stance")
    if (
        not isinstance(stance, int)
        or isinstance(stance, bool)
        or not 1 <= stance <= len(topic().stance_labels)
        or public_record.get("stance") != stance
    ):
        raise ValueError("round-zero stance must map to one topic label")
    private_reason = private_state.get("reason")
    if (
        not isinstance(private_reason, str)
        or public_record.get("public_reason") != private_reason
        or public_record.get("published") is not True
    ):
        raise ValueError("round-zero private/public reason evidence must agree")
    initial = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id=agent_id,
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label=topic().stance_labels[stance - 1],
        reason=private_reason,
        confidence=None,
        published=public_record["published"],
        source_attempt_id=None,
        mock_only=True,
    )
    state = PrivateState.from_update(initial, previous=None, mock_only=True)
    post = PublicPost.from_private_update(initial, mock_only=True)
    pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
    cursor = FeedCursor.initial(
        matched_seed=17,
        receiver_agent_id=agent_id,
        exposure_mode=exposure_mode,
        exposure_graph_hash=exposure_graph_hash,
        mock_only=True,
    )
    return initial, state, post, pointer, cursor


def _authorize_pipeline_retry(store: RunStorage, *, suffix: str) -> None:
    failure = store.terminal_failure_evidence()
    assert failure is not None
    store.authorize_resume(
        authorization_id=f"resume-{suffix}",
        event_id=failure.event_id,
        previous_terminal_failure_hash=failure.payload_hash,
        policy_evidence_id=f"retry-{suffix}",
        policy_evidence_hash="b" * 64,
        authorized_at=NOW,
    )


def _fixture(
    tmp_path: Path,
    *,
    exposure: str,
    bind_manifest_model_identity: bool = True,
    baseline_request_parameters: Mapping[str, object] | None = None,
    allowed_difference_fields: tuple[str, ...] | None = None,
    e0_script_steps: tuple[MockScriptStep, ...] | None = None,
) -> PipelineFixture:
    if exposure == "E0":
        size = 1
        cell_id = "P1-I0-C0-E0"
        exposure_mode = "self_history_only"
        graph = None
        source_ws = None
        neighbors = {"agent-0000": ()}
        slots = (ScheduleSlot(0, 1, 0, "agent-0000", False),)
        script_payloads = (
            {
                "stance": "label-2",
                "confidence": 3,
                "public_reason": "receiver-private-only-update",
            },
        )
    elif exposure == "E2":
        size = 4
        cell_id = "P1-I0-C0-E2"
        exposure_mode = "ws_neighbors"
        graph = build_ws_artifact(n=4, k=2, p=0.05, matched_seed=17, mock_only=True)
        source_ws = None
        node_neighbors: dict[int, set[int]] = {index: set() for index in range(size)}
        for left, right in graph.payload["edges"]:
            node_neighbors[left].add(right)
            node_neighbors[right].add(left)
        neighbors = {
            f"agent-{node:04d}": tuple(
                f"agent-{neighbor:04d}" for neighbor in sorted(node_neighbors[node])
            )
            for node in range(size)
        }
        slots = (
            ScheduleSlot(0, 1, 0, "agent-0001", False),
            ScheduleSlot(1, 1, 1, "agent-0000", True),
            ScheduleSlot(2, 1, 2, "agent-0002", False),
            ScheduleSlot(3, 1, 3, "agent-0003", False),
        )
        script_payloads = (
            {
                "stance": "label-5",
                "confidence": 5,
                "public_reason": "NEIGHBOR_PRIVATE_SECRET",
            },
            {
                "stance": "label-4",
                "confidence": 4,
                "public_reason": "receiver-published-update",
            },
        )
    elif exposure == "E1":
        size = 40
        cell_id = "P1-I0-C0-E1"
        exposure_mode = "shuffled_social"
        source_ws = build_ws_artifact(n=size, k=4, p=0.05, matched_seed=17, mock_only=True)
        graph = build_shadow_artifact(
            source_ws,
            matched_seed=17,
            max_attempts=3,
            trial_budget_per_edge=300,
            mock_only=True,
        )
        neighbors = {f"agent-{index:04d}": () for index in range(size)}
        slots = tuple(
            ScheduleSlot(index, 1, index, f"agent-{index:04d}", False) for index in range(size)
        )
        script_payloads = (
            {
                "stance": "label-2",
                "confidence": 3,
                "public_reason": "unused-e1-construction-response",
            },
        )
    else:
        raise ValueError("unsupported test exposure")

    schedule = FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id="mock.weighted-with-replacement",
        algorithm_version="1.0.0",
        population_size=size,
        sweep_count=1,
        slots=slots,
    )
    run_manifest = manifest(schedule, cell_id=cell_id)
    if baseline_request_parameters is not None:
        run_spec = {
            **dict(run_manifest.run_spec),
            "request_parameters": dict(baseline_request_parameters),
        }
        run_manifest = replace(
            run_manifest,
            run_id=derive_run_id(run_spec, run_manifest.matched_seed, run_manifest.launch_nonce),
            run_spec=run_spec,
            run_spec_hash=canonical_payload_hash(run_spec),
        )
    population = _population(size)
    artifacts = {population.artifact_id: population.output_hash}
    round0, stances, reason_library = _round0_artifacts(population)
    artifacts[round0.artifact_id] = round0.output_hash
    artifacts[stances.artifact_id] = stances.output_hash
    artifacts[reason_library.artifact_id] = reason_library.output_hash
    mapping = None
    if graph is not None:
        artifacts[graph.artifact_id] = graph.output_hash
        if source_ws is not None:
            artifacts[source_ws.artifact_id] = source_ws.output_hash
        mapping = build_agent_node_mapping(
            population_artifact=population,
            round0_initialization_artifact=round0,
            network_artifact=graph if source_ws is None else source_ws,
            matched_seed=17,
            mock_only=True,
        )
        artifacts[mapping.artifact_id] = mapping.output_hash
        neighbors = _mapped_neighbors(graph, mapping)
    script = {
        derive_event_id(run_manifest.run_id, index): (MockScriptStep.success(payload),)
        for index, payload in enumerate(script_payloads)
    }
    if exposure == "E0" and e0_script_steps is not None:
        script = {derive_event_id(run_manifest.run_id, 0): e0_script_steps}
    adapter = MockAdapter(
        script=script,
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    if bind_manifest_model_identity:
        binding = adapter.execution_binding()
        run_manifest = replace(
            run_manifest,
            model_identity={
                "provider": binding.runtime_identity["provider"],
                "model": binding.model_identity["model"],
                "revision": binding.model_identity["revision"],
                "runtime": binding.runtime_identity["runtime_version"],
                "mode": binding.model_identity["mode"],
            },
        )
    store = RunStorage.create(
        tmp_path / f"pipeline-{exposure}.sqlite",
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=tuple(f"agent-{index:04d}" for index in range(size)),
        expected_exposure_mode=exposure_mode,
        expected_exposure_graph_hash=None if graph is None else graph.output_hash,
        expected_exposure_graph_artifact=graph,
        expected_source_ws_artifact=source_ws,
    )
    round0_by_agent = {record["agent_id"]: record for record in round0.payload["round0_records"]}
    with store.acquire_run_lease():
        for agent_id in store.binding.expected_agent_ids:
            store.initialize_agent(
                *_initial_records(
                    round0_record=round0_by_agent[agent_id],
                    exposure_mode=exposure_mode,
                    exposure_graph_hash=None if graph is None else graph.output_hash,
                )
            )
        store.seal_initial_state()
    parser_limits, prompt_limits = _limits()
    policy = MockAttemptPolicyBinding.create(
        allowed_difference_fields=(
            ("model_seed", "request_parameters.temperature")
            if allowed_difference_fields is None
            else allowed_difference_fields
        ),
        mock_only=True,
        formal_eligible=False,
    )
    pipeline_kwargs = {
        "storage": store,
        "manifest": run_manifest,
        "topic_package": topic(),
        "persona_template": persona_template(),
        "population_artifact": population,
        "exposure_graph_artifact": graph,
        "source_ws_artifact": source_ws,
        "agent_node_mapping_artifact": mapping,
        "round0_initialization_artifact": round0 if graph is not None else None,
        "frozen_neighbor_agent_ids": neighbors,
        "clock": lambda: NOW,
    }
    pipeline = MockEventPipeline(**pipeline_kwargs)
    return PipelineFixture(
        database_path=tmp_path / f"pipeline-{exposure}.sqlite",
        store=store,
        pipeline=pipeline,
        adapter=adapter,
        pipeline_kwargs=pipeline_kwargs,
        graph=graph,
        mapping=mapping,
        round0=round0,
        execute_kwargs={
            "feed_capacity": 4,
            "memory_window": 3,
            "parser_limits": parser_limits,
            "prompt_limits": prompt_limits,
            "policy": policy,
            "model_identity": adapter.execution_binding().model_identity,
            "request_parameters": (
                {"temperature": 0.0}
                if baseline_request_parameters is None
                else dict(baseline_request_parameters)
            ),
            "model_seed": 12345,
            "adapter": adapter,
            "http_status": 200,
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            "finish_reason": "stop",
            "reconciliation": None,
        },
    )


def _reopen_fixture(fixture: PipelineFixture) -> PipelineFixture:
    binding = fixture.store.binding
    fixture.store.close()
    reopened = RunStorage.open(
        fixture.database_path,
        manifest=fixture.pipeline_kwargs["manifest"],
        artifact_hashes=dict(binding.artifact_hashes),
        expected_agent_ids=binding.expected_agent_ids,
        expected_exposure_mode=binding.expected_exposure_mode,
        expected_exposure_graph_hash=binding.expected_exposure_graph_hash,
        expected_exposure_graph_artifact=fixture.graph,
        expected_source_ws_artifact=fixture.pipeline_kwargs["source_ws_artifact"],
    )
    pipeline_kwargs = {**fixture.pipeline_kwargs, "storage": reopened}
    return replace(
        fixture,
        store=reopened,
        pipeline=MockEventPipeline(**pipeline_kwargs),
        pipeline_kwargs=pipeline_kwargs,
    )


def test_pipeline_rejects_same_run_id_with_manifest_payload_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    manifest_value = fixture.pipeline_kwargs["manifest"]
    assert isinstance(manifest_value, RunManifest)
    drifted = replace(manifest_value, updated_at="2026-09-01T00:00:01+00:00")

    with pytest.raises(ValueError, match="manifest|binding"):
        MockEventPipeline(**{**fixture.pipeline_kwargs, "manifest": drifted})


def test_pipeline_rejects_hash_cached_schedule_slot_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    manifest_value = fixture.pipeline_kwargs["manifest"]
    assert isinstance(manifest_value, RunManifest)
    schedule = FrozenSchedule.from_payload(manifest_value.schedule.to_payload())
    object.__setattr__(
        schedule,
        "slots",
        (ScheduleSlot(0, 1, 0, "agent-foreign", True),),
    )
    drifted = replace(manifest_value, schedule=schedule)

    with pytest.raises(ValueError, match="schedule|manifest|binding"):
        MockEventPipeline(**{**fixture.pipeline_kwargs, "manifest": drifted})


def test_execute_rejects_adapter_identity_drift_from_persisted_manifest(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E0", bind_manifest_model_identity=False)
    before = fixture.store.progress

    with pytest.raises(ValueError, match="model identity|manifest"):
        fixture.pipeline.execute(**fixture.execute_kwargs)

    assert fixture.store.progress == before
    assert (
        fixture.store.event_input_evidence(derive_event_id(fixture.store.binding.run_id, 0)) is None
    )


@pytest.mark.parametrize(
    "baseline_request_parameters",
    (
        {"sampling.temperature": 0.0},
        {"sampling": {"temperature.value": 0.0}},
        {"sampling": {"": 0.0}},
        {"sampling": {"   ": 0.0}},
    ),
)
def test_pipeline_rejects_invalid_manifest_request_parameter_paths_at_construction(
    tmp_path: Path, baseline_request_parameters: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="key|segment|path|request parameter"):
        _fixture(
            tmp_path,
            exposure="E0",
            baseline_request_parameters=baseline_request_parameters,
        )


def test_pipeline_rejects_non_text_manifest_request_parameter_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="key|segment|text|JSON-like"):
        _fixture(
            tmp_path,
            exposure="E0",
            baseline_request_parameters={"sampling": {1: 0.0}},  # type: ignore[dict-item]
        )


def test_pipeline_accepts_canonically_equivalent_list_parameters_on_first_attempt(
    tmp_path: Path,
) -> None:
    parameters = {
        "groups": [{"temperature": 0.0, "stop": ["END", "STOP"]}],
    }
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        baseline_request_parameters=parameters,
    )

    outcome = fixture.pipeline.execute(
        **{**fixture.execute_kwargs, "request_parameters": parameters}
    )

    assert outcome.lifecycle.state == "committed"
    assert fixture.store.progress.next_event_ordinal == 1


def test_pipeline_rejects_ambiguous_mapping_key_inside_array_before_first_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        baseline_request_parameters={"groups": [{"temperature": 0.0}]},
    )
    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    before = (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
    )
    adapter_calls = 0

    def fail_if_called(request):
        nonlocal adapter_calls
        adapter_calls += 1
        raise AssertionError(f"adapter called for invalid request: {request.request_id}")

    monkeypatch.setattr(fixture.adapter, "generate", fail_if_called)

    with pytest.raises(ValueError, match="key|segment|single path"):
        fixture.pipeline.execute(
            **{
                **fixture.execute_kwargs,
                "request_parameters": {"groups": [{"sampling.temperature": 0.0}]},
            }
        )

    assert adapter_calls == 0
    assert fixture.store.event_input_evidence(event_id) is None
    assert fixture.store.attempts_for_event(event_id) == ()
    assert (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
    ) == before


@pytest.mark.parametrize(
    "request_parameters",
    ({"temperature": 0.5}, {"temperature": 0.0, "top_p": 0.9}),
)
def test_first_attempt_rejects_request_parameter_drift_without_writing_evidence(
    tmp_path: Path, request_parameters: dict[str, object]
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    before = (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
    )

    with pytest.raises(ValueError, match="request parameters|manifest"):
        fixture.pipeline.execute(
            **{**fixture.execute_kwargs, "request_parameters": request_parameters}
        )

    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    assert fixture.store.event_input_evidence(event_id) is None
    assert fixture.store.attempts_for_event(event_id) == ()
    assert (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
    ) == before


@pytest.mark.parametrize(
    ("request_parameters", "error_type"),
    (
        ({"sampling.temperature": 0.0}, ValueError),
        ({"sampling": {"temperature.value": 0.0}}, ValueError),
        ({"sampling": {"   ": 0.0}}, ValueError),
        ({"sampling": {1: 0.0}}, TypeError),
    ),
)
def test_first_attempt_rejects_invalid_parameter_paths_before_adapter_or_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request_parameters: dict[object, object],
    error_type: type[Exception],
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    before = (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
    )
    adapter_calls = 0

    def fail_if_called(request):
        nonlocal adapter_calls
        adapter_calls += 1
        raise AssertionError(f"adapter called for invalid request: {request.request_id}")

    monkeypatch.setattr(fixture.adapter, "generate", fail_if_called)

    with pytest.raises(error_type, match="key|segment|text|request parameter"):
        fixture.pipeline.execute(
            **{
                **fixture.execute_kwargs,
                "request_parameters": request_parameters,
            }
        )

    assert adapter_calls == 0
    assert fixture.store.event_input_evidence(event_id) is None
    assert fixture.store.attempts_for_event(event_id) == ()
    assert (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
    ) == before


def test_retry_allows_only_the_policy_bound_nested_temperature_leaf(tmp_path: Path) -> None:
    baseline = {"sampling": {"temperature": 0.0, "top_p": 1.0}}
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        baseline_request_parameters=baseline,
        allowed_difference_fields=(
            "model_seed",
            "request_parameters.sampling.temperature",
        ),
        e0_script_steps=(
            MockScriptStep.timeout("retry nested temperature"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "nested retry"}
            ),
        ),
    )
    failed = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "http_status": None,
            "usage": {},
            "finish_reason": None,
        }
    )
    assert failed.lifecycle.state == "failed"
    assert failed.lifecycle.event_id is not None
    first_input = fixture.store.event_input_evidence(failed.lifecycle.event_id)
    assert first_input is not None
    first_progress = fixture.store.progress
    with fixture.store.acquire_run_lease():
        _authorize_pipeline_retry(fixture.store, suffix="pipeline-nested-allowed")
    retry_parameters = {"sampling": {"temperature": 0.5, "top_p": 1.0}}
    assert pipeline_module.changed_request_parameter_paths is changed_request_parameter_paths
    assert changed_request_parameter_paths(baseline, retry_parameters) == {
        "request_parameters.sampling.temperature"
    }

    outcome = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "request_parameters": retry_parameters,
        }
    )

    assert outcome.lifecycle.state == "committed"
    assert outcome.lifecycle.event_id == failed.lifecycle.event_id
    assert outcome.evidence.event_input_evidence_hash == first_input.record_hash
    assert fixture.store.attempts_for_event(failed.lifecycle.event_id)[0].attempt_id == (
        failed.lifecycle.attempt.attempt_id
    )
    assert fixture.store.progress.next_event_ordinal == first_progress.next_event_ordinal + 1
    assert fixture.store.progress.next_event_ordinal == 1


def test_retry_allows_explicit_policy_bound_model_seed_change(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        allowed_difference_fields=("model_seed",),
        e0_script_steps=(
            MockScriptStep.timeout("retry with authorized seed"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "seed retry"}
            ),
        ),
    )
    failed = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "http_status": None,
            "usage": {},
            "finish_reason": None,
        }
    )
    assert failed.lifecycle.event_id is not None
    first_request = fixture.store.adapter_request_evidence(failed.lifecycle.attempt.attempt_id)
    first_input = fixture.store.event_input_evidence(failed.lifecycle.event_id)
    assert first_request is not None and first_input is not None
    with fixture.store.acquire_run_lease():
        _authorize_pipeline_retry(fixture.store, suffix="pipeline-seed-allowed")

    outcome = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "model_seed": 54321,
        }
    )
    attempts = fixture.store.attempts_for_event(failed.lifecycle.event_id)
    retry_request = fixture.store.adapter_request_evidence(attempts[-1].attempt_id)

    assert outcome.lifecycle.state == "committed"
    assert outcome.lifecycle.event_id == failed.lifecycle.event_id
    assert outcome.evidence.event_input_evidence_hash == first_input.record_hash
    assert tuple(attempt.attempt_index for attempt in attempts) == (1, 2)
    assert first_request.model_seed == 12345
    assert retry_request is not None and retry_request.model_seed == 54321


def test_retry_rejects_unlisted_model_seed_before_adapter_or_evidence_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        allowed_difference_fields=("request_parameters.temperature",),
        e0_script_steps=(
            MockScriptStep.timeout("reject unauthorized seed"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "must not run"}
            ),
        ),
    )
    failed = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "http_status": None,
            "usage": {},
            "finish_reason": None,
        }
    )
    assert failed.lifecycle.event_id is not None
    with fixture.store.acquire_run_lease():
        _authorize_pipeline_retry(fixture.store, suffix="pipeline-seed-rejected")
    event_id = failed.lifecycle.event_id
    before = (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
        fixture.store.evidence_references(event_id),
        fixture.store.attempt_transitions(failed.lifecycle.attempt.attempt_id),
    )
    adapter_calls = 0

    def counted_generate(request):
        nonlocal adapter_calls
        adapter_calls += 1
        raise AssertionError(f"unauthorized seed reached adapter: {request.request_id}")

    monkeypatch.setattr(fixture.adapter, "generate", counted_generate)
    with pytest.raises(ValueError, match="model seed|attempt policy|unauthorized"):
        fixture.pipeline.execute(
            **{
                **fixture.execute_kwargs,
                "model_seed": 54321,
            }
        )

    assert adapter_calls == 0
    assert fixture.store.adapter_request_evidence(derive_attempt_id(event_id, 2)) is None
    assert (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
        fixture.store.evidence_references(event_id),
        fixture.store.attempt_transitions(failed.lifecycle.attempt.attempt_id),
    ) == before


@pytest.mark.parametrize(
    "retry_parameters",
    (
        {"sampling": {"temperature": 0.0, "top_p": 0.9}},
        {"sampling": 0.5},
    ),
)
def test_retry_rejects_unlisted_nested_or_parent_parameter_changes(
    tmp_path: Path, retry_parameters: dict[str, object]
) -> None:
    baseline = {"sampling": {"temperature": 0.0, "top_p": 1.0}}
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        baseline_request_parameters=baseline,
        allowed_difference_fields=(
            "model_seed",
            "request_parameters.sampling.temperature",
        ),
        e0_script_steps=(
            MockScriptStep.timeout("reject nested drift"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "must not run"}
            ),
        ),
    )
    failed = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "http_status": None,
            "usage": {},
            "finish_reason": None,
        }
    )
    assert failed.lifecycle.state == "failed"
    with fixture.store.acquire_run_lease():
        _authorize_pipeline_retry(fixture.store, suffix="pipeline-nested-rejected")

    with pytest.raises(ValueError, match="request parameters|attempt policy"):
        fixture.pipeline.execute(
            **{
                **fixture.execute_kwargs,
                "request_parameters": retry_parameters,
            }
        )

    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    assert len(fixture.store.attempts_for_event(event_id)) == 1


def test_retry_rejects_dotted_key_alias_before_attempt_or_adapter_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = {"sampling": {"temperature": 0.0, "top_p": 1.0}}
    fixture = _fixture(
        tmp_path,
        exposure="E0",
        baseline_request_parameters=baseline,
        allowed_difference_fields=(
            "model_seed",
            "request_parameters.sampling.temperature",
        ),
        e0_script_steps=(
            MockScriptStep.timeout("reject dotted alias"),
            MockScriptStep.success(
                {"stance": "label-2", "confidence": 3, "public_reason": "must not run"}
            ),
        ),
    )
    failed = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "http_status": None,
            "usage": {},
            "finish_reason": None,
        }
    )
    assert failed.lifecycle.state == "failed"
    with fixture.store.acquire_run_lease():
        _authorize_pipeline_retry(fixture.store, suffix="pipeline-dotted-alias")
    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    before = (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
        fixture.store.attempts_for_event(event_id),
    )
    adapter_calls = 0
    original_generate = fixture.adapter.generate

    def counted_generate(request):
        nonlocal adapter_calls
        adapter_calls += 1
        return original_generate(request)

    monkeypatch.setattr(fixture.adapter, "generate", counted_generate)

    with pytest.raises(ValueError, match="key|segment|path|request parameters"):
        fixture.pipeline.execute(
            **{
                **fixture.execute_kwargs,
                "request_parameters": {
                    "sampling": {"top_p": 1.0},
                    "sampling.temperature": 0.5,
                },
            }
        )

    assert adapter_calls == 0
    assert (
        fixture.store.progress,
        fixture.store.private_state("agent-0000"),
        fixture.store.latest_public_pointer("agent-0000"),
        fixture.store.feed_cursor("agent-0000"),
        fixture.store.attempts_for_event(event_id),
    ) == before


@pytest.mark.parametrize("drift", ("empty", "self", "out_of_roster", "asymmetric"))
def test_e2_rejects_neighbor_mapping_that_drifts_from_frozen_graph(
    tmp_path: Path, drift: str
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    assert (
        fixture.store.binding.artifact_hashes[fixture.round0.artifact_id]
        == fixture.round0.output_hash
    )
    wrong = dict(fixture.pipeline_kwargs["frozen_neighbor_agent_ids"])
    first = "agent-0000"
    neighbor = wrong[first][0]
    if drift == "empty":
        wrong[first] = ()
    elif drift == "self":
        wrong[first] = (first,)
    elif drift == "out_of_roster":
        wrong[first] = ("agent-foreign",)
    else:
        wrong[neighbor] = tuple(item for item in wrong[neighbor] if item != first)

    with pytest.raises(ValueError, match="neighbor|graph|mapping"):
        MockEventPipeline(**{**fixture.pipeline_kwargs, "frozen_neighbor_agent_ids": wrong})


def test_e2_rejects_hash_drifted_agent_node_mapping_artifact(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    mapping = fixture.mapping
    assert mapping is not None
    payload = copy.deepcopy(mapping.to_payload()["payload"])
    payload["assignments"][0]["node_id"], payload["assignments"][1]["node_id"] = (
        payload["assignments"][1]["node_id"],
        payload["assignments"][0]["node_id"],
    )
    drifted = ArtifactEnvelope.create(
        artifact_type=mapping.artifact_type,
        schema_version=mapping.schema_version,
        algorithm_id=mapping.algorithm_id,
        algorithm_version=mapping.algorithm_version,
        input_hashes=mapping.input_hashes,
        payload=payload,
        rng_provenance=mapping.rng_provenance,
    )

    with pytest.raises(ValueError, match="hash-bound|mapping"):
        MockEventPipeline(**{**fixture.pipeline_kwargs, "agent_node_mapping_artifact": drifted})


def test_e0_rejects_nonempty_neighbors_or_network_artifacts(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    wrong = {"agent-0000": ("agent-0000",)}

    with pytest.raises(ValueError, match="E0|self|neighbor|graph"):
        MockEventPipeline(**{**fixture.pipeline_kwargs, "frozen_neighbor_agent_ids": wrong})


def test_e0_mock_pipeline_records_explicit_empty_feed_and_commits(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exposure="E0")

    outcome = fixture.pipeline.execute(**fixture.execute_kwargs)

    assert isinstance(outcome, MockEventPipelineOutcome)
    assert outcome.lifecycle.state == "committed"
    assert outcome.evidence.committed_event_hash is not None
    event_input = fixture.store.event_input_evidence(outcome.lifecycle.event_id)
    assert event_input is not None
    assert event_input.exposure_selection.selected == ()
    assert event_input.prompt_view.social_messages == ()


def test_e2_mock_pipeline_persists_complete_chain_and_commits_publish_false_true(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    agent_one_pointer = fixture.store.latest_public_pointer("agent-0001")

    first = fixture.pipeline.execute(**fixture.execute_kwargs)
    assert first.lifecycle.state == "committed"
    assert fixture.store.latest_public_pointer("agent-0001") == agent_one_pointer
    assert fixture.store.private_state("agent-0001").reason == "NEIGHBOR_PRIVATE_SECRET"

    second = fixture.pipeline.execute(**fixture.execute_kwargs)

    assert second.lifecycle.state == "committed"
    assert all(
        (
            second.evidence.event_input_evidence_hash,
            second.evidence.request_hash,
            second.evidence.invocation_evidence_hash,
            second.evidence.parse_evidence_hash,
            second.evidence.terminal_attempt_hash,
            second.evidence.committed_event_hash,
        )
    )
    pointer = fixture.store.latest_public_pointer("agent-0000")
    assert pointer is not None
    assert pointer.published_event_ordinal == 1


def test_e1_accepts_shadow_neighbors_derived_through_frozen_ws_mapping(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E1")

    outcome = fixture.pipeline.execute(**fixture.execute_kwargs)

    assert fixture.store.binding.expected_exposure_mode == "shuffled_social"
    assert outcome.lifecycle.state == "committed"
    assert all(
        (
            outcome.evidence.event_input_evidence_hash,
            outcome.evidence.request_hash,
            outcome.evidence.invocation_evidence_hash,
            outcome.evidence.parse_evidence_hash,
            outcome.evidence.terminal_attempt_hash,
            outcome.evidence.committed_event_hash,
        )
    )
    event_input = fixture.store.event_input_evidence(outcome.lifecycle.event_id)
    assert event_input is not None
    assert event_input.exposure_selection.selected
    assert event_input.exposure_selection.exposure_graph_hash == fixture.graph.output_hash


def test_sqlite_round_zero_state_matches_the_bound_initialization_artifact(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")

    for record in fixture.round0.payload["round0_records"]:
        agent_id = record["agent_id"]
        stance = record["private_state"]["stance"]
        expected_label = topic().stance_labels[stance - 1]
        state = fixture.store.private_state(agent_id)
        posts = fixture.store.public_posts_for_agent(agent_id)

        assert state is not None
        assert state.stance_label == expected_label
        assert state.reason == record["private_state"]["reason"]
        assert len(posts) == 1
        assert posts[0].stance_label == expected_label
        assert posts[0].public_reason == record["public_post"]["public_reason"]


def test_social_prompt_never_contains_neighbor_private_reason_or_confidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    initial_public_reason = fixture.store.public_posts_for_agent("agent-0001")[0].public_reason
    fixture.pipeline.execute(**fixture.execute_kwargs)
    outcome = fixture.pipeline.execute(**fixture.execute_kwargs)

    event_input = fixture.store.event_input_evidence(outcome.lifecycle.event_id)
    assert event_input is not None
    prompt_payload = json.dumps(event_input.prompt_view.to_payload(), ensure_ascii=False)
    social_payload = json.dumps(event_input.prompt_view.social_messages, ensure_ascii=False)
    assert "NEIGHBOR_PRIVATE_SECRET" not in prompt_payload
    assert "confidence" not in social_payload
    assert initial_public_reason in social_payload


def test_consecutive_events_do_not_rescan_the_committed_history_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    fixture.pipeline.execute(**fixture.execute_kwargs)
    queried_ordinals: list[int] = []
    original_source_indexes = fixture.pipeline._source_indexes
    original_event_at = fixture.store.event_at

    def counted_source_indexes(ordinal: int):
        with monkeypatch.context() as scoped:

            def counted_event_at(event_ordinal: int):
                queried_ordinals.append(event_ordinal)
                return original_event_at(event_ordinal)

            scoped.setattr(fixture.store, "event_at", counted_event_at)
            return original_source_indexes(ordinal)

    monkeypatch.setattr(fixture.pipeline, "_source_indexes", counted_source_indexes)

    outcome = fixture.pipeline.execute(**fixture.execute_kwargs)

    assert outcome.lifecycle.state == "committed"
    assert 0 not in queried_ordinals


def test_landed_success_rebuilds_commit_from_storage_without_adapter_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    original = fixture.store.commit_success
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.store,
            "commit_success",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("after-finalize")),
        )
        with pytest.raises(RuntimeError, match="after-finalize"):
            fixture.pipeline.execute(**fixture.execute_kwargs)

    monkeypatch.setattr(fixture.pipeline, "_manifest", object())
    outcome = fixture.pipeline.execute(**fixture.execute_kwargs)

    assert fixture.store.commit_success == original
    assert outcome.lifecycle.state == "committed"
    assert outcome.lifecycle.adapter_invoked is False
    assert outcome.evidence.committed_event_hash is not None


def test_new_pipeline_recovers_landed_success_after_prior_committed_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    first = fixture.pipeline.execute(**fixture.execute_kwargs)
    assert first.lifecycle.state == "committed"

    original_commit = fixture.store.commit_success
    with monkeypatch.context() as scoped:
        scoped.setattr(
            fixture.store,
            "commit_success",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("after-finalize")),
        )
        with pytest.raises(RuntimeError, match="after-finalize"):
            fixture.pipeline.execute(**fixture.execute_kwargs)
    assert fixture.store.progress.next_event_ordinal == 1

    recovered_pipeline = MockEventPipeline(**fixture.pipeline_kwargs)
    monkeypatch.setattr(
        fixture.adapter,
        "generate",
        lambda request: (_ for _ in ()).throw(AssertionError("adapter must not be called")),
    )

    outcome = recovered_pipeline.execute(**fixture.execute_kwargs)

    assert fixture.store.commit_success == original_commit
    assert outcome.lifecycle.state == "committed"
    assert outcome.lifecycle.adapter_invoked is False
    assert fixture.store.progress.next_event_ordinal == 2
    assert all(
        (
            outcome.evidence.event_input_evidence_hash,
            outcome.evidence.request_hash,
            outcome.evidence.invocation_evidence_hash,
            outcome.evidence.parse_evidence_hash,
            outcome.evidence.terminal_attempt_hash,
            outcome.evidence.committed_event_hash,
        )
    )
    event = fixture.store.event_at(1)
    assert event is not None and event.event_id == outcome.lifecycle.event_id
    assert fixture.store.private_state("agent-0000").reason == "receiver-published-update"
    assert fixture.store.latest_public_pointer("agent-0000").published_event_ordinal == 1


@pytest.mark.parametrize(
    "crash_point",
    (
        "after_pending",
        "after_invocation",
        "after_terminal_success",
        "after_sqlite_commit_before_context",
    ),
)
def test_reopen_resumes_exact_durable_prefix_without_blind_resend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    adapter_calls = 0
    original_generate = fixture.adapter.generate

    def counted_generate(request):
        nonlocal adapter_calls
        adapter_calls += 1
        return original_generate(request)

    monkeypatch.setattr(fixture.adapter, "generate", counted_generate)
    with monkeypatch.context() as scoped:
        if crash_point == "after_pending":
            scoped.setattr(
                fixture.store,
                "append_attempt",
                lambda attempt: (_ for _ in ()).throw(RuntimeError(crash_point)),
            )
        elif crash_point == "after_invocation":
            scoped.setattr(
                fixture.store,
                "record_finalized_attempt",
                lambda evidence: (_ for _ in ()).throw(RuntimeError(crash_point)),
            )
        elif crash_point == "after_terminal_success":
            scoped.setattr(
                fixture.store,
                "commit_success",
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(crash_point)),
            )
        else:
            scoped.setattr(
                fixture.pipeline,
                "_advance_run_context_after_commit",
                lambda committed_event_id: (_ for _ in ()).throw(RuntimeError(crash_point)),
            )
        with pytest.raises(RuntimeError, match=crash_point):
            fixture.pipeline.execute(**fixture.execute_kwargs)

    prefix = fixture.store.evidence_references(event_id)
    calls_before_reopen = adapter_calls
    reopened = _reopen_fixture(fixture)
    outcome = reopened.pipeline.execute(**reopened.execute_kwargs)

    assert outcome.lifecycle.state in {"committed", "complete"}
    assert reopened.store.evidence_references(event_id).event_input_evidence_hash == (
        prefix.event_input_evidence_hash
    )
    assert reopened.store.evidence_references(event_id).request_hash == prefix.request_hash
    if crash_point == "after_pending":
        assert adapter_calls == calls_before_reopen + 1
    else:
        assert adapter_calls == calls_before_reopen


def test_reopen_in_progress_without_invocation_requires_explicit_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    adapter_calls = 0
    original_generate = fixture.adapter.generate
    original_append = fixture.store.append_attempt

    def counted_generate(request):
        nonlocal adapter_calls
        adapter_calls += 1
        return original_generate(request)

    def append_then_crash(attempt):
        original_append(attempt)
        raise RuntimeError("after_in_progress")

    monkeypatch.setattr(fixture.adapter, "generate", counted_generate)
    with monkeypatch.context() as scoped:
        scoped.setattr(fixture.store, "append_attempt", append_then_crash)
        with pytest.raises(RuntimeError, match="after_in_progress"):
            fixture.pipeline.execute(**fixture.execute_kwargs)
    prefix = fixture.store.evidence_references(event_id)
    assert prefix.invocation_evidence_hash is None
    assert adapter_calls == 0

    reopened = _reopen_fixture(fixture)
    with pytest.raises(RuntimeError, match="explicit provider reconciliation"):
        reopened.pipeline.execute(**reopened.execute_kwargs)

    assert adapter_calls == 0
    assert reopened.store.evidence_references(event_id) == prefix


def _crash_after_in_progress(fixture: PipelineFixture, monkeypatch: pytest.MonkeyPatch):
    original_append = fixture.store.append_attempt
    original_record_prepared = fixture.store.record_prepared_attempt
    captured_request = None

    def record_and_capture(*args, **kwargs):
        nonlocal captured_request
        captured_request = kwargs["request_evidence"].request
        return original_record_prepared(*args, **kwargs)

    def append_then_crash(attempt):
        original_append(attempt)
        raise RuntimeError("after_in_progress")

    with monkeypatch.context() as scoped:
        scoped.setattr(fixture.store, "record_prepared_attempt", record_and_capture)
        scoped.setattr(fixture.store, "append_attempt", append_then_crash)
        with pytest.raises(RuntimeError, match="after_in_progress"):
            fixture.pipeline.execute(**fixture.execute_kwargs)
    journal = fixture.store.current_event_journal()
    assert journal.latest_transition is not None
    request_evidence = fixture.store.adapter_request_evidence(journal.latest_transition.attempt_id)
    assert request_evidence is not None
    assert captured_request == request_evidence.request
    response = fixture.adapter.generate(captured_request)
    return (
        journal,
        request_evidence,
        captured_request,
        AttemptInvocationResult(
            response=response,
            evidence=AttemptExecutionEvidence(
                started_at=journal.latest_transition.started_at,
                finished_at=NOW,
                http_status=fixture.execute_kwargs["http_status"],
                provider_metadata=MockEventPipeline._provider_metadata(response),
                usage=fixture.execute_kwargs["usage"],
                finish_reason=fixture.execute_kwargs["finish_reason"],
            ),
        ),
    )


def test_reopen_in_progress_accepts_exact_public_reconciliation_without_adapter_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    journal, request_evidence, _trusted_request, reconciliation = _crash_after_in_progress(
        fixture, monkeypatch
    )
    before = fixture.store.progress
    reopened = _reopen_fixture(fixture)
    pipeline_calls = 0

    def fail_if_called(_request):
        nonlocal pipeline_calls
        pipeline_calls += 1
        raise AssertionError("pipeline adapter must not be called during reconciliation")

    monkeypatch.setattr(reopened.adapter, "generate", fail_if_called)
    outcome = reopened.pipeline.execute(
        **{**reopened.execute_kwargs, "reconciliation": reconciliation}
    )

    assert outcome.lifecycle.state == "committed"
    assert outcome.lifecycle.adapter_invoked is False
    assert pipeline_calls == 0
    assert outcome.lifecycle.event_id == journal.event_id
    assert reopened.store.progress.next_event_ordinal == before.next_event_ordinal + 1
    assert reopened.store.invocation_evidence(request_evidence.attempt_id) is not None
    assert reopened.store.parse_evidence(request_evidence.attempt_id) is not None
    assert reopened.store.event_at(0) is not None


@pytest.mark.parametrize("mismatch", ("request", "attempt", "response", "binding"))
def test_reconciliation_mismatch_is_rejected_atomically_before_evidence_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    journal, request_evidence, trusted_request, reconciliation = _crash_after_in_progress(
        fixture, monkeypatch
    )
    if mismatch in {"request", "attempt"}:
        response = copy.copy(reconciliation.response)
        object.__setattr__(
            response,
            "request_id" if mismatch == "request" else "attempt_id",
            "forged-request" if mismatch == "request" else "forged-attempt",
        )
        reconciliation = AttemptInvocationResult(response, reconciliation.evidence)
    elif mismatch == "response":
        evidence = copy.copy(reconciliation.evidence)
        object.__setattr__(
            evidence,
            "provider_metadata",
            {**dict(evidence.provider_metadata), "adapter_response_hash": "f" * 64},
        )
        reconciliation = AttemptInvocationResult(reconciliation.response, evidence)
    else:
        different_adapter = MockAdapter(
            script={journal.event_id: (MockScriptStep.timeout("different binding"),)},
            mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
            mock_only=True,
        )
        response = different_adapter.generate(trusted_request)
        reconciliation = AttemptInvocationResult(
            response,
            replace(
                reconciliation.evidence,
                provider_metadata=MockEventPipeline._provider_metadata(response),
            ),
        )

    reopened = _reopen_fixture(fixture)
    before = (
        reopened.store.progress,
        reopened.store.evidence_references(journal.event_id),
        reopened.store.private_state("agent-0000"),
        reopened.store.latest_public_pointer("agent-0000"),
        reopened.store.feed_cursor("agent-0000"),
    )
    with pytest.raises(ValueError, match="request|attempt|response|bind|invocation"):
        reopened.pipeline.execute(**{**reopened.execute_kwargs, "reconciliation": reconciliation})

    assert reopened.store.invocation_evidence(request_evidence.attempt_id) is None
    assert (
        reopened.store.progress,
        reopened.store.evidence_references(journal.event_id),
        reopened.store.private_state("agent-0000"),
        reopened.store.latest_public_pointer("agent-0000"),
        reopened.store.feed_cursor("agent-0000"),
    ) == before


def test_reconciliation_is_rejected_outside_unlanded_in_progress_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source"
    fresh_path = tmp_path / "fresh"
    source_path.mkdir()
    fresh_path.mkdir()
    source = _fixture(source_path, exposure="E0")
    _, _, _, reconciliation = _crash_after_in_progress(source, monkeypatch)
    fresh = _fixture(fresh_path, exposure="E0")
    before = fresh.store.progress

    with pytest.raises(ValueError, match="only valid for an existing IN_PROGRESS"):
        fresh.pipeline.execute(**{**fresh.execute_kwargs, "reconciliation": reconciliation})

    assert fresh.store.progress == before
    assert fresh.store.current_event_journal().latest_transition is None


def test_reconciliation_conflicts_with_already_persisted_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    original_record_finalized = fixture.store.record_finalized_attempt

    def crash_after_invocation(_evidence):
        raise RuntimeError("after_invocation")

    monkeypatch.setattr(fixture.store, "record_finalized_attempt", crash_after_invocation)
    with pytest.raises(RuntimeError, match="after_invocation"):
        fixture.pipeline.execute(**fixture.execute_kwargs)
    journal = fixture.store.current_event_journal()
    assert journal.latest_transition is not None
    persisted = fixture.store.invocation_evidence(journal.latest_transition.attempt_id)
    assert persisted is not None
    reconciliation = AttemptInvocationResult(
        response=persisted.response,
        evidence=AttemptExecutionEvidence(**dict(persisted.execution_payload)),
    )
    monkeypatch.setattr(fixture.store, "record_finalized_attempt", original_record_finalized)
    reopened = _reopen_fixture(fixture)

    with pytest.raises(ValueError, match="persisted invocation forbids"):
        reopened.pipeline.execute(**{**reopened.execute_kwargs, "reconciliation": reconciliation})
    assert reopened.store.parse_evidence(journal.latest_transition.attempt_id) is None


@pytest.mark.parametrize(
    "mismatch",
    (
        "final_request",
        "terminal_attempt",
        "terminal_response",
        "parse_attempt",
        "parse_request",
        "parse_response",
    ),
)
def test_mismatched_finalization_is_rejected_atomically_without_partial_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    agent_id = "agent-0000"
    before = (
        fixture.store.progress,
        fixture.store.private_state(agent_id),
        fixture.store.latest_public_pointer(agent_id),
        fixture.store.feed_cursor(agent_id),
    )
    original_finalize = fixture.pipeline._finalize

    def forged_finalize(prepared, result):
        finalized = original_finalize(prepared, result)
        forged = copy.copy(finalized)
        if mismatch == "final_request":
            object.__setattr__(forged, "request_hash", "f" * 64)
        elif mismatch.startswith("terminal_"):
            terminal = copy.copy(finalized.attempt)
            if mismatch == "terminal_attempt":
                object.__setattr__(terminal, "attempt_id", "attempt-forged")
            else:
                object.__setattr__(terminal, "raw_response", "forged response")
            object.__setattr__(forged, "attempt", terminal)
        else:
            parse = copy.copy(finalized.parse_evidence)
            if mismatch == "parse_attempt":
                object.__setattr__(parse, "attempt_id", "attempt-forged")
            elif mismatch == "parse_request":
                object.__setattr__(parse, "request_id", "request-forged")
            else:
                object.__setattr__(parse, "response_hash", "f" * 64)
            object.__setattr__(forged, "parse_evidence", parse)
        assert isinstance(forged, FinalizedAttemptEvidence)
        return forged

    monkeypatch.setattr(fixture.pipeline, "_finalize", forged_finalize)
    with pytest.raises(ValueError, match="request|attempt|response|parse|terminal|bind|drift"):
        fixture.pipeline.execute(**fixture.execute_kwargs)

    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    journal = fixture.store.current_event_journal()
    assert journal.resume_state == "in_progress_requires_provider_reconciliation"
    assert journal.latest_transition is not None
    attempt_id = journal.latest_transition.attempt_id
    assert fixture.store.invocation_evidence(attempt_id) is not None
    assert fixture.store.parse_evidence(attempt_id) is None
    assert fixture.store.attempts_for_event(event_id) == ()
    assert (
        fixture.store.progress,
        fixture.store.private_state(agent_id),
        fixture.store.latest_public_pointer(agent_id),
        fixture.store.feed_cursor(agent_id),
    ) == before


def test_post_commit_context_cache_failure_rebuilds_identical_next_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uninterrupted_path = tmp_path / "uninterrupted"
    interrupted_path = tmp_path / "interrupted"
    uninterrupted_path.mkdir()
    interrupted_path.mkdir()
    uninterrupted = _fixture(uninterrupted_path, exposure="E2")
    uninterrupted.pipeline.execute(**uninterrupted.execute_kwargs)
    uninterrupted.pipeline.execute(**uninterrupted.execute_kwargs)
    expected = uninterrupted.store.event_input_evidence(
        derive_event_id(uninterrupted.store.binding.run_id, 1)
    )
    assert expected is not None

    interrupted = _fixture(interrupted_path, exposure="E2")
    original_advance = interrupted.pipeline._advance_run_context_after_commit
    with monkeypatch.context() as scoped:
        scoped.setattr(
            interrupted.pipeline,
            "_advance_run_context_after_commit",
            lambda event_id: (_ for _ in ()).throw(RuntimeError("post-commit-cache")),
        )
        with pytest.raises(RuntimeError, match="post-commit-cache"):
            interrupted.pipeline.execute(**interrupted.execute_kwargs)
    assert interrupted.store.progress.next_event_ordinal == 1

    monkeypatch.setattr(
        interrupted.pipeline,
        "_advance_run_context_after_commit",
        original_advance,
    )
    outcome = interrupted.pipeline.execute(**interrupted.execute_kwargs)
    actual = interrupted.store.event_input_evidence(
        derive_event_id(interrupted.store.binding.run_id, 1)
    )

    assert outcome.lifecycle.state == "committed"
    assert actual is not None
    assert actual.prompt_view == expected.prompt_view


def test_timeout_persists_parse_not_applicable_and_leaves_research_state_unchanged(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    agent_id = "agent-0000"
    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    adapter = MockAdapter(
        script={event_id: (MockScriptStep.timeout("explicit mock timeout"),)},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    kwargs = {
        **fixture.execute_kwargs,
        "adapter": adapter,
        "model_identity": adapter.execution_binding().model_identity,
        "http_status": None,
        "usage": {},
        "finish_reason": None,
    }
    before = (
        fixture.store.progress,
        fixture.store.private_state(agent_id),
        fixture.store.latest_public_pointer(agent_id),
        fixture.store.feed_cursor(agent_id),
    )

    outcome = fixture.pipeline.execute(**kwargs)

    assert outcome.lifecycle.state == "failed"
    assert isinstance(
        fixture.store.parse_evidence(outcome.lifecycle.attempt.attempt_id),
        ParseNotApplicableEvidence,
    )
    assert fixture.store.terminal_failure_evidence() is not None
    assert (
        fixture.store.progress,
        fixture.store.private_state(agent_id),
        fixture.store.latest_public_pointer(agent_id),
        fixture.store.feed_cursor(agent_id),
    ) == before


def test_malformed_response_persists_typed_parse_failure_without_state_change(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E0")
    agent_id = "agent-0000"
    event_id = derive_event_id(fixture.store.binding.run_id, 0)
    adapter = MockAdapter(
        script={event_id: (MockScriptStep.malformed("not-json"),)},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    before = (
        fixture.store.progress,
        fixture.store.private_state(agent_id),
        fixture.store.latest_public_pointer(agent_id),
        fixture.store.feed_cursor(agent_id),
    )

    outcome = fixture.pipeline.execute(
        **{
            **fixture.execute_kwargs,
            "adapter": adapter,
            "model_identity": adapter.execution_binding().model_identity,
        }
    )

    parse = fixture.store.parse_evidence(outcome.lifecycle.attempt.attempt_id)
    assert outcome.lifecycle.state == "failed"
    assert isinstance(parse, ParseEvidence)
    assert parse.success is False
    assert parse.raw_response == "not-json"
    assert parse.error is not None
    invocation = fixture.store.invocation_evidence(outcome.lifecycle.attempt.attempt_id)
    assert invocation is not None
    assert invocation.response.raw_response == "not-json"
    assert outcome.lifecycle.attempt.raw_response == "not-json"
    assert fixture.store.terminal_failure_evidence() is not None
    assert (
        fixture.store.progress,
        fixture.store.private_state(agent_id),
        fixture.store.latest_public_pointer(agent_id),
        fixture.store.feed_cursor(agent_id),
    ) == before


def test_pipeline_has_no_research_or_runtime_parameter_defaults() -> None:
    parameters = inspect.signature(MockEventPipeline.execute).parameters
    for name in (
        "feed_capacity",
        "memory_window",
        "parser_limits",
        "prompt_limits",
        "policy",
        "model_identity",
        "request_parameters",
        "model_seed",
        "adapter",
        "http_status",
        "usage",
        "finish_reason",
        "reconciliation",
    ):
        assert parameters[name].default is inspect.Parameter.empty


def test_pipeline_public_types_are_exported() -> None:
    assert agent_ex.MockEventPipeline is MockEventPipeline
    assert agent_ex.MockEventPipelineOutcome is MockEventPipelineOutcome
