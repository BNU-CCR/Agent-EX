from dataclasses import replace
import sqlite3

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import (
    EventStatus,
    GenerationAttempt,
    _json_ready,
    canonical_payload_hash,
    derive_run_id,
)
from agent_ex.execution_evidence import DiagnosticAdapterRequestEvidence
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.evidence import StudyEventInputEvidence
from agent_ex.storage import RunStorage, _canonical_json
from test_identity_network_execution_inputs import inputs, rebind
from test_identity_network_storage import setup, initialize
from test_phase0b_storage import _binding, _policy


def prefix_store(tmp_path, cell, *, include_common=True, include_authorization=True):
    from agent_ex.identity_network.stored_input import StoredStudyInput

    cls, binding, manifest = setup(cell)
    common, _ = inputs(binding)
    binding = rebind(binding, common)
    spec = {
        **manifest.run_spec,
        "identity_network_binding": binding.to_payload(),
        "identity_network_execution_inputs": common.to_payload(),
        "sis_diagnostic_authorization_hash": "c" * 64,
    }
    if not include_common:
        del spec["identity_network_execution_inputs"]
    if not include_authorization:
        del spec["sis_diagnostic_authorization_hash"]
    manifest = replace(
        manifest,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, 17, manifest.launch_nonce),
    )
    path = tmp_path / "sis.sqlite"
    store = cls.create(path, manifest=manifest, **binding.storage_arguments())
    lease = store.acquire_run_lease()
    lease.acquire()
    for agent in binding.node_agent_ids:
        initialize(store, binding, agent)
    store.seal_initial_state()
    snapshot = store.snapshot_next_input(
        persona_text="Common persona.", feed_capacity=4, memory_window=3
    )
    prepared = store.prepare_bound_snapshot_event(snapshot, common, attempt_index=1)
    stored_input = StoredStudyInput(StudyEventInputEvidence.from_prepared(prepared), snapshot)
    request = prepared.request
    evidence = DiagnosticAdapterRequestEvidence.create(
        request=request,
        run_authorization_hash="c" * 64,
        parser_limits_hash=prepared.parser_limits.record_hash,
        attempt_policy_hash=_policy().record_hash,
        adapter_binding=_binding(),
    )
    pending = GenerationAttempt(
        attempt_id=request.attempt_id,
        event_id=request.event_id,
        attempt_index=1,
        status=EventStatus.PENDING,
        request_id=request.request_id,
        exposure_id=stored_input.exposure_id,
        rendered_messages=request.rendered_messages,
        rendered_prompt_hash=request.rendered_messages_hash,
        request_parameters=request.generation_settings,
        request_parameters_hash=request.generation_settings_hash,
        model_identity=evidence.model_identity,
        model_identity_hash=evidence.model_identity_hash,
        model_seed=request.model_seed,
        provider_request_id=None,
        provider_metadata={},
        provider_metadata_hash=canonical_payload_hash({}),
        http_status=None,
        raw_response=None,
        raw_response_hash=None,
        parsed_response=None,
        parsed_response_hash=None,
        usage={},
        usage_hash=canonical_payload_hash({}),
        finish_reason=None,
        error=None,
        started_at=None,
        finished_at=None,
    )
    kwargs = dict(
        policy=_policy(),
        adapter_binding=_binding(),
        request_evidence=evidence,
        pending_attempt=pending,
    )
    return store, cls, binding, manifest, path, stored_input, kwargs


def row_counts(store):
    return tuple(
        store._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "event_input_evidence",
            "attempt_policy_evidence",
            "adapter_execution_bindings",
            "adapter_requests",
            "attempt_transitions",
            "invocation_evidence",
            "parse_evidence",
        )
    )


@pytest.mark.parametrize("cell", study_cells())
def test_sis_pending_prefix_persists_reopens_and_does_not_commit(tmp_path, cell):
    store, cls, binding, manifest, path, stored_input, kwargs = prefix_store(tmp_path, cell)
    try:
        store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
        assert row_counts(store) == (1, 1, 1, 1, 1, 0, 0)
        assert store.progress.next_event_ordinal == 0
        assert store.feed_cursor(binding.node_agent_ids[0]).activation_count == 0
        store.verify_integrity()
        with pytest.raises(ValueError, match="legacy"):
            RunStorage.event_input_evidence(store, stored_input.event_id)
        store.close()
        store = cls.open(path, manifest=manifest, **binding.storage_arguments())
        assert store.event_input_evidence(stored_input.event_id) == stored_input
        assert row_counts(store) == (1, 1, 1, 1, 1, 0, 0)
        assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


def test_wrong_authorization_does_not_land_partial_prefix(tmp_path):
    store, _, _, _, _, stored_input, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        old = kwargs["request_evidence"]
        kwargs["request_evidence"] = DiagnosticAdapterRequestEvidence.create(
            request=old.request,
            run_authorization_hash="f" * 64,
            parser_limits_hash=old.parser_limits_hash,
            attempt_policy_hash=old.attempt_policy_hash,
            adapter_binding=_binding(),
        )
        with pytest.raises(ValueError, match="authorization"):
            store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
        assert row_counts(store) == (0, 0, 0, 0, 0, 0, 0)
    finally:
        store.close()


def test_sqlite_prefix_insert_failure_is_atomic(tmp_path):
    store, _, _, _, _, stored_input, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        store._connection.execute(
            "CREATE TRIGGER fail_request BEFORE INSERT ON adapter_requests BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected"):
            store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
        assert row_counts(store) == (0, 0, 0, 0, 0, 0, 0)
        assert store.progress.next_event_ordinal == 0
        assert not store._connection.in_transaction
    finally:
        store.close()


