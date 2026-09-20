from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import canonical_payload_hash
from agent_ex.mock_matrix import CANONICAL_CELL_IDS, load_mock_scale_cases
from agent_ex.phase0b import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
    build_diagnostic_n20_matrix_candidate,
)
from agent_ex.phase0b.run import (
    materialize_diagnostic_approval_packet,
    Phase0BJsonlStagingStore,
    preflight_diagnostic_run,
    run_fake_diagnostic_matrix,
    run_fake_diagnostic_slice,
    run_real_adapter_diagnostic_matrix,
    verify_diagnostic_matrix_run,
)
from helpers.mock_matrix import build_mock_artifact_family
from test_prompt import topic


SHA = "a" * 64
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper1"


class FakePhase0BAdapter:
    def __init__(self) -> None:
        self._before_dispatch = None
        self.calls = 0

    def bind_dispatch_journal(self, callback):
        self._before_dispatch = callback

    def generate(
        self,
        request,
        *,
        timeout_seconds: float,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
    ):
        assert self._before_dispatch is not None
        body = json.dumps({"request_id": request.request_id}).encode("utf-8")
        self._before_dispatch(request, body)
        from agent_ex.phase0b.vllm_event_adapter import (
            Phase0BVllmEventResponse,
            Phase0BVllmTransportEvidence,
        )

        self.calls += 1
        content = json.dumps(
            {
                "stance": "label-5",
                "confidence": 4,
                "public_reason": "real-qwen-diagnostic-update",
            },
            separators=(",", ":"),
        )
        raw_body = json.dumps(
            {
                "id": "phase0b-fake",
                "model": "qwen3-8b-paper1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
            separators=(",", ":"),
        ).encode("utf-8")
        evidence = Phase0BVllmTransportEvidence.create(
            request=request,
            http_status=200,
            response_headers={"x-request-id": f"fake-provider-{self.calls}"},
            provider_request_id=f"fake-provider-{self.calls}",
            request_body=body,
            raw_body=raw_body,
            body_truncated=False,
            started_at=f"2026-09-20T00:00:0{self.calls}Z",
            ended_at=f"2026-09-20T00:00:0{self.calls}Z",
            latency_seconds=0.1,
            outcome="response",
            error_code=None,
        )
        return Phase0BVllmEventResponse.create(
            request=request,
            outcome="response",
            error_code=None,
            retry_after_seconds=None,
            provider_request_id=f"fake-provider-{self.calls}",
            usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            finish_reason="stop",
            raw_body=raw_body,
            transport_evidence=evidence,
        )


def _policy() -> DiagnosticAttemptPolicy:
    return DiagnosticAttemptPolicy.create(
        connect_timeout_seconds=10.0,
        read_timeout_seconds=120.0,
        total_timeout_seconds=180.0,
        retryable_error_codes=("provider_busy", "transport_timeout"),
        max_same_event_retries=1,
    )


def _binding() -> DiagnosticAdapterBinding:
    return DiagnosticAdapterBinding.create(
        model_repository="Qwen/Qwen3-8B",
        model_revision="b" * 40,
        tokenizer_revision="b" * 40,
        chat_template_hash=SHA,
        vllm_version="0.23.0",
        package_lock_hash=SHA,
        image_identity_hash=SHA,
        environment_lock_hash=SHA,
        service_start_identity_hash=SHA,
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        served_model_name="qwen3-8b-paper1",
    )


def _candidate():
    matched_seed = 20260920
    artifact = ArtifactEnvelope.from_payload(
        json.loads((FIXTURE_DIR / "mock_scale_cases.artifact.json").read_text(encoding="utf-8"))
    )
    scale_case = next(
        case
        for case in load_mock_scale_cases(artifact)
        if case.case_id == "mock-n20-fault-recovery"
    )
    family = build_mock_artifact_family(n=20, sweeps=2, matched_seed=matched_seed)
    return build_diagnostic_n20_matrix_candidate(
        scale_case=scale_case,
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


def _authorization(
    candidate=None,
    binding: DiagnosticAdapterBinding | None = None,
    policy: DiagnosticAttemptPolicy | None = None,
) -> DiagnosticRunAuthorization:
    candidate = candidate or _candidate()
    binding = binding or _binding()
    policy = policy or _policy()
    return DiagnosticRunAuthorization.create(
        cell_ids=CANONICAL_CELL_IDS,
        artifact_hashes=candidate.authorization_artifact_hashes,
        feed_capacity_candidate=6,
        feed_capacity_research_qa_id="P1_MAX_NEIGHBORS",
        memory_window_candidate=3,
        memory_window_research_qa_id="P1_MEMORY_WINDOW",
        adapter_binding_hash=binding.record_hash,
        attempt_policy_hash=policy.record_hash,
        source_commit="c" * 40,
        source_dirty=False,
        source_diff_hash=None,
        temperature=0.7,
        top_p=0.8,
        max_tokens=128,
        enable_thinking=False,
        matched_seed=20260920,
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


def test_preflight_binds_authorization_matrix_policy_and_binding(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)

    preflight = preflight_diagnostic_run(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        run_root=tmp_path / "run",
    )

    assert preflight.authorization_hash == authorization.record_hash
    assert preflight.matrix_hash == candidate.matrix_hash
    assert preflight.expected_event_count == 480
    assert preflight.unresolved_dispatch_count == 0


def test_preflight_rejects_changed_authorization_hash(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    wrong_policy = DiagnosticAttemptPolicy.create(
        connect_timeout_seconds=11.0,
        read_timeout_seconds=120.0,
        total_timeout_seconds=180.0,
        retryable_error_codes=("provider_busy", "transport_timeout"),
        max_same_event_retries=1,
    )
    authorization = _authorization(candidate, binding, wrong_policy)

    with pytest.raises(ValueError, match="attempt policy hash"):
        preflight_diagnostic_run(
            authorization=authorization,
            matrix_candidate=candidate,
            adapter_binding=binding,
            attempt_policy=policy,
            run_root=tmp_path / "run",
        )


def test_preflight_rejects_duplicate_or_unresolved_run_root(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "dispatch.jsonl").write_text(
        json.dumps(
            {
                "kind": "intent",
                "request_id": "phase0b-vllm-request-pending",
                "record_hash": canonical_payload_hash(
                    {
                        "kind": "intent",
                        "request_id": "phase0b-vllm-request-pending",
                    }
                ),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unresolved dispatch|run root"):
        preflight_diagnostic_run(
            authorization=authorization,
            matrix_candidate=candidate,
            adapter_binding=binding,
            attempt_policy=policy,
            run_root=run_root,
        )


def test_fake_slice_writes_sanitized_staging_and_terminal_report(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    adapter = FakePhase0BAdapter()

    result = run_fake_diagnostic_slice(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        adapter=adapter,
        run_root=tmp_path / "run",
        event_count=2,
    )

    store = Phase0BJsonlStagingStore(tmp_path / "run" / "staging")
    attempts = store.read_jsonl("attempts.jsonl")
    assert len(attempts) == 2
    assert {record["outcome"] for record in attempts} == {"response"}
    assert all("raw_body_base64" not in json.dumps(record) for record in attempts)
    assert result.terminal_report.terminal_status == "terminal_incomplete"
    assert result.terminal_report.committed_event_count == 2
    assert result.terminal_report.transport_count == 2
    assert result.terminal_report.unresolved_dispatch_count == 0
    assert result.final_projection_hash == result.terminal_report.final_projection_hash


def test_fake_slice_rejects_reusing_launch_root(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    run_root = tmp_path / "run"

    run_fake_diagnostic_slice(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        adapter=FakePhase0BAdapter(),
        run_root=run_root,
        event_count=1,
    )

    with pytest.raises(FileExistsError, match="launch root"):
        run_fake_diagnostic_slice(
            authorization=authorization,
            matrix_candidate=candidate,
            adapter_binding=binding,
            attempt_policy=policy,
            adapter=FakePhase0BAdapter(),
            run_root=run_root,
            event_count=1,
        )


def test_fake_matrix_runner_completes_all_12_cells_and_480_events(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    adapter = FakePhase0BAdapter()

    result = run_fake_diagnostic_matrix(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        adapter=adapter,
        run_root=tmp_path / "run",
    )

    assert result.terminal_report.terminal_status == "complete"
    assert result.terminal_report.completed_cell_ids == CANONICAL_CELL_IDS
    assert result.committed_event_count == 480
    assert result.transport_count == 480
    assert adapter.calls == 480

    verified = verify_diagnostic_matrix_run(
        run_root=tmp_path / "run",
        authorization=authorization,
        matrix_candidate=candidate,
    )
    assert verified.terminal_status == "complete"
    assert verified.committed_event_count == 480
    assert verified.transport_count == 480


def test_real_adapter_matrix_runner_commits_480_events_without_raw_content(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    adapter = FakePhase0BAdapter()

    result = run_real_adapter_diagnostic_matrix(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        adapter=adapter,
        topic_package=topic(),
        run_root=tmp_path / "run",
    )

    assert result.terminal_report.terminal_status == "complete"
    assert result.terminal_report.completed_cell_ids == CANONICAL_CELL_IDS
    assert result.committed_event_count == 480
    assert result.transport_count == 480
    assert adapter.calls == 480

    store = Phase0BJsonlStagingStore(tmp_path / "run" / "staging")
    attempts = store.read_jsonl("attempts.jsonl")
    assert len(attempts) == 480
    assert {record["schema_version"] for record in attempts} == {
        "paper1.phase0b.real-adapter-attempt.v1"
    }
    serialized = json.dumps(attempts, sort_keys=True)
    assert "raw_body" not in serialized
    assert "real-qwen-diagnostic-update" not in serialized
    assert (
        verify_diagnostic_matrix_run(
            run_root=tmp_path / "run",
            authorization=authorization,
            matrix_candidate=candidate,
        ).committed_event_count
        == 480
    )


def test_approval_packet_binds_source_authority_endpoint_and_archive_without_raw_content() -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)

    packet = materialize_diagnostic_approval_packet(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
    )

    assert packet.source_commit == authorization.source_commit
    assert packet.source_dirty is authorization.source_dirty
    assert packet.source_diff_hash == authorization.source_diff_hash
    assert packet.authorization_hash == authorization.record_hash
    assert packet.matrix_hash == candidate.matrix_hash
    assert packet.expected_event_count == 480
    assert packet.max_transport_count == 960
    assert packet.archive_uri == authorization.archive_uri
    assert packet.endpoint == binding.endpoint
    assert packet.served_model_name == binding.served_model_name
    assert packet.labels == ("preliminary", "diagnostic", "not_frozen")
    serialized = json.dumps(packet.to_payload(), sort_keys=True)
    assert "raw_body" not in serialized
    assert "rendered_messages" not in serialized


def test_matrix_runner_rejects_partial_terminal_mismatch(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    run_root = tmp_path / "run"
    run_fake_diagnostic_matrix(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        adapter=FakePhase0BAdapter(),
        run_root=run_root,
    )
    terminal_path = run_root / "staging" / "terminal-report.json"
    terminal_payload = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal_payload["committed_event_count"] = 479
    terminal_path.write_text(json.dumps(terminal_payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="record hash drift|terminal report"):
        verify_diagnostic_matrix_run(
            run_root=run_root,
            authorization=authorization,
            matrix_candidate=candidate,
        )
