"""Diagnostic Phase 0B matrix binding for the N=20/T=2 fast track."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Mapping, Sequence

from ..artifacts import ArtifactEnvelope
from ..domain import FrozenSchedule, RunManifest, _json_ready, canonical_payload_hash
from ..execution_evidence import MockAdapterExecutionBinding
from ..feed import FeedCursor
from ..initialization import assign_initial_reasons, assign_initial_stances
from ..mock_matrix import (
    CANONICAL_CELL_IDS,
    MockMatchedSeedMatrix,
    MockScaleCase,
    build_mock_matched_seed_matrix,
    validate_mock_matched_seed_matrix,
)
from ..network import (
    build_agent_node_mapping,
    build_shadow_artifact,
    build_structural_gate_artifact,
    build_ws_artifact,
)
from ..persona import render_persona, validate_persona_factor_diff
from ..population import build_population_artifact
from ..schedule import (
    build_activation_schedule,
    build_attention_artifact,
    build_expression_artifact,
    build_publish_schedule,
)
from ..state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from ..storage import RunStorage
from ..topic import TopicPackage
from .contracts import DiagnosticAdapterBinding, DiagnosticRunAuthorization


_DIAGNOSTIC_MATRIX_SCHEMA = "paper1.phase0b.diagnostic-n20-t2-matrix.v1"
_AUTHORIZATION_ARTIFACT_KEYS = frozenset(
    {
        "topic",
        "population",
        "persona",
        "network",
        "shadow",
        "mapping",
        "attention",
        "expression",
        "activation",
        "publish",
        "schedule",
    }
)


def _strict_hash_mapping(value: Mapping[str, object]) -> dict[str, str]:
    if type(value) is not dict or set(value) != _AUTHORIZATION_ARTIFACT_KEYS:
        raise ValueError("diagnostic matrix artifact hashes must exactly match authorization keys")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if (
            type(item) is not str
            or len(item) != 64
            or any(ch not in "0123456789abcdef" for ch in item)
        ):
            raise ValueError(f"diagnostic matrix artifact hash {key} must be lowercase sha256")
        normalized[key] = item
    return normalized


def _content_payload(value: object) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in fields(value)  # type: ignore[arg-type]
        if field.name not in {"matrix", "record_hash"}
    }


@dataclass(frozen=True, slots=True)
class DiagnosticMatrixCandidate:
    """Outcome-free binding between synthetic Phase 4B inputs and a real-Qwen diagnostic."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    input_artifact_mode: str
    agent_count: int
    sweep_count: int
    matched_seed: int
    cell_ids: tuple[str, ...]
    expected_event_count: int
    max_transport_count: int
    authorization_artifact_hashes: Mapping[str, str]
    matrix_hash: str
    matrix: MockMatchedSeedMatrix
    record_hash: str

    _SCHEMA: ClassVar[str] = _DIAGNOSTIC_MATRIX_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA:
            raise ValueError("diagnostic matrix schema is unsupported")
        if self.calibration_only is not True or type(self.calibration_only) is not bool:
            raise ValueError("diagnostic matrix must remain calibration_only=true")
        if (
            self.formal_parameter_authority is not False
            or type(self.formal_parameter_authority) is not bool
        ):
            raise ValueError("diagnostic matrix must not grant formal parameter authority")
        if self.research_parameter_status != "not_frozen":
            raise ValueError("diagnostic matrix must remain not_frozen")
        if self.input_artifact_mode != "synthetic_phase4b_candidate":
            raise ValueError("diagnostic matrix inputs must remain synthetic candidates")
        if type(self.agent_count) is not int or self.agent_count != 20:
            raise ValueError("diagnostic matrix requires exactly 20 agents")
        if type(self.sweep_count) is not int or self.sweep_count != 2:
            raise ValueError("diagnostic matrix requires exactly 2 sweeps")
        if type(self.matched_seed) is not int:
            raise TypeError("diagnostic matrix matched seed must be a strict integer")
        if self.cell_ids != CANONICAL_CELL_IDS:
            raise ValueError("diagnostic matrix cells must be the canonical exact cover")
        if self.expected_event_count != 480:
            raise ValueError("diagnostic matrix requires exactly 480 logical events")
        if self.max_transport_count != 960:
            raise ValueError("diagnostic matrix hard ceiling must be 960 transports")
        validate_mock_matched_seed_matrix(self.matrix)
        if self.matrix.matched_seed != self.matched_seed:
            raise ValueError("diagnostic matrix matched seed drifted")
        if self.matrix.scale_case.population_size != self.agent_count:
            raise ValueError("diagnostic matrix population drifted from N=20")
        if self.matrix.scale_case.recovery_sweeps != self.sweep_count:
            raise ValueError("diagnostic matrix sweep count drifted from T=2")
        event_count = sum(cell.manifest.schedule.count for cell in self.matrix.cells)
        if event_count != self.expected_event_count:
            raise ValueError("diagnostic matrix event inventory is not 480")
        if self.matrix_hash != self.matrix.matrix_hash:
            raise ValueError("diagnostic matrix hash does not bind the matrix payload")
        hashes = _strict_hash_mapping(self.authorization_artifact_hashes)
        object.__setattr__(self, "authorization_artifact_hashes", hashes)
        expected_hashes = self.matrix.cells[0].artifact_hashes
        mapped = {
            "topic": expected_hashes["topic"],
            "population": expected_hashes["population"],
            "persona": expected_hashes["persona_template"],
            "network": expected_hashes["ws"],
            "shadow": expected_hashes["shadow"],
            "mapping": expected_hashes["mapping"],
            "attention": expected_hashes["attention"],
            "expression": expected_hashes["expression"],
            "activation": expected_hashes["activation"],
            "publish": expected_hashes["publish"],
            "schedule": expected_hashes["schedule"],
        }
        if hashes != mapped:
            raise ValueError("diagnostic matrix artifact hashes drifted from the validated matrix")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("diagnostic matrix record_hash does not match content")

    def content_payload(self) -> dict[str, object]:
        return _json_ready(_content_payload(self))

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})


