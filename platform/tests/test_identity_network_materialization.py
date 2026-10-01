"""Explicit candidate population/persona source replay; no model or filesystem I/O."""

from copy import deepcopy

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.execution_inputs import validate_execution_inputs
from test_identity_network_execution_inputs import inputs, rebind
from test_identity_network_storage import setup
from test_persona import member, template_artifact


def arguments(cell=None):
    _, binding, _ = setup(study_cells()[0] if cell is None else cell)
    _, execution = inputs(binding)
    execution.pop("persona_by_agent")
    donor = member()
    donor.pop("agent_id")
    frame = ArtifactEnvelope.create(
        artifact_type="sis-candidate-population-frame",
        schema_version="paper1.identity-network.population-frame.v1",
        algorithm_id="explicit-test-frame",
        algorithm_version="1.0.0",
        input_hashes={},
        rng_provenance=(),
        payload={"donors": (donor,), "metadata": {"source_kind": "synthetic_fixture"}},
    )
    return dict(
        **execution,
        population_frame=frame,
        population_weights=(20.0,),
        population_constraints={"marginals": {}, "joints": ()},
        population_tolerance=0,
        persona_template=template_artifact(),
        reason_family_by_agent={a: "explicit-test-family" for a in binding.node_agent_ids},
    )


def rebuild(artifact, payload):
    return ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        rng_provenance=artifact.rng_provenance,
        payload=payload,
    )


def test_demographic_reason_family_field_does_not_overwrite_reason_code_diagnostics():
    from agent_ex.identity_network.materialization import build_population_execution_candidate

    kwargs = arguments()
    frame = kwargs["population_frame"]
    payload = deepcopy(frame.to_payload()["payload"])
    payload["donors"][0]["fields"]["reason_family"] = "donor-audit-value"
    kwargs["population_frame"] = rebuild(frame, payload)
    candidate = build_population_execution_candidate(**kwargs)
    assert candidate.payload["group_balance"]["demographic"]["reason_family"]["blue"] == {
        '"donor-audit-value"': 10
    }
    assert candidate.payload["group_balance"]["reason_family"]["blue"] == {
        "explicit-test-family": 10
    }


def test_numeric_and_text_demographic_categories_remain_distinct_after_cold_replay():
    from collections import Counter
    from agent_ex.identity_network.materialization import (
        build_population_execution_candidate,
        validate_population_execution_candidate,
    )

    kwargs = arguments()
    frame = kwargs["population_frame"]
    payload = deepcopy(frame.to_payload()["payload"])
    first = payload["donors"][0]
    second = deepcopy(first)
    first["fields"]["audit_category"] = 1
    second["fields"]["audit_category"] = "1"
    second["donor_id"] = "d2"
    payload["donors"].append(second)
    kwargs["population_frame"] = rebuild(frame, payload)
    kwargs["population_weights"] = (10.0, 10.0)
    candidate = build_population_execution_candidate(**kwargs)
    common = ArtifactEnvelope.from_payload(candidate.to_payload()["payload"]["execution_inputs"])
    validate_population_execution_candidate(candidate, rebind(kwargs["binding"], common))
    totals = Counter()
    for counts in candidate.payload["group_balance"]["demographic"]["audit_category"].values():
        totals.update(counts)
    assert totals == {"1": 10, '"1"': 10}


