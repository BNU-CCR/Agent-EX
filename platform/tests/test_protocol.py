from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib import resources
import json
import math
from pathlib import Path

import jsonschema
import pytest
import yaml

from agent_ex import protocol as protocol_module
from agent_ex import (
    canonical_protocol_hash,
    load_protocol,
    render_human_protocol_summary,
    update_human_protocol_summary,
    validate_human_protocol_sync,
    validate_protocol,
)


PLATFORM_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = PLATFORM_ROOT.parent
PROTOCOL_PATH = PLATFORM_ROOT / "configs" / "paper1" / "protocol.yaml"
MIRROR_SCHEMA_PATH = PLATFORM_ROOT / "protocols" / "paper1.schema.json"
HUMAN_PROTOCOL_PATH = REPOSITORY_ROOT / "docs" / "paper1-protocol.md"
RESEARCH_QA_PATH = REPOSITORY_ROOT / "docs" / "research-qa.md"
DECISION_RECORDS_PATTERN = (
    "<!-- BEGIN DECISION RECORDS -->\n```yaml\n{body}```\n<!-- END DECISION RECORDS -->\n"
)


def _set(document, pointer: str, value) -> None:
    target = document
    parts = pointer.strip("/").split("/")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def _delete(document, pointer: str) -> None:
    target = document
    parts = pointer.strip("/").split("/")
    for part in parts[:-1]:
        target = target[part]
    del target[parts[-1]]


@pytest.fixture
def protocol() -> dict[str, object]:
    return load_protocol(PROTOCOL_PATH)


@pytest.fixture
def frozen_protocol(protocol) -> dict[str, object]:
    candidate = deepcopy(protocol)
    replacements = {
        "/protocol/version": "1.0.0",
        "/topic/id": "P1-TOPIC-001",
        "/topic/statement": "The city should expand its public transit system.",
        "/topic/statement_sha256": (
            "1bf032505ebcf1becc82c88623b93a3f3b8546c046ba855ce6f4d0d1810c6466"
        ),
        "/stance/construct": "support_for_public_transit_expansion",
        "/stance/scale": {"minimum": -1.0, "maximum": 1.0},
        "/population/source": "audited_synthetic_population",
        "/population/fields": ["age_band", "education", "topic_experience"],
        "/population/balance": "joint_quota",
        "/population/exact_n": "largest_remainder_then_seeded_shuffle",
        "/initialization/stance": "stratified_uniform",
        "/initialization/reason": "matched_template_bank",
        "/initialization/matched_across_cells": True,
        "/groups/cuts": [-0.34, 0.34],
        "/groups/min_size": 100,
        "/persona/identity_absent_continuity_absent/template_id": "persona-i0-c0-v1",
        "/persona/identity_absent_continuity_absent/template_sha256": "1" * 64,
        "/persona/identity_absent_continuity_present/template_id": "persona-i0-c1-v1",
        "/persona/identity_absent_continuity_present/template_sha256": "2" * 64,
        "/persona/identity_present_continuity_absent/template_id": "persona-i1-c0-v1",
        "/persona/identity_present_continuity_absent/template_sha256": "3" * 64,
        "/persona/identity_present_continuity_present/template_id": "persona-i1-c1-v1",
        "/persona/identity_present_continuity_present/template_sha256": "4" * 64,
        "/network/directed": False,
        "/network/connectivity": "connected",
        "/network/on_invalid": "fail",
        "/network/library/version": "3.6.1",
        "/network/ws/k": 6,
        "/network/ws/p": 0.1,
        "/network/ws/builder_algorithm": "paper1.mock_networkx_watts_strogatz@1.0.0",
        "/network/shadow/builder_algorithm": (
            "paper1.mock_forbidden_edge_connected_double_swap@1.0.0"
        ),
        "/network/shadow/max_attempts": 3,
        "/network/shadow/trial_budget_per_edge": 1000,
        "/network/structure_gate/algorithm_version": "1.0.0",
        "/network/structure_gate/ring_lattice_algorithm": ("networkx.watts_strogatz_graph_p0"),
        "/network/structure_gate/random_null_algorithm": "networkx.gnm_random_graph",
        "/network/structure_gate/random_null_replicates": 3,
        "/dynamics/activation_mode": "weighted_random_sequential_with_replacement",
        "/dynamics/activation_count": 1000,
        "/dynamics/activity_weights/parameters": {
            "log_location": 0.0,
            "log_sigma": 0.8,
            "minimum": 0.05,
            "maximum": 20.0,
        },
        "/dynamics/activity_weights/calibration_targets": {
            "weight_gini_range": [0.2, 0.6],
            "realized_activation_gini_range": [0.2, 0.6],
            "top_1_percent_share_range": [0.01, 0.2],
            "top_10_percent_share_range": [0.2, 0.7],
            "maximum_individual_share_max": 0.2,
            "zero_activation_rate_range": [0.0, 0.5],
            "cross_sweep_cv_range": [0.0, 1.0],
            "cross_n_absolute_tolerance": 0.1,
        },
        "/state_model/private_update_semantics": "private_then_optional_public_post",
        "/expression/publish_process/parameters": {
            "structural_lurker_probability": 0.4,
            "beta_alpha": 2.0,
            "beta_beta": 3.0,
        },
        "/expression/attention_expression_correlation/sensitivity": {
            "method": "gaussian_copula",
            "rho": 0.3,
        },
        "/memory/window": 5,
        "/exposure/feed_message_capacity": 6,
        "/exposure/social_count": "finite_unread_by_exposure_graph",
        "/model/revision": "0123456789abcdef",
        "/runtime/vllm/version": "0.10.0",
        "/runtime/timeout": {"seconds": 120.0},
        "/runtime/retry": {"max_attempts": 3},
        "/runtime/concurrency": {"max_requests": 32},
        "/runtime/rate_budget": {"requests_per_minute": 600},
        "/generation/temperature": 0.7,
        "/generation/top_p": 0.8,
        "/generation/max_tokens": 256,
        "/generation/seed": 42,
        "/generation/seed_pairing": "matched_by_event_ordinal_reused_for_retry",
        "/outcomes/primary/id": "private_state_endpoint_v1",
        "/outcomes/primary/definition": "mean_absolute_change_from_round_zero",
        "/outcomes/group_structure/t_star": 50,
        "/outcomes/group_structure/epsilon": 1e-6,
        "/metrics/variance_components": "weighted_anova_decomposition",
        "/metrics/ddof": 1,
        "/metrics/missing_group": "fail",
        "/sample_size/delta_min": 0.05,
        "/analysis/primary_test": "matched_seed_randomization_test",
        "/shapes/thresholds": {
            "homogenization": 0.1,
            "drift": 0.1,
            "polarization": 0.2,
            "bimodality": 0.2,
            "stagnation": 0.01,
        },
        "/shapes/window": 5,
        "/shapes/sensitivity": {"lower": 0.8, "upper": 1.2},
        "/gates/continuity/scoring": "blind_human_and_rule",
        "/gates/continuity/lock_max": 0.05,
        "/gates/quality/refusal_max": 0.01,
        "/gates/quality/parse_failure_max": 0.01,
        "/gates/scale/design": "primary_eight_cells_matched_seeds",
        "/gates/scale/primary_outcome_tolerance": 0.02,
        "/gates/scale/group_structure_delta_tolerance": 0.02,
        "/gates/scale/failure_max": 0.01,
        "/gates/scale/throughput_min": 5.0,
        "/gates/scale/memory_max": 24.0,
        "/gates/formal/duration_max": 168.0,
        "/gates/formal/recovery_drills": 2,
        "/gates/formal/matrix_complete": 1.0,
        "/quality/eligibility": "complete_only",
        "/quality/exclusion": "exclude_any_failed_imputed_or_fallback",
        "/stopping/on_gate_failure": "stop_before_formal",
        "/sampling/formal_seeds": list(range(20)),
        "/sampling/blind_ssr": {
            "initial_seed_count": 10,
            "maximum_seed_count": 20,
            "reestimate_after": 10,
            "statistic": "centered_primary_contrast_residual_variance",
            "decision_rule": "expand_once_to_precomputed_required_n_capped_at_20",
        },
        "/robustness/api/provider": "dashscope",
        "/robustness/api/model_snapshot": "qwen-plus-2025-12-01",
        "/robustness/api/cells": [
            "P1-I0-C0-E1",
            "P1-I0-C0-E2",
            "P1-I0-C1-E1",
            "P1-I0-C1-E2",
            "P1-I1-C0-E1",
            "P1-I1-C0-E2",
            "P1-I1-C1-E1",
            "P1-I1-C1-E2",
        ],
        "/robustness/api/scale": {"population_size": 200, "rounds": 50, "seeds": 5},
        "/storage/archive_uri": "s3://agent-ex-paper1/frozen/run-data",
        "/provenance/archive_map": {"pilot": "s3://agent-ex-paper1/pilot/manifest.json"},
    }
    candidate["status"] = "frozen"
    for pointer, value in replacements.items():
        _set(candidate, pointer, value)
    schema = json.loads(
        resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text("utf-8")
    )
    decision_ids = _schema_decision_paths(schema)
    candidate["decision_provenance"] = {
        decision_id: {
            "decision_record_id": f"D-TEST-{index:03d}",
            "approved_at": "2026-07-16T04:00:00Z",
            "approvers": [_qa_owners()[decision_id]],
        }
        for index, decision_id in enumerate(sorted(decision_ids), start=1)
    }
    return candidate


