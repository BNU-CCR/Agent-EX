"""Pure SIS event boundary using shared transport/parser/state contracts.

No function dispatches, retries, writes SQLite, advances a feed cursor or
claims a commit. Results are prospective until the serial storage transaction.
"""

from dataclasses import dataclass
import json
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import (
    _json_ready,
    _require_id,
    _require_int,
    _require_sha256,
    canonical_payload_hash,
    derive_event_id,
)
from ..execution_evidence import DiagnosticParseEvidence
from ..parser import (
    ParserLimits,
    _object_without_duplicates,
    _reject_constant,
    _validate_tree,
)
from ..phase0b.vllm_event_adapter import Phase0BVllmEventRequest, Phase0BVllmEventResponse
from ..state import PrivateState, PrivateUpdate, PublicPost
from ..topic import TopicPackage
from .contracts import STUDY_ID, study_cells
from .prompts import RENDERER_VERSION, StudyPrompt, validate_study_prompt_projection


@dataclass(frozen=True, slots=True)
class PreparedStudyEvent:
    run_id: str
    event_ordinal: int
    previous_event_hash: str
    publish_flag: bool
    prompt: StudyPrompt
    private_state: PrivateState
    topic_package: TopicPackage
    parser_limits: ParserLimits
    request: Phase0BVllmEventRequest

    def __post_init__(self):
        _require_id("run_id", self.run_id)
        _require_int("event_ordinal", self.event_ordinal)
        _require_sha256("previous_event_hash", self.previous_event_hash)
        if type(self.publish_flag) is not bool:
            raise TypeError("publish_flag must be a boolean")
        for value, expected in (
            (self.prompt, StudyPrompt),
            (self.private_state, PrivateState),
            (self.topic_package, TopicPackage),
            (self.parser_limits, ParserLimits),
            (self.request, Phase0BVllmEventRequest),
        ):
            if not isinstance(value, expected):
                raise TypeError("typed preparation inputs are required")
        if self.request.event_id != derive_event_id(self.run_id, self.event_ordinal):
            raise ValueError("request event identity does not bind run/ordinal")
        if (
            self.private_state.event_ordinal is not None
            and self.private_state.event_ordinal >= self.event_ordinal
        ):
            raise ValueError("event ordinal must advance the receiver state")
        evidence = self.prompt.evidence
        if evidence["renderer_version"] != RENDERER_VERSION:
            raise ValueError("unbound or unsupported prompt renderer")
        if evidence["cell_id"] not in {c.cell_id for c in study_cells()}:
            raise ValueError("unknown SIS cell")
        if self.private_state.agent_id != evidence["receiver_id"]:
            raise ValueError("prompt receiver does not bind private state")
        if evidence["pre_state"] != {
            "stance": self.private_state.stance_label,
            "reason": self.private_state.reason,
        }:
            raise ValueError("prompt pre-state does not bind receiver state")
        if (
            evidence["topic_package_hash"] != self.topic_package.package_hash
            or self.private_state.topic_package_hash != self.topic_package.package_hash
            or evidence["topic_package_id"] != self.topic_package.topic_id
            or self.private_state.topic_package_id != self.topic_package.topic_id
        ):
            raise ValueError("preparation topic identities differ")
        if (
            self.request.prompt_hash != self.prompt.prompt_hash
            or self.request.rendered_messages != self.prompt.messages
            or evidence["exact_messages_shown"] != self.prompt.messages
        ):
            raise ValueError("request and input evidence do not bind exact messages")
        validate_study_prompt_projection(self.prompt, self.topic_package)

    def content_payload(self):
        return _json_ready(
            {
                "schema_version": "paper1.identity-network.prepared-event.v1",
                "study_id": STUDY_ID,
                "run_id": self.run_id,
                "event_ordinal": self.event_ordinal,
                "previous_event_hash": self.previous_event_hash,
                "publish_flag": self.publish_flag,
                "input_evidence": self.prompt.evidence,
                "input_evidence_hash": self.prompt.evidence_hash,
                "pre_state": self.private_state.to_payload(),
                "topic_package_hash": self.topic_package.package_hash,
                "parser_limits": self.parser_limits.to_payload(),
                "request": self.request.to_payload(),
                "metadata": {
                    "status": "preliminary",
                    "research_parameter_status": "not_frozen",
                    "formal_parameter_authority": False,
                    "committed": False,
                },
            }
        )

    @property
    def record_hash(self):
        return canonical_payload_hash(self.content_payload())


