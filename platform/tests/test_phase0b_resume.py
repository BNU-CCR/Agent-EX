"""Small real-provider resume tests; no cloud service or research output."""

from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest

from agent_ex.phase0b.matrix import (
    initialize_diagnostic_n20_stores,
    materialize_diagnostic_n20_matrix,
)
from agent_ex.phase0b.real_pipeline import (
    _canonical_materialized_matrix_hash,
    prepare_real_diagnostic_event,
    resume_real_diagnostic_cell_events,
    resume_real_diagnostic_matrix,
    run_real_diagnostic_cell_events,
    verify_two_event_diagnostic_prefix,
)
from agent_ex.phase0b.vllm_event_adapter import (
    PHASE0B_VLLM_ENDPOINT,
    Phase0BDispatchJournal,
    Phase0BVllmEventAdapter,
)
from test_phase0b_matrix import _authorization, _production_family, _real_binding
from test_phase0b_vllm_event_adapter import FakeConnection
from test_pipeline import _limits
from agent_ex.pipeline import MockEventPipeline


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture
def setup(tmp_path):
    family = _production_family()
    authorization = _authorization(family)
    binding = _real_binding()
    from agent_ex.phase0b.contracts import DiagnosticAttemptPolicy

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
        launch_nonce_namespace="resume-test",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )
    stores = initialize_diagnostic_n20_stores(tmp_path / "stores", matrix=matrix)
    FakeConnection.requests = []
    FakeConnection.status = 200
    FakeConnection.headers = {"X-Request-Id": "provider-resume"}
    FakeConnection.body = json.dumps(
        {
            "id": "provider-resume",
            "model": binding.served_model_name,
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "stance": family.topic_package.stance_labels[2],
                                "confidence": 3,
                                "public_reason": "Synthetic response for local test.",
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }
    ).encode()
    parser_limits, prompt_limits = _limits()
    cell = matrix.cells[0]
    journal = Phase0BDispatchJournal(tmp_path / "run" / f"{cell.cell_id}.dispatch.jsonl")
    (tmp_path / "run").mkdir()

    def adapter_factory():
        return Phase0BVllmEventAdapter(
            PHASE0B_VLLM_ENDPOINT,
            served_model_name=binding.served_model_name,
            connection_factory=FakeConnection,
        )

    data = dict(
        storage=stores[cell.cell_id],
        cell=cell,
        family=family,
        authorization=authorization,
        policy=policy,
        adapter_binding=binding,
        parser_limits=parser_limits,
        prompt_limits=prompt_limits,
        adapter_factory=adapter_factory,
        dispatch_journal=journal,
        checkpoint_root=tmp_path / "run" / "checkpoints",
        clock=_now,
    )
    try:
        yield data
    finally:
        for store in stores.values():
            store.close()


def test_clean_committed_prefix_resumes_without_resending_success(setup) -> None:
    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=1)
    first_request = FakeConnection.requests[0]
    terminals = resume_real_diagnostic_cell_events(**setup, event_count=1)
    assert len(terminals) == 1
    assert setup["storage"].progress.next_event_ordinal == 2
    assert len(FakeConnection.requests) == 2
    assert FakeConnection.requests[0] == first_request


def test_two_event_preflight_verifies_clean_committed_prefix(setup) -> None:
    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=2)
    summary = verify_two_event_diagnostic_prefix(
        storage=setup["storage"],
        cell=setup["cell"],
        family=setup["family"],
        authorization=setup["authorization"],
        policy=setup["policy"],
        adapter_binding=setup["adapter_binding"],
        dispatch_journal=setup["dispatch_journal"],
        checkpoint_root=setup["checkpoint_root"],
    )
    assert summary.committed_event_count == 2
    assert summary.transport_count == 2
    assert summary.cell_id == setup["cell"].cell_id
    assert summary.authorization_hash == setup["authorization"].record_hash
    assert summary.calibration_only is True
    assert summary.formal_parameter_authority is False
    assert summary.research_parameter_status == "not_frozen"
    assert len(FakeConnection.requests) == 2


def test_two_event_preflight_rejects_partial_prefix(setup) -> None:
    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=1)
    with pytest.raises(ValueError, match="exactly two"):
        verify_two_event_diagnostic_prefix(
            storage=setup["storage"],
            cell=setup["cell"],
            family=setup["family"],
            authorization=setup["authorization"],
            policy=setup["policy"],
            adapter_binding=setup["adapter_binding"],
            dispatch_journal=setup["dispatch_journal"],
            checkpoint_root=setup["checkpoint_root"],
        )


