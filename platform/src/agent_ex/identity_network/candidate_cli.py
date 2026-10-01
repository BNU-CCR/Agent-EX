"""Portable candidate-only preparation. No run, transport or service operations.

Preparation persists its source plan before creating any databases. Interrupted
work is retained. Resume requires exactly the original request; check is read-only.
Paths reject symlinks/reparse points, but this is not a hostile-directory sandbox.
"""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, canonical_payload_hash
from .candidate import validate_six_cell_candidate
from .dispatch import _strict_json
from .initialization import (
    build_initial_manifests,
    initialize_candidate_family,
    verify_initialized_candidate_family,
)
from .storage import StudyRunStorage


REQUEST_SCHEMA = "paper1.identity-network.prepare-request.v1"
PLAN_SCHEMA = "paper1.identity-network.preparation-plan.v1"
MAX_BYTES = 32 * 1024 * 1024


def _safe_path(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("candidate paths cannot traverse symlink/reparse points")
    return path


def _read(path):
    path = _safe_path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("bounded regular JSON file required")
        content = source.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("JSON reader bound exceeded")
    return _strict_json(content.decode("utf-8"))


def _plan(request):
    if (
        type(request) is not dict
        or set(request) != {"schema_version", "candidate", "context"}
        or request["schema_version"] != REQUEST_SCHEMA
        or type(request["context"]) is not dict
    ):
        raise ValueError("exact candidate preparation request required")
    if request["context"].get("authorization_hash") is not None:
        raise ValueError("candidate CLI cannot accept launch authority")
    packet = ArtifactEnvelope.from_payload(request["candidate"])
    bindings = validate_six_cell_candidate(packet)
    manifests = build_initial_manifests(packet, **request["context"])
    plan = ArtifactEnvelope.create(
        artifact_type="sis-preparation-plan",
        schema_version=PLAN_SCHEMA,
        algorithm_id="sis-candidate-archive-layout",
        algorithm_version="1.0.0",
        input_hashes={
            "candidate": packet.output_hash,
            "context": canonical_payload_hash(request["context"]),
        },
        rng_provenance=(),
        payload={
            "request": request,
            "cells": tuple(
                {
                    "cell_id": b.cell.cell_id,
                    "database": b.cell.cell_id + ".sqlite",
                    "manifest": m.to_payload(),
                }
                for b, m in zip(bindings, manifests, strict=True)
            ),
        },
    )
    return packet, bindings, manifests, plan


def _stored_plan(root):
    stored = ArtifactEnvelope.from_payload(_read(root / "preparation.json"))
    result = _plan(_json_ready(stored.payload)["request"])
    if result[-1] != stored:
        raise ValueError("preparation plan differs from source replay")
    return result


def _check_layout(root, bindings):
    allowed = {"preparation.json"}
    for binding in bindings:
        name = binding.cell.cell_id + ".sqlite"
        allowed.update((name, name + ".lease", name + "-wal", name + "-shm"))
    for entry in root.iterdir():
        _safe_path(entry)
        if entry.name not in allowed or not entry.is_file():
            raise ValueError("unexpected file in candidate archive")


def _write_plan(path, plan):
    content = json.dumps(
        plan.to_payload(), sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if len(content) > MAX_BYTES:
        raise ValueError("preparation plan exceeds reader bound")
    with path.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Candidate-only SIS archive preparation (no model calls)"
    )
    parser.add_argument("command", choices=("prepare", "resume-init", "check-initial"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args(argv)
    try:
        root = _safe_path(args.root)
        if args.command == "check-initial":
            if args.request is not None:
                raise ValueError("check reads only the stored plan")
            packet, bindings, manifests, plan = _stored_plan(root)
        else:
            if args.request is None:
                raise ValueError("explicit preparation request required")
            packet, bindings, manifests, plan = _plan(_read(args.request))
            if args.command == "prepare":
                if root.exists() or not root.parent.is_dir():
                    raise ValueError("fresh child directory with existing parent required")
                # Validate serializability/reader bound before filesystem mutation.
                if (
                    len(json.dumps(plan.to_payload(), ensure_ascii=False).encode("utf-8"))
                    > MAX_BYTES
                ):
                    raise ValueError("preparation plan exceeds reader bound")
                root.mkdir()
                _write_plan(root / "preparation.json", plan)
            elif _stored_plan(root)[-1] != plan:
                raise ValueError("resume request must equal the stored preparation plan")
        _check_layout(root, bindings)
        with ExitStack() as stack:
            stores = []
            for manifest, binding in zip(manifests, bindings, strict=True):
                path = _safe_path(root / (binding.cell.cell_id + ".sqlite"))
                if path.exists():
                    store = StudyRunStorage.open(
                        path, manifest=manifest, **binding.storage_arguments()
                    )
                elif args.command != "check-initial":
                    store = StudyRunStorage.create(
                        path, manifest=manifest, **binding.storage_arguments()
                    )
                else:
                    raise ValueError("candidate archive lacks a database")
                stack.callback(store.close)
                if args.command != "check-initial":
                    stack.enter_context(store.acquire_run_lease())
                stores.append(store)
            report = (
                verify_initialized_candidate_family
                if args.command == "check-initial"
                else initialize_candidate_family
            )(packet, stores=tuple(stores))
        print(json.dumps(report.to_payload(), sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, sqlite3.Error):
        print(
            "SIS candidate preparation failed; evidence retained, no report emitted.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
