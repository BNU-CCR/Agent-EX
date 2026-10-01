import json
from dataclasses import replace

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.groups import GroupContext, build_group_assignment
from agent_ex.identity_network.prompts import ShownPost, render_study_prompt
from agent_ex.identity_network.prompts import StudyPrompt
from agent_ex.identity_network.execution import prepare_study_event, finalize_study_response
from agent_ex.parser import ParserLimits
from agent_ex.phase0b.vllm_event_adapter import (
    PHASE0B_VLLM_ENDPOINT,
    Phase0BVllmEventAdapter,
    Phase0BDispatchJournal,
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
    Phase0BVllmEventRequest,
)
from agent_ex.state import PrivateUpdate, PrivateState
from test_prompt import topic
from test_phase0b_vllm_event_adapter import FakeConnection


def prepared(cell, publish_flag=False, attempt_index=1):
    t = topic()
    groups = GroupContext.from_artifact(
        build_group_assignment(
            initial_stances={"receiver": "label-2", "source": "label-2"},
            matched_seed=3,
        )
    )
    prompt = render_study_prompt(
        cell=cell,
        groups=groups,
        receiver_id="receiver",
        persona_text="Adult participant.",
        topic_package=t,
        pre_state={"stance": "label-2", "reason": "Prior."},
        self_history=(),
        posts=()
        if cell.network == "no_social"
        else (ShownPost("p1", "source", "member-1", "label-5", "Public evidence."),),
    )
    initial = PrivateUpdate.create(
        topic_package=t,
        matched_seed=3,
        agent_id="receiver",
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label="label-2",
        reason="Prior.",
        confidence=None,
        published=True,
        source_attempt_id=None,
        mock_only=True,
    )
    state = PrivateState.from_update(initial, previous=None, mock_only=True)
    limits = ParserLimits.create(
        max_raw_chars=4096,
        max_raw_bytes=8192,
        max_json_depth=8,
        max_reason_chars=1024,
        mock_only=True,
    )
    return prepare_study_event(
        run_id=f"sis-test-{cell.cell_id}",
        event_ordinal=0,
        attempt_index=attempt_index,
        previous_event_hash="a" * 64,
        publish_flag=publish_flag,
        prompt=prompt,
        private_state=state,
        topic_package=t,
        parser_limits=limits,
        model_seed=17,
        generation_settings={"temperature": 0.0, "top_p": 1.0, "max_tokens": 128},
        adapter_binding_hash="b" * 64,
    )


def response_for(p, tmp_path, content=None, status=200):
    if content is None:
        content = '{"stance":"label-5","confidence":4,"public_reason":"New evidence."}'
    FakeConnection.requests = []
    FakeConnection.status = status
    FakeConnection.body = json.dumps(
        {
            "id": "provider-1",
            "model": "qwen3-8b-paper1",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
    ).encode()
    adapter = Phase0BVllmEventAdapter(
        PHASE0B_VLLM_ENDPOINT,
        served_model_name="qwen3-8b-paper1",
        connection_factory=FakeConnection,
    )
    journal = Phase0BDispatchJournal(tmp_path / "dispatch.jsonl")
    adapter.bind_dispatch_journal(journal.record_before_dispatch)
    response = adapter.generate(p.request, timeout_seconds=3.0)
    journal.record_resolution(response)
    journal.assert_no_unresolved_dispatches()
    return response


@pytest.mark.parametrize("cell", study_cells())
def test_all_six_cells_bridge_shared_transport_and_state(cell, tmp_path):
    p = prepared(cell, publish_flag=True)
    response = response_for(p, tmp_path)
    result = finalize_study_response(prepared=p, response=response)
    assert result.parse.success
    assert result.private_state.stance_label == "label-5"
    assert result.private_state.confidence == 4
    assert result.public_post.stance_label == "label-5"
    assert result.trace.payload["metadata"]["committed"] is False
    assert result.trace.payload["previous_event_hash"] == "a" * 64
    assert (
        result.trace.payload["input_evidence"]["source_groups"]
        == p.prompt.evidence["source_groups"]
    )
    assert result.trace.output_hash == canonical_payload_hash(result.trace.payload)
    assert ArtifactEnvelope.from_payload(result.trace.to_payload()) == result.trace
    assert p.private_state.stance_label == "label-2"


def test_nonpublishing_private_update_does_not_create_public_output(tmp_path):
    p = prepared(study_cells()[1])
    result = finalize_study_response(prepared=p, response=response_for(p, tmp_path))
    assert result.private_update.published is False
    assert result.public_post is None
    assert result.trace.payload["proposed_public_output"] is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"stance":"bad-label","confidence":4,"public_reason":"x"}',
        '{"stance":5,"confidence":4,"public_reason":"x"}',
        '{"stance":"label-5","confidence":0.8,"public_reason":"x"}',
    ],
)
def test_invalid_parse_keeps_original_state(content, tmp_path):
    p = prepared(study_cells()[1], publish_flag=True)
    result = finalize_study_response(prepared=p, response=response_for(p, tmp_path, content))
    assert not result.parse.success
    assert result.private_state is p.private_state
    assert result.private_update is None
    assert result.public_post is None
    assert result.trace.payload["proposed_post_state"] is None


