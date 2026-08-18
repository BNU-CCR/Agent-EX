import json
import math
import random
from collections.abc import Sequence

import pytest

import agent_ex.schedule as schedule_module
from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import FrozenSchedule
from agent_ex.rng import RNGProvenance
from agent_ex.schedule import (
    build_activation_schedule,
    build_attention_artifact,
    build_expression_artifact,
    build_publish_schedule,
    reconstruct_event_rng_provenance,
    validate_matched_schedule_reuse,
)


def agent_ids(n: int) -> tuple[str, ...]:
    return tuple(f"agent-{index:04d}" for index in range(n))


class OversizedUnmaterializableAgentIds(Sequence[str]):
    def __len__(self) -> int:
        return 1_001

    def __getitem__(self, index: int) -> str:
        del index
        raise AssertionError("MATERIALIZED_BEFORE_CAPACITY")


class BoundaryProbingAgentIds(Sequence[str]):
    def __len__(self) -> int:
        return 1_000

    def __getitem__(self, index: int) -> str:
        if 0 <= index < 1_000:
            return f"agent-{index:04d}"
        raise AssertionError("PROBED_BEYOND_VALIDATED_LENGTH")


def paper1_cell_ids() -> tuple[str, ...]:
    return tuple(
        f"P1-I{identity}-C{continuity}-E{exposure}"
        for identity in range(2)
        for continuity in range(2)
        for exposure in range(3)
    )


def cell_artifacts(attention, expression, activation, publish):
    return {cell_id: (attention, expression, activation, publish) for cell_id in paper1_cell_ids()}


def test_attention_lognormal_is_positive_normalized_and_mock_only() -> None:
    artifact = build_attention_artifact(
        agent_ids=agent_ids(20),
        matched_seed=17,
        family="positive_truncated_lognormal",
        parameters={"log_location": 0.0, "log_sigma": 0.7, "minimum": 0.1, "maximum": 8.0},
        mock_only=True,
    )

    weights = tuple(item["weight"] for item in artifact.payload["agents"])
    assert all(weight > 0 for weight in weights)
    assert sum(weights) == pytest.approx(20.0, abs=1e-12)
    assert artifact.payload["metadata"] == {
        "mock_only": True,
        "research_parameter_status": "not_frozen",
    }
    assert artifact.rng_provenance[0].namespace == "attention"
    assert "cell_id" not in artifact.rng_provenance[0].coordinates
    assert artifact.payload["diagnostics"]["weight_sum"] == pytest.approx(20.0)
    assert artifact.payload["opinion_inputs_read"] == ()


@pytest.mark.parametrize(
    ("family", "parameters"),
    [
        ("positive_truncated_pareto", {"shape": 2.5, "minimum": 0.1, "maximum": 8.0}),
        ("equal_weight", {}),
    ],
)
def test_attention_supports_only_explicit_mock_sensitivity_families(
    family: str, parameters: dict[str, float]
) -> None:
    artifact = build_attention_artifact(
        agent_ids=agent_ids(20),
        matched_seed=17,
        family=family,
        parameters=parameters,
        mock_only=True,
    )

    weights = tuple(item["weight"] for item in artifact.payload["agents"])
    assert all(weight > 0 for weight in weights)
    assert sum(weights) == pytest.approx(20.0, abs=1e-12)
    if family == "equal_weight":
        assert weights == (1.0,) * 20


@pytest.mark.parametrize(
    ("family", "parameters"),
    [
        (
            "positive_truncated_lognormal",
            {"log_location": 0.0, "log_sigma": 3.0, "minimum": 0.8, "maximum": 1.2},
        ),
        (
            "positive_truncated_pareto",
            {"shape": 1.2, "minimum": 0.8, "maximum": 1.2},
        ),
    ],
)
def test_attention_uses_true_bounded_rejection_sampling_without_boundary_mass(
    family: str, parameters: dict[str, float]
) -> None:
    artifact = build_attention_artifact(
        agent_ids=agent_ids(200),
        matched_seed=17,
        family=family,
        parameters=parameters,
        mock_only=True,
    )

    raw = tuple(record["raw_weight"] for record in artifact.payload["agents"])
    assert all(parameters["minimum"] < value < parameters["maximum"] for value in raw)
    assert artifact.payload["sampling"]["algorithm_id"].startswith("paper1.mock_true_truncated_")
    assert artifact.payload["sampling"]["rejected_draw_count"] > 0
    assert artifact.payload["sampling"]["max_draws_per_agent"] > 0


def test_attention_extreme_parameters_never_emit_nonpositive_normalized_weights() -> None:
    artifact = build_attention_artifact(
        agent_ids=agent_ids(100),
        matched_seed=0,
        family="positive_truncated_lognormal",
        parameters={
            "log_location": 0.0,
            "log_sigma": 200.0,
            "minimum": 1e-300,
            "maximum": 1e300,
        },
        mock_only=True,
    )

    weights = tuple(record["weight"] for record in artifact.payload["agents"])
    assert all(math.isfinite(weight) and weight > 0 for weight in weights)
    assert math.fsum(weights) == pytest.approx(100.0, abs=1e-12)


def test_attention_true_truncation_exhaustion_fails_closed() -> None:
    with pytest.raises(ValueError, match="exhausted.*budget"):
        build_attention_artifact(
            agent_ids=("agent-0000",),
            matched_seed=17,
            family="positive_truncated_lognormal",
            parameters={
                "log_location": 0.0,
                "log_sigma": 1.0,
                "minimum": 1e300,
                "maximum": 1.0000001e300,
            },
            mock_only=True,
        )


