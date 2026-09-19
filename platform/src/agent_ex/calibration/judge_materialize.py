"""Trusted materialization of a strictly blinded Phase 0A-1 judge view."""

from __future__ import annotations

from dataclasses import dataclass, fields
import ctypes
import errno
import hashlib
import json
import os
from pathlib import PureWindowsPath
from pathlib import Path
import secrets
import stat
from typing import Mapping

from ..domain import _require_sha256, canonical_payload_hash
from .review import BlindReviewItem, SemanticReviewBundle, items_for_coder


_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_PACK_SCHEMA = "paper1.calibration.blind-coder-pack.v1"
_INDEX_SCHEMA = "paper1.calibration.blind-coder-pack-index.v1"
_VISIBLE_FIELDS = ("topic_text", "history_text", "identity_text", "response_text")
EXPECTED_JUDGE_ITEM_COUNT = 797


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _duplicate_checked_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _load_canonical_json(data: bytes, name: str) -> dict[str, object]:
    if type(data) is not bytes:
        raise TypeError(f"{name} bytes must be exact bytes")
    try:
        payload = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_duplicate_checked_object,
            parse_constant=_reject_nonfinite,
        )
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} must be canonical UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise ValueError(f"{name} must be a canonical JSON object")
    if data != _canonical_bytes(payload):
        raise ValueError(f"{name} bytes are not the project canonical JSON representation")
    return payload


def _require_exact_fields(
    payload: Mapping[str, object], expected: set[str], schema: str, name: str
) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError(f"{name} fields do not match the exact contract")
    if payload["schema_version"] != schema:
        raise ValueError(f"{name} schema version is unsupported")


def _require_embedded_hash(payload: Mapping[str, object], name: str) -> None:
    digest = payload.get("record_hash")
    _require_sha256(f"{name} record_hash", digest)  # type: ignore[arg-type]
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    if digest != canonical_payload_hash(content):
        raise ValueError(f"{name} embedded record hash is invalid")


def _require_boundary_flags(payload: Mapping[str, object], name: str) -> None:
    if payload.get("calibration_only") is not True:
        raise ValueError(f"{name} must remain calibration-only")
    if payload.get("formal_parameter_authority") is not False:
        raise ValueError(f"{name} must have no formal parameter authority")


def _validate_pack(
    bundle: SemanticReviewBundle, pack: dict[str, object]
) -> tuple[str, str, tuple[BlindReviewItem, ...]]:
    _require_exact_fields(
        pack,
        {
            "schema_version",
            "coder_id",
            "coder_role",
            "coder_contract_hash",
            "policy_id",
            "policy_hash",
            "export_hash",
            "items",
            "calibration_only",
            "formal_parameter_authority",
            "record_hash",
        },
        _PACK_SCHEMA,
        "judge pack",
    )
    _require_embedded_hash(pack, "judge pack")
    _require_boundary_flags(pack, "judge pack")
    if pack["coder_role"] != "judge":
        raise ValueError("judge pack must contain only the judge role")
    if type(pack["coder_id"]) is not str:
        raise TypeError("judge pack coder_id must be text")
    matches = tuple(
        contract
        for contract in bundle.policy.coder_contracts
        if contract.coder_id == pack["coder_id"]
    )
    if len(matches) != 1 or matches[0].role != "judge":
        raise ValueError("judge pack coder is not the bundle judge contract")
    contract = matches[0]
    if pack["coder_contract_hash"] != contract.record_hash:
        raise ValueError("judge pack coder contract hash differs from the bundle")
    if pack["policy_id"] != bundle.policy.policy_id:
        raise ValueError("judge pack policy identity differs from the bundle")
    if pack["policy_hash"] != bundle.policy.record_hash:
        raise ValueError("judge pack policy hash differs from the bundle")
    if pack["export_hash"] != bundle.review_export.export_hash:
        raise ValueError("judge pack export hash differs from the bundle")
    if type(pack["items"]) is not list:
        raise TypeError("judge pack items must use a JSON array")
    if len(pack["items"]) != EXPECTED_JUDGE_ITEM_COUNT:
        raise ValueError(f"judge pack must contain exactly {EXPECTED_JUDGE_ITEM_COUNT} items")
    parsed: list[BlindReviewItem] = []
    for payload in pack["items"]:
        if type(payload) is not dict:
            raise TypeError("judge pack item must use a JSON object")
        try:
            item = BlindReviewItem.from_payload(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"judge pack item is invalid: {exc}") from exc
        if tuple(item.visible_payload) != _VISIBLE_FIELDS:
            raise ValueError("judge pack visible fields differ from the exact allowlist")
        parsed.append(item)
    expected = items_for_coder(bundle, contract.coder_id)
    if len(expected) != EXPECTED_JUDGE_ITEM_COUNT:
        raise ValueError(
            f"bundle-derived judge item count must be exactly {EXPECTED_JUDGE_ITEM_COUNT}"
        )
    if [item.to_payload() for item in parsed] != [item.to_payload() for item in expected]:
        raise ValueError("judge pack item identity, content, or order is not an exact bundle match")
    return contract.coder_id, contract.record_hash, expected


