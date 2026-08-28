"""Strict, resource-bounded, evidence-preserving parser for Phase 4B-7."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping

from .adapters.base import AdapterResponse, _has_trusted_response_seal
from .domain import (
    _freeze,
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
)
from .topic import TopicPackage

_PARSER_ID = "paper1.strict_agent_update_parser"
_PARSER_VERSION = "2.0.0"
_PARSE_SCHEMA = "paper1.mock-parse-evidence.v2"
_LIMITS_SCHEMA = "paper1.mock-parser-limits.v1"
_PROVIDER_FIELDS = ("stance", "confidence", "public_reason")
_PARSED_FIELDS = ("topic_package_id", "topic_package_hash", "stance", "confidence", "public_reason")
_METADATA = {"mock_only": True, "research_parameter_status": "not_frozen"}


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_raw_chars: int
    max_raw_bytes: int
    max_json_depth: int
    max_reason_chars: int
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("max_raw_chars", "max_raw_bytes", "max_json_depth", "max_reason_chars"):
            _require_int(name, getattr(self, name), minimum=1)
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _LIMITS_SCHEMA,
            "max_raw_chars": self.max_raw_chars,
            "max_raw_bytes": self.max_raw_bytes,
            "max_json_depth": self.max_json_depth,
            "max_reason_chars": self.max_reason_chars,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        *,
        max_raw_chars: int,
        max_raw_bytes: int,
        max_json_depth: int,
        max_reason_chars: int,
        mock_only: bool,
    ) -> ParserLimits:
        if mock_only is not True:
            raise ValueError("Phase 4B-7 parser limits must be explicitly mock_only")
        content = {
            "schema_version": _LIMITS_SCHEMA,
            "max_raw_chars": max_raw_chars,
            "max_raw_bytes": max_raw_bytes,
            "max_json_depth": max_json_depth,
            "max_reason_chars": max_reason_chars,
            "metadata": dict(_METADATA),
        }
        return cls(
            max_raw_chars,
            max_raw_bytes,
            max_json_depth,
            max_reason_chars,
            canonical_payload_hash(content),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ParserLimits:
        expected = {
            "schema_version",
            "max_raw_chars",
            "max_raw_bytes",
            "max_json_depth",
            "max_reason_chars",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("parser limits fields do not match the mock contract")
        _require_json_transport(payload, "parser limits")
        if payload["schema_version"] != _LIMITS_SCHEMA or payload["metadata"] != _METADATA:
            raise ValueError("parser limits schema or metadata is invalid")
        return cls(
            payload["max_raw_chars"],
            payload["max_raw_bytes"],
            payload["max_json_depth"],
            payload["max_reason_chars"],
            payload["record_hash"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class ParsedAgentUpdate:
    topic_package_id: str
    topic_package_hash: str
    stance: str
    confidence: int
    public_reason: str

    def __post_init__(self) -> None:
        _require_id("topic_package_id", self.topic_package_id)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_string("stance", self.stance)
        if type(self.confidence) is not int:
            raise TypeError("confidence must be a JSON integer")
        if not 1 <= self.confidence <= 5:
            raise ValueError("confidence must be between 1 and 5")
        _require_string("public_reason", self.public_reason)

    def provider_payload(self) -> dict[str, object]:
        return {
            "stance": self.stance,
            "confidence": self.confidence,
            "public_reason": self.public_reason,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            **self.provider_payload(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ParsedAgentUpdate:
        if type(payload) is not dict or tuple(payload) != _PARSED_FIELDS:
            raise ValueError("parsed agent update fields do not match the bound contract")
        _require_json_transport(payload, "parsed agent update")
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ParseEvidence:
    parser_id: str
    parser_version: str
    parser_limits_payload: Mapping[str, object]
    parser_limits_hash: str
    response_id: str
    response_hash: str
    request_id: str
    request_hash: str
    event_id: str
    attempt_index: int
    attempt_id: str
    topic_package_id: str
    topic_package_hash: str
    raw_response: str
    raw_response_hash: str
    success: bool
    parsed: ParsedAgentUpdate | None
    parsed_response_hash: str | None
    error: Mapping[str, str] | None
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        if (self.parser_id, self.parser_version) != (_PARSER_ID, _PARSER_VERSION):
            raise ValueError("parser identity or version is unsupported")
        if type(self.parser_limits_payload) is not dict:
            raise TypeError("parser_limits_payload must be a strict JSON object")
        limits = ParserLimits.from_payload(self.parser_limits_payload)
        if limits.record_hash != self.parser_limits_hash:
            raise ValueError("parser limits hash does not match")
        for name in ("response_id", "request_id", "event_id", "attempt_id", "topic_package_id"):
            _require_id(name, getattr(self, name))
        for name in ("response_hash", "request_hash", "topic_package_hash"):
            _require_sha256(name, getattr(self, name))
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if type(self.raw_response) is not str:
            raise TypeError("raw_response must be a string")
        _require_sha256("raw_response_hash", self.raw_response_hash)
        _require_payload_hash("raw_response_hash", self.raw_response_hash, self.raw_response)
        if type(self.success) is not bool:
            raise TypeError("success must be a boolean")
        if self.success:
            if not isinstance(self.parsed, ParsedAgentUpdate) or self.error is not None:
                raise ValueError("successful parse requires parsed content without an error")
            _require_sha256("parsed_response_hash", self.parsed_response_hash)
            _require_payload_hash(
                "parsed_response_hash", self.parsed_response_hash, self.parsed.to_payload()
            )
        else:
            if self.parsed is not None or self.parsed_response_hash is not None:
                raise ValueError("failed parse cannot contain parsed content")
            if type(self.error) is not dict or set(self.error) != {"code", "message"}:
                raise ValueError("failed parse requires an exact code/message error")
            _require_string("error code", self.error["code"])
            _require_string("error message", self.error["message"])
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "parser_limits_payload", _freeze(self.parser_limits_payload))
        object.__setattr__(self, "error", _freeze(self.error))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _PARSE_SCHEMA,
            "parser_id": self.parser_id,
            "parser_version": self.parser_version,
            "parser_limits_payload": self.parser_limits_payload,
            "parser_limits_hash": self.parser_limits_hash,
            "response_id": self.response_id,
            "response_hash": self.response_hash,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "event_id": self.event_id,
            "attempt_index": self.attempt_index,
            "attempt_id": self.attempt_id,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "raw_response": self.raw_response,
            "raw_response_hash": self.raw_response_hash,
            "success": self.success,
            "parsed": None if self.parsed is None else self.parsed.to_payload(),
            "parsed_response_hash": self.parsed_response_hash,
            "error": self.error,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ParseEvidence:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("parse evidence fields do not match the v2 contract")
        _require_json_transport(payload, "parse evidence")
        if payload["schema_version"] != _PARSE_SCHEMA or payload["metadata"] != _METADATA:
            raise ValueError("parse evidence schema or metadata is unsupported")
        if type(payload["parser_limits_payload"]) is not dict:
            raise TypeError("parser limits evidence must be a JSON object")
        parsed, error = payload["parsed"], payload["error"]
        if parsed is not None and type(parsed) is not dict:
            raise TypeError("parsed evidence must be a JSON object or null")
        if error is not None and type(error) is not dict:
            raise TypeError("parse error must be a JSON object or null")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["parsed"] = None if parsed is None else ParsedAgentUpdate.from_payload(parsed)
        return cls(**values)  # type: ignore[arg-type]


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


def _encode_raw_utf8(raw: str) -> bytes:
    """Encode only after conservative character preflights bound the allocation."""

    return raw.encode("utf-8", "strict")


def _validate_tree(value: object, max_depth: int) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if type(item) is str:
            item.encode("utf-8", "strict")
        elif type(item) is dict:
            if depth >= max_depth:
                raise OverflowError
            stack.extend((key, depth + 1) for key in item)
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            if depth >= max_depth:
                raise OverflowError
            stack.extend((child, depth + 1) for child in item)


def _make_evidence(
    response: AdapterResponse,
    topic: TopicPackage,
    limits: ParserLimits,
    parsed: ParsedAgentUpdate | None,
    error: Mapping[str, str] | None,
) -> ParseEvidence:
    assert response.raw_response is not None and response.raw_response_hash is not None
    values = {
        "parser_id": _PARSER_ID,
        "parser_version": _PARSER_VERSION,
        "parser_limits_payload": limits.to_payload(),
        "parser_limits_hash": limits.record_hash,
        "response_id": response.response_id,
        "response_hash": response.record_hash,
        "request_id": response.request_id,
        "request_hash": response.request_hash,
        "event_id": response.event_id,
        "attempt_index": response.attempt_index,
        "attempt_id": response.attempt_id,
        "topic_package_id": topic.topic_id,
        "topic_package_hash": topic.package_hash,
        "raw_response": response.raw_response,
        "raw_response_hash": response.raw_response_hash,
        "success": parsed is not None,
        "parsed": parsed,
        "parsed_response_hash": None
        if parsed is None
        else canonical_payload_hash(parsed.to_payload()),
        "error": error,
    }
    content = {
        "schema_version": _PARSE_SCHEMA,
        **values,
        "parsed": None if parsed is None else parsed.to_payload(),
        "metadata": dict(_METADATA),
    }
    return ParseEvidence(**values, record_hash=canonical_payload_hash(content))


def _failure(
    response: AdapterResponse, topic: TopicPackage, limits: ParserLimits, code: str, message: str
) -> ParseEvidence:
    return _make_evidence(response, topic, limits, None, {"code": code, "message": message})


def parse_agent_update(
    adapter_response: AdapterResponse, *, topic_package: TopicPackage, limits: ParserLimits
) -> ParseEvidence:
    """Parse one exact response without repair, coercion, defaults, or retries."""
    if not isinstance(adapter_response, AdapterResponse):
        raise TypeError("adapter_response must be an AdapterResponse")
    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be a TopicPackage")
    if not isinstance(limits, ParserLimits):
        raise TypeError("limits must be explicit typed ParserLimits")
    raw = adapter_response.raw_response
    encoded: bytes | None = None
    if adapter_response.outcome == "response":
        if type(raw) is not str:
            raise ValueError("response outcome raw content must be an exact string")
        if len(raw) > limits.max_raw_chars:
            raise ValueError("response exceeds explicit raw character limit")
        if len(raw) > limits.max_raw_bytes:
            raise ValueError("response exceeds explicit raw byte limit")
        try:
            encoded = _encode_raw_utf8(raw)
        except UnicodeError:
            encoded = None
        if encoded is not None and len(encoded) > limits.max_raw_bytes:
            raise ValueError("response exceeds explicit raw byte limit")
    if not _has_trusted_response_seal(adapter_response):
        raise ValueError("adapter_response is not a trusted sealed response capability")
    if (
        adapter_response.topic_package_id != topic_package.topic_id
        or adapter_response.topic_package_hash != topic_package.package_hash
    ):
        raise ValueError("adapter response topic package does not match parser topic")
    if adapter_response.outcome != "response" or adapter_response.raw_response is None:
        raise ValueError("parser requires a response outcome with raw content")
    assert type(raw) is str
    if encoded is None:
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "unicode",
            "response is not valid UTF-8 Unicode scalar text",
        )
    try:
        value = json.loads(
            raw, object_pairs_hook=_object_without_duplicates, parse_constant=_reject_constant
        )
        _validate_tree(value, limits.max_json_depth)
    except _DuplicateKey:
        return _failure(
            adapter_response, topic_package, limits, "duplicate", "JSON keys must be unique"
        )
    except (OverflowError, RecursionError):
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "depth",
            "JSON nesting exceeds explicit depth limit",
        )
    except UnicodeError:
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "unicode",
            "response contains a non-Unicode-scalar string",
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return _failure(
            adapter_response, topic_package, limits, "json", "response must be strict JSON"
        )
    if type(value) is not dict or tuple(value) != _PROVIDER_FIELDS:
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "fields",
            "response fields and order must be stance, confidence, public_reason",
        )
    stance, confidence, reason = value["stance"], value["confidence"], value["public_reason"]
    if type(stance) is not str:
        return _failure(
            adapter_response, topic_package, limits, "stance_type", "stance must be text"
        )
    if stance not in topic_package.stance_labels:
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "stance_label",
            "stance must be one of the topic package's seven text labels",
        )
    if type(confidence) is not int:
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "confidence_type",
            "confidence must be a JSON integer",
        )
    if not 1 <= confidence <= 5:
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "confidence_range",
            "confidence must be between 1 and 5",
        )
    if type(reason) is not str:
        return _failure(
            adapter_response, topic_package, limits, "reason_type", "public_reason must be text"
        )
    if not reason.strip():
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "reason",
            "public_reason must be non-empty text",
        )
    if len(reason) > limits.max_reason_chars:
        return _failure(
            adapter_response,
            topic_package,
            limits,
            "reason_size",
            "public_reason exceeds explicit character limit",
        )
    parsed = ParsedAgentUpdate(
        topic_package.topic_id, topic_package.package_hash, stance, confidence, reason
    )
    return _make_evidence(adapter_response, topic_package, limits, parsed, None)


def validate_parse_evidence(
    evidence: ParseEvidence,
    adapter_response: AdapterResponse,
    topic_package: TopicPackage,
    limits: ParserLimits,
) -> None:
    """Replay parsing and compare every success or failure evidence field."""
    if not isinstance(evidence, ParseEvidence):
        raise TypeError("evidence must be ParseEvidence")
    expected = parse_agent_update(adapter_response, topic_package=topic_package, limits=limits)
    if evidence != expected:
        raise ValueError("parse evidence replay does not match trusted response, topic, and limits")