def test_unresolved_dispatch_intent_refuses_resume_before_provider_call(setup) -> None:
    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=1)
    journal = setup["dispatch_journal"]
    # An unresolved, hash-valid intent is deliberately not repaired automatically.
    from agent_ex.domain import canonical_payload_hash

    payload = {
        "schema_version": "paper1.phase0b.dispatch-intent.v1",
        "kind": "intent",
        "request_id": "unresolved-next-event",
        "request_hash": "a" * 64,
        "request_body_sha256": "a" * 64,
        "created_at": _now(),
    }
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**payload, "record_hash": canonical_payload_hash(payload)}) + "\n")
    with pytest.raises(RuntimeError, match="unresolved dispatch"):
        resume_real_diagnostic_cell_events(**setup, event_count=1)
    assert len(FakeConnection.requests) == 1


def test_in_progress_attempt_refuses_resume_before_provider_call(setup) -> None:
    from dataclasses import replace

    from agent_ex.domain import EventStatus

    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=1)
    cell = setup["cell"]
    family = setup["family"]
    storage = setup["storage"]
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
        clock=_now,
    )
    with storage.acquire_run_lease():
        pending = prepare_real_diagnostic_event(
            storage=storage,
            input_pipeline=pipeline,
            manifest=cell.manifest,
            authorization=setup["authorization"],
            policy=setup["policy"],
            adapter_binding=setup["adapter_binding"],
            parser_limits=setup["parser_limits"],
            prompt_limits=setup["prompt_limits"],
        )
        storage.append_attempt(
            replace(pending.pending_attempt, status=EventStatus.IN_PROGRESS, started_at=_now())
        )
    with pytest.raises(RuntimeError, match="IN_PROGRESS"):
        resume_real_diagnostic_cell_events(**setup, event_count=1)
    assert len(FakeConnection.requests) == 1


def test_standalone_resume_acquires_lease_before_preflight(
    setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_ex.phase0b.real_pipeline as real_pipeline

    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=1)
    preflight_calls = 0
    original = real_pipeline._verify_clean_diagnostic_cell_prefix

    def observed_preflight(**kwargs):
        nonlocal preflight_calls
        preflight_calls += 1
        return original(**kwargs)

    monkeypatch.setattr(real_pipeline, "_verify_clean_diagnostic_cell_prefix", observed_preflight)
    before = len(FakeConnection.requests)
    with setup["storage"].acquire_run_lease():
        with pytest.raises(RuntimeError, match="lease.*owned"):
            resume_real_diagnostic_cell_events(**setup, event_count=1)
    assert preflight_calls == 0
    assert len(FakeConnection.requests) == before


def test_identity_drift_refuses_resume_before_provider_call(setup) -> None:
    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=1)
    from dataclasses import replace
    from agent_ex.domain import canonical_payload_hash

    binding = setup["adapter_binding"]
    content = dict(binding.content_payload())
    content["service_start_identity_hash"] = "b" * 64
    wrong = replace(
        binding,
        service_start_identity_hash="b" * 64,
        record_hash=canonical_payload_hash(content),
    )
    with pytest.raises(ValueError, match="authorization|hash"):
        resume_real_diagnostic_cell_events(**{**setup, "adapter_binding": wrong}, event_count=1)
    assert len(FakeConnection.requests) == 1


