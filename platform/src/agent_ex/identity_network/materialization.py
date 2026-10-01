"""Replayable candidate population/persona inputs, not a source or run approval.

The frame and round-0 values are explicit researcher inputs. This wrapper proves
their mechanical derivation, not donor authenticity or reason-family coding.
Attention/expression/schedule source replay remains a separate boundary.
"""

from collections import Counter
from collections.abc import Mapping
import json

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready
from ..parser import ParserLimits
from ..persona import render_persona
from ..population import build_population_artifact
from ..phase0b.contracts import DiagnosticAdapterBinding, DiagnosticAttemptPolicy
from ..state import PrivateUpdate
from .execution_inputs import build_execution_inputs, validate_execution_inputs
from .storage import StudyRunBinding


SCHEMA = "paper1.identity-network.population-execution-candidate.v1"


def _reject_unresolved(value):
    if isinstance(value, str) and "UNRESOLVED[" in value:
        raise ValueError("candidate inputs must be explicit, not UNRESOLVED")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_unresolved(key)
            _reject_unresolved(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _reject_unresolved(item)


def _group_balance(binding, members, reason_families):
    result = {"demographic": {}}
    fields = sorted({field for m in members for field in m["fields"]})
    # JSON-encoded category keys preserve the types of extra donor audit fields;
    # the six visible persona fields are strings, but legacy donors allow more.
    for name in fields:
        groups = {}
        for group in ("blue", "green"):
            counts = Counter()
            for member in members:
                agent = member["agent_id"]
                if binding.groups.group_for(agent) == group:
                    value = member["fields"].get(name)
                    category = json.dumps(
                        _json_ready(value),
                        sort_keys=True,
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                    counts[category] += 1
            groups[group] = dict(sorted(counts.items()))
        result["demographic"][name] = groups
    result["reason_family"] = {
        group: dict(
            sorted(
                Counter(
                    reason_families[m["agent_id"]]
                    for m in members
                    if binding.groups.group_for(m["agent_id"]) == group
                ).items()
            )
        )
        for group in ("blue", "green")
    }
    return result


def build_population_execution_candidate(
    *,
    binding,
    population_frame,
    population_weights,
    population_constraints,
    population_tolerance,
    persona_template,
    reason_family_by_agent,
    initial_updates,
    feed_capacity,
    memory_window,
    parser_limits,
    generation_settings,
    model_seeds,
    adapter_binding,
    attempt_policy,
):
    """Materialize source-audited common inputs without defaults, files or HTTP."""
    if not isinstance(binding, StudyRunBinding):
        raise TypeError("typed SIS binding required")
    for artifact in (population_frame, persona_template):
        if not isinstance(artifact, ArtifactEnvelope):
            raise TypeError("typed frame and persona artifacts required")
        ArtifactEnvelope.from_payload(artifact.to_payload())
    if (
        population_frame.artifact_type != "sis-candidate-population-frame"
        or population_frame.schema_version != "paper1.identity-network.population-frame.v1"
        or not isinstance(population_frame.payload, Mapping)
        or set(population_frame.payload) != {"donors", "metadata"}
    ):
        raise ValueError("explicit SIS population frame schema required")
    _reject_unresolved(
        (
            population_frame.payload,
            population_weights,
            population_constraints,
            population_tolerance,
            persona_template.payload,
            reason_family_by_agent,
        )
    )
    if (
        not isinstance(reason_family_by_agent, Mapping)
        or set(reason_family_by_agent) != set(binding.node_agent_ids)
        or any(type(f) is not str or not f.strip() for f in reason_family_by_agent.values())
    ):
        raise ValueError("explicit reason-family labels must exactly cover the roster")
    population = build_population_artifact(
        donors=population_frame.payload["donors"],
        weights=population_weights,
        n=len(binding.node_agent_ids),
        matched_seed=binding.matched_seed,
        input_artifact_hash=population_frame.output_hash,
        constraints=population_constraints,
        tolerance=population_tolerance,
        mock_only=True,
    )
    members = population.payload["members"]
    if set(m["agent_id"] for m in members) != set(binding.node_agent_ids):
        raise ValueError("materialized population must exactly cover SIS roster")
    personas = tuple(
        render_persona(
            persona_template, member, {"identity_present": True, "continuity_present": False}
        )
        for member in members
    )
    common = build_execution_inputs(
        binding=binding,
        persona_by_agent={
            m["agent_id"]: p.payload["rendered_text"]
            for m, p in zip(members, personas, strict=True)
        },
        initial_updates=initial_updates,
        feed_capacity=feed_capacity,
        memory_window=memory_window,
        parser_limits=parser_limits,
        generation_settings=generation_settings,
        model_seeds=model_seeds,
        adapter_binding=adapter_binding,
        attempt_policy=attempt_policy,
    )
    payload = {
        "population_frame": population_frame.to_payload(),
        "population_weights": tuple(population_weights),
        "population_constraints": population_constraints,
        "population_tolerance": population_tolerance,
        "population": population.to_payload(),
        "persona_template": persona_template.to_payload(),
        "rendered_personas": tuple(p.to_payload() for p in personas),
        "initial_updates": common.payload["initial_updates"],
        "reason_family_by_agent": dict(reason_family_by_agent),
        "group_balance": _group_balance(binding, members, reason_family_by_agent),
        "execution_inputs": common.to_payload(),
        "metadata": {
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
            "formal_parameter_authority": False,
            "source_authority": "candidate_unattested",
        },
    }
    return ArtifactEnvelope.create(
        artifact_type="sis-population-execution-candidate",
        schema_version=SCHEMA,
        algorithm_id="sis-population-persona-source-materializer",
        algorithm_version="1.0.0",
        input_hashes={
            "population_frame": population_frame.output_hash,
            "persona_template": persona_template.output_hash,
            "execution_inputs": common.output_hash,
        },
        rng_provenance=(),
        payload=payload,
    )


def validate_population_execution_candidate(artifact, binding):
    """Cold replay full population/persona derivation; compare all evidence."""
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("typed population execution candidate required")
    payload = _json_ready(artifact.payload)
    fields = {
        "population_frame",
        "population_weights",
        "population_constraints",
        "population_tolerance",
        "population",
        "persona_template",
        "rendered_personas",
        "initial_updates",
        "reason_family_by_agent",
        "group_balance",
        "execution_inputs",
        "metadata",
    }
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("population execution candidate fields mismatch")
    common = ArtifactEnvelope.from_payload(payload["execution_inputs"])
    validate_execution_inputs(common, binding)
    execution = _json_ready(common.payload)
    expected = build_population_execution_candidate(
        binding=binding,
        population_frame=ArtifactEnvelope.from_payload(payload["population_frame"]),
        population_weights=tuple(payload["population_weights"]),
        population_constraints=payload["population_constraints"],
        population_tolerance=payload["population_tolerance"],
        persona_template=ArtifactEnvelope.from_payload(payload["persona_template"]),
        reason_family_by_agent=payload["reason_family_by_agent"],
        initial_updates=tuple(PrivateUpdate.from_payload(u) for u in payload["initial_updates"]),
        feed_capacity=execution["feed_capacity"],
        memory_window=execution["memory_window"],
        parser_limits=ParserLimits.from_payload(execution["parser_limits"]),
        generation_settings=execution["generation_settings"],
        model_seeds=tuple(execution["model_seeds"]),
        adapter_binding=DiagnosticAdapterBinding.from_payload(execution["adapter_binding"]),
        attempt_policy=DiagnosticAttemptPolicy.from_payload(execution["attempt_policy"]),
    )
    if artifact != expected:
        raise ValueError("population execution candidate differs from full source replay")
