from __future__ import annotations

import copy
import inspect
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import pytest
import agent_ex

from agent_ex.adapters.mock import MockAdapter, MockScriptStep
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import FrozenSchedule, RunManifest, ScheduleSlot, derive_event_id
from agent_ex.execution_evidence import MockAttemptPolicyBinding, ParseNotApplicableEvidence
from agent_ex.feed import FeedCursor
from agent_ex.initialization import assign_initial_reasons, assign_initial_stances
from agent_ex.network import build_agent_node_mapping, build_shadow_artifact, build_ws_artifact
from agent_ex.parser import ParseEvidence, ParserLimits
from agent_ex.pipeline import MockEventPipeline, MockEventPipelineOutcome
from agent_ex.population import build_population_artifact
from agent_ex.prompt import PromptLimits
from agent_ex.state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from agent_ex.storage import RunStorage
from test_prompt import member, persona_template, topic
from test_storage import manifest


NOW = "2026-09-01T00:00:00+00:00"


@dataclass(frozen=True, slots=True)
class PipelineFixture:
    store: RunStorage
    pipeline: MockEventPipeline
    adapter: MockAdapter
    execute_kwargs: Mapping[str, object]
    pipeline_kwargs: Mapping[str, object]
    graph: ArtifactEnvelope | None
    mapping: ArtifactEnvelope | None


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
    *, agent_id: str, exposure_mode: str, exposure_graph_hash: str | None
) -> tuple[PrivateUpdate, PrivateState, PublicPost, LatestPublicPointer, FeedCursor]:
    initial = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id=agent_id,
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label="label-1",
        reason=f"round-zero-public-reason-{agent_id}",
        confidence=None,
        published=True,
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


def _fixture(
    tmp_path: Path, *, exposure: str, bind_manifest_model_identity: bool = True
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
    population = _population(size)
    artifacts = {population.artifact_id: population.output_hash}
    round0 = None
    mapping = None
    if graph is not None:
        artifacts[graph.artifact_id] = graph.output_hash
        if source_ws is not None:
            artifacts[source_ws.artifact_id] = source_ws.output_hash
        round0, stances, reason_library = _round0_artifacts(population)
        mapping = build_agent_node_mapping(
            population_artifact=population,
            round0_initialization_artifact=round0,
            network_artifact=graph if source_ws is None else source_ws,
            matched_seed=17,
            mock_only=True,
        )
        artifacts[round0.artifact_id] = round0.output_hash
        artifacts[stances.artifact_id] = stances.output_hash
        artifacts[reason_library.artifact_id] = reason_library.output_hash
        artifacts[mapping.artifact_id] = mapping.output_hash
        neighbors = _mapped_neighbors(graph, mapping)
    script = {
        derive_event_id(run_manifest.run_id, index): (MockScriptStep.success(payload),)
        for index, payload in enumerate(script_payloads)
    }
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
    with store.acquire_run_lease():
        for agent_id in store.binding.expected_agent_ids:
            store.initialize_agent(
                *_initial_records(
                    agent_id=agent_id,
                    exposure_mode=exposure_mode,
                    exposure_graph_hash=None if graph is None else graph.output_hash,
                )
            )
        store.seal_initial_state()
    parser_limits, prompt_limits = _limits()
    policy = MockAttemptPolicyBinding.create(
        allowed_difference_fields=("model_seed", "request_parameters.temperature"),
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
        "round0_initialization_artifact": round0,
        "frozen_neighbor_agent_ids": neighbors,
        "clock": lambda: NOW,
    }
    pipeline = MockEventPipeline(**pipeline_kwargs)
    return PipelineFixture(
        store=store,
        pipeline=pipeline,
        adapter=adapter,
        pipeline_kwargs=pipeline_kwargs,
        graph=graph,
        mapping=mapping,
        execute_kwargs={
            "feed_capacity": 4,
            "memory_window": 3,
            "parser_limits": parser_limits,
            "prompt_limits": prompt_limits,
            "policy": policy,
            "model_identity": adapter.execution_binding().model_identity,
            "request_parameters": {"temperature": 0.0},
            "model_seed": 12345,
            "adapter": adapter,
            "http_status": 200,
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            "finish_reason": "stop",
        },
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


@pytest.mark.parametrize("drift", ("empty", "self", "out_of_roster", "asymmetric"))
def test_e2_rejects_neighbor_mapping_that_drifts_from_frozen_graph(
    tmp_path: Path, drift: str
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
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
    assert fixture.store.terminal_failure_evidence() is not None
    assert (
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
    ):
        assert parameters[name].default is inspect.Parameter.empty


def test_pipeline_public_types_are_exported() -> None:
    assert agent_ex.MockEventPipeline is MockEventPipeline
    assert agent_ex.MockEventPipelineOutcome is MockEventPipelineOutcome
