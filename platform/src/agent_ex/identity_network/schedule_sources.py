"""Explicit SIS scheduling candidates over unchanged shared generators.

Source replay requires the recorded Python/random runtime, not a particular OS.
These are candidate inputs, not formal parameter choices or launch receipts.
"""

from ..artifacts import ArtifactEnvelope
from ..domain import FrozenSchedule, _json_ready, canonical_payload_hash
from ..schedule import (
    _runtime_provenance,
    build_activation_schedule,
    build_attention_artifact,
    build_expression_artifact,
    build_publish_schedule,
)
from .materialization import _reject_unresolved
from .storage import StudyRunBinding


SCHEMA = "paper1.identity-network.schedule-candidate.v1"


def build_schedule_candidate(
    *,
    matched_seed,
    agent_ids,
    sweep_count,
    attention_family,
    attention_parameters,
    structural_lurker_probability,
    expression_beta_alpha,
    expression_beta_beta,
    expression_max_beta_attempts_per_agent,
    expression_correlation_mode,
):
    """Build full attention → activation + independent expression → publish lineage."""
    if type(agent_ids) is not tuple:
        raise TypeError("explicit ordered agent tuple required")
    parameters = {
        "matched_seed": matched_seed,
        "agent_ids": agent_ids,
        "sweep_count": sweep_count,
        "attention_family": attention_family,
        "attention_parameters": attention_parameters,
        "structural_lurker_probability": structural_lurker_probability,
        "expression_beta_alpha": expression_beta_alpha,
        "expression_beta_beta": expression_beta_beta,
        "expression_max_beta_attempts_per_agent": expression_max_beta_attempts_per_agent,
        "expression_correlation_mode": expression_correlation_mode,
    }
    _reject_unresolved(parameters)
    attention = build_attention_artifact(
        agent_ids=agent_ids,
        matched_seed=matched_seed,
        family=attention_family,
        parameters=attention_parameters,
        mock_only=True,
    )
    expression = build_expression_artifact(
        agent_ids=agent_ids,
        matched_seed=matched_seed,
        structural_lurker_probability=structural_lurker_probability,
        beta_alpha=expression_beta_alpha,
        beta_beta=expression_beta_beta,
        max_beta_attempts_per_agent=expression_max_beta_attempts_per_agent,
        correlation_mode=expression_correlation_mode,
        mock_only=True,
    )
    activation = build_activation_schedule(
        attention,
        matched_seed=matched_seed,
        sweep_count=sweep_count,
        mock_only=True,
    )
    publish = build_publish_schedule(
        attention,
        activation,
        expression,
        matched_seed=matched_seed,
        mock_only=True,
    )
    schedule = FrozenSchedule.from_payload(_json_ready(publish.payload["frozen_schedule"]))
    runtime = _runtime_provenance()
    return ArtifactEnvelope.create(
        artifact_type="sis-schedule-candidate",
        schema_version=SCHEMA,
        algorithm_id="sis-shared-scheduling-source-materializer",
        algorithm_version="1.0.0",
        input_hashes={
            "parameters": canonical_payload_hash(parameters),
            "attention": attention.output_hash,
            "expression": expression.output_hash,
            "activation": activation.output_hash,
            "publish": publish.output_hash,
            "schedule": schedule.schedule_hash,
        },
        rng_provenance=(),
        payload={
            "parameters": parameters,
            "runtime_provenance": runtime,
            "attention": attention.to_payload(),
            "expression": expression.to_payload(),
            "activation": activation.to_payload(),
            "publish": publish.to_payload(),
            "schedule": schedule.to_payload(),
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
                "source_authority": "candidate_unattested",
            },
        },
    )


def validate_schedule_candidate(artifact, binding):
    """Rebuild all source artifacts and bind the exact frozen SIS schedule."""
    if not isinstance(artifact, ArtifactEnvelope) or not isinstance(binding, StudyRunBinding):
        raise TypeError("typed schedule candidate and SIS binding required")
    payload = _json_ready(artifact.payload)
    fields = {
        "parameters",
        "runtime_provenance",
        "attention",
        "expression",
        "activation",
        "publish",
        "schedule",
        "metadata",
    }
    if type(payload) is not dict or set(payload) != fields:
        raise ValueError("schedule candidate fields mismatch")
    if payload["runtime_provenance"] != _runtime_provenance():
        raise ValueError("schedule source runtime mismatch; use recorded Python/random runtime")
    parameters = payload["parameters"]
    expected_fields = {
        "matched_seed",
        "agent_ids",
        "sweep_count",
        "attention_family",
        "attention_parameters",
        "structural_lurker_probability",
        "expression_beta_alpha",
        "expression_beta_beta",
        "expression_max_beta_attempts_per_agent",
        "expression_correlation_mode",
    }
    if type(parameters) is not dict or set(parameters) != expected_fields:
        raise ValueError("explicit scheduling parameter fields mismatch")
    if (
        parameters["matched_seed"] != binding.matched_seed
        or tuple(parameters["agent_ids"]) != binding.node_agent_ids
        or parameters["sweep_count"] != binding.schedule.sweep_count
        or canonical_payload_hash(payload["schedule"])
        != canonical_payload_hash(binding.schedule.to_payload())
    ):
        raise ValueError("schedule source candidate differs from exact SIS seed/roster/schedule")
    expected = build_schedule_candidate(
        **{**parameters, "agent_ids": tuple(parameters["agent_ids"])}
    )
    if artifact != expected:
        raise ValueError("schedule source candidate differs from full source replay")
