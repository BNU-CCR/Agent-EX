# Phase 0A-1 Preflight Import Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the authoritative Phase 0A-1 preflight start from an exact clean source checkout before project installation without weakening the formal NetworkX dependency guard or changing the stable Agent-EX API.

**Architecture:** Replace eager root-package re-exports with one static, immutable lazy-export registry plus PEP 562 `__getattr__`/`__dir__`. Prove the bootstrap boundary in isolated subprocesses, retain wheel and public-object compatibility, then seal the failed cloud attempt and redeploy an exact repaired commit before rerunning the create-only preflight.

**Tech Stack:** Python 3.12, `importlib`, module-level `__getattr__`, pytest 9.1.1, Ruff 0.15.20, setuptools wheel builds, Git bundles, PowerShell/OpenSSH, AutoDL Ubuntu 22.04.

---

## File structure

- Create `platform/tests/test_public_api_import_boundary.py`: isolated pre-install, dependency-guard, registry, caching, introspection, unknown-name, and direct-submodule regressions.
- Modify `platform/src/agent_ex/__init__.py`: remove eager imports and add the fixed immutable export registry and lazy resolver while preserving `__all__` exactly.
- Modify `platform/tests/test_installation.py`: prove the built wheel retains the public export identity and console entry point after installation.
- Create after verified cloud execution `logs/2026-09-14-phase0a1-preflight-import-repair.md`: sanitized hashes and exact-commit evidence only; raw receipts and preflight JSON remain outside Git.

### Task 1: Add red tests for the pre-install import boundary

**Files:**
- Create: `platform/tests/test_public_api_import_boundary.py`

- [ ] **Step 1: Add the isolated source-tree and NetworkX-guard regressions**

Create the file with these imports, helper, and tests:

```python
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
```

- [ ] **Step 2: Run both tests and verify the eager package fails red**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_public_api_import_boundary.py
```

Expected: both tests fail before assertions complete because importing `agent_ex` reaches `agent_ex.network`; the first reports blocked `networkx`, and the second reports the exact `networkx==3.6.1; found 3.5` guard.

- [ ] **Step 3: Commit the red tests**

```powershell
git add platform/tests/test_public_api_import_boundary.py
git commit -m "test(platform): reproduce preinstall import failure"
```

### Task 2: Implement the static lazy public API

**Files:**
- Modify: `platform/src/agent_ex/__init__.py`
- Test: `platform/tests/test_public_api_import_boundary.py`

- [ ] **Step 1: Replace eager imports with the immutable registry**

Keep the module docstring and the existing `__all__` list with exactly the same 142 strings in exactly the same order. Remove every eager relative import above it. Add these imports and this registry above `__all__`:

```python
from collections.abc import Mapping
from importlib import import_module
from types import MappingProxyType
from typing import Final


