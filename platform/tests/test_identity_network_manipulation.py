import json

import pytest

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
        fact_card="Uncertain evidence.",
        core_statement="Policy X is desirable.",
        stance_labels=(-1, 0, 1),
        pre_state={"stance": 0, "reason": "Undecided."},
        self_history=(),
        posts=(ShownPost("p1", "source", "member-1", 1, "Reason one."),),
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
