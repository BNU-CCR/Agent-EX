"""Fixed source projection and service-only candidate rebinding; no authority.

A pre-service draft may contain a declared placeholder start hash. That hash is
not approved by this projection and must never be used as observed evidence.
Real launch must independently check the actual start record and human receipt.
"""

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, _require_sha256, canonical_payload_hash
from ..parser import ParserLimits
from ..phase0b.contracts import DiagnosticAdapterBinding, DiagnosticAttemptPolicy
from ..state import PrivateUpdate
from .candidate import build_six_cell_candidate, validate_six_cell_candidate
from .materialization import build_population_execution_candidate
from .storage import StudyRunBinding


def project_pre_service_inputs(packet):
    """Bind every fixed source, excluding only the future service identity.

    Derived wrapper hashes that transitively include the start identity are replaced
    by their full validated content, not silently retained as pre-service references.
    """
    bindings = validate_six_cell_candidate(packet)
    payload = _json_ready(packet.payload)
    population = payload["population_candidate"]["payload"]
    execution = population["execution_inputs"]["payload"]
    adapter = dict(execution["adapter_binding"])
    del adapter["service_start_identity_hash"]
    del adapter["record_hash"]
    # Full validated source bodies preserve donor audit fields and all explicit
    # research choices; no result-dependent choice or legacy protocol rewrite.
    fixed_population = {k: v for k, v in population.items() if k != "execution_inputs"}
    fixed_execution = {**execution, "adapter_binding": adapter}
    fixed_bindings = tuple(
        {k: v for k, v in b.to_payload().items() if k not in {"record_hash", "common_inputs_hash"}}
        for b in bindings
    )
    return ArtifactEnvelope.create(
        artifact_type="sis-pre-service-inputs",
        schema_version="paper1.identity-network.pre-service-inputs.v1",
        algorithm_id="sis-fixed-sources-without-start-identity",
        algorithm_version="1.0.0",
        input_hashes={},
        rng_provenance=(),
        payload={
            "study_id": payload["study_id"],
            "population_sources": fixed_population,
            "execution_sources": fixed_execution,
            "schedule_source": payload["schedule_candidate"],
            "bindings": fixed_bindings,
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
            "formal_parameter_authority": False,
            "launch_authorized": False,
            "service_identity_authority": "not_observed",
        },
    )


def bind_candidate_service(packet, *, service_start_identity_hash):
    """Mechanically derive a new candidate for an explicit start hash.

    This is not a service verifier or run authorization. Callers must validate a real
    start record first, and the changed candidate requires its own final receipt.
    """
    _require_sha256("service_start_identity_hash", service_start_identity_hash)
    bindings = validate_six_cell_candidate(packet)
    population = _json_ready(packet.payload)["population_candidate"]["payload"]
    execution = population["execution_inputs"]["payload"]
    adapter = dict(execution["adapter_binding"])
    adapter["service_start_identity_hash"] = service_start_identity_hash
    adapter["record_hash"] = canonical_payload_hash(
        {k: v for k, v in adapter.items() if k != "record_hash"}
    )
    rebound_population = build_population_execution_candidate(
        binding=bindings[0],
        population_frame=ArtifactEnvelope.from_payload(population["population_frame"]),
        population_weights=tuple(population["population_weights"]),
        population_constraints=population["population_constraints"],
        population_tolerance=population["population_tolerance"],
        persona_template=ArtifactEnvelope.from_payload(population["persona_template"]),
        reason_family_by_agent=population["reason_family_by_agent"],
        initial_updates=tuple(PrivateUpdate.from_payload(u) for u in population["initial_updates"]),
        feed_capacity=execution["feed_capacity"],
        memory_window=execution["memory_window"],
        parser_limits=ParserLimits.from_payload(execution["parser_limits"]),
        generation_settings=execution["generation_settings"],
        model_seeds=tuple(execution["model_seeds"]),
        adapter_binding=DiagnosticAdapterBinding.from_payload(adapter),
        attempt_policy=DiagnosticAttemptPolicy.from_payload(execution["attempt_policy"]),
    )
    common = ArtifactEnvelope.from_payload(
        rebound_population.to_payload()["payload"]["execution_inputs"]
    )
    base_payload = bindings[0].to_payload()
    base_payload["common_inputs_hash"] = common.output_hash
    base_payload["record_hash"] = canonical_payload_hash(
        {k: v for k, v in base_payload.items() if k != "record_hash"}
    )
    rebound = build_six_cell_candidate(
        population_candidate=rebound_population,
        schedule_candidate=ArtifactEnvelope.from_payload(
            _json_ready(packet.payload)["schedule_candidate"]
        ),
        base_binding=StudyRunBinding.from_payload(base_payload),
    )
    if project_pre_service_inputs(rebound) != project_pre_service_inputs(packet):
        raise ValueError("service rebinding changed fixed candidate sources")
    return rebound
