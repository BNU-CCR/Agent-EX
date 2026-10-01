"""Candidate scheduling source lineage, using real local generators only."""

from copy import deepcopy
import math

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import FrozenSchedule
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.storage import StudyRunBinding
from test_identity_network_storage import setup


def arguments():
    return dict(
        matched_seed=17,
        agent_ids=tuple(f"agent-{i:04d}" for i in range(20)),
        sweep_count=2,
        attention_family="positive_truncated_lognormal",
        attention_parameters={
            "log_location": 0.0,
            "log_sigma": 0.5,
            "minimum": 0.1,
            "maximum": 5.0,
        },
        structural_lurker_probability=0.2,
        expression_beta_alpha=2.0,
        expression_beta_beta=4.0,
        expression_max_beta_attempts_per_agent=100,
        expression_correlation_mode="independent",
    )


def bound(artifact, cell=None):
    _, old, _ = setup(study_cells()[0] if cell is None else cell)
    return StudyRunBinding.create(
        cell=old.cell,
        matched_seed=old.matched_seed,
        groups=ArtifactEnvelope.from_payload(old.to_payload()["groups"]),
        aliases=old.aliases,
        node_agent_ids=old.node_agent_ids,
        topic_package=old.topic_package,
        schedule=FrozenSchedule.from_payload(artifact.to_payload()["payload"]["schedule"]),
        ws=old.ws,
        randomized=old.randomized,
        common_inputs_hash=old.common_inputs_hash,
    )


def rehash(artifact, payload):
    return ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        rng_provenance=artifact.rng_provenance,
        payload=payload,
    )


def test_explicit_schedule_source_bundle_cold_replays_and_binds_six_cells():
    from agent_ex.identity_network.schedule_sources import (
        build_schedule_candidate,
        validate_schedule_candidate,
    )

    candidate = build_schedule_candidate(**arguments())
    assert candidate == build_schedule_candidate(**arguments())
    payload = candidate.payload
    assert len(payload["schedule"]["slots"]) == 40
    assert payload["metadata"]["formal_parameter_authority"] is False
    assert payload["metadata"]["source_authority"] == "candidate_unattested"
    assert payload["expression"]["payload"]["attention_inputs_read"] == ()
    assert payload["attention"]["payload"]["opinion_inputs_read"] == ()
    weights = [a["weight"] for a in payload["attention"]["payload"]["agents"]]
    assert all(w > 0 for w in weights) and math.isclose(math.fsum(weights), 20)
    for cell in study_cells():
        binding = bound(candidate, cell)
        validate_schedule_candidate(candidate, binding)
        assert candidate.input_hashes["schedule"] == binding.schedule.schedule_hash
    assert (
        candidate.input_hashes["publish"]
        == ArtifactEnvelope.from_payload(candidate.to_payload()["payload"]["publish"]).output_hash
    )


@pytest.mark.parametrize(
    "part",
    (
        "attention",
        "expression",
        "activation",
        "publish",
        "schedule",
        "metadata",
        "parameters",
        "input_hashes",
    ),
)
def test_rehashed_scheduling_source_drift_is_rejected(part):
    from agent_ex.identity_network.schedule_sources import (
        build_schedule_candidate,
        validate_schedule_candidate,
    )

    original = build_schedule_candidate(**arguments())
    binding = bound(original)
    payload = deepcopy(original.to_payload()["payload"])
    if part == "attention":
        payload[part]["payload"]["agents"][0]["weight"] *= 2
    elif part == "expression":
        payload[part]["payload"]["agents"][0]["publish_probability"] = 1.0
    elif part in ("activation", "publish"):
        payload[part]["algorithm_version"] = "unexpected"
    elif part == "schedule":
        payload[part]["slots"][0]["publish_flag"] = not payload[part]["slots"][0]["publish_flag"]
    elif part == "metadata":
        payload[part]["formal_parameter_authority"] = True
    elif part == "parameters":
        payload[part]["sweep_count"] = 1
    changed = rehash(original, payload)
    if part == "input_hashes":
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
        validate_schedule_candidate(changed, binding)


def test_runtime_mismatch_rejected_before_rebuilding_sources(monkeypatch):
    from agent_ex.identity_network import schedule_sources

    original = schedule_sources.build_schedule_candidate(**arguments())
    payload = deepcopy(original.to_payload()["payload"])
    payload["runtime_provenance"]["python_version"] = "different-runtime"
    changed = rehash(original, payload)

    def forbidden_rebuild(**kwargs):
        raise AssertionError("must reject runtime mismatch before rebuilding")

    monkeypatch.setattr(schedule_sources, "build_schedule_candidate", forbidden_rebuild)
    with pytest.raises(ValueError, match="runtime"):
        schedule_sources.validate_schedule_candidate(changed, bound(original))


def test_rehashed_roster_order_cannot_rebind_a_different_schedule():
    from agent_ex.identity_network.schedule_sources import (
        build_schedule_candidate,
        validate_schedule_candidate,
    )

    original = build_schedule_candidate(**arguments())
    _, wrong, _ = setup(study_cells()[0], sweeps=2)
    with pytest.raises(ValueError, match="schedule"):
        validate_schedule_candidate(original, wrong)


@pytest.mark.parametrize(
    "field,value",
    (
        ("sweep_count", True),
        ("sweep_count", 0),
        ("expression_correlation_mode", "positive"),
        ("attention_family", "UNRESOLVED[SIS_PILOT_CONFIG]"),
        ("attention_parameters", {"log_sigma": "UNRESOLVED[SIS_PILOT_CONFIG]"}),
        ("agent_ids", ("agent-0000", "agent-0000")),
    ),
)
def test_source_candidate_rejects_incomplete_illegal_or_unresolved_parameters(field, value):
    from agent_ex.identity_network.schedule_sources import build_schedule_candidate

    kwargs = arguments()
    kwargs[field] = value
    with pytest.raises((ValueError, TypeError)):
        build_schedule_candidate(**kwargs)
