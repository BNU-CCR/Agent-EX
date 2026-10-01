from dataclasses import replace

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import canonical_payload_hash, derive_run_id
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.storage import StudyRunBinding
from agent_ex.state import PrivateUpdate
from test_identity_network_storage import setup, initialize
from test_identity_network_snapshot_request import arguments
from test_phase0b_storage import _binding, _policy


def inputs(binding):
    from agent_ex.identity_network.execution_inputs import build_execution_inputs

    initial = tuple(
        PrivateUpdate.create(
            topic_package=binding.topic_package,
            matched_seed=17,
            agent_id=agent,
            event_id=None,
            event_ordinal=None,
            sequence_index=0,
            stance_label="label-2",
            reason="Prior.",
            confidence=None,
            published=True,
            source_attempt_id=None,
            mock_only=True,
        )
        for agent in binding.node_agent_ids
    )
    kwargs = dict(
        binding=binding,
        persona_by_agent={a: "Common persona." for a in binding.node_agent_ids},
        initial_updates=initial,
        feed_capacity=4,
        memory_window=3,
        parser_limits=arguments()["parser_limits"],
        generation_settings=arguments()["generation_settings"],
        model_seeds=tuple(17 for _ in binding.schedule.slots),
        adapter_binding=_binding(),
        attempt_policy=_policy(),
    )
    return build_execution_inputs(**kwargs), kwargs


def rebind(binding, artifact):
    return StudyRunBinding.create(
        cell=binding.cell,
        matched_seed=binding.matched_seed,
        groups=ArtifactEnvelope.from_payload(binding.to_payload()["groups"]),
        aliases=binding.aliases,
        node_agent_ids=binding.node_agent_ids,
        topic_package=binding.topic_package,
        schedule=binding.schedule,
        ws=binding.ws,
        randomized=binding.randomized,
        common_inputs_hash=artifact.output_hash,
    )


def test_common_artifact_identical_across_six_cells_and_replays():
    from agent_ex.identity_network.execution_inputs import validate_execution_inputs

    artifacts = []
    for cell in study_cells():
        _, binding, _ = setup(cell)
        artifact, _ = inputs(binding)
        binding = rebind(binding, artifact)
        validate_execution_inputs(ArtifactEnvelope.from_payload(artifact.to_payload()), binding)
        artifacts.append(artifact)
    assert all(a == artifacts[0] for a in artifacts)


@pytest.mark.parametrize(
    "change",
    [
        "roster",
        "duplicate",
        "seeds",
        "seed_bool",
        "capacity",
        "window",
        "persona",
        "parser",
        "settings",
    ],
)
def test_incomplete_or_invalid_common_inputs_rejected(change):
    from agent_ex.identity_network.execution_inputs import build_execution_inputs

    _, binding, _ = setup(study_cells()[0])
    _, kwargs = inputs(binding)
    if change == "roster":
        kwargs["initial_updates"] = kwargs["initial_updates"][:-1]
    elif change == "duplicate":
        kwargs["initial_updates"] = kwargs["initial_updates"][:-1] + (kwargs["initial_updates"][0],)
    elif change == "seeds":
        kwargs["model_seeds"] = (17,)
    elif change == "seed_bool":
        kwargs["model_seeds"] = tuple(True for _ in binding.schedule.slots)
    elif change == "capacity":
        kwargs["feed_capacity"] = True
    elif change == "window":
        kwargs["memory_window"] = 0
    elif change == "parser":
        kwargs["parser_limits"] = {}
    elif change == "settings":
        kwargs["generation_settings"] = {"max_tokens": -1}
    else:
        kwargs["persona_by_agent"] = {}
    with pytest.raises((ValueError, TypeError)):
        build_execution_inputs(**kwargs)


@pytest.mark.parametrize(
    "field",
    [
        "metadata",
        "adapter_binding",
        "extra",
        "common_identity",
        "attempt_policy",
        "consistency",
        "envelope",
    ],
)
def test_rehashed_bad_contract_rejected(field):
    from agent_ex.identity_network.execution_inputs import validate_execution_inputs

    _, binding, _ = setup(study_cells()[0])
    artifact, _ = inputs(binding)
    payload = artifact.to_payload()["payload"]
    if field == "metadata":
        payload[field]["formal_parameter_authority"] = True
    elif field == "extra":
        payload[field] = "not allowed"
    elif field == "common_identity":
        payload[field]["group_artifact_hash"] = "f" * 64
    elif field == "attempt_policy":
        payload[field]["max_same_event_retries"] = -1
    elif field == "consistency":
        payload["explicit_consistency_instruction"] = True
    elif field == "envelope":
        pass
    else:
        payload[field]["model_repository"] = "UNRESOLVED[SIS_MODEL]"
    forged = ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id="wrong-algorithm" if field == "envelope" else artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        rng_provenance=(),
        payload=payload,
    )
    # Coordinately updated reference alone must not bless invalid nested semantics.
    with pytest.raises((ValueError, TypeError)):
        validate_execution_inputs(forged, rebind(binding, forged))


