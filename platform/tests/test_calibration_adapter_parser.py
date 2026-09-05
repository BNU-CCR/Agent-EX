from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json

import pytest

from agent_ex.calibration.adapters import ProbeAdapter, ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.contracts import ProbeParseEvidence, ProbeRequest, ProbeResponse
from agent_ex.calibration.parser import (
    MAX_JSON_DEPTH,
    MAX_RAW_BYTES,
    MAX_RAW_CHARS,
    MAX_REASON_CHARS,
    parse_probe_response,
)
from agent_ex.calibration.specification import expand_probe_cases, load_probe_specification
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload


GENERATION_SETTINGS = {"temperature": 0.2, "top_p": 0.9, "max_tokens": 128}
ADAPTER_IDENTITY = {"provider": "scripted-probe", "runtime_version": "1.0.0"}
MODEL_IDENTITY = {"model": "synthetic", "revision": "offline-v1"}
TOKENIZER_IDENTITY = {"tokenizer": "synthetic", "revision": "offline-v1"}
CHAT_TEMPLATE_HASH = canonical_payload_hash("synthetic-chat-template-v1")


def probe_case(*, scale_id: str = "stance-1-7", field_order_id: str | None = None):
    cases = expand_probe_cases(load_probe_specification(probe_spec_payload()))
    return next(
        case
        for case in cases
        if case.scale_id == scale_id
        and (field_order_id is None or case.field_order_id == field_order_id)
    )


def request(*, scale_id: str = "stance-1-7", field_order_id: str | None = None):
    return ProbeRequest.create(
        probe_case(scale_id=scale_id, field_order_id=field_order_id),
        attempt_index=1,
        attempt_kind="semantic",
        generation_settings=GENERATION_SETTINGS,
    )


def response(raw: str, *, scale_id: str = "stance-1-7", field_order_id: str | None = None):
    req = request(scale_id=scale_id, field_order_id=field_order_id)
    return ProbeResponse.from_script_step(
        request=req,
        outcome="response",
        raw_response=raw,
        error_code=None,
        adapter_identity=ADAPTER_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        provider_request_id=f"scripted-{req.request_id}",
        provider_seed_supported=True,
        provider_seed_echo=req.requested_seed,
    )


def valid_raw(
    *,
    stance: int = 4,
    confidence: int = 3,
    reason: str = "A bounded synthetic reason.",
    field_order_id: str = "stance-confidence-reason",
) -> str:
    payload = {
        "stance": stance,
        "confidence": confidence,
        "public_reason": reason,
    }
    order = {
        "stance-confidence-reason": ("stance", "confidence", "public_reason"),
        "reason-confidence-stance": ("public_reason", "confidence", "stance"),
    }[field_order_id]
    return json.dumps({key: payload[key] for key in order}, separators=(",", ":"))


def test_probe_request_binds_case_attempt_messages_settings_and_seed() -> None:
    case = probe_case()
    record = ProbeRequest.create(
        case,
        attempt_index=1,
        attempt_kind="semantic",
        generation_settings=GENERATION_SETTINGS,
    )
    assert record.probe_case_id == case.probe_case_id
    assert record.probe_case_hash == case.record_hash
    assert record.rendered_messages_hash == case.rendered_messages_hash
    assert record.requested_seed == case.requested_seed
    assert record.metadata["formal_parameter_authority"] is False
    with pytest.raises(FrozenInstanceError):
        record.attempt_index = 2


def test_scripted_adapter_binds_response_and_consumes_exact_step() -> None:
    req = request()
    raw = valid_raw()
    adapter: ProbeAdapter = ScriptedProbeAdapter(
        {(req.probe_case_id, req.attempt_index): ProbeScriptStep("response", raw, None)}
    )
    record = adapter.generate(req)
    assert record.probe_case_id == req.probe_case_id
    assert record.request_hash == req.record_hash
    assert record.raw_response_hash == canonical_payload_hash(raw)
    assert record.metadata["formal_parameter_authority"] is False
    assert record.runtime_identity == ADAPTER_IDENTITY
    assert record.provider_seed_supported is True
    assert record.provider_seed_echo == req.requested_seed
    with pytest.raises(ValueError, match="missing|consumed"):
        adapter.generate(req)


