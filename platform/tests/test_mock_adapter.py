from __future__ import annotations

import json

import pytest

from agent_ex.adapters import base as adapter_base
from agent_ex.adapters.base import AdapterRequest, AdapterResponse, ModelAdapter
from agent_ex.adapters.mock import (
    MockAdapter,
    MockScriptStep,
    _validate_mock_response_against_binding,
    validate_adapter_response,
    verify_persisted_mock_response,
)
from agent_ex.domain import canonical_payload_hash, derive_attempt_id
from agent_ex.execution_evidence import MockAdapterExecutionBinding
from agent_ex.persona import render_persona
from agent_ex.prompt import PromptView, render_messages
from test_prompt import EVENT_ID, build as build_prompt, member, persona_template


MESSAGES = (
    {"role": "system", "content": "mock system"},
    {"role": "user", "content": "mock user"},
)


def request(
    *, event_id: str = EVENT_ID, attempt_index: int = 1, mock_seed: int = 12345
) -> AdapterRequest:
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
        mock_seed=mock_seed,
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


def _rehash_response_payload(payload: dict[str, object]) -> dict[str, object]:
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    return payload


def _public_binding_like(
    binding: MockAdapterExecutionBinding,
    *,
    script_step_hashes: dict[str, tuple[str, ...]] | None = None,
) -> MockAdapterExecutionBinding:
    return MockAdapterExecutionBinding.create(
        expected_adapter_kind=binding.expected_adapter_kind,
        expected_adapter_version=binding.expected_adapter_version,
        runtime_identity=binding.runtime_identity,
        model_identity=binding.model_identity,
        script_step_hashes=(
            dict(binding.script_step_hashes) if script_step_hashes is None else script_step_hashes
        ),
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


def test_execution_binding_is_available_before_generate_and_matches_response() -> None:
    value = adapter()

    binding = value.execution_binding()
    response = value.generate(request())

    assert isinstance(binding, MockAdapterExecutionBinding)
    assert MockAdapterExecutionBinding.from_payload(binding.to_payload()) == binding
    assert binding.expected_adapter_kind == response.runtime_identity["adapter"]
    assert binding.expected_adapter_version == response.runtime_identity["adapter_version"]
    assert binding.runtime_identity == response.runtime_identity
    assert binding.runtime_identity_hash == response.runtime_identity_hash
    assert binding.model_identity == response.model_identity
    assert binding.model_identity_hash == response.model_identity_hash
    assert binding.script_hash == response.script_hash
    assert binding.script_hash == canonical_payload_hash(binding.script_step_hashes)
    assert binding.script_step_hashes[EVENT_ID][0] == canonical_payload_hash(
        MockScriptStep.success(
            {"stance": "label-2", "confidence": 4, "public_reason": "scripted"}
        ).to_payload()
    )


def test_persisted_response_roundtrip_rehydrates_trusted_response_without_generate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = adapter()
    trusted_request = request()
    binding = value.execution_binding()
    response = value.generate(trusted_request)
    calls = 0

    def fail_generate(_: AdapterRequest) -> AdapterResponse:
        nonlocal calls
        calls += 1
        pytest.fail("persisted response verification replayed generate")

    monkeypatch.setattr(value, "generate", fail_generate)
    restored = verify_persisted_mock_response(
        request=trusted_request,
        response_payload=response.to_payload(),
        binding=binding,
    )

    assert restored == response
    assert adapter_base._has_trusted_response_seal(restored)
    assert calls == 0


def test_structural_response_validator_rejects_other_script_even_without_capability_check() -> None:
    trusted_request = request()
    expected = adapter()
    other = MockAdapter(
        script={EVENT_ID: (MockScriptStep.malformed("different raw response"),)},
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )

    with pytest.raises(ValueError, match="script|step|commit"):
        _validate_mock_response_against_binding(
            request=trusted_request,
            response=other.generate(trusted_request),
            binding=expected.execution_binding(),
        )


@pytest.mark.parametrize(
    "mismatch",
    ["request", "event", "attempt", "mock_seed"],
)
def test_persisted_response_rejects_complete_request_linkage_mismatch(mismatch: str) -> None:
    value = adapter()
    trusted_request = request()
    payload = value.generate(trusted_request).to_payload()
    if mismatch == "request":
        other = request(attempt_index=2)
    elif mismatch == "event":
        other = request(event_id="event-other")
    elif mismatch == "attempt":
        other = request(attempt_index=3)
    else:
        other = request(mock_seed=54321)

    with pytest.raises(ValueError, match="request|event|attempt|seed|link"):
        verify_persisted_mock_response(
            request=other,
            response_payload=payload,
            binding=value.execution_binding(),
        )


@pytest.mark.parametrize("field", ["script_hash", "runtime_identity", "model_identity"])
def test_persisted_response_rejects_independently_tampered_and_rehashed_response(
    field: str,
) -> None:
    value = adapter()
    trusted_request = request()
    payload = value.generate(trusted_request).to_payload()
    if field == "script_hash":
        payload[field] = "1" * 64
    else:
        identity = dict(payload[field])  # type: ignore[arg-type]
        identity[next(iter(identity))] = "tampered"
        payload[field] = identity
        payload[f"{field}_hash"] = canonical_payload_hash(identity)
    _rehash_response_payload(payload)

    with pytest.raises(ValueError, match="binding|script|runtime|model"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=payload,
            binding=value.execution_binding(),
        )


@pytest.mark.parametrize("field", ["script_hash", "runtime_identity", "model_identity"])
def test_persisted_response_rejects_independently_tampered_and_rehashed_binding(
    field: str,
) -> None:
    value = adapter()
    trusted_request = request()
    original = value.execution_binding()
    values = {
        "expected_adapter_kind": original.expected_adapter_kind,
        "expected_adapter_version": original.expected_adapter_version,
        "runtime_identity": dict(original.runtime_identity),
        "model_identity": dict(original.model_identity),
        "script_step_hashes": dict(original.script_step_hashes),
        "mock_only": True,
    }
    if field == "script_hash":
        values["script_step_hashes"] = {EVENT_ID: ("2" * 64,) * 3}
    else:
        identity = dict(values[field])  # type: ignore[arg-type]
        identity[next(iter(identity))] = "tampered"
        values[field] = identity
        if field == "runtime_identity":
            values["expected_adapter_kind"] = identity["adapter"]
            values["expected_adapter_version"] = identity["adapter_version"]
    tampered = MockAdapterExecutionBinding.create(**values)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="binding|script|runtime|model|adapter"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=value.generate(trusted_request).to_payload(),
            binding=tampered,
        )


