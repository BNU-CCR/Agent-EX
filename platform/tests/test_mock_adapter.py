from __future__ import annotations

import json

import pytest

from agent_ex.adapters.base import AdapterRequest, AdapterResponse, ModelAdapter
from agent_ex.adapters.mock import MockAdapter, MockScriptStep, validate_adapter_response
from agent_ex.domain import canonical_payload_hash, derive_attempt_id
from agent_ex.persona import render_persona
from agent_ex.prompt import PromptView, render_messages
from test_prompt import EVENT_ID, build as build_prompt, member, persona_template


MESSAGES = (
    {"role": "system", "content": "mock system"},
    {"role": "user", "content": "mock user"},
)


def request(*, event_id: str = EVENT_ID, attempt_index: int = 1) -> AdapterRequest:
    view = (
        build_prompt()
        if event_id == EVENT_ID
        else build_prompt(
            cell_id="P1-I0-C0-E2",
            persona=render_persona(
                persona_template(),
                member(),
                {"identity_present": False, "continuity_present": False},
            ),
        )
    )
    return AdapterRequest.create(
        prompt_view=view,
        attempt_index=attempt_index,
        mock_seed=12345,
        mock_only=True,
    )


def adapter() -> MockAdapter:
    return MockAdapter(
        script={
            EVENT_ID: (
                MockScriptStep.success(
                    {"stance": "label-2", "confidence": 4, "public_reason": "scripted"}
                ),
                MockScriptStep.malformed("not-json"),
                MockScriptStep.timeout("mock timeout"),
            )
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )


def test_mock_adapter_implements_interface_and_returns_hash_bound_success() -> None:
    value: ModelAdapter = adapter()
    response = value.generate(request())

    assert isinstance(response, AdapterResponse)
    assert response.outcome == "response"
    assert json.loads(response.raw_response or "") == {
        "stance": "label-2",
        "confidence": 4,
        "public_reason": "scripted",
    }
    assert response.event_id == EVENT_ID
    assert response.attempt_index == 1
    assert response.attempt_id == derive_attempt_id(EVENT_ID, 1)
    assert request().attempt_id == response.attempt_id
    assert response.request_hash == request().record_hash
    assert response.runtime_identity == {
        "adapter": "agent_ex.adapters.mock.MockAdapter",
        "adapter_version": "1.0.0",
        "provider": "deterministic-mock",
        "runtime_version": "1.0.0",
    }
    assert response.model_identity == {
        "model": "deterministic-mock-model",
        "revision": "phase4b7-script-v1",
        "mode": "script_only_no_generation",
    }
    assert response.model_identity_hash == canonical_payload_hash(response.model_identity)
    assert response.record_hash == canonical_payload_hash(response.content_payload())
    assert AdapterResponse.from_payload(response.to_payload()) == response
    validate_adapter_response(response, request(), adapter())


def test_mock_adapter_returns_scripted_malformed_and_timeout_without_retrying() -> None:
    malformed = adapter().generate(request(attempt_index=2))
    timeout = adapter().generate(request(attempt_index=3))

    assert malformed.outcome == "response" and malformed.raw_response == "not-json"
    assert timeout.outcome == "timeout" and timeout.raw_response is None
    assert timeout.error == {"code": "timeout", "message": "mock timeout"}
    assert malformed.attempt_index == 2 and timeout.attempt_index == 3


def test_mock_adapter_is_deterministic_and_binds_explicit_seed_script_and_attempt() -> None:
    first = adapter().generate(request())
    second = adapter().generate(request())
    assert first == second

    with pytest.raises(ValueError, match="script|event"):
        adapter().generate(request(event_id="event-unknown"))
    with pytest.raises(ValueError, match="attempt|script"):
        adapter().generate(request(attempt_index=4))
    with pytest.raises((TypeError, ValueError), match="mock_seed|seed"):
        AdapterRequest.create(
            prompt_view=build_prompt(), attempt_index=1, mock_seed=True, mock_only=True
        )


def test_mock_adapter_rejects_runtime_drift_and_script_rewrapping() -> None:
    with pytest.raises(ValueError, match="JSON|finite"):
        MockScriptStep.success(
            {"stance": "label-2", "confidence": float("nan"), "public_reason": "x"}
        )


def test_adapter_rejects_unsealed_stale_or_mutated_request_capabilities() -> None:
    trusted = request()
    unsealed = AdapterRequest.from_payload(trusted.to_payload())
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        adapter().generate(unsealed)

    payload = trusted.to_payload()
    payload["rendered_messages"][1]["content"] = "mutated"  # type: ignore[index]
    payload["rendered_messages_hash"] = canonical_payload_hash(payload["rendered_messages"])
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    with pytest.raises(ValueError, match="request_id|identity|trusted"):
        AdapterRequest.from_payload(payload)

    for field, forged_value in (
        ("persona_text", "hash-consistent forged persona"),
        ("social_messages", ["hash-consistent forged social"]),
    ):
        view_payload = build_prompt().to_payload()
        view_payload[field] = forged_value
        view_content = {key: value for key, value in view_payload.items() if key != "record_hash"}
        view_payload["record_hash"] = canonical_payload_hash(view_content)
        forged_view = PromptView.from_payload(view_payload)
        with pytest.raises(ValueError, match="trusted|sealed|capability|prompt"):
            render_messages(forged_view)
        with pytest.raises(ValueError, match="trusted|sealed|capability|prompt"):
            AdapterRequest.create(
                prompt_view=forged_view,
                attempt_index=1,
                mock_seed=12345,
                mock_only=True,
            )


def test_adapter_response_validator_replays_all_trusted_runtime_and_script_fields() -> None:
    trusted_request = request()
    trusted_adapter = adapter()
    response = trusted_adapter.generate(trusted_request)
    payload = response.to_payload()
    payload["model_identity"]["revision"] = "drifted"  # type: ignore[index]
    payload["model_identity_hash"] = canonical_payload_hash(payload["model_identity"])
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    forged = AdapterResponse.from_payload(payload)
    with pytest.raises(ValueError, match="response|replay|runtime|model"):
        validate_adapter_response(forged, trusted_request, trusted_adapter)

    timeout = trusted_adapter.generate(request(attempt_index=3))
    timeout_payload = timeout.to_payload()
    timeout_payload["error"]["extra"] = "not allowed"  # type: ignore[index]
    with pytest.raises(ValueError, match="timeout|error"):
        AdapterResponse.from_payload(timeout_payload)
    with pytest.raises(TypeError, match="message"):
        MockScriptStep.timeout(1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="runtime"):
        MockAdapter(
            script={EVENT_ID: (MockScriptStep.malformed("x"),)},
            mock_runtime={"provider": "network-provider", "runtime_version": "latest"},
            mock_only=True,
        )
    with pytest.raises(ValueError, match="mock_only"):
        MockAdapter(
            script={EVENT_ID: (MockScriptStep.malformed("x"),)},
            mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
            mock_only=False,
        )


def test_seals_bind_issued_content_digest_against_reflective_mutation() -> None:
    for field, value in (
        ("persona_text", "reflectively forged persona"),
        ("social_messages", ("reflectively forged social",)),
    ):
        view = build_prompt()
        object.__setattr__(view, field, value)
        object.__setattr__(view, "record_hash", canonical_payload_hash(view.content_payload()))
        with pytest.raises(ValueError, match="trusted|sealed|capability"):
            render_messages(view)
        with pytest.raises(ValueError, match="trusted|sealed|capability"):
            AdapterRequest.create(prompt_view=view, attempt_index=1, mock_seed=123, mock_only=True)

    forged_request = request()
    messages = tuple(forged_request.rendered_messages[:-1]) + (
        {"role": "user", "content": "reflectively forged request"},
    )
    object.__setattr__(forged_request, "rendered_messages", messages)
    object.__setattr__(
        forged_request,
        "rendered_messages_hash",
        canonical_payload_hash(messages),
    )
    object.__setattr__(
        forged_request,
        "record_hash",
        canonical_payload_hash(forged_request.content_payload()),
    )
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        adapter().generate(forged_request)


def test_object_visible_seal_material_cannot_resign_mutated_capabilities() -> None:
    def reuse_visible_seal(value: object) -> None:
        visible = value._factory_seal  # type: ignore[attr-defined]
        forged = (
            (visible[0], value.record_hash)  # type: ignore[attr-defined,index]
            if isinstance(visible, tuple)
            else visible
        )
        object.__setattr__(value, "_factory_seal", forged)

    view = build_prompt()
    object.__setattr__(view, "persona_text", "resigned forged persona")
    object.__setattr__(view, "record_hash", canonical_payload_hash(view.content_payload()))
    reuse_visible_seal(view)
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        render_messages(view)
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        AdapterRequest.create(prompt_view=view, attempt_index=1, mock_seed=123, mock_only=True)

    forged_request = request()
    messages = tuple(forged_request.rendered_messages[:-1]) + (
        {"role": "user", "content": "resigned forged request"},
    )
    object.__setattr__(forged_request, "rendered_messages", messages)
    object.__setattr__(forged_request, "rendered_messages_hash", canonical_payload_hash(messages))
    object.__setattr__(
        forged_request, "record_hash", canonical_payload_hash(forged_request.content_payload())
    )
    reuse_visible_seal(forged_request)
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        adapter().generate(forged_request)
