from __future__ import annotations

import copy

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.state import (
    LatestPublicPointer,
    PrivateState,
    PrivateUpdate,
    PublicPost,
    validate_latest_public_pointer,
    validate_private_state,
    validate_public_post,
)
from agent_ex.topic import TopicPackage


def topic() -> TopicPackage:
    return TopicPackage.from_payload(
        {
            "schema_version": "paper1.topic-package.mock.v1",
            "package_version": "0.0.1-mock",
            "topic_id": "mock-topic",
            "construct": "mock construct",
            "target_population": "mock population",
            "applicability": "mock only",
            "fact_card": "mock fact card",
            "core_statement": "mock statement",
            "paraphrases": ["mock paraphrase"],
            "stance_labels": [
                "strongly oppose",
                "oppose",
                "somewhat oppose",
                "neutral",
                "somewhat support",
                "support",
                "strongly support",
            ],
            "confidence_contract": {"minimum": 1, "maximum": 5, "analysis_only": True},
            "output_contract": ["stance", "confidence", "public_reason"],
            "argument_families": ["mock-family"],
            "round0_reason_library_artifact_id": "artifact-" + "a" * 64,
            "topic_extension_fields": [],
            "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
        }
    )


def update(
    *,
    ordinal: int | None = 4,
    sequence_index: int = 1,
    published: bool = True,
) -> PrivateUpdate:
    return PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        event_id=None if ordinal is None else "event-0004",
        event_ordinal=ordinal,
        sequence_index=sequence_index,
        stance_label="somewhat support",
        reason="A private reason that may or may not be published.",
        confidence=None if ordinal is None else 4,
        published=published,
        source_attempt_id=None if ordinal is None else "attempt-0004-1",
        mock_only=True,
    )


def test_private_update_round_trip_and_hash_bind_every_private_field() -> None:
    value = update()

    assert PrivateUpdate.from_payload(value.to_payload()) == value
    assert value.record_hash == canonical_payload_hash(value.content_payload())
    assert value.metadata == {
        "mock_only": True,
        "research_parameter_status": "not_frozen",
    }
    payload = value.to_payload()
    payload["reason"] = "forged private reason"
    with pytest.raises(ValueError, match="hash"):
        PrivateUpdate.from_payload(payload)


def test_round0_private_update_has_no_event_or_confidence_but_is_successful_history() -> None:
    value = update(ordinal=None, sequence_index=0)

    assert value.event_id is None
    assert value.source_attempt_id is None
    assert value.confidence is None
    assert value.sequence_index == 0


@pytest.mark.parametrize(
    ("field", "bad"),
    (("event_ordinal", True), ("sequence_index", True), ("confidence", True)),
)
def test_private_update_rejects_bool_as_integer(field: str, bad: object) -> None:
    arguments = {
        "topic_package": topic(),
        "matched_seed": 17,
        "agent_id": "agent-0001",
        "event_id": "event-0004",
        "event_ordinal": 4,
        "sequence_index": 1,
        "stance_label": "neutral",
        "reason": "reason",
        "confidence": 3,
        "published": False,
        "source_attempt_id": "attempt-0004-1",
        "mock_only": True,
    }
    arguments[field] = bad
    with pytest.raises(TypeError, match=field):
        PrivateUpdate.create(**arguments)


def test_private_state_advances_only_with_same_agent_next_successful_update() -> None:
    first = update(ordinal=None, sequence_index=0)
    state0 = PrivateState.from_update(first, previous=None, mock_only=True)
    second = update(ordinal=4, sequence_index=1, published=False)
    state1 = PrivateState.from_update(second, previous=state0, mock_only=True)

    assert state1.latest_update_id == second.update_id
    assert state1.successful_update_count == 2
    assert state1.reason == second.reason
    assert PrivateState.from_payload(state1.to_payload()) == state1

    foreign = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0002",
        event_id="event-0005",
        event_ordinal=5,
        sequence_index=2,
        stance_label="neutral",
        reason="foreign",
        confidence=3,
        published=False,
        source_attempt_id="attempt-0005-1",
        mock_only=True,
    )
    with pytest.raises(ValueError, match="agent"):
        PrivateState.from_update(foreign, previous=state1, mock_only=True)
    with pytest.raises(ValueError, match="sequence"):
        PrivateState.from_update(
            update(ordinal=6, sequence_index=3), previous=state1, mock_only=True
        )


def test_public_post_copies_only_public_fields_from_published_update() -> None:
    private = update(published=True)
    post = PublicPost.from_private_update(private, mock_only=True)

    assert post.author_agent_id == private.agent_id
    assert post.stance_label == private.stance_label
    assert post.public_reason == private.reason
    assert "confidence" not in post.to_payload()
    assert "private" not in " ".join(post.to_payload()).lower()
    assert PublicPost.from_payload(post.to_payload()) == post

    with pytest.raises(ValueError, match="published"):
        PublicPost.from_private_update(update(published=False), mock_only=True)


