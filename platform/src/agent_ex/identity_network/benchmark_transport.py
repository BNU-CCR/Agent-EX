"""Offline Stage-A prompt/wire candidate. Requires human renderer/runtime review.

Does not load a model, connect to a service, create a store or authorize dispatch.
The old quartet renderer is not silently substituted for frozen benchmark content.
"""

import hashlib
import json
from collections.abc import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, _require_sha256, canonical_payload_hash
from ..phase0b.vllm_event_adapter import Phase0BVllmEventAdapter, Phase0BVllmEventRequest
from .benchmark_trials import build_benchmark_trial_inventory
from .prompts import CONTROL

RENDERER = "sis.manipulation.benchmark-prompt-candidate.v1"


def build_benchmark_transport_candidate(
    *, benchmark, expected_hash, generation_settings, served_model_name, adapter_binding_hash
):
    """Encode explicit parameter candidates, not researcher-approved requests."""
    inventory = build_benchmark_trial_inventory(benchmark, expected_hash=expected_hash)
    if not isinstance(generation_settings, Mapping) or set(generation_settings) != {
        "temperature",
        "top_p",
        "max_tokens",
    }:
        raise ValueError("explicit generation parameter triple required")
    _require_sha256("adapter_binding_hash", adapter_binding_hash)
    # The endpoint below is an offline encoder fixture, not runtime authority.
    encoder = Phase0BVllmEventAdapter(
        "http://127.0.0.1:8000/v1/chat/completions", served_model_name=served_model_name
    )
    data = _json_ready(inventory.payload)
    cases = {case["case_id"]: case for case in benchmark["cases"]}
    aliases = {case_id: f"Member {i:03d}" for i, case_id in enumerate(cases, 1)}
    entries = []
    for trial in data["trials"]:
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
            {"role": "system", "content": CONTROL},
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
            }
        )
        for attempt_index in (1, 2, 3):
            request = Phase0BVllmEventRequest.create(
                event_id=event,
                attempt_index=attempt_index,
                prompt_hash=canonical_payload_hash(messages),
                rendered_messages=messages,
                generation_settings=dict(generation_settings),
                model_seed=trial["sampling_seed"],
                adapter_binding_hash=adapter_binding_hash,
            )
            requests.append(request.to_payload())
            wires.append(encoder._request_body(request))
        if len(set(wires)) != 1:
            raise ValueError("retry changed exact wire body")
        entries.append(
            {
                "trial_id": trial["trial_id"],
                "case_id": trial["case_id"],
                "attempt_requests": requests,
                "wire_body": wires[0].decode("utf-8"),
                "wire_hash": hashlib.sha256(wires[0]).hexdigest(),
            }
        )
    return ArtifactEnvelope.create(
        artifact_type="sis-benchmark-transport-candidate",
        schema_version="sis.manipulation.benchmark-transport-candidate.v1",
        algorithm_id="sis-offline-benchmark-wire-candidate",
        algorithm_version="1.0.0",
        input_hashes={
            "benchmark": expected_hash,
            "inventory": inventory.output_hash,
            "adapter": adapter_binding_hash,
        },
        rng_provenance=(),
        payload={
            "renderer_version": RENDERER,
            "renderer_approved": False,
            "runtime_approved": False,
            "stage": "pure_label",
            "entries": entries,
            "served_model_name": served_model_name,
            "generation_settings": dict(generation_settings),
            "dispatch_authorized": False,
            "cloud_launch_eligible": False,
            "formal_parameter_authority": False,
        },
    )