_LAZY_EXPORTS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "ArtifactEnvelope": (".artifacts", "ArtifactEnvelope"),
        "Checkpoint": (".checkpoint", "Checkpoint"),
        "AdapterRequest": (".adapters", "AdapterRequest"),
        "AdapterResponse": (".adapters", "AdapterResponse"),
        "AttemptAuthorization": (".engine", "AttemptAuthorization"),
        "AttemptExecutionEvidence": (".engine", "AttemptExecutionEvidence"),
        "AttemptInvocationResult": (".engine", "AttemptInvocationResult"),
        "AttemptLifecycleFailure": (".engine", "AttemptLifecycleFailure"),
        "AttemptOutcome": (".engine", "AttemptOutcome"),
        "EventStatus": (".domain", "EventStatus"),
        "EventJournalState": (".storage", "EventJournalState"),
        "EventEvidenceReferences": (".execution_evidence", "EventEvidenceReferences"),
        "EventInputEvidence": (".execution_evidence", "EventInputEvidence"),
        "ExecutionState": (".storage", "ExecutionState"),
        "ExecutionStatus": (".storage", "ExecutionStatus"),
        "ExposureSelection": (".feed", "ExposureSelection"),
        "FeedCandidate": (".feed", "FeedCandidate"),
        "FeedCursor": (".feed", "FeedCursor"),
        "ExposureRecord": (".domain", "ExposureRecord"),
        "ExposureProcessSummary": (".process_audit", "ExposureProcessSummary"),
        "ExternalResponseReference": (".storage", "ExternalResponseReference"),
        "ResumeAuthorizationEvidence": (".storage", "ResumeAuthorizationEvidence"),
        "FrozenSchedule": (".domain", "FrozenSchedule"),
        "FinalizedAttemptEvidence": (".execution_evidence", "FinalizedAttemptEvidence"),
        "GenerationAttempt": (".domain", "GenerationAttempt"),
        "GenerationEvent": (".domain", "GenerationEvent"),
        "LatestPublicPointer": (".state", "LatestPublicPointer"),
        "MemoryItem": (".memory", "MemoryItem"),
        "MemoryView": (".memory", "MemoryView"),
        "MockAdapter": (".adapters.mock", "MockAdapter"),
        "MockEventPipeline": (".pipeline", "MockEventPipeline"),
        "MockEventPipelineOutcome": (".pipeline", "MockEventPipelineOutcome"),
        "MockAdapterExecutionBinding": (".execution_evidence", "MockAdapterExecutionBinding"),
        "MockAttemptPolicyBinding": (".execution_evidence", "MockAttemptPolicyBinding"),
        "MockScriptStep": (".adapters.mock", "MockScriptStep"),
        "MockScaleCase": (".mock_matrix", "MockScaleCase"),
        "MockEventInvocation": (".mock_run", "MockEventInvocation"),
        "MockRunControl": (".mock_run", "MockRunControl"),
        "MockRunReport": (".mock_run", "MockRunReport"),
        "MockProcessAudit": (".process_audit", "MockProcessAudit"),
        "MockComparableRunProjection": (".process_audit", "MockComparableRunProjection"),
        "MockCellBinding": (".mock_matrix", "MockCellBinding"),
        "MockMatchedSeedMatrix": (".mock_matrix", "MockMatchedSeedMatrix"),
        "CANONICAL_CELL_IDS": (".mock_matrix", "CANONICAL_CELL_IDS"),
        "ModelAdapter": (".adapters", "ModelAdapter"),
        "ParseEvidence": (".parser", "ParseEvidence"),
        "ParseNotApplicableEvidence": (".execution_evidence", "ParseNotApplicableEvidence"),
        "ParsedAgentUpdate": (".parser", "ParsedAgentUpdate"),
        "ParserLimits": (".parser", "ParserLimits"),
        "PrivateState": (".state", "PrivateState"),
        "PrivateUpdate": (".state", "PrivateUpdate"),
        "PreparedAttempt": (".engine", "PreparedAttempt"),
        "PersistedInvocationEvidence": (".execution_evidence", "PersistedInvocationEvidence"),
        "PromptView": (".prompt", "PromptView"),
        "PromptLimits": (".prompt", "PromptLimits"),
        "ProbeCase": (".calibration", "ProbeCase"),
        "ProbePersonaView": (".calibration", "ProbePersonaView"),
        "ProbeTopicCandidate": (".calibration", "ProbeTopicCandidate"),
        "ValidatedPromptRunContext": (".prompt", "ValidatedPromptRunContext"),
        "PublicPost": (".state", "PublicPost"),
        "RNGProvenance": (".rng", "RNGProvenance"),
        "RunManifest": (".domain", "RunManifest"),
        "RunLease": (".storage", "RunLease"),
        "RunStorage": (".storage", "RunStorage"),
        "RoundZeroBaseline": (".process_audit", "RoundZeroBaseline"),
        "ScheduleSlot": (".domain", "ScheduleSlot"),
        "StorageBinding": (".storage", "StorageBinding"),
        "StorageProgress": (".storage", "StorageProgress"),
        "StrictSerialLifecycleEngine": (".engine", "StrictSerialLifecycleEngine"),
        "SuccessfulEventCommit": (".engine", "SuccessfulEventCommit"),
        "SweepProcessAudit": (".process_audit", "SweepProcessAudit"),
        "TerminalFailureEvidence": (".storage", "TerminalFailureEvidence"),
        "TRSIntegerization": (".population", "TRSIntegerization"),
        "TopicPackage": (".topic", "TopicPackage"),
        "assign_initial_reasons": (".initialization", "assign_initial_reasons"),
        "assign_initial_stances": (".initialization", "assign_initial_stances"),
        "advance_validated_prompt_run_context": (
            ".prompt",
            "advance_validated_prompt_run_context",
        ),
        "build_agent_node_mapping": (".network", "build_agent_node_mapping"),
        "build_checkpoint": (".checkpoint", "build_checkpoint"),
        "build_activation_schedule": (".schedule", "build_activation_schedule"),
        "build_attention_artifact": (".schedule", "build_attention_artifact"),
        "build_expression_artifact": (".schedule", "build_expression_artifact"),
        "build_exposure_record": (".feed", "build_exposure_record"),
        "build_memory_view": (".memory", "build_memory_view"),
        "build_mock_matched_seed_matrix": (
            ".mock_matrix",
            "build_mock_matched_seed_matrix",
        ),
        "build_mock_process_audit": (".process_audit", "build_mock_process_audit"),
        "build_mock_comparable_run_projection": (
            ".process_audit",
            "build_mock_comparable_run_projection",
        ),
        "build_population_artifact": (".population", "build_population_artifact"),
        "build_publish_schedule": (".schedule", "build_publish_schedule"),
        "build_prompt_view": (".prompt", "build_prompt_view"),
        "build_shadow_artifact": (".network", "build_shadow_artifact"),
        "build_structural_gate_artifact": (".network", "build_structural_gate_artifact"),
        "build_ws_artifact": (".network", "build_ws_artifact"),
        "canonical_payload_hash": (".domain", "canonical_payload_hash"),
        "canonical_protocol_hash": (".protocol", "canonical_protocol_hash"),
        "derive_attempt_id": (".domain", "derive_attempt_id"),
        "derive_event_id": (".domain", "derive_event_id"),
        "derive_rng_seed": (".rng", "derive_rng_seed"),
        "derive_run_id": (".domain", "derive_run_id"),
        "evaluate_analysis_eligibility": (".domain", "evaluate_analysis_eligibility"),
        "execution_projection": (".protocol", "execution_projection"),
        "execute_mock_run": (".mock_run", "execute_mock_run"),
        "load_protocol": (".protocol", "load_protocol"),
        "load_runnable_probe_specification": (
            ".calibration",
            "load_runnable_probe_specification",
        ),
        "load_checkpoint": (".checkpoint", "load_checkpoint"),
        "load_mock_scale_cases": (".mock_matrix", "load_mock_scale_cases"),
        "mock_adapter_semantics_hash": (".mock_matrix", "mock_adapter_semantics_hash"),
        "mock_clock_sequence_binding": (".mock_matrix", "mock_clock_sequence_binding"),
        "parse_agent_update": (".parser", "parse_agent_update"),
        "render_human_protocol_summary": (".validation", "render_human_protocol_summary"),
        "reconstruct_event_rng_provenance": (
            ".schedule",
            "reconstruct_event_rng_provenance",
        ),
        "render_persona": (".persona", "render_persona"),
        "render_messages": (".prompt", "render_messages"),
        "run_offline_probe": (".calibration", "run_offline_probe"),
        "select_unread_feed": (".feed", "select_unread_feed"),
        "scripted_probe_adapter": (".calibration", "scripted_probe_adapter"),
        "trs_integerize": (".population", "trs_integerize"),
        "update_human_protocol_summary": (
            ".validation",
            "update_human_protocol_summary",
        ),
        "validate_human_protocol_reference": (
            ".validation",
            "validate_human_protocol_reference",
        ),
        "validate_human_protocol_sync": (".validation", "validate_human_protocol_sync"),
        "validate_matched_schedule_reuse": (
            ".schedule",
            "validate_matched_schedule_reuse",
        ),
        "validate_latest_public_pointer": (".state", "validate_latest_public_pointer"),
        "validate_memory_view": (".memory", "validate_memory_view"),
        "validate_mock_matched_seed_matrix": (
            ".mock_matrix",
            "validate_mock_matched_seed_matrix",
        ),
        "validate_private_state": (".state", "validate_private_state"),
        "validate_public_post": (".state", "validate_public_post"),
        "validate_shadow_artifact": (".network", "validate_shadow_artifact"),
        "validate_structural_gate_artifact": (
            ".network",
            "validate_structural_gate_artifact",
        ),
        "validate_ws_artifact": (".network", "validate_ws_artifact"),
        "validate_persona_factor_diff": (".persona", "validate_persona_factor_diff"),
        "validate_evidence_graph": (".domain", "validate_evidence_graph"),
        "validate_exposure_record": (".feed", "validate_exposure_record"),
        "validate_exposure_selection": (".feed", "validate_exposure_selection"),
        "validate_event_rng_ledger": (".schedule", "validate_event_rng_ledger"),
        "validate_protocol": (".protocol", "validate_protocol"),
        "validate_adapter_response": (".adapters.mock", "validate_adapter_response"),
        "validate_checkpoint": (".checkpoint", "validate_checkpoint"),
        "validate_parse_evidence": (".parser", "validate_parse_evidence"),
        "validate_prompt_view": (".prompt", "validate_prompt_view"),
        "validate_prompt_run_context": (".prompt", "validate_prompt_run_context"),
        "validated_prompt_run_context_metadata": (
            ".prompt",
            "validated_prompt_run_context_metadata",
        ),
        "write_checkpoint_atomic": (".checkpoint", "write_checkpoint_atomic"),
    }
)
```

- [ ] **Step 2: Add drift enforcement and lazy resolution below `__all__`**

```python
if set(_LAZY_EXPORTS) != set(__all__):
    missing = sorted(set(__all__) - set(_LAZY_EXPORTS))
    extra = sorted(set(_LAZY_EXPORTS) - set(__all__))
    raise RuntimeError(f"lazy public API registry drift: missing={missing}, extra={extra}")