def test_matrix_preflights_later_pending_cell_before_any_new_dispatch(setup, tmp_path) -> None:
    family = setup["family"]
    authorization = setup["authorization"]
    binding = setup["adapter_binding"]
    policy = setup["policy"]
    matrix = materialize_diagnostic_n20_matrix(
        family=family,
        authorization=authorization,
        adapter_binding=binding,
        schedule_uri_root=tmp_path / "matrix-schedules",
        launch_nonce_namespace="matrix-resume-test",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )
    stores = initialize_diagnostic_n20_stores(tmp_path / "matrix-stores", matrix=matrix)
    run_root = tmp_path / "matrix-run"
    run_root.mkdir()
    first, second = matrix.cells[:2]
    try:
        run_real_diagnostic_cell_events(
            **{
                **setup,
                "storage": stores[first.cell_id],
                "cell": first,
                "dispatch_journal": Phase0BDispatchJournal(
                    run_root / f"{first.cell_id}.dispatch.jsonl"
                ),
                "checkpoint_root": run_root / "checkpoints",
            },
            start_ordinal=0,
            event_count=1,
        )
        pipeline = MockEventPipeline(
            storage=stores[second.cell_id],
            manifest=second.manifest,
            topic_package=family.topic_package,
            persona_template=family.persona_template,
            population_artifact=family.population_artifact,
            exposure_graph_artifact=second.exposure_graph_artifact,
            source_ws_artifact=second.source_ws_artifact,
            agent_node_mapping_artifact=second.agent_node_mapping_artifact,
            round0_initialization_artifact=second.round0_initialization_artifact,
            frozen_neighbor_agent_ids=second.frozen_neighbor_agent_ids,
            clock=_now,
        )
        with stores[second.cell_id].acquire_run_lease():
            prepare_real_diagnostic_event(
                storage=stores[second.cell_id],
                input_pipeline=pipeline,
                manifest=second.manifest,
                authorization=authorization,
                policy=policy,
                adapter_binding=binding,
                parser_limits=setup["parser_limits"],
                prompt_limits=setup["prompt_limits"],
            )
        before = len(FakeConnection.requests)
        with pytest.raises(RuntimeError, match="pending|IN_PROGRESS|failed"):
            resume_real_diagnostic_matrix(
                matrix=matrix,
                authorization=authorization,
                adapter_binding=binding,
                policy=policy,
                stores=stores,
                parser_limits=setup["parser_limits"],
                prompt_limits=setup["prompt_limits"],
                adapter_factory=lambda _cell_id: setup["adapter_factory"](),
                run_root=run_root,
                clock=_now,
            )
        assert len(FakeConnection.requests) == before
    finally:
        for store in stores.values():
            store.close()


def test_historical_checkpoint_conflict_refuses_resume_before_dispatch(setup) -> None:
    from agent_ex.checkpoint import load_checkpoint
    from agent_ex.domain import canonical_payload_hash

    run_real_diagnostic_cell_events(**setup, start_ordinal=0, event_count=21)
    checkpoint_path = setup["checkpoint_root"] / f"{setup['cell'].cell_id}-00020.checkpoint.json"
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    payload["checkpoint"]["current_manifest_hash"] = "f" * 64
    payload["checkpoint_hash"] = canonical_payload_hash(payload["checkpoint"])
    checkpoint_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    assert load_checkpoint(checkpoint_path).next_event_ordinal == 20
    before = len(FakeConnection.requests)

    with pytest.raises(ValueError, match="checkpoint|SQLite"):
        resume_real_diagnostic_cell_events(**setup, event_count=1)
    assert len(FakeConnection.requests) == before


def test_matrix_preflights_later_static_neighbor_wiring_before_dispatch(setup, tmp_path) -> None:
    from dataclasses import replace

    family = setup["family"]
    authorization = setup["authorization"]
    binding = setup["adapter_binding"]
    matrix = materialize_diagnostic_n20_matrix(
        family=family,
        authorization=authorization,
        adapter_binding=binding,
        schedule_uri_root=tmp_path / "matrix-schedules",
        launch_nonce_namespace="matrix-static-test",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )
    stores = initialize_diagnostic_n20_stores(tmp_path / "matrix-stores", matrix=matrix)
    run_root = tmp_path / "matrix-run"
    run_root.mkdir()
    first, second = matrix.cells[:2]
    try:
        run_real_diagnostic_cell_events(
            **{
                **setup,
                "storage": stores[first.cell_id],
                "cell": first,
                "dispatch_journal": Phase0BDispatchJournal(
                    run_root / f"{first.cell_id}.dispatch.jsonl"
                ),
                "checkpoint_root": run_root / "checkpoints",
            },
            start_ordinal=0,
            event_count=1,
        )
        broken_cell = replace(second, frozen_neighbor_agent_ids={})
        broken_matrix = replace(matrix, cells=(first, broken_cell, *matrix.cells[2:]))
        broken_matrix = replace(
            broken_matrix,
            matrix_hash=_canonical_materialized_matrix_hash(broken_matrix),
        )
        factory_calls = 0

        def forbidden_factory(_cell_id):
            nonlocal factory_calls
            factory_calls += 1
            raise AssertionError("provider factory must not run before full static preflight")

        with pytest.raises(ValueError, match="frozen neighbor"):
            resume_real_diagnostic_matrix(
                matrix=broken_matrix,
                authorization=authorization,
                adapter_binding=binding,
                policy=setup["policy"],
                stores=stores,
                parser_limits=setup["parser_limits"],
                prompt_limits=setup["prompt_limits"],
                adapter_factory=forbidden_factory,
                run_root=run_root,
                clock=_now,
            )
        assert factory_calls == 0
    finally:
        for store in stores.values():
            store.close()