def test_persisted_response_rejects_forged_raw_with_recomputed_hashes() -> None:
    value = adapter()
    trusted_request = request()
    binding = value.execution_binding()
    payload = value.generate(trusted_request).to_payload()
    payload["raw_response"] = '{"stance":"label-6","confidence":5,"public_reason":"forged"}'
    payload["raw_response_hash"] = canonical_payload_hash(payload["raw_response"])
    _rehash_response_payload(payload)

    with pytest.raises(ValueError, match="script|step|commit"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=payload,
            binding=binding,
        )


@pytest.mark.parametrize("rewrite", ["timeout_error", "outcome"])
def test_persisted_response_rejects_timeout_error_or_outcome_rewrite(rewrite: str) -> None:
    value = adapter()
    trusted_request = request(attempt_index=3)
    binding = value.execution_binding()
    payload = value.generate(trusted_request).to_payload()
    if rewrite == "timeout_error":
        payload["error"] = {"code": "timeout", "message": "rewritten timeout"}
    else:
        payload["outcome"] = "response"
        payload["raw_response"] = "rewritten response"
        payload["raw_response_hash"] = canonical_payload_hash(payload["raw_response"])
        payload["error"] = None
    _rehash_response_payload(payload)

    with pytest.raises(ValueError, match="script|step|commit"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=payload,
            binding=binding,
        )


def test_persisted_response_rejects_public_binding_joint_rewrite() -> None:
    value = adapter()
    trusted_request = request()
    trusted_binding = value.execution_binding()
    payload = value.generate(trusted_request).to_payload()
    payload["raw_response"] = "jointly forged"
    payload["raw_response_hash"] = canonical_payload_hash(payload["raw_response"])
    forged_step = {
        "outcome": "response",
        "raw_response": payload["raw_response"],
        "error_message": None,
    }
    commitments = dict(trusted_binding.script_step_hashes)
    commitments[EVENT_ID] = (
        canonical_payload_hash(forged_step),
        *commitments[EVENT_ID][1:],
    )
    public_binding = _public_binding_like(trusted_binding, script_step_hashes=commitments)
    payload["script_hash"] = public_binding.script_hash
    response_identity = {
        "request_hash": trusted_request.record_hash,
        "event_id": trusted_request.event_id,
        "topic_package_id": trusted_request.topic_package_id,
        "topic_package_hash": trusted_request.topic_package_hash,
        "attempt_index": trusted_request.attempt_index,
        "attempt_id": trusted_request.attempt_id,
        "mock_seed": trusted_request.mock_seed,
        "script_hash": public_binding.script_hash,
    }
    payload["response_id"] = "adapter-response-" + canonical_payload_hash(response_identity)
    payload["provider_request_id"] = "mock-provider-request-" + canonical_payload_hash(
        {**response_identity, "runtime_identity": public_binding.runtime_identity}
    )
    _rehash_response_payload(payload)

    with pytest.raises(ValueError, match="trusted|sealed|capability|binding"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=payload,
            binding=public_binding,
        )


