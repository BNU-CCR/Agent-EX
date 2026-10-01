"""Explicit round-zero check selections, not automatic sampling or real results."""

import json
from copy import deepcopy

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.state import PublicPost
from test_identity_network_candidate import sources
from test_identity_network_materialization import rebuild


def arguments():
    from agent_ex.identity_network.candidate import (
        build_six_cell_candidate,
        validate_six_cell_candidate,
    )

    candidate = build_six_cell_candidate(**sources())
    binding = validate_six_cell_candidate(candidate)[1]
    receiver, source = binding.node_agent_ids[:2]
    return dict(
        candidate=candidate,
        selections=(
            dict(case_id="explicit-case", receiver_id=receiver, source_id=source, sampling_seed=71),
        ),
        stage="pure_label",
        matched_seed=23,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
    )


def test_source_bound_round0_cases_replay_persona_private_memory_and_public_post():
    from agent_ex.identity_network.manipulation_sources import (
        build_source_bound_manipulation_pack,
        validate_source_bound_manipulation_pack,
    )
    from agent_ex.state import PrivateUpdate

    kwargs = arguments()
    result = build_source_bound_manipulation_pack(**kwargs)
    cold = ArtifactEnvelope.from_payload(json.loads(json.dumps(result.to_payload())))
    check = validate_source_bound_manipulation_pack(cold, candidate=kwargs["candidate"])
    fixture = check.payload["fixtures"][0]
    evidence = fixture["base_evidence"]
    common = kwargs["candidate"].payload["population_candidate"]["payload"]["execution_inputs"][
        "payload"
    ]
    selected = kwargs["selections"][0]
    # Cold payload conversion supplies strict state record JSON, not frozen mappings.
    updates = {
        u["agent_id"]: PrivateUpdate.from_payload(u)
        for u in kwargs["candidate"].to_payload()["payload"]["population_candidate"]["payload"][
            "execution_inputs"
        ]["payload"]["initial_updates"]
    }
    own = updates[selected["receiver_id"]]
    post = PublicPost.from_private_update(updates[selected["source_id"]], mock_only=True)
    assert evidence["persona_text"] == common["persona_by_agent"][own.agent_id]
    assert evidence["pre_state"] == {"stance": own.stance_label, "reason": own.reason}
    assert evidence["self_history"] == (
        {"stance": own.stance_label, "reason": own.reason, "published": own.published},
    )
    assert evidence["shown_posts"][0]["post_id"] == post.post_id
    assert evidence["shown_posts"][0]["reason"] == post.public_reason
    assert fixture["sampling_seed"] == 71
    assert len(check.payload["trials"]) == 4
    assert result.payload["metadata"]["dispatch_authorized"] is False


@pytest.mark.parametrize("change", ["unknown", "self", "extra", "bool_seed", "empty", "duplicate"])
def test_selection_requires_explicit_distinct_valid_sources_and_case_identity(change):
    from agent_ex.identity_network.manipulation_sources import build_source_bound_manipulation_pack

    kwargs = arguments()
    selection = kwargs["selections"][0]
    if change == "unknown":
        selection["source_id"] = "absent"
    elif change == "self":
        selection["source_id"] = selection["receiver_id"]
    elif change == "extra":
        selection["history"] = ()
    elif change == "bool_seed":
        selection["sampling_seed"] = True
    elif change == "empty":
        kwargs["selections"] = ()
    else:
        kwargs["selections"] *= 2
    with pytest.raises((ValueError, TypeError)):
        build_source_bound_manipulation_pack(**kwargs)


@pytest.mark.parametrize("change", ["persona", "seed", "metadata", "extra"])
def test_source_bound_reader_refuses_rehashed_content_or_selection_drift(change):
    from agent_ex.identity_network.manipulation_sources import (
        build_source_bound_manipulation_pack,
        validate_source_bound_manipulation_pack,
    )

    kwargs = arguments()
    result = build_source_bound_manipulation_pack(**kwargs)
    payload = deepcopy(result.to_payload()["payload"])
    if change == "persona":
        payload["pack"]["payload"]["fixtures"][0]["base_evidence"]["persona_text"] = "Changed"
    elif change == "seed":
        payload["selections"][0]["sampling_seed"] += 1
    elif change == "metadata":
        payload["metadata"]["dispatch_authorized"] = True
    else:
        payload["extra"] = True
    with pytest.raises(ValueError, match="source-bound manipulation"):
        validate_source_bound_manipulation_pack(
            rebuild(result, payload), candidate=kwargs["candidate"]
        )


