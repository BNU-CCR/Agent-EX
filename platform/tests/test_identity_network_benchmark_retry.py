"""Synthetic journal tests; no transport or research-result evidence."""

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.benchmark_retry import append_retry_record, replay_retry_journal


PLAN = "a" * 64
WIRES = (("trial-1", "b" * 64), ("trial-2", "c" * 64))


def add(rows, kind, evidence=None, bindings=WIRES):
    return (
        *rows,
        append_retry_record(bindings, rows, plan_hash=PLAN, kind=kind, evidence=evidence),
    )


def attempt(rows, classification):
    rows = add(rows, "INTENT")
    rows = add(rows, "RESULT", {"classification": classification, "response_record_hash": "d" * 64})
    return rows


def summary(rows, bindings=WIRES):
    return replay_retry_journal(bindings, rows, plan_hash=PLAN)


def test_empty_prefix_and_completed_two_trials():
    assert summary(())["next_action"] == "DISPATCH"
    rows = attempt((), "VALID")
    assert summary(rows)["valid_count"] == 1
    rows = attempt(rows, "VALID")
    assert summary(rows)["phase"] == "COMPLETE"
    assert summary(rows)["next_action"] == "VERIFY_TRANSPORT"
    assert summary(rows)["transport_evidence_verified"] is False
    with pytest.raises(ValueError):
        add(rows, "INTENT")


def test_two_extra_retries_preserve_logical_identity_and_wire():
    rows = attempt((), "PARSE_INVALID")
    assert summary(rows)["phase"] == "RETRY_READY"
    rows = attempt(rows, "HTTP_429_REJECTED")
    rows = attempt(rows, "VALID")
    intents = [row for row in rows if row["kind"] == "INTENT"]
    assert [r["attempt_index"] for r in intents] == [1, 2, 3]
    assert len({r["logical_request_id"] for r in intents}) == 1
    assert len({r["attempt_id"] for r in intents}) == 3
    assert all(r["wire_hash"] == WIRES[0][1] for r in intents)


def test_exhaustion_is_incomplete_and_cannot_skip_case():
    rows = ()
    for _ in range(3):
        rows = attempt(rows, "PARSE_INVALID")
    state = summary(rows)
    assert state["phase"] == "INCOMPLETE"
    assert state["valid_count"] == 0
    assert state["ordinal"] == 0
    assert state["next_action"] == "STOP"
    with pytest.raises(ValueError):
        add(rows, "INTENT")


@pytest.mark.parametrize(
    "classification", ["TIMEOUT_AMBIGUOUS", "TRANSPORT_AMBIGUOUS", "HTTP_5XX_AMBIGUOUS"]
)
def test_ambiguous_response_never_retries(classification):
    rows = attempt((), classification)
    assert summary(rows)["phase"] == "BLOCKED_AMBIGUOUS"
    with pytest.raises(ValueError):
        add(rows, "INTENT")


def test_crash_after_intent_requires_evidence_not_resend():
    rows = add((), "INTENT")
    assert summary(rows)["next_action"] == "RECOVER_RESPONSE_OR_STOP"
    with pytest.raises(ValueError):
        add(rows, "INTENT")


def test_illegal_result_or_missing_evidence():
    with pytest.raises(ValueError):
        add((), "RESULT", {"classification": "VALID", "response_record_hash": "d" * 64})
    rows = add((), "INTENT")
    for evidence in (
        None,
        {},
        {"classification": "VALID", "response_record_hash": "bad"},
        {"classification": "UNKNOWN", "response_record_hash": "d" * 64},
    ):
        with pytest.raises(ValueError):
            add(rows, "RESULT", evidence)


def test_tamper_even_with_recomputed_record_hash_is_rejected():
    rows = add((), "INTENT")
    bad = dict(rows[0])
    bad["attempt_index"] = 2
    bad["record_hash"] = canonical_payload_hash(
        {k: v for k, v in bad.items() if k != "record_hash"}
    )
    with pytest.raises(ValueError):
        summary((bad,))
    with pytest.raises(ValueError):
        summary(rows, (("trial-1", "e" * 64), WIRES[1]))


def test_duplicate_binding_invalid_hash_and_boolean_index_fail_closed():
    for bindings in ((), (WIRES[0], WIRES[0]), (("trial-1", "bad"),)):
        with pytest.raises(ValueError):
            summary((), bindings)
    row = dict(add((), "INTENT")[0])
    row["attempt_index"] = True
    with pytest.raises(ValueError):
        summary((row,))
