"""Crash-safe append-only storage for real calibration evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ex.calibration.store import ProbeRunStore
from agent_ex.calibration.transport_diagnostics import (
    DiagnosticCase,
    TransportDiagnosticEvidence,
)
from agent_ex.domain import canonical_payload_hash
from test_calibration_report import complete_bundle
from test_calibration_smoke import valid_service_stop_evidence, valid_smoke_progress


def hashed_payload(**values: object) -> dict[str, object]:
    return {**values, "record_hash": canonical_payload_hash(values)}


def manifest_payload() -> dict[str, object]:
    return hashed_payload(
        schema_version="paper1.calibration.test-run-manifest.v1",
        run_id="run-1",
    )


def attempt_payload(*, case_id: str = "case-1", index: int = 1) -> dict[str, object]:
    return hashed_payload(
        schema_version="paper1.calibration.test-attempt.v1",
        probe_case_id=case_id,
        attempt_index=index,
        outcome="response",
    )


def review_payload(*, review_id: str = "review-1") -> dict[str, object]:
    return hashed_payload(
        schema_version="paper1.calibration.test-review.v1",
        review_id=review_id,
        label="pass",
    )


def transport_diagnostic() -> TransportDiagnosticEvidence:
    case = DiagnosticCase.closed_port(port=65431)
    return TransportDiagnosticEvidence.create(
        case=case,
        actual_error_code="provider_unreachable",
        started_at="2026-09-15T00:00:00Z",
        ended_at="2026-09-15T00:00:00Z",
        duration_seconds=0.0,
        response_headers={},
        raw_body=b"",
        raw_error="ConnectionRefusedError",
    )


def test_smoke_recovery_records_survive_reopen(tmp_path: Path) -> None:
    approved = manifest_payload()
    manifest_hash = approved["record_hash"]
    assert isinstance(manifest_hash, str)
    store = ProbeRunStore.create(tmp_path / "smoke", manifest=approved)
    progress = valid_smoke_progress(manifest_hash=manifest_hash)
    diagnostic = transport_diagnostic()
    stop = valid_service_stop_evidence(manifest_hash=manifest_hash)

    store.append_smoke_progress(progress.to_payload())
    store.append_transport_diagnostic(diagnostic.to_payload())
    store.append_service_stop(stop.to_payload())
    del store

    reopened = ProbeRunStore.open(tmp_path / "smoke")
    assert reopened.load_smoke_progress() == (progress,)
    assert reopened.load_transport_diagnostics() == (diagnostic,)
    assert reopened.load_service_stops() == (stop,)
    assert reopened.attempt_hashes == ()


def test_smoke_progress_is_create_only_contiguous_and_hash_chained(
    tmp_path: Path,
) -> None:
    approved = manifest_payload()
    manifest_hash = approved["record_hash"]
    assert isinstance(manifest_hash, str)
    store = ProbeRunStore.create(tmp_path / "smoke", manifest=approved)
    ready = valid_smoke_progress(manifest_hash=manifest_hash)
    store.append_smoke_progress(ready.to_payload())

    with pytest.raises(FileExistsError):
        store.append_smoke_progress(ready.to_payload())
    with pytest.raises(ValueError, match="sequence"):
        store.append_smoke_progress(
            valid_smoke_progress(
                sequence=3,
                phase="phase_one_complete",
                completed_ordinals=tuple(range(1, 10)),
                manifest_hash=manifest_hash,
            ).to_payload()
        )
    with pytest.raises(ValueError, match="previous"):
        store.append_smoke_progress(
            valid_smoke_progress(
                sequence=2,
                phase="diagnostics_complete",
                manifest_hash=manifest_hash,
                previous_progress_hash="f" * 64,
            ).to_payload()
        )


def test_smoke_recovery_records_reject_duplicate_identity_or_wrong_manifest(
    tmp_path: Path,
) -> None:
    approved = manifest_payload()
    manifest_hash = approved["record_hash"]
    assert isinstance(manifest_hash, str)
    store = ProbeRunStore.create(tmp_path / "smoke", manifest=approved)
    diagnostic = transport_diagnostic()
    stop = valid_service_stop_evidence(manifest_hash=manifest_hash)

    store.append_transport_diagnostic(diagnostic.to_payload())
    with pytest.raises((FileExistsError, ValueError)):
        store.append_transport_diagnostic(diagnostic.to_payload())
    store.append_service_stop(stop.to_payload())
    with pytest.raises((FileExistsError, ValueError)):
        store.append_service_stop(stop.to_payload())
    with pytest.raises(ValueError, match="manifest"):
        store.append_smoke_progress(valid_smoke_progress(manifest_hash="f" * 64).to_payload())


def test_attempt_records_are_create_only_and_budget_survives_reopen(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    store.append_attempt(attempt_payload())

    with pytest.raises(FileExistsError):
        store.append_attempt(attempt_payload())

    reopened = ProbeRunStore.open(tmp_path / "run")
    assert reopened.consumed_attempts("case-1") == 1
    assert reopened.load_attempt_records() == (attempt_payload(),)


def test_reviews_are_content_addressed_and_reopenable(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    review = review_payload()
    store.append_review(review)

    reopened = ProbeRunStore.open(tmp_path / "run")
    assert reopened.review_hashes == (review["record_hash"],)


def test_open_rejects_hash_drift(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    attempt = attempt_payload()
    store.append_attempt(attempt)
    path = store.root / "staging" / "attempts" / f"{attempt['record_hash']}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["outcome"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="hash drift"):
        ProbeRunStore.open(store.root)


def test_open_rejects_projection_claiming_a_missing_record(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    attempt = attempt_payload()
    store.append_attempt(attempt)
    path = store.root / "staging" / "attempts" / f"{attempt['record_hash']}.json"
    path.unlink()

    with pytest.raises(ValueError, match="projection.*missing"):
        ProbeRunStore.open(store.root)


def test_attempt_indices_cannot_have_gaps_or_duplicate_case_positions(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    with pytest.raises(ValueError, match="contiguous"):
        store.append_attempt(attempt_payload(index=2))

    store.append_attempt(attempt_payload(index=1))
    with pytest.raises(ValueError, match="duplicate"):
        store.append_attempt(
            hashed_payload(
                schema_version="paper1.calibration.test-attempt.v1",
                probe_case_id="case-1",
                attempt_index=1,
                outcome="provider_error",
            )
        )


def test_sealed_store_rejects_all_new_records(tmp_path: Path) -> None:
    approved = manifest_payload()
    manifest_hash = approved["record_hash"]
    assert isinstance(manifest_hash, str)
    store = ProbeRunStore.create(tmp_path / "run", manifest=approved)
    store.append_attempt(attempt_payload())
    progress = valid_smoke_progress(manifest_hash=manifest_hash)
    diagnostic = transport_diagnostic()
    stop = valid_service_stop_evidence(manifest_hash=manifest_hash)
    store.append_smoke_progress(progress.to_payload())
    store.append_transport_diagnostic(diagnostic.to_payload())
    store.append_service_stop(stop.to_payload())
    attempt_hashes = store.attempt_hashes
    store.seal(bundle=complete_bundle())

    assert not (store.root / "staging").exists()
    assert (store.root / "sealed" / "manifest.json").is_file()
    assert (store.root / "sealed" / "files" / "gate-report.json").is_file()
    assert (store.root / "sealed" / "evidence" / "manifest.json").is_file()
    assert (store.root / "sealed" / "evidence" / "projection.json").is_file()
    assert len(list((store.root / "sealed" / "evidence" / "attempts").glob("*.json"))) == 1
    reopened = ProbeRunStore.open(store.root)
    assert reopened.attempt_hashes == attempt_hashes
    assert reopened.load_smoke_progress() == (progress,)
    assert reopened.load_transport_diagnostics() == (diagnostic,)
    assert reopened.load_service_stops() == (stop,)
    with pytest.raises(RuntimeError, match="sealed"):
        store.append_review(review_payload())


def test_open_rejects_tampered_sealed_append_only_evidence(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    store.append_attempt(attempt_payload())
    digest = store.attempt_hashes[0]
    store.seal(bundle=complete_bundle())
    evidence = store.root / "sealed" / "evidence" / "attempts" / f"{digest}.json"
    evidence.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="record_hash"):
        ProbeRunStore.open(store.root)


def test_open_rejects_sealed_plus_staging_conflict(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    store.seal(bundle=complete_bundle())
    (store.root / "staging").mkdir()

    with pytest.raises(ValueError, match="sealed.*staging"):
        ProbeRunStore.open(store.root)
