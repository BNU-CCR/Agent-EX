from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.mock_matrix import CANONICAL_CELL_IDS, load_mock_scale_cases
from agent_ex.phase0b import build_diagnostic_n20_matrix_candidate
from agent_ex.phase0b.contracts import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
)
from agent_ex.phase0b.matrix import (
    build_diagnostic_n20_artifact_family,
    initialize_diagnostic_n20_stores,
    materialize_diagnostic_n20_matrix,
)
from agent_ex.phase0b.real_pipeline import (
    dispatch_real_diagnostic_event_once,
    finalize_real_diagnostic_response,
    prepare_real_diagnostic_event,
)
from agent_ex.phase0b.vllm_event_adapter import (
    PHASE0B_VLLM_ENDPOINT,
    Phase0BDispatchJournal,
    Phase0BVllmEventAdapter,
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
)
from agent_ex.domain import EventStatus
from agent_ex.pipeline import MockEventPipeline
from agent_ex.topic import TopicPackage
from helpers.mock_matrix import build_mock_artifact_family
from test_pipeline import _limits
from test_phase0b_vllm_event_adapter import FakeConnection


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper1"


def _scale_case(case_id: str = "mock-n20-fault-recovery"):
    artifact = ArtifactEnvelope.from_payload(
        json.loads((FIXTURE_DIR / "mock_scale_cases.artifact.json").read_text(encoding="utf-8"))
    )
    return next(case for case in load_mock_scale_cases(artifact) if case.case_id == case_id)