def test_scripted_adapter_rejects_missing_step() -> None:
    with pytest.raises(ValueError, match="missing"):
        ScriptedProbeAdapter({}).generate(request())


@pytest.mark.parametrize("record_factory", [request, lambda: response(valid_raw())])
def test_request_and_response_strict_json_round_trip(record_factory) -> None:
    record = record_factory()
    restored = type(record).from_payload(json.loads(json.dumps(record.to_payload())))
    assert restored == record
    assert restored.record_hash == canonical_payload_hash(restored.content_payload())


def test_parse_evidence_strict_json_round_trip_and_hash_binding() -> None:
    record = parse_probe_response(response(valid_raw()))
    assert record.success is True
    assert record.stance == 4
    assert record.confidence == 3
    restored = ProbeParseEvidence.from_payload(json.loads(json.dumps(record.to_payload())))
    assert restored == record
    assert restored.record_hash == canonical_payload_hash(restored.content_payload())


@pytest.mark.parametrize("record_factory", [request, lambda: response(valid_raw())])
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_contract_payloads_reject_missing_or_extra_fields(record_factory, mutation: str) -> None:
    payload = record_factory().to_payload()
    if mutation == "missing":
        payload.pop("record_hash")
    else:
        payload["event_id"] = "forbidden"
    with pytest.raises(ValueError, match="fields|contract"):
        record_factory().__class__.from_payload(payload)


@pytest.mark.parametrize("field,value", [("attempt_index", True), ("provider_seed_echo", True)])
def test_contracts_reject_boolean_as_integer(field: str, value: object) -> None:
    record = request() if field == "attempt_index" else response(valid_raw())
    with pytest.raises(TypeError, match="integer"):
        replace(record, **{field: value})


def test_request_requires_explicit_generation_settings() -> None:
    with pytest.raises((TypeError, ValueError), match="generation_settings"):
        ProbeRequest.create(
            probe_case(),
            attempt_index=1,
            attempt_kind="semantic",
            generation_settings={},
        )


@pytest.mark.parametrize("supported,echo", [(False, 17), (True, 18)])
def test_provider_seed_declaration_and_echo_are_consistent(
    supported: bool, echo: int | None
) -> None:
    req = request()
    with pytest.raises(ValueError, match="seed"):
        ProbeResponse.from_script_step(
            request=req,
            outcome="response",
            raw_response=valid_raw(),
            error_code=None,
            adapter_identity=ADAPTER_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
            provider_request_id="provider-request",
            provider_seed_supported=supported,
            provider_seed_echo=echo,
        )


def test_provider_seed_unsupported_requires_no_echo() -> None:
    req = request()
    record = ProbeResponse.from_script_step(
        request=req,
        outcome="response",
        raw_response=valid_raw(),
        error_code=None,
        adapter_identity=ADAPTER_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        provider_request_id="provider-request",
        provider_seed_supported=False,
        provider_seed_echo=None,
    )
    assert record.provider_seed_echo is None


@pytest.mark.parametrize("outcome", ["timeout", "oom", "provider_error"])
def test_seed_support_without_echo_is_truthful_for_error_responses(outcome: str) -> None:
    req = request()
    record = ProbeResponse.from_script_step(
        request=req,
        outcome=outcome,
        raw_response=None,
        error_code=f"synthetic-{outcome}",
        adapter_identity=ADAPTER_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        provider_request_id="provider-request",
        provider_seed_supported=True,
        provider_seed_echo=None,
    )
    assert record.provider_seed_supported is True
    assert record.provider_seed_echo is None