def build_diagnostic_n20_matrix_candidate(
    *,
    scale_case: MockScaleCase,
    matched_seed: int,
    topic_package: TopicPackage,
    population_artifact: ArtifactEnvelope,
    initial_stance_artifact: ArtifactEnvelope,
    initial_reason_artifact: ArtifactEnvelope,
    persona_template: ArtifactEnvelope,
    ws_artifact: ArtifactEnvelope,
    shadow_artifact: ArtifactEnvelope,
    agent_node_mapping: ArtifactEnvelope,
    structural_gate_artifact: ArtifactEnvelope,
    attention_artifact: ArtifactEnvelope,
    expression_artifact: ArtifactEnvelope,
    activation_artifact: ArtifactEnvelope,
    publish_artifact: ArtifactEnvelope,
    schedules_by_cell: Mapping[str, FrozenSchedule],
    manifests_by_cell: Mapping[str, RunManifest],
    adapter_bindings_by_cell: Mapping[str, MockAdapterExecutionBinding],
) -> DiagnosticMatrixCandidate:
    """Build the outcome-free N=20/T=2 diagnostic matrix candidate."""

    matrix = build_mock_matched_seed_matrix(
        scale_case=scale_case,
        matched_seed=matched_seed,
        topic_package=topic_package,
        population_artifact=population_artifact,
        initial_stance_artifact=initial_stance_artifact,
        initial_reason_artifact=initial_reason_artifact,
        persona_template=persona_template,
        ws_artifact=ws_artifact,
        shadow_artifact=shadow_artifact,
        agent_node_mapping=agent_node_mapping,
        structural_gate_artifact=structural_gate_artifact,
        attention_artifact=attention_artifact,
        expression_artifact=expression_artifact,
        activation_artifact=activation_artifact,
        publish_artifact=publish_artifact,
        schedules_by_cell=schedules_by_cell,
        manifests_by_cell=manifests_by_cell,
        adapter_bindings_by_cell=adapter_bindings_by_cell,
    )
    matrix_hash = matrix.matrix_hash
    source_hashes = matrix.cells[0].artifact_hashes
    authorization_hashes = {
        "topic": source_hashes["topic"],
        "population": source_hashes["population"],
        "persona": source_hashes["persona_template"],
        "network": source_hashes["ws"],
        "shadow": source_hashes["shadow"],
        "mapping": source_hashes["mapping"],
        "attention": source_hashes["attention"],
        "expression": source_hashes["expression"],
        "activation": source_hashes["activation"],
        "publish": source_hashes["publish"],
        "schedule": source_hashes["schedule"],
    }
    content: dict[str, object] = {
        "schema_version": _DIAGNOSTIC_MATRIX_SCHEMA,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "input_artifact_mode": "synthetic_phase4b_candidate",
        "agent_count": 20,
        "sweep_count": 2,
        "matched_seed": matched_seed,
        "cell_ids": CANONICAL_CELL_IDS,
        "expected_event_count": 480,
        "max_transport_count": 960,
        "authorization_artifact_hashes": authorization_hashes,
        "matrix_hash": matrix_hash,
    }
    return DiagnosticMatrixCandidate(
        **content,
        matrix=matrix,
        record_hash=canonical_payload_hash(_json_ready(content)),
    )  # type: ignore[arg-type]


