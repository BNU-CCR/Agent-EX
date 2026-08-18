"""Deterministic mock attention, expression, and schedule artifacts for Phase 4B-5."""

from __future__ import annotations

import math
import platform
import random
import hashlib
from bisect import bisect_left
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import accumulate

from .artifacts import ArtifactEnvelope
from .domain import (
    FrozenSchedule,
    ScheduleSlot,
    _freeze,
    _require_id,
    _require_int,
    canonical_payload_hash,
)
from .rng import RNG_DERIVATION_VERSION, RNGProvenance


_ENVELOPE_VERSION = "paper1.artifact-envelope.v1"
_ATTENTION_ALGORITHM_ID = "paper1.mock_attention_weights"
_ATTENTION_ALGORITHM_VERSION = "3.0.0"
_EXPRESSION_ALGORITHM_ID = "paper1.mock_hurdle_beta_expression"
_EXPRESSION_ALGORITHM_VERSION = "3.0.0"
_ACTIVATION_ALGORITHM_ID = "paper1.mock_weighted_with_replacement_schedule"
_ACTIVATION_ALGORITHM_VERSION = "3.0.0"
_PUBLISH_ALGORITHM_ID = "paper1.mock_pregenerated_publish_schedule"
_PUBLISH_ALGORITHM_VERSION = "3.0.0"
_FROZEN_SCHEDULE_ALGORITHM_ID = "paper1.mock_weighted_activation_with_publish"
_FROZEN_SCHEDULE_ALGORITHM_VERSION = "3.0.0"
_TRUNCATED_SAMPLING_VERSION = "2.0.0"
_BETA_SAMPLING_VERSION = "2.0.0"
_EVENT_RNG_LEDGER_VERSION = "paper1.event-rng-ledger.v1"
_MAX_DRAWS_PER_AGENT = 10_000
_MAX_BETA_ATTEMPT_BUDGET = 10_000
_PHASE4B_MAX_POPULATION_SIZE = 1_000
_PHASE4B_MAX_SWEEP_COUNT = 50
_PHASE4B_MAX_EVENT_COUNT = 50_000
_PHASE4B_BENCHMARK_ACTIVATION_JSON_BYTES = 5 * 1024 * 1024
_PHASE4B_BENCHMARK_PUBLISH_JSON_BYTES = 6 * 1024 * 1024
_MIN_POSITIVE_FLOAT = math.nextafter(0.0, 1.0)
_VALIDATED_EVENT_RNG_LEDGER_SEAL = object()
_PAPER1_CELL_IDS = tuple(
    f"P1-I{identity}-C{continuity}-E{exposure}"
    for identity in range(2)
    for continuity in range(2)
    for exposure in range(3)
)


def _require_mock_only(mock_only: bool) -> None:
    if mock_only is not True:
        raise ValueError("Phase 4B-5 artifacts must be explicitly mock_only")


