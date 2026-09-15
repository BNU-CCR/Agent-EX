"""Append-only staging and terminal sealing for Phase 0A-1 probe evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from threading import RLock
from typing import TYPE_CHECKING, Mapping
from uuid import uuid4

from ..domain import _json_ready, _require_json_transport, _require_sha256, canonical_payload_hash
from .bundle import ProbeBundle, load_probe_bundle, write_probe_bundle_atomic

if TYPE_CHECKING:
    from .smoke import ServiceStopEvidence, SmokeProgress
    from .transport_diagnostics import TransportDiagnosticEvidence


_PROJECTION_SCHEMA = "paper1.calibration.probe-store-projection.v1"
_SEAL_SCHEMA = "paper1.calibration.probe-store-seal.v1"


def _duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"store entry must be a regular file: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON store entry: {path.name}") from error
    if type(value) is not dict:
        raise TypeError("store records must be JSON objects")
    _require_json_transport(value, "store record")
    return value


def _encoded(payload: Mapping[str, object]) -> bytes:
    _require_json_transport(payload, "store record")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_temp(directory: Path, payload: Mapping[str, object]) -> Path:
    temporary = directory / f".tmp-{uuid4().hex}"
    with temporary.open("xb") as handle:
        handle.write(_encoded(payload))
        handle.flush()
        os.fsync(handle.fileno())
    return temporary


def _write_create_only(path: Path, payload: Mapping[str, object]) -> None:
    temporary = _write_temp(path.parent, payload)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _write_projection(path: Path, payload: Mapping[str, object]) -> None:
    temporary = _write_temp(path.parent, payload)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _validate_hashed_record(payload: Mapping[str, object], *, name: str) -> str:
    if type(payload) is not dict or "record_hash" not in payload:
        raise ValueError(f"{name} must contain record_hash")
    _require_json_transport(payload, name)
    digest = payload["record_hash"]
    _require_sha256("record_hash", digest)
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    if digest != canonical_payload_hash(content):
        raise ValueError(f"{name} hash drift")
    return digest


def _projection_payload(
    *, manifest_hash: str, attempt_hashes: tuple[str, ...], review_hashes: tuple[str, ...]
) -> dict[str, object]:
    content: dict[str, object] = {
        "schema_version": _PROJECTION_SCHEMA,
        "manifest_hash": manifest_hash,
        "attempt_hashes": list(attempt_hashes),
        "review_hashes": list(review_hashes),
        "status": "staging",
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def _validate_projection(
    payload: Mapping[str, object],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    expected = {
        "schema_version",
        "manifest_hash",
        "attempt_hashes",
        "review_hashes",
        "status",
        "record_hash",
    }
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError("projection fields do not match the exact contract")
    if payload["schema_version"] != _PROJECTION_SCHEMA or payload["status"] != "staging":
        raise ValueError("projection schema or status is invalid")
    _validate_hashed_record(payload, name="projection")
    _require_sha256("manifest_hash", payload["manifest_hash"])
    if type(payload["attempt_hashes"]) is not list or type(payload["review_hashes"]) is not list:
        raise TypeError("projection hashes must use JSON arrays")
    attempts = tuple(payload["attempt_hashes"])
    reviews = tuple(payload["review_hashes"])
    for digest in (*attempts, *reviews):
        _require_sha256("projection record hash", digest)
    if len(attempts) != len(set(attempts)) or len(reviews) != len(set(reviews)):
        raise ValueError("projection contains duplicate hashes")
    return payload["manifest_hash"], attempts, reviews  # type: ignore[return-value]


def _attempt_position(payload: Mapping[str, object]) -> tuple[str, int]:
    case_id = payload.get("probe_case_id")
    index = payload.get("attempt_index")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("attempt probe_case_id must be non-empty")
    if type(index) is not int or index < 1:
        raise ValueError("attempt_index must be a positive integer")
    return case_id, index


def _validate_attempt_sequence(records: tuple[Mapping[str, object], ...]) -> None:
    positions = [_attempt_position(record) for record in records]
    if len(positions) != len(set(positions)):
        raise ValueError("attempt records contain a duplicate case position")
    by_case: dict[str, list[int]] = {}
    for case_id, index in positions:
        by_case.setdefault(case_id, []).append(index)
    for indices in by_case.values():
        if sorted(indices) != list(range(1, len(indices) + 1)):
            raise ValueError("attempt indices must form a contiguous prefix")


@dataclass(slots=True)
class ProbeRunStore:
    """One staging or sealed run rooted at an explicit external directory."""

    root: Path
    manifest_hash: str
    attempt_hashes: tuple[str, ...]
    review_hashes: tuple[str, ...]
    _sealed: bool
    _lock: RLock

    @classmethod
    def create(cls, root: Path, *, manifest: Mapping[str, object]) -> ProbeRunStore:
        if not isinstance(root, Path):
            raise TypeError("store root must be an explicit Path")
        if root.exists() or root.is_symlink():
            raise FileExistsError(root)
        if not root.parent.is_dir():
            raise FileNotFoundError("store parent directory must already exist")
        manifest_hash = _validate_hashed_record(manifest, name="store manifest")
        staging = root / "staging"
        try:
            (staging / "attempts").mkdir(parents=True, exist_ok=False)
            (staging / "reviews").mkdir(exist_ok=False)
            (staging / "smoke-progress").mkdir(exist_ok=False)
            (staging / "transport-diagnostics").mkdir(exist_ok=False)
            (staging / "service-stops").mkdir(exist_ok=False)
            _write_create_only(staging / "manifest.json", _json_ready(manifest))
            projection = _projection_payload(
                manifest_hash=manifest_hash, attempt_hashes=(), review_hashes=()
            )
            _write_projection(staging / "projection.json", projection)
            _fsync_directory(staging)
            _fsync_directory(root)
        except BaseException:
            if root.is_dir() and not root.is_symlink():
                shutil.rmtree(root, ignore_errors=True)
            raise
        return cls(root, manifest_hash, (), (), False, RLock())

    @classmethod
    def open(cls, root: Path) -> ProbeRunStore:
        if not isinstance(root, Path) or not root.is_dir() or root.is_symlink():
            raise ValueError("store root must be an existing regular directory")
        staging = root / "staging"
        sealed = root / "sealed"
        if sealed.exists():
            if not sealed.is_dir() or sealed.is_symlink():
                raise ValueError("sealed store must be a regular directory")
            seal = _read_json(sealed / "manifest.json")
            expected = {
                "schema_version",
                "staging_manifest_hash",
                "staging_projection_hash",
                "bundle_manifest_hash",
                "bundle_payloads_hash",
                "record_hash",
            }
            if set(seal) != expected or seal["schema_version"] != _SEAL_SCHEMA:
                raise ValueError("seal manifest fields are invalid")
            _validate_hashed_record(seal, name="seal manifest")
            bundle = load_probe_bundle(sealed / "files")
            payloads = bundle.to_payloads()
            if seal["bundle_payloads_hash"] != canonical_payload_hash(payloads):
                raise ValueError("sealed bundle hash drift")
            bundle_manifest = payloads["manifest.json"]
            if not isinstance(bundle_manifest, Mapping) or (
                seal["bundle_manifest_hash"] != bundle_manifest.get("manifest_hash")
            ):
                raise ValueError("sealed bundle manifest hash drift")
            evidence = sealed / "evidence"
            if not evidence.is_dir() or evidence.is_symlink():
                raise ValueError("sealed store lacks immutable append-only evidence")
            evidence_manifest = _read_json(evidence / "manifest.json")
            evidence_manifest_hash = _validate_hashed_record(
                evidence_manifest, name="sealed evidence manifest"
            )
            if evidence_manifest_hash != seal["staging_manifest_hash"]:
                raise ValueError("sealed evidence manifest hash drift")
            evidence_projection = _read_json(evidence / "projection.json")
            evidence_projection_hash = _validate_hashed_record(
                evidence_projection, name="sealed evidence projection"
            )
            if evidence_projection_hash != seal["staging_projection_hash"]:
                raise ValueError("sealed evidence projection hash drift")
            projected_manifest, projected_attempts, projected_reviews = _validate_projection(
                evidence_projection
            )
            if projected_manifest != evidence_manifest_hash:
                raise ValueError("sealed evidence authorization drift")
            attempts_by_hash = cls._load_records(evidence / "attempts", "attempt")
            reviews_by_hash = cls._load_records(evidence / "reviews", "review")
            recovery_records = {
                kind: cls._load_records(evidence / kind, name)
                for kind, name in (
                    ("smoke-progress", "smoke progress"),
                    ("transport-diagnostics", "transport diagnostic"),
                    ("service-stops", "service stop"),
                )
            }
            if set(attempts_by_hash) != set(projected_attempts) or set(reviews_by_hash) != set(
                projected_reviews
            ):
                raise ValueError("sealed evidence inventory differs from its projection")
            _validate_attempt_sequence(
                tuple(attempts_by_hash[digest] for digest in projected_attempts)
            )
            if staging.exists():
                if not staging.is_dir() or staging.is_symlink():
                    raise ValueError("sealed/staging recovery state is invalid")
                try:
                    stale_manifest = _read_json(staging / "manifest.json")
                    stale_projection = _read_json(staging / "projection.json")
                    duplicate_differs = (
                        _validate_hashed_record(stale_manifest, name="stale staging manifest")
                        != evidence_manifest_hash
                        or _validate_hashed_record(
                            stale_projection, name="stale staging projection"
                        )
                        != evidence_projection_hash
                        or cls._load_records(staging / "attempts", "attempt") != attempts_by_hash
                        or cls._load_records(staging / "reviews", "review") != reviews_by_hash
                        or any(
                            cls._load_records(staging / kind, name) != recovery_records[kind]
                            for kind, name in (
                                ("smoke-progress", "smoke progress"),
                                ("transport-diagnostics", "transport diagnostic"),
                                ("service-stops", "service stop"),
                            )
                        )
                    )
                except (OSError, TypeError, ValueError) as error:
                    raise ValueError("sealed and staging evidence differ") from error
                if duplicate_differs:
                    raise ValueError("sealed and staging evidence differ")
            result = cls(
                root,
                seal["staging_manifest_hash"],  # type: ignore[arg-type]
                projected_attempts,
                projected_reviews,
                True,
                RLock(),
            )
            result.load_smoke_progress()
            result.load_transport_diagnostics()
            result.load_service_stops()
            return result
        if not staging.is_dir() or staging.is_symlink():
            raise ValueError("store must contain exactly one staging or sealed state")
        manifest = _read_json(staging / "manifest.json")
        manifest_hash = _validate_hashed_record(manifest, name="store manifest")
        projection = _read_json(staging / "projection.json")
        projected_manifest, projected_attempts, projected_reviews = _validate_projection(projection)
        if projected_manifest != manifest_hash:
            raise ValueError("projection manifest hash drift")
        attempts_by_hash = cls._load_records(staging / "attempts", "attempt")
        reviews_by_hash = cls._load_records(staging / "reviews", "review")
        missing_attempts = set(projected_attempts) - set(attempts_by_hash)
        missing_reviews = set(projected_reviews) - set(reviews_by_hash)
        if missing_attempts or missing_reviews:
            raise ValueError("projection claims missing append-only records")
        remaining_attempts = sorted(set(attempts_by_hash) - set(projected_attempts))
        remaining_reviews = sorted(set(reviews_by_hash) - set(projected_reviews))
        attempt_hashes = (*projected_attempts, *remaining_attempts)
        review_hashes = (*projected_reviews, *remaining_reviews)
        _validate_attempt_sequence(tuple(attempts_by_hash[digest] for digest in attempt_hashes))
        result = cls(root, manifest_hash, attempt_hashes, review_hashes, False, RLock())
        result.load_smoke_progress()
        result.load_transport_diagnostics()
        result.load_service_stops()
        return result

    @staticmethod
    def _load_records(directory: Path, name: str) -> dict[str, Mapping[str, object]]:
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"{name} store must be a regular directory")
        records: dict[str, Mapping[str, object]] = {}
        for path in directory.iterdir():
            if path.name.startswith(".tmp-"):
                continue
            payload = _read_json(path)
            digest = _validate_hashed_record(payload, name=name)
            if path.name != f"{digest}.json":
                raise ValueError(f"{name} filename and hash drift")
            if digest in records:
                raise ValueError(f"duplicate {name} record hash")
            records[digest] = payload
        return records

    def _require_staging(self) -> Path:
        if self._sealed or (self.root / "sealed").exists():
            raise RuntimeError("probe run store is sealed")
        staging = self.root / "staging"
        if not staging.is_dir() or staging.is_symlink():
            raise RuntimeError("probe run staging state is unavailable")
        return staging

    def _persist_projection(self, staging: Path) -> None:
        projection = _projection_payload(
            manifest_hash=self.manifest_hash,
            attempt_hashes=self.attempt_hashes,
            review_hashes=self.review_hashes,
        )
        _write_projection(staging / "projection.json", projection)

    def append_attempt(self, payload: Mapping[str, object]) -> None:
        with self._lock:
            staging = self._require_staging()
            digest = _validate_hashed_record(payload, name="attempt")
            target = staging / "attempts" / f"{digest}.json"
            if target.exists() or target.is_symlink():
                raise FileExistsError(target)
            records = self._load_records(staging / "attempts", "attempt")
            candidate = (*records.values(), payload)
            _validate_attempt_sequence(candidate)
            position = _attempt_position(payload)
            if any(_attempt_position(record) == position for record in records.values()):
                raise ValueError("attempt records contain a duplicate case position")
            _write_create_only(target, _json_ready(payload))
            self.attempt_hashes = (*self.attempt_hashes, digest)
            self._persist_projection(staging)

    def append_review(self, payload: Mapping[str, object]) -> None:
        with self._lock:
            staging = self._require_staging()
            digest = _validate_hashed_record(payload, name="review")
            _write_create_only(staging / "reviews" / f"{digest}.json", _json_ready(payload))
            self.review_hashes = (*self.review_hashes, digest)
            self._persist_projection(staging)

    def append_smoke_progress(self, payload: Mapping[str, object]) -> None:
        from .smoke import SmokeProgress

        with self._lock:
            staging = self._require_staging()
            record = SmokeProgress.from_payload(payload)
            if record.manifest_hash != self.manifest_hash:
                raise ValueError("smoke progress manifest does not match store manifest")
            target = staging / "smoke-progress" / f"{record.record_hash}.json"
            if target.exists() or target.is_symlink():
                raise FileExistsError(target)
            existing = self.load_smoke_progress()
            if record.sequence != len(existing) + 1:
                raise ValueError("smoke progress sequence must be contiguous")
            if existing:
                previous = existing[-1]
                if record.previous_progress_hash != previous.record_hash:
                    raise ValueError("smoke progress previous hash does not match")
                if record.environment_lock_hash != previous.environment_lock_hash:
                    raise ValueError("smoke progress environment lock changed")
            _write_create_only(target, record.to_payload())

    def load_smoke_progress(self) -> tuple[SmokeProgress, ...]:
        from .smoke import SmokeProgress

        directory = self.root / ("sealed/evidence" if self._sealed else "staging")
        records = self._load_records(directory / "smoke-progress", "smoke progress")
        ordered = tuple(
            sorted(
                (SmokeProgress.from_payload(item) for item in records.values()),
                key=lambda item: item.sequence,
            )
        )
        if tuple(item.sequence for item in ordered) != tuple(range(1, len(ordered) + 1)):
            raise ValueError("smoke progress sequence must be contiguous")
        for index, item in enumerate(ordered):
            if item.manifest_hash != self.manifest_hash:
                raise ValueError("smoke progress manifest does not match store manifest")
            if index and item.previous_progress_hash != ordered[index - 1].record_hash:
                raise ValueError("smoke progress previous hash does not match")
            if index and item.environment_lock_hash != ordered[0].environment_lock_hash:
                raise ValueError("smoke progress environment lock changed")
        return ordered

    def append_transport_diagnostic(self, payload: Mapping[str, object]) -> None:
        from .transport_diagnostics import TransportDiagnosticEvidence

        with self._lock:
            staging = self._require_staging()
            record = TransportDiagnosticEvidence.from_payload(payload)
            target = staging / "transport-diagnostics" / f"{record.record_hash}.json"
            if target.exists() or target.is_symlink():
                raise FileExistsError(target)
            existing = self.load_transport_diagnostics()
            if any(item.diagnostic_id == record.diagnostic_id for item in existing):
                raise ValueError("transport diagnostic already complete")
            _write_create_only(target, record.to_payload())

    def load_transport_diagnostics(self) -> tuple[TransportDiagnosticEvidence, ...]:
        from .transport_diagnostics import TransportDiagnosticEvidence

        directory = self.root / ("sealed/evidence" if self._sealed else "staging")
        records = self._load_records(directory / "transport-diagnostics", "transport diagnostic")
        parsed = tuple(
            TransportDiagnosticEvidence.from_payload(value) for value in records.values()
        )
        if len({item.diagnostic_id for item in parsed}) != len(parsed):
            raise ValueError("transport diagnostic identity is duplicated")
        by_id = {item.diagnostic_id: item for item in parsed}
        order = ("closed-port", "controlled-timeout", "http-429-retry-after")
        return tuple(by_id[item] for item in order if item in by_id)

    def append_service_stop(self, payload: Mapping[str, object]) -> None:
        from .smoke import ServiceStopEvidence

        with self._lock:
            staging = self._require_staging()
            record = ServiceStopEvidence.from_payload(payload)
            if record.manifest_hash != self.manifest_hash:
                raise ValueError("service stop manifest does not match store manifest")
            target = staging / "service-stops" / f"{record.record_hash}.json"
            if target.exists() or target.is_symlink():
                raise FileExistsError(target)
            existing = self.load_service_stops()
            if any(
                item.service_start_identity_hash == record.service_start_identity_hash
                for item in existing
            ):
                raise ValueError("service stop identity already recorded")
            progress = self.load_smoke_progress()
            if progress and record.environment_lock_hash != progress[0].environment_lock_hash:
                raise ValueError("service stop environment lock does not match smoke progress")
            _write_create_only(target, record.to_payload())

    def load_service_stops(self) -> tuple[ServiceStopEvidence, ...]:
        from .smoke import ServiceStopEvidence

        directory = self.root / ("sealed/evidence" if self._sealed else "staging")
        records = self._load_records(directory / "service-stops", "service stop")
        parsed = tuple(ServiceStopEvidence.from_payload(value) for value in records.values())
        if len({item.service_start_identity_hash for item in parsed}) != len(parsed):
            raise ValueError("service stop identity is duplicated")
        for item in parsed:
            if item.manifest_hash != self.manifest_hash:
                raise ValueError("service stop manifest does not match store manifest")
        return tuple(sorted(parsed, key=lambda item: (item.stopped_at, item.record_hash)))

    def consumed_attempts(self, probe_case_id: str) -> int:
        if not isinstance(probe_case_id, str) or not probe_case_id.strip():
            raise ValueError("probe_case_id must be non-empty")
        if self._sealed:
            raise RuntimeError("sealed stores do not expose mutable retry budgets")
        records = self._load_records(self.root / "staging" / "attempts", "attempt")
        return sum(
            1 for payload in records.values() if payload.get("probe_case_id") == probe_case_id
        )

    def seal(self, *, bundle: ProbeBundle) -> None:
        with self._lock:
            staging = self._require_staging()
            if type(bundle) is not ProbeBundle:
                raise TypeError("seal requires a validated ProbeBundle")
            checked = ProbeBundle.from_payloads(bundle.to_payloads())
            reopened = type(self).open(self.root)
            if reopened.manifest_hash != self.manifest_hash:
                raise ValueError("store authorization changed before sealing")
            self.attempt_hashes = reopened.attempt_hashes
            self.review_hashes = reopened.review_hashes
            self._persist_projection(staging)
            sealed = self.root / "sealed"
            partial = self.root / "sealed.partial"
            if sealed.exists() or sealed.is_symlink() or partial.exists() or partial.is_symlink():
                raise FileExistsError(sealed)
            projection = _read_json(staging / "projection.json")
            projection_hash = _validate_hashed_record(projection, name="projection")
            payloads = checked.to_payloads()
            bundle_manifest = payloads["manifest.json"]
            if not isinstance(bundle_manifest, Mapping):
                raise TypeError("bundle manifest must be a mapping")
            bundle_manifest_hash = bundle_manifest.get("manifest_hash")
            _require_sha256("bundle_manifest_hash", bundle_manifest_hash)
            partial.mkdir()
            created = True
            try:
                write_probe_bundle_atomic(partial / "files", checked)
                evidence = partial / "evidence"
                (evidence / "attempts").mkdir(parents=True)
                (evidence / "reviews").mkdir()
                (evidence / "smoke-progress").mkdir()
                (evidence / "transport-diagnostics").mkdir()
                (evidence / "service-stops").mkdir()
                _write_create_only(
                    evidence / "manifest.json", _read_json(staging / "manifest.json")
                )
                _write_create_only(
                    evidence / "projection.json", _read_json(staging / "projection.json")
                )
                for kind in (
                    "attempts",
                    "reviews",
                    "smoke-progress",
                    "transport-diagnostics",
                    "service-stops",
                ):
                    source = staging / kind
                    target = evidence / kind
                    for source_path in source.iterdir():
                        if source_path.name.startswith(".tmp-"):
                            continue
                        _write_create_only(target / source_path.name, _read_json(source_path))
                    _fsync_directory(target)
                _fsync_directory(evidence)
                content: dict[str, object] = {
                    "schema_version": _SEAL_SCHEMA,
                    "staging_manifest_hash": self.manifest_hash,
                    "staging_projection_hash": projection_hash,
                    "bundle_manifest_hash": bundle_manifest_hash,
                    "bundle_payloads_hash": canonical_payload_hash(payloads),
                }
                seal_manifest = {**content, "record_hash": canonical_payload_hash(content)}
                _write_create_only(partial / "manifest.json", seal_manifest)
                _fsync_directory(partial)
                os.replace(partial, sealed)
                created = False
                _fsync_directory(self.root)
                shutil.rmtree(staging)
                _fsync_directory(self.root)
                self._sealed = True
                self.attempt_hashes = ()
                self.review_hashes = ()
            except BaseException:
                if created and partial.is_dir() and not partial.is_symlink():
                    shutil.rmtree(partial, ignore_errors=True)
                raise