def _reject_unresolved(value: object, name: str) -> None:
    if isinstance(value, str):
        if "UNRESOLVED[" in value:
            raise ValueError(f"{name} candidate must not contain UNRESOLVED markers")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_unresolved(item, f"{name}.{key}")
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _reject_unresolved(item, f"{name}[{index}]")


def _candidate_metadata(
    *,
    calibration_only: bool,
    formal_parameter_authority: bool,
    research_parameter_status: str,
) -> None:
    if calibration_only is not True or type(calibration_only) is not bool:
        raise ValueError("diagnostic artifact family must remain calibration_only=true")
    if formal_parameter_authority is not False or type(formal_parameter_authority) is not bool:
        raise ValueError("diagnostic artifact family cannot grant formal parameter authority")
    if research_parameter_status != "not_frozen":
        raise ValueError("diagnostic artifact family must remain not_frozen")


@dataclass(frozen=True, slots=True)
class DiagnosticN20ArtifactFamily:
    """One explicit synthetic candidate family shared by all twelve diagnostic cells."""

    matched_seed: int
    agent_count: int
    sweep_count: int
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
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
    schedule: FrozenSchedule
    agent_ids: tuple[str, ...]
    authorization_artifact_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        _candidate_metadata(
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
            research_parameter_status=self.research_parameter_status,
        )
        if type(self.matched_seed) is not int:
            raise TypeError("matched_seed must be a strict integer")
        if self.agent_count != 20 or self.sweep_count != 2:
            raise ValueError("diagnostic artifact family requires exactly N=20/T=2")
        if (
            self.schedule.population_size != 20
            or self.schedule.sweep_count != 2
            or self.schedule.count != 40
        ):
            raise ValueError("diagnostic schedule must contain exactly 40 N=20/T=2 events")
        if len(self.agent_ids) != 20 or len(set(self.agent_ids)) != 20:
            raise ValueError("diagnostic artifact family requires 20 unique agents")
        if any(slot.agent_id not in self.agent_ids for slot in self.schedule.slots):
            raise ValueError("diagnostic schedule contains an unknown agent")
        hashes = _strict_hash_mapping(self.authorization_artifact_hashes)
        expected_hashes = {
            "topic": self.topic_package.package_hash,
            "population": self.population_artifact.output_hash,
            "persona": self.persona_template.output_hash,
            "network": self.ws_artifact.output_hash,
            "shadow": self.shadow_artifact.output_hash,
            "mapping": self.agent_node_mapping.output_hash,
            "attention": self.attention_artifact.output_hash,
            "expression": self.expression_artifact.output_hash,
            "activation": self.activation_artifact.output_hash,
            "publish": self.publish_artifact.output_hash,
            "schedule": self.schedule.schedule_hash,
        }
        if hashes != expected_hashes:
            raise ValueError("diagnostic authorization hashes drift from the artifact family")
        object.__setattr__(self, "authorization_artifact_hashes", MappingProxyType(hashes))


