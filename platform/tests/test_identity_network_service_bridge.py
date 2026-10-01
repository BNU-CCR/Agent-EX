"""Source-bound fresh service observations; synthetic evidence only."""

from dataclasses import replace

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.calibration.environment import EnvironmentLock, PreliminaryEnvironmentInspection
from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.candidate import build_six_cell_candidate
from agent_ex.identity_network.launch import build_service_launch_intent, StudyApprovalReceipt
from agent_ex.identity_network.materialization import build_population_execution_candidate
from agent_ex.identity_network.service_inputs import bind_candidate_service
from agent_ex.phase0b.contracts import DiagnosticAdapterBinding
from test_calibration_environment import valid_observation
from test_identity_network_candidate import sources
from test_identity_network_execution_inputs import rebind
from test_identity_network_materialization import arguments
from test_phase0b_service_bridge import _fixture


def fixture(*, dtype="bfloat16", extra_arguments=()):
    from agent_ex.identity_network.service_bridge import build_service_vacancy

    source = sources()
    python = source["schedule_candidate"].payload["runtime_provenance"]["python_version"]
    observation = replace(
        valid_observation(),
        python_version=python,
        git_commit="c" * 40,
        serve_arguments=valid_observation().serve_arguments + ("--dtype", dtype) + extra_arguments,
    )
    lock = EnvironmentLock.create(observation, authorization_hash="a" * 64)
    original_adapter = arguments()["adapter_binding"].to_payload()
    updates = dict(
        model_revision=lock.model_revision,
        tokenizer_revision=lock.tokenizer_revision,
        chat_template_hash=lock.chat_template_hash,
        package_lock_hash=lock.package_lock_hash,
        image_identity_hash=lock.image_identity_hash,
        environment_lock_hash=lock.record_hash,
    )
    adapter = {**original_adapter, **updates}
    adapter["record_hash"] = canonical_payload_hash(
        {k: v for k, v in adapter.items() if k != "record_hash"}
    )
    values = arguments()
    values.update(
        binding=source["base_binding"],
        adapter_binding=DiagnosticAdapterBinding.from_payload(adapter),
        model_seeds=tuple(17 for _ in source["base_binding"].schedule.slots),
    )
    population = build_population_execution_candidate(**values)
    common = ArtifactEnvelope.from_payload(population.to_payload()["payload"]["execution_inputs"])
    packet = build_six_cell_candidate(
        population_candidate=population,
        schedule_candidate=source["schedule_candidate"],
        base_binding=rebind(values["binding"], common),
    )
    inspection = PreliminaryEnvironmentInspection.create(
        python_version=python,
        package_lock=observation.package_lock,
        wheel_entries=tuple(
            replace(w, sha256=observation.vllm_identity.wheel_hash)
            for w in _fixture()["inspection"].wheel_entries
        ),
        torch_source="fresh-vllm-environment",
    )
    config = _fixture()["service_config"]
    intent = build_service_launch_intent(
        packet=packet,
        source_commit="c" * 40,
        source_bundle_hash="a" * 64,
        source_bundle_size=17,
        service_config=config,
        archive_root="/root/autodl-tmp/sis-synthetic",
    )
    approval = StudyApprovalReceipt.create(
        target_hash=intent.output_hash,
        scope="service_start",
        researcher="Synthetic",
        approved_at="2026-10-01T00:00:00Z",
    )
    vacancy = build_service_vacancy(
        intent=intent,
        inspection=inspection,
        host_identity_hash="b" * 64,
        observed_at="2026-10-01T00:01:00Z",
        loopback_listener_absent=True,
        gpu_compute_process_observation_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    start = {
        **_fixture()["new_start"],
        "manifest_hash": intent.output_hash,
        "binding_hash": inspection.record_hash,
        "started_at": "2026-10-01T00:02:00Z",
    }
    rehash(start)
    packet = bind_candidate_service(packet, service_start_identity_hash=start["record_hash"])
    return dict(
        packet=packet,
        intent=intent,
        approval=approval,
        environment_lock=lock,
        current_observation=observation,
        inspection=inspection,
        vacancy=vacancy,
        new_start=start,
        current_host_identity_hash="b" * 64,
        observed_at="2026-10-01T00:03:00Z",
    )


def rehash(record):
    record["record_hash"] = canonical_payload_hash(
        {k: v for k, v in record.items() if k != "record_hash"}
    )


def test_bridge_binds_actual_start_and_runtime_to_intent_with_no_dispatch_authority():
    from agent_ex.identity_network.service_bridge import (
        build_service_bridge,
        validate_service_bridge,
    )

    values = fixture()
    bridge = build_service_bridge(**values)
    validate_service_bridge(ArtifactEnvelope.from_payload(bridge.to_payload()), **values)
    assert bridge.payload["dispatch_authorized"] is False
    assert bridge.input_hashes["service_start"] == values["new_start"]["record_hash"]
    assert (
        bridge.payload["current_environment"]["authorization_hash"] == values["intent"].output_hash
    )


@pytest.mark.parametrize(
    "drift",
    ("host", "start-manifest", "start-config", "time", "receipt", "model", "source", "package"),
)
def test_bridge_rejects_rehashed_foreign_service_and_runtime_evidence(drift):
    from agent_ex.identity_network.service_bridge import build_service_bridge

    values = fixture()
    if drift == "host":
        values["current_host_identity_hash"] = "e" * 64
    elif drift.startswith("start-"):
        values["new_start"]["manifest_hash" if drift == "start-manifest" else "model_path"] = (
            "e" * 64 if drift == "start-manifest" else "/different/model"
        )
        rehash(values["new_start"])
    elif drift == "time":
        values["observed_at"] = "2026-10-01T00:00:30Z"
    elif drift == "receipt":
        values["approval"] = StudyApprovalReceipt.create(
            target_hash=values["intent"].output_hash,
            scope="diagnostic_dispatch",
            researcher="Synthetic",
            approved_at="2026-10-01T00:00:00Z",
        )
    elif drift == "model":
        values["current_observation"] = replace(
            values["current_observation"], model_revision="e" * 40
        )
    elif drift == "source":
        values["current_observation"] = replace(values["current_observation"], git_commit="e" * 40)
    else:
        values["current_observation"] = replace(
            values["current_observation"],
            vllm_identity=replace(values["current_observation"].vllm_identity, wheel_hash="e" * 64),
        )
    with pytest.raises((ValueError, TypeError)):
        build_service_bridge(**values)


@pytest.mark.parametrize(
    "argument", ("--dtype=float16", "--port=8001", "--host=0.0.0.0", "--served-model-name=foreign")
)
def test_equals_form_cannot_override_protected_service_flags(argument):
    from agent_ex.identity_network.service_bridge import build_service_bridge

    with pytest.raises(ValueError, match="serve arguments"):
        build_service_bridge(**fixture(extra_arguments=(argument,)))


def test_service_requires_explicit_bf16_even_when_profile_matches():
    from agent_ex.identity_network.service_bridge import build_service_bridge

    with pytest.raises(ValueError, match="serve arguments"):
        build_service_bridge(**fixture(dtype="float16"))


@pytest.mark.parametrize("kind", ("port", "gpu"))
def test_vacancy_refuses_busy_resources(kind):
    from agent_ex.identity_network.service_bridge import build_service_vacancy

    values = fixture()
    with pytest.raises(ValueError):
        build_service_vacancy(
            intent=values["intent"],
            inspection=values["inspection"],
            host_identity_hash="b" * 64,
            observed_at="2026-10-01T00:01:00Z",
            loopback_listener_absent=kind != "port",
            gpu_compute_process_observation_hash="e" * 64
            if kind == "gpu"
            else "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
