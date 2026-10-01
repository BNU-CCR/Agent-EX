"""Bounded SIS execution primitives; not a real-run launch authorization."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path, PureWindowsPath
import sqlite3
import sys

from ..artifacts import ArtifactEnvelope
from ..domain import (
    EventStatus,
    GenerationAttempt,
    RunManifest,
    _json_ready,
    _require_sha256,
    canonical_payload_hash,
)
from ..execution_evidence import (
    DiagnosticAdapterRequestEvidence,
    DiagnosticPersistedInvocationEvidence,
)
from ..phase0b.contracts import DiagnosticAdapterBinding, DiagnosticAttemptPolicy
from ..phase0b.vllm_event_adapter import Phase0BVllmEventAdapter
from .contracts import STUDY_ID, study_cells
from .dispatch import StudyDispatchJournal, _strict_json, reconcile_study_event
from .evidence import StudyEventInputEvidence
from .storage import StudyRunBinding, StudyRunStorage
from .stored_input import StoredStudyInput


def _validate_family(stores, journals):
    if (
        type(stores) is not tuple
        or type(journals) is not tuple
        or len(stores) != 6
        or len(journals) != 6
    ):
        raise ValueError("exactly six SIS stores and journals required")
    if any(not isinstance(s, StudyRunStorage) for s in stores):
        raise TypeError("six SIS stores required")
    if tuple(s.study_binding.cell for s in stores) != study_cells():
        raise ValueError("six canonical SIS cells in canonical order required")
    if len({s.binding.run_id for s in stores}) != 6:
        raise ValueError("six independent run identities required")
    if len({s._database_identity for s in stores}) != 6:
        raise ValueError("six independent SQLite files required")
    if (
        any(not isinstance(j, StudyDispatchJournal) for j in journals)
        or len({j.path.resolve() for j in journals}) != 6
    ):
        raise ValueError("six independent SIS journal paths required")
    first = stores[0]
    for store, journal in zip(stores, journals, strict=True):
        if not isinstance(journal, StudyDispatchJournal) or journal.storage is not store:
            raise ValueError("journal/store family binding mismatch")
        store.verify_integrity()
        _require_sha256(
            "SIS authorization reference",
            store._sis_run_spec.get("sis_diagnostic_authorization_hash"),
        )
        common = store._stored_common_inputs
        if (
            common is None
            or common != first._stored_common_inputs
            or store.study_binding.common_inputs_hash != common.output_hash
            or store.study_binding.matched_seed != first.study_binding.matched_seed
            or store.binding.round0_root is None
        ):
            raise ValueError("SIS cells must share complete matched execution inputs")
        # Validate actual sealed initialization in *every* cell before first send.
        actual = {
            e["agent_id"]: e["private_update"] for e in store._round0_entries(require_exact=True)
        }
        expected = {u["agent_id"]: _json_ready(u) for u in common.payload["initial_updates"]}
        if actual != expected:
            raise ValueError("SIS common round-0 differs from actual cell initialization")
        records = journal._records()
        journal._assert_historical_cover(records)


def _prepare_pending(store):
    common = store._stored_common_inputs
    values = common.payload
    slot = store.schedule_slot(store.progress.next_event_ordinal)
    snapshot = store.snapshot_next_input(
        persona_text=values["persona_by_agent"][slot.agent_id],
        feed_capacity=values["feed_capacity"],
        memory_window=values["memory_window"],
    )
    prepared = store.prepare_bound_snapshot_event(snapshot, common, attempt_index=1)
    stored = StoredStudyInput(StudyEventInputEvidence.from_prepared(prepared), snapshot)
    policy = DiagnosticAttemptPolicy.from_payload(_json_ready(values["attempt_policy"]))
    adapter = DiagnosticAdapterBinding.from_payload(_json_ready(values["adapter_binding"]))
    evidence = DiagnosticAdapterRequestEvidence.create(
        request=prepared.request,
        run_authorization_hash=store._sis_run_spec["sis_diagnostic_authorization_hash"],
        parser_limits_hash=prepared.parser_limits.record_hash,
        attempt_policy_hash=policy.record_hash,
        adapter_binding=adapter,
    )
    r = prepared.request
    pending = GenerationAttempt(
        attempt_id=r.attempt_id,
        event_id=r.event_id,
        attempt_index=r.attempt_index,
        status=EventStatus.PENDING,
        request_id=r.request_id,
        exposure_id=stored.exposure_id,
        rendered_messages=r.rendered_messages,
        rendered_prompt_hash=r.rendered_messages_hash,
        request_parameters=r.generation_settings,
        request_parameters_hash=r.generation_settings_hash,
        model_identity=evidence.model_identity,
        model_identity_hash=evidence.model_identity_hash,
        model_seed=r.model_seed,
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
    store.record_diagnostic_prepared_attempt(
        stored,
        policy=policy,
        adapter_binding=adapter,
        request_evidence=evidence,
        pending_attempt=pending,
    )
    return pending


def run_study_cells_prefix(*, stores, journals, stop_ordinal, adapter_factory, clock):
    """Run a caller-bound six-cell prefix, stopping at first failure/ambiguity.

    This low-level primitive is not a standalone cloud launcher. A real launch
    must independently bind/approve SIS inputs, source and service ownership;
    the candidate authorization hash here is not a human approval receipt.
    No retry authorization is invented. The explicit stop ordinal is absolute,
    so repeating a finished prefix never increases its request budget.
    """
    _validate_family(stores, journals)
    if type(stop_ordinal) is not int or stop_ordinal < 0:
        raise ValueError("stop ordinal must be a nonnegative strict integer")
    if not callable(adapter_factory) or not callable(clock):
        raise TypeError("explicit adapter factory and clock required")
    for store in stores:
        store.assert_run_lease_owned()
        if (
            not store.progress.next_event_ordinal
            <= stop_ordinal
            <= store.progress.expected_event_count
        ):
            raise ValueError("stop ordinal must fit all current SIS prefixes")
    # Inspect *all* cells before sending into any cell. Do not let later
    # ambiguous dispatches or failures be hidden by an earlier healthy cell.
    for store, journal in zip(stores, journals, strict=True):
        latest = store.current_event_journal().latest_transition
        unresolved = journal.unresolved_request_ids()
        if unresolved and (
            latest is None
            or tuple(unresolved) != (latest.request_id,)
            or store.invocation_evidence(latest.attempt_id) is None
        ):
            raise RuntimeError("unresolved SIS dispatch prevents any further send")
        if latest is not None and latest.status is EventStatus.FAILED:
            return verify_study_cells(stores=stores, journals=journals, require_complete=False)
        if latest is not None and latest.status is EventStatus.IN_PROGRESS:
            invocation = store.invocation_evidence(latest.attempt_id)
            if invocation is None:
                raise RuntimeError("unresolved IN_PROGRESS SIS request; do not resend")
            if not store._validate_study_invocation(invocation).parse.success:
                reconcile_study_event(storage=store, journal=journal)
                return verify_study_cells(stores=stores, journals=journals, require_complete=False)
    for store, journal in zip(stores, journals, strict=True):
        while store.progress.next_event_ordinal < stop_ordinal:
            state = reconcile_study_event(storage=store, journal=journal)
            if state == "failed":
                return verify_study_cells(stores=stores, journals=journals, require_complete=False)
            if state == "committed":
                continue
            if state == "complete":
                break
            pending = (
                _prepare_pending(store)
                if state == "new_event"
                else store.current_event_journal().latest_transition
            )
            evidence = store.adapter_request_evidence(pending.attempt_id)
            policy = store.attempt_policy_evidence(pending.event_id)
            binding = store.adapter_execution_binding(pending.attempt_id)
            adapter = adapter_factory()
            if (
                not isinstance(adapter, Phase0BVllmEventAdapter)
                or adapter.endpoint != binding.endpoint
                or adapter._served_model_name != binding.served_model_name
            ):
                raise ValueError("adapter must match exact bound SIS service")
            adapter.bind_dispatch_journal(journal.record_before_dispatch)
            store.start_diagnostic_attempt(pending, started_at=clock())
            response = adapter.generate(
                evidence.request,
                timeout_seconds=policy.total_timeout_seconds,
                connect_timeout_seconds=policy.connect_timeout_seconds,
                read_timeout_seconds=policy.read_timeout_seconds,
            )
            invocation = DiagnosticPersistedInvocationEvidence.create(
                response=response,
                request_evidence=evidence,
            )
            store.record_diagnostic_invocation_evidence(invocation)
            if reconcile_study_event(storage=store, journal=journal) == "failed":
                return verify_study_cells(stores=stores, journals=journals, require_complete=False)
    return verify_study_cells(stores=stores, journals=journals, require_complete=False)


def verify_study_cells(*, stores, journals, require_complete):
    """Read-only descriptive evidence report. Never resolves or sends a request.

    Transport remains unattested: durable hashes alone do not prove real model
    inference. This is not a frozen scientific result or sycophancy classifier.
    """
    if type(require_complete) is not bool:
        raise TypeError("require_complete must be a strict boolean")
    _validate_family(stores, journals)
    snapshots = tuple(
        (s._connection_signature(), j._stat_signature())
        for s, j in zip(stores, journals, strict=True)
    )
    cells = []
    for store, journal in zip(stores, journals, strict=True):
        progress = store.progress
        records = journal._records()
        unresolved = journal.unresolved_request_ids()
        latest = store.current_event_journal().latest_transition
        status = (
            "complete"
            if progress.next_event_ordinal == progress.expected_event_count
            else "failed"
            if latest is not None and latest.status is EventStatus.FAILED
            else "partial"
        )
        if status == "complete" and (
            unresolved
            or len(records["intents"]) != progress.expected_event_count
            or len(records["resolutions"]) != progress.expected_event_count
        ):
            raise ValueError("complete SIS run lacks exact dispatch/response cover")
        histogram = {label: 0 for label in store.study_binding.topic_package.stance_labels}
        for agent in store.study_binding.node_agent_ids:
            histogram[store.private_state(agent).stance_label] += 1
        cells.append(
            {
                "cell_id": store.study_binding.cell.cell_id,
                "run_id": store.binding.run_id,
                "status": status,
                "committed_events": progress.next_event_ordinal,
                "expected_events": progress.expected_event_count,
                "intent_count": len(records["intents"]),
                "resolution_count": len(records["resolutions"]),
                "unresolved_dispatches": len(unresolved),
                "event_chain_head": progress.event_chain_head,
                "round0_root": store.binding.round0_root,
                "journal_chain_head": journal._tail,
                "baseline_manifest_hash": store.execution_state().baseline_manifest_hash,
                "private_stance_histogram": histogram,
            }
        )
    complete = all(c["status"] == "complete" for c in cells)
    if require_complete and not complete:
        raise ValueError("SIS family is not complete")
    if snapshots != tuple(
        (s._connection_signature(), j._stat_signature())
        for s, j in zip(stores, journals, strict=True)
    ):
        raise RuntimeError(
            "SIS evidence changed during read-only report; retry from a stable archive"
        )
    payload = {
        "study_id": STUDY_ID,
        "matched_seed": stores[0].study_binding.matched_seed,
        "common_inputs_hash": stores[0].study_binding.common_inputs_hash,
        "status": "preliminary",
        "research_parameter_status": "not_frozen",
        "formal_parameter_authority": False,
        "transport_provenance": "unattested",
        "complete": complete,
        "committed_events": sum(c["committed_events"] for c in cells),
        "expected_events": sum(c["expected_events"] for c in cells),
        "cells": cells,
    }
    return ArtifactEnvelope.create(
        artifact_type="sis-execution-report",
        schema_version="paper1.identity-network.execution-report.v1",
        algorithm_id="sis-readonly-evidence-report",
        algorithm_version="1.0.0",
        input_hashes={c["cell_id"]: c["baseline_manifest_hash"] for c in cells},
        rng_provenance=(),
        payload=payload,
    )


def _archive_path(root, value, *, database):
    if type(value) is not str or not value:
        raise ValueError("archive paths must be explicit relative strings")
    relative = Path(value)
    windows = PureWindowsPath(value)
    if relative.is_absolute() or windows.drive or windows.root or ".." in relative.parts:
        raise ValueError("archive path must remain inside the index directory")
    candidate = root / relative
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("archive path escapes the index directory")
    check = candidate
    while check != root:
        if check.is_symlink():
            raise ValueError("archive paths must not traverse symlinks")
        check = check.parent
    if database and not candidate.is_file():
        raise ValueError("archive database must already exist")
    if candidate.exists() and not candidate.is_file():
        raise ValueError("archive evidence path must be a file")
    return candidate


def main(argv=None):
    """Standalone *read-only* archive verification/report; no run command."""
    parser = argparse.ArgumentParser(
        description="Read-only SIS evidence verification (transport unattested)"
    )
    parser.add_argument("command", choices=("verify", "report"))
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.index.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("archive index exceeds reader bound")
        index = _strict_json(args.index.read_text(encoding="utf-8"))
        if (
            type(index) is not dict
            or set(index) != {"schema_version", "cells"}
            or index["schema_version"] != "paper1.identity-network.archive-index.v1"
            or type(index["cells"]) is not list
            or len(index["cells"]) != 6
        ):
            raise ValueError("explicit six-cell SIS archive index required")
        specs = []
        for entry in index["cells"]:
            if type(entry) is not dict or set(entry) != {
                "manifest",
                "database",
                "dispatch_journal",
            }:
                raise ValueError("archive index cell fields differ from schema")
            binding = StudyRunBinding.from_payload(
                entry["manifest"]["run_spec"]["identity_network_binding"]
            )
            manifest = RunManifest.from_payload(entry["manifest"], schedule=binding.schedule)
            database = _archive_path(args.index.parent, entry["database"], database=True)
            journal = _archive_path(args.index.parent, entry["dispatch_journal"], database=False)
            specs.append((manifest, binding, database, journal))
        with ExitStack() as stack:
            stores, journals = [], []
            for manifest, binding, path, journal_path in specs:
                store = StudyRunStorage.open(path, manifest=manifest, **binding.storage_arguments())
                stack.callback(store.close)
                stores.append(store)
                journals.append(StudyDispatchJournal(journal_path, storage=store))
            report = verify_study_cells(
                stores=tuple(stores),
                journals=tuple(journals),
                require_complete=args.command == "verify",
            )
        print(json.dumps(report.to_payload(), sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, sqlite3.Error) as error:
        # Never emit an input payload/response/traceback on a failed verification.
        print(
            f"SIS verification failed ({type(error).__name__}); no report emitted.", file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
