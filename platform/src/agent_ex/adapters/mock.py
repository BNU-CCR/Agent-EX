"""Deterministic, script-only adapter with no network or real model dependency."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from ..domain import (
    _freeze,
    _require_id,
    _require_json_transport,
    _require_string,
    canonical_payload_hash,
)
from ..execution_evidence import MockAdapterExecutionBinding
from .base import (
    AdapterRequest,
    AdapterResponse,
    ModelAdapter,
    _issue_response_seal,
    _has_trusted_request_seal,
    _reseal_verified_persisted_response,
)


_RUNTIME = {
    "adapter": "agent_ex.adapters.mock.MockAdapter",
    "adapter_version": "1.0.0",
    "provider": "deterministic-mock",
    "runtime_version": "1.0.0",
}
_MODEL_IDENTITY = {
    "model": "deterministic-mock-model",
    "revision": "phase4b7-script-v1",
    "mode": "script_only_no_generation",
}


@dataclass(frozen=True, slots=True)
class MockScriptStep:
    outcome: str
    raw_response: str | None
    error_message: str | None

    def __post_init__(self) -> None:
        if self.outcome not in {"response", "timeout"}:
            raise ValueError("mock script outcome must be response or timeout")
        if self.outcome == "response":
            if type(self.raw_response) is not str or self.error_message is not None:
                raise ValueError("mock response step requires raw response only")
        elif self.raw_response is not None or not self.error_message:
            raise ValueError("mock timeout step requires an error message only")

    @classmethod
    def success(cls, payload: Mapping[str, object]) -> MockScriptStep:
        if type(payload) is not dict:
            raise TypeError("mock success payload must be a JSON object")
        _require_json_transport(payload, "mock success payload")
        return cls(
            outcome="response",
            raw_response=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            error_message=None,
        )

    @classmethod
    def malformed(cls, raw_response: str) -> MockScriptStep:
        return cls(outcome="response", raw_response=raw_response, error_message=None)

    @classmethod
    def timeout(cls, message: str) -> MockScriptStep:
        _require_string("mock timeout message", message)
        return cls(outcome="timeout", raw_response=None, error_message=message)

    def to_payload(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "raw_response": self.raw_response,
            "error_message": self.error_message,
        }


class MockAdapter(ModelAdapter):
    def __init__(
        self,
        *,
        script: Mapping[str, Sequence[MockScriptStep]],
        mock_runtime: Mapping[str, str],
        mock_only: bool,
    ) -> None:
        if mock_only is not True:
            raise ValueError("MockAdapter must be explicitly mock_only")
        if type(mock_runtime) is not dict or mock_runtime != {
            "provider": _RUNTIME["provider"],
            "runtime_version": _RUNTIME["runtime_version"],
        }:
            raise ValueError("mock runtime identity is unsupported or drifted")
        if type(script) is not dict or not script:
            raise ValueError("mock script must be a non-empty mapping")
        normalized: dict[str, tuple[MockScriptStep, ...]] = {}
        for event_id, steps in script.items():
            _require_id("script event_id", event_id)
            if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
                raise TypeError("mock script steps must be a sequence")
            values = tuple(steps)
            if not values or not all(isinstance(step, MockScriptStep) for step in values):
                raise ValueError("mock script event must contain typed steps")
            normalized[event_id] = values
        self._script = MappingProxyType(dict(normalized))
        self._runtime = _freeze(dict(_RUNTIME))
        self._script_hash = canonical_payload_hash(
            {
                event_id: tuple(step.to_payload() for step in steps)
                for event_id, steps in sorted(normalized.items())
            }
        )

    def execution_binding(self) -> MockAdapterExecutionBinding:
        """Return immutable execution evidence derived from this frozen adapter."""

        return MockAdapterExecutionBinding.create(
            expected_adapter_kind=_RUNTIME["adapter"],
            expected_adapter_version=_RUNTIME["adapter_version"],
            runtime_identity=dict(self._runtime),
            model_identity=dict(_MODEL_IDENTITY),
            script_hash=self._script_hash,
            mock_only=True,
        )

    def generate(self, request: AdapterRequest) -> AdapterResponse:
        if not isinstance(request, AdapterRequest):
            raise TypeError("request must be an AdapterRequest")
        if not _has_trusted_request_seal(request):
            raise ValueError("adapter request is not a trusted sealed prompt capability")
        if AdapterRequest.from_payload(request.to_payload()) != request:
            raise ValueError("adapter request replay does not match its record")
        steps = self._script.get(request.event_id)
        if steps is None:
            raise ValueError("mock script has no entry for request event")
        index = request.attempt_index - 1
        if not 0 <= index < len(steps):
            raise ValueError("attempt index is outside the scripted response sequence")
        step = steps[index]
        response_identity = {
            "request_hash": request.record_hash,
            "event_id": request.event_id,
            "topic_package_id": request.topic_package_id,
            "topic_package_hash": request.topic_package_hash,
            "attempt_index": request.attempt_index,
            "attempt_id": request.attempt_id,
            "mock_seed": request.mock_seed,
            "script_hash": self._script_hash,
        }
        response_id = "adapter-response-" + canonical_payload_hash(response_identity)
        provider_request_id = "mock-provider-request-" + canonical_payload_hash(
            {**response_identity, "runtime_identity": self._runtime}
        )
        values = {
            "response_id": response_id,
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "event_id": request.event_id,
            "topic_package_id": request.topic_package_id,
            "topic_package_hash": request.topic_package_hash,
            "attempt_index": request.attempt_index,
            "attempt_id": request.attempt_id,
            "outcome": step.outcome,
            "raw_response": step.raw_response,
            "raw_response_hash": None
            if step.raw_response is None
            else canonical_payload_hash(step.raw_response),
            "error": None
            if step.error_message is None
            else {"code": "timeout", "message": step.error_message},
            "runtime_identity": dict(self._runtime),
            "runtime_identity_hash": canonical_payload_hash(self._runtime),
            "model_identity": dict(_MODEL_IDENTITY),
            "model_identity_hash": canonical_payload_hash(_MODEL_IDENTITY),
            "provider_request_id": provider_request_id,
            "mock_seed": request.mock_seed,
            "script_hash": self._script_hash,
        }
        content = {
            "schema_version": "paper1.mock-adapter-response.v1",
            **values,
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        }
        return AdapterResponse(
            **values,
            record_hash=canonical_payload_hash(content),
            _factory_seal=_issue_response_seal(canonical_payload_hash(content)),  # type: ignore[operator]
        )


def validate_adapter_response(
    response: AdapterResponse,
    request: AdapterRequest,
    adapter: MockAdapter,
) -> AdapterResponse:
    """Replay a response from the trusted request, script, runtime, and model identity."""

    if not isinstance(response, AdapterResponse) or not isinstance(request, AdapterRequest):
        raise TypeError("response validation requires typed adapter response and request")
    if not isinstance(adapter, MockAdapter):
        raise TypeError("response validation requires the trusted MockAdapter")
    expected = adapter.generate(request)
    if response != expected:
        raise ValueError(
            "adapter response replay does not match trusted request, script, or runtime"
        )
    return expected


def verify_persisted_mock_response(
    *,
    request: AdapterRequest,
    response_payload: Mapping[str, object],
    binding: MockAdapterExecutionBinding,
) -> AdapterResponse:
    """Causally verify and reseal persisted mock evidence without invoking an adapter."""

    if not isinstance(request, AdapterRequest):
        raise TypeError("persisted response verification requires an AdapterRequest")
    if not _has_trusted_request_seal(request):
        raise ValueError("adapter request is not a trusted sealed prompt capability")
    if AdapterRequest.from_payload(request.to_payload()) != request:
        raise ValueError("adapter request replay does not match its record")
    if not isinstance(binding, MockAdapterExecutionBinding):
        raise TypeError("persisted response verification requires a typed execution binding")

    expected_binding = {
        "expected_adapter_kind": _RUNTIME["adapter"],
        "expected_adapter_version": _RUNTIME["adapter_version"],
        "runtime_identity": _RUNTIME,
        "runtime_identity_hash": canonical_payload_hash(_RUNTIME),
        "model_identity": _MODEL_IDENTITY,
        "model_identity_hash": canonical_payload_hash(_MODEL_IDENTITY),
    }
    for name, expected in expected_binding.items():
        if getattr(binding, name) != expected:
            raise ValueError(f"mock adapter execution binding {name} drifted")

    response = AdapterResponse.from_payload(response_payload)
    linked_fields = (
        "request_id",
        "event_id",
        "topic_package_id",
        "topic_package_hash",
        "attempt_index",
        "attempt_id",
        "mock_seed",
    )
    if response.request_hash != request.record_hash or any(
        getattr(response, name) != getattr(request, name) for name in linked_fields
    ):
        raise ValueError("persisted response does not completely bind its trusted request")
    if (
        response.runtime_identity != binding.runtime_identity
        or response.runtime_identity_hash != binding.runtime_identity_hash
    ):
        raise ValueError("persisted response runtime binding drifted")
    if (
        response.model_identity != binding.model_identity
        or response.model_identity_hash != binding.model_identity_hash
    ):
        raise ValueError("persisted response model binding drifted")
    if response.script_hash != binding.script_hash:
        raise ValueError("persisted response script binding drifted")

    response_identity = {
        "request_hash": request.record_hash,
        "event_id": request.event_id,
        "topic_package_id": request.topic_package_id,
        "topic_package_hash": request.topic_package_hash,
        "attempt_index": request.attempt_index,
        "attempt_id": request.attempt_id,
        "mock_seed": request.mock_seed,
        "script_hash": binding.script_hash,
    }
    if response.response_id != "adapter-response-" + canonical_payload_hash(response_identity):
        raise ValueError("persisted response identity does not match its causal linkage")
    expected_provider_request_id = "mock-provider-request-" + canonical_payload_hash(
        {**response_identity, "runtime_identity": binding.runtime_identity}
    )
    if response.provider_request_id != expected_provider_request_id:
        raise ValueError("persisted provider request identity does not match execution binding")

    return _reseal_verified_persisted_response(response)