def prepare_study_event(
    *,
    run_id: str,
    event_ordinal: int,
    attempt_index: int,
    previous_event_hash: str,
    publish_flag: bool,
    prompt: StudyPrompt,
    private_state: PrivateState,
    topic_package: TopicPackage,
    parser_limits: ParserLimits,
    model_seed: int,
    generation_settings: Mapping[str, object],
    adapter_binding_hash: str,
) -> PreparedStudyEvent:
    if not isinstance(prompt, StudyPrompt):
        raise TypeError("a typed study prompt is required")
    request = Phase0BVllmEventRequest.create(
        event_id=derive_event_id(run_id, event_ordinal),
        attempt_index=attempt_index,
        prompt_hash=prompt.prompt_hash,
        rendered_messages=tuple(dict(m) for m in prompt.messages),
        generation_settings=dict(generation_settings),
        model_seed=model_seed,
        adapter_binding_hash=adapter_binding_hash,
    )
    return PreparedStudyEvent(
        run_id,
        event_ordinal,
        previous_event_hash,
        publish_flag,
        prompt,
        private_state,
        topic_package,
        parser_limits,
        request,
    )


@dataclass(frozen=True, slots=True)
class StudyEventResult:
    parse: DiagnosticParseEvidence
    private_state: PrivateState
    private_update: PrivateUpdate | None
    public_post: PublicPost | None
    trace: ArtifactEnvelope


def _parse_bounded_response(prepared, response):
    if response.outcome == "response":
        try:
            limits = prepared.parser_limits
            if len(response.raw_body) > limits.max_raw_bytes:
                raise ValueError("raw_byte_limit")
            body = json.loads(
                response.raw_body,
                object_pairs_hook=_object_without_duplicates,
                parse_constant=_reject_constant,
            )
            content = body["choices"][0]["message"]["content"]
            if type(content) is not str:
                raise ValueError("provider_schema")
            if len(content) > limits.max_raw_chars:
                raise ValueError("raw_character_limit")
            payload = json.loads(
                content,
                object_pairs_hook=_object_without_duplicates,
                parse_constant=_reject_constant,
            )
            _validate_tree(payload, limits.max_json_depth)
            if isinstance(payload, dict) and isinstance(payload.get("public_reason"), str):
                if len(payload["public_reason"]) > limits.max_reason_chars:
                    raise ValueError("reason_limit")
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, RecursionError):
            values = {
                "evidence_id": "diagnostic-parse-evidence-"
                + canonical_payload_hash({"attempt_id": response.attempt_id}),
                "event_id": response.event_id,
                "attempt_id": response.attempt_id,
                "attempt_index": response.attempt_index,
                "request_id": response.request_id,
                "request_hash": response.request_hash,
                "response_hash": response.record_hash,
                "raw_body_sha256": response.raw_body_sha256,
                "parser_limits_hash": prepared.parser_limits.record_hash,
                "topic_package_id": prepared.topic_package.topic_id,
                "topic_package_hash": prepared.topic_package.package_hash,
                "success": False,
                "parsed_response": None,
                "error_code": "bounded_parse",
            }
            content = {"schema_version": "paper1.phase0b.diagnostic-parse-evidence.v1", **values}
            return DiagnosticParseEvidence(**values, record_hash=canonical_payload_hash(content))
    return DiagnosticParseEvidence.create(
        response=response,
        topic_package=prepared.topic_package,
        parser_limits_hash=prepared.parser_limits.record_hash,
    )


