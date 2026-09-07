from __future__ import annotations

from copy import copy
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

import pytest
import yaml

import agent_ex.calibration.offline as offline_module
from agent_ex import (
    load_runnable_probe_specification,
    run_offline_probe,
    scripted_probe_adapter,
)
from agent_ex.calibration.bundle import ProbeBundle, build_probe_bundle
from agent_ex.calibration.contracts import ProbeTopicCandidate
from agent_ex.calibration.specification import ALLOWED_DECISION_IDS, load_probe_specification
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload, reversed_nonsemantic_arrays


DRAFT_PATH = Path(__file__).parents[1] / "configs" / "paper1" / "phase0a-probe.draft.yaml"


def _mock_probe_specification(*, replicates: int = 4, reordered: bool = False):
    payload = probe_spec_payload()
    payload["replicates"] = [
        {"replicate_id": index, "requested_seed": 100 + index} for index in range(replicates)
    ]
    payload["policy_hashes"] = offline_module._offline_policy_hashes()
    if reordered:
        payload = reversed_nonsemantic_arrays(payload)
    return load_probe_specification(payload)


@lru_cache(maxsize=None)
def _report(
    mode: str = "all_pass",
    *,
    replicates: int = 4,
    format_repair: bool = False,
    runtime_failure: bool = False,
    review_complete: bool = True,
):
    return run_offline_probe(
        _mock_probe_specification(replicates=replicates),
        scripted_probe_adapter(
            mode=mode,
            format_repair=format_repair,
            runtime_failure=runtime_failure,
            review_complete=review_complete,
        ),
    )


@lru_cache(maxsize=1)
def _reordered_report():
    return run_offline_probe(_mock_probe_specification(reordered=True), scripted_probe_adapter())


def test_mock_three_topic_four_persona_probe_is_reproducible() -> None:
    specification = _mock_probe_specification()
    first = _report()
    second = _reordered_report()
    assert first.to_payload() == second.to_payload()
    assert {case.candidate_id for case in first.source.cases} == {
        candidate.candidate_id
        for candidate in (
            ProbeTopicCandidate.create(
                construct=raw["construct"],
                fact_card=raw["fact_card"],
                statements=tuple(raw["statements"]),
                stance_labels_1_7=tuple(raw["stance_labels_1_7"]),
            )
            for raw in specification.payload["topic_candidates"]
        )
    }
    assert {
        (
            condition["identity_present"],
            condition["continuity_present"],
        )
        for condition in specification.payload["persona_conditions"]
    } == {
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    }
    assert first.status == "proposal_only"
    assert first.metadata["formal_parameter_authority"] is False


@pytest.mark.parametrize(
    ("mode", "status", "primary", "robustness", "replicates"),
    [
        ("all_pass", "proposal_only", "retirement-delay", "gm-soybean-oil", 4),
        ("partial_pass", "proposal_only", "gm-soybean-oil", None, 4),
        ("no_pass", "no_candidate", None, None, 1),
    ],
)
def test_precommitted_selection_for_all_partial_and_no_topic_passes(
    mode: str,
    status: str,
    primary: str | None,
    robustness: str | None,
    replicates: int,
) -> None:
    report = _report(mode, replicates=replicates)
    assert report.status == status
    assert report.topic_selection.primary == primary
    assert report.topic_selection.robustness == robustness


def test_one_format_repair_is_preserved_in_end_to_end_report() -> None:
    report = _report(format_repair=True)
    chains: dict[str, list[str]] = {}
    for attempt in report.source.projection.attempts:
        chains.setdefault(attempt.probe_case_id, []).append(attempt.request.attempt_kind)
    assert list(chains.values()).count(["semantic", "format_repair"]) == 1
    assert report.status == "proposal_only"


def test_permanent_runtime_failure_suppresses_selection() -> None:
    report = _report(replicates=1, runtime_failure=True)
    assert report.status == "incomplete"
    assert report.completeness.status == "incomplete"
    assert "runtime_failed" in report.source.projection.case_statuses.values()
    assert report.topic_selection.status == "suppressed"
    assert report.freeze_proposal.proposed_values == {}


def test_incomplete_review_suppresses_selection() -> None:
    report = _report(replicates=1, review_complete=False)
    assert report.status == "incomplete"
    assert report.source.semantic_review.status == "review_incomplete"
    assert report.topic_selection.status == "suppressed"


def test_nonsemantic_specification_input_order_does_not_change_projection() -> None:
    normal = _report()
    reordered = _reordered_report()
    assert normal.specification_hash == reordered.specification_hash
    assert normal.case_inventory_hash == reordered.case_inventory_hash
    assert normal.report_projection_hash == reordered.report_projection_hash