def _schema_decision_paths(schema: dict[str, object]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}

    def walk(node, path: str) -> None:
        if not isinstance(node, dict):
            return
        decision_id = node.get("x-decision-id")
        if decision_id:
            found.setdefault(decision_id, set()).add(path)
        for name, child in node.get("properties", {}).items():
            walk(child, f"{path}.{name}" if path else name)

    walk(schema, "")
    return found


def _qa_decision_paths() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for line in RESEARCH_QA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| P1_"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        found[columns[0]] = {path.strip() for path in columns[-1].split(",")}
    return found


def _qa_owners() -> dict[str, str]:
    found = {}
    for line in RESEARCH_QA_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("| P1_"):
            columns = [column.strip() for column in line.strip("|").split("|")]
            found[columns[0]] = columns[3]
    return found


def _artifact_hashes(protocol, schema, decision_id: str) -> dict[str, str]:
    paths = _schema_decision_paths(schema)[decision_id]
    payload = {}
    for path in paths:
        value = protocol
        for part in path.split("."):
            value = value[part]
        payload[f"/{path.replace('.', '/')}"] = value
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {decision_id: hashlib.sha256(encoded).hexdigest()}


def _read_decision_records(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    body = text.split("```yaml\n", 1)[1].split("```", 1)[0]
    return yaml.safe_load(body)


def _write_decision_records(path: Path, document: dict[str, object]) -> None:
    body = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    path.write_text(DECISION_RECORDS_PATTERN.format(body=body), encoding="utf-8")


@pytest.fixture
def approved_decisions_path(frozen_protocol, tmp_path) -> Path:
    path = tmp_path / "decisions.md"
    schema = json.loads(
        resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text("utf-8")
    )
    records = []
    for decision_id, provenance in frozen_protocol["decision_provenance"].items():
        records.append(
            {
                **provenance,
                "field_ids": [decision_id],
                "artifact_hashes": _artifact_hashes(frozen_protocol, schema, decision_id),
            }
        )
    body = yaml.safe_dump({"records": records}, sort_keys=False, allow_unicode=True)
    path.write_text(DECISION_RECORDS_PATTERN.format(body=body), encoding="utf-8")
    return path


@pytest.fixture
def approved_human_protocol_path(frozen_protocol, tmp_path) -> Path:
    path = tmp_path / "paper1-protocol.md"
    path.write_text(render_human_protocol_summary(frozen_protocol), encoding="utf-8")
    return path


def test_mode_and_status_are_consistent(
    protocol,
    frozen_protocol,
    approved_decisions_path,
    approved_human_protocol_path,
):
    validate_protocol(protocol, mode="draft")
    confirmed = deepcopy(frozen_protocol)
    confirmed["status"] = "confirmed"
    validate_protocol(confirmed, mode="confirmed")
    validate_protocol(
        frozen_protocol,
        mode="formal",
        decisions_path=approved_decisions_path,
        human_protocol_path=approved_human_protocol_path,
    )

    for mode, invalid_statuses in {
        "draft": ("confirmed", "frozen"),
        "confirmed": ("draft", "frozen"),
        "formal": ("draft", "confirmed"),
    }.items():
        for status in invalid_statuses:
            candidate = deepcopy(frozen_protocol)
            candidate["status"] = status
            with pytest.raises(ValueError, match=f"{mode} mode requires status"):
                validate_protocol(
                    candidate,
                    mode=mode,
                    decisions_path=approved_decisions_path,
                    human_protocol_path=approved_human_protocol_path,
                )


def test_draft_accepts_only_registered_unresolved_markers(protocol):
    validate_protocol(protocol, mode="draft")
    candidate = deepcopy(protocol)
    candidate["model"]["revision"] = "TBD"
    with pytest.raises(ValueError, match="placeholder"):
        validate_protocol(candidate, mode="draft")
    candidate["model"]["revision"] = "UNRESOLVED[P1_NOT_REGISTERED]"
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(candidate, mode="draft")


def test_formal_rejects_phase4b_draft_unresolved_fields(protocol):
    candidate = deepcopy(protocol)
    candidate["status"] = "frozen"
    with pytest.raises(ValueError, match="placeholder|unresolved"):
        validate_protocol(candidate, mode="formal")


def test_lognormal_location_must_be_explicit_in_resolved_protocol(frozen_protocol):
    schema = json.loads(MIRROR_SCHEMA_PATH.read_text(encoding="utf-8"))
    parameters_schema = schema["properties"]["dynamics"]["properties"]["activity_weights"][
        "properties"
    ]["parameters"]["oneOf"][0]
    assert "log_location" in parameters_schema["required"]
    assert "default" not in parameters_schema["properties"]["log_location"]

    candidate = deepcopy(frozen_protocol)
    del candidate["dynamics"]["activity_weights"]["parameters"]["log_location"]
    with pytest.raises(ValueError, match="schema.*activity_weights.parameters"):
        validate_protocol(candidate, mode="confirmed")


def test_draft_contains_registered_markers_instead_of_coder_defaults(protocol):
    expected = {
        "/population/source": "UNRESOLVED[P1_POPULATION_SOURCE]",
        "/population/fields": "UNRESOLVED[P1_POPULATION_FIELDS]",
        "/initialization/reason": "UNRESOLVED[P1_INITIAL_REASON_SOURCE]",
        "/network/directed": "UNRESOLVED[P1_GRAPH_DIRECTION]",
        "/network/library/version": "UNRESOLVED[P1_NETWORK_LIBRARY_VERSION]",
        "/network/ws/builder_algorithm": "UNRESOLVED[P1_WS_BUILDER_ALGORITHM]",
        "/network/shadow/builder_algorithm": "UNRESOLVED[P1_SHADOW_BUILDER_ALGORITHM]",
        "/network/shadow/max_attempts": "UNRESOLVED[P1_SHADOW_MAX_ATTEMPTS]",
        "/network/shadow/trial_budget_per_edge": ("UNRESOLVED[P1_SHADOW_TRIAL_BUDGET_PER_EDGE]"),
        "/network/structure_gate/algorithm_version": (
            "UNRESOLVED[P1_STRUCTURE_GATE_ALGORITHM_VERSION]"
        ),
        "/network/structure_gate/ring_lattice_algorithm": (
            "UNRESOLVED[P1_RING_LATTICE_BASELINE_ALGORITHM]"
        ),
        "/network/structure_gate/random_null_algorithm": (
            "UNRESOLVED[P1_RANDOM_GRAPH_NULL_ALGORITHM]"
        ),
        "/network/structure_gate/random_null_replicates": (
            "UNRESOLVED[P1_RANDOM_GRAPH_NULL_REPLICATES]"
        ),
        "/dynamics/activation_mode": "weighted_random_sequential_with_replacement",
        "/dynamics/activity_weights/parameters": ("UNRESOLVED[P1_ACTIVITY_WEIGHT_DISTRIBUTION]"),
        "/dynamics/activity_weights/calibration_targets": (
            "UNRESOLVED[P1_ACTIVITY_CALIBRATION_TARGETS]"
        ),
        "/expression/publish_process/parameters": "UNRESOLVED[P1_PUBLISH_PROCESS]",
        "/expression/attention_expression_correlation/sensitivity": (
            "UNRESOLVED[P1_ATTENTION_EXPRESSION_CORRELATION]"
        ),
        "/memory/window": "UNRESOLVED[P1_MEMORY_WINDOW]",
        "/exposure/feed_message_capacity": "UNRESOLVED[P1_MAX_NEIGHBORS]",
        "/generation/seed": "UNRESOLVED[P1_REQUEST_SEED]",
        "/generation/seed_pairing": "UNRESOLVED[P1_MODEL_SEED_PAIRING]",
        "/outcomes/primary/id": "UNRESOLVED[P1_PRIMARY_OUTCOME]",
        "/outcomes/primary/definition": "UNRESOLVED[P1_PRIMARY_OUTCOME]",
        "/runtime/timeout": "UNRESOLVED[P1_TIMEOUT_RETRY]",
        "/runtime/concurrency": "UNRESOLVED[P1_CONCURRENCY_BUDGET]",
        "/metrics/ddof": "UNRESOLVED[P1_BW_DDOF]",
        "/sample_size/delta_min": "UNRESOLVED[P1_DELTA_MIN]",
        "/shapes/window": "UNRESOLVED[P1_SHAPE_WINDOW]",
        "/gates/scale/primary_outcome_tolerance": ("UNRESOLVED[P1_GATE_PRIMARY_OUTCOME_STABILITY]"),
        "/robustness/api/provider": "UNRESOLVED[P1_API_PROVIDER]",
        "/quality/eligibility": "UNRESOLVED[P1_ANALYSIS_ELIGIBILITY]",
        "/sampling/formal_seeds": "UNRESOLVED[P1_FORMAL_SEEDS]",
        "/storage/archive_uri": "UNRESOLVED[P1_DATA_ARCHIVE_URI]",
        "/provenance/archive_map": "UNRESOLVED[P1_ARCHIVE_PROVENANCE_MAP]",
    }
    for pointer, value in expected.items():
        target = protocol
        for part in pointer.strip("/").split("/"):
            target = target[part]
        assert target == value


def test_phase4b_protocol_contract_replaces_synchronous_round_semantics(protocol):
    assert protocol["primary_estimand"] == {
        "id": "P1_PRIMARY_WS_SHADOW_AVERAGE_EFFECT",
        "definition": ("equal_weight_identity_continuity_average_of_matched_seed_ws_minus_shadow"),
    }
    assert protocol["analysis"]["hierarchy"]["key_secondary"] == [
        "P1_SECONDARY_CONTINUITY_WS_SHADOW_MODERATION"
    ]
    assert protocol["outcomes"]["group_structure"]["id"] == "P1_CANDIDATE_DELTA_LOG_BW"
    assert protocol["outcomes"]["primary"]["id"] == "UNRESOLVED[P1_PRIMARY_OUTCOME]"
    assert protocol["dynamics"]["activation_mode"] == "weighted_random_sequential_with_replacement"
    assert protocol["event_model"] == {
        "identity": "run_id_plus_event_ordinal",
        "read_state": "previous_successful_commit",
        "commit_order": "strict_serial",
        "failure_effect": "no_state_cursor_or_rng_progress",
        "retry_identity": "same_event_id_new_attempt_id",
        "sweep_role": "observation_and_checkpoint_boundary_only",
    }
    assert protocol["checkpoint"]["resume_cursor"] == "next_event_ordinal"
    assert protocol["state_model"]["social_exposure_reads"] == "public_posts_only"
    assert protocol["analysis"]["outcome_priority"] == {
        "primary": "private_state",
        "required_secondary": ["public_stock", "public_flow", "expression_gap"],
    }
    assert protocol["robustness"]["labels"] == {
        "model": ["primary_self_hosted", "api_snapshot_subset"],
        "prompt": ["canonical", "order_sensitivity"],
        "topic": ["primary", "reduced_topic_package"],
        "mechanism": [
            "equal_activity",
            "truncated_pareto_activity",
            "positive_attention_expression_correlation",
            "high_exposure_stock_snapshot",
        ],
    }
    assert "max_neighbors" not in protocol["exposure"]
    assert "all_synchronous" not in json.dumps(protocol)
    assert "subset_synchronous" not in json.dumps(protocol)
    assert "previous_round" not in json.dumps(protocol)


def test_legacy_protocol_fields_and_values_are_rejected(protocol):
    legacy_exposure = deepcopy(protocol)
    legacy_exposure["exposure"]["max_neighbors"] = legacy_exposure["exposure"].pop(
        "feed_message_capacity"
    )
    legacy_activation = deepcopy(protocol)
    legacy_activation["dynamics"]["activation_mode"] = "all_synchronous"
    legacy_primary = deepcopy(protocol)
    legacy_primary["outcomes"]["primary"] = {
        "id": "P1_PRIMARY_DELTA_LOG_BW",
        "definition": "delta_log_between_within",
        "t_star": "UNRESOLVED[P1_ENDPOINT_TSTAR]",
        "epsilon": "UNRESOLVED[P1_LOG_EPSILON]",
    }
    for candidate in (legacy_exposure, legacy_activation, legacy_primary):
        with pytest.raises(ValueError, match="schema"):
            validate_protocol(candidate, mode="draft")


def test_memory_window_rejects_removed_all_history_candidate(protocol):
    candidate = deepcopy(protocol)
    candidate["memory"]["window"] = "all_history"
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(candidate, mode="draft")


def test_activation_count_is_exactly_one_population_per_sweep(protocol):
    candidate = deepcopy(protocol)
    candidate["dynamics"]["activation_count"] = 500
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(candidate, mode="draft")


def test_seed_pairing_is_auditable_without_precommitting_one_resolved_answer(protocol):
    schema = json.loads(
        resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text("utf-8")
    )
    assert _schema_decision_paths(schema)["P1_MODEL_SEED_PAIRING"] == {"generation.seed_pairing"}
    assert "/generation/seed_pairing" in schema["x-formal-required"]

    candidate = deepcopy(protocol)
    candidate["generation"]["seed_pairing"] = "auditable_pairing_contract_selected_at_freeze"
    validate_protocol(candidate, mode="draft")

    candidate["generation"]["seed_pairing"] = ""
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(candidate, mode="draft")


def test_new_nested_process_blocks_reject_unknown_fields(frozen_protocol):
    candidate = deepcopy(frozen_protocol)
    candidate["dynamics"]["activity_weights"]["calibration_targets"]["outcome_delta"] = [
        0.0,
        1.0,
    ]
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(candidate, mode="confirmed")


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [
        (1.0, 1.0),
        (2.0, 1.0),
    ],
)
def test_activity_weight_minimum_must_be_strictly_below_maximum(frozen_protocol, minimum, maximum):
    candidate = deepcopy(frozen_protocol)
    candidate["status"] = "confirmed"
    parameters = candidate["dynamics"]["activity_weights"]["parameters"]
    parameters["minimum"] = minimum
    parameters["maximum"] = maximum
    with pytest.raises(
        ValueError,
        match=r"dynamics\.activity_weights\.parameters\.minimum.*maximum",
    ):
        validate_protocol(candidate, mode="confirmed")


