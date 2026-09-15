"""Fail-closed command surface for the Phase 0A-1 cloud calibration gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from agent_ex.calibration.cloud import CloudPreflight
from agent_ex.calibration import cli
from agent_ex.calibration.cloud_run import CloudRunManifest
from agent_ex.calibration.environment import (
    EnvironmentLock,
    PackageEntry,
    PreliminaryEnvironmentInspection,
    WheelEntry,
)
from agent_ex.domain import canonical_payload_hash
from test_calibration_cloud_run import (
    approved_artifacts,
    approved_run_artifacts_payload,
    environment_lock_for,
)
from test_calibration_environment import valid_observation
from test_calibration_smoke import manifest as smoke_manifest


COMMIT = "a" * 40
PLATFORM_ROOT = Path(__file__).parents[1]


def valid_preflight() -> CloudPreflight:
    return CloudPreflight.create(
        os_release="Ubuntu 22.04.5 LTS",
        kernel="5.15.0",
        python_version="3.12.3",
        gpu_name="NVIDIA GeForce RTX 5090",
        gpu_memory_bytes=32_607 * 1024 * 1024,
        driver_version="580.105.08",
        reported_cuda_version="12.8",
        free_disk_bytes=129 * 1024**3,
        git_commit=COMMIT,
        git_dirty=False,
    )


def test_parser_exposes_only_approved_subcommands() -> None:
    parser = cli.build_parser()
    action = next(action for action in parser._actions if action.dest == "command")  # noqa: SLF001

    assert set(action.choices) == {
        "preflight",
        "smoke-manifest",
        "smoke-preliminary-inspection",
        "smoke-lock",
        "smoke-diagnostics",
        "smoke-phase-one",
        "smoke-mark-stopped",
        "smoke-phase-two",
        "smoke-finalize",
        "lock",
        "manifest",
        "run",
        "resume",
        "review-export",
        "review-import",
        "seal",
        "verify",
    }


def test_preflight_command_has_no_network_or_install_side_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def recording_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(cli, "collect_cloud_preflight", lambda: valid_preflight())
    monkeypatch.setattr(cli.subprocess, "run", recording_run)
    output = tmp_path / "preflight.json"

    assert cli.main(["preflight", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == valid_preflight().to_payload()
    forbidden = {"pip", "uv", "curl", "wget", "git", "ssh", "scp"}
    assert not any(Path(command[0]).name.casefold() in forbidden for command in calls)


@pytest.mark.parametrize(
    "command",
    [
        "smoke-manifest",
        "smoke-preliminary-inspection",
        "smoke-lock",
        "smoke-diagnostics",
        "smoke-phase-one",
        "smoke-mark-stopped",
        "smoke-phase-two",
        "smoke-finalize",
        "lock",
        "manifest",
        "run",
        "resume",
        "review-export",
        "review-import",
        "seal",
        "verify",
    ],
)
def test_evidence_commands_require_explicit_archive_root(command: str) -> None:
    with pytest.raises(SystemExit):
        cli.main([command])


def test_run_requires_explicit_manifest_and_archive_root(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["run", "--archive-root", str(tmp_path)])


def test_lock_requires_approved_six_group_packet_and_fresh_observation(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["lock", "--archive-root", str(tmp_path)])


def test_manifest_requires_verified_environment_lock(tmp_path: Path) -> None:
    approved = tmp_path / "approved.json"
    approved.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit):
        cli.main(
            [
                "manifest",
                "--archive-root",
                str(tmp_path),
                "--approved-artifacts",
                str(approved),
                "--approved-artifacts-hash",
                "a" * 64,
            ]
        )


def test_preflight_rejects_relative_output() -> None:
    with pytest.raises(SystemExit):
        cli.main(["preflight", "--output", "preflight.json"])


def test_preflight_refuses_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "preflight.json"
    output.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(cli, "collect_cloud_preflight", lambda: valid_preflight())

    with pytest.raises(SystemExit):
        cli.main(["preflight", "--output", str(output)])


def test_control_file_write_fsyncs_parent_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    synced: list[Path] = []
    monkeypatch.setattr(cli, "_fsync_directory", synced.append)
    output = tmp_path / "control.json"

    cli._write_json_create_only(output, {"status": "ok"})  # noqa: SLF001

    assert synced == [tmp_path]


def test_git_identity_is_bound_to_running_agent_ex_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "_agent_ex_checkout_root", lambda: tmp_path)

    def checked(command: list[str]) -> str:
        calls.append(command)
        return COMMIT if "rev-parse" in command else ""

    monkeypatch.setattr(cli, "_checked_run", checked)

    assert cli._git_identity() == (COMMIT, False)  # noqa: SLF001
    assert calls == [
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        ["git", "-C", str(tmp_path), "status", "--porcelain=v1", "--untracked-files=all"],
    ]


def test_archive_root_rejects_symlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    link = tmp_path / "linked-archive"
    link.mkdir()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link or original(self))

    with pytest.raises(SystemExit):
        cli.main(["verify", "--archive-root", str(link)])


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def inspection_inputs_payload(tmp_path: Path) -> dict[str, object]:
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.environment-inspection-inputs.v1",
        "artifact_root": tmp_path.as_posix(),
        "model_files": ["model.safetensors"],
        "tokenizer_files": ["tokenizer.json"],
        "chat_template_file": "chat-template.txt",
        "rendered_non_thinking_file": "rendered.txt",
        "vllm_wheel_file": "vllm.whl",
        "image_repository": "docker.io/vllm/vllm-openai",
        "image_digest": "sha256:" + "6" * 64,
        "serve_arguments": ["--host", "127.0.0.1", "--port", "8000"],
        "health_endpoint": "http://127.0.0.1:8000/health",
        "archived_diff_file": None,
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def test_manifest_binds_exact_approved_packet_and_environment_lock(tmp_path: Path) -> None:
    packet = approved_run_artifacts_payload()
    lock = environment_lock_for(packet)
    approved_path = tmp_path / "approved.json"
    lock_path = tmp_path / "environment-lock.json"
    output_path = tmp_path / "cloud-run-manifest.json"
    write_json(approved_path, packet)
    write_json(lock_path, lock.to_payload())

    assert (
        cli.main(
            [
                "manifest",
                "--archive-root",
                str(tmp_path),
                "--approved-artifacts",
                str(approved_path),
                "--approved-artifacts-hash",
                packet["record_hash"],
                "--environment-lock",
                str(lock_path),
                "--environment-lock-hash",
                lock.record_hash,
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    manifest = CloudRunManifest.from_payload(json.loads(output_path.read_text(encoding="utf-8")))
    assert manifest.approved_artifacts_hash == packet["record_hash"]
    assert manifest.environment_lock_hash == lock.record_hash


def test_manifest_rejects_affirmative_hash_drift(tmp_path: Path) -> None:
    packet = approved_run_artifacts_payload()
    lock = environment_lock_for(packet)
    approved_path = tmp_path / "approved.json"
    lock_path = tmp_path / "environment-lock.json"
    write_json(approved_path, packet)
    write_json(lock_path, lock.to_payload())

    with pytest.raises(ValueError, match="affirmative hash"):
        cli.main(
            [
                "manifest",
                "--archive-root",
                str(tmp_path),
                "--approved-artifacts",
                str(approved_path),
                "--approved-artifacts-hash",
                "f" * 64,
                "--environment-lock",
                str(lock_path),
                "--environment-lock-hash",
                lock.record_hash,
                "--output",
                str(tmp_path / "cloud-run-manifest.json"),
            ]
        )


def test_lock_collects_fresh_observation_and_binds_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    packet = approved_run_artifacts_payload()
    inspection = inspection_inputs_payload(tmp_path)
    approved_path = tmp_path / "approved.json"
    inspection_path = tmp_path / "inspection-inputs.json"
    output_path = tmp_path / "environment-lock.json"
    write_json(approved_path, packet)
    write_json(inspection_path, inspection)
    calls: list[object] = []

    def collect(artifacts: object, inputs: object, archive_root: Path) -> object:
        calls.append((artifacts, inputs, archive_root))
        from test_calibration_environment import valid_observation

        return valid_observation()

    monkeypatch.setattr(cli, "collect_environment_observation", collect)

    assert (
        cli.main(
            [
                "lock",
                "--archive-root",
                str(tmp_path),
                "--approved-artifacts",
                str(approved_path),
                "--approved-artifacts-hash",
                packet["record_hash"],
                "--inspection-inputs",
                str(inspection_path),
                "--inspection-inputs-hash",
                inspection["record_hash"],
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    lock = EnvironmentLock.from_payload(json.loads(output_path.read_text(encoding="utf-8")))
    assert lock.authorization_hash == packet["record_hash"]
    assert len(calls) == 1


def test_old_one_shot_smoke_command_is_absent() -> None:
    with pytest.raises(SystemExit):
        cli.main(["smoke"])


def test_smoke_manifest_requires_new_clean_preflight_and_materializes_exact_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old_commit = "6711a6d767cc1993db1d823d183bb125070c107e"
    run_root = tmp_path / "new-smoke-run"
    preflight_path = tmp_path / "preflight.json"
    output_path = tmp_path / "smoke-manifest.json"
    old = CloudPreflight.create(
        os_release="Ubuntu 22.04.5 LTS",
        kernel="5.15.0",
        python_version="3.12.3",
        gpu_name="NVIDIA GeForce RTX 5090",
        gpu_memory_bytes=32_607 * 1024 * 1024,
        driver_version="580.105.08",
        reported_cuda_version="12.8",
        free_disk_bytes=129 * 1024**3,
        git_commit=old_commit,
        git_dirty=False,
    )
    write_json(preflight_path, old.to_payload())
    monkeypatch.setattr(cli, "_git_identity", lambda: (old_commit, False))

    with pytest.raises(ValueError, match="superseded source"):
        cli.main(
            [
                "smoke-manifest",
                "--archive-root",
                str(tmp_path),
                "--preflight",
                str(preflight_path),
                "--preflight-hash",
                old.record_hash,
                "--run-archive",
                str(run_root),
                "--output",
                str(output_path),
            ]
        )

    current = valid_preflight()
    write_json(preflight_path, current.to_payload())
    monkeypatch.setattr(cli, "_git_identity", lambda: (current.git_commit, False))

    assert (
        cli.main(
            [
                "smoke-manifest",
                "--archive-root",
                str(tmp_path),
                "--preflight",
                str(preflight_path),
                "--preflight-hash",
                current.record_hash,
                "--run-archive",
                str(run_root),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    created = smoke_manifest(run_root)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["preflight_hash"] == current.record_hash
    assert payload["model_repository"] == created.model_repository
    assert payload["model_revision_candidate"] == created.model_revision_candidate
    assert payload["runtime_policy_hash"] == (
        "e0c72256eb39927f0e76565bb95b7b570c5930c22c40a28267ec872d97af0f13"
    )
    assert payload["record_hash"] != (
        "9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304"
    )


def test_smoke_phase_handlers_are_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers = {
        "smoke-manifest": "_smoke_manifest_command",
        "smoke-preliminary-inspection": "_smoke_preliminary_inspection_command",
        "smoke-lock": "_smoke_lock_command",
        "smoke-diagnostics": "_smoke_diagnostics_command",
        "smoke-phase-one": "_smoke_phase_one_command",
        "smoke-mark-stopped": "_smoke_mark_stopped_command",
        "smoke-phase-two": "_smoke_phase_two_command",
        "smoke-finalize": "_smoke_finalize_command",
    }
    for selected_command, selected_handler in handlers.items():
        calls: list[str] = []
        for handler in handlers.values():
            if handler == selected_handler:
                monkeypatch.setattr(
                    cli, handler, lambda args, name=handler: calls.append(name) or 0
                )
            else:
                monkeypatch.setattr(
                    cli,
                    handler,
                    lambda args, name=handler: pytest.fail(f"crossed into {name}"),
                )
        monkeypatch.setattr(
            cli,
            "build_parser",
            lambda command=selected_command: SimpleNamespace(
                parse_args=lambda argv: SimpleNamespace(command=command)
            ),
        )

        assert cli.main([selected_command]) == 0
        assert calls == [selected_handler]


@pytest.mark.parametrize(
    ("command", "handler", "target", "uses_policy", "uses_adapter"),
    [
        ("smoke-diagnostics", "_smoke_diagnostics_command", "run_smoke_diagnostics", True, False),
        ("smoke-phase-one", "_smoke_phase_one_command", "run_smoke_phase_one", True, True),
        ("smoke-phase-two", "_smoke_phase_two_command", "run_smoke_phase_two", True, True),
        ("smoke-finalize", "_smoke_finalize_command", "finalize_probe_smoke", False, False),
    ],
)
def test_live_smoke_handler_calls_only_its_named_phase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    handler: str,
    target: str,
    uses_policy: bool,
    uses_adapter: bool,
) -> None:
    manifest = object()
    lock = object()
    run_root = tmp_path / "run"
    observation = object()
    policy = object()
    adapter = object()
    called: list[str] = []
    phase_functions = {
        "run_smoke_diagnostics",
        "run_smoke_phase_one",
        "mark_smoke_service_stopped",
        "run_smoke_phase_two",
        "finalize_probe_smoke",
    }
    monkeypatch.setattr(
        cli,
        "_load_smoke_live_context",
        lambda args: (manifest, lock, run_root, observation),
    )
    monkeypatch.setattr(cli, "_load_smoke_policy", lambda args, value: policy)
    monkeypatch.setattr(cli, "_smoke_adapter", lambda value: adapter)
    for name in phase_functions:
        if name == target:
            monkeypatch.setattr(
                cli,
                name,
                lambda *args, selected=name, **kwargs: (
                    called.append(selected)
                    or SimpleNamespace(to_payload=lambda: {"phase": selected})
                ),
            )
        else:
            monkeypatch.setattr(
                cli,
                name,
                lambda *args, unexpected=name, **kwargs: pytest.fail(f"crossed into {unexpected}"),
            )
    args = SimpleNamespace(output=tmp_path / f"{command}.json")

    assert getattr(cli, handler)(args) == 0
    assert called == [target]
    if uses_policy:
        assert policy is not None
    if uses_adapter:
        assert adapter is not None


def test_smoke_mark_stopped_calls_only_stop_transition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = SimpleNamespace(archive_uri=(tmp_path / "run").as_posix())
    lock = object()
    stop = object()
    called: list[str] = []
    args = SimpleNamespace(
        archive_root=tmp_path,
        manifest=tmp_path / "manifest.json",
        manifest_hash="a" * 64,
        environment_lock=tmp_path / "lock.json",
        environment_lock_hash="b" * 64,
        service_stop_evidence=tmp_path / "stop.json",
        service_stop_evidence_hash="c" * 64,
        output=tmp_path / "result.json",
    )
    monkeypatch.setattr(cli, "_require_within_archive", lambda path, root: None)
    monkeypatch.setattr(cli, "_load_smoke_manifest_and_lock", lambda value: (manifest, lock))
    monkeypatch.setattr(cli, "_read_json_record", lambda path, affirmative_hash: {})
    monkeypatch.setattr(
        cli,
        "ServiceStopEvidence",
        SimpleNamespace(from_payload=lambda payload: stop),
    )
    monkeypatch.setattr(cli, "_run_archive_path", lambda *args, **kwargs: tmp_path / "run")
    monkeypatch.setattr(
        cli,
        "mark_smoke_service_stopped",
        lambda *values, **kwargs: (
            called.append("mark_smoke_service_stopped")
            or SimpleNamespace(to_payload=lambda: {"phase": "service_stopped"})
        ),
    )
    for name in (
        "run_smoke_diagnostics",
        "run_smoke_phase_one",
        "run_smoke_phase_two",
        "finalize_probe_smoke",
    ):
        monkeypatch.setattr(
            cli,
            name,
            lambda *values, unexpected=name, **kwargs: pytest.fail(f"crossed into {unexpected}"),
        )

    assert cli._smoke_mark_stopped_command(args) == 0  # noqa: SLF001
    assert called == ["mark_smoke_service_stopped"]


def test_smoke_preliminary_inspection_binds_wheels_and_current_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wheels = (
        WheelEntry(
            name="vllm",
            version="0.23.0",
            sha256="5" * 64,
            source="official-cuda-12.9",
        ),
    )
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.wheel-manifest.v1",
        "wheel_entries": [item.to_payload() for item in wheels],
    }
    wheel_manifest = {**content, "record_hash": canonical_payload_hash(content)}
    wheel_path = tmp_path / "wheels.json"
    output = tmp_path / "preliminary.json"
    write_json(wheel_path, wheel_manifest)
    packages = (
        PackageEntry(name="torch", version="2.8.0"),
        PackageEntry(name="vllm", version="0.23.0"),
    )
    monkeypatch.setattr(cli, "_package_lock", lambda: packages)
    monkeypatch.setattr(cli, "_distribution_is_in_current_environment", lambda name: True)
    monkeypatch.setattr(cli.platform, "python_version", lambda: "3.12.3")

    assert (
        cli.main(
            [
                "smoke-preliminary-inspection",
                "--archive-root",
                str(tmp_path),
                "--wheel-manifest",
                str(wheel_path),
                "--wheel-manifest-hash",
                wheel_manifest["record_hash"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    result = PreliminaryEnvironmentInspection.from_payload(
        json.loads(output.read_text(encoding="utf-8"))
    )
    assert result.wheel_entries == wheels
    assert result.package_lock == packages
    assert result.torch_source == "fresh-vllm-environment"


def test_smoke_lock_binds_manifest_preliminary_and_complete_observation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_root = tmp_path / "run"
    manifest = smoke_manifest(run_root)
    observation = valid_observation()
    preliminary = PreliminaryEnvironmentInspection.create(
        python_version=observation.python_version,
        package_lock=observation.package_lock,
        wheel_entries=(
            WheelEntry(
                name="vllm",
                version="0.23.0",
                sha256=observation.vllm_identity.wheel_hash,
                source="official-cuda-12.9",
            ),
        ),
        torch_source="fresh-vllm-environment",
    )
    observation = replace(observation, package_lock=preliminary.package_lock)
    inspection = inspection_inputs_payload(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    preliminary_path = tmp_path / "preliminary.json"
    inspection_path = tmp_path / "inspection.json"
    output = tmp_path / "lock.json"
    write_json(manifest_path, manifest.to_payload())
    write_json(preliminary_path, preliminary.to_payload())
    write_json(inspection_path, inspection)
    monkeypatch.setattr(
        cli,
        "collect_smoke_environment_observation",
        lambda manifest, inputs, archive_root: observation,
    )

    assert (
        cli.main(
            [
                "smoke-lock",
                "--archive-root",
                str(tmp_path),
                "--manifest",
                str(manifest_path),
                "--manifest-hash",
                manifest.record_hash,
                "--preliminary-inspection",
                str(preliminary_path),
                "--preliminary-inspection-hash",
                preliminary.record_hash,
                "--inspection-inputs",
                str(inspection_path),
                "--inspection-inputs-hash",
                inspection["record_hash"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    lock = EnvironmentLock.from_payload(json.loads(output.read_text(encoding="utf-8")))
    assert lock.authorization_hash == manifest.record_hash


def test_environment_inspection_hashes_fresh_host_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed = valid_observation()
    contents = {
        "model.safetensors": b"model-bytes",
        "tokenizer.json": b"tokenizer-bytes",
        "chat-template.txt": observed.chat_template_text.encode("utf-8"),
        "rendered.txt": b"rendered-non-thinking",
        "vllm.whl": b"wheel-bytes",
    }
    for name, value in contents.items():
        (tmp_path / name).write_bytes(value)
    inputs = inspection_inputs_payload(tmp_path)

    def checked_run(command: list[str]) -> str:
        if command[0] == "git" and "rev-parse" in command:
            return observed.git_commit
        if command[0] == "git" and "status" in command:
            return ""
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cli, "_checked_run", checked_run)
    monkeypatch.setattr(cli, "_package_lock", lambda: observed.package_lock)
    monkeypatch.setattr(
        cli,
        "_single_gpu_observation",
        lambda: (observed.gpu, observed.driver_version, observed.reported_cuda_version),
    )
    monkeypatch.setattr(cli, "_health_check", lambda endpoint: observed.health_check)

    current = cli.collect_environment_observation(approved_artifacts(), inputs, tmp_path)

    assert (
        current.model_artifacts[0].sha256
        == hashlib.sha256(contents["model.safetensors"]).hexdigest()
    )
    assert (
        current.tokenizer_artifacts[0].sha256
        == hashlib.sha256(contents["tokenizer.json"]).hexdigest()
    )
    assert current.chat_template_hash == observed.chat_template_hash
    assert current.vllm_identity.wheel_hash == hashlib.sha256(contents["vllm.whl"]).hexdigest()


def test_serve_script_is_loopback_only_and_uses_exact_candidate_contract() -> None:
    script = (PLATFORM_ROOT / "scripts" / "phase0a1-serve.sh").read_text(encoding="utf-8")

    for fragment in (
        "--host 127.0.0.1",
        "--port 8000",
        "--revision b968826d9c46dd6066d109eabc6255188de91218",
        "--tokenizer-revision b968826d9c46dd6066d109eabc6255188de91218",
        "--dtype bfloat16",
        "--max-model-len 32768",
        "--generation-config vllm",
        "--served-model-name qwen3-8b-paper1",
        "--default-chat-template-kwargs",
        "--enable-request-id-headers",
    ):
        assert fragment in script
    assert "0.0.0.0" not in script
    assert script.count("realpath -e") == 2
    assert "--enable-reasoning" not in script
    assert not any(
        secret in script.casefold() for secret in ("api_key", "access_token", "hf_token")
    )
