"""Full common-source candidate binding; no launch, filesystem or model calls."""

from copy import deepcopy

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.identity_network.contracts import study_cells
from test_identity_network_execution_inputs import rebind
from test_identity_network_materialization import arguments as population_arguments, rebuild
from test_identity_network_schedule_sources import arguments as schedule_arguments, bound


def sources():
    from agent_ex.identity_network.materialization import build_population_execution_candidate
    from agent_ex.identity_network.schedule_sources import build_schedule_candidate

    schedule = build_schedule_candidate(**schedule_arguments())
    kwargs = population_arguments()
    kwargs["binding"] = bound(schedule)
    kwargs["model_seeds"] = tuple(17 for _ in kwargs["binding"].schedule.slots)
    population = build_population_execution_candidate(**kwargs)
    common = ArtifactEnvelope.from_payload(population.to_payload()["payload"]["execution_inputs"])
    return dict(
        population_candidate=population,
        schedule_candidate=schedule,
        base_binding=rebind(kwargs["binding"], common),
    )


def test_self_contained_candidate_derives_and_replays_exact_six_cell_bindings():
    from agent_ex.identity_network.candidate import (
        build_six_cell_candidate,
        validate_six_cell_candidate,
    )

    kwargs = sources()
    candidate = build_six_cell_candidate(**kwargs)
    bindings = validate_six_cell_candidate(ArtifactEnvelope.from_payload(candidate.to_payload()))
    assert tuple(b.cell for b in bindings) == study_cells()
    assert len({b.record_hash for b in bindings}) == 6
    assert len({b.common_inputs_hash for b in bindings}) == 1
    assert all(b.schedule == kwargs["base_binding"].schedule for b in bindings)
    assert all(b.groups == kwargs["base_binding"].groups for b in bindings)
    assert bindings[0].exposure_graph is None and bindings[3].exposure_graph is None
    assert bindings[1].exposure_graph == kwargs["base_binding"].randomized
    assert bindings[2].exposure_graph == kwargs["base_binding"].ws
    assert (
        candidate.input_hashes["population_candidate"] == kwargs["population_candidate"].output_hash
    )
    assert candidate.input_hashes["schedule_candidate"] == kwargs["schedule_candidate"].output_hash
    assert candidate.payload["metadata"]["formal_parameter_authority"] is False
    assert candidate.payload["metadata"]["launch_authorized"] is False


@pytest.mark.parametrize(
    "change", ("missing_cell", "duplicate_cell", "order", "common", "schedule", "metadata", "extra")
)
def test_full_candidate_rejects_rehashed_late_binding_or_source_drift(change):
    from agent_ex.identity_network.candidate import (
        build_six_cell_candidate,
        validate_six_cell_candidate,
    )

    candidate = build_six_cell_candidate(**sources())
    payload = deepcopy(candidate.to_payload()["payload"])
    if change == "missing_cell":
        payload["bindings"].pop()
    elif change == "duplicate_cell":
        payload["bindings"][5] = payload["bindings"][0]
    elif change == "order":
        payload["bindings"].reverse()
    elif change == "common":
        payload["population_candidate"]["payload"]["execution_inputs"]["payload"][
            "memory_window"
        ] = 99
    elif change == "schedule":
        slot = payload["schedule_candidate"]["payload"]["schedule"]["slots"][0]
        slot["publish_flag"] = not slot["publish_flag"]
    elif change == "metadata":
        payload["metadata"]["launch_authorized"] = True
    else:
        payload["unexpected"] = "field"
    with pytest.raises((ValueError, TypeError)):
        validate_six_cell_candidate(rebuild(candidate, payload))


def test_foreign_initial_reference_schedule_not_silently_adopted():
    from agent_ex.identity_network.candidate import build_six_cell_candidate
    from test_identity_network_storage import setup

    kwargs = sources()
    _, wrong, _ = setup(study_cells()[0], sweeps=2)
    kwargs["base_binding"] = rebind(
        wrong,
        ArtifactEnvelope.from_payload(
            kwargs["population_candidate"].to_payload()["payload"]["execution_inputs"]
        ),
    )
    with pytest.raises(ValueError):
        build_six_cell_candidate(**kwargs)


def test_valid_rehashed_late_cell_alias_mapping_cannot_differ_from_common_sources():
    from agent_ex.identity_network.candidate import (
        build_six_cell_candidate,
        validate_six_cell_candidate,
    )
    from agent_ex.identity_network.storage import StudyRunBinding

    candidate = build_six_cell_candidate(**sources())
    payload = deepcopy(candidate.to_payload()["payload"])
    old = StudyRunBinding.from_payload(payload["bindings"][-1])
    aliases = dict(old.aliases)
    first, second = old.node_agent_ids[:2]
    aliases[first], aliases[second] = aliases[second], aliases[first]
    changed = StudyRunBinding.create(
        cell=old.cell,
        matched_seed=old.matched_seed,
        groups=ArtifactEnvelope.from_payload(old.to_payload()["groups"]),
        aliases=aliases,
        node_agent_ids=old.node_agent_ids,
        topic_package=old.topic_package,
        schedule=old.schedule,
        ws=old.ws,
        randomized=old.randomized,
        common_inputs_hash=old.common_inputs_hash,
    )
    payload["bindings"][-1] = changed.to_payload()
    hashes = {**candidate.input_hashes, changed.cell.cell_id: changed.record_hash}
    forged = ArtifactEnvelope.create(
        artifact_type=candidate.artifact_type,
        schema_version=candidate.schema_version,
        algorithm_id=candidate.algorithm_id,
        algorithm_version=candidate.algorithm_version,
        input_hashes=hashes,
        rng_provenance=(),
        payload=payload,
    )
    with pytest.raises(ValueError, match="shared source/binding"):
        validate_six_cell_candidate(forged)
