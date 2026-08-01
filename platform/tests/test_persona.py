import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import canonical_payload_hash
from agent_ex.persona import render_persona, validate_persona_factor_diff


SHA = "3" * 64
CONDITIONS = (
    {"identity_present": False, "continuity_present": False},
    {"identity_present": False, "continuity_present": True},
    {"identity_present": True, "continuity_present": False},
    {"identity_present": True, "continuity_present": True},
)


def template_artifact() -> ArtifactEnvelope:
    payload = {
        "schema_version": "paper1.mock-persona-template.v1",
        "common_skeleton": "共同任务边界。\n{identity_block}{continuity_block}请按统一合同作答。",
        "identity_block_template": (
            "[身份信息]\n年龄段：{age_band}\n调查记录性别：{gender}\n"
            "最高教育：{education}\n当前城乡：{urban}\n主要活动：{activity}\n"
            "宽职业组：{occupation}\n这些背景不预设你的立场。\n"
        ),
        "continuity_block": (
            "[解释连贯要求]\n参考此前立场和理由；保持或改变都可以。若改变，请说明"
            "促使你重新权衡的信息，不要为了表面一致而忽略有说服力的信息。\n"
        ),
        "required_identity_fields": [
            "age_band",
            "gender",
            "education",
            "urban",
            "activity",
            "occupation",
        ],
        "forbidden_phrases": ["永不改变", "不要被影响", "最大变化一步", "普通中国人"],
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_persona_template",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )


def member() -> dict[str, object]:
    return {
        "agent_id": "agent-0001",
        "donor_id": "d1",
        "fields": {
            "age_band": "30—39岁",
            "gender": "女",
            "education": "大学",
            "urban": "城镇",
            "activity": "就业",
            "occupation": "专业技术",
            "analysis_only_region": "mock-region",
        },
    }


def rendered_four() -> tuple[ArtifactEnvelope, ...]:
    return tuple(
        render_persona(template_artifact(), member(), condition) for condition in CONDITIONS
    )


def test_persona_uses_one_skeleton_and_only_inserts_factor_blocks() -> None:
    rendered = rendered_four()
    report = validate_persona_factor_diff(rendered)

    assert report == {
        "valid": True,
        "condition_count": 4,
        "allowed_differences": ["identity_block", "continuity_block"],
    }
    assert all(value.artifact_type == "paper1.mock_rendered_persona" for value in rendered)
    assert all(value.rng_provenance == () for value in rendered)


def test_absent_conditions_truly_omit_blocks_and_placebos() -> None:
    i0c0, i0c1, i1c0, _ = rendered_four()

    assert i0c0.payload["identity_block"] == ""
    assert i0c0.payload["continuity_block"] == ""
    assert "普通中国人" not in i0c0.payload["rendered_text"]
    assert "30—39岁" not in i0c1.payload["rendered_text"]
    assert "解释连贯要求" not in i1c0.payload["rendered_text"]
    assert "analysis_only_region" not in i1c0.payload["rendered_text"]
    assert "mock-region" not in i1c0.payload["rendered_text"]


def test_identity_and_continuity_blocks_are_independently_reused() -> None:
    i0c0, i0c1, i1c0, i1c1 = rendered_four()

    assert i1c0.payload["identity_block"] == i1c1.payload["identity_block"]
    assert i0c1.payload["continuity_block"] == i1c1.payload["continuity_block"]
    assert i0c0.payload["population_member_hash"] == canonical_payload_hash(member())


def test_persona_diff_rejects_unapproved_condition_specific_text() -> None:
    rendered = list(rendered_four())
    payload = rendered[3].to_payload()["payload"]
    payload["rendered_text"] += "\n只在此条件出现的额外指令。"
    rendered[3] = ArtifactEnvelope.create(
        artifact_type="paper1.mock_rendered_persona",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_persona_renderer",
        algorithm_version="1.0.0",
        input_hashes=rendered[0].input_hashes,
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="factor blocks"):
        validate_persona_factor_diff(tuple(rendered))


def test_persona_diff_rejects_unknown_condition_specific_hidden_payload() -> None:
    rendered = list(rendered_four())
    payload = rendered[3].to_payload()["payload"]
    payload["condition_specific_hidden"] = "covert treatment text"
    rendered[3] = ArtifactEnvelope.create(
        artifact_type="paper1.mock_rendered_persona",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_persona_renderer",
        algorithm_version="1.0.0",
        input_hashes=rendered[3].input_hashes,
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="payload fields"):
        validate_persona_factor_diff(tuple(rendered))


def test_persona_diff_rejects_envelope_tampering_outside_derived_identity() -> None:
    rendered = list(rendered_four())
    rendered[3] = ArtifactEnvelope.create(
        artifact_type="paper1.mock_rendered_persona",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.tampered_renderer",
        algorithm_version="1.0.0",
        input_hashes=rendered[3].input_hashes,
        payload=rendered[3].payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="envelope invariant.*algorithm_id"):
        validate_persona_factor_diff(tuple(rendered))


def test_persona_rejects_missing_identity_field_and_illegal_condition() -> None:
    incomplete = member()
    incomplete["fields"].pop("occupation")
    with pytest.raises(ValueError, match="occupation"):
        render_persona(template_artifact(), incomplete, CONDITIONS[2])

    with pytest.raises(ValueError, match="condition"):
        render_persona(
            template_artifact(),
            member(),
            {"identity_present": True, "continuity_present": True, "extra": False},
        )


def test_persona_template_rejects_locking_language() -> None:
    artifact = template_artifact()
    payload = artifact.to_payload()["payload"]
    payload["continuity_block"] += "永不改变。"
    broken = ArtifactEnvelope.create(
        artifact_type="paper1.mock_persona_template",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="forbidden"):
        render_persona(broken, member(), CONDITIONS[1])


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        ("Age again: {age_band}\n", "exactly once"),
        ("", "exactly once"),
        ("Unknown: {analysis_only_region}\n", "unknown"),
    ],
)
def test_identity_template_requires_each_frozen_format_field_exactly_once(
    replacement, match
) -> None:
    artifact = template_artifact()
    payload = artifact.to_payload()["payload"]
    if replacement == "":
        payload["identity_block_template"] = payload["identity_block_template"].replace(
            "{occupation}", "occupation"
        )
    else:
        payload["identity_block_template"] += replacement
    broken = ArtifactEnvelope.create(
        artifact_type="paper1.mock_persona_template",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match=match):
        render_persona(broken, member(), CONDITIONS[2])


