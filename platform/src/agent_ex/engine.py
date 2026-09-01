"""Strictly serial single-event lifecycle kernel for mock Phase 4B execution.

This module intentionally stops at lifecycle orchestration.  Feed construction,
prompt provenance persistence, retry/timeout policy, and real provider execution
remain outside this C2 boundary and must be supplied explicitly by later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from .adapters.base import (
    AdapterRequest,
    AdapterResponse,
    _has_trusted_request_seal,
    _has_trusted_response_seal,
)
from .checkpoint import build_checkpoint, write_checkpoint_atomic
from .domain import (
    EventStatus,
    GenerationAttempt,
    GenerationEvent,
    _require_id,
    _require_int,
    _require_sha256,
    _require_timestamp,
    _freeze,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
)
from .feed import FeedCursor
from .state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from .storage import EventJournalState, RunLease, RunStorage


def _deep_freeze(value: object) -> object:
    """Recursively copy evidence, including non-JSON sets used by in-memory context."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return _freeze(value)


def _response_provider_metadata(response: AdapterResponse) -> dict[str, object]:
    """Canonical adapter provenance that must survive in GenerationAttempt metadata."""

    return {
        "adapter_response_id": response.response_id,
        "adapter_response_hash": response.record_hash,
        "adapter_outcome": response.outcome,
        "adapter_error": None if response.error is None else dict(response.error),
        "runtime_identity": dict(response.runtime_identity),
        "runtime_identity_hash": response.runtime_identity_hash,
        "script_hash": response.script_hash,
    }


@dataclass(frozen=True, slots=True)
class AttemptAuthorization:
    run_id: str
    event_id: str
    event_ordinal: int
    attempt_index: int
    model_seed: int
    model_identity: Mapping[str, object]
    model_identity_hash: str
    request_parameters: Mapping[str, object]
    request_parameters_hash: str
    resume_authorization_hash: str | None
    mock_only: bool

    def __post_init__(self) -> None:
        _require_id("authorization run_id", self.run_id)
        _require_id("authorization event_id", self.event_id)
        _require_int("authorization event_ordinal", self.event_ordinal)
        _require_int("authorization attempt_index", self.attempt_index, minimum=1)
        _require_int("authorization model_seed", self.model_seed)
        if self.event_id != derive_event_id(self.run_id, self.event_ordinal):
            raise ValueError("authorization event identity is not derived from run and ordinal")
        if not isinstance(self.model_identity, Mapping) or not self.model_identity:
            raise ValueError("authorization model_identity must be a non-empty mapping")
        if not isinstance(self.request_parameters, Mapping):
            raise TypeError("authorization request_parameters must be a mapping")
        _require_sha256("authorization model_identity_hash", self.model_identity_hash)
        _require_sha256("authorization request_parameters_hash", self.request_parameters_hash)
        if self.model_identity_hash != canonical_payload_hash(self.model_identity):
            raise ValueError("authorization model identity hash does not match")
        if self.request_parameters_hash != canonical_payload_hash(self.request_parameters):
            raise ValueError("authorization request parameters hash does not match")
        if self.resume_authorization_hash is not None:
            _require_sha256(
                "authorization resume_authorization_hash", self.resume_authorization_hash
            )
        if self.mock_only is not True:
            raise ValueError("lifecycle authorization must remain explicitly mock_only")
        object.__setattr__(self, "model_identity", _deep_freeze(self.model_identity))
        object.__setattr__(self, "request_parameters", _deep_freeze(self.request_parameters))