@dataclass(frozen=True, slots=True)
class DiagnosticCellInputBundle:
    """Provider-ready inputs for one cell, without invoking a provider."""

    cell_id: str
    identity_present: bool
    continuity_present: bool
    exposure_mode: str
    exposure_graph_artifact: ArtifactEnvelope | None
    source_ws_artifact: ArtifactEnvelope | None
    agent_node_mapping_artifact: ArtifactEnvelope | None
    round0_initialization_artifact: ArtifactEnvelope | None
    frozen_neighbor_agent_ids: Mapping[str, tuple[str, ...]]
    rendered_personas: Mapping[str, ArtifactEnvelope]
    manifest: RunManifest

    def __post_init__(self) -> None:
        if self.cell_id not in CANONICAL_CELL_IDS:
            raise ValueError("diagnostic cell ID is not canonical")
        if type(self.identity_present) is not bool or type(self.continuity_present) is not bool:
            raise TypeError("diagnostic persona factors must be booleans")
        expected_mode = {
            "E0": "self_history_only",
            "E1": "shuffled_social",
            "E2": "ws_neighbors",
        }[self.cell_id.rsplit("-", 1)[-1]]
        if self.exposure_mode != expected_mode:
            raise ValueError("diagnostic exposure mode drifts from cell identity")
        object.__setattr__(
            self,
            "frozen_neighbor_agent_ids",
            MappingProxyType(dict(self.frozen_neighbor_agent_ids)),
        )
        object.__setattr__(
            self, "rendered_personas", MappingProxyType(dict(self.rendered_personas))
        )


@dataclass(frozen=True, slots=True)
class DiagnosticN20MaterializedMatrix:
    family: DiagnosticN20ArtifactFamily
    authorization_hash: str
    adapter_binding_hash: str
    cells: tuple[DiagnosticCellInputBundle, ...]
    matrix_hash: str

    def __post_init__(self) -> None:
        if tuple(cell.cell_id for cell in self.cells) != CANONICAL_CELL_IDS:
            raise ValueError("materialized matrix must exact-cover canonical cells")
        if sum(cell.manifest.schedule.count for cell in self.cells) != 480:
            raise ValueError("materialized matrix must contain exactly 480 logical events")