@pytest.mark.parametrize(
    ("family", "parameters", "forbidden_helper", "draws_per_attempt"),
    [
        (
            "positive_truncated_lognormal",
            {"log_location": 0.0, "log_sigma": 0.7, "minimum": 0.1, "maximum": 8.0},
            "lognormvariate",
            2,
        ),
        (
            "positive_truncated_pareto",
            {"shape": 2.5, "minimum": 0.1, "maximum": 8.0},
            "paretovariate",
            1,
        ),
    ],
)
def test_attention_truncation_uses_explicit_bounded_primitive_rng(
    monkeypatch: pytest.MonkeyPatch,
    family: str,
    parameters: dict[str, float],
    forbidden_helper: str,
    draws_per_attempt: int,
) -> None:
    original_random = random.Random.random
    primitive_calls = 0

    def counted_random(rng: random.Random) -> float:
        nonlocal primitive_calls
        primitive_calls += 1
        return original_random(rng)

    def forbidden(*args: object, **kwargs: object) -> float:
        del args, kwargs
        raise AssertionError("stdlib distribution helper must not be called")

    monkeypatch.setattr(random.Random, "random", counted_random)
    monkeypatch.setattr(random.Random, "normalvariate", forbidden)
    monkeypatch.setattr(random.Random, "lognormvariate", forbidden)
    monkeypatch.setattr(random.Random, forbidden_helper, forbidden)

    artifact = build_attention_artifact(
        agent_ids=agent_ids(20),
        matched_seed=17,
        family=family,
        parameters=parameters,
        mock_only=True,
    )

    attempts = 20 + artifact.payload["sampling"]["rejected_draw_count"]
    assert primitive_calls == draws_per_attempt * attempts
    assert artifact.payload["sampling"]["primitive_random_calls_per_attempt"] == draws_per_attempt


def test_lognormal_zero_uniform_exhausts_finite_primitive_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primitive_calls = 0

    def zero_random(rng: random.Random) -> float:
        del rng
        nonlocal primitive_calls
        primitive_calls += 1
        return 0.0

    monkeypatch.setattr(random.Random, "random", zero_random)
    with pytest.raises(ValueError, match="exhausted.*budget"):
        build_attention_artifact(
            agent_ids=("agent-0000",),
            matched_seed=17,
            family="positive_truncated_lognormal",
            parameters={
                "log_location": 0.0,
                "log_sigma": 1.0,
                "minimum": 0.1,
                "maximum": 8.0,
            },
            mock_only=True,
        )
    assert primitive_calls == 2 * schedule_module._MAX_DRAWS_PER_AGENT


def test_attention_is_seed_deterministic_and_rejects_coder_defaults() -> None:
    arguments = {
        "agent_ids": agent_ids(20),
        "family": "positive_truncated_lognormal",
        "parameters": {
            "log_location": 0.0,
            "log_sigma": 0.7,
            "minimum": 0.1,
            "maximum": 8.0,
        },
        "mock_only": True,
    }
    first = build_attention_artifact(matched_seed=17, **arguments)

    assert first == build_attention_artifact(matched_seed=17, **arguments)
    assert first != build_attention_artifact(matched_seed=18, **arguments)
    with pytest.raises(ValueError, match="parameters"):
        build_attention_artifact(
            agent_ids=agent_ids(20),
            matched_seed=17,
            family="positive_truncated_lognormal",
            parameters={},
            mock_only=True,
        )


def test_lognormal_location_is_explicit_hashed_and_replayed_fail_closed() -> None:
    common = {
        "agent_ids": agent_ids(20),
        "matched_seed": 17,
        "family": "positive_truncated_lognormal",
        "mock_only": True,
    }
    with pytest.raises(ValueError, match="log_location"):
        build_attention_artifact(
            **common,
            parameters={"log_sigma": 0.7, "minimum": 0.1, "maximum": 8.0},
        )

    centered = build_attention_artifact(
        **common,
        parameters={"log_location": 0.0, "log_sigma": 0.7, "minimum": 0.1, "maximum": 8.0},
    )
    shifted = build_attention_artifact(
        **common,
        parameters={"log_location": 0.5, "log_sigma": 0.7, "minimum": 0.1, "maximum": 8.0},
    )

    assert centered.payload["parameters"]["log_location"] == 0.0
    assert shifted.payload["parameters"]["log_location"] == 0.5
    assert centered.input_hashes["mock_parameters"] != shifted.input_hashes["mock_parameters"]
    assert (
        centered.rng_provenance[0].coordinates["parameters_hash"]
        != (shifted.rng_provenance[0].coordinates["parameters_hash"])
    )
    assert centered.output_hash != shifted.output_hash
    assert centered.payload["agents"] != shifted.payload["agents"]

    forged_payload = centered.to_payload()["payload"]
    del forged_payload["parameters"]["log_location"]
    forged = rebuild(centered, forged_payload)
    with pytest.raises(ValueError, match="log_location"):
        build_activation_schedule(forged, matched_seed=17, sweep_count=3, mock_only=True)

    wrong_location_payload = centered.to_payload()["payload"]
    wrong_location_payload["parameters"]["log_location"] = 0.5
    wrong_location = rebuild(centered, wrong_location_payload)
    with pytest.raises(ValueError, match="attention.*drift"):
        build_activation_schedule(
            wrong_location,
            matched_seed=17,
            sweep_count=3,
            mock_only=True,
        )


def test_schedule_artifacts_record_python_and_random_runtime_provenance() -> None:
    attention, expression, activation, publish = schedule_artifacts()

    for artifact in (attention, expression, activation, publish):
        runtime = artifact.payload["runtime_provenance"]
        assert runtime["python_implementation"] == "CPython"
        assert runtime["python_version"]
        assert runtime["random_implementation"] == "python.random.Random(MT19937)"


