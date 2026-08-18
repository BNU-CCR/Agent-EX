"""Read-only private memory views for Paper 1 Phase 4B-6 mock execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

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
from .state import PrivateUpdate
from .topic import TopicPackage


_MEMORY_SCHEMA_VERSION = "paper1.mock-memory.v1"
_MOCK_WINDOWS = frozenset({1, 3, 5})
_MOCK_METADATA = {"mock_only": True, "research_parameter_status": "not_frozen"}


def _require_mock_only(mock_only: bool) -> None:
    if mock_only is not True:
        raise ValueError("Phase 4B-6 memory views must be explicitly mock_only")


def _require_window(window: object) -> None:
    _require_int("window", window, minimum=1)
    if window not in _MOCK_WINDOWS:
        raise ValueError("window must be an explicit Phase 0 mock challenge value: 1, 3, or 5")


def _metadata_from_payload(value: object) -> None:
    if type(value) is not dict or value != _MOCK_METADATA:
        raise ValueError("memory metadata must remain mock_only and not_frozen")


@dataclass(frozen=True, slots=True)
class MemoryItem:
    """One private update rendered to the owning agent's memory only."""

    update_id: str
    update_hash: str
    topic_package_id: str
    topic_package_hash: str
    matched_seed: int
    sequence_index: int
    event_ordinal: int | None
    stance_label: str
    private_reason: str
    confidence: int | None
    published: bool

    def __post_init__(self) -> None:
        _require_id("update_id", self.update_id)
        _require_sha256("update_hash", self.update_hash)
        _require_id("topic_package_id", self.topic_package_id)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_int("matched_seed", self.matched_seed)
        _require_int("sequence_index", self.sequence_index)
        if self.event_ordinal is not None:
            _require_int("event_ordinal", self.event_ordinal)
        _require_string("stance_label", self.stance_label)
        _require_string("private_reason", self.private_reason)
        if self.confidence is not None:
            _require_int("confidence", self.confidence, minimum=1)
            if self.confidence > 5:
                raise ValueError("confidence must be between 1 and 5")
        if not isinstance(self.published, bool):
            raise TypeError("published must be a boolean")

    @classmethod
    def from_update(cls, update: PrivateUpdate) -> MemoryItem:
        if not isinstance(update, PrivateUpdate):
            raise TypeError("memory source must be a PrivateUpdate")
        return cls(
            update_id=update.update_id,
            update_hash=update.record_hash,
            topic_package_id=update.topic_package_id,
            topic_package_hash=update.topic_package_hash,
            matched_seed=update.matched_seed,
            sequence_index=update.sequence_index,
            event_ordinal=update.event_ordinal,
            stance_label=update.stance_label,
            private_reason=update.reason,
            confidence=update.confidence,
            published=update.published,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "update_id": self.update_id,
            "update_hash": self.update_hash,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "sequence_index": self.sequence_index,
            "event_ordinal": self.event_ordinal,
            "stance_label": self.stance_label,
            "private_reason": self.private_reason,
            "confidence": self.confidence,
            "published": self.published,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> MemoryItem:
        expected = {
            "update_id",
            "update_hash",
            "topic_package_id",
            "topic_package_hash",
            "matched_seed",
            "sequence_index",
            "event_ordinal",
            "stance_label",
            "private_reason",
            "confidence",
            "published",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("memory item fields do not match the v1 contract")
        _require_json_transport(payload, "memory item payload")
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class MemoryView:
    """Hash-bound, oldest-to-newest rolling view over complete private history."""

    view_id: str
    topic_package_id: str
    topic_package_hash: str
    matched_seed: int
    agent_id: str
    window: int
    source_update_count: int
    source_history_hash: str
    items: tuple[MemoryItem, ...]
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_id("view_id", self.view_id)
        _require_id("topic_package_id", self.topic_package_id)
        _require_sha256("topic_package_hash", self.topic_package_hash)
        _require_int("matched_seed", self.matched_seed)
        _require_id("agent_id", self.agent_id)
        _require_window(self.window)
        _require_int("source_update_count", self.source_update_count)
        _require_sha256("source_history_hash", self.source_history_hash)
        if not isinstance(self.items, tuple) or not all(
            isinstance(item, MemoryItem) for item in self.items
        ):
            raise TypeError("items must be a tuple of MemoryItem values")
        if len(self.items) > self.window or len(self.items) > self.source_update_count:
            raise ValueError("memory items exceed the configured window or source history")
        if any(
            item.matched_seed != self.matched_seed
            or item.topic_package_id != self.topic_package_id
            or item.topic_package_hash != self.topic_package_hash
            for item in self.items
        ):
            raise ValueError("memory item seed and topic package must match its view")
        sequences = tuple(item.sequence_index for item in self.items)
        if sequences != tuple(sorted(sequences)) or len(set(sequences)) != len(sequences):
            raise ValueError("memory items must be unique and ordered oldest to newest")
        expected_id = "memory-view-" + canonical_payload_hash(
            {
                "agent_id": self.agent_id,
                "topic_package_id": self.topic_package_id,
                "matched_seed": self.matched_seed,
                "window": self.window,
                "source_history_hash": self.source_history_hash,
            }
        )
        if self.view_id != expected_id:
            raise ValueError("view_id does not match memory view identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "items", tuple(self.items))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_MOCK_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _MEMORY_SCHEMA_VERSION,
            "view_id": self.view_id,
            "topic_package_id": self.topic_package_id,
            "topic_package_hash": self.topic_package_hash,
            "matched_seed": self.matched_seed,
            "agent_id": self.agent_id,
            "window": self.window,
            "source_update_count": self.source_update_count,
            "source_history_hash": self.source_history_hash,
            "items": tuple(item.to_payload() for item in self.items),
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> MemoryView:
        expected = {
            "schema_version",
            "view_id",
            "topic_package_id",
            "topic_package_hash",
            "matched_seed",
            "agent_id",
            "window",
            "source_update_count",
            "source_history_hash",
            "items",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("memory view payload fields do not match the v1 contract")
        _require_json_transport(payload, "memory view payload")
        if payload["schema_version"] != _MEMORY_SCHEMA_VERSION:
            raise ValueError("memory view schema_version is not supported")
        _metadata_from_payload(payload["metadata"])
        if type(payload["items"]) is not list:
            raise TypeError("memory view items must be a JSON array")
        return cls(
            view_id=payload["view_id"],  # type: ignore[arg-type]
            topic_package_id=payload["topic_package_id"],  # type: ignore[arg-type]
            topic_package_hash=payload["topic_package_hash"],  # type: ignore[arg-type]
            matched_seed=payload["matched_seed"],  # type: ignore[arg-type]
            agent_id=payload["agent_id"],  # type: ignore[arg-type]
            window=payload["window"],  # type: ignore[arg-type]
            source_update_count=payload["source_update_count"],  # type: ignore[arg-type]
            source_history_hash=payload["source_history_hash"],  # type: ignore[arg-type]
            items=tuple(MemoryItem.from_payload(item) for item in payload["items"]),  # type: ignore[arg-type,union-attr]
            record_hash=payload["record_hash"],  # type: ignore[arg-type]
        )


def build_memory_view(
    *,
    private_updates: Sequence[PrivateUpdate],
    topic_package: TopicPackage,
    matched_seed: int,
    agent_id: str,
    window: int,
    mock_only: bool,
) -> MemoryView:
    """Build the latest-K self-memory without publication-based filtering or summarization."""

    _require_mock_only(mock_only)
    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be a TopicPackage")
    _require_id("agent_id", agent_id)
    _require_int("matched_seed", matched_seed)
    _require_window(window)
    if not isinstance(private_updates, Sequence) or isinstance(private_updates, (str, bytes)):
        raise TypeError("private_updates must be a sequence")
    updates = tuple(private_updates)
    if not all(isinstance(update, PrivateUpdate) for update in updates):
        raise TypeError("private_updates must contain PrivateUpdate values")
    if any(update.agent_id != agent_id for update in updates):
        raise ValueError("all private updates must belong to the memory agent")
    if any(update.matched_seed != matched_seed for update in updates):
        raise ValueError("all private updates must belong to the memory matched seed")
    if any(
        update.topic_package_id != topic_package.topic_id
        or update.topic_package_hash != topic_package.package_hash
        or update.stance_label not in topic_package.stance_labels
        for update in updates
    ):
        raise ValueError("all private updates must match the memory topic package and labels")
    ordinals = tuple(update.event_ordinal for update in updates if update.event_ordinal is not None)
    if any(right <= left for left, right in zip(ordinals, ordinals[1:], strict=False)):
        raise ValueError("private update event ordinal must strictly advance")
    if tuple(update.sequence_index for update in updates) != tuple(range(len(updates))):
        raise ValueError("private update sequence must be complete and contiguous from round 0")
    if updates and updates[0].event_ordinal is not None:
        raise ValueError("private update sequence must begin with round 0")

    source_history_hash = canonical_payload_hash(tuple(update.to_payload() for update in updates))
    items = tuple(MemoryItem.from_update(update) for update in updates[-window:])
    view_id = "memory-view-" + canonical_payload_hash(
        {
            "agent_id": agent_id,
            "matched_seed": matched_seed,
            "topic_package_id": topic_package.topic_id,
            "window": window,
            "source_history_hash": source_history_hash,
        }
    )
    content = {
        "schema_version": _MEMORY_SCHEMA_VERSION,
        "view_id": view_id,
        "topic_package_id": topic_package.topic_id,
        "topic_package_hash": topic_package.package_hash,
        "matched_seed": matched_seed,
        "agent_id": agent_id,
        "window": window,
        "source_update_count": len(updates),
        "source_history_hash": source_history_hash,
        "items": tuple(item.to_payload() for item in items),
        "metadata": dict(_MOCK_METADATA),
    }
    return MemoryView(
        view_id=view_id,
        topic_package_id=topic_package.topic_id,
        topic_package_hash=topic_package.package_hash,
        matched_seed=matched_seed,
        agent_id=agent_id,
        window=window,
        source_update_count=len(updates),
        source_history_hash=source_history_hash,
        items=items,
        record_hash=canonical_payload_hash(content),
    )


def validate_memory_view(
    view: MemoryView,
    private_updates: Sequence[PrivateUpdate],
    topic_package: TopicPackage,
) -> None:
    """Replay the complete ordered successful history and exact latest-K memory view."""

    if not isinstance(view, MemoryView):
        raise TypeError("view must be a MemoryView")
    expected = build_memory_view(
        private_updates=private_updates,
        topic_package=topic_package,
        matched_seed=view.matched_seed,
        agent_id=view.agent_id,
        window=view.window,
        mock_only=True,
    )
    if view != expected:
        raise ValueError("memory view replay does not match complete successful update history")
