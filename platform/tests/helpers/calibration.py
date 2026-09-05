"""Synthetic Phase 0A calibration fixture helpers."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


FIXTURE = Path(__file__).parents[1] / "fixtures" / "paper1" / "phase0a_probe_spec.mock.json"


def probe_spec_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def reversed_nonsemantic_arrays(payload: dict[str, object]) -> dict[str, object]:
    changed = deepcopy(payload)
    for field in ("scales", "field_orders", "persona_conditions", "factor_orders"):
        changed[field].reverse()  # type: ignore[union-attr]
    persona = changed["persona"]
    persona["continuity_blocks"].reverse()  # type: ignore[index,union-attr]
    changed["continuity_scenarios"].reverse()  # type: ignore[union-attr]
    changed["replicates"].reverse()  # type: ignore[union-attr]
    return changed
