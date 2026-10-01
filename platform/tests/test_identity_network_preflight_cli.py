"""Portable full-evidence requests, synthetic HTTP/procfs and real tiny Git."""

import json

import pytest

from test_identity_network_preflight import joined_evidence  # noqa: F401
from test_identity_network_source_bundle import bundle  # noqa: F401
from test_identity_network_service_live import proc_fixture  # noqa: F401


def test_portable_preflight_roundtrip_and_file_cli(joined_evidence, monkeypatch, tmp_path, capsys):  # noqa: F811
    from agent_ex.identity_network import preflight, preflight_cli, service_health

    kwargs = {k: joined_evidence[k] for k in ("auth", "receipt", "evidence")}
    request = preflight_cli.build_preflight_request(**kwargs)
    cold = preflight_cli.parse_preflight_request(json.loads(json.dumps(request)))
    from agent_ex.calibration.environment import EnvironmentLock

    assert cold["auth"] == kwargs["auth"]
    assert cold["receipt"] == kwargs["receipt"]
    for key in ("candidate", "source_pack", "preregistration", "bridge"):
        assert cold["evidence"][key] == kwargs["evidence"][key]
    before = kwargs["evidence"]["service_evidence"]
    after = cold["evidence"]["service_evidence"]
    assert {k: v for k, v in before.items() if k != "current_observation"} == {
        k: v for k, v in after.items() if k != "current_observation"
    }
    assert EnvironmentLock.create(
        before["current_observation"], authorization_hash=before["intent"].output_hash
    ) == EnvironmentLock.create(
        after["current_observation"], authorization_hash=after["intent"].output_hash
    )
    path = tmp_path / "preflight.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    monkeypatch.setattr(preflight, "_utcnow", lambda: "2026-10-01T00:05:00Z")
    monkeypatch.setattr(service_health, "_read_health", lambda: b"health body must not appear")
    assert (
        preflight_cli.main(
            [
                "--request",
                str(path),
                "--bundle",
                str(joined_evidence["bundle_path"]),
                "--runtime-repo",
                str(joined_evidence["runtime_repo"]),
            ]
        )
        == 0
    )
    result = capsys.readouterr()
    assert not result.err
    assert "health body must not appear" not in result.out
    assert json.loads(result.out)["payload"]["dispatch_authorized"] is False
    # Fresh process receives no monkeypatches; wrong scoped target must refuse
    # before any Linux observation or health request on either host OS.
    import os
    import subprocess
    import sys
    from agent_ex.identity_network.launch import StudyApprovalReceipt

    request["receipt"] = StudyApprovalReceipt.create(
        target_hash="f" * 64,
        scope="diagnostic_dispatch",
        researcher="Synthetic",
        approved_at="2026-10-01T00:04:00Z",
    ).to_payload()
    path.write_text(json.dumps(request), encoding="utf-8")
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_ex.identity_network.preflight_cli",
            "--request",
            str(path),
            "--bundle",
            str(joined_evidence["bundle_path"]),
            "--runtime-repo",
            str(joined_evidence["runtime_repo"]),
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 2
    assert not child.stdout
    assert "ValueError" in child.stderr
    assert "Traceback" not in child.stderr


def test_portable_reader_rejects_extra_fields_and_rehashed_current_auth(joined_evidence):  # noqa: F811
    from agent_ex.domain import canonical_payload_hash
    from agent_ex.identity_network import preflight_cli

    kwargs = {k: joined_evidence[k] for k in ("auth", "receipt", "evidence")}
    original = preflight_cli.build_preflight_request(**kwargs)
    for target in ("root", "evidence", "service", "current"):
        request = json.loads(json.dumps(original))
        if target == "root":
            request["dispatch_authorized"] = True
        elif target == "evidence":
            request["evidence"]["cached_health"] = {}
        elif target == "service":
            request["evidence"]["service_evidence"]["packet"] = request["evidence"]["candidate"]
        else:
            lock = request["evidence"]["service_evidence"]["current_environment"]
            lock["authorization_hash"] = "f" * 64
            lock["record_hash"] = canonical_payload_hash(
                {k: v for k, v in lock.items() if k != "record_hash"}
            )
        with pytest.raises(ValueError):
            preflight_cli.parse_preflight_request(request)


def test_cli_rejects_duplicate_json_without_health(tmp_path, capsys, monkeypatch):
    from agent_ex.identity_network import preflight_cli, service_health

    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"wrong","schema_version":"wrong"}')

    def forbidden():
        pytest.fail("malformed JSON must not reach HTTP")

    monkeypatch.setattr(service_health, "_read_health", forbidden)
    assert (
        preflight_cli.main(
            [
                "--request",
                str(path),
                "--bundle",
                "unused",
                "--runtime-repo",
                "unused",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert not output.out
    assert "wrong" not in output.err
