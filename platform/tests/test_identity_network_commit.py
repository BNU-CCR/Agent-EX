"""Local SQLite commits with explicitly synthetic provider responses."""

import sqlite3

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import GenerationAttempt, _json_ready
from agent_ex.storage import _canonical_json
from agent_ex.execution_evidence import DiagnosticAdapterRequestEvidence
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.evidence import StudyEventInputEvidence
from agent_ex.identity_network.execution import finalize_study_response
from agent_ex.identity_network.stored_input import StoredStudyInput
from test_identity_network_prefix import prefix_store
from test_identity_network_response import response_for, terminal_for


def next_input(store, template):
    common = store._stored_common_inputs
    slot = store.schedule_slot(store.progress.next_event_ordinal)
    snapshot = store.snapshot_next_input(
        persona_text=common.payload["persona_by_agent"][slot.agent_id],
        feed_capacity=common.payload["feed_capacity"],
        memory_window=common.payload["memory_window"],
    )
    prepared = store.prepare_bound_snapshot_event(snapshot, common, attempt_index=1)
    stored = StoredStudyInput(StudyEventInputEvidence.from_prepared(prepared), snapshot)
    request = prepared.request
    old = template["request_evidence"]
    evidence = DiagnosticAdapterRequestEvidence.create(
        request=request,
        run_authorization_hash=old.run_authorization_hash,
        parser_limits_hash=prepared.parser_limits.record_hash,
        attempt_policy_hash=template["policy"].record_hash,
        adapter_binding=template["adapter_binding"],
    )
    payload = template["pending_attempt"].to_payload()
    payload.update(
        event_id=request.event_id,
        attempt_id=request.attempt_id,
        request_id=request.request_id,
        exposure_id=stored.exposure_id,
        rendered_messages=[dict(m) for m in request.rendered_messages],
        rendered_prompt_hash=request.rendered_messages_hash,
        request_parameters=dict(request.generation_settings),
        request_parameters_hash=request.generation_settings_hash,
        model_seed=request.model_seed,
    )
    kwargs = {
        **template,
        "request_evidence": evidence,
        "pending_attempt": GenerationAttempt.from_payload(payload),
    }
    return stored, kwargs


def land_terminal(store, stored, kwargs, *, valid=True):
    store.record_diagnostic_prepared_attempt(stored, **kwargs)
    running = store.start_diagnostic_attempt(
        kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z"
    )
    invocation, prepared = response_for(stored, kwargs, content=None if valid else "not JSON")
    result = finalize_study_response(prepared=prepared, response=invocation.response)
    store.record_diagnostic_invocation_evidence(invocation)
    terminal = terminal_for(running, invocation, result.parse)
    store.record_diagnostic_finalized_attempt(terminal, result.parse)
    return terminal, result


@pytest.mark.parametrize("cell", study_cells())
def test_two_success_commits_reopen_and_public_private_split(tmp_path, cell):
    store, cls, binding, manifest, path, stored, kwargs = prefix_store(tmp_path, cell)
    try:
        first, result = land_terminal(store, stored, kwargs)
        store.commit_study_success(first.attempt_id)
        assert store.progress.next_event_ordinal == 1
        assert store.private_state(stored.receiver_agent_id) == result.private_state
        assert (
            store.latest_public_pointer(stored.receiver_agent_id).latest_post_id
            == result.public_post.post_id
        )
        store.close()
        store = cls.open(path, manifest=manifest, **binding.storage_arguments())
        with store.acquire_run_lease():
            second_input, second_kwargs = next_input(store, kwargs)
            assert second_input.input.previous_event_hash == store.progress.event_chain_head
            prior_pointer = store.latest_public_pointer(second_input.receiver_agent_id)
            second, result = land_terminal(store, second_input, second_kwargs)
            assert not second_input.publish_flag
            store.commit_study_success(second.attempt_id)
            assert store.private_state(second_input.receiver_agent_id) == result.private_state
            assert store.latest_public_pointer(second_input.receiver_agent_id) == prior_pointer
        store.close()
        store = cls.open(path, manifest=manifest, **binding.storage_arguments())
        assert store.progress.next_event_ordinal == 2
        assert store.event_at(0).publish_flag
        assert not store.event_at(1).publish_flag
        store.verify_integrity()
    finally:
        store.close()


