from copy import deepcopy

import pytest

from agent_ex.calibration.render import (
    render_probe_persona,
    validate_probe_persona_factor_diff,
)
from agent_ex.calibration.specification import (
    ALLOWED_DECISION_IDS,
    EXPECTED_TOPIC_ORDER,
    expand_probe_cases,
    load_probe_specification,
)
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload, reversed_nonsemantic_arrays


def test_loads_hash_bound_calibration_only_specification() -> None:
    payload = probe_spec_payload()
    artifact = load_probe_specification(payload)
    assert artifact.artifact_type == "paper1.calibration_probe_specification"
    assert artifact.output_hash == canonical_payload_hash(artifact.payload)
    assert artifact.payload["metadata"] == {
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
    }
    assert tuple(artifact.payload["candidate_order"]) == EXPECTED_TOPIC_ORDER
    assert set(artifact.payload["decision_ids"]) == ALLOWED_DECISION_IDS


def test_expansion_is_complete_unique_and_iteration_order_independent() -> None:
    first = expand_probe_cases(load_probe_specification(probe_spec_payload()))
    second = expand_probe_cases(
        load_probe_specification(reversed_nonsemantic_arrays(probe_spec_payload()))
    )
    assert {case.case_family for case in first} == {"topic_quality", "identity", "continuity"}
    assert len(first) == 408
    assert len({case.probe_case_id for case in first}) == len(first)
    assert tuple(case.probe_case_id for case in first) == tuple(
        sorted(case.probe_case_id for case in first)
    )
    assert {case.probe_case_id for case in first} == {case.probe_case_id for case in second}


@pytest.mark.parametrize("field", ["schema_version", "metadata", "topic_candidates"])
def test_specification_requires_exact_fields(field: str) -> None:
    payload = probe_spec_payload()
    payload.pop(field)
    with pytest.raises(ValueError, match="fields|contract"):
        load_probe_specification(payload)
    payload = probe_spec_payload()
    payload["event_id"] = "forbidden-event"
    with pytest.raises(ValueError, match="fields|identity|forbidden"):
        load_probe_specification(payload)


@pytest.mark.parametrize(
    "field",
    ["event_id", "run_id", "cell_id", "feed_cursor", "private_state", "public_state"],
)
def test_specification_rejects_nested_event_run_feed_or_state_identity(field: str) -> None:
    payload = probe_spec_payload()
    payload["continuity_scenarios"][0][field] = "forbidden"
    with pytest.raises(ValueError, match="identity|forbidden"):
        load_probe_specification(payload)


def test_specification_rejects_duplicate_or_reordered_candidates() -> None:
    payload = probe_spec_payload()
    payload["topic_candidates"][1] = deepcopy(payload["topic_candidates"][0])
    with pytest.raises(ValueError, match="duplicate|candidate"):
        load_probe_specification(payload)
    for order_field in ("candidate_order", "preselection_priority"):
        payload = probe_spec_payload()
        payload[order_field].reverse()
        with pytest.raises(ValueError, match="order|priority"):
            load_probe_specification(payload)


def test_specification_binds_persona_condition_ids_to_exact_factor_values() -> None:
    payload = probe_spec_payload()
    first = payload["persona_conditions"][0]
    last = payload["persona_conditions"][-1]
    first["condition_id"], last["condition_id"] = last["condition_id"], first["condition_id"]
    with pytest.raises(ValueError, match="condition|mapping|combination"):
        load_probe_specification(payload)


def test_specification_binds_factor_order_ids_to_exact_sequences() -> None:
    payload = probe_spec_payload()
    first = payload["factor_orders"][0]
    second = payload["factor_orders"][1]
    first["factor_order_id"], second["factor_order_id"] = (
        second["factor_order_id"],
        first["factor_order_id"],
    )
    with pytest.raises(ValueError, match="factor|order|mapping"):
        load_probe_specification(payload)


