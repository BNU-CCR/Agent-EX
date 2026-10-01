"""Cell-independent, explicit candidate inputs for SIS execution preparation.

This is neither a formal freeze nor a cloud/run authorization. Population
attention/expression provenance remains a separate materializer responsibility.
"""

from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, _require_int
from ..feed import _require_capacity
from ..memory import _require_window
from ..parser import ParserLimits
from ..phase0b.contracts import DiagnosticAdapterBinding, DiagnosticAttemptPolicy
from ..phase0b.vllm_event_adapter import Phase0BVllmEventRequest
from ..state import PrivateUpdate


SCHEMA = "paper1.identity-network.execution-inputs.v1"


def _common_identity(binding):
    return {
        "matched_seed": binding.matched_seed,
        "topic_package_hash": binding.topic_package.package_hash,
        "group_artifact_hash": binding.groups.artifact_hash,
        "schedule_hash": binding.schedule.schedule_hash,
        "node_agent_ids": binding.node_agent_ids,
        "aliases": binding.aliases,
        "ws_hash": binding.ws.output_hash,
        "randomized_hash": binding.randomized.output_hash,
    }


def build_execution_inputs(
    *,
    binding,
    persona_by_agent,
    initial_updates,
    feed_capacity,
    memory_window,
    parser_limits,
    generation_settings,
    model_seeds,
    adapter_binding,
    attempt_policy,
):
    from .storage import StudyRunBinding

    if not isinstance(binding, StudyRunBinding):
        raise TypeError("typed SIS binding required")
    if not isinstance(persona_by_agent, Mapping) or set(persona_by_agent) != set(
        binding.node_agent_ids
    ):
        raise ValueError("persona must exactly cover the bound agent roster")
    if any(type(p) is not str or not p.strip() for p in persona_by_agent.values()):
        raise ValueError("each rendered persona must be nonempty text")
    if type(initial_updates) is not tuple or any(
        not isinstance(u, PrivateUpdate) for u in initial_updates
    ):
        raise TypeError("initial updates must be a typed tuple")
    updates = {u.agent_id: PrivateUpdate.from_payload(u.to_payload()) for u in initial_updates}
    if len(updates) != len(initial_updates) or set(updates) != set(binding.node_agent_ids):
        raise ValueError("initial updates must exactly cover the bound agent roster")
    stances = binding.to_payload()["groups"]["payload"]["initial_stances"]
    for u in updates.values():
        if (
            u.matched_seed != binding.matched_seed
            or u.topic_package_id != binding.topic_package.topic_id
            or u.topic_package_hash != binding.topic_package.package_hash
            or u.stance_label != stances[u.agent_id]
            or u.event_id is not None
            or u.event_ordinal is not None
            or u.sequence_index != 0
            or u.source_attempt_id is not None
            or u.published is not True
            or u.confidence is not None
        ):
            raise ValueError("common initial updates must bind round-0/topic/seed/groups")
    _require_capacity(feed_capacity)
    _require_window(memory_window)
    for obj, expected in (
        (parser_limits, ParserLimits),
        (adapter_binding, DiagnosticAdapterBinding),
        (attempt_policy, DiagnosticAttemptPolicy),
    ):
        if not isinstance(obj, expected):
            raise TypeError("typed parser, adapter and retry policy required")
        expected.from_payload(obj.to_payload())
    if type(model_seeds) is not tuple or len(model_seeds) != len(binding.schedule.slots):
        raise ValueError("model seeds must exactly cover the event schedule")
    for seed in model_seeds:
        _require_int("model_seed", seed)
    # Reuse the actual request contract to validate the explicit generation settings.
    request = Phase0BVllmEventRequest.create(
        event_id="sis-candidate-settings-validation",
        attempt_index=1,
        prompt_hash="a" * 64,
        rendered_messages=({"role": "user", "content": "Configuration validation only."},),
        generation_settings=generation_settings,
        model_seed=model_seeds[0],
        adapter_binding_hash=adapter_binding.record_hash,
    )
    payload = {
        "common_identity": _common_identity(binding),
        "persona_by_agent": dict(persona_by_agent),
        "initial_updates": tuple(updates[a].to_payload() for a in binding.node_agent_ids),
        "feed_capacity": feed_capacity,
        "memory_window": memory_window,
        "parser_limits": parser_limits.to_payload(),
        "generation_settings": request.generation_settings,
        "model_seeds": model_seeds,
        "adapter_binding": adapter_binding.to_payload(),
        "attempt_policy": attempt_policy.to_payload(),
        "explicit_consistency_instruction": False,
        "metadata": {
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
            "formal_parameter_authority": False,
        },
    }
    return ArtifactEnvelope.create(
        artifact_type="sis-execution-inputs",
        schema_version=SCHEMA,
        algorithm_id="sis-common-execution-inputs",
        algorithm_version="1.0.0",
        input_hashes={},
        rng_provenance=(),
        payload=payload,
    )


def validate_execution_inputs(artifact, binding):
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("typed execution-input artifact required")
    payload = _json_ready(artifact.payload)
    fields = {
        "common_identity",
        "persona_by_agent",
        "initial_updates",
        "feed_capacity",
        "memory_window",
        "parser_limits",
        "generation_settings",
        "model_seeds",
        "adapter_binding",
        "attempt_policy",
        "explicit_consistency_instruction",
        "metadata",
    }
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("execution-input artifact fields mismatch")
    expected = build_execution_inputs(
        binding=binding,
        persona_by_agent=payload["persona_by_agent"],
        initial_updates=tuple(PrivateUpdate.from_payload(u) for u in payload["initial_updates"]),
        feed_capacity=payload["feed_capacity"],
        memory_window=payload["memory_window"],
        parser_limits=ParserLimits.from_payload(payload["parser_limits"]),
        generation_settings=payload["generation_settings"],
        model_seeds=tuple(payload["model_seeds"]),
        adapter_binding=DiagnosticAdapterBinding.from_payload(payload["adapter_binding"]),
        attempt_policy=DiagnosticAttemptPolicy.from_payload(payload["attempt_policy"]),
    )
    if artifact != expected or artifact.output_hash != binding.common_inputs_hash:
        raise ValueError("execution-input artifact does not bind current SIS common inputs")