def __getattr__(name: str) -> object:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = import_module(module_name, __name__)
    try:
        value = vars(module)[attribute_name]
    except KeyError as error:
        raise ImportError(
            f"lazy public API target is missing: {module.__name__}.{attribute_name}"
        ) from error
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
```

- [ ] **Step 3: Run the red tests and verify they pass green**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_public_api_import_boundary.py
```

Expected: `2 passed`.

- [ ] **Step 4: Commit the minimal lazy implementation**

```powershell
git add platform/src/agent_ex/__init__.py
git commit -m "fix(platform): defer root public API imports"
```

### Task 3: Prove the complete compatibility boundary

**Files:**
- Modify: `platform/tests/test_public_api_import_boundary.py`
- Modify: `platform/tests/test_installation.py`

- [ ] **Step 1: Add registry, object identity, cache, `dir`, unknown-name, and submodule tests**

Append to `platform/tests/test_public_api_import_boundary.py`:

```python
def test_lazy_registry_exactly_matches_stable_public_api() -> None:
    assert list(agent_ex.__all__) == list(dict.fromkeys(agent_ex.__all__))
    assert set(agent_ex._LAZY_EXPORTS) == set(agent_ex.__all__)  # noqa: SLF001


@pytest.mark.parametrize("name", agent_ex.__all__)
def test_every_public_export_resolves_to_defining_object_and_is_cached(name: str) -> None:
    module_name, attribute_name = agent_ex._LAZY_EXPORTS[name]  # noqa: SLF001
    expected = vars(importlib.import_module(module_name, agent_ex.__name__))[attribute_name]
    resolved = getattr(agent_ex, name)

    assert resolved is expected
    assert getattr(agent_ex, name) is resolved
    assert getattr(resolved, "__module__", None) == getattr(expected, "__module__", None)


def test_dir_exposes_all_stable_public_names() -> None:
    assert set(agent_ex.__all__) <= set(dir(agent_ex))


def test_unknown_package_attribute_has_normal_error() -> None:
    with pytest.raises(
        AttributeError,
        match=r"module 'agent_ex' has no attribute 'not_a_public_export'",
    ):
        agent_ex.not_a_public_export


def test_direct_submodule_import_remains_supported() -> None:
    from agent_ex import protocol

    assert protocol is importlib.import_module("agent_ex.protocol")
```

