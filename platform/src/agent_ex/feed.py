"""Finite unread public-post feeds for Paper 1 Phase 4B-6 mock execution."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from .domain import (
    ExposureRecord,
    _freeze,
    _json_ready,
    _require_id,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
)
from .rng import RNGProvenance
from .state import PrivateUpdate, PublicPost, validate_public_post
from .topic import TopicPackage


_FEED_SCHEMA_VERSION = "paper1.mock-feed.v1"
_MOCK_CAPACITIES = frozenset({4, 6, 8})
_SOCIAL_MODES = frozenset({"shuffled_social", "ws_neighbors"})
_ALL_MODES = _SOCIAL_MODES | {"self_history_only"}
_MOCK_METADATA = {"mock_only": True, "research_parameter_status": "not_frozen"}


def _require_mock_only(mock_only: bool) -> None:
    if mock_only is not True:
        raise ValueError("Phase 4B-6 feed records must be explicitly mock_only")


def _require_capacity(capacity: object) -> None:
    _require_int("capacity", capacity, minimum=1)
    if capacity not in _MOCK_CAPACITIES:
        raise ValueError("capacity must be an explicit Phase 0 mock challenge value: 4, 6, or 8")


def _require_mode_graph(mode: object, graph_hash: object) -> None:
    if mode not in _ALL_MODES:
        raise ValueError("exposure_mode is not a legal Paper 1 factor level")
    if mode == "self_history_only":
        if graph_hash is not None:
            raise ValueError("self_history_only cannot bind an exposure graph")
    else:
        _require_sha256("exposure_graph_hash", graph_hash)


def _metadata_from_payload(value: object) -> None:
    if type(value) is not dict or value != _MOCK_METADATA:
        raise ValueError("feed metadata must remain mock_only and not_frozen")


@dataclass(frozen=True, slots=True)
class FeedCursor:
    """Receiver-specific boundary through which public events have been scanned."""

    cursor_id: str
    matched_seed: int
    receiver_agent_id: str
    exposure_mode: str
    exposure_graph_hash: str | None
    last_scanned_event_ordinal: int | None
    activation_count: int
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_id("cursor_id", self.cursor_id)
        _require_int("matched_seed", self.matched_seed)
        _require_id("receiver_agent_id", self.receiver_agent_id)
        _require_mode_graph(self.exposure_mode, self.exposure_graph_hash)
        if self.last_scanned_event_ordinal is not None:
            _require_int("last_scanned_event_ordinal", self.last_scanned_event_ordinal)
        _require_int("activation_count", self.activation_count)
        if (self.last_scanned_event_ordinal is None) != (self.activation_count == 0):
            raise ValueError("initial cursor alone may have no scanned event ordinal")
        expected_id = "feed-cursor-" + canonical_payload_hash(
            {
                "matched_seed": self.matched_seed,
                "receiver_agent_id": self.receiver_agent_id,
                "exposure_mode": self.exposure_mode,
                "exposure_graph_hash": self.exposure_graph_hash,
                "activation_count": self.activation_count,
            }
        )
        if self.cursor_id != expected_id:
            raise ValueError("cursor_id does not match feed cursor identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_MOCK_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _FEED_SCHEMA_VERSION,
            "cursor_id": self.cursor_id,
            "matched_seed": self.matched_seed,
            "receiver_agent_id": self.receiver_agent_id,
            "exposure_mode": self.exposure_mode,
            "exposure_graph_hash": self.exposure_graph_hash,
            "last_scanned_event_ordinal": self.last_scanned_event_ordinal,
            "activation_count": self.activation_count,
            "metadata": self.metadata,
        }

    @classmethod
    def initial(
        cls,
        *,
        matched_seed: int,
        receiver_agent_id: str,
        exposure_mode: str,
        exposure_graph_hash: str | None,
        mock_only: bool,
    ) -> FeedCursor:
        _require_mock_only(mock_only)
        identity = {
            "matched_seed": matched_seed,
            "receiver_agent_id": receiver_agent_id,
            "exposure_mode": exposure_mode,
            "exposure_graph_hash": exposure_graph_hash,
            "activation_count": 0,
        }
        cursor_id = "feed-cursor-" + canonical_payload_hash(identity)
        content = {
            "schema_version": _FEED_SCHEMA_VERSION,
            "cursor_id": cursor_id,
            **identity,
            "last_scanned_event_ordinal": None,
            "metadata": dict(_MOCK_METADATA),
        }
        return cls(
            cursor_id=cursor_id,
            matched_seed=matched_seed,
            receiver_agent_id=receiver_agent_id,
            exposure_mode=exposure_mode,
            exposure_graph_hash=exposure_graph_hash,
            last_scanned_event_ordinal=None,
            activation_count=0,
            record_hash=canonical_payload_hash(content),
        )

    def advance(self, event_ordinal: int) -> FeedCursor:
        _require_int("event_ordinal", event_ordinal)
        if (
            self.last_scanned_event_ordinal is not None
            and event_ordinal <= self.last_scanned_event_ordinal
        ):
            raise ValueError("feed cursor must strictly advance")
        count = self.activation_count + 1
        identity = {
            "matched_seed": self.matched_seed,
            "receiver_agent_id": self.receiver_agent_id,
            "exposure_mode": self.exposure_mode,
            "exposure_graph_hash": self.exposure_graph_hash,
            "activation_count": count,
        }
        cursor_id = "feed-cursor-" + canonical_payload_hash(identity)
        content = {
            "schema_version": _FEED_SCHEMA_VERSION,
            "cursor_id": cursor_id,
            **identity,
            "last_scanned_event_ordinal": event_ordinal,
            "metadata": dict(_MOCK_METADATA),
        }
        return FeedCursor(
            cursor_id=cursor_id,
            matched_seed=self.matched_seed,
            receiver_agent_id=self.receiver_agent_id,
            exposure_mode=self.exposure_mode,
            exposure_graph_hash=self.exposure_graph_hash,
            last_scanned_event_ordinal=event_ordinal,
            activation_count=count,
            record_hash=canonical_payload_hash(content),
        )

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FeedCursor:
        expected = {
            "schema_version",
            "cursor_id",
            "matched_seed",
            "receiver_agent_id",
            "exposure_mode",
            "exposure_graph_hash",
            "last_scanned_event_ordinal",
            "activation_count",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("feed cursor payload fields do not match the v1 contract")
        _require_json_transport(payload, "feed cursor payload")
        if payload["schema_version"] != _FEED_SCHEMA_VERSION:
            raise ValueError("feed cursor schema_version is not supported")
        _metadata_from_payload(payload["metadata"])
        return cls(**{key: payload[key] for key in expected - {"schema_version", "metadata"}})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class FeedCandidate:
    """Public-only feed evidence for one candidate, selected, or expired post."""

    post_id: str
    post_hash: str
    source_update_id: str
    source_update_hash: str
    source_matched_seed: int
    source_agent_id: str
    source_event_id: str | None
    source_event_ordinal: int | None
    is_round0: bool
    stance_label: str
    public_reason: str
    message_age: int
    original_order: int
    display_slot: int | None
    rendered_text: str
    rendered_hash: str

    def __post_init__(self) -> None:
        for name in ("post_id", "source_update_id", "source_agent_id"):
            _require_id(name, getattr(self, name))
        _require_sha256("post_hash", self.post_hash)
        _require_sha256("source_update_hash", self.source_update_hash)
        _require_int("source_matched_seed", self.source_matched_seed)
        if self.source_event_id is not None:
            _require_id("source_event_id", self.source_event_id)
        if self.source_event_ordinal is not None:
            _require_int("source_event_ordinal", self.source_event_ordinal)
        if not isinstance(self.is_round0, bool):
            raise TypeError("is_round0 must be a boolean")
        if self.is_round0 != (self.source_event_ordinal is None):
            raise ValueError("round-0 flag must match the absence of a source event ordinal")
        _require_string("stance_label", self.stance_label)
        _require_string("public_reason", self.public_reason)
        _require_int("message_age", self.message_age, minimum=1)
        _require_int("original_order", self.original_order)
        if self.display_slot is not None:
            _require_int("display_slot", self.display_slot)
        _require_string("rendered_text", self.rendered_text)
        _require_sha256("rendered_hash", self.rendered_hash)
        if self.rendered_hash != canonical_payload_hash(self.rendered_text):
            raise ValueError("rendered_hash does not match rendered public text")

    def to_payload(self) -> dict[str, object]:
        return {
            "post_id": self.post_id,
            "post_hash": self.post_hash,
            "source_update_id": self.source_update_id,
            "source_update_hash": self.source_update_hash,
            "source_matched_seed": self.source_matched_seed,
            "source_agent_id": self.source_agent_id,
            "source_event_id": self.source_event_id,
            "source_event_ordinal": self.source_event_ordinal,
            "is_round0": self.is_round0,
            "stance_label": self.stance_label,
            "public_reason": self.public_reason,
            "message_age": self.message_age,
            "original_order": self.original_order,
            "display_slot": self.display_slot,
            "rendered_text": self.rendered_text,
            "rendered_hash": self.rendered_hash,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FeedCandidate:
        expected = {
            "post_id",
            "post_hash",
            "source_update_id",
            "source_update_hash",
            "source_matched_seed",
            "source_agent_id",
            "source_event_id",
            "source_event_ordinal",
            "is_round0",
            "stance_label",
            "public_reason",
            "message_age",
            "original_order",
            "display_slot",
            "rendered_text",
            "rendered_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("feed candidate fields do not match the v1 contract")
        _require_json_transport(payload, "feed candidate payload")
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ExposureSelection:
    """Complete finite-unread selection evidence before prompt construction."""

    selection_id: str
    receiver_event_id: str
    receiver_event_ordinal: int
    matched_seed: int
    receiver_agent_id: str
    exposure_mode: str
    exposure_graph_hash: str | None
    capacity: int
    cursor_before: FeedCursor
    cursor_after: FeedCursor
    candidates: tuple[FeedCandidate, ...]
    selected: tuple[FeedCandidate, ...]
    expired: tuple[FeedCandidate, ...]
    round0_rng_provenance: RNGProvenance | None
    slot_rng_provenance: RNGProvenance
    input_hashes: Mapping[str, str]
    diagnostics: Mapping[str, object]
    record_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_id("selection_id", self.selection_id)
        _require_id("receiver_event_id", self.receiver_event_id)
        _require_int("receiver_event_ordinal", self.receiver_event_ordinal)
        _require_int("matched_seed", self.matched_seed)
        _require_id("receiver_agent_id", self.receiver_agent_id)
        _require_mode_graph(self.exposure_mode, self.exposure_graph_hash)
        _require_capacity(self.capacity)
        if not isinstance(self.cursor_before, FeedCursor) or not isinstance(
            self.cursor_after, FeedCursor
        ):
            raise TypeError("selection cursors must be FeedCursor values")
        for name, cursor in (
            ("cursor_before", self.cursor_before),
            ("cursor_after", self.cursor_after),
        ):
            if cursor.matched_seed != self.matched_seed:
                raise ValueError(f"{name} seed must match selection seed")
            if cursor.receiver_agent_id != self.receiver_agent_id:
                raise ValueError(f"{name} receiver must match selection receiver")
            if cursor.exposure_mode != self.exposure_mode:
                raise ValueError(f"{name} mode must match selection mode")
            if cursor.exposure_graph_hash != self.exposure_graph_hash:
                raise ValueError(f"{name} graph must match selection graph")
        if (
            self.cursor_after.activation_count != self.cursor_before.activation_count + 1
            or self.cursor_after.last_scanned_event_ordinal != self.receiver_event_ordinal
        ):
            raise ValueError("cursor_after must be the single-event advance of cursor_before")
        for name in ("candidates", "selected", "expired"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(
                isinstance(item, FeedCandidate) for item in values
            ):
                raise TypeError(f"{name} must be a tuple of FeedCandidate values")
        candidate_ids = tuple(item.post_id for item in self.candidates)
        selected_ids = tuple(item.post_id for item in self.selected)
        expired_ids = tuple(item.post_id for item in self.expired)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate posts must be unique")
        if set(selected_ids) & set(expired_ids) or set(selected_ids) | set(expired_ids) != set(
            candidate_ids
        ):
            raise ValueError("selected and expired posts must exactly partition candidates")
        if len(selected_ids) > self.capacity:
            raise ValueError("selected posts exceed capacity")
        if any(item.source_matched_seed != self.matched_seed for item in self.candidates):
            raise ValueError("candidate post seed must match selection seed")
        if any(item.display_slot is not None for item in self.candidates + self.expired):
            raise ValueError("only selected feed items may have display slots")
        slots = tuple(item.display_slot for item in self.selected)
        if set(slots) != set(range(len(self.selected))):
            raise ValueError("selected display slots must be a complete zero-based permutation")
        if self.round0_rng_provenance is not None and not isinstance(
            self.round0_rng_provenance, RNGProvenance
        ):
            raise TypeError("round0_rng_provenance must be RNGProvenance or None")
        round0_ids = tuple(item.post_id for item in self.candidates if item.is_round0)
        expected_round0_coordinates = {
            "artifact_kind": "mock_feed_round0_admission",
            "receiver_agent_id": self.receiver_agent_id,
            "receiver_event_ordinal": self.receiver_event_ordinal,
            "candidate_post_ids_hash": canonical_payload_hash(round0_ids),
        }
        if round0_ids:
            if (
                self.round0_rng_provenance is None
                or self.round0_rng_provenance.namespace != "round0_tiebreak"
                or self.round0_rng_provenance.matched_seed != self.matched_seed
                or dict(self.round0_rng_provenance.coordinates) != expected_round0_coordinates
            ):
                raise ValueError("round-0 RNG provenance namespace or coordinates do not match")
        elif self.round0_rng_provenance is not None:
            raise ValueError("round-0 RNG provenance is forbidden without round-0 candidates")
        if not isinstance(self.slot_rng_provenance, RNGProvenance):
            raise TypeError("slot_rng_provenance must be RNGProvenance")
        if self.slot_rng_provenance.namespace != "message_slot":
            raise ValueError("slot RNG provenance must use message_slot namespace")
        if self.slot_rng_provenance.matched_seed != self.matched_seed or dict(
            self.slot_rng_provenance.coordinates
        ) != {
            "artifact_kind": "mock_feed_message_slots",
            "receiver_agent_id": self.receiver_agent_id,
            "event_ordinal": self.receiver_event_ordinal,
        }:
            raise ValueError("slot RNG provenance must bind seed, receiver, and event ordinal")
        if not isinstance(self.input_hashes, Mapping):
            raise TypeError("input_hashes must be a mapping")
        if set(self.input_hashes) != {
            "unread_public_posts",
            "neighbor_agent_ids",
            "cursor_before",
            "exposure_graph",
        }:
            raise ValueError("input_hashes keys must exactly match the unread feed contract")
        for name, digest in self.input_hashes.items():
            _require_id("input_hash key", name)
            _require_sha256(f"input_hashes[{name}]", digest)
        if self.input_hashes.get("cursor_before") != self.cursor_before.record_hash:
            raise ValueError("input cursor hash must match cursor_before")
        if self.input_hashes.get("exposure_graph") != canonical_payload_hash(
            self.exposure_graph_hash
        ):
            raise ValueError("input exposure graph hash must match selection graph")
        if not isinstance(self.diagnostics, Mapping):
            raise TypeError("diagnostics must be a mapping")
        expected_id = "exposure-selection-" + canonical_payload_hash(
            {
                "receiver_event_id": self.receiver_event_id,
                "cursor_before_hash": self.cursor_before.record_hash,
                "cursor_after_hash": self.cursor_after.record_hash,
                "input_hashes": self.input_hashes,
            }
        )
        if self.selection_id != expected_id:
            raise ValueError("selection_id does not match exposure selection identity")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "input_hashes", _freeze(self.input_hashes))
        object.__setattr__(self, "diagnostics", _freeze(self.diagnostics))

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_MOCK_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": _FEED_SCHEMA_VERSION,
            "selection_id": self.selection_id,
            "receiver_event_id": self.receiver_event_id,
            "receiver_event_ordinal": self.receiver_event_ordinal,
            "matched_seed": self.matched_seed,
            "receiver_agent_id": self.receiver_agent_id,
            "exposure_mode": self.exposure_mode,
            "exposure_graph_hash": self.exposure_graph_hash,
            "capacity": self.capacity,
            "cursor_before": self.cursor_before.to_payload(),
            "cursor_after": self.cursor_after.to_payload(),
            "candidates": tuple(item.to_payload() for item in self.candidates),
            "selected": tuple(item.to_payload() for item in self.selected),
            "expired": tuple(item.to_payload() for item in self.expired),
            "round0_rng_provenance": None
            if self.round0_rng_provenance is None
            else self.round0_rng_provenance.to_payload(),
            "slot_rng_provenance": self.slot_rng_provenance.to_payload(),
            "input_hashes": self.input_hashes,
            "diagnostics": self.diagnostics,
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ExposureSelection:
        expected = {
            "schema_version",
            "selection_id",
            "receiver_event_id",
            "receiver_event_ordinal",
            "matched_seed",
            "receiver_agent_id",
            "exposure_mode",
            "exposure_graph_hash",
            "capacity",
            "cursor_before",
            "cursor_after",
            "candidates",
            "selected",
            "expired",
            "round0_rng_provenance",
            "slot_rng_provenance",
            "input_hashes",
            "diagnostics",
            "metadata",
            "record_hash",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("exposure selection payload fields do not match the v1 contract")
        _require_json_transport(payload, "exposure selection payload")
        if payload["schema_version"] != _FEED_SCHEMA_VERSION:
            raise ValueError("exposure selection schema_version is not supported")
        _metadata_from_payload(payload["metadata"])
        for name in ("candidates", "selected", "expired"):
            if type(payload[name]) is not list:
                raise TypeError(f"{name} must be a JSON array")
        if type(payload["cursor_before"]) is not dict or type(payload["cursor_after"]) is not dict:
            raise TypeError("selection cursors must be JSON objects")
        if type(payload["slot_rng_provenance"]) is not dict:
            raise TypeError("slot_rng_provenance must be a JSON object")
        round0 = payload["round0_rng_provenance"]
        if round0 is not None and type(round0) is not dict:
            raise TypeError("round0_rng_provenance must be a JSON object or null")
        return cls(
            selection_id=payload["selection_id"],  # type: ignore[arg-type]
            receiver_event_id=payload["receiver_event_id"],  # type: ignore[arg-type]
            receiver_event_ordinal=payload["receiver_event_ordinal"],  # type: ignore[arg-type]
            matched_seed=payload["matched_seed"],  # type: ignore[arg-type]
            receiver_agent_id=payload["receiver_agent_id"],  # type: ignore[arg-type]
            exposure_mode=payload["exposure_mode"],  # type: ignore[arg-type]
            exposure_graph_hash=payload["exposure_graph_hash"],  # type: ignore[arg-type]
            capacity=payload["capacity"],  # type: ignore[arg-type]
            cursor_before=FeedCursor.from_payload(payload["cursor_before"]),
            cursor_after=FeedCursor.from_payload(payload["cursor_after"]),
            candidates=tuple(FeedCandidate.from_payload(item) for item in payload["candidates"]),  # type: ignore[arg-type,union-attr]
            selected=tuple(FeedCandidate.from_payload(item) for item in payload["selected"]),  # type: ignore[arg-type,union-attr]
            expired=tuple(FeedCandidate.from_payload(item) for item in payload["expired"]),  # type: ignore[arg-type,union-attr]
            round0_rng_provenance=None if round0 is None else RNGProvenance.from_payload(round0),
            slot_rng_provenance=RNGProvenance.from_payload(payload["slot_rng_provenance"]),
            input_hashes=payload["input_hashes"],  # type: ignore[arg-type]
            diagnostics=payload["diagnostics"],  # type: ignore[arg-type]
            record_hash=payload["record_hash"],  # type: ignore[arg-type]
        )


def _validate_timeline(
    posts: tuple[PublicPost, ...], receiver_event_id: str, receiver_event_ordinal: int
) -> None:
    seen: set[str] = set()
    saw_event = False
    prior_ordinal: int | None = None
    for value in posts:
        if value.post_id in seen:
            raise ValueError("public post timeline contains duplicate post IDs")
        seen.add(value.post_id)
        ordinal = value.published_event_ordinal
        if ordinal is None:
            if saw_event:
                raise ValueError("round-0 public posts must precede event posts")
        else:
            saw_event = True
            if value.source_event_id == receiver_event_id:
                raise ValueError("public post cannot name the current receiver event as source")
            if ordinal >= receiver_event_ordinal:
                raise ValueError("public post cannot come from the current or a future event")
            if prior_ordinal is not None and ordinal <= prior_ordinal:
                raise ValueError("public event posts must follow strict event order")
            prior_ordinal = ordinal


def _candidate_from_post(post: PublicPost, *, order: int, receiver_ordinal: int) -> FeedCandidate:
    rendered = f"Member {post.author_agent_id} | {post.stance_label} | {post.public_reason}"
    age = (
        receiver_ordinal + 1
        if post.published_event_ordinal is None
        else receiver_ordinal - post.published_event_ordinal
    )
    return FeedCandidate(
        post_id=post.post_id,
        post_hash=post.record_hash,
        source_update_id=post.source_update_id,
        source_update_hash=post.source_update_hash,
        source_matched_seed=post.matched_seed,
        source_agent_id=post.author_agent_id,
        source_event_id=post.source_event_id,
        source_event_ordinal=post.published_event_ordinal,
        is_round0=post.published_event_ordinal is None,
        stance_label=post.stance_label,
        public_reason=post.public_reason,
        message_age=age,
        original_order=order,
        display_slot=None,
        rendered_text=rendered,
        rendered_hash=canonical_payload_hash(rendered),
    )


def select_unread_feed(
    *,
    unread_public_posts: Sequence[PublicPost],
    topic_package: TopicPackage,
    neighbor_agent_ids: Sequence[str],
    cursor: FeedCursor,
    receiver_event_id: str,
    receiver_event_ordinal: int,
    matched_seed: int,
    exposure_mode: str,
    exposure_graph_hash: str | None,
    capacity: int,
    mock_only: bool,
) -> ExposureSelection:
    """Select latest unread public posts, then independently permute display slots."""

    _require_mock_only(mock_only)
    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be a TopicPackage")
    _require_id("receiver_event_id", receiver_event_id)
    _require_int("receiver_event_ordinal", receiver_event_ordinal)
    _require_int("matched_seed", matched_seed)
    _require_mode_graph(exposure_mode, exposure_graph_hash)
    _require_capacity(capacity)
    if not isinstance(cursor, FeedCursor):
        raise TypeError("cursor must be a FeedCursor")
    if cursor.matched_seed != matched_seed:
        raise ValueError("cursor matched seed does not match feed seed")
    if cursor.exposure_mode != exposure_mode:
        raise ValueError("cursor exposure mode does not match feed mode")
    if cursor.exposure_graph_hash != exposure_graph_hash:
        raise ValueError("cursor exposure graph hash does not match feed graph")
    if (
        cursor.last_scanned_event_ordinal is not None
        and receiver_event_ordinal <= cursor.last_scanned_event_ordinal
    ):
        raise ValueError("receiver event must advance beyond the feed cursor")
    if not isinstance(unread_public_posts, Sequence) or isinstance(
        unread_public_posts, (str, bytes)
    ):
        raise TypeError("unread_public_posts must be a sequence")
    supplied_posts = tuple(unread_public_posts)
    if not all(isinstance(value, PublicPost) for value in supplied_posts):
        raise TypeError("public_posts must contain PublicPost values")
    if any(value.matched_seed != matched_seed for value in supplied_posts):
        raise ValueError("public post matched seed does not match feed seed")
    if any(
        value.topic_package_id != topic_package.topic_id
        or value.topic_package_hash != topic_package.package_hash
        or value.stance_label not in topic_package.stance_labels
        for value in supplied_posts
    ):
        raise ValueError("public post topic package or stance_label does not match feed topic")
    _validate_timeline(supplied_posts, receiver_event_id, receiver_event_ordinal)
    posts = tuple(
        sorted(
            (value for value in supplied_posts if value.published_event_ordinal is None),
            key=lambda value: value.post_id,
        )
    ) + tuple(value for value in supplied_posts if value.published_event_ordinal is not None)
    if not isinstance(neighbor_agent_ids, Sequence) or isinstance(neighbor_agent_ids, (str, bytes)):
        raise TypeError("neighbor_agent_ids must be a sequence")
    supplied_neighbors = tuple(neighbor_agent_ids)
    for value in supplied_neighbors:
        _require_id("neighbor_agent_id", value)
    if len(set(supplied_neighbors)) != len(supplied_neighbors):
        raise ValueError("neighbor agent IDs must be unique")
    neighbors = tuple(sorted(supplied_neighbors))
    if cursor.receiver_agent_id in neighbors:
        raise ValueError("receiver cannot be its own social neighbor")
    if exposure_mode == "self_history_only" and neighbors:
        raise ValueError("self_history_only cannot have social neighbors")
    if exposure_mode == "self_history_only" and posts:
        raise ValueError("self_history_only unread slice must be empty")

    neighbor_set = set(neighbors)
    if exposure_mode in _SOCIAL_MODES and any(
        value.author_agent_id not in neighbor_set for value in posts
    ):
        raise ValueError("unread public post source must be an exposure-graph neighbor")
    if cursor.activation_count > 0 and any(
        value.published_event_ordinal is None
        or value.published_event_ordinal <= cursor.last_scanned_event_ordinal  # type: ignore[operator]
        for value in posts
    ):
        raise ValueError("unread public post must be strictly after the receiver cursor")
    candidates = []
    if exposure_mode in _SOCIAL_MODES:
        for order, value in enumerate(posts):
            candidates.append(
                _candidate_from_post(value, order=order, receiver_ordinal=receiver_event_ordinal)
            )
    candidate_tuple = tuple(candidates)

    round0 = [item for item in candidate_tuple if item.is_round0]
    normal = [item for item in candidate_tuple if not item.is_round0]
    round0_provenance: RNGProvenance | None = None
    if round0:
        round0_provenance = RNGProvenance.create(
            matched_seed=matched_seed,
            namespace="round0_tiebreak",
            coordinates={
                "artifact_kind": "mock_feed_round0_admission",
                "receiver_agent_id": cursor.receiver_agent_id,
                "receiver_event_ordinal": receiver_event_ordinal,
                "candidate_post_ids_hash": canonical_payload_hash(
                    tuple(item.post_id for item in round0)
                ),
            },
        )
        random.Random(round0_provenance.derived_seed).shuffle(round0)
    priority = tuple(round0 + normal)
    selected_base = priority[-capacity:]
    selected_ids = {item.post_id for item in selected_base}
    expired = tuple(item for item in candidate_tuple if item.post_id not in selected_ids)

    slot_provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="message_slot",
        coordinates={
            "artifact_kind": "mock_feed_message_slots",
            "receiver_agent_id": cursor.receiver_agent_id,
            "event_ordinal": receiver_event_ordinal,
        },
    )
    slots = list(range(len(selected_base)))
    random.Random(slot_provenance.derived_seed).shuffle(slots)
    selected = tuple(
        replace(item, display_slot=slot) for item, slot in zip(selected_base, slots, strict=True)
    )
    cursor_after = cursor.advance(receiver_event_ordinal)
    counts = Counter(item.source_agent_id for item in selected)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    diagnostics = {
        "message_count": len(selected),
        "candidate_count": len(candidate_tuple),
        "expired_count": len(expired),
        "source_coverage": len(counts),
        "repeated_source_share": 0.0 if not selected else repeated / len(selected),
        "empty_feed": not selected,
        "message_ages": tuple(item.message_age for item in selected),
        "sender_activity": dict(sorted(counts.items())),
    }
    input_hashes = {
        "unread_public_posts": canonical_payload_hash(tuple(item.to_payload() for item in posts)),
        "neighbor_agent_ids": canonical_payload_hash(neighbors),
        "cursor_before": cursor.record_hash,
        "exposure_graph": canonical_payload_hash(exposure_graph_hash),
    }
    selection_id = "exposure-selection-" + canonical_payload_hash(
        {
            "receiver_event_id": receiver_event_id,
            "cursor_before_hash": cursor.record_hash,
            "cursor_after_hash": cursor_after.record_hash,
            "input_hashes": input_hashes,
        }
    )
    content = {
        "schema_version": _FEED_SCHEMA_VERSION,
        "selection_id": selection_id,
        "receiver_event_id": receiver_event_id,
        "receiver_event_ordinal": receiver_event_ordinal,
        "matched_seed": matched_seed,
        "receiver_agent_id": cursor.receiver_agent_id,
        "exposure_mode": exposure_mode,
        "exposure_graph_hash": exposure_graph_hash,
        "capacity": capacity,
        "cursor_before": cursor.to_payload(),
        "cursor_after": cursor_after.to_payload(),
        "candidates": tuple(item.to_payload() for item in candidate_tuple),
        "selected": tuple(item.to_payload() for item in selected),
        "expired": tuple(item.to_payload() for item in expired),
        "round0_rng_provenance": None
        if round0_provenance is None
        else round0_provenance.to_payload(),
        "slot_rng_provenance": slot_provenance.to_payload(),
        "input_hashes": input_hashes,
        "diagnostics": diagnostics,
        "metadata": dict(_MOCK_METADATA),
    }
    return ExposureSelection(
        selection_id=selection_id,
        receiver_event_id=receiver_event_id,
        receiver_event_ordinal=receiver_event_ordinal,
        matched_seed=matched_seed,
        receiver_agent_id=cursor.receiver_agent_id,
        exposure_mode=exposure_mode,
        exposure_graph_hash=exposure_graph_hash,
        capacity=capacity,
        cursor_before=cursor,
        cursor_after=cursor_after,
        candidates=candidate_tuple,
        selected=selected,
        expired=expired,
        round0_rng_provenance=round0_provenance,
        slot_rng_provenance=slot_provenance,
        input_hashes=input_hashes,
        diagnostics=diagnostics,
        record_hash=canonical_payload_hash(content),
    )


def build_exposure_record(
    selection: ExposureSelection,
    *,
    mock_only: bool,
) -> ExposureRecord:
    """Freeze a selection into the event evidence graph's extended exposure record."""

    _require_mock_only(mock_only)
    if not isinstance(selection, ExposureSelection):
        raise TypeError("selection must be an ExposureSelection")
    return ExposureRecord.create(
        matched_seed=selection.matched_seed,
        event_ordinal=selection.receiver_event_ordinal,
        receiver_agent_id=selection.receiver_agent_id,
        exposure_mode=selection.exposure_mode,
        exposure_graph_hash=selection.exposure_graph_hash,
        capacity=selection.capacity,
        selection_id=selection.selection_id,
        selection_hash=selection.record_hash,
        cursor_before_id=selection.cursor_before.cursor_id,
        cursor_before_hash=selection.cursor_before.record_hash,
        cursor_after_id=selection.cursor_after.cursor_id,
        cursor_after_hash=selection.cursor_after.record_hash,
        candidate_post_ids=tuple(item.post_id for item in selection.candidates),
        candidate_post_hashes=tuple(item.post_hash for item in selection.candidates),
        selected_post_ids=tuple(item.post_id for item in selection.selected),
        expired_post_ids=tuple(item.post_id for item in selection.expired),
        round0_candidate_post_ids=tuple(
            item.post_id for item in selection.candidates if item.is_round0
        ),
        source_post_ids=tuple(item.post_id for item in selection.selected),
        source_post_hashes=tuple(item.post_hash for item in selection.selected),
        source_update_ids=tuple(item.source_update_id for item in selection.selected),
        source_update_hashes=tuple(item.source_update_hash for item in selection.selected),
        source_agent_ids=tuple(item.source_agent_id for item in selection.selected),
        source_event_ids=tuple(item.source_event_id for item in selection.selected),
        message_ages=tuple(item.message_age for item in selection.selected),
        original_orders=tuple(item.original_order for item in selection.selected),
        display_slots=tuple(item.display_slot for item in selection.selected),  # type: ignore[arg-type]
        rendered_texts=tuple(item.rendered_text for item in selection.selected),
        rendered_hashes=tuple(item.rendered_hash for item in selection.selected),
        slot_rng_hash=canonical_payload_hash(selection.slot_rng_provenance.to_payload()),
        round0_rng_hash=(
            None
            if selection.round0_rng_provenance is None
            else canonical_payload_hash(selection.round0_rng_provenance.to_payload())
        ),
        mock_only=True,
    )