def test_http_failure_preserves_state(tmp_path):
    p = prepared(study_cells()[0])
    result = finalize_study_response(prepared=p, response=response_for(p, tmp_path, status=503))
    assert not result.parse.success
    assert result.private_state is p.private_state


def test_foreign_response_is_rejected(tmp_path):
    p = prepared(study_cells()[0])
    foreign = prepared(study_cells()[3])
    with pytest.raises(ValueError, match="bind"):
        finalize_study_response(prepared=p, response=response_for(foreign, tmp_path))


def test_retry_changes_attempt_not_event_or_prompt():
    first = prepared(study_cells()[0])
    second = prepared(study_cells()[0], attempt_index=2)
    assert first.request.event_id == second.request.event_id
    assert first.request.prompt_hash == second.request.prompt_hash
    assert first.request.model_seed == second.request.model_seed
    assert first.request.attempt_id != second.request.attempt_id


def test_typed_preparation_rejects_actor_and_topic_drift():
    p = prepared(study_cells()[0])
    payload = topic().to_payload()
    payload["fact_card"] = "Other fact card."
    foreign = type(topic()).from_payload(payload)
    with pytest.raises(ValueError, match="topic"):
        replace(p, topic_package=foreign)
    with pytest.raises(ValueError, match="ordinal"):
        replace(p, event_ordinal=1)


@pytest.mark.parametrize(
    "content",
    [
        '{"stance":"label-5","stance":"label-1","confidence":4,"public_reason":"x"}',
        '{"stance":"label-5","confidence":NaN,"public_reason":"x"}',
        '{"stance":"label-5","confidence":4,"public_reason":' + json.dumps("x" * 1025) + "}",
    ],
)
def test_bounded_parse_rejects_duplicate_nonfinite_and_oversize_reason(content, tmp_path):
    p = prepared(study_cells()[1])
    result = finalize_study_response(prepared=p, response=response_for(p, tmp_path, content))
    assert not result.parse.success
    assert result.parse.error_code == "bounded_parse"
    assert result.private_state is p.private_state


def test_rehashed_wrong_wire_messages_are_rejected(tmp_path):
    p = prepared(study_cells()[1])
    response = response_for(p, tmp_path)
    wire = json.loads(response.transport_evidence.request_body)
    wire["messages"] = [{"role": "user", "content": "Other prompt"}]
    old = response.transport_evidence
    transport = Phase0BVllmTransportEvidence.create(
        request=p.request,
        http_status=old.http_status,
        response_headers=dict(old.response_headers),
        provider_request_id=old.provider_request_id,
        request_body=json.dumps(wire).encode(),
        raw_body=response.raw_body,
        body_truncated=False,
        started_at=old.started_at,
        ended_at=old.ended_at,
        latency_seconds=old.latency_seconds,
        outcome=response.outcome,
        error_code=response.error_code,
    )
    changed = Phase0BVllmEventResponse.create(
        request=p.request,
        outcome=response.outcome,
        error_code=response.error_code,
        retry_after_seconds=response.retry_after_seconds,
        provider_request_id=response.provider_request_id,
        usage=dict(response.usage),
        finish_reason=response.finish_reason,
        raw_body=response.raw_body,
        transport_evidence=transport,
    )
    with pytest.raises(ValueError, match="wire"):
        finalize_study_response(prepared=p, response=changed)


@pytest.mark.parametrize("tamper", ["blind_group_leak", "visible_state_drift"])
def test_rehashed_visible_projection_drift_is_rejected(tamper):
    p = prepared(study_cells()[0])
    visible = json.loads(p.prompt.messages[1]["content"])
    if tamper == "blind_group_leak":
        visible["self_group"] = "Blue"
    else:
        visible["current_private"]["stance"] = "label-6"
    messages = (dict(p.prompt.messages[0]), {"role": "user", "content": json.dumps(visible)})
    evidence = dict(p.prompt.evidence)
    evidence["exact_messages_shown"] = messages
    changed = StudyPrompt(
        messages, canonical_payload_hash(messages), evidence, canonical_payload_hash(evidence)
    )
    req = Phase0BVllmEventRequest.create(
        event_id=p.request.event_id,
        attempt_index=p.request.attempt_index,
        prompt_hash=changed.prompt_hash,
        rendered_messages=tuple(dict(m) for m in changed.messages),
        generation_settings=dict(p.request.generation_settings),
        model_seed=p.request.model_seed,
        adapter_binding_hash=p.request.adapter_binding_hash,
    )
    with pytest.raises(ValueError, match="projection"):
        replace(p, prompt=changed, request=req)
