"""Portable candidate preparation, real SQLite, no model transport."""

import json
import subprocess
import sys

import pytest

from agent_ex.domain import _json_ready
from test_identity_network_initialization import candidate, context


def request_file(tmp_path):
    packet = candidate()
    request = {
        "schema_version": "paper1.identity-network.prepare-request.v1",
        "candidate": packet.to_payload(),
        "context": context(packet),
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(_json_ready(request)), encoding="utf-8")
    return path


def tree_bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_prepare_check_and_resume_are_portable_and_do_not_overwrite(tmp_path, capsys):
    from agent_ex.identity_network.candidate_cli import main

    request = request_file(tmp_path)
    root = tmp_path / "prepared"
    assert main(["prepare", "--request", str(request), "--root", str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["payload"]["initialized_agents"] == 120
    assert report["payload"]["launch_authorized"] is False
    assert len(list(root.glob("*.sqlite"))) == 6
    before = tree_bytes(root)
    assert main(["prepare", "--request", str(request), "--root", str(root)]) == 2
    capsys.readouterr()
    assert tree_bytes(root) == before
    assert main(["check-initial", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert tree_bytes(root) == before
    assert main(["resume-init", "--request", str(request), "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert tree_bytes(root) == before
    # Module entry point is independently callable, no enclosing Codex process.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_ex.identity_network.candidate_cli",
            "check-initial",
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == report
    assert "Synthetic" not in result.stdout


def test_interrupted_prepare_retains_plan_and_resumes_missing_databases(
    tmp_path, capsys, monkeypatch
):
    from agent_ex.identity_network.candidate_cli import main
    from agent_ex.identity_network.storage import StudyRunStorage

    request = request_file(tmp_path)
    root = tmp_path / "prepared"
    original = StudyRunStorage.create
    calls = []

    def interrupted(*args, **kwargs):
        if len(calls) == 2:
            raise RuntimeError("synthetic interruption")
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(StudyRunStorage, "create", interrupted)
    assert main(["prepare", "--request", str(request), "--root", str(root)]) == 2
    capsys.readouterr()
    assert (root / "preparation.json").is_file()
    assert len(list(root.glob("*.sqlite"))) == 2
    assert main(["check-initial", "--root", str(root)]) == 2
    capsys.readouterr()
    monkeypatch.setattr(StudyRunStorage, "create", original)
    assert main(["resume-init", "--request", str(request), "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["payload"]["initialized_agents"] == 120


@pytest.mark.parametrize("drift", ("unknown", "authorization", "nonce", "duplicate-json"))
def test_bad_request_rejected_without_creating_root(tmp_path, drift, capsys):
    from agent_ex.identity_network.candidate_cli import main

    request = request_file(tmp_path)
    data = json.loads(request.read_text(encoding="utf-8"))
    if drift == "unknown":
        data["unexpected"] = True
    elif drift == "authorization":
        data["context"]["authorization_hash"] = "a" * 64
    elif drift == "nonce":
        data["context"]["launch_nonces"].pop("SIS-A1-B2")
    else:
        request.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
    if drift != "duplicate-json":
        request.write_text(json.dumps(data), encoding="utf-8")
    root = tmp_path / "prepared"
    assert main(["prepare", "--request", str(request), "--root", str(root)]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "Traceback" not in output.err
    assert not root.exists()


def test_resume_changed_request_preserves_evidence(tmp_path, capsys):
    from agent_ex.identity_network.candidate_cli import main

    request = request_file(tmp_path)
    root = tmp_path / "prepared"
    assert main(["prepare", "--request", str(request), "--root", str(root)]) == 0
    capsys.readouterr()
    data = json.loads(request.read_text(encoding="utf-8"))
    data["context"]["launch_nonces"]["SIS-A1-B2"] = "different-explicit-nonce"
    request.write_text(json.dumps(data), encoding="utf-8")
    before = tree_bytes(root)
    assert main(["resume-init", "--request", str(request), "--root", str(root)]) == 2
    capsys.readouterr()
    assert tree_bytes(root) == before


def test_check_incomplete_initial_state_never_completes_it(tmp_path, capsys, monkeypatch):
    from agent_ex.identity_network.candidate_cli import main
    from agent_ex.identity_network.storage import StudyRunStorage

    request = request_file(tmp_path)
    root = tmp_path / "prepared"
    original = StudyRunStorage.initialize_agent
    calls = []

    def interrupted(self, **kwargs):
        if len(calls) == 2:
            raise RuntimeError("synthetic interruption")
        calls.append(kwargs["private_update"].agent_id)
        return original(self, **kwargs)

    monkeypatch.setattr(StudyRunStorage, "initialize_agent", interrupted)
    assert main(["prepare", "--request", str(request), "--root", str(root)]) == 2
    capsys.readouterr()
    before = tree_bytes(root)
    assert main(["check-initial", "--root", str(root)]) == 2
    capsys.readouterr()
    assert tree_bytes(root) == before


@pytest.mark.parametrize("target", ("root", "request"))
def test_symlink_inputs_rejected_without_mutating_target(tmp_path, target, capsys):
    from agent_ex.identity_network.candidate_cli import main

    request = request_file(tmp_path)
    root = tmp_path / "prepared"
    linked = tmp_path / "link"
    actual = request if target == "request" else tmp_path / "outside"
    if target == "root":
        actual.mkdir()
    try:
        linked.symlink_to(actual, target_is_directory=target == "root")
    except OSError:
        pytest.skip("symlink privilege unavailable")
    original = request.read_bytes()
    assert (
        main(
            [
                "prepare",
                "--request",
                str(linked if target == "request" else request),
                "--root",
                str(linked if target == "root" else root),
            ]
        )
        == 2
    )
    capsys.readouterr()
    assert request.read_bytes() == original
    assert not root.exists()
    if target == "root":
        assert list(actual.iterdir()) == []
