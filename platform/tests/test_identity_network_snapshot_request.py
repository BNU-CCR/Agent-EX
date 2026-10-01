"""Preparing a request from a database-checked snapshot is still non-dispatching."""

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.identity_network.contracts import study_cells
from agent_ex.parser import ParserLimits
from agent_ex.identity_network.execution import finalize_study_response
from test_identity_network_execution import response_for
from test_identity_network_storage import setup, initialize


def arguments():
    return dict(
        persona_text="Common persona.",
        feed_capacity=4,
        memory_window=3,
        attempt_index=1,
        parser_limits=ParserLimits.create(
            max_raw_chars=4096,
            max_raw_bytes=8192,
            max_json_depth=8,
            max_reason_chars=1024,
            mock_only=True,
        ),
        model_seed=17,
        generation_settings={"temperature": 0.0, "top_p": 1.0, "max_tokens": 128},
        adapter_binding_hash="b" * 64,
    )


def sealed_store(tmp_path, cell):
    cls, binding, manifest = setup(cell)
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    return store, binding


@pytest.mark.parametrize("cell", study_cells())
def test_snapshot_request_exactly_binds_database_input_without_writes(tmp_path, cell):
    store, binding = sealed_store(tmp_path, cell)
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            snapshot = store.snapshot_next_input(
                persona_text="Common persona.", feed_capacity=4, memory_window=3
            )
            before = store._connection.total_changes
            prepared = store.prepare_snapshot_event(snapshot, **arguments())
            payload = snapshot.to_payload()["payload"]
            assert prepared.run_id == payload["run_id"]
            assert prepared.previous_event_hash == payload["previous_event_hash"]
            assert prepared.request.event_id == payload["event_id"]
            assert prepared.private_state.to_payload() == payload["pre_state"]
            assert prepared.prompt.prompt_hash == payload["prompt"]["prompt_hash"]
            assert prepared.prompt.evidence_hash == payload["prompt"]["evidence_hash"]
            assert prepared.request.rendered_messages == prepared.prompt.messages
            assert prepared.publish_flag == payload["publish_flag"]
            result = finalize_study_response(
                prepared=prepared, response=response_for(prepared, tmp_path)
            )
            assert result.parse.success
            assert result.private_state.stance_label == "label-5"
            assert result.public_post is not None
            assert result.trace.payload["metadata"]["committed"] is False
            assert store.private_state(binding.node_agent_ids[0]).stance_label == "label-2"
            assert store._connection.total_changes == before
            assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


@pytest.mark.parametrize(
    "field",
    [
        "previous_event_hash",
        "publish_flag",
        "receiver_agent_id",
        "round0_root",
        "study_binding_hash",
        "unread_public_posts",
        "private_history",
        "selection",
        "metadata",
        "prompt",
        "event_ordinal",
        "run_id",
    ],
)
def test_rehashed_snapshot_tampering_rejected_without_writes(tmp_path, field):
    store, binding = sealed_store(tmp_path, study_cells()[1])
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            snapshot = store.snapshot_next_input(
                persona_text="Common persona.", feed_capacity=4, memory_window=3
            )
            payload = snapshot.to_payload()["payload"]
            if field in {"previous_event_hash", "round0_root", "study_binding_hash"}:
                payload[field] = "f" * 64
            elif field == "publish_flag":
                payload[field] = False
            elif field == "receiver_agent_id":
                payload[field] = binding.node_agent_ids[1]
            elif field == "run_id":
                payload[field] = "other-run"
            elif field == "event_ordinal":
                payload[field] = 1
            elif field == "metadata":
                payload[field]["committed"] = True
            else:
                payload[field] = []
            forged = ArtifactEnvelope.create(
                artifact_type=snapshot.artifact_type,
                schema_version=snapshot.schema_version,
                algorithm_id=snapshot.algorithm_id,
                algorithm_version=snapshot.algorithm_version,
                input_hashes=snapshot.input_hashes,
                payload=payload,
                rng_provenance=(),
            )
            changes = store._connection.total_changes
            with pytest.raises(ValueError, match="snapshot"):
                store.prepare_snapshot_event(forged, **arguments())
            assert store._connection.total_changes == changes
            assert not store._connection.in_transaction
    finally:
        store.close()


def test_changed_persona_or_policy_cannot_reuse_snapshot(tmp_path):
    store, binding = sealed_store(tmp_path, study_cells()[0])
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            snapshot = store.snapshot_next_input(
                persona_text="Common persona.", feed_capacity=4, memory_window=3
            )
            for changed in (
                {"persona_text": "Different persona."},
                {"feed_capacity": 6},
                {"memory_window": 5},
            ):
                with pytest.raises(ValueError, match="snapshot"):
                    store.prepare_snapshot_event(snapshot, **{**arguments(), **changed})
    finally:
        store.close()
