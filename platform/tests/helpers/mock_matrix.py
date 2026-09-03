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
from agent_ex.engine import AttemptInvocationResult
from agent_ex.initialization import assign_initial_reasons, assign_initial_stances
from agent_ex.mock_matrix import (
    CANONICAL_CELL_IDS,
    MockMatchedSeedMatrix,
    MockScaleCase,
    build_mock_matched_seed_matrix,
    load_mock_scale_cases,
    mock_adapter_semantics_hash,
    mock_clock_sequence_binding,
)
from agent_ex.mock_run import MockEventInvocation
from agent_ex.network import (
    build_agent_node_mapping,
    build_shadow_artifact,
    build_structural_gate_artifact,
    build_ws_artifact,
)
from agent_ex.population import build_population_artifact
from agent_ex.parser import ParserLimits
from agent_ex.pipeline import MockEventPipeline
from agent_ex.prompt import PromptLimits
from agent_ex.feed import FeedCursor
from agent_ex.schedule import (
    build_activation_schedule,
    build_attention_artifact,
    build_expression_artifact,
    build_publish_schedule,
)
from agent_ex.topic import TopicPackage
from agent_ex.execution_evidence import MockAttemptPolicyBinding
from agent_ex.storage import RunStorage
from agent_ex.state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost


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


@dataclass(frozen=True, slots=True)
class MatrixCellFixture:
    pipeline: MockEventPipeline
    storage: RunStorage
    parser_limits: ParserLimits
    prompt_limits: PromptLimits
    policy: MockAttemptPolicyBinding
    model_identity: Mapping[str, str]
    request_parameters: Mapping[str, object]
    http_status: int | None
    usage: Mapping[str, object]
    finish_reason: str | None
    stance_label: str


@dataclass(frozen=True, slots=True)
class BoundMockMatrixCell:
    """Test-only durable cell wiring used by integration recovery tests."""

    matrix_fixture: MockMatrixFixture
    cell: MatrixCellFixture
    cell_id: str
    database_path: Path
    manifest: RunManifest
    exposure_graph_artifact: ArtifactEnvelope | None
    source_ws_artifact: ArtifactEnvelope | None
    agent_node_mapping_artifact: ArtifactEnvelope | None
    round0_initialization_artifact: ArtifactEnvelope | None
    frozen_neighbor_agent_ids: Mapping[str, tuple[str, ...]]