@dataclass(frozen=True, slots=True)
class AttemptExecutionEvidence:
    started_at: str
    finished_at: str
    http_status: int | None
    provider_metadata: Mapping[str, object]
    usage: Mapping[str, object]
    finish_reason: str | None

    def __post_init__(self) -> None:
        started = _require_timestamp("execution started_at", self.started_at)
        finished = _require_timestamp("execution finished_at", self.finished_at)
        if finished < started:
            raise ValueError("execution finished_at cannot precede started_at")
        if self.http_status is not None:
            _require_int("execution http_status", self.http_status, minimum=100)
            if self.http_status > 599:
                raise ValueError("execution http_status must be at most 599")
        if not isinstance(self.provider_metadata, Mapping):
            raise TypeError("execution provider_metadata must be a mapping")
        if not isinstance(self.usage, Mapping):
            raise TypeError("execution usage must be a mapping")
        if self.finish_reason is not None and (
            type(self.finish_reason) is not str or not self.finish_reason
        ):
            raise ValueError("execution finish_reason must be non-empty or None")
        object.__setattr__(self, "provider_metadata", _deep_freeze(self.provider_metadata))
        object.__setattr__(self, "usage", _deep_freeze(self.usage))


@dataclass(frozen=True, slots=True)
class AttemptInvocationResult:
    response: AdapterResponse
    evidence: AttemptExecutionEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.response, AdapterResponse):
            raise TypeError("invocation response must be typed AdapterResponse")
        if not isinstance(self.evidence, AttemptExecutionEvidence):
            raise TypeError("invocation execution evidence must be typed")


@dataclass(frozen=True, slots=True)
class PreparedAttempt:
    authorization: AttemptAuthorization
    request: AdapterRequest
    pending_attempt: GenerationAttempt
    in_progress_attempt: GenerationAttempt
    context_provenance: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.authorization, AttemptAuthorization):
            raise TypeError("prepared authorization must be typed")
        if not isinstance(self.request, AdapterRequest) or not _has_trusted_request_seal(
            self.request
        ):
            raise ValueError("prepared request must be a trusted sealed AdapterRequest")
        if not isinstance(self.pending_attempt, GenerationAttempt) or not isinstance(
            self.in_progress_attempt, GenerationAttempt
        ):
            raise TypeError("prepared attempts must be typed")
        if self.pending_attempt.status is not EventStatus.PENDING:
            raise ValueError("prepared pending attempt must have PENDING status")
        if self.in_progress_attempt.status is not EventStatus.IN_PROGRESS:
            raise ValueError("prepared in-progress attempt must have IN_PROGRESS status")
        if not isinstance(self.context_provenance, Mapping) or not self.context_provenance:
            raise ValueError("prepared attempt requires explicit future-C3 context provenance")
        object.__setattr__(self, "context_provenance", _deep_freeze(self.context_provenance))


@dataclass(frozen=True, slots=True)
class SuccessfulEventCommit:
    event: GenerationEvent
    private_update: PrivateUpdate
    private_state: PrivateState
    feed_cursor: FeedCursor
    public_post: PublicPost | None
    latest_public_pointer: LatestPublicPointer | None

    def __post_init__(self) -> None:
        if not isinstance(self.event, GenerationEvent):
            raise TypeError("commit event must be typed")
        if not isinstance(self.private_update, PrivateUpdate):
            raise TypeError("commit private_update must be typed")
        if not isinstance(self.private_state, PrivateState):
            raise TypeError("commit private_state must be typed")
        if not isinstance(self.feed_cursor, FeedCursor):
            raise TypeError("commit feed_cursor must be typed")
        if self.public_post is not None and not isinstance(self.public_post, PublicPost):
            raise TypeError("commit public_post must be typed or None")
        if self.latest_public_pointer is not None and not isinstance(
            self.latest_public_pointer, LatestPublicPointer
        ):
            raise TypeError("commit latest_public_pointer must be typed or None")


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    state: str
    event_id: str | None
    attempt: GenerationAttempt | None
    adapter_invoked: bool

    def __post_init__(self) -> None:
        if self.state not in {"committed", "failed", "complete"}:
            raise ValueError("attempt outcome state is unsupported")
        if self.event_id is not None:
            _require_id("outcome event_id", self.event_id)
        if self.attempt is not None and not isinstance(self.attempt, GenerationAttempt):
            raise TypeError("outcome attempt must be typed or None")
        if type(self.adapter_invoked) is not bool:
            raise TypeError("outcome adapter_invoked must be boolean")


