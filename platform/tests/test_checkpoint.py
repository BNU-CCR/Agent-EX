from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from time import perf_counter

import pytest
import agent_ex.checkpoint as checkpoint_module

from agent_ex.checkpoint import (
    Checkpoint,
    build_checkpoint,
    load_checkpoint,
    validate_checkpoint,
    write_checkpoint_atomic,
)
from agent_ex.domain import (
    EventStatus,
    FrozenSchedule,
    ScheduleSlot,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
)
from agent_ex.storage import ExternalResponseReference, RunStorage

from test_storage import (
    append_terminal_attempt,
    attempt,
    attempt_transition,
    expected_agent_ids,
    manifest,
    schedule,
    seal_expected_initial_state,
    finalized_evidence,
    land_invocation,
    prepared_evidence_bundle,
    successful_event,
    successful_state_records,
)


@pytest.fixture(autouse=True)
def explicitly_lease_created_checkpoint_stores(monkeypatch: pytest.MonkeyPatch):
    """Checkpoint fixtures explicitly hold the writer lease during mutation."""

    original = RunStorage.create.__func__

    def create_with_explicit_lease(cls, *args: object, **kwargs: object) -> RunStorage:
        store = original(cls, *args, **kwargs)
        store.acquire_run_lease().acquire()
        return store

    monkeypatch.setattr(RunStorage, "create", classmethod(create_with_explicit_lease))
    yield


def _create_sealed_store(path: Path) -> tuple[RunStorage, object, dict[str, str]]:
    run_manifest = manifest()
    artifacts = {"population": "b" * 64}
    store = RunStorage.create(
        path,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    seal_expected_initial_state(store, run_manifest)
    return store, run_manifest, artifacts


def test_empty_sealed_run_builds_deterministic_storage_bound_checkpoint(tmp_path: Path) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        first = build_checkpoint(store)
        second = build_checkpoint(store)

        assert first == second
        assert first.version == "paper1.checkpoint.v3"
        assert first.run_id == run_manifest.run_id
        assert first.protocol_id == run_manifest.protocol_id
        assert first.protocol_version == run_manifest.protocol_version
        assert first.baseline_manifest_hash == store.binding.manifest_hash
        assert first.storage_schema_version == store.binding.schema_version
        assert first.next_event_ordinal == 0
        assert first.current_event_id == derive_event_id(run_manifest.run_id, 0)
        assert first.event_chain_head == store.progress.event_chain_head
        assert first.current_attempt_prefix == ()
        assert first.expected_exposure_mode == "self_history_only"
        assert first.expected_exposure_graph_hash is None
        assert first.expected_source_ws_artifact_hash is None
        assert validate_checkpoint(first, store) == "current"


def test_checkpoint_binds_ordered_v6_evidence_hashes_and_rejects_total_erasure(
    tmp_path: Path,
) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation = land_invocation(store, values)
    store.record_finalized_attempt(finalized_evidence(store, values, invocation))
    checkpoint = build_checkpoint(store)
    assert set(checkpoint.v6_evidence_hashes) == {
        "event_input_evidence",
        "attempt_policy_evidence",
        "adapter_execution_bindings",
        "adapter_requests",
        "invocation_evidence",
        "parse_evidence",
    }
    assert all(len(hashes) == 1 for hashes in checkpoint.v6_evidence_hashes.values())
    assert checkpoint.v6_evidence_root == canonical_payload_hash(checkpoint.v6_evidence_hashes)
    store.close()
    connection = sqlite3.connect(values["path"])
    connection.execute("PRAGMA foreign_keys = OFF")
    for table in (
        "parse_evidence",
        "invocation_evidence",
        "adapter_requests",
        "adapter_execution_bindings",
        "attempt_policy_evidence",
        "event_input_evidence",
    ):
        connection.execute(f"DELETE FROM {table}")
    connection.commit()
    connection.close()
    reopened = RunStorage.open(
        values["path"],
        manifest=values["manifest"],
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=("agent-0001", "agent-0002"),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    reopened.acquire_run_lease().acquire()
    with pytest.raises(ValueError, match="checkpoint|evidence|conflict"):
        validate_checkpoint(checkpoint, reopened)


def test_checkpoint_rejects_coordinated_v6_hash_prefix_downgrade(tmp_path: Path) -> None:
    store, values = prepared_evidence_bundle(tmp_path)
    invocation = land_invocation(store, values)
    store.record_finalized_attempt(finalized_evidence(store, values, invocation))
    checkpoint = build_checkpoint(store)
    payload = checkpoint.to_payload()
    body = payload["checkpoint"]
    body["v6_evidence_hashes"] = {name: [] for name in body["v6_evidence_hashes"]}
    body["v6_evidence_root"] = canonical_payload_hash(body["v6_evidence_hashes"])
    payload["checkpoint_hash"] = canonical_payload_hash(body)
    downgraded = Checkpoint.from_payload(payload)

    with pytest.raises(ValueError, match="checkpoint|evidence|conflict"):
        validate_checkpoint(downgraded, store)


def test_checkpoint_binds_halt_and_explicit_resume_authorization(tmp_path: Path) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "halted.sqlite3")
    with store:
        failed = attempt(run_manifest)
        append_terminal_attempt(store, failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="externally authorized stop",
            policy_evidence={"policy_id": "halt-policy", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T00:00:00+00:00",
        )
        halted = build_checkpoint(store)
        assert halted.resume_action == "halted_current_event"
        assert halted.terminal_failure_hash == failure.payload_hash
        assert halted.resume_authorization is None

        authorization = store.authorize_resume(
            authorization_id="resume-checkpoint-1",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-30T01:00:00+00:00",
        )
        resumed = build_checkpoint(store)
        assert resumed.resume_action == "retry_same_event"
        assert resumed.resume_authorization_hash == authorization.payload_hash
        assert validate_checkpoint(resumed, store) == "current"
        assert validate_checkpoint(halted, store) == "stale"

        tampered = resumed.to_payload()
        body = tampered["checkpoint"]
        assert isinstance(body, dict)
        body["resume_authorization"] = None
        body["resume_authorization_hash"] = None
        tampered["checkpoint_hash"] = canonical_payload_hash(body)
        with pytest.raises(ValueError, match="execution state disagrees|authorization"):
            Checkpoint.from_payload(tampered)


def test_validate_checkpoint_uses_exactly_one_consistent_read_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "snapshot.sqlite3")
    with store:
        checkpoint = build_checkpoint(store)
        original = RunStorage.consistent_read
        calls = 0

        def counted(self: RunStorage):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            return original(self)

        monkeypatch.setattr(RunStorage, "consistent_read", counted)
        assert validate_checkpoint(checkpoint, store) == "current"
        assert calls == 1


def test_checkpoint_binds_full_multiple_halt_authorization_prefix(tmp_path: Path) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "multi-halt.sqlite3")
    with store:
        for index in (1, 2):
            failed = attempt(run_manifest, index=index)
            append_terminal_attempt(store, failed)
            failure = store.record_terminal_failure(
                event_id=failed.event_id,
                reason=f"halt-{index}",
                policy_evidence={"policy_id": f"halt-{index}", "policy_hash": "a" * 64},
                recorded_at=f"2026-08-30T0{index}:00:00+00:00",
            )
            store.authorize_resume(
                authorization_id=f"resume-{index}",
                event_id=failed.event_id,
                previous_terminal_failure_hash=failure.payload_hash,
                policy_evidence_id=f"retry-{index}",
                policy_evidence_hash="b" * 64,
                authorized_at=f"2026-08-30T1{index}:00:00+00:00",
            )
        checkpoint = build_checkpoint(store)
        assert len(checkpoint.terminal_failure_prefix) == 2
        assert len(checkpoint.resume_authorization_prefix) == 2
        assert Checkpoint.from_payload(checkpoint.to_payload()) == checkpoint
        assert validate_checkpoint(checkpoint, store) == "current"


