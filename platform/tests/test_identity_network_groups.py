from collections import Counter

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.groups import GroupContext, build_group_assignment


STANCES = {f"agent-{i:03}": i // 4 - 1 for i in range(12)}


def test_six_cells_have_distinct_new_identity():
    cells = study_cells()
    assert tuple(c.cell_id for c in cells) == (
        "SIS-A0-B0",
        "SIS-A0-B1",
        "SIS-A0-B2",
        "SIS-A1-B0",
        "SIS-A1-B1",
        "SIS-A1-B2",
    )
    assert {c.salience for c in cells} == {"blind", "salient"}
    assert {c.network for c in cells} == {"no_social", "randomized", "clustered_ws"}


def test_exact_orthogonality_replay_and_immutable_lookup():
    artifact = build_group_assignment(initial_stances=STANCES, matched_seed=7)
    reverse = build_group_assignment(
        initial_stances=dict(reversed(tuple(STANCES.items()))), matched_seed=7
    )
    assert artifact == reverse
    context = GroupContext.from_artifact(artifact)
    for stance in set(STANCES.values()):
        counts = Counter(context.group_for(a) for a, s in STANCES.items() if s == stance)
        assert counts == {"blue": 2, "green": 2}
    with pytest.raises(TypeError):
        context.memberships["agent-000"] = "green"
    with pytest.raises(ValueError, match="unknown"):
        context.group_for("missing")


@pytest.mark.parametrize("stances", [{}, {"a": 1}, {"a": True, "b": True}, {1: 0, 2: 0}])
def test_invalid_population_fails_closed(stances):
    with pytest.raises((TypeError, ValueError)):
        build_group_assignment(initial_stances=stances, matched_seed=7)


def test_rehashed_membership_tampering_is_rejected():
    artifact = build_group_assignment(initial_stances=STANCES, matched_seed=7)
    payload = artifact.to_payload()["payload"]
    first = next(iter(payload["memberships"]))
    payload["memberships"][first] = "green" if payload["memberships"][first] == "blue" else "blue"
    tampered = ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        payload=payload,
        rng_provenance=artifact.rng_provenance,
    )
    with pytest.raises(ValueError, match="replay"):
        GroupContext.from_artifact(tampered)


def test_text_label_strata_replay_and_exact_balance():
    labels = {a: f"label-{s + 2}" for a, s in STANCES.items()}
    artifact = build_group_assignment(initial_stances=labels, matched_seed=7)
    context = GroupContext.from_artifact(artifact)
    for label in set(labels.values()):
        assert Counter(context.group_for(a) for a, s in labels.items() if s == label) == {
            "blue": 2,
            "green": 2,
        }


@pytest.mark.parametrize("stances", [{"a": "", "b": ""}, {"a": 1, "b": "1"}])
def test_empty_and_mixed_strata_labels_fail(stances):
    with pytest.raises(TypeError):
        build_group_assignment(initial_stances=stances, matched_seed=7)
