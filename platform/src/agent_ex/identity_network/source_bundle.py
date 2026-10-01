"""Verify pinned Git bundle bytes in disposable local storage, never import live.

The prerequisite repository is read-only. Incremental bundles need its actual
base objects. This checks source content, not an upload, human receipt or model.
Directories and the installed Git executable must be trusted by the caller.
"""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

from ..artifacts import ArtifactEnvelope
from ..domain import _require_int, _require_sha256


MAX_BUNDLE_BYTES = 256 * 1024 * 1024


def _git(repo, *arguments, data=None):
    # Do not inherit a redirected git-dir/object-dir or command-line config.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
    )
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), *arguments],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("source bundle Git verification failed") from exc
    return result.stdout


def verify_source_bundle(
    *,
    bundle_bytes,
    expected_commit,
    expected_hash,
    expected_size,
    prerequisite_repo,
):
    """Verify size/hash, advertised commit, real pack and complete reachable tree."""
    _require_sha256("source bundle hash", expected_hash)
    _require_int("source bundle size", expected_size, minimum=1)
    if (
        type(bundle_bytes) is not bytes
        or len(bundle_bytes) != expected_size
        or expected_size > MAX_BUNDLE_BYTES
        or hashlib.sha256(bundle_bytes).hexdigest() != expected_hash
        or type(expected_commit) is not str
        or re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None
    ):
        raise ValueError("source bundle bytes/size/hash/commit mismatch")
    header, separator, pack = bundle_bytes.partition(b"\n\n")
    if (
        not separator
        or not pack.startswith(b"PACK")
        or header.splitlines()[0] not in (b"# v2 git bundle", b"# v3 git bundle")
        or any(
            line.startswith(b"@object-format=") and line != b"@object-format=sha1"
            for line in header.splitlines()
        )
    ):
        raise ValueError("supported SHA-1 Git source bundle required")
    repo = Path(prerequisite_repo).resolve(strict=True)
    prerequisites = tuple(line[1:41] for line in header.splitlines() if line.startswith(b"-"))
    if any(re.fullmatch(rb"[0-9a-f]{40}", commit) is None for commit in prerequisites):
        raise ValueError("source bundle prerequisite identity invalid")
    # Only this newly allocated temporary directory is written or cleaned up.
    with tempfile.TemporaryDirectory(prefix="sis-bundle-verify-") as scratch:
        scratch = Path(scratch)
        pinned = scratch / "source.bundle"
        pinned.write_bytes(bundle_bytes)
        _git(repo, "bundle", "verify", str(pinned))
        heads = _git(repo, "bundle", "list-heads", str(pinned)).decode("utf-8").splitlines()
        if not any(line.split(" ", 1)[0] == expected_commit for line in heads):
            raise ValueError("source bundle does not advertise the exact source commit")
        isolated = scratch / "objects-repo"
        isolated.mkdir()
        _git(isolated, "init", "--bare", "--quiet", "--object-format=sha1")
        if prerequisites:
            # Export only the graph reachable from declared prerequisites. A
            # broad alternate would silently hide objects missing from the pack.
            bases = _git(
                repo,
                "pack-objects",
                "--stdout",
                "--revs",
                "--quiet",
                data=b"\n".join(prerequisites) + b"\n",
            )
            if len(bases) > MAX_BUNDLE_BYTES:
                raise ValueError("source bundle prerequisite graph exceeds verification bound")
            _git(isolated, "index-pack", "--stdin", "--strict", data=bases)
        indexed = _git(
            isolated,
            "index-pack",
            "--stdin",
            "--fix-thin",
            "--strict",
            data=pack,
        )
        pack_id = indexed.strip().split()
        if (
            len(pack_id) != 2
            or pack_id[0] != b"pack"
            or re.fullmatch(rb"[0-9a-f]{40}", pack_id[1]) is None
        ):
            raise ValueError("source bundle imported pack identity invalid")
        index = isolated / "objects" / "pack" / ("pack-" + pack_id[1].decode("ascii") + ".idx")
        contents = _git(isolated, "verify-pack", "-v", str(index)).decode("ascii").splitlines()
        if not any(line.split()[:2] == [expected_commit, "commit"] for line in contents):
            raise ValueError("source bundle does not contain the advertised source commit")
        if _git(isolated, "cat-file", "-t", expected_commit).strip() != b"commit":
            raise ValueError("source bundle head is not a commit")
        _git(isolated, "fsck", "--strict", "--no-reflogs", expected_commit)
        tree = _git(isolated, "rev-parse", expected_commit + "^{tree}")
        tree = tree.decode("ascii").strip()
    if re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        raise ValueError("source bundle tree identity invalid")
    return ArtifactEnvelope.create(
        artifact_type="sis-source-bundle-verification",
        schema_version="paper1.identity-network.source-bundle-verification.v1",
        algorithm_id="sis-isolated-git-pack-source-check",
        algorithm_version="1.0.0",
        input_hashes={"source_bundle": expected_hash},
        rng_provenance=(),
        payload={
            "source_commit": expected_commit,
            "source_tree": tree,
            "source_bundle_size": expected_size,
            "source_bundle_hash": expected_hash,
            "pack_verified": True,
            "reachable_source_verified": True,
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
        },
    )
