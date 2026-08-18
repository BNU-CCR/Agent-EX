from __future__ import annotations

import inspect

import pytest

from agent_ex.memory import MemoryItem, MemoryView, build_memory_view, validate_memory_view
from agent_ex.state import PrivateUpdate
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


def history(agent_id: str = "agent-0001", count: int = 6) -> tuple[PrivateUpdate, ...]:
    values = [
        PrivateUpdate.create(
            topic_package=topic(),
            matched_seed=17,
            agent_id=agent_id,
            event_id=None,
            event_ordinal=None,
            sequence_index=0,
            stance_label="label-0",
            reason="round zero private reason",
            confidence=None,
            published=True,
            source_attempt_id=None,
            mock_only=True,
        )
    ]
    for index in range(1, count):
        values.append(
            PrivateUpdate.create(
                topic_package=topic(),
                matched_seed=17,
                agent_id=agent_id,
                event_id=f"event-{index:04d}",
                event_ordinal=index * 3,
                sequence_index=index,
                stance_label=f"label-{index % 7}",
                reason=f"private reason {index}",
                confidence=(index % 5) + 1,
                published=index % 2 == 0,
                source_attempt_id=f"attempt-{index:04d}-1",
                mock_only=True,
            )
        )
    return tuple(values)


@pytest.mark.parametrize("window", (1, 3, 5))
def test_memory_uses_explicit_mock_window_and_latest_successful_private_updates(
    window: int,
) -> None:
    complete = history()
    view = build_memory_view(
        private_updates=complete,
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=window,
        mock_only=True,
    )

    assert tuple(item.sequence_index for item in view.items) == tuple(range(6 - window, 6))
    assert tuple(item.published for item in view.items) == tuple(
        update.published for update in complete[-window:]
    )
    assert view.source_update_count == len(complete)
    assert view.metadata["research_parameter_status"] == "not_frozen"
    assert MemoryView.from_payload(view.to_payload()) == view
    assert all(isinstance(item, MemoryItem) for item in view.items)


def test_round0_is_not_permanently_pinned_and_items_are_oldest_to_newest() -> None:
    view = build_memory_view(
        private_updates=history(),
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=3,
        mock_only=True,
    )

    assert tuple(item.sequence_index for item in view.items) == (3, 4, 5)
    assert all(item.event_ordinal is not None for item in view.items)


def test_memory_keeps_unpublished_private_reason_and_confidence_for_self_only() -> None:
    view = build_memory_view(
        private_updates=history(),
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=5,
        mock_only=True,
    )

    unpublished = [item for item in view.items if not item.published]
    assert unpublished
    assert all(item.private_reason.startswith("private reason") for item in unpublished)
    assert all(item.confidence is not None for item in unpublished)


def test_memory_rejects_cross_agent_noncontiguous_or_reordered_history() -> None:
    complete = history()
    foreign = history(agent_id="agent-0002", count=2)[-1]
    with pytest.raises(ValueError, match="agent"):
        build_memory_view(
            private_updates=complete + (foreign,),
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            window=3,
            mock_only=True,
        )
    with pytest.raises(ValueError, match="sequence"):
        build_memory_view(
            private_updates=(complete[0], complete[2]),
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            window=3,
            mock_only=True,
        )
    with pytest.raises(ValueError, match="ordinal"):
        build_memory_view(
            private_updates=(complete[0], complete[2], complete[1]),
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            window=3,
            mock_only=True,
        )


def test_memory_rejects_unapproved_mock_window_bool_and_implicit_defaults() -> None:
    assert (
        inspect.signature(build_memory_view).parameters["window"].default is inspect.Parameter.empty
    )
    for value in (0, 2, 6, True):
        error = TypeError if value is True else ValueError
        with pytest.raises(error, match="window"):
            build_memory_view(
                private_updates=history(),
                topic_package=topic(),
                matched_seed=17,
                agent_id="agent-0001",
                window=value,
                mock_only=True,
            )
    with pytest.raises(ValueError, match="mock_only"):
        build_memory_view(
            private_updates=history(),
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            window=3,
            mock_only=False,
        )


def test_memory_empty_history_is_legal_and_hash_binds_full_history_not_only_view() -> None:
    empty = build_memory_view(
        private_updates=(),
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=3,
        mock_only=True,
    )
    short = build_memory_view(
        private_updates=history(count=2),
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=3,
        mock_only=True,
    )
    longer = build_memory_view(
        private_updates=history(count=5),
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=3,
        mock_only=True,
    )

    assert empty.items == ()
    assert len(short.items) == 2
    assert (
        longer.source_history_hash
        != build_memory_view(
            private_updates=history(count=4),
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            window=3,
            mock_only=True,
        ).source_history_hash
    )


def test_memory_scales_to_one_thousand_updates_without_model_calls() -> None:
    view = build_memory_view(
        private_updates=history(count=1000),
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=5,
        mock_only=True,
    )
    assert tuple(item.sequence_index for item in view.items) == (995, 996, 997, 998, 999)


def test_memory_view_binds_expected_matched_seed() -> None:
    view = build_memory_view(
        private_updates=history(),
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=3,
        mock_only=True,
    )
    assert view.matched_seed == 17


def test_memory_validator_replays_full_history_latest_k_and_item_seed() -> None:
    updates = history()
    view = build_memory_view(
        private_updates=updates,
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        window=3,
        mock_only=True,
    )
    validate_memory_view(view, updates, topic())
    forged = object.__new__(MemoryView)
    for name in MemoryView.__dataclass_fields__:
        object.__setattr__(forged, name, getattr(view, name))
    bad_item = object.__new__(MemoryItem)
    for name in MemoryItem.__dataclass_fields__:
        object.__setattr__(bad_item, name, getattr(view.items[0], name))
    object.__setattr__(bad_item, "matched_seed", 18)
    object.__setattr__(forged, "items", (bad_item,) + view.items[1:])
    with pytest.raises(ValueError, match="memory.*replay|item.*seed"):
        validate_memory_view(forged, updates, topic())

    for field, value in (("private_reason", "forged"), ("update_hash", "f" * 64)):
        forged_item = object.__new__(MemoryItem)
        for name in MemoryItem.__dataclass_fields__:
            object.__setattr__(
                forged_item, name, value if name == field else getattr(view.items[0], name)
            )
        object.__setattr__(forged, "items", (forged_item,) + view.items[1:])
        with pytest.raises(ValueError, match="memory.*replay"):
            validate_memory_view(forged, updates, topic())
