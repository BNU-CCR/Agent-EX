"""Platform-neutral contract tests for the reviewed Phase 0A-1 cloud scripts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


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
    for signal_name in ("HUP", "INT", "TERM"):
        assert "trap 'signal_exit" in script
        assert signal_name in script
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


def test_serve_script_disables_flashinfer_sampler_before_exec() -> None:
    script = _script("phase0a1-serve.sh")

    assignment = "export VLLM_USE_FLASHINFER_SAMPLER=0"
    assert assignment in script
    assert script.index(assignment) < script.index('exec "$vllm_executable"')
    assert "CUDA_HOME=" not in script


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
    assert 'kill -TERM -- "-$pid"' in script
    assert 'wait "$pid"' in script
    launch = script.index("exec 9>&-")
    exec_serve = script.index('exec setsid "$serve_script"', launch)
    background = script.index('&\n    pid="$!"', exec_serve)
    cleanup = script.index("cleanup_failed_start", background)
    health_loop = script.index("for _ in $(seq 1 300)", cleanup)
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
    assert 'kill -TERM -- "-$pid"' in script
    assert "noclobber" in script
    assert "active generation" in script


def test_service_script_owns_and_reaps_the_whole_vllm_process_group() -> None:
    script = _script("phase0a1-service.sh")

    assert 'exec setsid "$serve_script" "$vllm_executable" "$model_path"' in script
    assert 'kill -TERM -- "-$pid"' in script
    assert 'kill -KILL -- "-$pid"' in script
    assert 'kill -0 -- "-$pid"' in script
    assert "for _ in $(seq 1 300)" in script


def test_service_script_uses_an_explicit_recorded_control_python() -> None:
    script = _script("phase0a1-service.sh")

    assert "SERVE VLLM PYTHON MODEL" in script
    assert "status PYTHON EVIDENCE_DIR" in script
    assert "stop PYTHON EVIDENCE_DIR" in script
    assert 'require_exact_file "$python_executable" "ABSOLUTE_PYTHON"' in script
    assert '"$python_executable" -c' in script
    assert '"$python_executable" - "$1" "$2"' in script
    assert '"$python_executable" - "$output" "$@"' in script
    assert '"control_python"' in script
    assert "python3" not in script


def test_service_script_has_a_verified_prelock_abort_terminal_record() -> None:
    script = _script("phase0a1-service.sh")

    assert "abort-first PYTHON EVIDENCE_DIR MANIFEST_HASH PRELIMINARY_HASH" in script
    assert "abort-first|stop)" in script
    assert "paper1.calibration.service-prelock-abort-evidence.v1" in script
    assert '"preliminary_inspection_hash"' in script
    assert "write_prelock_abort_evidence" in script
    assert (
        'start-identity.json" && ! -e "$candidate/stop-evidence.json" && ! -e "$candidate/abort-evidence.json"'
        in script
    )
    assert 'elif [[ "$(json_field "$identity" binding_kind)" == "environment-lock" ]]' in script

    stop_start = script.index("write_stop_evidence() {")
    stop_python_close = script.index("\nPY\n}", stop_start)
    abort_start = script.index("write_prelock_abort_evidence() {")
    abort_python_close = script.index("\nPY\n}", abort_start)
    assert stop_start < stop_python_close < abort_start < abort_python_close


def test_judge_service_script_has_distinct_two_stage_authorization_lifecycle() -> None:
    script = _script("phase0a1-judge-service.sh")

    assert 'case "$mode" in' in script
    for mode in ("start)", "status)", "abort-pre-manifest)", "stop)"):
        assert mode in script
    assert "AUTHORIZATION_HASH" in script
    assert "MANIFEST_HASH" in script
    assert "paper1.calibration.judge-service-start-identity.v1" in script
    assert "paper1.calibration.judge-pre-manifest-abort-evidence.v1" in script
    assert "paper1.calibration.judge-service-stop-evidence.v1" in script
    assert "gpu_compute_process_observation_hash" in script
    assert "gpu_idle_observation_hash" in script
    assert "environment_lock_hash" in script
    assert "service_start_identity_hash" in script
    assert "127.0.0.1:8000" in script
    assert "/health" in script
    assert ".phase0a1-judge-service.lock.d" in script
    assert "pkill" not in script


def test_judge_service_start_binds_only_authorization_and_abort_never_invents_manifest() -> None:
    script = _script("phase0a1-judge-service.sh")

    start_block = script[script.index("  start)") : script.index("  status)")]
    abort_block = script[script.index("  abort-pre-manifest)") : script.index("  stop)")]
    stop_block = script[script.index("  stop)") :]
    assert "authorization_hash" in start_block
    assert "manifest_hash" not in start_block
    assert "manifest_hash" not in abort_block
    assert "manifest_hash" in stop_block
    assert 'kill -TERM -- "-$group_id"' in script
    assert "loopback_listener_absent" in script
    assert "process_exit_observed" in script


def test_judge_service_hardens_identity_filesystem_and_cleanup_contracts() -> None:
    script = _script("phase0a1-judge-service.sh")

    assert "object_pairs_hook" in script
    assert "parse_constant" in script
    assert "judge start identity fields are not exact" in script
    assert "judge start identity record hash mismatch" in script
    assert "control Python identity mismatch" in script
    assert "process start-time mismatch" in script
    assert "process-group identity mismatch" in script
    assert "session identity mismatch" in script
    assert "O_NOFOLLOW" in script
    assert "O_EXCL" in script
    assert ".phase0a1-judge-service.lock.d" in script
    assert "kill -KILL" in script
    assert "assert_loopback_listener_absent" in script
    assert "assert_gpu_compute_processes_absent" in script
    for status in (129, 130, 143):
        assert f"exit {status}" in script


def test_judge_service_treats_any_port_8000_listener_as_occupied() -> None:
    script = _script("phase0a1-judge-service.sh")

    absence_check = script[
        script.index("assert_loopback_listener_absent()") : script.index(
            "listener_owned_by_pid()"
        )
    ]
    assert '[[ -z "$sockets" ]]' in absence_check
    assert '[[ "$sockets" != *"127.0.0.1:8000"* ]]' not in absence_check


def test_judge_service_anchors_all_evidence_io_to_a_held_directory_capability() -> None:
    script = _script("phase0a1-judge-service.sh")

    assert 'os.O_DIRECTORY | os.O_NOFOLLOW' in script
    assert "os.set_inheritable(directory_fd, True)" in script
    assert 'evidence_anchor="/proc/$$/fd/$evidence_directory_fd"' in script
    assert "verify_evidence_directory_binding" in script
    assert '"$evidence_anchor/service.log"' in script
    assert '"$evidence_anchor/start-identity.json"' in script
    assert '"$evidence_anchor/gpu-stop-observation"' in script
    assert '"$evidence_anchor/stop-evidence.json"' in script
    assert '"$evidence_dir/service.log"' not in script


@pytest.mark.skipif(os.name != "posix", reason="requires Linux procfs and sockets")
def test_judge_service_rejects_tampered_identity_and_pid_reuse_fields(
    tmp_path: Path,
) -> None:
    harness = _judge_harness(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    started = harness.run("start", evidence=evidence)
    assert started.returncode == 0, started.stderr
    identity = evidence / "start-identity.json"
    original = identity.read_text(encoding="utf-8")
    payload = json.loads(original)

    def rejected(raw: str, message: str) -> None:
        identity.write_text(raw, encoding="utf-8")
        result = harness.run("status", evidence=evidence)
        assert result.returncode != 0
        assert message in result.stderr
        identity.write_text(original, encoding="utf-8")

    try:
        rejected(original.rstrip()[:-1] + ',"pid":1}\n', "duplicate JSON field")
        rejected(original.replace('"pid":', '"unexpected":NaN,"pid":', 1), "non-finite JSON")
        extra = {**payload, "unexpected": "field"}
        rejected(json.dumps(extra), "fields are not exact")
        bad_hash = {**payload, "record_hash": "0" * 64}
        rejected(json.dumps(bad_hash), "record hash mismatch")
        changed_python = {**payload, "control_python": "/not/the/control/python"}
        changed_content = {
            key: value for key, value in changed_python.items() if key != "record_hash"
        }
        changed_python["record_hash"] = hashlib.sha256(
            json.dumps(
                changed_content,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        rejected(json.dumps(changed_python), "control Python identity mismatch")
        for field, message in (
            ("proc_start_time", "process start-time mismatch"),
            ("process_group_id", "process-group identity mismatch"),
            ("session_id", "session identity mismatch"),
        ):
            changed = {**payload, field: int(payload[field]) + 1}
            content = {key: value for key, value in changed.items() if key != "record_hash"}
            changed["record_hash"] = hashlib.sha256(
                json.dumps(
                    content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            rejected(json.dumps(changed), message)
    finally:
        identity.write_text(original, encoding="utf-8")
        stopped = harness.run("stop", evidence=evidence, start_hash=str(payload["record_hash"]))
        if stopped.returncode != 0:
            os.killpg(int(payload["process_group_id"]), signal.SIGKILL)


@pytest.mark.skipif(os.name != "posix", reason="requires Linux procfs and sockets")
def test_judge_service_refuses_preset_symlinks_and_existing_outputs(
    tmp_path: Path,
) -> None:
    harness = _judge_harness(tmp_path)
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("do-not-touch", encoding="utf-8")

    for trap_name in (".phase0a1-judge-service.lock.d", "service.log"):
        evidence = tmp_path / trap_name.replace(".", "_")
        evidence.mkdir()
        (evidence / trap_name).symlink_to(sentinel)
        result = harness.run("start", evidence=evidence)
        assert result.returncode != 0
        assert sentinel.read_text(encoding="utf-8") == "do-not-touch"

    evidence = tmp_path / "existing-log"
    evidence.mkdir()
    (evidence / "service.log").write_text("existing", encoding="utf-8")
    result = harness.run("start", evidence=evidence)
    assert result.returncode != 0
    assert (evidence / "service.log").read_text(encoding="utf-8") == "existing"

    evidence = tmp_path / "terminal-evidence"
    evidence.mkdir()
    started = harness.run("start", evidence=evidence)
    assert started.returncode == 0, started.stderr
    payload = json.loads((evidence / "start-identity.json").read_text(encoding="utf-8"))
    (evidence / "gpu-stop-observation").symlink_to(sentinel)
    (evidence / "stop-evidence.json").symlink_to(sentinel)
    result = harness.run(
        "stop",
        evidence=evidence,
        start_hash=str(payload["record_hash"]),
    )
    assert result.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "do-not-touch"
    _wait_process_absent(int(payload["process_group_id"]), process_group=True)


@pytest.mark.skipif(os.name != "posix", reason="requires Linux procfs and sockets")
def test_judge_failed_start_kills_term_ignoring_process_group_and_keeps_signal_exit(
    tmp_path: Path,
) -> None:
    harness = _judge_harness(tmp_path, stubborn=True)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    process = harness.popen("start", evidence=evidence)
    pid_file = evidence / "stubborn.pid"
    deadline = time.monotonic() + 10
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.exists()
    process.send_signal(signal.SIGTERM)
    _stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 143, stderr
    stubborn_pid = int(pid_file.read_text(encoding="utf-8"))
    _wait_process_absent(stubborn_pid)
    assert "escalating to KILL" in stderr


@pytest.mark.skipif(os.name != "posix", reason="requires Linux procfs and sockets")
def test_judge_early_child_failure_performs_bounded_final_cleanup(tmp_path: Path) -> None:
    harness = _judge_harness(tmp_path, early_exit=True)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    before = time.monotonic()
    result = harness.run("start", evidence=evidence)
    elapsed = time.monotonic() - before
    assert result.returncode != 0
    assert elapsed < 10
    assert "vLLM exited before judge health" in result.stderr
    early_pid = int((evidence / "early.pid").read_text(encoding="utf-8"))
    _wait_process_absent(early_pid)


@pytest.mark.skipif(os.name != "posix", reason="requires Linux sockets")
def test_judge_failed_start_detects_wildcard_port_8000_listener(tmp_path: Path) -> None:
    harness = _judge_harness(tmp_path, early_exit=True)
    ready = tmp_path / "wildcard-ready"
    listener = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,socket,sys,time; "
                "s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); "
                "s.bind(('0.0.0.0',8000)); s.listen(); "
                "pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(30)"
            ),
            str(ready),
        ]
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists()
        evidence = tmp_path / "evidence"
        evidence.mkdir()
        result = harness.run("start", evidence=evidence)
        assert result.returncode != 0
        assert "judge port 8000 remains occupied" in result.stderr
    finally:
        listener.terminate()
        listener.wait(timeout=5)


@pytest.mark.skipif(os.name != "posix", reason="requires Linux directory descriptors")
def test_judge_start_fails_closed_if_evidence_directory_is_replaced(
    tmp_path: Path,
) -> None:
    harness = _judge_harness(tmp_path, replace_evidence=True)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    result = harness.run("start", evidence=evidence)
    assert result.returncode != 0
    assert "evidence directory pathname identity changed" in result.stderr
    replacement = tmp_path / "evidence"
    original = tmp_path / "evidence-renamed"
    assert replacement.is_dir()
    assert list(replacement.iterdir()) == []
    assert (original / "service.log").is_file()
    assert not (original / ".phase0a1-judge-service.lock.d").exists()
    assert not (replacement / ".phase0a1-judge-service.lock.d").exists()


class _JudgeHarness:
    def __init__(
        self,
        root: Path,
        *,
        stubborn: bool = False,
        early_exit: bool = False,
        replace_evidence: bool = False,
    ) -> None:
        self.script = (SCRIPTS / "phase0a1-judge-service.sh").resolve(strict=True)
        self.python = Path(sys.executable).resolve(strict=True)
        self.model = root / "model"
        self.model.mkdir()
        server = self.model / "health_server.py"
        server.write_text(
            "from http.server import HTTPServer,BaseHTTPRequestHandler\n"
            "class H(BaseHTTPRequestHandler):\n"
            " def do_GET(self): self.send_response(200 if self.path=='/health' else 404); self.end_headers()\n"
            " def log_message(self,*args): pass\n"
            "HTTPServer(('127.0.0.1',8000),H).serve_forever()\n",
            encoding="utf-8",
        )
        self.serve = root / "serve.sh"
        if replace_evidence:
            body = (
                "#!/usr/bin/env bash\n"
                'mv "$2/../evidence" "$2/../evidence-renamed"\n'
                'mkdir "$2/../evidence"\n'
                'exec "$1" "$2/health_server.py"\n'
            )
        elif stubborn:
            body = (
                "#!/usr/bin/env bash\n"
                "(\n"
                "  trap '' TERM\n"
                '  echo "$BASHPID" > "$2/../evidence/stubborn.pid"\n'
                "  while :; do sleep 1; done\n"
                ") &\n"
                "wait\n"
            )
        elif early_exit:
            body = '#!/usr/bin/env bash\necho "$$" > "$2/../evidence/early.pid"\nexit 23\n'
        else:
            body = '#!/usr/bin/env bash\nexec "$1" "$2/health_server.py"\n'
        self.serve.write_text(body, encoding="utf-8")
        self.serve.chmod(0o700)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_nvidia = fake_bin / "nvidia-smi"
        fake_nvidia.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        fake_nvidia.chmod(0o700)
        self.environment = {
            name: value for name, value in os.environ.items() if "proxy" not in name.casefold()
        }
        self.environment["PATH"] = f"{fake_bin}{os.pathsep}{self.environment['PATH']}"

    def command(
        self,
        mode: str,
        *,
        evidence: Path,
        start_hash: str = "d" * 64,
    ) -> list[str]:
        if mode == "start":
            args = [self.serve, self.python, self.python, self.model, evidence, "a" * 64]
        elif mode == "status":
            args = [self.python, evidence]
        elif mode == "stop":
            args = [self.python, evidence, "b" * 64, "c" * 64, start_hash]
        else:
            raise AssertionError(mode)
        return ["bash", str(self.script), mode, *(str(value) for value in args)]

    def run(
        self, mode: str, *, evidence: Path, start_hash: str = "d" * 64
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.command(mode, evidence=evidence, start_hash=start_hash),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
            env=self.environment,
        )

    def popen(
        self, mode: str, *, evidence: Path, start_hash: str = "d" * 64
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(
            self.command(mode, evidence=evidence, start_hash=start_hash),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment,
        )


def _judge_harness(
    tmp_path: Path,
    *,
    stubborn: bool = False,
    early_exit: bool = False,
    replace_evidence: bool = False,
) -> _JudgeHarness:
    return _JudgeHarness(
        tmp_path,
        stubborn=stubborn,
        early_exit=early_exit,
        replace_evidence=replace_evidence,
    )


def _wait_process_absent(pid: int, *, process_group: bool = False) -> None:
    target = -pid if process_group else pid
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(target, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"process identity {target} remains")


@pytest.mark.skipif(os.name != "posix", reason="requires Linux process and socket evidence")
def test_judge_service_executes_both_lifecycle_paths_and_writes_canonical_records(
    tmp_path: Path,
) -> None:
    script = (SCRIPTS / "phase0a1-judge-service.sh").resolve(strict=True)
    python = Path(sys.executable).resolve(strict=True)
    model = tmp_path / "model"
    model.mkdir()
    server = model / "health_server.py"
    server.write_text(
        """from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == '/health' else 404)
        self.end_headers()
    def log_message(self, format, *args):
        pass
HTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
""",
        encoding="utf-8",
    )
    serve = tmp_path / "serve.sh"
    serve.write_text(
        '#!/usr/bin/env bash\nexec "$1" "$2/health_server.py"\n',
        encoding="utf-8",
    )
    serve.chmod(0o700)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_nvidia_smi = fake_bin / "nvidia-smi"
    fake_nvidia_smi.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_nvidia_smi.chmod(0o700)
    environment = {
        name: value for name, value in os.environ.items() if "proxy" not in name.casefold()
    }
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    authorization_hash = "a" * 64
    manifest_hash = "b" * 64
    lock_hash = "c" * 64
    active_groups: set[int] = set()

    def run(*arguments: object) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["bash", str(script), *(str(value) for value in arguments)],
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
            env=environment,
        )
        assert completed.returncode == 0, completed.stderr
        return completed

    def load_record(path: Path) -> dict[str, object]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        content = {name: value for name, value in payload.items() if name != "record_hash"}
        encoded = json.dumps(
            content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        assert payload["record_hash"] == hashlib.sha256(encoded).hexdigest()
        return payload

    try:
        abort_dir = tmp_path / "abort-evidence"
        abort_dir.mkdir()
        run("start", serve, python, python, model, abort_dir, authorization_hash)
        start = load_record(abort_dir / "start-identity.json")
        active_groups.add(int(start["pid"]))
        run("status", python, abort_dir)
        run(
            "abort-pre-manifest",
            python,
            abort_dir,
            authorization_hash,
            start["record_hash"],
            "-",
        )
        active_groups.discard(int(start["pid"]))
        abort = load_record(abort_dir / "abort-evidence.json")
        assert abort["schema_version"] == (
            "paper1.calibration.judge-pre-manifest-abort-evidence.v1"
        )
        assert abort["environment_lock_hash"] is None
        assert "manifest_hash" not in abort

        stop_dir = tmp_path / "stop-evidence"
        stop_dir.mkdir()
        run("start", serve, python, python, model, stop_dir, authorization_hash)
        start = load_record(stop_dir / "start-identity.json")
        active_groups.add(int(start["pid"]))
        run("stop", python, stop_dir, manifest_hash, lock_hash, start["record_hash"])
        active_groups.discard(int(start["pid"]))
        stop = load_record(stop_dir / "stop-evidence.json")
        assert stop["schema_version"] == "paper1.calibration.judge-service-stop-evidence.v1"
        assert stop["manifest_hash"] == manifest_hash
        assert stop["environment_lock_hash"] == lock_hash
        assert stop["service_start_identity_hash"] == start["record_hash"]
    finally:
        for process_group in active_groups:
            try:
                os.killpg(process_group, signal.SIGTERM)
            except ProcessLookupError:
                pass