def _agent_ids(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("agent_ids must be a sequence")
    population_size = len(values)
    if population_size == 0:
        raise ValueError("agent_ids cannot be empty")
    _require_population_capacity(population_size)
    result = tuple(values[index] for index in range(population_size))
    _require_population_capacity(len(result))
    for value in result:
        _require_id("agent_id", value)
    if len(set(result)) != len(result):
        raise ValueError("agent_ids must be unique")
    return result


def _require_population_capacity(population_size: int) -> None:
    _require_int("population_size", population_size, minimum=1)
    if population_size > _PHASE4B_MAX_POPULATION_SIZE:
        raise ValueError("population_size exceeds the approved Phase 4B platform capacity")


def _preflight_record_population_capacity(artifact: object, record_field: str) -> None:
    if not isinstance(artifact, ArtifactEnvelope) or not isinstance(artifact.payload, Mapping):
        raise ValueError(f"{record_field} capacity payload is required")
    if record_field not in artifact.payload:
        raise ValueError(f"{record_field} is required for capacity preflight")
    records = artifact.payload[record_field]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError(f"{record_field} must be a sequence for capacity preflight")
    _require_population_capacity(len(records))


def _preflight_declared_schedule_capacity(payload: Mapping[str, object], label: str) -> int:
    required_fields = {"population_size", "sweep_count", "slots"}
    missing = required_fields - set(payload)
    if missing:
        raise ValueError(f"{label} required capacity fields are missing: {sorted(missing)}")
    population_size = payload["population_size"]
    _require_int(f"{label} population_size", population_size, minimum=1)  # type: ignore[arg-type]
    _require_population_capacity(population_size)  # type: ignore[arg-type]
    sweep_count = payload["sweep_count"]
    _require_int(f"{label} sweep_count", sweep_count, minimum=1)  # type: ignore[arg-type]
    if sweep_count > _PHASE4B_MAX_SWEEP_COUNT:  # type: ignore[operator]
        raise ValueError("sweep_count exceeds the approved Phase 4B platform capacity")
    event_count = population_size * sweep_count  # type: ignore[operator]
    if event_count > _PHASE4B_MAX_EVENT_COUNT:
        raise ValueError("event count exceeds the approved Phase 4B platform capacity")
    slots = payload["slots"]
    if not isinstance(slots, Sequence) or isinstance(slots, (str, bytes)):
        raise ValueError(f"{label} slots must be a sequence for capacity preflight")
    if len(slots) != event_count:
        raise ValueError(f"{label} slots must equal the required population-by-sweep capacity")
    return event_count


def _preflight_event_ledger_capacity(payload: Mapping[str, object], label: str) -> int:
    if "rng_ledger" not in payload or not isinstance(payload["rng_ledger"], Mapping):
        raise ValueError(f"{label} rng_ledger is required for capacity preflight")
    ledger = payload["rng_ledger"]
    if "event_count" not in ledger:
        raise ValueError(f"{label} event_count is required for capacity preflight")
    event_count = ledger["event_count"]
    _require_int(f"{label} event_count", event_count, minimum=1)  # type: ignore[arg-type]
    if event_count > _PHASE4B_MAX_EVENT_COUNT:  # type: ignore[operator]
        raise ValueError("event_count exceeds the approved Phase 4B platform capacity")
    return event_count  # type: ignore[return-value]


def _preflight_activation_capacity(artifact: object) -> None:
    if not isinstance(artifact, ArtifactEnvelope) or not isinstance(artifact.payload, Mapping):
        raise ValueError("activation capacity payload is required")
    event_count = _preflight_declared_schedule_capacity(artifact.payload, "activation")
    ledger_count = _preflight_event_ledger_capacity(artifact.payload, "activation ledger")
    if ledger_count != event_count:
        raise ValueError("activation ledger event_count must equal population-by-sweep capacity")


def _preflight_publish_capacity(artifact: object) -> None:
    if not isinstance(artifact, ArtifactEnvelope) or not isinstance(artifact.payload, Mapping):
        raise ValueError("publish capacity payload is required")
    if "frozen_schedule" not in artifact.payload or not isinstance(
        artifact.payload["frozen_schedule"], Mapping
    ):
        raise ValueError("publish frozen_schedule is required for capacity preflight")
    event_count = _preflight_declared_schedule_capacity(
        artifact.payload["frozen_schedule"], "publish frozen schedule"
    )
    ledger_count = _preflight_event_ledger_capacity(artifact.payload, "publish ledger")
    if ledger_count != event_count:
        raise ValueError("publish ledger event_count must equal population-by-sweep capacity")


def _finite_number(name: str, value: object, *, strictly_positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    if strictly_positive and numeric <= 0:
        raise ValueError(f"{name} must be strictly positive")
    return numeric


def _strict_json_canonical_hash(name: str, value: object) -> str:
    def require_json(item: object, path: str) -> None:
        if item is None or type(item) in {str, bool, int}:
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError(f"{path} must contain only finite JSON numbers")
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                if type(key) is not str:
                    raise TypeError(f"{path} JSON object keys must be strings")
                require_json(child, f"{path}.{key}")
            return
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            for index in range(len(item)):
                require_json(item[index], f"{path}[{index}]")
            return
        raise TypeError(f"{path} must contain only strict JSON values")

    require_json(value, name)
    return canonical_payload_hash(value)


def _gini(values: Sequence[float]) -> float:
    ordered = sorted(values)
    total = math.fsum(ordered)
    if not ordered or total <= 0:
        return 0.0
    weighted = math.fsum((index + 1) * value for index, value in enumerate(ordered))
    return 2.0 * weighted / (len(ordered) * total) - (len(ordered) + 1) / len(ordered)


def _runtime_provenance() -> dict[str, str]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "random_implementation": "python.random.Random(MT19937)",
    }


def _sample_true_truncated(
    *,
    family: str,
    location: float | None,
    shape: float,
    minimum: float,
    maximum: float,
    count: int,
    rng: random.Random,
) -> tuple[tuple[float, ...], int]:
    values: list[float] = []
    rejected = 0
    for _ in range(count):
        for _attempt in range(_MAX_DRAWS_PER_AGENT):
            if family == "positive_truncated_lognormal":
                if location is None:
                    raise ValueError("lognormal location must be explicit")
                first_uniform = rng.random()
                second_uniform = rng.random()
                candidate = math.inf
                if (
                    not isinstance(first_uniform, bool)
                    and not isinstance(second_uniform, bool)
                    and math.isfinite(first_uniform)
                    and math.isfinite(second_uniform)
                    and 0.0 < first_uniform < 1.0
                    and 0.0 <= second_uniform < 1.0
                ):
                    try:
                        standard_normal = math.sqrt(-2.0 * math.log(first_uniform)) * math.cos(
                            math.tau * second_uniform
                        )
                        exponent = location + shape * standard_normal
                        candidate = math.exp(exponent)
                    except (OverflowError, ValueError):
                        candidate = math.inf
            else:
                uniform = rng.random()
                candidate = math.inf
                if (
                    not isinstance(uniform, bool)
                    and math.isfinite(uniform)
                    and 0.0 <= uniform < 1.0
                ):
                    try:
                        exponent = -math.log1p(-uniform) / shape
                        candidate = minimum * math.exp(exponent)
                    except (OverflowError, ValueError):
                        candidate = math.inf
            if math.isfinite(candidate) and minimum < candidate < maximum:
                values.append(candidate)
                break
            rejected += 1
        else:
            raise ValueError(
                "true truncated attention sampling exhausted the finite per-agent draw budget"
            )
    return tuple(values), rejected


def _normalize_positive_weights(raw: Sequence[float]) -> tuple[float, ...]:
    if not raw or any(not math.isfinite(value) or value <= 0 for value in raw):
        raise ValueError("raw attention weights must be finite and strictly positive")
    log_values = tuple(math.log(value) for value in raw)
    maximum_log = max(log_values)
    scaled = tuple(max(math.exp(value - maximum_log), _MIN_POSITIVE_FLOAT) for value in log_values)
    scaled_sum = math.fsum(scaled)
    if not math.isfinite(scaled_sum) or scaled_sum <= 0:
        raise ValueError("attention normalization scale is not finite and positive")
    population_size = len(raw)
    weights = [max(population_size * value / scaled_sum, _MIN_POSITIVE_FLOAT) for value in scaled]
    anchor = max(range(population_size), key=weights.__getitem__)
    weights[anchor] += population_size - math.fsum(weights)
    if any(not math.isfinite(weight) or weight <= 0 for weight in weights):
        raise ValueError("normalized attention weights must remain finite and strictly positive")
    if not math.isclose(math.fsum(weights), population_size, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("normalized attention weights must sum to population size")
    return tuple(weights)


def _bounded_gamma_candidate(rng: random.Random, shape: float) -> float | None:
    adjusted_shape = shape if shape >= 1.0 else shape + 1.0
    d = adjusted_shape - (1.0 / 3.0)
    nine_d = 9.0 * d
    if not math.isfinite(d) or not math.isfinite(nine_d) or d <= 0.0:
        return None
    c = 1.0 / math.sqrt(nine_d)
    normal = rng.gauss(0.0, 1.0)
    base = 1.0 + c * normal
    if not math.isfinite(normal) or not math.isfinite(base) or base <= 0.0:
        return None
    v = base * base * base
    if not math.isfinite(v) or v <= 0.0:
        return None
    uniform = rng.random()
    if not 0.0 < uniform < 1.0:
        return None
    accepted = uniform < 1.0 - 0.0331 * normal**4 or math.log(uniform) < (
        0.5 * normal * normal + d * (1.0 - v + math.log(v))
    )
    if not accepted:
        return None
    candidate = d * v
    if shape < 1.0:
        adjustment_uniform = rng.random()
        if not 0.0 < adjustment_uniform < 1.0:
            return None
        exponent = math.log(adjustment_uniform) / shape
        if not math.isfinite(exponent):
            return None
        candidate *= math.exp(exponent)
    if not math.isfinite(candidate) or candidate <= 0.0:
        return None
    return candidate


def _bounded_beta_candidate(
    rng: random.Random,
    alpha: float,
    beta: float,
) -> float | None:
    alpha_gamma = _bounded_gamma_candidate(rng, alpha)
    if alpha_gamma is None:
        return None
    beta_gamma = _bounded_gamma_candidate(rng, beta)
    if beta_gamma is None:
        return None
    if alpha_gamma >= beta_gamma:
        probability = 1.0 / (1.0 + beta_gamma / alpha_gamma)
    else:
        ratio = alpha_gamma / beta_gamma
        probability = ratio / (1.0 + ratio)
    if not math.isfinite(probability) or not 0.0 < probability < 1.0:
        return None
    return probability


def build_attention_artifact(
    *,
    agent_ids: Sequence[str],
    matched_seed: int,
    family: str,
    parameters: Mapping[str, object],
    mock_only: bool,
) -> ArtifactEnvelope:
    """Build positive attention weights normalized to exactly the population size."""

    _require_mock_only(mock_only)
    ids = _agent_ids(agent_ids)
    _require_population_capacity(len(ids))
    _require_int("matched_seed", matched_seed)
    if not isinstance(parameters, Mapping):
        raise TypeError("parameters must be a mapping")
    parameter_values = dict(parameters)
    if family == "positive_truncated_lognormal":
        if set(parameters) != {"log_location", "log_sigma", "minimum", "maximum"}:
            raise ValueError(
                "lognormal parameters must be log_location, log_sigma, minimum, and maximum"
            )
        location = _finite_number("log_location", parameters["log_location"])
        shape = _finite_number("log_sigma", parameters["log_sigma"], strictly_positive=True)
    elif family == "positive_truncated_pareto":
        if set(parameters) != {"shape", "minimum", "maximum"}:
            raise ValueError("Pareto parameters must be shape, minimum, and maximum")
        shape = _finite_number("shape", parameters["shape"], strictly_positive=True)
    elif family == "equal_weight":
        if parameters:
            raise ValueError("equal_weight does not accept parameters")
        shape = 1.0
    else:
        raise ValueError("unsupported attention family")
    if family == "equal_weight":
        location = None
        minimum = maximum = 1.0
    else:
        if family == "positive_truncated_pareto":
            location = None
        minimum = _finite_number("minimum", parameters["minimum"], strictly_positive=True)
        maximum = _finite_number("maximum", parameters["maximum"], strictly_positive=True)
        if minimum >= maximum:
            raise ValueError("attention minimum must be smaller than maximum")
    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="attention",
        coordinates={
            "artifact_kind": "mock_attention_weights",
            "family": family,
            "agent_ids_hash": canonical_payload_hash(ids),
            "parameters_hash": canonical_payload_hash(parameter_values),
            "algorithm_version": _ATTENTION_ALGORITHM_VERSION,
            "runtime_provenance_hash": canonical_payload_hash(_runtime_provenance()),
        },
    )
    rng = random.Random(provenance.derived_seed)
    if family in {"positive_truncated_lognormal", "positive_truncated_pareto"}:
        raw, rejected_draw_count = _sample_true_truncated(
            family=family,
            location=location,
            shape=shape,
            minimum=minimum,
            maximum=maximum,
            count=len(ids),
            rng=rng,
        )
    else:
        raw = (1.0,) * len(ids)
        rejected_draw_count = 0
    weights = _normalize_positive_weights(raw)
    sampling_algorithm_id = (
        f"paper1.mock_true_truncated_{family.removeprefix('positive_truncated_')}"
        if family != "equal_weight"
        else "paper1.mock_equal_weight"
    )
    primitive_rng_algorithm = {
        "positive_truncated_lognormal": "box_muller_cosine_two_uniforms_v1",
        "positive_truncated_pareto": "pareto_inverse_cdf_log1p_one_uniform_v1",
        "equal_weight": "none",
    }[family]
    primitive_random_calls_per_attempt = {
        "positive_truncated_lognormal": 2,
        "positive_truncated_pareto": 1,
        "equal_weight": 0,
    }[family]
    sampling_contract = {
        "algorithm_id": sampling_algorithm_id,
        "algorithm_version": _TRUNCATED_SAMPLING_VERSION,
        "max_draws_per_agent": _MAX_DRAWS_PER_AGENT,
        "primitive_rng_algorithm": primitive_rng_algorithm,
        "primitive_random_calls_per_attempt": primitive_random_calls_per_attempt,
        "boundary_rule": "strict_interior_no_winsorization",
    }
    payload = {
        "schema_version": "paper1.mock-attention.v1",
        "matched_seed": matched_seed,
        "family": family,
        "parameters": parameter_values,
        "normalization": "sum_equals_population_size",
        "agents": tuple(
            {"agent_id": agent_id, "raw_weight": raw_weight, "weight": weight}
            for agent_id, raw_weight, weight in zip(ids, raw, weights, strict=True)
        ),
        "sampling": {
            **sampling_contract,
            "rejected_draw_count": rejected_draw_count,
        },
        "diagnostics": {
            "weight_sum": math.fsum(weights),
            "minimum_weight": min(weights),
            "maximum_weight": max(weights),
            "weight_gini": _gini(weights),
        },
        "opinion_inputs_read": (),
        "runtime_provenance": _runtime_provenance(),
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_attention",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=_ATTENTION_ALGORITHM_ID,
        algorithm_version=_ATTENTION_ALGORITHM_VERSION,
        input_hashes={
            "agent_ids": canonical_payload_hash(ids),
            "mock_parameters": canonical_payload_hash(parameter_values),
            "sampling_contract": canonical_payload_hash(sampling_contract),
        },
        payload=payload,
        rng_provenance=(provenance,),
    )


def build_expression_artifact(
    *,
    agent_ids: Sequence[str],
    matched_seed: int,
    structural_lurker_probability: float,
    beta_alpha: float,
    beta_beta: float,
    max_beta_attempts_per_agent: int,
    correlation_mode: str,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Build expression propensities independently from attention and opinion state."""

    _require_mock_only(mock_only)
    ids = _agent_ids(agent_ids)
    _require_population_capacity(len(ids))
    _require_int("matched_seed", matched_seed)
    lurker_probability = _finite_number(
        "structural_lurker_probability", structural_lurker_probability
    )
    if not 0.0 <= lurker_probability <= 1.0:
        raise ValueError("structural_lurker_probability must be between zero and one")
    alpha = _finite_number("beta_alpha", beta_alpha, strictly_positive=True)
    beta = _finite_number("beta_beta", beta_beta, strictly_positive=True)
    _require_int("max_beta_attempts_per_agent", max_beta_attempts_per_agent, minimum=1)
    if max_beta_attempts_per_agent > _MAX_BETA_ATTEMPT_BUDGET:
        raise ValueError("max_beta_attempts_per_agent exceeds the Phase 4B platform capacity")
    if correlation_mode != "independent":
        raise ValueError(
            "correlation_mode must be independent; positive sensitivity requires a frozen method"
        )
    mock_parameters = {
        "structural_lurker_probability": lurker_probability,
        "beta_alpha": alpha,
        "beta_beta": beta,
    }
    sampling_contract = {
        "algorithm_id": "paper1.mock_bounded_gamma_ratio_beta",
        "algorithm_version": _BETA_SAMPLING_VERSION,
        "max_beta_attempts_per_agent": max_beta_attempts_per_agent,
        "maximum_gamma_candidates_per_attempt": 2,
        "maximum_gauss_calls_per_attempt": 2,
        "maximum_explicit_uniform_calls_per_attempt": 4,
        "boundary_rule": "strict_interior_no_clipping",
    }
    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="expression",
        coordinates={
            "artifact_kind": "mock_hurdle_beta_expression",
            "agent_ids_hash": canonical_payload_hash(ids),
            "parameters_hash": canonical_payload_hash(mock_parameters),
            "correlation_mode": correlation_mode,
            "algorithm_version": _EXPRESSION_ALGORITHM_VERSION,
            "sampling_contract_hash": canonical_payload_hash(sampling_contract),
            "runtime_provenance_hash": canonical_payload_hash(_runtime_provenance()),
        },
    )
    rng = random.Random(provenance.derived_seed)
    records = []
    rejected_beta_attempt_count = 0
    for agent_id in ids:
        lurker = rng.random() < lurker_probability
        if lurker:
            probability = 0.0
        else:
            for _attempt in range(max_beta_attempts_per_agent):
                probability = _bounded_beta_candidate(rng, alpha, beta)
                if probability is not None:
                    break
                rejected_beta_attempt_count += 1
            else:
                raise ValueError(
                    "strict interior Beta sampling exhausted the finite attempt budget"
                )
        records.append(
            {
                "agent_id": agent_id,
                "structural_lurker": lurker,
                "publish_probability": probability,
            }
        )
    payload = {
        "schema_version": "paper1.mock-expression.v1",
        "matched_seed": matched_seed,
        "family": "hurdle_beta",
        "parameters": mock_parameters,
        "correlation_mode": correlation_mode,
        "attention_inputs_read": (),
        "sampling": sampling_contract,
        "runtime_provenance": _runtime_provenance(),
        "agents": tuple(records),
        "diagnostics": {
            "structural_lurker_count": sum(record["structural_lurker"] for record in records),
            "structural_lurker_share": sum(record["structural_lurker"] for record in records)
            / len(records),
            "mean_publish_probability": math.fsum(
                record["publish_probability"] for record in records
            )
            / len(records),
            "rejected_beta_attempt_count": rejected_beta_attempt_count,
        },
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_expression",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=_EXPRESSION_ALGORITHM_ID,
        algorithm_version=_EXPRESSION_ALGORITHM_VERSION,
        input_hashes={
            "agent_ids": canonical_payload_hash(ids),
            "mock_parameters": canonical_payload_hash(mock_parameters),
            "sampling_contract": canonical_payload_hash(sampling_contract),
            "independence_contract": canonical_payload_hash(
                {
                    "correlation_mode": "independent",
                    "attention_inputs_read": (),
                    "opinion_inputs_read": (),
                }
            ),
        },
        payload=payload,
        rng_provenance=(provenance,),
    )


def _attention_records(
    artifact: ArtifactEnvelope,
) -> tuple[int, tuple[str, ...], tuple[float, ...]]:
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("attention_artifact must be an ArtifactEnvelope")
    if artifact.artifact_type != "paper1.mock_attention" or (
        artifact.algorithm_id != _ATTENTION_ALGORITHM_ID
        or artifact.algorithm_version != _ATTENTION_ALGORITHM_VERSION
    ):
        raise ValueError("attention artifact identity does not match the Phase 4B-5 contract")
    if not isinstance(artifact.payload, Mapping):
        raise TypeError("attention artifact payload must be a mapping")
    matched_seed = artifact.payload.get("matched_seed")
    _require_int("attention matched_seed", matched_seed)  # type: ignore[arg-type]
    records = artifact.payload.get("agents")
    if not isinstance(records, tuple) or not records:
        raise ValueError("attention agents must be a non-empty tuple")
    _require_population_capacity(len(records))
    ids = []
    weights = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "agent_id",
            "raw_weight",
            "weight",
        }:
            raise ValueError("attention agent records do not match the contract")
        _require_id("attention agent_id", record["agent_id"])  # type: ignore[arg-type]
        _finite_number("raw attention weight", record["raw_weight"], strictly_positive=True)
        weight = _finite_number("attention weight", record["weight"], strictly_positive=True)
        ids.append(record["agent_id"])
        weights.append(weight)
    frozen_ids = _agent_ids(ids)  # type: ignore[arg-type]
    if not math.isclose(math.fsum(weights), len(weights), rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("attention weights must sum to population size")
    if artifact.payload.get("metadata") != {
        "mock_only": True,
        "research_parameter_status": "not_frozen",
    }:
        raise ValueError("attention artifact must remain mock_only and not_frozen")
    family = artifact.payload.get("family")
    parameters = artifact.payload.get("parameters")
    if not isinstance(family, str) or not isinstance(parameters, Mapping):
        raise ValueError("attention family and parameters are missing")
    expected = build_attention_artifact(
        agent_ids=frozen_ids,
        matched_seed=matched_seed,  # type: ignore[arg-type]
        family=family,
        parameters=parameters,
        mock_only=True,
    )
    if artifact != expected:
        raise ValueError("attention RNG, parameter, agent, or hash drift detected")
    return matched_seed, frozen_ids, tuple(weights)  # type: ignore[return-value]


def _event_rng_key_digest(
    *,
    matched_seed: int,
    namespace: str,
    artifact_kind: str,
    event_count: int,
    common_coordinates: Mapping[str, object],
) -> str:
    if "event_ordinal" in common_coordinates:
        raise ValueError("event RNG ledger common coordinates cannot override event_ordinal")
    digest = hashlib.sha256()
    for event_ordinal in range(event_count):
        provenance = RNGProvenance.create(
            matched_seed=matched_seed,
            namespace=namespace,
            coordinates={
                "artifact_kind": artifact_kind,
                "event_ordinal": event_ordinal,
                **common_coordinates,
            },
        )
        digest.update(bytes.fromhex(canonical_payload_hash(provenance.to_payload())))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class ValidatedEventRNGLedger:
    matched_seed: int
    namespace: str
    artifact_kind: str
    event_count: int
    common_coordinates: Mapping[str, object]
    event_key_digest: str
    _validation_seal: object

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("ValidatedEventRNGLedger capabilities require trusted validation")

    def provenance_at(self, event_ordinal: int) -> RNGProvenance:
        if self._validation_seal is not _VALIDATED_EVENT_RNG_LEDGER_SEAL:
            raise TypeError("ledger capability was not issued by trusted validation")
        _require_int("event_ordinal", event_ordinal)
        if not 0 <= event_ordinal < self.event_count:
            raise ValueError("event_ordinal is outside the validated ledger range")
        return RNGProvenance.create(
            matched_seed=self.matched_seed,
            namespace=self.namespace,
            coordinates={
                "artifact_kind": self.artifact_kind,
                "event_ordinal": event_ordinal,
                **self.common_coordinates,
            },
        )


def _issue_validated_event_rng_ledger(
    *,
    matched_seed: int,
    namespace: str,
    artifact_kind: str,
    event_count: int,
    common_coordinates: Mapping[str, object],
    event_key_digest: str,
) -> ValidatedEventRNGLedger:
    """Issue an internal immutable capability after construction or validation."""

    _require_int("ledger matched_seed", matched_seed)
    _require_int("ledger event_count", event_count, minimum=1)
    if event_count > _PHASE4B_MAX_EVENT_COUNT:
        raise ValueError("ledger event_count exceeds the Phase 4B platform capacity")
    if "event_ordinal" in common_coordinates:
        raise ValueError("event RNG ledger common coordinates cannot override event_ordinal")
    capability = object.__new__(ValidatedEventRNGLedger)
    object.__setattr__(capability, "matched_seed", matched_seed)
    object.__setattr__(capability, "namespace", namespace)
    object.__setattr__(capability, "artifact_kind", artifact_kind)
    object.__setattr__(capability, "event_count", event_count)
    object.__setattr__(capability, "common_coordinates", _freeze(common_coordinates))
    object.__setattr__(capability, "event_key_digest", event_key_digest)
    object.__setattr__(capability, "_validation_seal", _VALIDATED_EVENT_RNG_LEDGER_SEAL)
    return capability


def _build_event_rng_ledger(
    *,
    matched_seed: int,
    namespace: str,
    artifact_kind: str,
    event_count: int,
    common_coordinates: Mapping[str, object],
) -> tuple[dict[str, object], RNGProvenance, ValidatedEventRNGLedger]:
    _require_int("event_count", event_count, minimum=1)
    if event_count > _PHASE4B_MAX_EVENT_COUNT:
        raise ValueError("event_count exceeds the Phase 4B platform capacity")
    event_key_digest = _event_rng_key_digest(
        matched_seed=matched_seed,
        namespace=namespace,
        artifact_kind=artifact_kind,
        event_count=event_count,
        common_coordinates=common_coordinates,
    )
    validated = _issue_validated_event_rng_ledger(
        matched_seed=matched_seed,
        namespace=namespace,
        artifact_kind=artifact_kind,
        event_count=event_count,
        common_coordinates=common_coordinates,
        event_key_digest=event_key_digest,
    )
    ledger = {
        "schema_version": _EVENT_RNG_LEDGER_VERSION,
        "derivation_version": RNG_DERIVATION_VERSION,
        "matched_seed": matched_seed,
        "event_namespace": namespace,
        "artifact_kind": artifact_kind,
        "ordinal_start": 0,
        "event_count": event_count,
        "common_coordinates": dict(common_coordinates),
        "digest_algorithm": "sha256_concat_canonical_event_provenance_hashes_v1",
        "event_key_digest": event_key_digest,
    }
    root = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace=f"{namespace}_ledger",
        coordinates={
            "artifact_kind": f"{artifact_kind}_ledger",
            "ledger_version": _EVENT_RNG_LEDGER_VERSION,
            "event_namespace": namespace,
            "event_count": event_count,
            "common_coordinates_hash": canonical_payload_hash(common_coordinates),
            "event_key_digest": ledger["event_key_digest"],
        },
    )
    return ledger, root, validated


def validate_event_rng_ledger(
    ledger: object,
    root: RNGProvenance,
    *,
    matched_seed: int,
    namespace: str,
    artifact_kind: str,
    event_count: int,
    expected_common_coordinates: Mapping[str, object],
) -> ValidatedEventRNGLedger:
    _require_int("event_count", event_count, minimum=1)
    if event_count > _PHASE4B_MAX_EVENT_COUNT:
        raise ValueError("event_count exceeds the Phase 4B platform capacity")
    if not isinstance(ledger, Mapping):
        raise TypeError("event RNG ledger must be a mapping")
    expected_fields = {
        "schema_version",
        "derivation_version",
        "matched_seed",
        "event_namespace",
        "artifact_kind",
        "ordinal_start",
        "event_count",
        "common_coordinates",
        "digest_algorithm",
        "event_key_digest",
    }
    if set(ledger) != expected_fields:
        raise ValueError("event RNG ledger fields do not match the contract")
    raw_matched_seed = ledger["matched_seed"]
    _require_int("ledger matched_seed", raw_matched_seed)  # type: ignore[arg-type]
    raw_event_count = ledger["event_count"]
    _require_int("ledger event_count", raw_event_count, minimum=1)  # type: ignore[arg-type]
    if raw_event_count > _PHASE4B_MAX_EVENT_COUNT:  # type: ignore[operator]
        raise ValueError("ledger event_count exceeds the Phase 4B platform capacity")
    ordinal_start = ledger["ordinal_start"]
    _require_int("ledger ordinal_start", ordinal_start, minimum=0)  # type: ignore[arg-type]
    if ordinal_start != 0:
        raise ValueError("ledger ordinal_start must be exactly zero")
    raw_common_coordinates = ledger["common_coordinates"]
    if not isinstance(raw_common_coordinates, Mapping):
        raise TypeError("ledger common_coordinates must be a JSON object")
    raw_common_hash = _strict_json_canonical_hash(
        "ledger common_coordinates", raw_common_coordinates
    )
    expected_common_hash = _strict_json_canonical_hash(
        "expected common_coordinates", expected_common_coordinates
    )
    if raw_common_hash != expected_common_hash:
        raise ValueError(f"{namespace} ledger common source coordinates drift detected")
    expected_ledger, expected_root, validated = _build_event_rng_ledger(
        matched_seed=matched_seed,
        namespace=namespace,
        artifact_kind=artifact_kind,
        event_count=event_count,
        common_coordinates=expected_common_coordinates,
    )
    if _strict_json_canonical_hash("event RNG ledger", ledger) != _strict_json_canonical_hash(
        "expected event RNG ledger", expected_ledger
    ) or _strict_json_canonical_hash(
        "event RNG ledger root", root.to_payload()
    ) != _strict_json_canonical_hash("expected event RNG ledger root", expected_root.to_payload()):
        raise ValueError(f"{namespace} event RNG ledger drift detected")
    return validated


def _validate_event_rng_ledger(
    ledger: object,
    root: RNGProvenance,
    **expected: object,
) -> ValidatedEventRNGLedger:
    return validate_event_rng_ledger(ledger, root, **expected)  # type: ignore[arg-type]


def reconstruct_event_rng_provenance(
    ledger: ValidatedEventRNGLedger, event_ordinal: int
) -> RNGProvenance:
    """Reconstruct one event key in O(1) from an already trusted ledger."""

    if not isinstance(ledger, ValidatedEventRNGLedger):
        raise TypeError("ledger must be a ValidatedEventRNGLedger")
    return ledger.provenance_at(event_ordinal)


def build_activation_schedule(
    attention_artifact: ArtifactEnvelope,
    *,
    matched_seed: int,
    sweep_count: int,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Pregenerate a weighted sequential activation artifact with replacement."""

    _require_mock_only(mock_only)
    _require_int("matched_seed", matched_seed)
    _require_int("sweep_count", sweep_count, minimum=1)
    if sweep_count > _PHASE4B_MAX_SWEEP_COUNT:
        raise ValueError("sweep_count exceeds the approved Phase 4B platform capacity")
    _preflight_record_population_capacity(attention_artifact, "agents")
    source_seed, ids, weights = _attention_records(attention_artifact)
    if source_seed != matched_seed:
        raise ValueError("activation matched_seed must match the attention artifact")
    population_size = len(ids)
    if population_size > _PHASE4B_MAX_POPULATION_SIZE:
        raise ValueError("population exceeds the approved Phase 4B platform capacity")
    event_count = population_size * sweep_count
    if event_count > _PHASE4B_MAX_EVENT_COUNT:
        raise ValueError("event count exceeds the approved Phase 4B platform capacity")
    common_coordinates = {
        "attention_artifact_id": attention_artifact.artifact_id,
        "attention_output_hash": attention_artifact.output_hash,
        "agent_ids_hash": canonical_payload_hash(ids),
        "sweep_count": sweep_count,
        "algorithm_version": _ACTIVATION_ALGORITHM_VERSION,
        "runtime_provenance_hash": canonical_payload_hash(_runtime_provenance()),
    }
    ledger, ledger_provenance, validated_ledger = _build_event_rng_ledger(
        matched_seed=matched_seed,
        namespace="activation",
        artifact_kind="mock_activation_event_choice",
        event_count=event_count,
        common_coordinates=common_coordinates,
    )
    cumulative_weights = tuple(accumulate(weights))
    total_weight = cumulative_weights[-1]
    draws = tuple(
        ids[
            min(
                bisect_left(
                    cumulative_weights,
                    random.Random(
                        validated_ledger.provenance_at(event_ordinal).derived_seed
                    ).random()
                    * total_weight,
                ),
                population_size - 1,
            )
        ]
        for event_ordinal in range(event_count)
    )
    slots = tuple(
        {
            "event_ordinal": ordinal,
            "sweep_index": ordinal // population_size + 1,
            "draw_index": ordinal % population_size,
            "agent_id": agent_id,
        }
        for ordinal, agent_id in enumerate(draws)
    )
    observed_counts = Counter(draws)
    activation_counts = {agent_id: observed_counts[agent_id] for agent_id in ids}
    payload = {
        "schema_version": "paper1.mock-activation-schedule.v1",
        "matched_seed": matched_seed,
        "population_size": population_size,
        "sweep_count": sweep_count,
        "sampling": "with_replacement",
        "rng_derivation": {
            "namespace": "activation",
            "per_event_ordinal": True,
            "algorithm": "independent_sha256_seed_then_random_uniform_cdf",
        },
        "rng_ledger": ledger,
        "capacity_contract": {
            "phase_boundary": "Phase 4B mock platform",
            "maximum_population_size": _PHASE4B_MAX_POPULATION_SIZE,
            "maximum_sweep_count": _PHASE4B_MAX_SWEEP_COUNT,
            "maximum_event_count": _PHASE4B_MAX_EVENT_COUNT,
        },
        "benchmark_resource_gate": {
            "scope": "N1000_T50_agent_percent04d_mock_fixture",
            "maximum_envelope_json_bytes": _PHASE4B_BENCHMARK_ACTIVATION_JSON_BYTES,
            "semantic_role": "engineering_regression_not_input_validity",
        },
        "population_agent_ids": ids,
        "attention_weights": weights,
        "population_agent_ids_hash": canonical_payload_hash(ids),
        "source_attention_artifact_id": attention_artifact.artifact_id,
        "source_attention_output_hash": attention_artifact.output_hash,
        "slots": slots,
        "diagnostics": {
            "activation_counts": activation_counts,
            "realized_activation_gini": _gini(tuple(activation_counts.values())),
            "zero_activation_count": sum(count == 0 for count in activation_counts.values()),
        },
        "opinion_inputs_read": (),
        "runtime_provenance": _runtime_provenance(),
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_activation_schedule",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=_ACTIVATION_ALGORITHM_ID,
        algorithm_version=_ACTIVATION_ALGORITHM_VERSION,
        input_hashes={
            "attention": attention_artifact.output_hash,
            "agent_ids": canonical_payload_hash(ids),
        },
        payload=payload,
        rng_provenance=(ledger_provenance,),
    )


def _expression_records(
    artifact: ArtifactEnvelope,
) -> tuple[int, tuple[str, ...], dict[str, tuple[bool, float]]]:
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("expression_artifact must be an ArtifactEnvelope")
    if artifact.artifact_type != "paper1.mock_expression" or (
        artifact.algorithm_id != _EXPRESSION_ALGORITHM_ID
        or artifact.algorithm_version != _EXPRESSION_ALGORITHM_VERSION
    ):
        raise ValueError("expression artifact identity does not match the Phase 4B-5 contract")
    if not isinstance(artifact.payload, Mapping):
        raise TypeError("expression artifact payload must be a mapping")
    seed = artifact.payload.get("matched_seed")
    _require_int("expression matched_seed", seed)  # type: ignore[arg-type]
    if artifact.payload.get("family") != "hurdle_beta" or (
        artifact.payload.get("correlation_mode") != "independent"
    ):
        raise ValueError("expression family or independence contract drift detected")
    if artifact.payload.get("attention_inputs_read") != ():
        raise ValueError("independent expression artifact cannot bind attention inputs")
    parameters = artifact.payload.get("parameters")
    if not isinstance(parameters, Mapping) or set(parameters) != {
        "structural_lurker_probability",
        "beta_alpha",
        "beta_beta",
    }:
        raise ValueError("expression parameters do not match the hurdle-Beta contract")
    lurker_probability = _finite_number(
        "structural_lurker_probability", parameters["structural_lurker_probability"]
    )
    if not 0 <= lurker_probability <= 1:
        raise ValueError("structural_lurker_probability must be between zero and one")
    alpha = _finite_number("beta_alpha", parameters["beta_alpha"], strictly_positive=True)
    beta = _finite_number("beta_beta", parameters["beta_beta"], strictly_positive=True)
    sampling = artifact.payload.get("sampling")
    if not isinstance(sampling, Mapping) or set(sampling) != {
        "algorithm_id",
        "algorithm_version",
        "max_beta_attempts_per_agent",
        "maximum_gamma_candidates_per_attempt",
        "maximum_gauss_calls_per_attempt",
        "maximum_explicit_uniform_calls_per_attempt",
        "boundary_rule",
    }:
        raise ValueError("expression sampling contract is missing")
    if sampling.get("algorithm_id") != "paper1.mock_bounded_gamma_ratio_beta" or (
        sampling.get("algorithm_version") != _BETA_SAMPLING_VERSION
        or sampling.get("boundary_rule") != "strict_interior_no_clipping"
        or sampling.get("maximum_gamma_candidates_per_attempt") != 2
        or sampling.get("maximum_gauss_calls_per_attempt") != 2
        or sampling.get("maximum_explicit_uniform_calls_per_attempt") != 4
    ):
        raise ValueError("expression sampling contract drift detected")
    max_beta_attempts = sampling.get("max_beta_attempts_per_agent")
    _require_int("max_beta_attempts_per_agent", max_beta_attempts, minimum=1)  # type: ignore[arg-type]
    records = artifact.payload.get("agents")
    if not isinstance(records, tuple) or not records:
        raise ValueError("expression agents must be a non-empty tuple")
    _require_population_capacity(len(records))
    ids = []
    values: dict[str, tuple[bool, float]] = {}
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "agent_id",
            "structural_lurker",
            "publish_probability",
        }:
            raise ValueError("expression agent records do not match the contract")
        agent_id = record["agent_id"]
        _require_id("expression agent_id", agent_id)  # type: ignore[arg-type]
        if type(record["structural_lurker"]) is not bool:
            raise TypeError("structural_lurker must be a boolean")
        probability = _finite_number("publish_probability", record["publish_probability"])
        if not 0 <= probability <= 1:
            raise ValueError("publish_probability must be between zero and one")
        if record["structural_lurker"] and probability != 0:
            raise ValueError("structural lurkers must have zero publish probability")
        if not record["structural_lurker"] and not 0 < probability < 1:
            raise ValueError("non-lurker publish probability must be strictly between zero and one")
        ids.append(agent_id)
        values[agent_id] = (record["structural_lurker"], probability)  # type: ignore[index]
    frozen_ids = _agent_ids(ids)  # type: ignore[arg-type]
    expected = build_expression_artifact(
        agent_ids=frozen_ids,
        matched_seed=seed,  # type: ignore[arg-type]
        structural_lurker_probability=lurker_probability,
        beta_alpha=alpha,
        beta_beta=beta,
        max_beta_attempts_per_agent=max_beta_attempts,  # type: ignore[arg-type]
        correlation_mode="independent",
        mock_only=True,
    )
    if artifact != expected:
        raise ValueError("expression RNG, parameter, agent, or hash drift detected")
    return seed, frozen_ids, values  # type: ignore[return-value]


def _activation_details(
    artifact: ArtifactEnvelope,
    attention_artifact: ArtifactEnvelope,
) -> tuple[int, tuple[str, ...], tuple[float, ...], int, tuple[Mapping[str, object], ...]]:
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("activation_artifact must be an ArtifactEnvelope")
    if artifact.artifact_type != "paper1.mock_activation_schedule" or (
        artifact.algorithm_id != _ACTIVATION_ALGORITHM_ID
        or artifact.algorithm_version != _ACTIVATION_ALGORITHM_VERSION
    ):
        raise ValueError("activation artifact identity does not match the Phase 4B-5 contract")
    if not isinstance(artifact.payload, Mapping):
        raise TypeError("activation artifact payload must be a mapping")
    attention_seed, attention_ids, attention_weights = _attention_records(attention_artifact)
    seed = artifact.payload.get("matched_seed")
    population_size = artifact.payload.get("population_size")
    sweep_count = artifact.payload.get("sweep_count")
    _require_int("activation matched_seed", seed)  # type: ignore[arg-type]
    _require_int("activation population_size", population_size, minimum=1)  # type: ignore[arg-type]
    _require_int("activation sweep_count", sweep_count, minimum=1)  # type: ignore[arg-type]
    ids = _agent_ids(artifact.payload.get("population_agent_ids"))  # type: ignore[arg-type]
    if len(ids) != population_size:
        raise ValueError("activation population_size does not match agent IDs")
    raw_weights = artifact.payload.get("attention_weights")
    if not isinstance(raw_weights, tuple) or len(raw_weights) != len(ids):
        raise ValueError("activation attention_weights do not match population")
    weights = tuple(
        _finite_number("activation attention weight", value, strictly_positive=True)
        for value in raw_weights
    )
    if seed != attention_seed or ids != attention_ids or weights != attention_weights:
        raise ValueError("activation must exactly bind the expected attention artifact")
    expected_input_hashes = {
        "attention": attention_artifact.output_hash,
        "agent_ids": canonical_payload_hash(attention_ids),
    }
    if dict(artifact.input_hashes) != expected_input_hashes or (
        artifact.payload.get("source_attention_artifact_id") != attention_artifact.artifact_id
        or artifact.payload.get("source_attention_output_hash") != attention_artifact.output_hash
    ):
        raise ValueError("activation source attention IDs or hashes drift detected")
    if not math.isclose(math.fsum(weights), len(ids), rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("activation attention weights must sum to population size")
    if artifact.payload.get("population_agent_ids_hash") != canonical_payload_hash(ids) or (
        artifact.input_hashes.get("agent_ids") != canonical_payload_hash(ids)
    ):
        raise ValueError("activation agent IDs hash drift detected")
    slots = artifact.payload.get("slots")
    if not isinstance(slots, tuple) or len(slots) != len(ids) * sweep_count:
        raise ValueError("activation slots do not cover N draws in every sweep")
    if len(artifact.rng_provenance) != 1 or artifact.rng_provenance[0].namespace != (
        "activation_ledger"
    ):
        raise ValueError("activation RNG provenance must use one compact ledger root")
    for ordinal, slot in enumerate(slots):
        if not isinstance(slot, Mapping) or set(slot) != {
            "event_ordinal",
            "sweep_index",
            "draw_index",
            "agent_id",
        }:
            raise ValueError("activation slots do not match the contract")
        if (
            slot["event_ordinal"] != ordinal
            or slot["sweep_index"] != ordinal // len(ids) + 1
            or slot["draw_index"] != ordinal % len(ids)
        ):
            raise ValueError("activation ordinal, sweep, or draw sequence drift detected")
    common_coordinates = {
        "attention_artifact_id": attention_artifact.artifact_id,
        "attention_output_hash": attention_artifact.output_hash,
        "agent_ids_hash": canonical_payload_hash(ids),
        "sweep_count": sweep_count,
        "algorithm_version": _ACTIVATION_ALGORITHM_VERSION,
        "runtime_provenance_hash": canonical_payload_hash(_runtime_provenance()),
    }
    _validate_event_rng_ledger(
        artifact.payload.get("rng_ledger"),
        artifact.rng_provenance[0],
        matched_seed=seed,  # type: ignore[arg-type]
        namespace="activation",
        artifact_kind="mock_activation_event_choice",
        event_count=len(slots),
        expected_common_coordinates=common_coordinates,
    )
    expected = build_activation_schedule(
        attention_artifact,
        matched_seed=attention_seed,
        sweep_count=sweep_count,  # type: ignore[arg-type]
        mock_only=True,
    )
    if artifact != expected:
        raise ValueError(
            "activation RNG, source, diagnostics, runtime provenance, or hash drift detected"
        )
    return seed, ids, weights, sweep_count, slots  # type: ignore[return-value]


def build_publish_schedule(
    attention_artifact: ArtifactEnvelope,
    activation_artifact: ArtifactEnvelope,
    expression_artifact: ArtifactEnvelope,
    *,
    matched_seed: int,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Bind pregenerated publish flags to activation slots as a complete frozen schedule."""

    _require_mock_only(mock_only)
    _require_int("matched_seed", matched_seed)
    _preflight_record_population_capacity(attention_artifact, "agents")
    _preflight_record_population_capacity(expression_artifact, "agents")
    _preflight_activation_capacity(activation_artifact)
    attention_seed, attention_ids, _ = _attention_records(attention_artifact)
    activation_seed, ids, _, sweep_count, activation_slots = _activation_details(
        activation_artifact, attention_artifact
    )
    expression_seed, expression_ids, expression_by_agent = _expression_records(expression_artifact)
    if not attention_seed == activation_seed == expression_seed == matched_seed:
        raise ValueError(
            "publish matched_seed must match attention, activation, and expression artifacts"
        )
    if not attention_ids == ids == expression_ids:
        raise ValueError("publish requires identical ordered agent IDs across source artifacts")
    common_coordinates = {
        "attention_artifact_id": attention_artifact.artifact_id,
        "attention_output_hash": attention_artifact.output_hash,
        "activation_artifact_id": activation_artifact.artifact_id,
        "activation_output_hash": activation_artifact.output_hash,
        "expression_artifact_id": expression_artifact.artifact_id,
        "expression_output_hash": expression_artifact.output_hash,
        "algorithm_version": _PUBLISH_ALGORITHM_VERSION,
        "runtime_provenance_hash": canonical_payload_hash(_runtime_provenance()),
    }
    ledger, ledger_provenance, validated_ledger = _build_event_rng_ledger(
        matched_seed=matched_seed,
        namespace="publish",
        artifact_kind="mock_publish_event_flag",
        event_count=len(activation_slots),
        common_coordinates=common_coordinates,
    )
    slots = tuple(
        ScheduleSlot(
            event_ordinal=slot["event_ordinal"],  # type: ignore[arg-type]
            sweep_index=slot["sweep_index"],  # type: ignore[arg-type]
            draw_index=slot["draw_index"],  # type: ignore[arg-type]
            agent_id=slot["agent_id"],  # type: ignore[arg-type]
            publish_flag=random.Random(
                validated_ledger.provenance_at(slot["event_ordinal"]).derived_seed  # type: ignore[arg-type]
            ).random()
            < expression_by_agent[slot["agent_id"]][1],  # type: ignore[index]
        )
        for slot in activation_slots
    )
    frozen = FrozenSchedule(
        schema_version="paper1.schedule.v2",
        algorithm_id=_FROZEN_SCHEDULE_ALGORITHM_ID,
        algorithm_version=_FROZEN_SCHEDULE_ALGORITHM_VERSION,
        population_size=len(ids),
        sweep_count=sweep_count,
        slots=slots,
    )
    published_counts = Counter(slot.agent_id for slot in slots if slot.publish_flag)
    per_agent_counts = {agent_id: published_counts[agent_id] for agent_id in ids}
    payload = {
        "schema_version": "paper1.mock-publish-schedule.v1",
        "matched_seed": matched_seed,
        "source_attention_artifact_id": attention_artifact.artifact_id,
        "source_attention_output_hash": attention_artifact.output_hash,
        "source_activation_artifact_id": activation_artifact.artifact_id,
        "source_activation_output_hash": activation_artifact.output_hash,
        "source_expression_artifact_id": expression_artifact.artifact_id,
        "source_expression_output_hash": expression_artifact.output_hash,
        "population_agent_ids_hash": canonical_payload_hash(ids),
        "rng_derivation": {
            "namespace": "publish",
            "per_event_ordinal": True,
            "algorithm": "independent_sha256_seed_then_random_uniform_threshold",
        },
        "rng_ledger": ledger,
        "capacity_contract": {
            "phase_boundary": "Phase 4B mock platform",
            "maximum_population_size": _PHASE4B_MAX_POPULATION_SIZE,
            "maximum_sweep_count": _PHASE4B_MAX_SWEEP_COUNT,
            "maximum_event_count": _PHASE4B_MAX_EVENT_COUNT,
        },
        "benchmark_resource_gate": {
            "scope": "N1000_T50_agent_percent04d_mock_fixture",
            "maximum_envelope_json_bytes": _PHASE4B_BENCHMARK_PUBLISH_JSON_BYTES,
            "semantic_role": "engineering_regression_not_input_validity",
        },
        "flags_generated_before_run": True,
        "frozen_schedule": frozen.to_payload(),
        "schedule_hash": frozen.schedule_hash,
        "publish_count": sum(slot.publish_flag for slot in slots),
        "per_agent_publish_counts": per_agent_counts,
        "opinion_inputs_read": (),
        "runtime_provenance": _runtime_provenance(),
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_publish_schedule",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=_PUBLISH_ALGORITHM_ID,
        algorithm_version=_PUBLISH_ALGORITHM_VERSION,
        input_hashes={
            "attention": attention_artifact.output_hash,
            "activation": activation_artifact.output_hash,
            "expression": expression_artifact.output_hash,
            "agent_ids": canonical_payload_hash(ids),
        },
        payload=payload,
        rng_provenance=(ledger_provenance,),
    )


def validate_matched_schedule_reuse(
    *,
    cell_artifacts: Mapping[
        str,
        tuple[ArtifactEnvelope, ArtifactEnvelope, ArtifactEnvelope, ArtifactEnvelope],
    ],
    expected_matched_seed: int,
) -> Mapping[str, str]:
    """Require exact same-seed reuse of all four artifacts across the 12 Paper 1 cells."""

    _require_int("expected_matched_seed", expected_matched_seed)
    if not isinstance(cell_artifacts, Mapping):
        raise TypeError("cell_artifacts must be a mapping keyed by canonical cell identity")
    if set(cell_artifacts) != set(_PAPER1_CELL_IDS) or len(cell_artifacts) != 12:
        raise ValueError("matched schedule reuse requires the complete canonical 12-cell set")
    ordered = []
    for cell_id in _PAPER1_CELL_IDS:
        bundle = cell_artifacts[cell_id]
        if (
            not isinstance(bundle, tuple)
            or len(bundle) != 4
            or not all(isinstance(item, ArtifactEnvelope) for item in bundle)
        ):
            raise TypeError(
                "each canonical cell must bind an attention/expression/activation/publish tuple"
            )
        ordered.append(bundle)
    for attention, expression, activation, publish in ordered:
        _preflight_record_population_capacity(attention, "agents")
        _preflight_record_population_capacity(expression, "agents")
        _preflight_activation_capacity(activation)
        _preflight_publish_capacity(publish)
    reference = ordered[0]
    if any(bundle != reference for bundle in ordered[1:]):
        raise ValueError("matched schedule reuse requires exact four-artifact reuse across cells")
    attention, expression, activation, publish = reference
    attention_seed, attention_ids, _ = _attention_records(attention)
    expression_seed, expression_ids, _ = _expression_records(expression)
    activation_seed, activation_ids, _, _, _ = _activation_details(activation, attention)
    if not attention_seed == expression_seed == activation_seed == expected_matched_seed:
        raise ValueError("matched schedule reuse expected seed does not match all artifacts")
    expected_activation = build_activation_schedule(
        attention,
        matched_seed=attention_seed,
        sweep_count=activation.payload["sweep_count"],  # type: ignore[index,arg-type]
        mock_only=True,
    )
    if activation != expected_activation:
        raise ValueError("matched schedule reuse activation binding or RNG drift detected")
    expected_publish = build_publish_schedule(
        attention,
        activation,
        expression,
        matched_seed=attention_seed,
        mock_only=True,
    )
    if publish != expected_publish:
        raise ValueError("matched schedule reuse publish binding or RNG drift detected")
    if not (
        attention_seed == expression_seed == activation_seed
        and attention_ids == expression_ids == activation_ids
    ):
        raise ValueError("matched schedule reuse seed or agent binding drift detected")
    transported_payload = publish.to_payload()["payload"]
    assert isinstance(transported_payload, dict)
    frozen = FrozenSchedule.from_payload(transported_payload["frozen_schedule"])  # type: ignore[arg-type]
    return {
        "attention": attention.output_hash,
        "expression": expression.output_hash,
        "activation": activation.output_hash,
        "publish": publish.output_hash,
        "frozen_schedule": frozen.schedule_hash,
    }
