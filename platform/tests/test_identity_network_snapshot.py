"""Real SQLite input snapshots; no provider dispatch or state mutation."""

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.identity_network.contracts import study_cells
from test_identity_network_storage import setup, initialize


@pytest.mark.parametrize("cell", study_cells())
@pytest.mark.parametrize("degree", [4, 8])
def test_next_input_uses_bound_graph_and_actual_public_rows(tmp_path, cell, degree):
    cls, binding, manifest = setup(cell, k=degree)
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            before = store.progress
            cursor = store.feed_cursor(binding.node_agent_ids[0])
            snapshot = store.snapshot_next_input(
                persona_text="Common demographic persona.", feed_capacity=4, memory_window=3
            )
            payload = snapshot.to_payload()["payload"]
            neighbors = []
            if binding.exposure_graph is not None:
                for a, b in binding.exposure_graph.payload["edges"]:
                    if a == 0:
                        neighbors.append(binding.node_agent_ids[b])
                    elif b == 0:
                        neighbors.append(binding.node_agent_ids[a])
            assert payload["potential_neighbor_ids"] == sorted(neighbors)
            posts = payload["unread_public_posts"]
            assert {p["author_agent_id"] for p in posts} == set(neighbors)
            shown = payload["prompt"]["evidence"]["shown_posts"]
            assert len(shown) == min(4, len(neighbors))
            selected_ids = {p["post_id"] for p in shown}
            candidate_ids = {p["post_id"] for p in posts}
            expired_ids = {p["post_id"] for p in payload["selection"]["expired"]}
            assert selected_ids | expired_ids == candidate_ids
            assert not selected_ids & expired_ids
            assert len(expired_ids) == max(0, len(neighbors) - 4)
            assert all(p["reason"] == "Prior." for p in shown)
            selected = sorted(payload["selection"]["selected"], key=lambda p: p["display_slot"])
            assert [p["post_id"] for p in shown] == [p["post_id"] for p in selected]
            assert payload["prompt"]["evidence"]["source_groups"] == [
                binding.groups.group_for(p["source_agent_id"]) for p in shown
            ]
            assert payload["prompt"]["evidence"]["self_history"] == [
                {"stance": "label-2", "reason": "Prior.", "published": True}
            ]
            assert payload["previous_event_hash"] == before.event_chain_head
            assert payload["publish_flag"] is True
            assert payload["metadata"]["committed"] is False
            assert ArtifactEnvelope.from_payload(snapshot.to_payload()) == snapshot
            assert (
                store.snapshot_next_input(
                    persona_text="Common demographic persona.", feed_capacity=4, memory_window=3
                )
                == snapshot
            )
            assert store.progress == before
            assert store.feed_cursor(binding.node_agent_ids[0]) == cursor
        store.close()
        store = cls.open(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
        with store.acquire_run_lease():
            assert (
                store.snapshot_next_input(
                    persona_text="Common demographic persona.", feed_capacity=4, memory_window=3
                )
                == snapshot
            )
    finally:
        store.close()


def test_renderer_failure_rolls_back_read_transaction(tmp_path, monkeypatch):
    import agent_ex.identity_network.prompts as prompts

    cls, binding, manifest = setup(study_cells()[1])
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            before = store.progress
            changes = store._connection.total_changes
            original = prompts.render_study_prompt

            def interrupted(**kwargs):
                raise RuntimeError("injected render interruption")

            monkeypatch.setattr(prompts, "render_study_prompt", interrupted)
            with pytest.raises(RuntimeError, match="injected"):
                store.snapshot_next_input(persona_text="Persona", feed_capacity=4, memory_window=3)
            assert not store._connection.in_transaction
            assert store.progress == before
            assert store._connection.total_changes == changes
            monkeypatch.setattr(prompts, "render_study_prompt", original)
            store.snapshot_next_input(persona_text="Persona", feed_capacity=4, memory_window=3)
    finally:
        store.close()


@pytest.mark.parametrize("capacity,window", [(0, 3), (4, 0), (True, 3), (4, True)])
def test_invalid_candidate_policy_does_not_write(tmp_path, capacity, window):
    cls, binding, manifest = setup(study_cells()[0])
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            changes = store._connection.total_changes
            with pytest.raises((ValueError, TypeError)):
                store.snapshot_next_input(
                    persona_text="Persona", feed_capacity=capacity, memory_window=window
                )
            assert not store._connection.in_transaction
            assert store._connection.total_changes == changes
            assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


def test_snapshot_requires_lease_and_sealed_round0(tmp_path):
    cls, binding, manifest = setup(study_cells()[0])
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    try:
        with pytest.raises(RuntimeError, match="lease"):
            store.snapshot_next_input(persona_text="Persona", feed_capacity=4, memory_window=3)
        with store.acquire_run_lease():
            with pytest.raises(ValueError, match="round-0"):
                store.snapshot_next_input(persona_text="Persona", feed_capacity=4, memory_window=3)
    finally:
        store.close()
