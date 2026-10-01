"""Complete SIS orchestration using local fake HTTP only."""

import json

import pytest

from agent_ex.identity_network import runner
from agent_ex.identity_network.contracts import study_cells
from agent_ex.identity_network.dispatch import StudyDispatchJournal
from agent_ex.phase0b.vllm_event_adapter import Phase0BVllmEventAdapter
from test_identity_network_prefix import prefix_store
from test_phase0b_vllm_event_adapter import FakeConnection


def family(tmp_path, *, sweeps=2):
    entries = []
    journals = []
    for cell in study_cells():
        root = tmp_path / cell.cell_id
        root.mkdir()
        entry = prefix_store(root, cell, sweeps=sweeps)
        entries.append(entry)
        journals.append(StudyDispatchJournal(root / "dispatch.jsonl", storage=entry[0]))
    return tuple(entries), tuple(journals)


def adapter_factory(calls, *, bad_request=None, crash_request=None):
    class LocalConnection(FakeConnection):
        requests = []

        def request(self, *args, **kwargs):
            super().request(*args, **kwargs)
            calls.append(kwargs["headers"]["X-Request-Id"])
            if len(calls) == crash_request:
                raise RuntimeError("injected after dispatch")

        def getresponse(self):
            content = (
                "not JSON"
                if len(calls) == bad_request
                else json.dumps(
                    {"stance": "label-5", "confidence": 3, "public_reason": "Synthetic test only."}
                )
            )
            self.body = json.dumps(
                {
                    "model": "qwen3-8b-paper1",
                    "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
                }
            ).encode()
            return super().getresponse()

    return lambda: Phase0BVllmEventAdapter(
        "http://127.0.0.1:8000/v1/chat/completions",
        served_model_name="qwen3-8b-paper1",
        connection_factory=LocalConnection,
    )


def run(entries, journals, calls, *, stop=40, **kwargs):
    return runner.run_study_cells_prefix(
        stores=tuple(e[0] for e in entries),
        journals=journals,
        stop_ordinal=stop,
        adapter_factory=adapter_factory(calls, **kwargs),
        clock=lambda: "2026-10-01T00:00:00Z",
    )


def close(entries):
    for e in entries:
        e[0].close()


def test_complete_six_cells_240_events_and_readonly_cold_verification(tmp_path, capsys):
    entries, journals = family(tmp_path)
    calls = []
    reopened = []
    try:
        report = run(entries, journals, calls)
        assert len(calls) == len(set(calls)) == 240
        assert report.payload["complete"] is True
        assert report.payload["committed_events"] == 240
        assert report.payload["expected_events"] == 240
        assert report.payload["formal_parameter_authority"] is False
        assert report.payload["transport_provenance"] == "unattested"
        assert [c["cell_id"] for c in report.payload["cells"]] == [c.cell_id for c in study_cells()]
        assert all(c["committed_events"] == 40 for c in report.payload["cells"])
        assert all(
            c["intent_count"] == c["resolution_count"] == 40 for c in report.payload["cells"]
        )
        for original, journal in zip(entries, journals, strict=True):
            store, cls, binding, manifest, path, _, _ = original
            store.close()
            restored = cls.open(path, manifest=manifest, **binding.storage_arguments())
            reopened.append(restored)
        cold_journals = tuple(
            StudyDispatchJournal(j.path, storage=s) for j, s in zip(journals, reopened, strict=True)
        )
        before = tuple(j.path.read_bytes() for j in cold_journals)
        cold = runner.verify_study_cells(
            stores=tuple(reopened), journals=cold_journals, require_complete=True
        )
        assert cold == report
        assert tuple(j.path.read_bytes() for j in cold_journals) == before
        assert "Synthetic test only." not in json.dumps(cold.to_payload())
        index = tmp_path / "index.json"
        index.write_text(json.dumps(archive_index(entries, journals, tmp_path)), encoding="utf-8")
        assert runner.main(["verify", "--index", str(index)]) == 0
        assert json.loads(capsys.readouterr().out) == cold.to_payload()
    finally:
        close(entries)
        for s in reopened:
            s.close()


