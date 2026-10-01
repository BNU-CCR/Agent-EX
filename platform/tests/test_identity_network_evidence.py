import json

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.contracts import study_cells
from test_identity_network_execution import prepared


def evidence_type():
    from agent_ex.identity_network.evidence import StudyEventInputEvidence

    return StudyEventInputEvidence


@pytest.mark.parametrize("cell", study_cells())
def test_input_round_trip_and_retry_identity(cell):
    cls = evidence_type()
    a = cls.from_prepared(prepared(cell, attempt_index=1))
    b = cls.from_prepared(prepared(cell, attempt_index=2))
    assert a.record_hash == b.record_hash
    payload = json.loads(json.dumps(a.to_payload()))
    assert cls.from_payload(payload) == a
    assert canonical_payload_hash(payload["topic_package"]) == a.topic_package.package_hash
    assert "request" not in payload
    assert "attempt_index" not in payload


def rehash(payload):
    payload["record_hash"] = canonical_payload_hash(
        {k: v for k, v in payload.items() if k != "record_hash"}
    )
    return payload


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "foreign-run"),
        ("event_ordinal", True),
        ("publish_flag", 1),
        ("study_id", "legacy"),
        ("receiver_agent_id", "foreign"),
    ],
)
def test_rehashed_identity_drift_rejected(field, value):
    cls = evidence_type()
    payload = cls.from_prepared(prepared(study_cells()[0])).to_payload()
    payload[field] = value
    with pytest.raises((TypeError, ValueError)):
        cls.from_payload(rehash(payload))


def test_hash_and_unknown_fields_fail_closed():
    cls = evidence_type()
    payload = cls.from_prepared(prepared(study_cells()[0])).to_payload()
    payload["previous_event_hash"] = "c" * 64
    with pytest.raises(ValueError, match="hash"):
        cls.from_payload(payload)
    payload = rehash(payload)
    payload["extra"] = "ignored?"
    with pytest.raises(ValueError, match="fields"):
        cls.from_payload(rehash(payload))


def test_rehashed_metadata_does_not_grant_formal_authority():
    cls = evidence_type()
    payload = cls.from_prepared(prepared(study_cells()[0])).to_payload()
    payload["metadata"]["formal_parameter_authority"] = True
    with pytest.raises(ValueError, match="metadata"):
        cls.from_payload(rehash(payload))


def test_rehashed_prompt_projection_drift_rejected():
    cls = evidence_type()
    payload = cls.from_prepared(prepared(study_cells()[0])).to_payload()
    visible = json.loads(payload["prompt"]["messages"][1]["content"])
    visible["self_group"] = "Blue"
    payload["prompt"]["messages"][1]["content"] = json.dumps(visible)
    payload["prompt"]["prompt_hash"] = canonical_payload_hash(payload["prompt"]["messages"])
    with pytest.raises(ValueError):
        cls.from_payload(rehash(payload))


def test_schema_decoder_preserves_legacy_and_decodes_sis(tmp_path, monkeypatch):
    from agent_ex.storage import RunStorage
    from test_storage import prepared_evidence_bundle
    import agent_ex.storage as storage_module

    decoder = getattr(storage_module, "decode_event_input_payload", None)
    assert callable(decoder), "missing discriminated input decoder"
    original = RunStorage.create.__func__

    def create(cls, *args, **kwargs):
        store = original(cls, *args, **kwargs)
        store.acquire_run_lease().acquire()
        return store

    monkeypatch.setattr(RunStorage, "create", classmethod(create))
    store, values = prepared_evidence_bundle(tmp_path)
    try:
        legacy = values["event_input"]
        assert decoder(legacy.to_payload()) == legacy
        sis = evidence_type().from_prepared(prepared(study_cells()[0]))
        assert decoder(sis.to_payload()) == sis
        with pytest.raises(ValueError, match="unsupported"):
            decoder({**sis.to_payload(), "schema_version": "future-input.v99"})
        payload = sis.to_payload()
        store._connection.execute(
            "INSERT INTO event_input_evidence (event_id, payload, record_hash) VALUES (?, ?, ?)",
            (
                sis.event_id,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                sis.record_hash,
            ),
        )
        with pytest.raises(ValueError, match="legacy"):
            store.event_input_evidence(sis.event_id)
    finally:
        store.close()


@pytest.mark.parametrize("kind", ["metadata", "attempt"])
def test_rehashed_nested_prompt_contract_rejected(kind):
    cls = evidence_type()
    payload = cls.from_prepared(prepared(study_cells()[0])).to_payload()
    evidence = payload["prompt"]["evidence"]
    if kind == "metadata":
        evidence["metadata"]["formal_parameter_authority"] = True
    else:
        evidence["attempt_index"] = 1
    payload["prompt"]["evidence_hash"] = canonical_payload_hash(evidence)
    with pytest.raises(ValueError):
        cls.from_payload(rehash(payload))


@pytest.mark.parametrize(
    "entry",
    [
        {"stance": "unknown", "reason": "Prior.", "published": False},
        {"stance": "label-2", "reason": 5, "published": False},
        {"stance": "label-2", "reason": "Prior.", "published": "false"},
        {"stance": "label-2", "reason": "Prior.", "published": False, "extra": 1},
    ],
)
def test_coordinated_history_drift_rejected(entry):
    cls = evidence_type()
    payload = cls.from_prepared(prepared(study_cells()[0])).to_payload()
    evidence = payload["prompt"]["evidence"]
    evidence["self_history"] = [entry]
    messages = payload["prompt"]["messages"]
    visible = json.loads(messages[1]["content"])
    visible["memory"] = [entry]
    messages[1]["content"] = json.dumps(visible)
    evidence["exact_messages_shown"] = messages
    payload["prompt"]["prompt_hash"] = canonical_payload_hash(messages)
    payload["prompt"]["evidence_hash"] = canonical_payload_hash(evidence)
    with pytest.raises((TypeError, ValueError)):
        cls.from_payload(rehash(payload))


@pytest.mark.parametrize("kind", ["duplicate_post", "source_two_aliases", "alias_two_sources"])
def test_coordinated_post_identity_drift_rejected(kind):
    cls = evidence_type()
    payload = cls.from_prepared(prepared(study_cells()[1])).to_payload()
    evidence = payload["prompt"]["evidence"]
    first = evidence["shown_posts"][0]
    second = dict(first)
    if kind != "duplicate_post":
        second["post_id"] = "p2"
    if kind == "source_two_aliases":
        second["member_id"] = "member-2"
    if kind == "alias_two_sources":
        second["source_agent_id"] = "other-source"
    evidence["shown_posts"] = [first, second]
    evidence["post_ids"] = [first["post_id"], second["post_id"]]
    evidence["source_agent_ids"] = [first["source_agent_id"], second["source_agent_id"]]
    evidence["source_groups"] *= 2
    evidence["local_opinion_context"] *= 2
    messages = payload["prompt"]["messages"]
    visible = json.loads(messages[1]["content"])
    visible["social_messages"] = [
        {k: post[k] for k in ("member_id", "stance", "reason")} for post in (first, second)
    ]
    messages[1]["content"] = json.dumps(visible)
    evidence["exact_messages_shown"] = messages
    payload["prompt"]["prompt_hash"] = canonical_payload_hash(messages)
    payload["prompt"]["evidence_hash"] = canonical_payload_hash(evidence)
    with pytest.raises(ValueError):
        cls.from_payload(rehash(payload))