def _one_event_matrix(setup, tmp_path):
    matrix = materialize_diagnostic_n20_matrix(
        family=setup["family"],
        authorization=setup["authorization"],
        adapter_binding=setup["adapter_binding"],
        schedule_uri_root=tmp_path / "matrix-schedules",
        launch_nonce_namespace="matrix-lock-test",
        started_at="2040-01-01T00:00:00Z",
        environment={
            "python_version": "3.12.13",
            "dependency_lock_hash": "a" * 64,
            "platform": "linux-x86_64",
        },
    )
    stores = initialize_diagnostic_n20_stores(tmp_path / "matrix-stores", matrix=matrix)
    run_root = tmp_path / "matrix-run"
    run_root.mkdir()
    first = matrix.cells[0]
    run_real_diagnostic_cell_events(
        **{
            **setup,
            "storage": stores[first.cell_id],
            "cell": first,
            "dispatch_journal": Phase0BDispatchJournal(
                run_root / f"{first.cell_id}.dispatch.jsonl"
            ),
            "checkpoint_root": run_root / "checkpoints",
        },
        start_ordinal=0,
        event_count=1,
    )
    return matrix, stores, run_root


def test_matrix_resume_rejects_forged_matrix_hash_before_dispatch(setup, tmp_path) -> None:
    from dataclasses import replace

    matrix, stores, run_root = _one_event_matrix(setup, tmp_path)
    try:
        bad_matrix = replace(matrix, matrix_hash="f" * 64)
        before = len(FakeConnection.requests)
        with pytest.raises(ValueError, match="matrix hash"):
            resume_real_diagnostic_matrix(
                matrix=bad_matrix,
                authorization=setup["authorization"],
                adapter_binding=setup["adapter_binding"],
                policy=setup["policy"],
                stores=stores,
                parser_limits=setup["parser_limits"],
                prompt_limits=setup["prompt_limits"],
                adapter_factory=lambda _cell_id: setup["adapter_factory"](),
                run_root=run_root,
                clock=_now,
            )
        assert len(FakeConnection.requests) == before
    finally:
        for store in stores.values():
            store.close()


def test_matrix_resume_rejects_competing_later_cell_lease_before_dispatch(setup, tmp_path) -> None:
    matrix, stores, run_root = _one_event_matrix(setup, tmp_path)
    later = matrix.cells[1]
    try:
        before = len(FakeConnection.requests)
        with stores[later.cell_id].acquire_run_lease():
            with pytest.raises(RuntimeError, match="lease.*owned"):
                resume_real_diagnostic_matrix(
                    matrix=matrix,
                    authorization=setup["authorization"],
                    adapter_binding=setup["adapter_binding"],
                    policy=setup["policy"],
                    stores=stores,
                    parser_limits=setup["parser_limits"],
                    prompt_limits=setup["prompt_limits"],
                    adapter_factory=lambda _cell_id: setup["adapter_factory"](),
                    run_root=run_root,
                    clock=_now,
                )
        assert len(FakeConnection.requests) == before
    finally:
        for store in stores.values():
            store.close()


def test_matrix_resume_executes_under_all_cell_leases_without_reacquiring(setup, tmp_path) -> None:
    matrix, stores, run_root = _one_event_matrix(setup, tmp_path)
    calls = 0

    def factory(_cell_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("bounded-test-stop")
        return setup["adapter_factory"]()

    try:
        before = len(FakeConnection.requests)
        with pytest.raises(RuntimeError, match="bounded-test-stop"):
            resume_real_diagnostic_matrix(
                matrix=matrix,
                authorization=setup["authorization"],
                adapter_binding=setup["adapter_binding"],
                policy=setup["policy"],
                stores=stores,
                parser_limits=setup["parser_limits"],
                prompt_limits=setup["prompt_limits"],
                adapter_factory=factory,
                run_root=run_root,
                clock=_now,
            )
        assert calls == 2
        assert len(FakeConnection.requests) == before + 1
        assert stores[matrix.cells[0].cell_id].progress.next_event_ordinal == 2
    finally:
        for store in stores.values():
            store.close()
