"""Strict independent-trial transport binding and pure bounded parse replay."""

from dataclasses import dataclass, fields

from ..domain import _json_ready
from ..execution_evidence import DiagnosticPersistedInvocationEvidence
from ..parser import ParserLimits
from ..phase0b.vllm_event_adapter import (
    Phase0BVllmEventAdapter,
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
)
from ..topic import TopicPackage
from .execution import _parse_bounded_response


@dataclass(frozen=True, slots=True)
class CheckParseContext:
    parser_limits: ParserLimits
    topic_package: TopicPackage


def response_payload(response):
    if not isinstance(response, Phase0BVllmEventResponse):
        raise TypeError("typed manipulation response required")
    return DiagnosticPersistedInvocationEvidence._response_payload(response)


def reconstruct_response(payload):
    if type(payload) is not dict or set(payload) != {
        f.name for f in fields(Phase0BVllmEventResponse)
    }:
        raise ValueError("response payload fields differ")
    values = dict(payload)
    values["transport_evidence"] = Phase0BVllmTransportEvidence.from_payload(
        values["transport_evidence"]
    )
    return Phase0BVllmEventResponse(**values)


def bind_response(payload, *, request, wire, adapter_binding):
    response = reconstruct_response(payload)
    transport = response.transport_evidence
    for name, expected in (
        ("request_id", request.request_id),
        ("request_hash", request.record_hash),
        ("event_id", request.event_id),
        ("attempt_id", request.attempt_id),
        ("attempt_index", request.attempt_index),
    ):
        if getattr(response, name) != expected:
            raise ValueError("response request/attempt binding differs")
    if (
        transport.request_id != request.request_id
        or transport.request_hash != request.record_hash
        or transport.request_body != wire
        or transport.endpoint != adapter_binding["endpoint"]
        or transport.raw_body != response.raw_body
        or transport.outcome != response.outcome
        or transport.error_code != response.error_code
        or transport.provider_request_id != response.provider_request_id
    ):
        raise ValueError("response transport/wire binding differs")
    adapter = Phase0BVllmEventAdapter(
        adapter_binding["endpoint"], served_model_name=adapter_binding["served_model_name"]
    )
    if transport.http_status is not None or transport.raw_body:
        if transport.provider_request_id != transport.response_headers.get("x-request-id"):
            raise ValueError("provider identity differs from saved HTTP header")
        expected = adapter._classify(
            status=transport.http_status,
            headers=transport.response_headers,
            raw_body=transport.raw_body,
            truncated=transport.body_truncated,
            provider_request_id=transport.provider_request_id,
        )
    else:
        if (
            transport.body_truncated
            or transport.response_headers
            or transport.provider_request_id is not None
            or (response.outcome, response.error_code)
            not in {("timeout", "timeout"), ("provider_error", "provider_unreachable")}
        ):
            raise ValueError("unreachable/timeout evidence contract differs")
        expected = (
            response.outcome,
            response.error_code,
            None,
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            None,
        )
    actual = (
        response.outcome,
        response.error_code,
        response.retry_after_seconds,
        dict(response.usage),
        response.finish_reason,
    )
    if actual != expected:
        raise ValueError("provider classification differs from raw evidence")
    return response


def terminal_evidence(plan, response):
    context = CheckParseContext(
        ParserLimits.from_payload(_json_ready(plan.payload["parser_limits"])),
        TopicPackage.from_payload(_json_ready(plan.payload["topic_package"])),
    )
    parsed = _parse_bounded_response(context, response)
    return ("VALID" if parsed.success else "INVALID"), parsed.to_payload()
