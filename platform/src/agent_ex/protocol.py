"""Loading, validation, policy checks, and execution-projection hashing."""

from __future__ import annotations

from datetime import datetime
import hashlib
from importlib import resources
import json
import math
import re
from pathlib import Path
import tomllib
from typing import Any, Mapping
import unicodedata

import jsonschema
import yaml


_UNRESOLVED_FULL = re.compile(r"UNRESOLVED\[(P1_[A-Z0-9_]+)\]")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
_PLACEHOLDER_VALUES = {
    "TBD",
    "TODO",
    "FIXME",
    "UNDECIDED",
    "PENDING",
    "NOTDECIDED",
    "NOTYETDECIDED",
    "PLACEHOLDER",
    "NA",
    "???",
    "待定",
    "未决定",
    "待确认",
    "未知",
}
_DECORATED_PLACEHOLDER_PREFIXES = (
    "NOT YET DECIDED",
    "NOT DECIDED",
    "TODO",
    "TBD",
    "FIXME",
    "UNDECIDED",
    "PENDING",
    "PLACEHOLDER",
    "N/A",
    "NA",
    "待定",
    "未决定",
    "待确认",
    "未知",
)
_WHITESPACE_DECORATED_PLACEHOLDERS = {
    "TODO",
    "TBD",
    "FIXME",
    "UNDECIDED",
    "PLACEHOLDER",
    "待定",
    "未决定",
    "待确认",
    "未知",
}
_DEFAULT_IGNORABLE_RANGES = (
    (0x115F, 0x1160),
    (0x3164, 0x3164),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0xE0000, 0xE0FFF),
)


def _is_placeholder_ignorable(character: str) -> bool:
    if unicodedata.category(character) in {"Cf", "Mn", "Me"}:
        return True
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in _DEFAULT_IGNORABLE_RANGES)


def _is_strict_rfc3339_utc(value: object) -> bool:
    if not isinstance(value, str) or _RFC3339_UTC.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


FORMAT_CHECKER = jsonschema.FormatChecker()
FORMAT_CHECKER.checks("date-time")(_is_strict_rfc3339_utc)