def test_checkpoint_cannot_hide_authorized_failure_by_truncating_causal_evidence(
    tmp_path: Path,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "truncated-causal.sqlite3")
    with store:
        failed = attempt(run_manifest)
        append_terminal_attempt(store, failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="halt",
            policy_evidence={"policy_id": "halt-policy", "policy_hash": "a" * 64},
            recorded_at="2026-08-30T01:00:00+00:00",
        )
        store.authorize_resume(
            authorization_id="resume-hidden-chain",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-30T02:00:00+00:00",
        )
        retry = attempt(run_manifest, index=2)
        store.append_attempt(attempt_transition(retry, EventStatus.PENDING))
        payload = build_checkpoint(store).to_payload()
        body = payload["checkpoint"]
        assert isinstance(body, dict)
        body["terminal_failure"] = None
        body["terminal_failure_hash"] = None
        body["resume_authorization"] = None
        body["resume_authorization_hash"] = None
        body["terminal_failure_prefix"] = []
        body["terminal_failure_prefix_hash"] = canonical_payload_hash([])
        body["resume_authorization_prefix"] = []
        body["resume_authorization_prefix_hash"] = canonical_payload_hash([])
        body["causal_evidence_prefix"] = []
        body["causal_evidence_root"] = canonical_payload_hash([])
        payload["checkpoint_hash"] = canonical_payload_hash(body)
        with pytest.raises(ValueError, match="causal|authorization|failure|attempt"):
            Checkpoint.from_payload(payload)


@pytest.mark.parametrize(
    "tamper", ["duplicate", "reverse", "skip-sequence", "wrong-event", "fork", "cross-ordinal"]
)
def test_checkpoint_from_payload_rejects_causal_chain_tamper(tmp_path: Path, tamper: str) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / f"checkpoint-{tamper}.sqlite3")
    with store:
        for index in (1, 2):
            failed = attempt(run_manifest, index=index)
            append_terminal_attempt(store, failed)
            failure = store.record_terminal_failure(
                event_id=failed.event_id,
                reason=f"halt-{index}",
                policy_evidence={"policy_id": f"halt-{index}", "policy_hash": "a" * 64},
                recorded_at=f"2026-08-30T0{index}:00:00+00:00",
            )
            store.authorize_resume(
                authorization_id=f"resume-{index}",
                event_id=failed.event_id,
                previous_terminal_failure_hash=failure.payload_hash,
                policy_evidence_id=f"retry-{index}",
                policy_evidence_hash="b" * 64,
                authorized_at=f"2026-08-30T1{index}:00:00+00:00",
            )
        payload = build_checkpoint(store).to_payload()
    body = payload["checkpoint"]
    assert isinstance(body, dict)
    causal = body["causal_evidence_prefix"]
    assert isinstance(causal, list)
    if tamper == "duplicate":
        causal.insert(1, dict(causal[0]))
    elif tamper == "reverse":
        causal[0], causal[1] = causal[1], causal[0]
    elif tamper == "skip-sequence":
        causal[2]["evidence_sequence"] = 9
    elif tamper == "wrong-event":
        causal[2]["event_id"] = "event-forged"
    elif tamper == "fork":
        causal[3]["previous_evidence_hash"] = "f" * 64
    else:
        causal[2]["event_ordinal"] = 1
    body["causal_evidence_root"] = canonical_payload_hash(causal)
    payload["checkpoint_hash"] = canonical_payload_hash(body)
    with pytest.raises(ValueError, match="causal|evidence|authorization|attempt"):
        Checkpoint.from_payload(payload)


def test_checkpoint_from_payload_replays_execution_instead_of_trusting_rehashed_claim(
    tmp_path: Path,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "forged-execution.sqlite3")
    with store:
        payload = build_checkpoint(store).to_payload()
    body = payload["checkpoint"]
    assert isinstance(body, dict)
    execution = body["execution_state"]
    assert isinstance(execution, dict)
    execution["status"] = "failed"
    body["execution_state_hash"] = canonical_payload_hash(execution)
    payload["checkpoint_hash"] = canonical_payload_hash(body)
    with pytest.raises(ValueError, match="execution state does not replay"):
        Checkpoint.from_payload(payload)


def test_authorized_failure_history_remains_recoverable_through_retry_and_commit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "authorized-lifecycle.sqlite3"
    store, run_manifest, artifacts = _create_sealed_store(database)
    checkpoints: list[Checkpoint] = []
    with store:
        failed = attempt(run_manifest, index=1)
        append_terminal_attempt(store, failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="halt",
            policy_evidence={"policy_id": "halt-policy", "policy_hash": "a" * 64},
            recorded_at="2026-08-30T01:00:00+00:00",
        )
        store.authorize_resume(
            authorization_id="resume-lifecycle",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-30T02:00:00+00:00",
        )
        checkpoints.append(build_checkpoint(store))
        retry_failed = attempt(run_manifest, index=2)
        store.append_attempt(attempt_transition(retry_failed, EventStatus.PENDING))
        checkpoints.append(build_checkpoint(store))
        store.append_attempt(attempt_transition(retry_failed, EventStatus.IN_PROGRESS))
        checkpoints.append(build_checkpoint(store))
        store.append_attempt(retry_failed)
        checkpoints.append(build_checkpoint(store))
        retry_failure = store.record_terminal_failure(
            event_id=retry_failed.event_id,
            reason="halt retry",
            policy_evidence={"policy_id": "halt-policy-2", "policy_hash": "a" * 64},
            recorded_at="2026-08-30T03:00:00+00:00",
        )
        checkpoints.append(build_checkpoint(store))
        store.authorize_resume(
            authorization_id="resume-lifecycle-2",
            event_id=retry_failed.event_id,
            previous_terminal_failure_hash=retry_failure.payload_hash,
            policy_evidence_id="retry-policy-2",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-30T04:00:00+00:00",
        )
        checkpoints.append(build_checkpoint(store))
        succeeded = attempt(run_manifest, index=3, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, succeeded)
        landed = build_checkpoint(store)
        checkpoints.append(landed)
        records = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=store.private_state("agent-0"),  # type: ignore[arg-type]
            previous_cursor=store.feed_cursor("agent-0"),  # type: ignore[arg-type]
            previous_pointer=store.latest_public_pointer("agent-0"),
            attempt_index=3,
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=3),
            final_attempt=succeeded,
            private_update=records[0],
            private_state=records[1],
            feed_cursor=records[2],
            public_post=records[3],
            latest_public_pointer=records[4],
        )
        committed = build_checkpoint(store)
        assert committed.resume_action == "start_current_event"
        assert committed.terminal_failure is None
        assert committed.resume_authorization is None
        assert len(committed.causal_evidence_prefix) == 4
        assert all(validate_checkpoint(item, store) == "stale" for item in checkpoints)

    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as reopened:
        reopened.verify_integrity()
        assert validate_checkpoint(committed, reopened) == "current"