def test_latest_public_pointer_advances_without_exposing_private_state() -> None:
    round0 = PublicPost.from_private_update(update(ordinal=None, sequence_index=0), mock_only=True)
    pointer0 = LatestPublicPointer.from_post(round0, previous=None, mock_only=True)
    later = PublicPost.from_private_update(update(), mock_only=True)
    pointer1 = LatestPublicPointer.from_post(later, previous=pointer0, mock_only=True)

    assert pointer1.latest_post_id == later.post_id
    assert pointer1.latest_post_hash == later.record_hash
    assert LatestPublicPointer.from_payload(pointer1.to_payload()) == pointer1

    payload = copy.deepcopy(pointer1.to_payload())
    payload["latest_post_hash"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        LatestPublicPointer.from_payload(payload)


def test_latest_public_pointer_validator_replays_post_and_previous_pointer() -> None:
    round0 = PublicPost.from_private_update(update(ordinal=None, sequence_index=0), mock_only=True)
    pointer0 = LatestPublicPointer.from_post(round0, previous=None, mock_only=True)
    later = PublicPost.from_private_update(update(), mock_only=True)
    pointer1 = LatestPublicPointer.from_post(later, previous=pointer0, mock_only=True)
    validate_latest_public_pointer(pointer1, later, previous_pointer=pointer0)

    wrong_topic = object.__new__(PublicPost)
    for name in PublicPost.__dataclass_fields__:
        object.__setattr__(wrong_topic, name, getattr(later, name))
    object.__setattr__(wrong_topic, "topic_package_id", "other-topic")
    object.__setattr__(wrong_topic, "topic_package_hash", "f" * 64)

    for source in (
        round0,
        wrong_topic,
        PublicPost.from_private_update(
            PrivateUpdate.create(
                topic_package=topic(),
                matched_seed=18,
                agent_id="agent-0001",
                event_id="event-0004",
                event_ordinal=4,
                sequence_index=1,
                stance_label="neutral",
                reason="wrong seed",
                confidence=3,
                published=True,
                source_attempt_id="attempt-0004-1",
                mock_only=True,
            ),
            mock_only=True,
        ),
        PublicPost.from_private_update(
            PrivateUpdate.create(
                topic_package=topic(),
                matched_seed=17,
                agent_id="agent-other",
                event_id="event-0004",
                event_ordinal=4,
                sequence_index=1,
                stance_label="neutral",
                reason="wrong agent",
                confidence=3,
                published=True,
                source_attempt_id="attempt-0004-1",
                mock_only=True,
            ),
            mock_only=True,
        ),
    ):
        with pytest.raises(ValueError, match="pointer|post|seed|agent|ordinal"):
            validate_latest_public_pointer(pointer1, source, previous_pointer=pointer0)

    with pytest.raises(ValueError, match="advance|ordinal"):
        validate_latest_public_pointer(pointer0, round0, previous_pointer=pointer1)


def test_state_objects_require_explicit_mock_only_and_never_claim_formal_freeze() -> None:
    with pytest.raises(ValueError, match="mock_only"):
        PrivateUpdate.create(
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            event_id="event-0004",
            event_ordinal=4,
            sequence_index=1,
            stance_label="neutral",
            reason="reason",
            confidence=3,
            published=False,
            source_attempt_id="attempt-0004-1",
            mock_only=False,
        )


def test_private_and_public_state_bind_the_matched_seed() -> None:
    value = PrivateUpdate.create(
        topic_package=topic(),
        matched_seed=17,
        agent_id="agent-0001",
        event_id="event-0004",
        event_ordinal=4,
        sequence_index=1,
        stance_label="neutral",
        reason="reason",
        confidence=3,
        published=True,
        source_attempt_id="attempt-0004-1",
        mock_only=True,
    )
    public = PublicPost.from_private_update(value, mock_only=True)

    assert value.matched_seed == public.matched_seed == 17


def test_state_rejects_numeric_label_round0_silence_and_out_of_range_confidence() -> None:
    common = {
        "topic_package": topic(),
        "matched_seed": 17,
        "agent_id": "agent-0001",
        "event_id": "event-1",
        "event_ordinal": 1,
        "sequence_index": 1,
        "reason": "reason",
        "confidence": 3,
        "published": False,
        "source_attempt_id": "attempt-1",
        "mock_only": True,
    }
    with pytest.raises(ValueError, match="stance_label"):
        PrivateUpdate.create(**common, stance_label="7")
    with pytest.raises(ValueError, match="round-0.*published"):
        PrivateUpdate.create(
            topic_package=topic(),
            matched_seed=17,
            agent_id="agent-0001",
            event_id=None,
            event_ordinal=None,
            sequence_index=0,
            stance_label="neutral",
            reason="reason",
            confidence=None,
            published=False,
            source_attempt_id=None,
            mock_only=True,
        )
    with pytest.raises(ValueError, match="confidence"):
        PrivateUpdate.create(**{**common, "stance_label": "neutral", "confidence": 999})


def test_state_and_public_validators_replay_exact_source_fields() -> None:
    round0 = update(ordinal=None, sequence_index=0)
    state = PrivateState.from_update(round0, previous=None, mock_only=True)
    validate_private_state(state, round0, topic())
    forged_state = object.__new__(PrivateState)
    for name in PrivateState.__dataclass_fields__:
        object.__setattr__(forged_state, name, getattr(state, name))
    object.__setattr__(forged_state, "reason", "forged")
    with pytest.raises(ValueError, match="private state.*source|replay"):
        validate_private_state(forged_state, round0, topic())

    source = update()
    public = PublicPost.from_private_update(source, mock_only=True)
    validate_public_post(public, source, topic())
    forged_post = object.__new__(PublicPost)
    for name in PublicPost.__dataclass_fields__:
        object.__setattr__(forged_post, name, getattr(public, name))
    object.__setattr__(forged_post, "public_reason", "forged")
    with pytest.raises(ValueError, match="public post.*source|replay"):
        validate_public_post(forged_post, source, topic())


def test_public_post_requires_source_event_id_and_ordinal_as_a_pair() -> None:
    public = PublicPost.from_private_update(update(), mock_only=True)
    payload = public.to_payload()
    payload["source_event_id"] = None
    with pytest.raises(ValueError, match="pair"):
        PublicPost.from_payload(payload)