def build_diagnostic_n20_artifact_family(
    *,
    matched_seed: int,
    population_frame_artifact: ArtifactEnvelope,
    population_weights: Sequence[float],
    population_constraints: Mapping[str, object],
    population_tolerance: int,
    topic_package: TopicPackage,
    reason_library_artifact: ArtifactEnvelope,
    persona_template: ArtifactEnvelope,
    stance_orthogonal_fields: tuple[str, ...],
    stance_max_category_imbalance: float,
    ws_k: int,
    ws_rewire_probability: float,
    shadow_max_attempts: int,
    shadow_trial_budget_per_edge: int,
    structural_null_replicates: int,
    attention_family: str,
    attention_parameters: Mapping[str, object],
    structural_lurker_probability: float,
    expression_beta_alpha: float,
    expression_beta_beta: float,
    expression_max_beta_attempts_per_agent: int,
    expression_correlation_mode: str,
    sweep_count: int,
    calibration_only: bool,
    formal_parameter_authority: bool,
    research_parameter_status: str,
) -> DiagnosticN20ArtifactFamily:
    """Build all synthetic N=20/T=2 candidate artifacts from explicit inputs."""

    _candidate_metadata(
        calibration_only=calibration_only,
        formal_parameter_authority=formal_parameter_authority,
        research_parameter_status=research_parameter_status,
    )
    if sweep_count != 2:
        raise ValueError("diagnostic artifact family requires exactly two sweeps")
    explicit_candidates = {
        "population_weights": tuple(population_weights),
        "population_constraints": population_constraints,
        "stance_orthogonal_fields": stance_orthogonal_fields,
        "ws_k": ws_k,
        "ws_rewire_probability": ws_rewire_probability,
        "attention_family": attention_family,
        "attention_parameters": attention_parameters,
        "structural_lurker_probability": structural_lurker_probability,
        "expression_beta_alpha": expression_beta_alpha,
        "expression_beta_beta": expression_beta_beta,
        "expression_correlation_mode": expression_correlation_mode,
    }
    _reject_unresolved(explicit_candidates, "diagnostic")
    if not isinstance(population_frame_artifact.payload, Mapping):
        raise TypeError("population frame payload must be a mapping")
    donors = population_frame_artifact.payload.get("donors")
    if not isinstance(donors, tuple):
        raise ValueError("population frame must provide a typed donor tuple")
    population = build_population_artifact(
        donors=donors,
        weights=population_weights,
        n=20,
        matched_seed=matched_seed,
        input_artifact_hash=population_frame_artifact.output_hash,
        constraints=population_constraints,
        tolerance=population_tolerance,
        mock_only=True,
    )
    stances = assign_initial_stances(
        population_artifact=population,
        matched_seed=matched_seed,
        orthogonal_fields=stance_orthogonal_fields,
        max_category_imbalance=stance_max_category_imbalance,
        mock_only=True,
    )
    round0 = assign_initial_reasons(
        stance_artifact=stances,
        reason_library_artifact=reason_library_artifact,
        matched_seed=matched_seed,
        mock_only=True,
    )
    ws = build_ws_artifact(
        n=20, k=ws_k, p=ws_rewire_probability, matched_seed=matched_seed, mock_only=True
    )
    shadow = build_shadow_artifact(
        ws,
        matched_seed=matched_seed,
        max_attempts=shadow_max_attempts,
        trial_budget_per_edge=shadow_trial_budget_per_edge,
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
        ws,
        matched_seed=matched_seed,
        random_null_replicates=structural_null_replicates,
        mock_only=True,
    )
    members = population.payload["members"]
    assert isinstance(members, tuple)
    agent_ids = tuple(member["agent_id"] for member in members)
    attention = build_attention_artifact(
        agent_ids=agent_ids,
        matched_seed=matched_seed,
        family=attention_family,
        parameters=attention_parameters,
        mock_only=True,
    )
    expression = build_expression_artifact(
        agent_ids=agent_ids,
        matched_seed=matched_seed,
        structural_lurker_probability=structural_lurker_probability,
        beta_alpha=expression_beta_alpha,
        beta_beta=expression_beta_beta,
        max_beta_attempts_per_agent=expression_max_beta_attempts_per_agent,
        correlation_mode=expression_correlation_mode,
        mock_only=True,
    )
    activation = build_activation_schedule(
        attention, matched_seed=matched_seed, sweep_count=2, mock_only=True
    )
    publish = build_publish_schedule(
        attention, activation, expression, matched_seed=matched_seed, mock_only=True
    )
    schedule = FrozenSchedule.from_payload(
        publish.to_payload()["payload"]["frozen_schedule"]  # type: ignore[index]
    )
    hashes = {
        "topic": topic_package.package_hash,
        "population": population.output_hash,
        "persona": persona_template.output_hash,
        "network": ws.output_hash,
        "shadow": shadow.output_hash,
        "mapping": mapping.output_hash,
        "attention": attention.output_hash,
        "expression": expression.output_hash,
        "activation": activation.output_hash,
        "publish": publish.output_hash,
        "schedule": schedule.schedule_hash,
    }
    return DiagnosticN20ArtifactFamily(
        matched_seed=matched_seed,
        agent_count=20,
        sweep_count=2,
        calibration_only=True,
        formal_parameter_authority=False,
        research_parameter_status="not_frozen",
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
        schedule=schedule,
        agent_ids=agent_ids,
        authorization_artifact_hashes=hashes,
    )


