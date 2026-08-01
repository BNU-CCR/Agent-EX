from dataclasses import FrozenInstanceError, replace
import json

import pytest

import agent_ex
from agent_ex.domain import canonical_payload_hash
from agent_ex.topic import TopicPackage


def topic_payload() -> dict[str, object]:
    return {
        "schema_version": "paper1.topic-package.mock.v1",
        "package_version": "0.0.1-mock",
        "topic_id": "mock-topic",
        "construct": "对明确陈述的总体支持程度",
        "target_population": "仅用于测试的合成人口",
        "applicability": "mock-only；不得用于正式运行",
        "fact_card": "这是不含真实研究参数的测试事实卡。",
        "core_statement": "我支持这项测试陈述。",
        "paraphrases": ["总体而言，我赞成这项测试陈述。"],
        "stance_labels": [
            "强烈反对",
            "反对",
            "比较反对",
            "中立",
            "比较支持",
            "支持",
            "强烈支持",
        ],
        "confidence_contract": {"minimum": 1, "maximum": 5, "analysis_only": True},
        "output_contract": ["stance", "confidence", "public_reason"],
        "argument_families": ["mock-family-a", "mock-family-b"],
        "round0_reason_library_artifact_id": "artifact-" + "a" * 64,
        "topic_extension_fields": ["mock_extension"],
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }


def test_topic_package_strict_round_trip_and_hash() -> None:
    payload = topic_payload()
    package = TopicPackage.from_payload(json.loads(json.dumps(payload, ensure_ascii=False)))

    assert package.to_payload() == payload
    assert package.package_hash == canonical_payload_hash(payload)
    assert TopicPackage.from_payload(package.to_payload()) == package

    with pytest.raises(FrozenInstanceError):
        package.topic_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda payload: payload.update(extra="value"), ValueError),
        (lambda payload: payload.pop("package_version"), ValueError),
        (lambda payload: payload.update(schema_version="paper1.topic-package.v2"), ValueError),
        (lambda payload: payload.update(stance_labels=["only-one"]), ValueError),
        (lambda payload: payload["metadata"].update(mock_only=False), ValueError),  # type: ignore[union-attr]
    ],
)
def test_topic_package_fails_closed_on_contract_drift(mutation, error) -> None:
    payload = topic_payload()
    mutation(payload)

    with pytest.raises(error):
        TopicPackage.from_payload(payload)


def test_topic_package_hash_changes_with_any_visible_content() -> None:
    package = TopicPackage.from_payload(topic_payload())
    changed = replace(package, core_statement="另一条测试陈述。")

    assert changed.package_hash != package.package_hash


def test_phase4b3_interfaces_are_public() -> None:
    assert agent_ex.TopicPackage is TopicPackage
    assert callable(agent_ex.trs_integerize)
    assert callable(agent_ex.build_population_artifact)
    assert callable(agent_ex.assign_initial_stances)
    assert callable(agent_ex.assign_initial_reasons)
    assert callable(agent_ex.render_persona)
    assert callable(agent_ex.validate_persona_factor_diff)
