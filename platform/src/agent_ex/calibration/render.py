"""Mechanical rendering and orthogonality checks for calibration personas."""

from __future__ import annotations

from typing import Mapping

from .contracts import ProbePersonaView


_FORBIDDEN_LOCKING_PHRASES = (
    "坚持",
    "捍卫",
    "忠于",
    "抗从众",
    "不要被影响",
    "除非证据确凿",
    "最大变化一步",
    "保持原有价值观",
    "永不改变",
)
_FACTOR_NAMES = {"identity", "continuity"}
_ALLOWED_VARYING_FIELDS = {
    "identity_present",
    "continuity_present",
    "identity_block",
    "continuity_block",
    "rendered_text",
    "persona_view_id",
    "record_hash",
}


def _reject_locking_language(text: str) -> None:
    for phrase in _FORBIDDEN_LOCKING_PHRASES:
        if phrase in text:
            raise ValueError(f"probe persona contains forbidden locking phrase: {phrase}")


def render_probe_persona(
    *,
    common_skeleton: str,
    identity_present: bool,
    continuity_present: bool,
    identity_block: str,
    continuity_block: str,
    factor_order: tuple[str, str],
) -> ProbePersonaView:
    """Insert the two factors without borrowing the legacy mock renderer."""

    if not isinstance(common_skeleton, str) or not common_skeleton.strip():
        raise ValueError("common_skeleton must be a non-empty string")
    if common_skeleton.count("{factor_blocks}") != 1:
        raise ValueError("common_skeleton must contain {factor_blocks} exactly once")
    if type(identity_present) is not bool or type(continuity_present) is not bool:
        raise TypeError("persona factor conditions must be booleans")
    if not isinstance(identity_block, str) or not identity_block.strip():
        raise ValueError("identity_block candidate must be a non-empty string")
    if not isinstance(continuity_block, str) or not continuity_block.strip():
        raise ValueError("continuity_block candidate must be a non-empty string")
    if type(factor_order) is not tuple or len(factor_order) != 2:
        raise TypeError("factor_order must be a two-item tuple")
    if set(factor_order) != _FACTOR_NAMES or len(set(factor_order)) != 2:
        raise ValueError("factor_order must contain identity and continuity exactly once")

    visible_identity = identity_block if identity_present else None
    visible_continuity = continuity_block if continuity_present else None
    selected = {
        "identity": visible_identity,
        "continuity": visible_continuity,
    }
    factor_text = "\n".join(selected[name] for name in factor_order if selected[name] is not None)
    rendered_text = common_skeleton.replace("{factor_blocks}", factor_text)
    _reject_locking_language(common_skeleton + identity_block + continuity_block + rendered_text)
    return ProbePersonaView.create(
        identity_present=identity_present,
        continuity_present=continuity_present,
        common_skeleton=common_skeleton,
        identity_block=visible_identity,
        continuity_block=visible_continuity,
        rendered_text=rendered_text,
    )


def validate_probe_persona_factor_diff(
    views: tuple[ProbePersonaView, ...],
) -> Mapping[str, object]:
    """Verify exact four-cell coverage and byte-identical non-factor fields."""

    if type(views) is not tuple or len(views) != 4:
        raise ValueError("views must contain exactly four probe persona records")
    if not all(isinstance(view, ProbePersonaView) for view in views):
        raise TypeError("views must contain ProbePersonaView records")
    expected = {(False, False), (False, True), (True, False), (True, True)}
    observed = {(view.identity_present, view.continuity_present) for view in views}
    if observed != expected:
        raise ValueError("views must cover all four identity x continuity conditions")

    payloads = [view.to_payload() for view in views]
    invariant_fields = set(payloads[0]) - _ALLOWED_VARYING_FIELDS
    for payload in payloads:
        if set(payload) != set(payloads[0]):
            raise ValueError("persona fields differ outside the allowed factor payload")
        _reject_locking_language(payload["rendered_text"])
    for field in sorted(invariant_fields):
        baseline = payloads[0][field]
        if any(payload[field] != baseline for payload in payloads[1:]):
            raise ValueError(f"persona invariant differs outside allowed fields: {field}")

    identities = {view.identity_block for view in views if view.identity_present}
    continuities = {view.continuity_block for view in views if view.continuity_present}
    if len(identities) != 1 or None in identities:
        raise ValueError("present identity block must be reused byte-for-byte")
    if len(continuities) != 1 or None in continuities:
        raise ValueError("present continuity block must be reused byte-for-byte")
    if any(view.identity_block is not None for view in views if not view.identity_present):
        raise ValueError("absent identity blocks must be empty")
    if any(view.continuity_block is not None for view in views if not view.continuity_present):
        raise ValueError("absent continuity blocks must be empty")
    return {
        "valid": True,
        "condition_count": 4,
        "allowed_varying_fields": sorted(_ALLOWED_VARYING_FIELDS),
    }