@pytest.mark.parametrize(
    "field",
    [
        "weight_gini_range",
        "realized_activation_gini_range",
        "top_1_percent_share_range",
        "top_10_percent_share_range",
        "zero_activation_rate_range",
        "cross_sweep_cv_range",
    ],
)
def test_activity_calibration_ranges_require_ordered_bounds(frozen_protocol, field):
    candidate = deepcopy(frozen_protocol)
    candidate["status"] = "confirmed"
    candidate["dynamics"]["activity_weights"]["calibration_targets"][field] = [0.8, 0.2]
    with pytest.raises(
        ValueError,
        match=rf"dynamics\.activity_weights\.calibration_targets\.{field}",
    ):
        validate_protocol(candidate, mode="confirmed")


def test_every_formal_required_path_is_present_and_enforced(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    schema = json.loads(
        resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text("utf-8")
    )
    assert len(schema["x-formal-required"]) >= 55
    for pointer in schema["x-formal-required"]:
        candidate = deepcopy(frozen_protocol)
        _delete(candidate, pointer)
        with pytest.raises(ValueError, match="schema|formal-required"):
            validate_protocol(
                candidate,
                mode="formal",
                decisions_path=approved_decisions_path,
                human_protocol_path=approved_human_protocol_path,
            )


@pytest.mark.parametrize(
    "block",
    [
        "topic",
        "stance",
        "population",
        "initialization",
        "groups",
        "network",
        "dynamics",
        "memory",
        "exposure",
        "generation",
        "runtime",
        "metrics",
        "sample_size",
        "shapes",
        "gates",
        "quality",
        "stopping",
        "sampling",
        "analysis",
        "robustness",
        "storage",
        "provenance",
    ],
)
def test_every_execution_block_is_required(protocol, block):
    del protocol[block]
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(protocol, mode="draft")


def test_typos_and_unknown_fields_are_rejected_at_root_and_nested(protocol):
    root_typo = deepcopy(protocol)
    root_typo["generaton"] = root_typo.pop("generation")
    nested_typo = deepcopy(protocol)
    nested_typo["network"]["ws"]["probablity"] = nested_typo["network"]["ws"].pop("p")
    for candidate in (root_typo, nested_typo):
        with pytest.raises(ValueError, match="schema"):
            validate_protocol(candidate, mode="draft")


@pytest.mark.parametrize(
    "placeholder",
    [
        "TBD",
        "todo",
        "ＦＩＸＭＥ",
        "un-decided",
        "P E N D I N G",
        "not yet decided",
        "place_holder",
    ],
)
def test_bare_placeholders_are_rejected_recursively(protocol, placeholder):
    candidate = deepcopy(protocol)
    candidate["topic"]["statement"] = placeholder
    with pytest.raises(ValueError, match="placeholder"):
        validate_protocol(candidate, mode="draft")


@pytest.mark.parametrize(
    "placeholder",
    [
        "ＦＩＸＭＥ",
        "not_decided",
        "N/A",
        "???",
        "待定",
        "未决定",
        "待确认",
        "未知",
    ],
)
def test_structural_placeholder_variants_are_rejected(protocol, placeholder):
    candidate = deepcopy(protocol)
    candidate["topic"]["statement"] = placeholder
    with pytest.raises(ValueError, match="placeholder"):
        validate_protocol(candidate, mode="draft")


def test_placeholder_words_inside_a_substantive_value_are_not_rejected(protocol):
    candidate = deepcopy(protocol)
    candidate["topic"]["statement"] = "The city has pending transit projects."
    validate_protocol(candidate, mode="draft")


@pytest.mark.parametrize(
    "placeholder",
    [
        "TODO: choose a topic",
        "TODO, choose a topic",
        "TBD - choose a topic",
        "FIXME=choose a topic",
        "UNDECIDED—choose a topic",
        "PENDING: choose a topic",
        "PENDING, choose a topic",
        "PENDING? choose a topic",
        "PENDING! choose a topic",
        "PENDING\u200b: choose a topic",
        "NOT DECIDED: choose a topic",
        "NOT DECIDED (choose a topic)",
        "NOT\u200c DECIDED (choose a topic)",
        "NOT YET DECIDED, choose a topic",
        "NA: choose a topic",
        "NA | choose a topic",
        "NA\ufe0f: choose a topic",
        "PLACEHOLDER / choose a topic",
        "N/A: choose a topic",
        "N/A, choose a topic",
        "N/A\ufeff| choose a topic",
        "TBD. choose a topic",
        "TBD\u0301: choose a topic",
        "T\u200dBD. choose a topic",
        "TODO\u2060—choose a topic",
        "TO\u034fDO: choose a topic",
        "PEND\u20dding: choose a topic",
        "PEND\u3164ING: choose a topic",
        "待定：选择议题",
        "未决定 - 选择议题",
        "待确认 选择议题",
        "未知=选择议题",
    ],
)
def test_decorated_placeholder_prefixes_are_rejected(protocol, placeholder):
    candidate = deepcopy(protocol)
    candidate["topic"]["statement"] = placeholder
    with pytest.raises(ValueError, match="placeholder"):
        validate_protocol(candidate, mode="draft")


@pytest.mark.parametrize("extra", ["prompt", "system", "instruction"])
def test_topic_rejects_prompt_and_instruction_fields(protocol, extra):
    candidate = deepcopy(protocol)
    candidate["topic"][extra] = "Any free text"
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(candidate, mode="draft")


def test_persona_rejects_free_text(protocol):
    candidate = deepcopy(protocol)
    candidate["persona"]["identity_present_continuity_present"]["text"] = (
        "Keep the initial position."
    )
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(candidate, mode="draft")


def test_topic_statement_hash_must_match(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    frozen_protocol["topic"]["statement_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="statement_sha256"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_qa_paths_and_decision_ids_exactly_match_schema_annotations():
    schema = json.loads(
        resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text("utf-8")
    )
    assert _schema_decision_paths(schema) == _qa_decision_paths()


def test_formal_rejects_missing_decision_log_and_missing_approval(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path, tmp_path
):
    missing = tmp_path / "missing.md"
    with pytest.raises(ValueError, match="decision log"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=missing,
            human_protocol_path=approved_human_protocol_path,
        )

    text = approved_decisions_path.read_text(encoding="utf-8")
    one_id, one_provenance = next(iter(frozen_protocol["decision_provenance"].items()))
    incomplete = tmp_path / "incomplete.md"
    incomplete.write_text(
        text.replace(one_provenance["decision_record_id"], "REMOVED", 1), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="decision record"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=incomplete,
            human_protocol_path=approved_human_protocol_path,
        )

    del frozen_protocol["decision_provenance"][one_id]
    with pytest.raises(ValueError, match="decision provenance"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_formal_rejects_empty_approval_timestamp(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    first = next(iter(frozen_protocol["decision_provenance"].values()))
    first["approved_at"] = ""
    with pytest.raises(ValueError, match="schema|approved_at"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


@pytest.mark.parametrize(
    "approved_at",
    [
        "not-a-date",
        "2026-02-30T04:00:00Z",
        "2026-07-16 04:00:00Z",
        "2026-07-16T04:00:00+08:00",
    ],
)
def test_formal_requires_strict_rfc3339_utc_approval_timestamps(
    frozen_protocol,
    approved_decisions_path,
    approved_human_protocol_path,
    approved_at,
):
    first = next(iter(frozen_protocol["decision_provenance"].values()))
    first["approved_at"] = approved_at
    records = _read_decision_records(approved_decisions_path)
    records["records"][0]["approved_at"] = approved_at
    _write_decision_records(approved_decisions_path, records)
    with pytest.raises(ValueError, match="approved_at|date-time|RFC3339"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_project_format_checker_enforces_strict_rfc3339_utc() -> None:
    validator = jsonschema.Draft202012Validator(
        {"type": "string", "format": "date-time"},
        format_checker=protocol_module.FORMAT_CHECKER,
    )

    assert not list(validator.iter_errors("2026-07-16T04:00:00Z"))
    for invalid in (
        "2026-02-30T04:00:00Z",
        "2026-07-16 04:00:00Z",
        "2026-07-16T04:00:00+08:00",
    ):
        assert list(validator.iter_errors(invalid)), invalid


def test_formal_accepts_explicit_research_qa_path(
    frozen_protocol,
    approved_decisions_path,
    approved_human_protocol_path,
):
    validate_protocol(
        frozen_protocol,
        mode="formal",
        decisions_path=approved_decisions_path,
        human_protocol_path=approved_human_protocol_path,
        qa_path=RESEARCH_QA_PATH,
    )


def test_formal_requires_exact_decision_record_id_binding(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    records = _read_decision_records(approved_decisions_path)
    records["records"][0]["decision_record_id"] += "-EXTRA"
    _write_decision_records(approved_decisions_path, records)
    with pytest.raises(ValueError, match="decision record"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_formal_requires_exact_field_id_membership(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    records = _read_decision_records(approved_decisions_path)
    records["records"][0]["field_ids"][0] += "_EXTRA"
    _write_decision_records(approved_decisions_path, records)
    with pytest.raises(ValueError, match="field|decision ID"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_formal_rejects_fake_approver_even_when_record_matches(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    first = next(iter(frozen_protocol["decision_provenance"].values()))
    first["approvers"] = ["fake approver"]
    records = _read_decision_records(approved_decisions_path)
    records["records"][0]["approvers"] = ["fake approver"]
    _write_decision_records(approved_decisions_path, records)
    with pytest.raises(ValueError, match="approver|owner"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


@pytest.mark.parametrize("artifact", ["topic", "persona"])
def test_formal_rejects_unapproved_artifact_hashes(
    frozen_protocol,
    approved_decisions_path,
    approved_human_protocol_path,
    artifact,
):
    if artifact == "topic":
        statement = "The city should pause its public transit expansion."
        frozen_protocol["topic"]["statement"] = statement
        frozen_protocol["topic"]["statement_sha256"] = hashlib.sha256(
            statement.encode("utf-8")
        ).hexdigest()
    else:
        frozen_protocol["persona"]["identity_absent_continuity_absent"]["template_sha256"] = (
            "a" * 64
        )
    with pytest.raises(ValueError, match="artifact"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_formal_rejects_post_approval_field_mutation_even_after_human_summary_rerender(
    frozen_protocol,
    approved_decisions_path,
    approved_human_protocol_path,
):
    frozen_protocol["generation"]["temperature"] = 0.5
    approved_human_protocol_path.write_text(
        render_human_protocol_summary(frozen_protocol), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="artifact"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_formal_automatically_rejects_human_protocol_drift(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    text = approved_human_protocol_path.read_text(encoding="utf-8")
    approved_human_protocol_path.write_text(
        text.replace("population_size: 1000", "population_size: 999", 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="drift"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_api_robustness_cells_accept_any_nonempty_canonical_unique_subset(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path
):
    frozen_protocol["robustness"]["api"]["cells"] = ["P1-I0-C0-E0"]
    schema = json.loads(
        resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_text("utf-8")
    )
    records = _read_decision_records(approved_decisions_path)
    record = next(
        item for item in records["records"] if "P1_API_ROBUSTNESS_CELLS" in item["field_ids"]
    )
    record["artifact_hashes"] = _artifact_hashes(frozen_protocol, schema, "P1_API_ROBUSTNESS_CELLS")
    _write_decision_records(approved_decisions_path, records)
    approved_human_protocol_path.write_text(
        render_human_protocol_summary(frozen_protocol), encoding="utf-8"
    )
    validate_protocol(
        frozen_protocol,
        mode="formal",
        decisions_path=approved_decisions_path,
        human_protocol_path=approved_human_protocol_path,
    )


@pytest.mark.parametrize(
    "cells",
    [
        [],
        ["P1-I0-C0-E0", "P1-I0-C0-E0"],
        ["P1-NOT-A-CELL"],
    ],
)
def test_api_robustness_cells_reject_empty_duplicate_or_unknown_values(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path, cells
):
    frozen_protocol["robustness"]["api"]["cells"] = cells
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_draft_may_leave_decision_provenance_empty(protocol):
    assert protocol["decision_provenance"] == {}
    validate_protocol(protocol, mode="draft")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected_and_never_hashed(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path, value
):
    frozen_protocol["generation"]["temperature"] = value
    with pytest.raises(ValueError, match="finite"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )
    with pytest.raises(ValueError):
        canonical_protocol_hash(frozen_protocol)


def test_schema_override_cannot_weaken_canonical_validation(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path, tmp_path
):
    del frozen_protocol["generation"]["max_tokens"]
    open_schema = tmp_path / "open.schema.json"
    open_schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            schema_path=open_schema,
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_schema_override_is_additive_and_identity_checked(
    frozen_protocol, approved_decisions_path, approved_human_protocol_path, tmp_path
):
    restrictive = tmp_path / "restrictive.schema.json"
    restrictive.write_text(
        json.dumps(
            {
                "$id": "https://agent-ex.local/schemas/paper1.schema.json",
                "type": "object",
                "properties": {
                    "protocol": {
                        "type": "object",
                        "properties": {"version": {"const": "2.0.0"}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="override schema"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            schema_path=restrictive,
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )

    wrong_identity = tmp_path / "wrong.schema.json"
    wrong_identity.write_text(json.dumps({"$id": "https://elsewhere/schema"}), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        validate_protocol(
            frozen_protocol,
            mode="formal",
            schema_path=wrong_identity,
            decisions_path=approved_decisions_path,
            human_protocol_path=approved_human_protocol_path,
        )


def test_human_generated_summary_matches_machine_projection(protocol):
    validate_human_protocol_sync(protocol, HUMAN_PROTOCOL_PATH)
    text = HUMAN_PROTOCOL_PATH.read_text(encoding="utf-8")
    assert f"execution_hash: {canonical_protocol_hash(protocol)}" in text
    assert "primary_estimand_id: P1_PRIMARY_WS_SHADOW_AVERAGE_EFFECT" in text
    assert "P1_SECONDARY_CONTINUITY_WS_SHADOW_MODERATION" in text
    assert "primary: private_state" in text
    assert "activation_mode: weighted_random_sequential_with_replacement" in text
    assert "feed_message_capacity: UNRESOLVED[P1_MAX_NEIGHBORS]" in text
    assert "event_identity: run_id_plus_event_ordinal" in text
    assert "resume_cursor: next_event_ordinal" in text
    assert "library_version: UNRESOLVED[P1_NETWORK_LIBRARY_VERSION]" in text
    assert "ws_builder_algorithm: UNRESOLVED[P1_WS_BUILDER_ALGORITHM]" in text
    assert "random_null_replicates: UNRESOLVED[P1_RANDOM_GRAPH_NULL_REPLICATES]" in text


def test_human_protocol_does_not_claim_phase4b_machine_migration_is_pending():
    text = HUMAN_PROTOCOL_PATH.read_text(encoding="utf-8")
    assert "generated summary/schema尚未扩展" not in text
    assert "summary仍显示旧continuity DiD和旧outcome" not in text


@pytest.mark.parametrize("layout", ["duplicate", "missing_begin", "missing_end", "reversed"])
def test_human_sync_requires_exactly_one_ordered_generated_summary_block(
    protocol, tmp_path, layout
):
    path = tmp_path / "paper1-protocol.md"
    summary = render_human_protocol_summary(protocol)
    begin = "<!-- BEGIN GENERATED PROTOCOL SUMMARY -->"
    end = "<!-- END GENERATED PROTOCOL SUMMARY -->"
    documents = {
        "duplicate": f"{summary}\n\n{summary}\n",
        "missing_begin": summary.replace(begin, "", 1),
        "missing_end": summary.replace(end, "", 1),
        "reversed": f"{end}\n```yaml\n{{}}\n```\n{begin}",
    }
    path.write_text(documents[layout], encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one|markers"):
        validate_human_protocol_sync(protocol, path)


@pytest.mark.parametrize("layout", ["duplicate", "missing_begin", "missing_end", "reversed"])
def test_human_summary_update_requires_exactly_one_ordered_marker_pair(protocol, layout):
    summary = render_human_protocol_summary(protocol)
    begin = "<!-- BEGIN GENERATED PROTOCOL SUMMARY -->"
    end = "<!-- END GENERATED PROTOCOL SUMMARY -->"
    documents = {
        "duplicate": f"{summary}\n\n{summary}\n",
        "missing_begin": summary.replace(begin, "", 1),
        "missing_end": summary.replace(end, "", 1),
        "reversed": f"{end}\n```yaml\n{{}}\n```\n{begin}",
    }

    with pytest.raises(ValueError, match="exactly one|markers"):
        update_human_protocol_summary(documents[layout], protocol)


@pytest.mark.parametrize(
    ("git_marker", "project_name"),
    [
        (False, "agent-ex"),
        (True, "unrelated-project"),
    ],
)
def test_default_formal_paths_require_verified_source_checkout(
    monkeypatch, tmp_path, git_marker, project_name
):
    fake_root = tmp_path / "fake"
    fake_module = fake_root / "platform" / "src" / "agent_ex" / "protocol.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.touch()
    (fake_root / "platform" / "pyproject.toml").write_text(
        f'[project]\nname = "{project_name}"\n', encoding="utf-8"
    )
    (fake_root / "docs").mkdir()
    (fake_root / "docs" / "decisions.md").write_text("not trusted", encoding="utf-8")
    if git_marker:
        (fake_root / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    monkeypatch.setattr(protocol_module, "__file__", str(fake_module))

    with pytest.raises(ValueError, match="required.*outside a source checkout"):
        protocol_module._resolve_formal_path(
            None,
            default_relative_path="docs/decisions.md",
            argument_name="decision log",
        )


def test_default_formal_paths_resolve_in_verified_source_checkout():
    assert (
        protocol_module._resolve_formal_path(
            None,
            default_relative_path="docs/decisions.md",
            argument_name="decision log",
        )
        == REPOSITORY_ROOT / "docs" / "decisions.md"
    )


def test_human_sync_detects_any_execution_field_drift(protocol, tmp_path):
    for pointer, replacement in (
        ("/generation/temperature", 0.5),
        ("/population/source", "different_source"),
        ("/topic/statement", "A different neutral statement."),
    ):
        changed = deepcopy(protocol)
        _set(changed, pointer, replacement)
        with pytest.raises(ValueError, match="drift"):
            validate_human_protocol_sync(changed, HUMAN_PROTOCOL_PATH)

    original = HUMAN_PROTOCOL_PATH.read_text(encoding="utf-8")
    rendered = render_human_protocol_summary(protocol)
    assert rendered.startswith("<!-- BEGIN GENERATED PROTOCOL SUMMARY -->")
    assert update_human_protocol_summary(original, protocol) == original


def test_hash_tracks_execution_projection_but_ignores_review_metadata(frozen_protocol):
    baseline = canonical_protocol_hash(frozen_protocol)
    changed_status = deepcopy(frozen_protocol)
    changed_status["status"] = "confirmed"
    changed_reference = deepcopy(frozen_protocol)
    changed_reference["human_protocol_reference"] = "docs/other.md"
    changed_metadata = deepcopy(frozen_protocol)
    changed_metadata["metadata"] = {"review_note": "wording only", "reviewer": "A"}
    changed_execution = deepcopy(frozen_protocol)
    changed_execution["generation"]["temperature"] = 0.6

    assert canonical_protocol_hash(changed_status) == baseline
    assert canonical_protocol_hash(changed_reference) == baseline
    assert canonical_protocol_hash(changed_metadata) == baseline
    assert canonical_protocol_hash(changed_execution) != baseline


def test_hash_is_insensitive_to_mapping_order(frozen_protocol):
    reordered = yaml.safe_load(yaml.safe_dump(frozen_protocol, sort_keys=True, allow_unicode=True))
    assert canonical_protocol_hash(reordered) == canonical_protocol_hash(frozen_protocol)


def test_packaged_schema_and_release_mirror_are_identical():
    packaged = resources.files("agent_ex.schemas").joinpath("paper1.schema.json").read_bytes()
    assert packaged == MIRROR_SCHEMA_PATH.read_bytes()
    schema = json.loads(packaged)
    assert schema["x-formal-required"]


def test_public_protocol_api_is_importable():
    from agent_ex import load_protocol as public_load
    from agent_ex import validate_human_protocol_reference as public_reference

    assert callable(public_load)
    assert callable(public_reference)
