"""Local dispatch recovery tests. No network or model calls."""

import json
import os

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network import dispatch
from agent_ex.identity_network.contracts import study_cells
from test_identity_network_prefix import prefix_store
from test_identity_network_response import response_for


def started(tmp_path, cell=None):
    store, cls, binding, manifest, path, stored, kwargs = prefix_store(
        tmp_path, cell or study_cells()[0]
    )
    store.record_diagnostic_prepared_attempt(stored, **kwargs)
    store.start_diagnostic_attempt(kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z")
    invocation, _ = response_for(stored, kwargs)
    journal = dispatch.StudyDispatchJournal(tmp_path / "dispatch.jsonl", storage=store)
    return store, cls, binding, manifest, path, kwargs, invocation, journal


@pytest.mark.parametrize("cell", study_cells())
def test_saved_response_reconciles_and_commits_after_reopen_without_resend(tmp_path, cell):
    store, cls, binding, manifest, path, kwargs, invocation, journal = started(tmp_path, cell)
    journal.record_before_dispatch(
        kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
    )
    store.record_diagnostic_invocation_evidence(invocation)
    store.close()
    store = cls.open(path, manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            journal = dispatch.StudyDispatchJournal(journal.path, storage=store)
            assert dispatch.reconcile_study_event(storage=store, journal=journal) == "committed"
            assert store.progress.next_event_ordinal == 1
            assert journal.unresolved_request_ids() == ()
            assert dispatch.reconcile_study_event(storage=store, journal=journal) == "new_event"
        store.verify_integrity()
    finally:
        store.close()


def test_unresolved_intent_without_response_stops_and_never_changes_state(tmp_path):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        before = store.progress
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        with pytest.raises(RuntimeError, match="unresolved"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
        assert store.progress == before
        assert store.invocation_evidence(invocation.attempt_id) is None
    finally:
        store.close()


def test_in_progress_without_intent_stops_even_if_response_is_saved(tmp_path):
    store, _, _, _, _, _, invocation, journal = started(tmp_path)
    try:
        store.record_diagnostic_invocation_evidence(invocation)
        with pytest.raises(RuntimeError, match="intent"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
        assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


def test_intent_is_fsynced_before_callback_returns(tmp_path, monkeypatch):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    calls = []
    original = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), original(fd)))
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        assert calls
    finally:
        store.close()


def test_wrong_wire_is_rejected_before_intent(tmp_path):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        wire = json.loads(invocation.response.transport_evidence.request_body)
        wire["seed"] += 1
        with pytest.raises(ValueError, match="wire"):
            journal.record_before_dispatch(
                kwargs["request_evidence"].request, json.dumps(wire).encode()
            )
        assert journal.unresolved_request_ids() == ()
    finally:
        store.close()


def test_resolution_requires_sqlite_response_and_is_idempotent(tmp_path):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        with pytest.raises(ValueError, match="durable"):
            journal.record_resolution(invocation.response)
        store.record_diagnostic_invocation_evidence(invocation)
        journal.record_resolution(invocation.response)
        before = journal.path.read_bytes()
        journal.record_resolution(invocation.response)
        assert journal.path.read_bytes() == before
    finally:
        store.close()


def test_rehashed_foreign_run_journal_is_rejected(tmp_path):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        payload = json.loads(journal.path.read_text())
        payload["run_id"] = "foreign-run"
        payload["record_hash"] = canonical_payload_hash(
            {k: v for k, v in payload.items() if k != "record_hash"}
        )
        journal.path.write_text(json.dumps(payload) + "\n")
        with pytest.raises(ValueError, match="binding"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
    finally:
        store.close()


def test_failed_response_halts_without_advancing_or_retrying(tmp_path):
    store, _, _, _, _, kwargs, _, journal = started(tmp_path)
    try:
        stored = store.event_input_evidence(kwargs["pending_attempt"].event_id)
        invocation, _ = response_for(stored, kwargs, content="not JSON")
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        store.record_diagnostic_invocation_evidence(invocation)
        before = store.progress
        assert dispatch.reconcile_study_event(storage=store, journal=journal) == "failed"
        assert store.progress == before
        failure = store.terminal_failure_evidence()
        assert failure is not None
        assert dispatch.reconcile_study_event(storage=store, journal=journal) == "failed"
        assert store.terminal_failure_evidence() == failure
    finally:
        store.close()


def test_commit_crash_recovery_uses_same_response_and_single_resolution(tmp_path):
    import sqlite3

    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        store.record_diagnostic_invocation_evidence(invocation)
        store._connection.execute(
            "CREATE TRIGGER fail_progress BEFORE UPDATE ON progress BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
        assert store.progress.next_event_ordinal == 0
        assert journal.unresolved_request_ids() == ()
        saved = journal.path.read_bytes()
        store._connection.execute("DROP TRIGGER fail_progress")
        assert dispatch.reconcile_study_event(storage=store, journal=journal) == "committed"
        assert journal.path.read_bytes() == saved
    finally:
        store.close()


def test_missing_historical_ledger_does_not_make_next_event_safe(tmp_path):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        store.record_diagnostic_invocation_evidence(invocation)
        assert dispatch.reconcile_study_event(storage=store, journal=journal) == "committed"
        journal.path.write_bytes(b"")
        with pytest.raises(RuntimeError, match="intent"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
    finally:
        store.close()


def test_pending_prefix_is_classified_without_sending_or_starting(tmp_path):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[0])
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        journal = dispatch.StudyDispatchJournal(tmp_path / "dispatch.jsonl", storage=store)
        assert dispatch.reconcile_study_event(storage=store, journal=journal) == "pending"
        assert store.current_event_journal().latest_transition == kwargs["pending_attempt"]
        assert not journal.path.exists()
    finally:
        store.close()


def test_partial_journal_is_not_implicitly_repaired(tmp_path):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        journal.path.write_bytes(journal.path.read_bytes().rstrip(b"\n"))
        with pytest.raises(ValueError, match="partial"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
    finally:
        store.close()


@pytest.mark.parametrize("change", ["boolean", "duplicate"])
def test_ambiguous_json_wire_is_rejected_before_intent(tmp_path, change):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        wire = json.loads(invocation.response.transport_evidence.request_body)
        if change == "boolean":
            wire["top_p"] = True
            body = json.dumps(wire).encode()
        else:
            body = json.dumps(wire).replace('{"model":', '{"seed":0,"model":', 1).encode()
        with pytest.raises(ValueError, match="wire"):
            journal.record_before_dispatch(kwargs["request_evidence"].request, body)
        assert not journal.path.exists()
    finally:
        store.close()


def test_unchanged_hot_journal_does_not_rescan_history(tmp_path, monkeypatch):
    from pathlib import Path

    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        store.record_diagnostic_invocation_evidence(invocation)
        journal.record_resolution(invocation.response)
        journal.unresolved_request_ids()
        reads = []
        original = Path.open

        def traced(path, *args, **kwargs):
            if path == journal.path and args and args[0] == "r":
                reads.append(path)
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", traced)
        for _ in range(3):
            assert journal.unresolved_request_ids() == ()
        assert reads == []
    finally:
        store.close()


def test_hot_cover_detects_new_trusted_commit_without_intent(tmp_path):
    from test_identity_network_commit import land_terminal, next_input

    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        store.record_diagnostic_invocation_evidence(invocation)
        assert dispatch.reconcile_study_event(storage=store, journal=journal) == "committed"
        stored, following = next_input(store, kwargs)
        terminal, _ = land_terminal(store, stored, following)
        store.commit_study_success(terminal.attempt_id)
        with pytest.raises(RuntimeError, match="intent"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
    finally:
        store.close()


@pytest.mark.parametrize("cell", study_cells())
def test_existing_vllm_adapter_callback_integrates_with_sis_recovery(tmp_path, cell):
    from agent_ex.execution_evidence import DiagnosticPersistedInvocationEvidence
    from agent_ex.phase0b.vllm_event_adapter import Phase0BVllmEventAdapter
    from test_phase0b_vllm_event_adapter import FakeConnection

    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path, cell)
    try:
        envelope = json.loads(invocation.response.raw_body)
        envelope["usage"] = dict(invocation.response.usage)
        envelope["choices"][0]["finish_reason"] = "stop"

        class LocalConnection(FakeConnection):
            requests = []
            body = json.dumps(envelope).encode()

            def request(self, *args, **kwargs):
                assert len(journal.unresolved_request_ids()) == 1
                return super().request(*args, **kwargs)

        binding = kwargs["adapter_binding"]
        adapter = Phase0BVllmEventAdapter(
            binding.endpoint,
            served_model_name=binding.served_model_name,
            connection_factory=LocalConnection,
        )
        adapter.bind_dispatch_journal(journal.record_before_dispatch)
        response = adapter.generate(kwargs["request_evidence"].request, timeout_seconds=10.0)
        saved = DiagnosticPersistedInvocationEvidence.create(
            response=response, request_evidence=kwargs["request_evidence"]
        )
        store.record_diagnostic_invocation_evidence(saved)
        assert dispatch.reconcile_study_event(storage=store, journal=journal) == "committed"
        assert len(LocalConnection.requests) == 1
        assert store.progress.next_event_ordinal == 1
    finally:
        store.close()


def test_fsync_failure_prevents_adapter_from_even_opening_connection(tmp_path, monkeypatch):
    from agent_ex.phase0b.vllm_event_adapter import Phase0BVllmEventAdapter

    store, _, _, _, _, kwargs, _, journal = started(tmp_path)
    opened = []
    try:

        def fail_sync(fd):
            raise OSError("injected fsync failure")

        def forbidden_connection(*args, **kwargs):
            opened.append(True)
            raise AssertionError("must not connect")

        monkeypatch.setattr(os, "fsync", fail_sync)
        binding = kwargs["adapter_binding"]
        adapter = Phase0BVllmEventAdapter(
            binding.endpoint,
            served_model_name=binding.served_model_name,
            connection_factory=forbidden_connection,
        )
        adapter.bind_dispatch_journal(journal.record_before_dispatch)
        with pytest.raises(OSError, match="fsync"):
            adapter.generate(kwargs["request_evidence"].request, timeout_seconds=10.0)
        assert opened == []
        assert store.invocation_evidence(kwargs["pending_attempt"].attempt_id) is None
        assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


def test_hot_cache_still_checks_exact_wire_bytes_of_new_saved_response(tmp_path):
    store, _, _, _, _, kwargs, invocation, journal = started(tmp_path)
    try:
        wire = json.loads(invocation.response.transport_evidence.request_body)
        # Semantically identical wire, but not the bytes saved in transport.
        journal.record_before_dispatch(
            kwargs["request_evidence"].request, json.dumps(wire, sort_keys=True).encode()
        )
        store.record_diagnostic_invocation_evidence(invocation)
        with pytest.raises(ValueError, match="transport"):
            dispatch.reconcile_study_event(storage=store, journal=journal)
        assert store.progress.next_event_ordinal == 0
    finally:
        store.close()