- [ ] **Step 2: Extend the wheel runner with public API and console-entry checks**

In the generated `wheel_smoke.py` body in `platform/tests/test_installation.py`, immediately after `import agent_ex`, add:

```python
from importlib.metadata import distribution
from agent_ex import validate_protocol as public_validate_protocol
from agent_ex.protocol import validate_protocol as defining_validate_protocol

assert public_validate_protocol is defining_validate_protocol
assert set(agent_ex._LAZY_EXPORTS) == set(agent_ex.__all__)
entry_points = {
    entry.name: entry.value
    for entry in distribution("agent-ex").entry_points
    if entry.group == "console_scripts"
}
assert entry_points["agent-ex-phase0a1"] == "agent_ex.calibration.cli:main"
```

- [ ] **Step 3: Run the complete compatibility tests**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_public_api_import_boundary.py tests/test_installation.py tests/test_calibration_cli.py
```

Expected: all selected tests pass, including 142 parameterized export cases and the isolated wheel test.

- [ ] **Step 4: Commit compatibility evidence**

```powershell
git add platform/tests/test_public_api_import_boundary.py platform/tests/test_installation.py
git commit -m "test(platform): verify lazy API compatibility"
```

### Task 3A: Remove the adapter-facade circular import

**Files:**
- Modify: `platform/tests/test_public_api_import_boundary.py`
- Modify: `platform/src/agent_ex/adapters/__init__.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Test: `platform/tests/test_storage.py`

