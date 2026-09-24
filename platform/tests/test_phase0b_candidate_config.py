from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import canonical_payload_hash
from agent_ex.phase0b.candidate_config import Phase0BCandidateConfig
from agent_ex.phase0b.launch_intent import Phase0BLaunchIntent
from agent_ex.phase0b.matrix import build_diagnostic_n20_artifact_family
from agent_ex.topic import TopicPackage


FIXTURES = Path(__file__).parent / "fixtures" / "paper1"


def _artifact(name: str) -> ArtifactEnvelope:
    return ArtifactEnvelope.from_payload(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def _inputs() -> dict[str, object]:
    frame = _artifact("mock_population_frame.artifact.json")
    persona_fixture = _artifact("mock_persona_template.artifact.json")
    persona = ArtifactEnvelope.create(
        artifact_type=persona_fixture.artifact_type,
        schema_version=persona_fixture.schema_version,
        algorithm_id=persona_fixture.algorithm_id,
        algorithm_version=persona_fixture.algorithm_version,
        input_hashes={"fixture": persona_fixture.output_hash},
        payload=persona_fixture.payload,
        rng_provenance=(),
    )
    return {
        "matched_seed": 20260920,
        "population_frame_artifact": frame,
        "population_weights": tuple(frame.payload["weight_profiles"]["20"]),
        "population_constraints": frame.payload["constraints"],
        "population_tolerance": 0,
        "topic_package": TopicPackage.from_payload(
            _artifact("mock_topic_package.artifact.json").to_payload()["payload"]
        ),
        "reason_library_artifact": _artifact("mock_reason_library.artifact.json"),
        "persona_template": persona,
        "stance_orthogonal_fields": ("gender", "urban", "education"),
        "stance_max_category_imbalance": 1.0,
        "ws_k": 4,
        "ws_rewire_probability": 0.05,
        "shadow_max_attempts": 4,
        "shadow_trial_budget_per_edge": 500,
        "structural_null_replicates": 1,
        "attention_family": "equal_weight",
        "attention_parameters": {},
        "structural_lurker_probability": 0.2,
        "expression_beta_alpha": 2.0,
        "expression_beta_beta": 2.0,
        "expression_max_beta_attempts_per_agent": 100,
        "expression_correlation_mode": "independent",
        "sweep_count": 2,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
    }


def _config() -> Phase0BCandidateConfig:
    return Phase0BCandidateConfig.create(**_inputs())


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    payload["record_hash"] = canonical_payload_hash(
        {key: value for key, value in payload.items() if key != "record_hash"}
    )
    return payload


def test_cold_json_roundtrip_reconstructs_exact_family() -> None:
    inputs = _inputs()
    expected = build_diagnostic_n20_artifact_family(**inputs)
    config = Phase0BCandidateConfig.create(**inputs)
    payload = json.loads(json.dumps(config.to_payload()))
    loaded = Phase0BCandidateConfig.from_payload(payload)
    actual = loaded.build_family()

    assert loaded.record_hash == config.record_hash
    assert loaded.to_payload() == config.to_payload()
    assert actual.authorization_artifact_hashes == expected.authorization_artifact_hashes
    assert actual.population_artifact.output_hash == expected.population_artifact.output_hash
    assert (
        actual.initial_reason_artifact.output_hash == expected.initial_reason_artifact.output_hash
    )
    assert actual.schedule.schedule_hash == expected.schedule.schedule_hash
    assert payload["population_frame_artifact"] == inputs["population_frame_artifact"].to_payload()
    assert payload["topic_package"] == inputs["topic_package"].to_payload()


def test_config_rejects_tampering_and_unresolved_inputs() -> None:
    payload = _config().to_payload()
    payload["matched_seed"] += 1
    with pytest.raises(ValueError, match="record_hash"):
        Phase0BCandidateConfig.from_payload(payload)

    payload = _config().to_payload()
    payload["population_frame_artifact"]["payload"]["donors"][0]["gender"] = "tampered"
    with pytest.raises(ValueError, match="output_hash"):
        Phase0BCandidateConfig.from_payload(_rehash(payload))

    payload = _rehash(_config().to_payload())
    payload["attention_parameters"] = {"sigma": "UNRESOLVED[P1_ATTENTION_SIGMA]"}
    with pytest.raises(ValueError, match="UNRESOLVED"):
        Phase0BCandidateConfig.from_payload(_rehash(payload))

    payload = _config().to_payload()
    payload["population_frame_artifact"]["payload"]["donors"][0]["gender"] = "tampered"
    with pytest.raises(ValueError, match="record_hash"):
        Phase0BCandidateConfig.from_payload(payload)


def test_config_rejects_missing_extra_and_wrong_transport_types() -> None:
    payload = _config().to_payload()
    del payload["shadow_max_attempts"]
    with pytest.raises(ValueError, match="exact"):
        Phase0BCandidateConfig.from_payload(payload)
    payload = _config().to_payload()
    payload["unexpected"] = "no"
    with pytest.raises(ValueError, match="exact"):
        Phase0BCandidateConfig.from_payload(payload)
    payload = _config().to_payload()
    payload["population_weights"] = tuple(payload["population_weights"])
    with pytest.raises(TypeError, match="JSON"):
        Phase0BCandidateConfig.from_payload(payload)
    inputs = _inputs()
    del inputs["ws_k"]
    with pytest.raises(TypeError, match="ws_k"):
        Phase0BCandidateConfig.create(**inputs)

    payload = _config().to_payload()
    payload["ws_rewire_probability"] = True
    with pytest.raises(TypeError, match="ws_rewire_probability"):
        Phase0BCandidateConfig.from_payload(_rehash(payload))

    payload = _config().to_payload()
    payload["stance_orthogonal_fields"] = ["gender", 7]
    with pytest.raises(TypeError, match="stance_orthogonal_fields"):
        Phase0BCandidateConfig.from_payload(_rehash(payload))

    payload = _config().to_payload()
    payload["formal_parameter_authority"] = True
    with pytest.raises(ValueError, match="formal parameter authority"):
        Phase0BCandidateConfig.from_payload(_rehash(payload))


def test_config_copies_mutable_inputs() -> None:
    inputs = _inputs()
    weights = list(inputs["population_weights"])
    inputs["population_weights"] = weights
    config = Phase0BCandidateConfig.create(**inputs)
    original_hash = config.record_hash
    weights[0] = weights[0] + 1
    assert config.record_hash == original_hash
    assert config.to_payload()["population_weights"][0] != weights[0]


def test_config_rejects_topic_pointing_to_another_reason_library() -> None:
    inputs = _inputs()
    topic_payload = inputs["topic_package"].to_payload()
    topic_payload["round0_reason_library_artifact_id"] = "artifact-" + "f" * 64
    inputs["topic_package"] = TopicPackage.from_payload(topic_payload)

    with pytest.raises(ValueError, match="round0_reason_library_artifact_id"):
        Phase0BCandidateConfig.create(**inputs)


def _intent(config: Phase0BCandidateConfig) -> Phase0BLaunchIntent:
    return Phase0BLaunchIntent.create(
        source_commit="a" * 40,
        source_bundle_hash="b" * 64,
        candidate_config_hash=config.record_hash,
        artifact_hashes=config.build_family().authorization_artifact_hashes,
        model_repository="Qwen/Qwen3-8B",
        model_revision="c" * 40,
        tokenizer_revision="c" * 40,
        environment_lock_hash="d" * 64,
        service_config_hash="e" * 64,
        preflight_archive_uri="/root/autodl-tmp/phase0b-preflight",
        full_run_archive_uri="/root/autodl-tmp/phase0b-full",
    )


def test_launch_intent_requires_both_config_hash_and_family_hashes() -> None:
    config = _config()
    intent = _intent(config)
    config.verify_intent(intent)

    payload = intent.to_payload()
    payload["candidate_config_hash"] = "f" * 64
    with pytest.raises(ValueError, match="candidate_config_hash"):
        config.verify_intent(Phase0BLaunchIntent.from_payload(_rehash(payload)))

    payload = intent.to_payload()
    payload["artifact_hashes"]["network"] = "f" * 64
    with pytest.raises(ValueError, match="artifact_hashes"):
        config.verify_intent(Phase0BLaunchIntent.from_payload(_rehash(payload)))
