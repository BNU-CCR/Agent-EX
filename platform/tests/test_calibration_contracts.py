from dataclasses import FrozenInstanceError, replace
import json

import pytest

from agent_ex.calibration import ProbeCase, ProbePersonaView, ProbeTopicCandidate
from agent_ex.domain import canonical_payload_hash


SHA_A = "a" * 64
CALIBRATION_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}


def topic_candidate() -> ProbeTopicCandidate:
    return ProbeTopicCandidate.create(
        construct="对延迟退休政策的支持程度",
        fact_card="本题仅询问对政策的总体态度。",
        statements=("题干甲", "题干乙", "题干丙"),
        stance_labels_1_7=tuple(f"标签 {index}" for index in range(1, 8)),
    )


def persona_view() -> ProbePersonaView:
    return ProbePersonaView.create(
        identity_present=True,
        continuity_present=True,
        common_skeleton="共同任务说明",
        identity_block="最小身份卡",
        continuity_block="可保持也可改变，但请解释与历史的关系。",
        rendered_text="共同任务说明\n最小身份卡\n可保持也可改变，但请解释与历史的关系。",
    )


def probe_case() -> ProbeCase:
    candidate = topic_candidate()
    persona = persona_view()
    return ProbeCase.create(
        specification_hash=SHA_A,
        candidate_id=candidate.candidate_id,
        case_family="continuity",
        scenario_id="reasonable-update",
        variant_index=1,
        scale_id="stance-1-7",
        field_order_id="stance-confidence-reason",
        replicate_id="replicate-01",
        requested_seed=17,
        persona_view_id=persona.persona_view_id,
        rendered_messages=(
            {"role": "system", "content": persona.rendered_text},
            {"role": "user", "content": "题干甲"},
        ),
    )


@pytest.mark.parametrize("record_factory", [topic_candidate, persona_view, probe_case])
def test_calibration_records_are_frozen(record_factory) -> None:
    record = record_factory()
    with pytest.raises(FrozenInstanceError):
        record.record_hash = SHA_A


def test_probe_case_payload_is_calibration_only_and_has_no_event_identity() -> None:
    payload = probe_case().to_payload()
    assert payload["metadata"] == CALIBRATION_METADATA
    assert (
        not {
            "event_id",
            "run_id",
            "cell_id",
            "feed_cursor",
            "private_state",
        }
        & payload.keys()
    )


@pytest.mark.parametrize("record_factory", [topic_candidate, persona_view, probe_case])
def test_calibration_records_strict_json_round_trip(record_factory) -> None:
    record = record_factory()
    payload = json.loads(json.dumps(record.to_payload(), ensure_ascii=False))
    restored = type(record).from_payload(payload)
    assert restored == record
    assert restored.record_hash == canonical_payload_hash(restored.content_payload())


@pytest.mark.parametrize("record_factory", [topic_candidate, persona_view, probe_case])
def test_payload_rejects_formal_authority(record_factory) -> None:
    record = record_factory()
    payload = record.to_payload()
    payload["metadata"]["formal_parameter_authority"] = True
    with pytest.raises(ValueError, match="calibration-only"):
        type(record).from_payload(payload)


@pytest.mark.parametrize("record_factory", [topic_candidate, persona_view, probe_case])
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_payload_requires_exact_fields(record_factory, mutation: str) -> None:
    record = record_factory()
    payload = record.to_payload()
    if mutation == "missing":
        payload.pop("record_hash")
    else:
        payload["event_id"] = "event-forbidden"
    with pytest.raises(ValueError, match="fields|contract"):
        type(record).from_payload(payload)


@pytest.mark.parametrize(
    ("record_factory", "field"),
    [
        (topic_candidate, "statements"),
        (topic_candidate, "stance_labels_1_7"),
        (topic_candidate, "statement_hashes"),
        (probe_case, "rendered_messages"),
    ],
)
def test_constructor_requires_tuples_and_transport_requires_json_lists(
    record_factory, field: str
) -> None:
    record = record_factory()
    with pytest.raises(TypeError, match="tuple"):
        replace(record, **{field: list(getattr(record, field))})

    payload = record.to_payload()
    payload[field] = tuple(payload[field])
    with pytest.raises(TypeError, match="JSON|array"):
        type(record).from_payload(payload)