def test_expression_is_independent_hurdle_beta_and_auditable() -> None:
    artifact = build_expression_artifact(
        agent_ids=agent_ids(100),
        matched_seed=17,
        structural_lurker_probability=0.2,
        beta_alpha=2.0,
        beta_beta=5.0,
        max_beta_attempts_per_agent=100,
        correlation_mode="independent",
        mock_only=True,
    )

    records = artifact.payload["agents"]
    assert any(item["structural_lurker"] for item in records)
    assert any(not item["structural_lurker"] for item in records)
    assert all(
        item["publish_probability"] == 0.0
        if item["structural_lurker"]
        else 0.0 < item["publish_probability"] < 1.0
        for item in records
    )
    assert artifact.payload["correlation_mode"] == "independent"
    assert artifact.payload["attention_inputs_read"] == ()
    assert artifact.rng_provenance[0].namespace == "expression"
    assert artifact.payload["metadata"]["research_parameter_status"] == "not_frozen"
    assert artifact.payload["sampling"] == {
        "algorithm_id": "paper1.mock_bounded_gamma_ratio_beta",
        "algorithm_version": "2.0.0",
        "max_beta_attempts_per_agent": 100,
        "maximum_gamma_candidates_per_attempt": 2,
        "maximum_gauss_calls_per_attempt": 2,
        "maximum_explicit_uniform_calls_per_attempt": 4,
        "boundary_rule": "strict_interior_no_clipping",
    }
    assert artifact.input_hashes["sampling_contract"]
    assert artifact.rng_provenance[0].coordinates["sampling_contract_hash"]
    assert artifact.payload["diagnostics"]["structural_lurker_count"] == sum(
        item["structural_lurker"] for item in records
    )


def test_expression_is_seed_deterministic_and_requires_explicit_mock_parameters() -> None:
    arguments = {
        "agent_ids": agent_ids(100),
        "structural_lurker_probability": 0.2,
        "beta_alpha": 2.0,
        "beta_beta": 5.0,
        "max_beta_attempts_per_agent": 100,
        "correlation_mode": "independent",
        "mock_only": True,
    }
    first = build_expression_artifact(matched_seed=17, **arguments)

    assert first == build_expression_artifact(matched_seed=17, **arguments)
    assert first != build_expression_artifact(matched_seed=18, **arguments)
    with pytest.raises(ValueError, match="correlation"):
        build_expression_artifact(matched_seed=17, **{**arguments, "correlation_mode": "positive"})


def test_expression_beta_sampling_is_strictly_interior_budgeted_and_explicit() -> None:
    common = {
        "agent_ids": ("agent-0000",),
        "matched_seed": 17,
        "structural_lurker_probability": 0.0,
        "beta_alpha": 1e-300,
        "beta_beta": 1.0,
        "correlation_mode": "independent",
        "mock_only": True,
    }
    with pytest.raises(TypeError, match="max_beta_attempts_per_agent"):
        build_expression_artifact(**common)
    with pytest.raises(ValueError, match="exhausted.*budget"):
        build_expression_artifact(**common, max_beta_attempts_per_agent=3)
    with pytest.raises(TypeError, match="max_beta_attempts_per_agent"):
        build_expression_artifact(**common, max_beta_attempts_per_agent=True)
    with pytest.raises(ValueError, match="capacity"):
        build_expression_artifact(**common, max_beta_attempts_per_agent=10_001)


def test_expression_extreme_shapes_never_call_unbounded_stdlib_beta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primitive_calls = {"random": 0, "gauss": 0}
    original_random = random.Random.random
    original_gauss = random.Random.gauss

    def counted_random(self):
        primitive_calls["random"] += 1
        return original_random(self)

    def counted_gauss(self, mu, sigma):
        primitive_calls["gauss"] += 1
        return original_gauss(self, mu, sigma)

    def forbidden_betavariate(self, alpha, beta):
        raise AssertionError("stdlib betavariate is an unbounded internal loop")

    monkeypatch.setattr(random.Random, "random", counted_random)
    monkeypatch.setattr(random.Random, "gauss", counted_gauss)
    monkeypatch.setattr(random.Random, "betavariate", forbidden_betavariate)

    with pytest.raises(ValueError, match="exhausted.*budget|unsupported.*shape"):
        build_expression_artifact(
            agent_ids=("agent-0000",),
            matched_seed=17,
            structural_lurker_probability=0.0,
            beta_alpha=1e308,
            beta_beta=1e308,
            max_beta_attempts_per_agent=2,
            correlation_mode="independent",
            mock_only=True,
        )
    assert primitive_calls["random"] <= 9
    assert primitive_calls["gauss"] <= 4


def test_bounded_beta_sampler_preserves_basic_distribution_sanity() -> None:
    artifact = build_expression_artifact(
        agent_ids=agent_ids(1_000),
        matched_seed=17,
        structural_lurker_probability=0.0,
        beta_alpha=2.0,
        beta_beta=2.0,
        max_beta_attempts_per_agent=100,
        correlation_mode="independent",
        mock_only=True,
    )
    probabilities = tuple(record["publish_probability"] for record in artifact.payload["agents"])
    assert all(0.0 < probability < 1.0 for probability in probabilities)
    assert math.fsum(probabilities) / len(probabilities) == pytest.approx(0.5, abs=0.04)
    assert artifact.payload["metadata"]["research_parameter_status"] == "not_frozen"


def test_activation_schedule_is_weighted_with_replacement_and_continuous() -> None:
    attention = build_attention_artifact(
        agent_ids=agent_ids(20),
        matched_seed=17,
        family="equal_weight",
        parameters={},
        mock_only=True,
    )
    artifact = build_activation_schedule(
        attention,
        matched_seed=17,
        sweep_count=3,
        mock_only=True,
    )

    slots = artifact.payload["slots"]
    assert len(slots) == 60
    assert tuple(slot["event_ordinal"] for slot in slots) == tuple(range(60))
    assert tuple(slot["sweep_index"] for slot in slots[:20]) == (1,) * 20
    assert tuple(slot["draw_index"] for slot in slots[:20]) == tuple(range(20))
    assert len({slot["agent_id"] for slot in slots[:20]}) < 20
    assert artifact.payload["sampling"] == "with_replacement"
    assert artifact.payload["population_agent_ids"] == agent_ids(20)
    assert artifact.payload["attention_weights"] == (1.0,) * 20
    assert artifact.payload["population_agent_ids_hash"] == artifact.input_hashes["agent_ids"]
    assert len(artifact.rng_provenance) == 1
    assert artifact.rng_provenance[0].namespace == "activation_ledger"
    assert artifact.payload["rng_ledger"]["event_count"] == len(slots)
    ledger = artifact.payload["rng_ledger"]
    validated = schedule_module.validate_event_rng_ledger(
        ledger,
        artifact.rng_provenance[0],
        matched_seed=17,
        namespace="activation",
        artifact_kind="mock_activation_event_choice",
        event_count=60,
        expected_common_coordinates=ledger["common_coordinates"],
    )
    assert validated.provenance_at(59).coordinates["event_ordinal"] == 59
    assert artifact.input_hashes["attention"] == attention.output_hash
    assert sum(artifact.payload["diagnostics"]["activation_counts"].values()) == 60


