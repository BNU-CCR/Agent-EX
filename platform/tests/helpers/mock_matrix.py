from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Callable, Mapping

from agent_ex.adapters import MockAdapter, MockScriptStep
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import (
    EventStatus,
    FrozenSchedule,
    RunManifest,
    canonical_payload_hash,
    derive_event_id,
    derive_run_id,
)
from agent_ex.execution_evidence import MockAdapterExecutionBinding
from agent_ex.initialization import assign_initial_reasons, assign_initial_stances
from agent_ex.mock_matrix import (
    CANONICAL_CELL_IDS,
    MockMatchedSeedMatrix,
    MockScaleCase,
    build_mock_matched_seed_matrix,
    load_mock_scale_cases,
)
from agent_ex.network import (
    build_agent_node_mapping,
    build_shadow_artifact,
    build_structural_gate_artifact,
    build_ws_artifact,
)
from agent_ex.population import build_population_artifact
from agent_ex.schedule import (
    build_activation_schedule,
    build_attention_artifact,
    build_expression_artifact,
    build_publish_schedule,
)
from agent_ex.topic import TopicPackage


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "paper1"


def _load_envelope(name: str) -> ArtifactEnvelope:
    return ArtifactEnvelope.from_payload(
        json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    )


@dataclass(frozen=True, slots=True)
class MockArtifactFamily:
    topic_package: TopicPackage
    population_artifact: ArtifactEnvelope
    initial_stance_artifact: ArtifactEnvelope
    initial_reason_artifact: ArtifactEnvelope
    persona_template: ArtifactEnvelope
    ws_artifact: ArtifactEnvelope
    shadow_artifact: ArtifactEnvelope
    agent_node_mapping: ArtifactEnvelope
    structural_gate_artifact: ArtifactEnvelope
    attention_artifact: ArtifactEnvelope
    expression_artifact: ArtifactEnvelope
    activation_artifact: ArtifactEnvelope
    publish_artifact: ArtifactEnvelope
    schedules_by_cell: dict[str, FrozenSchedule]
    manifests_by_cell: dict[str, RunManifest]
    adapter_bindings_by_cell: dict[str, MockAdapterExecutionBinding]


@dataclass(frozen=True, slots=True)
class MockMatrixFixture:
    scale_case: MockScaleCase
    family: MockArtifactFamily
    matrix: MockMatchedSeedMatrix
    clock: Callable[[], str]


def _manifest(
    *,
    cell_id: str,
    matched_seed: int,
    schedule: FrozenSchedule,
    location: Path,
    mock_matrix_binding: Mapping[str, object],
) -> RunManifest:
    run_spec = {
        "protocol_id": "paper1",
        "protocol_version": "mock-matrix-v1",
        "protocol_hash": "a" * 64,
        "schedule_hash": schedule.schedule_hash,
        "cell_id": cell_id,
        "run_config": {
            "population": schedule.population_size,
            "sweep_count": schedule.sweep_count,
            "expected_event_count": schedule.count,
        },
        "request_parameters": {"temperature": 0.0},
        "mock_matrix_binding": dict(mock_matrix_binding),
    }
    launch_nonce = f"mock-matrix-{cell_id.lower()}"
    run_id = derive_run_id(run_spec, matched_seed, launch_nonce)
    return RunManifest(
        run_id=run_id,
        run_spec=run_spec,
        run_spec_hash=canonical_payload_hash(run_spec),
        matched_seed=matched_seed,
        launch_nonce=launch_nonce,
        protocol_id="paper1",
        protocol_version="mock-matrix-v1",
        protocol_hash="a" * 64,
        git_sha="c" * 40,
        dirty=False,
        diff_hash=None,
        environment_lock_hash="b" * 64,
        model_identity={
            "provider": "deterministic-mock",
            "model": "deterministic-mock-model",
            "revision": "phase4b7-script-v1",
            "runtime": "agent_ex.adapters.mock.MockAdapter",
        },
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "b" * 64,
            "platform": "test",
        },
        schedule_uri=(location / f"{cell_id}.schedule.json").as_uri(),
        schedule=schedule,
        schedule_hash=schedule.schedule_hash,
        checkpoint_uri=None,
        checkpoint_hash=None,
        recovery_cursor=None,
        event_ids=(),
        terminal_counts={status.value: 0 for status in EventStatus},
        started_at="2040-01-01T00:00:00Z",
        updated_at="2040-01-01T00:00:00Z",
        archive={"status": "pending", "uri": None, "hash": None},
    )