- [ ] **Step 1: Add fresh-process regressions and correct the independent contract**

In `PUBLIC_API_CONTRACT`, change only these three tuples so the frozen contract names
the true defining module rather than the adapter facade:

```python
    ("MockAdapter", ".adapters.mock", "MockAdapter"),
    ("MockScriptStep", ".adapters.mock", "MockScriptStep"),
    ("validate_adapter_response", ".adapters.mock", "validate_adapter_response"),
```

Append these tests to `platform/tests/test_public_api_import_boundary.py`:

```python
def test_direct_execution_evidence_import_does_not_prime_mock_adapter() -> None:
    completed = _source_subprocess(
        """
        import sys

        import agent_ex.execution_evidence

        assert "agent_ex.adapters.base" in sys.modules
        assert "agent_ex.adapters.mock" not in sys.modules
        """,
        include_dependencies=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_root_mock_adapter_export_loads_true_defining_object_from_fresh_process() -> None:
    completed = _source_subprocess(
        """
        import sys

        import agent_ex

        assert "MockAdapter" not in vars(agent_ex)
        assert "agent_ex.adapters.mock" not in sys.modules
        resolved = agent_ex.MockAdapter
        from agent_ex.adapters.mock import MockAdapter

        assert resolved is MockAdapter
        assert vars(agent_ex)["MockAdapter"] is MockAdapter
        """,
        include_dependencies=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_adapter_facade_lazily_preserves_mock_exports() -> None:
    completed = _source_subprocess(
        """
        import sys

        import agent_ex.adapters as adapters

        assert "agent_ex.adapters.mock" not in sys.modules
        from agent_ex.adapters import MockAdapter, MockScriptStep, validate_adapter_response
        from agent_ex.adapters import mock

        assert "agent_ex.adapters.mock" in sys.modules
        assert MockAdapter is mock.MockAdapter
        assert MockScriptStep is mock.MockScriptStep
        assert validate_adapter_response is mock.validate_adapter_response
        assert vars(adapters)["MockAdapter"] is MockAdapter
        assert vars(adapters)["MockScriptStep"] is MockScriptStep
        assert vars(adapters)["validate_adapter_response"] is validate_adapter_response
        """,
        include_dependencies=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
```

- [ ] **Step 2: Run the minimal reproduction and confirm the cycle is red**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q `
  tests/test_public_api_import_boundary.py::test_direct_execution_evidence_import_does_not_prime_mock_adapter `
  tests/test_public_api_import_boundary.py::test_root_mock_adapter_export_loads_true_defining_object_from_fresh_process `
  tests/test_public_api_import_boundary.py::test_adapter_facade_lazily_preserves_mock_exports `
  tests/test_storage.py::test_second_process_direct_mutator_is_rejected_and_crash_releases_lease `
  tests/test_storage.py::test_hardlink_alias_blocks_every_preopened_writer_and_cross_process_owner
```

Expected before the repair: the direct `execution_evidence` case and both storage
cross-process cases fail through
`execution_evidence -> adapters.__init__ -> adapters.mock -> execution_evidence`.
The root and facade cases may already pass because the old facade import order happens
to prime `adapters.base`; they do not replace the direct-import red evidence.

