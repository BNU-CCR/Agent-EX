from __future__ import annotations

import json

from agent_ex.phase0b.pipeline import (
    DiagnosticEventState,
    apply_diagnostic_vllm_response,
    prepare_diagnostic_event,
    run_diagnostic_vllm_event_loop,
)
from agent_ex.phase0b.vllm_event_adapter import (
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
)
from test_phase0b_run import _authorization, _binding
from test_prompt import topic


def _response(request, *, outcome: str = "response", content: str | None = None):
    if content is None:
        content = json.dumps(
            {
                "stance": "label-5",
                "confidence": 4,
                "public_reason": "real-qwen-diagnostic-update",
            },
            separators=(",", ":"),
        )
    raw_body = json.dumps(
        {
            "id": "phase0b-provider-id",
            "model": "qwen3-8b-paper1",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    evidence = Phase0BVllmTransportEvidence.create(
        request=request,
        http_status=200 if outcome == "response" else None,
        response_headers={"x-request-id": "phase0b-provider-id"},
        provider_request_id="phase0b-provider-id",
        request_body=b"{}",
        raw_body=raw_body if outcome == "response" else b"",
        body_truncated=False,
        started_at="2026-09-20T00:00:00Z",
        ended_at="2026-09-20T00:00:01Z",
        latency_seconds=1.0,
        outcome=outcome,
        error_code=None if outcome == "response" else "timeout",
    )
    return Phase0BVllmEventResponse.create(
        request=request,
        outcome=outcome,
        error_code=None if outcome == "response" else "timeout",
        retry_after_seconds=None,
        provider_request_id="phase0b-provider-id",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        finish_reason="stop" if outcome == "response" else None,
        raw_body=raw_body if outcome == "response" else b"",
        transport_evidence=evidence,
    )


def _state() -> DiagnosticEventState:
    return DiagnosticEventState.initial(
        topic_package=topic(),
        matched_seed=20260920,
        agent_id="agent-0000",
        stance_label="label-2",
        reason="round-zero",
    )


def test_successful_vllm_response_commits_private_state_cursor_and_public_post() -> None:
    state = _state()
    prepared = prepare_diagnostic_event(
        state=state,
        authorization=_authorization(binding=_binding()),
        adapter_binding=_binding(),
        publish_flag=True,
    )

    result = apply_diagnostic_vllm_response(
        state=state,
        prepared=prepared,
        response=_response(prepared.request),
        topic_package=topic(),
    )

    assert result.committed is True
    assert result.state.private_state.stance_label == "label-5"
    assert result.state.private_state.successful_update_count == 2
    assert result.state.feed_cursor.last_scanned_event_ordinal == 0
    assert result.state.next_event_ordinal == 1
    assert len(result.state.public_posts) == 2
    assert result.evidence.parse_success is True


def test_timeout_response_records_failure_without_mutating_state_or_cursor() -> None:
    state = _state()
    prepared = prepare_diagnostic_event(
        state=state,
        authorization=_authorization(binding=_binding()),
        adapter_binding=_binding(),
        publish_flag=True,
    )

    result = apply_diagnostic_vllm_response(
        state=state,
        prepared=prepared,
        response=_response(prepared.request, outcome="timeout"),
        topic_package=topic(),
    )

    assert result.committed is False
    assert result.state == state
    assert result.evidence.parse_success is False
    assert result.evidence.error_code == "timeout"


def test_malformed_vllm_content_records_failure_without_mutating_state() -> None:
    state = _state()
    prepared = prepare_diagnostic_event(
        state=state,
        authorization=_authorization(binding=_binding()),
        adapter_binding=_binding(),
        publish_flag=True,
    )

    result = apply_diagnostic_vllm_response(
        state=state,
        prepared=prepared,
        response=_response(prepared.request, content="not-json"),
        topic_package=topic(),
    )

    assert result.committed is False
    assert result.state == state
    assert result.evidence.error_code == "json"


def test_event_loop_stops_on_first_failed_response_and_keeps_prefix_state() -> None:
    state = _state()
    binding = _binding()
    authorization = _authorization(binding=binding)

    def generate(request):
        if request.event_id.endswith("0001"):
            return _response(request, content="not-json")
        return _response(
            request,
            content=json.dumps(
                {
                    "stance": "label-3",
                    "confidence": 3,
                    "public_reason": "first-prefix-update",
                },
                separators=(",", ":"),
            ),
        )

    result = run_diagnostic_vllm_event_loop(
        state=state,
        authorization=authorization,
        adapter_binding=binding,
        publish_flags=(True, True, True),
        generate=generate,
        topic_package=topic(),
    )

    assert result.committed_count == 1
    assert result.state.next_event_ordinal == 1
    assert result.state.private_state.reason == "first-prefix-update"
    assert len(result.step_results) == 2
    assert result.step_results[-1].committed is False
