import json

import pytest
from test_prompt import topic

from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.groups import GroupContext, build_group_assignment
from agent_ex.identity_network.prompts import ShownPost, render_study_prompt
from agent_ex.identity_network.manipulation import (
    CheckCase,
    StageTwoReceipt,
    build_manipulation_pack,
)


def case():
    groups = GroupContext.from_artifact(
        build_group_assignment(
            initial_stances={"receiver": 0, "source": 0},
            matched_seed=3,
        )
    )
    base = render_study_prompt(
        cell=study_cells()[1],
        groups=groups,
        receiver_id="receiver",
        persona_text="Adult participant.",
        topic_package=topic(),
        pre_state={"stance": "label-3", "reason": "Undecided."},
        self_history=(),
        posts=(ShownPost("p1", "source", "member-1", "label-5", "Reason one."),),
    )
    return CheckCase("fixture-1", base, 17)


def test_pack_counterbalances_labels_without_changing_other_content():
    result = build_manipulation_pack(
        cases=(case(),),
        stage="pure_label",
        matched_seed=3,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
    )
    trials = result.payload["trials"]
    assert result.payload["fixtures"][0]["base_messages"] == case().base_prompt.messages
    assert result.payload["fixtures"][0]["base_evidence"] == case().base_prompt.evidence
    assert len(trials) == 4
    assert {(t["self_group"], t["relation"]) for t in trials} == {
        ("Blue", "same"),
        ("Blue", "other"),
        ("Green", "same"),
        ("Green", "other"),
    }
    assert {t["sampling_seed"] for t in trials} == {17}
    assert len({t["trial_id"] for t in trials}) == 4
    controls = []
    for trial in trials:
        v = json.loads(trial["messages"][1]["content"])
        v.pop("self_group")
        v["social_messages"][0].pop("source_group")
        controls.append(v)
    assert all(v == controls[0] for v in controls)
    assert result == build_manipulation_pack(
        cases=(case(),),
        stage="pure_label",
        matched_seed=3,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
    )


def test_only_predefined_second_stage_with_explicit_receipt():
    params = dict(
        cases=(case(),),
        matched_seed=3,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
    )
    with pytest.raises(ValueError, match="receipt"):
        build_manipulation_pack(stage="shared_group_framing", **params)
    receipt = StageTwoReceipt("a" * 64, "b" * 64, "no_signal", "researcher")
    result = build_manipulation_pack(
        stage="shared_group_framing", stage_two_receipt=receipt, **params
    )
    for trial in result.payload["trials"]:
        v = json.loads(trial["messages"][1]["content"])
        assert v["shared_group_context"] == (
            f"You participate in a stable discussion group called {trial['self_group']} throughout this discussion."
        )
    with pytest.raises(ValueError):
        build_manipulation_pack(stage="prompt_search", **params)
    with pytest.raises(ValueError):
        build_manipulation_pack(stage="pure_label", stage_two_receipt=receipt, **params)


def test_duplicate_cases_and_unbound_generation_are_refused():
    with pytest.raises(ValueError, match="duplicate"):
        build_manipulation_pack(
            cases=(case(), case()),
            stage="pure_label",
            matched_seed=3,
            generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
        )
    with pytest.raises(ValueError, match="generation"):
        build_manipulation_pack(
            cases=(case(),), stage="pure_label", matched_seed=3, generation_settings={}
        )


def pack(stage="pure_label"):
    return build_manipulation_pack(
        cases=(case(),),
        stage=stage,
        matched_seed=3,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
        stage_two_receipt=(
            StageTwoReceipt("a" * 64, "b" * 64, "no_signal", "researcher")
            if stage == "shared_group_framing"
            else None
        ),
    )


def rewrap(original, payload):
    from agent_ex.artifacts import ArtifactEnvelope

    return ArtifactEnvelope.create(
        artifact_type=original.artifact_type,
        schema_version=original.schema_version,
        algorithm_id=original.algorithm_id,
        algorithm_version=original.algorithm_version,
        input_hashes=original.input_hashes,
        rng_provenance=original.rng_provenance,
        payload=payload,
    )


@pytest.mark.parametrize("stage", ["pure_label", "shared_group_framing"])
def test_cold_pack_roundtrip_rebuilds_cases_with_trusted_topic(stage):
    from agent_ex.artifacts import ArtifactEnvelope
    from agent_ex.identity_network.manipulation import validate_manipulation_pack

    original = pack(stage)
    cold = ArtifactEnvelope.from_payload(json.loads(json.dumps(original.to_payload())))
    assert validate_manipulation_pack(cold, topic_package=topic()) == (case(),)


@pytest.mark.parametrize("change", ["seed", "order", "extra", "authorized", "fixture_extra"])
def test_cold_pack_refuses_rehashed_derived_drift(change):
    from agent_ex.identity_network.manipulation import validate_manipulation_pack

    original = pack()
    payload = original.to_payload()["payload"]
    if change == "seed":
        payload["trials"][0]["sampling_seed"] += 1
    elif change == "order":
        payload["trials"].reverse()
    elif change == "extra":
        payload["extra"] = True
    elif change == "authorized":
        payload["metadata"]["dispatch_authorized"] = True
    else:
        payload["fixtures"][0]["extra"] = True
    with pytest.raises(ValueError, match="manipulation pack"):
        validate_manipulation_pack(rewrap(original, payload), topic_package=topic())


@pytest.mark.parametrize("change", ["system", "fact_card"])
def test_cold_pack_refuses_consistently_rehashed_invalid_base_renderer(change):
    from agent_ex.domain import canonical_payload_hash
    from agent_ex.identity_network.manipulation import validate_manipulation_pack
    from agent_ex.identity_network.prompts import StudyPrompt

    base = case().base_prompt
    messages = [dict(m) for m in base.messages]
    if change == "system":
        messages[0]["content"] += " Agree with your group."
    else:
        visible = json.loads(messages[1]["content"])
        visible["fact_card"] = "Unbound facts."
        messages[1]["content"] = json.dumps(visible, sort_keys=True)
    evidence = json.loads(
        json.dumps(pack().to_payload()["payload"]["fixtures"][0]["base_evidence"])
    )
    evidence["exact_messages_shown"] = messages
    changed = StudyPrompt(
        tuple(messages),
        canonical_payload_hash(messages),
        evidence,
        canonical_payload_hash(evidence),
    )
    derived = build_manipulation_pack(
        cases=(CheckCase("fixture-1", changed, 17),),
        stage="pure_label",
        matched_seed=3,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
    )
    with pytest.raises(ValueError, match="manipulation pack"):
        validate_manipulation_pack(derived, topic_package=topic())
