"""Platform-neutral contract tests for the reviewed Phase 0A-1 cloud scripts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


PLATFORM_ROOT = Path(__file__).parents[1]
SCRIPTS = PLATFORM_ROOT / "scripts"
PROXY_NAMES = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "all_proxy",
)


def _script(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def _python_block(script: str, occurrence: int = 0) -> str:
    blocks = script.split("<<'PY'\n")[1:]
    return blocks[occurrence].split("\nPY", 1)[0]


def test_download_script_has_only_fixed_modes_and_scoped_network_turbo() -> None:
    script = _script("phase0a1-download.sh")

    assert 'case "$mode" in' in script
    assert "packages)" in script
    assert "model)" in script
    assert script.count("source /etc/network_turbo") == 1
    assert "(" in script[: script.index("source /etc/network_turbo")]
    assert "trap cleanup EXIT" in script
    for signal in ("HUP", "INT", "TERM"):
        assert "trap 'signal_exit" in script
        assert signal in script
    for name in PROXY_NAMES:
        assert name in script
    assert "[Pp][Rr][Oo][Xx][Yy]" in script
    assert '"vllm==0.23.0"' in script
    assert "Qwen/Qwen3-8B" in script
    assert "b968826d9c46dd6066d109eabc6255188de91218" in script
    assert "hashlib.sha256" in script
    assert "paper1.calibration.wheel-manifest.v1" in script
    assert '"wheel_entries"' in script
    assert '"official-cuda-12.9"' in script
    assert '"record_hash"' in script
    assert "SHA256SUMS" not in script
    assert "HF_TOKEN" not in script


def test_download_manifest_and_install_verifier_share_canonical_json_contract(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    vllm_wheel = wheelhouse / "vllm-0.23.0+cu129-py3-none-any.whl"
    dependency_wheel = wheelhouse / "idna-3.10-py3-none-any.whl"
    vllm_wheel.write_bytes(b"vllm")
    dependency_wheel.write_bytes(b"dependency")

    generated = subprocess.run(
        [sys.executable, "-", str(wheelhouse)],
        input=_python_block(_script("phase0a1-download.sh")),
        text=True,
        capture_output=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr
    manifest_path = wheelhouse / "wheel-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(payload) == {"schema_version", "wheel_entries", "record_hash"}
    assert [entry["name"] for entry in payload["wheel_entries"]] == ["idna", "vllm"]
    assert payload["wheel_entries"][1]["version"] == "0.23.0"
    assert payload["wheel_entries"][1]["source"] == "official-cuda-12.9"
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    encoded = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    assert payload["record_hash"] == hashlib.sha256(encoded).hexdigest()

    verified = subprocess.run(
        [sys.executable, "-", str(wheelhouse), str(manifest_path), payload["record_hash"]],
        input=_python_block(_script("phase0a1-install.sh")),
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr

    vllm_wheel.write_bytes(b"tampered")
    rejected = subprocess.run(
        [sys.executable, "-", str(wheelhouse), str(manifest_path), payload["record_hash"]],
        input=_python_block(_script("phase0a1-install.sh")),
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "wheel content hash mismatch" in rejected.stderr


def test_install_script_is_offline_hash_checked_and_fresh_environment_only() -> None:
    script = _script("phase0a1-install.sh")
    folded = script.casefold()

    assert '[[ "$#" -eq 5 ]]' in script
    assert "WHEEL_MANIFEST_SHA256" in script
    assert "paper1.calibration.wheel-manifest.v1" in script
    assert "wheel manifest record hash mismatch" in script
    assert "wheel manifest fields are not exact" in script
    assert "--no-index" in script
    assert "--find-links" in script
    assert '"vllm==0.23.0"' in script
    assert "pip check" in script
    assert "sys.version_info[:2] == (3, 12)" in script
    assert "torch.__file__" in script
    assert "source /etc/network_turbo" not in script
    assert "index-url" not in folded
    assert "extra-index" not in folded
    assert "http://" not in folded and "https://" not in folded


def test_serve_script_rejects_every_proxy_name_immediately_before_exec() -> None:
    script = _script("phase0a1-serve.sh")
    exec_offset = script.index('exec "$vllm_executable"')
    guard_offset = script.rindex("proxy", 0, exec_offset)

    assert guard_offset < exec_offset
    assert "${!" in script and "[Pp][Rr][Oo][Xx][Yy]" in script
    assert "exit 2" in script[guard_offset - 500 : exec_offset]
    assert "compgen -e" in script


def test_service_script_exposes_only_two_generations_and_strict_modes() -> None:
    script = _script("phase0a1-service.sh")

    assert 'case "$mode" in' in script
    for mode in ("start-first|start-recovery)", "status)", "stop)"):
        assert mode in script
    assert 'generation="0001"' in script
    assert 'generation="0002"' in script
    assert "flock" in script
    assert '"/proc/$1/cmdline"' in script
    assert '"/proc/$1/stat"' in script
    assert "127.0.0.1:8000" in script
    assert "/health" in script
    assert "curl" in script and "--max-redirs 0" in script
    assert "cmdline_sha256" in script
    assert "service_start_identity_hash" in script
    assert "paper1.calibration.service-stop-evidence.v1" in script
    assert "service evidence record hash mismatch" in script
    assert "service evidence fields are not exact" in script
    assert "9>&-" in script
    assert "cleanup_failed_start" in script
    assert 'kill -TERM "$pid"' in script
    assert 'wait "$pid"' in script
    launch = script.index("exec 9>&-")
    exec_serve = script.index('exec "$serve_script"', launch)
    background = script.index('&\n    pid="$!"', exec_serve)
    cleanup = script.index("cleanup_failed_start", background)
    health_loop = script.index("for _ in $(seq 1 120)", cleanup)
    assert launch < exec_serve < background < cleanup < health_loop
    assert "process_exit_observed" in script
    assert "loopback_listener_absent" in script
    assert "pkill" not in script


def test_service_script_rejects_proxy_symlink_stale_pid_and_identity_drift() -> None:
    script = _script("phase0a1-service.sh")

    assert "${!" in script and "[Pp][Rr][Oo][Xx][Yy]" in script
    assert "compgen -e" in script
    assert "realpath -e" in script
    assert "-L" in script
    assert 'kill -0 "$pid"' in script
    assert "command-line identity mismatch" in script
    assert "process start-time mismatch" in script
    assert 'kill -TERM "$pid"' in script
    assert "noclobber" in script
    assert "active generation" in script
