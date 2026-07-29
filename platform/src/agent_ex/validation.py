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
_DECISION_RECORDS_PATTERN = re.compile(
    r"<!-- BEGIN DECISION RECORDS -->\s*```yaml\s*(.*?)\s*```\s*"
    r"<!-- END DECISION RECORDS -->",
    re.DOTALL,
)
_DECISION_RECORD_KEYS = {
    "decision_record_id",
    "approved_at",
    "approvers",
    "field_ids",
    "artifact_hashes",
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SUMMARY_BEGIN = "<!-- BEGIN GENERATED PROTOCOL SUMMARY -->"
_SUMMARY_END = "<!-- END GENERATED PROTOCOL SUMMARY -->"


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
        "key_secondary_estimand_ids": protocol["analysis"]["hierarchy"]["key_secondary"],
        "outcome_priority": protocol["analysis"]["outcome_priority"],
        "process_contract": {
            "activation_mode": protocol["dynamics"]["activation_mode"],
            "feed_message_capacity": protocol["exposure"]["feed_message_capacity"],
            "event_identity": protocol["event_model"]["identity"],
            "resume_cursor": protocol["checkpoint"]["resume_cursor"],
        },
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

    matches = list(_SUMMARY_PATTERN.finditer(markdown))
    if (
        markdown.count(_SUMMARY_BEGIN) != 1
        or markdown.count(_SUMMARY_END) != 1
        or len(matches) != 1
    ):
        raise ValueError("human protocol must contain exactly one ordered generated summary block")
    return _SUMMARY_PATTERN.sub(render_human_protocol_summary(protocol), markdown, count=1)


def validate_human_protocol_sync(protocol: Mapping[str, Any], markdown_path: str | Path) -> None:
    text = Path(markdown_path).read_text(encoding="utf-8")
    matches = list(_SUMMARY_PATTERN.finditer(text))
    if text.count(_SUMMARY_BEGIN) != 1 or text.count(_SUMMARY_END) != 1 or len(matches) != 1:
        raise ValueError("human protocol must contain exactly one ordered generated summary block")
    match = matches[0]
    summary = yaml.safe_load(match.group(1))
    if summary != human_protocol_projection(protocol):
        raise ValueError("generated human protocol summary drift detected")


def load_decision_records(markdown_path: str | Path) -> dict[str, dict[str, Any]]:
    """Load the fenced machine-readable decision records, keyed by exact record ID."""

    text = Path(markdown_path).read_text(encoding="utf-8")
    matches = list(_DECISION_RECORDS_PATTERN.finditer(text))
    if len(matches) != 1:
        raise ValueError("decision log must contain exactly one fenced decision records block")
    document = yaml.safe_load(matches[0].group(1))
    if not isinstance(document, dict) or set(document) != {"records"}:
        raise ValueError("decision records block must contain only a records list")
    records = document["records"]
    if not isinstance(records, list):
        raise ValueError("decision records must be a list")

    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != _DECISION_RECORD_KEYS:
            raise ValueError("each decision record must contain exactly the required fields")
        record_id = record["decision_record_id"]
        approved_at = record["approved_at"]
        approvers = record["approvers"]
        field_ids = record["field_ids"]
        artifact_hashes = record["artifact_hashes"]
        if not isinstance(record_id, str) or not re.fullmatch(r"D-[A-Z0-9-]+", record_id):
            raise ValueError("decision record ID must use the canonical D-* format")
        if record_id in indexed:
            raise ValueError(f"duplicate decision record ID: {record_id}")
        if not isinstance(approved_at, str):
            raise ValueError(f"approved_at must be a string in decision record {record_id}")
        if (
            not isinstance(approvers, list)
            or not approvers
            or any(
                not isinstance(approver, str)
                or not approver.strip()
                or approver.strip().casefold() in {"none", "null", "n/a"}
                for approver in approvers
            )
            or len(approvers) != len(set(approvers))
        ):
            raise ValueError(
                f"approvers must be nonempty and unique in decision record {record_id}"
            )
        if (
            not isinstance(field_ids, list)
            or not field_ids
            or any(
                not isinstance(field_id, str) or re.fullmatch(r"P1_[A-Z0-9_]+", field_id) is None
                for field_id in field_ids
            )
            or len(field_ids) != len(set(field_ids))
        ):
            raise ValueError(
                f"field_ids must be canonical and unique in decision record {record_id}"
            )
        if not isinstance(artifact_hashes, dict) or any(
            not isinstance(name, str)
            or not name
            or not isinstance(value, str)
            or _SHA256.fullmatch(value) is None
            for name, value in artifact_hashes.items()
        ):
            raise ValueError(f"artifact_hashes must map artifact IDs to SHA-256 in {record_id}")
        if set(artifact_hashes) != set(field_ids):
            raise ValueError(
                f"artifact_hashes must exactly cover field_ids in decision record {record_id}"
            )
        indexed[record_id] = record
    return indexed


def load_research_qa_owners(markdown_path: str | Path) -> dict[str, str]:
    """Load exact decision owner roles from the canonical research-QA table."""

    owners: dict[str, str] = {}
    for line in Path(markdown_path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("| P1_"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) < 4 or not columns[3]:
            raise ValueError("research-QA decision rows must include an owner role")
        decision_id = columns[0]
        if decision_id in owners:
            raise ValueError(f"duplicate research-QA decision ID: {decision_id}")
        owners[decision_id] = columns[3]
    return owners
