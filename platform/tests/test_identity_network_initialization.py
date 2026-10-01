"""Six-store candidate initialization, source bound and network free."""

from contextlib import ExitStack
from dataclasses import replace

import pytest

from agent_ex.domain import canonical_payload_hash, derive_run_id
from agent_ex.identity_network.candidate import (
    build_six_cell_candidate,
    validate_six_cell_candidate,
)
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.storage import StudyRunStorage
from test_identity_network_candidate import sources


def context(candidate):
    runtime = candidate.payload["schedule_candidate"]["payload"]["runtime_provenance"]
    adapter = candidate.payload["population_candidate"]["payload"]["execution_inputs"]["payload"][
        "adapter_binding"
    ]
    return dict(
        git_sha="c" * 40,
        dirty=False,
        diff_hash=None,
        environment={
            "python_version": runtime["python_version"],
            "dependency_lock_hash": adapter["environment_lock_hash"],
            "platform": "synthetic-local-test",
        },
        launch_nonces={c.cell_id: "explicit-" + c.cell_id for c in study_cells()},
        schedule_uris={
            c.cell_id: "file:///test/" + c.cell_id + ".schedule.json" for c in study_cells()
        },
        created_at="2026-10-01T00:00:00+00:00",
        authorization_hash=None,
    )


def candidate():
    return build_six_cell_candidate(**sources())


def open_family(tmp_path, packet, stack, *, manifests=None):
    from agent_ex.identity_network.initialization import build_initial_manifests

    manifests = (
        build_initial_manifests(packet, **context(packet)) if manifests is None else manifests
    )
    stores = []
    for manifest, binding in zip(manifests, validate_six_cell_candidate(packet), strict=True):
        path = tmp_path / (binding.cell.cell_id + ".sqlite")
        store = StudyRunStorage.create(path, manifest=manifest, **binding.storage_arguments())
        stack.callback(store.close)
        stack.enter_context(store.acquire_run_lease())
        stores.append(store)
    return tuple(stores), manifests


def test_fresh_manifest_and_actual_round0_derive_from_full_candidate_and_reopen(tmp_path):
    from agent_ex.identity_network.initialization import (
        build_initial_manifests,
        initialize_candidate_family,
    )

    packet = candidate()
    manifests = build_initial_manifests(packet, **context(packet))
    assert len({m.run_id for m in manifests}) == 6
    assert all(m.event_ids == () and not m.is_complete for m in manifests)
    assert all(m.run_spec["sis_six_cell_candidate_hash"] == packet.output_hash for m in manifests)
    assert all("sis_diagnostic_authorization_hash" not in m.run_spec for m in manifests)
    assert all(m.run_spec["metadata"]["launch_authorized"] is False for m in manifests)
    with ExitStack() as stack:
        stores, _ = open_family(tmp_path, packet, stack, manifests=manifests)
        report = initialize_candidate_family(packet, stores=stores)
        assert report.payload["initialized_agents"] == 120
        assert report.payload["committed_events"] == 0
        assert report.payload["launch_authorized"] is False
        counts = tuple(s._connection.total_changes for s in stores)
        assert initialize_candidate_family(packet, stores=stores) == report
        assert tuple(s._connection.total_changes for s in stores) == counts
        for store in stores:
            assert store.binding.round0_root is not None
            assert len(store._round0_entries(require_exact=True)) == 20
    for m, b in zip(manifests, validate_six_cell_candidate(packet), strict=True):
        store = StudyRunStorage.open(
            tmp_path / (b.cell.cell_id + ".sqlite"), manifest=m, **b.storage_arguments()
        )
        try:
            store.verify_integrity()
            assert store.binding.round0_root is not None
            assert store.progress.next_event_ordinal == 0
        finally:
            store.close()


def test_candidate_only_initialization_cannot_start_existing_dispatch_runner(tmp_path):
    from agent_ex.identity_network.initialization import initialize_candidate_family
    from agent_ex.identity_network.dispatch import StudyDispatchJournal
    from agent_ex.identity_network.runner import run_study_cells_prefix

    packet = candidate()
    with ExitStack() as stack:
        stores, _ = open_family(tmp_path, packet, stack)
        initialize_candidate_family(packet, stores=stores)
        journals = tuple(
            StudyDispatchJournal(tmp_path / (s.study_binding.cell.cell_id + ".jsonl"), storage=s)
            for s in stores
        )

        def no_adapter():
            raise AssertionError("no model adapter may be constructed")

        with pytest.raises((ValueError, TypeError)):
            run_study_cells_prefix(
                stores=stores,
                journals=journals,
                stop_ordinal=1,
                adapter_factory=no_adapter,
                clock=lambda: "2026-10-01T00:00:01+00:00",
            )
        assert not list(tmp_path.glob("*.jsonl"))


