"""Synthetic service observations and HTTP transport; no cloud requests."""

import hashlib

import pytest

from test_identity_network_service_live import proc_fixture as linux_proc_fixture, stat_line  # noqa: F401


@pytest.fixture
def proc_fixture(linux_proc_fixture):  # noqa: F811 - pytest injects the imported fixture
    return linux_proc_fixture


def test_health_observation_brackets_transport_with_live_identity(proc_fixture, monkeypatch):
    from agent_ex.identity_network import service_health as health

    live, _, start, _ = proc_fixture
    host = live.observe_linux_host().payload["host_identity_hash"]
    monkeypatch.setattr(health, "_read_health", lambda: b"healthy")
    result = health.observe_service_health(start, expected_host_identity_hash=host)
    assert result.input_hashes["service_start"] == start["record_hash"]
    assert result.payload["response_sha256"] == hashlib.sha256(b"healthy").hexdigest()
    assert result.payload["endpoint"] == "http://127.0.0.1:8000/health"
    assert result.payload["dispatch_authorized"] is False
    assert "healthy" not in str(result.to_payload())


def test_health_refuses_process_change_during_transport(proc_fixture, monkeypatch):
    from agent_ex.identity_network import service_health as health

    live, root, start, _ = proc_fixture
    host = live.observe_linux_host().payload["host_identity_hash"]

    def changed():
        (root / "123" / "stat").write_text(stat_line(123, "568"))
        return b""

    monkeypatch.setattr(health, "_read_health", changed)
    with pytest.raises(ValueError):
        health.observe_service_health(start, expected_host_identity_hash=host)


@pytest.mark.parametrize(
    "status,body",
    [(503, b""), (302, b""), (200, b"x" * 8193)],
    ids=["unhealthy", "redirect", "oversized"],
)
def test_health_transport_rejects_non_200_and_oversized_body(monkeypatch, status, body):
    from agent_ex.identity_network import service_health as health

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def getcode(self):
            return status

        def read(self, limit):
            assert limit == 8193
            return body

    class Opener:
        def open(self, url, timeout):
            assert url == "http://127.0.0.1:8000/health"
            assert timeout == 5
            return Response()

    def build(*handlers):
        assert any(isinstance(h, health.ProxyHandler) and h.proxies == {} for h in handlers)
        redirect = next(h for h in handlers if isinstance(h, health.HTTPRedirectHandler))
        assert redirect.redirect_request(None, None, 302, "", {}, "http://external/") is None
        return Opener()

    monkeypatch.setattr(health, "build_opener", build)
    with pytest.raises(ValueError):
        health._read_health()


def test_health_cli_emits_only_bound_observation(proc_fixture, monkeypatch, tmp_path, capsys):
    import json
    from agent_ex.identity_network import service_health as health

    live, _, start, _ = proc_fixture
    host = live.observe_linux_host().payload["host_identity_hash"]
    path = tmp_path / "start.json"
    path.write_text(json.dumps(start), encoding="utf-8")
    monkeypatch.setattr(health, "_read_health", lambda: b"secret health body")
    assert health.main(["--start", str(path), "--host-identity-hash", host]) == 0
    output = capsys.readouterr().out
    assert "secret health body" not in output
    assert json.loads(output)["payload"]["dispatch_authorized"] is False


def test_health_never_contacts_transport_if_initial_identity_invalid(proc_fixture, monkeypatch):
    from agent_ex.identity_network import service_health as health

    live, root, start, _ = proc_fixture
    host = live.observe_linux_host().payload["host_identity_hash"]
    (root / "123" / "stat").write_text(stat_line(123, "568"))

    def forbidden():
        pytest.fail("invalid service must not reach HTTP")

    monkeypatch.setattr(health, "_read_health", forbidden)
    with pytest.raises(ValueError):
        health.observe_service_health(start, expected_host_identity_hash=host)
