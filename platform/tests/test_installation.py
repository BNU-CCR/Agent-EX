import json
from importlib import resources
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

import agent_ex
from agent_ex import domain, protocol, validation


SOURCE_PACKAGE = (Path(__file__).parents[1] / "src" / "agent_ex").resolve()


def test_imports_resolve_to_current_source_tree() -> None:
    imported_files = {
        "agent_ex": Path(agent_ex.__file__).resolve(),
        "agent_ex.domain": Path(domain.__file__).resolve(),
        "agent_ex.protocol": Path(protocol.__file__).resolve(),
        "agent_ex.validation": Path(validation.__file__).resolve(),
    }

    for module_name, imported_file in imported_files.items():
        assert imported_file.is_relative_to(SOURCE_PACKAGE), (
            f"{module_name} resolved to stale installation: {imported_file}"
        )


def test_phase4b4_network_interfaces_are_public() -> None:
    expected = {
        "build_ws_artifact",
        "build_shadow_artifact",
        "build_agent_node_mapping",
        "validate_ws_artifact",
        "validate_shadow_artifact",
    }

    assert expected <= set(agent_ex.__all__)
    assert all(callable(getattr(agent_ex, name)) for name in expected)


def test_packaged_schema_matches_canonical_source() -> None:
    canonical_schema = SOURCE_PACKAGE / "schemas" / "paper1.schema.json"
    packaged_schema = resources.files("agent_ex.schemas").joinpath("paper1.schema.json")

    assert packaged_schema.read_bytes() == canonical_schema.read_bytes()


def test_built_wheel_supports_isolated_formal_validation() -> None:
    platform_root = Path(__file__).parents[1]
    repository_root = platform_root.parent
    helpers = runpy.run_path(str(Path(__file__).with_name("test_protocol.py")))
    draft = helpers["load_protocol"](platform_root / "configs" / "paper1" / "protocol.yaml")
    frozen = helpers["frozen_protocol"].__wrapped__(draft)

    with tempfile.TemporaryDirectory(prefix="agent-ex-wheel-") as temporary:
        root = Path(temporary)
        wheelhouse = root / "wheelhouse"
        target = root / "target"
        wheelhouse.mkdir()
        target.mkdir()

        helpers["approved_decisions_path"].__wrapped__(frozen, root)
        helpers["approved_human_protocol_path"].__wrapped__(frozen, root)
        qa_path = root / "research-qa.md"
        qa_path.write_bytes((repository_root / "docs" / "research-qa.md").read_bytes())
        frozen_path = root / "formal.json"
        frozen_path.write_text(json.dumps(frozen), encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--disable-pip-version-check",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--no-index",
                "--wheel-dir",
                str(wheelhouse),
                str(platform_root),
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        wheel = next(wheelhouse.glob("agent_ex-*.whl"))
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                "--no-deps",
                "--no-index",
                "--target",
                str(target),
                str(wheel),
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )

        runner = root / "wheel_smoke.py"
        runner.write_text(
            """
import json
from importlib import resources
from pathlib import Path

import agent_ex
from agent_ex import validate_protocol

root = Path(__file__).parent
installed = Path(agent_ex.__file__).resolve()
target = (root / "target").resolve()
assert installed.is_relative_to(target), (installed, target)
assert json.loads(
    resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text("utf-8")
)["x-formal-required"]
formal = json.loads((root / "formal.json").read_text("utf-8"))
formal_paths = {
    "decisions_path": root / "decisions.md",
    "human_protocol_path": root / "paper1-protocol.md",
    "qa_path": root / "research-qa.md",
}
for omitted in formal_paths:
    supplied = {name: path for name, path in formal_paths.items() if name != omitted}
    try:
        validate_protocol(formal, mode="formal", **supplied)
    except ValueError as error:
        assert omitted in str(error), (omitted, str(error))
    else:
        raise AssertionError(
            f"isolated formal validation must require an explicit {omitted}"
        )
validate_protocol(
    formal,
    mode="formal",
    **formal_paths,
)
print(installed)
print("FORMAL_OK")
""".lstrip(),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(target)
        environment["PYTHONNOUSERSITE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(runner)],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert str(target.resolve()) in completed.stdout
        assert "FORMAL_OK" in completed.stdout
