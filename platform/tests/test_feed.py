from __future__ import annotations

import inspect
from dataclasses import replace

import pytest

from agent_ex.feed import (
    FeedCursor,
    ExposureSelection,
    build_exposure_record,
    select_unread_feed,
    validate_exposure_record,
    validate_exposure_selection,
)
from agent_ex.state import PrivateUpdate, PublicPost
from agent_ex.topic import TopicPackage


def topic() -> TopicPackage:
    return TopicPackage.from_payload(
        {
            "schema_version": "paper1.topic-package.mock.v1",
            "package_version": "mock",
            "topic_id": "mock-topic",
            "construct": "mock",
            "target_population": "mock",
            "applicability": "mock",
            "fact_card": "mock",
            "core_statement": "mock",
            "paraphrases": ["mock"],
            "stance_labels": [
                "label-0",
                "label-1",
                "label-2",
                "label-3",
                "label-4",
                "label-5",
                "label-6",
            ],
            "confidence_contract": {"minimum": 1, "maximum": 5, "analysis_only": True},
            "output_contract": ["stance", "confidence", "public_reason"],
            "argument_families": ["mock"],
            "round0_reason_library_artifact_id": "artifact-" + "a" * 64,
            "topic_extension_fields": [],
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        }
    )


def post(author: str, ordinal: int | None, sequence: int, *, seed: int = 17) -> PublicPost:
    update = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=seed,
        agent_id=author,
        event_id=None if ordinal is None else f"event-{ordinal:04d}",
        event_ordinal=ordinal,
        sequence_index=sequence,
        stance_label=topic().stance_labels[sequence % 7],
        reason=f"public reason from {author} at {sequence}",
        confidence=None if ordinal is None else 3,
        published=True,
        source_attempt_id=None if ordinal is None else f"attempt-{ordinal:04d}-1",
        mock_only=True,
    )
    return PublicPost.from_private_update(update, mock_only=True)


def timeline() -> tuple[PublicPost, ...]:
    return (
        post("agent-a", None, 0),
        post("agent-b", None, 0),
        post("agent-c", None, 0),
        post("agent-a", 1, 1),
        post("agent-a", 2, 2),
        post("agent-b", 3, 1),
        post("agent-c", 4, 1),
    )


def initial_cursor(
    *, seed: int = 17, mode: str = "ws_neighbors", graph_hash: str = "a" * 64
) -> FeedCursor:
    return FeedCursor.initial(
        matched_seed=seed,
        receiver_agent_id="agent-r",
        exposure_mode=mode,
        exposure_graph_hash=graph_hash,
        mock_only=True,
    )


def select(
    *,
    posts: tuple[PublicPost, ...] | None = None,
    cursor: FeedCursor | None = None,
    ordinal: int = 5,
    mode: str = "ws_neighbors",
    graph_hash: str = "a" * 64,
    capacity: int = 4,
) -> ExposureSelection:
    return select_unread_feed(
        unread_public_posts=timeline() if posts is None else posts,
        topic_package=topic(),
        neighbor_agent_ids=("agent-a", "agent-b", "agent-c"),
        cursor=initial_cursor(mode=mode, graph_hash=graph_hash) if cursor is None else cursor,
        receiver_event_id=f"event-{ordinal:04d}",
        receiver_event_ordinal=ordinal,
        matched_seed=17,
        exposure_mode=mode,
        exposure_graph_hash=graph_hash,
        capacity=capacity,
        mock_only=True,
    )


def test_first_activation_selects_latest_b_and_expires_older_round0_posts() -> None:
    result = select()

    assert tuple(item.source_event_ordinal for item in result.selected) == (1, 2, 3, 4)
    assert tuple(item.source_agent_id for item in result.selected).count("agent-a") == 2
    assert {item.post_id for item in result.expired} == {
        item.post_id for item in result.candidates if item.is_round0
    }
    assert result.cursor_after.last_scanned_event_ordinal == 5
    assert result.cursor_after.activation_count == 1
    assert ExposureSelection.from_payload(result.to_payload()) == result


def test_later_activation_reads_only_cursor_new_posts_without_backfill() -> None:
    first = select()
    new_post = post("agent-b", 6, 2)
    second = select(
        posts=(new_post,),
        cursor=first.cursor_after,
        ordinal=8,
        capacity=4,
    )

    assert tuple(item.post_id for item in second.candidates) == (new_post.post_id,)
    assert tuple(item.post_id for item in second.selected) == (new_post.post_id,)
    assert second.expired == ()
    assert second.cursor_after.last_scanned_event_ordinal == 8