@pytest.mark.parametrize(
    ("status", "expected_statuses"),
    [
        (EventStatus.PENDING, ("pending",)),
        (EventStatus.IN_PROGRESS, ("pending", "in_progress")),
        (EventStatus.FAILED, ("pending", "in_progress", "failed")),
        (EventStatus.SUCCEEDED, ("pending", "in_progress", "succeeded")),
    ],
)
def test_checkpoint_exactly_captures_current_attempt_transition_prefix(
    tmp_path: Path,
    status: EventStatus,
    expected_statuses: tuple[str, ...],
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / f"{status.value}.sqlite3")
    with store:
        terminal_status = (
            status if status in {EventStatus.FAILED, EventStatus.SUCCEEDED} else EventStatus.FAILED
        )
        terminal = attempt(run_manifest, status=terminal_status)
        store.append_attempt(attempt_transition(terminal, EventStatus.PENDING))
        if status is not EventStatus.PENDING:
            store.append_attempt(attempt_transition(terminal, EventStatus.IN_PROGRESS))
        if status in {EventStatus.FAILED, EventStatus.SUCCEEDED}:
            store.append_attempt(terminal)

        checkpoint = build_checkpoint(store)

        assert len(checkpoint.current_attempt_prefix) == 1
        assert (
            tuple(
                transition["status"]
                for transition in checkpoint.current_attempt_prefix[0]["transitions"]
            )
            == expected_statuses
        )
        assert validate_checkpoint(checkpoint, store) == "current"
        assert (
            checkpoint.resume_action
            == {
                EventStatus.PENDING: "resume_same_attempt",
                EventStatus.IN_PROGRESS: "resume_same_attempt",
                EventStatus.FAILED: "retry_same_event",
                EventStatus.SUCCEEDED: "commit_landed_success",
            }[status]
        )


def test_committed_event_advances_checkpoint_and_prior_checkpoint_is_stale(
    tmp_path: Path,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        stale = build_checkpoint(store)
        final_attempt = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, final_attempt)
        event = successful_event(run_manifest, ordinal=0)
        previous_state = store.private_state("agent-0")
        previous_cursor = store.feed_cursor("agent-0")
        assert previous_state is not None and previous_cursor is not None
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=previous_state,
            previous_cursor=previous_cursor,
            previous_pointer=store.latest_public_pointer("agent-0"),
        )
        store.commit_success(
            event,
            final_attempt=final_attempt,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )

        current = build_checkpoint(store)

        assert current.next_event_ordinal == 1
        assert current.current_event_id == derive_event_id(run_manifest.run_id, 1)
        assert current.current_attempt_prefix == ()
        assert validate_checkpoint(current, store) == "current"
        assert validate_checkpoint(stale, store) == "stale"