def test_absent_requested_seed_cannot_gain_a_provider_echo() -> None:
    original = probe_case()
    case = original.create(
        specification_hash=original.specification_hash,
        candidate_id=original.candidate_id,
        case_family=original.case_family,
        scenario_id=original.scenario_id,
        variant_index=original.variant_index,
        scale_id=original.scale_id,
        field_order_id=original.field_order_id,
        replicate_id=original.replicate_id,
        requested_seed=None,
        persona_view_id=original.persona_view_id,
        rendered_messages=original.rendered_messages,
    )
    req = ProbeRequest.create(
        case,
        attempt_index=1,
        attempt_kind="semantic",
        generation_settings=GENERATION_SETTINGS,
    )
    with pytest.raises(ValueError, match="seed"):
        ProbeResponse.from_script_step(
            request=req,
            outcome="response",
            raw_response=valid_raw(),
            error_code=None,
            adapter_identity=ADAPTER_IDENTITY,
            model_identity=MODEL_IDENTITY,
            tokenizer_identity=TOKENIZER_IDENTITY,
            chat_template_hash=CHAT_TEMPLATE_HASH,
            provider_request_id="provider-request",
            provider_seed_supported=True,
            provider_seed_echo=17,
        )


@pytest.mark.parametrize("outcome", ["timeout", "oom", "provider_error"])
def test_typed_error_responses_exclude_raw_content(outcome: str) -> None:
    req = request()
    record = ProbeResponse.from_script_step(
        request=req,
        outcome=outcome,
        raw_response=None,
        error_code=f"synthetic-{outcome}",
        adapter_identity=ADAPTER_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
        provider_request_id="provider-request",
        provider_seed_supported=True,
        provider_seed_echo=req.requested_seed,
    )
    assert record.raw_response is None
    assert record.raw_response_hash is None
    assert record.error_code == f"synthetic-{outcome}"


@pytest.mark.parametrize(
    "raw,error_code",
    [
        ('{"stance":4,"confidence":3}', "fields"),
        ('{"stance":4,"confidence":3,"public_reason":"x","extra":1}', "fields"),
        ('{"stance":true,"confidence":3,"public_reason":"x"}', "stance_type"),
        ('{"stance":8,"confidence":3,"public_reason":"x"}', "stance_range"),
        ('{"stance":NaN,"confidence":3,"public_reason":"x"}', "json"),
        ('{"stance":Infinity,"confidence":3,"public_reason":"x"}', "json"),
        ('{"stance":4,"stance":5,"confidence":3,"public_reason":"x"}', "duplicate"),
        ('{"stance":4,"confidence":true,"public_reason":"x"}', "confidence_type"),
        ('{"stance":4,"confidence":0,"public_reason":"x"}', "confidence_range"),
        ('{"stance":4,"confidence":3,"public_reason":" "}', "reason"),
    ],
)
def test_parser_fails_closed_for_malformed_model_content(raw: str, error_code: str) -> None:
    evidence = parse_probe_response(response(raw))
    assert evidence.success is False
    assert evidence.error == {"code": error_code, "message": evidence.error["message"]}


@pytest.mark.parametrize(
    "scale_id,stance",
    [("stance-1-7", 1), ("stance-1-7", 7), ("stance-0-10", 0), ("stance-0-10", 10)],
)
def test_parser_enforces_scale_specific_inclusive_ranges(scale_id: str, stance: int) -> None:
    evidence = parse_probe_response(response(valid_raw(stance=stance), scale_id=scale_id))
    assert evidence.success is True
    assert evidence.stance == stance


@pytest.mark.parametrize(
    "field_order_id",
    ["stance-confidence-reason", "reason-confidence-stance"],
)
def test_parser_accepts_only_the_case_declared_field_order(field_order_id: str) -> None:
    raw = valid_raw(field_order_id=field_order_id)
    evidence = parse_probe_response(response(raw, field_order_id=field_order_id))
    assert evidence.success is True
    other = (
        "reason-confidence-stance"
        if field_order_id == "stance-confidence-reason"
        else "stance-confidence-reason"
    )
    failed = parse_probe_response(
        response(valid_raw(field_order_id=other), field_order_id=field_order_id)
    )
    assert failed.success is False
    assert failed.error["code"] == "fields"


def test_parser_enforces_reason_character_bound() -> None:
    assert parse_probe_response(response(valid_raw(reason="x" * MAX_REASON_CHARS))).success
    evidence = parse_probe_response(response(valid_raw(reason="x" * (MAX_REASON_CHARS + 1))))
    assert evidence.success is False
    assert evidence.error["code"] == "reason_size"