def _exposure_wiring(
    family: DiagnosticN20ArtifactFamily, cell_id: str
) -> tuple[
    str,
    ArtifactEnvelope | None,
    ArtifactEnvelope | None,
    ArtifactEnvelope | None,
    ArtifactEnvelope | None,
    dict[str, tuple[str, ...]],
]:
    exposure = cell_id.rsplit("-", 1)[-1]
    if exposure == "E0":
        return (
            "self_history_only",
            None,
            None,
            None,
            None,
            {agent_id: () for agent_id in family.agent_ids},
        )
    graph = family.shadow_artifact if exposure == "E1" else family.ws_artifact
    assignments = family.agent_node_mapping.payload["assignments"]
    agent_by_node = {record["node_id"]: record["agent_id"] for record in assignments}  # type: ignore[index,union-attr]
    neighbor_sets = {agent_id: set() for agent_id in family.agent_ids}
    for left, right in graph.payload["edges"]:  # type: ignore[union-attr]
        left_agent = agent_by_node[left]
        right_agent = agent_by_node[right]
        neighbor_sets[left_agent].add(right_agent)
        neighbor_sets[right_agent].add(left_agent)
    neighbors = {key: tuple(sorted(values)) for key, values in neighbor_sets.items()}
    return (
        "shuffled_social" if exposure == "E1" else "ws_neighbors",
        graph,
        family.ws_artifact if exposure == "E1" else None,
        family.agent_node_mapping,
        family.initial_reason_artifact,
        neighbors,
    )


def _diagnostic_manifest(
    *,
    cell_id: str,
    family: DiagnosticN20ArtifactFamily,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    schedule_uri_root: Path,
    launch_nonce_namespace: str,
    started_at: str,
    environment: Mapping[str, str],
    exposure_mode: str,
    exposure_graph_hash: str | None,
) -> RunManifest:
    identity_token, continuity_token = cell_id.split("-")[1:3]
    run_spec = {
        "protocol_id": "paper1",
        "protocol_version": "phase0b-preliminary-diagnostic-v1",
        "protocol_hash": authorization.record_hash,
        "schedule_hash": family.schedule.schedule_hash,
        "cell_id": cell_id,
        "diagnostic_authorization_hash": authorization.record_hash,
        "adapter_binding_hash": adapter_binding.record_hash,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "input_artifact_mode": "synthetic_phase4b_candidate",
        "run_config": {
            "population": 20,
            "sweep_count": 2,
            "expected_event_count": 40,
        },
        "request_parameters": {
            "temperature": authorization.temperature,
            "top_p": authorization.top_p,
            "max_tokens": authorization.max_tokens,
            "enable_thinking": authorization.enable_thinking,
        },
        "cell_binding": {
            "identity_present": identity_token == "I1",
            "continuity_present": continuity_token == "C1",
            "exposure_mode": exposure_mode,
            "exposure_graph_hash": exposure_graph_hash,
            "artifact_hashes": dict(family.authorization_artifact_hashes),
        },
    }
    launch_nonce = f"{launch_nonce_namespace}-{cell_id.lower()}"
    from ..domain import EventStatus, derive_run_id

    run_id = derive_run_id(run_spec, family.matched_seed, launch_nonce)
    schedule_uri_root = schedule_uri_root.resolve(strict=False)
    return RunManifest(
        run_id=run_id,
        run_spec=run_spec,
        run_spec_hash=canonical_payload_hash(run_spec),
        matched_seed=family.matched_seed,
        launch_nonce=launch_nonce,
        protocol_id="paper1",
        protocol_version="phase0b-preliminary-diagnostic-v1",
        protocol_hash=authorization.record_hash,
        git_sha=authorization.source_commit,
        dirty=authorization.source_dirty,
        diff_hash=authorization.source_diff_hash,
        environment_lock_hash=adapter_binding.environment_lock_hash,
        model_identity={
            "provider": "vllm",
            "model": adapter_binding.model_repository,
            "revision": adapter_binding.model_revision,
            "runtime": adapter_binding.vllm_version,
            "mode": "real_qwen_non_thinking",
            "served_model_name": adapter_binding.served_model_name,
        },
        environment=environment,
        schedule_uri=(schedule_uri_root / f"{cell_id}.schedule.json").as_uri(),
        schedule=family.schedule,
        schedule_hash=family.schedule.schedule_hash,
        checkpoint_uri=None,
        checkpoint_hash=None,
        recovery_cursor=None,
        event_ids=(),
        terminal_counts={status.value: 0 for status in EventStatus},
        started_at=started_at,
        updated_at=started_at,
        archive={"status": "pending", "uri": None, "hash": None},
    )