def _validate_index(
    bundle: SemanticReviewBundle,
    index: dict[str, object],
    *,
    coder_id: str,
    pack_hash: str,
) -> None:
    _require_exact_fields(
        index,
        {
            "schema_version",
            "review_bundle_hash",
            "packs",
            "calibration_only",
            "formal_parameter_authority",
            "record_hash",
        },
        _INDEX_SCHEMA,
        "judge pack index",
    )
    _require_embedded_hash(index, "judge pack index")
    _require_boundary_flags(index, "judge pack index")
    if index["review_bundle_hash"] != bundle.record_hash:
        raise ValueError("judge pack index review bundle hash differs from the bundle")
    if type(index["packs"]) is not list or len(index["packs"]) != 1:
        raise ValueError("judge pack index must contain exactly one judge pack")
    entry = index["packs"][0]
    if type(entry) is not dict or set(entry) != {"coder_id", "filename", "record_hash"}:
        raise ValueError("judge pack index entry fields do not match the exact contract")
    if entry["coder_id"] != coder_id or entry["record_hash"] != pack_hash:
        raise ValueError("judge pack index coder or pack hash differs from the approved judge pack")
    if type(entry["filename"]) is not str or not entry["filename"]:
        raise ValueError("judge pack index filename must be explicit text")
    filename = Path(entry["filename"])
    windows_filename = PureWindowsPath(entry["filename"])
    if (
        filename.name != entry["filename"]
        or filename.is_absolute()
        or windows_filename.is_absolute()
        or windows_filename.drive
        or "/" in entry["filename"]
        or "\\" in entry["filename"]
        or entry["filename"] in {".", ".."}
    ):
        raise ValueError("judge pack index filename must not escape its source directory")


