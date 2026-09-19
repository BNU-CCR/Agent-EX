"""Create-only filesystem store for blinded judge execution evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from contextlib import contextmanager
from typing import Mapping

from ..domain import canonical_payload_hash
from .judge_contracts import (
    JudgeExecutionManifest,
    JudgePreflightEvidence,
    JudgeResponseEvidence,
    JudgeServiceEvidence,
)
from .judge_runner import (
    JudgeApprovedOrder,
    JudgeAttemptResolution,
    JudgeCompletedAttempt,
    JudgeDispatchIntent,
    JudgeDispatchReconciliation,
    JudgeIncompleteAttemptMarker,
    JudgeNegativeDispatchEvidence,
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
_EXTRA_LAYOUT = ("journal", "projections", "transactions/prepared", "transactions/committed")
_KIND_TYPES: dict[str, tuple[type[object], ...]] = {
    "dispatch": (JudgeDispatchIntent,),
    "reconciliation": (
        JudgeDispatchReconciliation,
        JudgeNegativeDispatchEvidence,
        JudgeAttemptResolution,
    ),
    "raw": (JudgeProviderAuditRecord, JudgeResponseEvidence),
    "attempts": (JudgeIncompleteAttemptMarker, JudgeCompletedAttempt),
    "service/preflight": (JudgePreflightEvidence,),
    "service/start": (JudgeServiceEvidence,),
}
_SCHEMA_TYPES = {
    record_type._SCHEMA: record_type
    for record_types in _KIND_TYPES.values()
    for record_type in record_types
}

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _transaction_checkpoint(phase: str) -> None:
    """Test seam immediately after each durable append transaction phase."""


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _archive_lock(root: Path):
    key = str(root.resolve(strict=True))
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.Lock())
    with thread_lock:
        lock_path = root / "staging" / ".append.lock"
        descriptor = os.open(lock_path, os.O_RDWR)
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _write_json_create_only(path: Path, payload: Mapping[str, object]) -> None:
    content = _canonical_json_bytes(payload)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("short write while appending judge evidence")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _publish_json_exact(path: Path, payload: Mapping[str, object]) -> None:
    expected = _canonical_json_bytes(payload)
    try:
        _write_json_create_only(path, payload)
    except FileExistsError:
        try:
            observed = path.read_bytes()
        except OSError as error:
            raise ValueError("existing judge transaction artifact cannot be read") from error
        if observed != expected:
            raise ValueError(
                f"existing judge transaction {path.parent.name} artifact differs from prepared bytes"
            )


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

    def __init__(
        self,
        root: Path,
        manifest: JudgeExecutionManifest,
        approved_order: JudgeApprovedOrder,
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.approved_order = approved_order

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @classmethod
    def create(
        cls,
        root: Path,
        manifest: JudgeExecutionManifest,
        pack: Mapping[str, object],
        index: Mapping[str, object],
    ) -> JudgeRunStore:
        if not isinstance(root, Path):
            raise TypeError("judge store root must be a Path")
        if not isinstance(manifest, JudgeExecutionManifest):
            raise TypeError("judge store requires a JudgeExecutionManifest")
        approved_order = JudgeApprovedOrder.from_manifest_bound_payloads(manifest, pack, index)
        JudgeExecutionManifest.from_payload(manifest.to_payload())
        root.mkdir(parents=False, exist_ok=False)
        staging = root / "staging"
        staging.mkdir()
        for relative in (*LAYOUT, *_EXTRA_LAYOUT):
            (staging / relative).mkdir(parents=True, exist_ok=False)
        lock_descriptor = os.open(
            staging / ".append.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            os.write(lock_descriptor, b"0")
            os.fsync(lock_descriptor)
        finally:
            os.close(lock_descriptor)
        _fsync_directory(staging)
        _write_json_create_only(staging / "manifest.json", manifest.to_payload())
        _write_json_create_only(staging / "approved-pack.json", pack)
        _write_json_create_only(staging / "approved-index.json", index)
        _write_json_create_only(staging / "approved-order.json", approved_order.to_payload())
        initial = replay_judge_records(manifest, approved_order, ())[-1]
        cls._write_projection(staging, initial)
        return cls.open(root)

    @classmethod
    def open(cls, root: Path) -> JudgeRunStore:
        if not isinstance(root, Path) or not root.is_dir() or root.is_symlink():
            raise ValueError("judge store root must be an existing non-link directory")
        staging = root / "staging"
        expected_top = {
            "manifest.json",
            "approved-order.json",
            "approved-pack.json",
            "approved-index.json",
            ".append.lock",
            "attempts",
            "dispatch",
            "reconciliation",
            "raw",
            "service",
            "journal",
            "projections",
            "transactions",
        }
        top_names = (
            frozenset(p.name for p in staging.iterdir()) if staging.is_dir() else frozenset()
        )
        if (
            not staging.is_dir()
            or staging.is_symlink()
            or top_names
            not in {frozenset(expected_top), frozenset((*expected_top, "projection.json"))}
        ):
            raise ValueError("judge store staging inventory is not exact")
        if {p.name for p in (staging / "service").iterdir()} != {"preflight", "start", "stop"}:
            raise ValueError("judge service evidence inventory is not exact")
        cls._require_safe_layout(staging)
        manifest = JudgeExecutionManifest.from_payload(_load_json(staging / "manifest.json"))
        stored_order = JudgeApprovedOrder.from_payload(_load_json(staging / "approved-order.json"))
        approved_order = JudgeApprovedOrder.from_manifest_bound_payloads(
            manifest,
            _load_json(staging / "approved-pack.json"),
            _load_json(staging / "approved-index.json"),
        )
        if stored_order != approved_order:
            raise ValueError("stored approved order differs from manifest-bound pack and index")
        store = cls(root, manifest, approved_order)
        with _archive_lock(root):
            store._recover_transactions()
            records = store.read_records()
            expected = replay_judge_records(manifest, approved_order, records)
            actual = store._read_projections()
            if len(actual) != len(expected):
                raise ValueError("judge projection hash chain is not contiguous")
            for sequence, (observed, derived) in enumerate(zip(actual, expected, strict=True)):
                if observed.sequence != sequence or observed.to_payload() != derived.to_payload():
                    raise ValueError("judge projection hash chain differs from exact replay")
            terminal_path = staging / "projection.json"
            if terminal_path.exists():
                if terminal_path.is_symlink() or not terminal_path.is_file():
                    raise ValueError("terminal judge projection must be a regular file")
                terminal = JudgeProjection.from_payload(_load_json(terminal_path))
                if not actual or terminal.to_payload() != actual[-1].to_payload():
                    raise ValueError("terminal judge projection differs from final snapshot")
        return store

    @staticmethod
    def _require_safe_layout(staging: Path) -> None:
        directories = (
            "attempts",
            "dispatch",
            "reconciliation",
            "raw",
            "journal",
            "projections",
            "service",
            "service/preflight",
            "service/start",
            "service/stop",
            "transactions",
            "transactions/prepared",
            "transactions/committed",
        )
        for relative in directories:
            path = staging / relative
            if path.is_symlink() or not path.is_dir():
                raise ValueError("judge store layout directory is missing or is a link")
        if {p.name for p in (staging / "transactions").iterdir()} != {
            "prepared",
            "committed",
        }:
            raise ValueError("judge transaction inventory is not exact")

    def _recover_transactions(self) -> None:
        prepared_dir = self.staging / "transactions" / "prepared"
        committed_dir = self.staging / "transactions" / "committed"
        prepared_paths = sorted(prepared_dir.iterdir())
        prepared_hashes: set[str] = set()
        for path in prepared_paths:
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise ValueError("prepared judge transaction inventory is invalid")
            payload = _load_json(path)
            required = {
                "schema_version",
                "sequence",
                "kind",
                "record_hash",
                "record_payload",
                "journal_payload",
                "projection_payload",
                "transaction_hash",
            }
            if (
                set(payload) != required
                or payload["schema_version"] != "paper1.calibration.judge-append-transaction.v1"
            ):
                raise ValueError("prepared judge transaction requires exact fields")
            content = {name: value for name, value in payload.items() if name != "transaction_hash"}
            transaction_hash = canonical_payload_hash(content)
            if (
                payload["transaction_hash"] != transaction_hash
                or path.name != f"{payload['sequence']:012d}-{transaction_hash}.json"
            ):
                raise ValueError("prepared judge transaction hash or filename differs")
            kind = payload["kind"]
            record_hash = payload["record_hash"]
            if kind not in _KIND_TYPES or type(record_hash) is not str:
                raise ValueError("prepared judge transaction kind is invalid")
            for name in ("record_payload", "journal_payload", "projection_payload"):
                if type(payload[name]) is not dict:
                    raise TypeError("prepared judge transaction payloads must be JSON objects")
            journal_payload = payload["journal_payload"]
            projection_payload = payload["projection_payload"]
            journal_hash = journal_payload.get("journal_hash")
            projection_hash = projection_payload.get("record_hash")
            if type(journal_hash) is not str or type(projection_hash) is not str:
                raise ValueError("prepared transaction identities are invalid")
            _publish_json_exact(
                self.staging / kind / f"{record_hash}.json", payload["record_payload"]
            )
            expected_journal_path = (
                self.staging / "journal" / f"{payload['sequence']:012d}-{journal_hash}.json"
            )
            if not expected_journal_path.exists():
                conflicting = tuple(
                    (self.staging / "journal").glob(f"{payload['sequence']:012d}-*.json")
                )
                for candidate in conflicting:
                    candidate_payload = _load_json(candidate)
                    if candidate_payload.get("manifest_hash") != self.manifest.record_hash:
                        raise ValueError("judge journal manifest hash differs from store manifest")
                if conflicting:
                    raise ValueError("judge journal transaction conflicts with prepared evidence")
            _publish_json_exact(
                expected_journal_path,
                journal_payload,
            )
            _publish_json_exact(
                self.staging / "projections" / f"{payload['sequence']:012d}-{projection_hash}.json",
                projection_payload,
            )
            _publish_json_exact(
                committed_dir / f"{payload['sequence']:012d}-{transaction_hash}.json",
                {
                    "schema_version": "paper1.calibration.judge-append-commit.v1",
                    "sequence": payload["sequence"],
                    "transaction_hash": transaction_hash,
                },
            )
            prepared_hashes.add(transaction_hash)
        committed_hashes: set[str] = set()
        for path in committed_dir.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise ValueError("committed judge transaction inventory is invalid")
            payload = _load_json(path)
            if (
                set(payload) != {"schema_version", "sequence", "transaction_hash"}
                or payload["schema_version"] != "paper1.calibration.judge-append-commit.v1"
            ):
                raise ValueError("judge transaction commit requires exact fields")
            expected_name = f"{payload['sequence']:012d}-{payload['transaction_hash']}.json"
            if path.name != expected_name:
                raise ValueError("judge transaction commit filename differs")
            committed_hashes.add(payload["transaction_hash"])
        if committed_hashes != prepared_hashes:
            raise ValueError("judge transaction commit inventory differs from prepared inventory")

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
        expected = replay_judge_records(self.manifest, self.approved_order, records)
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
            if payload["manifest_hash"] != self.manifest.record_hash:
                raise ValueError("judge journal manifest hash differs from store manifest")
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
            record_payload = _load_json(record_path)
            record_type = _SCHEMA_TYPES.get(record_payload.get("schema_version"))
            if record_type is None or record_type not in _KIND_TYPES[kind]:
                raise ValueError("judge evidence schema differs from journal kind")
            record = record_type.from_payload(record_payload)
            if record.record_hash != record_hash:
                raise ValueError("judge journal record identity differs from evidence")
            referenced[kind].add(record_hash)
            records.append(record)
        for kind in _KIND_TYPES:
            entries = tuple((self.staging / kind).iterdir())
            if any(
                path.is_symlink() or not path.is_file() or path.suffix != ".json"
                for path in entries
            ):
                raise ValueError("judge append-only inventory requires regular JSON files")
            actual = {path.stem for path in entries}
            if actual != referenced[kind]:
                raise ValueError("judge append-only inventory contains orphan or missing evidence")
        stop_entries = tuple((self.staging / "service" / "stop").iterdir())
        if stop_entries:
            raise ValueError("judge service stop inventory is outside the Task 5 store contract")
        return tuple(records)

    def append(self, kind: str, record: object) -> None:
        if kind not in _KIND_TYPES or not isinstance(record, _KIND_TYPES[kind]):
            raise ValueError("unsupported judge evidence kind or record type")
        record_manifest_hash = getattr(record, "manifest_hash", None)
        if record_manifest_hash is not None and record_manifest_hash != self.manifest.record_hash:
            raise ValueError("judge evidence manifest differs from store manifest")
        with _archive_lock(self.root):
            self._require_safe_layout(self.staging)
            self._recover_transactions()
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
            journal_payload = {**entry_content, "journal_hash": journal_hash}
            candidate_records = (*current_records, record)
            derived_projection = replay_judge_records(
                self.manifest, self.approved_order, candidate_records
            )[-1]
            transaction_content: dict[str, object] = {
                "schema_version": "paper1.calibration.judge-append-transaction.v1",
                "sequence": sequence,
                "kind": kind,
                "record_hash": record.record_hash,
                "record_payload": record.to_payload(),
                "journal_payload": journal_payload,
                "projection_payload": derived_projection.to_payload(),
            }
            transaction_hash = canonical_payload_hash(transaction_content)
            transaction_payload = {
                **transaction_content,
                "transaction_hash": transaction_hash,
            }
            prepared_path = (
                self.staging
                / "transactions"
                / "prepared"
                / f"{sequence:012d}-{transaction_hash}.json"
            )
            _write_json_create_only(prepared_path, transaction_payload)
            _transaction_checkpoint("prepared")
            _publish_json_exact(record_path, record.to_payload())
            _transaction_checkpoint("record")
            _publish_json_exact(
                self.staging / "journal" / f"{sequence:012d}-{journal_hash}.json",
                journal_payload,
            )
            _transaction_checkpoint("journal")
            _publish_json_exact(
                self.staging
                / "projections"
                / f"{sequence:012d}-{derived_projection.record_hash}.json",
                derived_projection.to_payload(),
            )
            _transaction_checkpoint("projection")
            _publish_json_exact(
                self.staging
                / "transactions"
                / "committed"
                / f"{sequence:012d}-{transaction_hash}.json",
                {
                    "schema_version": "paper1.calibration.judge-append-commit.v1",
                    "sequence": sequence,
                    "transaction_hash": transaction_hash,
                },
            )
            _transaction_checkpoint("commit")

    def verify_terminal_projection(self) -> JudgeProjection:
        with _archive_lock(self.root):
            self._recover_transactions()
            records = self.read_records()
            self._require_exact_projection_replay(records)
            projection = replay_judge_records(self.manifest, self.approved_order, records)[-1]
            if (
                tuple(projection.item_order)
                != tuple(item.item_id for item in self.approved_order.items)
                or len(projection.item_states) != self.manifest.expected_item_count
                or any(
                    state.unresolved_intent_hash is not None
                    or state.status not in {"coded", "terminal_failed", "ambiguous_incomplete"}
                    for state in projection.item_states.values()
                )
            ):
                raise ValueError("terminal projection lacks exact terminal item cover")
            target = self.staging / "projection.json"
            if target.exists() or target.is_symlink():
                raise FileExistsError("terminal projection already exists")
            _write_json_create_only(target, projection.to_payload())
            return projection

    def append_intent(self, record: JudgeDispatchIntent) -> None:
        self.append("dispatch", record)

    def append_reconciliation(self, record: JudgeDispatchReconciliation) -> None:
        self.append("reconciliation", record)

    def append_negative_dispatch_evidence(self, record: JudgeNegativeDispatchEvidence) -> None:
        self.append("reconciliation", record)

    def append_response(self, record: JudgeResponseEvidence) -> None:
        self.append("raw", record)

    def append_completed_attempt(self, record: JudgeCompletedAttempt) -> None:
        self.append("attempts", record)

    def append_attempt_resolution(self, record: JudgeAttemptResolution) -> None:
        self.append("reconciliation", record)

    def append_preflight(self, record: JudgePreflightEvidence) -> None:
        self.append("service/preflight", record)

    def append_service_start(self, record: JudgeServiceEvidence) -> None:
        self.append("service/start", record)

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
