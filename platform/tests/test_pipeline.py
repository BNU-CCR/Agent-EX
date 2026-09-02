from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pytest
import agent_ex

from agent_ex.adapters.mock import MockAdapter, MockScriptStep
from agent_ex.domain import FrozenSchedule, ScheduleSlot, derive_event_id
from agent_ex.execution_evidence import MockAttemptPolicyBinding, ParseNotApplicableEvidence
from agent_ex.feed import FeedCursor
from agent_ex.network import build_ws_artifact
from agent_ex.parser import ParserLimits
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


def _fixture(tmp_path: Path, *, exposure: str) -> PipelineFixture:
    if exposure == "E0":
        size = 1
        cell_id = "P1-I0-C0-E0"
        exposure_mode = "self_history_only"
        graph = None
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
    if graph is not None:
        artifacts[graph.artifact_id] = graph.output_hash
    store = RunStorage.create(
        tmp_path / f"pipeline-{exposure}.sqlite",
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=tuple(f"agent-{index:04d}" for index in range(size)),
        expected_exposure_mode=exposure_mode,
        expected_exposure_graph_hash=None if graph is None else graph.output_hash,
        expected_exposure_graph_artifact=graph,
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
    script = {
        f"event-{run_manifest.run_id}-{index}": (MockScriptStep.success(payload),)
        for index, payload in enumerate(script_payloads)
    }
    # Event IDs are hash-derived rather than human-readable.
    script = {
        derive_event_id(run_manifest.run_id, index): (MockScriptStep.success(payload),)
        for index, payload in enumerate(script_payloads)
    }
    adapter = MockAdapter(
        script=script,
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    parser_limits, prompt_limits = _limits()
    policy = MockAttemptPolicyBinding.create(
        allowed_difference_fields=("model_seed", "request_parameters.temperature"),
        mock_only=True,
        formal_eligible=False,
    )
    pipeline = MockEventPipeline(
        storage=store,
        manifest=run_manifest,
        topic_package=topic(),
        persona_template=persona_template(),
        population_artifact=population,
        frozen_neighbor_agent_ids=neighbors,
        clock=lambda: NOW,
    )
    return PipelineFixture(
        store=store,
        pipeline=pipeline,
        adapter=adapter,
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


def test_social_prompt_never_contains_neighbor_private_reason_or_confidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, exposure="E2")
    fixture.pipeline.execute(**fixture.execute_kwargs)
    outcome = fixture.pipeline.execute(**fixture.execute_kwargs)

    event_input = fixture.store.event_input_evidence(outcome.lifecycle.event_id)
    assert event_input is not None
    prompt_payload = json.dumps(event_input.prompt_view.to_payload(), ensure_ascii=False)
    social_payload = json.dumps(event_input.prompt_view.social_messages, ensure_ascii=False)
    assert "NEIGHBOR_PRIVATE_SECRET" not in prompt_payload
    assert "confidence" not in social_payload
    assert "round-zero-public-reason-agent-0001" in social_payload


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
