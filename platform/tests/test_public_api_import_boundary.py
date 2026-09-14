"""Regression tests for the source-bound, pre-install Agent-EX import boundary."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

import agent_ex

PLATFORM_ROOT = Path(__file__).parents[1].resolve()
SOURCE_ROOT = (PLATFORM_ROOT / "src").resolve()

PUBLIC_API_CONTRACT = (
    ("ArtifactEnvelope", ".artifacts", "ArtifactEnvelope"),
    ("Checkpoint", ".checkpoint", "Checkpoint"),
    ("AdapterRequest", ".adapters", "AdapterRequest"),
    ("AdapterResponse", ".adapters", "AdapterResponse"),
    ("AttemptAuthorization", ".engine", "AttemptAuthorization"),
    ("AttemptExecutionEvidence", ".engine", "AttemptExecutionEvidence"),
    ("AttemptInvocationResult", ".engine", "AttemptInvocationResult"),
    ("AttemptLifecycleFailure", ".engine", "AttemptLifecycleFailure"),
    ("AttemptOutcome", ".engine", "AttemptOutcome"),
    ("EventStatus", ".domain", "EventStatus"),
    ("EventJournalState", ".storage", "EventJournalState"),
    ("EventEvidenceReferences", ".execution_evidence", "EventEvidenceReferences"),
    ("EventInputEvidence", ".execution_evidence", "EventInputEvidence"),
    ("ExecutionState", ".storage", "ExecutionState"),
    ("ExecutionStatus", ".storage", "ExecutionStatus"),
    ("ExposureSelection", ".feed", "ExposureSelection"),
    ("FeedCandidate", ".feed", "FeedCandidate"),
    ("FeedCursor", ".feed", "FeedCursor"),
    ("ExposureRecord", ".domain", "ExposureRecord"),
    ("ExposureProcessSummary", ".process_audit", "ExposureProcessSummary"),
    ("ExternalResponseReference", ".storage", "ExternalResponseReference"),
    ("ResumeAuthorizationEvidence", ".storage", "ResumeAuthorizationEvidence"),
    ("FrozenSchedule", ".domain", "FrozenSchedule"),
    ("FinalizedAttemptEvidence", ".execution_evidence", "FinalizedAttemptEvidence"),
    ("GenerationAttempt", ".domain", "GenerationAttempt"),
    ("GenerationEvent", ".domain", "GenerationEvent"),
    ("LatestPublicPointer", ".state", "LatestPublicPointer"),
    ("MemoryItem", ".memory", "MemoryItem"),
    ("MemoryView", ".memory", "MemoryView"),
    ("MockAdapter", ".adapters", "MockAdapter"),
    ("MockEventPipeline", ".pipeline", "MockEventPipeline"),
    ("MockEventPipelineOutcome", ".pipeline", "MockEventPipelineOutcome"),
    ("MockAdapterExecutionBinding", ".execution_evidence", "MockAdapterExecutionBinding"),
    ("MockAttemptPolicyBinding", ".execution_evidence", "MockAttemptPolicyBinding"),
    ("MockScriptStep", ".adapters", "MockScriptStep"),
    ("MockScaleCase", ".mock_matrix", "MockScaleCase"),
    ("MockEventInvocation", ".mock_run", "MockEventInvocation"),
    ("MockRunControl", ".mock_run", "MockRunControl"),
    ("MockRunReport", ".mock_run", "MockRunReport"),
    ("MockProcessAudit", ".process_audit", "MockProcessAudit"),
    ("MockComparableRunProjection", ".process_audit", "MockComparableRunProjection"),
    ("MockCellBinding", ".mock_matrix", "MockCellBinding"),
    ("MockMatchedSeedMatrix", ".mock_matrix", "MockMatchedSeedMatrix"),
    ("CANONICAL_CELL_IDS", ".mock_matrix", "CANONICAL_CELL_IDS"),
    ("ModelAdapter", ".adapters", "ModelAdapter"),
    ("ParseEvidence", ".parser", "ParseEvidence"),
    ("ParseNotApplicableEvidence", ".execution_evidence", "ParseNotApplicableEvidence"),
    ("ParsedAgentUpdate", ".parser", "ParsedAgentUpdate"),
    ("ParserLimits", ".parser", "ParserLimits"),
    ("PrivateState", ".state", "PrivateState"),
    ("PrivateUpdate", ".state", "PrivateUpdate"),
    ("PreparedAttempt", ".engine", "PreparedAttempt"),
    ("PersistedInvocationEvidence", ".execution_evidence", "PersistedInvocationEvidence"),
    ("PromptView", ".prompt", "PromptView"),
    ("PromptLimits", ".prompt", "PromptLimits"),
    ("ProbeCase", ".calibration", "ProbeCase"),
    ("ProbePersonaView", ".calibration", "ProbePersonaView"),
    ("ProbeTopicCandidate", ".calibration", "ProbeTopicCandidate"),
    ("ValidatedPromptRunContext", ".prompt", "ValidatedPromptRunContext"),
    ("PublicPost", ".state", "PublicPost"),
    ("RNGProvenance", ".rng", "RNGProvenance"),
    ("RunManifest", ".domain", "RunManifest"),
    ("RunLease", ".storage", "RunLease"),
    ("RunStorage", ".storage", "RunStorage"),
    ("RoundZeroBaseline", ".process_audit", "RoundZeroBaseline"),
    ("ScheduleSlot", ".domain", "ScheduleSlot"),
    ("StorageBinding", ".storage", "StorageBinding"),
    ("StorageProgress", ".storage", "StorageProgress"),
    ("StrictSerialLifecycleEngine", ".engine", "StrictSerialLifecycleEngine"),
    ("SuccessfulEventCommit", ".engine", "SuccessfulEventCommit"),
    ("SweepProcessAudit", ".process_audit", "SweepProcessAudit"),
    ("TerminalFailureEvidence", ".storage", "TerminalFailureEvidence"),
    ("TRSIntegerization", ".population", "TRSIntegerization"),
    ("TopicPackage", ".topic", "TopicPackage"),
    ("assign_initial_reasons", ".initialization", "assign_initial_reasons"),
    ("assign_initial_stances", ".initialization", "assign_initial_stances"),
    (
        "advance_validated_prompt_run_context",
        ".prompt",
        "advance_validated_prompt_run_context",
    ),
    ("build_agent_node_mapping", ".network", "build_agent_node_mapping"),
    ("build_checkpoint", ".checkpoint", "build_checkpoint"),
    ("build_activation_schedule", ".schedule", "build_activation_schedule"),
    ("build_attention_artifact", ".schedule", "build_attention_artifact"),
    ("build_expression_artifact", ".schedule", "build_expression_artifact"),
    ("build_exposure_record", ".feed", "build_exposure_record"),
    ("build_memory_view", ".memory", "build_memory_view"),
    ("build_mock_matched_seed_matrix", ".mock_matrix", "build_mock_matched_seed_matrix"),
    ("build_mock_process_audit", ".process_audit", "build_mock_process_audit"),
    (
        "build_mock_comparable_run_projection",
        ".process_audit",
        "build_mock_comparable_run_projection",
    ),
    ("build_population_artifact", ".population", "build_population_artifact"),
    ("build_publish_schedule", ".schedule", "build_publish_schedule"),
    ("build_prompt_view", ".prompt", "build_prompt_view"),
    ("build_shadow_artifact", ".network", "build_shadow_artifact"),
    ("build_structural_gate_artifact", ".network", "build_structural_gate_artifact"),
    ("build_ws_artifact", ".network", "build_ws_artifact"),
    ("canonical_payload_hash", ".domain", "canonical_payload_hash"),
    ("canonical_protocol_hash", ".protocol", "canonical_protocol_hash"),
    ("derive_attempt_id", ".domain", "derive_attempt_id"),
    ("derive_event_id", ".domain", "derive_event_id"),
    ("derive_rng_seed", ".rng", "derive_rng_seed"),
    ("derive_run_id", ".domain", "derive_run_id"),
    ("evaluate_analysis_eligibility", ".domain", "evaluate_analysis_eligibility"),
    ("execution_projection", ".protocol", "execution_projection"),
    ("execute_mock_run", ".mock_run", "execute_mock_run"),
    ("load_protocol", ".protocol", "load_protocol"),
    (
        "load_runnable_probe_specification",
        ".calibration",
        "load_runnable_probe_specification",
    ),
    ("load_checkpoint", ".checkpoint", "load_checkpoint"),
    ("load_mock_scale_cases", ".mock_matrix", "load_mock_scale_cases"),
    ("mock_adapter_semantics_hash", ".mock_matrix", "mock_adapter_semantics_hash"),
    ("mock_clock_sequence_binding", ".mock_matrix", "mock_clock_sequence_binding"),
    ("parse_agent_update", ".parser", "parse_agent_update"),
    ("render_human_protocol_summary", ".validation", "render_human_protocol_summary"),
    (
        "reconstruct_event_rng_provenance",
        ".schedule",
        "reconstruct_event_rng_provenance",
    ),
    ("render_persona", ".persona", "render_persona"),
    ("render_messages", ".prompt", "render_messages"),
    ("run_offline_probe", ".calibration", "run_offline_probe"),
    ("select_unread_feed", ".feed", "select_unread_feed"),
    ("scripted_probe_adapter", ".calibration", "scripted_probe_adapter"),
    ("trs_integerize", ".population", "trs_integerize"),
    ("update_human_protocol_summary", ".validation", "update_human_protocol_summary"),
    (
        "validate_human_protocol_reference",
        ".validation",
        "validate_human_protocol_reference",
    ),
    ("validate_human_protocol_sync", ".validation", "validate_human_protocol_sync"),
    ("validate_matched_schedule_reuse", ".schedule", "validate_matched_schedule_reuse"),
    ("validate_latest_public_pointer", ".state", "validate_latest_public_pointer"),
    ("validate_memory_view", ".memory", "validate_memory_view"),
    (
        "validate_mock_matched_seed_matrix",
        ".mock_matrix",
        "validate_mock_matched_seed_matrix",
    ),
    ("validate_private_state", ".state", "validate_private_state"),
    ("validate_public_post", ".state", "validate_public_post"),
    ("validate_shadow_artifact", ".network", "validate_shadow_artifact"),
    (
        "validate_structural_gate_artifact",
        ".network",
        "validate_structural_gate_artifact",
    ),
    ("validate_ws_artifact", ".network", "validate_ws_artifact"),
    ("validate_persona_factor_diff", ".persona", "validate_persona_factor_diff"),
    ("validate_evidence_graph", ".domain", "validate_evidence_graph"),
    ("validate_exposure_record", ".feed", "validate_exposure_record"),
    ("validate_exposure_selection", ".feed", "validate_exposure_selection"),
    ("validate_event_rng_ledger", ".schedule", "validate_event_rng_ledger"),
    ("validate_protocol", ".protocol", "validate_protocol"),
    ("validate_adapter_response", ".adapters", "validate_adapter_response"),
    ("validate_checkpoint", ".checkpoint", "validate_checkpoint"),
    ("validate_parse_evidence", ".parser", "validate_parse_evidence"),
    ("validate_prompt_view", ".prompt", "validate_prompt_view"),
    ("validate_prompt_run_context", ".prompt", "validate_prompt_run_context"),
    (
        "validated_prompt_run_context_metadata",
        ".prompt",
        "validated_prompt_run_context_metadata",
    ),
    ("write_checkpoint_atomic", ".checkpoint", "write_checkpoint_atomic"),
)


def _source_subprocess(
    script: str,
    *extra_paths: Path,
    include_dependencies: bool = False,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(path.resolve()) for path in extra_paths] + [str(SOURCE_ROOT)]
    )
    python_arguments = [] if include_dependencies else ["-S"]
    return subprocess.run(
        [sys.executable, *python_arguments, "-c", textwrap.dedent(script)],
        cwd=PLATFORM_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_lazy_registry_exactly_matches_stable_public_api() -> None:
    contract_names = tuple(name for name, _, _ in PUBLIC_API_CONTRACT)
    registry = agent_ex._LAZY_EXPORTS  # noqa: SLF001

    assert len(contract_names) == 142
    assert len(contract_names) == len(set(contract_names))
    assert tuple(agent_ex.__all__) == contract_names
    assert set(registry) == set(contract_names)
    assert all(
        registry[name] == (module_name, attribute_name)
        for name, module_name, attribute_name in PUBLIC_API_CONTRACT
    )


@pytest.mark.parametrize(
    ("name", "module_name", "attribute_name"),
    PUBLIC_API_CONTRACT,
)
def test_lazy_public_export_resolves_and_caches_exact_defining_object(
    name: str,
    module_name: str,
    attribute_name: str,
) -> None:
    completed = _source_subprocess(
        f"""
        import importlib
        import agent_ex

        name = {name!r}
        module_name = {module_name!r}
        attribute_name = {attribute_name!r}
        importlib.import_module(".adapters", agent_ex.__name__)
        assert name not in vars(agent_ex), name
        module = importlib.import_module(module_name, agent_ex.__name__)
        expected = vars(module)[attribute_name]
        resolved = getattr(agent_ex, name)
        assert resolved is expected, name
        assert vars(agent_ex)[name] is resolved, name
        assert getattr(agent_ex, name) is resolved, name
        assert getattr(resolved, "__module__", None) == getattr(
            expected, "__module__", None
        ), name
        """,
        include_dependencies=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_dir_covers_every_stable_public_export() -> None:
    completed = _source_subprocess(
        f"""
        import sys
        import agent_ex

        contract_names = {{name for name, _, _ in {PUBLIC_API_CONTRACT!r}}}
        heavy_modules = {{"agent_ex.network", "agent_ex.storage", "agent_ex.engine"}}
        assert heavy_modules.isdisjoint(sys.modules)
        assert contract_names <= set(dir(agent_ex))
        assert heavy_modules.isdisjoint(sys.modules)
        assert all(name not in vars(agent_ex) for name in contract_names)
        """,
        include_dependencies=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_unknown_public_export_raises_standard_attribute_error() -> None:
    with pytest.raises(
        AttributeError,
        match=r"^module 'agent_ex' has no attribute 'not_a_public_export'$",
    ):
        agent_ex.not_a_public_export


def test_direct_protocol_submodule_import_has_standard_identity() -> None:
    completed = _source_subprocess(
        """
        import importlib
        import sys
        import agent_ex

        assert "agent_ex.protocol" not in sys.modules
        from agent_ex import protocol

        expected = importlib.import_module("agent_ex.protocol")
        assert protocol is expected
        assert vars(agent_ex)["protocol"] is expected
        """,
        include_dependencies=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


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
