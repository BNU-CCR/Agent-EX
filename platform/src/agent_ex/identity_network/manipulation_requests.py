"""Source-derived immutable Stage-A transport inventory; no dispatch or state writes.

The v1 quartet path is a contract fixture, not the proposed 240-request candidate.
Cold replay occurs once at entry; the returned immutable requests are reusable.
"""

import hashlib

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, canonical_payload_hash
from ..parser import ParserLimits
from ..phase0b.contracts import DiagnosticAdapterBinding, DiagnosticAttemptPolicy
from ..phase0b.vllm_event_adapter import Phase0BVllmEventAdapter, Phase0BVllmEventRequest
from ..topic import TopicPackage
from .manipulation_authorization import validate_manipulation_dispatch_approval
from .preflight_cli import build_preflight_request, parse_preflight_request
from .dispatch import _strict_json


SCHEMA = "paper1.identity-network.manipulation-request-plan.v1"


def build_manipulation_request_plan(*, auth, receipt, evidence, checked_at):
    """Replay approval and complete sources, then derive every frozen trial once."""
    validate_manipulation_dispatch_approval(auth, receipt, checked_at=checked_at, **evidence)
    candidate = _json_ready(evidence["candidate"].payload)
    common = candidate["population_candidate"]["payload"]["execution_inputs"]["payload"]
    adapter = DiagnosticAdapterBinding.from_payload(common["adapter_binding"])
    policy = DiagnosticAttemptPolicy.from_payload(common["attempt_policy"])
    limits = ParserLimits.from_payload(common["parser_limits"])
    topic = TopicPackage.from_payload(candidate["bindings"][1]["topic_package"])
    # Authorization replay has already cold-derived this exact inner pack.
    pack = ArtifactEnvelope.from_payload(_json_ready(evidence["source_pack"].payload)["pack"])
    settings = _json_ready(pack.payload["generation_settings"])
    generation = {
        "temperature": float(settings["temperature"]),
        "top_p": float(settings["top_p"]),
        "max_tokens": settings["max_tokens"],
    }
    encoder = Phase0BVllmEventAdapter(adapter.endpoint, served_model_name=adapter.served_model_name)
    entries = []
    for trial in pack.payload["trials"]:
        event_id = "sis-check-event-" + canonical_payload_hash(
            {"authorization": auth.output_hash, "trial_id": trial["trial_id"]}
        )
        request = Phase0BVllmEventRequest.create(
            event_id=event_id,
            attempt_index=1,
            prompt_hash=trial["prompt_hash"],
            rendered_messages=tuple(dict(m) for m in trial["messages"]),
            generation_settings=generation,
            model_seed=trial["sampling_seed"],
            adapter_binding_hash=adapter.record_hash,
        )
        wire = encoder._request_body(request)  # Pure encoder; no connection is created.
        entries.append(
            {
                "trial_id": trial["trial_id"],
                "request": request.to_payload(),
                "wire_payload": _strict_json(wire.decode("utf-8")),
                "wire_sha256": hashlib.sha256(wire).hexdigest(),
            }
        )
    if len({e["request"]["request_id"] for e in entries}) != len(entries):
        raise ValueError("manipulation request identity collision")
    return ArtifactEnvelope.create(
        artifact_type="sis-manipulation-request-plan",
        schema_version=SCHEMA,
        algorithm_id="sis-source-bound-check-transport-inventory",
        algorithm_version="1.0.0",
        input_hashes={
            "authorization": auth.output_hash,
            "receipt": receipt.record_hash,
            "candidate": evidence["candidate"].output_hash,
            "pack": pack.output_hash,
            "adapter": adapter.record_hash,
            "attempt_policy": policy.record_hash,
            "parser_limits": limits.record_hash,
            "topic": topic.package_hash,
        },
        rng_provenance=(),
        payload={
            "preflight_request": build_preflight_request(
                auth=auth, receipt=receipt, evidence=evidence
            ),
            "entries": tuple(entries),
            "adapter_binding": adapter.to_payload(),
            "attempt_policy": policy.to_payload(),
            "parser_limits": limits.to_payload(),
            "topic_package": topic.to_payload(),
            "source_generation_settings": settings,
            "stage": "pure_label",
            "trial_count": len(entries),
            "failure_policy": "stop_without_automatic_retry_or_ambiguous_resend",
            "dispatch_authorized": False,
            "cloud_launch_eligible": False,
            "inventory_contract": "quartet-v1-local-contract-only",
            "formal_parameter_authority": False,
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
        },
    )


def validate_manipulation_request_plan(plan, *, checked_at):
    """Cold derive the complete saved plan; return immutable ordered requests."""
    if not isinstance(plan, ArtifactEnvelope):
        raise ValueError("typed manipulation request plan required")
    payload = _json_ready(plan.payload)
    rebuilt = build_manipulation_request_plan(
        **parse_preflight_request(payload["preflight_request"]), checked_at=checked_at
    )
    if plan != rebuilt:
        raise ValueError("manipulation requests differ from approved source derivation")
    requests = []
    for entry in payload["entries"]:
        values = entry["request"]
        values["rendered_messages"] = tuple(values["rendered_messages"])
        requests.append(Phase0BVllmEventRequest(**values))
    return tuple(requests)