def materialize_diagnostic_n20_matrix(
    *,
    family: DiagnosticN20ArtifactFamily,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    schedule_uri_root: Path,
    launch_nonce_namespace: str,
    started_at: str,
    environment: Mapping[str, str],
) -> DiagnosticN20MaterializedMatrix:
    """Bind one artifact family to twelve real-provider manifests and input bundles."""

    if authorization.artifact_hashes != family.authorization_artifact_hashes:
        raise ValueError("diagnostic authorization artifact hashes drift from artifact family")
    if authorization.matched_seed != family.matched_seed:
        raise ValueError("diagnostic authorization matched seed drifts from artifact family")
    if authorization.adapter_binding_hash != adapter_binding.record_hash:
        raise ValueError("diagnostic authorization adapter binding hash does not match")
    if not isinstance(environment, Mapping) or not {
        "python_version",
        "dependency_lock_hash",
        "platform",
    }.issubset(environment):
        raise ValueError("diagnostic environment must bind Python, dependency lock, and platform")
    _reject_unresolved(environment, "environment")
    members = family.population_artifact.payload["members"]
    assert isinstance(members, tuple)
    cells = []
    for cell_id in CANONICAL_CELL_IDS:
        _, identity_token, continuity_token, _ = cell_id.split("-")
        identity_present = identity_token == "I1"
        continuity_present = continuity_token == "C1"
        rendered = {
            member["agent_id"]: render_persona(
                family.persona_template,
                member,
                {
                    "identity_present": identity_present,
                    "continuity_present": continuity_present,
                },
            )
            for member in members
        }
        mode, graph, source_ws, mapping, round0, neighbors = _exposure_wiring(family, cell_id)
        cells.append(
            DiagnosticCellInputBundle(
                cell_id=cell_id,
                identity_present=identity_present,
                continuity_present=continuity_present,
                exposure_mode=mode,
                exposure_graph_artifact=graph,
                source_ws_artifact=source_ws,
                agent_node_mapping_artifact=mapping,
                round0_initialization_artifact=round0,
                frozen_neighbor_agent_ids=neighbors,
                rendered_personas=rendered,
                manifest=_diagnostic_manifest(
                    cell_id=cell_id,
                    family=family,
                    authorization=authorization,
                    adapter_binding=adapter_binding,
                    schedule_uri_root=schedule_uri_root,
                    launch_nonce_namespace=launch_nonce_namespace,
                    started_at=started_at,
                    environment=environment,
                    exposure_mode=mode,
                    exposure_graph_hash=None if graph is None else graph.output_hash,
                ),
            )
        )
    for member in members:
        validate_persona_factor_diff(
            tuple(
                render_persona(
                    family.persona_template,
                    member,
                    {"identity_present": identity, "continuity_present": continuity},
                )
                for identity in (False, True)
                for continuity in (False, True)
            )
        )
    hash_payload = {
        "authorization_hash": authorization.record_hash,
        "adapter_binding_hash": adapter_binding.record_hash,
        "cells": tuple(
            {
                "cell_id": cell.cell_id,
                "manifest_hash": canonical_payload_hash(cell.manifest.to_payload()),
                "persona_hashes": tuple(
                    (agent_id, persona.output_hash)
                    for agent_id, persona in cell.rendered_personas.items()
                ),
                "neighbor_wiring": tuple(cell.frozen_neighbor_agent_ids.items()),
            }
            for cell in cells
        ),
    }
    return DiagnosticN20MaterializedMatrix(
        family=family,
        authorization_hash=authorization.record_hash,
        adapter_binding_hash=adapter_binding.record_hash,
        cells=tuple(cells),
        matrix_hash=canonical_payload_hash(hash_payload),
    )