def _packaged_schema() -> dict[str, Any]:
    text = (
        resources.files("agent_ex.schemas")
        .joinpath("paper1.schema.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def load_protocol(path: str | Path) -> dict[str, Any]:
    """Load a YAML protocol without supplying research defaults."""

    loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("protocol YAML must contain a mapping at its root")
    return loaded


def _walk_strings(value: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.extend(_walk_strings(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_walk_strings(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        found.append((path, value))
    return found


def _resolve_pointer(document: Mapping[str, Any], pointer: str) -> Any:
    current: Any = document
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"formal-required path is missing: {pointer}")
        current = current[part]
    return current


def _validate_formal_required(protocol: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    for pointer in schema.get("x-formal-required", ()):
        value = _resolve_pointer(protocol, pointer)
        if value is None or value == "" or value == [] or value == {}:
            raise ValueError(f"formal-required path is empty: {pointer}")
        if isinstance(value, str) and _placeholder_token(value) is not None:
            raise ValueError(f"formal-required path contains placeholder: {pointer}")


def _validate_finite_numbers(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_finite_numbers(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_finite_numbers(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"numeric values must be finite at {path}")


def _schema_decision_ids(schema: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            decision_id = value.get("x-decision-id")
            if isinstance(decision_id, str):
                found.add(decision_id)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schema.get("properties", {}))
    return found


def _placeholder_token(text: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", text).strip().upper()
    normalized = "".join(
        character for character in normalized if not _is_placeholder_ignorable(character)
    )
    unresolved = _UNRESOLVED_FULL.fullmatch(normalized)
    if unresolved:
        return "UNRESOLVED"
    collapsed = re.sub(r"[\s_/-]+", "", normalized)
    if collapsed.startswith("UNRESOLVED"):
        return "UNRESOLVED"
    if collapsed in _PLACEHOLDER_VALUES:
        return collapsed
    for prefix in _DECORATED_PLACEHOLDER_PREFIXES:
        if not normalized.startswith(prefix):
            continue
        remainder = normalized[len(prefix) :]
        boundary = remainder.lstrip()[:1]
        if boundary and unicodedata.category(boundary)[0] in {"P", "S"}:
            return prefix
        if prefix in _WHITESPACE_DECORATED_PLACEHOLDERS and remainder[:1].isspace():
            return prefix
    return None


def _validate_placeholders(
    protocol: Mapping[str, Any], *, mode: str, schema: Mapping[str, Any]
) -> None:
    registered = _schema_decision_ids(schema)
    for path, text in _walk_strings(protocol):
        token = _placeholder_token(text)
        if token is None:
            continue
        unresolved = _UNRESOLVED_FULL.fullmatch(unicodedata.normalize("NFKC", text))
        if mode == "draft" and unresolved and unresolved.group(1) in registered:
            continue
        raise ValueError(f"placeholder is not permitted at {path}: {token}")


def _validate_cell_matrix(protocol: Mapping[str, Any]) -> None:
    expected = [
        (f"P1-I{i}-C{c}-E{e}", identity, continuity, exposure)
        for i, identity in enumerate(("identity_absent", "identity_present"))
        for c, continuity in enumerate(("continuity_absent", "continuity_present"))
        for e, exposure in enumerate(("self_history_only", "shuffled_social", "ws_neighbors"))
    ]
    actual = [
        (cell["id"], cell["identity"], cell["continuity"], cell["exposure"])
        for cell in protocol["design"]["cells"]
    ]
    if actual != expected:
        raise ValueError("12 cells must use stable IDs and canonical factor ordering")


def _validate_topic_hash(protocol: Mapping[str, Any]) -> None:
    topic = protocol["topic"]
    statement = topic["statement"]
    recorded_hash = topic["statement_sha256"]
    if _UNRESOLVED_FULL.fullmatch(statement) or _UNRESOLVED_FULL.fullmatch(recorded_hash):
        return
    actual_hash = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    if recorded_hash != actual_hash:
        raise ValueError("topic.statement_sha256 does not match topic.statement")


def _validate_approved_at(value: Any, *, record_id: str) -> None:
    if not _is_strict_rfc3339_utc(value):
        raise ValueError(f"approved_at for {record_id} must be strict RFC3339 UTC")


def _decision_artifact_payloads(
    protocol: Mapping[str, Any], schema: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}

    def walk(node: Any, value: Any, pointer: str) -> None:
        if not isinstance(node, Mapping):
            return
        decision_id = node.get("x-decision-id")
        if isinstance(decision_id, str):
            payloads.setdefault(decision_id, {})[pointer] = value
        properties = node.get("properties", {})
        if not isinstance(properties, Mapping) or not isinstance(value, Mapping):
            return
        for name, child in properties.items():
            if name not in value:
                continue
            escaped = str(name).replace("~", "~0").replace("/", "~1")
            walk(child, value[name], f"{pointer}/{escaped}")

    walk(schema, protocol, "")
    return payloads


def _canonical_payload_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _decision_artifact_hashes(
    protocol: Mapping[str, Any], schema: Mapping[str, Any]
) -> dict[str, str]:
    return {
        decision_id: _canonical_payload_hash(payload)
        for decision_id, payload in _decision_artifact_payloads(protocol, schema).items()
    }


def _resolve_formal_path(
    explicit_path: str | Path | None,
    *,
    default_relative_path: str | Path,
    argument_name: str,
) -> Path:
    if explicit_path is not None:
        path = Path(explicit_path)
        if path.is_file():
            return path
        raise ValueError(f"{argument_name} does not identify a file: {path}")

    relative_path = Path(default_relative_path)
    module_path = Path(__file__).resolve()
    for ancestor in module_path.parents:
        if module_path != ancestor / "platform" / "src" / "agent_ex" / "protocol.py":
            continue
        git_marker = ancestor / ".git"
        pyproject_path = ancestor / "platform" / "pyproject.toml"
        if not git_marker.exists() or not pyproject_path.is_file():
            continue
        try:
            project = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get("project", {})
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if project.get("name") != "agent-ex":
            continue
        candidate = ancestor / relative_path
        if candidate.is_file():
            return candidate
    raise ValueError(f"{argument_name} is required for formal validation outside a source checkout")


def _validate_decision_provenance(
    protocol: Mapping[str, Any],
    schema: Mapping[str, Any],
    decisions_path: str | Path | None,
    qa_path: str | Path | None,
) -> None:
    required_ids = _schema_decision_ids(schema)
    provenance = protocol["decision_provenance"]
    actual_ids = set(provenance)
    if actual_ids != required_ids:
        missing = sorted(required_ids - actual_ids)
        extra = sorted(actual_ids - required_ids)
        raise ValueError(
            f"decision provenance must exactly cover schema IDs; missing={missing}, extra={extra}"
        )

    path = _resolve_formal_path(
        decisions_path,
        default_relative_path="docs/decisions.md",
        argument_name="decision log (decisions_path)",
    )
    resolved_qa_path = _resolve_formal_path(
        qa_path,
        default_relative_path="docs/research-qa.md",
        argument_name="qa_path",
    )
    from .validation import load_decision_records, load_research_qa_owners

    records = load_decision_records(path)
    owners = load_research_qa_owners(resolved_qa_path)
    if set(owners) != required_ids:
        raise ValueError("research-QA decision IDs must exactly match schema decision IDs")
    expected_artifact_hashes = _decision_artifact_hashes(protocol, schema)
    if set(expected_artifact_hashes) != required_ids:
        raise ValueError("decision artifact hashes must exactly cover schema decision IDs")
    for decision_id, approval in provenance.items():
        record_id = approval["decision_record_id"]
        record = records.get(record_id)
        if record is None:
            raise ValueError(f"decision record {record_id} is absent from decision log")
        _validate_approved_at(approval["approved_at"], record_id=record_id)
        _validate_approved_at(record["approved_at"], record_id=record_id)
        if decision_id not in record["field_ids"]:
            raise ValueError(
                f"decision ID {decision_id} is absent from decision record {record_id} field_ids"
            )
        if approval["approved_at"] != record["approved_at"]:
            raise ValueError(f"approved_at does not match decision record {record_id}")
        if approval["approvers"] != record["approvers"]:
            raise ValueError(f"approvers do not match decision record {record_id}")
        owner = owners[decision_id]
        if owner not in approval["approvers"]:
            raise ValueError(
                f"approvers for {decision_id} must include research-QA owner role {owner!r}"
            )
        artifact_hashes = record["artifact_hashes"]
        if artifact_hashes.get(decision_id) != expected_artifact_hashes[decision_id]:
            raise ValueError(
                f"artifact hash {decision_id} is not approved by decision record {record_id}"
            )


def _validate_schema(
    protocol: Mapping[str, Any], schema: Mapping[str, Any], *, label: str = "schema"
) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(schema, format_checker=FORMAT_CHECKER).iter_errors(
            protocol
        ),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"{label} validation failed at {location}: {error.message}") from error


def validate_protocol(
    protocol: Mapping[str, Any],
    *,
    mode: str,
    schema_path: str | Path | None = None,
    decisions_path: str | Path | None = None,
    human_protocol_path: str | Path | None = None,
    qa_path: str | Path | None = None,
) -> None:
    """Validate schema and Paper 1 research-safety constraints."""

    required_status = {"draft": "draft", "confirmed": "confirmed", "formal": "frozen"}
    if mode not in required_status:
        raise ValueError("mode must be 'draft', 'confirmed', or 'formal'")
    canonical_schema = _packaged_schema()
    _validate_finite_numbers(protocol)
    _validate_schema(protocol, canonical_schema)
    if protocol["status"] != required_status[mode]:
        raise ValueError(f"{mode} mode requires status={required_status[mode]}")
    if schema_path is not None:
        override = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        override_id = override.get("$id")
        if override_id is not None and override_id != canonical_schema["$id"]:
            raise ValueError("override schema identity must match canonical schema identity")
        _validate_schema(protocol, override, label="override schema")
    _validate_cell_matrix(protocol)
    _validate_topic_hash(protocol)
    _validate_placeholders(protocol, mode=mode, schema=canonical_schema)
    if mode == "formal":
        _validate_formal_required(protocol, canonical_schema)
        _validate_decision_provenance(
            protocol,
            canonical_schema,
            decisions_path,
            qa_path,
        )
        from .validation import (
            validate_human_protocol_reference,
            validate_human_protocol_sync,
        )

        validate_human_protocol_reference(protocol)
        resolved_human_path = _resolve_formal_path(
            human_protocol_path,
            default_relative_path=protocol["human_protocol_reference"],
            argument_name="human_protocol_path",
        )
        validate_human_protocol_sync(protocol, resolved_human_path)


def execution_projection(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Return only schema-declared fields that control execution or analysis."""

    schema = _packaged_schema()
    return {key: protocol[key] for key in schema["x-execution-properties"]}


def canonical_protocol_hash(protocol: Mapping[str, Any]) -> str:
    """Hash the canonical execution projection, excluding review metadata."""

    projection = execution_projection(protocol)
    _validate_finite_numbers(projection)
    encoded = json.dumps(
        projection,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
