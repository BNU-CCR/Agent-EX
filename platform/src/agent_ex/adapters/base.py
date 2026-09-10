"""Provider-neutral model adapter evidence contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import hmac
import secrets
from typing import Mapping

from ..domain import (
    _freeze,
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
    derive_attempt_id,
)
from ..prompt import PromptView, _has_trusted_prompt_view_seal, render_messages


_REQUEST_SCHEMA = "paper1.mock-adapter-request.v1"
_RESPONSE_SCHEMA = "paper1.mock-adapter-response.v1"
_METADATA = {"mock_only": True, "research_parameter_status": "not_frozen"}


def _make_capability_authenticator(type_tag: bytes) -> tuple[object, object]:
    """Create an integrity sentinel, not a security boundary against same-process code."""
    key = secrets.token_bytes(32)

    def issue(record_hash: str) -> str:
        return hmac.new(
            key, type_tag + b"\x00" + record_hash.encode("ascii"), hashlib.sha256
        ).hexdigest()

    def verify(signature: object, record_hash: str) -> bool:
        return type(signature) is str and hmac.compare_digest(signature, issue(record_hash))

    return issue, verify


_issue_request_seal, _verify_request_seal = _make_capability_authenticator(
    b"agent-ex/adapter-request/v1"
)
_issue_response_seal, _verify_response_seal = _make_capability_authenticator(
    b"agent-ex/adapter-response/v1"
)


def _has_bound_seal(value: object, verify: object) -> bool:
    seal = getattr(value, "_factory_seal", None)
    record_hash = getattr(value, "record_hash", None)
    try:
        return (
            type(record_hash) is str
            and verify(seal, record_hash)  # type: ignore[operator]
            and record_hash == canonical_payload_hash(value.content_payload())  # type: ignore[attr-defined]
        )
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return False


def _has_trusted_request_seal(request: AdapterRequest) -> bool:
    return _has_bound_seal(request, _verify_request_seal)


def _has_trusted_response_seal(response: AdapterResponse) -> bool:
    return _has_bound_seal(response, _verify_response_seal)


def _reseal_verified_persisted_response(response: AdapterResponse) -> AdapterResponse:
    """Restore same-process integrity after a private caller completes causal checks.

    This is an internal integrity boundary, not a security boundary.  It deliberately
    does not validate provenance itself and must never be exposed as a public response
    factory; adapter-specific rehydration code owns those checks.
    """

    if not isinstance(response, AdapterResponse):
        raise TypeError("persisted response must be a typed AdapterResponse")
    object.__setattr__(
        response,
        "_factory_seal",
        _issue_response_seal(response.record_hash),  # type: ignore[operator]
    )
    return response


def _derive_request_id(
    *,
    event_id: str,
    topic_package_id: str,
    topic_package_hash: str,
    attempt_index: int,
    prompt_view_id: str,
    prompt_view_hash: str,
    rendered_messages_hash: str,
    mock_seed: int,
) -> str:
    return "adapter-request-" + canonical_payload_hash(
        {
            "event_id": event_id,
            "topic_package_id": topic_package_id,
            "topic_package_hash": topic_package_hash,
            "attempt_index": attempt_index,
            "prompt_view_id": prompt_view_id,
            "prompt_view_hash": prompt_view_hash,
            "rendered_messages_hash": rendered_messages_hash,
            "mock_seed": mock_seed,
        }
    )


@dataclass(frozen=True, slots=True)
class AdapterRequest:
    request_id: str
    event_id: str
    topic_package_id: str
    topic_package_hash: str
    attempt_index: int
    attempt_id: str
    prompt_view_id: str
    prompt_view_hash: str
    rendered_messages: tuple[Mapping[str, str], ...]
    rendered_messages_hash: str
    mock_seed: int
    record_hash: str = field(repr=False)
    _factory_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "event_id",
            "topic_package_id",
            "attempt_id",
            "prompt_view_id",
        ):
            _require_id(name, getattr(self, name))
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if self.attempt_id != derive_attempt_id(self.event_id, self.attempt_index):
            raise ValueError("attempt_id does not match event_id and attempt_index")
        _require_sha256("prompt_view_hash", self.prompt_view_hash)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        if not isinstance(self.rendered_messages, tuple) or not self.rendered_messages:
            raise ValueError("rendered_messages must be a non-empty tuple")
        for message in self.rendered_messages:
            if type(message) is not dict or set(message) != {"role", "content"}:
                raise ValueError("each rendered message must contain exact role/content fields")
            if message["role"] not in {"system", "user", "assistant"}:
                raise ValueError("rendered message role is unsupported")
            _require_string("rendered message content", message["content"])
        _require_sha256("rendered_messages_hash", self.rendered_messages_hash)
        _require_payload_hash(
            "rendered_messages_hash", self.rendered_messages_hash, self.rendered_messages
        )
        _require_int("mock_seed", self.mock_seed)
        if self.request_id != _derive_request_id(
            event_id=self.event_id,
            topic_package_id=self.topic_package_id,
            topic_package_hash=self.topic_package_hash,
            attempt_index=self.attempt_index,
            prompt_view_id=self.prompt_view_id,
            prompt_view_hash=self.prompt_view_hash,
            rendered_messages_hash=self.rendered_messages_hash,
            mock_seed=self.mock_seed,
        ):
            raise ValueError("request_id does not match adapter request identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "rendered_messages", _freeze(self.rendered_messages))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _REQUEST_SCHEMA,
            "request_id": self.request_id,
            "event_id": self.event_id,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "attempt_index": self.attempt_index,
            "attempt_id": self.attempt_id,
            "prompt_view_id": self.prompt_view_id,
            "prompt_view_hash": self.prompt_view_hash,
            "rendered_messages": self.rendered_messages,
            "rendered_messages_hash": self.rendered_messages_hash,
            "mock_seed": self.mock_seed,
            "metadata": self.metadata,
        }

    @classmethod
    def create(
        cls,
        *,
        prompt_view: PromptView,
        attempt_index: int,
        mock_seed: int,
        mock_only: bool,
    ) -> AdapterRequest:
        if mock_only is not True:
            raise ValueError("adapter requests must be explicitly mock_only")
        if not isinstance(prompt_view, PromptView):
            raise TypeError("prompt_view must be a PromptView")
        if not _has_trusted_prompt_view_seal(prompt_view):
            raise ValueError("prompt_view is not a trusted sealed prompt capability")
        # Rendering itself validates the hash-bound view before exposing messages.
        rendered_messages = render_messages(prompt_view)
        messages_hash = canonical_payload_hash(rendered_messages)
        request_id = _derive_request_id(
            event_id=prompt_view.event_id,
            topic_package_id=prompt_view.topic_package_id,
            topic_package_hash=prompt_view.topic_hash,
            attempt_index=attempt_index,
            prompt_view_id=prompt_view.view_id,
            prompt_view_hash=prompt_view.record_hash,
            rendered_messages_hash=messages_hash,
            mock_seed=mock_seed,
        )
        values = {
            "request_id": request_id,
            "event_id": prompt_view.event_id,
            "topic_package_id": prompt_view.topic_package_id,
            "topic_package_hash": prompt_view.topic_hash,
            "attempt_index": attempt_index,
            "attempt_id": derive_attempt_id(prompt_view.event_id, attempt_index),
            "prompt_view_id": prompt_view.view_id,
            "prompt_view_hash": prompt_view.record_hash,
            "rendered_messages": rendered_messages,
            "rendered_messages_hash": messages_hash,
            "mock_seed": mock_seed,
        }
        content = {"schema_version": _REQUEST_SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(
            **values,
            record_hash=canonical_payload_hash(content),
            _factory_seal=_issue_request_seal(canonical_payload_hash(content)),  # type: ignore[operator]
        )

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> AdapterRequest:
        expected = {
            "schema_version",
            "request_id",
            "event_id",
            "topic_package_id",
            "topic_package_hash",
            "attempt_index",
            "attempt_id",
            "prompt_view_id",
            "prompt_view_hash",
            "rendered_messages",
            "rendered_messages_hash",
            "mock_seed",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("adapter request fields do not match the v1 contract")
        _require_json_transport(payload, "adapter request")
        if payload["schema_version"] != _REQUEST_SCHEMA or payload["metadata"] != _METADATA:
            raise ValueError("adapter request schema or metadata is unsupported")
        if type(payload["rendered_messages"]) is not list:
            raise TypeError("adapter rendered_messages must be a JSON array")
        return cls(
            **{
                name: tuple(payload[name]) if name == "rendered_messages" else payload[name]
                for name in cls.__dataclass_fields__
                if name != "_factory_seal"
            }
        )  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class AdapterResponse:
    response_id: str
    request_id: str
    request_hash: str
    event_id: str
    topic_package_id: str
    topic_package_hash: str
    attempt_index: int
    attempt_id: str
    outcome: str
    raw_response: str | None
    raw_response_hash: str | None
    error: Mapping[str, str] | None
    runtime_identity: Mapping[str, str]
    runtime_identity_hash: str
    model_identity: Mapping[str, str]
    model_identity_hash: str
    provider_request_id: str
    mock_seed: int
    script_hash: str
    record_hash: str = field(repr=False)
    _factory_seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in (
            "response_id",
            "request_id",
            "event_id",
            "topic_package_id",
            "attempt_id",
            "provider_request_id",
        ):
            _require_id(name, getattr(self, name))
        _require_sha256("request_hash", self.request_hash)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_int("attempt_index", self.attempt_index, minimum=1)
        if self.attempt_id != derive_attempt_id(self.event_id, self.attempt_index):
            raise ValueError("attempt_id does not match event_id and attempt_index")
        if self.outcome not in {"response", "timeout"}:
            raise ValueError("adapter outcome must be response or timeout")
        if self.outcome == "response":
            if type(self.raw_response) is not str or self.error is not None:
                raise ValueError("response outcome requires raw_response without error")
            _require_sha256("raw_response_hash", self.raw_response_hash)
            _require_payload_hash("raw_response_hash", self.raw_response_hash, self.raw_response)
        else:
            if self.raw_response is not None or self.raw_response_hash is not None:
                raise ValueError("timeout cannot contain raw response content")
            if (
                type(self.error) is not dict
                or set(self.error) != {"code", "message"}
                or self.error.get("code") != "timeout"
            ):
                raise ValueError("timeout requires a timeout error")
            _require_string("timeout message", self.error.get("message"))
        if type(self.runtime_identity) is not dict or set(self.runtime_identity) != {
            "adapter",
            "adapter_version",
            "provider",
            "runtime_version",
        }:
            raise ValueError("runtime_identity fields do not match the mock contract")
        for value in self.runtime_identity.values():
            _require_string("runtime identity value", value)
        _require_sha256("runtime_identity_hash", self.runtime_identity_hash)
        _require_payload_hash(
            "runtime_identity_hash", self.runtime_identity_hash, self.runtime_identity
        )
        if type(self.model_identity) is not dict or set(self.model_identity) != {
            "model",
            "revision",
            "mode",
        }:
            raise ValueError("model_identity fields do not match the mock contract")
        for value in self.model_identity.values():
            _require_string("model identity value", value)
        _require_sha256("model_identity_hash", self.model_identity_hash)
        _require_payload_hash("model_identity_hash", self.model_identity_hash, self.model_identity)
        _require_int("mock_seed", self.mock_seed)
        _require_sha256("script_hash", self.script_hash)
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "error", _freeze(self.error))
        object.__setattr__(self, "runtime_identity", _freeze(self.runtime_identity))
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _RESPONSE_SCHEMA,
            "response_id": self.response_id,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "event_id": self.event_id,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "attempt_index": self.attempt_index,
            "attempt_id": self.attempt_id,
            "outcome": self.outcome,
            "raw_response": self.raw_response,
            "raw_response_hash": self.raw_response_hash,
            "error": self.error,
            "runtime_identity": self.runtime_identity,
            "runtime_identity_hash": self.runtime_identity_hash,
            "model_identity": self.model_identity,
            "model_identity_hash": self.model_identity_hash,
            "provider_request_id": self.provider_request_id,
            "mock_seed": self.mock_seed,
            "script_hash": self.script_hash,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> AdapterResponse:
        expected = (set(cls.__dataclass_fields__) - {"_factory_seal"}) | {
            "schema_version",
            "metadata",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("adapter response fields do not match the v1 contract")
        _require_json_transport(payload, "adapter response")
        if payload["schema_version"] != _RESPONSE_SCHEMA or payload["metadata"] != _METADATA:
            raise ValueError("adapter response schema or metadata is unsupported")
        return cls(
            **{name: payload[name] for name in cls.__dataclass_fields__ if name != "_factory_seal"}
        )  # type: ignore[arg-type]


class ModelAdapter(ABC):
    @abstractmethod
    def generate(self, request: AdapterRequest) -> AdapterResponse:
        """Execute one attempt. Retry policy and state mutation belong to later phases."""
