from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.groups import GroupContext, build_group_assignment
from agent_ex.identity_network.prompts import ShownPost, render_study_prompt
from test_prompt import topic


def test_new_prompt_uses_the_existing_provider_contract():
    groups = GroupContext.from_artifact(
        build_group_assignment(
            initial_stances={"receiver": "label-2", "source": "label-2"},
            matched_seed=3,
        )
    )
    prompt = render_study_prompt(
        cell=study_cells()[4],
        groups=groups,
        receiver_id="receiver",
        persona_text="Adult participant.",
        topic_package=topic(),
        pre_state={"stance": "label-2", "reason": "Prior evidence."},
        self_history=(),
        posts=(ShownPost("p", "source", "member-1", "label-5", "Public reason."),),
    )
    assert "confidence (a JSON integer from 1 to 5)" in prompt.messages[0]["content"]
    assert prompt.evidence["topic_package_hash"] == topic().package_hash
    assert prompt.evidence["renderer_version"] == "paper1.identity-network.prompt.v2"