def validate_exposure_selection(
    selection: ExposureSelection,
    *,
    unread_public_posts: Sequence[PublicPost],
    topic_package: TopicPackage,
    neighbor_agent_ids: Sequence[str],
    cursor: FeedCursor,
    receiver_event_id: str,
    receiver_event_ordinal: int,
    matched_seed: int,
    exposure_mode: str,
    exposure_graph_hash: str | None,
    capacity: int,
) -> None:
    """Replay selection from the trusted incremental slice and compare every field."""

    if not isinstance(selection, ExposureSelection):
        raise TypeError("selection must be an ExposureSelection")
    expected = select_unread_feed(
        unread_public_posts=unread_public_posts,
        topic_package=topic_package,
        neighbor_agent_ids=neighbor_agent_ids,
        cursor=cursor,
        receiver_event_id=receiver_event_id,
        receiver_event_ordinal=receiver_event_ordinal,
        matched_seed=matched_seed,
        exposure_mode=exposure_mode,
        exposure_graph_hash=exposure_graph_hash,
        capacity=capacity,
        mock_only=True,
    )
    if selection != expected:
        raise ValueError("exposure selection replay does not match trusted unread inputs")


def validate_exposure_record(
    record: ExposureRecord,
    selection: ExposureSelection,
    public_posts_by_id: Mapping[str, PublicPost],
    private_updates_by_id: Mapping[str, PrivateUpdate],
    topic_package: TopicPackage,
) -> None:
    """Validate the frozen exposure against its selection and source evidence graph."""

    if not isinstance(record, ExposureRecord):
        raise TypeError("record must be an ExposureRecord")
    expected = build_exposure_record(selection, mock_only=True)
    if record != expected:
        raise ValueError("exposure record replay does not match its selection")
    for candidate in selection.selected:
        post = public_posts_by_id.get(candidate.post_id)
        if post is None or post.record_hash != candidate.post_hash:
            raise ValueError("exposure source post hash does not match trusted post evidence")
        update = private_updates_by_id.get(candidate.source_update_id)
        if update is None or update.record_hash != candidate.source_update_hash:
            raise ValueError("exposure source update hash does not match trusted update evidence")
        validate_public_post(post, update, topic_package)
