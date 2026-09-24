"""The destination judge store must match every source entry, not a selected list."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil

import pytest

from agent_ex.phase0b.archive_copy import inventory_tree, verify_tree_copy
import agent_ex.phase0b.archive_copy as archive_copy


def _source_copy(tmp_path):
    source = tmp_path / "source"
    (source / "staging" / "journal").mkdir(parents=True)
    (source / "staging" / "empty").mkdir()
    (source / "staging" / "manifest.json").write_bytes(b'{"manifest":true}')
    (source / "staging" / "journal" / "0001.json").write_bytes(b'{"sequence":1}')
    destination = tmp_path / "destination"
    shutil.copytree(source, destination)
    return source, destination


def test_inventory_includes_all_regular_files_and_empty_directories(tmp_path) -> None:
    source, destination = _source_copy(tmp_path)

    inventory = inventory_tree(source)
    assert inventory.directories == ("staging", "staging/empty", "staging/journal")
    assert inventory.files == (
        ("staging/journal/0001.json", 14, hashlib.sha256(b'{"sequence":1}').hexdigest()),
        ("staging/manifest.json", 17, hashlib.sha256(b'{"manifest":true}').hexdigest()),
    )
    assert verify_tree_copy(source, destination).record_hash == inventory.record_hash


@pytest.mark.parametrize("change", ["bytes", "missing", "extra_file", "extra_directory"])
def test_tree_copy_rejects_any_changed_or_missing_entry(tmp_path, change: str) -> None:
    source, destination = _source_copy(tmp_path)
    if change == "bytes":
        (destination / "staging" / "manifest.json").write_bytes(b'{"manifest":false}')
    elif change == "missing":
        (destination / "staging" / "journal" / "0001.json").unlink()
    elif change == "extra_file":
        (destination / "staging" / "unexpected.json").write_bytes(b"{}")
    else:
        (destination / "staging" / "unexpected").mkdir()

    with pytest.raises(ValueError, match="tree|inventory|copy"):
        verify_tree_copy(source, destination)


def test_inventory_rejects_linked_root_or_child(tmp_path) -> None:
    source, destination = _source_copy(tmp_path)
    link = tmp_path / "linked"
    try:
        link.symlink_to(source, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory links are unavailable on this host")
    with pytest.raises(ValueError, match="link"):
        inventory_tree(link)

    child_link = destination / "staging" / "linked-manifest.json"
    child_link.symlink_to(source / "staging" / "manifest.json")
    with pytest.raises(ValueError, match="link"):
        inventory_tree(destination)


def test_inventory_rejects_windows_directory_junction(tmp_path, monkeypatch) -> None:
    source, _ = _source_copy(tmp_path)
    original = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path.name == "empty" or original(path),
    )
    with pytest.raises(ValueError, match="link|junction"):
        inventory_tree(source)


def test_inventory_rejects_file_replaced_between_listing_and_read(tmp_path, monkeypatch) -> None:
    source, _ = _source_copy(tmp_path)
    original = archive_copy._hash_regular_file
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b'{"manifest":false}')

    def swap_then_hash(path):
        if path.name == "manifest.json":
            os.replace(replacement, path)
        return original(path)

    monkeypatch.setattr(archive_copy, "_hash_regular_file", swap_then_hash)
    with pytest.raises(ValueError, match="changed|identity"):
        inventory_tree(source)