def test_activation_schedule_is_deterministic_and_fails_on_seed_drift() -> None:
    attention = build_attention_artifact(
        agent_ids=agent_ids(20),
        matched_seed=17,
        family="equal_weight",
        parameters={},
        mock_only=True,
    )
    first = build_activation_schedule(attention, matched_seed=17, sweep_count=3, mock_only=True)

    assert first == build_activation_schedule(
        attention, matched_seed=17, sweep_count=3, mock_only=True
    )
    with pytest.raises(ValueError, match="matched_seed"):
        build_activation_schedule(attention, matched_seed=18, sweep_count=3, mock_only=True)


def test_activation_schedule_enforces_phase4b_capacity_boundaries() -> None:
    attention = build_attention_artifact(
        agent_ids=agent_ids(20),
        matched_seed=17,
        family="equal_weight",
        parameters={},
        mock_only=True,
    )
    with pytest.raises(TypeError, match="sweep_count"):
        build_activation_schedule(attention, matched_seed=17, sweep_count=True, mock_only=True)
    for invalid_sweeps in (0, 51, 10**12):
        with pytest.raises(ValueError, match="sweep_count|capacity"):
            build_activation_schedule(
                attention,
                matched_seed=17,
                sweep_count=invalid_sweeps,
                mock_only=True,
            )

    with pytest.raises(ValueError, match="population|event.*capacity"):
        build_attention_artifact(
            agent_ids=agent_ids(1001),
            matched_seed=17,
            family="equal_weight",
            parameters={},
            mock_only=True,
        )


