"""Immutable mock private/public state records for Paper 1 Phase 4B-6."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .domain import (
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
)
from .topic import TopicPackage


_STATE_SCHEMA_VERSION = "paper1.mock-state.v1"
_MOCK_METADATA = {"mock_only": True, "research_parameter_status": "not_frozen"}


def _require_mock_only(mock_only: bool) -> None:
    if mock_only is not True:
        raise ValueError("Phase 4B-6 state records must be explicitly mock_only")


def _strict_optional_int(name: str, value: object, *, minimum: int = 0) -> None:
    if value is not None:
        _require_int(name, value, minimum=minimum)


def _strict_optional_id(name: str, value: object) -> None:
    if value is not None:
        _require_id(name, value)


def _metadata_from_payload(payload: object) -> None:
    if type(payload) is not dict or payload != _MOCK_METADATA:
        raise ValueError("state record metadata must remain mock_only and not_frozen")


def _derive_id(prefix: str, payload: Mapping[str, object]) -> str:
    return prefix + canonical_payload_hash(payload)


@dataclass(frozen=True, slots=True)
class PrivateUpdate:
    """One successful private update; unpublished content remains private evidence."""

    update_id: str
    topic_package_id: str
    topic_package_hash: str
    matched_seed: int
    agent_id: str
    event_id: str | None
    event_ordinal: int | None
    sequence_index: int
    stance_label: str
    reason: str
    confidence: int | None
    published: bool
    source_attempt_id: str | None
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_id("update_id", self.update_id)
        _require_id("topic_package_id", self.topic_package_id)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_int("matched_seed", self.matched_seed)
        _require_id("agent_id", self.agent_id)
        _strict_optional_id("event_id", self.event_id)
        _strict_optional_int("event_ordinal", self.event_ordinal)
        _require_int("sequence_index", self.sequence_index)
        _require_string("stance_label", self.stance_label)
        _require_string("reason", self.reason)
        _strict_optional_int("confidence", self.confidence, minimum=1)
        if self.confidence is not None and self.confidence > 5:
            raise ValueError("confidence must be between 1 and 5")
        if not isinstance(self.published, bool):
            raise TypeError("published must be a boolean")
        _strict_optional_id("source_attempt_id", self.source_attempt_id)
        if self.event_ordinal is None:
            if self.event_id is not None or self.source_attempt_id is not None:
                raise ValueError("round-0 private update cannot bind an event or attempt")
            if self.sequence_index != 0 or self.confidence is not None:
                raise ValueError("round-0 private update must use sequence 0 and no confidence")
            if self.published is not True:
                raise ValueError("round-0 private update must be published")
        elif self.event_id is None or self.source_attempt_id is None or self.sequence_index < 1:
            raise ValueError("event private update requires event, attempt, and positive sequence")
        expected_id = _derive_id("private-update-", self.identity_payload())
        if self.update_id != expected_id:
            raise ValueError("update_id does not match private update identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_MOCK_METADATA)

    def identity_payload(self) -> dict[str, object]:
        return {
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "agent_id": self.agent_id,
            "event_id": self.event_id,
            "event_ordinal": self.event_ordinal,
            "sequence_index": self.sequence_index,
        }

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _STATE_SCHEMA_VERSION,
            "update_id": self.update_id,
            **self.identity_payload(),
            "stance_label": self.stance_label,
            "reason": self.reason,
            "confidence": self.confidence,
            "published": self.published,
            "source_attempt_id": self.source_attempt_id,
            "metadata": self.metadata,
        }

    @classmethod
    def create(
        cls,
        *,
        topic_package: TopicPackage,
        matched_seed: int,
        agent_id: str,
        event_id: str | None,
        event_ordinal: int | None,
        sequence_index: int,
        stance_label: str,
        reason: str,
        confidence: int | None,
        published: bool,
        source_attempt_id: str | None,
        mock_only: bool,
    ) -> PrivateUpdate:
        _require_mock_only(mock_only)
        if not isinstance(topic_package, TopicPackage):
            raise TypeError("topic_package must be a TopicPackage")
        if stance_label not in topic_package.stance_labels:
            raise ValueError("stance_label must be one of the topic package's seven text labels")
        identity = {
            "topic_package_id": topic_package.topic_id,
            "topic_package_hash": topic_package.package_hash,
            "matched_seed": matched_seed,
            "agent_id": agent_id,
            "event_id": event_id,
            "event_ordinal": event_ordinal,
            "sequence_index": sequence_index,
        }
        update_id = _derive_id("private-update-", identity)
        content = {
            "schema_version": _STATE_SCHEMA_VERSION,
            "update_id": update_id,
            **identity,
            "stance_label": stance_label,
            "reason": reason,
            "confidence": confidence,
            "published": published,
            "source_attempt_id": source_attempt_id,
            "metadata": dict(_MOCK_METADATA),
        }
        return cls(
            update_id=update_id,
            topic_package_id=topic_package.topic_id,
            topic_package_hash=topic_package.package_hash,
            matched_seed=matched_seed,
            agent_id=agent_id,
            event_id=event_id,
            event_ordinal=event_ordinal,
            sequence_index=sequence_index,
            stance_label=stance_label,
            reason=reason,
            confidence=confidence,
            published=published,
            source_attempt_id=source_attempt_id,
            record_hash=canonical_payload_hash(content),
        )

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PrivateUpdate:
        expected = {
            "schema_version",
            "update_id",
            "topic_package_id",
            "topic_package_hash",
            "matched_seed",
            "agent_id",
            "event_id",
            "event_ordinal",
            "sequence_index",
            "stance_label",
            "reason",
            "confidence",
            "published",
            "source_attempt_id",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("private update payload fields do not match the v1 contract")
        _require_json_transport(payload, "private update payload")
        if payload["schema_version"] != _STATE_SCHEMA_VERSION:
            raise ValueError("private update schema_version is not supported")
        _metadata_from_payload(payload["metadata"])
        return cls(
            update_id=payload["update_id"],  # type: ignore[arg-type]
            topic_package_id=payload["topic_package_id"],  # type: ignore[arg-type]
            topic_package_hash=payload["topic_package_hash"],  # type: ignore[arg-type]
            matched_seed=payload["matched_seed"],  # type: ignore[arg-type]
            agent_id=payload["agent_id"],  # type: ignore[arg-type]
            event_id=payload["event_id"],  # type: ignore[arg-type]
            event_ordinal=payload["event_ordinal"],  # type: ignore[arg-type]
            sequence_index=payload["sequence_index"],  # type: ignore[arg-type]
            stance_label=payload["stance_label"],  # type: ignore[arg-type]
            reason=payload["reason"],  # type: ignore[arg-type]
            confidence=payload["confidence"],  # type: ignore[arg-type]
            published=payload["published"],  # type: ignore[arg-type]
            source_attempt_id=payload["source_attempt_id"],  # type: ignore[arg-type]
            record_hash=payload["record_hash"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class PrivateState:
    """Current private-state pointer; private history remains append-only elsewhere."""

    state_id: str
    topic_package_id: str
    topic_package_hash: str
    matched_seed: int
    agent_id: str
    latest_update_id: str
    latest_update_hash: str
    successful_update_count: int
    event_ordinal: int | None
    stance_label: str
    reason: str
    confidence: int | None
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("state_id", "agent_id", "latest_update_id"):
            _require_id(name, getattr(self, name))
        _require_id("topic_package_id", self.topic_package_id)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_int("matched_seed", self.matched_seed)
        _require_sha256("latest_update_hash", self.latest_update_hash)
        _require_int("successful_update_count", self.successful_update_count, minimum=1)
        _strict_optional_int("event_ordinal", self.event_ordinal)
        _require_string("stance_label", self.stance_label)
        _require_string("reason", self.reason)
        _strict_optional_int("confidence", self.confidence, minimum=1)
        if self.confidence is not None and self.confidence > 5:
            raise ValueError("confidence must be between 1 and 5")
        expected = _derive_id(
            "private-state-",
            {
                "matched_seed": self.matched_seed,
                "topic_package_id": self.topic_package_id,
                "agent_id": self.agent_id,
                "latest_update_id": self.latest_update_id,
                "successful_update_count": self.successful_update_count,
            },
        )
        if self.state_id != expected:
            raise ValueError("state_id does not match private state identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_MOCK_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _STATE_SCHEMA_VERSION,
            "state_id": self.state_id,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "agent_id": self.agent_id,
            "latest_update_id": self.latest_update_id,
            "latest_update_hash": self.latest_update_hash,
            "successful_update_count": self.successful_update_count,
            "event_ordinal": self.event_ordinal,
            "stance_label": self.stance_label,
            "reason": self.reason,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_update(
        cls,
        update: PrivateUpdate,
        *,
        previous: PrivateState | None,
        mock_only: bool,
    ) -> PrivateState:
        _require_mock_only(mock_only)
        if not isinstance(update, PrivateUpdate):
            raise TypeError("update must be a PrivateUpdate")
        if previous is None:
            if update.sequence_index != 0:
                raise ValueError("initial private state must be built from sequence 0")
            count = 1
        else:
            if not isinstance(previous, PrivateState):
                raise TypeError("previous must be a PrivateState or None")
            if previous.agent_id != update.agent_id:
                raise ValueError("private state and update agent must match")
            if previous.matched_seed != update.matched_seed:
                raise ValueError("private state and update matched seed must match")
            if (
                previous.topic_package_id != update.topic_package_id
                or previous.topic_package_hash != update.topic_package_hash
            ):
                raise ValueError("private state and update topic package must match")
            if update.sequence_index != previous.successful_update_count:
                raise ValueError("private update sequence must be the next successful update")
            if update.event_ordinal is None or (
                previous.event_ordinal is not None
                and update.event_ordinal <= previous.event_ordinal
            ):
                raise ValueError("private update event ordinal must advance")
            count = previous.successful_update_count + 1
        state_id = _derive_id(
            "private-state-",
            {
                "matched_seed": update.matched_seed,
                "topic_package_id": update.topic_package_id,
                "agent_id": update.agent_id,
                "latest_update_id": update.update_id,
                "successful_update_count": count,
            },
        )
        content = {
            "schema_version": _STATE_SCHEMA_VERSION,
            "state_id": state_id,
            "topic_package_id": update.topic_package_id,
            "topic_package_hash": update.topic_package_hash,
            "matched_seed": update.matched_seed,
            "agent_id": update.agent_id,
            "latest_update_id": update.update_id,
            "latest_update_hash": update.record_hash,
            "successful_update_count": count,
            "event_ordinal": update.event_ordinal,
            "stance_label": update.stance_label,
            "reason": update.reason,
            "confidence": update.confidence,
            "metadata": dict(_MOCK_METADATA),
        }
        return cls(
            record_hash=canonical_payload_hash(content),
            **{
                key: value
                for key, value in content.items()
                if key not in {"schema_version", "metadata"}
            },
        )  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PrivateState:
        expected = {
            "schema_version",
            "state_id",
            "topic_package_id",
            "topic_package_hash",
            "matched_seed",
            "agent_id",
            "latest_update_id",
            "latest_update_hash",
            "successful_update_count",
            "event_ordinal",
            "stance_label",
            "reason",
            "confidence",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("private state payload fields do not match the v1 contract")
        _require_json_transport(payload, "private state payload")
        if payload["schema_version"] != _STATE_SCHEMA_VERSION:
            raise ValueError("private state schema_version is not supported")
        _metadata_from_payload(payload["metadata"])
        return cls(**{key: payload[key] for key in expected - {"schema_version", "metadata"}})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class PublicPost:
    """Public-only message derived from a successful update with publish_flag=true."""

    post_id: str
    topic_package_id: str
    topic_package_hash: str
    matched_seed: int
    author_agent_id: str
    source_update_id: str
    source_update_hash: str
    source_event_id: str | None
    published_event_ordinal: int | None
    stance_label: str
    public_reason: str
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("post_id", "author_agent_id", "source_update_id"):
            _require_id(name, getattr(self, name))
        _require_id("topic_package_id", self.topic_package_id)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_int("matched_seed", self.matched_seed)
        _require_sha256("source_update_hash", self.source_update_hash)
        _strict_optional_id("source_event_id", self.source_event_id)
        _strict_optional_int("published_event_ordinal", self.published_event_ordinal)
        if (self.source_event_id is None) != (self.published_event_ordinal is None):
            raise ValueError("source_event_id and published_event_ordinal must be a pair")
        _require_string("stance_label", self.stance_label)
        _require_string("public_reason", self.public_reason)
        identity = {
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "author_agent_id": self.author_agent_id,
            "source_update_id": self.source_update_id,
            "source_event_id": self.source_event_id,
            "published_event_ordinal": self.published_event_ordinal,
        }
        if self.post_id != _derive_id("public-post-", identity):
            raise ValueError("post_id does not match public post identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_MOCK_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _STATE_SCHEMA_VERSION,
            "post_id": self.post_id,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "author_agent_id": self.author_agent_id,
            "source_update_id": self.source_update_id,
            "source_update_hash": self.source_update_hash,
            "source_event_id": self.source_event_id,
            "published_event_ordinal": self.published_event_ordinal,
            "stance_label": self.stance_label,
            "public_reason": self.public_reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_private_update(cls, update: PrivateUpdate, *, mock_only: bool) -> PublicPost:
        _require_mock_only(mock_only)
        if not isinstance(update, PrivateUpdate):
            raise TypeError("update must be a PrivateUpdate")
        if update.published is not True:
            raise ValueError("public post requires a published private update")
        identity = {
            "topic_package_id": update.topic_package_id,
            "topic_package_hash": update.topic_package_hash,
            "matched_seed": update.matched_seed,
            "author_agent_id": update.agent_id,
            "source_update_id": update.update_id,
            "source_event_id": update.event_id,
            "published_event_ordinal": update.event_ordinal,
        }
        post_id = _derive_id("public-post-", identity)
        content = {
            "schema_version": _STATE_SCHEMA_VERSION,
            "post_id": post_id,
            **identity,
            "source_update_hash": update.record_hash,
            "stance_label": update.stance_label,
            "public_reason": update.reason,
            "metadata": dict(_MOCK_METADATA),
        }
        return cls(
            post_id=post_id,
            topic_package_id=update.topic_package_id,
            topic_package_hash=update.topic_package_hash,
            matched_seed=update.matched_seed,
            author_agent_id=update.agent_id,
            source_update_id=update.update_id,
            source_update_hash=update.record_hash,
            source_event_id=update.event_id,
            published_event_ordinal=update.event_ordinal,
            stance_label=update.stance_label,
            public_reason=update.reason,
            record_hash=canonical_payload_hash(content),
        )

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PublicPost:
        expected = {
            "schema_version",
            "post_id",
            "topic_package_id",
            "topic_package_hash",
            "matched_seed",
            "author_agent_id",
            "source_update_id",
            "source_update_hash",
            "source_event_id",
            "published_event_ordinal",
            "stance_label",
            "public_reason",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("public post payload fields do not match the v1 contract")
        _require_json_transport(payload, "public post payload")
        if payload["schema_version"] != _STATE_SCHEMA_VERSION:
            raise ValueError("public post schema_version is not supported")
        _metadata_from_payload(payload["metadata"])
        return cls(**{key: payload[key] for key in expected - {"schema_version", "metadata"}})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class LatestPublicPointer:
    """A hash-bound pointer to an agent's latest public post stock."""

    pointer_id: str
    topic_package_id: str
    topic_package_hash: str
    matched_seed: int
    agent_id: str
    latest_post_id: str
    latest_post_hash: str
    published_event_ordinal: int | None
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("pointer_id", "agent_id", "latest_post_id"):
            _require_id(name, getattr(self, name))
        _require_id("topic_package_id", self.topic_package_id)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_int("matched_seed", self.matched_seed)
        _require_sha256("latest_post_hash", self.latest_post_hash)
        _strict_optional_int("published_event_ordinal", self.published_event_ordinal)
        identity = {
            "matched_seed": self.matched_seed,
            "topic_package_id": self.topic_package_id,
            "agent_id": self.agent_id,
            "latest_post_id": self.latest_post_id,
        }
        if self.pointer_id != _derive_id("latest-public-", identity):
            raise ValueError("pointer_id does not match latest public identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_MOCK_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _STATE_SCHEMA_VERSION,
            "pointer_id": self.pointer_id,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "agent_id": self.agent_id,
            "latest_post_id": self.latest_post_id,
            "latest_post_hash": self.latest_post_hash,
            "published_event_ordinal": self.published_event_ordinal,
            "metadata": self.metadata,
        }

    @classmethod
    def from_post(
        cls,
        post: PublicPost,
        *,
        previous: LatestPublicPointer | None,
        mock_only: bool,
    ) -> LatestPublicPointer:
        _require_mock_only(mock_only)
        if not isinstance(post, PublicPost):
            raise TypeError("post must be a PublicPost")
        if previous is not None:
            if not isinstance(previous, LatestPublicPointer):
                raise TypeError("previous must be a LatestPublicPointer or None")
            if previous.agent_id != post.author_agent_id:
                raise ValueError("latest public pointer and post agent must match")
            if previous.matched_seed != post.matched_seed:
                raise ValueError("latest public pointer and post matched seed must match")
            if (
                previous.topic_package_id != post.topic_package_id
                or previous.topic_package_hash != post.topic_package_hash
            ):
                raise ValueError("latest public pointer and post topic package must match")
            if post.published_event_ordinal is None or (
                previous.published_event_ordinal is not None
                and post.published_event_ordinal <= previous.published_event_ordinal
            ):
                raise ValueError("latest public post event ordinal must advance")
        identity = {
            "matched_seed": post.matched_seed,
            "topic_package_id": post.topic_package_id,
            "agent_id": post.author_agent_id,
            "latest_post_id": post.post_id,
        }
        pointer_id = _derive_id("latest-public-", identity)
        content = {
            "schema_version": _STATE_SCHEMA_VERSION,
            "pointer_id": pointer_id,
            **identity,
            "topic_package_hash": post.topic_package_hash,
            "latest_post_hash": post.record_hash,
            "published_event_ordinal": post.published_event_ordinal,
            "metadata": dict(_MOCK_METADATA),
        }
        return cls(
            pointer_id=pointer_id,
            topic_package_id=post.topic_package_id,
            topic_package_hash=post.topic_package_hash,
            matched_seed=post.matched_seed,
            agent_id=post.author_agent_id,
            latest_post_id=post.post_id,
            latest_post_hash=post.record_hash,
            published_event_ordinal=post.published_event_ordinal,
            record_hash=canonical_payload_hash(content),
        )

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> LatestPublicPointer:
        expected = {
            "schema_version",
            "pointer_id",
            "topic_package_id",
            "topic_package_hash",
            "matched_seed",
            "agent_id",
            "latest_post_id",
            "latest_post_hash",
            "published_event_ordinal",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("latest public pointer payload fields do not match the v1 contract")
        _require_json_transport(payload, "latest public pointer payload")
        if payload["schema_version"] != _STATE_SCHEMA_VERSION:
            raise ValueError("latest public pointer schema_version is not supported")
        _metadata_from_payload(payload["metadata"])
        return cls(**{key: payload[key] for key in expected - {"schema_version", "metadata"}})  # type: ignore[arg-type]


def _validate_update_topic(update: PrivateUpdate, topic_package: TopicPackage) -> None:
    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be a TopicPackage")
    if (
        update.topic_package_id != topic_package.topic_id
        or update.topic_package_hash != topic_package.package_hash
        or update.stance_label not in topic_package.stance_labels
    ):
        raise ValueError("private update topic package or stance_label does not match")


def validate_private_state(
    state: PrivateState,
    latest_update: PrivateUpdate,
    topic_package: TopicPackage,
) -> None:
    """Replay the latest successful update into an exact current private state."""

    if not isinstance(state, PrivateState) or not isinstance(latest_update, PrivateUpdate):
        raise TypeError("private state validation requires typed state and update records")
    _validate_update_topic(latest_update, topic_package)
    expected_fields = {
        "matched_seed": latest_update.matched_seed,
        "topic_package_id": latest_update.topic_package_id,
        "topic_package_hash": latest_update.topic_package_hash,
        "agent_id": latest_update.agent_id,
        "latest_update_id": latest_update.update_id,
        "latest_update_hash": latest_update.record_hash,
        "successful_update_count": latest_update.sequence_index + 1,
        "event_ordinal": latest_update.event_ordinal,
        "stance_label": latest_update.stance_label,
        "reason": latest_update.reason,
        "confidence": latest_update.confidence,
    }
    if any(getattr(state, name) != value for name, value in expected_fields.items()):
        raise ValueError("private state replay does not match its latest source update")
    expected_id = _derive_id(
        "private-state-",
        {
            "matched_seed": latest_update.matched_seed,
            "topic_package_id": latest_update.topic_package_id,
            "agent_id": latest_update.agent_id,
            "latest_update_id": latest_update.update_id,
            "successful_update_count": latest_update.sequence_index + 1,
        },
    )
    if state.state_id != expected_id or state.record_hash != canonical_payload_hash(
        state.content_payload()
    ):
        raise ValueError("private state replay hash or identity does not match")


def validate_public_post(
    post: PublicPost,
    source_update: PrivateUpdate,
    topic_package: TopicPackage,
) -> None:
    """Replay an explicitly published private update into its exact public projection."""

    if not isinstance(post, PublicPost) or not isinstance(source_update, PrivateUpdate):
        raise TypeError("public post validation requires typed post and update records")
    _validate_update_topic(source_update, topic_package)
    if source_update.published is not True:
        raise ValueError("public post source update must be successfully published")
    if post != PublicPost.from_private_update(source_update, mock_only=True):
        raise ValueError("public post replay does not match its source private update")


def validate_latest_public_pointer(
    pointer: LatestPublicPointer,
    latest_post: PublicPost,
    *,
    previous_pointer: LatestPublicPointer | None = None,
) -> None:
    """Replay the latest-public stock pointer from its trusted public post."""

    if not isinstance(pointer, LatestPublicPointer):
        raise TypeError("pointer must be a LatestPublicPointer")
    if not isinstance(latest_post, PublicPost):
        raise TypeError("latest_post must be a PublicPost")
    if previous_pointer is not None and not isinstance(previous_pointer, LatestPublicPointer):
        raise TypeError("previous_pointer must be a LatestPublicPointer or None")
    expected = LatestPublicPointer.from_post(latest_post, previous=previous_pointer, mock_only=True)
    if pointer != expected:
        raise ValueError("latest public pointer replay does not match its trusted post")