def test_empty_feed_is_legal_and_cursor_still_advances() -> None:
    first = select()
    empty = select(posts=(), cursor=first.cursor_after, ordinal=8)

    assert empty.candidates == empty.selected == empty.expired == ()
    assert empty.cursor_after.last_scanned_event_ordinal == 8


@pytest.mark.parametrize("capacity", (4, 6, 8))
def test_capacity_is_an_explicit_mock_challenge_and_never_an_implicit_default(
    capacity: int,
) -> None:
    assert (
        inspect.signature(select_unread_feed).parameters["capacity"].default
        is inspect.Parameter.empty
    )
    result = select(capacity=capacity)
    assert result.capacity == capacity


def test_feed_rejects_future_post_cursor_regression_and_bool_integer() -> None:
    with pytest.raises(ValueError, match="future|current"):
        select(posts=timeline() + (post("agent-a", 5, 3),))
    first = select()
    with pytest.raises(ValueError, match="advance|cursor"):
        select(cursor=first.cursor_after, ordinal=5)
    with pytest.raises(TypeError, match="ordinal"):
        select_unread_feed(
            unread_public_posts=timeline(),
            topic_package=topic(),
            neighbor_agent_ids=("agent-a",),
            cursor=initial_cursor(),
            receiver_event_id="event-x",
            receiver_event_ordinal=True,
            matched_seed=17,
            exposure_mode="ws_neighbors",
            exposure_graph_hash="a" * 64,
            capacity=4,
            mock_only=True,
        )

    source = post("agent-a", 1, 1)
    forged = object.__new__(PublicPost)
    for name in PublicPost.__dataclass_fields__:
        object.__setattr__(
            forged, name, "event-0005" if name == "source_event_id" else getattr(source, name)
        )
    with pytest.raises(ValueError, match="current"):
        select(posts=(forged,), ordinal=5)


def test_feed_rejects_cross_seed_mode_graph_and_non_neighbor_source() -> None:
    cursor = initial_cursor()
    for name, kwargs in (
        ("seed", {"matched_seed": 18}),
        ("mode", {"exposure_mode": "shuffled_social"}),
        ("graph", {"exposure_graph_hash": "b" * 64}),
    ):
        arguments = {
            "unread_public_posts": timeline(),
            "topic_package": topic(),
            "neighbor_agent_ids": ("agent-a", "agent-b", "agent-c"),
            "cursor": cursor,
            "receiver_event_id": "event-0005",
            "receiver_event_ordinal": 5,
            "matched_seed": 17,
            "exposure_mode": "ws_neighbors",
            "exposure_graph_hash": "a" * 64,
            "capacity": 4,
            "mock_only": True,
            **kwargs,
        }
        with pytest.raises(ValueError, match=name):
            select_unread_feed(**arguments)

    with pytest.raises(ValueError, match="neighbor"):
        select_unread_feed(
            unread_public_posts=timeline(),
            topic_package=topic(),
            neighbor_agent_ids=("agent-a",),
            cursor=cursor,
            receiver_event_id="event-0005",
            receiver_event_ordinal=5,
            matched_seed=17,
            exposure_mode="ws_neighbors",
            exposure_graph_hash="a" * 64,
            capacity=4,
            mock_only=True,
        )

    cross_seed = (post("agent-a", None, 0, seed=18),)
    with pytest.raises(ValueError, match="post.*seed|seed.*post"):
        select_unread_feed(
            unread_public_posts=cross_seed,
            topic_package=topic(),
            neighbor_agent_ids=("agent-a",),
            cursor=cursor,
            receiver_event_id="event-0005",
            receiver_event_ordinal=5,
            matched_seed=17,
            exposure_mode="ws_neighbors",
            exposure_graph_hash="a" * 64,
            capacity=4,
            mock_only=True,
        )

    selection = select()
    with pytest.raises(ValueError, match="cursor.*seed|seed.*cursor"):
        replace(selection, cursor_before=initial_cursor(seed=18))