def _candidate():
    matched_seed = 20260920
    family = build_mock_artifact_family(n=20, sweeps=2, matched_seed=matched_seed)
    return build_diagnostic_n20_matrix_candidate(
        scale_case=_scale_case(),
        matched_seed=matched_seed,
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


def test_diagnostic_matrix_candidate_binds_exact_n20_t2_inventory() -> None:
    candidate = _candidate()

    assert candidate.agent_count == 20
    assert candidate.sweep_count == 2
    assert candidate.cell_ids == CANONICAL_CELL_IDS
    assert candidate.expected_event_count == 480
    assert candidate.max_transport_count == 960
    assert sum(cell.manifest.schedule.count for cell in candidate.matrix.cells) == 480
    assert candidate.calibration_only is True
    assert candidate.formal_parameter_authority is False
    assert candidate.research_parameter_status == "not_frozen"
    assert candidate.to_payload()["record_hash"] == candidate.record_hash


def test_diagnostic_matrix_candidate_exposes_authorization_artifact_keys() -> None:
    candidate = _candidate()

    assert set(candidate.authorization_artifact_hashes) == {
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


def test_diagnostic_matrix_candidate_rejects_non_n20_case() -> None:
    scale_case = _scale_case("mock-n100-full-matrix")
    family = build_mock_artifact_family(n=20, sweeps=2, matched_seed=20260920)

    with pytest.raises(ValueError, match="population|20|scale"):
        build_diagnostic_n20_matrix_candidate(
            scale_case=scale_case,
            matched_seed=20260920,
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


def test_phase0b_matrix_production_code_does_not_import_tests() -> None:
    source = (Path(__file__).parents[1] / "src" / "agent_ex" / "phase0b" / "matrix.py").read_text(
        encoding="utf-8"
    )

    assert "platform.tests" not in source
    assert "tests.helpers" not in source
    assert "from helpers" not in source


def _base_envelope(name: str) -> ArtifactEnvelope:
    return ArtifactEnvelope.from_payload(
        json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    )


def _production_family():
    frame = _base_envelope("mock_population_frame.artifact.json")
    frame_payload = frame.payload
    persona_fixture = _base_envelope("mock_persona_template.artifact.json")
    persona = ArtifactEnvelope.create(
        artifact_type=persona_fixture.artifact_type,
        schema_version=persona_fixture.schema_version,
        algorithm_id=persona_fixture.algorithm_id,
        algorithm_version=persona_fixture.algorithm_version,
        input_hashes={"fixture": persona_fixture.output_hash},
        payload=persona_fixture.payload,
        rng_provenance=(),
    )
    return build_diagnostic_n20_artifact_family(
        matched_seed=20260920,
        population_frame_artifact=frame,
        population_weights=tuple(frame_payload["weight_profiles"]["20"]),
        population_constraints=frame_payload["constraints"],
        population_tolerance=0,
        topic_package=TopicPackage.from_payload(
            _base_envelope("mock_topic_package.artifact.json").to_payload()["payload"]
        ),
        reason_library_artifact=_base_envelope("mock_reason_library.artifact.json"),
        persona_template=persona,
        stance_orthogonal_fields=("gender", "urban", "education"),
        stance_max_category_imbalance=1.0,
        ws_k=4,
        ws_rewire_probability=0.05,
        shadow_max_attempts=4,
        shadow_trial_budget_per_edge=500,
        structural_null_replicates=1,
        attention_family="equal_weight",
        attention_parameters={},
        structural_lurker_probability=0.2,
        expression_beta_alpha=2.0,
        expression_beta_beta=2.0,
        expression_max_beta_attempts_per_agent=100,
        expression_correlation_mode="independent",
        sweep_count=2,
        calibration_only=True,
        formal_parameter_authority=False,
        research_parameter_status="not_frozen",
    )


def _real_binding() -> DiagnosticAdapterBinding:
    return DiagnosticAdapterBinding.create(
        model_repository="Qwen/Qwen3-8B",
        model_revision="b" * 40,
        tokenizer_revision="b" * 40,
        chat_template_hash="a" * 64,
        vllm_version="0.23.0",
        package_lock_hash="a" * 64,
        image_identity_hash="a" * 64,
        environment_lock_hash="a" * 64,
        service_start_identity_hash="a" * 64,
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        served_model_name="qwen3-8b-paper1",
    )


def _authorization(family) -> DiagnosticRunAuthorization:
    policy = DiagnosticAttemptPolicy.create(
        connect_timeout_seconds=10.0,
        read_timeout_seconds=120.0,
        total_timeout_seconds=180.0,
        retryable_error_codes=("provider_busy", "transport_timeout"),
        max_same_event_retries=1,
    )
    return DiagnosticRunAuthorization.create(
        cell_ids=CANONICAL_CELL_IDS,
        artifact_hashes=family.authorization_artifact_hashes,
        feed_capacity_candidate=6,
        feed_capacity_research_qa_id="P1_MAX_NEIGHBORS",
        memory_window_candidate=3,
        memory_window_research_qa_id="P1_MEMORY_WINDOW",
        adapter_binding_hash=_real_binding().record_hash,
        attempt_policy_hash=policy.record_hash,
        source_commit="c" * 40,
        source_dirty=False,
        source_diff_hash=None,
        temperature=0.7,
        top_p=0.8,
        max_tokens=128,
        enable_thinking=False,
        matched_seed=family.matched_seed,
        model_seed_pairing_rule="sha256-v1:matched-seed+cell-id+event-id",
        disk_budget_bytes=20_000_000_000,
        token_budget=200_000,
        wall_clock_limit_seconds=7200,
        checkpoint_cadence="completed_sweep_and_cell",
        archive_uri="/root/autodl-tmp/agent-ex-phase0b-n20-t2-v1",
        forbidden_claims=(
            "causal_estimate",
            "formal_experiment",
            "independent_agent_replicates",
            "inferential_statistics",
            "parameter_freeze",
            "primary_result",
        ),
    )


def test_production_artifact_family_exactly_reuses_matched_n20_t2_inputs() -> None:
    family = _production_family()

    assert family.agent_count == 20
    assert family.sweep_count == 2
    assert family.schedule.population_size == 20
    assert family.schedule.sweep_count == 2
    assert family.schedule.count == 40
    assert {slot.agent_id for slot in family.schedule.slots} <= set(family.agent_ids)
    assert family.calibration_only is True
    assert family.formal_parameter_authority is False
    assert family.research_parameter_status == "not_frozen"
    assert (
        family.publish_artifact.to_payload()["payload"]["frozen_schedule"]
        == family.schedule.to_payload()
    )


def test_materializer_builds_real_manifests_personas_and_exact_exposure_wiring(
    tmp_path: Path,
) -> None:
    family = _production_family()
    matrix = materialize_diagnostic_n20_matrix(
        family=family,
        authorization=_authorization(family),
        adapter_binding=_real_binding(),
        schedule_uri_root=tmp_path,
        launch_nonce_namespace="diagnostic-test",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )

    assert tuple(cell.cell_id for cell in matrix.cells) == CANONICAL_CELL_IDS
    assert sum(cell.manifest.schedule.count for cell in matrix.cells) == 480
    assert len({cell.manifest.run_id for cell in matrix.cells}) == 12
    assert len({cell.manifest.schedule_hash for cell in matrix.cells}) == 1
    for cell in matrix.cells:
        assert cell.manifest.schedule == family.schedule
        assert cell.manifest.model_identity["provider"] == "vllm"
        assert cell.manifest.run_spec["diagnostic_authorization_hash"] == matrix.authorization_hash
        assert len(cell.rendered_personas) == 20
        sample = cell.rendered_personas[family.agent_ids[0]].payload
        assert bool(sample["identity_block"]) is cell.identity_present
        assert bool(sample["continuity_block"]) is cell.continuity_present
        if cell.exposure_mode == "self_history_only":
            assert cell.exposure_graph_artifact is None
            assert cell.source_ws_artifact is None
            assert all(not neighbors for neighbors in cell.frozen_neighbor_agent_ids.values())
        elif cell.exposure_mode == "shuffled_social":
            assert cell.exposure_graph_artifact == family.shadow_artifact
            assert cell.source_ws_artifact == family.ws_artifact
        else:
            assert cell.exposure_mode == "ws_neighbors"
            assert cell.exposure_graph_artifact == family.ws_artifact
            assert cell.source_ws_artifact is None
    for prefix in ("P1-I0-C0", "P1-I0-C1", "P1-I1-C0", "P1-I1-C1"):
        shadow_cell = next(cell for cell in matrix.cells if cell.cell_id == f"{prefix}-E1")
        ws_cell = next(cell for cell in matrix.cells if cell.cell_id == f"{prefix}-E2")
        for agent_id in family.agent_ids:
            shadow_neighbors = set(shadow_cell.frozen_neighbor_agent_ids[agent_id])
            ws_neighbors = set(ws_cell.frozen_neighbor_agent_ids[agent_id])
            assert len(shadow_neighbors) == len(ws_neighbors)
            assert shadow_neighbors.isdisjoint(ws_neighbors)


def test_materializer_initializes_independent_v6_stores_with_exact_round0_state(
    tmp_path: Path,
) -> None:
    family = _production_family()
    matrix = materialize_diagnostic_n20_matrix(
        family=family,
        authorization=_authorization(family),
        adapter_binding=_real_binding(),
        schedule_uri_root=tmp_path / "schedules",
        launch_nonce_namespace="diagnostic-storage-test",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )

    stores = initialize_diagnostic_n20_stores(tmp_path / "stores", matrix=matrix)
    try:
        assert tuple(stores) == CANONICAL_CELL_IDS
        assert len(tuple((tmp_path / "stores").glob("*.sqlite"))) == 12
        assert len({store.binding.run_id for store in stores.values()}) == 12
        for cell_id, storage in stores.items():
            assert storage.binding.schema_version == "paper1.run-storage.v6"
            assert storage.binding.round0_root is not None
            assert storage.binding.expected_agent_ids == family.agent_ids
            assert len([agent for agent in family.agent_ids if storage.private_state(agent)]) == 20
            assert (
                len([agent for agent in family.agent_ids if storage.public_posts_for_agent(agent)])
                == 20
            )
            expected_mode = next(
                cell.exposure_mode for cell in matrix.cells if cell.cell_id == cell_id
            )
            assert storage.binding.expected_exposure_mode == expected_mode
    finally:
        for storage in stores.values():
            storage.close()


def test_production_artifact_family_rejects_unresolved_candidate_input() -> None:
    frame = _base_envelope("mock_population_frame.artifact.json")
    frame_payload = frame.payload
    with pytest.raises(ValueError, match="UNRESOLVED|candidate"):
        build_diagnostic_n20_artifact_family(
            matched_seed=20260920,
            population_frame_artifact=frame,
            population_weights=tuple(frame_payload["weight_profiles"]["20"]),
            population_constraints=frame_payload["constraints"],
            population_tolerance=0,
            topic_package=TopicPackage.from_payload(
                _base_envelope("mock_topic_package.artifact.json").to_payload()["payload"]
            ),
            reason_library_artifact=_base_envelope("mock_reason_library.artifact.json"),
            persona_template=_base_envelope("mock_persona_template.artifact.json"),
            stance_orthogonal_fields=("gender", "urban", "education"),
            stance_max_category_imbalance=1.0,
            ws_k=4,
            ws_rewire_probability=0.05,
            shadow_max_attempts=4,
            shadow_trial_budget_per_edge=500,
            structural_null_replicates=1,
            attention_family="UNRESOLVED[P1_ATTENTION]",
            attention_parameters={},
            structural_lurker_probability=0.2,
            expression_beta_alpha=2.0,
            expression_beta_beta=2.0,
            expression_max_beta_attempts_per_agent=100,
            expression_correlation_mode="independent",
            sweep_count=2,
            calibration_only=True,
            formal_parameter_authority=False,
            research_parameter_status="not_frozen",
        )


def test_real_n20_cells_can_prepare_shared_network_event_inputs(tmp_path: Path) -> None:
    family = _production_family()
    matrix = materialize_diagnostic_n20_matrix(
        family=family,
        authorization=_authorization(family),
        adapter_binding=_real_binding(),
        schedule_uri_root=tmp_path / "schedules",
        launch_nonce_namespace="diagnostic-input-test",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )
    stores = initialize_diagnostic_n20_stores(tmp_path / "stores", matrix=matrix)
    parser_limits, prompt_limits = _limits()
    try:
        for cell in (matrix.cells[0], matrix.cells[1], matrix.cells[2]):
            storage = stores[cell.cell_id]
            pipeline = MockEventPipeline(
                storage=storage,
                manifest=cell.manifest,
                topic_package=family.topic_package,
                persona_template=family.persona_template,
                population_artifact=family.population_artifact,
                exposure_graph_artifact=cell.exposure_graph_artifact,
                source_ws_artifact=cell.source_ws_artifact,
                agent_node_mapping_artifact=cell.agent_node_mapping_artifact,
                round0_initialization_artifact=cell.round0_initialization_artifact,
                frozen_neighbor_agent_ids=cell.frozen_neighbor_agent_ids,
                clock=lambda: "2040-01-01T00:00:00Z",
            )
            event_input = pipeline.prepare_event_input(
                journal=storage.current_event_journal(),
                feed_capacity=6,
                memory_window=3,
                parser_limits=parser_limits,
                prompt_limits=prompt_limits,
            )
            slot = cell.manifest.schedule.slots[0]
            assert event_input.receiver_agent_id == slot.agent_id
            assert event_input.publish_flag == slot.publish_flag
            assert event_input.exposure_record.exposure_mode == cell.exposure_mode
            assert storage.progress.next_event_ordinal == 0
    finally:
        for storage in stores.values():
            storage.close()


def test_real_n20_first_event_persists_diagnostic_request_for_scheduled_agent(
    tmp_path: Path,
) -> None:
    family = _production_family()
    authorization = _authorization(family)
    binding = _real_binding()
    policy = DiagnosticAttemptPolicy.create(
        connect_timeout_seconds=10.0,
        read_timeout_seconds=120.0,
        total_timeout_seconds=180.0,
        retryable_error_codes=("provider_busy", "transport_timeout"),
        max_same_event_retries=1,
    )
    matrix = materialize_diagnostic_n20_matrix(
        family=family,
        authorization=authorization,
        adapter_binding=binding,
        schedule_uri_root=tmp_path / "schedules",
        launch_nonce_namespace="diagnostic-first-event",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )
    stores = initialize_diagnostic_n20_stores(tmp_path / "stores", matrix=matrix)
    parser_limits, prompt_limits = _limits()
    try:
        cell = matrix.cells[2]
        storage = stores[cell.cell_id]
        pipeline = MockEventPipeline(
            storage=storage,
            manifest=cell.manifest,
            topic_package=family.topic_package,
            persona_template=family.persona_template,
            population_artifact=family.population_artifact,
            exposure_graph_artifact=cell.exposure_graph_artifact,
            source_ws_artifact=cell.source_ws_artifact,
            agent_node_mapping_artifact=cell.agent_node_mapping_artifact,
            round0_initialization_artifact=cell.round0_initialization_artifact,
            frozen_neighbor_agent_ids=cell.frozen_neighbor_agent_ids,
            clock=lambda: "2040-01-01T00:00:00Z",
        )
        with storage.acquire_run_lease():
            prepared = prepare_real_diagnostic_event(
                storage=storage,
                input_pipeline=pipeline,
                manifest=cell.manifest,
                authorization=authorization,
                policy=policy,
                adapter_binding=binding,
                parser_limits=parser_limits,
                prompt_limits=prompt_limits,
            )
        assert prepared.event_input.receiver_agent_id == cell.manifest.schedule.slots[0].agent_id
        assert prepared.request.event_id == storage.current_event_journal().event_id
        assert prepared.request.attempt_index == 1
        assert storage.adapter_request_evidence(prepared.request.attempt_id) == (
            prepared.request_evidence
        )
        assert storage.current_event_journal().latest_transition == prepared.pending_attempt
        assert storage.progress.next_event_ordinal == 0
    finally:
        for storage in stores.values():
            storage.close()


def test_real_n20_first_response_commits_only_scheduled_agent(tmp_path: Path) -> None:
    family = _production_family()
    authorization = _authorization(family)
    binding = _real_binding()
    policy = DiagnosticAttemptPolicy.create(
        connect_timeout_seconds=10.0,
        read_timeout_seconds=120.0,
        total_timeout_seconds=180.0,
        retryable_error_codes=("provider_busy", "transport_timeout"),
        max_same_event_retries=1,
    )
    matrix = materialize_diagnostic_n20_matrix(
        family=family,
        authorization=authorization,
        adapter_binding=binding,
        schedule_uri_root=tmp_path / "schedules",
        launch_nonce_namespace="diagnostic-first-response",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )
    stores = initialize_diagnostic_n20_stores(tmp_path / "stores", matrix=matrix)
    parser_limits, prompt_limits = _limits()
    try:
        cell = matrix.cells[2]
        storage = stores[cell.cell_id]
        pipeline = MockEventPipeline(
            storage=storage,
            manifest=cell.manifest,
            topic_package=family.topic_package,
            persona_template=family.persona_template,
            population_artifact=family.population_artifact,
            exposure_graph_artifact=cell.exposure_graph_artifact,
            source_ws_artifact=cell.source_ws_artifact,
            agent_node_mapping_artifact=cell.agent_node_mapping_artifact,
            round0_initialization_artifact=cell.round0_initialization_artifact,
            frozen_neighbor_agent_ids=cell.frozen_neighbor_agent_ids,
            clock=lambda: "2040-01-01T00:00:00Z",
        )
        receiver = cell.manifest.schedule.slots[0].agent_id
        receiver_before = storage.private_state(receiver)
        other = next(agent_id for agent_id in family.agent_ids if agent_id != receiver)
        other_before = storage.private_state(other)
        with storage.acquire_run_lease():
            prepared = prepare_real_diagnostic_event(
                storage=storage,
                input_pipeline=pipeline,
                manifest=cell.manifest,
                authorization=authorization,
                policy=policy,
                adapter_binding=binding,
                parser_limits=parser_limits,
                prompt_limits=prompt_limits,
            )
            in_progress = replace(
                prepared.pending_attempt,
                status=EventStatus.IN_PROGRESS,
                started_at="2040-01-01T00:00:00Z",
            )
            storage.append_attempt(in_progress)
            content = json.dumps(
                {
                    "stance": family.topic_package.stance_labels[2],
                    "confidence": 3,
                    "public_reason": "A concise diagnostic reason.",
                }
            )
            body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            transport = Phase0BVllmTransportEvidence.create(
                request=prepared.request,
                http_status=200,
                response_headers={},
                provider_request_id="provider-first",
                request_body=b"{}",
                raw_body=body,
                body_truncated=False,
                started_at="2040-01-01T00:00:00.100000Z",
                ended_at="2040-01-01T00:00:01Z",
                latency_seconds=0.9,
                outcome="response",
                error_code=None,
            )
            response = Phase0BVllmEventResponse.create(
                request=prepared.request,
                outcome="response",
                error_code=None,
                retry_after_seconds=None,
                provider_request_id="provider-first",
                usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                finish_reason="stop",
                raw_body=body,
                transport_evidence=transport,
            )
            terminal = finalize_real_diagnostic_response(
                storage=storage,
                input_pipeline=pipeline,
                prepared=prepared,
                in_progress=in_progress,
                response=response,
                topic_package=family.topic_package,
            )
        assert terminal.status is EventStatus.SUCCEEDED
        assert storage.progress.next_event_ordinal == 1
        assert storage.private_state(receiver).successful_update_count == (
            receiver_before.successful_update_count + 1
        )
        assert storage.private_state(other) == other_before
        assert storage.event_at(0).agent_id == receiver
        with storage.acquire_run_lease():
            second = prepare_real_diagnostic_event(
                storage=storage,
                input_pipeline=pipeline,
                manifest=cell.manifest,
                authorization=authorization,
                policy=policy,
                adapter_binding=binding,
                parser_limits=parser_limits,
                prompt_limits=prompt_limits,
            )
        assert second.event_input.receiver_agent_id == cell.manifest.schedule.slots[1].agent_id
        assert second.request.event_id != prepared.request.event_id
        assert second.request.model_seed != prepared.request.model_seed
        assert storage.progress.next_event_ordinal == 1
        FakeConnection.requests = []
        FakeConnection.status = 200
        FakeConnection.headers = {"X-Request-Id": "provider-second"}
        FakeConnection.body = json.dumps(
            {
                "id": "provider-second",
                "model": binding.served_model_name,
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "stance": family.topic_package.stance_labels[2],
                                    "confidence": 3,
                                    "public_reason": "Second diagnostic reason.",
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            }
        ).encode()
        adapter = Phase0BVllmEventAdapter(
            PHASE0B_VLLM_ENDPOINT,
            served_model_name=binding.served_model_name,
            connection_factory=FakeConnection,
        )
        dispatch_journal = Phase0BDispatchJournal(tmp_path / "dispatch.jsonl")
        with storage.acquire_run_lease():
            second_terminal = dispatch_real_diagnostic_event_once(
                storage=storage,
                input_pipeline=pipeline,
                prepared=second,
                adapter=adapter,
                policy=policy,
                topic_package=family.topic_package,
                dispatch_journal=dispatch_journal,
                clock=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            )
        assert second_terminal.status is EventStatus.SUCCEEDED
        assert storage.progress.next_event_ordinal == 2
        assert len(FakeConnection.requests) == 1
        assert dispatch_journal.unresolved_request_ids() == ()
    finally:
        for storage in stores.values():
            storage.close()
