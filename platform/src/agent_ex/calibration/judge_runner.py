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
    request_hash: str
    request_id: str
    idempotency_key: str
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
        _sha256("request_hash", self.request_hash)
        _text("request_id", self.request_id)
        _text("idempotency_key", self.idempotency_key)
        _text("created_at", self.created_at)
        _sha256("record_hash", self.record_hash)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("judge dispatch intent hash differs from content")

    def content_payload(self) -> dict[str, object]:
        return _record_payload(self, self._SCHEMA)

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        *,
        manifest_hash: str,
        item_id: str,
        item_hash: str,
        order_index: int,
        attempt_index: int,
        request_hash: str,
        request_id: str,
        idempotency_key: str,
        created_at: str,
    ) -> JudgeDispatchIntent:
        attempt_identity = canonical_payload_hash(
            {
                "manifest_hash": manifest_hash,
                "item_id": item_id,
                "item_hash": item_hash,
                "order_index": order_index,
                "attempt_index": attempt_index,
                "request_hash": request_hash,
                "request_id": request_id,
                "idempotency_key": idempotency_key,
            }
        )
        values = {
            "manifest_hash": manifest_hash,
            "item_id": item_id,
            "item_hash": item_hash,
            "order_index": order_index,
            "attempt_index": attempt_index,
            "attempt_id": f"judge-attempt-{attempt_identity}",
            "request_hash": request_hash,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "created_at": created_at,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeDispatchIntent:
        return cls(**_validate_payload(payload, cls, cls._SCHEMA))  # type: ignore[arg-type]


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
class JudgeItemState:
    item_id: str
    item_hash: str
    order_index: int
    status: str
    attempt_count: int
    attempt_ids: tuple[str, ...]
    unresolved_intent_hash: str | None
    last_reconciliation_hash: str | None

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
        )


@dataclass(frozen=True, slots=True)
class JudgeProjection:
    manifest_hash: str
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
        sequence: int,
        previous_projection_hash: str | None,
        item_order: tuple[str, ...],
        item_states: Mapping[str, JudgeItemState],
    ) -> JudgeProjection:
        values = {
            "manifest_hash": manifest_hash,
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
    manifest_hash: str,
    records: tuple[object, ...],
) -> tuple[JudgeProjection, ...]:
    """Replay every append exactly, returning the full immutable projection chain."""

    states: dict[str, JudgeItemState] = {}
    item_order: list[str] = []
    projection = JudgeProjection.create(
        manifest_hash=manifest_hash,
        sequence=0,
        previous_projection_hash=None,
        item_order=(),
        item_states={},
    )
    projections = [projection]
    intents: dict[str, JudgeDispatchIntent] = {}
    audits: dict[str, JudgeProviderAuditRecord] = {}
    for sequence, record in enumerate(records, 1):
        if getattr(record, "manifest_hash", None) != manifest_hash:
            raise ValueError("judge evidence manifest differs from store manifest")
        if isinstance(record, JudgeDispatchIntent):
            prior = states.get(record.item_id)
            if prior is None:
                if any(state.unresolved_intent_hash is not None for state in states.values()):
                    raise AmbiguousJudgeDispatchError(
                        "unresolved dispatch blocks the next approved item"
                    )
                if record.order_index != len(item_order):
                    raise ValueError("judge intents require contiguous approved item order")
                if record.attempt_index != 1:
                    raise ValueError("first judge dispatch must use attempt index one")
                item_order.append(record.item_id)
                attempts: tuple[str, ...] = ()
            else:
                if prior.status != "pending_retry" or prior.unresolved_intent_hash is not None:
                    raise ValueError("judge item is immutable or not authorized for retry")
                if record.order_index != prior.order_index or record.item_hash != prior.item_hash:
                    raise ValueError("judge retry changed immutable item identity")
                if record.attempt_index != prior.attempt_count + 1:
                    raise ValueError("judge retry attempt budget is not monotonic")
                attempts = prior.attempt_ids
            if record.record_hash in intents or record.attempt_id in {
                attempt for state in states.values() for attempt in state.attempt_ids
            }:
                raise ValueError("judge dispatch identity is duplicated")
            intents[record.record_hash] = record
            states[record.item_id] = JudgeItemState(
                item_id=record.item_id,
                item_hash=record.item_hash,
                order_index=record.order_index,
                status="dispatch_unresolved",
                attempt_count=record.attempt_index,
                attempt_ids=(*attempts, record.attempt_id),
                unresolved_intent_hash=record.record_hash,
                last_reconciliation_hash=(
                    None if prior is None else prior.last_reconciliation_hash
                ),
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
                if audit is not None:
                    raise ValueError("proved_not_sent contradicts persisted response evidence")
                status = "pending_retry"
            else:
                status = "ambiguous_incomplete"
            states[record.item_id] = replace(
                state,
                status=status,
                unresolved_intent_hash=None,
                last_reconciliation_hash=record.record_hash,
            )
        else:
            raise TypeError("unsupported judge replay record")
        projection = JudgeProjection.create(
            manifest_hash=manifest_hash,
            sequence=sequence,
            previous_projection_hash=projection.record_hash,
            item_order=tuple(item_order),
            item_states=states,
        )
        projections.append(projection)
    return tuple(projections)


def reconstruct_judge_projection(store: JudgeRunStore) -> JudgeProjection:
    projections = replay_judge_records(store.manifest.record_hash, store.read_records())
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
    store: JudgeRunStore, intent: JudgeDispatchIntent
) -> JudgeDispatchReconciliation:
    evidence = {
        "provider_audit_hash": canonical_payload_hash(
            {"intent_hash": intent.record_hash, "decision": "proved_not_sent"}
        ),
        "checked_at": intent.created_at,
    }
    reconciliation = JudgeDispatchReconciliation.create(intent, "proved_not_sent", evidence)
    store.append_reconciliation(reconciliation)
    return reconciliation


def build_retry_after_not_sent(
    intent: JudgeDispatchIntent,
    reconciliation: JudgeDispatchReconciliation,
) -> JudgeDispatchIntent:
    if (
        reconciliation.decision != "proved_not_sent"
        or reconciliation.intent_hash != intent.record_hash
    ):
        raise ValueError("retry requires proved_not_sent for the exact dispatch intent")
    next_index = intent.attempt_index + 1
    retry_identity = canonical_payload_hash(
        {
            "prior_intent_hash": intent.record_hash,
            "reconciliation_hash": reconciliation.record_hash,
            "attempt_index": next_index,
        }
    )
    return JudgeDispatchIntent.create(
        manifest_hash=intent.manifest_hash,
        item_id=intent.item_id,
        item_hash=intent.item_hash,
        order_index=intent.order_index,
        attempt_index=next_index,
        request_hash=canonical_payload_hash(
            {"prior_request_hash": intent.request_hash, "attempt_index": next_index}
        ),
        request_id=f"judge-request-{retry_identity}",
        idempotency_key=f"judge-idempotency-{retry_identity}",
        created_at=reconciliation.checked_at,
    )
