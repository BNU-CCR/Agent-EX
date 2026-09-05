"""Strict, resource-bounded parser for Phase 0A probe responses."""

from __future__ import annotations

import json

from .contracts import ProbeParseEvidence, ProbeResponse


MAX_RAW_CHARS = 32_768
MAX_RAW_BYTES = 65_536
MAX_JSON_DEPTH = 16
MAX_REASON_CHARS = 2_048

_FIELD_ORDERS = {
    "stance-confidence-reason": ("stance", "confidence", "public_reason"),
    "reason-confidence-stance": ("public_reason", "confidence", "stance"),
}
_SCALE_RANGES = {"stance-1-7": (1, 7), "stance-0-10": (0, 10)}


class _DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _validate_depth(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if type(item) is dict:
            if depth >= MAX_JSON_DEPTH:
                raise OverflowError
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            if depth >= MAX_JSON_DEPTH:
                raise OverflowError
            stack.extend((child, depth + 1) for child in item)


def _failure(
    response: ProbeResponse, *, scale_id: str, field_order_id: str, code: str, message: str
) -> ProbeParseEvidence:
    return ProbeParseEvidence.create(
        response=response,
        scale_id=scale_id,
        field_order_id=field_order_id,
        stance=None,
        confidence=None,
        public_reason=None,
        error={"code": code, "message": message},
    )


def parse_probe_response(response: ProbeResponse) -> ProbeParseEvidence:
    """Parse one response without coercion, repair, defaults, or formal-run identities."""
    if not isinstance(response, ProbeResponse):
        raise TypeError("response must be a ProbeResponse")
    if response.outcome != "response" or type(response.raw_response) is not str:
        raise ValueError("parser requires a response outcome with raw content")
    raw = response.raw_response
    if len(raw) > MAX_RAW_CHARS:
        raise ValueError("response exceeds explicit raw character limit")
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("response exceeds explicit raw byte limit")
    try:
        encoded = raw.encode("utf-8", "strict")
    except UnicodeError:
        return _failure(
            response,
            scale_id="unknown",
            field_order_id="unknown",
            code="unicode",
            message="response is not valid UTF-8 Unicode scalar text",
        )
    if len(encoded) > MAX_RAW_BYTES:
        raise ValueError("response exceeds explicit raw byte limit")

    scale_id = response.scale_id
    field_order_id = response.field_order_id
    if scale_id not in _SCALE_RANGES:
        raise ValueError("response declares an unsupported probe scale")
    if field_order_id not in _FIELD_ORDERS:
        raise ValueError("response declares an unsupported field order")
    try:
        value = json.loads(
            raw, object_pairs_hook=_object_without_duplicates, parse_constant=_reject_constant
        )
        _validate_depth(value)
    except _DuplicateKey:
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="duplicate",
            message="JSON keys must be unique",
        )
    except (OverflowError, RecursionError):
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="depth",
            message="JSON nesting exceeds explicit depth limit",
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="json",
            message="response must be strict JSON",
        )
    if type(value) is not dict or tuple(value) != _FIELD_ORDERS[field_order_id]:
        if type(value) is dict and tuple(value) == ("refusal",) and value["refusal"] is True:
            return _failure(
                response,
                scale_id=scale_id,
                field_order_id=field_order_id,
                code="refusal",
                message="model explicitly refused the probe",
            )
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="fields",
            message="response fields and order do not match the declared probe contract",
        )
    stance, confidence, reason = value["stance"], value["confidence"], value["public_reason"]
    if type(stance) is not int:
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="stance_type",
            message="stance must be a JSON integer",
        )
    minimum, maximum = _SCALE_RANGES[scale_id]
    if not minimum <= stance <= maximum:
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="stance_range",
            message=f"stance must be between {minimum} and {maximum}",
        )
    if type(confidence) is not int:
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="confidence_type",
            message="confidence must be a JSON integer",
        )
    if not 1 <= confidence <= 5:
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="confidence_range",
            message="confidence must be between 1 and 5",
        )
    if type(reason) is not str:
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="reason_type",
            message="public_reason must be text",
        )
    if not reason.strip():
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="reason",
            message="public_reason must be non-empty text",
        )
    if len(reason) > MAX_REASON_CHARS:
        return _failure(
            response,
            scale_id=scale_id,
            field_order_id=field_order_id,
            code="reason_size",
            message="public_reason exceeds explicit character limit",
        )
    return ProbeParseEvidence.create(
        response=response,
        scale_id=scale_id,
        field_order_id=field_order_id,
        stance=stance,
        confidence=confidence,
        public_reason=reason,
        error=None,
    )
