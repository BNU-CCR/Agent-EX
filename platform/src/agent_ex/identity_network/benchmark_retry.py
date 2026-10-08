"""Pure v2 retry-prefix contract. Not a durable store or response authenticator.

RESULT classifications must come from verified saved transport/parse evidence.
This module deliberately cannot authorize dispatch or substantive inference.
"""

import re
from collections.abc import Mapping

from ..domain import canonical_payload_hash

SCHEMA = "sis.manipulation.benchmark-retry-transition.v2"
RETRYABLE = frozenset({"PARSE_INVALID", "HTTP_429_REJECTED"})
AMBIGUOUS = frozenset({"TIMEOUT_AMBIGUOUS", "TRANSPORT_AMBIGUOUS", "HTTP_5XX_AMBIGUOUS"})


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("canonical SHA-256 required")
    return value


def _bindings(bindings):
    result = tuple(bindings)
    if not result:
        raise ValueError("nonempty ordered trial/wire bindings required")
    ids = []
    for item in result:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("trial/wire pair required")
        trial, wire = item
        if type(trial) is not str or not trial:
            raise ValueError("nonempty trial identity required")
        _hash(wire)
        ids.append(trial)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate trial identity")
    return result


def _record(bindings, *, plan_hash, seq, tail, ordinal, attempt, phase, kind, evidence):
    if ordinal == len(bindings):
        raise ValueError("complete journal cannot advance")
    if kind == "INTENT":
        if phase not in {"READY", "RETRY_READY"} or evidence is not None:
            raise ValueError("dispatch requires resolved ready prefix")
    elif kind == "RESULT":
        if phase != "INTENT" or not isinstance(evidence, Mapping):
            raise ValueError("result requires intent and saved evidence")
        if set(evidence) != {"classification", "response_record_hash"}:
            raise ValueError("result evidence fields differ")
        _hash(evidence["response_record_hash"])
        if evidence["classification"] not in RETRYABLE | AMBIGUOUS | {"VALID"}:
            raise ValueError("unsupported verified result classification")
        evidence = dict(evidence)
    else:
        raise ValueError("unknown transition kind")
    trial, wire = bindings[ordinal]
    logical_id = canonical_payload_hash(
        {"plan_hash": plan_hash, "trial_id": trial, "wire_hash": wire}
    )
    content = {
        "schema_version": SCHEMA,
        "plan_hash": plan_hash,
        "seq": seq,
        "previous_record_hash": tail,
        "ordinal": ordinal,
        "trial_id": trial,
        "wire_hash": wire,
        "logical_request_id": logical_id,
        "attempt_index": attempt,
        "attempt_id": canonical_payload_hash(
            {"logical_request_id": logical_id, "attempt_index": attempt}
        ),
        "kind": kind,
        "evidence": evidence,
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def replay_retry_journal(bindings, records, *, plan_hash):
    """Cold replay an exact prefix. Self-consistent hashes are not source proof."""
    bindings = _bindings(bindings)
    _hash(plan_hash)
    ordinal, attempt, phase, tail, count = 0, 1, "READY", None, 0
    for count, record in enumerate(records, 1):
        if not isinstance(record, Mapping):
            raise ValueError("transition record required")
        expected = _record(
            bindings,
            plan_hash=plan_hash,
            seq=count,
            tail=tail,
            ordinal=ordinal,
            attempt=attempt,
            phase=phase,
            kind=record.get("kind"),
            evidence=record.get("evidence"),
        )
        # Reject bool/int equality and noncanonical representations, not just ==.
        if canonical_payload_hash(record) != canonical_payload_hash(expected):
            raise ValueError("transition binding/order/hash differs")
        tail = expected["record_hash"]
        if record["kind"] == "INTENT":
            phase = "INTENT"
        else:
            classification = record["evidence"]["classification"]
            if classification == "VALID":
                ordinal, attempt, phase = ordinal + 1, 1, "READY"
            elif classification in AMBIGUOUS:
                phase = "BLOCKED_AMBIGUOUS"
            elif attempt == 3:
                phase = "INCOMPLETE"
            else:
                attempt, phase = attempt + 1, "RETRY_READY"
    if ordinal == len(bindings):
        phase = "COMPLETE"
    action = {
        "READY": "DISPATCH",
        "RETRY_READY": "DISPATCH",
        "INTENT": "RECOVER_RESPONSE_OR_STOP",
        "BLOCKED_AMBIGUOUS": "STOP",
        "INCOMPLETE": "STOP",
        "COMPLETE": "VERIFY_TRANSPORT",
    }[phase]
    return {
        "phase": phase,
        "ordinal": ordinal,
        "attempt_index": attempt,
        "valid_count": ordinal,
        "trial_count": len(bindings),
        "transition_count": count,
        "tail_hash": tail,
        "next_action": action,
        "transport_evidence_verified": False,
        "dispatch_authorized": False,
        "formal_parameter_authority": False,
    }


def append_retry_record(bindings, records, *, plan_hash, kind, evidence=None):
    """Build the next record; caller still owes atomic durable write before HTTP."""
    bindings, records = _bindings(bindings), tuple(records)
    state = replay_retry_journal(bindings, records, plan_hash=plan_hash)
    return _record(
        bindings,
        plan_hash=plan_hash,
        seq=state["transition_count"] + 1,
        tail=state["tail_hash"],
        ordinal=state["ordinal"],
        attempt=state["attempt_index"],
        phase=state["phase"],
        kind=kind,
        evidence=evidence,
    )