@dataclass(frozen=True, slots=True)
class JudgeMaterialization:
    """Hash-bound receipt for a runner-only judge pack and index."""

    review_bundle_hash: str
    export_hash: str
    policy_hash: str
    coder_id: str
    coder_contract_hash: str
    pack_hash: str
    index_hash: str
    pack_file_sha256: str
    index_file_sha256: str
    item_count: int
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-materialization.v1"

    def __post_init__(self) -> None:
        for name in (
            "review_bundle_hash",
            "export_hash",
            "policy_hash",
            "coder_contract_hash",
            "pack_hash",
            "index_hash",
            "pack_file_sha256",
            "index_file_sha256",
            "record_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if type(self.coder_id) is not str or not self.coder_id:
            raise ValueError("materialization coder_id must be explicit text")
        if (
            type(self.item_count) is not int
            or isinstance(self.item_count, bool)
            or self.item_count < 1
        ):
            raise ValueError("materialization item_count must be a positive integer")
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("judge materialization record hash differs from content")

    @property
    def metadata(self) -> dict[str, object]:
        return dict(_METADATA)

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA,
            **{
                field.name: getattr(self, field.name)
                for field in fields(self)
                if field.name != "record_hash"
            },
            "metadata": self.metadata,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(
        cls,
        *,
        bundle: SemanticReviewBundle,
        coder_id: str,
        coder_contract_hash: str,
        pack_hash: str,
        index_hash: str,
        pack_bytes: bytes,
        index_bytes: bytes,
        item_count: int,
    ) -> JudgeMaterialization:
        values = {
            "review_bundle_hash": bundle.record_hash,
            "export_hash": bundle.review_export.export_hash,
            "policy_hash": bundle.policy.record_hash,
            "coder_id": coder_id,
            "coder_contract_hash": coder_contract_hash,
            "pack_hash": pack_hash,
            "index_hash": index_hash,
            "pack_file_sha256": hashlib.sha256(pack_bytes).hexdigest(),
            "index_file_sha256": hashlib.sha256(index_bytes).hexdigest(),
            "item_count": item_count,
        }
        content = {"schema_version": cls._SCHEMA, **values, "metadata": dict(_METADATA)}
        return cls(**values, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> JudgeMaterialization:
        expected = {field.name for field in fields(cls)} | {"schema_version", "metadata"}
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("judge materialization fields do not match the exact contract")
        if payload["schema_version"] != cls._SCHEMA:
            raise ValueError("judge materialization schema version is unsupported")
        metadata = payload["metadata"]
        if (
            type(metadata) is not dict
            or set(metadata) != set(_METADATA)
            or any(
                type(metadata[name]) is not type(expected) for name, expected in _METADATA.items()
            )
            or metadata != _METADATA
        ):
            raise ValueError("judge materialization metadata must remain calibration-only")
        return cls(**{field.name: payload[field.name] for field in fields(cls)})  # type: ignore[arg-type]


_Identity = tuple[int, int]


def _stable_identity(stat_result: os.stat_result) -> _Identity | None:
    """Return an object identity; inode zero fails closed instead of using time metadata."""

    inode = int(stat_result.st_ino)
    if inode == 0:
        return None
    return int(stat_result.st_dev), inode


def _is_link_or_reparse(path: Path) -> bool:
    try:
        stat_result = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(stat_result.st_mode) or path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    return bool(getattr(stat_result, "st_file_attributes", 0) & 0x400)


def _safe_identity(path: Path, kind: str) -> _Identity | None:
    try:
        stat_result = os.lstat(path)
    except OSError:
        return None
    if _is_link_or_reparse(path):
        return None
    if kind == "directory" and not stat.S_ISDIR(stat_result.st_mode):
        return None
    if kind == "file" and not stat.S_ISREG(stat_result.st_mode):
        return None
    return _stable_identity(stat_result)


def _existing_ancestors_are_safe(path: Path) -> None:
    current = path.parent
    while True:
        if current.exists() and _is_link_or_reparse(current):
            raise ValueError("output path must not traverse a symlink")
        parent = current.parent
        if parent == current:
            return
        current = parent


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


def _unlink_owned_file(
    path: Path,
    identity: _Identity,
    parent_identity: _Identity | None = None,
    *,
    directory_fd: int | None = None,
) -> bool:
    """Unlink only by a held POSIX directory/file handle; otherwise quarantine."""

    if os.name == "posix":
        owns_directory_fd = directory_fd is None
        if owns_directory_fd:
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
            try:
                directory_fd = os.open(path.parent, directory_flags)
            except OSError:
                return False
        try:
            assert directory_fd is not None
            if (
                parent_identity is not None
                and _stable_identity(os.fstat(directory_fd)) != parent_identity
            ):
                return False
            file_flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_NOFOLLOW
            try:
                file_fd = os.open(path.name, file_flags, dir_fd=directory_fd)
            except OSError:
                return False
            try:
                if _stable_identity(os.fstat(file_fd)) != identity:
                    return False
                unlinkat = getattr(ctypes.CDLL(None, use_errno=True), "unlinkat", None)
                if unlinkat is None:
                    return False
                unlinkat.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
                unlinkat.restype = ctypes.c_int
                if unlinkat(file_fd, b"", 0x1000) == 0:  # AT_EMPTY_PATH
                    return True
                return False
            finally:
                os.close(file_fd)
        finally:
            if owns_directory_fd:
                os.close(directory_fd)

    # Windows has no portable handle-relative unlink API in the standard library.
    # Keep the private staging tree as quarantine rather than risking a path race.
    return False


def _write_bytes_create_only(path: Path, content: bytes) -> _Identity:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor: int | None = None
    directory_fd: int | None = None
    parent_identity: _Identity | None = None
    identity: _Identity | None = None
    try:
        if os.name == "posix":
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
            directory_fd = os.open(path.parent, directory_flags)
            parent_identity = _stable_identity(os.fstat(directory_fd))
            if parent_identity is None:
                raise ValueError("staging parent has no stable object identity")
            descriptor = os.open(
                path.name,
                flags | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
        else:
            descriptor = os.open(path, flags, 0o600)
        stat_result = os.fstat(descriptor)
        identity = _stable_identity(stat_result)
        if identity is None:
            raise ValueError("created file has no stable object identity")
        written = os.write(descriptor, content)
        if written != len(content):
            raise OSError("short write while materializing judge view")
        os.fsync(descriptor)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if identity is not None:
            if directory_fd is None:
                _unlink_owned_file(path, identity, parent_identity)
            else:
                _unlink_owned_file(
                    path,
                    identity,
                    parent_identity,
                    directory_fd=directory_fd,
                )
        if directory_fd is not None:
            os.close(directory_fd)
        raise
    else:
        assert descriptor is not None and identity is not None
        os.close(descriptor)
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
    if directory_fd is not None:
        os.close(directory_fd)
    return identity


def _rollback_materialization(
    staging_root: Path,
    parent_identity: _Identity | None,
    staging_identity: _Identity | None,
    created_files: list[tuple[Path, _Identity]],
) -> None:
    """Remove only a private staging tree proven to belong to this invocation."""

    if parent_identity is None or staging_identity is None:
        return
    if _safe_identity(staging_root.parent, "directory") != parent_identity:
        return
    if _safe_identity(staging_root, "directory") != staging_identity:
        return
    for path, identity in reversed(created_files):
        if not _unlink_owned_file(path, identity, staging_identity):
            return
    if _safe_identity(staging_root, "directory") != staging_identity:
        return
    if not _rmdir_owned_directory(staging_root, parent_identity, staging_identity):
        return
    if _safe_identity(staging_root.parent, "directory") == parent_identity:
        _fsync_directory(staging_root.parent)


def _rmdir_owned_directory(path: Path, parent_identity: _Identity, identity: _Identity) -> bool:
    """Remove an empty owned directory relative to a held parent handle."""

    if os.name != "posix":
        return False
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    try:
        parent_fd = os.open(path.parent, directory_flags)
    except OSError:
        return False
    try:
        if _stable_identity(os.fstat(parent_fd)) != parent_identity:
            return False
        try:
            directory_fd = os.open(path.name, directory_flags, dir_fd=parent_fd)
        except OSError:
            return False
        try:
            if _stable_identity(os.fstat(directory_fd)) != identity:
                return False
            if os.listdir(directory_fd):
                return False
        finally:
            os.close(directory_fd)
        try:
            os.rmdir(path.name, dir_fd=parent_fd)
        except OSError:
            return False
        return True
    finally:
        os.close(parent_fd)


def _make_staging_directory(parent: Path, name: str) -> tuple[Path, _Identity]:
    """Create a private high-entropy sibling directory without following links."""

    if os.name == "posix":
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        try:
            parent_fd = os.open(parent, directory_flags)
        except OSError:
            raise ValueError("staging parent must be a real directory") from None
        try:
            if _stable_identity(os.fstat(parent_fd)) is None:
                raise ValueError("staging parent has no stable object identity")
            for _ in range(32):
                staging_name = f".{name}.staging-{secrets.token_hex(16)}"
                try:
                    os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    continue
                staging = parent / staging_name
                identity = _safe_identity(staging, "directory")
                if identity is None:
                    raise ValueError("staging directory has no stable non-link identity")
                return staging, identity
        finally:
            os.close(parent_fd)
        raise FileExistsError("could not allocate a unique private staging directory")

    for _ in range(32):
        staging = parent / f".{name}.staging-{secrets.token_hex(16)}"
        try:
            staging.mkdir(mode=0o700)
        except FileExistsError:
            continue
        identity = _safe_identity(staging, "directory")
        if identity is None:
            raise ValueError("staging directory has no stable non-link identity")
        return staging, identity
    raise FileExistsError("could not allocate a unique private staging directory")


def _verify_staged_files(
    staging_root: Path,
    staging_identity: _Identity,
    files: tuple[tuple[Path, bytes, _Identity], ...],
) -> None:
    if _safe_identity(staging_root, "directory") != staging_identity:
        raise ValueError("staging directory identity changed")
    if {entry.name for entry in staging_root.iterdir()} != {path.name for path, _, _ in files}:
        raise ValueError("staging inventory is not exact")
    for path, expected, identity in files:
        if _safe_identity(path, "file") != identity:
            raise ValueError("staged file identity changed")
        actual = path.read_bytes()
        if _safe_identity(path, "file") != identity:
            raise ValueError("staged file identity changed during verification")
        if (
            actual != expected
            or hashlib.sha256(actual).digest() != hashlib.sha256(expected).digest()
        ):
            raise ValueError("staged file bytes or hash changed")


def _rename_directory_no_replace(
    source: Path,
    target: Path,
    expected_parent_identity: _Identity | None = None,
) -> None:
    """Atomically publish a directory while refusing an existing target."""

    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file = kernel32.MoveFileExW
        move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        move_file.restype = ctypes.c_int
        if move_file(str(source), str(target), 0):
            return
        error = ctypes.get_last_error()
        if error in {80, 183}:
            raise FileExistsError(target)
        raise OSError(error, "atomic directory publish failed", target)

    if os.name == "posix":
        if source.parent != target.parent:
            raise ValueError("source and target must share a parent directory")
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        try:
            parent_fd = os.open(source.parent, directory_flags)
        except OSError:
            raise OSError(errno.ENOENT, "publish parent directory is unavailable") from None
        try:
            if (
                expected_parent_identity is not None
                and _stable_identity(os.fstat(parent_fd)) != expected_parent_identity
            ):
                raise ValueError("publish parent directory identity changed")
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                raise OSError(errno.ENOTSUP, "atomic no-replace directory publish is unavailable")
            renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renameat2.restype = ctypes.c_int
            result = renameat2(
                parent_fd,
                os.fsencode(source.name),
                parent_fd,
                os.fsencode(target.name),
                1,
            )
            if result == 0:
                return
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise FileExistsError(target)
            raise OSError(error, "atomic directory publish failed", target)
        finally:
            os.close(parent_fd)
    raise OSError(errno.ENOTSUP, "atomic no-replace directory publish is unavailable")


def materialize_judge_view(
    *,
    bundle: SemanticReviewBundle,
    pack_bytes: bytes,
    index_bytes: bytes,
    approved_pack_hash: str,
    approved_index_hash: str,
    output_root: Path,
) -> JudgeMaterialization:
    """Validate approved evidence and create a byte-identical, judge-only directory."""

    if type(bundle) is not SemanticReviewBundle:
        raise TypeError("bundle must be a SemanticReviewBundle")
    SemanticReviewBundle.from_payload(bundle.to_payload())
    _require_sha256("approved_pack_hash", approved_pack_hash)
    _require_sha256("approved_index_hash", approved_index_hash)
    if not isinstance(output_root, Path):
        raise TypeError("output_root must be a Path")
    _existing_ancestors_are_safe(output_root)
    if output_root.exists() or output_root.is_symlink():
        raise FileExistsError("output root already exists or is a symlink")
    parent_identity = _safe_identity(output_root.parent, "directory")
    if parent_identity is None:
        raise ValueError("output root parent must be an existing directory")

    pack = _load_canonical_json(pack_bytes, "judge pack")
    index = _load_canonical_json(index_bytes, "judge pack index")
    coder_id, coder_contract_hash, items = _validate_pack(bundle, pack)
    _validate_index(
        bundle,
        index,
        coder_id=coder_id,
        pack_hash=pack["record_hash"],  # type: ignore[arg-type]
    )
    if pack["record_hash"] != approved_pack_hash:
        raise ValueError("judge pack differs from its owner-approved embedded record hash")
    if index["record_hash"] != approved_index_hash:
        raise ValueError("judge pack index differs from its owner-approved embedded record hash")
    result = JudgeMaterialization.create(
        bundle=bundle,
        coder_id=coder_id,
        coder_contract_hash=coder_contract_hash,
        pack_hash=approved_pack_hash,
        index_hash=approved_index_hash,
        pack_bytes=pack_bytes,
        index_bytes=index_bytes,
        item_count=len(items),
    )

    staging_root: Path | None = None
    staging_identity: _Identity | None = None
    created_files: list[tuple[Path, _Identity]] = []
    try:
        staging_root, staging_identity = _make_staging_directory(
            output_root.parent, output_root.name
        )
        if _safe_identity(output_root.parent, "directory") != parent_identity:
            raise ValueError("output root parent directory identity changed")

        files = (
            (staging_root / "judge-pack.json", pack_bytes),
            (staging_root / "index.json", index_bytes),
            (staging_root / "materialization.json", _canonical_bytes(result.to_payload())),
        )
        for path, content in files:
            if _safe_identity(staging_root, "directory") != staging_identity:
                raise ValueError("staging directory identity changed")
            if _safe_identity(staging_root.parent, "directory") != parent_identity:
                raise ValueError("output root parent directory identity changed")
            created_files.append((path, _write_bytes_create_only(path, content)))  # type: ignore[arg-type]
        staged = tuple(
            (path, content, identity)
            for (path, content), (_, identity) in zip(files, created_files)
        )
        _verify_staged_files(staging_root, staging_identity, staged)
        _fsync_directory(staging_root)
        if _safe_identity(output_root.parent, "directory") != parent_identity:
            raise ValueError("output root parent directory identity changed before publish")
        if output_root.exists() or _is_link_or_reparse(output_root):
            raise FileExistsError("output root appeared before publish")
        _rename_directory_no_replace(staging_root, output_root, parent_identity)
        staging_root = None
        published_identity = _safe_identity(output_root, "directory")
        if published_identity != staging_identity:
            raise ValueError("published output directory identity changed")
        published_files = tuple(
            (output_root / path.name, content, identity) for path, content, identity in staged
        )
        _verify_staged_files(output_root, published_identity, published_files)
        _fsync_directory(output_root.parent)
        if _safe_identity(output_root, "directory") != published_identity:
            raise ValueError("published output directory identity changed before return")
        if _safe_identity(output_root.parent, "directory") != parent_identity:
            raise ValueError("output root parent directory identity changed before return")
    except BaseException:
        if staging_root is not None:
            _rollback_materialization(
                staging_root, parent_identity, staging_identity, created_files
            )
        raise
    return result


__all__ = ["EXPECTED_JUDGE_ITEM_COUNT", "JudgeMaterialization", "materialize_judge_view"]
