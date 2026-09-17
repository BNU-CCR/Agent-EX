"""Immutable calibration-only records for independent Phase 0A probes."""

from __future__ import annotations

from dataclasses import dataclass
import math
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
    _require_timestamp,
    _require_tuple,
    canonical_payload_hash,
)


_CALIBRATION_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_PROBE_SCALE_IDS = {"stance-1-7", "stance-0-10"}
_PROBE_FIELD_ORDER_IDS = {
    "stance-confidence-reason",
    "reason-confidence-stance",
}


def _require_probe_declarations(scale_id: object, field_order_id: object) -> None:
    _require_id("scale_id", scale_id)
    _require_id("field_order_id", field_order_id)
    if scale_id not in _PROBE_SCALE_IDS:
        raise ValueError("scale_id is not supported")
    if field_order_id not in _PROBE_FIELD_ORDER_IDS:
        raise ValueError("field_order_id is not supported")


def _require_calibration_metadata(value: object, *, record_name: str) -> None:
    if type(value) is not dict or set(value) != set(_CALIBRATION_METADATA):
        raise ValueError(f"{record_name} metadata fields must match the calibration-only contract")
    if type(value["calibration_only"]) is not bool or value["calibration_only"] is not True:
        raise ValueError(f"{record_name} metadata must remain calibration-only")
    if (
        type(value["formal_parameter_authority"]) is not bool
        or value["formal_parameter_authority"] is not False
    ):
        raise ValueError(
            f"{record_name} metadata must remain calibration-only without formal authority"
        )
    if (
        type(value["research_parameter_status"]) is not str
        or value["research_parameter_status"] != "not_frozen"
    ):
        raise ValueError(f"{record_name} metadata research parameter status must be not_frozen")


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
    _require_calibration_metadata(payload["metadata"], record_name=record_name)


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
    replicate_id: int
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
            ("persona_view_id", self.persona_view_id),
        ):
            _require_id(name, value)
        _require_string("case_family", self.case_family)
        _require_int("variant_index", self.variant_index)
        _require_int("replicate_id", self.replicate_id)
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
        replicate_id: int,
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


def _require_nonempty_json_mapping(field_name: str, value: object) -> None:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{field_name} must be an explicit non-empty mapping")
    _require_json_transport(_json_ready(value), field_name)


def _require_identity_mapping(
    field_name: str, value: object, *, exact_fields: tuple[str, ...]
) -> None:
    if not isinstance(value, Mapping) or set(value) != set(exact_fields):
        raise ValueError(f"{field_name} fields must be exactly {', '.join(exact_fields)}")
    for key in exact_fields:
        _require_string(f"{field_name}[{key}]", value[key])