def test_source_bound_check_remains_controlled_input_not_randomized_graph_feed():
    from agent_ex.identity_network.manipulation_sources import build_source_bound_manipulation_pack

    result = build_source_bound_manipulation_pack(**arguments())
    assert result.payload["history_mode"] == "shared_memory_round0"
    assert result.payload["source_mode"] == "explicit_controlled_single_round0_post"
    assert result.payload["metadata"]["formal_parameter_authority"] is False


def test_valid_fully_rehashed_alternative_persona_pack_cannot_replace_bound_source():
    from agent_ex.domain import canonical_payload_hash
    from agent_ex.identity_network.candidate import validate_six_cell_candidate
    from agent_ex.identity_network.manipulation import (
        CheckCase,
        build_manipulation_pack,
        validate_manipulation_pack,
    )
    from agent_ex.identity_network.manipulation_sources import (
        build_source_bound_manipulation_pack,
        validate_source_bound_manipulation_pack,
    )
    from agent_ex.identity_network.prompts import ShownPost, render_study_prompt

    kwargs = arguments()
    result = build_source_bound_manipulation_pack(**kwargs)
    payload = result.to_payload()["payload"]
    e = payload["pack"]["payload"]["fixtures"][0]["base_evidence"]
    binding = validate_six_cell_candidate(kwargs["candidate"])[1]
    prompt = render_study_prompt(
        cell=binding.cell,
        groups=binding.groups,
        receiver_id=e["receiver_id"],
        persona_text="Different but renderer-valid persona.",
        topic_package=binding.topic_package,
        pre_state=e["pre_state"],
        self_history=tuple(e["self_history"]),
        posts=tuple(ShownPost(**p) for p in e["shown_posts"]),
    )
    alternate = build_manipulation_pack(
        cases=(CheckCase("explicit-case", prompt, 71),),
        stage="pure_label",
        matched_seed=23,
        generation_settings=kwargs["generation_settings"],
    )
    validate_manipulation_pack(alternate, topic_package=binding.topic_package)
    payload["pack"] = alternate.to_payload()
    forged = ArtifactEnvelope.create(
        artifact_type=result.artifact_type,
        schema_version=result.schema_version,
        algorithm_id=result.algorithm_id,
        algorithm_version=result.algorithm_version,
        input_hashes={"candidate": kwargs["candidate"].output_hash, "pack": alternate.output_hash},
        rng_provenance=(),
        payload=payload,
    )
    assert canonical_payload_hash(forged.payload) == forged.output_hash
    with pytest.raises(ValueError, match="source-bound manipulation"):
        validate_source_bound_manipulation_pack(forged, candidate=kwargs["candidate"])


def test_source_bound_stage_two_and_selection_order_are_deterministic():
    from agent_ex.identity_network.manipulation import StageTwoReceipt
    from agent_ex.identity_network.manipulation_sources import (
        build_source_bound_manipulation_pack,
        validate_source_bound_manipulation_pack,
    )

    kwargs = arguments()
    kwargs["stage"] = "shared_group_framing"
    kwargs["stage_two_receipt"] = StageTwoReceipt("a" * 64, "b" * 64, "no_signal", "researcher")
    second = {**kwargs["selections"][0], "case_id": "another-case", "sampling_seed": 72}
    kwargs["selections"] += (second,)
    result = build_source_bound_manipulation_pack(**kwargs)
    assert result == build_source_bound_manipulation_pack(
        **{**kwargs, "selections": tuple(reversed(kwargs["selections"]))}
    )
    cold = ArtifactEnvelope.from_payload(result.to_payload())
    check = validate_source_bound_manipulation_pack(cold, candidate=kwargs["candidate"])
    assert len(check.payload["trials"]) == 8