def _adapter_semantics_hash(
    ordered_script_step_hashes: tuple[tuple[str, ...], ...],
) -> str:
    return canonical_payload_hash(
        {
            "expected_adapter_kind": "agent_ex.adapters.mock.MockAdapter",
            "expected_adapter_version": "1.0.0",
            "runtime_identity_hash": canonical_payload_hash(
                {
                    "adapter": "agent_ex.adapters.mock.MockAdapter",
                    "adapter_version": "1.0.0",
                    "provider": "deterministic-mock",
                    "runtime_version": "1.0.0",
                }
            ),
            "model_identity_hash": canonical_payload_hash(
                {
                    "model": "deterministic-mock-model",
                    "revision": "phase4b7-script-v1",
                    "mode": "script_only_no_generation",
                }
            ),
            "ordered_script_step_hashes": ordered_script_step_hashes,
        }
    )


def build_mock_artifact_family(*, n: int, sweeps: int, matched_seed: int) -> MockArtifactFamily:
    frame = _load_envelope("mock_population_frame.artifact.json")
    reasons = _load_envelope("mock_reason_library.artifact.json")
    topic_artifact = _load_envelope("mock_topic_package.artifact.json")
    persona_template = _load_envelope("mock_persona_template.artifact.json")
    scale_case = next(
        case
        for case in load_mock_scale_cases(_load_envelope("mock_scale_cases.artifact.json"))
        if case.population_size == n
    )
    topic_package = TopicPackage.from_payload(topic_artifact.to_payload()["payload"])
    frame_payload = frame.to_payload()["payload"]
    population = build_population_artifact(
        donors=tuple(frame_payload["donors"]),
        weights=tuple(frame_payload["weight_profiles"][str(n)]),
        n=n,
        matched_seed=matched_seed,
        input_artifact_hash=frame.output_hash,
        constraints=frame_payload["constraints"],
        tolerance=0,
        mock_only=True,
    )
    stances = assign_initial_stances(
        population_artifact=population,
        matched_seed=matched_seed,
        orthogonal_fields=("gender", "urban", "education"),
        max_category_imbalance=1.0,
        mock_only=True,
    )
    round0 = assign_initial_reasons(
        stance_artifact=stances,
        reason_library_artifact=reasons,
        matched_seed=matched_seed,
        mock_only=True,
    )
    ws = build_ws_artifact(n=n, k=4, p=0.05, matched_seed=matched_seed, mock_only=True)
    shadow = build_shadow_artifact(
        ws,
        matched_seed=matched_seed,
        max_attempts=4,
        trial_budget_per_edge=500,
        mock_only=True,
    )
    mapping = build_agent_node_mapping(
        population_artifact=population,
        round0_initialization_artifact=round0,
        network_artifact=ws,
        matched_seed=matched_seed,
        mock_only=True,
    )
    structural_gate = build_structural_gate_artifact(
        ws, matched_seed=matched_seed, random_null_replicates=3, mock_only=True
    )
    agent_ids = tuple(record["agent_id"] for record in population.payload["members"])
    attention = build_attention_artifact(
        agent_ids=agent_ids,
        matched_seed=matched_seed,
        family="equal_weight",
        parameters={},
        mock_only=True,
    )
    expression = build_expression_artifact(
        agent_ids=agent_ids,
        matched_seed=matched_seed,
        structural_lurker_probability=0.2,
        beta_alpha=2.0,
        beta_beta=2.0,
        max_beta_attempts_per_agent=100,
        correlation_mode="independent",
        mock_only=True,
    )
    activation = build_activation_schedule(
        attention, matched_seed=matched_seed, sweep_count=sweeps, mock_only=True
    )
    publish = build_publish_schedule(
        attention, activation, expression, matched_seed=matched_seed, mock_only=True
    )
    schedule = FrozenSchedule.from_payload(publish.to_payload()["payload"]["frozen_schedule"])
    schedules = {cell_id: schedule for cell_id in CANONICAL_CELL_IDS}
    location = FIXTURE_DIR.resolve()
    steps_by_ordinal = tuple(
        (
            MockScriptStep.success(
                {
                    "stance": "label-4",
                    "confidence": 3,
                    "public_reason": f"mock matrix event {ordinal}",
                }
            ),
        )
        for ordinal in range(schedule.count)
    )
    ordered_step_hashes = tuple(
        tuple(canonical_payload_hash(step.to_payload()) for step in steps)
        for steps in steps_by_ordinal
    )
    adapter_semantics_hash = _adapter_semantics_hash(ordered_step_hashes)
    artifact_hashes = {
        "topic": topic_package.package_hash,
        "population": population.output_hash,
        "stance": stances.output_hash,
        "reason": round0.output_hash,
        "persona_template": persona_template.output_hash,
        "ws": ws.output_hash,
        "shadow": shadow.output_hash,
        "mapping": mapping.output_hash,
        "structural_gate": structural_gate.output_hash,
        "attention": attention.output_hash,
        "expression": expression.output_hash,
        "activation": activation.output_hash,
        "publish": publish.output_hash,
        "schedule": schedule.schedule_hash,
    }
    clock_payload = {
        "schema_version": "paper1.mock-clock-sequence.v1",
        "mock_clock_start": scale_case.mock_clock_start,
        "mock_clock_step_seconds": scale_case.mock_clock_step_seconds,
    }
    clock_hash = canonical_payload_hash(clock_payload)
    manifests = {}
    for cell_id in CANONICAL_CELL_IDS:
        _, identity_token, continuity_token, exposure_token = cell_id.split("-")
        exposure_mode = {
            "E0": "self_history_only",
            "E1": "shuffled_social",
            "E2": "ws_neighbors",
        }[exposure_token]
        exposure_graph_hash = (
            None
            if exposure_token == "E0"
            else shadow.output_hash
            if exposure_token == "E1"
            else ws.output_hash
        )
        manifests[cell_id] = _manifest(
            cell_id=cell_id,
            matched_seed=matched_seed,
            schedule=schedule,
            location=location,
            mock_matrix_binding={
                "schema_version": "paper1.mock-cell-run-binding.v1",
                "scale_case_id": scale_case.case_id,
                "scale_case_hash": canonical_payload_hash(scale_case.to_payload()),
                "cell_id": cell_id,
                "identity_present": identity_token == "I1",
                "continuity_present": continuity_token == "C1",
                "exposure_mode": exposure_mode,
                "exposure_graph_hash": exposure_graph_hash,
                "artifact_hashes": artifact_hashes,
                "clock_sequence_id": "mock-clock-" + clock_hash,
                "clock_sequence_hash": clock_hash,
                "adapter_semantics_hash": adapter_semantics_hash,
            },
        )
    bindings = {}
    for cell_id, manifest in manifests.items():
        adapter = MockAdapter(
            script={
                derive_event_id(manifest.run_id, ordinal): steps_by_ordinal[ordinal]
                for ordinal in range(schedule.count)
            },
            mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
            mock_only=True,
        )
        bindings[cell_id] = adapter.execution_binding()
    return MockArtifactFamily(
        topic_package=topic_package,
        population_artifact=population,
        initial_stance_artifact=stances,
        initial_reason_artifact=round0,
        persona_template=persona_template,
        ws_artifact=ws,
        shadow_artifact=shadow,
        agent_node_mapping=mapping,
        structural_gate_artifact=structural_gate,
        attention_artifact=attention,
        expression_artifact=expression,
        activation_artifact=activation,
        publish_artifact=publish,
        schedules_by_cell=schedules,
        manifests_by_cell=manifests,
        adapter_bindings_by_cell=bindings,
    )