@dataclass(frozen=True, slots=True)
class ProbeRequest:
    """One immutable provider-neutral request for a calibration probe attempt."""

    request_id: str
    probe_case_id: str
    probe_case_hash: str
    attempt_index: int
    attempt_kind: str
    scale_id: str
    field_order_id: str
    rendered_messages: tuple[Mapping[str, str], ...]
    rendered_messages_hash: str
    generation_settings: Mapping[str, object]
    generation_settings_hash: str
    requested_seed: int | None
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.probe-request.v1"
    _ID_PREFIX = "probe-request-"
    _ATTEMPT_KINDS = {"semantic", "format_repair"}

    def __post_init__(self) -> None:
        _require_id("probe_case_id", self.probe_case_id)
        _require_sha256("probe_case_hash", self.probe_case_hash)
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if type(self.attempt_kind) is not str or self.attempt_kind not in self._ATTEMPT_KINDS:
            raise ValueError("attempt_kind must be semantic or format_repair")
        _require_probe_declarations(self.scale_id, self.field_order_id)
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
        _require_nonempty_json_mapping("generation_settings", self.generation_settings)
        _require_sha256("generation_settings_hash", self.generation_settings_hash)
        _require_payload_hash(
            "generation_settings_hash", self.generation_settings_hash, self.generation_settings
        )
        if self.requested_seed is not None:
            _require_int("requested_seed", self.requested_seed)
        _require_derived_id(
            "request_id", self.request_id, prefix=self._ID_PREFIX, payload=self._identity_payload()
        )
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "rendered_messages", _freeze(self.rendered_messages))
        object.__setattr__(self, "generation_settings", _freeze(self.generation_settings))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "probe_case_id": self.probe_case_id,
            "probe_case_hash": self.probe_case_hash,
            "attempt_index": self.attempt_index,
            "attempt_kind": self.attempt_kind,
            "scale_id": self.scale_id,
            "field_order_id": self.field_order_id,
            "rendered_messages": self.rendered_messages,
            "rendered_messages_hash": self.rendered_messages_hash,
            "generation_settings": self.generation_settings,
            "generation_settings_hash": self.generation_settings_hash,
            "requested_seed": self.requested_seed,
            "metadata": self.metadata,
        }

    def content_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "request_id": self.request_id}

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        case: ProbeCase,
        *,
        attempt_index: int,
        attempt_kind: str,
        generation_settings: Mapping[str, object],
    ) -> ProbeRequest:
        if not isinstance(case, ProbeCase):
            raise TypeError("case must be a ProbeCase")
        rendered_messages = case.rendered_messages
        if attempt_kind == "format_repair":
            rendered_messages = rendered_messages + (
                {
                    "role": "user",
                    "content": (
                        "FORMAT REPAIR ONLY: return exactly the previously requested JSON "
                        "fields in the declared order; do not change the substantive answer."
                    ),
                },
            )
        rendered_messages_hash = canonical_payload_hash(rendered_messages)
        settings_hash = canonical_payload_hash(generation_settings)
        identity = {
            "schema_version": cls._SCHEMA_VERSION,
            "probe_case_id": case.probe_case_id,
            "probe_case_hash": case.record_hash,
            "attempt_index": attempt_index,
            "attempt_kind": attempt_kind,
            "scale_id": case.scale_id,
            "field_order_id": case.field_order_id,
            "rendered_messages": rendered_messages,
            "rendered_messages_hash": rendered_messages_hash,
            "generation_settings": generation_settings,
            "generation_settings_hash": settings_hash,
            "requested_seed": case.requested_seed,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        request_id = _derived_id(cls._ID_PREFIX, identity)
        content = {**identity, "request_id": request_id}
        return cls(
            request_id=request_id,
            probe_case_id=case.probe_case_id,
            probe_case_hash=case.record_hash,
            attempt_index=attempt_index,
            attempt_kind=attempt_kind,
            scale_id=case.scale_id,
            field_order_id=case.field_order_id,
            rendered_messages=rendered_messages,
            rendered_messages_hash=rendered_messages_hash,
            generation_settings=generation_settings,
            generation_settings_hash=settings_hash,
            requested_seed=case.requested_seed,
            record_hash=canonical_payload_hash(content),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeRequest:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="probe request",
            schema_version=cls._SCHEMA_VERSION,
        )
        if type(payload["rendered_messages"]) is not list:
            raise TypeError("probe request rendered_messages must use a JSON array")
        if type(payload["generation_settings"]) is not dict:
            raise TypeError("probe request generation_settings must use a JSON object")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["rendered_messages"] = tuple(payload["rendered_messages"])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeResponse:
    """Raw or typed-error evidence from one calibration provider attempt."""

    response_id: str
    request_id: str
    request_hash: str
    probe_case_id: str
    probe_case_hash: str
    attempt_index: int
    attempt_kind: str
    scale_id: str
    field_order_id: str
    generation_settings: Mapping[str, object]
    generation_settings_hash: str
    requested_seed: int | None
    provider_seed_supported: bool
    provider_seed_echo: int | None
    runtime_identity: Mapping[str, str]
    model_identity: Mapping[str, str]
    tokenizer_identity: Mapping[str, str]
    chat_template_hash: str
    provider_request_id: str
    started_at: str
    ended_at: str
    outcome: str
    termination_reason: str
    input_tokens: int
    output_tokens: int
    raw_response: str | None
    raw_response_hash: str | None
    error_code: str | None
    retry_after_seconds: float | None
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.probe-response.v1"
    _ID_PREFIX = "probe-response-"
    _OUTCOMES = {"response", "timeout", "oom", "provider_error"}

    def __post_init__(self) -> None:
        for name in ("request_id", "probe_case_id", "provider_request_id"):
            _require_id(name, getattr(self, name))
        for name in (
            "request_hash",
            "probe_case_hash",
            "generation_settings_hash",
            "chat_template_hash",
        ):
            _require_sha256(name, getattr(self, name))
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if (
            type(self.attempt_kind) is not str
            or self.attempt_kind not in ProbeRequest._ATTEMPT_KINDS
        ):
            raise ValueError("attempt_kind must be semantic or format_repair")
        _require_probe_declarations(self.scale_id, self.field_order_id)
        _require_nonempty_json_mapping("generation_settings", self.generation_settings)
        _require_payload_hash(
            "generation_settings_hash", self.generation_settings_hash, self.generation_settings
        )
        if self.requested_seed is not None:
            _require_int("requested_seed", self.requested_seed)
        if type(self.provider_seed_supported) is not bool:
            raise TypeError("provider_seed_supported must be a boolean")
        if self.provider_seed_echo is not None:
            _require_int("provider_seed_echo", self.provider_seed_echo)
        if not self.provider_seed_supported and self.provider_seed_echo is not None:
            raise ValueError("provider seed echo is forbidden when seed support is false")
        if self.requested_seed is None and self.provider_seed_echo is not None:
            raise ValueError("provider seed echo is forbidden without a requested seed")
        if self.provider_seed_echo is not None and self.provider_seed_echo != self.requested_seed:
            raise ValueError("provider seed echo must match the requested seed")
        _require_identity_mapping(
            "runtime_identity", self.runtime_identity, exact_fields=("provider", "runtime_version")
        )
        _require_identity_mapping(
            "model_identity", self.model_identity, exact_fields=("model", "revision")
        )
        _require_identity_mapping(
            "tokenizer_identity", self.tokenizer_identity, exact_fields=("tokenizer", "revision")
        )
        started = _require_timestamp("started_at", self.started_at)
        ended = _require_timestamp("ended_at", self.ended_at)
        assert started is not None and ended is not None
        if ended < started:
            raise ValueError("ended_at must not precede started_at")
        if type(self.outcome) is not str or self.outcome not in self._OUTCOMES:
            raise ValueError("outcome must be response, timeout, oom, or provider_error")
        _require_string("termination_reason", self.termination_reason)
        _require_int("input_tokens", self.input_tokens)
        _require_int("output_tokens", self.output_tokens)
        if self.outcome == "response":
            if type(self.raw_response) is not str or self.error_code is not None:
                raise ValueError("response outcome requires raw_response without error_code")
            if self.retry_after_seconds is not None:
                raise ValueError("successful response cannot declare Retry-After")
            _require_sha256("raw_response_hash", self.raw_response_hash)
            _require_payload_hash("raw_response_hash", self.raw_response_hash, self.raw_response)
        else:
            if self.raw_response is not None or self.raw_response_hash is not None:
                raise ValueError("typed error response cannot contain raw response content")
            _require_string("error_code", self.error_code)
            if self.retry_after_seconds is not None:
                if type(self.retry_after_seconds) is not float:
                    raise TypeError("retry_after_seconds must be a float or null")
                _require_finite_number(
                    "retry_after_seconds", self.retry_after_seconds, positive=False
                )
        _require_derived_id(
            "response_id",
            self.response_id,
            prefix=self._ID_PREFIX,
            payload=self._identity_payload(),
        )
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "generation_settings", _freeze(self.generation_settings))
        object.__setattr__(self, "runtime_identity", _freeze(self.runtime_identity))
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))
        object.__setattr__(self, "tokenizer_identity", _freeze(self.tokenizer_identity))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            **{
                name: getattr(self, name)
                for name in self.__dataclass_fields__
                if name not in {"response_id", "record_hash"}
            },
            "metadata": self.metadata,
        }

    def content_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "response_id": self.response_id}

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_script_step(
        cls,
        *,
        request: ProbeRequest,
        outcome: str,
        raw_response: str | None,
        error_code: str | None,
        adapter_identity: Mapping[str, str],
        model_identity: Mapping[str, str],
        tokenizer_identity: Mapping[str, str],
        chat_template_hash: str,
        provider_request_id: str,
        provider_seed_supported: bool,
        provider_seed_echo: int | None,
        retry_after_seconds: float | None,
    ) -> ProbeResponse:
        if not isinstance(request, ProbeRequest):
            raise TypeError("request must be a ProbeRequest")
        raw_hash = None if raw_response is None else canonical_payload_hash(raw_response)
        values: dict[str, object] = {
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "probe_case_id": request.probe_case_id,
            "probe_case_hash": request.probe_case_hash,
            "attempt_index": request.attempt_index,
            "attempt_kind": request.attempt_kind,
            "scale_id": request.scale_id,
            "field_order_id": request.field_order_id,
            "generation_settings": request.generation_settings,
            "generation_settings_hash": request.generation_settings_hash,
            "requested_seed": request.requested_seed,
            "provider_seed_supported": provider_seed_supported,
            "provider_seed_echo": provider_seed_echo,
            "runtime_identity": adapter_identity,
            "model_identity": model_identity,
            "tokenizer_identity": tokenizer_identity,
            "chat_template_hash": chat_template_hash,
            "provider_request_id": provider_request_id,
            "started_at": "1970-01-01T00:00:00Z",
            "ended_at": "1970-01-01T00:00:00Z",
            "outcome": outcome,
            "termination_reason": "stop" if outcome == "response" else outcome,
            "input_tokens": 0,
            "output_tokens": 0,
            "raw_response": raw_response,
            "raw_response_hash": raw_hash,
            "error_code": error_code,
            "retry_after_seconds": retry_after_seconds,
        }
        identity = {
            "schema_version": cls._SCHEMA_VERSION,
            **values,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        response_id = _derived_id(cls._ID_PREFIX, identity)
        content = {**identity, "response_id": response_id}
        return cls(
            response_id=response_id,
            **values,
            record_hash=canonical_payload_hash(content),
        )  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeResponse:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="probe response",
            schema_version=cls._SCHEMA_VERSION,
        )
        for name in (
            "generation_settings",
            "runtime_identity",
            "model_identity",
            "tokenizer_identity",
        ):
            if type(payload[name]) is not dict:
                raise TypeError(f"probe response {name} must use a JSON object")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeParseEvidence:
    """Strict parse result bound to one calibration request and response."""

    parse_evidence_id: str
    parser_id: str
    parser_version: str
    probe_case_id: str
    probe_case_hash: str
    scale_id: str
    field_order_id: str
    request_id: str
    request_hash: str
    response_id: str
    response_hash: str
    raw_response_hash: str
    success: bool
    stance: int | None
    confidence: int | None
    public_reason: str | None
    parsed_response_hash: str | None
    error: Mapping[str, str] | None
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.probe-parse-evidence.v1"
    _ID_PREFIX = "probe-parse-"

    def __post_init__(self) -> None:
        for name in (
            "parser_id",
            "parser_version",
            "probe_case_id",
            "scale_id",
            "field_order_id",
            "request_id",
            "response_id",
        ):
            _require_id(name, getattr(self, name))
        for name in (
            "probe_case_hash",
            "request_hash",
            "response_hash",
            "raw_response_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if (
            self.parser_id != "paper1.calibration.strict-probe-parser"
            or self.parser_version != "1.0.0"
        ):
            raise ValueError("parser declarations must match the versioned strict probe parser")
        _require_probe_declarations(self.scale_id, self.field_order_id)
        if type(self.success) is not bool:
            raise TypeError("success must be a boolean")
        if self.success:
            _require_int("stance", self.stance)  # type: ignore[arg-type]
            _require_int("confidence", self.confidence, minimum=1)  # type: ignore[arg-type]
            _require_string("public_reason", self.public_reason)
            ranges = {"stance-1-7": (1, 7), "stance-0-10": (0, 10)}
            if not ranges[self.scale_id][0] <= self.stance <= ranges[self.scale_id][1]:  # type: ignore[operator]
                raise ValueError("stance is outside the declared scale")
            if self.confidence > 5:  # type: ignore[operator]
                raise ValueError("confidence must be between 1 and 5")
            if len(self.public_reason) > 2_048:  # type: ignore[arg-type]
                raise ValueError("public_reason exceeds the probe character limit")
            if self.error is not None:
                raise ValueError("successful parse cannot contain an error")
            _require_sha256("parsed_response_hash", self.parsed_response_hash)
            _require_payload_hash(
                "parsed_response_hash", self.parsed_response_hash, self.parsed_payload()
            )
        else:
            if any(
                value is not None
                for value in (
                    self.stance,
                    self.confidence,
                    self.public_reason,
                    self.parsed_response_hash,
                )
            ):
                raise ValueError("failed parse cannot contain parsed values")
            if type(self.error) is not dict or tuple(self.error) != ("code", "message"):
                raise ValueError("failed parse requires an exact code/message error")
            _require_string("error code", self.error["code"])
            _require_string("error message", self.error["message"])
        _require_derived_id(
            "parse_evidence_id",
            self.parse_evidence_id,
            prefix=self._ID_PREFIX,
            payload=self._identity_payload(),
        )
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "error", _freeze(self.error))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def parsed_payload(self) -> dict[str, object] | None:
        if not self.success:
            return None
        return {
            "stance": self.stance,
            "confidence": self.confidence,
            "public_reason": self.public_reason,
        }

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            **{
                name: getattr(self, name)
                for name in self.__dataclass_fields__
                if name not in {"parse_evidence_id", "record_hash"}
            },
            "metadata": self.metadata,
        }

    def content_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "parse_evidence_id": self.parse_evidence_id}

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        response: ProbeResponse,
        scale_id: str,
        field_order_id: str,
        stance: int | None,
        confidence: int | None,
        public_reason: str | None,
        error: Mapping[str, str] | None,
    ) -> ProbeParseEvidence:
        if not isinstance(response, ProbeResponse):
            raise TypeError("response must be a ProbeResponse")
        if scale_id != response.scale_id:
            raise ValueError("scale_id must match the bound response scale")
        if field_order_id != response.field_order_id:
            raise ValueError("field_order_id must match the bound response field order")
        success = error is None
        parsed = (
            None
            if not success
            else {"stance": stance, "confidence": confidence, "public_reason": public_reason}
        )
        values: dict[str, object] = {
            "parser_id": "paper1.calibration.strict-probe-parser",
            "parser_version": "1.0.0",
            "probe_case_id": response.probe_case_id,
            "probe_case_hash": response.probe_case_hash,
            "scale_id": scale_id,
            "field_order_id": field_order_id,
            "request_id": response.request_id,
            "request_hash": response.request_hash,
            "response_id": response.response_id,
            "response_hash": response.record_hash,
            "raw_response_hash": response.raw_response_hash,
            "success": success,
            "stance": stance,
            "confidence": confidence,
            "public_reason": public_reason,
            "parsed_response_hash": None if parsed is None else canonical_payload_hash(parsed),
            "error": error,
        }
        identity = {
            "schema_version": cls._SCHEMA_VERSION,
            **values,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        evidence_id = _derived_id(cls._ID_PREFIX, identity)
        content = {**identity, "parse_evidence_id": evidence_id}
        return cls(
            parse_evidence_id=evidence_id,
            **values,
            record_hash=canonical_payload_hash(content),
        )  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeParseEvidence:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="probe parse evidence",
            schema_version=cls._SCHEMA_VERSION,
        )
        if payload["error"] is not None and type(payload["error"]) is not dict:
            raise TypeError("probe parse error must use a JSON object or null")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        return cls(**values)  # type: ignore[arg-type]