@pytest.mark.parametrize("field", ["statements", "stance_labels_1_7"])
def test_topic_candidate_text_inventory_must_be_pairwise_distinct(field: str) -> None:
    payload = probe_spec_payload()
    payload["topic_candidates"][0][field][1] = payload["topic_candidates"][0][field][0]
    with pytest.raises(ValueError, match="distinct|duplicate"):
        load_probe_specification(payload)


def test_specification_rejects_incomplete_variants_decisions_policies_and_seeds() -> None:
    mutations = []
    payload = probe_spec_payload()
    payload["topic_candidates"][0]["statements"].pop()
    mutations.append(payload)
    payload = probe_spec_payload()
    payload["decision_ids"].append("P1_NOT_REGISTERED")
    mutations.append(payload)
    for policy in ("gate_algorithm", "semantic_review_policy", "runtime_policy"):
        payload = probe_spec_payload()
        payload["policy_hashes"].pop(policy)
        mutations.append(payload)
    payload = probe_spec_payload()
    payload["replicates"][0].pop("requested_seed")
    mutations.append(payload)
    for payload in mutations:
        with pytest.raises(ValueError):
            load_probe_specification(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("calibration_only", 1),
        ("formal_parameter_authority", 0),
        ("research_parameter_status", 7),
    ],
)
def test_specification_metadata_requires_exact_json_types(field: str, value: object) -> None:
    payload = probe_spec_payload()
    payload["metadata"][field] = value
    with pytest.raises(ValueError, match="metadata|calibration-only"):
        load_probe_specification(payload)


def test_probe_persona_rendering_uses_true_omission_and_mechanical_blocks() -> None:
    spec = load_probe_specification(probe_spec_payload())
    views = tuple(
        render_probe_persona(
            common_skeleton=spec.payload["persona"]["common_skeleton"],
            identity_present=condition["identity_present"],
            continuity_present=condition["continuity_present"],
            identity_block=spec.payload["persona"]["identity_block"],
            continuity_block=spec.payload["persona"]["continuity_blocks"][0]["text"],
            factor_order=("identity", "continuity"),
        )
        for condition in spec.payload["persona_conditions"]
    )
    assert views[0].identity_block is None
    assert views[0].continuity_block is None
    assert views[3].identity_block in views[3].rendered_text
    assert views[3].continuity_block in views[3].rendered_text
    report = validate_probe_persona_factor_diff(views)
    assert report["valid"] is True
    assert report["condition_count"] == 4


def test_probe_persona_diff_rejects_nonfactor_drift() -> None:
    views = tuple(
        render_probe_persona(
            common_skeleton="MOCK {factor_blocks} common",
            identity_present=identity,
            continuity_present=continuity,
            identity_block="identity",
            continuity_block="continuity",
            factor_order=("identity", "continuity"),
        )
        for identity, continuity in ((False, False), (False, True), (True, False), (True, True))
    )
    drifted = list(views)
    drifted[3] = render_probe_persona(
        common_skeleton="DRIFT {factor_blocks} common",
        identity_present=True,
        continuity_present=True,
        identity_block="identity",
        continuity_block="continuity",
        factor_order=("identity", "continuity"),
    )
    with pytest.raises(ValueError, match="invariant|allowed"):
        validate_probe_persona_factor_diff(tuple(drifted))


@pytest.mark.parametrize(
    "phrase",
    [
        "坚持",
        "捍卫",
        "忠于",
        "抗从众",
        "不要被影响",
        "除非证据确凿",
        "最大变化一步",
        "保持原有价值观",
        "永不改变",
    ],
)
def test_probe_persona_rejects_approved_chinese_locking_phrases(phrase: str) -> None:
    with pytest.raises(ValueError, match="forbidden|locking"):
        render_probe_persona(
            common_skeleton="MOCK {factor_blocks}",
            identity_present=False,
            continuity_present=True,
            identity_block="identity",
            continuity_block=f"请{phrase}",
            factor_order=("identity", "continuity"),
        )
