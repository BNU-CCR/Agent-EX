"""Loading, validation, policy checks, and execution-projection hashing."""

from __future__ import annotations

import hashlib
from importlib import resources
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping
import unicodedata

import jsonschema
import yaml


_UNRESOLVED_FULL = re.compile(r"UNRESOLVED\[(P1_[A-Z0-9_]+)\]")
_PLACEHOLDER_TOKENS = (
    "UNRESOLVED",
    "NOTYETDECIDED",
    "PLACEHOLDER",
    "UNDECIDED",
    "PENDING",
    "FIXME",
    "TODO",
    "TBD",
)


def _packaged_schema() -> dict[str, Any]:
    text = resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text(
        encoding="utf-8"
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
    normalized = unicodedata.normalize("NFKC", text).upper()
    collapsed = "".join(character for character in normalized if character.isalnum())
    return next((token for token in _PLACEHOLDER_TOKENS if token in collapsed), None)


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


def _validate_decision_provenance(
    protocol: Mapping[str, Any], schema: Mapping[str, Any], decisions_path: str | Path | None
) -> None:
    required_ids = _schema_decision_ids(schema)
    provenance = protocol["decision_provenance"]
    actual_ids = set(provenance)
    if actual_ids != required_ids:
        missing = sorted(required_ids - actual_ids)
        extra = sorted(actual_ids - required_ids)
        raise ValueError(f"decision provenance must exactly cover schema IDs; missing={missing}, extra={extra}")

    path = Path(decisions_path) if decisions_path is not None else Path(__file__).parents[3] / "docs" / "decisions.md"
    if not path.is_file():
        raise ValueError(f"decision log is missing: {path}")
    decision_log = path.read_text(encoding="utf-8")
    for decision_id, approval in provenance.items():
        record_id = approval["decision_record_id"]
        if record_id not in decision_log:
            raise ValueError(f"decision record {record_id} is absent from decision log")
        if decision_id not in decision_log:
            raise ValueError(f"decision ID {decision_id} is absent from decision log")


def _validate_schema(
    protocol: Mapping[str, Any], schema: Mapping[str, Any], *, label: str = "schema"
) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(protocol),
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
        _validate_decision_provenance(protocol, canonical_schema, decisions_path)


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