def test_message_slots_use_independent_seed_reused_across_e1_and_e2_without_copying_content() -> (
    None
):
    e2 = select()
    e1_posts = (
        post("agent-d", None, 0),
        post("agent-e", None, 0),
        post("agent-f", None, 0),
        post("agent-d", 1, 1),
        post("agent-d", 2, 2),
        post("agent-e", 3, 1),
        post("agent-f", 4, 1),
    )
    e1 = select_unread_feed(
        unread_public_posts=e1_posts,
        topic_package=topic(),
        neighbor_agent_ids=("agent-d", "agent-e", "agent-f"),
        cursor=initial_cursor(mode="shuffled_social", graph_hash="b" * 64),
        receiver_event_id="event-0005",
        receiver_event_ordinal=5,
        matched_seed=17,
        exposure_mode="shuffled_social",
        exposure_graph_hash="b" * 64,
        capacity=4,
        mock_only=True,
    )

    assert e1.slot_rng_provenance == e2.slot_rng_provenance
    assert tuple(item.display_slot for item in e1.selected) == tuple(
        item.display_slot for item in e2.selected
    )
    assert {item.source_agent_id for item in e1.selected} != {
        item.source_agent_id for item in e2.selected
    }
    assert "exposure_mode" not in e1.slot_rng_provenance.coordinates
    assert "post" not in " ".join(e1.slot_rng_provenance.coordinates).lower()

    sparse_e1 = select_unread_feed(
        unread_public_posts=e1_posts[:3],
        topic_package=topic(),
        neighbor_agent_ids=("agent-d", "agent-e", "agent-f"),
        cursor=initial_cursor(mode="shuffled_social", graph_hash="b" * 64),
        receiver_event_id="event-0005",
        receiver_event_ordinal=5,
        matched_seed=17,
        exposure_mode="shuffled_social",
        exposure_graph_hash="b" * 64,
        capacity=4,
        mock_only=True,
    )
    assert sparse_e1.slot_rng_provenance == e2.slot_rng_provenance


def test_exposure_payload_contains_public_rendering_audit_and_no_private_confidence() -> None:
    result = select()
    for item in result.selected:
        payload = item.to_payload()
        assert payload["rendered_text"]
        assert payload["rendered_hash"]
        assert payload["message_age"] == 5 - payload["source_event_ordinal"]
        assert "confidence" not in payload
        assert "private_reason" not in payload
        assert set(payload) >= {
            "post_id",
            "post_hash",
            "source_agent_id",
            "source_event_id",
            "original_order",
            "display_slot",
            "rendered_text",
            "rendered_hash",
        }
    assert result.diagnostics["message_count"] == 4
    assert result.diagnostics["repeated_source_share"] > 0
    assert result.diagnostics["empty_feed"] is False


def test_feed_rejects_numeric_stance_label_before_public_rendering() -> None:
    source = post("agent-a", None, 0)
    forged = object.__new__(PublicPost)
    for name in PublicPost.__dataclass_fields__:
        object.__setattr__(forged, name, "7" if name == "stance_label" else getattr(source, name))
    with pytest.raises(ValueError, match="stance_label"):
        select(posts=(forged,), ordinal=1)


def test_extended_exposure_record_binds_selection_cursor_posts_slots_and_rendering() -> None:
    selection = select()
    record = build_exposure_record(selection, mock_only=True)

    assert record.event_ordinal == selection.receiver_event_ordinal
    assert record.selection_id == selection.selection_id
    assert record.selection_hash == selection.record_hash
    assert record.cursor_before_hash == selection.cursor_before.record_hash
    assert record.cursor_after_hash == selection.cursor_after.record_hash
    assert record.candidate_post_ids == tuple(item.post_id for item in selection.candidates)
    assert record.selected_post_ids == tuple(item.post_id for item in selection.selected)
    assert record.expired_post_ids == tuple(item.post_id for item in selection.expired)
    assert record.source_agent_ids == tuple(item.source_agent_id for item in selection.selected)
    assert record.display_slots == tuple(item.display_slot for item in selection.selected)
    assert record.rendered_hashes == tuple(item.rendered_hash for item in selection.selected)
    assert record.record_hash
    assert type(record).from_payload(record.to_payload()) == record


def test_self_history_only_has_no_social_candidates_and_no_graph() -> None:
    cursor = FeedCursor.initial(
        matched_seed=17,
        receiver_agent_id="agent-r",
        exposure_mode="self_history_only",
        exposure_graph_hash=None,
        mock_only=True,
    )
    result = select_unread_feed(
        unread_public_posts=(),
        topic_package=topic(),
        neighbor_agent_ids=(),
        cursor=cursor,
        receiver_event_id="event-0005",
        receiver_event_ordinal=5,
        matched_seed=17,
        exposure_mode="self_history_only",
        exposure_graph_hash=None,
        capacity=4,
        mock_only=True,
    )
    assert result.candidates == result.selected == ()


