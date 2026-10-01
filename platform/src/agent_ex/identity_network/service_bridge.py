"""Metadata-only fresh SIS service evidence; no service actions or dispatch.

Observed inputs must come from the actual host collector. Pure validation cannot
prove a live process or truthful observations, preserve old archives, or safely
stop an unknown process. Occupied resources fail closed; never kill to proceed.
"""

from ..artifacts import ArtifactEnvelope
from ..calibration.environment import (
    EnvironmentLock,
    EnvironmentObservation,
    PreliminaryEnvironmentInspection,
)
from ..domain import (
    _json_ready,
    _require_int,
    _require_sha256,
    _require_timestamp,
    canonical_payload_hash,
)
from ..phase0b.service_bridge import _SERVICE_START_FIELDS, _verified_record
from .launch import SERVICE_CONFIG_FIELDS, StudyApprovalReceipt, validate_service_launch_intent
from .service_inputs import project_pre_service_inputs


EMPTY_GPU_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
RUNTIME_FIELDS = (
    "python_version",
    "package_lock_hash",
    "model_repository",
    "model_revision",
    "model_artifacts_hash",
    "tokenizer_repository",
    "tokenizer_revision",
    "tokenizer_artifacts_hash",
    "chat_template_hash",
    "rendered_non_thinking_hash",
    "vllm_identity_hash",
    "image_identity_hash",
    "serve_arguments_hash",
)


def build_service_vacancy(
    *,
    intent,
    inspection,
    host_identity_hash,
    observed_at,
    loopback_listener_absent,
    gpu_compute_process_observation_hash,
):
    if (
        not isinstance(intent, ArtifactEnvelope)
        or intent.schema_version != "paper1.identity-network.service-launch-intent.v1"
    ):
        raise TypeError("typed SIS service intent required")
    if not isinstance(inspection, PreliminaryEnvironmentInspection):
        raise TypeError("typed preliminary inspection required")
    inspection = PreliminaryEnvironmentInspection.from_payload(inspection.to_payload())
    _require_sha256("host_identity_hash", host_identity_hash)
    _require_timestamp("observed_at", observed_at)
    if (
        loopback_listener_absent is not True
        or gpu_compute_process_observation_hash != EMPTY_GPU_HASH
    ):
        raise ValueError("port8000 and GPU must be observed vacant before starting")
    return ArtifactEnvelope.create(
        artifact_type="sis-service-vacancy",
        schema_version="paper1.identity-network.service-vacancy.v1",
        algorithm_id="sis-pre-start-resource-observation",
        algorithm_version="1.0.0",
        input_hashes={"intent": intent.output_hash, "inspection": inspection.record_hash},
        rng_provenance=(),
        payload={
            "host_identity_hash": host_identity_hash,
            "observed_at": observed_at,
            "loopback_listener_absent": True,
            "gpu_compute_process_observation_hash": EMPTY_GPU_HASH,
            "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
        },
    )


