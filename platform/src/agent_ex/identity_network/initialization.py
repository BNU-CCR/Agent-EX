"""Candidate-only manifests and resumable round-0 initialization; no dispatch.

Callers create stores and own all leases. Initialization is atomic per agent,
not across databases; interrupted work is retained and checked on reentry.
An authorization hash is only a reference, never a verified human receipt.
"""

from ..artifacts import ArtifactEnvelope
from ..domain import (
    EventStatus,
    RunManifest,
    _json_ready,
    _require_sha256,
    canonical_payload_hash,
    derive_run_id,
)
from ..feed import FeedCursor
from ..state import LatestPublicPointer, PrivateState, PrivateUpdate, PublicPost
from ..storage import _load_canonical_json
from .candidate import validate_six_cell_candidate
from .contracts import STUDY_ID
from .materialization import _reject_unresolved
from .storage import StudyRunStorage


def build_initial_manifests(
    packet,
    *,
    git_sha,
    dirty,
    diff_hash,
    environment,
    launch_nonces,
    schedule_uris,
    created_at,
    authorization_hash,
):
    """Build fresh explicit candidate manifests without writing any files."""
    bindings = validate_six_cell_candidate(packet)
    _reject_unresolved((environment, launch_nonces, schedule_uris, created_at))
    _require_sha256("authorization_hash", authorization_hash, optional=True)
    cells = {b.cell.cell_id for b in bindings}
    if set(launch_nonces) != cells or set(schedule_uris) != cells:
        raise ValueError("exact six-cell nonce and schedule URI cover required")
    payload = _json_ready(packet.payload)
    common = payload["population_candidate"]["payload"]["execution_inputs"]
    adapter = common["payload"]["adapter_binding"]
    runtime = payload["schedule_candidate"]["payload"]["runtime_provenance"]
    if environment.get("python_version") != runtime["python_version"]:
        raise ValueError("candidate schedule Python runtime mismatch")
    if environment.get("dependency_lock_hash") != adapter["environment_lock_hash"]:
        raise ValueError("candidate environment lock mismatch")
    manifests = []
    for b in bindings:
        spec = {
            "study_id": STUDY_ID,
            "cell_id": b.cell.cell_id,
            "protocol_id": STUDY_ID,
            "protocol_version": "sis-candidate-v1",
            "protocol_hash": packet.output_hash,
            "schedule_hash": b.schedule.schedule_hash,
            "sis_six_cell_candidate_hash": packet.output_hash,
            "identity_network_binding": b.to_payload(),
            "identity_network_execution_inputs": common,
            "run_config": {
                "population": b.schedule.population_size,
                "sweep_count": b.schedule.sweep_count,
                "expected_event_count": b.schedule.count,
            },
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
                "launch_authorized": False,
                "runtime_authority": "declared_candidate_unattested",
            },
        }
        if authorization_hash is not None:
            spec["sis_diagnostic_authorization_hash"] = authorization_hash
        nonce = launch_nonces[b.cell.cell_id]
        manifests.append(
            RunManifest(
                run_id=derive_run_id(spec, b.matched_seed, nonce),
                run_spec=spec,
                run_spec_hash=canonical_payload_hash(spec),
                matched_seed=b.matched_seed,
                launch_nonce=nonce,
                protocol_id=STUDY_ID,
                protocol_version="sis-candidate-v1",
                protocol_hash=packet.output_hash,
                git_sha=git_sha,
                dirty=dirty,
                diff_hash=diff_hash,
                environment_lock_hash=adapter["environment_lock_hash"],
                model_identity={
                    "provider": "vllm",
                    "model": adapter["model_repository"],
                    "revision": adapter["model_revision"],
                    "runtime": adapter["vllm_version"],
                },
                environment=environment,
                schedule_uri=schedule_uris[b.cell.cell_id],
                schedule=b.schedule,
                schedule_hash=b.schedule.schedule_hash,
                checkpoint_uri=None,
                checkpoint_hash=None,
                recovery_cursor=None,
                event_ids=(),
                terminal_counts={s.value: 0 for s in EventStatus},
                started_at=created_at,
                updated_at=created_at,
                archive={"status": "pending", "uri": None, "hash": None},
            )
        )
    return tuple(manifests)


def _initial_bundle(update, binding):
    post = PublicPost.from_private_update(update, mock_only=True)
    return dict(
        private_update=update,
        private_state=PrivateState.from_update(update, previous=None, mock_only=True),
        public_post=post,
        latest_public_pointer=LatestPublicPointer.from_post(post, previous=None, mock_only=True),
        feed_cursor=FeedCursor.initial(
            matched_seed=binding.matched_seed,
            receiver_agent_id=update.agent_id,
            exposure_mode=binding.cursor_mode,
            exposure_graph_hash=binding.exposure_graph_hash,
            mock_only=True,
        ),
    )


