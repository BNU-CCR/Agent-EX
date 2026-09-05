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
    if not isinstance(value, Mapping) or tuple(value) != exact_fields:
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
            if not isinstance(message, Mapping) or tuple(message) != ("role", "content"):
                raise ValueError(
                    "rendered_messages must contain exact ordered role/content mappings"
                )
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
        settings_hash = canonical_payload_hash(generation_settings)
        identity = {
            "schema_version": cls._SCHEMA_VERSION,
            "probe_case_id": case.probe_case_id,
            "probe_case_hash": case.record_hash,
            "attempt_index": attempt_index,
            "attempt_kind": attempt_kind,
            "scale_id": case.scale_id,
            "field_order_id": case.field_order_id,
            "rendered_messages": case.rendered_messages,
            "rendered_messages_hash": case.rendered_messages_hash,
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
            rendered_messages=case.rendered_messages,
            rendered_messages_hash=case.rendered_messages_hash,
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
            _require_sha256("raw_response_hash", self.raw_response_hash)
            _require_payload_hash("raw_response_hash", self.raw_response_hash, self.raw_response)
        else:
            if self.raw_response is not None or self.raw_response_hash is not None:
                raise ValueError("typed error response cannot contain raw response content")
            _require_string("error_code", self.error_code)
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