def test_feed_scales_to_one_thousand_public_posts() -> None:
    posts = tuple(post(f"agent-{index:04d}", None, 0) for index in range(1000))
    result = select_unread_feed(
        unread_public_posts=posts,
        topic_package=topic(),
        neighbor_agent_ids=tuple(f"agent-{index:04d}" for index in range(1000)),
        cursor=FeedCursor.initial(
            matched_seed=17,
            receiver_agent_id="agent-r",
            exposure_mode="ws_neighbors",
            exposure_graph_hash="a" * 64,
            mock_only=True,
        ),
        receiver_event_id="event-0001",
        receiver_event_ordinal=1,
        matched_seed=17,
        exposure_mode="ws_neighbors",
        exposure_graph_hash="a" * 64,
        capacity=8,
        mock_only=True,
    )
    assert len(result.candidates) == 1000
    assert len(result.selected) == 8
    assert len(result.expired) == 992


def test_feed_api_accepts_only_incremental_unread_slice() -> None:
    parameters = inspect.signature(select_unread_feed).parameters
    assert "unread_public_posts" in parameters
    assert "public_posts" not in parameters


def test_n1000_t50_call_shape_passes_only_incremental_unread_slices() -> None:
    cursors = {
        agent_id: FeedCursor.initial(
            matched_seed=17,
            receiver_agent_id=agent_id,
            exposure_mode="ws_neighbors",
            exposure_graph_hash="a" * 64,
            mock_only=True,
        )
        for agent_id in (f"agent-{index:04d}" for index in range(1000))
    }
    package = topic()
    event_ordinal = 0
    for _sweep in range(50):
        for agent_id, cursor in cursors.items():
            result = select_unread_feed(
                unread_public_posts=(),
                topic_package=package,
                neighbor_agent_ids=(),
                cursor=cursor,
                receiver_event_id=f"event-{event_ordinal:05d}",
                receiver_event_ordinal=event_ordinal,
                matched_seed=17,
                exposure_mode="ws_neighbors",
                exposure_graph_hash="a" * 64,
                capacity=4,
                mock_only=True,
            )
            assert result.candidates == ()
            cursors[agent_id] = result.cursor_after
            event_ordinal += 1
    assert event_ordinal == 50_000


def test_round0_admission_is_invariant_to_input_order() -> None:
    posts = tuple(post(f"agent-{index}", None, 0) for index in range(10))
    neighbors = tuple(f"agent-{index}" for index in range(10))
    common = {
        "topic_package": topic(),
        "neighbor_agent_ids": neighbors,
        "cursor": initial_cursor(),
        "receiver_event_id": "event-0001",
        "receiver_event_ordinal": 1,
        "matched_seed": 17,
        "exposure_mode": "ws_neighbors",
        "exposure_graph_hash": "a" * 64,
        "capacity": 4,
        "mock_only": True,
    }
    forward = select_unread_feed(unread_public_posts=posts, **common)
    reverse = select_unread_feed(unread_public_posts=tuple(reversed(posts)), **common)
    assert tuple(item.post_id for item in forward.selected) == tuple(
        item.post_id for item in reverse.selected
    )


def test_neighbor_set_order_is_canonical_for_selection_identity_and_hash() -> None:
    common = {
        "unread_public_posts": timeline(),
        "topic_package": topic(),
        "cursor": initial_cursor(),
        "receiver_event_id": "event-0005",
        "receiver_event_ordinal": 5,
        "matched_seed": 17,
        "exposure_mode": "ws_neighbors",
        "exposure_graph_hash": "a" * 64,
        "capacity": 4,
        "mock_only": True,
    }
    forward = select_unread_feed(neighbor_agent_ids=("agent-a", "agent-b", "agent-c"), **common)
    reverse = select_unread_feed(neighbor_agent_ids=("agent-c", "agent-b", "agent-a"), **common)
    assert reverse == forward
    assert reverse.selection_id == forward.selection_id
    assert reverse.record_hash == forward.record_hash