def test_bounded_prefix_then_same_identity_continuation_never_resends(tmp_path):
    entries, journals = family(tmp_path)
    calls = []
    try:
        report = run(entries, journals, calls, stop=2)
        assert len(calls) == 12
        assert report.payload["complete"] is False
        assert run(entries, journals, calls, stop=2) == report
        assert len(calls) == 12
        later = run(entries, journals, calls, stop=3)
        assert len(calls) == len(set(calls)) == 18
        assert later.payload["committed_events"] == 18
        with pytest.raises(ValueError, match="complete"):
            runner.verify_study_cells(
                stores=tuple(e[0] for e in entries), journals=journals, require_complete=True
            )
    finally:
        close(entries)


def test_failure_stops_all_cells_and_does_not_advance_failed_receiver(tmp_path):
    entries, journals = family(tmp_path)
    calls = []
    try:
        report = run(entries, journals, calls, bad_request=3)
        assert len(calls) == 3
        assert report.payload["committed_events"] == 2
        assert report.payload["complete"] is False
        assert report.payload["cells"][0]["status"] == "failed"
        assert entries[0][0].progress.next_event_ordinal == 2
        assert all(e[0].progress.next_event_ordinal == 0 for e in entries[1:])
        assert run(entries, journals, calls) == report
        assert len(calls) == 3
    finally:
        close(entries)


def test_ambiguous_dispatch_stops_before_any_resend_or_other_cell(tmp_path):
    entries, journals = family(tmp_path)
    calls = []
    try:
        with pytest.raises(RuntimeError, match="injected"):
            run(entries, journals, calls, crash_request=2)
        assert len(calls) == 2
        assert entries[0][0].progress.next_event_ordinal == 1
        with pytest.raises(RuntimeError, match="unresolved"):
            run(entries, journals, calls)
        assert len(calls) == 2
        assert all(e[0].progress.next_event_ordinal == 0 for e in entries[1:])
    finally:
        close(entries)


@pytest.mark.parametrize(
    "change",
    ["missing", "duplicate", "wrong_journal", "bool_limit", "past_end", "shared_journal_path"],
)
def test_family_or_budget_drift_rejected_before_dispatch(tmp_path, change):
    entries, journals = family(tmp_path)
    calls = []
    originals = entries
    stop = 2
    if change == "missing":
        entries, journals = entries[:-1], journals[:-1]
    elif change == "duplicate":
        entries = entries[:-1] + (entries[0],)
    elif change == "wrong_journal":
        journals = journals[:-1] + (journals[0],)
    elif change == "shared_journal_path":
        journals = journals[:-1] + (StudyDispatchJournal(journals[0].path, storage=entries[-1][0]),)
    elif change == "bool_limit":
        stop = True
    else:
        stop = 41
    try:
        with pytest.raises((ValueError, TypeError)):
            run(entries, journals, calls, stop=stop)
        assert calls == []
        assert all(e[0].progress.next_event_ordinal == 0 for e in originals)
    finally:
        close(originals)


def test_late_cell_missing_authorization_is_rejected_before_any_send(tmp_path):
    entries, journals = family(tmp_path)
    root = tmp_path / "without-authorization"
    root.mkdir()
    bad = prefix_store(root, study_cells()[-1], sweeps=2, include_authorization=False)
    bad_journal = StudyDispatchJournal(root / "dispatch.jsonl", storage=bad[0])
    calls = []
    try:
        with pytest.raises((ValueError, TypeError), match="authorization"):
            run(entries[:-1] + (bad,), journals[:-1] + (bad_journal,), calls, stop=1)
        assert calls == []
        assert all(e[0].progress.next_event_ordinal == 0 for e in entries)
    finally:
        close(entries)
        bad[0].close()