@pytest.mark.parametrize("cell", study_cells())
def test_bound_request_uses_artifact_and_actual_round0(tmp_path, cell):
    cls, binding, manifest = setup(cell)
    artifact, _ = inputs(binding)
    binding = rebind(binding, artifact)
    spec = {**manifest.run_spec, "identity_network_binding": binding.to_payload()}
    manifest = replace(
        manifest,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, 17, manifest.launch_nonce),
    )
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            snapshot = store.snapshot_next_input(
                persona_text="Common persona.", feed_capacity=4, memory_window=3
            )
            changes = store._connection.total_changes
            prepared = store.prepare_bound_snapshot_event(snapshot, artifact, attempt_index=1)
            assert prepared.request.adapter_binding_hash == _binding().record_hash
            assert prepared.request.model_seed == 17
            assert prepared.parser_limits == arguments()["parser_limits"]
            assert store._connection.total_changes == changes
            assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


def test_bound_request_rejects_actual_initial_reason_drift(tmp_path):
    cls, binding, manifest = setup(study_cells()[1])
    artifact, _ = inputs(binding)
    binding = rebind(binding, artifact)
    spec = {**manifest.run_spec, "identity_network_binding": binding.to_payload()}
    manifest = replace(
        manifest,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, 17, manifest.launch_nonce),
    )
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent, reason="Different initial evidence.")
            store.seal_initial_state()
            snapshot = store.snapshot_next_input(
                persona_text="Common persona.", feed_capacity=4, memory_window=3
            )
            changes = store._connection.total_changes
            with pytest.raises(ValueError, match="actual round-0"):
                store.prepare_bound_snapshot_event(snapshot, artifact, attempt_index=1)
            assert store._connection.total_changes == changes
            assert store.progress.next_event_ordinal == 0
    finally:
        store.close()


def test_unbound_reference_rejected():
    from agent_ex.identity_network.execution_inputs import validate_execution_inputs

    _, binding, _ = setup(study_cells()[0])
    artifact, _ = inputs(binding)
    with pytest.raises(ValueError, match="common inputs"):
        validate_execution_inputs(artifact, binding)


def test_repeated_bound_preparation_does_not_rescan_full_static_inputs(tmp_path, monkeypatch):
    import agent_ex.identity_network.execution_inputs as module

    cls, binding, manifest = setup(study_cells()[1])
    artifact, _ = inputs(binding)
    binding = rebind(binding, artifact)
    spec = {**manifest.run_spec, "identity_network_binding": binding.to_payload()}
    manifest = replace(
        manifest,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, 17, manifest.launch_nonce),
    )
    store = cls.create(tmp_path / "sis.sqlite", manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            snapshot = store.snapshot_next_input(
                persona_text="Common persona.", feed_capacity=4, memory_window=3
            )
            counts = {"artifact": 0, "round0": 0}
            original_validate = module.validate_execution_inputs
            original_round0 = store._round0_entries

            def counted_validate(*args):
                counts["artifact"] += 1
                return original_validate(*args)

            def counted_round0(**kwargs):
                counts["round0"] += 1
                return original_round0(**kwargs)

            monkeypatch.setattr(module, "validate_execution_inputs", counted_validate)
            monkeypatch.setattr(store, "_round0_entries", counted_round0)
            first = store.prepare_bound_snapshot_event(snapshot, artifact, attempt_index=1)
            assert store.prepare_bound_snapshot_event(snapshot, artifact, attempt_index=1) == first
            assert counts == {"artifact": 1, "round0": 1}
    finally:
        store.close()


@pytest.mark.parametrize("source", ["same_connection", "external_connection"])
def test_cached_artifact_does_not_bypass_database_mutation_detection(tmp_path, source):
    import sqlite3

    cls, binding, manifest = setup(study_cells()[1])
    artifact, _ = inputs(binding)
    binding = rebind(binding, artifact)
    spec = {**manifest.run_spec, "identity_network_binding": binding.to_payload()}
    manifest = replace(
        manifest,
        run_spec=spec,
        run_spec_hash=canonical_payload_hash(spec),
        run_id=derive_run_id(spec, 17, manifest.launch_nonce),
    )
    path = tmp_path / "sis.sqlite"
    store = cls.create(path, manifest=manifest, **binding.storage_arguments())
    try:
        with store.acquire_run_lease():
            for agent in binding.node_agent_ids:
                initialize(store, binding, agent)
            store.seal_initial_state()
            snapshot = store.snapshot_next_input(
                persona_text="Common persona.", feed_capacity=4, memory_window=3
            )
            store.prepare_bound_snapshot_event(snapshot, artifact, attempt_index=1)
            if source == "same_connection":
                store._connection.execute(
                    "UPDATE private_updates SET payload_hash = ?", ("f" * 64,)
                )
            else:
                with sqlite3.connect(path) as connection:
                    connection.execute("UPDATE private_updates SET payload_hash = ?", ("f" * 64,))
            with pytest.raises(ValueError, match="hash"):
                store.prepare_bound_snapshot_event(snapshot, artifact, attempt_index=1)
    finally:
        store.close()
