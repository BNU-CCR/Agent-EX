"""Strict loading and deterministic expansion of Phase 0A probe specifications."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _require_json_transport, _require_sha256
from .contracts import ProbeCase, ProbeTopicCandidate
from .render import render_probe_persona


EXPECTED_TOPIC_ORDER = ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
ALLOWED_DECISION_IDS = {
    "P1_TOPIC_PRIMARY",
    "P1_STANCE_SCALE",
    "P1_PERSONA_TEMPLATES",
    "P1_CONTINUITY_MC_SCORING",
    "P1_CONTINUITY_LOCK_THRESHOLD",
    "P1_REFUSAL_THRESHOLD",
    "P1_PARSE_FAILURE_THRESHOLD",
    "P1_TEMPERATURE",
    "P1_TOP_P",
    "P1_REQUEST_SEED",
    "P1_TIMEOUT_RETRY",
}

_SPEC_FIELDS = {
    "schema_version",
    "metadata",
    "candidate_order",
    "preselection_priority",
    "topic_candidates",
    "scales",
    "field_orders",
    "persona",
    "persona_conditions",
    "factor_orders",
    "continuity_scenarios",
    "replicates",
    "generation_settings",
    "policy_hashes",
    "decision_ids",
}
_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_FORBIDDEN_IDENTITY_FIELDS = {
    "event_id",
    "event_identity",
    "run_id",
    "run_identity",
    "cell_id",
    "feed_id",
    "feed_cursor",
    "state_id",
    "state_identity",
    "private_state",
    "public_state",
    "public_stock",
    "public_flow",
}
_PLACEHOLDER = re.compile(r"UNRESOLVED\[([^\]]+)\]")


def _exact_dict(value: object, fields: set[str], name: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"{name} fields do not match the calibration specification contract")
    return value


def _exact_list(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"{name} must be an explicit JSON array")
    return value


def _nonempty_string(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _reject_forbidden_identity_fields(value: object) -> None:
    if type(value) is dict:
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in _FORBIDDEN_IDENTITY_FIELDS:
                raise ValueError(f"forbidden event/run/feed/state identity field: {key}")
            _reject_forbidden_identity_fields(child)
    elif type(value) is list:
        for child in value:
            _reject_forbidden_identity_fields(child)


def _reject_unknown_placeholders(value: object) -> None:
    if type(value) is str:
        for decision_id in _PLACEHOLDER.findall(value):
            if decision_id not in ALLOWED_DECISION_IDS:
                raise ValueError(f"unknown calibration decision ID: {decision_id}")
    elif type(value) is dict:
        for child in value.values():
            _reject_unknown_placeholders(child)
    elif type(value) is list:
        for child in value:
            _reject_unknown_placeholders(child)


def _validate_topic_candidates(payload: dict[str, object]) -> None:
    candidates = _exact_list(payload["topic_candidates"], "topic_candidates")
    if len(candidates) != 3:
        raise ValueError("topic_candidates must contain exactly three candidates")
    keys: list[str] = []
    records: list[ProbeTopicCandidate] = []
    for index, raw in enumerate(candidates):
        candidate = _exact_dict(
            raw,
            {"candidate_key", "construct", "fact_card", "statements", "stance_labels_1_7"},
            f"topic_candidates[{index}]",
        )
        key = _nonempty_string(candidate["candidate_key"], "candidate_key")
        keys.append(key)
        statements = _exact_list(candidate["statements"], "statements")
        labels = _exact_list(candidate["stance_labels_1_7"], "stance_labels_1_7")
        if len(statements) != 3:
            raise ValueError("every topic candidate must have exactly three statement variants")
        if len(labels) != 7:
            raise ValueError("stance_labels_1_7 must have exactly seven labels")
        statement_texts = tuple(_nonempty_string(item, "statement") for item in statements)
        label_texts = tuple(_nonempty_string(item, "stance label") for item in labels)
        if len(set(statement_texts)) != 3:
            raise ValueError("topic statement variants must be pairwise distinct")
        if len(set(label_texts)) != 7:
            raise ValueError("stance_labels_1_7 must be pairwise distinct")
        records.append(
            ProbeTopicCandidate.create(
                construct=_nonempty_string(candidate["construct"], "construct"),
                fact_card=_nonempty_string(candidate["fact_card"], "fact_card"),
                statements=statement_texts,  # type: ignore[arg-type]
                stance_labels_1_7=label_texts,
            )
        )
    if len(keys) != len(set(keys)) or len({item.candidate_id for item in records}) != 3:
        raise ValueError("duplicate topic candidates are forbidden")
    if tuple(keys) != EXPECTED_TOPIC_ORDER:
        raise ValueError("topic candidate order must match the fixed candidate order")


def _validate_scales(payload: dict[str, object]) -> None:
    scales = _exact_list(payload["scales"], "scales")
    expected = {
        ("stance-1-7", 1, 7, "main"),
        ("stance-0-10", 0, 10, "challenger"),
    }
    observed = set()
    for raw in scales:
        scale = _exact_dict(raw, {"scale_id", "minimum", "maximum", "role"}, "scale")
        if type(scale["minimum"]) is not int or type(scale["maximum"]) is not int:
            raise TypeError("scale bounds must be integers")
        observed.add((scale["scale_id"], scale["minimum"], scale["maximum"], scale["role"]))
    if observed != expected or len(scales) != 2:
        raise ValueError("scales must contain the exact 1-7 main and 0-10 challenger")


def _validate_field_orders(payload: dict[str, object]) -> None:
    orders = _exact_list(payload["field_orders"], "field_orders")
    expected = {
        ("stance-confidence-reason", ("stance", "confidence", "public_reason")),
        ("reason-confidence-stance", ("public_reason", "confidence", "stance")),
    }
    observed = set()
    for raw in orders:
        order = _exact_dict(raw, {"field_order_id", "fields"}, "field order")
        fields = _exact_list(order["fields"], "field order fields")
        observed.add((order["field_order_id"], tuple(fields)))
    if observed != expected or len(orders) != 2:
        raise ValueError("field_orders must contain both exact output order challenges")


def _validate_persona(payload: dict[str, object]) -> None:
    persona = _exact_dict(
        payload["persona"],
        {"common_skeleton", "identity_block", "continuity_blocks"},
        "persona",
    )
    _nonempty_string(persona["common_skeleton"], "common_skeleton")
    _nonempty_string(persona["identity_block"], "identity_block")
    blocks = _exact_list(persona["continuity_blocks"], "continuity_blocks")
    block_ids = []
    block_texts = []
    for raw in blocks:
        block = _exact_dict(raw, {"wording_id", "text"}, "continuity wording")
        block_ids.append(_nonempty_string(block["wording_id"], "wording_id"))
        block_texts.append(_nonempty_string(block["text"], "continuity wording text"))
    if len(blocks) != 2 or len(set(block_ids)) != 2 or len(set(block_texts)) != 2:
        raise ValueError("persona must contain exactly two distinct continuity wording contents")

    conditions = _exact_list(payload["persona_conditions"], "persona_conditions")
    observed_conditions = set()
    for raw in conditions:
        condition = _exact_dict(
            raw,
            {"condition_id", "identity_present", "continuity_present"},
            "persona condition",
        )
        if (
            type(condition["identity_present"]) is not bool
            or type(condition["continuity_present"]) is not bool
        ):
            raise TypeError("persona condition factors must be booleans")
        observed_conditions.add(
            (
                _nonempty_string(condition["condition_id"], "condition_id"),
                condition["identity_present"],
                condition["continuity_present"],
            )
        )
    if len(conditions) != 4 or observed_conditions != {
        ("i0-c0", False, False),
        ("i0-c1", False, True),
        ("i1-c0", True, False),
        ("i1-c1", True, True),
    }:
        raise ValueError("persona condition IDs must map to their exact factor combinations")

    factor_orders = _exact_list(payload["factor_orders"], "factor_orders")
    observed_orders = set()
    for raw in factor_orders:
        order = _exact_dict(raw, {"factor_order_id", "factors"}, "factor order")
        factors = _exact_list(order["factors"], "factor order factors")
        observed_orders.add(
            (
                _nonempty_string(order["factor_order_id"], "factor_order_id"),
                tuple(factors),
            )
        )
    if len(factor_orders) != 2 or observed_orders != {
        ("identity-continuity", ("identity", "continuity")),
        ("continuity-identity", ("continuity", "identity")),
    }:
        raise ValueError("factor order IDs must map to their exact factor sequences")


def _validate_scenarios_and_replicates(payload: dict[str, object]) -> None:
    scenarios = _exact_list(payload["continuity_scenarios"], "continuity_scenarios")
    scenario_ids = set()
    scenario_histories = set()
    for raw in scenarios:
        scenario = _exact_dict(raw, {"scenario_id", "history"}, "continuity scenario")
        scenario_ids.add(_nonempty_string(scenario["scenario_id"], "scenario_id"))
        scenario_histories.add(_nonempty_string(scenario["history"], "scenario history"))
    if len(scenarios) != 3 or len(scenario_histories) != 3:
        raise ValueError("continuity scenario contents must be pairwise distinct")
    if scenario_ids != {"reasonable-hold", "warranted-update", "insufficient-information"}:
        raise ValueError("continuity_scenarios must contain the exact three scenario families")
    replicates = _exact_list(payload["replicates"], "replicates")
    ids = set()
    pairs = set()
    for raw in replicates:
        replicate = _exact_dict(raw, {"replicate_id", "requested_seed"}, "replicate")
        replicate_id = replicate["replicate_id"]
        seed = replicate["requested_seed"]
        if type(replicate_id) is not int or replicate_id < 0:
            raise ValueError("replicate_id must be an explicit nonnegative integer")
        if seed is not None and type(seed) is not int:
            raise TypeError("requested_seed must be an explicit integer or null")
        ids.add(replicate_id)
        pairs.add((replicate_id, seed))
    if not replicates or len(ids) != len(replicates) or len(pairs) != len(replicates):
        raise ValueError("replicates and requested seeds must be explicit and unique")


def _validate_policies_and_decisions(payload: dict[str, object]) -> None:
    policies = _exact_dict(
        payload["policy_hashes"],
        {"gate_algorithm", "semantic_review_policy", "runtime_policy"},
        "policy_hashes",
    )
    for name, digest in policies.items():
        _require_sha256(f"policy_hashes[{name}]", digest)
    decisions = _exact_list(payload["decision_ids"], "decision_ids")
    if any(type(item) is not str for item in decisions):
        raise TypeError("decision_ids must contain strings")
    if len(decisions) != len(set(decisions)) or set(decisions) != ALLOWED_DECISION_IDS:
        raise ValueError("decision_ids must equal the registered P1 calibration decision IDs")
    settings = _exact_dict(
        payload["generation_settings"],
        {"temperature", "top_p", "request_seed"},
        "generation_settings",
    )
    expected = {
        "temperature": "UNRESOLVED[P1_TEMPERATURE]",
        "top_p": "UNRESOLVED[P1_TOP_P]",
        "request_seed": "UNRESOLVED[P1_REQUEST_SEED]",
    }
    if settings != expected:
        raise ValueError("generation_settings must remain bound to registered unresolved IDs")


def _canonicalize_nonsemantic_arrays(payload: dict[str, object]) -> None:
    for field, key in (
        ("scales", "scale_id"),
        ("field_orders", "field_order_id"),
        ("persona_conditions", "condition_id"),
        ("factor_orders", "factor_order_id"),
        ("continuity_scenarios", "scenario_id"),
        ("replicates", "replicate_id"),
    ):
        payload[field].sort(key=lambda item: item[key])  # type: ignore[union-attr,index]
    payload["persona"]["continuity_blocks"].sort(key=lambda item: item["wording_id"])  # type: ignore[index,union-attr]
    payload["decision_ids"].sort()  # type: ignore[union-attr]


def load_probe_specification(payload: Mapping[str, object]) -> ArtifactEnvelope:
    """Validate an exact calibration-only v1 payload and bind its canonical form."""

    if type(payload) is not dict or set(payload) != _SPEC_FIELDS:
        raise ValueError("probe specification fields do not match the calibration contract")
    _require_json_transport(payload, "probe specification")
    working = deepcopy(payload)
    _reject_forbidden_identity_fields(working)
    _reject_unknown_placeholders(working)
    if working["schema_version"] != "paper1.calibration.probe-specification.v1":
        raise ValueError("probe specification schema_version is not supported")
    metadata = working["metadata"]
    if (
        type(metadata) is not dict
        or set(metadata) != set(_METADATA)
        or type(metadata["calibration_only"]) is not bool
        or metadata["calibration_only"] is not True
        or type(metadata["formal_parameter_authority"]) is not bool
        or metadata["formal_parameter_authority"] is not False
        or type(metadata["research_parameter_status"]) is not str
        or metadata["research_parameter_status"] != "not_frozen"
    ):
        raise ValueError("probe specification metadata must be strictly calibration-only")
    if tuple(_exact_list(working["candidate_order"], "candidate_order")) != EXPECTED_TOPIC_ORDER:
        raise ValueError("candidate_order must match the fixed topic order")
    if (
        tuple(_exact_list(working["preselection_priority"], "preselection_priority"))
        != EXPECTED_TOPIC_ORDER
    ):
        raise ValueError("preselection_priority must match the fixed topic priority")
    _validate_topic_candidates(working)
    _validate_scales(working)
    _validate_field_orders(working)
    _validate_persona(working)
    _validate_scenarios_and_replicates(working)
    _validate_policies_and_decisions(working)
    _canonicalize_nonsemantic_arrays(working)
    return ArtifactEnvelope.create(
        artifact_type="paper1.calibration_probe_specification",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.calibration_probe_specification_loader",
        algorithm_version="1.0.0",
        input_hashes={},
        payload=working,
        rng_provenance=(),
    )


def _topic_records(spec: Mapping[str, object]) -> dict[str, ProbeTopicCandidate]:
    records = {}
    for raw in spec["topic_candidates"]:  # type: ignore[union-attr]
        records[raw["candidate_key"]] = ProbeTopicCandidate.create(
            construct=raw["construct"],
            fact_card=raw["fact_card"],
            statements=tuple(raw["statements"]),
            stance_labels_1_7=tuple(raw["stance_labels_1_7"]),
        )
    return records


def _messages(
    *,
    persona_text: str,
    fact_card: str,
    statement: str,
    scale: Mapping[str, object],
    field_order: Mapping[str, object],
    history: str | None,
) -> tuple[Mapping[str, str], ...]:
    user_parts = [fact_card, statement]
    if history is not None:
        user_parts.append(history)
    user_parts.append(
        f"Scale {scale['minimum']}..{scale['maximum']}; JSON field order: "
        + ",".join(field_order["fields"])  # type: ignore[arg-type]
    )
    return (
        {"role": "system", "content": persona_text},
        {"role": "user", "content": "\n".join(user_parts)},
    )


def expand_probe_cases(specification: ArtifactEnvelope) -> tuple[ProbeCase, ...]:
    """Expand all semantic dimensions and return cases in canonical ID order."""

    if not isinstance(specification, ArtifactEnvelope) or (
        specification.artifact_type != "paper1.calibration_probe_specification"
    ):
        raise TypeError("specification must be a calibration probe specification envelope")
    spec = specification.payload
    if not isinstance(spec, Mapping):
        raise TypeError("specification payload must be a mapping")
    # Revalidate the thawed transport so forged envelopes cannot bypass strict loading.
    validated = load_probe_specification(specification.to_payload()["payload"])
    if validated.output_hash != specification.output_hash:
        raise ValueError("specification hash does not match strict canonical validation")
    spec = validated.payload
    topics = _topic_records(spec)
    conditions = spec["persona_conditions"]
    orders = spec["factor_orders"]
    persona = spec["persona"]
    continuity_blocks = persona["continuity_blocks"]
    default_continuity = continuity_blocks[0]
    default_order = orders[0]
    absent_view = render_probe_persona(
        common_skeleton=persona["common_skeleton"],
        identity_present=False,
        continuity_present=False,
        identity_block=persona["identity_block"],
        continuity_block=default_continuity["text"],
        factor_order=tuple(default_order["factors"]),
    )
    cases: list[ProbeCase] = []

    for candidate_key in EXPECTED_TOPIC_ORDER:
        topic = topics[candidate_key]
        raw_topic = next(
            raw for raw in spec["topic_candidates"] if raw["candidate_key"] == candidate_key
        )
        for variant_index, statement in enumerate(raw_topic["statements"]):
            for scale in spec["scales"]:
                for field_order in spec["field_orders"]:
                    for replicate in spec["replicates"]:
                        cases.append(
                            ProbeCase.create(
                                specification_hash=specification.output_hash,
                                candidate_id=topic.candidate_id,
                                case_family="topic_quality",
                                scenario_id=f"topic-{candidate_key}",
                                variant_index=variant_index,
                                scale_id=scale["scale_id"],
                                field_order_id=field_order["field_order_id"],
                                replicate_id=replicate["replicate_id"],
                                requested_seed=replicate["requested_seed"],
                                persona_view_id=absent_view.persona_view_id,
                                rendered_messages=_messages(
                                    persona_text=absent_view.rendered_text,
                                    fact_card=raw_topic["fact_card"],
                                    statement=statement,
                                    scale=scale,
                                    field_order=field_order,
                                    history=None,
                                ),
                            )
                        )

        main_scale = next(scale for scale in spec["scales"] if scale["role"] == "main")
        first_order = next(
            item
            for item in spec["field_orders"]
            if item["field_order_id"] == "stance-confidence-reason"
        )
        for condition in conditions:
            for factor_order in orders:
                view = render_probe_persona(
                    common_skeleton=persona["common_skeleton"],
                    identity_present=condition["identity_present"],
                    continuity_present=condition["continuity_present"],
                    identity_block=persona["identity_block"],
                    continuity_block=default_continuity["text"],
                    factor_order=tuple(factor_order["factors"]),
                )
                for replicate in spec["replicates"]:
                    cases.append(
                        ProbeCase.create(
                            specification_hash=specification.output_hash,
                            candidate_id=topic.candidate_id,
                            case_family="identity",
                            scenario_id=(
                                f"identity-{condition['condition_id']}-"
                                f"{factor_order['factor_order_id']}"
                            ),
                            variant_index=0,
                            scale_id=main_scale["scale_id"],
                            field_order_id=first_order["field_order_id"],
                            replicate_id=replicate["replicate_id"],
                            requested_seed=replicate["requested_seed"],
                            persona_view_id=view.persona_view_id,
                            rendered_messages=_messages(
                                persona_text=view.rendered_text,
                                fact_card=raw_topic["fact_card"],
                                statement=raw_topic["statements"][0],
                                scale=main_scale,
                                field_order=first_order,
                                history=None,
                            ),
                        )
                    )

        for condition in conditions:
            for wording in continuity_blocks:
                for factor_order in orders:
                    view = render_probe_persona(
                        common_skeleton=persona["common_skeleton"],
                        identity_present=condition["identity_present"],
                        continuity_present=condition["continuity_present"],
                        identity_block=persona["identity_block"],
                        continuity_block=wording["text"],
                        factor_order=tuple(factor_order["factors"]),
                    )
                    for scenario in spec["continuity_scenarios"]:
                        for replicate in spec["replicates"]:
                            cases.append(
                                ProbeCase.create(
                                    specification_hash=specification.output_hash,
                                    candidate_id=topic.candidate_id,
                                    case_family="continuity",
                                    scenario_id=(
                                        f"continuity-{condition['condition_id']}-"
                                        f"{wording['wording_id']}-{factor_order['factor_order_id']}-"
                                        f"{scenario['scenario_id']}"
                                    ),
                                    variant_index=0,
                                    scale_id=main_scale["scale_id"],
                                    field_order_id=first_order["field_order_id"],
                                    replicate_id=replicate["replicate_id"],
                                    requested_seed=replicate["requested_seed"],
                                    persona_view_id=view.persona_view_id,
                                    rendered_messages=_messages(
                                        persona_text=view.rendered_text,
                                        fact_card=raw_topic["fact_card"],
                                        statement=raw_topic["statements"][0],
                                        scale=main_scale,
                                        field_order=first_order,
                                        history=scenario["history"],
                                    ),
                                )
                            )

    ids = [case.probe_case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate probe cases produced by semantic expansion")
    return tuple(sorted(cases, key=lambda case: case.probe_case_id))