class MockClockLedger:
    """Test-only deterministic clock; never model-seed or formal-time authority."""

    def __init__(
        self,
        *,
        scale_case: MockScaleCase,
        replay_values: tuple[str, ...],
        next_sequence_index: int,
    ) -> None:
        if type(next_sequence_index) is not int or next_sequence_index < 0:
            raise ValueError("mock clock next_sequence_index must be nonnegative")
        self._start = datetime.fromisoformat(scale_case.mock_clock_start.replace("Z", "+00:00"))
        self._step = timedelta(seconds=scale_case.mock_clock_step_seconds)
        self._replay = list(replay_values)
        self._next_sequence_index = next_sequence_index
        self.calls: list[str] = []

    def __call__(self) -> str:
        if self._replay:
            value = self._replay.pop(0)
        else:
            value = (
                (self._start + self._step * self._next_sequence_index)
                .astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            self._next_sequence_index += 1
        self.calls.append(value)
        return value


def rebuild_mock_clock_ledger(
    *,
    scale_case: MockScaleCase,
    storage: RunStorage,
    manifest: RunManifest,
    reconciliation: AttemptInvocationResult | None,
) -> MockClockLedger:
    """Rebuild mock clock position from public durable evidence and journal state."""

    if not isinstance(manifest, RunManifest):
        raise TypeError("mock clock rebuild requires a typed manifest")
    if (
        manifest.run_id != storage.binding.run_id
        or canonical_payload_hash(manifest.to_payload()) != storage.binding.manifest_hash
    ):
        raise ValueError("mock clock manifest does not match storage binding")
    matrix_binding = manifest.run_spec.get("mock_matrix_binding")
    if matrix_binding is not None:
        if not isinstance(matrix_binding, Mapping):
            raise TypeError("mock matrix clock binding must be a mapping")
        clock_id, clock_hash = mock_clock_sequence_binding(scale_case)
        if (
            matrix_binding.get("clock_sequence_id") != clock_id
            or matrix_binding.get("clock_sequence_hash") != clock_hash
        ):
            raise ValueError("scale case clock does not match frozen manifest clock binding")
    start = datetime.fromisoformat(scale_case.mock_clock_start.replace("Z", "+00:00"))
    step_seconds = scale_case.mock_clock_step_seconds
    observed_indexes: list[int] = []

    def observe(value: str) -> None:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        delta = (parsed - start).total_seconds()
        if delta < 0 or delta % step_seconds != 0:
            raise ValueError("durable mock timestamp is outside the frozen clock sequence")
        observed_indexes.append(int(delta // step_seconds))

    journal = storage.current_event_journal()
    ordinals = set(range(storage.progress.next_event_ordinal))
    if journal.event_ordinal is not None:
        ordinals.add(journal.event_ordinal)
    for ordinal in sorted(ordinals):
        event_id = derive_event_id(storage.binding.run_id, ordinal)
        for attempt in storage.attempts_for_event(event_id):
            if attempt.started_at is not None:
                observe(attempt.started_at)
            if attempt.finished_at is not None:
                observe(attempt.finished_at)
            invocation = storage.invocation_evidence(attempt.attempt_id)
            if invocation is not None:
                observe(invocation.execution_payload["started_at"])  # type: ignore[arg-type]
                observe(invocation.execution_payload["finished_at"])  # type: ignore[arg-type]
    for failure in storage.terminal_failure_evidence_prefix():
        observe(failure.recorded_at)
    if journal.latest_transition is not None:
        transition = journal.latest_transition
        if transition.started_at is not None:
            observe(transition.started_at)
        current_invocation = storage.invocation_evidence(transition.attempt_id)
        if current_invocation is not None:
            observe(current_invocation.execution_payload["started_at"])  # type: ignore[arg-type]
            observe(current_invocation.execution_payload["finished_at"])  # type: ignore[arg-type]
    if reconciliation is not None:
        observe(reconciliation.evidence.started_at)
        observe(reconciliation.evidence.finished_at)
    replay_values: tuple[str, ...] = ()
    if (
        journal.resume_state == "in_progress_requires_provider_reconciliation"
        and journal.latest_transition is not None
        and journal.latest_transition.started_at is not None
    ):
        replay_values = (journal.latest_transition.started_at,)
    return MockClockLedger(
        scale_case=scale_case,
        replay_values=replay_values,
        next_sequence_index=0 if not observed_indexes else max(observed_indexes) + 1,
    )


def explicit_success_invocations(
    fixture: MatrixCellFixture,
    *,
    start: int,
    stop: int,
    feed_capacity: int,
    memory_window: int,
) -> tuple[MockEventInvocation, ...]:
    """Build an explicit mock success ledger without seed-pairing authority."""

    if type(start) is not int or type(stop) is not int or not 0 <= start <= stop:
        raise ValueError("mock invocation bounds must be strict ordered integers")
    if start == stop:
        return ()
    all_event_ids = tuple(
        derive_event_id(fixture.storage.binding.run_id, ordinal)
        for ordinal in range(fixture.storage.progress.expected_event_count)
    )
    adapter = MockAdapter(
        script={
            event_id: (
                MockScriptStep.success(
                    {
                        "stance": fixture.stance_label,
                        "confidence": 3,
                        "public_reason": f"mock matrix event {ordinal}",
                    }
                ),
            )
            for ordinal, event_id in enumerate(all_event_ids)
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    values = []
    for ordinal in range(start, stop):
        event_id = all_event_ids[ordinal]
        values.append(
            MockEventInvocation(
                event_ordinal=ordinal,
                event_id=event_id,
                feed_capacity=feed_capacity,
                memory_window=memory_window,
                parser_limits=fixture.parser_limits,
                prompt_limits=fixture.prompt_limits,
                policy=fixture.policy,
                model_identity=adapter.execution_binding().model_identity,
                request_parameters=fixture.request_parameters,
                model_seed=10_000 + ordinal,
                adapter=adapter,
                reconciliation=None,
                http_status=fixture.http_status,
                usage=fixture.usage,
                finish_reason=fixture.finish_reason,
            )
        )
    return tuple(values)


def _mock_limits() -> tuple[ParserLimits, PromptLimits]:
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


def _artifact_hashes(family: MockArtifactFamily) -> dict[str, str]:
    artifacts = (
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
    return {
        family.topic_package.topic_id: family.topic_package.package_hash,
        **{artifact.artifact_id: artifact.output_hash for artifact in artifacts},
    }


def _cell_exposure_wiring(
    family: MockArtifactFamily, cell_id: str
) -> tuple[
    str,
    ArtifactEnvelope | None,
    ArtifactEnvelope | None,
    ArtifactEnvelope | None,
    ArtifactEnvelope | None,
    dict[str, tuple[str, ...]],
]:
    exposure_token = cell_id.rsplit("-", 1)[-1]
    roster = tuple(record["agent_id"] for record in family.population_artifact.payload["members"])
    if exposure_token == "E0":
        return "self_history_only", None, None, None, None, {agent: () for agent in roster}
    graph = family.shadow_artifact if exposure_token == "E1" else family.ws_artifact
    source_ws = family.ws_artifact if exposure_token == "E1" else None
    assignments = family.agent_node_mapping.payload["assignments"]
    agent_by_node = {record["node_id"]: record["agent_id"] for record in assignments}
    neighbor_sets = {agent: set() for agent in roster}
    for left, right in graph.payload["edges"]:
        left_agent = agent_by_node[left]
        right_agent = agent_by_node[right]
        neighbor_sets[left_agent].add(right_agent)
        neighbor_sets[right_agent].add(left_agent)
    neighbors = {agent: tuple(sorted(values)) for agent, values in neighbor_sets.items()}
    return (
        "shuffled_social" if exposure_token == "E1" else "ws_neighbors",
        graph,
        source_ws,
        family.agent_node_mapping,
        family.initial_reason_artifact,
        neighbors,
    )


def _initialize_mock_cell(
    storage: RunStorage, family: MockArtifactFamily, *, matched_seed: int
) -> None:
    round0 = {
        record["agent_id"]: record
        for record in family.initial_reason_artifact.payload["round0_records"]
    }
    with storage.acquire_run_lease():
        for agent_id in storage.binding.expected_agent_ids:
            record = round0[agent_id]
            stance = record["private_state"]["stance"]
            update = PrivateUpdate.create(
                topic_package=family.topic_package,
                matched_seed=matched_seed,
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
                matched_seed=matched_seed,
                receiver_agent_id=agent_id,
                exposure_mode=storage.binding.expected_exposure_mode,
                exposure_graph_hash=storage.binding.expected_exposure_graph_hash,
                mock_only=True,
            )
            storage.initialize_agent(update, state, post, pointer, cursor)
        storage.seal_initial_state()


def _bind_cell(
    *,
    matrix_fixture: MockMatrixFixture,
    cell_id: str,
    database_path: Path,
    storage: RunStorage,
    clock: Callable[[], str],
) -> BoundMockMatrixCell:
    family = matrix_fixture.family
    matrix_cell = next(cell for cell in matrix_fixture.matrix.cells if cell.cell_id == cell_id)
    mode, graph, source_ws, mapping, round0, neighbors = _cell_exposure_wiring(family, cell_id)
    if storage.binding.expected_exposure_mode != mode:
        raise ValueError("opened storage exposure mode differs from requested matrix cell")
    parser_limits, prompt_limits = _mock_limits()
    policy = MockAttemptPolicyBinding.create(
        allowed_difference_fields=("model_seed", "request_parameters.temperature"),
        mock_only=True,
        formal_eligible=False,
    )
    pipeline = MockEventPipeline(
        storage=storage,
        manifest=matrix_cell.manifest,
        topic_package=family.topic_package,
        persona_template=family.persona_template,
        population_artifact=family.population_artifact,
        exposure_graph_artifact=graph,
        source_ws_artifact=source_ws,
        agent_node_mapping_artifact=mapping,
        round0_initialization_artifact=round0,
        frozen_neighbor_agent_ids=neighbors,
        clock=clock,
    )
    return BoundMockMatrixCell(
        matrix_fixture=matrix_fixture,
        cell=MatrixCellFixture(
            pipeline=pipeline,
            storage=storage,
            parser_limits=parser_limits,
            prompt_limits=prompt_limits,
            policy=policy,
            model_identity=matrix_cell.adapter_binding.model_identity,
            request_parameters={"temperature": 0.0},
            http_status=200,
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            finish_reason="stop",
            stance_label=family.topic_package.stance_labels[3],
        ),
        cell_id=cell_id,
        database_path=database_path,
        manifest=matrix_cell.manifest,
        exposure_graph_artifact=graph,
        source_ws_artifact=source_ws,
        agent_node_mapping_artifact=mapping,
        round0_initialization_artifact=round0,
        frozen_neighbor_agent_ids=neighbors,
    )


def create_mock_matrix_cell(
    root: Path, *, matrix_fixture: MockMatrixFixture, cell_id: str
) -> BoundMockMatrixCell:
    """Create and initialize one real SQLite-backed canonical mock matrix cell."""

    root.mkdir(parents=True, exist_ok=True)
    family = matrix_fixture.family
    matrix_cell = next(cell for cell in matrix_fixture.matrix.cells if cell.cell_id == cell_id)
    mode, graph, source_ws, _, _, _ = _cell_exposure_wiring(family, cell_id)
    database_path = root / f"{cell_id}.sqlite"
    storage = RunStorage.create(
        database_path,
        manifest=matrix_cell.manifest,
        artifact_hashes=_artifact_hashes(family),
        expected_agent_ids=tuple(
            record["agent_id"] for record in family.population_artifact.payload["members"]
        ),
        expected_exposure_mode=mode,
        expected_exposure_graph_hash=None if graph is None else graph.output_hash,
        expected_exposure_graph_artifact=graph,
        expected_source_ws_artifact=source_ws,
    )
    _initialize_mock_cell(storage, family, matched_seed=matrix_cell.manifest.matched_seed)
    clock = MockClockLedger(
        scale_case=matrix_fixture.scale_case, replay_values=(), next_sequence_index=0
    )
    return _bind_cell(
        matrix_fixture=matrix_fixture,
        cell_id=cell_id,
        database_path=database_path,
        storage=storage,
        clock=clock,
    )


def reopen_mock_matrix_cell(
    fixture: BoundMockMatrixCell,
    *,
    reconciliation: AttemptInvocationResult | None,
) -> BoundMockMatrixCell:
    """Close/open a durable cell and rebuild its clock from public evidence."""

    binding = fixture.cell.storage.binding
    fixture.cell.storage.close()
    storage = RunStorage.open(
        fixture.database_path,
        manifest=fixture.manifest,
        artifact_hashes=dict(binding.artifact_hashes),
        expected_agent_ids=binding.expected_agent_ids,
        expected_exposure_mode=binding.expected_exposure_mode,
        expected_exposure_graph_hash=binding.expected_exposure_graph_hash,
        expected_exposure_graph_artifact=fixture.exposure_graph_artifact,
        expected_source_ws_artifact=fixture.source_ws_artifact,
    )
    clock = rebuild_mock_clock_ledger(
        scale_case=fixture.matrix_fixture.scale_case,
        storage=storage,
        manifest=fixture.manifest,
        reconciliation=reconciliation,
    )
    return _bind_cell(
        matrix_fixture=fixture.matrix_fixture,
        cell_id=fixture.cell_id,
        database_path=fixture.database_path,
        storage=storage,
        clock=clock,
    )


def _manifest(
    *,
    cell_id: str,
    matched_seed: int,
    schedule: FrozenSchedule,
    location: Path,
    mock_matrix_binding: Mapping[str, object],
    launch_nonce_namespace: str,
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
    launch_nonce = f"{launch_nonce_namespace}-{cell_id.lower()}"
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
            "runtime": "1.0.0",
            "mode": "script_only_no_generation",
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


def _build_mock_artifact_family(
    *,
    n: int,
    sweeps: int,
    matched_seed: int,
    explicit_steps_by_ordinal: tuple[tuple[MockScriptStep, ...], ...] | None,
    launch_nonce_namespace: str,
) -> MockArtifactFamily:
    frame = _load_envelope("mock_population_frame.artifact.json")
    reasons = _load_envelope("mock_reason_library.artifact.json")
    topic_artifact = _load_envelope("mock_topic_package.artifact.json")
    persona_fixture = _load_envelope("mock_persona_template.artifact.json")
    persona_template = ArtifactEnvelope.create(
        artifact_type=persona_fixture.artifact_type,
        schema_version=persona_fixture.schema_version,
        algorithm_id=persona_fixture.algorithm_id,
        algorithm_version=persona_fixture.algorithm_version,
        input_hashes={"fixture": persona_fixture.output_hash},
        payload=persona_fixture.payload,
        rng_provenance=(),
    )
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
    steps_by_ordinal = (
        tuple(
            (
                MockScriptStep.success(
                    {
                        "stance": topic_package.stance_labels[3],
                        "confidence": 3,
                        "public_reason": f"mock matrix event {ordinal}",
                    }
                ),
            )
            for ordinal in range(schedule.count)
        )
        if explicit_steps_by_ordinal is None
        else explicit_steps_by_ordinal
    )
    if len(steps_by_ordinal) != schedule.count or any(not steps for steps in steps_by_ordinal):
        raise ValueError("explicit mock scripts must exact-cover every schedule ordinal")
    semantic_event_ids = tuple(f"semantic-event-{ordinal}" for ordinal in range(schedule.count))
    semantic_adapter = MockAdapter(
        script={
            event_id: steps_by_ordinal[ordinal]
            for ordinal, event_id in enumerate(semantic_event_ids)
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    adapter_semantics_hash = mock_adapter_semantics_hash(
        semantic_adapter.execution_binding(), semantic_event_ids
    )
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
    clock_id, clock_hash = mock_clock_sequence_binding(scale_case)
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
            launch_nonce_namespace=launch_nonce_namespace,
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
                "clock_sequence_id": clock_id,
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


def build_mock_artifact_family(*, n: int, sweeps: int, matched_seed: int) -> MockArtifactFamily:
    return _build_mock_artifact_family(
        n=n,
        sweeps=sweeps,
        matched_seed=matched_seed,
        explicit_steps_by_ordinal=None,
        launch_nonce_namespace="mock-matrix",
    )


def _assemble_matrix_fixture(
    *, scale_case: MockScaleCase, family: MockArtifactFamily
) -> MockMatrixFixture:
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

    return MockMatrixFixture(scale_case=scale_case, family=family, matrix=matrix, clock=clock)


def build_mock_matrix_fixture(tmp_path: Path, *, case_id: str, sweeps: int) -> MockMatrixFixture:
    cases = load_mock_scale_cases(_load_envelope("mock_scale_cases.artifact.json"))
    scale_case = next(case for case in cases if case.case_id == case_id)
    namespace = (
        "mock-matrix-"
        + canonical_payload_hash({"fixture_root": tmp_path.resolve(strict=False).as_posix()})[:16]
    )
    family = _build_mock_artifact_family(
        n=scale_case.population_size,
        sweeps=sweeps,
        matched_seed=101,
        explicit_steps_by_ordinal=None,
        launch_nonce_namespace=namespace,
    )
    return _assemble_matrix_fixture(scale_case=scale_case, family=family)


def build_mock_matrix_fixture_with_steps(
    tmp_path: Path,
    *,
    case_id: str,
    sweeps: int,
    steps_by_ordinal: tuple[tuple[MockScriptStep, ...], ...],
) -> MockMatrixFixture:
    """Build an explicit failure-script matrix without weakening production validation."""

    cases = load_mock_scale_cases(_load_envelope("mock_scale_cases.artifact.json"))
    scale_case = next(case for case in cases if case.case_id == case_id)
    family = _build_mock_artifact_family(
        n=scale_case.population_size,
        sweeps=sweeps,
        matched_seed=101,
        explicit_steps_by_ordinal=steps_by_ordinal,
        launch_nonce_namespace=(
            "mock-matrix-"
            + canonical_payload_hash({"fixture_root": tmp_path.resolve(strict=False).as_posix()})[
                :16
            ]
        ),
    )
    return _assemble_matrix_fixture(scale_case=scale_case, family=family)
