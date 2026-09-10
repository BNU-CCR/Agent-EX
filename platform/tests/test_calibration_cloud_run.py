"""Authorization and execution facade for real Phase 0A-1 cloud probes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from agent_ex.calibration.cloud_run import (
    AmbiguousCloudDispatchError,
    CloudRunManifest,
    build_cloud_probe_report,
    build_cloud_run_manifest,
    execute_cloud_probe,
    load_cloud_run_artifacts,
    mark_cloud_probe_terminal,
    reconstruct_cloud_projection,
    resume_cloud_probe,
    seal_cloud_probe_report,
)
import agent_ex.calibration.cloud_run as cloud_run_module
from agent_ex.calibration.environment import EnvironmentDriftError, EnvironmentLock
from agent_ex.calibration.store import ProbeRunStore
from agent_ex.calibration.vllm_adapter import VllmProbeAdapter
from agent_ex.calibration.runner import ProbeRunCrash
from agent_ex.calibration.specification import load_probe_specification
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload
from test_calibration_environment import mutate_observation, valid_observation
from test_calibration_gates import algorithm, required_challenges
from test_calibration_review import review_policy
from test_calibration_report import complete_bundle
from test_calibration_runner import policy as runtime_policy
from test_calibration_vllm_adapter import FakeVllmServer


GROUP_NAMES = {
    "probe_specification",
    "runtime_policy",
    "semantic_review_policy",
    "candidate_manifest",
    "credential_boundary",
    "archive_declaration",
}


def _record(schema_version: str, **values: object) -> dict[str, object]:
    content = {"schema_version": schema_version, **values}
    return {**content, "record_hash": canonical_payload_hash(content)}


def approved_run_artifacts_payload() -> dict[str, object]:
    gate = algorithm(required_challenges())
    semantic = replace(
        review_policy(),
        classifier_id=gate.classifier_id,
        classifier_version=gate.classifier_version,
        classifier_hash=gate.classifier_hash,
    )
    runtime = runtime_policy()
    specification_payload = probe_spec_payload()
    specification_payload["replicates"] = [
        {"replicate_id": index, "requested_seed": 100 + index} for index in range(4)
    ]
    specification_payload["policy_hashes"] = {
        "gate_algorithm": gate.record_hash,
        "semantic_review_policy": semantic.record_hash,
        "runtime_policy": runtime.record_hash,
    }
    specification = load_probe_specification(specification_payload)
    observation = valid_observation()
    model_artifacts_hash = canonical_payload_hash(
        tuple(
            item.to_payload()
            for item in sorted(observation.model_artifacts, key=lambda item: item.relative_path)
        )
    )
    tokenizer_artifacts_hash = canonical_payload_hash(
        tuple(item.to_payload() for item in observation.tokenizer_artifacts)
    )
    groups = {
        "probe_specification": _record(
            "paper1.calibration.approved-specification.v1",
            specification=specification.to_payload(),
            gate_algorithm=gate.to_payload(),
        ),
        "runtime_policy": runtime.to_payload(),
        "semantic_review_policy": semantic.to_payload(),
        "candidate_manifest": _record(
            "paper1.calibration.candidate-manifest.v1",
            metadata={
                "calibration_only": True,
                "formal_parameter_authority": False,
                "research_parameter_status": "not_frozen",
            },
            model_repository="Qwen/Qwen3-8B",
            model_revision="b968826d9c46dd6066d109eabc6255188de91218",
            tokenizer_repository="Qwen/Qwen3-8B",
            tokenizer_revision="b968826d9c46dd6066d109eabc6255188de91218",
            vllm_version="0.23.0",
            endpoint="http://127.0.0.1:8000/v1/chat/completions",
            served_model_name="qwen3-8b-paper1",
            chat_template_hash=observation.chat_template_hash,
            rendered_non_thinking_hash=observation.rendered_non_thinking_hash,
            model_artifacts_hash=model_artifacts_hash,
            tokenizer_artifacts_hash=tokenizer_artifacts_hash,
            vllm_wheel_hash=observation.vllm_identity.wheel_hash,
            image_repository=observation.image_identity.repository,
            image_digest=observation.image_identity.digest,
            serve_arguments=list(observation.serve_arguments),
            generation_settings={
                "temperature": 0.7,
                "top_p": 0.8,
                "max_tokens": 128,
                "request_seed": "probe_case.requested_seed",
            },
        ),
        "credential_boundary": _record(
            "paper1.calibration.credential-boundary.v1",
            metadata={
                "calibration_only": True,
                "formal_parameter_authority": False,
            },
            injection_channel="ssh-agent-and-host-environment",
            credential_values_archived=False,
        ),
        "archive_declaration": _record(
            "paper1.calibration.archive-declaration.v1",
            metadata={
                "calibration_only": True,
                "formal_parameter_authority": False,
            },
            archive_uri="/root/autodl-tmp/agent-ex/phase0a1/probe-001",
            raw_artifacts_in_git=False,
        ),
    }
    group_hashes = {name: group["record_hash"] for name, group in groups.items()}
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.approved-cloud-artifacts.v1",
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "artifact_groups": groups,
        "approved_group_hashes": group_hashes,
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def approved_artifacts():
    return load_cloud_run_artifacts(approved_run_artifacts_payload())


def environment_lock_for(packet: dict[str, object]) -> EnvironmentLock:
    return EnvironmentLock.create(
        valid_observation(),
        authorization_hash=packet["record_hash"],  # type: ignore[arg-type]
    )


def test_cloud_run_requires_all_six_bound_artifact_groups() -> None:
    payload = approved_run_artifacts_payload()
    del payload["artifact_groups"]["semantic_review_policy"]  # type: ignore[index]

    with pytest.raises(ValueError, match="six artifact groups"):
        load_cloud_run_artifacts(payload)


def test_cloud_run_rejects_any_unresolved_marker() -> None:
    payload = approved_run_artifacts_payload()
    payload["artifact_groups"]["runtime_policy"]["timeout_seconds"] = (  # type: ignore[index]
        "UNRESOLVED[P1_TIMEOUT_RETRY]"
    )

    with pytest.raises(ValueError, match="UNRESOLVED"):
        load_cloud_run_artifacts(payload)


def test_run_manifest_requires_environment_lock_after_six_group_approval() -> None:
    artifacts = approved_artifacts()

    with pytest.raises(ValueError, match="environment lock"):
        build_cloud_run_manifest(artifacts, environment_lock=None)


def test_cloud_run_manifest_binds_816_case_inventory_and_round_trips() -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    lock = environment_lock_for(packet)

    manifest = build_cloud_run_manifest(artifacts, environment_lock=lock)

    assert manifest.case_count == 816
    assert manifest.case_family_counts == {
        "continuity": 576,
        "identity": 96,
        "topic_quality": 144,
    }
    assert manifest.environment_lock_hash == lock.record_hash
    assert manifest.approved_artifacts_hash == artifacts.record_hash
    assert CloudRunManifest.from_payload(manifest.to_payload()) == manifest


def test_cloud_run_manifest_rejects_a_lock_from_another_approval() -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    stale_lock = EnvironmentLock.create(valid_observation(), authorization_hash="f" * 64)

    with pytest.raises(ValueError, match="after six-group approval"):
        build_cloud_run_manifest(artifacts, environment_lock=stale_lock)


def test_cloud_run_artifact_packet_rejects_group_or_top_hash_drift() -> None:
    payload = approved_run_artifacts_payload()
    changed = deepcopy(payload)
    changed["artifact_groups"]["candidate_manifest"]["served_model_name"] = "wrong"  # type: ignore[index]
    with pytest.raises(ValueError, match="record_hash"):
        load_cloud_run_artifacts(changed)

    changed = deepcopy(payload)
    changed["approved_group_hashes"]["runtime_policy"] = "f" * 64  # type: ignore[index]
    changed["record_hash"] = canonical_payload_hash(
        {key: value for key, value in changed.items() if key != "record_hash"}
    )
    with pytest.raises(ValueError, match="approved_group_hashes"):
        load_cloud_run_artifacts(changed)


def test_cloud_run_manifest_rejects_candidate_environment_mismatch() -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    observation = replace(valid_observation(), rendered_non_thinking_hash="f" * 64)
    lock = EnvironmentLock.create(
        observation,
        authorization_hash=packet["record_hash"],  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="rendered_non_thinking_hash"):
        build_cloud_run_manifest(artifacts, environment_lock=lock)


def test_resume_rejects_environment_lock_drift() -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    lock = environment_lock_for(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=lock)
    changed = mutate_observation(valid_observation(), "chat_template_text")

    with pytest.raises(EnvironmentDriftError, match="chat_template_text"):
        resume_cloud_probe(
            manifest=manifest,
            run_artifacts=artifacts,
            environment_lock=lock,
            current_environment=changed,
        )


def test_cloud_facade_cannot_accept_formal_engine_types() -> None:
    with pytest.raises(TypeError, match="VllmProbeAdapter"):
        execute_cloud_probe(run_artifacts=approved_artifacts(), adapter=object())


def test_cloud_facade_persists_each_validated_attempt_before_advancing(
    tmp_path: Path,
) -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    lock = environment_lock_for(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=lock)
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest.to_payload())
    server = FakeVllmServer(port=8000)
    adapter = VllmProbeAdapter(
        server.endpoint,
        expected_model="qwen3-8b-paper1",
        model_revision=valid_observation().model_revision,
        tokenizer_repository=valid_observation().tokenizer_repository,
        tokenizer_revision=valid_observation().tokenizer_revision,
        runtime_version=valid_observation().vllm_identity.version,
        chat_template_hash=valid_observation().chat_template_hash,
    )
    try:
        projection = execute_cloud_probe(
            run_artifacts=artifacts,
            environment_lock=lock,
            current_environment=valid_observation(),
            manifest=manifest,
            adapter=adapter,
            store=store,
            stop_after_attempts=1,
        )
    finally:
        server.close()

    assert len(projection.attempts) == 1
    assert len(store.attempt_hashes) == 1
    stored = json.loads(
        (store.root / "staging" / "attempts" / f"{store.attempt_hashes[0]}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["probe_attempt"] == projection.attempts[0].to_payload()
    assert stored["transport_evidence"]["request_hash"] == (
        projection.attempts[0].request.record_hash
    )
    reviews = store._load_records(  # noqa: SLF001
        store.root / "staging" / "reviews", "review"
    )
    schemas = {record["schema_version"] for record in reviews.values()}
    assert schemas == {
        "paper1.calibration.cloud-dispatch-intent.v1",
        "paper1.calibration.cloud-dispatch-resolution.v1",
    }
    assert len(server.requests) == 1


class _FailIfSecondRequestAdapter(VllmProbeAdapter):
    def __init__(self, endpoint: str) -> None:
        observation = valid_observation()
        super().__init__(
            endpoint,
            expected_model="qwen3-8b-paper1",
            model_revision=observation.model_revision,
            tokenizer_repository=observation.tokenizer_repository,
            tokenizer_revision=observation.tokenizer_revision,
            runtime_version=observation.vllm_identity.version,
            chat_template_hash=observation.chat_template_hash,
        )
        self.calls = 0

    def generate(self, request, *, timeout_seconds=None):
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("terminal failure must stop before a second request")
        return super().generate(request, timeout_seconds=timeout_seconds)


def test_irreversible_runtime_failure_becomes_terminal_incomplete(
    tmp_path: Path,
) -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    lock = environment_lock_for(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=lock)
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest.to_payload())
    server = FakeVllmServer(port=8000)
    server.status = 500
    server.body = b'{"error":"internal"}'
    adapter = _FailIfSecondRequestAdapter(server.endpoint)
    try:
        projection = execute_cloud_probe(
            run_artifacts=artifacts,
            environment_lock=lock,
            current_environment=valid_observation(),
            manifest=manifest,
            adapter=adapter,
            store=store,
        )
    finally:
        server.close()

    assert "runtime_failed" in projection.case_statuses.values()
    assert adapter.calls == 1
    assert build_cloud_probe_report(store).status == "incomplete"


class _CrashAfterOneAdapter(_FailIfSecondRequestAdapter):
    def generate(self, request, *, timeout_seconds=None):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("controlled client crash")
        return VllmProbeAdapter.generate(self, request, timeout_seconds=timeout_seconds)


def test_unexpected_adapter_crash_keeps_recoverable_prefix(tmp_path: Path) -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    lock = environment_lock_for(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=lock)
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest.to_payload())
    server = FakeVllmServer(port=8000)
    adapter = _CrashAfterOneAdapter(server.endpoint)
    try:
        with pytest.raises(ProbeRunCrash, match="validated evidence"):
            execute_cloud_probe(
                run_artifacts=artifacts,
                environment_lock=lock,
                current_environment=valid_observation(),
                manifest=manifest,
                adapter=adapter,
                store=store,
            )
    finally:
        server.close()

    assert len(store.attempt_hashes) == 1
    recovered = reconstruct_cloud_projection(
        ProbeRunStore.open(tmp_path / "run"),
        run_artifacts=artifacts,
        manifest=manifest,
    )
    assert len(recovered.attempts) == 1
    assert recovered.attempts[0].request.request_id == next(iter(adapter._evidence))  # noqa: SLF001
    resumed_server = FakeVllmServer(port=8000)
    resumed_adapter = _FailIfSecondRequestAdapter(resumed_server.endpoint)
    try:
        resumed = resume_cloud_probe(
            manifest=manifest,
            run_artifacts=artifacts,
            environment_lock=lock,
            current_environment=valid_observation(),
            projection=None,
            adapter=resumed_adapter,
            store=ProbeRunStore.open(tmp_path / "run"),
            stop_after_attempts=1,
        )
    finally:
        resumed_server.close()
    assert len(resumed.attempts) == 2
    assert len(resumed_server.requests) == 1
    with pytest.raises(RuntimeError, match="recoverable staging"):
        build_cloud_probe_report(store)


def test_power_loss_after_response_never_reissues_indeterminate_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    lock = environment_lock_for(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=lock)
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest.to_payload())
    server = FakeVllmServer(port=8000)
    adapter = _FailIfSecondRequestAdapter(server.endpoint)

    def lose_power_before_attempt_append(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt("simulated hard power loss")

    monkeypatch.setattr(cloud_run_module, "_persist_projection", lose_power_before_attempt_append)
    try:
        with pytest.raises(KeyboardInterrupt, match="hard power loss"):
            execute_cloud_probe(
                run_artifacts=artifacts,
                environment_lock=lock,
                current_environment=valid_observation(),
                manifest=manifest,
                adapter=adapter,
                store=store,
                stop_after_attempts=1,
            )
    finally:
        server.close()

    assert len(server.requests) == 1
    assert len(store.attempt_hashes) == 0
    resumed_server = FakeVllmServer(port=8000)
    resumed_adapter = _FailIfSecondRequestAdapter(resumed_server.endpoint)
    try:
        with pytest.raises(AmbiguousCloudDispatchError, match="indeterminate"):
            resume_cloud_probe(
                manifest=manifest,
                run_artifacts=artifacts,
                environment_lock=lock,
                current_environment=valid_observation(),
                adapter=resumed_adapter,
                store=ProbeRunStore.open(tmp_path / "run"),
                stop_after_attempts=1,
            )
    finally:
        resumed_server.close()
    assert resumed_server.requests == []


def test_seal_rejects_bundle_not_rebuilt_from_this_store(tmp_path: Path) -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    lock = environment_lock_for(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=lock)
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest.to_payload())
    server = FakeVllmServer(port=8000)
    try:
        execute_cloud_probe(
            run_artifacts=artifacts,
            environment_lock=lock,
            current_environment=valid_observation(),
            manifest=manifest,
            adapter=_FailIfSecondRequestAdapter(server.endpoint),
            store=store,
            stop_after_attempts=1,
        )
    finally:
        server.close()

    with pytest.raises(ValueError, match="projection differs"):
        seal_cloud_probe_report(
            store,
            bundle=complete_bundle(),
            run_artifacts=artifacts,
            manifest=manifest,
        )


def _store_with_manifest(tmp_path: Path) -> tuple[ProbeRunStore, CloudRunManifest]:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=environment_lock_for(packet))
    return ProbeRunStore.create(tmp_path / "run", manifest=manifest.to_payload()), manifest


def test_terminal_incomplete_store_builds_audit_report_without_candidate(
    tmp_path: Path,
) -> None:
    store, manifest = _store_with_manifest(tmp_path)
    mark_cloud_probe_terminal(
        store,
        manifest=manifest,
        status="incomplete",
        selected_candidate=None,
        reason="runtime_budget_exhausted",
    )

    report = build_cloud_probe_report(store)

    assert report.status == "incomplete"
    assert report.selected_candidate is None


def test_terminal_complete_store_allows_predeclared_no_candidate(tmp_path: Path) -> None:
    store, manifest = _store_with_manifest(tmp_path)
    mark_cloud_probe_terminal(
        store,
        manifest=manifest,
        status="complete",
        selected_candidate=None,
        reason="all_topic_candidates_failed_predeclared_gates",
    )

    report = build_cloud_probe_report(store)

    assert report.status == "complete"
    assert report.selected_candidate is None


def test_recoverable_staging_store_cannot_build_or_seal_report(tmp_path: Path) -> None:
    packet = approved_run_artifacts_payload()
    artifacts = load_cloud_run_artifacts(packet)
    manifest = build_cloud_run_manifest(artifacts, environment_lock=environment_lock_for(packet))
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest.to_payload())

    with pytest.raises(RuntimeError, match="recoverable staging"):
        build_cloud_probe_report(store)
    with pytest.raises(TypeError, match="ProbeBundle"):
        seal_cloud_probe_report(
            store,
            bundle=None,
            run_artifacts=artifacts,
            manifest=manifest,
        )