def test_persisted_response_rejects_deserialized_binding() -> None:
    value = adapter()
    trusted_request = request()
    response = value.generate(trusted_request)
    restored_binding = MockAdapterExecutionBinding.from_payload(
        value.execution_binding().to_payload()
    )

    with pytest.raises(ValueError, match="trusted|sealed|capability|binding"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=response.to_payload(),
            binding=restored_binding,
        )


@pytest.mark.parametrize("attempt_index", [2, 3])
def test_persisted_response_rejects_wrong_committed_event_attempt_step(
    attempt_index: int,
) -> None:
    value = adapter()
    trusted_request = request(attempt_index=attempt_index)
    payload = value.generate(trusted_request).to_payload()
    first_step_payload = value.generate(request()).to_payload()
    payload["outcome"] = first_step_payload["outcome"]
    payload["raw_response"] = first_step_payload["raw_response"]
    payload["raw_response_hash"] = first_step_payload["raw_response_hash"]
    payload["error"] = first_step_payload["error"]
    _rehash_response_payload(payload)

    with pytest.raises(ValueError, match="script|step|commit"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=payload,
            binding=value.execution_binding(),
        )


def test_persisted_response_rejects_binding_without_committed_event() -> None:
    value = adapter()
    trusted_request = request()
    payload = value.generate(trusted_request).to_payload()
    other_event = "event-other"
    other_adapter = MockAdapter(
        script={
            other_event: (
                MockScriptStep.success(
                    {"stance": "label-2", "confidence": 4, "public_reason": "scripted"}
                ),
            )
        },
        mock_runtime={"provider": "deterministic-mock", "runtime_version": "1.0.0"},
        mock_only=True,
    )
    other_binding = other_adapter.execution_binding()
    payload["script_hash"] = other_binding.script_hash
    response_identity = {
        "request_hash": trusted_request.record_hash,
        "event_id": trusted_request.event_id,
        "topic_package_id": trusted_request.topic_package_id,
        "topic_package_hash": trusted_request.topic_package_hash,
        "attempt_index": trusted_request.attempt_index,
        "attempt_id": trusted_request.attempt_id,
        "mock_seed": trusted_request.mock_seed,
        "script_hash": other_binding.script_hash,
    }
    payload["response_id"] = "adapter-response-" + canonical_payload_hash(response_identity)
    payload["provider_request_id"] = "mock-provider-request-" + canonical_payload_hash(
        {**response_identity, "runtime_identity": other_binding.runtime_identity}
    )
    _rehash_response_payload(payload)

    with pytest.raises(ValueError, match="event|attempt|commit"):
        verify_persisted_mock_response(
            request=trusted_request,
            response_payload=payload,
            binding=other_binding,
        )


def test_persisted_response_rejects_untrusted_and_tampered_request() -> None:
    value = adapter()
    trusted = request()
    response_payload = value.generate(trusted).to_payload()
    untrusted = AdapterRequest.from_payload(trusted.to_payload())
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        verify_persisted_mock_response(
            request=untrusted,
            response_payload=response_payload,
            binding=value.execution_binding(),
        )

    object.__setattr__(trusted, "mock_seed", 999)
    object.__setattr__(trusted, "record_hash", canonical_payload_hash(trusted.content_payload()))
    with pytest.raises(ValueError, match="trusted|sealed|capability"):
        verify_persisted_mock_response(
            request=trusted,
            response_payload=response_payload,
            binding=value.execution_binding(),
        )


def test_base_layer_does_not_export_a_public_arbitrary_response_reseal() -> None:
    assert not hasattr(adapter_base, "reseal_verified_persisted_response")


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