def test_population_capacity_fails_before_attention_or_expression_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def sampled(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("sampling must not start above the population capacity")

    monkeypatch.setattr(schedule_module, "_sample_true_truncated", sampled)
    with pytest.raises(ValueError, match="population.*capacity"):
        build_attention_artifact(
            agent_ids=agent_ids(1_001),
            matched_seed=17,
            family="positive_truncated_lognormal",
            parameters={
                "log_location": 0.0,
                "log_sigma": 0.7,
                "minimum": 0.1,
                "maximum": 8.0,
            },
            mock_only=True,
        )

    monkeypatch.setattr(random.Random, "random", sampled)
    with pytest.raises(ValueError, match="population.*capacity"):
        build_expression_artifact(
            agent_ids=agent_ids(1_001),
            matched_seed=17,
            structural_lurker_probability=0.2,
            beta_alpha=2.0,
            beta_beta=5.0,
            max_beta_attempts_per_agent=100,
            correlation_mode="independent",
            mock_only=True,
        )


@pytest.mark.parametrize("builder_name", ["attention", "expression"])
def test_oversized_agent_sequence_is_rejected_before_any_element_access(
    builder_name: str,
) -> None:
    common = {
        "agent_ids": OversizedUnmaterializableAgentIds(),
        "matched_seed": 17,
        "mock_only": True,
    }
    with pytest.raises(ValueError, match="population.*capacity"):
        if builder_name == "attention":
            build_attention_artifact(
                **common,
                family="equal_weight",
                parameters={},
            )
        else:
            build_expression_artifact(
                **common,
                structural_lurker_probability=0.2,
                beta_alpha=2.0,
                beta_beta=5.0,
                max_beta_attempts_per_agent=100,
                correlation_mode="independent",
            )


@pytest.mark.parametrize("builder_name", ["attention", "expression"])
def test_agent_sequence_materialization_never_probes_past_validated_length(
    builder_name: str,
) -> None:
    common = {
        "agent_ids": BoundaryProbingAgentIds(),
        "matched_seed": 17,
        "mock_only": True,
    }
    if builder_name == "attention":
        artifact = build_attention_artifact(
            **common,
            family="equal_weight",
            parameters={},
        )
    else:
        artifact = build_expression_artifact(
            **common,
            structural_lurker_probability=1.0,
            beta_alpha=2.0,
            beta_beta=5.0,
            max_beta_attempts_per_agent=1,
            correlation_mode="independent",
        )
    assert len(artifact.payload["agents"]) == 1_000


def test_oversized_attention_fails_before_activation_deterministic_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attention = build_attention_artifact(
        agent_ids=agent_ids(1_000),
        matched_seed=17,
        family="equal_weight",
        parameters={},
        mock_only=True,
    )
    oversized_payload = attention.to_payload()["payload"]
    oversized_payload["agents"].append({"agent_id": "agent-1000", "raw_weight": 1.0, "weight": 1.0})
    oversized_attention = rebuild(attention, oversized_payload)

    def replayed(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("deterministic replay must not start above capacity")

    monkeypatch.setattr(schedule_module, "build_attention_artifact", replayed)
    with pytest.raises(ValueError, match="population.*capacity"):
        build_activation_schedule(
            oversized_attention,
            matched_seed=17,
            sweep_count=1,
            mock_only=True,
        )


def test_publish_preflights_oversized_activation_before_source_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attention, expression, activation, _ = schedule_artifacts(n=20, sweeps=3)
    oversized_payload = activation.to_payload()["payload"]
    oversized_payload["population_size"] = 1_001
    oversized_activation = rebuild(activation, oversized_payload)

    def replayed(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("source replay must not start above capacity")

    monkeypatch.setattr(schedule_module, "_attention_records", replayed)
    with pytest.raises(ValueError, match="population.*capacity"):
        build_publish_schedule(
            attention,
            oversized_activation,
            expression,
            matched_seed=17,
            mock_only=True,
        )


def schedule_artifacts(n: int = 20, seed: int = 17, sweeps: int = 3):
    attention = build_attention_artifact(
        agent_ids=agent_ids(n),
        matched_seed=seed,
        family="equal_weight",
        parameters={},
        mock_only=True,
    )
    expression = build_expression_artifact(
        agent_ids=agent_ids(n),
        matched_seed=seed,
        structural_lurker_probability=0.2,
        beta_alpha=2.0,
        beta_beta=5.0,
        max_beta_attempts_per_agent=100,
        correlation_mode="independent",
        mock_only=True,
    )
    activation = build_activation_schedule(
        attention, matched_seed=seed, sweep_count=sweeps, mock_only=True
    )
    publish = build_publish_schedule(
        attention,
        activation,
        expression,
        matched_seed=seed,
        mock_only=True,
    )
    return attention, expression, activation, publish


def test_publish_schedule_is_pregenerated_bound_and_restores_frozen_schedule() -> None:
    attention, expression, activation, publish = schedule_artifacts()

    transported = json.loads(json.dumps(publish.to_payload()))
    schedule = FrozenSchedule.from_payload(transported["payload"]["frozen_schedule"])
    expression_by_agent = {record["agent_id"]: record for record in expression.payload["agents"]}
    assert schedule.count == 60
    assert schedule.schedule_hash == publish.payload["schedule_hash"]
    assert publish.input_hashes == {
        "attention": attention.output_hash,
        "activation": activation.output_hash,
        "expression": expression.output_hash,
        "agent_ids": attention.input_hashes["agent_ids"],
    }
    assert all(
        not slot.publish_flag
        for slot in schedule.slots
        if expression_by_agent[slot.agent_id]["structural_lurker"]
    )
    assert publish.payload["flags_generated_before_run"] is True
    assert publish.payload["opinion_inputs_read"] == ()
    assert len(publish.rng_provenance) == 1
    assert publish.rng_provenance[0].namespace == "publish_ledger"
    ledger = publish.payload["rng_ledger"]
    assert ledger["event_count"] == schedule.count
    assert ledger["ordinal_start"] == 0
    assert "event_ordinal" not in ledger["common_coordinates"]
    validated = schedule_module.validate_event_rng_ledger(
        ledger,
        publish.rng_provenance[0],
        matched_seed=17,
        namespace="publish",
        artifact_kind="mock_publish_event_flag",
        event_count=schedule.count,
        expected_common_coordinates=ledger["common_coordinates"],
    )
    first = schedule_module.reconstruct_event_rng_provenance(validated, 0)
    last = schedule_module.reconstruct_event_rng_provenance(validated, schedule.count - 1)
    assert first.coordinates["event_ordinal"] == 0
    assert last.coordinates["event_ordinal"] == schedule.count - 1
    assert first.derived_seed != last.derived_seed
    assert publish.payload["per_agent_publish_counts"] == {
        agent_id: sum(slot.publish_flag and slot.agent_id == agent_id for slot in schedule.slots)
        for agent_id in expression_by_agent
    }
    with pytest.raises(TypeError, match="ValidatedEventRNGLedger"):
        schedule_module.reconstruct_event_rng_provenance(ledger, 1)


def test_event_rng_ledger_requires_trusted_validation_then_o1_reconstruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attention, expression, activation, publish = schedule_artifacts()
    raw = publish.to_payload()["payload"]["rng_ledger"]
    trusted_common = dict(raw["common_coordinates"])
    raw["common_coordinates"]["expression_output_hash"] = "f" * 64
    raw["event_key_digest"] = schedule_module._event_rng_key_digest(
        matched_seed=17,
        namespace="publish",
        artifact_kind="mock_publish_event_flag",
        event_count=60,
        common_coordinates=raw["common_coordinates"],
    )
    with pytest.raises(ValueError, match="source|common|ledger.*drift"):
        schedule_module.validate_event_rng_ledger(
            raw,
            publish.rng_provenance[0],
            matched_seed=17,
            namespace="publish",
            artifact_kind="mock_publish_event_flag",
            event_count=60,
            expected_common_coordinates=trusted_common,
        )

    validated = schedule_module.validate_event_rng_ledger(
        publish.payload["rng_ledger"],
        publish.rng_provenance[0],
        matched_seed=17,
        namespace="publish",
        artifact_kind="mock_publish_event_flag",
        event_count=60,
        expected_common_coordinates=trusted_common,
    )
    monkeypatch.setattr(
        schedule_module,
        "_event_rng_key_digest",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("O(E) digest rescan")),
    )
    assert (
        schedule_module.reconstruct_event_rng_provenance(validated, 59).coordinates["event_ordinal"]
        == 59
    )


def test_validated_event_rng_ledger_cannot_be_constructed_by_public_callers() -> None:
    with pytest.raises(TypeError, match="trusted validation"):
        schedule_module.ValidatedEventRNGLedger(
            matched_seed=17,
            namespace="publish",
            artifact_kind="mock_publish_event_flag",
            event_count=1,
            common_coordinates={},
            event_key_digest="0" * 64,
        )


def test_event_rng_ledger_rejects_boolean_and_over_capacity_counts() -> None:
    _, _, _, publish = schedule_artifacts()
    for invalid_count in (True, 50_001):
        raw = publish.to_payload()["payload"]["rng_ledger"]
        raw["event_count"] = invalid_count
        with pytest.raises((TypeError, ValueError), match="event_count|capacity"):
            schedule_module.validate_event_rng_ledger(
                raw,
                publish.rng_provenance[0],
                matched_seed=17,
                namespace="publish",
                artifact_kind="mock_publish_event_flag",
                event_count=invalid_count,
                expected_common_coordinates=raw["common_coordinates"],
            )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("matched_seed",), 17.0),
        (("matched_seed",), True),
        (("event_count",), 3.0),
        (("event_count",), True),
        (("ordinal_start",), 0.0),
        (("ordinal_start",), False),
        (("common_coordinates", "sweep_count"), 3.0),
        (("common_coordinates", "sweep_count"), True),
        (("common_coordinates", "population_size"), 20.0),
        (("common_coordinates", "population_size"), True),
    ],
)
def test_event_rng_ledger_rejects_non_strict_json_integer_types_before_issuing_capability(
    monkeypatch: pytest.MonkeyPatch,
    path: tuple[str, ...],
    value: object,
) -> None:
    expected_common = {"sweep_count": 3, "population_size": 20}
    raw, root, _ = schedule_module._build_event_rng_ledger(
        matched_seed=17,
        namespace="activation",
        artifact_kind="mock_activation_event_choice",
        event_count=3,
        common_coordinates=expected_common,
    )
    target = raw
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    if path[0] == "common_coordinates":
        raw["event_key_digest"] = schedule_module._event_rng_key_digest(
            matched_seed=17,
            namespace="activation",
            artifact_kind="mock_activation_event_choice",
            event_count=3,
            common_coordinates=raw["common_coordinates"],
        )
        root = RNGProvenance.create(
            matched_seed=17,
            namespace="activation_ledger",
            coordinates={
                "artifact_kind": "mock_activation_event_choice_ledger",
                "ledger_version": schedule_module._EVENT_RNG_LEDGER_VERSION,
                "event_namespace": "activation",
                "event_count": 3,
                "common_coordinates_hash": schedule_module.canonical_payload_hash(
                    raw["common_coordinates"]
                ),
                "event_key_digest": raw["event_key_digest"],
            },
        )

    def rebuilt(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("CAPABILITY_REBUILD_BEFORE_RAW_TYPE_CHECK")

    monkeypatch.setattr(schedule_module, "_build_event_rng_ledger", rebuilt)
    with pytest.raises((TypeError, ValueError), match="matched_seed|event_count|ordinal|common"):
        schedule_module.validate_event_rng_ledger(
            raw,
            root,
            matched_seed=17,
            namespace="activation",
            artifact_kind="mock_activation_event_choice",
            event_count=3,
            expected_common_coordinates=expected_common,
        )


@pytest.mark.parametrize("invalid", [math.nan, math.inf, object()])
def test_event_rng_ledger_rejects_non_json_or_nonfinite_common_coordinates(
    invalid: object,
) -> None:
    expected_common = {"sweep_count": 3}
    raw, root, _ = schedule_module._build_event_rng_ledger(
        matched_seed=17,
        namespace="activation",
        artifact_kind="mock_activation_event_choice",
        event_count=3,
        common_coordinates=expected_common,
    )
    raw["common_coordinates"]["sweep_count"] = invalid
    with pytest.raises((TypeError, ValueError)):
        schedule_module.validate_event_rng_ledger(
            raw,
            root,
            matched_seed=17,
            namespace="activation",
            artifact_kind="mock_activation_event_choice",
            event_count=3,
            expected_common_coordinates=expected_common,
        )


def test_publish_requires_expected_attention_artifact_binding() -> None:
    attention, expression, activation, _ = schedule_artifacts()

    rebuilt = build_publish_schedule(
        attention,
        activation,
        expression,
        matched_seed=17,
        mock_only=True,
    )

    assert rebuilt.input_hashes["attention"] == attention.output_hash


def test_matched_seed_reuses_all_four_artifacts_across_exactly_twelve_cells() -> None:
    attention, expression, activation, publish = schedule_artifacts()

    hashes = validate_matched_schedule_reuse(
        cell_artifacts=cell_artifacts(attention, expression, activation, publish),
        expected_matched_seed=17,
    )

    assert hashes == {
        "attention": attention.output_hash,
        "expression": expression.output_hash,
        "activation": activation.output_hash,
        "publish": publish.output_hash,
        "frozen_schedule": publish.payload["schedule_hash"],
    }


@pytest.mark.parametrize(
    ("artifact_name", "path", "value"),
    [
        ("attention", ("agents",), "oversized_records"),
        ("expression", ("agents",), "oversized_records"),
        ("activation", ("population_size",), 1_001),
        ("activation", ("sweep_count",), 51),
        ("activation", ("rng_ledger", "event_count"), 50_001),
        ("activation", ("population_size",), True),
        ("activation", ("sweep_count",), True),
        ("activation", ("rng_ledger", "event_count"), True),
        ("publish", ("frozen_schedule", "population_size"), 1_001),
        ("publish", ("frozen_schedule", "sweep_count"), 51),
        ("publish", ("rng_ledger", "event_count"), 50_001),
        ("publish", ("frozen_schedule", "population_size"), True),
        ("publish", ("frozen_schedule", "sweep_count"), True),
        ("publish", ("rng_ledger", "event_count"), True),
    ],
)
def test_matched_reuse_preflights_every_artifact_capacity_before_replay(
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
    path: tuple[str, ...],
    value: object,
) -> None:
    attention, expression, activation, publish = schedule_artifacts()
    artifacts = {
        "attention": attention,
        "expression": expression,
        "activation": activation,
        "publish": publish,
    }
    payload = artifacts[artifact_name].to_payload()["payload"]
    if value == "oversized_records":
        records = payload[path[0]]
        payload[path[0]] = records + [records[0]] * (1_001 - len(records))
    else:
        target = payload
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = value
    artifacts[artifact_name] = rebuild(artifacts[artifact_name], payload)

    def replayed(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("REPLAY_BEFORE_CAPACITY")

    for name in (
        "_attention_records",
        "_expression_records",
        "_activation_details",
        "build_activation_schedule",
        "build_publish_schedule",
    ):
        monkeypatch.setattr(schedule_module, name, replayed)

    with pytest.raises((TypeError, ValueError), match="population|sweep|event"):
        validate_matched_schedule_reuse(
            cell_artifacts=cell_artifacts(
                artifacts["attention"],
                artifacts["expression"],
                artifacts["activation"],
                artifacts["publish"],
            ),
            expected_matched_seed=17,
        )


@pytest.mark.parametrize(
    ("artifact_name", "path"),
    [
        ("attention", ("agents",)),
        ("expression", ("agents",)),
        ("activation", ("population_size",)),
        ("activation", ("sweep_count",)),
        ("activation", ("slots",)),
        ("activation", ("rng_ledger", "event_count")),
        ("publish", ("frozen_schedule", "population_size")),
        ("publish", ("frozen_schedule", "sweep_count")),
        ("publish", ("frozen_schedule", "slots")),
        ("publish", ("rng_ledger", "event_count")),
    ],
)
def test_matched_reuse_preflight_requires_all_capacity_fields_before_replay(
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
    path: tuple[str, ...],
) -> None:
    attention, expression, activation, publish = schedule_artifacts()
    artifacts = {
        "attention": attention,
        "expression": expression,
        "activation": activation,
        "publish": publish,
    }
    payload = artifacts[artifact_name].to_payload()["payload"]
    target = payload
    for component in path[:-1]:
        target = target[component]
    del target[path[-1]]
    artifacts[artifact_name] = rebuild(artifacts[artifact_name], payload)

    def replayed(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("REPLAY_BEFORE_REQUIRED_CAPACITY_FIELDS")

    for name in (
        "_attention_records",
        "_expression_records",
        "_activation_details",
        "build_activation_schedule",
        "build_publish_schedule",
    ):
        monkeypatch.setattr(schedule_module, name, replayed)

    with pytest.raises(ValueError, match="required|missing|capacity"):
        validate_matched_schedule_reuse(
            cell_artifacts=cell_artifacts(
                artifacts["attention"],
                artifacts["expression"],
                artifacts["activation"],
                artifacts["publish"],
            ),
            expected_matched_seed=17,
        )


def test_matched_reuse_requires_canonical_cells_and_explicit_expected_seed() -> None:
    attention, expression, activation, publish = schedule_artifacts()
    canonical = cell_artifacts(attention, expression, activation, publish)

    hashes = validate_matched_schedule_reuse(
        cell_artifacts=canonical,
        expected_matched_seed=17,
    )
    assert hashes["publish"] == publish.output_hash

    with pytest.raises(ValueError, match="canonical.*cell|12.*cell"):
        validate_matched_schedule_reuse(
            cell_artifacts={str(index): value for index, value in enumerate(canonical.values())},
            expected_matched_seed=17,
        )
    with pytest.raises(ValueError, match="seed"):
        validate_matched_schedule_reuse(
            cell_artifacts=canonical,
            expected_matched_seed=18,
        )
    with pytest.raises(TypeError, match="expected_matched_seed"):
        validate_matched_schedule_reuse(
            cell_artifacts=canonical,
            expected_matched_seed=True,
        )
    with pytest.raises(TypeError):
        validate_matched_schedule_reuse(  # type: ignore[call-arg]
            attention_artifacts=(attention,) * 12,
            expression_artifacts=(expression,) * 12,
            activation_artifacts=(activation,) * 12,
            publish_artifacts=(publish,) * 12,
        )


def test_publish_and_matched_reuse_fail_closed_on_seed_or_hash_drift() -> None:
    attention, expression, activation, publish = schedule_artifacts()
    other_attention, other_expression, other_activation, other_publish = schedule_artifacts(seed=18)

    with pytest.raises(ValueError, match="matched_seed"):
        build_publish_schedule(
            attention, activation, other_expression, matched_seed=17, mock_only=True
        )
    with pytest.raises(ValueError, match="reuse"):
        validate_matched_schedule_reuse(
            cell_artifacts={
                **cell_artifacts(attention, expression, activation, publish),
                paper1_cell_ids()[-1]: (
                    other_attention,
                    other_expression,
                    other_activation,
                    other_publish,
                ),
            },
            expected_matched_seed=17,
        )


def test_phase4b5_builders_are_public_api() -> None:
    import agent_ex

    for name in (
        "build_attention_artifact",
        "build_expression_artifact",
        "build_activation_schedule",
        "build_publish_schedule",
        "validate_matched_schedule_reuse",
    ):
        assert getattr(agent_ex, name) is globals()[name]
    assert agent_ex.reconstruct_event_rng_provenance is reconstruct_event_rng_provenance


@pytest.mark.parametrize(
    ("builder", "kwargs", "error"),
    [
        (
            build_attention_artifact,
            {
                "agent_ids": agent_ids(2),
                "matched_seed": True,
                "family": "equal_weight",
                "parameters": {},
                "mock_only": True,
            },
            TypeError,
        ),
        (
            build_attention_artifact,
            {
                "agent_ids": agent_ids(2),
                "matched_seed": 1,
                "family": "positive_truncated_lognormal",
                "parameters": {
                    "log_location": 0.0,
                    "log_sigma": True,
                    "minimum": 0.1,
                    "maximum": 2.0,
                },
                "mock_only": True,
            },
            TypeError,
        ),
        (
            build_expression_artifact,
            {
                "agent_ids": agent_ids(2),
                "matched_seed": 1,
                "structural_lurker_probability": True,
                "beta_alpha": 2.0,
                "beta_beta": 5.0,
                "max_beta_attempts_per_agent": 100,
                "correlation_mode": "independent",
                "mock_only": True,
            },
            TypeError,
        ),
        (
            build_expression_artifact,
            {
                "agent_ids": agent_ids(2),
                "matched_seed": 1,
                "structural_lurker_probability": 0.2,
                "beta_alpha": 2.0,
                "beta_beta": 5.0,
                "max_beta_attempts_per_agent": 100,
                "correlation_mode": "independent",
                "mock_only": False,
            },
            ValueError,
        ),
    ],
)
def test_phase4b5_parameters_reject_boolean_and_implicit_formal_values(
    builder, kwargs, error
) -> None:
    with pytest.raises(error):
        builder(**kwargs)


def rebuild(
    artifact: ArtifactEnvelope,
    payload: dict[str, object],
    *,
    input_hashes=None,
    rng_provenance=None,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes if input_hashes is None else input_hashes,
        payload=payload,
        rng_provenance=artifact.rng_provenance if rng_provenance is None else rng_provenance,
    )


def test_downstream_builders_reject_forged_activation_and_expression_payloads() -> None:
    attention, expression, activation, _ = schedule_artifacts()
    attention_payload = attention.to_payload()["payload"]
    first_weight = attention_payload["agents"][0]["weight"]
    attention_payload["agents"][0]["weight"] = attention_payload["agents"][1]["weight"]
    attention_payload["agents"][1]["weight"] = first_weight
    attention_payload["agents"][0]["weight"] += 0.1
    attention_payload["agents"][1]["weight"] -= 0.1
    forged_attention = rebuild(attention, attention_payload)
    with pytest.raises(ValueError, match="attention.*drift"):
        build_activation_schedule(forged_attention, matched_seed=17, sweep_count=3, mock_only=True)

    activation_payload = activation.to_payload()["payload"]
    activation_payload["slots"][0]["agent_id"] = "agent-0019"
    forged_activation = rebuild(activation, activation_payload)
    with pytest.raises(ValueError, match="activation.*drift"):
        build_publish_schedule(
            attention, forged_activation, expression, matched_seed=17, mock_only=True
        )

    expression_payload = expression.to_payload()["payload"]
    expression_payload["agents"][0]["structural_lurker"] = 1
    forged_expression = rebuild(expression, expression_payload)
    with pytest.raises(TypeError, match="structural_lurker"):
        build_publish_schedule(
            attention, activation, forged_expression, matched_seed=17, mock_only=True
        )


def test_publish_rejects_hash_consistent_alternate_attention_source_and_rng_provenance() -> None:
    attention, expression, activation, _ = schedule_artifacts()
    alternate_attention = build_attention_artifact(
        agent_ids=agent_ids(20),
        matched_seed=17,
        family="positive_truncated_lognormal",
        parameters={"log_location": 0.0, "log_sigma": 0.7, "minimum": 0.1, "maximum": 8.0},
        mock_only=True,
    )
    alternate_activation = build_activation_schedule(
        alternate_attention, matched_seed=17, sweep_count=3, mock_only=True
    )
    with pytest.raises(ValueError, match="expected attention|source attention"):
        build_publish_schedule(
            attention, alternate_activation, expression, matched_seed=17, mock_only=True
        )

    forged_payload = activation.to_payload()["payload"]
    forged_payload["rng_ledger"]["common_coordinates"]["attention_output_hash"] = "f" * 64
    forged_activation = rebuild(
        activation,
        forged_payload,
    )
    with pytest.raises(ValueError, match="activation.*drift"):
        build_publish_schedule(
            attention, forged_activation, expression, matched_seed=17, mock_only=True
        )


def test_runtime_and_diagnostics_rewrapping_are_rejected() -> None:
    attention, expression, activation, publish = schedule_artifacts()
    activation_payload = activation.to_payload()["payload"]
    activation_payload["runtime_provenance"]["python_version"] = "0.0.0"
    activation_payload["diagnostics"]["zero_activation_count"] = True
    forged_activation = rebuild(activation, activation_payload)
    with pytest.raises(ValueError, match="activation.*drift"):
        build_publish_schedule(
            attention, forged_activation, expression, matched_seed=17, mock_only=True
        )

    publish_payload = publish.to_payload()["payload"]
    publish_payload["runtime_provenance"]["random_implementation"] = "forged"
    forged_publish = rebuild(publish, publish_payload)
    with pytest.raises(ValueError, match="publish.*drift"):
        validate_matched_schedule_reuse(
            cell_artifacts=cell_artifacts(attention, expression, activation, forged_publish),
            expected_matched_seed=17,
        )


def test_matched_reuse_rejects_forged_pregenerated_publish_flag() -> None:
    attention, expression, activation, publish = schedule_artifacts()
    payload = publish.to_payload()["payload"]
    payload["frozen_schedule"]["slots"][0]["publish_flag"] = not payload["frozen_schedule"][
        "slots"
    ][0]["publish_flag"]
    forged = rebuild(publish, payload)

    with pytest.raises(ValueError, match="publish.*drift"):
        validate_matched_schedule_reuse(
            cell_artifacts=cell_artifacts(attention, expression, activation, forged),
            expected_matched_seed=17,
        )

    ledger_payload = publish.to_payload()["payload"]
    ledger_payload["rng_ledger"]["event_key_digest"] = "f" * 64
    forged_ledger = rebuild(publish, ledger_payload)
    with pytest.raises(ValueError, match="publish.*drift"):
        validate_matched_schedule_reuse(
            cell_artifacts=cell_artifacts(attention, expression, activation, forged_ledger),
            expected_matched_seed=17,
        )


def test_formal_scale_mock_schedule_has_fifty_thousand_frozen_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, expression, activation, publish = schedule_artifacts(n=1000, sweeps=50)
    transported = publish.to_payload()["payload"]
    schedule = FrozenSchedule.from_payload(transported["frozen_schedule"])

    assert schedule.count == 50_000
    assert schedule.slots[0].event_ordinal == 0
    assert schedule.slots[-1].event_ordinal == 49_999
    assert activation.payload["metadata"]["research_parameter_status"] == "not_frozen"
    assert expression.payload["metadata"]["mock_only"] is True
    activation_json = json.dumps(activation.to_payload(), separators=(",", ":")).encode("utf-8")
    publish_json = json.dumps(publish.to_payload(), separators=(",", ":")).encode("utf-8")
    assert len(activation_json) <= 5 * 1024 * 1024
    assert len(publish_json) <= 6 * 1024 * 1024
    assert activation.payload["benchmark_resource_gate"] == {
        "scope": "N1000_T50_agent_percent04d_mock_fixture",
        "maximum_envelope_json_bytes": 5 * 1024 * 1024,
        "semantic_role": "engineering_regression_not_input_validity",
    }
    assert publish.payload["benchmark_resource_gate"] == {
        "scope": "N1000_T50_agent_percent04d_mock_fixture",
        "maximum_envelope_json_bytes": 6 * 1024 * 1024,
        "semantic_role": "engineering_regression_not_input_validity",
    }
    assert ArtifactEnvelope.from_payload(json.loads(publish_json)) == publish
    activation_ledger = activation.payload["rng_ledger"]
    validated = schedule_module.validate_event_rng_ledger(
        activation_ledger,
        activation.rng_provenance[0],
        matched_seed=17,
        namespace="activation",
        artifact_kind="mock_activation_event_choice",
        event_count=50_000,
        expected_common_coordinates=dict(activation_ledger["common_coordinates"]),
    )
    monkeypatch.setattr(
        schedule_module,
        "_event_rng_key_digest",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("O(E) digest rescan")),
    )
    assert validated.provenance_at(49_999).coordinates["event_ordinal"] == 49_999