def test_checkpoint_atomic_canonical_round_trip(tmp_path: Path) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        checkpoint = build_checkpoint(store)
        written_hash = write_checkpoint_atomic(target, checkpoint)

        assert written_hash == checkpoint.checkpoint_hash
        assert load_checkpoint(target) == checkpoint
        raw = target.read_text(encoding="utf-8")
        assert raw == json.dumps(
            checkpoint.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


def test_atomic_write_uses_once_normalized_checkpoint_payload(tmp_path: Path) -> None:
    class ChangingMapping(Mapping[str, str]):
        def __init__(self) -> None:
            self.reads = 0

        def __getitem__(self, key: str) -> str:
            if key != "population":
                raise KeyError(key)
            self.reads += 1
            return ("b" if self.reads == 1 else "f") * 64

        def __iter__(self) -> Iterator[str]:
            return iter(("population",))

        def __len__(self) -> int:
            return 1

    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        trusted = build_checkpoint(store)
        changing = replace(trusted, artifact_hashes=ChangingMapping())
        written_hash = write_checkpoint_atomic(target, changing)
        loaded = load_checkpoint(target)

    assert dict(loaded.artifact_hashes) == {"population": "b" * 64}
    assert written_hash == loaded.checkpoint_hash


@pytest.mark.parametrize("failure_point", ["before", "flush", "replace"])
def test_atomic_write_failure_preserves_old_checkpoint_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        old = build_checkpoint(store)
        write_checkpoint_atomic(target, old)
        pending = attempt_transition(attempt(run_manifest), EventStatus.PENDING)
        store.append_attempt(pending)
        new = build_checkpoint(store)

        def fail(*_args: object, **_kwargs: object) -> object:
            raise OSError(f"injected {failure_point} failure")

        if failure_point == "before":
            monkeypatch.setattr(checkpoint_module.tempfile, "mkstemp", fail)
        elif failure_point == "flush":
            monkeypatch.setattr(checkpoint_module.os, "fsync", fail)
        else:
            monkeypatch.setattr(checkpoint_module.os, "replace", fail)

        with pytest.raises(OSError, match="injected"):
            write_checkpoint_atomic(target, new)

        assert load_checkpoint(target) == old
        assert validate_checkpoint(load_checkpoint(target), store) == "stale"
        assert list(tmp_path.glob(".checkpoint.json.*.tmp")) == []


def test_atomic_write_invokes_parent_directory_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    calls: list[Path] = []

    def record_sync(path: Path) -> bool:
        calls.append(path)
        return True

    monkeypatch.setattr(
        checkpoint_module,
        "_fsync_parent_directory",
        record_sync,
        raising=False,
    )
    with store:
        write_checkpoint_atomic(target, build_checkpoint(store))

    assert calls == [target]


def test_parent_directory_sync_failure_keeps_replaced_valid_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        old = build_checkpoint(store)
        write_checkpoint_atomic(target, old)
        store.append_attempt(attempt_transition(attempt(run_manifest), EventStatus.PENDING))
        new = build_checkpoint(store)

        def fail_sync(_path: Path) -> bool:
            raise OSError("injected directory fsync failure")

        monkeypatch.setattr(
            checkpoint_module,
            "_fsync_parent_directory",
            fail_sync,
            raising=False,
        )
        with pytest.raises(OSError, match="directory fsync"):
            write_checkpoint_atomic(target, new)

        assert load_checkpoint(target) == new
        assert validate_checkpoint(load_checkpoint(target), store) == "current"
        assert list(tmp_path.glob(".checkpoint.json.*.tmp")) == []


@pytest.mark.parametrize(
    "progression",
    ["empty_to_pending", "pending_to_in_progress", "failed_to_retry", "in_progress_to_success"],
)
def test_same_ordinal_strict_attempt_prefix_is_trustworthy_stale(
    tmp_path: Path,
    progression: str,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        first = attempt(run_manifest, status=EventStatus.FAILED)
        if progression == "empty_to_pending":
            stale = build_checkpoint(store)
            store.append_attempt(attempt_transition(first, EventStatus.PENDING))
        elif progression == "pending_to_in_progress":
            store.append_attempt(attempt_transition(first, EventStatus.PENDING))
            stale = build_checkpoint(store)
            store.append_attempt(attempt_transition(first, EventStatus.IN_PROGRESS))
        elif progression == "failed_to_retry":
            append_terminal_attempt(store, first)
            stale = build_checkpoint(store)
            failure = store.record_terminal_failure(
                event_id=first.event_id,
                reason="retry progression",
                policy_evidence={"policy_id": "halt", "policy_hash": "a" * 64},
                recorded_at="2026-08-18T00:00:00+00:00",
            )
            store.authorize_resume(
                authorization_id="resume-progression",
                event_id=first.event_id,
                previous_terminal_failure_hash=failure.payload_hash,
                policy_evidence_id="retry-policy",
                policy_evidence_hash="b" * 64,
                authorized_at="2026-08-18T01:00:00+00:00",
            )
            second = attempt(run_manifest, index=2, status=EventStatus.FAILED)
            store.append_attempt(attempt_transition(second, EventStatus.PENDING))
        else:
            succeeded = attempt(run_manifest, status=EventStatus.SUCCEEDED)
            store.append_attempt(attempt_transition(succeeded, EventStatus.PENDING))
            store.append_attempt(attempt_transition(succeeded, EventStatus.IN_PROGRESS))
            stale = build_checkpoint(store)
            store.append_attempt(succeeded)

        current = build_checkpoint(store)

        assert stale.next_event_ordinal == current.next_event_ordinal == 0
        assert validate_checkpoint(stale, store) == "stale"
        assert validate_checkpoint(current, store) == "current"


def test_same_ordinal_attempt_prefix_ahead_or_fork_conflicts(tmp_path: Path) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        terminal = attempt(run_manifest, status=EventStatus.FAILED)
        store.append_attempt(attempt_transition(terminal, EventStatus.PENDING))
        current = build_checkpoint(store)
        ahead_payload = current.to_payload()
        in_progress = attempt_transition(terminal, EventStatus.IN_PROGRESS).to_payload()
        entry = ahead_payload["checkpoint"]["current_attempt_prefix"][0]
        entry["transitions"].append(in_progress)
        envelope = dict(entry["transition_entries"][0]["row_envelope"])
        envelope.update(
            {
                "transition_index": 2,
                "status": "in_progress",
                "payload_hash": canonical_payload_hash(in_progress),
                "checkpoint_payload_hash": canonical_payload_hash(in_progress),
            }
        )
        entry["transition_entries"].append(
            {"transition": dict(in_progress), "row_envelope": envelope}
        )
        execution = ahead_payload["checkpoint"]["execution_state"]
        execution["status_counts"]["pending"] = 0
        execution["status_counts"]["in_progress"] = 1
        ahead_payload["checkpoint"]["execution_state_hash"] = canonical_payload_hash(execution)
        ahead_payload["checkpoint_hash"] = canonical_payload_hash(ahead_payload["checkpoint"])
        ahead = Checkpoint.from_payload(ahead_payload)
        fork = replace(current, current_manifest_hash="f" * 64)

        with pytest.raises(ValueError, match="conflict"):
            validate_checkpoint(ahead, store)
        with pytest.raises(ValueError, match="conflict"):
            validate_checkpoint(fork, store)


def test_load_checkpoint_rejects_duplicate_noncanonical_and_hash_tamper(tmp_path: Path) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        checkpoint = build_checkpoint(store)
        write_checkpoint_atomic(target, checkpoint)
    raw = target.read_text(encoding="utf-8")

    target.write_text(
        raw.replace('{"checkpoint":', '{"checkpoint_hash":"x","checkpoint":', 1), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_checkpoint(target)

    target.write_text(raw + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical"):
        load_checkpoint(target)

    payload = json.loads(raw)
    payload["checkpoint"]["event_chain_head"] = "f" * 64
    target.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash"):
        load_checkpoint(target)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "paper1.checkpoint.v999"),
        ("storage_schema_version", "paper1.run-storage.v999"),
        ("run_id", "run-forged"),
        ("run_spec_hash", "f" * 64),
        ("protocol_id", "paper-forged"),
        ("protocol_version", "formal"),
        ("protocol_hash", "f" * 64),
        ("schedule_hash", "f" * 64),
        ("expected_agent_ids_hash", "f" * 64),
        ("round0_root", "f" * 64),
        ("baseline_manifest_hash", "f" * 64),
        ("current_manifest_hash", "f" * 64),
        ("private_state_root", "f" * 64),
        ("public_stock_root", "f" * 64),
        ("latest_public_pointer_root", "f" * 64),
        ("feed_cursor_root", "f" * 64),
        ("state_collection_root", "f" * 64),
        ("event_chain_head", "f" * 64),
        ("current_event_id", "event-forged"),
    ],
)
def test_validate_checkpoint_fails_closed_on_identity_hash_state_and_pointer_tamper(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        checkpoint = build_checkpoint(store)
        with pytest.raises(ValueError):
            validate_checkpoint(replace(checkpoint, **{field: value}), store)


def test_validate_checkpoint_rejects_ahead_ordinal(tmp_path: Path) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        checkpoint = build_checkpoint(store)
        with pytest.raises(ValueError, match="ahead|identity"):
            validate_checkpoint(
                replace(
                    checkpoint,
                    next_event_ordinal=1,
                    current_event_id=derive_event_id(checkpoint.run_id, 1),
                ),
                store,
            )


def test_stale_checkpoint_with_failed_attempt_prefix_validates_against_later_success(
    tmp_path: Path,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        failed = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed)
        stale = build_checkpoint(store)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="later success retry",
            policy_evidence={"policy_id": "halt", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T00:00:00+00:00",
        )
        store.authorize_resume(
            authorization_id="resume-later-success",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-18T01:00:00+00:00",
        )
        succeeded = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, succeeded)
        event = successful_event(run_manifest, ordinal=0, attempt_count=2)
        previous_state = store.private_state("agent-0")
        previous_cursor = store.feed_cursor("agent-0")
        assert previous_state is not None and previous_cursor is not None
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=previous_state,
            previous_cursor=previous_cursor,
            previous_pointer=store.latest_public_pointer("agent-0"),
            attempt_index=2,
        )
        store.commit_success(
            event,
            final_attempt=succeeded,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )

        assert validate_checkpoint(stale, store) == "stale"