def test_end_to_end_bundle_rejects_evidence_tamper() -> None:
    report = _report()
    bundle = build_probe_bundle(
        report,
        manifest_algorithms={"offline_facade": "paper1.calibration.offline.v1"},
        external_archive_locator="file:///phase0a/offline",
    )
    payloads = json.loads(json.dumps(bundle.to_payloads()))
    payloads["raw-responses.json"]["responses"][0]["provider_request_id"] = "tampered"
    payloads["raw-responses.json"]["content_hash"] = canonical_payload_hash(
        {
            key: value
            for key, value in payloads["raw-responses.json"].items()
            if key != "content_hash"
        }
    )
    manifest = payloads["manifest.json"]
    manifest["file_hashes"]["raw-responses.json"] = canonical_payload_hash(
        payloads["raw-responses.json"]
    )
    manifest["manifest_hash"] = canonical_payload_hash(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )
    with pytest.raises(ValueError, match="hash|identity|request|response|reconstruction"):
        ProbeBundle.from_payloads(payloads)


def test_offline_facade_does_not_create_main_experiment_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = []

    def reject(*args, **kwargs):
        forbidden.append((args, kwargs))
        raise AssertionError("main-experiment object construction is forbidden")

    import agent_ex.checkpoint as checkpoint_module
    import agent_ex.domain as domain_module
    import agent_ex.feed as feed_module
    import agent_ex.state as state_module
    import agent_ex.storage as storage_module

    monkeypatch.setattr(checkpoint_module.Checkpoint, "__init__", reject)
    monkeypatch.setattr(domain_module.GenerationEvent, "__init__", reject)
    monkeypatch.setattr(feed_module.FeedCursor, "__init__", reject)
    monkeypatch.setattr(state_module.PrivateState, "__init__", reject)
    monkeypatch.setattr(storage_module.RunStorage, "__init__", reject)
    report = run_offline_probe(
        _mock_probe_specification(replicates=1), scripted_probe_adapter(review_complete=False)
    )
    assert report.status == "incomplete"
    assert forbidden == []


def test_real_draft_is_not_runnable_and_keeps_every_research_value_unresolved() -> None:
    payload = yaml.safe_load(DRAFT_PATH.read_text(encoding="utf-8"))
    assert payload["candidate_order"] == [
        "retirement-delay",
        "gm-soybean-oil",
        "ai-net-employment",
    ]
    expected_ids = set(ALLOWED_DECISION_IDS)
    assert set(payload["decision_ids"]) == expected_ids
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "UNRESOLVED[P1_TOPIC_PRIMARY]" in serialized
    assert "UNRESOLVED[P1_PERSONA_TEMPLATES]" in serialized
    assert "UNRESOLVED[P1_TEMPERATURE]" in serialized
    assert "UNRESOLVED[P1_TOP_P]" in serialized
    assert payload["replicates"][0]["requested_seed"] == "UNRESOLVED[P1_REQUEST_SEED]"
    assert "UNRESOLVED[P1_TIMEOUT_RETRY]" in serialized
    assert "UNRESOLVED[P1_CONTINUITY_MC_SCORING]" in serialized
    with pytest.raises(ValueError, match="UNRESOLVED"):
        load_runnable_probe_specification(payload)


def test_runnable_loader_rejects_nested_unresolved_before_partial_validation() -> None:
    payload = deepcopy(probe_spec_payload())
    payload["topic_candidates"][0]["fact_card"] = {"nested": "UNRESOLVED[P1_TOPIC_PRIMARY]"}
    with pytest.raises(ValueError, match="UNRESOLVED"):
        load_runnable_probe_specification(payload)


def test_public_facade_has_no_network_or_credentials_parameters() -> None:
    import inspect

    assert tuple(inspect.signature(run_offline_probe).parameters) == (
        "specification",
        "adapter",
    )
    source = inspect.getsource(offline_module)
    for forbidden in (
        "requests.",
        "httpx",
        "urllib",
        "api_key",
        "credential",
        "sqlite3",
        "checkpoint",
        "GenerationEvent",
        "FeedCursor",
        "PrivateState",
    ):
        assert forbidden not in source


def test_report_source_rejects_projection_tamper_on_rebuild() -> None:
    report = _report()
    source = report.source
    tampered_projection = copy(source.projection)
    object.__setattr__(tampered_projection, "run_evidence_hash", "0" * 64)
    with pytest.raises(ValueError, match="hash"):
        offline_module._build_report_from_projection(
            specification=source.specification,
            cases=source.cases,
            projection=tampered_projection,
            adapter=scripted_probe_adapter(),
        )
