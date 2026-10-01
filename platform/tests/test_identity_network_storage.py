from dataclasses import replace

import pytest

from agent_ex.domain import FrozenSchedule, ScheduleSlot, canonical_payload_hash, derive_run_id
from agent_ex.identity_network.contracts import STUDY_ID, study_cells
from agent_ex.identity_network.groups import build_group_assignment
from agent_ex.identity_network.networks import build_randomized_counterpart
from agent_ex.network import build_ws_artifact
from agent_ex.state import PrivateUpdate, PrivateState, PublicPost, LatestPublicPointer
from agent_ex.feed import FeedCursor
from agent_ex.storage import RunStorage
from test_storage import manifest
from test_prompt import topic


def setup(cell, *, k=4, sweeps=1):
    from agent_ex.identity_network.storage import StudyRunBinding, StudyRunStorage

    agents = tuple(f"agent-{i:04d}" for i in range(20))
    schedule = FrozenSchedule(
        "paper1.schedule.v2",
        "sis-schedule",
        "1.0.0",
        20,
        sweeps,
        tuple(
            ScheduleSlot(s * 20 + i, s + 1, i, a, i % 2 == 0)
            for s in range(sweeps)
            for i, a in enumerate(agents)
        ),
    )
    groups = build_group_assignment(initial_stances={a: "label-2" for a in agents}, matched_seed=17)
    ws = build_ws_artifact(n=20, k=k, p=0, matched_seed=17, mock_only=True)
    randomized = build_randomized_counterpart(ws, matched_seed=17, swap_target=3, max_trials=1000)
    binding = StudyRunBinding.create(
        cell=cell,
        matched_seed=17,
        groups=groups,
        aliases={a: f"member-{i}" for i, a in enumerate(agents)},
        node_agent_ids=agents,
        topic_package=topic(),
        schedule=schedule,
        ws=ws,
        randomized=randomized,
        common_inputs_hash="a" * 64,
    )
    old = manifest(schedule)
    spec = {
        **dict(old.run_spec),
        "study_id": STUDY_ID,
        "cell_id": cell.cell_id,
        "protocol_id": STUDY_ID,
        "identity_network_binding": binding.to_payload(),
    }
    m = replace(
        old,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, 17, old.launch_nonce),
        protocol_id=STUDY_ID,
    )
    return StudyRunStorage, binding, m


def initialize(store, binding, agent, stance="label-2", topic_package=None, reason="Prior."):
    update = PrivateUpdate.create(
        topic_package=binding.topic_package if topic_package is None else topic_package,
        matched_seed=17,
        agent_id=agent,
        event_id=None,
        event_ordinal=None,
        sequence_index=0,
        stance_label=stance,
        reason=reason,
        confidence=None,
        published=True,
        source_attempt_id=None,
        mock_only=True,
    )
    state = PrivateState.from_update(update, previous=None, mock_only=True)
    post = PublicPost.from_private_update(update, mock_only=True)
    pointer = LatestPublicPointer.from_post(post, previous=None, mock_only=True)
    cursor = FeedCursor.initial(
        matched_seed=17,
        receiver_agent_id=agent,
        exposure_mode=binding.cursor_mode,
        exposure_graph_hash=binding.exposure_graph_hash,
        mock_only=True,
    )
    store.initialize_agent(
        private_update=update,
        private_state=state,
        public_post=post,
        latest_public_pointer=pointer,
        feed_cursor=cursor,
    )


@pytest.mark.parametrize("cell", study_cells())
def test_six_cell_stores_initialize_seal_reopen_and_legacy_reject(tmp_path, cell):
    cls, binding, m = setup(cell)
    args = binding.storage_arguments()
    path = tmp_path / "sis.sqlite"
    store = cls.create(path, manifest=m, **args)
    with store.acquire_run_lease():
        for agent in binding.node_agent_ids:
            initialize(store, binding, agent)
        root = store.seal_initial_state()
        assert store.progress.next_event_ordinal == 0
    store.close()
    reopened = cls.open(path, manifest=m, **args)
    assert reopened.binding.round0_root == root
    assert reopened.private_state(binding.node_agent_ids[0]).stance_label == "label-2"
    reopened.close()
    with pytest.raises(ValueError, match="canonical"):
        RunStorage.create(tmp_path / "legacy.sqlite", manifest=m, **args)