def test_failed_transition_checkpoint_becomes_stale_after_halt_evidence(
    tmp_path: Path,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        failed = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed)
        pre_halt = build_checkpoint(store)
        assert pre_halt.execution_state["status"] == "running"
        assert pre_halt.terminal_failure_prefix == ()

        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="external halt",
            policy_evidence={"policy_id": "halt-policy", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T00:00:00+00:00",
        )
        halted = build_checkpoint(store)
        assert halted.execution_state["status"] == "failed"
        assert halted.terminal_failure_hash == failure.payload_hash
        assert validate_checkpoint(pre_halt, store) == "stale"


def test_checkpoint_replays_every_failed_attempt_causal_stage_as_a_stale_prefix(
    tmp_path: Path,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        snapshots: list[tuple[str, Checkpoint]] = []
        failed1 = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed1)
        snapshots.append(("attempt-1-pre-halt", build_checkpoint(store)))
        failure1 = store.record_terminal_failure(
            event_id=failed1.event_id,
            reason="halt one",
            policy_evidence={"policy_id": "halt-1", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T00:00:00+00:00",
        )
        snapshots.append(("attempt-1-halted", build_checkpoint(store)))
        store.authorize_resume(
            authorization_id="resume-1",
            event_id=failed1.event_id,
            previous_terminal_failure_hash=failure1.payload_hash,
            policy_evidence_id="retry-1",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-18T01:00:00+00:00",
        )
        snapshots.append(("attempt-1-authorized", build_checkpoint(store)))

        attempt2 = attempt(run_manifest, index=2, status=EventStatus.FAILED)
        store.append_attempt(attempt_transition(attempt2, EventStatus.PENDING))
        retry_pending = build_checkpoint(store)
        snapshots.append(("attempt-2-pending", retry_pending))
        store.append_attempt(attempt_transition(attempt2, EventStatus.IN_PROGRESS))
        snapshots.append(("attempt-2-in-progress", build_checkpoint(store)))
        store.append_attempt(attempt2)
        snapshots.append(("attempt-2-pre-halt", build_checkpoint(store)))
        failure2 = store.record_terminal_failure(
            event_id=attempt2.event_id,
            reason="halt two",
            policy_evidence={"policy_id": "halt-2", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T02:00:00+00:00",
        )
        snapshots.append(("attempt-2-halted", build_checkpoint(store)))
        store.authorize_resume(
            authorization_id="resume-2",
            event_id=attempt2.event_id,
            previous_terminal_failure_hash=failure2.payload_hash,
            policy_evidence_id="retry-2",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-18T03:00:00+00:00",
        )
        snapshots.append(("attempt-2-authorized", build_checkpoint(store)))

        succeeded3 = attempt(run_manifest, index=3, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, succeeded3)
        snapshots.append(("attempt-3-succeeded-uncommitted", build_checkpoint(store)))
        previous_state = store.private_state("agent-0")
        previous_cursor = store.feed_cursor("agent-0")
        assert previous_state is not None and previous_cursor is not None
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=previous_state,
            previous_cursor=previous_cursor,
            previous_pointer=store.latest_public_pointer("agent-0"),
            attempt_index=3,
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=3),
            final_attempt=succeeded3,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )

        for label, checkpoint in snapshots:
            assert validate_checkpoint(checkpoint, store) == "stale", label

        forged = replace(
            retry_pending,
            terminal_failure=None,
            terminal_failure_hash=None,
            resume_authorization=None,
            resume_authorization_hash=None,
            terminal_failure_prefix=(),
            terminal_failure_prefix_hash=canonical_payload_hash([]),
            resume_authorization_prefix=(),
            resume_authorization_prefix_hash=canonical_payload_hash([]),
            causal_evidence_prefix=(),
            causal_evidence_root=canonical_payload_hash([]),
        )
        with pytest.raises(ValueError, match="causal|failed|conflict"):
            validate_checkpoint(forged, store)


@pytest.mark.parametrize("tamper", ["drop_failed_attempt", "drop_causal_pair"])
def test_checkpoint_from_payload_exact_covers_retry_attempts_and_causal_pairs(
    tmp_path: Path, tamper: str
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / f"{tamper}.sqlite3")
    with store:
        failed = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="exact-cover gate",
            policy_evidence={"policy_id": "halt", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T00:00:00+00:00",
        )
        store.authorize_resume(
            authorization_id="resume-exact-cover",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-18T01:00:00+00:00",
        )
        retry = attempt(run_manifest, index=2, status=EventStatus.FAILED)
        store.append_attempt(attempt_transition(retry, EventStatus.PENDING))
        payload = build_checkpoint(store).to_payload()

    body = payload["checkpoint"]
    assert isinstance(body, dict)
    if tamper == "drop_failed_attempt":
        body["current_attempt_prefix"] = body["current_attempt_prefix"][1:]
    else:
        body["terminal_failure_prefix"] = []
        body["terminal_failure_prefix_hash"] = canonical_payload_hash([])
        body["resume_authorization_prefix"] = []
        body["resume_authorization_prefix_hash"] = canonical_payload_hash([])
        body["causal_evidence_prefix"] = []
        body["causal_evidence_root"] = canonical_payload_hash([])
        body["resume_authorization"] = None
        body["resume_authorization_hash"] = None
    payload["checkpoint_hash"] = canonical_payload_hash(body)
    with pytest.raises(ValueError, match="attempt|causal|failure|authorization|continuous"):
        Checkpoint.from_payload(payload)


def test_committed_checkpoint_cannot_delete_preexisting_causal_history(
    tmp_path: Path,
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False,)))
    store = RunStorage.create(
        tmp_path / "committed-causal.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    with store:
        seal_expected_initial_state(store, run_manifest)
        failed = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed)
        failure = store.record_terminal_failure(
            event_id=failed.event_id,
            reason="committed causal gate",
            policy_evidence={"policy_id": "halt", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T00:00:00+00:00",
        )
        store.authorize_resume(
            authorization_id="resume-committed-causal",
            event_id=failed.event_id,
            previous_terminal_failure_hash=failure.payload_hash,
            policy_evidence_id="retry-policy",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-18T01:00:00+00:00",
        )
        succeeded = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, succeeded)
        previous_state = store.private_state("agent-0")
        previous_cursor = store.feed_cursor("agent-0")
        assert previous_state is not None and previous_cursor is not None
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=previous_state,
            previous_cursor=previous_cursor,
            previous_pointer=store.latest_public_pointer("agent-0"),
            attempt_index=2,
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=2),
            final_attempt=succeeded,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )
        payload = build_checkpoint(store).to_payload()
        body = payload["checkpoint"]
        assert isinstance(body, dict)
        body["terminal_failure_prefix"] = []
        body["terminal_failure_prefix_hash"] = canonical_payload_hash([])
        body["resume_authorization_prefix"] = []
        body["resume_authorization_prefix_hash"] = canonical_payload_hash([])
        body["causal_evidence_prefix"] = []
        body["causal_evidence_root"] = canonical_payload_hash([])
        payload["checkpoint_hash"] = canonical_payload_hash(body)
        forged = Checkpoint.from_payload(payload)
        with pytest.raises(ValueError, match="causal|authorization|conflict|failure"):
            validate_checkpoint(forged, store)


