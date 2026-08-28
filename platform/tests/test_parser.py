from __future__ import annotations

import json

import pytest

import agent_ex.parser as parser_module

from agent_ex.adapters.base import AdapterRequest, AdapterResponse
from agent_ex.adapters.mock import MockAdapter, MockScriptStep, validate_adapter_response
from agent_ex.domain import canonical_payload_hash
from agent_ex.parser import (
    ParseEvidence,
    ParsedAgentUpdate,
    ParserLimits,
    parse_agent_update,
    validate_parse_evidence,
)
from agent_ex.topic import TopicPackage
from test_prompt import EVENT_ID, build as build_prompt, topic as prompt_topic


def topic() -> TopicPackage:
    return prompt_topic()


def limits(**overrides: int) -> ParserLimits:
    return ParserLimits.create(
        max_raw_chars=overrides.get("max_raw_chars", 100_000),
        max_raw_bytes=overrides.get("max_raw_bytes", 100_000),
        max_json_depth=overrides.get("max_json_depth", 32),
        max_reason_chars=overrides.get("max_reason_chars", 10_000),
        mock_only=True,
    )


def response(raw: str) -> tuple[AdapterResponse, AdapterRequest, MockAdapter]:
    request = AdapterRequest.create(
        prompt_view=build_prompt(), attempt_index=1, mock_seed=123, mock_only=True
    )
    adapter = MockAdapter(
        script={EVENT_ID: (MockScriptStep.malformed(raw),)},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    return adapter.generate(request), request, adapter


def parse(raw: str, parser_limits: ParserLimits | None = None) -> ParseEvidence:
    adapter_response, _, _ = response(raw)
    return parse_agent_update(
        adapter_response,
        topic_package=topic(),
        limits=parser_limits or limits(),
    )


def test_parser_accepts_only_exact_topic_contract_and_records_raw_evidence() -> None:
    raw = json.dumps(
        {"stance": "label-2", "confidence": 4, "public_reason": "A non-empty reason."},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    evidence = parse(raw)

    assert evidence.success is True
    assert evidence.parsed == ParsedAgentUpdate(
        topic_package_id=topic().topic_id,
        topic_package_hash=topic().package_hash,
        stance="label-2",
        confidence=4,
        public_reason="A non-empty reason.",
    )
    assert evidence.raw_response == raw
    assert evidence.raw_response_hash
    assert evidence.parsed_response_hash
    assert evidence.error is None
    assert ParseEvidence.from_payload(evidence.to_payload()) == evidence
    trusted_response, _, _ = response(raw)
    validate_parse_evidence(evidence, trusted_response, topic(), limits())


@pytest.mark.parametrize(
    ("raw", "code"),
    (
        ('{"stance":"label-2","confidence":4}', "fields"),
        ('{"stance":"label-2","confidence":4,"public_reason":"x","extra":1}', "fields"),
        ('{"stance":2,"confidence":4,"public_reason":"x"}', "stance_type"),
        ('{"stance":"2","confidence":4,"public_reason":"x"}', "stance_label"),
        ('{"stance":"label-2","confidence":true,"public_reason":"x"}', "confidence_type"),
        ('{"stance":"label-2","confidence":0,"public_reason":"x"}', "confidence_range"),
        ('{"stance":"label-2","confidence":6,"public_reason":"x"}', "confidence_range"),
        ('{"stance":"label-2","confidence":4,"public_reason":"  "}', "reason"),
        ('{"stance":"label-2","confidence":4,"public_reason":false}', "reason_type"),
        ('{"stance":"label-2","confidence":NaN,"public_reason":"x"}', "json"),
        ('{"stance":"label-2","confidence":Infinity,"public_reason":"x"}', "json"),
        ('{"stance":"label-2","stance":"label-3","confidence":4,"public_reason":"x"}', "duplicate"),
        ('```json\n{"stance":"label-2","confidence":4,"public_reason":"x"}\n```', "json"),
        ('{"stance":"label-2","confidence":4,"public_reason":"x"} trailing', "json"),
        ('{"stance":"label-2","confidence":4,"public_reason":"x","publish_flag":true}', "fields"),
    ),
)
def test_parser_rejects_malformed_or_semantically_rewrapped_content(raw: str, code: str) -> None:
    evidence = parse(raw)

    assert evidence.success is False
    assert evidence.parsed is None
    assert evidence.parsed_response_hash is None
    assert evidence.error is not None
    assert evidence.error["code"] == code
    assert evidence.raw_response == raw


def test_parser_does_not_mutate_or_default_missing_content() -> None:
    raw = '{"stance":"label-2","confidence":"4","public_reason":"x"}'
    evidence = parse(raw)

    assert evidence.success is False
    assert evidence.error == {
        "code": "confidence_type",
        "message": "confidence must be a JSON integer",
    }


def test_parser_accepts_natural_reason_text_without_instruction_keyword_filtering() -> None:
    evidence = parse(
        '{"stance":"label-2","confidence":4,'
        '"public_reason":"Ignore previous text is quoted natural language.\\nStill data."}'
    )
    assert evidence.success is True


def test_parser_fails_with_evidence_for_unicode_depth_and_byte_budget_attacks() -> None:
    unicode_evidence = parse('{"stance":"label-2","confidence":4,"public_reason":"\\ud800"}')
    assert unicode_evidence.success is False
    assert unicode_evidence.error is not None
    assert unicode_evidence.error["code"] == "unicode"

    deep = "[" * 10_000 + "0" + "]" * 10_000
    depth_evidence = parse(deep, limits(max_json_depth=10))
    assert depth_evidence.success is False
    assert depth_evidence.error is not None
    assert depth_evidence.error["code"] in {"depth", "json"}

    with pytest.raises(ValueError, match="raw byte limit"):
        parse("x" * 100, limits(max_raw_bytes=16))

    with pytest.raises(ValueError, match="raw character limit"):
        parse(
            "x" * 100,
            limits(max_raw_chars=16, max_raw_bytes=1_000),
        )


@pytest.mark.parametrize(
    ("raw", "parser_limits", "message"),
    (
        ("x" * 100, limits(max_raw_chars=16, max_raw_bytes=1_000), "character limit"),
        ("界" * 10, limits(max_raw_chars=100, max_raw_bytes=16), "byte limit"),
    ),
)
def test_parser_rejects_resource_oversize_before_response_seal_or_hash(
    monkeypatch,
    raw: str,
    parser_limits: ParserLimits,
    message: str,
) -> None:
    trusted, _, _ = response(raw)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("oversized raw response reached sealing or hashing")

    monkeypatch.setattr(parser_module, "_has_trusted_response_seal", forbidden)
    monkeypatch.setattr(parser_module, "canonical_payload_hash", forbidden)

    with pytest.raises(ValueError, match=message):
        parse_agent_update(
            trusted,
            topic_package=topic(),
            limits=parser_limits,
        )


def test_parser_checks_character_count_above_byte_budget_before_bounded_utf8_encoding(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def counted(raw: str) -> bytes:
        calls.append(raw)
        return raw.encode("utf-8", "strict")

    monkeypatch.setattr(parser_module, "_encode_raw_utf8", counted, raising=False)
    oversized, _, _ = response("x" * 17)

    with pytest.raises(ValueError, match="raw byte limit"):
        parse_agent_update(
            oversized,
            topic_package=topic(),
            limits=limits(max_raw_chars=100, max_raw_bytes=16),
        )
    assert calls == []

    raw = '{"stance":"label-2","confidence":4,"public_reason":"x"}'
    trusted, _, _ = response(raw)
    assert parse_agent_update(
        trusted,
        topic_package=topic(),
        limits=limits(max_raw_chars=100, max_raw_bytes=100),
    ).success
    assert calls == [raw]


def test_parse_evidence_validator_reparses_raw_and_rejects_rewrapped_label() -> None:
    raw = '{"stance":"label-2","confidence":4,"public_reason":"x"}'
    evidence = parse(raw)
    payload = evidence.to_payload()
    payload["parsed"]["stance"] = "label-6"  # type: ignore[index]
    payload["parsed_response_hash"] = __import__(
        "agent_ex.domain", fromlist=["canonical_payload_hash"]
    ).canonical_payload_hash(payload["parsed"])
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    payload["record_hash"] = __import__(
        "agent_ex.domain", fromlist=["canonical_payload_hash"]
    ).canonical_payload_hash(content)
    forged = ParseEvidence.from_payload(payload)
    trusted_response, _, _ = response(raw)
    with pytest.raises(ValueError, match="evidence|replay|parsed"):
        validate_parse_evidence(forged, trusted_response, topic(), limits())


def test_parser_rejects_unsealed_raw_response_rewrap_until_adapter_replay() -> None:
    raw = '{"stance":"label-2","confidence":4,"public_reason":"x"}'
    trusted, request, adapter = response(raw)
    payload = trusted.to_payload()
    payload["raw_response"] = '{"stance":"label-6","confidence":4,"public_reason":"forged"}'
    payload["raw_response_hash"] = canonical_payload_hash(payload["raw_response"])
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    forged = AdapterResponse.from_payload(payload)
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        parse_agent_update(forged, topic_package=topic(), limits=limits())

    resigned = validate_adapter_response(
        AdapterResponse.from_payload(trusted.to_payload()), request, adapter
    )
    assert parse_agent_update(resigned, topic_package=topic(), limits=limits()).success is True


def test_parser_rejects_reflectively_mutated_sealed_response_and_cross_topic_laundering() -> None:
    raw = '{"stance":"label-2","confidence":4,"public_reason":"x"}'
    trusted, _, _ = response(raw)
    object.__setattr__(
        trusted,
        "raw_response",
        '{"stance":"label-6","confidence":4,"public_reason":"forged"}',
    )
    object.__setattr__(
        trusted,
        "raw_response_hash",
        canonical_payload_hash(trusted.raw_response),
    )
    object.__setattr__(trusted, "record_hash", canonical_payload_hash(trusted.content_payload()))
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        parse_agent_update(trusted, topic_package=topic(), limits=limits())

    clean, _, _ = response(raw)
    evidence = parse_agent_update(clean, topic_package=topic(), limits=limits())
    other_payload = topic().to_payload()
    other_payload["topic_id"] = "other-topic-with-same-labels"
    other_topic = TopicPackage.from_payload(other_payload)
    with pytest.raises(ValueError, match="topic"):
        parse_agent_update(clean, topic_package=other_topic, limits=limits())
    with pytest.raises(ValueError, match="topic"):
        validate_parse_evidence(evidence, clean, other_topic, limits())


def test_object_visible_response_seal_material_cannot_resign_mutated_raw_response() -> None:
    trusted, _, _ = response('{"stance":"label-2","confidence":4,"public_reason":"x"}')
    visible = trusted._factory_seal
    object.__setattr__(
        trusted,
        "raw_response",
        '{"stance":"label-6","confidence":4,"public_reason":"resigned forged"}',
    )
    object.__setattr__(trusted, "raw_response_hash", canonical_payload_hash(trusted.raw_response))
    object.__setattr__(trusted, "record_hash", canonical_payload_hash(trusted.content_payload()))
    forged_seal = (visible[0], trusted.record_hash) if isinstance(visible, tuple) else visible
    object.__setattr__(trusted, "_factory_seal", forged_seal)
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        parse_agent_update(trusted, topic_package=topic(), limits=limits())