def test_parser_rejects_raw_character_limit_before_parsing() -> None:
    with pytest.raises(ValueError, match="character"):
        parse_probe_response(response("x" * (MAX_RAW_CHARS + 1)))


def test_parser_rejects_raw_byte_limit() -> None:
    raw = '"' + ("界" * (MAX_RAW_BYTES // 3)) + '"'
    assert len(raw) <= MAX_RAW_CHARS
    with pytest.raises(ValueError, match="byte"):
        parse_probe_response(response(raw))


def test_parser_rejects_excessive_json_depth_as_failure_evidence() -> None:
    raw = "[" * (MAX_JSON_DEPTH + 1) + "0" + "]" * (MAX_JSON_DEPTH + 1)
    evidence = parse_probe_response(response(raw))
    assert evidence.success is False
    assert evidence.error["code"] == "depth"


def test_parse_evidence_binds_request_and_response_hashes() -> None:
    resp = response(valid_raw())
    evidence = parse_probe_response(resp)
    assert evidence.probe_case_id == resp.probe_case_id
    assert evidence.request_id == resp.request_id
    assert evidence.request_hash == resp.request_hash
    assert evidence.response_id == resp.response_id
    assert evidence.response_hash == resp.record_hash
    with pytest.raises(ValueError, match="canonical payload|hash|identity"):
        replace(evidence, response_hash="0" * 64)


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [("scale_id", "stance-0-10"), ("field_order_id", "reason-confidence-stance")],
)
@pytest.mark.parametrize("success", [True, False])
def test_parse_evidence_create_rejects_declarations_mismatching_response(
    field: str, wrong_value: str, success: bool
) -> None:
    resp = response(valid_raw())
    arguments = {
        "response": resp,
        "scale_id": resp.scale_id,
        "field_order_id": resp.field_order_id,
        "stance": 4 if success else None,
        "confidence": 3 if success else None,
        "public_reason": "synthetic reason" if success else None,
        "error": None if success else {"code": "fields", "message": "synthetic failure"},
    }
    arguments[field] = wrong_value
    with pytest.raises(ValueError, match="response|scale|field order"):
        ProbeParseEvidence.create(**arguments)


def rehash_record_payload(
    payload: dict[str, object], *, identity_field: str, identity_prefix: str
) -> None:
    identity = {
        key: value for key, value in payload.items() if key not in {identity_field, "record_hash"}
    }
    payload[identity_field] = identity_prefix + canonical_payload_hash(identity)
    payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in payload.items() if key != "record_hash"}
    )


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [("scale_id", "stance-2-9"), ("field_order_id", "reason-first")],
)
@pytest.mark.parametrize("success", [True, False])
def test_rehashed_parse_evidence_rejects_unsupported_declarations(
    field: str, wrong_value: str, success: bool
) -> None:
    raw = valid_raw() if success else '{"stance":4}'
    payload = parse_probe_response(response(raw)).to_payload()
    payload[field] = wrong_value
    rehash_record_payload(
        payload,
        identity_field="parse_evidence_id",
        identity_prefix="probe-parse-",
    )
    with pytest.raises(ValueError, match="scale|field_order|field order|supported"):
        ProbeParseEvidence.from_payload(payload)


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [("scale_id", "stance-2-9"), ("field_order_id", "reason-first")],
)
def test_rehashed_response_rejects_unsupported_declarations(field: str, wrong_value: str) -> None:
    payload = response(valid_raw()).to_payload()
    payload[field] = wrong_value
    rehash_record_payload(payload, identity_field="response_id", identity_prefix="probe-response-")
    with pytest.raises(ValueError, match="scale|field_order|field order|supported"):
        ProbeResponse.from_payload(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"stance": 0},
        {"confidence": 6},
        {"public_reason": "x" * (MAX_REASON_CHARS + 1)},
    ],
)
def test_parse_evidence_contract_rejects_invalid_success_values(changes) -> None:
    evidence = parse_probe_response(response(valid_raw()))
    with pytest.raises(ValueError, match="stance|confidence|public_reason|reason"):
        replace(evidence, **changes)