def test_cross_ordinal_pre_halt_checkpoint_does_not_reuse_prior_event_evidence(
    tmp_path: Path,
) -> None:
    run_manifest = manifest(schedule(publish_flags=(False, False)))
    store = RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    )
    with store:
        seal_expected_initial_state(store, run_manifest)
        failed0 = attempt(run_manifest, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed0)
        failure0 = store.record_terminal_failure(
            event_id=failed0.event_id,
            reason="halt zero",
            policy_evidence={"policy_id": "halt-0", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T00:00:00+00:00",
        )
        store.authorize_resume(
            authorization_id="resume-0",
            event_id=failed0.event_id,
            previous_terminal_failure_hash=failure0.payload_hash,
            policy_evidence_id="retry-0",
            policy_evidence_hash="b" * 64,
            authorized_at="2026-08-18T01:00:00+00:00",
        )
        succeeded0 = attempt(run_manifest, index=2, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, succeeded0)
        state0 = store.private_state("agent-0")
        cursor0 = store.feed_cursor("agent-0")
        assert state0 is not None and cursor0 is not None
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=state0,
            previous_cursor=cursor0,
            previous_pointer=store.latest_public_pointer("agent-0"),
            attempt_index=2,
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0, attempt_count=2),
            final_attempt=succeeded0,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )
        failed1 = attempt(run_manifest, ordinal=1, index=1, status=EventStatus.FAILED)
        append_terminal_attempt(store, failed1)
        pre_halt1 = build_checkpoint(store)
        assert pre_halt1.execution_state["status"] == "running"
        assert pre_halt1.terminal_failure is None
        store.record_terminal_failure(
            event_id=failed1.event_id,
            reason="halt one",
            policy_evidence={"policy_id": "halt-1", "policy_hash": "a" * 64},
            recorded_at="2026-08-18T02:00:00+00:00",
        )
        assert validate_checkpoint(pre_halt1, store) == "stale"


def test_build_runs_exactly_one_full_storage_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    original = RunStorage.verify_integrity
    calls = 0

    def counted(self: RunStorage) -> None:
        nonlocal calls
        calls += 1
        original(self)

    monkeypatch.setattr(RunStorage, "verify_integrity", counted)
    with store:
        build_checkpoint(store)
    assert calls == 1


def test_checkpoint_roots_equal_direct_verified_storage_projection(tmp_path: Path) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        checkpoint = build_checkpoint(store)
        evidence = store.recovery_evidence()

        assert checkpoint.private_state_root == canonical_payload_hash(
            list(evidence["private_states"])
        )
        assert checkpoint.public_stock_root == canonical_payload_hash(
            list(evidence["public_stock"])
        )
        assert checkpoint.feed_cursor_root == canonical_payload_hash(list(evidence["feed_cursors"]))


@pytest.mark.parametrize(
    ("collection", "nested_path"),
    [
        ("private_states", (0,)),
        ("public_stock", (0,)),
        ("latest_public_pointers", (0,)),
        ("feed_cursors", (0,)),
        ("current_attempt_prefix", (0, "transitions", 0, "request_parameters")),
    ],
)
def test_recovery_evidence_is_recursively_immutable(
    tmp_path: Path,
    collection: str,
    nested_path: tuple[object, ...],
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        store.append_attempt(attempt_transition(attempt(run_manifest), EventStatus.PENDING))
        evidence = store.recovery_evidence()
    target: object = evidence[collection]
    for key in nested_path:
        target = target[key]

    with pytest.raises(TypeError):
        target["forged"] = True


def test_close_reopen_checkpoint_validates_against_same_storage_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "run.sqlite3"
    store, run_manifest, artifacts = _create_sealed_store(database)
    checkpoint = build_checkpoint(store)
    store.close()

    with RunStorage.open(
        database,
        manifest=run_manifest,
        artifact_hashes=artifacts,
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as reopened:
        assert validate_checkpoint(checkpoint, reopened) == "current"


def test_recomputed_checkpoint_attempt_tamper_conflicts_with_storage(tmp_path: Path) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        store.append_attempt(attempt_transition(attempt(run_manifest), EventStatus.PENDING))
        checkpoint = build_checkpoint(store)
        payload = checkpoint.to_payload()
        payload["checkpoint"]["current_attempt_prefix"][0]["transitions"][0]["request_id"] = (
            "request-forged"
        )
        payload["checkpoint"]["current_attempt_prefix"][0]["transition_entries"][0]["transition"][
            "request_id"
        ] = "request-forged"
        forged_transition = payload["checkpoint"]["current_attempt_prefix"][0][
            "transition_entries"
        ][0]["transition"]
        forged_hash = canonical_payload_hash(forged_transition)
        row_envelope = payload["checkpoint"]["current_attempt_prefix"][0]["transition_entries"][0][
            "row_envelope"
        ]
        row_envelope["payload_hash"] = forged_hash
        row_envelope["checkpoint_payload_hash"] = forged_hash
        payload["checkpoint_hash"] = canonical_payload_hash(payload["checkpoint"])
        forged = checkpoint_module.Checkpoint.from_payload(payload)

        with pytest.raises(ValueError, match="conflicts"):
            validate_checkpoint(forged, store)


def test_validate_checkpoint_uses_normalized_mapping_not_custom_equality(tmp_path: Path) -> None:
    class EqualToAnythingMapping(dict[str, str]):
        def __eq__(self, _other: object) -> bool:
            return True

    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        trusted = build_checkpoint(store)
        forged = replace(
            trusted,
            artifact_hashes=EqualToAnythingMapping({"population": "f" * 64}),
        )

        with pytest.raises(ValueError, match="conflict"):
            validate_checkpoint(forged, store)


def test_resume_action_rejects_checkpoint_not_structurally_replayed(tmp_path: Path) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        store.append_attempt(attempt_transition(attempt(run_manifest), EventStatus.PENDING))
        checkpoint = build_checkpoint(store)
        untrusted_prefix = checkpoint.to_payload()["checkpoint"]["current_attempt_prefix"]
        del untrusted_prefix[0]["transitions"][0]["request_id"]
        malformed = replace(checkpoint, current_attempt_prefix=tuple(untrusted_prefix))

        with pytest.raises((TypeError, ValueError)):
            _ = malformed.resume_action


def test_build_checkpoint_fails_if_storage_attempt_journal_has_gap(tmp_path: Path) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        store.append_attempt(attempt_transition(attempt(run_manifest), EventStatus.PENDING))
        store._connection.execute("UPDATE attempt_transitions SET attempt_index = 2")

        with pytest.raises(ValueError, match="gap|identity|index"):
            build_checkpoint(store)


def test_load_checkpoint_enforces_local_path_size_and_depth_boundaries(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="local filesystem"):
        load_checkpoint("file:///tmp/checkpoint.json")
    with pytest.raises(FileNotFoundError):
        load_checkpoint(tmp_path / "missing.json")

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (checkpoint_module._MAX_CHECKPOINT_BYTES + 1))
    with pytest.raises(ValueError, match="byte size"):
        load_checkpoint(oversized)

    deep = tmp_path / "deep.json"
    value: object = 0
    for _ in range(checkpoint_module._MAX_JSON_DEPTH + 2):
        value = [value]
    deep.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ValueError, match="nesting depth"):
        load_checkpoint(deep)