@pytest.mark.parametrize(
    "unapproved_field",
    ["analysis_only_region", "sensitive_identity", "directional_experience"],
)
def test_persona_template_rejects_identity_fields_outside_platform_allowlist(
    unapproved_field,
) -> None:
    artifact = template_artifact()
    payload = artifact.to_payload()["payload"]
    payload["required_identity_fields"].append(unapproved_field)
    payload["identity_block_template"] += f"Unapproved: {{{unapproved_field}}}\n"
    population_member = member()
    population_member["fields"][unapproved_field] = "must-not-render"
    broken = ArtifactEnvelope.create(
        artifact_type="paper1.mock_persona_template",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="platform identity field allowlist"):
        render_persona(broken, population_member, CONDITIONS[2])


def test_platform_locking_rule_cannot_be_cleared_by_empty_template_denylist() -> None:
    artifact = template_artifact()
    payload = artifact.to_payload()["payload"]
    payload["forbidden_phrases"] = []
    payload["continuity_block"] += "You must never change your stance.\n"
    broken = ArtifactEnvelope.create(
        artifact_type="paper1.mock_persona_template",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="platform-forbidden"):
        render_persona(broken, member(), CONDITIONS[1])


@pytest.mark.parametrize(
    ("platform_forbidden_phrase", "template_block"),
    [
        ("抗从众", "continuity_block"),
        ("保持原有价值观", "continuity_block"),
        ("最大变化一步", "continuity_block"),
        ("at most one point", "continuity_block"),
        ("never change", "continuity_block"),
        ("坚持", "identity_block_template"),
        ("捍卫", "continuity_block"),
        ("忠于", "identity_block_template"),
        ("除非证据确凿", "continuity_block"),
    ],
)
def test_each_platform_persona_policy_cannot_be_cleared_by_empty_template_denylist(
    platform_forbidden_phrase,
    template_block,
) -> None:
    artifact = template_artifact()
    payload = artifact.to_payload()["payload"]
    payload["forbidden_phrases"] = []
    payload[template_block] += f"{platform_forbidden_phrase}.\n"
    broken = ArtifactEnvelope.create(
        artifact_type="paper1.mock_persona_template",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="platform-forbidden"):
        render_persona(broken, member(), CONDITIONS[1])