class AttemptLifecycleFailure(RuntimeError):
    """Typed failure carrying complete, caller-observed terminal attempt evidence."""

    def __init__(self, terminal_attempt: GenerationAttempt) -> None:
        if not isinstance(terminal_attempt, GenerationAttempt):
            raise TypeError("lifecycle failure requires a typed terminal attempt")
        if terminal_attempt.status is not EventStatus.FAILED:
            raise ValueError("lifecycle failure requires FAILED attempt evidence")
        self.terminal_attempt = terminal_attempt
        super().__init__("attempt lifecycle failed with explicit terminal evidence")


class StrictSerialLifecycleEngine:
    """Own one run lease and advance only the storage journal's current event."""

    def __init__(self, storage: RunStorage) -> None:
        self._storage = storage
        self._lease: RunLease | None = None

    def __enter__(self) -> StrictSerialLifecycleEngine:
        if self._lease is not None:
            raise RuntimeError("lifecycle engine is already open")
        lease = self._storage.acquire_run_lease()
        lease.acquire()
        try:
            self._storage.verify_integrity()
        except BaseException:
            lease.release()
            raise
        self._lease = lease
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self._lease is not None:
            self._lease.release()
            self._lease = None

    def write_checkpoint(self, path: str | Path) -> str:
        self._require_open()
        return write_checkpoint_atomic(path, build_checkpoint(self._storage))

    def execute(
        self,
        *,
        prepare: Callable[[EventJournalState], PreparedAttempt],
        invoke: Callable[[AdapterRequest], AttemptInvocationResult],
        finalize: Callable[[PreparedAttempt, AttemptInvocationResult], GenerationAttempt],
        build_commit: Callable[[GenerationAttempt], SuccessfulEventCommit],
        reconciliation: AttemptInvocationResult | None = None,
    ) -> AttemptOutcome:
        """Advance exactly the current journal event, never selecting policy defaults."""

        self._require_open()
        journal = self._storage.current_event_journal()
        if (
            reconciliation is not None
            and journal.resume_state != "in_progress_requires_provider_reconciliation"
        ):
            raise ValueError("reconciliation is only valid for an existing IN_PROGRESS attempt")
        if journal.resume_state == "complete":
            return AttemptOutcome("complete", None, None, False)
        if journal.event_id is None:
            raise ValueError("current journal event identity is missing")
        if journal.resume_state == "succeeded_attempt_requires_atomic_commit":
            terminal = journal.latest_transition
            if terminal is None or terminal.status is not EventStatus.SUCCEEDED:
                raise ValueError("landed success journal is inconsistent")
            self._commit_terminal(terminal, build_commit)
            return AttemptOutcome("committed", journal.event_id, terminal, False)
        if journal.resume_state in {
            "failed_attempt_requires_external_authorization",
            "halted_current_event",
        }:
            raise RuntimeError("failed current event requires explicit external authorization")

        value = prepare(journal)
        self._validate_prepared(
            value, journal.event_id, journal.event_ordinal, journal.next_attempt_index
        )
        if journal.resume_state == "retry_same_event":
            authorization = self._storage.resume_authorization_evidence()
            if (
                authorization is None
                or value.authorization.resume_authorization_hash != authorization.payload_hash
            ):
                raise ValueError("retry requires the exact resume authorization hash")
        elif value.authorization.resume_authorization_hash is not None:
            raise ValueError("first or resumed existing attempt cannot carry retry authorization")

        invoked = False
        try:
            if journal.resume_state in {"new_attempt", "retry_same_event"}:
                self._storage.append_attempt(value.pending_attempt)
                self._storage.append_attempt(value.in_progress_attempt)
                invoked = True
                result = invoke(value.request)
            elif journal.resume_state == "pending_attempt_requires_same_request":
                if journal.latest_transition != value.pending_attempt:
                    raise ValueError("pending recovery requires the exact sealed request evidence")
                self._storage.append_attempt(value.in_progress_attempt)
                invoked = True
                result = invoke(value.request)
            elif journal.resume_state == "in_progress_requires_provider_reconciliation":
                if journal.latest_transition != value.in_progress_attempt:
                    raise ValueError("in-progress recovery request evidence drifted")
                if reconciliation is None:
                    raise RuntimeError(
                        "in-progress attempt requires explicit provider reconciliation"
                    )
                result = reconciliation
            else:
                raise RuntimeError(f"unsupported journal resume state: {journal.resume_state}")
        except AttemptLifecycleFailure as failure:
            self._validate_failed_terminal(value, failure.terminal_attempt)
            self._storage.append_attempt(failure.terminal_attempt)
            return AttemptOutcome(
                "failed", value.authorization.event_id, failure.terminal_attempt, invoked
            )

        self._validate_invocation(value, result)
        try:
            terminal = finalize(value, result)
        except AttemptLifecycleFailure as failure:
            self._validate_terminal(value, result, failure.terminal_attempt)
            self._storage.append_attempt(failure.terminal_attempt)
            return AttemptOutcome(
                "failed", value.authorization.event_id, failure.terminal_attempt, invoked
            )
        self._validate_terminal(value, result, terminal)
        self._storage.append_attempt(terminal)
        if terminal.status is EventStatus.FAILED:
            return AttemptOutcome("failed", terminal.event_id, terminal, invoked)
        self._commit_terminal(terminal, build_commit)
        return AttemptOutcome("committed", terminal.event_id, terminal, invoked)

    def _validate_prepared(
        self, value: PreparedAttempt, event_id: str, ordinal: int, attempt_index: int
    ) -> None:
        if not isinstance(value, PreparedAttempt):
            raise TypeError("prepare must return PreparedAttempt")
        authorization = value.authorization
        request = value.request
        if (
            authorization.run_id != self._storage.binding.run_id
            or authorization.event_id != event_id
            or authorization.event_ordinal != ordinal
            or authorization.attempt_index != attempt_index
            or request.event_id != event_id
            or request.attempt_index != attempt_index
            or request.attempt_id != derive_attempt_id(event_id, attempt_index)
            or request.mock_seed != authorization.model_seed
        ):
            raise ValueError("prepared attempt does not bind the exact current journal identity")
        immutable = (
            value.pending_attempt.attempt_id,
            value.pending_attempt.event_id,
            value.pending_attempt.attempt_index,
            value.pending_attempt.request_id,
            value.pending_attempt.rendered_messages,
            value.pending_attempt.rendered_prompt_hash,
            value.pending_attempt.request_parameters_hash,
            value.pending_attempt.model_identity_hash,
            value.pending_attempt.model_seed,
        )
        expected = (
            request.attempt_id,
            request.event_id,
            request.attempt_index,
            request.request_id,
            request.rendered_messages,
            request.rendered_messages_hash,
            authorization.request_parameters_hash,
            authorization.model_identity_hash,
            authorization.model_seed,
        )
        if immutable != expected:
            raise ValueError("prepared pending attempt does not bind authorization and request")
        if value.pending_attempt.request_parameters != authorization.request_parameters:
            raise ValueError("prepared request parameters drifted")
        if value.pending_attempt.model_identity != authorization.model_identity:
            raise ValueError("prepared model identity drifted")
        pending_payload = value.pending_attempt.to_payload()
        in_progress_payload = value.in_progress_attempt.to_payload()
        lifecycle_fields = {
            "status",
            "started_at",
            "provider_request_id",
            "provider_metadata",
            "provider_metadata_hash",
        }
        if any(
            pending_payload[name] != in_progress_payload[name]
            for name in pending_payload
            if name not in lifecycle_fields
        ):
            raise ValueError("prepared in-progress attempt changed immutable request evidence")

    def _validate_invocation(self, value: PreparedAttempt, result: AttemptInvocationResult) -> None:
        if not isinstance(result, AttemptInvocationResult):
            raise TypeError("invoke or reconciliation must return AttemptInvocationResult")
        response = result.response
        if not _has_trusted_response_seal(response):
            raise ValueError("invocation response is not a trusted sealed adapter response")
        if (
            response.request_id != value.request.request_id
            or response.request_hash != value.request.record_hash
            or response.event_id != value.authorization.event_id
            or response.attempt_index != value.authorization.attempt_index
            or response.attempt_id != value.request.attempt_id
            or response.mock_seed != value.authorization.model_seed
            or response.model_identity != value.authorization.model_identity
            or response.model_identity_hash != value.authorization.model_identity_hash
            or result.evidence.started_at != value.in_progress_attempt.started_at
            or result.evidence.provider_metadata != _response_provider_metadata(response)
        ):
            raise ValueError("invocation evidence does not bind the prepared attempt")

    @staticmethod
    def _validate_terminal(
        value: PreparedAttempt,
        result: AttemptInvocationResult,
        terminal: GenerationAttempt,
    ) -> None:
        if not isinstance(terminal, GenerationAttempt) or terminal.status not in {
            EventStatus.FAILED,
            EventStatus.SUCCEEDED,
        }:
            raise ValueError("finalize must return a terminal GenerationAttempt")
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
            "started_at",
        )
        if any(
            getattr(terminal, name) != getattr(value.in_progress_attempt, name)
            for name in immutable_fields
        ):
            raise ValueError("terminal attempt changed immutable request or start evidence")
        evidence = result.evidence
        if (
            terminal.finished_at != evidence.finished_at
            or terminal.http_status != evidence.http_status
            or terminal.provider_metadata != evidence.provider_metadata
            or terminal.usage != evidence.usage
            or terminal.finish_reason != evidence.finish_reason
            or terminal.provider_request_id != result.response.provider_request_id
        ):
            raise ValueError("terminal attempt does not replay explicit execution evidence")
        response = result.response
        if terminal.status is EventStatus.SUCCEEDED:
            if (
                response.outcome != "response"
                or response.error is not None
                or terminal.raw_response != response.raw_response
                or terminal.raw_response_hash != response.raw_response_hash
            ):
                raise ValueError(
                    "successful terminal attempt does not bind actual response outcome and raw text"
                )
        elif response.outcome == "response":
            if (
                response.error is not None
                or terminal.raw_response != response.raw_response
                or terminal.raw_response_hash != response.raw_response_hash
            ):
                raise ValueError(
                    "failed finalize attempt must preserve actual response raw evidence"
                )
        elif (
            response.outcome != "timeout"
            or terminal.raw_response is not None
            or terminal.raw_response_hash is not None
            or terminal.error != response.error
        ):
            raise ValueError("failed terminal attempt does not preserve timeout evidence")

    @staticmethod
    def _validate_failed_terminal(value: PreparedAttempt, terminal: GenerationAttempt) -> None:
        if terminal.status is not EventStatus.FAILED:
            raise ValueError("typed lifecycle failure must carry FAILED attempt evidence")
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
            "started_at",
        )
        if any(
            getattr(terminal, name) != getattr(value.in_progress_attempt, name)
            for name in immutable_fields
        ):
            raise ValueError("failed terminal attempt changed immutable request evidence")

    def _commit_terminal(
        self,
        terminal: GenerationAttempt,
        build_commit: Callable[[GenerationAttempt], SuccessfulEventCommit],
    ) -> None:
        self._require_open()
        bundle = build_commit(terminal)
        if not isinstance(bundle, SuccessfulEventCommit):
            raise TypeError("build_commit must return SuccessfulEventCommit")
        self._storage.commit_success(
            bundle.event,
            final_attempt=terminal,
            private_update=bundle.private_update,
            private_state=bundle.private_state,
            feed_cursor=bundle.feed_cursor,
            public_post=bundle.public_post,
            latest_public_pointer=bundle.latest_public_pointer,
        )

    def _require_open(self) -> None:
        if self._lease is None:
            raise RuntimeError("lifecycle engine is not open")
        self._storage.assert_run_lease_owned()