def _require_finite_number(field_name: str, value: object, *, positive: bool) -> None:
    if type(value) not in {int, float}:
        raise TypeError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        qualifier = "positive " if positive else "nonnegative "
        raise ValueError(f"{field_name} must be a finite {qualifier}number")


@dataclass(frozen=True, slots=True)
class ProbeRuntimePolicy:
    """Hash-bound transport policy for one calibration run."""

    policy_id: str
    retryable_error_codes: tuple[str, ...]
    nonretryable_error_codes: tuple[str, ...]
    max_transport_attempts_by_code: Mapping[str, int]
    timeout_seconds: float
    obey_retry_after: bool
    backoff_seconds: tuple[float, ...]
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.probe-runtime-policy.v1"

    def __post_init__(self) -> None:
        _require_id("policy_id", self.policy_id)
        for field_name, codes in (
            ("retryable_error_codes", self.retryable_error_codes),
            ("nonretryable_error_codes", self.nonretryable_error_codes),
        ):
            _require_tuple(field_name, codes)
            if not codes or tuple(sorted(codes)) != codes or len(set(codes)) != len(codes):
                raise ValueError(f"{field_name} must be non-empty, unique, and canonically sorted")
            for code in codes:
                _require_id("error_code", code)
        retryable = set(self.retryable_error_codes)
        nonretryable = set(self.nonretryable_error_codes)
        if retryable & nonretryable:
            raise ValueError("runtime policy error code partitions must be disjoint")
        if type(self.max_transport_attempts_by_code) is not dict:
            raise TypeError("max_transport_attempts_by_code must be an exact mapping")
        if set(self.max_transport_attempts_by_code) != retryable | nonretryable:
            raise ValueError("transport budget codes must exactly partition all policy error codes")
        for code, budget in self.max_transport_attempts_by_code.items():
            _require_id("transport budget error code", code)
            _require_int("transport attempt budget", budget, minimum=1)
        _require_finite_number("timeout_seconds", self.timeout_seconds, positive=True)
        if type(self.obey_retry_after) is not bool:
            raise TypeError("obey_retry_after must be a boolean")
        _require_tuple("backoff_seconds", self.backoff_seconds)
        expected_backoff_count = max(
            0,
            max(self.max_transport_attempts_by_code[code] for code in retryable) - 1,
        )
        if len(self.backoff_seconds) != expected_backoff_count:
            raise ValueError(
                "backoff_seconds schedule length must cover every retryable attempt transition"
            )
        for value in self.backoff_seconds:
            if type(value) is not float:
                raise TypeError("backoff_seconds schedule values must be floats")
            _require_finite_number("backoff_seconds value", value, positive=False)
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(
            self,
            "max_transport_attempts_by_code",
            _freeze(dict(sorted(self.max_transport_attempts_by_code.items()))),
        )

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "retryable_error_codes": self.retryable_error_codes,
            "nonretryable_error_codes": self.nonretryable_error_codes,
            "max_transport_attempts_by_code": self.max_transport_attempts_by_code,
            "timeout_seconds": self.timeout_seconds,
            "obey_retry_after": self.obey_retry_after,
            "backoff_seconds": self.backoff_seconds,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        retryable_error_codes: tuple[str, ...],
        nonretryable_error_codes: tuple[str, ...],
        max_transport_attempts_by_code: Mapping[str, int],
        timeout_seconds: float,
        obey_retry_after: bool,
        backoff_seconds: tuple[float, ...],
    ) -> ProbeRuntimePolicy:
        content = {
            "schema_version": cls._SCHEMA_VERSION,
            "policy_id": policy_id,
            "retryable_error_codes": tuple(sorted(retryable_error_codes)),
            "nonretryable_error_codes": tuple(sorted(nonretryable_error_codes)),
            "max_transport_attempts_by_code": dict(sorted(max_transport_attempts_by_code.items())),
            "timeout_seconds": timeout_seconds,
            "obey_retry_after": obey_retry_after,
            "backoff_seconds": backoff_seconds,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        return cls(
            policy_id=policy_id,
            retryable_error_codes=content["retryable_error_codes"],  # type: ignore[arg-type]
            nonretryable_error_codes=content["nonretryable_error_codes"],  # type: ignore[arg-type]
            max_transport_attempts_by_code=content["max_transport_attempts_by_code"],  # type: ignore[arg-type]
            timeout_seconds=timeout_seconds,
            obey_retry_after=obey_retry_after,
            backoff_seconds=backoff_seconds,
            record_hash=canonical_payload_hash(content),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeRuntimePolicy:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="probe runtime policy",
            schema_version=cls._SCHEMA_VERSION,
        )
        if (
            type(payload["retryable_error_codes"]) is not list
            or type(payload["nonretryable_error_codes"]) is not list
        ):
            raise TypeError("runtime policy code fields must use JSON arrays")
        if type(payload["max_transport_attempts_by_code"]) is not dict:
            raise TypeError("runtime policy budgets must use a JSON object")
        if type(payload["backoff_seconds"]) is not list:
            raise TypeError("runtime policy backoff_seconds must use a JSON array")
        return cls(
            policy_id=payload["policy_id"],
            retryable_error_codes=tuple(payload["retryable_error_codes"]),
            nonretryable_error_codes=tuple(payload["nonretryable_error_codes"]),
            max_transport_attempts_by_code=payload["max_transport_attempts_by_code"],
            timeout_seconds=payload["timeout_seconds"],
            obey_retry_after=payload["obey_retry_after"],
            backoff_seconds=tuple(payload["backoff_seconds"]),
            record_hash=payload["record_hash"],
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class CloudProbeRuntimePolicy(ProbeRuntimePolicy):
    """Transport policy plus hash-bound whole-run safety budgets for the 816 probe."""

    connect_timeout_seconds: float
    read_timeout_seconds: float
    retry_after_min_seconds: float
    retry_after_max_seconds: float
    invalid_retry_after_action: str
    oom_action: str
    server_crash_action: str
    model_identity_drift_action: str
    disk_below_threshold_action: str
    max_total_cases: int
    max_total_transport_attempts: int
    dispatch_stop_cumulative_attempt_seconds: float
    dispatch_stop_input_tokens: int
    dispatch_stop_output_tokens: int
    minimum_free_disk_bytes: int

    _SCHEMA_VERSION = "paper1.calibration.cloud-probe-runtime-policy.v2"

    def __post_init__(self) -> None:
        ProbeRuntimePolicy.__post_init__(self)
        for name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "retry_after_min_seconds",
            "retry_after_max_seconds",
            "dispatch_stop_cumulative_attempt_seconds",
        ):
            _require_finite_number(
                name, getattr(self, name), positive=name not in {"retry_after_min_seconds"}
            )
        if self.connect_timeout_seconds > self.timeout_seconds:
            raise ValueError("connect timeout cannot exceed the overall request timeout")
        if self.read_timeout_seconds > self.timeout_seconds:
            raise ValueError("read timeout cannot exceed the overall request timeout")
        if self.retry_after_min_seconds > self.retry_after_max_seconds:
            raise ValueError("Retry-After bounds are reversed")
        if self.invalid_retry_after_action != "use_deterministic_backoff":
            raise ValueError("invalid Retry-After must use deterministic backoff")
        expected_actions = {
            "oom_action": "terminal_incomplete",
            "server_crash_action": "retry_then_terminal_incomplete",
            "model_identity_drift_action": "terminal_incomplete",
            "disk_below_threshold_action": "terminal_incomplete",
        }
        for name, expected in expected_actions.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} must be {expected}")
        required_retryable = {"provider_unreachable": 2}
        required_nonretryable = {
            "provider_identity_mismatch": 1,
            "provider_missing_request_id": 1,
        }
        for code, attempts in required_retryable.items():
            if (
                code not in self.retryable_error_codes
                or self.max_transport_attempts_by_code.get(code) != attempts
            ):
                raise ValueError(
                    f"{code} must be retryable with exactly {attempts} transport attempts"
                )
        for code, attempts in required_nonretryable.items():
            if (
                code not in self.nonretryable_error_codes
                or self.max_transport_attempts_by_code.get(code) != attempts
            ):
                raise ValueError(
                    f"{code} must be nonretryable with exactly {attempts} transport attempt"
                )
        for name in (
            "max_total_cases",
            "max_total_transport_attempts",
            "dispatch_stop_input_tokens",
            "dispatch_stop_output_tokens",
            "minimum_free_disk_bytes",
        ):
            _require_int(name, getattr(self, name), minimum=1)
        if self.max_total_cases != 816:
            raise ValueError("cloud probe runtime policy must bind exactly 816 cases")
        if self.max_total_transport_attempts < self.max_total_cases:
            raise ValueError("total transport budget cannot be smaller than the case inventory")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "retryable_error_codes": self.retryable_error_codes,
            "nonretryable_error_codes": self.nonretryable_error_codes,
            "max_transport_attempts_by_code": self.max_transport_attempts_by_code,
            "timeout_seconds": self.timeout_seconds,
            "obey_retry_after": self.obey_retry_after,
            "backoff_seconds": self.backoff_seconds,
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "read_timeout_seconds": self.read_timeout_seconds,
            "retry_after_min_seconds": self.retry_after_min_seconds,
            "retry_after_max_seconds": self.retry_after_max_seconds,
            "invalid_retry_after_action": self.invalid_retry_after_action,
            "oom_action": self.oom_action,
            "server_crash_action": self.server_crash_action,
            "model_identity_drift_action": self.model_identity_drift_action,
            "disk_below_threshold_action": self.disk_below_threshold_action,
            "max_total_cases": self.max_total_cases,
            "max_total_transport_attempts": self.max_total_transport_attempts,
            "dispatch_stop_cumulative_attempt_seconds": (
                self.dispatch_stop_cumulative_attempt_seconds
            ),
            "dispatch_stop_input_tokens": self.dispatch_stop_input_tokens,
            "dispatch_stop_output_tokens": self.dispatch_stop_output_tokens,
            "minimum_free_disk_bytes": self.minimum_free_disk_bytes,
            "metadata": self.metadata,
        }

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        retryable_error_codes: tuple[str, ...],
        nonretryable_error_codes: tuple[str, ...],
        max_transport_attempts_by_code: Mapping[str, int],
        timeout_seconds: float,
        obey_retry_after: bool,
        backoff_seconds: tuple[float, ...],
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        retry_after_min_seconds: float,
        retry_after_max_seconds: float,
        invalid_retry_after_action: str,
        oom_action: str,
        server_crash_action: str,
        model_identity_drift_action: str,
        disk_below_threshold_action: str,
        max_total_cases: int,
        max_total_transport_attempts: int,
        dispatch_stop_cumulative_attempt_seconds: float,
        dispatch_stop_input_tokens: int,
        dispatch_stop_output_tokens: int,
        minimum_free_disk_bytes: int,
    ) -> CloudProbeRuntimePolicy:
        values = {
            "policy_id": policy_id,
            "retryable_error_codes": tuple(sorted(retryable_error_codes)),
            "nonretryable_error_codes": tuple(sorted(nonretryable_error_codes)),
            "max_transport_attempts_by_code": dict(sorted(max_transport_attempts_by_code.items())),
            "timeout_seconds": timeout_seconds,
            "obey_retry_after": obey_retry_after,
            "backoff_seconds": backoff_seconds,
            "connect_timeout_seconds": connect_timeout_seconds,
            "read_timeout_seconds": read_timeout_seconds,
            "retry_after_min_seconds": retry_after_min_seconds,
            "retry_after_max_seconds": retry_after_max_seconds,
            "invalid_retry_after_action": invalid_retry_after_action,
            "oom_action": oom_action,
            "server_crash_action": server_crash_action,
            "model_identity_drift_action": model_identity_drift_action,
            "disk_below_threshold_action": disk_below_threshold_action,
            "max_total_cases": max_total_cases,
            "max_total_transport_attempts": max_total_transport_attempts,
            "dispatch_stop_cumulative_attempt_seconds": (dispatch_stop_cumulative_attempt_seconds),
            "dispatch_stop_input_tokens": dispatch_stop_input_tokens,
            "dispatch_stop_output_tokens": dispatch_stop_output_tokens,
            "minimum_free_disk_bytes": minimum_free_disk_bytes,
        }
        content = {
            "schema_version": cls._SCHEMA_VERSION,
            **values,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> CloudProbeRuntimePolicy:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="cloud probe runtime policy",
            schema_version=cls._SCHEMA_VERSION,
        )
        if (
            type(payload["retryable_error_codes"]) is not list
            or type(payload["nonretryable_error_codes"]) is not list
            or type(payload["backoff_seconds"]) is not list
            or type(payload["max_transport_attempts_by_code"]) is not dict
        ):
            raise TypeError("cloud runtime policy repeated fields use invalid JSON containers")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["retryable_error_codes"] = tuple(payload["retryable_error_codes"])
        values["nonretryable_error_codes"] = tuple(payload["nonretryable_error_codes"])
        values["backoff_seconds"] = tuple(payload["backoff_seconds"])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeAttempt:
    """One replayable request/response transition in a probe run."""

    attempt_id: str
    probe_run_id: str
    run_instance_id: str
    specification_hash: str
    case_inventory_hash: str
    runtime_policy_hash: str
    probe_case_id: str
    probe_case_hash: str
    attempt_index: int
    attempt_kind: str
    request: ProbeRequest
    request_hash: str
    response: ProbeResponse
    response_hash: str
    parse_evidence: ProbeParseEvidence | None
    parse_evidence_hash: str | None
    transport_error_code: str | None
    transport_retryable: bool | None
    transport_attempt_number_for_code: int | None
    transport_budget_for_code: int | None
    retry_delay_seconds: float | None
    retry_delay_source: str | None
    case_status_after: str
    record_hash: str

    _SCHEMA_VERSION = "paper1.calibration.probe-attempt.v1"
    _ID_PREFIX = "probe-attempt-"
    _STATUSES = {"pending", "format_pending", "parsed", "parse_failed", "refused", "runtime_failed"}

    def __post_init__(self) -> None:
        for name in ("probe_run_id", "run_instance_id", "probe_case_id"):
            _require_id(name, getattr(self, name))
        for name in (
            "specification_hash",
            "case_inventory_hash",
            "runtime_policy_hash",
            "probe_case_hash",
            "request_hash",
            "response_hash",
        ):
            _require_sha256(name, getattr(self, name))
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if self.attempt_kind not in ProbeRequest._ATTEMPT_KINDS:
            raise ValueError("attempt_kind is unsupported")
        if not isinstance(self.request, ProbeRequest) or not isinstance(
            self.response, ProbeResponse
        ):
            raise TypeError("attempt requires bound ProbeRequest and ProbeResponse records")
        _require_payload_hash("request_hash", self.request_hash, self.request.content_payload())
        _require_payload_hash("response_hash", self.response_hash, self.response.content_payload())
        if (
            self.request.probe_case_id != self.probe_case_id
            or self.request.probe_case_hash != self.probe_case_hash
            or self.response.probe_case_id != self.probe_case_id
            or self.response.probe_case_hash != self.probe_case_hash
            or self.request.attempt_index != self.attempt_index
            or self.response.attempt_index != self.attempt_index
            or self.request.attempt_kind != self.attempt_kind
            or self.response.attempt_kind != self.attempt_kind
            or self.response.request_id != self.request.request_id
            or self.response.request_hash != self.request.record_hash
            or self.response.scale_id != self.request.scale_id
            or self.response.field_order_id != self.request.field_order_id
            or self.response.generation_settings != self.request.generation_settings
            or self.response.generation_settings_hash != self.request.generation_settings_hash
            or self.response.requested_seed != self.request.requested_seed
        ):
            raise ValueError("attempt request/response identity chain is inconsistent")
        if self.parse_evidence is None:
            if self.parse_evidence_hash is not None:
                raise ValueError("absent parse evidence cannot have a hash")
        else:
            if not isinstance(self.parse_evidence, ProbeParseEvidence):
                raise TypeError("parse_evidence must be ProbeParseEvidence or null")
            _require_sha256("parse_evidence_hash", self.parse_evidence_hash)
            _require_payload_hash(
                "parse_evidence_hash",
                self.parse_evidence_hash,
                self.parse_evidence.content_payload(),
            )
            if (
                self.parse_evidence.response_id != self.response.response_id
                or self.parse_evidence.response_hash != self.response.record_hash
                or self.parse_evidence.request_id != self.request.request_id
                or self.parse_evidence.request_hash != self.request.record_hash
                or self.parse_evidence.probe_case_id != self.probe_case_id
                or self.parse_evidence.probe_case_hash != self.probe_case_hash
                or self.parse_evidence.raw_response_hash != self.response.raw_response_hash
                or self.parse_evidence.scale_id != self.request.scale_id
                or self.parse_evidence.field_order_id != self.request.field_order_id
                or self.parse_evidence.parser_id != "paper1.calibration.strict-probe-parser"
                or self.parse_evidence.parser_version != "1.0.0"
            ):
                raise ValueError(
                    "parse evidence is not fully bound to the attempt request and response"
                )
        if self.response.outcome == "response":
            if any(
                value is not None
                for value in (
                    self.transport_error_code,
                    self.transport_retryable,
                    self.transport_attempt_number_for_code,
                    self.transport_budget_for_code,
                    self.retry_delay_seconds,
                    self.retry_delay_source,
                )
            ):
                raise ValueError("semantic response cannot contain transport retry evidence")
            expected = self._semantic_status()
        else:
            _require_id("transport_error_code", self.transport_error_code)
            if type(self.transport_retryable) is not bool:
                raise TypeError("transport_retryable must be a boolean for transport errors")
            _require_int(
                "transport_attempt_number_for_code",
                self.transport_attempt_number_for_code,  # type: ignore[arg-type]
                minimum=1,
            )
            _require_int(
                "transport_budget_for_code",
                self.transport_budget_for_code,  # type: ignore[arg-type]
                minimum=1,
            )
            if self.transport_error_code != self.response.error_code:
                raise ValueError("transport error code must match response")
            exhausted = self.transport_attempt_number_for_code >= self.transport_budget_for_code  # type: ignore[operator]
            expected = (
                "runtime_failed"
                if exhausted or not self.transport_retryable or self.response.outcome == "oom"
                else "pending"
            )
            if expected == "pending":
                _require_finite_number(
                    "retry_delay_seconds", self.retry_delay_seconds, positive=False
                )
                if self.retry_delay_source not in {"backoff", "retry_after"}:
                    raise ValueError("retry delay source must be backoff or retry_after")
                if self.retry_delay_source == "retry_after" and (
                    self.response.retry_after_seconds is None
                    or self.retry_delay_seconds != self.response.retry_after_seconds
                ):
                    raise ValueError(
                        "Retry-After delay must equal the hash-bound response evidence"
                    )
            elif self.retry_delay_seconds is not None or self.retry_delay_source is not None:
                raise ValueError("terminal transport failure cannot schedule another retry")
        if self.case_status_after != expected or self.case_status_after not in self._STATUSES:
            raise ValueError("case status is not derived from attempt evidence")
        _require_derived_id(
            "attempt_id", self.attempt_id, prefix=self._ID_PREFIX, payload=self._identity_payload()
        )
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def _semantic_status(self) -> str:
        if self.parse_evidence is None:
            raise ValueError("semantic response must have hash-bound parse evidence")
        if not self.parse_evidence.success and self.parse_evidence.error["code"] == "refusal":
            return "refused"
        if self.parse_evidence.success:
            return "parsed"
        return "format_pending" if self.attempt_kind == "semantic" else "parse_failed"

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            **{
                name: (
                    value.to_payload()
                    if name in {"request", "response", "parse_evidence"} and value is not None
                    else value
                )
                for name in self.__dataclass_fields__
                if name not in {"attempt_id", "record_hash"}
                for value in (getattr(self, name),)
            },
            "metadata": self.metadata,
        }

    def content_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "attempt_id": self.attempt_id}

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(cls, **values: object) -> ProbeAttempt:
        identity = {
            "schema_version": cls._SCHEMA_VERSION,
            **values,
            "metadata": dict(_CALIBRATION_METADATA),
        }
        for name in ("request", "response", "parse_evidence"):
            if identity.get(name) is not None:
                identity[name] = identity[name].to_payload()
        attempt_id = _derived_id(cls._ID_PREFIX, identity)
        content = {**identity, "attempt_id": attempt_id}
        return cls(attempt_id=attempt_id, **values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeAttempt:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="probe attempt",
            schema_version=cls._SCHEMA_VERSION,
        )
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["request"] = ProbeRequest.from_payload(payload["request"])  # type: ignore[arg-type]
        values["response"] = ProbeResponse.from_payload(payload["response"])  # type: ignore[arg-type]
        if payload["parse_evidence"] is not None:
            values["parse_evidence"] = ProbeParseEvidence.from_payload(payload["parse_evidence"])  # type: ignore[arg-type]
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProbeRunProjection:
    """Canonical current run state derived exclusively from ordered attempts."""

    probe_run_id: str
    run_instance_id: str
    specification_hash: str
    case_inventory_hash: str
    runtime_policy: ProbeRuntimePolicy
    runtime_policy_hash: str
    generation_settings: Mapping[str, object]
    generation_settings_hash: str
    runtime_identity: Mapping[str, str]
    model_identity: Mapping[str, str]
    tokenizer_identity: Mapping[str, str]
    chat_template_hash: str
    execution_context_hash: str
    case_statuses: Mapping[str, str]
    attempts: tuple[ProbeAttempt, ...]
    status: str
    run_evidence_hash: str

    _SCHEMA_VERSION = "paper1.calibration.probe-run-projection.v1"
    _ID_PREFIX = "probe-run-"

    def __post_init__(self) -> None:
        _require_id("run_instance_id", self.run_instance_id)
        for name in (
            "specification_hash",
            "case_inventory_hash",
            "runtime_policy_hash",
            "generation_settings_hash",
            "chat_template_hash",
            "execution_context_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if not isinstance(self.runtime_policy, ProbeRuntimePolicy):
            raise TypeError("runtime_policy must be a ProbeRuntimePolicy")
        if self.runtime_policy_hash != self.runtime_policy.record_hash:
            raise ValueError("runtime_policy_hash does not bind the runtime policy artifact")
        _require_nonempty_json_mapping("generation_settings", self.generation_settings)
        _require_payload_hash(
            "generation_settings_hash", self.generation_settings_hash, self.generation_settings
        )
        _require_identity_mapping(
            "runtime_identity",
            self.runtime_identity,
            exact_fields=("provider", "runtime_version"),
        )
        _require_identity_mapping(
            "model_identity", self.model_identity, exact_fields=("model", "revision")
        )
        _require_identity_mapping(
            "tokenizer_identity",
            self.tokenizer_identity,
            exact_fields=("tokenizer", "revision"),
        )
        expected_context_hash = canonical_payload_hash(self.execution_context_payload())
        if self.execution_context_hash != expected_context_hash:
            raise ValueError("execution_context_hash does not bind the complete run context")
        expected_run_id = _derived_id(
            self._ID_PREFIX,
            {
                "run_instance_id": self.run_instance_id,
                "specification_hash": self.specification_hash,
                "case_inventory_hash": self.case_inventory_hash,
                "runtime_policy_hash": self.runtime_policy_hash,
                "execution_context_hash": self.execution_context_hash,
            },
        )
        if self.probe_run_id != expected_run_id:
            raise ValueError("probe_run_id does not match derived run identity")
        if type(self.case_statuses) is not dict or not self.case_statuses:
            raise ValueError("case_statuses must be an explicit non-empty mapping")
        if tuple(self.case_statuses) != tuple(sorted(self.case_statuses)):
            raise ValueError("case statuses must use canonical case order")
        _require_tuple("attempts", self.attempts)
        if tuple((a.probe_case_id, a.attempt_index) for a in self.attempts) != tuple(
            sorted((a.probe_case_id, a.attempt_index) for a in self.attempts)
        ):
            raise ValueError("attempts must use canonical report order")
        derived = self._replay_attempts()
        if dict(self.case_statuses) != derived:
            raise ValueError("case statuses must be derived only by replaying attempts")
        terminal = {"parsed", "parse_failed", "refused"}
        expected_status = (
            "complete" if all(value in terminal for value in derived.values()) else "incomplete"
        )
        if self.status != expected_status:
            raise ValueError("run status must be derived from replayed case statuses")
        expected_evidence_hash = canonical_payload_hash(
            [item.record_hash for item in self.attempts]
        )
        if self.run_evidence_hash != expected_evidence_hash:
            raise ValueError("run_evidence_hash does not match canonical attempts")
        object.__setattr__(self, "generation_settings", _freeze(self.generation_settings))
        object.__setattr__(self, "runtime_identity", _freeze(self.runtime_identity))
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))
        object.__setattr__(self, "tokenizer_identity", _freeze(self.tokenizer_identity))
        object.__setattr__(self, "case_statuses", _freeze(self.case_statuses))

    def execution_context_payload(self) -> dict[str, object]:
        return {
            "generation_settings": self.generation_settings,
            "generation_settings_hash": self.generation_settings_hash,
            "runtime_identity": self.runtime_identity,
            "model_identity": self.model_identity,
            "tokenizer_identity": self.tokenizer_identity,
            "chat_template_hash": self.chat_template_hash,
        }

    def _replay_attempts(self) -> dict[str, str]:
        derived = {case_id: "unstarted" for case_id in self.case_statuses}
        last_index: dict[str, int] = {}
        last_kind: dict[str, str] = {}
        transport_counts: dict[str, dict[str, int]] = {
            case_id: {} for case_id in self.case_statuses
        }
        for attempt in self.attempts:
            if not isinstance(attempt, ProbeAttempt):
                raise TypeError("attempts must contain ProbeAttempt records")
            if (
                attempt.probe_run_id != self.probe_run_id
                or attempt.run_instance_id != self.run_instance_id
                or attempt.specification_hash != self.specification_hash
                or attempt.case_inventory_hash != self.case_inventory_hash
                or attempt.runtime_policy_hash != self.runtime_policy_hash
                or attempt.probe_case_id not in derived
            ):
                raise ValueError("attempt identity cannot be mixed across runs")
            if (
                attempt.request.generation_settings_hash != self.generation_settings_hash
                or attempt.request.generation_settings != self.generation_settings
                or attempt.response.runtime_identity != self.runtime_identity
                or attempt.response.model_identity != self.model_identity
                or attempt.response.tokenizer_identity != self.tokenizer_identity
                or attempt.response.chat_template_hash != self.chat_template_hash
            ):
                raise ValueError("attempt execution context differs from its probe run")
            if derived[attempt.probe_case_id] in {
                "parsed",
                "parse_failed",
                "refused",
                "runtime_failed",
            }:
                raise ValueError("terminal case status is irreversible")
            if attempt.attempt_index != last_index.get(attempt.probe_case_id, 0) + 1:
                raise ValueError("attempt chain must be contiguous")
            previous_status = derived[attempt.probe_case_id]
            if previous_status == "format_pending":
                expected_kind = "format_repair"
            elif previous_status == "pending":
                expected_kind = last_kind[attempt.probe_case_id]
            else:
                expected_kind = "semantic"
            if attempt.attempt_kind != expected_kind:
                raise ValueError("attempt kind is not derived from the prior replay state")
            last_index[attempt.probe_case_id] = attempt.attempt_index
            last_kind[attempt.probe_case_id] = attempt.attempt_kind
            if attempt.response.outcome == "response":
                expected_status = attempt._semantic_status()
                expected_error_code = None
                expected_retryable = None
                expected_ordinal = None
                expected_budget = None
                expected_delay = None
                expected_delay_source = None
            else:
                code = attempt.response.error_code
                if code not in self.runtime_policy.max_transport_attempts_by_code:
                    raise ValueError("attempt error code is outside the runtime policy")
                if (
                    attempt.response.outcome == "oom"
                    and code not in self.runtime_policy.nonretryable_error_codes
                ):
                    raise ValueError("OOM must replay as an explicitly nonretryable error")
                counts = transport_counts[attempt.probe_case_id]
                counts[code] = counts.get(code, 0) + 1
                expected_error_code = code
                expected_ordinal = counts[code]
                expected_budget = self.runtime_policy.max_transport_attempts_by_code[code]
                expected_retryable = code in self.runtime_policy.retryable_error_codes
                exhausted = expected_ordinal >= expected_budget
                expected_status = (
                    "pending"
                    if expected_retryable and not exhausted and attempt.response.outcome != "oom"
                    else "runtime_failed"
                )
                if expected_status == "pending":
                    if (
                        self.runtime_policy.obey_retry_after
                        and attempt.response.retry_after_seconds is not None
                    ):
                        retry_after = attempt.response.retry_after_seconds
                        if isinstance(self.runtime_policy, CloudProbeRuntimePolicy) and not (
                            self.runtime_policy.retry_after_min_seconds
                            <= retry_after
                            <= self.runtime_policy.retry_after_max_seconds
                        ):
                            expected_delay = self.runtime_policy.backoff_seconds[
                                expected_ordinal - 1
                            ]
                            expected_delay_source = "backoff"
                        else:
                            expected_delay = retry_after
                            expected_delay_source = "retry_after"
                    else:
                        expected_delay = self.runtime_policy.backoff_seconds[expected_ordinal - 1]
                        expected_delay_source = "backoff"
                else:
                    expected_delay = None
                    expected_delay_source = None
            observed = (
                attempt.transport_error_code,
                attempt.transport_retryable,
                attempt.transport_attempt_number_for_code,
                attempt.transport_budget_for_code,
                attempt.retry_delay_seconds,
                attempt.retry_delay_source,
                attempt.case_status_after,
            )
            expected = (
                expected_error_code,
                expected_retryable,
                expected_ordinal,
                expected_budget,
                expected_delay,
                expected_delay_source,
                expected_status,
            )
            if observed != expected:
                raise ValueError(
                    "attempt transport ordinal, budget, delay, or status disagrees with replay"
                )
            derived[attempt.probe_case_id] = expected_status
        return derived

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_CALIBRATION_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "probe_run_id": self.probe_run_id,
            "run_instance_id": self.run_instance_id,
            "specification_hash": self.specification_hash,
            "case_inventory_hash": self.case_inventory_hash,
            "runtime_policy": self.runtime_policy.to_payload(),
            "runtime_policy_hash": self.runtime_policy_hash,
            "generation_settings": self.generation_settings,
            "generation_settings_hash": self.generation_settings_hash,
            "runtime_identity": self.runtime_identity,
            "model_identity": self.model_identity,
            "tokenizer_identity": self.tokenizer_identity,
            "chat_template_hash": self.chat_template_hash,
            "execution_context_hash": self.execution_context_hash,
            "case_statuses": self.case_statuses,
            "attempts": tuple(item.to_payload() for item in self.attempts),
            "status": self.status,
            "run_evidence_hash": self.run_evidence_hash,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready(self.content_payload())

    @classmethod
    def create(
        cls,
        *,
        run_instance_id: str,
        specification_hash: str,
        case_inventory_hash: str,
        runtime_policy: ProbeRuntimePolicy,
        generation_settings: Mapping[str, object],
        runtime_identity: Mapping[str, str],
        model_identity: Mapping[str, str],
        tokenizer_identity: Mapping[str, str],
        chat_template_hash: str,
        case_ids: tuple[str, ...],
        attempts: tuple[ProbeAttempt, ...],
    ) -> ProbeRunProjection:
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_ids must be unique")
        generation_settings_hash = canonical_payload_hash(generation_settings)
        context = {
            "generation_settings": generation_settings,
            "generation_settings_hash": generation_settings_hash,
            "runtime_identity": runtime_identity,
            "model_identity": model_identity,
            "tokenizer_identity": tokenizer_identity,
            "chat_template_hash": chat_template_hash,
        }
        execution_context_hash = canonical_payload_hash(context)
        run_id = _derived_id(
            cls._ID_PREFIX,
            {
                "run_instance_id": run_instance_id,
                "specification_hash": specification_hash,
                "case_inventory_hash": case_inventory_hash,
                "runtime_policy_hash": runtime_policy.record_hash,
                "execution_context_hash": execution_context_hash,
            },
        )
        statuses = {case_id: "unstarted" for case_id in sorted(case_ids)}
        for attempt in sorted(attempts, key=lambda item: (item.probe_case_id, item.attempt_index)):
            statuses[attempt.probe_case_id] = attempt.case_status_after
        status = (
            "complete"
            if all(value in {"parsed", "parse_failed", "refused"} for value in statuses.values())
            else "incomplete"
        )
        ordered = tuple(sorted(attempts, key=lambda item: (item.probe_case_id, item.attempt_index)))
        return cls(
            probe_run_id=run_id,
            run_instance_id=run_instance_id,
            specification_hash=specification_hash,
            case_inventory_hash=case_inventory_hash,
            runtime_policy=runtime_policy,
            runtime_policy_hash=runtime_policy.record_hash,
            generation_settings=generation_settings,
            generation_settings_hash=generation_settings_hash,
            runtime_identity=runtime_identity,
            model_identity=model_identity,
            tokenizer_identity=tokenizer_identity,
            chat_template_hash=chat_template_hash,
            execution_context_hash=execution_context_hash,
            case_statuses=statuses,
            attempts=ordered,
            status=status,
            run_evidence_hash=canonical_payload_hash([item.record_hash for item in ordered]),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ProbeRunProjection:
        expected = set(cls.__dataclass_fields__) | {"schema_version", "metadata"}
        _require_calibration_payload(
            payload,
            expected_fields=expected,
            record_name="probe run projection",
            schema_version=cls._SCHEMA_VERSION,
        )
        if type(payload["case_statuses"]) is not dict or type(payload["attempts"]) is not list:
            raise TypeError("projection statuses and attempts require JSON object/array transport")
        for name in (
            "generation_settings",
            "runtime_identity",
            "model_identity",
            "tokenizer_identity",
            "runtime_policy",
        ):
            if type(payload[name]) is not dict:
                raise TypeError(f"projection {name} must use a JSON object")
        return cls(
            probe_run_id=payload["probe_run_id"],
            run_instance_id=payload["run_instance_id"],
            specification_hash=payload["specification_hash"],
            case_inventory_hash=payload["case_inventory_hash"],
            runtime_policy=(
                CloudProbeRuntimePolicy.from_payload(payload["runtime_policy"])
                if payload["runtime_policy"].get("schema_version")
                == CloudProbeRuntimePolicy._SCHEMA_VERSION
                else ProbeRuntimePolicy.from_payload(payload["runtime_policy"])
            ),  # type: ignore[arg-type,union-attr]
            runtime_policy_hash=payload["runtime_policy_hash"],
            generation_settings=payload["generation_settings"],
            generation_settings_hash=payload["generation_settings_hash"],
            runtime_identity=payload["runtime_identity"],
            model_identity=payload["model_identity"],
            tokenizer_identity=payload["tokenizer_identity"],
            chat_template_hash=payload["chat_template_hash"],
            execution_context_hash=payload["execution_context_hash"],
            case_statuses=payload["case_statuses"],
            attempts=tuple(ProbeAttempt.from_payload(item) for item in payload["attempts"]),
            status=payload["status"],
            run_evidence_hash=payload["run_evidence_hash"],
        )  # type: ignore[arg-type]