@pytest.mark.parametrize(
    ("record_factory", "field"),
    [
        (topic_candidate, "candidate_id"),
        (topic_candidate, "construct"),
        (persona_view, "persona_view_id"),
        (persona_view, "common_skeleton"),
        (probe_case, "probe_case_id"),
        (probe_case, "case_family"),
    ],
)
def test_empty_ids_and_text_fail_closed(record_factory, field: str) -> None:
    with pytest.raises(ValueError, match="empty|ID"):
        replace(record_factory(), **{field: " "})


@pytest.mark.parametrize(
    ("record_factory", "field"),
    [
        (topic_candidate, "record_hash"),
        (topic_candidate, "statement_hashes"),
        (persona_view, "record_hash"),
        (probe_case, "specification_hash"),
        (probe_case, "rendered_messages_hash"),
        (probe_case, "record_hash"),
    ],
)
def test_invalid_sha256_values_fail_closed(record_factory, field: str) -> None:
    record = record_factory()
    value = ("bad-sha",) * 3 if field == "statement_hashes" else "bad-sha"
    with pytest.raises(ValueError, match="SHA-256|hash"):
        replace(record, **{field: value})


@pytest.mark.parametrize("field", ["identity_present", "continuity_present"])
def test_persona_rejects_integer_for_boolean(field: str) -> None:
    with pytest.raises(TypeError, match="boolean"):
        replace(persona_view(), **{field: 1})


@pytest.mark.parametrize("field", ["variant_index", "requested_seed"])
def test_probe_case_rejects_boolean_for_integer(field: str) -> None:
    with pytest.raises(TypeError, match="integer"):
        replace(probe_case(), **{field: True})


def test_persona_absent_blocks_are_really_absent() -> None:
    absent = ProbePersonaView.create(
        identity_present=False,
        continuity_present=False,
        common_skeleton="共同任务说明",
        identity_block=None,
        continuity_block=None,
        rendered_text="共同任务说明",
    )
    assert absent.identity_block is None
    assert absent.continuity_block is None
    with pytest.raises(ValueError, match="identity_block"):
        replace(absent, identity_block="不应存在")
    with pytest.raises(ValueError, match="continuity_block"):
        replace(absent, continuity_block="不应存在")


def test_topic_exact_cardinality_and_derived_statement_hashes() -> None:
    record = topic_candidate()
    assert record.statement_hashes == tuple(
        canonical_payload_hash(statement) for statement in record.statements
    )
    with pytest.raises(ValueError, match="exactly three"):
        replace(record, statements=record.statements[:2])
    with pytest.raises(ValueError, match="exactly seven"):
        replace(record, stance_labels_1_7=record.stance_labels_1_7[:6])


@pytest.mark.parametrize("record_factory", [topic_candidate, persona_view, probe_case])
@pytest.mark.parametrize("field", ["identity", "hash"])
def test_caller_supplied_wrong_identity_or_hash_fails_closed(record_factory, field: str) -> None:
    record = record_factory()
    identity_field = {
        ProbeTopicCandidate: "candidate_id",
        ProbePersonaView: "persona_view_id",
        ProbeCase: "probe_case_id",
    }[type(record)]
    target = identity_field if field == "identity" else "record_hash"
    replacement = "forged-id" if field == "identity" else SHA_A
    with pytest.raises(ValueError, match="identity|canonical payload|record_hash|derived"):
        replace(record, **{target: replacement})


def test_probe_case_binds_rendered_messages_hash_and_freezes_nested_messages() -> None:
    record = probe_case()
    assert record.rendered_messages_hash == canonical_payload_hash(record.rendered_messages)
    with pytest.raises(TypeError):
        record.rendered_messages[0]["content"] = "mutated"


def test_payload_rejects_non_json_nested_containers() -> None:
    payload = probe_case().to_payload()
    payload["rendered_messages"][0] = {"role", "system"}
    with pytest.raises(TypeError, match="strict JSON|JSON"):
        ProbeCase.from_payload(payload)