def test_load_checkpoint_uses_one_bounded_file_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        checkpoint = build_checkpoint(store)
        write_checkpoint_atomic(target, checkpoint)
    open_count = 0

    if os.name == "nt":
        real_open = checkpoint_module._open_checkpoint_windows

        def counted_windows_open(path: Path) -> int:
            nonlocal open_count
            open_count += 1
            return real_open(path)

        monkeypatch.setattr(checkpoint_module, "_open_checkpoint_windows", counted_windows_open)
    else:
        real_open = checkpoint_module.os.open

        def counted_posix_open(*args: object, **kwargs: object) -> int:
            nonlocal open_count
            open_count += 1
            return real_open(*args, **kwargs)

        monkeypatch.setattr(checkpoint_module.os, "open", counted_posix_open)

    def forbidden_read_bytes(_self: Path) -> bytes:
        raise AssertionError("load must not reopen checkpoint through Path.read_bytes")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)

    assert load_checkpoint(target) == checkpoint
    assert open_count == 1


def test_load_checkpoint_reads_selected_handle_not_a_replaced_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    selected = tmp_path / "selected.json"
    path_now = tmp_path / "checkpoint.json"
    with store:
        checkpoint = build_checkpoint(store)
        write_checkpoint_atomic(selected, checkpoint)
    path_now.write_text("{}", encoding="utf-8")
    if os.name == "nt":
        real_open = checkpoint_module._open_checkpoint_windows

        def select_original_windows_handle(_path: object) -> int:
            return real_open(selected)

        monkeypatch.setattr(
            checkpoint_module,
            "_open_checkpoint_windows",
            select_original_windows_handle,
        )
    else:
        real_open = checkpoint_module.os.open

        def select_original_posix_handle(_path: object, flags: int) -> int:
            return real_open(selected, flags)

        monkeypatch.setattr(checkpoint_module.os, "open", select_original_posix_handle)

    assert load_checkpoint(path_now) == checkpoint


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse-point handle boundary")
def test_windows_load_rejects_symlink_at_opened_handle_even_if_path_precheck_misses_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    target = real_directory / "checkpoint.json"
    link = tmp_path / "checkpoint-link.json"
    with store:
        checkpoint = build_checkpoint(store)
        write_checkpoint_atomic(target, checkpoint)
    assert load_checkpoint(target) == checkpoint
    try:
        link.symlink_to(target)
    except OSError:
        link = tmp_path / "checkpoint-junction"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(real_directory)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert created.returncode == 0, created.stderr
        monkeypatch.setattr(Path, "is_file", lambda _self: True)
    else:
        assert link.is_symlink()
    monkeypatch.setattr(Path, "is_symlink", lambda _self: False)

    with pytest.raises(ValueError, match="reparse"):
        load_checkpoint(link)


def test_load_checkpoint_reads_at_most_max_plus_one_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        checkpoint = build_checkpoint(store)
        write_checkpoint_atomic(target, checkpoint)
    real_fdopen = checkpoint_module.os.fdopen
    read_sizes: list[int] = []

    class ReadSpy:
        def __init__(self, stream: object) -> None:
            self.stream = stream

        def __enter__(self) -> ReadSpy:
            return self

        def __exit__(self, *_args: object) -> None:
            self.stream.close()

        def read(self, size: int) -> bytes:
            read_sizes.append(size)
            return self.stream.read(size)

    def spy_fdopen(descriptor: int, mode: str) -> ReadSpy:
        return ReadSpy(real_fdopen(descriptor, mode))

    monkeypatch.setattr(checkpoint_module.os, "fdopen", spy_fdopen)

    assert load_checkpoint(target) == checkpoint
    assert read_sizes == [checkpoint_module._MAX_CHECKPOINT_BYTES + 1]


def test_load_checkpoint_normalizes_extreme_json_depth_to_value_error(tmp_path: Path) -> None:
    target = tmp_path / "deep.json"
    target.write_text("[" * 100_000 + "0" + "]" * 100_000, encoding="utf-8")

    with pytest.raises(ValueError, match="nesting depth"):
        load_checkpoint(target)


def test_external_response_checkpoint_binds_uri_and_hash_without_inlining_body(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    terminal = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    assert terminal.raw_response is not None and terminal.raw_response_hash is not None
    reference = ExternalResponseReference(
        uri="file:///archive/attempt-1.json",
        sha256=terminal.raw_response_hash,
    )

    def resolver(requested: ExternalResponseReference) -> str:
        return terminal.raw_response if requested == reference else "wrong"

    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        raw_response_resolver=resolver,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, terminal, external_response=reference)

        checkpoint = build_checkpoint(store)
        prefix = checkpoint.current_attempt_prefix[0]
        raw = json.dumps(checkpoint.to_payload(), ensure_ascii=False)

        assert reference.uri in raw
        assert reference.sha256 in raw
        assert prefix["transitions"][-1]["raw_response"] is None
        assert prefix["transition_entries"][-1]["transition"]["raw_response"] is None
        assert validate_checkpoint(checkpoint, store) == "current"


def test_external_redacted_transition_rejects_missing_domain_field(tmp_path: Path) -> None:
    run_manifest = manifest()
    terminal = attempt(run_manifest, status=EventStatus.SUCCEEDED)
    assert terminal.raw_response is not None and terminal.raw_response_hash is not None
    reference = ExternalResponseReference(
        uri="file:///archive/attempt-1.json",
        sha256=terminal.raw_response_hash,
    )

    def resolver(_requested: ExternalResponseReference) -> str:
        return terminal.raw_response

    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        raw_response_resolver=resolver,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, terminal, external_response=reference)
        payload = build_checkpoint(store).to_payload()
    last = payload["checkpoint"]["current_attempt_prefix"][0]
    del last["transitions"][-1]["request_id"]
    del last["transition_entries"][-1]["transition"]["request_id"]
    payload["checkpoint_hash"] = canonical_payload_hash(payload["checkpoint"])

    with pytest.raises(ValueError, match="attempt|transition"):
        Checkpoint.from_payload(payload)


