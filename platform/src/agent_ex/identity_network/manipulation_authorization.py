"""Stage-one dispatch gate: explicit human rules, sources and service evidence.

No transport, live-host truth, automatic signal decision or human signature is
provided. The runner must independently check a fresh archive and actual service
before sending. A receipt constructed by software is not human authorization.
"""

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, _require_string, _require_timestamp, canonical_payload_hash
from .launch import StudyApprovalReceipt
from .manipulation_sources import validate_source_bound_manipulation_pack
from .materialization import _reject_unresolved
from .service_bridge import validate_service_bridge


def build_manipulation_preregistration(
    *,
    source_pack,
    candidate,
    created_at,
    sample_definition,
    analysis_plan,
    success_rule,
    no_signal_rule,
):
    """Record researcher-supplied rules without choosing or interpreting them."""
    pack = validate_source_bound_manipulation_pack(source_pack, candidate=candidate)
    _require_timestamp("criteria created_at", created_at)
    texts = dict(
        sample_definition=sample_definition,
        analysis_plan=analysis_plan,
        success_rule=success_rule,
        no_signal_rule=no_signal_rule,
    )
    for name, value in texts.items():
        _require_string(name, value)
    _reject_unresolved(texts)
    return ArtifactEnvelope.create(
        artifact_type="sis-manipulation-preregistration",
        schema_version="paper1.identity-network.manipulation-preregistration.v1",
        algorithm_id="sis-explicit-check-rules",
        algorithm_version="1.0.0",
        input_hashes={"fixtures": pack.input_hashes["fixtures"]},
        rng_provenance=(),
        payload={
            **texts,
            "created_at": created_at,
            "stage": pack.payload["stage"],
            "case_count": len(pack.payload["fixtures"]),
            "trial_count": len(pack.payload["trials"]),
            "case_sampling_seeds": tuple(
                {"case_id": f["case_id"], "sampling_seed": f["sampling_seed"]}
                for f in pack.payload["fixtures"]
            ),
            "trial_order_provenance": tuple(r.to_payload() for r in pack.rng_provenance),
            "criteria_authority": "researcher_statement_not_automatically_evaluated",
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
            "formal_parameter_authority": False,
            "dispatch_authorized": False,
        },
    )


def build_manipulation_authorization(
    *,
    source_pack,
    candidate,
    preregistration,
    bridge,
    service_evidence,
):
    """Build the exact stage-one target for a subsequent human dispatch receipt.

    Stage two cannot use this gate; it needs completed stage-one results and an
    independently verified no-signal transition, not just a receipt-shaped object.
    """
    pack = validate_source_bound_manipulation_pack(source_pack, candidate=candidate)
    if pack.payload["stage"] != "pure_label":
        raise ValueError("stage-two dispatch requires completed stage-one evidence")
    if not isinstance(preregistration, ArtifactEnvelope):
        raise ValueError("typed preregistration required")
    rules = _json_ready(preregistration.payload)
    if preregistration != build_manipulation_preregistration(
        source_pack=source_pack,
        candidate=candidate,
        **{
            k: rules[k]
            for k in (
                "created_at",
                "sample_definition",
                "analysis_plan",
                "success_rule",
                "no_signal_rule",
            )
        },
    ):
        raise ValueError("preregistration differs from exact samples and rules")
    if service_evidence.get("packet") != candidate:
        raise ValueError("service evidence belongs to another candidate")
    validate_service_bridge(bridge, **service_evidence)
    adapter = _json_ready(candidate.payload)["population_candidate"]["payload"]["execution_inputs"][
        "payload"
    ]["adapter_binding"]
    return ArtifactEnvelope.create(
        artifact_type="sis-manipulation-dispatch-authorization",
        schema_version="paper1.identity-network.manipulation-authorization.v1",
        algorithm_id="sis-stage-one-final-dispatch-target",
        algorithm_version="1.0.0",
        input_hashes={
            "candidate": candidate.output_hash,
            "source_pack": source_pack.output_hash,
            "pack": pack.output_hash,
            "preregistration": preregistration.output_hash,
            "service_bridge": bridge.output_hash,
            "service_start": bridge.input_hashes["service_start"],
            "adapter": adapter["record_hash"],
        },
        rng_provenance=(),
        payload={
            "stage": "pure_label",
            "case_count": len(pack.payload["fixtures"]),
            "trial_count": len(pack.payload["trials"]),
            "trial_inventory_hash": canonical_payload_hash(
                tuple(
                    {k: t[k] for k in ("trial_id", "prompt_hash", "sampling_seed")}
                    for t in pack.payload["trials"]
                )
            ),
            "generation_settings": pack.payload["generation_settings"],
            "endpoint": adapter["endpoint"],
            "served_model_name": adapter["served_model_name"],
            "archive_root": service_evidence["intent"].payload["archive_root"]
            + "/manipulation-pure-label",
            "failure_policy": "stop_without_automatic_retry_or_ambiguous_resend",
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
        },
    )


def validate_manipulation_dispatch_approval(auth, receipt, *, checked_at, **evidence):
    """Require the scoped human target after full replay, before any dispatch."""
    if not isinstance(auth, ArtifactEnvelope) or auth != build_manipulation_authorization(
        **evidence
    ):
        raise ValueError("manipulation authorization differs from full evidence replay")
    if not isinstance(receipt, StudyApprovalReceipt):
        raise ValueError("typed human dispatch approval required")
    receipt = StudyApprovalReceipt.from_payload(receipt.to_payload())
    if receipt.scope != "diagnostic_dispatch" or receipt.target_hash != auth.output_hash:
        raise ValueError("receipt does not approve this exact manipulation dispatch")
    approved = _require_timestamp("approved_at", receipt.approved_at)
    if not (
        _require_timestamp("preregistered_at", evidence["preregistration"].payload["created_at"])
        <= approved
        and _require_timestamp("service observed_at", evidence["bridge"].payload["observed_at"])
        <= approved
        <= _require_timestamp("checked_at", checked_at)
    ):
        raise ValueError("manipulation approval chronology is inconsistent")
