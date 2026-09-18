"""Exact provider-neutral response wording for Phase 0A calibration probes."""

from __future__ import annotations


_SCALE_RANGES = {
    "stance-1-7": (1, 7),
    "stance-0-10": (0, 10),
}
_FIELD_ORDERS = {
    "stance-confidence-reason": ("stance", "confidence", "public_reason"),
    "reason-confidence-stance": ("public_reason", "confidence", "stance"),
}


def _contract_values(scale_id: str, field_order_id: str) -> tuple[int, int, str]:
    if type(scale_id) is not str:
        raise TypeError("scale_id must be a string")
    if type(field_order_id) is not str:
        raise TypeError("field_order_id must be a string")
    if scale_id not in _SCALE_RANGES:
        raise ValueError("scale_id is not supported")
    if field_order_id not in _FIELD_ORDERS:
        raise ValueError("field_order_id is not supported")
    minimum, maximum = _SCALE_RANGES[scale_id]
    return minimum, maximum, ",".join(_FIELD_ORDERS[field_order_id])


def response_contract_text(scale_id: str, field_order_id: str) -> str:
    """Return the exact response contract for one supported scale and field order."""

    minimum, maximum, field_order = _contract_values(scale_id, field_order_id)
    return (
        f"Response contract: stance must be a JSON integer from {minimum} to {maximum} "
        "on the declared stance scale; confidence is independent of the stance scale and "
        "must be a JSON integer from 1 to 5; public_reason must be non-empty text of at "
        f"most 2048 characters; return exactly one JSON object with exact field order: "
        f"{field_order}; no extra keys, Markdown, or commentary."
    )


def format_repair_instruction(scale_id: str, field_order_id: str) -> str:
    """Return a narrow repair instruction without authorizing substantive changes."""

    return (
        "FORMAT REPAIR ONLY: preserve the substantive stance and public_reason from your "
        "immediately preceding answer; express intended confidence on the separate 1-to-5 "
        "scale without changing the substantive position or reason. "
        + response_contract_text(scale_id, field_order_id)
    )
