"""Regression tests for the source-bound, pre-install Agent-EX import boundary."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

import agent_ex


PLATFORM_ROOT = Path(__file__).parents[1].resolve()
SOURCE_ROOT = (PLATFORM_ROOT / "src").resolve()


def _source_subprocess(script: str, *extra_paths: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(path.resolve()) for path in extra_paths] + [str(SOURCE_ROOT)]
    )
    return subprocess.run(
        [sys.executable, "-S", "-c", textwrap.dedent(script)],
        cwd=PLATFORM_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_preinstall_cli_bootstrap_uses_exact_source_without_project_dependencies() -> None:
    completed = _source_subprocess(
        f"""
        import importlib.abc
        from pathlib import Path
        import sys

        blocked = {{"networkx", "jsonschema", "yaml"}}

        class DeclaredDependencyBlocker(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.partition(".")[0] in blocked:
                    raise ModuleNotFoundError(f"blocked declared dependency: {{fullname}}")
                return None

        sys.meta_path.insert(0, DeclaredDependencyBlocker())
        import agent_ex
        from agent_ex.calibration import cli

        source_root = Path({str(SOURCE_ROOT)!r}).resolve()
        imported = Path(agent_ex.__file__).resolve()
        assert imported.is_relative_to(source_root), (imported, source_root)
        output = (Path.cwd() / "preflight.json").resolve()
        parsed = cli.build_parser().parse_args(["preflight", "--output", str(output)])
        assert parsed.command == "preflight"
        forbidden = {{
            "agent_ex.network",
            "agent_ex.storage",
            "agent_ex.engine",
            "agent_ex.protocol",
            "agent_ex.validation",
        }}
        assert forbidden.isdisjoint(sys.modules), forbidden.intersection(sys.modules)
        assert blocked.isdisjoint(sys.modules), blocked.intersection(sys.modules)
        """
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_old_networkx_does_not_block_cli_but_still_blocks_network_export(tmp_path: Path) -> None:
    fake_dependency = tmp_path / "fake-dependency"
    fake_dependency.mkdir()
    (fake_dependency / "networkx.py").write_text("__version__ = '3.5'\n", encoding="utf-8")
    completed = _source_subprocess(
        """
        import sys
        import agent_ex
        from agent_ex.calibration import cli

        assert cli.build_parser().prog == "agent-ex-phase0a1"
        assert "agent_ex.network" not in sys.modules
        try:
            agent_ex.build_ws_artifact
        except RuntimeError as error:
            assert str(error) == (
                "network artifact implementation requires networkx==3.6.1; found 3.5"
            )
        else:
            raise AssertionError("network export must retain the exact dependency guard")
        """,
        fake_dependency,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
