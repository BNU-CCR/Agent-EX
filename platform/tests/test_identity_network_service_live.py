"""Synthetic procfs fixtures: not observations from AutoDL or real vLLM."""

import hashlib

import pytest

from agent_ex.domain import canonical_payload_hash
from test_phase0b_service_bridge import _fixture


def stat_line(pid, tick, state="S"):
    # comm can contain spaces and right parentheses; field22 is offset19 after it.
    fields = [state] + ["0"] * 18 + [tick] + ["0"] * 8
    return f"{pid} (vllm worker ) name) " + " ".join(fields)


def tcp_line(address="0100007F:1F40", inode="9001"):
    return f"0: {address} 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 {inode}\n"


@pytest.fixture
def proc_fixture(tmp_path, monkeypatch):
    from agent_ex.identity_network import service_live as live

    root = tmp_path / "proc"
    pid = 123
    directory = root / str(pid)
    (directory / "fd").mkdir(parents=True)
    (directory / "ns").mkdir()
    (root / "self" / "ns").mkdir(parents=True)
    (root / "sys" / "kernel" / "random").mkdir(parents=True)
    (root / "net").mkdir()
    (root / "sys" / "kernel" / "random" / "boot_id").write_text(
        "11111111-2222-3333-4444-555555555555\n"
    )
    command = b"/opt/env/bin/python\0-m\0vllm.entrypoints.openai.api_server\0"
    start = {
        **_fixture()["new_start"],
        "pid": pid,
        "proc_start_time": "567",
        "executable": "/opt/env/bin/python",
        "cmdline_sha256": hashlib.sha256(command).hexdigest(),
    }
    start["record_hash"] = canonical_payload_hash(
        {k: v for k, v in start.items() if k != "record_hash"}
    )
    (directory / "stat").write_text(stat_line(pid, "567"))
    (directory / "cmdline").write_bytes(command)
    # Mock only readlink boundary because Windows cannot create proc-style links.
    links = {
        directory / "exe": start["executable"],
        directory / "ns" / "net": "net:[10]",
        root / "self" / "ns" / "net": "net:[10]",
        directory / "fd" / "3": "socket:[9001]",
    }
    (directory / "fd" / "3").touch()
    (root / "net" / "tcp").write_text("header\n" + tcp_line())
    (root / "net" / "tcp6").write_text("header\n")
    monkeypatch.setattr(live, "_PROC_ROOT", root)
    monkeypatch.setattr(live, "_PLATFORM", "linux")
    monkeypatch.setattr(live, "_hostname", lambda: "synthetic-container")
    monkeypatch.setattr(live, "_utcnow", lambda: "2026-10-01T00:03:00Z")
    monkeypatch.setattr(live, "_readlink", lambda path: links[path])
    return live, root, start, links


def test_observed_service_identity_binds_process_namespace_and_owned_loopback(proc_fixture):
    live, _, start, _ = proc_fixture
    host = live.observe_linux_host()
    result = live.observe_linux_service(
        start, expected_host_identity_hash=host.payload["host_identity_hash"]
    )
    assert result.input_hashes["service_start"] == start["record_hash"]
    assert result.payload["pid"] == 123
    assert result.payload["proc_start_time"] == "567"
    assert result.payload["loopback_listener_owned"] is True
    assert result.payload["dispatch_authorized"] is False
    assert "synthetic-container" not in str(result.to_payload())


@pytest.mark.parametrize(
    "change", ["reused", "zombie", "cmdline", "exe", "wildcard", "foreign_owner", "netns", "boot"]
)
def test_live_service_refuses_identity_and_listener_drift(proc_fixture, change):
    live, root, start, links = proc_fixture
    host_hash = live.observe_linux_host().payload["host_identity_hash"]
    pid = root / "123"
    if change in ("reused", "zombie"):
        (pid / "stat").write_text(
            stat_line(
                123, "568" if change == "reused" else "567", "Z" if change == "zombie" else "S"
            )
        )
    elif change == "cmdline":
        (pid / "cmdline").write_bytes(b"other\0")
    elif change == "exe":
        links[pid / "exe"] = "/foreign/python"
    elif change == "wildcard":
        (root / "net" / "tcp").write_text("header\n" + tcp_line("00000000:1F40"))
    elif change == "foreign_owner":
        links[pid / "fd" / "3"] = "socket:[9002]"
    elif change == "netns":
        links[pid / "ns" / "net"] = "net:[11]"
    else:
        (root / "sys" / "kernel" / "random" / "boot_id").write_text(
            "21111111-2222-3333-4444-555555555555\n"
        )
    with pytest.raises(ValueError, match="live service"):
        live.observe_linux_service(start, expected_host_identity_hash=host_hash)


def test_collector_refuses_non_linux_even_with_valid_fixture(proc_fixture, monkeypatch):
    live, _, start, _ = proc_fixture
    monkeypatch.setattr(live, "_PLATFORM", "win32")
    with pytest.raises(ValueError, match="Linux"):
        live.observe_linux_host()
    with pytest.raises(ValueError, match="live service"):
        live.observe_linux_service(start, expected_host_identity_hash="a" * 64)


def test_live_namespace_must_remain_stable_through_observation(proc_fixture, monkeypatch):
    live, root, start, links = proc_fixture
    host = live.observe_linux_host().payload["host_identity_hash"]
    calls = 0

    def changing_link(path):
        nonlocal calls
        if path == root / "123/ns/net":
            calls += 1
            return "net:[10]" if calls == 1 else "net:[11]"
        return links[path]

    monkeypatch.setattr(live, "_readlink", changing_link)
    with pytest.raises(ValueError, match="live service"):
        live.observe_linux_service(start, expected_host_identity_hash=host)


def test_observation_cli_is_safe_and_read_only_on_supported_platform():
    import json
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "agent_ex.identity_network.service_live", "host"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if sys.platform == "linux":
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["payload"]["dispatch_authorized"] is False
    else:
        assert result.returncode == 2
        assert not result.stdout
        assert "observation refused" in result.stderr