def test_incorrect_initial_stance_fails_without_write(tmp_path):
    cls, binding, m = setup(study_cells()[0])
    store = cls.create(tmp_path / "sis.sqlite", manifest=m, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            with pytest.raises(ValueError, match="initial"):
                initialize(store, binding, binding.node_agent_ids[0], "label-3")
            assert store.private_state(binding.node_agent_ids[0]) is None
            with pytest.raises(ValueError):
                store.seal_initial_state()
            assert store.binding.round0_root is None
    finally:
        store.close()


@pytest.mark.parametrize("change", ["cell", "seed", "schedule", "protocol", "graph"])
def test_manifest_binding_drift_rejected_before_database_creation(tmp_path, change):
    cls, binding, m = setup(study_cells()[1])
    spec = dict(m.run_spec)
    args = binding.storage_arguments()
    changes = {}
    if change == "cell":
        spec["cell_id"] = study_cells()[2].cell_id
    elif change == "seed":
        changes["matched_seed"] = 18
    elif change == "schedule":
        slots = list(m.schedule.slots)
        slots[0] = replace(slots[0], publish_flag=not slots[0].publish_flag)
        schedule = replace(m.schedule, slots=tuple(slots))
        changes.update(schedule=schedule, schedule_hash=schedule.schedule_hash)
        spec["schedule_hash"] = schedule.schedule_hash
    elif change == "protocol":
        spec["protocol_id"] = "paper1"
        changes["protocol_id"] = "paper1"
    else:
        args["expected_exposure_graph_artifact"] = binding.ws
        args["expected_exposure_graph_hash"] = binding.ws.output_hash
    altered = replace(
        m,
        **changes,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, changes.get("matched_seed", 17), m.launch_nonce),
    )
    path = tmp_path / "must-not-exist.sqlite"
    with pytest.raises(ValueError):
        cls.create(path, manifest=altered, **args)
    assert not path.exists()


@pytest.mark.parametrize("change", ["duplicate_alias", "group_alias", "metadata", "node_cover"])
def test_rehashed_binding_tampering_fails(change):
    from agent_ex.identity_network.storage import StudyRunBinding

    _, binding, _ = setup(study_cells()[0])
    payload = binding.to_payload()
    if change == "duplicate_alias":
        payload["aliases"][binding.node_agent_ids[1]] = payload["aliases"][
            binding.node_agent_ids[0]
        ]
    elif change == "group_alias":
        payload["aliases"][binding.node_agent_ids[0]] = "Blue-1"
    elif change == "metadata":
        payload["metadata"]["formal_parameter_authority"] = True
    else:
        payload["node_agent_ids"][0] = "outsider"
    payload["record_hash"] = canonical_payload_hash(
        {k: v for k, v in payload.items() if k != "record_hash"}
    )
    with pytest.raises(ValueError):
        StudyRunBinding.from_payload(payload)


def test_shared_initialization_and_seal_transactions_rollback(tmp_path, monkeypatch):
    cls, binding, m = setup(study_cells()[0])
    path = tmp_path / "rollback.sqlite"
    store = cls.create(path, manifest=m, **binding.storage_arguments())
    with store.acquire_run_lease():
        original = store._insert_current

        def fail(table, *args, **kwargs):
            if table == "feed_cursors":
                raise RuntimeError("injected write interruption")
            return original(table, *args, **kwargs)

        monkeypatch.setattr(store, "_insert_current", fail)
        with pytest.raises(RuntimeError, match="injected"):
            initialize(store, binding, binding.node_agent_ids[0])
        assert store.private_state(binding.node_agent_ids[0]) is None
        assert store.latest_public_pointer(binding.node_agent_ids[0]) is None
        monkeypatch.setattr(store, "_insert_current", original)
        for agent in binding.node_agent_ids:
            initialize(store, binding, agent)
        with monkeypatch.context() as patch:

            def abort_commit():
                raise RuntimeError("injected commit interruption")

            patch.setattr(store, "_commit_write", abort_commit)
            with pytest.raises(RuntimeError, match="injected"):
                store.seal_initial_state()
        assert store._read_binding().round0_root is None
        store.seal_initial_state()
        with pytest.raises(TypeError, match="StoredStudyInput"):
            store.record_diagnostic_prepared_attempt(
                None, policy=None, adapter_binding=None, request_evidence=None, pending_attempt=None
            )
        with pytest.raises(ValueError, match="SIS event writes"):
            store.commit_success(None)
    store.close()
    reopened = cls.open(path, manifest=m, **binding.storage_arguments())
    assert reopened.binding.round0_root is not None
    assert reopened.progress.next_event_ordinal == 0
    reopened.close()


@pytest.mark.parametrize("corruption", ["stance", "topic"])
def test_partial_unsealed_reopen_validates_sis_initial_stance(tmp_path, monkeypatch, corruption):
    cls, binding, m = setup(study_cells()[0])
    path = tmp_path / "partial-corrupt.sqlite"
    store = cls.create(path, manifest=m, **binding.storage_arguments())
    try:
        with store.acquire_run_lease(), monkeypatch.context() as patch:
            # Construct an otherwise valid shared typed bundle with wrong SIS stance.
            patch.setattr(store, "_validate_initial_update", lambda update: None)
            if corruption == "stance":
                initialize(store, binding, binding.node_agent_ids[0], "label-3")
            else:
                foreign_topic = replace(
                    binding.topic_package, core_statement="A different statement."
                )
                initialize(store, binding, binding.node_agent_ids[0], topic_package=foreign_topic)
        assert store.binding.round0_root is None
    finally:
        store.close()
    with pytest.raises(ValueError, match="SIS initial"):
        cls.open(path, manifest=m, **binding.storage_arguments())