@pytest.mark.parametrize(
    ("platform_forbidden_phrase", "rendered_block"),
    [
        ("抗从众", "continuity_block"),
        ("保持原有价值观", "continuity_block"),
        ("最大变化一步", "continuity_block"),
        ("at most one point", "continuity_block"),
        ("never change", "continuity_block"),
        ("坚持", "identity_block"),
        ("捍卫", "continuity_block"),
        ("忠于", "identity_block"),
        ("除非证据确凿", "continuity_block"),
    ],
)
def test_persona_diff_validation_rejects_each_platform_forbidden_policy(
    platform_forbidden_phrase,
    rendered_block,
) -> None:
    rendered = list(rendered_four())
    for index, artifact in enumerate(rendered):
        payload = artifact.to_payload()["payload"]
        condition_field = rendered_block.removesuffix("_block") + "_present"
        if payload["condition"][condition_field]:
            payload[rendered_block] += f"{platform_forbidden_phrase}."
        payload["rendered_text"] = (
            payload["common_skeleton"]
            .replace("{identity_block}", payload["identity_block"])
            .replace("{continuity_block}", payload["continuity_block"])
        )
        rendered[index] = ArtifactEnvelope.create(
            artifact_type="paper1.mock_rendered_persona",
            schema_version="paper1.artifact-envelope.v1",
            algorithm_id="paper1.mock_persona_renderer",
            algorithm_version="1.0.0",
            input_hashes=artifact.input_hashes,
            payload=payload,
            rng_provenance=(),
        )

    with pytest.raises(ValueError, match="platform-forbidden"):
        validate_persona_factor_diff(tuple(rendered))


@pytest.mark.parametrize("empty_field", ["identity_block_template", "continuity_block"])
def test_persona_template_rejects_empty_present_factor_blocks(empty_field) -> None:
    artifact = template_artifact()
    payload = artifact.to_payload()["payload"]
    payload[empty_field] = ""
    broken = ArtifactEnvelope.create(
        artifact_type="paper1.mock_persona_template",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_fixture",
        algorithm_version="1.0.0",
        input_hashes={"fixture_source": SHA},
        payload=payload,
        rng_provenance=(),
    )

    with pytest.raises(ValueError, match="present factor blocks must be non-empty"):
        render_persona(broken, member(), CONDITIONS[3])


@pytest.mark.parametrize(
    ("block_field", "present_indices"),
    [("identity_block", (2, 3)), ("continuity_block", (1, 3))],
)
def test_persona_diff_rejects_empty_present_factor_blocks(block_field, present_indices) -> None:
    rendered = list(rendered_four())
    for index in present_indices:
        payload = rendered[index].to_payload()["payload"]
        payload[block_field] = ""
        skeleton = payload["common_skeleton"]
        payload["rendered_text"] = skeleton.replace(
            "{identity_block}", payload["identity_block"]
        ).replace("{continuity_block}", payload["continuity_block"])
        rendered[index] = ArtifactEnvelope.create(
            artifact_type="paper1.mock_rendered_persona",
            schema_version="paper1.artifact-envelope.v1",
            algorithm_id="paper1.mock_persona_renderer",
            algorithm_version="1.0.0",
            input_hashes=rendered[index].input_hashes,
            payload=payload,
            rng_provenance=(),
        )

    with pytest.raises(ValueError, match="present factor blocks must be non-empty"):
        validate_persona_factor_diff(tuple(rendered))
