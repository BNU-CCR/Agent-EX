"""Read-only byte and layout comparison of an external judge archive copy.

This module never copies files or opens raw responses as text. A matching tree
alone is not proof of a complete judge run; the store must also be replayed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

from ..domain import _require_payload_hash, _require_sha256, canonical_payload_hash


_BLOCK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArchiveTreeInventory:
    directories: tuple[str, ...]
    files: tuple[tuple[str, int, str], ...]
    record_hash: str

    def __post_init__(self) -> None:
        if tuple(sorted(set(self.directories))) != self.directories:
            raise ValueError("archive directories must be sorted and unique")
        if tuple(sorted(self.files)) != self.files:
            raise ValueError("archive files must be sorted")
        paths = [path for path, _, _ in self.files]
        if len(set(paths)) != len(paths) or set(paths) & set(self.directories):
            raise ValueError("archive inventory paths must be unique")
        for path, size, digest in self.files:
            _relative_path(path)
            if type(size) is not int or size < 0:
                raise ValueError("archive file size must be nonnegative")
            _require_sha256("archive file sha256", digest)
        for path in self.directories:
            _relative_path(path)
        _require_sha256("archive inventory record_hash", self.record_hash)
        _require_payload_hash(
            "archive inventory record_hash", self.record_hash, self.content_payload()
        )

    def content_payload(self) -> dict[str, object]:
        return {"directories": self.directories, "files": self.files}


def _relative_path(value: str) -> None:
    if (
        type(value) is not str
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("archive inventory path must be a canonical relative POSIX path")


def _hash_regular_file(path: Path) -> tuple[int, str]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("archive entry must remain a regular file")
        digest = hashlib.sha256()
        while block := os.read(descriptor, _BLOCK_SIZE):
            digest.update(block)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("archive file changed while hashing")
        return before.st_size, digest.hexdigest()
    finally:
        os.close(descriptor)


def _entry_identity(entry: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        entry.st_dev,
        entry.st_ino,
        entry.st_mode,
        entry.st_size,
        entry.st_mtime_ns,
        entry.st_ctime_ns,
    )


def inventory_tree(root: Path) -> ArchiveTreeInventory:
    """Inventory every regular file and directory beneath an existing root."""

    if not isinstance(root, Path) or root.is_symlink() or root.is_junction() or not root.is_dir():
        raise ValueError("archive root must be an existing non-link directory")
    directories: list[str] = []
    files: list[tuple[str, int, str]] = []
    root_identity = _entry_identity(root.lstat())

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda entry: entry.name):
            relative = child.relative_to(root).as_posix()
            _relative_path(relative)
            before = child.lstat()
            mode = before.st_mode
            if stat.S_ISLNK(mode) or child.is_junction():
                raise ValueError("archive tree must not contain links or junctions")
            if stat.S_ISDIR(mode):
                directories.append(relative)
                visit(child)
            elif stat.S_ISREG(mode):
                size, digest = _hash_regular_file(child)
                files.append((relative, size, digest))
            else:
                raise ValueError("archive tree contains a non-regular entry")
            if _entry_identity(child.lstat()) != _entry_identity(before):
                raise ValueError("archive entry identity changed during inventory")

    visit(root)
    if _entry_identity(root.lstat()) != root_identity:
        raise ValueError("archive root identity changed during inventory")
    content: dict[str, object] = {
        "directories": tuple(sorted(directories)),
        "files": tuple(sorted(files)),
    }
    return ArchiveTreeInventory(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]


def verify_tree_copy(source: Path, destination: Path) -> ArchiveTreeInventory:
    """Reject a copy with any extra, missing, linked, or changed tree entry."""

    if source == destination or source.resolve() == destination.resolve():
        raise ValueError("archive copy must have a distinct destination")
    source_inventory = inventory_tree(source)
    destination_inventory = inventory_tree(destination)
    if source_inventory != destination_inventory:
        raise ValueError("archive copy tree inventory differs from source")
    return destination_inventory
