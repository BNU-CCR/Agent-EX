"""Create-only filesystem store for blinded judge execution evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from ..domain import canonical_payload_hash
from .judge_contracts import JudgeExecutionManifest
from .judge_runner import (
    JudgeDispatchIntent,
    JudgeDispatchReconciliation,
    JudgeIncompleteAttemptMarker,
    JudgeProjection,
    JudgeProviderAuditRecord,
    replay_judge_records,
)


LAYOUT = (
    "attempts",
    "dispatch",
    "reconciliation",
    "raw",
    "service/preflight",
    "service/start",
    "service/stop",
)
_EXTRA_LAYOUT = ("journal", "projections")
_KIND_TYPES = {
    "dispatch": JudgeDispatchIntent,
    "reconciliation": JudgeDispatchReconciliation,
    "raw": JudgeProviderAuditRecord,
    "attempts": JudgeIncompleteAttemptMarker,
}


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _write_json_create_only(path: Path, payload: Mapping[str, object]) -> None:
    content = _canonical_json_bytes(payload)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        written = os.write(descriptor, content)
        if written != len(content):
            raise OSError("short write while appending judge evidence")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid judge evidence JSON: {path.name}") from error
    if type(payload) is not dict:
        raise ValueError("judge evidence file must contain a JSON object")
    return payload


class JudgeRunStore:
    """A create-only evidence archive whose projections are always replay-derived."""

    def __init__(self, root: Path, manifest: JudgeExecutionManifest) -> None:
        self.root = root
        self.manifest = manifest

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @classmethod
    def create(cls, root: Path, manifest: JudgeExecutionManifest) -> JudgeRunStore:
        if not isinstance(root, Path):
            raise TypeError("judge store root must be a Path")
        if not isinstance(manifest, JudgeExecutionManifest):
            raise TypeError("judge store requires a JudgeExecutionManifest")
        JudgeExecutionManifest.from_payload(manifest.to_payload())
        root.mkdir(parents=False, exist_ok=False)
        staging = root / "staging"
        staging.mkdir()
        for relative in (*LAYOUT, *_EXTRA_LAYOUT):
            (staging / relative).mkdir(parents=True, exist_ok=False)
        _write_json_create_only(staging / "manifest.json", manifest.to_payload())
        initial = replay_judge_records(manifest.record_hash, ())[-1]
        cls._write_projection(staging, initial)
        return cls.open(root)

    @classmethod
    def open(cls, root: Path) -> JudgeRunStore:
        if not isinstance(root, Path) or not root.is_dir() or root.is_symlink():
            raise ValueError("judge store root must be an existing non-link directory")
        staging = root / "staging"
        expected_top = {
            "manifest.json",
            "attempts",
            "dispatch",
            "reconciliation",
            "raw",
            "service",
            "journal",
            "projections",
        }
        if (
            not staging.is_dir()
            or staging.is_symlink()
            or {p.name for p in staging.iterdir()} != expected_top
        ):
            raise ValueError("judge store staging inventory is not exact")
        if {p.name for p in (staging / "service").iterdir()} != {"preflight", "start", "stop"}:
            raise ValueError("judge service evidence inventory is not exact")
        manifest = JudgeExecutionManifest.from_payload(_load_json(staging / "manifest.json"))
        store = cls(root, manifest)
        records = store.read_records()
        expected = replay_judge_records(manifest.record_hash, records)
        actual = store._read_projections()
        if len(actual) != len(expected):
            raise ValueError("judge projection hash chain is not contiguous")
        for sequence, (observed, derived) in enumerate(zip(actual, expected, strict=True)):
            if observed.sequence != sequence or observed.to_payload() != derived.to_payload():
                raise ValueError("judge projection hash chain differs from exact replay")
        return store

    @staticmethod
    def _write_projection(staging: Path, projection: JudgeProjection) -> None:
        filename = f"{projection.sequence:012d}-{projection.record_hash}.json"
        _write_json_create_only(staging / "projections" / filename, projection.to_payload())

    def _read_projections(self) -> tuple[JudgeProjection, ...]:
        paths = sorted((self.staging / "projections").iterdir())
        projections: list[JudgeProjection] = []
        for expected_sequence, path in enumerate(paths):
            if path.is_symlink() or not path.is_file():
                raise ValueError("judge projection inventory contains a non-file")
            prefix = f"{expected_sequence:012d}-"
            if not path.name.startswith(prefix) or not path.name.endswith(".json"):
                raise ValueError("judge projection hash chain filenames are not contiguous")
            projection = JudgeProjection.from_payload(_load_json(path))
            if path.name != f"{projection.sequence:012d}-{projection.record_hash}.json":
                raise ValueError("judge projection filename differs from record identity")
            if expected_sequence == 0:
                if projection.previous_projection_hash is not None:
                    raise ValueError("initial judge projection must not have a predecessor")
            elif projection.previous_projection_hash != projections[-1].record_hash:
                raise ValueError("judge projection hash chain predecessor differs")
            projections.append(projection)
        return tuple(projections)

    @property
    def current_projection(self) -> JudgeProjection:
        projections = self._read_projections()
        if not projections:
            raise ValueError("judge store has no projection snapshot")
        return projections[-1]

    def _require_exact_projection_replay(self, records: tuple[object, ...]) -> None:
        expected = replay_judge_records(self.manifest.record_hash, records)
        actual = self._read_projections()
        if len(actual) != len(expected) or any(
            observed.to_payload() != derived.to_payload()
            for observed, derived in zip(actual, expected, strict=False)
        ):
            raise ValueError("judge projection hash chain differs from exact replay")

    def read_records(self) -> tuple[object, ...]:
        journal = self.staging / "journal"
        paths = sorted(journal.iterdir())
        records: list[object] = []
        referenced: dict[str, set[str]] = {kind: set() for kind in _KIND_TYPES}
        for expected_sequence, path in enumerate(paths, 1):
            if path.is_symlink() or not path.is_file():
                raise ValueError("judge journal contains a non-file")
            payload = _load_json(path)
            expected_fields = {
                "schema_version",
                "sequence",
                "kind",
                "record_hash",
                "manifest_hash",
                "journal_hash",
            }
            if (
                set(payload) != expected_fields
                or payload["schema_version"] != "paper1.calibration.judge-journal-entry.v1"
            ):
                raise ValueError("judge journal entry requires exact fields")
            if payload["sequence"] != expected_sequence:
                raise ValueError("judge journal sequence is not contiguous")
            kind = payload["kind"]
            record_hash = payload["record_hash"]
            if kind not in _KIND_TYPES or type(record_hash) is not str:
                raise ValueError("judge journal kind or record hash is invalid")
            content = {name: value for name, value in payload.items() if name != "journal_hash"}
            if payload["journal_hash"] != canonical_payload_hash(content):
                raise ValueError("judge journal entry hash differs from content")
            expected_name = f"{expected_sequence:012d}-{payload['journal_hash']}.json"
            if path.name != expected_name:
                raise ValueError("judge journal filename differs from entry identity")
            record_path = self.staging / kind / f"{record_hash}.json"
            record_type = _KIND_TYPES[kind]
            record = record_type.from_payload(_load_json(record_path))
            if record.record_hash != record_hash:
                raise ValueError("judge journal record identity differs from evidence")
            referenced[kind].add(record_hash)
            records.append(record)
        for kind in _KIND_TYPES:
            actual = {
                path.stem
                for path in (self.staging / kind).iterdir()
                if path.is_file() and not path.is_symlink()
            }
            if actual != referenced[kind]:
                raise ValueError("judge append-only inventory contains orphan or missing evidence")
        return tuple(records)

    def append(self, kind: str, record: object) -> None:
        if kind not in _KIND_TYPES or not isinstance(record, _KIND_TYPES[kind]):
            raise ValueError("unsupported judge evidence kind or record type")
        if record.manifest_hash != self.manifest.record_hash:
            raise ValueError("judge evidence manifest differs from store manifest")
        # Validate the complete current archive before introducing another immutable file.
        current_records = self.read_records()
        self._require_exact_projection_replay(current_records)
        record_path = self.staging / kind / f"{record.record_hash}.json"
        if record_path.exists() or record_path.is_symlink():
            raise FileExistsError("judge evidence record already exists")
        sequence = len(current_records) + 1
        entry_content: dict[str, object] = {
            "schema_version": "paper1.calibration.judge-journal-entry.v1",
            "sequence": sequence,
            "kind": kind,
            "record_hash": record.record_hash,
            "manifest_hash": self.manifest.record_hash,
        }
        journal_hash = canonical_payload_hash(entry_content)
        journal_path = self.staging / "journal" / f"{sequence:012d}-{journal_hash}.json"
        candidate_records = (*current_records, record)
        derived_projection = replay_judge_records(self.manifest.record_hash, candidate_records)[-1]
        _write_json_create_only(record_path, record.to_payload())
        _write_json_create_only(journal_path, {**entry_content, "journal_hash": journal_hash})
        self._write_projection(self.staging, derived_projection)

    def append_intent(self, record: JudgeDispatchIntent) -> None:
        self.append("dispatch", record)

    def append_reconciliation(self, record: JudgeDispatchReconciliation) -> None:
        self.append("reconciliation", record)

    def append_raw_provider_audit(
        self, intent: JudgeDispatchIntent, evidence: Mapping[str, object]
    ) -> JudgeProviderAuditRecord:
        record = JudgeProviderAuditRecord.create(intent, evidence)
        self.append("raw", record)
        return record

    def append_incomplete_attempt_marker(
        self, intent: JudgeDispatchIntent
    ) -> JudgeIncompleteAttemptMarker:
        record = JudgeIncompleteAttemptMarker.create(intent)
        self.append("attempts", record)
        return record