def test_selection_validator_replays_candidates_latest_b_diagnostics_and_provenance() -> None:
    selection = select()
    validate_exposure_selection(
        selection,
        unread_public_posts=timeline(),
        topic_package=topic(),
        neighbor_agent_ids=("agent-a", "agent-b", "agent-c"),
        cursor=initial_cursor(),
        receiver_event_id="event-0005",
        receiver_event_ordinal=5,
        matched_seed=17,
        exposure_mode="ws_neighbors",
        exposure_graph_hash="a" * 64,
        capacity=4,
    )
    forged = object.__new__(ExposureSelection)
    for name in ExposureSelection.__dataclass_fields__:
        object.__setattr__(forged, name, getattr(selection, name))
    object.__setattr__(forged, "diagnostics", {**dict(selection.diagnostics), "message_count": 999})
    with pytest.raises(ValueError, match="selection.*replay"):
        validate_exposure_selection(
            forged,
            unread_public_posts=timeline(),
            topic_package=topic(),
            neighbor_agent_ids=("agent-a", "agent-b", "agent-c"),
            cursor=initial_cursor(),
            receiver_event_id="event-0005",
            receiver_event_ordinal=5,
            matched_seed=17,
            exposure_mode="ws_neighbors",
            exposure_graph_hash="a" * 64,
            capacity=4,
        )


def test_selection_validator_rejects_reenveloped_selected_and_provenance_attacks() -> None:
    selection = select()

    def raw_copy(value: object, **changes: object) -> object:
        forged = object.__new__(type(value))
        for name in type(value).__dataclass_fields__:
            object.__setattr__(forged, name, changes.get(name, getattr(value, name)))
        return forged

    first = selection.selected[0]
    forged_item = raw_copy(
        first,
        source_agent_id="agent-forged",
        public_reason="forged public reason",
        message_age=999,
        original_order=999,
    )
    wrong_slot_rng = raw_copy(selection.slot_rng_provenance, namespace="round0_tiebreak")
    cases = (
        {"selected": (forged_item,) + selection.selected[1:]},
        {"selected": selection.selected[:-1], "expired": selection.expired + (first,)},
        {"slot_rng_provenance": wrong_slot_rng},
        {
            "input_hashes": {
                **dict(selection.input_hashes),
                "unread_public_posts": "f" * 64,
            }
        },
    )
    common = {
        "unread_public_posts": timeline(),
        "topic_package": topic(),
        "neighbor_agent_ids": ("agent-a", "agent-b", "agent-c"),
        "cursor": initial_cursor(),
        "receiver_event_id": "event-0005",
        "receiver_event_ordinal": 5,
        "matched_seed": 17,
        "exposure_mode": "ws_neighbors",
        "exposure_graph_hash": "a" * 64,
        "capacity": 4,
    }
    for changes in cases:
        forged = raw_copy(selection, **changes)
        with pytest.raises(ValueError, match="selection.*replay"):
            validate_exposure_selection(forged, **common)


def test_exposure_record_validator_binds_selection_posts_and_updates() -> None:
    selection = select()
    record = build_exposure_record(selection, mock_only=True)
    posts_by_id = {value.post_id: value for value in timeline()}
    # Source-update objects are reconstructed from the helper's deterministic posts below.
    source_updates = tuple(
        PrivateUpdate.create(
            topic_package=topic(),
            matched_seed=value.matched_seed,
            agent_id=value.author_agent_id,
            event_id=value.source_event_id,
            event_ordinal=value.published_event_ordinal,
            sequence_index=(
                0
                if value.published_event_ordinal is None
                else int(value.stance_label.removeprefix("label-"))
            ),
            stance_label=value.stance_label,
            reason=value.public_reason,
            confidence=None if value.published_event_ordinal is None else 3,
            published=True,
            source_attempt_id=None
            if value.published_event_ordinal is None
            else f"attempt-{value.published_event_ordinal:04d}-1",
            mock_only=True,
        )
        for value in timeline()
    )
    updates_by_id = {value.update_id: value for value in source_updates}
    validate_exposure_record(record, selection, posts_by_id, updates_by_id, topic())
    forged_record = object.__new__(type(record))
    for name in type(record).__dataclass_fields__:
        object.__setattr__(forged_record, name, getattr(record, name))
    object.__setattr__(
        forged_record, "source_post_hashes", ("f" * 64,) + record.source_post_hashes[1:]
    )
    with pytest.raises(ValueError, match="record.*replay|source post"):
        validate_exposure_record(forged_record, selection, posts_by_id, updates_by_id, topic())