def build_mock_matrix_fixture(tmp_path: Path, *, case_id: str, sweeps: int) -> MockMatrixFixture:
    cases = load_mock_scale_cases(_load_envelope("mock_scale_cases.artifact.json"))
    scale_case = next(case for case in cases if case.case_id == case_id)
    family = build_mock_artifact_family(
        n=scale_case.population_size, sweeps=sweeps, matched_seed=101
    )
    matrix = build_mock_matched_seed_matrix(
        scale_case=scale_case,
        matched_seed=101,
        topic_package=family.topic_package,
        population_artifact=family.population_artifact,
        initial_stance_artifact=family.initial_stance_artifact,
        initial_reason_artifact=family.initial_reason_artifact,
        persona_template=family.persona_template,
        ws_artifact=family.ws_artifact,
        shadow_artifact=family.shadow_artifact,
        agent_node_mapping=family.agent_node_mapping,
        structural_gate_artifact=family.structural_gate_artifact,
        attention_artifact=family.attention_artifact,
        expression_artifact=family.expression_artifact,
        activation_artifact=family.activation_artifact,
        publish_artifact=family.publish_artifact,
        schedules_by_cell=family.schedules_by_cell,
        manifests_by_cell=family.manifests_by_cell,
        adapter_bindings_by_cell=family.adapter_bindings_by_cell,
    )
    current = datetime.fromisoformat(scale_case.mock_clock_start.replace("Z", "+00:00"))
    step = timedelta(seconds=scale_case.mock_clock_step_seconds)

    def clock() -> str:
        nonlocal current
        value = current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        current += step
        return value

    del tmp_path
    return MockMatrixFixture(scale_case=scale_case, family=family, matrix=matrix, clock=clock)