def test_late_store_source_drift_rejected_before_any_agent_writes(tmp_path):
    from agent_ex.identity_network.initialization import (
        build_initial_manifests,
        initialize_candidate_family,
    )

    packet = candidate()
    manifests = list(build_initial_manifests(packet, **context(packet)))
    old = manifests[-1]
    spec = {**old.run_spec, "sis_six_cell_candidate_hash": "f" * 64}
    manifests[-1] = replace(
        old,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, old.matched_seed, old.launch_nonce),
    )
    with ExitStack() as stack:
        stores, _ = open_family(tmp_path, packet, stack, manifests=tuple(manifests))
        with pytest.raises(ValueError, match="candidate"):
            initialize_candidate_family(packet, stores=stores)
        assert all(
            s.binding.round0_root is None and s._round0_entries(require_exact=False) == []
            for s in stores
        )


@pytest.mark.parametrize("drift", ("lock", "model", "python"))
def test_external_late_manifest_runtime_drift_rejected_before_writes(tmp_path, drift):
    from agent_ex.identity_network.initialization import (
        build_initial_manifests,
        initialize_candidate_family,
    )

    packet = candidate()
    manifests = list(build_initial_manifests(packet, **context(packet)))
    old = manifests[-1]
    if drift == "lock":
        manifests[-1] = replace(
            old,
            environment_lock_hash="e" * 64,
            environment={**old.environment, "dependency_lock_hash": "e" * 64},
        )
    elif drift == "model":
        manifests[-1] = replace(
            old, model_identity={**old.model_identity, "revision": "foreign-revision"}
        )
    else:
        manifests[-1] = replace(old, environment={**old.environment, "python_version": "different"})
    with ExitStack() as stack:
        stores, _ = open_family(tmp_path, packet, stack, manifests=tuple(manifests))
        with pytest.raises(ValueError, match="candidate"):
            initialize_candidate_family(packet, stores=stores)
        assert all(s._round0_entries(require_exact=False) == [] for s in stores)


def test_missing_late_lease_rejected_before_any_initialization(tmp_path):
    from agent_ex.identity_network.initialization import initialize_candidate_family

    packet = candidate()
    with ExitStack() as stack:
        stores, _ = open_family(tmp_path, packet, stack)
        stores[-1]._owned_lease.release()
        with pytest.raises(RuntimeError):
            initialize_candidate_family(packet, stores=stores)
        assert all(s._round0_entries(require_exact=False) == [] for s in stores)


def test_existing_different_reason_rejected_before_other_cells_written(tmp_path):
    from agent_ex.identity_network.initialization import initialize_candidate_family
    from test_identity_network_storage import initialize

    packet = candidate()
    with ExitStack() as stack:
        stores, _ = open_family(tmp_path, packet, stack)
        binding = stores[-1].study_binding
        agent = binding.node_agent_ids[0]
        stance = packet.payload["population_candidate"]["payload"]["initial_updates"][0][
            "stance_label"
        ]
        initialize(stores[-1], binding, agent, stance=stance, reason="Different synthetic reason.")
        with pytest.raises(ValueError, match="candidate"):
            initialize_candidate_family(packet, stores=stores)
        assert all(s._round0_entries(require_exact=False) == [] for s in stores[:-1])
        assert len(stores[-1]._round0_entries(require_exact=False)) == 1


def test_interrupted_initialization_can_only_complete_same_candidate(tmp_path, monkeypatch):
    from agent_ex.identity_network.initialization import initialize_candidate_family

    packet = candidate()
    with ExitStack() as stack:
        stores, _ = open_family(tmp_path, packet, stack)
        original = stores[1].initialize_agent
        calls = []

        def fail_after_two(**kwargs):
            if len(calls) == 2:
                raise RuntimeError("injected initialization interruption")
            calls.append(kwargs["private_update"].agent_id)
            return original(**kwargs)

        monkeypatch.setattr(stores[1], "initialize_agent", fail_after_two)
        with pytest.raises(RuntimeError, match="interruption"):
            initialize_candidate_family(packet, stores=stores)
        assert stores[0].binding.round0_root is not None
        assert len(stores[1]._round0_entries(require_exact=False)) == 2
        assert stores[2]._round0_entries(require_exact=False) == []
        monkeypatch.setattr(stores[1], "initialize_agent", original)
        result = initialize_candidate_family(packet, stores=stores)
        assert result.payload["initialized_agents"] == 120


@pytest.mark.parametrize(
    "change", ("nonce", "uri", "python", "lock", "unresolved", "authorization")
)
def test_manifest_builder_rejects_incomplete_or_incompatible_provenance(change):
    from agent_ex.identity_network.initialization import build_initial_manifests

    packet = candidate()
    kwargs = context(packet)
    if change == "nonce":
        kwargs["launch_nonces"].pop(study_cells()[-1].cell_id)
    elif change == "uri":
        kwargs["schedule_uris"].pop(study_cells()[-1].cell_id)
    elif change == "python":
        kwargs["environment"]["python_version"] = "different"
    elif change == "lock":
        actual = kwargs["environment"]["dependency_lock_hash"]
        kwargs["environment"]["dependency_lock_hash"] = ("f" if actual != "f" * 64 else "e") * 64
    elif change == "unresolved":
        kwargs["environment"]["platform"] = "UNRESOLVED[SIS_MODEL_RUNTIME]"
    else:
        kwargs["authorization_hash"] = "not-a-hash"
    with pytest.raises((ValueError, TypeError)):
        build_initial_manifests(packet, **kwargs)