def test_failed_response_cannot_commit_or_advance(tmp_path):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        terminal, _ = land_terminal(store, stored, kwargs, valid=False)
        with pytest.raises(ValueError, match="success"):
            store.commit_study_success(terminal.attempt_id)
        assert store.progress.next_event_ordinal == 0
        assert store.private_state(stored.receiver_agent_id) == stored.input.private_state
    finally:
        store.close()


def test_commit_interruption_rolls_back_all_state_and_retries_without_http(tmp_path):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        terminal, result = land_terminal(store, stored, kwargs)
        before = store.progress
        pointer = store.latest_public_pointer(stored.receiver_agent_id)
        store._connection.execute(
            "CREATE TRIGGER fail_progress BEFORE UPDATE ON progress BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected"):
            store.commit_study_success(terminal.attempt_id)
        assert store.progress == before
        assert store.event_at(0) is None
        assert store.private_state(stored.receiver_agent_id) == stored.input.private_state
        assert store.latest_public_pointer(stored.receiver_agent_id) == pointer
        assert not store._connection.in_transaction
        store._connection.execute("DROP TRIGGER fail_progress")
        store.commit_study_success(terminal.attempt_id)
        assert store.private_state(stored.receiver_agent_id) == result.private_state
        assert store.progress.next_event_ordinal == 1
    finally:
        store.close()


def test_repeated_receiver_uses_committed_private_history_after_reopen(tmp_path):
    store, cls, binding, manifest, path, stored, kwargs = prefix_store(
        tmp_path, study_cells()[5], sweeps=2
    )
    try:
        for ordinal in range(20):
            if ordinal:
                stored, current = next_input(store, kwargs)
            else:
                current = kwargs
            terminal, _ = land_terminal(store, stored, current)
            store.commit_study_success(terminal.attempt_id)
        store.close()
        store = cls.open(path, manifest=manifest, **binding.storage_arguments())
        with store.acquire_run_lease():
            stored, current = next_input(store, kwargs)
            assert stored.receiver_agent_id == binding.node_agent_ids[0]
            assert stored.input.private_state.successful_update_count == 2
            assert len(stored.snapshot.payload["private_history"]) == 2
            assert stored.input.prompt.evidence["self_history"][-1]["stance"] == "label-5"
            terminal, result = land_terminal(store, stored, current)
            store.commit_study_success(terminal.attempt_id)
            assert result.private_state.successful_update_count == 3
            for _ in range(21, 40):
                stored, current = next_input(store, kwargs)
                terminal, _ = land_terminal(store, stored, current)
                store.commit_study_success(terminal.attempt_id)
        store.close()
        store = cls.open(path, manifest=manifest, **binding.storage_arguments())
        assert store.progress.next_event_ordinal == 40
        assert store.current_event_journal().resume_state == "complete"
    finally:
        store.close()


def test_cold_reopen_rejects_rehashed_historical_previous_chain(tmp_path):
    from dataclasses import replace

    store, cls, binding, manifest, path, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    terminal, _ = land_terminal(store, stored, kwargs)
    store.commit_study_success(terminal.attempt_id)
    store.close()
    payload = _json_ready(stored.snapshot.payload)
    payload["previous_event_hash"] = "f" * 64
    snapshot = ArtifactEnvelope.create(
        artifact_type=stored.snapshot.artifact_type,
        schema_version=stored.snapshot.schema_version,
        algorithm_id=stored.snapshot.algorithm_id,
        algorithm_version=stored.snapshot.algorithm_version,
        input_hashes=stored.snapshot.input_hashes,
        rng_provenance=(),
        payload=payload,
    )
    changed = StoredStudyInput(replace(stored.input, previous_event_hash="f" * 64), snapshot)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE event_input_evidence SET payload=?, record_hash=?",
            (_canonical_json(changed.to_payload()), changed.record_hash),
        )
    with pytest.raises(ValueError, match="database/common"):
        reopened = cls.open(path, manifest=manifest, **binding.storage_arguments())
        reopened.close()


def test_committed_event_has_full_evidence_references(tmp_path):
    store, _, _, _, _, stored, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        terminal, _ = land_terminal(store, stored, kwargs)
        store.commit_study_success(terminal.attempt_id)
        refs = store.evidence_references(terminal.event_id)
        assert refs.event_input_evidence_hash == stored.record_hash
        assert refs.committed_event_id == terminal.event_id
    finally:
        store.close()