- [ ] **Step 3: Make the adapter facade base-eager and mock-lazy**

Replace `platform/src/agent_ex/adapters/__init__.py` with:

```python
"""Model adapter contracts and mock-only Phase 4B-7 implementation."""

from collections.abc import Mapping
from importlib import import_module
from types import MappingProxyType
from typing import Final

from .base import AdapterRequest, AdapterResponse, ModelAdapter


_EAGER_EXPORTS: Final = frozenset({"AdapterRequest", "AdapterResponse", "ModelAdapter"})
_LAZY_EXPORTS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "MockAdapter": (".mock", "MockAdapter"),
        "MockScriptStep": (".mock", "MockScriptStep"),
        "validate_adapter_response": (".mock", "validate_adapter_response"),
    }
)

__all__ = [
    "AdapterRequest",
    "AdapterResponse",
    "MockAdapter",
    "MockScriptStep",
    "ModelAdapter",
    "validate_adapter_response",
]


if _EAGER_EXPORTS & set(_LAZY_EXPORTS):
    raise RuntimeError("adapter facade eager and lazy exports overlap")
if _EAGER_EXPORTS | set(_LAZY_EXPORTS) != set(__all__):
    missing = sorted(set(__all__) - (_EAGER_EXPORTS | set(_LAZY_EXPORTS)))
    extra = sorted((_EAGER_EXPORTS | set(_LAZY_EXPORTS)) - set(__all__))
    raise RuntimeError(f"adapter facade export drift: missing={missing}, extra={extra}")


def __getattr__(name: str) -> object:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = import_module(module_name, __name__)
    try:
        value = vars(module)[attribute_name]
    except KeyError as error:
        raise ImportError(
            f"lazy adapter facade target is missing: {module.__name__}.{attribute_name}"
        ) from error
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
```

- [ ] **Step 4: Point the three root mock exports at their true defining module**

In `platform/src/agent_ex/__init__.py`, change only these registry values:

```python
        "MockAdapter": (".adapters.mock", "MockAdapter"),
        "MockScriptStep": (".adapters.mock", "MockScriptStep"),
        "validate_adapter_response": (".adapters.mock", "validate_adapter_response"),
```

Do not change `agent_ex.__all__`, the other 139 registry entries, or any adapter,
evidence, storage, protocol, or experiment implementation.

- [ ] **Step 5: Run the cycle and compatibility gates green**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q `
  tests/test_public_api_import_boundary.py `
  tests/test_installation.py `
  tests/test_calibration_cli.py `
  tests/test_storage.py::test_second_process_direct_mutator_is_rejected_and_crash_releases_lease `
  tests/test_storage.py::test_hardlink_alias_blocks_every_preopened_writer_and_cross_process_owner
& .\.venv\Scripts\python.exe -m ruff check `
  src/agent_ex/__init__.py src/agent_ex/adapters/__init__.py `
  tests/test_public_api_import_boundary.py
& .\.venv\Scripts\python.exe -m ruff format --check `
  src/agent_ex/__init__.py src/agent_ex/adapters/__init__.py `
  tests/test_public_api_import_boundary.py
git -C .. diff --check
```

Expected: all selected tests and static checks pass. The two storage subprocess tests
must reach their intended exit-code assertions rather than fail during import.

- [ ] **Step 6: Commit the cycle repair**

```powershell
git add platform/src/agent_ex/__init__.py platform/src/agent_ex/adapters/__init__.py platform/tests/test_public_api_import_boundary.py
git commit -m "fix(platform): break adapter facade import cycle"
```

### Task 4: Run local release gates and record the repair checkpoint

**Files:**
- Modify: `docs/superpowers/plans/2026-09-14-phase0a1-preflight-import-boundary-implementation.md`

