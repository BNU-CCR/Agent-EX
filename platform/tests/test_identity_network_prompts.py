import json

import pytest

from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.groups import GroupContext, build_group_assignment
from agent_ex.identity_network.prompts import ShownPost, render_study_prompt


def render(cell, posts=None):
    context = GroupContext.from_artifact(
        build_group_assignment(
            initial_stances={"receiver": -1, "source": -1},
            matched_seed=3,
        )
    )
    return render_study_prompt(
        cell=cell,
        groups=context,
        receiver_id="receiver",
        persona_text="Age 25.",
        fact_card="Evidence is uncertain.",
        core_statement="Policy X is desirable.",
        stance_labels=(-1, 0, 1),
        pre_state={"stance": -1, "reason": "Prior evidence."},
        self_history=({"stance": 0, "reason": "Earlier evidence.", "published": False},),
        posts=tuple(posts or ()),
    )


def test_blind_and_salient_only_differ_in_group_metadata():
    post = ShownPost("post-1", "source", "member-1", 1, "New evidence.")
    blind = render(study_cells()[1], [post])
    salient = render(study_cells()[4], [post])
    b = json.loads(blind.messages[1]["content"])
    s = json.loads(salient.messages[1]["content"])
    assert "self_group" not in b
    assert "source_group" not in b["social_messages"][0]
    assert s.pop("self_group") in ("Blue", "Green")
    assert s["social_messages"][0].pop("source_group") in ("Blue", "Green")
    assert b == s
    assert blind.messages[0] == salient.messages[0]
    assert blind.evidence["source_groups"] == salient.evidence["source_groups"]
    assert "initial_stances" not in blind.messages[1]["content"]
    assert "receiver" not in blind.messages[1]["content"]
    assert "source" not in blind.messages[1]["content"]
    assert "consisten" not in blind.messages[0]["content"].lower()


def test_no_social_retains_self_group_but_refuses_posts():
    salient = render(study_cells()[3])
    visible = json.loads(salient.messages[1]["content"])
    assert visible["self_group"] in ("Blue", "Green")
    assert not visible["social_messages"]
    with pytest.raises(ValueError, match="no_social"):
        render(study_cells()[0], [ShownPost("p", "source", "member-1", 0, "reason")])


def test_original_text_is_not_censored_and_unknown_source_rejected():
    result = render(
        study_cells()[1], [ShownPost("p", "source", "member-1", 0, "I mentioned Blue.")]
    )
    assert "I mentioned Blue." in result.messages[1]["content"]
    with pytest.raises(ValueError, match="unknown"):
        render(study_cells()[1], [ShownPost("p", "missing", "member-1", 0, "reason")])


def test_trace_content_is_hashed_and_immutable():
    result = render(study_cells()[0])
    assert len(result.prompt_hash) == 64
    assert len(result.evidence_hash) == 64
    with pytest.raises(TypeError):
        result.messages[0]["content"] = "changed"


def test_alias_cannot_leak_metadata_or_split_one_source():
    with pytest.raises(ValueError, match="neutral"):
        ShownPost("p", "source", "Blue-member", 0, "reason")
    with pytest.raises(ValueError, match="alias"):
        render(
            study_cells()[1],
            [
                ShownPost("p1", "source", "member-1", 0, "one"),
                ShownPost("p2", "source", "member-2", 0, "two"),
            ],
        )


def test_alias_cannot_merge_distinct_sources():
    with pytest.raises(ValueError, match="alias"):
        render(
            study_cells()[1],
            [
                ShownPost("p1", "source", "member-1", 0, "one"),
                ShownPost("p2", "receiver", "member-1", 0, "two"),
            ],
        )


def test_multiple_posts_from_one_source_are_allowed():
    result = render(
        study_cells()[1],
        [
            ShownPost("p1", "source", "member-1", 0, "one"),
            ShownPost("p2", "source", "member-1", 1, "two"),
        ],
    )
    assert len(json.loads(result.messages[1]["content"])["social_messages"]) == 2