def test_external_failed_redacted_transition_replays_nonempty_usage_contract(
    tmp_path: Path,
) -> None:
    run_manifest = manifest()
    raw_response = '{"error":"provider_failure"}'
    usage = {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}
    terminal = replace(
        attempt(run_manifest, status=EventStatus.FAILED),
        raw_response=raw_response,
        raw_response_hash=canonical_payload_hash(raw_response),
        usage=usage,
        usage_hash=canonical_payload_hash(usage),
    )
    reference = ExternalResponseReference(
        uri="file:///archive/failed-attempt-1.json",
        sha256=terminal.raw_response_hash,
    )

    def resolver(_requested: ExternalResponseReference) -> str:
        return raw_response

    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=expected_agent_ids(run_manifest),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
        raw_response_resolver=resolver,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        append_terminal_attempt(store, terminal, external_response=reference)
        payload = build_checkpoint(store).to_payload()

    attempt_entry = payload["checkpoint"]["current_attempt_prefix"][0]
    redacted = attempt_entry["transitions"][-1]
    redacted["usage"].pop("total_tokens")
    redacted["usage_hash"] = canonical_payload_hash(redacted["usage"])
    attempt_entry["transition_entries"][-1]["transition"] = dict(redacted)
    attempt_entry["transition_entries"][-1]["row_envelope"]["checkpoint_payload_hash"] = (
        canonical_payload_hash(redacted)
    )
    payload["checkpoint_hash"] = canonical_payload_hash(payload["checkpoint"])

    with pytest.raises(ValueError, match="usage"):
        Checkpoint.from_payload(payload)


def test_checkpoint_api_is_exported_from_package_root() -> None:
    from agent_ex import Checkpoint as ExportedCheckpoint
    from agent_ex import build_checkpoint as exported_build
    from agent_ex import load_checkpoint as exported_load
    from agent_ex import validate_checkpoint as exported_validate
    from agent_ex import write_checkpoint_atomic as exported_write

    assert ExportedCheckpoint is Checkpoint
    assert exported_build is build_checkpoint
    assert exported_load is load_checkpoint
    assert exported_validate is validate_checkpoint
    assert exported_write is write_checkpoint_atomic


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_transitions",
        "missing_request_id",
        "attempt_gap",
        "illegal_lifecycle",
        "row_envelope_drift",
    ],
)
def test_load_rejects_structurally_invalid_attempt_prefix(
    tmp_path: Path,
    mutation: str,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    target = tmp_path / "checkpoint.json"
    with store:
        terminal = attempt(run_manifest, status=EventStatus.FAILED)
        append_terminal_attempt(store, terminal)
        payload = build_checkpoint(store).to_payload()
    prefix = payload["checkpoint"]["current_attempt_prefix"]
    if mutation == "missing_transitions":
        prefix[0]["transitions"] = []
    elif mutation == "missing_request_id":
        del prefix[0]["transitions"][0]["request_id"]
        del prefix[0]["transition_entries"][0]["transition"]["request_id"]
    elif mutation == "attempt_gap":
        prefix[0]["attempt_index"] = 2
    elif mutation == "illegal_lifecycle":
        prefix[0]["transitions"][1]["status"] = "succeeded"
    else:
        prefix[0]["transition_entries"][0]["row_envelope"]["event_id"] = "event-forged"
    payload["checkpoint_hash"] = canonical_payload_hash(payload["checkpoint"])
    target.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises((TypeError, ValueError), match="attempt|transition"):
        load_checkpoint(target)


def test_validate_stale_checkpoint_replays_untrusted_dataclass_structure(
    tmp_path: Path,
) -> None:
    store, run_manifest, _ = _create_sealed_store(tmp_path / "run.sqlite3")
    with store:
        stale = build_checkpoint(store)
        final_attempt = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, final_attempt)
        event = successful_event(run_manifest, ordinal=0)
        previous_state = store.private_state("agent-0")
        previous_cursor = store.feed_cursor("agent-0")
        assert previous_state is not None and previous_cursor is not None
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=previous_state,
            previous_cursor=previous_cursor,
            previous_pointer=store.latest_public_pointer("agent-0"),
        )
        store.commit_success(
            event,
            final_attempt=final_attempt,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )
        forged = replace(
            stale,
            current_attempt_prefix=(
                {
                    "attempt_id": derive_attempt_id(stale.current_event_id, 1),
                    "attempt_index": 1,
                },
            ),
        )

        with pytest.raises(ValueError, match="attempt|transition"):
            validate_checkpoint(forged, store)


def test_n50000_schedule_empty_state_checkpoint_boundary_is_linear_once(
    tmp_path: Path,
) -> None:
    frozen_schedule = FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id="mock.weighted-with-replacement",
        algorithm_version="1.0.0",
        population_size=1,
        sweep_count=50_000,
        slots=tuple(
            ScheduleSlot(
                event_ordinal=ordinal,
                sweep_index=ordinal + 1,
                draw_index=0,
                agent_id="agent-0",
                publish_flag=False,
            )
            for ordinal in range(50_000)
        ),
    )
    run_manifest = manifest(frozen_schedule)
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        started = perf_counter()
        checkpoint = build_checkpoint(store)
        elapsed = perf_counter() - started

    assert checkpoint.schedule_count == 50_000
    assert checkpoint.next_event_ordinal == 0
    assert checkpoint.current_attempt_prefix == ()
    assert checkpoint.causal_evidence_prefix == ()
    assert elapsed < 8.0


def test_complete_run_checkpoint_has_no_current_event_and_reopens(tmp_path: Path) -> None:
    run_manifest = manifest(
        FrozenSchedule(
            schema_version="paper1.schedule.v2",
            algorithm_id="mock.weighted-with-replacement",
            algorithm_version="1.0.0",
            population_size=1,
            sweep_count=1,
            slots=(
                ScheduleSlot(
                    event_ordinal=0,
                    sweep_index=1,
                    draw_index=0,
                    agent_id="agent-0",
                    publish_flag=False,
                ),
            ),
        )
    )
    with RunStorage.create(
        tmp_path / "run.sqlite3",
        manifest=run_manifest,
        artifact_hashes={"population": "b" * 64},
        expected_agent_ids=("agent-0",),
        expected_exposure_mode="self_history_only",
        expected_exposure_graph_hash=None,
    ) as store:
        seal_expected_initial_state(store, run_manifest)
        final_attempt = attempt(run_manifest, status=EventStatus.SUCCEEDED)
        append_terminal_attempt(store, final_attempt)
        previous_state = store.private_state("agent-0")
        previous_cursor = store.feed_cursor("agent-0")
        assert previous_state is not None and previous_cursor is not None
        update, state, cursor, post, pointer = successful_state_records(
            run_manifest,
            ordinal=0,
            previous_state=previous_state,
            previous_cursor=previous_cursor,
            previous_pointer=store.latest_public_pointer("agent-0"),
        )
        store.commit_success(
            successful_event(run_manifest, ordinal=0),
            final_attempt=final_attempt,
            private_update=update,
            private_state=state,
            feed_cursor=cursor,
            public_post=post,
            latest_public_pointer=pointer,
        )
        checkpoint = build_checkpoint(store)
        target = tmp_path / "checkpoint.json"
        write_checkpoint_atomic(target, checkpoint)
        loaded = load_checkpoint(target)

        assert checkpoint.current_event_id is None
        assert checkpoint.resume_action == "complete"
        assert validate_checkpoint(loaded, store) == "current"