- [ ] **Step 1: Run focused tests and static checks**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_public_api_import_boundary.py tests/test_installation.py tests/test_calibration_cli.py tests/test_calibration_cloud.py
& .\.venv\Scripts\python.exe -m ruff check src tests
& .\.venv\Scripts\python.exe -m ruff format --check src tests
& .\.venv\Scripts\python.exe -m pip check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run the full non-release-scale suite**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q
```

Expected: all non-`release_scale` tests pass with only the existing intentional skips/deselection.

- [ ] **Step 3: Verify repository hygiene and exact diff scope**

```powershell
Set-Location ..
git diff --check 6c8af93 HEAD
git status --short
git diff --stat 6c8af93 HEAD
git ls-files .ssh_local .tmp_autodl_known_hosts
```

Expected: no whitespace error; only the plan, import-boundary implementation/tests, and any sanitized checkpoint log are changed; no SSH material is tracked.

- [ ] **Step 4: Check off completed local tasks and commit the verified plan state**

Update the completed checkboxes in this plan, then:

```powershell
git add docs/superpowers/plans/2026-09-14-phase0a1-preflight-import-boundary-implementation.md
git commit -m "docs(platform): record import-boundary verification"
```

### Task 5: Seal the failed cloud attempt and rerun authoritative preflight

**Files:**
- Create outside Git: `/root/autodl-tmp/agent-ex-phase0a1-evidence/failed-preflight-14cffa6.json`
- Create outside Git: `/root/autodl-tmp/agent-ex-phase0a1-evidence/preflight.json`
- Create: `logs/2026-09-14-phase0a1-preflight-import-repair.md`

- [ ] **Step 1: Ask the user to start the AutoDL instance and obtain the current SSH endpoint**

Do not assume that the previous endpoint `root@connect.bjb2.seetacloud.com:11741` survives a stop/start. Make no cloud call until the user supplies the current endpoint; this step is an external-state gate, not permission for a model request.

- [ ] **Step 2: Reverify the failed checkout before replacing it**

Over the user-supplied endpoint, run read-only checks against `/root/autodl-tmp/agent-ex-phase0a1`: `hostname`, `/root/miniconda3/bin/python --version`, `git rev-parse HEAD`, `git status --porcelain`, Python's observed `networkx.__version__`, and a file non-existence check for `/root/autodl-tmp/agent-ex-phase0a1-evidence/preflight.json`.

Expected: HEAD `14cffa67bcdc36d2e4f2f8628812259a322bb9d1`, clean checkout, Python 3.12.3, NetworkX 3.5, and absent output. Any mismatch stops this task and requires a revised receipt rather than rewriting history.

- [ ] **Step 3: Write and hash the sanitized failure receipt outside Git**

Use `/root/miniconda3/bin/python` with the following script to reproduce the original
failure against the still-clean old checkout, verify all expected observations, and
serialize a sorted compact receipt without any manually substituted value:

```python
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

checkout = Path("/root/autodl-tmp/agent-ex-phase0a1").resolve(strict=True)
evidence = Path("/root/autodl-tmp/agent-ex-phase0a1-evidence").resolve(strict=True)
output = evidence / "preflight.json"
receipt_path = evidence / "failed-preflight-14cffa6.json"
command = [
    "/root/miniconda3/bin/python",
    "-m",
    "agent_ex.calibration.cli",
    "preflight",
    "--output",
    str(output),
]
environment = os.environ.copy()
environment["PYTHONDONTWRITEBYTECODE"] = "1"
environment["PYTHONPATH"] = str(checkout / "platform" / "src")

