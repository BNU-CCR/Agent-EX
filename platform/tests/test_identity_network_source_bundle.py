"""Real tiny Git bundles, without project code uploads or cloud operations."""

import hashlib
import subprocess

import pytest


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def bundle(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Synthetic Test")
    git(repo, "config", "user.email", "synthetic@example.invalid")
    (repo / "code.txt").write_text("initial\n", encoding="utf-8")
    git(repo, "add", "code.txt")
    git(repo, "commit", "-qm", "initial")
    base = git(repo, "rev-parse", "HEAD")
    full = tmp_path / "full.bundle"
    git(repo, "bundle", "create", str(full), "HEAD")
    (repo / "code.txt").write_text("next\n", encoding="utf-8")
    git(repo, "commit", "-qam", "next")
    commit = git(repo, "rev-parse", "HEAD")
    incremental = tmp_path / "incremental.bundle"
    git(repo, "bundle", "create", str(incremental), f"{base}..HEAD")
    return repo, full.read_bytes(), incremental.read_bytes(), base, commit


@pytest.mark.parametrize("incremental", [False, True])
def test_bundle_verifier_reads_pack_and_exact_commit_without_mutating_source_repo(
    bundle, incremental
):
    from agent_ex.identity_network.source_bundle import verify_source_bundle

    repo, full, delta, base, commit = bundle
    content, expected = (delta, commit) if incremental else (full, base)
    before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    result = verify_source_bundle(
        bundle_bytes=content,
        expected_commit=expected,
        expected_hash=hashlib.sha256(content).hexdigest(),
        expected_size=len(content),
        prerequisite_repo=repo,
    )
    assert result.payload["source_commit"] == expected
    assert result.payload["source_tree"] == git(repo, "rev-parse", expected + "^{tree}")
    assert result.payload["dispatch_authorized"] is False
    assert before == {
        str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("change", ["wrong_commit", "wrong_hash", "wrong_size", "bad_pack"])
def test_bundle_verifier_rejects_wrong_source_or_rehashed_corruption(bundle, change):
    from agent_ex.identity_network.source_bundle import verify_source_bundle

    repo, full, _, base, commit = bundle
    if change == "bad_pack":
        # Header remains valid: bundle verify alone cannot prove pack integrity.
        full = full[:-20] + bytes([full[-20] ^ 1]) + full[-19:]
    with pytest.raises(ValueError):
        verify_source_bundle(
            bundle_bytes=full,
            expected_commit=commit if change == "wrong_commit" else base,
            expected_hash="a" * 64 if change == "wrong_hash" else hashlib.sha256(full).hexdigest(),
            expected_size=len(full) + (1 if change == "wrong_size" else 0),
            prerequisite_repo=repo,
        )


def test_incremental_bundle_requires_actual_base_objects(bundle, tmp_path):
    from agent_ex.identity_network.source_bundle import verify_source_bundle

    _, _, delta, _, commit = bundle
    absent = tmp_path / "absent"
    absent.mkdir()
    git(absent, "init", "-q")
    with pytest.raises(ValueError, match="bundle"):
        verify_source_bundle(
            bundle_bytes=delta,
            expected_commit=commit,
            expected_hash=hashlib.sha256(delta).hexdigest(),
            expected_size=len(delta),
            prerequisite_repo=absent,
        )


def test_incremental_verification_can_read_declared_bases_from_linked_worktree(bundle, tmp_path):
    from agent_ex.identity_network.source_bundle import verify_source_bundle

    repo, _, delta, _, commit = bundle
    worktree = tmp_path / "linked"
    git(repo, "worktree", "add", "--detach", str(worktree), commit)
    result = verify_source_bundle(
        bundle_bytes=delta,
        expected_commit=commit,
        expected_hash=hashlib.sha256(delta).hexdigest(),
        expected_size=len(delta),
        prerequisite_repo=worktree,
    )
    assert result.payload["source_commit"] == commit


@pytest.mark.parametrize("change", ["unrelated_pack", "undeclared_tree"])
def test_correct_header_cannot_use_undeclared_repository_objects_to_cover_wrong_pack(
    bundle, tmp_path, change
):
    from agent_ex.identity_network.source_bundle import verify_source_bundle

    repo, full, _, base, _ = bundle
    header = full.partition(b"\n\n")[0] + b"\n\n"
    if change == "unrelated_pack":
        other = tmp_path / "other"
        other.mkdir()
        git(other, "init", "-q")
        git(
            other,
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "unrelated",
        )
        other_bundle = tmp_path / "other.bundle"
        git(other, "bundle", "create", str(other_bundle), "HEAD")
        pack_bytes = other_bundle.read_bytes().partition(b"\n\n")[2]
    else:
        # Valid pack containing the exact commit but not its tree/blob. No prereqs
        # are declared by this full-bundle header, so a broad alternate masks it.
        pack_bytes = subprocess.run(
            ["git", "-C", str(repo), "pack-objects", "--stdout"],
            input=(base + "\n").encode("ascii"),
            capture_output=True,
            check=True,
        ).stdout
    forged = header + pack_bytes
    with pytest.raises(ValueError, match="bundle"):
        verify_source_bundle(
            bundle_bytes=forged,
            expected_commit=base,
            expected_hash=hashlib.sha256(forged).hexdigest(),
            expected_size=len(forged),
            prerequisite_repo=repo,
        )


def test_standalone_source_cli_checks_exact_approved_bundle_and_emits_only_safe_metadata(
    bundle, tmp_path
):
    import json
    import os
    import sys

    from agent_ex.identity_network.candidate import build_six_cell_candidate
    from agent_ex.identity_network.launch import build_service_launch_intent, StudyApprovalReceipt
    from test_identity_network_candidate import sources
    from test_phase0b_service_bridge import _fixture

    repo, _, delta, _, commit = bundle
    candidate = build_six_cell_candidate(**sources())
    intent = build_service_launch_intent(
        packet=candidate,
        source_commit=commit,
        source_bundle_hash=hashlib.sha256(delta).hexdigest(),
        source_bundle_size=len(delta),
        service_config=_fixture()["service_config"],
        archive_root="/root/autodl-tmp/sis-test-source",
    )
    receipt = StudyApprovalReceipt.create(
        target_hash=intent.output_hash,
        scope="service_start",
        researcher="Synthetic",
        approved_at="2026-10-01T00:00:00Z",
    )
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            dict(
                candidate=candidate.to_payload(),
                intent=intent.to_payload(),
                approval=receipt.to_payload(),
            )
        ),
        encoding="utf-8",
    )
    path = tmp_path / "pinned.bundle"
    path.write_bytes(delta)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_ex.identity_network.source_cli",
            "verify",
            "--request",
            str(request),
            "--bundle",
            str(path),
            "--prerequisite-repo",
            str(repo),
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["payload"]["source_commit"] == commit
    assert evidence["input_hashes"]["intent"] == intent.output_hash
    assert evidence["input_hashes"]["approval"] == receipt.record_hash
    assert "synthetic@example.invalid" not in result.stdout
    assert "next\\n" not in result.stdout
    assert "Adult" not in result.stdout
