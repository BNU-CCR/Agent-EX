"""Immutable calibration-only records for independent Phase 0A probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..domain import (
    _freeze,
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    _require_tuple,
    canonical_payload_hash,
)


_CALIBRATION_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}


def _require_calibration_payload(
    payload: Mapping[str, object],
    *,
    expected_fields: set[str],
    record_name: str,
    schema_version: str,
) -> None:
    if type(payload) is not dict or set(payload) != expected_fields:
        raise ValueError(f"{record_name} payload fields do not match the calibration-only contract")
    _require_json_transport(payload, f"{record_name} payload")
    if payload["schema_version"] != schema_version:
        raise ValueError(f"{record_name} schema_version is not supported")
    if payload["metadata"] != _CALIBRATION_METADATA:
        raise ValueError(
            f"{record_name} metadata must remain calibration-only without formal authority"
        )


def _derived_id(prefix: str, payload: Mapping[str, object]) -> str:
    return prefix + canonical_payload_hash(payload)


def _require_derived_id(
    field_name: str,
    actual: str,
    *,
    prefix: str,
    payload: Mapping[str, object],
) -> None:
    _require_id(field_name, actual)
    if actual != _derived_id(prefix, payload):
        raise ValueError(f"{field_name} does not match its derived calibration identity")


@dataclass(frozen=True, slots=True)
class ProbeTopicCandidate:
    """A hash-bound topic candidate with exactly three wording variants."""

    candidate_id: str
    construct: str
    fact_card: str
    statements: tuple[str, str, str]
    stance_labels_1_7: tuple[str, ...]
    statement_hashes: tuple[str, str, str]
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.topic-candidate.v1"
    _ID_PREFIX = "probe-topic-"

    def __post_init__(self) -> None:
        _require_string("construct", self.construct)
        _require_string("fact_card", self.fact_card)
        _require_tuple("statements", self.statements)
        if len(self.statements) != 3:
            raise ValueError("statements must contain exactly three texts")
        for statement in self.statements:
            _require_string("statement", statement)
        _require_tuple("stance_labels_1_7", self.stance_labels_1_7)
        if len(self.stance_labels_1_7) != 7:
            raise ValueError("stance_labels_1_7 must contain exactly seven labels")
        for label in self.stance_labels_1_7:
            _require_string("stance_label", label)
        _require_tuple("statement_hashes", self.statement_hashes)
        if len(self.statement_hashes) != 3:
            raise ValueError("statement_hashes must contain exactly three hashes")
        for statement, digest in zip(self.statements, self.statement_hashes, strict=True):
            _require_sha256("statement_hash", digest)
            _require_payload_hash("statement_hash", digest, statement)
        _require_derived_id(
            "candidate_id",
            self.candidate_id,
            prefix=self._ID_PREFIX,
            payload=self._identity_payload(),
        )
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "construct": self.construct,
            "fact_card": self.fact_card,
            "statements": self.statements,
            "stance_labels_1_7": self.stance_labels_1_7,
            "statement_hashes": self.statement_hashes,
            "metadata": self.metadata,
        }

    def content_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "candidate_id": self.candidate_id}

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        construct: str,
        fact_card: str,
        statements: tuple[str, str, str],
        stance_labels_1_7: tuple[str, ...],
    ) -> ProbeTopicCandidate:
        statement_hashes = tuple(canonical_payload_hash(value) for value in statements)
        identity_payload = {
            "schema_version": cls._SCHEMA_VERSION,
            "construct": construct,
            "fact_card": fact_card,
            "statements": statements,
            "stance_labels_1_7": stance_labels_1_7,
            "statement_hashes": statement_hashes,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        candidate_id = _derived_id(cls._ID_PREFIX, identity_payload)
        content = {**identity_payload, "candidate_id": candidate_id}
        return cls(
            candidate_id=candidate_id,
            construct=construct,
            fact_card=fact_card,
            statements=statements,
            stance_labels_1_7=stance_labels_1_7,
            statement_hashes=statement_hashes,  # type: ignore[arg-type]
            record_hash=canonical_payload_hash(content),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeTopicCandidate:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="topic candidate",
            schema_version=cls._SCHEMA_VERSION,
        )
        tuple_fields = ("statements", "stance_labels_1_7", "statement_hashes")
        if any(type(payload[name]) is not list for name in tuple_fields):
            raise TypeError("topic candidate repeated fields must use JSON arrays")
        return cls(
            candidate_id=payload["candidate_id"],
            construct=payload["construct"],
            fact_card=payload["fact_card"],
            statements=tuple(payload["statements"]),
            stance_labels_1_7=tuple(payload["stance_labels_1_7"]),
            statement_hashes=tuple(payload["statement_hashes"]),
            record_hash=payload["record_hash"],
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbePersonaView:
    """A mechanically rendered identity/continuity calibration view."""

    persona_view_id: str
    identity_present: bool
    continuity_present: bool
    common_skeleton: str
    identity_block: str | None
    continuity_block: str | None
    rendered_text: str
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.persona-view.v1"
    _ID_PREFIX = "probe-persona-"

    def __post_init__(self) -> None:
        for name, value in (
            ("identity_present", self.identity_present),
            ("continuity_present", self.continuity_present),
        ):
            if type(value) is not bool:
                raise TypeError(f"{name} must be a boolean")
        _require_string("common_skeleton", self.common_skeleton)
        _require_string("identity_block", self.identity_block, optional=True)
        _require_string("continuity_block", self.continuity_block, optional=True)
        _require_string("rendered_text", self.rendered_text)
        if self.identity_present != (self.identity_block is not None):
            raise ValueError("identity_block presence must match identity_present")
        if self.continuity_present != (self.continuity_block is not None):
            raise ValueError("continuity_block presence must match continuity_present")
        _require_derived_id(
            "persona_view_id",
            self.persona_view_id,
            prefix=self._ID_PREFIX,
            payload=self._identity_payload(),
        )
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "identity_present": self.identity_present,
            "continuity_present": self.continuity_present,
            "common_skeleton": self.common_skeleton,
            "identity_block": self.identity_block,
            "continuity_block": self.continuity_block,
            "rendered_text": self.rendered_text,
            "metadata": self.metadata,
        }

    def content_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "persona_view_id": self.persona_view_id}

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        identity_present: bool,
        continuity_present: bool,
        common_skeleton: str,
        identity_block: str | None,
        continuity_block: str | None,
        rendered_text: str,
    ) -> ProbePersonaView:
        identity_payload = {
            "schema_version": cls._SCHEMA_VERSION,
            "identity_present": identity_present,
            "continuity_present": continuity_present,
            "common_skeleton": common_skeleton,
            "identity_block": identity_block,
            "continuity_block": continuity_block,
            "rendered_text": rendered_text,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        persona_view_id = _derived_id(cls._ID_PREFIX, identity_payload)
        content = {**identity_payload, "persona_view_id": persona_view_id}
        return cls(
            persona_view_id=persona_view_id,
            identity_present=identity_present,
            continuity_present=continuity_present,
            common_skeleton=common_skeleton,
            identity_block=identity_block,
            continuity_block=continuity_block,
            rendered_text=rendered_text,
            record_hash=canonical_payload_hash(content),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbePersonaView:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="persona view",
            schema_version=cls._SCHEMA_VERSION,
        )
        return cls(
            persona_view_id=payload["persona_view_id"],
            identity_present=payload["identity_present"],
            continuity_present=payload["continuity_present"],
            common_skeleton=payload["common_skeleton"],
            identity_block=payload["identity_block"],
            continuity_block=payload["continuity_block"],
            rendered_text=payload["rendered_text"],
            record_hash=payload["record_hash"],
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeCase:
    """An independent, hash-bound calibration case without network identity."""

    probe_case_id: str
    specification_hash: str
    candidate_id: str
    case_family: str
    scenario_id: str
    variant_index: int
    scale_id: str
    field_order_id: str
    replicate_id: str
    requested_seed: int | None
    persona_view_id: str
    rendered_messages: tuple[Mapping[str, str], ...]
    rendered_messages_hash: str
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.probe-case.v1"
    _ID_PREFIX = "probe-case-"

    def __post_init__(self) -> None:
        _require_sha256("specification_hash", self.specification_hash)
        for name, value in (
            ("candidate_id", self.candidate_id),
            ("scenario_id", self.scenario_id),
            ("scale_id", self.scale_id),
            ("field_order_id", self.field_order_id),
            ("replicate_id", self.replicate_id),
            ("persona_view_id", self.persona_view_id),
        ):
            _require_id(name, value)
        _require_string("case_family", self.case_family)
        _require_int("variant_index", self.variant_index)
        if self.requested_seed is not None:
            _require_int("requested_seed", self.requested_seed)
        _require_tuple("rendered_messages", self.rendered_messages)
        if not self.rendered_messages:
            raise ValueError("rendered_messages must not be empty")
        for message in self.rendered_messages:
            if not isinstance(message, Mapping) or set(message) != {"role", "content"}:
                raise ValueError("rendered_messages must contain exact role/content mappings")
            _require_string("message role", message["role"])
            _require_string("message content", message["content"])
        _require_sha256("rendered_messages_hash", self.rendered_messages_hash)
        _require_payload_hash(
            "rendered_messages_hash", self.rendered_messages_hash, self.rendered_messages
        )
        _require_derived_id(
            "probe_case_id",
            self.probe_case_id,
            prefix=self._ID_PREFIX,
            payload=self._identity_payload(),
        )
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "rendered_messages", _freeze(self.rendered_messages))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "specification_hash": self.specification_hash,
            "candidate_id": self.candidate_id,
            "case_family": self.case_family,
            "scenario_id": self.scenario_id,
            "variant_index": self.variant_index,
            "scale_id": self.scale_id,
            "field_order_id": self.field_order_id,
            "replicate_id": self.replicate_id,
            "requested_seed": self.requested_seed,
            "persona_view_id": self.persona_view_id,
            "rendered_messages": self.rendered_messages,
            "rendered_messages_hash": self.rendered_messages_hash,
            "metadata": self.metadata,
        }

    def content_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "probe_case_id": self.probe_case_id}

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        specification_hash: str,
        candidate_id: str,
        case_family: str,
        scenario_id: str,
        variant_index: int,
        scale_id: str,
        field_order_id: str,
        replicate_id: str,
        requested_seed: int | None,
        persona_view_id: str,
        rendered_messages: tuple[Mapping[str, str], ...],
    ) -> ProbeCase:
        rendered_messages_hash = canonical_payload_hash(rendered_messages)
        identity_payload = {
            "schema_version": cls._SCHEMA_VERSION,
            "specification_hash": specification_hash,
            "candidate_id": candidate_id,
            "case_family": case_family,
            "scenario_id": scenario_id,
            "variant_index": variant_index,
            "scale_id": scale_id,
            "field_order_id": field_order_id,
            "replicate_id": replicate_id,
            "requested_seed": requested_seed,
            "persona_view_id": persona_view_id,
            "rendered_messages": rendered_messages,
            "rendered_messages_hash": rendered_messages_hash,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        probe_case_id = _derived_id(cls._ID_PREFIX, identity_payload)
        content = {**identity_payload, "probe_case_id": probe_case_id}
        return cls(
            probe_case_id=probe_case_id,
            specification_hash=specification_hash,
            candidate_id=candidate_id,
            case_family=case_family,
            scenario_id=scenario_id,
            variant_index=variant_index,
            scale_id=scale_id,
            field_order_id=field_order_id,
            replicate_id=replicate_id,
            requested_seed=requested_seed,
            persona_view_id=persona_view_id,
            rendered_messages=rendered_messages,
            rendered_messages_hash=rendered_messages_hash,
            record_hash=canonical_payload_hash(content),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeCase:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="probe case",
            schema_version=cls._SCHEMA_VERSION,
        )
        if type(payload["rendered_messages"]) is not list:
            raise TypeError("probe case rendered_messages must use a JSON array")
        return cls(
            probe_case_id=payload["probe_case_id"],
            specification_hash=payload["specification_hash"],
            candidate_id=payload["candidate_id"],
            case_family=payload["case_family"],
            scenario_id=payload["scenario_id"],
            variant_index=payload["variant_index"],
            scale_id=payload["scale_id"],
            field_order_id=payload["field_order_id"],
            replicate_id=payload["replicate_id"],
            requested_seed=payload["requested_seed"],
            persona_view_id=payload["persona_view_id"],
            rendered_messages=tuple(payload["rendered_messages"]),
            rendered_messages_hash=payload["rendered_messages_hash"],
            record_hash=payload["record_hash"],
        )  # type: ignore[arg-type]
