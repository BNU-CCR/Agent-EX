"""Offline Stage-A prompt/wire candidate. Requires human renderer/runtime review.

Does not load a model, connect to a service, create a store or authorize dispatch.
The old quartet renderer is not silently substituted for frozen benchmark content.
"""

import hashlib
import json
from collections.abc import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, _require_sha256, canonical_payload_hash
from ..phase0b.vllm_event_adapter import Phase0BVllmEventRequest
from .benchmark_adapter import BenchmarkVllmAdapter, SAMPLING, SYSTEM
from .benchmark_trials import build_benchmark_trial_inventory

RENDERER = "sis.manipulation.benchmark-prompt.v2"


def build_benchmark_transport_candidate(
    *,
    benchmark,
    expected_hash,
    generation_settings,
    served_model_name,
    adapter_binding_hash,
    mode="stage-a",
):
    """Encode explicit parameter candidates, not researcher-approved requests."""
    inventory = build_benchmark_trial_inventory(benchmark, expected_hash=expected_hash)
    if not isinstance(generation_settings, Mapping) or canonical_payload_hash(
        generation_settings
    ) != canonical_payload_hash(SAMPLING):
        raise ValueError("explicit approved five-parameter sampling required")
    if mode not in {"stage-a", "preflight"}:
        raise ValueError("Stage-B dispatch is disabled")
    _require_sha256("adapter_binding_hash", adapter_binding_hash)
    effective_binding = canonical_payload_hash(
        {
            "runtime_binding": adapter_binding_hash,
            "sampling": dict(SAMPLING),
            "renderer": RENDERER,
            "system": SYSTEM,
            "mode": mode,
        }
    )
    # The endpoint below is an offline encoder fixture, not runtime authority.
    encoder = BenchmarkVllmAdapter(
        "http://127.0.0.1:8000/v1/chat/completions", served_model_name=served_model_name
    )
    data = _json_ready(inventory.payload)
    cases = {case["case_id"]: case for case in benchmark["cases"]}
    aliases = {case_id: f"Member {i:03d}" for i, case_id in enumerate(cases, 1)}
    entries = []
    for trial in data["trials"] if mode == "stage-a" else data["trials"][:2]:
        case = cases[trial["case_id"]]
        visible = {
            "persona_context": benchmark["persona_context"],
            "fact_card": benchmark["topic"]["fact_card"],
            "core_statement": benchmark["topic"]["statement"],
            "allowed_stance_labels": benchmark["topic"]["stance_mapping"],
            "focal_context": benchmark["focal_context"],
            "self_history": [],
            "self_group": trial["focal_group"],
            "social_messages": [
                {
                    "member_id": aliases[trial["case_id"]],
                    "source_group": trial["source_group"],
                    "source_message": case["source_message"],
                }
            ],
        }
        # reason/provenance are archive metadata, not a duplicate extra exposure.
        messages = (
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    visible, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            },
        )
        requests, wires = [], []
        event = "sis-benchmark-event-" + canonical_payload_hash(
            {
                "inventory_hash": inventory.output_hash,
                "trial_id": trial["trial_id"],
                "renderer": RENDERER,
                "served_model_name": served_model_name,
                "mode": mode,
                "effective_adapter_binding_hash": effective_binding,
            }
        )
        for attempt_index in (1, 2, 3):
            request = Phase0BVllmEventRequest.create(
                event_id=event,
                attempt_index=attempt_index,
                prompt_hash=canonical_payload_hash(messages),
                rendered_messages=messages,
                generation_settings={
                    key: SAMPLING[key] for key in ("temperature", "top_p", "max_tokens")
                },
                model_seed=trial["sampling_seed"],
                adapter_binding_hash=effective_binding,
            )
            requests.append(request.to_payload())
            wires.append(encoder._request_body(request))
        if len(set(wires)) != 1:
            raise ValueError("retry changed exact wire body")
        entries.append(
            {
                "trial_id": trial["trial_id"]
                if mode == "stage-a"
                else "preflight-" + trial["trial_id"],
                "case_id": trial["case_id"],
                "attempt_requests": requests,
                "wire_body": wires[0].decode("utf-8"),
                "wire_hash": hashlib.sha256(wires[0]).hexdigest(),
            }
        )
    return ArtifactEnvelope.create(
        artifact_type="sis-benchmark-transport-candidate",
        schema_version="sis.manipulation.benchmark-transport-candidate.v2",
        algorithm_id="sis-offline-benchmark-wire-candidate",
        algorithm_version="2.0.0",
        input_hashes={
            "benchmark": expected_hash,
            "inventory": inventory.output_hash,
            "adapter": adapter_binding_hash,
        },
        rng_provenance=(),
        payload={
            "renderer_version": RENDERER,
            "renderer_approved": True,
            "sampling_approved": True,
            "runtime_approved": False,
            "stage": "pure_label",
            "mode": mode,
            "effective_adapter_binding_hash": effective_binding,
            "entries": entries,
            "served_model_name": served_model_name,
            "generation_settings": dict(generation_settings),
            "dispatch_authorized": False,
            "cloud_launch_eligible": False,
            "formal_parameter_authority": False,
        },
    )


def replay_benchmark_transport_candidate(pack, benchmark, *, expected_hash):
    values = pack.payload
    rebuilt = build_benchmark_transport_candidate(
        benchmark=benchmark,
        expected_hash=expected_hash,
        generation_settings=values["generation_settings"],
        served_model_name=values["served_model_name"],
        adapter_binding_hash=pack.input_hashes["adapter"],
        mode=values["mode"],
    )
    if pack != rebuilt:
        raise ValueError("saved transport candidate differs from frozen derivation")
    return rebuilt
