"""Canonical derived recovery checkpoints for a per-run SQLite store."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, replace
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Mapping

from .domain import (
    _require_id,
    _require_int,
    _require_sha256,
    _require_string,
    _require_timestamp,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
    GenerationAttempt,
    EventStatus,
)
from .storage import (
    ExecutionState,
    ExecutionStatus,
    ExternalResponseReference,
    ResumeAuthorizationEvidence,
    RunStorage,
    TerminalFailureEvidence,
)


_LEGACY_CHECKPOINT_VERSION = "paper1.checkpoint.v3"
_CHECKPOINT_VERSION = "paper1.checkpoint.v4"
_SUPPORTED_CHECKPOINT_VERSIONS = frozenset({_LEGACY_CHECKPOINT_VERSION, _CHECKPOINT_VERSION})
# Checkpoint v4 carries ordered evidence hashes.  The approved 50,000-event
# release shape exceeds the earlier 16 MiB ceiling while remaining bounded.
_MAX_CHECKPOINT_BYTES = 32 * 1024 * 1024
_MAX_JSON_DEPTH = 32


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_depth(value: object, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("checkpoint JSON exceeds maximum nesting depth")
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_depth(item, depth + 1)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _validate_depth(item, depth + 1)


def _preflight_json_depth(raw: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in raw:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                raise ValueError("checkpoint JSON exceeds maximum nesting depth")
        elif character in "]}":
            depth -= 1


def _validate_attempt_prefix(prefix: list[object], current_event_id: str | None) -> None:
    if prefix and current_event_id is None:
        raise ValueError("complete checkpoint cannot contain a current attempt prefix")
    allowed_lifecycles = {
        ("pending",),
        ("pending", "in_progress"),
        ("pending", "in_progress", "failed"),
        ("pending", "in_progress", "succeeded"),
    }
    for expected_index, attempt in enumerate(prefix, start=1):
        if type(attempt) is not dict or set(attempt) != {
            "attempt_id",
            "attempt_index",
            "transitions",
            "transition_entries",
        }:
            raise ValueError("checkpoint attempt prefix entry has unexpected fields")
        _require_int("checkpoint attempt index", attempt["attempt_index"])
        if attempt["attempt_index"] != expected_index:
            raise ValueError("checkpoint attempt prefix has an attempt-index gap")
        if attempt["attempt_id"] != derive_attempt_id(current_event_id, expected_index):
            raise ValueError("checkpoint attempt identity does not match current event")
        transitions = attempt["transitions"]
        entries = attempt["transition_entries"]
        if (
            type(transitions) is not list
            or not transitions
            or type(entries) is not list
            or len(entries) != len(transitions)
        ):
            raise ValueError("checkpoint attempt transition prefix is incomplete")
        statuses = tuple(
            transition.get("status") if type(transition) is dict else None
            for transition in transitions
        )
        if statuses not in allowed_lifecycles:
            raise ValueError("checkpoint attempt transition lifecycle is invalid")
        if expected_index < len(prefix) and statuses != ("pending", "in_progress", "failed"):
            raise ValueError("only a failed attempt may precede another attempt")
        for transition_index, (transition, entry) in enumerate(zip(transitions, entries), start=1):
            if type(transition) is not dict:
                raise TypeError("checkpoint attempt transition must be a plain mapping")
            if (
                transition.get("attempt_id") != attempt["attempt_id"]
                or transition.get("event_id") != current_event_id
                or transition.get("attempt_index") != expected_index
            ):
                raise ValueError("checkpoint attempt transition identity drifted")
            if type(entry) is not dict or set(entry) != {"transition", "row_envelope"}:
                raise ValueError("checkpoint attempt transition entry has unexpected fields")
            if entry["transition"] != transition:
                raise ValueError("checkpoint attempt transition copies do not match")
            envelope = entry["row_envelope"]
            if type(envelope) is not dict or set(envelope) != {
                "attempt_id",
                "event_id",
                "attempt_index",
                "transition_index",
                "status",
                "payload_hash",
                "checkpoint_payload_hash",
                "raw_response_uri",
                "raw_response_hash",
            }:
                raise ValueError("checkpoint attempt transition row envelope is invalid")
            if (
                envelope["attempt_id"] != attempt["attempt_id"]
                or envelope["event_id"] != current_event_id
                or envelope["attempt_index"] != expected_index
                or envelope["transition_index"] != transition_index
                or envelope["status"] != transition["status"]
            ):
                raise ValueError("checkpoint attempt transition row identity drifted")
            _require_sha256("checkpoint attempt transition payload hash", envelope["payload_hash"])
            _require_sha256(
                "checkpoint redacted transition payload hash",
                envelope["checkpoint_payload_hash"],
            )
            if canonical_payload_hash(transition) != envelope["checkpoint_payload_hash"]:
                raise ValueError("checkpoint transition canonical payload hash drifted")
            raw_uri = envelope["raw_response_uri"]
            raw_hash = envelope["raw_response_hash"]
            if (raw_uri is None) != (raw_hash is None):
                raise ValueError("checkpoint external response URI/hash binding is incomplete")
            if raw_uri is not None:
                ExternalResponseReference(uri=raw_uri, sha256=raw_hash)
                if transition.get("raw_response") is not None or (
                    transition.get("raw_response_hash") != raw_hash
                ):
                    raise ValueError("checkpoint external response body/hash binding drifted")
                _validate_redacted_attempt_transition(transition)
            else:
                replayed_transition = GenerationAttempt.from_payload(transition)
                if replayed_transition.to_payload() != transition:
                    raise ValueError("checkpoint attempt transition is not canonical")
                if canonical_payload_hash(transition) != envelope["payload_hash"]:
                    raise ValueError("checkpoint attempt transition payload hash drifted")
        immutable_fields = (
            "attempt_id",
            "event_id",
            "attempt_index",
            "request_id",
            "exposure_id",
            "rendered_messages",
            "rendered_prompt_hash",
            "request_parameters",
            "request_parameters_hash",
            "model_identity",
            "model_identity_hash",
            "model_seed",
        )
        if any(
            transition[field] != transitions[0][field]
            for transition in transitions[1:]
            for field in immutable_fields
        ):
            raise ValueError("checkpoint attempt immutable request evidence drifted")
        if len(transitions) == 3 and transitions[2]["started_at"] != transitions[1]["started_at"]:
            raise ValueError("checkpoint terminal transition start time drifted")
        for previous, current in zip(transitions, transitions[1:]):
            if previous["provider_request_id"] is not None and (
                current["provider_request_id"] != previous["provider_request_id"]
            ):
                raise ValueError("checkpoint provider request identity drifted")
            if any(
                key not in current["provider_metadata"]
                or current["provider_metadata"][key] != value
                for key, value in previous["provider_metadata"].items()
            ):
                raise ValueError("checkpoint provider metadata progression drifted")


def _validate_redacted_attempt_transition(payload: dict[str, object]) -> None:
    expected_fields = set(GenerationAttempt.__dataclass_fields__)
    if set(payload) != expected_fields:
        raise ValueError("redacted checkpoint attempt fields do not match the v2 contract")
    pending_shadow = dict(payload)
    pending_shadow.update(
        {
            "status": "pending",
            "provider_request_id": None,
            "provider_metadata": {},
            "provider_metadata_hash": canonical_payload_hash({}),
            "http_status": None,
            "raw_response": None,
            "raw_response_hash": None,
            "parsed_response": None,
            "parsed_response_hash": None,
            "usage": {},
            "usage_hash": canonical_payload_hash({}),
            "finish_reason": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
    )
    GenerationAttempt.from_payload(pending_shadow)
    if payload["status"] not in {"failed", "succeeded"}:
        raise ValueError("only terminal checkpoint attempts may redact an external response")
    provider_request_id = payload["provider_request_id"]
    if provider_request_id is not None:
        _require_id("provider_request_id", provider_request_id)
    for name in ("provider_metadata", "usage"):
        if type(payload[name]) is not dict:
            raise TypeError(f"redacted checkpoint attempt {name} must be a JSON object")
        if canonical_payload_hash(payload[name]) != payload[f"{name}_hash"]:
            raise ValueError(f"redacted checkpoint attempt {name} hash drifted")
    for name in ("parsed_response", "error"):
        if payload[name] is not None and type(payload[name]) is not dict:
            raise TypeError(f"redacted checkpoint attempt {name} must be an object or null")
    if (payload["parsed_response"] is None) != (payload["parsed_response_hash"] is None):
        raise ValueError("redacted checkpoint parsed response hash pairing drifted")
    if (
        payload["parsed_response"] is not None
        and canonical_payload_hash(payload["parsed_response"]) != payload["parsed_response_hash"]
    ):
        raise ValueError("redacted checkpoint parsed response hash drifted")
    _require_sha256("redacted raw response hash", payload["raw_response_hash"])
    started = _require_timestamp("started_at", payload["started_at"])
    finished = _require_timestamp("finished_at", payload["finished_at"])
    if finished < started:
        raise ValueError("redacted checkpoint finish time precedes start")
    if payload["http_status"] is not None:
        _require_int("http_status", payload["http_status"], minimum=100)
        if payload["http_status"] > 599:
            raise ValueError("redacted checkpoint HTTP status is outside range")
    _require_string("finish_reason", payload["finish_reason"], optional=True)
    if payload["usage"]:
        required_usage = {"prompt_tokens", "completion_tokens", "total_tokens"}
        if not required_usage.issubset(payload["usage"]):
            raise ValueError("redacted checkpoint attempt usage is incomplete")
        for key in required_usage:
            _require_int(f"usage[{key}]", payload["usage"][key])
        if payload["usage"]["total_tokens"] != (
            payload["usage"]["prompt_tokens"] + payload["usage"]["completion_tokens"]
        ):
            raise ValueError("redacted checkpoint usage total drifted")
    if payload["status"] == "succeeded":
        if (
            provider_request_id is None
            or not payload["provider_metadata"]
            or payload["parsed_response"] is None
            or not payload["usage"]
            or payload["finish_reason"] is None
            or payload["error"] is not None
            or type(payload["http_status"]) is not int
            or not 200 <= payload["http_status"] < 300
        ):
            raise ValueError("redacted succeeded checkpoint attempt is incomplete")
    elif not payload["error"] or payload["parsed_response"] is not None:
        raise ValueError("redacted failed checkpoint attempt is incomplete")


@dataclass(frozen=True, slots=True)
class Checkpoint:
    version: str
    storage_schema_version: str
    run_id: str
    run_spec_hash: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    schedule_hash: str
    schedule_count: int
    artifact_hashes: Mapping[str, str]
    expected_agent_ids_hash: str
    expected_exposure_mode: str
    expected_exposure_graph_hash: str | None
    expected_exposure_graph_artifact_id: str | None
    expected_exposure_graph_artifact_type: str | None
    expected_source_ws_artifact_hash: str | None
    expected_source_ws_artifact_id: str | None
    expected_source_ws_artifact_type: str | None
    round0_root: str
    baseline_manifest_hash: str
    current_manifest_hash: str
    next_event_ordinal: int
    current_event_id: str | None
    private_state_root: str
    public_stock_root: str
    latest_public_pointer_root: str
    feed_cursor_root: str
    state_collection_root: str
    event_chain_head: str
    current_attempt_prefix: tuple[Mapping[str, object], ...]
    execution_state: Mapping[str, object]
    execution_state_hash: str
    terminal_failure: Mapping[str, object] | None
    terminal_failure_hash: str | None
    resume_authorization: Mapping[str, object] | None
    resume_authorization_hash: str | None
    terminal_failure_prefix: tuple[Mapping[str, object], ...]
    terminal_failure_prefix_hash: str
    resume_authorization_prefix: tuple[Mapping[str, object], ...]
    resume_authorization_prefix_hash: str
    causal_evidence_prefix: tuple[Mapping[str, object], ...]
    causal_evidence_root: str
    v6_evidence_hashes: Mapping[str, tuple[str, ...]]
    v6_evidence_root: str

    @property
    def resume_action(self) -> str:
        """Describe the evidence-preserving recovery action without choosing policy."""

        validated = Checkpoint.from_payload(self.to_payload())
        if validated.current_event_id is None:
            return "complete"
        if not validated.current_attempt_prefix:
            return "start_current_event"
        transitions = validated.current_attempt_prefix[-1].get("transitions")
        if not isinstance(transitions, (tuple, list)) or not transitions:
            raise ValueError("checkpoint attempt prefix is incomplete")
        last = transitions[-1]
        if not isinstance(last, Mapping):
            raise ValueError("checkpoint attempt transition is invalid")
        status = last.get("status")
        if status in {"pending", "in_progress"}:
            return "resume_same_attempt"
        if status == "failed":
            if validated.terminal_failure is not None:
                return (
                    "retry_same_event"
                    if validated.resume_authorization is not None
                    else "halted_current_event"
                )
            return "retry_same_event"
        if status == "succeeded":
            return "commit_landed_success"
        raise ValueError("checkpoint attempt transition status is invalid")

    @property
    def checkpoint_hash(self) -> str:
        return canonical_payload_hash(self._body_payload())

    def _body_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "storage_schema_version": self.storage_schema_version,
            "run_id": self.run_id,
            "run_spec_hash": self.run_spec_hash,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_hash": self.protocol_hash,
            "schedule_hash": self.schedule_hash,
            "schedule_count": self.schedule_count,
            "artifact_hashes": dict(self.artifact_hashes),
            "expected_agent_ids_hash": self.expected_agent_ids_hash,
            "expected_exposure_mode": self.expected_exposure_mode,
            "expected_exposure_graph_hash": self.expected_exposure_graph_hash,
            "expected_exposure_graph_artifact_id": self.expected_exposure_graph_artifact_id,
            "expected_exposure_graph_artifact_type": self.expected_exposure_graph_artifact_type,
            "expected_source_ws_artifact_hash": self.expected_source_ws_artifact_hash,
            "expected_source_ws_artifact_id": self.expected_source_ws_artifact_id,
            "expected_source_ws_artifact_type": self.expected_source_ws_artifact_type,
            "round0_root": self.round0_root,
            "baseline_manifest_hash": self.baseline_manifest_hash,
            "current_manifest_hash": self.current_manifest_hash,
            "next_event_ordinal": self.next_event_ordinal,
            "current_event_id": self.current_event_id,
            "private_state_root": self.private_state_root,
            "public_stock_root": self.public_stock_root,
            "latest_public_pointer_root": self.latest_public_pointer_root,
            "feed_cursor_root": self.feed_cursor_root,
            "state_collection_root": self.state_collection_root,
            "event_chain_head": self.event_chain_head,
            "current_attempt_prefix": _plain(self.current_attempt_prefix),
            "execution_state": _plain(self.execution_state),
            "execution_state_hash": self.execution_state_hash,
            "terminal_failure": _plain(self.terminal_failure),
            "terminal_failure_hash": self.terminal_failure_hash,
            "resume_authorization": _plain(self.resume_authorization),
            "resume_authorization_hash": self.resume_authorization_hash,
            "terminal_failure_prefix": _plain(self.terminal_failure_prefix),
            "terminal_failure_prefix_hash": self.terminal_failure_prefix_hash,
            "resume_authorization_prefix": _plain(self.resume_authorization_prefix),
            "resume_authorization_prefix_hash": self.resume_authorization_prefix_hash,
            "causal_evidence_prefix": _plain(self.causal_evidence_prefix),
            "causal_evidence_root": self.causal_evidence_root,
            "v6_evidence_hashes": _plain(self.v6_evidence_hashes),
            "v6_evidence_root": self.v6_evidence_root,
        }

    def to_payload(self) -> dict[str, object]:
        body = self._body_payload()
        return {"checkpoint": body, "checkpoint_hash": canonical_payload_hash(body)}

    @classmethod
    def from_payload(cls, payload: object) -> Checkpoint:
        if type(payload) is not dict or set(payload) != {"checkpoint", "checkpoint_hash"}:
            raise ValueError("checkpoint envelope has unexpected fields")
        body = payload["checkpoint"]
        if type(body) is not dict:
            raise TypeError("checkpoint body must be a plain mapping")
        expected_fields = {
            "version",
            "storage_schema_version",
            "run_id",
            "run_spec_hash",
            "protocol_id",
            "protocol_version",
            "protocol_hash",
            "schedule_hash",
            "schedule_count",
            "artifact_hashes",
            "expected_agent_ids_hash",
            "expected_exposure_mode",
            "expected_exposure_graph_hash",
            "expected_exposure_graph_artifact_id",
            "expected_exposure_graph_artifact_type",
            "expected_source_ws_artifact_hash",
            "expected_source_ws_artifact_id",
            "expected_source_ws_artifact_type",
            "round0_root",
            "baseline_manifest_hash",
            "current_manifest_hash",
            "next_event_ordinal",
            "current_event_id",
            "private_state_root",
            "public_stock_root",
            "latest_public_pointer_root",
            "feed_cursor_root",
            "state_collection_root",
            "event_chain_head",
            "current_attempt_prefix",
            "execution_state",
            "execution_state_hash",
            "terminal_failure",
            "terminal_failure_hash",
            "resume_authorization",
            "resume_authorization_hash",
            "terminal_failure_prefix",
            "terminal_failure_prefix_hash",
            "resume_authorization_prefix",
            "resume_authorization_prefix_hash",
            "causal_evidence_prefix",
            "causal_evidence_root",
            "v6_evidence_hashes",
            "v6_evidence_root",
        }
        if set(body) != expected_fields:
            raise ValueError("checkpoint body has unexpected fields")
        _require_sha256("checkpoint_hash", payload["checkpoint_hash"])
        if canonical_payload_hash(body) != payload["checkpoint_hash"]:
            raise ValueError("checkpoint envelope hash does not match body")
        if body["version"] not in _SUPPORTED_CHECKPOINT_VERSIONS:
            raise ValueError("checkpoint version is unsupported")
        _require_id("storage_schema_version", body["storage_schema_version"])
        _require_id("run_id", body["run_id"])
        _require_id("protocol_id", body["protocol_id"])
        _require_id("protocol_version", body["protocol_version"])
        _require_id("expected_exposure_mode", body["expected_exposure_mode"])
        for name in (
            "run_spec_hash",
            "protocol_hash",
            "schedule_hash",
            "expected_agent_ids_hash",
            "round0_root",
            "baseline_manifest_hash",
            "current_manifest_hash",
            "private_state_root",
            "public_stock_root",
            "latest_public_pointer_root",
            "feed_cursor_root",
            "state_collection_root",
            "event_chain_head",
            "v6_evidence_root",
        ):
            _require_sha256(name, body[name])
        v6_hashes = body["v6_evidence_hashes"]
        expected_v6_tables = {
            "event_input_evidence",
            "attempt_policy_evidence",
            "adapter_execution_bindings",
            "adapter_requests",
            "invocation_evidence",
            "parse_evidence",
        }
        if type(v6_hashes) is not dict or set(v6_hashes) != expected_v6_tables:
            raise ValueError("checkpoint v6 evidence hashes do not exact-cover tables")
        for table, hashes in v6_hashes.items():
            if type(hashes) is not list:
                raise TypeError(f"checkpoint {table} hashes must be a JSON array")
            for item in hashes:
                _require_sha256(f"checkpoint {table} row hash", item)
        if canonical_payload_hash(v6_hashes) != body["v6_evidence_root"]:
            raise ValueError("checkpoint v6 evidence root does not match ordered hashes")
        _require_int("schedule_count", body["schedule_count"])
        _require_int("next_event_ordinal", body["next_event_ordinal"])
        if not 0 <= body["next_event_ordinal"] <= body["schedule_count"]:
            raise ValueError("checkpoint next event ordinal is outside schedule")
        expected_event_id = (
            derive_event_id(body["run_id"], body["next_event_ordinal"])
            if body["next_event_ordinal"] < body["schedule_count"]
            else None
        )
        if body["current_event_id"] != expected_event_id:
            raise ValueError("checkpoint current event identity does not match ordinal")
        artifacts = body["artifact_hashes"]
        if type(artifacts) is not dict or not artifacts:
            raise ValueError("checkpoint artifact hashes must be a non-empty plain mapping")
        for artifact_id, artifact_hash in artifacts.items():
            _require_id("checkpoint artifact ID", artifact_id)
            _require_sha256("checkpoint artifact hash", artifact_hash)
        for name in (
            "expected_exposure_graph_hash",
            "expected_source_ws_artifact_hash",
        ):
            if body[name] is not None:
                _require_sha256(name, body[name])
        for name in (
            "expected_exposure_graph_artifact_id",
            "expected_exposure_graph_artifact_type",
            "expected_source_ws_artifact_id",
            "expected_source_ws_artifact_type",
        ):
            if body[name] is not None:
                _require_id(name, body[name])
        prefix = body["current_attempt_prefix"]
        if type(prefix) is not list or any(type(item) is not dict for item in prefix):
            raise TypeError("checkpoint attempt prefix must be a list of plain mappings")
        _validate_attempt_prefix(prefix, body["current_event_id"])
        execution_payload = body["execution_state"]
        if type(execution_payload) is not dict:
            raise TypeError("checkpoint execution state must be a plain mapping")
        execution = ExecutionState.from_payload(execution_payload)
        _require_sha256("execution_state_hash", body["execution_state_hash"])
        if execution.payload_hash != body["execution_state_hash"]:
            raise ValueError("checkpoint execution state hash does not match")
        if (
            execution.run_id != body["run_id"]
            or execution.baseline_manifest_hash != body["baseline_manifest_hash"]
            or execution.next_event_ordinal != body["next_event_ordinal"]
            or execution.current_event_id != body["current_event_id"]
        ):
            raise ValueError("checkpoint execution state identity does not match")
        failure_payload = body["terminal_failure"]
        authorization_payload = body["resume_authorization"]
        failure_prefix_payload = body["terminal_failure_prefix"]
        authorization_prefix_payload = body["resume_authorization_prefix"]
        if type(failure_prefix_payload) is not list or any(
            type(item) is not dict for item in failure_prefix_payload
        ):
            raise TypeError("checkpoint terminal failure prefix must be a list of mappings")
        if type(authorization_prefix_payload) is not list or any(
            type(item) is not dict for item in authorization_prefix_payload
        ):
            raise TypeError("checkpoint resume authorization prefix must be a list of mappings")
        failure_prefix = tuple(
            TerminalFailureEvidence.from_payload(item) for item in failure_prefix_payload
        )
        authorization_prefix = tuple(
            ResumeAuthorizationEvidence.from_payload(item) for item in authorization_prefix_payload
        )
        causal_prefix_payload = body["causal_evidence_prefix"]
        if type(causal_prefix_payload) is not list or any(
            type(item) is not dict for item in causal_prefix_payload
        ):
            raise TypeError("checkpoint causal evidence prefix must be a list of mappings")
        _require_sha256("causal_evidence_root", body["causal_evidence_root"])
        if canonical_payload_hash(causal_prefix_payload) != body["causal_evidence_root"]:
            raise ValueError("checkpoint causal evidence root does not match prefix")
        causal_prefix: list[TerminalFailureEvidence | ResumeAuthorizationEvidence] = []
        previous_hash: str | None = None
        previous_value: TerminalFailureEvidence | ResumeAuthorizationEvidence | None = None
        halted_attempt_indexes: dict[str, int] = {}
        for expected_sequence, item in enumerate(causal_prefix_payload, start=1):
            evidence_kind = item.get("evidence_kind")
            value = (
                TerminalFailureEvidence.from_payload(item)
                if evidence_kind == "failure"
                else ResumeAuthorizationEvidence.from_payload(item)
                if evidence_kind == "authorization"
                else None
            )
            expected_type = (
                TerminalFailureEvidence
                if expected_sequence % 2 == 1
                else ResumeAuthorizationEvidence
            )
            if (
                value is None
                or not isinstance(value, expected_type)
                or value.evidence_sequence != expected_sequence
                or value.previous_evidence_hash != previous_hash
                or value.run_id != body["run_id"]
                or value.event_id != derive_event_id(value.run_id, value.event_ordinal)
                or value.event_ordinal > body["next_event_ordinal"]
            ):
                raise ValueError("checkpoint causal evidence chain is discontinuous or forked")
            if isinstance(value, ResumeAuthorizationEvidence) and (
                value.previous_terminal_failure_hash != value.previous_evidence_hash
                or not isinstance(previous_value, TerminalFailureEvidence)
                or value.event_id != previous_value.event_id
                or value.event_ordinal != previous_value.event_ordinal
            ):
                raise ValueError("checkpoint authorization does not bind preceding failure")
            if isinstance(value, TerminalFailureEvidence):
                if value.attempt_index <= halted_attempt_indexes.get(value.event_id, 0):
                    raise ValueError("checkpoint halted attempt indexes are not increasing")
                halted_attempt_indexes[value.event_id] = value.attempt_index
            causal_prefix.append(value)
            previous_hash = value.payload_hash
            previous_value = value
        if (
            tuple(item for item in causal_prefix if isinstance(item, TerminalFailureEvidence))
            != (failure_prefix)
            or tuple(
                item for item in causal_prefix if isinstance(item, ResumeAuthorizationEvidence)
            )
            != authorization_prefix
        ):
            raise ValueError("checkpoint causal evidence does not exact-cover typed prefixes")
        for name, values in (
            ("terminal_failure_prefix_hash", failure_prefix_payload),
            ("resume_authorization_prefix_hash", authorization_prefix_payload),
        ):
            _require_sha256(name, body[name])
            if canonical_payload_hash(values) != body[name]:
                raise ValueError(f"checkpoint {name} does not match prefix")
        failure = None
        authorization = None
        if failure_payload is None:
            if body["terminal_failure_hash"] is not None:
                raise ValueError("checkpoint terminal failure hash lacks payload")
        else:
            if type(failure_payload) is not dict:
                raise TypeError("checkpoint terminal failure must be a plain mapping")
            failure = TerminalFailureEvidence.from_payload(failure_payload)
            _require_sha256("terminal_failure_hash", body["terminal_failure_hash"])
            if failure.payload_hash != body["terminal_failure_hash"]:
                raise ValueError("checkpoint terminal failure hash does not match")
            if (
                failure.run_id != body["run_id"]
                or failure.event_id != body["current_event_id"]
                or failure.event_ordinal != body["next_event_ordinal"]
            ):
                raise ValueError("checkpoint terminal failure identity does not match")
        if authorization_payload is None:
            if body["resume_authorization_hash"] is not None:
                raise ValueError("checkpoint resume authorization hash lacks payload")
        else:
            if type(authorization_payload) is not dict:
                raise TypeError("checkpoint resume authorization must be a plain mapping")
            authorization = ResumeAuthorizationEvidence.from_payload(authorization_payload)
            _require_sha256("resume_authorization_hash", body["resume_authorization_hash"])
            if authorization.payload_hash != body["resume_authorization_hash"]:
                raise ValueError("checkpoint resume authorization hash does not match")
            if (
                authorization.run_id != body["run_id"]
                or authorization.event_id != body["current_event_id"]
                or authorization.event_ordinal != body["next_event_ordinal"]
            ):
                raise ValueError("checkpoint resume authorization identity does not match")
        if failure is not None:
            if not prefix:
                raise ValueError("checkpoint terminal failure lacks attempt evidence")
            last_transitions = prefix[-1]["transitions"]
            last_transition = last_transitions[-1]
            terminal_envelope = prefix[-1]["transition_entries"][-1]["row_envelope"]
            if (
                last_transition["status"] != "failed"
                or prefix[-1]["attempt_id"] != failure.attempt_id
                or prefix[-1]["attempt_index"] != failure.attempt_index
                or terminal_envelope["payload_hash"] != failure.terminal_transition_hash
            ):
                raise ValueError("checkpoint terminal failure lacks failed terminal attempt")
            if execution.status.value != "failed" or execution.failed_event_ids != (
                failure.event_id,
            ):
                raise ValueError("checkpoint execution state disagrees with halt evidence")
        elif authorization is not None and (
            execution.status.value != "running" or execution.failed_event_ids
        ):
            raise ValueError("checkpoint execution state disagrees with resume authorization")
        terminal_evidence = causal_prefix[-1] if causal_prefix else None
        current_terminal_evidence = (
            terminal_evidence
            if terminal_evidence is not None
            and terminal_evidence.event_ordinal == body["next_event_ordinal"]
            else None
        )
        if failure != (
            current_terminal_evidence
            if isinstance(current_terminal_evidence, TerminalFailureEvidence)
            else None
        ):
            raise ValueError("checkpoint current terminal failure does not match causal chain")
        if authorization != (
            current_terminal_evidence
            if isinstance(current_terminal_evidence, ResumeAuthorizationEvidence)
            else None
        ):
            raise ValueError("checkpoint current resume authorization does not match causal chain")
        failures_by_hash = {item.payload_hash: item for item in failure_prefix}
        if len(failures_by_hash) != len(failure_prefix):
            raise ValueError("checkpoint terminal failure prefix contains duplicates")
        seen_authorizations: set[str] = set()
        for item in authorization_prefix:
            matched = failures_by_hash.get(item.previous_terminal_failure_hash)
            if (
                matched is None
                or item.previous_terminal_failure_hash in seen_authorizations
                or (
                    item.run_id != matched.run_id
                    or item.event_id != matched.event_id
                    or item.event_ordinal != matched.event_ordinal
                )
            ):
                raise ValueError("checkpoint resume authorization prefix is forked")
            seen_authorizations.add(item.previous_terminal_failure_hash)
        failure_by_attempt = {
            (item.event_id, item.event_ordinal, item.attempt_index): item for item in failure_prefix
        }
        authorization_by_failure = {
            item.previous_terminal_failure_hash: item for item in authorization_prefix
        }
        if len(failure_by_attempt) != len(failure_prefix) or len(authorization_by_failure) != len(
            authorization_prefix
        ):
            raise ValueError("checkpoint causal evidence is duplicate or forked")
        for item in failure_prefix:
            bound_authorization = authorization_by_failure.get(item.payload_hash)
            if item.event_ordinal < body["next_event_ordinal"] and bound_authorization is None:
                raise ValueError("committed checkpoint history crossed an unauthorized failure")
            if item.event_ordinal == body["next_event_ordinal"]:
                bound_attempt = next(
                    (
                        attempt_item
                        for attempt_item in prefix
                        if attempt_item["attempt_id"] == item.attempt_id
                        and attempt_item["attempt_index"] == item.attempt_index
                    ),
                    None,
                )
                if bound_attempt is None:
                    raise ValueError("checkpoint failure lacks its exact candidate attempt")
                bound_terminal = bound_attempt["transitions"][-1]
                bound_envelope = bound_attempt["transition_entries"][-1]["row_envelope"]
                if (
                    bound_terminal["status"] != EventStatus.FAILED.value
                    or bound_envelope["payload_hash"] != item.terminal_transition_hash
                    or item.terminal_attempt_hash != item.terminal_transition_hash
                ):
                    raise ValueError("checkpoint failure does not bind a real FAILED terminal")
        for position, attempt_item in enumerate(prefix):
            attempt_index = attempt_item["attempt_index"]
            terminal_status = attempt_item["transitions"][-1]["status"]
            bound_failure = failure_by_attempt.get(
                (body["current_event_id"], body["next_event_ordinal"], attempt_index)
            )
            bound_authorization = (
                None
                if bound_failure is None
                else authorization_by_failure.get(bound_failure.payload_hash)
            )
            if attempt_index > 1:
                prior = prefix[position - 1] if position else None
                prior_failure = failure_by_attempt.get(
                    (
                        body["current_event_id"],
                        body["next_event_ordinal"],
                        attempt_index - 1,
                    )
                )
                if (
                    prior is None
                    or prior["attempt_index"] != attempt_index - 1
                    or prior["transitions"][-1]["status"] != EventStatus.FAILED.value
                    or prior_failure is None
                    or authorization_by_failure.get(prior_failure.payload_hash) is None
                ):
                    raise ValueError(
                        "checkpoint retry attempt lacks exact failure and authorization evidence"
                    )
            if terminal_status != EventStatus.FAILED.value and bound_failure is not None:
                raise ValueError("checkpoint causal failure binds a non-failed attempt")
            if position < len(prefix) - 1 and (
                bound_failure is None or bound_authorization is None
            ):
                raise ValueError("checkpoint prior attempt lacks exact causal authorization")
        succeeded_ids = tuple(
            derive_event_id(body["run_id"], ordinal)
            for ordinal in range(body["next_event_ordinal"])
        )
        expected_counts = {status.value: 0 for status in EventStatus}
        expected_counts[EventStatus.SUCCEEDED.value] = body["next_event_ordinal"]
        expected_event_ids = succeeded_ids
        if prefix:
            last_status = prefix[-1]["transitions"][-1]["status"]
            expected_counts[last_status] += 1
            expected_event_ids += (body["current_event_id"],)
        expected_execution = ExecutionState(
            schema_version="paper1.execution-state.v1",
            run_id=body["run_id"],
            baseline_manifest_hash=body["baseline_manifest_hash"],
            status=(
                ExecutionStatus.COMPLETE
                if body["next_event_ordinal"] == body["schedule_count"]
                else ExecutionStatus.FAILED
                if failure is not None
                else ExecutionStatus.RUNNING
            ),
            next_event_ordinal=body["next_event_ordinal"],
            expected_event_count=body["schedule_count"],
            current_event_id=body["current_event_id"],
            event_ids=expected_event_ids,  # type: ignore[arg-type]
            status_counts=expected_counts,
            failed_event_ids=() if failure is None else (failure.event_id,),
        )
        if execution != expected_execution:
            raise ValueError("checkpoint execution state does not replay from causal evidence")
        _validate_depth(payload)
        frozen_prefix = tuple(_freeze(item) for item in prefix)
        return cls(
            version=body["version"],
            storage_schema_version=body["storage_schema_version"],
            run_id=body["run_id"],
            run_spec_hash=body["run_spec_hash"],
            protocol_id=body["protocol_id"],
            protocol_version=body["protocol_version"],
            protocol_hash=body["protocol_hash"],
            schedule_hash=body["schedule_hash"],
            schedule_count=body["schedule_count"],
            artifact_hashes=MappingProxyType(dict(artifacts)),
            expected_agent_ids_hash=body["expected_agent_ids_hash"],
            expected_exposure_mode=body["expected_exposure_mode"],
            expected_exposure_graph_hash=body["expected_exposure_graph_hash"],
            expected_exposure_graph_artifact_id=body["expected_exposure_graph_artifact_id"],
            expected_exposure_graph_artifact_type=body["expected_exposure_graph_artifact_type"],
            expected_source_ws_artifact_hash=body["expected_source_ws_artifact_hash"],
            expected_source_ws_artifact_id=body["expected_source_ws_artifact_id"],
            expected_source_ws_artifact_type=body["expected_source_ws_artifact_type"],
            round0_root=body["round0_root"],
            baseline_manifest_hash=body["baseline_manifest_hash"],
            current_manifest_hash=body["current_manifest_hash"],
            next_event_ordinal=body["next_event_ordinal"],
            current_event_id=body["current_event_id"],
            private_state_root=body["private_state_root"],
            public_stock_root=body["public_stock_root"],
            latest_public_pointer_root=body["latest_public_pointer_root"],
            feed_cursor_root=body["feed_cursor_root"],
            state_collection_root=body["state_collection_root"],
            event_chain_head=body["event_chain_head"],
            current_attempt_prefix=frozen_prefix,  # type: ignore[arg-type]
            execution_state=_freeze(execution_payload),  # type: ignore[arg-type]
            execution_state_hash=body["execution_state_hash"],
            terminal_failure=(None if failure_payload is None else _freeze(failure_payload)),  # type: ignore[arg-type]
            terminal_failure_hash=body["terminal_failure_hash"],
            resume_authorization=(
                None if authorization_payload is None else _freeze(authorization_payload)
            ),  # type: ignore[arg-type]
            resume_authorization_hash=body["resume_authorization_hash"],
            terminal_failure_prefix=tuple(  # type: ignore[arg-type]
                _freeze(item) for item in failure_prefix_payload
            ),
            terminal_failure_prefix_hash=body["terminal_failure_prefix_hash"],
            resume_authorization_prefix=tuple(  # type: ignore[arg-type]
                _freeze(item) for item in authorization_prefix_payload
            ),
            resume_authorization_prefix_hash=body["resume_authorization_prefix_hash"],
            causal_evidence_prefix=tuple(  # type: ignore[arg-type]
                _freeze(item) for item in causal_prefix_payload
            ),
            causal_evidence_root=body["causal_evidence_root"],
            v6_evidence_hashes=MappingProxyType(
                {name: tuple(hashes) for name, hashes in v6_hashes.items()}
            ),
            v6_evidence_root=body["v6_evidence_root"],
        )


def _root(values: list[object]) -> str:
    return canonical_payload_hash(values)


def _path(value: str | Path, *, must_exist: bool) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError("checkpoint path must be a string or Path")
    raw = str(value)
    if not raw or "\x00" in raw or "://" in raw:
        raise ValueError("checkpoint path must be a local filesystem path")
    path = Path(value)
    if path.is_symlink():
        raise ValueError("checkpoint path must not be a symbolic link")
    if must_exist:
        if not path.is_file():
            raise FileNotFoundError(f"checkpoint file does not exist: {path}")
    elif not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("checkpoint parent must be an existing non-symlink directory")
    return path


def _fsync_parent_directory(path: Path) -> bool:
    """Persist a rename on POSIX; Windows has no portable directory-fsync API."""

    if os.name == "nt":
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path.parent, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def _open_checkpoint_windows(path: Path) -> int:
    """Open one Windows handle without following a final reparse point."""

    import ctypes
    from ctypes import wintypes
    import msvcrt

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    absolute = os.path.abspath(os.fspath(path))
    if absolute.startswith("\\\\"):
        api_path = "\\\\?\\UNC\\" + absolute[2:]
    else:
        api_path = "\\\\?\\" + absolute
    handle = create_file(
        api_path,
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # FILE_SHARE_READ | WRITE | DELETE
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x02000000,  # OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    information = FileAttributeTagInfo()
    try:
        if not get_information(
            handle,
            9,  # FileAttributeTagInfo
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if information.file_attributes & 0x00000400:  # FILE_ATTRIBUTE_REPARSE_POINT
            raise ValueError("checkpoint path must not be a Windows reparse point")
        descriptor = msvcrt.open_osfhandle(
            handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
    except BaseException:
        close_handle(handle)
        raise
    return descriptor


def write_checkpoint_atomic(path: str | Path, checkpoint: Checkpoint) -> str:
    """Atomically replace a local checkpoint without damaging an older file."""

    if not isinstance(checkpoint, Checkpoint):
        raise TypeError("checkpoint must be a Checkpoint")
    checkpoint = Checkpoint.from_payload(checkpoint.to_payload())
    target = _path(path, must_exist=False)
    raw = _canonical_json(checkpoint.to_payload()).encode("utf-8")
    if len(raw) > _MAX_CHECKPOINT_BYTES:
        raise ValueError("checkpoint exceeds maximum byte size")
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        _fsync_parent_directory(target)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return checkpoint.checkpoint_hash


def load_checkpoint(path: str | Path) -> Checkpoint:
    """Load a bounded canonical checkpoint from a local regular file."""

    source = _path(path, must_exist=True)
    if os.name == "nt":
        descriptor = _open_checkpoint_windows(source)
    else:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("checkpoint must be a regular file")
        if metadata.st_size > _MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint exceeds maximum byte size")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw_bytes = stream.read(_MAX_CHECKPOINT_BYTES + 1)
        if len(raw_bytes) > _MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint exceeds maximum byte size")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("checkpoint is not valid UTF-8") from error
    _preflight_json_depth(raw)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("checkpoint JSON contains a duplicate key")
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise ValueError("checkpoint JSON is invalid or contains a duplicate key") from error
    _validate_depth(payload)
    if raw != _canonical_json(payload):
        raise ValueError("checkpoint JSON bytes are not canonical")
    return Checkpoint.from_payload(payload)


def build_checkpoint(storage: RunStorage) -> Checkpoint:
    """Build a deterministic checkpoint from fully verified storage."""

    if not isinstance(storage, RunStorage):
        raise TypeError("storage must be a RunStorage")
    with storage.consistent_read():
        return _build_checkpoint_snapshot(storage, version=_CHECKPOINT_VERSION)


def _build_checkpoint_snapshot(storage: RunStorage, *, version: str) -> Checkpoint:
    """Build while the caller pins one authoritative SQLite read snapshot."""

    if version not in _SUPPORTED_CHECKPOINT_VERSIONS:
        raise ValueError("checkpoint projection version is unsupported")
    binding = storage.binding
    if binding.round0_root is None:
        raise ValueError("checkpoint requires sealed round-0 state")
    progress = storage.progress
    evidence = storage._recovery_evidence_snapshot(checkpoint_version=version)
    private_root = _root(list(evidence["private_states"]))
    public_root = _root(list(evidence["public_stock"]))
    pointer_root = _root(list(evidence["latest_public_pointers"]))
    cursor_root = _root(list(evidence["feed_cursors"]))
    current_manifest_hash = canonical_payload_hash(
        {
            "baseline_manifest_hash": binding.manifest_hash,
            "next_event_ordinal": progress.next_event_ordinal,
            "succeeded_event_count": progress.succeeded_event_count,
            "event_chain_head": progress.event_chain_head,
        }
    )
    current_event_id = (
        derive_event_id(binding.run_id, progress.next_event_ordinal)
        if progress.next_event_ordinal < progress.expected_event_count
        else None
    )
    execution_payload = _plain(evidence["execution_state"])
    assert type(execution_payload) is dict
    failure_payload = _plain(evidence["terminal_failure"])
    authorization_payload = _plain(evidence["resume_authorization"])
    failure_prefix_payload = _plain(evidence["terminal_failure_prefix"])
    authorization_prefix_payload = _plain(evidence["resume_authorization_prefix"])
    causal_prefix_payload = _plain(evidence["causal_evidence_prefix"])
    assert type(failure_prefix_payload) is list
    assert type(authorization_prefix_payload) is list
    assert type(causal_prefix_payload) is list
    checkpoint = Checkpoint(
        version=version,
        storage_schema_version=binding.schema_version,
        run_id=binding.run_id,
        run_spec_hash=binding.run_spec_hash,
        protocol_id=binding.protocol_id,
        protocol_version=binding.protocol_version,
        protocol_hash=binding.protocol_hash,
        schedule_hash=binding.schedule_hash,
        schedule_count=binding.schedule_count,
        artifact_hashes=MappingProxyType(dict(binding.artifact_hashes)),
        expected_agent_ids_hash=binding.expected_agent_ids_hash,
        expected_exposure_mode=binding.expected_exposure_mode,
        expected_exposure_graph_hash=binding.expected_exposure_graph_hash,
        expected_exposure_graph_artifact_id=binding.expected_exposure_graph_artifact_id,
        expected_exposure_graph_artifact_type=binding.expected_exposure_graph_artifact_type,
        expected_source_ws_artifact_hash=binding.expected_source_ws_artifact_hash,
        expected_source_ws_artifact_id=binding.expected_source_ws_artifact_id,
        expected_source_ws_artifact_type=binding.expected_source_ws_artifact_type,
        round0_root=binding.round0_root,
        baseline_manifest_hash=binding.manifest_hash,
        current_manifest_hash=current_manifest_hash,
        next_event_ordinal=progress.next_event_ordinal,
        current_event_id=current_event_id,
        private_state_root=private_root,
        public_stock_root=public_root,
        latest_public_pointer_root=pointer_root,
        feed_cursor_root=cursor_root,
        state_collection_root=canonical_payload_hash(
            {
                "private_state_root": private_root,
                "public_stock_root": public_root,
                "latest_public_pointer_root": pointer_root,
                "feed_cursor_root": cursor_root,
            }
        ),
        event_chain_head=evidence["event_chain_head"],  # type: ignore[arg-type]
        current_attempt_prefix=evidence["current_attempt_prefix"],  # type: ignore[arg-type]
        execution_state=execution_payload,
        execution_state_hash=canonical_payload_hash(execution_payload),
        terminal_failure=failure_payload,  # type: ignore[arg-type]
        terminal_failure_hash=(
            None if failure_payload is None else canonical_payload_hash(failure_payload)
        ),
        resume_authorization=authorization_payload,  # type: ignore[arg-type]
        resume_authorization_hash=(
            None if authorization_payload is None else canonical_payload_hash(authorization_payload)
        ),
        terminal_failure_prefix=tuple(failure_prefix_payload),  # type: ignore[arg-type]
        terminal_failure_prefix_hash=canonical_payload_hash(failure_prefix_payload),
        resume_authorization_prefix=tuple(authorization_prefix_payload),  # type: ignore[arg-type]
        resume_authorization_prefix_hash=canonical_payload_hash(authorization_prefix_payload),
        causal_evidence_prefix=tuple(causal_prefix_payload),  # type: ignore[arg-type]
        causal_evidence_root=canonical_payload_hash(causal_prefix_payload),
        v6_evidence_hashes=evidence["v6_evidence_hashes"],  # type: ignore[arg-type]
        v6_evidence_root=evidence["v6_evidence_root"],  # type: ignore[arg-type]
    )
    return Checkpoint.from_payload(checkpoint.to_payload())


def validate_checkpoint(checkpoint: Checkpoint, storage: RunStorage) -> str:
    """Validate a checkpoint against storage and classify its freshness."""

    if not isinstance(checkpoint, Checkpoint):
        raise TypeError("checkpoint must be a Checkpoint")
    checkpoint = Checkpoint.from_payload(checkpoint.to_payload())
    with storage.consistent_read():
        return _validate_checkpoint_snapshot(checkpoint, storage)


def _validate_checkpoint_snapshot(checkpoint: Checkpoint, storage: RunStorage) -> str:
    """Classify freshness while the caller holds one SQLite read snapshot."""

    if checkpoint.next_event_ordinal > storage.progress.next_event_ordinal:
        raise ValueError("checkpoint is ahead of SQLite storage")
    if checkpoint.next_event_ordinal < storage.progress.next_event_ordinal:
        evidence = storage._recovery_evidence_snapshot(
            checkpoint.next_event_ordinal,
            checkpoint_version=checkpoint.version,
        )
        expected = _build_checkpoint_from_evidence(
            storage,
            evidence,
            version=checkpoint.version,
        )
        if not _is_attempt_prefix(
            checkpoint.current_attempt_prefix,
            evidence["current_attempt_prefix"],  # type: ignore[arg-type]
        ):
            raise ValueError("stale checkpoint attempt prefix conflicts with SQLite history")
        if not _is_evidence_prefix(checkpoint, expected):
            raise ValueError("stale checkpoint recovery authorization prefix conflicts")
        if not _candidate_covers_bound_failures(checkpoint, expected):
            raise ValueError("checkpoint causal evidence omits a bound failed attempt")
        expected = _replace_progress_evidence(expected, checkpoint)
        if checkpoint != expected:
            raise ValueError("stale checkpoint conflicts with SQLite history")
        return "stale"
    current = _build_checkpoint_snapshot(storage, version=checkpoint.version)
    if checkpoint == current:
        return "current"
    if (
        _is_attempt_prefix(
            checkpoint.current_attempt_prefix,
            current.current_attempt_prefix,
        )
        and _is_evidence_prefix(checkpoint, current)
        and _candidate_covers_bound_failures(checkpoint, current)
        and checkpoint == _replace_progress_evidence(current, checkpoint)
    ):
        return "stale"
    raise ValueError("checkpoint conflicts with SQLite storage")


def _candidate_covers_bound_failures(candidate: Checkpoint, stored: Checkpoint) -> bool:
    """Replay candidate attempt cycles without collapsing legal pre-halt stages."""

    del stored  # Prefix equality is checked separately; this helper checks causal completeness.
    failures = tuple(
        TerminalFailureEvidence.from_payload(_plain(item))
        for item in candidate.terminal_failure_prefix
    )
    authorizations = tuple(
        ResumeAuthorizationEvidence.from_payload(_plain(item))
        for item in candidate.resume_authorization_prefix
    )
    failure_by_attempt = {
        (item.event_id, item.event_ordinal, item.attempt_id, item.attempt_index): item
        for item in failures
    }
    authorization_by_failure = {
        item.previous_terminal_failure_hash: item for item in authorizations
    }
    attempts = candidate.current_attempt_prefix
    for position, attempt in enumerate(attempts):
        transitions = attempt.get("transitions")
        if not isinstance(transitions, (tuple, list)) or not transitions:
            return False
        terminal = transitions[-1]
        if not isinstance(terminal, Mapping):
            return False
        status = terminal.get("status")
        key = (
            candidate.current_event_id,
            candidate.next_event_ordinal,
            attempt.get("attempt_id"),
            attempt.get("attempt_index"),
        )
        failure = failure_by_attempt.get(key)
        authorization = (
            None if failure is None else authorization_by_failure.get(failure.payload_hash)
        )
        if position < len(attempts) - 1:
            if status != EventStatus.FAILED.value or failure is None or authorization is None:
                return False
        elif status != EventStatus.FAILED.value and failure is not None:
            return False
    return True


def _is_evidence_prefix(candidate: Checkpoint, stored: Checkpoint) -> bool:
    if set(candidate.v6_evidence_hashes) != set(stored.v6_evidence_hashes):
        return False
    for table, candidate_hashes in candidate.v6_evidence_hashes.items():
        stored_hashes = stored.v6_evidence_hashes[table]
        if len(candidate_hashes) > len(stored_hashes) or tuple(candidate_hashes) != tuple(
            stored_hashes[: len(candidate_hashes)]
        ):
            return False
    if not _is_status_conditioned_v6_prefix(candidate, stored):
        return False
    required_committed = tuple(
        item
        for item in stored.causal_evidence_prefix
        if item.get("event_ordinal") < candidate.next_event_ordinal
    )
    if len(candidate.causal_evidence_prefix) < len(required_committed) or _plain(
        candidate.causal_evidence_prefix[: len(required_committed)]
    ) != _plain(required_committed):
        return False
    for candidate_values, stored_values in (
        (candidate.terminal_failure_prefix, stored.terminal_failure_prefix),
        (candidate.resume_authorization_prefix, stored.resume_authorization_prefix),
        (candidate.causal_evidence_prefix, stored.causal_evidence_prefix),
    ):
        if len(candidate_values) > len(stored_values) or _plain(candidate_values) != _plain(
            stored_values[: len(candidate_values)]
        ):
            return False
    return True


def _current_v6_counts(checkpoint: Checkpoint) -> tuple[int, int, int, int]:
    """Return current event/request/required invocation/parse row counts."""

    attempts = checkpoint.current_attempt_prefix
    if not attempts:
        return (0, 0, 0, 0)
    terminal = 0
    in_progress = 0
    for attempt in attempts:
        transitions = attempt["transitions"]
        status = transitions[-1]["status"]
        if status in {EventStatus.SUCCEEDED.value, EventStatus.FAILED.value}:
            terminal += 1
        elif status == EventStatus.IN_PROGRESS.value:
            in_progress += 1
    return (1, len(attempts), terminal, in_progress)


def _is_status_conditioned_v6_prefix(candidate: Checkpoint, stored: Checkpoint) -> bool:
    """Prevent independent table-prefix truncation from inventing a lifecycle state."""

    names = candidate.v6_evidence_hashes
    stored_names = stored.v6_evidence_hashes
    if not any(stored_names.values()):
        return not any(names.values())
    stored_event, stored_requests, stored_terminal, stored_in_progress = _current_v6_counts(stored)
    candidate_event, candidate_requests, candidate_terminal, candidate_in_progress = (
        _current_v6_counts(candidate)
    )
    base_event = len(stored_names["event_input_evidence"]) - stored_event
    base_policy = len(stored_names["attempt_policy_evidence"]) - stored_event
    base_requests = len(stored_names["adapter_requests"]) - stored_requests
    base_parse = len(stored_names["parse_evidence"]) - stored_terminal
    stored_current_invocations = stored_terminal + min(stored_in_progress, 1)
    if len(stored_names["invocation_evidence"]) < base_parse + stored_terminal:
        return False
    if len(stored_names["invocation_evidence"]) == base_parse + stored_terminal:
        stored_current_invocations = stored_terminal
    base_invocation = len(stored_names["invocation_evidence"]) - stored_current_invocations
    expected_fixed = {
        "event_input_evidence": base_event + candidate_event,
        "attempt_policy_evidence": base_policy + candidate_event,
        "adapter_requests": base_requests + candidate_requests,
        "parse_evidence": base_parse + candidate_terminal,
    }
    if any(len(names[table]) != count for table, count in expected_fixed.items()):
        return False
    invocation_count = len(names["invocation_evidence"])
    allowed_invocations = {base_invocation + candidate_terminal}
    if candidate_in_progress:
        allowed_invocations.add(base_invocation + candidate_terminal + 1)
    if invocation_count not in allowed_invocations:
        return False
    expected_binding = 1 if len(names["adapter_requests"]) else 0
    return len(names["adapter_execution_bindings"]) == expected_binding


def _replace_progress_evidence(expected: Checkpoint, candidate: Checkpoint) -> Checkpoint:
    """Replay, rather than trust, a structurally validated older causal prefix."""

    counts = {status.value: 0 for status in EventStatus}
    counts[EventStatus.SUCCEEDED.value] = candidate.next_event_ordinal
    event_ids = tuple(
        derive_event_id(candidate.run_id, ordinal)
        for ordinal in range(candidate.next_event_ordinal)
    )
    if candidate.current_attempt_prefix:
        status = candidate.current_attempt_prefix[-1]["transitions"][-1]["status"]
        counts[status] += 1
        event_ids += (candidate.current_event_id,)  # type: ignore[arg-type]
    terminal_payload = (
        candidate.causal_evidence_prefix[-1] if candidate.causal_evidence_prefix else None
    )
    terminal: TerminalFailureEvidence | ResumeAuthorizationEvidence | None = None
    if terminal_payload is not None:
        plain_terminal = _plain(terminal_payload)
        assert type(plain_terminal) is dict
        terminal = (
            TerminalFailureEvidence.from_payload(plain_terminal)
            if plain_terminal.get("evidence_kind") == "failure"
            else ResumeAuthorizationEvidence.from_payload(plain_terminal)
        )
        if terminal.event_ordinal != candidate.next_event_ordinal:
            terminal = None
    failure = terminal if isinstance(terminal, TerminalFailureEvidence) else None
    authorization = terminal if isinstance(terminal, ResumeAuthorizationEvidence) else None
    execution = ExecutionState(
        schema_version="paper1.execution-state.v1",
        run_id=candidate.run_id,
        baseline_manifest_hash=candidate.baseline_manifest_hash,
        status=(
            ExecutionStatus.COMPLETE
            if candidate.next_event_ordinal == candidate.schedule_count
            else ExecutionStatus.FAILED
            if failure is not None
            else ExecutionStatus.RUNNING
        ),
        next_event_ordinal=candidate.next_event_ordinal,
        expected_event_count=candidate.schedule_count,
        current_event_id=candidate.current_event_id,
        event_ids=event_ids,
        status_counts=counts,
        failed_event_ids=() if failure is None else (failure.event_id,),
    )
    failure_payload = None if failure is None else failure.to_payload()
    authorization_payload = None if authorization is None else authorization.to_payload()

    return replace(
        expected,
        current_attempt_prefix=candidate.current_attempt_prefix,
        execution_state=_freeze(execution.to_payload()),  # type: ignore[arg-type]
        execution_state_hash=execution.payload_hash,
        terminal_failure=(None if failure_payload is None else _freeze(failure_payload)),  # type: ignore[arg-type]
        terminal_failure_hash=None if failure is None else failure.payload_hash,
        resume_authorization=(
            None if authorization_payload is None else _freeze(authorization_payload)
        ),  # type: ignore[arg-type]
        resume_authorization_hash=(None if authorization is None else authorization.payload_hash),
        terminal_failure_prefix=candidate.terminal_failure_prefix,
        terminal_failure_prefix_hash=candidate.terminal_failure_prefix_hash,
        resume_authorization_prefix=candidate.resume_authorization_prefix,
        resume_authorization_prefix_hash=candidate.resume_authorization_prefix_hash,
        causal_evidence_prefix=candidate.causal_evidence_prefix,
        causal_evidence_root=candidate.causal_evidence_root,
        v6_evidence_hashes=candidate.v6_evidence_hashes,
        v6_evidence_root=candidate.v6_evidence_root,
    )


def _is_attempt_prefix(
    candidate: tuple[Mapping[str, object], ...],
    stored: tuple[Mapping[str, object], ...],
) -> bool:
    if len(candidate) > len(stored):
        return False
    for candidate_attempt, stored_attempt in zip(candidate, stored):
        if candidate_attempt.get("attempt_id") != stored_attempt.get("attempt_id") or (
            candidate_attempt.get("attempt_index") != stored_attempt.get("attempt_index")
        ):
            return False
        for name in ("transitions", "transition_entries"):
            candidate_values = tuple(candidate_attempt.get(name, ()))
            stored_values = tuple(stored_attempt.get(name, ()))
            if len(candidate_values) > len(stored_values) or _plain(candidate_values) != _plain(
                stored_values[: len(candidate_values)]
            ):
                return False
    return True


def _build_checkpoint_from_evidence(
    storage: RunStorage,
    evidence: Mapping[str, object],
    *,
    version: str,
) -> Checkpoint:
    """Build a historical checkpoint projection for stale validation."""

    if version not in _SUPPORTED_CHECKPOINT_VERSIONS:
        raise ValueError("checkpoint projection version is unsupported")
    binding = storage.binding
    ordinal = evidence["next_event_ordinal"]
    assert type(ordinal) is int
    private_root = _root(list(evidence["private_states"]))
    public_root = _root(list(evidence["public_stock"]))
    pointer_root = _root(list(evidence["latest_public_pointers"]))
    cursor_root = _root(list(evidence["feed_cursors"]))
    chain_head = evidence["event_chain_head"]
    assert type(chain_head) is str
    current_manifest_hash = canonical_payload_hash(
        {
            "baseline_manifest_hash": binding.manifest_hash,
            "next_event_ordinal": ordinal,
            "succeeded_event_count": ordinal,
            "event_chain_head": chain_head,
        }
    )
    attempt_prefix = evidence["current_attempt_prefix"]
    assert isinstance(attempt_prefix, (tuple, list))
    succeeded_ids = tuple(derive_event_id(binding.run_id, index) for index in range(ordinal))
    counts = {status.value: 0 for status in EventStatus}
    counts[EventStatus.SUCCEEDED.value] = ordinal
    event_ids = succeeded_ids
    if attempt_prefix:
        latest = attempt_prefix[-1]
        assert isinstance(latest, Mapping)
        transitions = latest["transitions"]
        assert isinstance(transitions, (tuple, list)) and transitions
        terminal = transitions[-1]
        assert isinstance(terminal, Mapping)
        terminal_status = terminal["status"]
        assert isinstance(terminal_status, str)
        counts[terminal_status] += 1
        event_ids += (derive_event_id(binding.run_id, ordinal),)
    execution = ExecutionState(
        schema_version="paper1.execution-state.v1",
        run_id=binding.run_id,
        baseline_manifest_hash=binding.manifest_hash,
        status=(
            ExecutionStatus.COMPLETE
            if ordinal == binding.schedule_count
            else ExecutionStatus.RUNNING
        ),
        next_event_ordinal=ordinal,
        expected_event_count=binding.schedule_count,
        current_event_id=(
            derive_event_id(binding.run_id, ordinal) if ordinal < binding.schedule_count else None
        ),
        event_ids=event_ids,
        status_counts=counts,
        failed_event_ids=(),
    )
    failure_prefix_payload = _plain(evidence["terminal_failure_prefix"])
    authorization_prefix_payload = _plain(evidence["resume_authorization_prefix"])
    causal_prefix_payload = _plain(evidence["causal_evidence_prefix"])
    assert type(failure_prefix_payload) is list
    assert type(authorization_prefix_payload) is list
    assert type(causal_prefix_payload) is list
    failure_payload = _plain(evidence["terminal_failure"])
    authorization_payload = _plain(evidence["resume_authorization"])
    checkpoint = Checkpoint(
        version=version,
        storage_schema_version=binding.schema_version,
        run_id=binding.run_id,
        run_spec_hash=binding.run_spec_hash,
        protocol_id=binding.protocol_id,
        protocol_version=binding.protocol_version,
        protocol_hash=binding.protocol_hash,
        schedule_hash=binding.schedule_hash,
        schedule_count=binding.schedule_count,
        artifact_hashes=MappingProxyType(dict(binding.artifact_hashes)),
        expected_agent_ids_hash=binding.expected_agent_ids_hash,
        expected_exposure_mode=binding.expected_exposure_mode,
        expected_exposure_graph_hash=binding.expected_exposure_graph_hash,
        expected_exposure_graph_artifact_id=binding.expected_exposure_graph_artifact_id,
        expected_exposure_graph_artifact_type=binding.expected_exposure_graph_artifact_type,
        expected_source_ws_artifact_hash=binding.expected_source_ws_artifact_hash,
        expected_source_ws_artifact_id=binding.expected_source_ws_artifact_id,
        expected_source_ws_artifact_type=binding.expected_source_ws_artifact_type,
        round0_root=binding.round0_root,  # type: ignore[arg-type]
        baseline_manifest_hash=binding.manifest_hash,
        current_manifest_hash=current_manifest_hash,
        next_event_ordinal=ordinal,
        current_event_id=(
            derive_event_id(binding.run_id, ordinal) if ordinal < binding.schedule_count else None
        ),
        private_state_root=private_root,
        public_stock_root=public_root,
        latest_public_pointer_root=pointer_root,
        feed_cursor_root=cursor_root,
        state_collection_root=canonical_payload_hash(
            {
                "private_state_root": private_root,
                "public_stock_root": public_root,
                "latest_public_pointer_root": pointer_root,
                "feed_cursor_root": cursor_root,
            }
        ),
        event_chain_head=chain_head,
        current_attempt_prefix=attempt_prefix,  # type: ignore[arg-type]
        execution_state=execution.to_payload(),
        execution_state_hash=execution.payload_hash,
        terminal_failure=failure_payload,  # type: ignore[arg-type]
        terminal_failure_hash=(
            None if failure_payload is None else canonical_payload_hash(failure_payload)
        ),
        resume_authorization=authorization_payload,  # type: ignore[arg-type]
        resume_authorization_hash=(
            None if authorization_payload is None else canonical_payload_hash(authorization_payload)
        ),
        terminal_failure_prefix=tuple(failure_prefix_payload),  # type: ignore[arg-type]
        terminal_failure_prefix_hash=canonical_payload_hash(failure_prefix_payload),
        resume_authorization_prefix=tuple(authorization_prefix_payload),  # type: ignore[arg-type]
        resume_authorization_prefix_hash=canonical_payload_hash(authorization_prefix_payload),
        causal_evidence_prefix=tuple(causal_prefix_payload),  # type: ignore[arg-type]
        causal_evidence_root=canonical_payload_hash(causal_prefix_payload),
        v6_evidence_hashes=evidence["v6_evidence_hashes"],  # type: ignore[arg-type]
        v6_evidence_root=evidence["v6_evidence_root"],  # type: ignore[arg-type]
    )
    return Checkpoint.from_payload(checkpoint.to_payload())