def test_late_cell_saved_failed_response_prevents_all_new_sends(tmp_path):
    from test_identity_network_response import response_for

    entries, journals = family(tmp_path)
    store, _, _, _, _, stored, kwargs = entries[-1]
    calls = []
    try:
        store.record_diagnostic_prepared_attempt(stored, **kwargs)
        store.start_diagnostic_attempt(kwargs["pending_attempt"], started_at="2026-10-01T00:00:00Z")
        invocation, _ = response_for(stored, kwargs, content="not JSON")
        journals[-1].record_before_dispatch(
            kwargs["request_evidence"].request, invocation.response.transport_evidence.request_body
        )
        store.record_diagnostic_invocation_evidence(invocation)
        report = run(entries, journals, calls, stop=1)
        assert calls == []
        assert report.payload["committed_events"] == 0
        assert report.payload["cells"][-1]["status"] == "failed"
    finally:
        close(entries)


def archive_index(entries, journals, root):
    return {
        "schema_version": "paper1.identity-network.archive-index.v1",
        "cells": [
            {
                "manifest": e[3].to_payload(),
                "database": e[4].relative_to(root).as_posix(),
                "dispatch_journal": j.path.relative_to(root).as_posix(),
            }
            for e, j in zip(entries, journals, strict=True)
        ],
    }


def test_cli_report_partial_archive_without_writes_and_verify_rejects_partial(tmp_path, capsys):
    entries, journals = family(tmp_path)
    index = tmp_path / "index.json"
    index.write_text(json.dumps(archive_index(entries, journals, tmp_path)), encoding="utf-8")
    try:
        before = tuple(e[4].read_bytes() for e in entries)
        assert runner.main(["report", "--index", str(index)]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["payload"]["committed_events"] == 0
        assert report["payload"]["complete"] is False
        assert report["payload"]["transport_provenance"] == "unattested"
        assert tuple(e[4].read_bytes() for e in entries) == before
        assert not any(j.path.exists() for j in journals)
        assert runner.main(["verify", "--index", str(index)]) == 2
        assert capsys.readouterr().out == ""
    finally:
        close(entries)


@pytest.mark.parametrize("change", ["outside", "absolute", "wrong_schema", "extra_field"])
def test_cli_rejects_bad_index_without_output_or_creating_files(tmp_path, capsys, change):
    entries, journals = family(tmp_path)
    payload = archive_index(entries, journals, tmp_path)
    if change == "outside":
        payload["cells"][-1]["database"] = "../missing.sqlite"
    elif change == "absolute":
        payload["cells"][-1]["database"] = str(entries[-1][4])
    elif change == "wrong_schema":
        payload["schema_version"] = "legacy"
    else:
        payload["cells"][-1]["trust_me"] = True
    index = tmp_path / "index.json"
    index.write_text(json.dumps(payload), encoding="utf-8")
    try:
        assert runner.main(["report", "--index", str(index)]) == 2
        assert capsys.readouterr().out == ""
        assert not (tmp_path.parent / "missing.sqlite").exists()
        assert not any(j.path.exists() for j in journals)
    finally:
        close(entries)


def test_readonly_report_rejects_database_change_mid_snapshot(tmp_path, monkeypatch):
    entries, journals = family(tmp_path)
    store = entries[0][0]
    original = store.private_state
    changed = []

    def during_read(agent):
        value = original(agent)
        if not changed:
            store._connection.execute("UPDATE progress SET event_chain_head=event_chain_head")
            changed.append(True)
        return value

    monkeypatch.setattr(store, "private_state", during_read)
    try:
        with pytest.raises(RuntimeError, match="changed"):
            runner.verify_study_cells(
                stores=tuple(e[0] for e in entries), journals=journals, require_complete=False
            )
    finally:
        close(entries)


def test_report_does_not_reread_baseline_hashes_after_collecting_all_cells(tmp_path, monkeypatch):
    entries, journals = family(tmp_path)
    reads = []
    late_reads = []
    for entry in entries:
        store = entry[0]
        original = store.private_state

        def counted(agent, original=original):
            reads.append(agent)
            return original(agent)

        monkeypatch.setattr(store, "private_state", counted)
    first = entries[0][0]
    original_state = first.execution_state

    def counted_state():
        if len(reads) >= 120:
            late_reads.append(True)
        return original_state()

    monkeypatch.setattr(first, "execution_state", counted_state)
    try:
        runner.verify_study_cells(
            stores=tuple(e[0] for e in entries), journals=journals, require_complete=False
        )
        assert late_reads == []
    finally:
        close(entries)