def finalize_study_response(
    *,
    prepared: PreparedStudyEvent,
    response: Phase0BVllmEventResponse,
) -> StudyEventResult:
    if not isinstance(prepared, PreparedStudyEvent) or not isinstance(
        response, Phase0BVllmEventResponse
    ):
        raise TypeError("typed preparation and shared vLLM response are required")
    request = prepared.request
    transport = response.transport_evidence
    if (
        response.request_id != request.request_id
        or response.request_hash != request.record_hash
        or response.event_id != request.event_id
        or response.attempt_id != request.attempt_id
        or transport.request_id != request.request_id
        or transport.request_hash != request.record_hash
        or transport.raw_body_sha256 != response.raw_body_sha256
        or transport.outcome != response.outcome
        or transport.error_code != response.error_code
    ):
        raise ValueError("response and transport do not bind the prepared request")
    try:
        wire = json.loads(
            transport.request_body,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
        expected_wire = {
            "messages": request.rendered_messages,
            **dict(request.generation_settings),
            "seed": request.model_seed,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if not isinstance(wire, dict) or set(wire) != set(expected_wire) | {"model"}:
            raise ValueError("unexpected wire fields")
        if not isinstance(wire["model"], str) or not wire["model"].strip():
            raise ValueError("wire model identity is absent")
        without_model = {k: v for k, v in wire.items() if k != "model"}
        if canonical_payload_hash(without_model) != canonical_payload_hash(expected_wire):
            raise ValueError("wire message/settings drift")
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "transport wire body does not bind exact request messages/settings"
        ) from exc
    parsed = _parse_bounded_response(prepared, response)
    state, update, post = prepared.private_state, None, None
    if parsed.success:
        payload = parsed.parsed_response
        update = PrivateUpdate.create(
            topic_package=prepared.topic_package,
            matched_seed=state.matched_seed,
            agent_id=state.agent_id,
            event_id=request.event_id,
            event_ordinal=prepared.event_ordinal,
            sequence_index=state.successful_update_count,
            stance_label=payload["stance"],
            reason=payload["public_reason"],
            confidence=payload["confidence"],
            published=prepared.publish_flag,
            source_attempt_id=request.attempt_id,
            mock_only=True,
        )
        state = PrivateState.from_update(update, previous=state, mock_only=True)
        if prepared.publish_flag:
            post = PublicPost.from_private_update(update, mock_only=True)
    trace = ArtifactEnvelope.create(
        artifact_type="identity_network_prospective_event_trace",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.shared_event_boundary",
        algorithm_version="1.0.0",
        input_hashes={"preparation": prepared.record_hash, "response": response.record_hash},
        rng_provenance=(),
        payload={
            "schema_version": "paper1.identity-network.prospective-event-trace.v1",
            "study_id": STUDY_ID,
            "cell_id": prepared.prompt.evidence["cell_id"],
            "run_id": prepared.run_id,
            "event_id": request.event_id,
            "event_ordinal": prepared.event_ordinal,
            "attempt_id": request.attempt_id,
            "previous_event_hash": prepared.previous_event_hash,
            "input_evidence": prepared.prompt.evidence,
            "pre_state": prepared.private_state.to_payload(),
            "publish_flag": prepared.publish_flag,
            "proposed_post_state": state.to_payload() if parsed.success else None,
            "proposed_private_update": update.to_payload() if update else None,
            "proposed_public_output": post.to_payload() if post else None,
            "request_hash": request.record_hash,
            "response_hash": response.record_hash,
            "transport_hash": transport.record_hash,
            "raw_body_sha256": response.raw_body_sha256,
            "parse_evidence": parsed.to_payload(),
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
                "committed": False,
            },
        },
    )
    return StudyEventResult(parsed, state, update, post, trace)
