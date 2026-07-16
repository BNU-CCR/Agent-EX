"""Cross-artifact source-of-truth checks."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

import yaml


CANONICAL_HUMAN_PROTOCOL_PATH = "docs/paper1-protocol.md"
_SUMMARY_PATTERN = re.compile(
    r"<!-- BEGIN GENERATED PROTOCOL SUMMARY -->\s*```yaml\s*(.*?)\s*```\s*"
    r"<!-- END GENERATED PROTOCOL SUMMARY -->",
    re.DOTALL,
)


def validate_human_protocol_reference(protocol: Mapping[str, Any]) -> None:
    actual = protocol.get("human_protocol_reference")
    if actual != CANONICAL_HUMAN_PROTOCOL_PATH:
        raise ValueError(
            f"human_protocol_reference must be {CANONICAL_HUMAN_PROTOCOL_PATH!r}, got {actual!r}"
        )


def human_protocol_projection(protocol: Mapping[str, Any]) -> dict[str, Any]:
    design = protocol["design"]
    model = protocol["model"]
    from .protocol import canonical_protocol_hash

    return {
        "protocol_id": protocol["protocol"]["id"],
        "execution_hash": canonical_protocol_hash(protocol),
        "primary_outcome_id": protocol["outcomes"]["primary"]["id"],
        "primary_estimand_id": protocol["primary_estimand"]["id"],
        "factor_levels": design["factor_levels"],
        "cell_ids": [cell["id"] for cell in design["cells"]],
        "formal_scale": {
            "population_size": design["population_size"],
            "rounds": design["rounds"],
            "matched_seeds_initial": design["matched_seeds_initial"],
            "matched_seeds_max": design["matched_seeds_max"],
        },
        "model_route": {
            "provider": model["provider"],
            "model_id": model["model_id"],
            "precision": model["precision"],
            "thinking": protocol["generation"]["thinking"],
            "runtime": protocol["runtime"]["vllm"]["name"],
        },
    }


def render_human_protocol_summary(protocol: Mapping[str, Any]) -> str:
    """Render the generated Markdown region without writing any files."""

    body = yaml.safe_dump(
        human_protocol_projection(protocol), sort_keys=False, allow_unicode=True
    ).rstrip()
    return (
        "<!-- BEGIN GENERATED PROTOCOL SUMMARY -->\n"
        f"```yaml\n{body}\n```\n"
        "<!-- END GENERATED PROTOCOL SUMMARY -->"
    )


def update_human_protocol_summary(markdown: str, protocol: Mapping[str, Any]) -> str:
    """Return Markdown with its generated region replaced; never write implicitly."""

    if _SUMMARY_PATTERN.search(markdown) is None:
        raise ValueError("generated protocol summary markers are missing")
    return _SUMMARY_PATTERN.sub(render_human_protocol_summary(protocol), markdown, count=1)


def validate_human_protocol_sync(protocol: Mapping[str, Any], markdown_path: str | Path) -> None:
    text = Path(markdown_path).read_text(encoding="utf-8")
    match = _SUMMARY_PATTERN.search(text)
    if match is None:
        raise ValueError("generated protocol summary markers are missing")
    summary = yaml.safe_load(match.group(1))
    if summary != human_protocol_projection(protocol):
        raise ValueError("generated human protocol summary drift detected")