def test_same_pending_prefix_is_idempotent(tmp_path):
    store, _, _, _, _, stored_input, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
        store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
        assert row_counts(store) == (1, 1, 1, 1, 1, 0, 0)
        assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


@pytest.mark.parametrize("missing", ["common", "authorization"])
def test_incomplete_manifest_cannot_land_prefix(tmp_path, missing):
    store, _, _, _, _, stored_input, kwargs = prefix_store(
        tmp_path,
        study_cells()[1],
        include_common=missing != "common",
        include_authorization=missing != "authorization",
    )
    try:
        with pytest.raises(ValueError):
            store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
        assert row_counts(store) == (0, 0, 0, 0, 0, 0, 0)
    finally:
        store.close()


def test_old_unstored_sis_input_cannot_land_prefix(tmp_path):
    store, _, _, _, _, stored_input, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        with pytest.raises(TypeError, match="StoredStudyInput"):
            store.record_diagnostic_prepared_attempt(stored_input.input, **kwargs)
        assert row_counts(store) == (0, 0, 0, 0, 0, 0, 0)
    finally:
        store.close()


@pytest.mark.parametrize("tamper", ["hash", "missing_request"])
def test_cold_reopen_rejects_corrupt_prefix(tmp_path, tamper):
    store, cls, binding, manifest, path, stored_input, kwargs = prefix_store(
        tmp_path, study_cells()[1]
    )
    store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
    store.close()
    with sqlite3.connect(path) as connection:
        if tamper == "hash":
            connection.execute("UPDATE event_input_evidence SET record_hash = ?", ("f" * 64,))
        else:
            connection.execute("DELETE FROM adapter_requests")
    with pytest.raises(ValueError):
        reopened = cls.open(path, manifest=manifest, **binding.storage_arguments())
        reopened.close()


def test_cold_reopen_rejects_rehashed_snapshot_binding_drift(tmp_path):
    from agent_ex.identity_network.stored_input import StoredStudyInput

    store, cls, binding, manifest, path, stored_input, kwargs = prefix_store(
        tmp_path, study_cells()[1]
    )
    store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
    store.close()
    snapshot_payload = _json_ready(stored_input.snapshot.payload)
    snapshot_payload["round0_root"] = "f" * 64
    changed_snapshot = ArtifactEnvelope.create(
        artifact_type="sis-input-snapshot",
        schema_version="paper1.identity-network.input-snapshot.v1",
        algorithm_id="sis-sqlite-input-snapshot",
        algorithm_version="1.0.0",
        input_hashes={"study-binding": binding.record_hash},
        rng_provenance=(),
        payload=snapshot_payload,
    )
    changed = StoredStudyInput(stored_input.input, changed_snapshot)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE event_input_evidence SET payload = ?, record_hash = ?",
            (_canonical_json(changed.to_payload()), changed.record_hash),
        )
    with pytest.raises(ValueError, match="database/common"):
        reopened = cls.open(path, manifest=manifest, **binding.storage_arguments())
        reopened.close()


def test_self_consistent_request_with_wrong_common_model_seed_is_rejected(tmp_path):
    store, _, _, _, _, stored_input, kwargs = prefix_store(tmp_path, study_cells()[1])
    try:
        evidence = kwargs["request_evidence"]
        old_request = evidence.request
        request = type(old_request).create(
            event_id=old_request.event_id,
            attempt_index=old_request.attempt_index,
            prompt_hash=old_request.prompt_hash,
            rendered_messages=tuple(dict(m) for m in old_request.rendered_messages),
            generation_settings=dict(old_request.generation_settings),
            model_seed=old_request.model_seed + 1,
            adapter_binding_hash=old_request.adapter_binding_hash,
        )
        kwargs["request_evidence"] = DiagnosticAdapterRequestEvidence.create(
            request=request,
            run_authorization_hash=evidence.run_authorization_hash,
            parser_limits_hash=evidence.parser_limits_hash,
            attempt_policy_hash=evidence.attempt_policy_hash,
            adapter_binding=_binding(),
        )
        kwargs["pending_attempt"] = replace(
            kwargs["pending_attempt"],
            model_seed=request.model_seed,
            request_id=request.request_id,
        )
        with pytest.raises(ValueError, match="common inputs"):
            store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
        assert row_counts(store) == (0, 0, 0, 0, 0, 0, 0)
    finally:
        store.close()


def test_cold_reopen_in_progress_never_implies_resend_permission(tmp_path):
    store, cls, binding, manifest, path, stored_input, kwargs = prefix_store(
        tmp_path, study_cells()[1]
    )
    store.record_diagnostic_prepared_attempt(stored_input, **kwargs)
    # Deliberately bypass the subclass's public write gate to emulate a coherent
    # out-of-scope database left by another implementation, without HTTP.
    RunStorage.append_attempt(
        store,
        replace(
            kwargs["pending_attempt"],
            status=EventStatus.IN_PROGRESS,
            started_at="2026-10-01T00:00:00Z",
        ),
    )
    store.close()
    reopened = cls.open(path, manifest=manifest, **binding.storage_arguments())
    try:
        assert (
            reopened.current_event_journal().resume_state
            == "in_progress_requires_provider_reconciliation"
        )
        assert reopened.progress.next_event_ordinal == 0
    finally:
        reopened.close()


def test_sis_response_writers_require_typed_evidence(tmp_path):
    store, _, _, _, _, _, _ = prefix_store(tmp_path, study_cells()[1])
    try:
        with pytest.raises(TypeError, match="typed diagnostic"):
            store.record_diagnostic_invocation_evidence(None)
        with pytest.raises(TypeError, match="typed diagnostic"):
            store.record_diagnostic_finalized_attempt(None, None)
    finally:
        store.close()