def _storage_artifact_hashes(family: DiagnosticN20ArtifactFamily) -> dict[str, str]:
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


def _initialize_round0(storage: RunStorage, family: DiagnosticN20ArtifactFamily) -> None:
    records = {
        record["agent_id"]: record
        for record in family.initial_reason_artifact.payload["round0_records"]  # type: ignore[union-attr]
    }
    with storage.acquire_run_lease():
        for agent_id in family.agent_ids:
            record = records[agent_id]
            private = record["private_state"]
            stance = private["stance"]
            update = PrivateUpdate.create(
                topic_package=family.topic_package,
                matched_seed=family.matched_seed,
                agent_id=agent_id,
                event_id=None,
                event_ordinal=None,
                sequence_index=0,
                stance_label=family.topic_package.stance_labels[stance - 1],
                reason=private["reason"],
                confidence=None,
                published=True,
                source_attempt_id=None,
                mock_only=True,
            )
            state = PrivateState.from_update(update, previous=None, mock_only=True)
            post = PublicPost.from_private_update(update, mock_only=True)
            pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
            cursor = FeedCursor.initial(
                matched_seed=family.matched_seed,
                receiver_agent_id=agent_id,
                exposure_mode=storage.binding.expected_exposure_mode,
                exposure_graph_hash=storage.binding.expected_exposure_graph_hash,
                mock_only=True,
            )
            storage.initialize_agent(update, state, post, pointer, cursor)
        storage.seal_initial_state()


def initialize_diagnostic_n20_stores(
    root: Path, *, matrix: DiagnosticN20MaterializedMatrix
) -> dict[str, RunStorage]:
    """Create twelve independent v6 stores and initialize all 20 round-zero agents."""

    root.mkdir(parents=True, exist_ok=True)
    stores: dict[str, RunStorage] = {}
    try:
        for cell in matrix.cells:
            path = root / f"{cell.cell_id}.sqlite"
            storage = RunStorage.create(
                path,
                manifest=cell.manifest,
                artifact_hashes=_storage_artifact_hashes(matrix.family),
                expected_agent_ids=matrix.family.agent_ids,
                expected_exposure_mode=cell.exposure_mode,
                expected_exposure_graph_hash=(
                    None
                    if cell.exposure_graph_artifact is None
                    else cell.exposure_graph_artifact.output_hash
                ),
                expected_exposure_graph_artifact=cell.exposure_graph_artifact,
                expected_source_ws_artifact=cell.source_ws_artifact,
            )
            stores[cell.cell_id] = storage
            _initialize_round0(storage, matrix.family)
    except BaseException:
        for storage in stores.values():
            storage.close()
        raise
    return stores