def build_service_bridge(
    *,
    packet,
    intent,
    approval,
    environment_lock,
    current_observation,
    inspection,
    vacancy,
    new_start,
    current_host_identity_hash,
    observed_at,
):
    validate_service_launch_intent(intent, packet)
    if not isinstance(approval, StudyApprovalReceipt):
        raise TypeError("typed service-start approval required")
    approval = StudyApprovalReceipt.from_payload(approval.to_payload())
    if approval.scope != "service_start" or approval.target_hash != intent.output_hash:
        raise ValueError("current SIS intent service approval required")
    if not isinstance(environment_lock, EnvironmentLock) or not isinstance(
        current_observation, EnvironmentObservation
    ):
        raise TypeError("typed environment lock and current observation required")
    environment_lock = EnvironmentLock.from_payload(environment_lock.to_payload())
    current_lock = EnvironmentLock.create(
        current_observation, authorization_hash=intent.output_hash
    )
    if not isinstance(inspection, PreliminaryEnvironmentInspection) or not isinstance(
        vacancy, ArtifactEnvelope
    ):
        raise TypeError("typed inspection and vacancy observation required")
    inspection = PreliminaryEnvironmentInspection.from_payload(inspection.to_payload())
    v = _json_ready(vacancy.payload)
    if vacancy != build_service_vacancy(
        intent=intent,
        inspection=inspection,
        host_identity_hash=v["host_identity_hash"],
        observed_at=v["observed_at"],
        loopback_listener_absent=v["loopback_listener_absent"],
        gpu_compute_process_observation_hash=v["gpu_compute_process_observation_hash"],
    ):
        raise ValueError("vacancy differs from bound source inspection")
    _require_sha256("current_host_identity_hash", current_host_identity_hash)
    if current_host_identity_hash != v["host_identity_hash"]:
        raise ValueError("service observations are from different hosts")
    start = _verified_record(
        "SIS service start",
        new_start,
        _SERVICE_START_FIELDS,
        "paper1.calibration.service-start-identity.v1",
        judge_metadata=False,
    )
    _require_int("service pid", start["pid"], minimum=1)
    if (
        type(start["proc_start_time"]) is not str
        or not start["proc_start_time"].isdigit()
        or int(start["proc_start_time"]) <= 0
    ):
        raise ValueError("explicit service proc start tick required")
    if (
        start["mode"] != "start-first"
        or start["generation"] != "0001"
        or start["manifest_hash"] != intent.output_hash
        or start["binding_kind"] != "preliminary-inspection"
        or start["binding_hash"] != inspection.record_hash
        or any(start[k] != intent.payload["service_config"][k] for k in SERVICE_CONFIG_FIELDS)
    ):
        raise ValueError("service start differs from current intent/config/inspection")
    start_time = _require_timestamp("started_at", start["started_at"])
    if not (
        _require_timestamp("approved_at", approval.approved_at) <= start_time
        and _require_timestamp("vacancy time", v["observed_at"]) < start_time
        and start_time <= _require_timestamp("observed_at", observed_at)
    ):
        raise ValueError("service observation chronology is inconsistent")
    if (
        current_observation.git_commit != intent.payload["source_commit"]
        or current_observation.git_dirty
        or any(getattr(current_lock, k) != getattr(environment_lock, k) for k in RUNTIME_FIELDS)
        or inspection.python_version != current_lock.python_version
        or canonical_payload_hash(tuple(p.to_payload() for p in inspection.package_lock))
        != current_lock.package_lock_hash
    ):
        raise ValueError("current source/runtime differs from fixed environment profile")
    wheel = next(w for w in inspection.wheel_entries if w.name.casefold() == "vllm")
    if (
        wheel.version != current_lock.vllm_identity.version
        or wheel.sha256 != current_lock.vllm_identity.wheel_hash
    ):
        raise ValueError("inspection wheel differs from current runtime")
    adapter = _json_ready(packet.payload)["population_candidate"]["payload"]["execution_inputs"][
        "payload"
    ]["adapter_binding"]
    expected = {
        "environment_lock_hash": environment_lock.record_hash,
        "model_repository": current_lock.model_repository,
        "model_revision": current_lock.model_revision,
        "tokenizer_revision": current_lock.tokenizer_revision,
        "chat_template_hash": current_lock.chat_template_hash,
        "package_lock_hash": current_lock.package_lock_hash,
        "image_identity_hash": current_lock.image_identity_hash,
        "vllm_version": current_lock.vllm_identity.version,
        "service_start_identity_hash": start["record_hash"],
    }
    if any(adapter[k] != value for k, value in expected.items()):
        raise ValueError("candidate adapter differs from actual service/runtime evidence")
    if current_lock.health_check.endpoint != "http://127.0.0.1:8000/health":
        raise ValueError("fresh health evidence must be for port8000")
    args = current_lock.serve_arguments
    for flag, value in (
        ("--host", "127.0.0.1"),
        ("--port", "8000"),
        ("--served-model-name", adapter["served_model_name"]),
        ("--dtype", "bfloat16"),
    ):
        positions = [i for i, item in enumerate(args) if item == flag]
        if (
            any(item.startswith(flag + "=") for item in args)
            or len(positions) != 1
            or positions[0] + 1 >= len(args)
            or args[positions[0] + 1] != value
        ):
            raise ValueError("current serve arguments differ from candidate endpoint/model")
    fixed = project_pre_service_inputs(packet)
    return ArtifactEnvelope.create(
        artifact_type="sis-service-bridge",
        schema_version="paper1.identity-network.service-bridge.v1",
        algorithm_id="sis-fresh-service-evidence-binding",
        algorithm_version="1.0.0",
        input_hashes={
            "candidate": packet.output_hash,
            "intent": intent.output_hash,
            "approval": approval.record_hash,
            "environment_lock": environment_lock.record_hash,
            "current_environment": current_lock.record_hash,
            "vacancy": vacancy.output_hash,
            "inspection": inspection.record_hash,
            "service_start": start["record_hash"],
        },
        rng_provenance=(),
        payload={
            "fixed_inputs_hash": fixed.output_hash,
            "host_identity_hash": current_host_identity_hash,
            "observed_at": observed_at,
            "service_start": start,
            "current_environment": current_lock.to_payload(),
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
        },
    )


def validate_service_bridge(bridge, **evidence):
    if not isinstance(bridge, ArtifactEnvelope) or bridge != build_service_bridge(**evidence):
        raise ValueError("service bridge differs from full evidence replay")
