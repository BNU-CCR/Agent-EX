"""Preliminary Phase 0B bridge from real vLLM responses to event state.

This is not the formal SQLite v6 runner.  It is a small, explicit diagnostic
bridge used to prove that a real vLLM event response can be parsed and committed
without treating that response as a scripted mock adapter output.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

from ..domain import canonical_payload_hash
from ..feed import FeedCursor
from ..parser import ParsedAgentUpdate
from ..state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from ..topic import TopicPackage
from .contracts import DiagnosticAdapterBinding, DiagnosticRunAuthorization
from .vllm_event_adapter import Phase0BVllmEventRequest, Phase0BVllmEventResponse


@dataclass(frozen=True, slots=True)
class DiagnosticEventState:
    """In-memory preliminary state for a single Phase 0B diagnostic event chain."""

    topic_package_id: str
    topic_package_hash: str
    matched_seed: int
    agent_id: str
    private_updates: tuple[PrivateUpdate, ...]
    private_state: PrivateState
    feed_cursor: FeedCursor
    public_posts: tuple[PublicPost, ...]
    latest_public_pointer: LatestPublicPointer | None
    next_event_ordinal: int
    record_hash: str

    def __post_init__(self) -> None:
        if not self.private_updates:
            raise ValueError("diagnostic state requires an initial private update")
        if self.private_updates[-1].record_hash != self.private_state.latest_update_hash:
            raise ValueError("private state must point to the last private update")
        if self.feed_cursor.receiver_agent_id != self.agent_id:
            raise ValueError("feed cursor receiver must match diagnostic agent")
        if self.next_event_ordinal < 0 or self.next_event_ordinal > 480:
            raise ValueError("diagnostic next_event_ordinal must remain within 0..480")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("diagnostic event state hash drift")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": "paper1.phase0b.diagnostic-event-state.v1",
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "agent_id": self.agent_id,
            "private_update_hashes": tuple(item.record_hash for item in self.private_updates),
            "private_state_hash": self.private_state.record_hash,
            "feed_cursor_hash": self.feed_cursor.record_hash,
            "public_post_hashes": tuple(item.record_hash for item in self.public_posts),
            "latest_public_pointer_hash": None
            if self.latest_public_pointer is None
            else self.latest_public_pointer.record_hash,
            "next_event_ordinal": self.next_event_ordinal,
        }

    @classmethod
    def initial(
        cls,
        *,
        topic_package: TopicPackage,
        matched_seed: int,
        agent_id: str,
        stance_label: str,
        reason: str,
    ) -> DiagnosticEventState:
        if not isinstance(topic_package, TopicPackage):
            raise TypeError("topic_package must be a TopicPackage")
        update = PrivateUpdate.create(
            topic_package=topic_package,
            matched_seed=matched_seed,
            agent_id=agent_id,
            event_id=None,
            event_ordinal=None,
            sequence_index=0,
            stance_label=stance_label,
            reason=reason,
            confidence=None,
            published=True,
            source_attempt_id=None,
            mock_only=True,
        )
        state = PrivateState.from_update(update, previous=None, mock_only=True)
        post = PublicPost.from_private_update(update, mock_only=True)
        pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
        cursor = FeedCursor.initial(
            matched_seed=matched_seed,
            receiver_agent_id=agent_id,
            exposure_mode="self_history_only",
            exposure_graph_hash=None,
            mock_only=True,
        )
        content = {
            "schema_version": "paper1.phase0b.diagnostic-event-state.v1",
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "topic_package_id": topic_package.topic_id,
            "topic_package_hash": topic_package.package_hash,
            "matched_seed": matched_seed,
            "agent_id": agent_id,
            "private_update_hashes": (update.record_hash,),
            "private_state_hash": state.record_hash,
            "feed_cursor_hash": cursor.record_hash,
            "public_post_hashes": (post.record_hash,),
            "latest_public_pointer_hash": pointer.record_hash,
            "next_event_ordinal": 0,
        }
        return cls(
            topic_package_id=topic_package.topic_id,
            topic_package_hash=topic_package.package_hash,
            matched_seed=matched_seed,
            agent_id=agent_id,
            private_updates=(update,),
            private_state=state,
            feed_cursor=cursor,
            public_posts=(post,),
            latest_public_pointer=pointer,
            next_event_ordinal=0,
            record_hash=canonical_payload_hash(content),
        )


@dataclass(frozen=True, slots=True)
class DiagnosticPreparedEvent:
    """One prepared real-vLLM diagnostic event request."""

    event_id: str
    event_ordinal: int
    agent_id: str
    publish_flag: bool
    state_before_hash: str
    feed_cursor_before_hash: str
    request: Phase0BVllmEventRequest
    record_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, Phase0BVllmEventRequest):
            raise TypeError("prepared event request must be a Phase0BVllmEventRequest")
        if self.request.event_id != self.event_id:
            raise ValueError("prepared event request id drift")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("prepared event hash drift")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": "paper1.phase0b.diagnostic-prepared-event.v1",
            "event_id": self.event_id,
            "event_ordinal": self.event_ordinal,
            "agent_id": self.agent_id,
            "publish_flag": self.publish_flag,
            "state_before_hash": self.state_before_hash,
            "feed_cursor_before_hash": self.feed_cursor_before_hash,
            "request_hash": self.request.record_hash,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticPipelineEvidence:
    """Sanitized preliminary evidence for one parse/commit decision."""

    prepared_hash: str
    response_hash: str
    transport_outcome: str
    parse_success: bool
    parsed_response_hash: str | None
    error_code: str | None
    committed_state_hash: str | None
    record_hash: str

    def __post_init__(self) -> None:
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("diagnostic pipeline evidence hash drift")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": "paper1.phase0b.diagnostic-pipeline-evidence.v1",
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "prepared_hash": self.prepared_hash,
            "response_hash": self.response_hash,
            "transport_outcome": self.transport_outcome,
            "parse_success": self.parse_success,
            "parsed_response_hash": self.parsed_response_hash,
            "error_code": self.error_code,
            "committed_state_hash": self.committed_state_hash,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticPipelineResult:
    """Result of applying one vLLM response to preliminary diagnostic state."""

    committed: bool
    state: DiagnosticEventState
    evidence: DiagnosticPipelineEvidence


@dataclass(frozen=True, slots=True)
class DiagnosticEventLoopResult:
    """Prefix-preserving result for a preliminary diagnostic event loop."""

    state: DiagnosticEventState
    step_results: tuple[DiagnosticPipelineResult, ...]
    committed_count: int
    record_hash: str

    def __post_init__(self) -> None:
        if self.committed_count != sum(1 for result in self.step_results if result.committed):
            raise ValueError("committed_count must match committed step results")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("diagnostic event loop result hash drift")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": "paper1.phase0b.diagnostic-event-loop-result.v1",
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "state_hash": self.state.record_hash,
            "step_evidence_hashes": tuple(
                result.evidence.record_hash for result in self.step_results
            ),
            "committed_count": self.committed_count,
        }


def prepare_diagnostic_event(
    *,
    state: DiagnosticEventState,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    publish_flag: bool,
) -> DiagnosticPreparedEvent:
    """Build a real-vLLM request from the current preliminary state."""

    if not isinstance(state, DiagnosticEventState):
        raise TypeError("state must be DiagnosticEventState")
    if not isinstance(authorization, DiagnosticRunAuthorization):
        raise TypeError("authorization must be DiagnosticRunAuthorization")
    if not isinstance(adapter_binding, DiagnosticAdapterBinding):
        raise TypeError("adapter_binding must be DiagnosticAdapterBinding")
    if authorization.adapter_binding_hash != adapter_binding.record_hash:
        raise ValueError("authorization adapter binding hash drift")
    if state.next_event_ordinal >= authorization.expected_event_count:
        raise ValueError("diagnostic state already reached the authorized event count")
    if type(publish_flag) is not bool:
        raise TypeError("publish_flag must be a boolean")

    event_ordinal = state.next_event_ordinal
    event_id = f"phase0b-event-{state.agent_id}-{event_ordinal:04d}"
    messages = (
        {"role": "system", "content": "Return strict JSON: stance, confidence, public_reason."},
        {
            "role": "user",
            "content": (
                f"Agent {state.agent_id}; prior stance {state.private_state.stance_label}; "
                f"prior reason {state.private_state.reason}"
            ),
        },
    )
    prompt_hash = canonical_payload_hash(
        {
            "state_before_hash": state.record_hash,
            "event_ordinal": event_ordinal,
            "publish_flag": publish_flag,
            "topic_package_hash": state.topic_package_hash,
        }
    )
    seed_hash = canonical_payload_hash(
        {
            "matched_seed": authorization.matched_seed,
            "agent_id": state.agent_id,
            "event_id": event_id,
            "rule": authorization.model_seed_pairing_rule,
        }
    )
    request = Phase0BVllmEventRequest.create(
        event_id=event_id,
        attempt_index=1,
        prompt_hash=prompt_hash,
        rendered_messages=messages,
        generation_settings={
            "temperature": authorization.temperature,
            "top_p": authorization.top_p,
            "max_tokens": authorization.max_tokens,
        },
        model_seed=int(seed_hash[:15], 16),
        adapter_binding_hash=adapter_binding.record_hash,
    )
    content = {
        "schema_version": "paper1.phase0b.diagnostic-prepared-event.v1",
        "event_id": event_id,
        "event_ordinal": event_ordinal,
        "agent_id": state.agent_id,
        "publish_flag": publish_flag,
        "state_before_hash": state.record_hash,
        "feed_cursor_before_hash": state.feed_cursor.record_hash,
        "request_hash": request.record_hash,
    }
    return DiagnosticPreparedEvent(
        event_id=event_id,
        event_ordinal=event_ordinal,
        agent_id=state.agent_id,
        publish_flag=publish_flag,
        state_before_hash=state.record_hash,
        feed_cursor_before_hash=state.feed_cursor.record_hash,
        request=request,
        record_hash=canonical_payload_hash(content),
    )


def apply_diagnostic_vllm_response(
    *,
    state: DiagnosticEventState,
    prepared: DiagnosticPreparedEvent,
    response: Phase0BVllmEventResponse,
    topic_package: TopicPackage,
) -> DiagnosticPipelineResult:
    """Parse and atomically apply one real-vLLM diagnostic response."""

    if not isinstance(state, DiagnosticEventState):
        raise TypeError("state must be DiagnosticEventState")
    if not isinstance(prepared, DiagnosticPreparedEvent):
        raise TypeError("prepared must be DiagnosticPreparedEvent")
    if not isinstance(response, Phase0BVllmEventResponse):
        raise TypeError("response must be Phase0BVllmEventResponse")
    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be TopicPackage")
    if prepared.state_before_hash != state.record_hash:
        raise ValueError("prepared event does not bind the supplied state")
    if response.request_id != prepared.request.request_id or response.request_hash != (
        prepared.request.record_hash
    ):
        raise ValueError("vLLM response does not bind the prepared request")
    if response.outcome != "response":
        return _failed_result(state, prepared, response, response.error_code or response.outcome)

    parsed, error_code = _parse_vllm_message_content(response, topic_package)
    if parsed is None:
        return _failed_result(state, prepared, response, error_code)

    update = PrivateUpdate.create(
        topic_package=topic_package,
        matched_seed=state.matched_seed,
        agent_id=state.agent_id,
        event_id=prepared.event_id,
        event_ordinal=prepared.event_ordinal,
        sequence_index=state.private_state.successful_update_count,
        stance_label=parsed.stance,
        reason=parsed.public_reason,
        confidence=parsed.confidence,
        published=prepared.publish_flag,
        source_attempt_id=prepared.request.attempt_id,
        mock_only=True,
    )
    private_state = PrivateState.from_update(update, previous=state.private_state, mock_only=True)
    feed_cursor = state.feed_cursor.advance(prepared.event_ordinal)
    public_posts = state.public_posts
    latest_pointer = state.latest_public_pointer
    if prepared.publish_flag:
        post = PublicPost.from_private_update(update, mock_only=True)
        latest_pointer = LatestPublicPointer.from_post(
            post, previous=latest_pointer, mock_only=True
        )
        public_posts = (*public_posts, post)
    next_state = _state_from_parts(
        topic_package_id=state.topic_package_id,
        topic_package_hash=state.topic_package_hash,
        matched_seed=state.matched_seed,
        agent_id=state.agent_id,
        private_updates=(*state.private_updates, update),
        private_state=private_state,
        feed_cursor=feed_cursor,
        public_posts=public_posts,
        latest_public_pointer=latest_pointer,
        next_event_ordinal=state.next_event_ordinal + 1,
    )
    evidence = _evidence(
        prepared=prepared,
        response=response,
        parse_success=True,
        parsed_response_hash=canonical_payload_hash(parsed.to_payload()),
        error_code=None,
        committed_state_hash=next_state.record_hash,
    )
    return DiagnosticPipelineResult(committed=True, state=next_state, evidence=evidence)


def run_diagnostic_vllm_event_loop(
    *,
    state: DiagnosticEventState,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    publish_flags: tuple[bool, ...],
    generate: Callable[[Phase0BVllmEventRequest], Phase0BVllmEventResponse],
    topic_package: TopicPackage,
) -> DiagnosticEventLoopResult:
    """Run a strict prefix loop, stopping at the first uncommitted event."""

    if type(publish_flags) is not tuple or not publish_flags:
        raise ValueError("publish_flags must be a non-empty tuple")
    if not callable(generate):
        raise TypeError("generate must be callable")
    current = state
    results: list[DiagnosticPipelineResult] = []
    for publish_flag in publish_flags:
        prepared = prepare_diagnostic_event(
            state=current,
            authorization=authorization,
            adapter_binding=adapter_binding,
            publish_flag=publish_flag,
        )
        response = generate(prepared.request)
        result = apply_diagnostic_vllm_response(
            state=current,
            prepared=prepared,
            response=response,
            topic_package=topic_package,
        )
        results.append(result)
        if not result.committed:
            break
        current = result.state
    content = {
        "schema_version": "paper1.phase0b.diagnostic-event-loop-result.v1",
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "state_hash": current.record_hash,
        "step_evidence_hashes": tuple(result.evidence.record_hash for result in results),
        "committed_count": sum(1 for result in results if result.committed),
    }
    return DiagnosticEventLoopResult(
        state=current,
        step_results=tuple(results),
        committed_count=content["committed_count"],  # type: ignore[arg-type]
        record_hash=canonical_payload_hash(content),
    )


def _parse_vllm_message_content(
    response: Phase0BVllmEventResponse, topic_package: TopicPackage
) -> tuple[ParsedAgentUpdate | None, str | None]:
    try:
        body = json.loads(response.raw_body)
        choices = body["choices"]
        message = choices[0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None, "provider_schema"
    if type(content) is not str:
        return None, "provider_schema"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None, "json"
    if type(payload) is not dict or tuple(payload) != ("stance", "confidence", "public_reason"):
        return None, "fields"
    try:
        parsed = ParsedAgentUpdate.from_payload(
            {
                "topic_package_id": topic_package.topic_id,
                "topic_package_hash": topic_package.package_hash,
                **payload,
            }
        )
    except (TypeError, ValueError):
        return None, "parsed_contract"
    return parsed, None


def _failed_result(
    state: DiagnosticEventState,
    prepared: DiagnosticPreparedEvent,
    response: Phase0BVllmEventResponse,
    error_code: str | None,
) -> DiagnosticPipelineResult:
    return DiagnosticPipelineResult(
        committed=False,
        state=state,
        evidence=_evidence(
            prepared=prepared,
            response=response,
            parse_success=False,
            parsed_response_hash=None,
            error_code=error_code or "unknown",
            committed_state_hash=None,
        ),
    )


def _evidence(
    *,
    prepared: DiagnosticPreparedEvent,
    response: Phase0BVllmEventResponse,
    parse_success: bool,
    parsed_response_hash: str | None,
    error_code: str | None,
    committed_state_hash: str | None,
) -> DiagnosticPipelineEvidence:
    content = {
        "schema_version": "paper1.phase0b.diagnostic-pipeline-evidence.v1",
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "prepared_hash": prepared.record_hash,
        "response_hash": response.record_hash,
        "transport_outcome": response.outcome,
        "parse_success": parse_success,
        "parsed_response_hash": parsed_response_hash,
        "error_code": error_code,
        "committed_state_hash": committed_state_hash,
    }
    return DiagnosticPipelineEvidence(
        prepared_hash=prepared.record_hash,
        response_hash=response.record_hash,
        transport_outcome=response.outcome,
        parse_success=parse_success,
        parsed_response_hash=parsed_response_hash,
        error_code=error_code,
        committed_state_hash=committed_state_hash,
        record_hash=canonical_payload_hash(content),
    )


def _state_from_parts(
    *,
    topic_package_id: str,
    topic_package_hash: str,
    matched_seed: int,
    agent_id: str,
    private_updates: tuple[PrivateUpdate, ...],
    private_state: PrivateState,
    feed_cursor: FeedCursor,
    public_posts: tuple[PublicPost, ...],
    latest_public_pointer: LatestPublicPointer | None,
    next_event_ordinal: int,
) -> DiagnosticEventState:
    content = {
        "schema_version": "paper1.phase0b.diagnostic-event-state.v1",
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "topic_package_id": topic_package_id,
        "topic_package_hash": topic_package_hash,
        "matched_seed": matched_seed,
        "agent_id": agent_id,
        "private_update_hashes": tuple(item.record_hash for item in private_updates),
        "private_state_hash": private_state.record_hash,
        "feed_cursor_hash": feed_cursor.record_hash,
        "public_post_hashes": tuple(item.record_hash for item in public_posts),
        "latest_public_pointer_hash": None
        if latest_public_pointer is None
        else latest_public_pointer.record_hash,
        "next_event_ordinal": next_event_ordinal,
    }
    return DiagnosticEventState(
        topic_package_id=topic_package_id,
        topic_package_hash=topic_package_hash,
        matched_seed=matched_seed,
        agent_id=agent_id,
        private_updates=private_updates,
        private_state=private_state,
        feed_cursor=feed_cursor,
        public_posts=public_posts,
        latest_public_pointer=latest_public_pointer,
        next_event_ordinal=next_event_ordinal,
        record_hash=canonical_payload_hash(content),
    )
