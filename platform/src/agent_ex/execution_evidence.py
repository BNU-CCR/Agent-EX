"""Immutable, hash-bound evidence contracts for the Phase 4B mock pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Mapping

from .adapters.base import AdapterResponse
from .domain import (
    EventStatus,
    ExposureRecord,
    GenerationAttempt,
    _freeze,
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    _require_timestamp,
    canonical_payload_hash,
    derive_event_id,
)
from .feed import ExposureSelection
from .memory import MemoryView
from .parser import ParseEvidence, ParserLimits
from .prompt import PromptView

if TYPE_CHECKING:
    from .storage import TerminalFailureEvidence


_POLICY_SCHEMA = "paper1.mock-attempt-policy-binding.v1"
_ADAPTER_BINDING_SCHEMA = "paper1.mock-adapter-execution-binding.v1"
_EVENT_INPUT_SCHEMA = "paper1.event-input-evidence.v1"
_INVOCATION_SCHEMA = "paper1.persisted-invocation-evidence.v1"
_PARSE_NA_SCHEMA = "paper1.parse-not-applicable-evidence.v1"
_FINALIZED_SCHEMA = "paper1.finalized-attempt-evidence.v1"
_REFERENCES_SCHEMA = "paper1.event-evidence-references.v1"
_POLICY_ID = "paper1.mock-attempt-policy.phase4b8c3"
_RESEARCH_QA_IDS = ("P1_MODEL_SEED_PAIRING", "P1_TIMEOUT_RETRY")
_PATH_PATTERN = re.compile(
    r"request_parameters\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
)
_EXECUTION_FIELDS = {
    "started_at",
    "finished_at",
    "http_status",
    "provider_metadata",
    "usage",
    "finish_reason",
}


def _strict_payload(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError(f"{label} payload fields do not match the contract")
    _require_json_transport(payload, label)


def _derive_record_id(prefix: str, identity: Mapping[str, object]) -> str:
    return prefix + canonical_payload_hash(identity)


@dataclass(frozen=True, slots=True)
class MockAttemptPolicyBinding:
    policy_id: str
    research_qa_ids: tuple[str, str]
    allowed_difference_fields: tuple[str, ...]
    mock_only: bool
    formal_eligible: bool
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.policy_id != _POLICY_ID:
            raise ValueError("policy_id is not the stable Phase 4B mock policy ID")
        if self.research_qa_ids != _RESEARCH_QA_IDS:
            raise ValueError("research_qa_ids must exactly bind the approved stable IDs")
        if not isinstance(self.allowed_difference_fields, tuple):
            raise TypeError("allowed_difference_fields must be a tuple")
        if not self.allowed_difference_fields:
            raise ValueError("allowed difference fields must be explicit and non-empty")
        if self.allowed_difference_fields != tuple(sorted(set(self.allowed_difference_fields))):
            raise ValueError("allowed_difference_fields must be unique and sorted")
        for name in self.allowed_difference_fields:
            if name != "model_seed" and _PATH_PATTERN.fullmatch(name) is None:
                raise ValueError(
                    "allowed difference fields are limited to model_seed and named "
                    "request_parameters paths"
                )
        if self.mock_only is not True or self.formal_eligible is not False:
            raise ValueError("Phase 4B policy must be mock_only and formal ineligible")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _POLICY_SCHEMA,
            "policy_id": self.policy_id,
            "research_qa_ids": self.research_qa_ids,
            "allowed_difference_fields": self.allowed_difference_fields,
            "mock_only": self.mock_only,
            "formal_eligible": self.formal_eligible,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        allowed_difference_fields: tuple[str, ...],
        mock_only: bool,
        formal_eligible: bool,
    ) -> MockAttemptPolicyBinding:
        content = {
            "schema_version": _POLICY_SCHEMA,
            "policy_id": _POLICY_ID,
            "research_qa_ids": _RESEARCH_QA_IDS,
            "allowed_difference_fields": allowed_difference_fields,
            "mock_only": mock_only,
            "formal_eligible": formal_eligible,
        }
        return cls(
            policy_id=_POLICY_ID,
            research_qa_ids=_RESEARCH_QA_IDS,
            allowed_difference_fields=allowed_difference_fields,
            mock_only=mock_only,
            formal_eligible=formal_eligible,
            record_hash=canonical_payload_hash(content),
        )

    def require_formal_eligible(self) -> None:
        raise ValueError("mock attempt policy is not eligible for formal execution")

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> MockAttemptPolicyBinding:
        expected = set(cls.__dataclass_fields__) | {"schema_version"}
        _strict_payload(payload, expected, "attempt policy binding")
        if payload["schema_version"] != _POLICY_SCHEMA:
            raise ValueError("attempt policy binding schema is unsupported")
        if type(payload["research_qa_ids"]) is not list:
            raise TypeError("research_qa_ids must be a JSON array")
        if type(payload["allowed_difference_fields"]) is not list:
            raise TypeError("allowed_difference_fields must be a JSON array")
        return cls(
            policy_id=payload["policy_id"],  # type: ignore[arg-type]
            research_qa_ids=tuple(payload["research_qa_ids"]),  # type: ignore[arg-type]
            allowed_difference_fields=tuple(payload["allowed_difference_fields"]),  # type: ignore[arg-type]
            mock_only=payload["mock_only"],  # type: ignore[arg-type]
            formal_eligible=payload["formal_eligible"],  # type: ignore[arg-type]
            record_hash=payload["record_hash"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class MockAdapterExecutionBinding:
    binding_id: str
    expected_adapter_kind: str
    expected_adapter_version: str
    runtime_identity: Mapping[str, str]
    runtime_identity_hash: str
    model_identity: Mapping[str, str]
    model_identity_hash: str
    script_hash: str
    mock_only: bool
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_id("binding_id", self.binding_id)
        _require_string("expected_adapter_kind", self.expected_adapter_kind)
        _require_string("expected_adapter_version", self.expected_adapter_version)
        for name in ("runtime_identity", "model_identity"):
            value = getattr(self, name)
            if not isinstance(value, Mapping) or not value:
                raise ValueError(f"{name} must be a non-empty mapping")
            for item in value.values():
                _require_string(f"{name} value", item)
        if self.runtime_identity.get("adapter") != self.expected_adapter_kind:
            raise ValueError("expected adapter kind does not match runtime identity")
        if self.runtime_identity.get("adapter_version") != self.expected_adapter_version:
            raise ValueError("expected adapter version does not match runtime identity")
        for name in (
            "runtime_identity_hash",
            "model_identity_hash",
            "script_hash",
            "record_hash",
        ):
            _require_sha256(name, getattr(self, name))
        _require_payload_hash(
            "runtime_identity_hash", self.runtime_identity_hash, self.runtime_identity
        )
        _require_payload_hash("model_identity_hash", self.model_identity_hash, self.model_identity)
        if self.mock_only is not True:
            raise ValueError("adapter execution binding must be explicitly mock_only")
        expected_id = _derive_record_id(
            "adapter-execution-binding-",
            {
                "expected_adapter_kind": self.expected_adapter_kind,
                "expected_adapter_version": self.expected_adapter_version,
                "runtime_identity_hash": self.runtime_identity_hash,
                "model_identity_hash": self.model_identity_hash,
                "script_hash": self.script_hash,
            },
        )
        if self.binding_id != expected_id:
            raise ValueError("binding_id does not match adapter execution identity")
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "runtime_identity", _freeze(self.runtime_identity))
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _ADAPTER_BINDING_SCHEMA,
            "binding_id": self.binding_id,
            "expected_adapter_kind": self.expected_adapter_kind,
            "expected_adapter_version": self.expected_adapter_version,
            "runtime_identity": self.runtime_identity,
            "runtime_identity_hash": self.runtime_identity_hash,
            "model_identity": self.model_identity,
            "model_identity_hash": self.model_identity_hash,
            "script_hash": self.script_hash,
            "mock_only": self.mock_only,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        expected_adapter_kind: str,
        expected_adapter_version: str,
        runtime_identity: Mapping[str, str],
        model_identity: Mapping[str, str],
        script_hash: str,
        mock_only: bool,
    ) -> MockAdapterExecutionBinding:
        runtime_hash = canonical_payload_hash(runtime_identity)
        model_hash = canonical_payload_hash(model_identity)
        binding_id = _derive_record_id(
            "adapter-execution-binding-",
            {
                "expected_adapter_kind": expected_adapter_kind,
                "expected_adapter_version": expected_adapter_version,
                "runtime_identity_hash": runtime_hash,
                "model_identity_hash": model_hash,
                "script_hash": script_hash,
            },
        )
        values = {
            "binding_id": binding_id,
            "expected_adapter_kind": expected_adapter_kind,
            "expected_adapter_version": expected_adapter_version,
            "runtime_identity": runtime_identity,
            "runtime_identity_hash": runtime_hash,
            "model_identity": model_identity,
            "model_identity_hash": model_hash,
            "script_hash": script_hash,
            "mock_only": mock_only,
        }
        content = {"schema_version": _ADAPTER_BINDING_SCHEMA, **values}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> MockAdapterExecutionBinding:
        expected = set(cls.__dataclass_fields__) | {"schema_version"}
        _strict_payload(payload, expected, "adapter execution binding")
        if payload["schema_version"] != _ADAPTER_BINDING_SCHEMA:
            raise ValueError("adapter execution binding schema is unsupported")
        if (
            type(payload["runtime_identity"]) is not dict
            or type(payload["model_identity"]) is not dict
        ):
            raise TypeError("adapter identities must be JSON objects")
        return cls(**{name: payload[name] for name in cls.__dataclass_fields__})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class EventInputEvidence:
    evidence_id: str
    event_id: str
    receiver_agent_id: str
    exposure_selection: ExposureSelection
    exposure_record: ExposureRecord
    memory_view: MemoryView
    prompt_view: PromptView
    parser_limits: ParserLimits
    state_context_hash: str
    publish_flag: bool
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_id("evidence_id", self.evidence_id)
        _require_id("event_id", self.event_id)
        _require_id("receiver_agent_id", self.receiver_agent_id)
        typed = (
            ("exposure_selection", self.exposure_selection, ExposureSelection),
            ("exposure_record", self.exposure_record, ExposureRecord),
            ("memory_view", self.memory_view, MemoryView),
            ("prompt_view", self.prompt_view, PromptView),
            ("parser_limits", self.parser_limits, ParserLimits),
        )
        for name, value, expected_type in typed:
            if not isinstance(value, expected_type):
                raise TypeError(f"{name} must be typed {expected_type.__name__}")
        selection = self.exposure_selection
        exposure = self.exposure_record
        memory = self.memory_view
        prompt = self.prompt_view
        if not (
            self.event_id
            == selection.receiver_event_id
            == exposure.receiver_event_id
            == prompt.event_id
        ):
            raise ValueError("event identities do not match across event input evidence")
        if not (selection.receiver_event_ordinal == exposure.event_ordinal == prompt.event_ordinal):
            raise ValueError("event ordinals do not match across event input evidence")
        if not (
            self.receiver_agent_id
            == selection.receiver_agent_id
            == exposure.receiver_agent_id
            == memory.agent_id
            == prompt.agent_id
        ):
            raise ValueError("receiver and memory identities do not match")
        if not (
            selection.selection_id == exposure.selection_id
            and selection.record_hash == exposure.selection_hash
            and selection.capacity == exposure.capacity
            and selection.exposure_mode == exposure.exposure_mode
            and selection.exposure_graph_hash == exposure.exposure_graph_hash
        ):
            raise ValueError("exposure selection and record bindings do not match")
        projection = {
            "exposure_id": f"exposure-{selection.receiver_event_ordinal}",
            "event_ordinal": selection.receiver_event_ordinal,
            "cursor_before_id": selection.cursor_before.cursor_id,
            "cursor_before_hash": selection.cursor_before.record_hash,
            "cursor_after_id": selection.cursor_after.cursor_id,
            "cursor_after_hash": selection.cursor_after.record_hash,
            "candidate_post_ids": tuple(item.post_id for item in selection.candidates),
            "candidate_post_hashes": tuple(item.post_hash for item in selection.candidates),
            "selected_post_ids": tuple(item.post_id for item in selection.selected),
            "expired_post_ids": tuple(item.post_id for item in selection.expired),
            "round0_candidate_post_ids": tuple(
                item.post_id for item in selection.candidates if item.is_round0
            ),
            "source_post_ids": tuple(item.post_id for item in selection.selected),
            "source_post_hashes": tuple(item.post_hash for item in selection.selected),
            "source_update_ids": tuple(item.source_update_id for item in selection.selected),
            "source_update_hashes": tuple(item.source_update_hash for item in selection.selected),
            "source_agent_ids": tuple(item.source_agent_id for item in selection.selected),
            "source_event_ids": tuple(item.source_event_id for item in selection.selected),
            "message_ages": tuple(item.message_age for item in selection.selected),
            "original_orders": tuple(item.original_order for item in selection.selected),
            "display_slots": tuple(item.display_slot for item in selection.selected),
            "rendered_texts": tuple(item.rendered_text for item in selection.selected),
            "rendered_hashes": tuple(item.rendered_hash for item in selection.selected),
            "slot_rng_hash": canonical_payload_hash(selection.slot_rng_provenance.to_payload()),
            "round0_rng_hash": (
                None
                if selection.round0_rng_provenance is None
                else canonical_payload_hash(selection.round0_rng_provenance.to_payload())
            ),
        }
        if any(getattr(exposure, name) != expected for name, expected in projection.items()):
            raise ValueError("exposure record is not the deterministic selection projection")
        if not (
            prompt.exposure_id == exposure.exposure_id
            and prompt.exposure_hash == exposure.record_hash
            and prompt.memory_id == memory.view_id
            and prompt.memory_hash == memory.record_hash
        ):
            raise ValueError("prompt exposure or memory bindings do not match")
        if not (
            selection.matched_seed
            == exposure.matched_seed
            == memory.matched_seed
            == prompt.matched_seed
        ):
            raise ValueError("matched seed does not match across event input evidence")
        if not (
            exposure.topic_package_id == memory.topic_package_id == prompt.topic_package_id
            and exposure.topic_package_hash == memory.topic_package_hash == prompt.topic_hash
        ):
            raise ValueError("topic identity does not match across event input evidence")
        if type(self.publish_flag) is not bool:
            raise TypeError("publish_flag must be a frozen boolean")
        event_publish_flag = prompt.event_payload.get("publish_flag")
        if event_publish_flag != self.publish_flag:
            raise ValueError("publish_flag does not match the scheduled prompt event")
        _require_sha256("state_context_hash", self.state_context_hash)
        expected_id = _derive_record_id("event-input-", {"event_id": self.event_id})
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match event input identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _EVENT_INPUT_SCHEMA,
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "receiver_agent_id": self.receiver_agent_id,
            "exposure_selection": self.exposure_selection.to_payload(),
            "exposure_record": self.exposure_record.to_payload(),
            "memory_view": self.memory_view.to_payload(),
            "prompt_view": self.prompt_view.to_payload(),
            "parser_limits": self.parser_limits.to_payload(),
            "state_context_hash": self.state_context_hash,
            "publish_flag": self.publish_flag,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        exposure_selection: ExposureSelection,
        exposure_record: ExposureRecord,
        memory_view: MemoryView,
        prompt_view: PromptView,
        parser_limits: ParserLimits,
        state_context_hash: str,
        publish_flag: bool,
    ) -> EventInputEvidence:
        event_id = prompt_view.event_id
        evidence_id = _derive_record_id("event-input-", {"event_id": event_id})
        values = {
            "evidence_id": evidence_id,
            "event_id": event_id,
            "receiver_agent_id": prompt_view.agent_id,
            "exposure_selection": exposure_selection,
            "exposure_record": exposure_record,
            "memory_view": memory_view,
            "prompt_view": prompt_view,
            "parser_limits": parser_limits,
            "state_context_hash": state_context_hash,
            "publish_flag": publish_flag,
        }
        content = {
            "schema_version": _EVENT_INPUT_SCHEMA,
            "evidence_id": evidence_id,
            "event_id": event_id,
            "receiver_agent_id": prompt_view.agent_id,
            "exposure_selection": exposure_selection.to_payload(),
            "exposure_record": exposure_record.to_payload(),
            "memory_view": memory_view.to_payload(),
            "prompt_view": prompt_view.to_payload(),
            "parser_limits": parser_limits.to_payload(),
            "state_context_hash": state_context_hash,
            "publish_flag": publish_flag,
        }
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> EventInputEvidence:
        expected = set(cls.__dataclass_fields__) | {"schema_version"}
        _strict_payload(payload, expected, "event input evidence")
        if payload["schema_version"] != _EVENT_INPUT_SCHEMA:
            raise ValueError("event input evidence schema is unsupported")
        for name in (
            "exposure_selection",
            "exposure_record",
            "memory_view",
            "prompt_view",
            "parser_limits",
        ):
            if type(payload[name]) is not dict:
                raise TypeError(f"{name} must be a JSON object")
        return cls(
            evidence_id=payload["evidence_id"],  # type: ignore[arg-type]
            event_id=payload["event_id"],  # type: ignore[arg-type]
            receiver_agent_id=payload["receiver_agent_id"],  # type: ignore[arg-type]
            exposure_selection=ExposureSelection.from_payload(payload["exposure_selection"]),  # type: ignore[arg-type]
            exposure_record=ExposureRecord.from_payload(payload["exposure_record"]),  # type: ignore[arg-type]
            memory_view=MemoryView.from_payload(payload["memory_view"]),  # type: ignore[arg-type]
            prompt_view=PromptView.from_payload(payload["prompt_view"]),  # type: ignore[arg-type]
            parser_limits=ParserLimits.from_payload(payload["parser_limits"]),  # type: ignore[arg-type]
            state_context_hash=payload["state_context_hash"],  # type: ignore[arg-type]
            publish_flag=payload["publish_flag"],  # type: ignore[arg-type]
            record_hash=payload["record_hash"],  # type: ignore[arg-type]
        )


def _validate_execution_payload(payload: Mapping[str, object]) -> None:
    if type(payload) is not dict or set(payload) != _EXECUTION_FIELDS:
        raise ValueError("execution payload fields do not match AttemptExecutionEvidence")
    started = _require_timestamp("execution started_at", payload["started_at"])
    finished = _require_timestamp("execution finished_at", payload["finished_at"])
    if finished < started:
        raise ValueError("execution finished_at cannot precede started_at")
    http_status = payload["http_status"]
    if http_status is not None:
        _require_int("execution http_status", http_status, minimum=100)
        if http_status > 599:
            raise ValueError("execution http_status must be at most 599")
    if type(payload["provider_metadata"]) is not dict:
        raise TypeError("execution provider_metadata must be a JSON object")
    if type(payload["usage"]) is not dict:
        raise TypeError("execution usage must be a JSON object")
    finish_reason = payload["finish_reason"]
    if finish_reason is not None:
        _require_string("execution finish_reason", finish_reason)


@dataclass(frozen=True, slots=True)
class PersistedInvocationEvidence:
    evidence_id: str
    attempt_id: str
    request_id: str
    request_hash: str
    response_id: str
    response_hash: str
    response: AdapterResponse
    execution_payload: Mapping[str, object]
    execution_hash: str
    parser_limits_hash: str
    attempt_policy_hash: str
    adapter_execution_binding_hash: str
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("evidence_id", "attempt_id", "request_id", "response_id"):
            _require_id(name, getattr(self, name))
        for name in (
            "request_hash",
            "response_hash",
            "execution_hash",
            "parser_limits_hash",
            "attempt_policy_hash",
            "adapter_execution_binding_hash",
            "record_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if not isinstance(self.response, AdapterResponse):
            raise TypeError("response must be a typed AdapterResponse")
        if (
            self.attempt_id != self.response.attempt_id
            or self.request_id != self.response.request_id
            or self.request_hash != self.response.request_hash
            or self.response_id != self.response.response_id
            or self.response_hash != self.response.record_hash
        ):
            raise ValueError("attempt, request, or response binding does not match response")
        if not isinstance(self.execution_payload, Mapping):
            raise TypeError("execution_payload must be a mapping")
        normalized_execution = _json_ready(self.execution_payload)
        if type(normalized_execution) is not dict:
            raise TypeError("execution_payload must normalize to a JSON object")
        _validate_execution_payload(normalized_execution)
        _require_payload_hash("execution_hash", self.execution_hash, normalized_execution)
        metadata = normalized_execution["provider_metadata"]
        assert isinstance(metadata, Mapping)
        expected_metadata = {
            "adapter_response_id": self.response.response_id,
            "adapter_response_hash": self.response.record_hash,
            "adapter_outcome": self.response.outcome,
            "adapter_error": None if self.response.error is None else dict(self.response.error),
            "runtime_identity": dict(self.response.runtime_identity),
            "runtime_identity_hash": self.response.runtime_identity_hash,
            "script_hash": self.response.script_hash,
        }
        if dict(metadata) != expected_metadata:
            raise ValueError("execution provider metadata does not bind the complete response")
        expected_id = _derive_record_id("invocation-evidence-", {"attempt_id": self.attempt_id})
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match invocation attempt identity")
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "execution_payload", _freeze(normalized_execution))

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _INVOCATION_SCHEMA,
            "evidence_id": self.evidence_id,
            "attempt_id": self.attempt_id,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "response_id": self.response_id,
            "response_hash": self.response_hash,
            "response": self.response.to_payload(),
            "execution_payload": self.execution_payload,
            "execution_hash": self.execution_hash,
            "parser_limits_hash": self.parser_limits_hash,
            "attempt_policy_hash": self.attempt_policy_hash,
            "adapter_execution_binding_hash": self.adapter_execution_binding_hash,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        response: AdapterResponse,
        execution_payload: Mapping[str, object],
        request_hash: str,
        parser_limits_hash: str,
        attempt_policy_hash: str,
        adapter_execution_binding_hash: str,
    ) -> PersistedInvocationEvidence:
        execution_hash = canonical_payload_hash(execution_payload)
        evidence_id = _derive_record_id("invocation-evidence-", {"attempt_id": response.attempt_id})
        values = {
            "evidence_id": evidence_id,
            "attempt_id": response.attempt_id,
            "request_id": response.request_id,
            "request_hash": request_hash,
            "response_id": response.response_id,
            "response_hash": response.record_hash,
            "response": response,
            "execution_payload": execution_payload,
            "execution_hash": execution_hash,
            "parser_limits_hash": parser_limits_hash,
            "attempt_policy_hash": attempt_policy_hash,
            "adapter_execution_binding_hash": adapter_execution_binding_hash,
        }
        content = {
            "schema_version": _INVOCATION_SCHEMA,
            **{key: value for key, value in values.items() if key != "response"},
            "response": response.to_payload(),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PersistedInvocationEvidence:
        expected = set(cls.__dataclass_fields__) | {"schema_version"}
        _strict_payload(payload, expected, "persisted invocation evidence")
        if payload["schema_version"] != _INVOCATION_SCHEMA:
            raise ValueError("persisted invocation schema is unsupported")
        if type(payload["response"]) is not dict or type(payload["execution_payload"]) is not dict:
            raise TypeError("response and execution payload must be JSON objects")
        values = {name: payload[name] for name in cls.__dataclass_fields__}
        values["response"] = AdapterResponse.from_payload(payload["response"])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ParseNotApplicableEvidence:
    evidence_id: str
    attempt_id: str
    request_id: str
    request_hash: str
    response_id: str
    response_hash: str
    outcome: str
    error: Mapping[str, str]
    error_hash: str
    parser_limits_hash: str
    reason: str
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("evidence_id", "attempt_id", "request_id", "response_id"):
            _require_id(name, getattr(self, name))
        for name in (
            "request_hash",
            "response_hash",
            "error_hash",
            "parser_limits_hash",
            "record_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if self.outcome != "timeout":
            raise ValueError("parse-not-applicable outcome must be timeout")
        if not isinstance(self.error, Mapping):
            raise TypeError("parse-not-applicable error must be a mapping")
        normalized_error = _json_ready(self.error)
        if type(normalized_error) is not dict or set(normalized_error) != {"code", "message"}:
            raise ValueError("parse-not-applicable requires the exact timeout error")
        if normalized_error.get("code") != "timeout":
            raise ValueError("parse-not-applicable error code must be timeout")
        _require_string("timeout message", normalized_error.get("message"))
        _require_payload_hash("error_hash", self.error_hash, normalized_error)
        if self.reason != "adapter_timeout_no_response":
            raise ValueError("parse-not-applicable reason is not the fixed timeout reason")
        expected_id = _derive_record_id("parse-not-applicable-", {"attempt_id": self.attempt_id})
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match timeout attempt identity")
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "error", _freeze(normalized_error))

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _PARSE_NA_SCHEMA,
            "evidence_id": self.evidence_id,
            "attempt_id": self.attempt_id,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "response_id": self.response_id,
            "response_hash": self.response_hash,
            "outcome": self.outcome,
            "error": self.error,
            "error_hash": self.error_hash,
            "parser_limits_hash": self.parser_limits_hash,
            "reason": self.reason,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls, *, response: AdapterResponse, parser_limits_hash: str
    ) -> ParseNotApplicableEvidence:
        if response.outcome != "timeout" or response.error is None:
            raise ValueError("parse-not-applicable requires a timeout AdapterResponse")
        evidence_id = _derive_record_id(
            "parse-not-applicable-", {"attempt_id": response.attempt_id}
        )
        values = {
            "evidence_id": evidence_id,
            "attempt_id": response.attempt_id,
            "request_id": response.request_id,
            "request_hash": response.request_hash,
            "response_id": response.response_id,
            "response_hash": response.record_hash,
            "outcome": response.outcome,
            "error": dict(response.error),
            "error_hash": canonical_payload_hash(response.error),
            "parser_limits_hash": parser_limits_hash,
            "reason": "adapter_timeout_no_response",
        }
        content = {"schema_version": _PARSE_NA_SCHEMA, **values}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ParseNotApplicableEvidence:
        expected = set(cls.__dataclass_fields__) | {"schema_version"}
        _strict_payload(payload, expected, "parse-not-applicable evidence")
        if payload["schema_version"] != _PARSE_NA_SCHEMA:
            raise ValueError("parse-not-applicable schema is unsupported")
        if type(payload["error"]) is not dict:
            raise TypeError("parse-not-applicable error must be a JSON object")
        return cls(**{name: payload[name] for name in cls.__dataclass_fields__})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class FinalizedAttemptEvidence:
    evidence_id: str
    request_hash: str
    attempt: GenerationAttempt
    parse_evidence: ParseEvidence | ParseNotApplicableEvidence
    terminal_failure_evidence: TerminalFailureEvidence | None
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        from .storage import TerminalFailureEvidence

        _require_id("evidence_id", self.evidence_id)
        _require_sha256("request_hash", self.request_hash)
        if not isinstance(self.attempt, GenerationAttempt):
            raise TypeError("attempt must be a typed GenerationAttempt")
        if self.attempt.status not in {EventStatus.SUCCEEDED, EventStatus.FAILED}:
            raise ValueError("finalized attempt must be SUCCEEDED or FAILED")
        if not isinstance(self.parse_evidence, (ParseEvidence, ParseNotApplicableEvidence)):
            raise TypeError("parse_evidence must be ParseEvidence or ParseNotApplicableEvidence")
        if self.terminal_failure_evidence is not None and not isinstance(
            self.terminal_failure_evidence, TerminalFailureEvidence
        ):
            raise TypeError("terminal_failure_evidence must be typed or None")
        parse = self.parse_evidence
        if parse.request_hash != self.request_hash:
            raise ValueError(
                "parse evidence request_hash does not match authoritative request hash"
            )
        if (
            parse.attempt_id != self.attempt.attempt_id
            or parse.request_id != self.attempt.request_id
            or getattr(parse, "event_id", self.attempt.event_id) != self.attempt.event_id
            or getattr(parse, "attempt_index", self.attempt.attempt_index)
            != self.attempt.attempt_index
        ):
            raise ValueError(
                "parse evidence event, attempt index, attempt ID, or request does not match"
            )
        expected_outcome = (
            "timeout" if isinstance(parse, ParseNotApplicableEvidence) else "response"
        )
        metadata = self.attempt.provider_metadata
        if (
            metadata.get("adapter_response_id") != parse.response_id
            or metadata.get("adapter_response_hash") != parse.response_hash
            or metadata.get("adapter_outcome") != expected_outcome
        ):
            raise ValueError("terminal attempt provider metadata does not bind parse response")
        if self.attempt.status is EventStatus.SUCCEEDED:
            if not isinstance(parse, ParseEvidence) or not parse.success:
                raise ValueError("SUCCEEDED requires successful response parse evidence")
            if self.terminal_failure_evidence is not None:
                raise ValueError("SUCCEEDED cannot contain terminal failure evidence")
            if (
                self.attempt.raw_response_hash != parse.raw_response_hash
                or self.attempt.parsed_response_hash != parse.parsed_response_hash
            ):
                raise ValueError("successful attempt and parse payload hashes do not match")
        else:
            if self.terminal_failure_evidence is None:
                raise ValueError("FAILED requires terminal failure evidence")
            failure = self.terminal_failure_evidence
            if (
                failure.attempt_id != self.attempt.attempt_id
                or failure.attempt_index != self.attempt.attempt_index
                or failure.event_id != self.attempt.event_id
                or failure.terminal_attempt_hash
                != canonical_payload_hash(self.attempt.to_payload())
                or failure.terminal_transition_hash
                != canonical_payload_hash(self.attempt.to_payload())
                or derive_event_id(failure.run_id, failure.event_ordinal) != self.attempt.event_id
            ):
                raise ValueError("terminal failure evidence does not match failed attempt")
            if isinstance(parse, ParseNotApplicableEvidence):
                if self.attempt.raw_response is not None or self.attempt.error is None:
                    raise ValueError("timeout parse N/A requires failed timeout without response")
                if self.attempt.error.get("code") != "timeout":
                    raise ValueError("timeout parse N/A requires timeout attempt error")
                if (
                    dict(self.attempt.error) != dict(parse.error)
                    or canonical_payload_hash(self.attempt.error) != parse.error_hash
                ):
                    raise ValueError("timeout attempt error must exactly match parse N/A error")
            else:
                if parse.success:
                    raise ValueError("FAILED response attempt requires failed parse evidence")
                if self.attempt.raw_response_hash != parse.raw_response_hash:
                    raise ValueError("failed response attempt and parse raw hash do not match")
                if self.attempt.error is None or dict(self.attempt.error) != dict(
                    parse.error or {}
                ):
                    raise ValueError("failed response attempt error must exactly match parse error")
        expected_id = _derive_record_id(
            "finalized-attempt-", {"attempt_id": self.attempt.attempt_id}
        )
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match finalized attempt identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _FINALIZED_SCHEMA,
            "evidence_id": self.evidence_id,
            "request_hash": self.request_hash,
            "attempt": self.attempt.to_payload(),
            "parse_evidence_kind": (
                "parse" if isinstance(self.parse_evidence, ParseEvidence) else "not_applicable"
            ),
            "parse_evidence": self.parse_evidence.to_payload(),
            "terminal_failure_evidence": (
                None
                if self.terminal_failure_evidence is None
                else self.terminal_failure_evidence.to_payload()
            ),
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def create(
        cls,
        *,
        request_hash: str,
        attempt: GenerationAttempt,
        parse_evidence: ParseEvidence | ParseNotApplicableEvidence,
        terminal_failure_evidence: TerminalFailureEvidence | None,
    ) -> FinalizedAttemptEvidence:
        evidence_id = _derive_record_id("finalized-attempt-", {"attempt_id": attempt.attempt_id})
        values = {
            "evidence_id": evidence_id,
            "request_hash": request_hash,
            "attempt": attempt,
            "parse_evidence": parse_evidence,
            "terminal_failure_evidence": terminal_failure_evidence,
        }
        content = {
            "schema_version": _FINALIZED_SCHEMA,
            "evidence_id": evidence_id,
            "request_hash": request_hash,
            "attempt": attempt.to_payload(),
            "parse_evidence_kind": (
                "parse" if isinstance(parse_evidence, ParseEvidence) else "not_applicable"
            ),
            "parse_evidence": parse_evidence.to_payload(),
            "terminal_failure_evidence": (
                None
                if terminal_failure_evidence is None
                else terminal_failure_evidence.to_payload()
            ),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FinalizedAttemptEvidence:
        from .storage import TerminalFailureEvidence

        expected = set(cls.__dataclass_fields__) | {"schema_version", "parse_evidence_kind"}
        _strict_payload(payload, expected, "finalized attempt evidence")
        if payload["schema_version"] != _FINALIZED_SCHEMA:
            raise ValueError("finalized attempt evidence schema is unsupported")
        if type(payload["attempt"]) is not dict or type(payload["parse_evidence"]) is not dict:
            raise TypeError("attempt and parse evidence must be JSON objects")
        kind = payload["parse_evidence_kind"]
        if kind == "parse":
            parse = ParseEvidence.from_payload(payload["parse_evidence"])
        elif kind == "not_applicable":
            parse = ParseNotApplicableEvidence.from_payload(payload["parse_evidence"])
        else:
            raise ValueError("parse_evidence_kind is unsupported")
        raw_failure = payload["terminal_failure_evidence"]
        if raw_failure is not None and type(raw_failure) is not dict:
            raise TypeError("terminal_failure_evidence must be a JSON object or null")
        return cls(
            evidence_id=payload["evidence_id"],  # type: ignore[arg-type]
            request_hash=payload["request_hash"],  # type: ignore[arg-type]
            attempt=GenerationAttempt.from_payload(payload["attempt"]),
            parse_evidence=parse,
            terminal_failure_evidence=(
                None if raw_failure is None else TerminalFailureEvidence.from_payload(raw_failure)
            ),
            record_hash=payload["record_hash"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class EventEvidenceReferences:
    event_input_evidence_id: str | None
    event_input_evidence_hash: str | None
    request_id: str | None
    request_hash: str | None
    invocation_evidence_id: str | None
    invocation_evidence_hash: str | None
    parse_evidence_id: str | None
    parse_evidence_hash: str | None
    terminal_attempt_id: str | None
    terminal_attempt_hash: str | None
    committed_event_id: str | None
    committed_event_hash: str | None
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        pairs = (
            ("event_input_evidence", self.event_input_evidence_id, self.event_input_evidence_hash),
            ("request", self.request_id, self.request_hash),
            ("invocation_evidence", self.invocation_evidence_id, self.invocation_evidence_hash),
            ("parse_evidence", self.parse_evidence_id, self.parse_evidence_hash),
            ("terminal_attempt", self.terminal_attempt_id, self.terminal_attempt_hash),
            ("committed_event", self.committed_event_id, self.committed_event_hash),
        )
        seen_gap = False
        for name, identity, digest in pairs:
            if (identity is None) != (digest is None):
                raise ValueError(f"{name} ID and hash must be paired")
            if identity is None:
                seen_gap = True
                continue
            if seen_gap:
                raise ValueError("evidence references must form a contiguous lifecycle prefix")
            _require_id(f"{name}_id", identity)
            _require_sha256(f"{name}_hash", digest)

        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _REFERENCES_SCHEMA,
            **{
                name: getattr(self, name)
                for name in self.__dataclass_fields__
                if name != "record_hash"
            },
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        *,
        event_input_evidence_id: str | None,
        event_input_evidence_hash: str | None,
        request_id: str | None,
        request_hash: str | None,
        invocation_evidence_id: str | None,
        invocation_evidence_hash: str | None,
        parse_evidence_id: str | None,
        parse_evidence_hash: str | None,
        terminal_attempt_id: str | None,
        terminal_attempt_hash: str | None,
        committed_event_id: str | None,
        committed_event_hash: str | None,
    ) -> EventEvidenceReferences:
        values = {
            "event_input_evidence_id": event_input_evidence_id,
            "event_input_evidence_hash": event_input_evidence_hash,
            "request_id": request_id,
            "request_hash": request_hash,
            "invocation_evidence_id": invocation_evidence_id,
            "invocation_evidence_hash": invocation_evidence_hash,
            "parse_evidence_id": parse_evidence_id,
            "parse_evidence_hash": parse_evidence_hash,
            "terminal_attempt_id": terminal_attempt_id,
            "terminal_attempt_hash": terminal_attempt_hash,
            "committed_event_id": committed_event_id,
            "committed_event_hash": committed_event_hash,
        }
        content = {"schema_version": _REFERENCES_SCHEMA, **values}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> EventEvidenceReferences:
        expected = set(cls.__dataclass_fields__) | {"schema_version"}
        _strict_payload(payload, expected, "event evidence references")
        if payload["schema_version"] != _REFERENCES_SCHEMA:
            raise ValueError("event evidence references schema is unsupported")
        return cls(**{name: payload[name] for name in cls.__dataclass_fields__})  # type: ignore[arg-type]