def test_population_persona_materializer_replays_and_is_identical_in_six_cells():
    from agent_ex.identity_network.materialization import (
        build_population_execution_candidate,
        validate_population_execution_candidate,
    )

    family = []
    for cell in study_cells():
        kwargs = arguments(cell)
        candidate = build_population_execution_candidate(**kwargs)
        common = ArtifactEnvelope.from_payload(
            candidate.to_payload()["payload"]["execution_inputs"]
        )
        binding = rebind(kwargs["binding"], common)
        validate_execution_inputs(common, binding)
        validate_population_execution_candidate(candidate, binding)
        assert candidate.input_hashes["population_frame"] == kwargs["population_frame"].output_hash
        assert candidate.input_hashes["execution_inputs"] == common.output_hash
        assert candidate.payload["metadata"]["formal_parameter_authority"] is False
        assert candidate.payload["metadata"]["source_authority"] == "candidate_unattested"
        assert len(candidate.payload["rendered_personas"]) == 20
        assert all(
            p["payload"]["continuity_block"] == "" for p in candidate.payload["rendered_personas"]
        )
        assert all(p["payload"]["identity_block"] for p in candidate.payload["rendered_personas"])
        assert candidate.payload["group_balance"]["reason_family"]["blue"] == {
            "explicit-test-family": 10
        }
        assert candidate.payload["group_balance"]["reason_family"]["green"] == {
            "explicit-test-family": 10
        }
        assert len(set(common.payload["persona_by_agent"].values())) == 1
        family.append(candidate)
    assert len({a.output_hash for a in family}) == 1
    assert len({a.artifact_id for a in family}) == 1


@pytest.mark.parametrize(
    "change", ("rendered", "population", "initial", "diagnostics", "metadata", "hashes")
)
def test_rehashed_candidate_tampering_is_rejected(change):
    from agent_ex.identity_network.materialization import (
        build_population_execution_candidate,
        validate_population_execution_candidate,
    )

    kwargs = arguments()
    candidate = build_population_execution_candidate(**kwargs)
    payload = deepcopy(candidate.to_payload()["payload"])
    common = ArtifactEnvelope.from_payload(payload["execution_inputs"])
    binding = rebind(kwargs["binding"], common)
    if change == "rendered":
        payload["rendered_personas"][0]["payload"]["rendered_text"] = "arbitrary persona"
    elif change == "population":
        payload["population"]["payload"]["members"][0]["fields"]["gender"] = "changed"
    elif change == "initial":
        payload["initial_updates"][0]["reason"] = "changed reason"
    elif change == "diagnostics":
        payload["group_balance"]["reason_family"]["blue"]["explicit-test-family"] = 0
    elif change == "metadata":
        payload["metadata"]["formal_parameter_authority"] = True
    changed = rebuild(candidate, payload)
    if change == "hashes":
        changed = ArtifactEnvelope.create(
            artifact_type=changed.artifact_type,
            schema_version=changed.schema_version,
            algorithm_id=changed.algorithm_id,
            algorithm_version=changed.algorithm_version,
            input_hashes={},
            rng_provenance=(),
            payload=changed.payload,
        )
    with pytest.raises((ValueError, TypeError)):
        validate_population_execution_candidate(changed, binding)


@pytest.mark.parametrize(
    "change", ("weights", "unresolved", "reason_cover", "initial_cover", "roster")
)
def test_explicit_candidate_rejects_incomplete_or_unresolved_inputs(change):
    from agent_ex.identity_network.materialization import build_population_execution_candidate

    kwargs = arguments()
    if change == "weights":
        kwargs["population_weights"] = (19.0,)
    elif change == "unresolved":
        kwargs["population_tolerance"] = "UNRESOLVED[SIS_PILOT_CONFIG]"
    elif change == "reason_cover":
        kwargs["reason_family_by_agent"].pop("agent-0000")
    elif change == "initial_cover":
        kwargs["initial_updates"] = kwargs["initial_updates"][:-1]
    else:
        from agent_ex.state import PrivateUpdate

        kwargs["initial_updates"] = tuple(
            PrivateUpdate.create(
                topic_package=kwargs["binding"].topic_package,
                matched_seed=17,
                agent_id="foreign-" + u.agent_id,
                event_id=None,
                event_ordinal=None,
                sequence_index=0,
                stance_label=u.stance_label,
                reason=u.reason,
                confidence=None,
                published=True,
                source_attempt_id=None,
                mock_only=True,
            )
            for u in kwargs["initial_updates"]
        )
    with pytest.raises((ValueError, TypeError)):
        build_population_execution_candidate(**kwargs)
