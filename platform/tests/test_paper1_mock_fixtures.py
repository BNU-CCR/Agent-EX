from collections import Counter
import json
from pathlib import Path

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.initialization import assign_initial_reasons, assign_initial_stances
from agent_ex.persona import render_persona, validate_persona_factor_diff
from agent_ex.population import build_population_artifact
from agent_ex.topic import TopicPackage


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper1"


def load_artifact(name: str) -> ArtifactEnvelope:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    return ArtifactEnvelope.from_payload(payload)


def test_all_paper1_fixture_files_are_explicit_mock_artifact_envelopes() -> None:
    fixture_paths = tuple(sorted(FIXTURE_DIR.glob("*.artifact.json")))

    assert {path.name for path in fixture_paths} == {
        "mock_persona_template.artifact.json",
        "mock_population_frame.artifact.json",
        "mock_reason_library.artifact.json",
        "mock_scale_cases.artifact.json",
        "mock_topic_package.artifact.json",
    }
    for path in fixture_paths:
        assert "mock" in path.name
        artifact = ArtifactEnvelope.from_payload(json.loads(path.read_text(encoding="utf-8")))
        assert artifact.payload["metadata"] == {
            "mock_only": True,
            "research_parameter_status": "not_frozen",
        }
        assert ArtifactEnvelope.from_payload(artifact.to_payload()) == artifact


def test_topic_fixture_is_a_strict_topic_package_bound_to_reason_library() -> None:
    topic_artifact = load_artifact("mock_topic_package.artifact.json")
    reason_artifact = load_artifact("mock_reason_library.artifact.json")
    package = TopicPackage.from_payload(topic_artifact.to_payload()["payload"])

    assert package.round0_reason_library_artifact_id == reason_artifact.artifact_id


def test_scale_fixtures_build_exact_population_and_initialization_artifacts() -> None:
    frame = load_artifact("mock_population_frame.artifact.json")
    cases = load_artifact("mock_scale_cases.artifact.json")
    frame_payload = frame.to_payload()["payload"]
    reasons = load_artifact("mock_reason_library.artifact.json")

    for case in cases.payload["cases"]:
        n = case["n"]
        population = build_population_artifact(
            donors=tuple(frame_payload["donors"]),
            weights=tuple(frame_payload["weight_profiles"][str(n)]),
            n=n,
            matched_seed=101,
            input_artifact_hash=frame.output_hash,
            constraints=frame_payload["constraints"],
            tolerance=0,
            mock_only=True,
        )
        initialized = assign_initial_stances(
            population_artifact=population,
            matched_seed=101,
            orthogonal_fields=("gender", "urban", "education"),
            max_category_imbalance=1.0,
            mock_only=True,
        )
        round0 = assign_initial_reasons(
            stance_artifact=initialized,
            reason_library_artifact=reasons,
            matched_seed=101,
            mock_only=True,
        )

        counts = Counter(item["stance"] for item in initialized.payload["assignments"])
        assert len(population.payload["members"]) == n
        assert [counts[stance] for stance in range(1, 8)] == list(case["stance_counts"])
        assert len({record["reason_id"] for record in round0.payload["round0_records"]}) == n


def test_persona_fixture_renders_all_four_factor_conditions() -> None:
    frame = load_artifact("mock_population_frame.artifact.json")
    template = load_artifact("mock_persona_template.artifact.json")
    member = {
        "agent_id": "agent-0000",
        "donor_id": frame.payload["donors"][0]["donor_id"],
        "fields": frame.payload["donors"][0]["fields"],
    }
    rendered = tuple(
        render_persona(
            template,
            member,
            {"identity_present": identity, "continuity_present": continuity},
        )
        for identity in (False, True)
        for continuity in (False, True)
    )

    assert validate_persona_factor_diff(rendered)["valid"] is True
