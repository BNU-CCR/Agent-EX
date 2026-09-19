"""Crash-safe projection and reconciliation primitives for the blinded judge run.

This module deliberately contains no network execution loop.  It defines the immutable
records and deterministic replay rules used by Task 6's runner.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, fields, replace
import hashlib
from typing import TYPE_CHECKING, Mapping

from ..domain import canonical_payload_hash
from .judge_contracts import (
    JudgeExecutionManifest,
    JudgeParseEvidence,
    JudgePreflightEvidence,
    JudgeRequestEvidence,
    JudgeResponseEvidence,
    JudgeServiceEvidence,
)
from .review import BlindReviewItem

if TYPE_CHECKING:
    from .judge_store import JudgeRunStore


_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_RECONCILIATION_DECISIONS = (
    "recovered_response",
    "proved_not_sent",
    "ambiguous",
)


@dataclass(frozen=True, slots=True)
class JudgeApprovedItem:
    item_id: str
    item_hash: str

    def to_payload(self) -> dict[str, str]:
        return {"item_id": self.item_id, "item_hash": self.item_hash}


@dataclass(frozen=True, slots=True)
class JudgeApprovedOrder:
    """Exact item identity/order extracted from the manifest-bound pack and index."""

    manifest_hash: str
    pack_hash: str
    index_hash: str
    items: tuple[JudgeApprovedItem, ...]
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-approved-order.v1"

    def __post_init__(self) -> None:
        for name in ("manifest_hash", "pack_hash", "index_hash", "record_hash"):
            _sha256(name, getattr(self, name))
        if type(self.items) is not tuple or not self.items:
            raise ValueError("approved judge order must contain items")
        if len({item.item_id for item in self.items}) != len(self.items) or len(
            {item.item_hash for item in self.items}
        ) != len(self.items):
            raise ValueError("approved judge order contains duplicate identities")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("approved judge order hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "manifest_hash": self.manifest_hash,
            "pack_hash": self.pack_hash,
            "index_hash": self.index_hash,
            "items": [item.to_payload() for item in self.items],
            "metadata": dict(_METADATA),
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeApprovedOrder:
        expected = {
            "schema_version",
            "manifest_hash",
            "pack_hash",
            "index_hash",
            "items",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("approved judge order requires exact fields")
        if payload["schema_version"] != cls._SCHEMA or payload["metadata"] != _METADATA:
            raise ValueError("approved judge order schema or metadata differs")
        if type(payload["items"]) is not list:
            raise TypeError("approved judge order items must use a JSON array")
        items: list[JudgeApprovedItem] = []
        for item in payload["items"]:
            if type(item) is not dict or set(item) != {"item_id", "item_hash"}:
                raise ValueError("approved judge item requires exact fields")
            items.append(JudgeApprovedItem(item_id=item["item_id"], item_hash=item["item_hash"]))
        return cls(
            manifest_hash=payload["manifest_hash"],
            pack_hash=payload["pack_hash"],
            index_hash=payload["index_hash"],
            items=tuple(items),
            record_hash=payload["record_hash"],
        )  # type: ignore[arg-type]

    @classmethod
    def from_manifest_bound_payloads(
        cls,
        manifest: JudgeExecutionManifest,
        pack: Mapping[str, object],
        index: Mapping[str, object],
    ) -> JudgeApprovedOrder:
        """Verify canonical pack/index identities and derive the only allowed order."""

        if type(pack) is not dict or type(index) is not dict:
            raise TypeError("judge pack and index must be decoded JSON objects")
        for name, payload, expected_hash in (
            ("pack", pack, manifest.judge_pack_hash),
            ("index", index, manifest.judge_pack_index_hash),
        ):
            embedded = payload.get("record_hash")
            if embedded != expected_hash or embedded != canonical_payload_hash(
                {key: value for key, value in payload.items() if key != "record_hash"}
            ):
                raise ValueError(f"judge {name} hash differs from manifest-bound evidence")
        if (
            pack.get("schema_version") != "paper1.calibration.blind-coder-pack.v1"
            or pack.get("coder_role") != "judge"
            or pack.get("coder_contract_hash") != manifest.judge_coder_contract_hash
            or pack.get("export_hash") != manifest.export_hash
            or type(pack.get("items")) is not list
        ):
            raise ValueError("judge pack contract differs from execution manifest")
        if (
            index.get("schema_version") != "paper1.calibration.blind-coder-pack-index.v1"
            or index.get("review_bundle_hash") != manifest.review_bundle_hash
            or type(index.get("packs")) is not list
            or len(index["packs"]) != 1
            or type(index["packs"][0]) is not dict
            or index["packs"][0].get("record_hash") != manifest.judge_pack_hash
            or index["packs"][0].get("coder_id") != pack.get("coder_id")
        ):
            raise ValueError("judge pack index differs from execution manifest")
        parsed = tuple(BlindReviewItem.from_payload(item) for item in pack["items"])
        if len(parsed) != manifest.expected_item_count:
            raise ValueError("judge pack item count differs from execution manifest")
        items = tuple(JudgeApprovedItem(item.item_id, item.record_hash) for item in parsed)
        values = {
            "manifest_hash": manifest.record_hash,
            "pack_hash": manifest.judge_pack_hash,
            "index_hash": manifest.judge_pack_index_hash,
            "items": items,
        }
        content = {
            "schema_version": cls._SCHEMA,
            "manifest_hash": manifest.record_hash,
            "pack_hash": manifest.judge_pack_hash,
            "index_hash": manifest.judge_pack_index_hash,
            "items": [item.to_payload() for item in items],
            "metadata": dict(_METADATA),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))


class AmbiguousJudgeDispatchError(RuntimeError):
    """Raised when replay reaches an intent whose send outcome is unresolved."""


def _sha256(name: str, value: object) -> str:
    if type(value) is not str or len(value) != 64:
        raise ValueError(f"{name} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be a SHA-256 digest") from error
    if value != value.lower():
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _text(name: str, value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be explicit text")
    return value


def _integer(name: str, value: object, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _record_payload(record: object, schema: str) -> dict[str, object]:
    return {
        "schema_version": schema,
        **{
            field.name: getattr(record, field.name)
            for field in fields(record)
            if field.name != "record_hash"
        },
        "metadata": dict(_METADATA),
    }


def _validate_payload(
    payload: Mapping[str, object], cls: type[object], schema: str
) -> dict[str, object]:
    expected = {field.name for field in fields(cls)} | {"schema_version", "metadata"}
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError("judge evidence payload requires exact fields")
    if payload["schema_version"] != schema or payload["metadata"] != _METADATA:
        raise ValueError("judge evidence schema or metadata differs from contract")
    return {field.name: payload[field.name] for field in fields(cls)}


@dataclass(frozen=True, slots=True)
class JudgeDispatchIntent:
    manifest_hash: str
    item_id: str
    item_hash: str
    order_index: int
    attempt_index: int
    attempt_id: str
    request: JudgeRequestEvidence
    created_at: str
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-dispatch-intent.v1"

    def __post_init__(self) -> None:
        _sha256("manifest_hash", self.manifest_hash)
        _text("item_id", self.item_id)
        _sha256("item_hash", self.item_hash)
        _integer("order_index", self.order_index)
        _integer("attempt_index", self.attempt_index, 1)
        _text("attempt_id", self.attempt_id)
        if not isinstance(self.request, JudgeRequestEvidence):
            raise TypeError("dispatch intent requires JudgeRequestEvidence")
        JudgeRequestEvidence.from_payload(self.request.to_payload())
        if (
            self.request.manifest_hash != self.manifest_hash
            or self.request.rendered_request.item_id != self.item_id
            or self.request.rendered_request.item_hash != self.item_hash
            or self.request.order_index != self.order_index
            or self.request.rendered_request.attempt_index != self.attempt_index
        ):
            raise ValueError("dispatch request identity differs from intent")
        _text("created_at", self.created_at)
        _sha256("record_hash", self.record_hash)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("judge dispatch intent hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "manifest_hash": self.manifest_hash,
            "item_id": self.item_id,
            "item_hash": self.item_hash,
            "order_index": self.order_index,
            "attempt_index": self.attempt_index,
            "attempt_id": self.attempt_id,
            "request": self.request.to_payload(),
            "created_at": self.created_at,
            "metadata": dict(_METADATA),
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        *,
        request: JudgeRequestEvidence,
        created_at: str,
    ) -> JudgeDispatchIntent:
        if not isinstance(request, JudgeRequestEvidence):
            raise TypeError("dispatch intent requires JudgeRequestEvidence")
        rendered = request.rendered_request
        attempt_identity = canonical_payload_hash(
            {
                "manifest_hash": request.manifest_hash,
                "item_id": rendered.item_id,
                "item_hash": rendered.item_hash,
                "order_index": request.order_index,
                "attempt_index": rendered.attempt_index,
                "request_hash": request.record_hash,
                "request_id": request.request_id,
                "idempotency_key": rendered.idempotency_key,
            }
        )
        values = {
            "manifest_hash": request.manifest_hash,
            "item_id": rendered.item_id,
            "item_hash": rendered.item_hash,
            "order_index": request.order_index,
            "attempt_index": rendered.attempt_index,
            "attempt_id": f"judge-attempt-{attempt_identity}",
            "request": request,
            "created_at": created_at,
        }
        content = {
            "schema_version": cls._SCHEMA,
            **{name: value for name, value in values.items() if name != "request"},
            "request": request.to_payload(),
            "metadata": dict(_METADATA),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeDispatchIntent:
        values = _validate_payload(payload, cls, cls._SCHEMA)
        if type(values["request"]) is not dict:
            raise TypeError("dispatch request must use a JSON object")
        values["request"] = JudgeRequestEvidence.from_payload(values["request"])
        return cls(**values)  # type: ignore[arg-type]

    @property
    def request_hash(self) -> str:
        return self.request.record_hash

    @property
    def request_id(self) -> str:
        return self.request.request_id

    @property
    def idempotency_key(self) -> str:
        return self.request.rendered_request.idempotency_key


@dataclass(frozen=True, slots=True)
class JudgeProviderAuditRecord:
    manifest_hash: str
    intent_hash: str
    item_id: str
    attempt_id: str
    request_id: str
    provider_audit_hash: str
    response_bytes_base64: str
    response_bytes_hash: str
    checked_at: str
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-provider-audit.v1"

    def __post_init__(self) -> None:
        for name in ("manifest_hash", "intent_hash", "provider_audit_hash", "response_bytes_hash"):
            _sha256(name, getattr(self, name))
        for name in ("item_id", "attempt_id", "request_id", "checked_at"):
            _text(name, getattr(self, name))
        try:
            raw = base64.b64decode(self.response_bytes_base64, validate=True)
        except ValueError as error:
            raise ValueError("provider audit response bytes are not canonical base64") from error
        if hashlib.sha256(raw).hexdigest() != self.response_bytes_hash:
            raise ValueError("provider audit response bytes differ from their hash")
        _sha256("record_hash", self.record_hash)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("provider audit record hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return _record_payload(self, self._SCHEMA)

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls, intent: JudgeDispatchIntent, evidence: Mapping[str, object]
    ) -> JudgeProviderAuditRecord:
        required = {
            "provider_audit_hash",
            "request_id",
            "response_bytes_base64",
            "response_bytes_hash",
            "checked_at",
        }
        if type(evidence) is not dict or set(evidence) != required:
            raise ValueError("provider audit evidence requires exact fields")
        if evidence["request_id"] != intent.request_id:
            raise ValueError("provider audit request identity differs from dispatch intent")
        values = {
            "manifest_hash": intent.manifest_hash,
            "intent_hash": intent.record_hash,
            "item_id": intent.item_id,
            "attempt_id": intent.attempt_id,
            **evidence,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeProviderAuditRecord:
        return cls(**_validate_payload(payload, cls, cls._SCHEMA))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JudgeIncompleteAttemptMarker:
    manifest_hash: str
    intent_hash: str
    item_id: str
    attempt_id: str
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-incomplete-attempt-marker.v1"

    def __post_init__(self) -> None:
        _sha256("manifest_hash", self.manifest_hash)
        _sha256("intent_hash", self.intent_hash)
        _text("item_id", self.item_id)
        _text("attempt_id", self.attempt_id)
        _sha256("record_hash", self.record_hash)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("incomplete attempt marker hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return _record_payload(self, self._SCHEMA)

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(cls, intent: JudgeDispatchIntent) -> JudgeIncompleteAttemptMarker:
        values = {
            "manifest_hash": intent.manifest_hash,
            "intent_hash": intent.record_hash,
            "item_id": intent.item_id,
            "attempt_id": intent.attempt_id,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeIncompleteAttemptMarker:
        return cls(**_validate_payload(payload, cls, cls._SCHEMA))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JudgeDispatchReconciliation:
    manifest_hash: str
    intent_hash: str
    item_id: str
    attempt_id: str
    decision: str
    provider_audit_hash: str
    response_bytes_hash: str | None
    checked_at: str
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-dispatch-reconciliation.v1"

    def __post_init__(self) -> None:
        for name in ("manifest_hash", "intent_hash", "provider_audit_hash"):
            _sha256(name, getattr(self, name))
        for name in ("item_id", "attempt_id", "checked_at"):
            _text(name, getattr(self, name))
        if self.decision not in _RECONCILIATION_DECISIONS:
            raise ValueError("reconciliation decision is outside the exact three outcomes")
        if self.decision == "recovered_response":
            _sha256("response_bytes_hash", self.response_bytes_hash)
        elif self.response_bytes_hash is not None:
            raise ValueError("only recovered_response may bind response bytes")
        _sha256("record_hash", self.record_hash)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("dispatch reconciliation hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return _record_payload(self, self._SCHEMA)

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        intent: JudgeDispatchIntent,
        decision: str,
        evidence: Mapping[str, object],
    ) -> JudgeDispatchReconciliation:
        required = {"provider_audit_hash", "checked_at"}
        if decision == "recovered_response":
            required.add("response_bytes_hash")
        if type(evidence) is not dict or set(evidence) != required:
            raise ValueError("reconciliation evidence fields differ from its decision")
        values = {
            "manifest_hash": intent.manifest_hash,
            "intent_hash": intent.record_hash,
            "item_id": intent.item_id,
            "attempt_id": intent.attempt_id,
            "decision": decision,
            "provider_audit_hash": evidence["provider_audit_hash"],
            "response_bytes_hash": evidence.get("response_bytes_hash"),
            "checked_at": evidence["checked_at"],
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(**values, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeDispatchReconciliation:
        return cls(**_validate_payload(payload, cls, cls._SCHEMA))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JudgeNegativeDispatchEvidence:
    """Externally verified evidence that no provider dispatch occurred."""

    manifest_hash: str
    intent_hash: str
    verifier_id: str
    observation_id: str
    provider_log_hash: str
    observed_at: str
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-negative-dispatch-evidence.v1"

    def __post_init__(self) -> None:
        for name in ("manifest_hash", "intent_hash", "provider_log_hash", "record_hash"):
            _sha256(name, getattr(self, name))
        for name in ("verifier_id", "observation_id", "observed_at"):
            _text(name, getattr(self, name))
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("negative dispatch evidence hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return _record_payload(self, self._SCHEMA)

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        intent: JudgeDispatchIntent,
        *,
        verifier_id: str,
        observation_id: str,
        provider_log_hash: str,
        observed_at: str,
    ) -> JudgeNegativeDispatchEvidence:
        values = {
            "manifest_hash": intent.manifest_hash,
            "intent_hash": intent.record_hash,
            "verifier_id": verifier_id,
            "observation_id": observation_id,
            "provider_log_hash": provider_log_hash,
            "observed_at": observed_at,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeNegativeDispatchEvidence:
        return cls(**_validate_payload(payload, cls, cls._SCHEMA))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JudgeCompletedAttempt:
    manifest_hash: str
    intent_hash: str
    item_id: str
    attempt_id: str
    request: JudgeRequestEvidence
    response: JudgeResponseEvidence
    parse: JudgeParseEvidence | None
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-completed-attempt.v1"

    def __post_init__(self) -> None:
        _sha256("manifest_hash", self.manifest_hash)
        _sha256("intent_hash", self.intent_hash)
        _text("item_id", self.item_id)
        _text("attempt_id", self.attempt_id)
        if not isinstance(self.request, JudgeRequestEvidence) or not isinstance(
            self.response, JudgeResponseEvidence
        ):
            raise TypeError("completed attempt requires typed request and response evidence")
        if self.response.request_hash != self.request.record_hash:
            raise ValueError("completed attempt response differs from exact request")
        if self.response.success:
            if not isinstance(self.parse, JudgeParseEvidence):
                raise ValueError("successful response requires exact parse evidence")
            if (
                self.response.output_bytes is None
                or self.parse.raw_bytes != self.response.output_bytes
            ):
                raise ValueError("parse evidence differs from exact provider output bytes")
        elif self.parse is not None:
            raise ValueError("transport failure cannot carry parse evidence")
        _sha256("record_hash", self.record_hash)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("completed attempt hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "manifest_hash": self.manifest_hash,
            "intent_hash": self.intent_hash,
            "item_id": self.item_id,
            "attempt_id": self.attempt_id,
            "request": self.request.to_payload(),
            "response": self.response.to_payload(),
            "parse": None if self.parse is None else self.parse.to_payload(),
            "metadata": dict(_METADATA),
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        intent: JudgeDispatchIntent,
        response: JudgeResponseEvidence,
        parse: JudgeParseEvidence | None,
    ) -> JudgeCompletedAttempt:
        values = {
            "manifest_hash": intent.manifest_hash,
            "intent_hash": intent.record_hash,
            "item_id": intent.item_id,
            "attempt_id": intent.attempt_id,
            "request": intent.request,
            "response": response,
            "parse": parse,
        }
        content = {
            "schema_version": cls._SCHEMA,
            **{
                name: value
                for name, value in values.items()
                if name not in {"request", "response", "parse"}
            },
            "request": intent.request.to_payload(),
            "response": response.to_payload(),
            "parse": None if parse is None else parse.to_payload(),
            "metadata": dict(_METADATA),
        }
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeCompletedAttempt:
        values = _validate_payload(payload, cls, cls._SCHEMA)
        if type(values["request"]) is not dict or type(values["response"]) is not dict:
            raise TypeError("completed attempt evidence must use JSON objects")
        values["request"] = JudgeRequestEvidence.from_payload(values["request"])
        values["response"] = JudgeResponseEvidence.from_payload(values["response"])
        if values["parse"] is not None:
            if type(values["parse"]) is not dict:
                raise TypeError("completed attempt parse must use a JSON object")
            values["parse"] = JudgeParseEvidence.from_payload(values["parse"])
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JudgeAttemptResolution:
    manifest_hash: str
    attempt_hash: str
    intent_hash: str
    item_id: str
    attempt_id: str
    outcome: str
    failure_code: str | None
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-attempt-resolution.v1"

    def __post_init__(self) -> None:
        for name in ("manifest_hash", "attempt_hash", "intent_hash", "record_hash"):
            _sha256(name, getattr(self, name))
        for name in ("item_id", "attempt_id"):
            _text(name, getattr(self, name))
        if self.outcome not in {"coded", "retryable_failed", "terminal_failed"}:
            raise ValueError("attempt resolution outcome is unsupported")
        if self.outcome == "coded" and self.failure_code is not None:
            raise ValueError("coded resolution cannot carry a failure code")
        if self.outcome != "coded":
            _text("failure_code", self.failure_code)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("attempt resolution hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return _record_payload(self, self._SCHEMA)

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        attempt: JudgeCompletedAttempt,
        *,
        outcome: str,
        failure_code: str | None,
    ) -> JudgeAttemptResolution:
        if outcome == "coded" and (attempt.parse is None or not attempt.parse.success):
            raise ValueError("coded resolution requires a successful exact parse")
        observed_failure = (
            attempt.response.failure_code
            if not attempt.response.success
            else None
            if attempt.parse is None
            else attempt.parse.failure_code
        )
        if outcome != "coded" and failure_code != observed_failure:
            raise ValueError("resolution failure differs from completed attempt evidence")
        values = {
            "manifest_hash": attempt.manifest_hash,
            "attempt_hash": attempt.record_hash,
            "intent_hash": attempt.intent_hash,
            "item_id": attempt.item_id,
            "attempt_id": attempt.attempt_id,
            "outcome": outcome,
            "failure_code": failure_code,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeAttemptResolution:
        return cls(**_validate_payload(payload, cls, cls._SCHEMA))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JudgeItemState:
    item_id: str
    item_hash: str
    order_index: int
    status: str
    attempt_count: int
    attempt_ids: tuple[str, ...]
    unresolved_intent_hash: str | None
    last_reconciliation_hash: str | None
    completed_attempt_hash: str | None
    resolution_hash: str | None
    last_error: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "item_hash": self.item_hash,
            "order_index": self.order_index,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "attempt_ids": list(self.attempt_ids),
            "unresolved_intent_hash": self.unresolved_intent_hash,
            "last_reconciliation_hash": self.last_reconciliation_hash,
            "completed_attempt_hash": self.completed_attempt_hash,
            "resolution_hash": self.resolution_hash,
            "last_error": self.last_error,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeItemState:
        expected = {
            "item_id",
            "item_hash",
            "order_index",
            "status",
            "attempt_count",
            "attempt_ids",
            "unresolved_intent_hash",
            "last_reconciliation_hash",
            "completed_attempt_hash",
            "resolution_hash",
            "last_error",
        }
        if (
            type(payload) is not dict
            or set(payload) != expected
            or type(payload["attempt_ids"]) is not list
        ):
            raise ValueError("judge item state requires exact fields")
        return cls(
            item_id=payload["item_id"],  # type: ignore[arg-type]
            item_hash=payload["item_hash"],  # type: ignore[arg-type]
            order_index=payload["order_index"],  # type: ignore[arg-type]
            status=payload["status"],  # type: ignore[arg-type]
            attempt_count=payload["attempt_count"],  # type: ignore[arg-type]
            attempt_ids=tuple(payload["attempt_ids"]),  # type: ignore[arg-type]
            unresolved_intent_hash=payload["unresolved_intent_hash"],  # type: ignore[arg-type]
            last_reconciliation_hash=payload["last_reconciliation_hash"],  # type: ignore[arg-type]
            completed_attempt_hash=payload["completed_attempt_hash"],  # type: ignore[arg-type]
            resolution_hash=payload["resolution_hash"],  # type: ignore[arg-type]
            last_error=payload["last_error"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class JudgeProjection:
    manifest_hash: str
    preflight_hash: str | None
    service_start_identity_hash: str | None
    sequence: int
    previous_projection_hash: str | None
    item_order: tuple[str, ...]
    item_states: Mapping[str, JudgeItemState]
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-projection.v1"

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            "manifest_hash": self.manifest_hash,
            "preflight_hash": self.preflight_hash,
            "service_start_identity_hash": self.service_start_identity_hash,
            "sequence": self.sequence,
            "previous_projection_hash": self.previous_projection_hash,
            "item_order": list(self.item_order),
            "item_states": {
                item_id: self.item_states[item_id].to_payload() for item_id in self.item_order
            },
            "metadata": dict(_METADATA),
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        *,
        manifest_hash: str,
        preflight_hash: str | None,
        service_start_identity_hash: str | None,
        sequence: int,
        previous_projection_hash: str | None,
        item_order: tuple[str, ...],
        item_states: Mapping[str, JudgeItemState],
    ) -> JudgeProjection:
        values = {
            "manifest_hash": manifest_hash,
            "preflight_hash": preflight_hash,
            "service_start_identity_hash": service_start_identity_hash,
            "sequence": sequence,
            "previous_projection_hash": previous_projection_hash,
            "item_order": item_order,
            "item_states": dict(item_states),
        }
        temporary = cls(**values, record_hash="0" * 64)
        return replace(temporary, record_hash=canonical_payload_hash(temporary.content_payload()))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeProjection:
        expected = {
            "schema_version",
            "manifest_hash",
            "preflight_hash",
            "service_start_identity_hash",
            "sequence",
            "previous_projection_hash",
            "item_order",
            "item_states",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("judge projection requires exact fields")
        if payload["schema_version"] != cls._SCHEMA or payload["metadata"] != _METADATA:
            raise ValueError("judge projection schema or metadata differs")
        if type(payload["item_order"]) is not list or type(payload["item_states"]) is not dict:
            raise TypeError("judge projection order and states require JSON containers")
        projection = cls(
            manifest_hash=payload["manifest_hash"],  # type: ignore[arg-type]
            preflight_hash=payload["preflight_hash"],  # type: ignore[arg-type]
            service_start_identity_hash=payload["service_start_identity_hash"],  # type: ignore[arg-type]
            sequence=payload["sequence"],  # type: ignore[arg-type]
            previous_projection_hash=payload["previous_projection_hash"],  # type: ignore[arg-type]
            item_order=tuple(payload["item_order"]),  # type: ignore[arg-type]
            item_states={
                item_id: JudgeItemState.from_payload(state)
                for item_id, state in payload["item_states"].items()
            },
            record_hash=payload["record_hash"],  # type: ignore[arg-type]
        )
        _sha256("manifest_hash", projection.manifest_hash)
        if projection.preflight_hash is not None:
            _sha256("preflight_hash", projection.preflight_hash)
        if projection.service_start_identity_hash is not None:
            _sha256("service_start_identity_hash", projection.service_start_identity_hash)
        _integer("sequence", projection.sequence)
        if projection.previous_projection_hash is not None:
            _sha256("previous_projection_hash", projection.previous_projection_hash)
        _sha256("record_hash", projection.record_hash)
        if projection.record_hash != canonical_payload_hash(projection.content_payload()):
            raise ValueError("judge projection hash differs from content")
        if set(projection.item_states) != set(projection.item_order):
            raise ValueError("judge projection state inventory differs from item order")
        return projection


def replay_judge_records(
    manifest: JudgeExecutionManifest,
    approved_order: JudgeApprovedOrder,
    records: tuple[object, ...],
) -> tuple[JudgeProjection, ...]:
    """Replay every append exactly, returning the full immutable projection chain."""

    states: dict[str, JudgeItemState] = {}
    item_order: list[str] = []
    preflight_hash: str | None = None
    service_start_identity_hash: str | None = None
    projection = JudgeProjection.create(
        manifest_hash=manifest.record_hash,
        preflight_hash=None,
        service_start_identity_hash=None,
        sequence=0,
        previous_projection_hash=None,
        item_order=(),
        item_states={},
    )
    projections = [projection]
    intents: dict[str, JudgeDispatchIntent] = {}
    audits: dict[str, JudgeProviderAuditRecord] = {}
    negative_evidence: dict[str, JudgeNegativeDispatchEvidence] = {}
    responses: dict[str, JudgeResponseEvidence] = {}
    attempts: dict[str, JudgeCompletedAttempt] = {}
    request_ids: set[str] = set()
    idempotency_keys: set[str] = set()
    attempt_ids: set[str] = set()
    for sequence, record in enumerate(records, 1):
        if isinstance(record, JudgePreflightEvidence):
            if preflight_hash is not None or record.record_hash != manifest.preflight_hash:
                raise ValueError("service preflight evidence differs from manifest")
            if record.authorization_hash != manifest.authorization_hash:
                raise ValueError("service preflight authorization differs from manifest")
            preflight_hash = record.record_hash
        elif isinstance(record, JudgeServiceEvidence):
            if (
                record.phase != "start"
                or service_start_identity_hash is not None
                or record.authorization_hash != manifest.authorization_hash
                or record.evidence_hash != manifest.service_start_identity_hash
            ):
                raise ValueError("service start evidence differs from manifest")
            service_start_identity_hash = record.evidence_hash
        elif getattr(record, "manifest_hash", None) != manifest.record_hash:
            raise ValueError("judge evidence manifest differs from store manifest")
        elif isinstance(record, JudgeDispatchIntent):
            if preflight_hash is None or service_start_identity_hash is None:
                raise ValueError(
                    "judge dispatch requires manifest-bound preflight and start evidence"
                )
            prior = states.get(record.item_id)
            if prior is None:
                if any(state.unresolved_intent_hash is not None for state in states.values()):
                    raise AmbiguousJudgeDispatchError(
                        "unresolved dispatch blocks the next approved item"
                    )
                if record.order_index != len(item_order):
                    raise ValueError("judge intents require contiguous approved item order")
                approved = approved_order.items[record.order_index]
                if (record.item_id, record.item_hash) != (
                    approved.item_id,
                    approved.item_hash,
                ):
                    raise ValueError("judge intent differs from manifest-bound approved order")
                if record.attempt_index != 1:
                    raise ValueError("first judge dispatch must use attempt index one")
                item_order.append(record.item_id)
                item_attempt_ids: tuple[str, ...] = ()
            else:
                if prior.status != "pending_retry" or prior.unresolved_intent_hash is not None:
                    raise ValueError("judge item is immutable or not authorized for retry")
                if record.order_index != prior.order_index or record.item_hash != prior.item_hash:
                    raise ValueError("judge retry changed immutable item identity")
                if record.attempt_index != prior.attempt_count + 1:
                    raise ValueError("judge retry attempt budget is not monotonic")
                item_attempt_ids = prior.attempt_ids
            if record.attempt_index > manifest.max_attempts_per_item:
                raise ValueError("judge dispatch exceeds manifest attempt budget")
            if record.request.rendered_request.renderer_hash != manifest.renderer_hash:
                raise ValueError("judge request renderer differs from manifest")
            if (
                record.record_hash in intents
                or record.attempt_id in attempt_ids
                or record.request_id in request_ids
                or record.idempotency_key in idempotency_keys
            ):
                raise ValueError("judge dispatch identity is duplicated")
            intents[record.record_hash] = record
            attempt_ids.add(record.attempt_id)
            request_ids.add(record.request_id)
            idempotency_keys.add(record.idempotency_key)
            states[record.item_id] = JudgeItemState(
                item_id=record.item_id,
                item_hash=record.item_hash,
                order_index=record.order_index,
                status="dispatch_unresolved",
                attempt_count=record.attempt_index,
                attempt_ids=(*item_attempt_ids, record.attempt_id),
                unresolved_intent_hash=record.record_hash,
                last_reconciliation_hash=(
                    None if prior is None else prior.last_reconciliation_hash
                ),
                completed_attempt_hash=None,
                resolution_hash=None,
                last_error=None,
            )
        elif isinstance(record, JudgeProviderAuditRecord):
            intent = intents.get(record.intent_hash)
            state = states.get(record.item_id)
            if (
                intent is None
                or state is None
                or state.unresolved_intent_hash != record.intent_hash
                or record.attempt_id != intent.attempt_id
                or record.request_id != intent.request_id
            ):
                raise ValueError("provider audit does not cover the unresolved intent")
            if record.intent_hash in audits:
                raise ValueError("provider audit is duplicated for one dispatch")
            audits[record.intent_hash] = record
        elif isinstance(record, JudgeNegativeDispatchEvidence):
            intent = intents.get(record.intent_hash)
            state = states.get(intent.item_id) if intent is not None else None
            if (
                intent is None
                or state is None
                or state.unresolved_intent_hash != record.intent_hash
            ):
                raise ValueError("negative dispatch evidence does not cover unresolved intent")
            if record.intent_hash in negative_evidence:
                raise ValueError("negative dispatch evidence is duplicated")
            negative_evidence[record.intent_hash] = record
        elif isinstance(record, JudgeResponseEvidence):
            matching = tuple(
                intent
                for intent in intents.values()
                if intent.request_hash == record.request_hash
                and intent.request_id == record.request_id
            )
            if len(matching) != 1:
                raise ValueError("judge response does not uniquely cover a dispatch request")
            intent = matching[0]
            state = states[intent.item_id]
            if state.unresolved_intent_hash != intent.record_hash:
                raise ValueError("judge response does not cover unresolved dispatch")
            if intent.record_hash in responses:
                raise ValueError("judge response is duplicated for one dispatch")
            responses[intent.record_hash] = record
        elif isinstance(record, JudgeCompletedAttempt):
            intent = intents.get(record.intent_hash)
            response = responses.get(record.intent_hash)
            state = states.get(record.item_id)
            if (
                intent is None
                or response is None
                or state is None
                or state.unresolved_intent_hash != record.intent_hash
                or record.request != intent.request
                or record.response != response
                or record.attempt_id != intent.attempt_id
            ):
                raise ValueError("completed attempt lacks exact request/response coverage")
            if record.intent_hash in attempts:
                raise ValueError("completed attempt is duplicated")
            attempts[record.intent_hash] = record
            states[record.item_id] = replace(state, completed_attempt_hash=record.record_hash)
        elif isinstance(record, JudgeIncompleteAttemptMarker):
            intent = intents.get(record.intent_hash)
            state = states.get(record.item_id)
            if (
                intent is None
                or state is None
                or state.unresolved_intent_hash != record.intent_hash
            ):
                raise ValueError("attempt marker does not cover the unresolved dispatch")
            if record.attempt_id != intent.attempt_id:
                raise ValueError("attempt marker identity differs from dispatch")
        elif isinstance(record, JudgeDispatchReconciliation):
            intent = intents.get(record.intent_hash)
            state = states.get(record.item_id)
            if (
                intent is None
                or state is None
                or state.unresolved_intent_hash != record.intent_hash
                or record.attempt_id != intent.attempt_id
            ):
                raise ValueError("reconciliation does not cover the unresolved dispatch")
            audit = audits.get(record.intent_hash)
            if record.decision == "recovered_response":
                if (
                    audit is None
                    or audit.provider_audit_hash != record.provider_audit_hash
                    or audit.response_bytes_hash != record.response_bytes_hash
                ):
                    raise ValueError("recovered response lacks exact provider audit evidence")
                status = "recovered_response"
            elif record.decision == "proved_not_sent":
                negative = negative_evidence.get(record.intent_hash)
                if (
                    audit is not None
                    or negative is None
                    or negative.record_hash != record.provider_audit_hash
                ):
                    raise ValueError("proved_not_sent contradicts persisted response evidence")
                status = "pending_retry"
            else:
                status = "ambiguous_incomplete"
            states[record.item_id] = replace(
                state,
                status=status,
                unresolved_intent_hash=(
                    record.intent_hash if record.decision == "recovered_response" else None
                ),
                last_reconciliation_hash=record.record_hash,
            )
        elif isinstance(record, JudgeAttemptResolution):
            attempt = attempts.get(record.intent_hash)
            state = states.get(record.item_id)
            if (
                attempt is None
                or state is None
                or state.unresolved_intent_hash != record.intent_hash
                or record.attempt_hash != attempt.record_hash
                or record.attempt_id != attempt.attempt_id
            ):
                raise ValueError("attempt resolution lacks exact completed attempt coverage")
            if record.outcome == "coded":
                status = "coded"
            elif record.outcome == "terminal_failed":
                status = "terminal_failed"
            else:
                if state.attempt_count >= manifest.max_attempts_per_item:
                    raise ValueError("retryable resolution exceeds manifest attempt budget")
                status = "pending_retry"
            states[record.item_id] = replace(
                state,
                status=status,
                unresolved_intent_hash=None,
                resolution_hash=record.record_hash,
                last_error=record.failure_code,
            )
        else:
            raise TypeError("unsupported judge replay record")
        projection = JudgeProjection.create(
            manifest_hash=manifest.record_hash,
            preflight_hash=preflight_hash,
            service_start_identity_hash=service_start_identity_hash,
            sequence=sequence,
            previous_projection_hash=projection.record_hash,
            item_order=tuple(item_order),
            item_states=states,
        )
        projections.append(projection)
    return tuple(projections)


def reconstruct_judge_projection(store: JudgeRunStore) -> JudgeProjection:
    projections = replay_judge_records(store.manifest, store.approved_order, store.read_records())
    projection = projections[-1]
    unresolved = tuple(
        item_id
        for item_id in projection.item_order
        if projection.item_states[item_id].unresolved_intent_hash is not None
    )
    if unresolved:
        raise AmbiguousJudgeDispatchError(
            "unresolved dispatch requires typed reconciliation: " + ", ".join(unresolved)
        )
    return projection


def reconcile_from_provider_log(
    store: JudgeRunStore,
    intent: JudgeDispatchIntent,
    provider_audit: Mapping[str, object],
) -> JudgeDispatchReconciliation:
    audit = store.append_raw_provider_audit(intent, provider_audit)
    reconciliation = JudgeDispatchReconciliation.create(
        intent,
        "recovered_response",
        {
            "provider_audit_hash": audit.provider_audit_hash,
            "response_bytes_hash": audit.response_bytes_hash,
            "checked_at": audit.checked_at,
        },
    )
    store.append_reconciliation(reconciliation)
    return reconciliation


def reconcile_proved_not_sent(
    store: JudgeRunStore,
    intent: JudgeDispatchIntent,
    evidence: JudgeNegativeDispatchEvidence,
) -> JudgeDispatchReconciliation:
    if (
        not isinstance(evidence, JudgeNegativeDispatchEvidence)
        or evidence.intent_hash != intent.record_hash
        or evidence.manifest_hash != intent.manifest_hash
    ):
        raise ValueError("proved_not_sent requires exact external negative provider evidence")
    store.append_negative_dispatch_evidence(evidence)
    reconciliation = JudgeDispatchReconciliation.create(
        intent,
        "proved_not_sent",
        {"provider_audit_hash": evidence.record_hash, "checked_at": evidence.observed_at},
    )
    store.append_reconciliation(reconciliation)
    return reconciliation


def build_retry_after_not_sent(
    intent: JudgeDispatchIntent,
    reconciliation: JudgeDispatchReconciliation,
    request: JudgeRequestEvidence,
) -> JudgeDispatchIntent:
    if (
        reconciliation.decision != "proved_not_sent"
        or reconciliation.intent_hash != intent.record_hash
    ):
        raise ValueError("retry requires proved_not_sent for the exact dispatch intent")
    next_index = intent.attempt_index + 1
    rendered = request.rendered_request
    if (
        request.manifest_hash != intent.manifest_hash
        or request.order_index != intent.order_index
        or rendered.item_id != intent.item_id
        or rendered.item_hash != intent.item_hash
        or rendered.attempt_index != next_index
        or rendered.request_id == intent.request_id
        or rendered.idempotency_key == intent.idempotency_key
    ):
        raise ValueError("retry request does not match exact next rendered attempt")
    return JudgeDispatchIntent.create(
        request=request,
        created_at=reconciliation.checked_at,
    )