def _preflight_candidate_family(packet, stores, *, require_leases):
    bindings = validate_six_cell_candidate(packet)
    if (
        type(stores) is not tuple
        or len(stores) != 6
        or any(not isinstance(s, StudyRunStorage) for s in stores)
    ):
        raise ValueError("six typed candidate stores required")
    if (
        len({s._database_identity for s in stores}) != 6
        or len({s.binding.run_id for s in stores}) != 6
    ):
        raise ValueError("six independent candidate databases/run identities required")
    common = _json_ready(packet.payload)["population_candidate"]["payload"]["execution_inputs"]
    adapter = common["payload"]["adapter_binding"]
    runtime = packet.payload["schedule_candidate"]["payload"]["runtime_provenance"]
    updates = tuple(PrivateUpdate.from_payload(u) for u in common["payload"]["initial_updates"])
    missing = []
    for store, binding in zip(stores, bindings, strict=True):
        if require_leases:
            store.assert_run_lease_owned()
        store.verify_integrity()
        manifest = RunManifest.from_payload(
            _load_canonical_json(
                store._connection.execute(
                    "SELECT manifest_payload_json FROM binding WHERE singleton=1"
                ).fetchone()[0],
                "candidate baseline manifest",
            ),
            schedule=binding.schedule,
        )
        expected_model = {
            "provider": "vllm",
            "model": adapter["model_repository"],
            "revision": adapter["model_revision"],
            "runtime": adapter["vllm_version"],
        }
        _reject_unresolved(manifest.environment)
        if (
            dict(manifest.model_identity) != expected_model
            or manifest.environment_lock_hash != adapter["environment_lock_hash"]
            or manifest.environment["python_version"] != runtime["python_version"]
            or manifest.protocol_version != "sis-candidate-v1"
            or manifest.protocol_hash != packet.output_hash
            or manifest.run_spec.get("metadata", {}).get("launch_authorized") is not False
        ):
            raise ValueError("baseline manifest runtime/protocol differs from candidate")
        if (
            store.study_binding != binding
            or store._sis_run_spec.get("sis_six_cell_candidate_hash") != packet.output_hash
            or _json_ready(store._sis_run_spec.get("identity_network_execution_inputs")) != common
        ):
            raise ValueError("store differs from full candidate identity")
        if (
            store.progress.next_event_ordinal != 0
            or store._connection.execute("SELECT 1 FROM attempt_transitions LIMIT 1").fetchone()
        ):
            raise ValueError("candidate initialization requires no started attempts/events")
        entries = store._round0_entries(require_exact=store.binding.round0_root is not None)
        expected = {}
        for update in updates:
            bundle = _initial_bundle(update, binding)
            expected[update.agent_id] = {
                "agent_id": update.agent_id,
                **{k: v.to_payload() for k, v in bundle.items()},
                "initial_feed_cursor": bundle["feed_cursor"].to_payload(),
            }
        observed = {entry["agent_id"]: entry for entry in entries}
        if any(
            _json_ready(entry) != _json_ready(expected.get(agent))
            for agent, entry in observed.items()
        ):
            raise ValueError("existing round-0 differs from candidate initial evidence")
        missing.append(tuple(u for u in updates if u.agent_id not in observed))
    return bindings, tuple(missing)


def initialize_candidate_family(packet, *, stores):
    """Preflight every store before filling only missing source-bound agents."""
    bindings, missing = _preflight_candidate_family(packet, stores, require_leases=True)
    for store, binding, remaining in zip(stores, bindings, missing, strict=True):
        for update in remaining:
            store.initialize_agent(**_initial_bundle(update, binding))
        if store.binding.round0_root is None:
            store.seal_initial_state()
    return _initialization_report(packet, stores, bindings)


def verify_initialized_candidate_family(packet, *, stores):
    """Read-only initial archive check; never fill missing agents or acquire leases."""
    signatures = tuple(s._connection_signature() for s in stores)
    bindings, missing = _preflight_candidate_family(packet, stores, require_leases=False)
    if any(missing) or any(s.binding.round0_root is None for s in stores):
        raise ValueError("candidate initialization is incomplete")
    report = _initialization_report(packet, stores, bindings)
    if signatures != tuple(s._connection_signature() for s in stores):
        raise RuntimeError("candidate evidence changed during read-only verification")
    return report


def _initialization_report(packet, stores, bindings):
    return ArtifactEnvelope.create(
        artifact_type="sis-candidate-initialization",
        schema_version="paper1.identity-network.initialization.v1",
        algorithm_id="sis-source-bound-round0",
        algorithm_version="1.0.0",
        input_hashes={
            "candidate": packet.output_hash,
            **{s.study_binding.cell.cell_id: s.binding.manifest_hash for s in stores},
        },
        rng_provenance=(),
        payload={
            "initialized_agents": sum(len(b.node_agent_ids) for b in bindings),
            "committed_events": 0,
            "launch_authorized": False,
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
            "formal_parameter_authority": False,
            "cells": tuple(
                {
                    "cell_id": s.study_binding.cell.cell_id,
                    "run_id": s.binding.run_id,
                    "round0_root": s.binding.round0_root,
                }
                for s in stores
            ),
        },
    )
