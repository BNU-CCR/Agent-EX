"""Crash-safe append-only storage for real calibration evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ex.calibration.store import ProbeRunStore
from agent_ex.domain import canonical_payload_hash
from test_calibration_report import complete_bundle


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


def test_attempt_records_are_create_only_and_budget_survives_reopen(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    store.append_attempt(attempt_payload())

    with pytest.raises(FileExistsError):
        store.append_attempt(attempt_payload())

    reopened = ProbeRunStore.open(tmp_path / "run")
    assert reopened.consumed_attempts("case-1") == 1


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
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    store.append_attempt(attempt_payload())
    store.seal(bundle=complete_bundle())

    assert not (store.root / "staging").exists()
    assert (store.root / "sealed" / "manifest.json").is_file()
    assert (store.root / "sealed" / "files" / "gate-report.json").is_file()
    with pytest.raises(RuntimeError, match="sealed"):
        store.append_review(review_payload())


def test_open_rejects_sealed_plus_staging_conflict(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    store.seal(bundle=complete_bundle())
    (store.root / "staging").mkdir()

    with pytest.raises(ValueError, match="sealed.*staging"):
        ProbeRunStore.open(store.root)