head = subprocess.run(
    ["git", "-C", str(checkout), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
status = subprocess.run(
    ["git", "-C", str(checkout), "status", "--porcelain=v1", "--untracked-files=all"],
    check=True,
    capture_output=True,
    text=True,
).stdout
networkx_version = subprocess.run(
    ["/root/miniconda3/bin/python", "-c", "import networkx; print(networkx.__version__)"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
attempt = subprocess.run(
    command,
    cwd=checkout,
    env=environment,
    check=False,
    capture_output=True,
    text=True,
)
combined_error = attempt.stdout + attempt.stderr
expected_error = "network artifact implementation requires networkx==3.6.1; found 3.5"
assert head == "14cffa67bcdc36d2e4f2f8628812259a322bb9d1"
assert status == ""
assert networkx_version == "3.5"
assert attempt.returncode == 1
assert expected_error in combined_error
assert not output.exists()
assert not receipt_path.exists()

receipt = {
    "authority": {
        "install": False,
        "model_download": False,
        "model_request": False,
        "server_start": False,
        "smoke": False,
    },
    "checkout_clean": True,
    "checkout_head": head,
    "command_form": (
        "PYTHONDONTWRITEBYTECODE=1 "
        "PYTHONPATH=/root/autodl-tmp/agent-ex-phase0a1/platform/src "
        "/root/miniconda3/bin/python -m agent_ex.calibration.cli preflight "
        "--output /root/autodl-tmp/agent-ex-phase0a1-evidence/preflight.json"
    ),
    "error_summary": expected_error,
    "exit_code": attempt.returncode,
    "host_identifier": platform.node(),
    "networkx_version": networkx_version,
    "output_exists": False,
    "output_path": str(output),
    "python_version": platform.python_version(),
    "status": "failed_preflight",
}
encoded = json.dumps(
    receipt,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8") + b"\n"
descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as stream:
    stream.write(encoded)
    stream.flush()
    os.fsync(stream.fileno())
print(hashlib.sha256(encoded).hexdigest())
```

Do not include environment variables, credentials, SSH paths, or passwords. Calculate
the receipt SHA-256 independently, copy it to a local external evidence directory, and
verify equal hashes.

- [ ] **Step 4: Build and transfer an exact repaired Git bundle**

From the local worktree, create a full bundle containing the current `codex/paper1-phase0` HEAD, calculate its SHA-256, upload it to `/root/autodl-tmp/agent-ex-phase0a1-repaired.bundle`, and verify the remote hash equals the local hash. Do not put GitHub credentials on the cloud host.

- [ ] **Step 5: Replace only the failed checkout with a fresh exact-HEAD clone**

First resolve and verify that the old checkout is exactly `/root/autodl-tmp/agent-ex-phase0a1` and that the failure receipt is sealed. Rename it to `/root/autodl-tmp/agent-ex-phase0a1-failed-14cffa6`; do not recursively delete it. Clone the verified bundle into `/root/autodl-tmp/agent-ex-phase0a1`, checkout the bundled branch, and verify exact local HEAD and a clean status.

- [ ] **Step 6: Verify source binding and run preflight before installation**

Run the exact source check and bootstrap:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/root/autodl-tmp/agent-ex-phase0a1/platform/src \
/root/miniconda3/bin/python -c 'from pathlib import Path; import agent_ex; source=Path("/root/autodl-tmp/agent-ex-phase0a1/platform/src").resolve(); loaded=Path(agent_ex.__file__).resolve(); assert loaded.is_relative_to(source), (loaded, source); print(loaded)'

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/root/autodl-tmp/agent-ex-phase0a1/platform/src \
/root/miniconda3/bin/python -m agent_ex.calibration.cli preflight \
  --output /root/autodl-tmp/agent-ex-phase0a1-evidence/preflight.json
```

Expected: the source check prints a path below the repaired checkout; preflight exits 0 and creates exactly one JSON record. Do not install packages, source network turbo, download a model, start vLLM, or make a model request during this step.

- [ ] **Step 7: Reopen and cross-verify the authoritative record**

Copy `preflight.json` to the local external evidence directory, verify equal SHA-256, and use the repaired local source to call `CloudPreflight.from_payload`. Verify the canonical `record_hash`, repaired `git_commit`, `git_dirty is False`, exactly one visible RTX 5090, and all calibration-only/no-formal-authority flags.

- [ ] **Step 8: Commit only the sanitized cloud log**

Create `logs/2026-09-14-phase0a1-preflight-import-repair.md` recording the failed receipt hash/external path, repaired bundle hash, exact repaired commit, cloud preflight hash/external path, source-binding result, and explicit statements that no install/model download/server/model request occurred. Do not commit either raw JSON artifact.

```powershell
git add logs/2026-09-14-phase0a1-preflight-import-repair.md docs/superpowers/plans/2026-09-14-phase0a1-preflight-import-boundary-implementation.md
git commit -m "docs(platform): record repaired cloud preflight"
```

- [ ] **Step 9: Stop at the existing smoke authorization boundary**

The repaired preflight grants no smoke authority. Return to Task 9 Step 2 of `docs/superpowers/plans/2026-09-10-paper1-phase0a1-cloud-probe-implementation.md`; obtain the separately required authorization before dependency installation, immutable Qwen3-8B download, vLLM startup, or any of the ten real smoke requests.
