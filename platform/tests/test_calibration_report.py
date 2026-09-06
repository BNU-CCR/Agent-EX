from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path

import pytest

from agent_ex.calibration.adapters import ProbeAdapter, ProbeScriptStep, ScriptedProbeAdapter
from agent_ex.calibration.bundle import (
    PROBE_BUNDLE_FILES,
    build_probe_bundle,
    load_probe_bundle,
    write_probe_bundle_atomic,
)
from agent_ex.calibration.contracts import ProbeResponse
from agent_ex.calibration.gates import evaluate_quality_gates, select_topic
from agent_ex.calibration.report import (
    FORBIDDEN_REPORT_KEYS,
    FreezeProposal,
    ProposalArtifact,
    build_freeze_proposal,
    build_probe_report,
    compute_run_evidence_hash,
)
from agent_ex.calibration.review import (
    export_blind_review,
    import_review_codes,
    to_semantic_gate_evidence,
)
from agent_ex.calibration.runner import execute_probe_run
from agent_ex.calibration.specification import (
    ALLOWED_DECISION_IDS,
    expand_probe_cases,
    load_probe_specification,
)
from agent_ex.domain import canonical_payload_hash
from helpers.calibration import probe_spec_payload
from test_calibration_gates import algorithm, required_challenges
from test_calibration_review import complete_codes, review_policy
from test_calibration_runner import (
    CHAT_TEMPLATE_HASH,
    GENERATION_SETTINGS,
    MODEL_IDENTITY,
    RUNTIME_IDENTITY,
    TOKENIZER_IDENTITY,
    policy as runtime_policy,
)


def _raw(case, stance: int) -> str:
    values = {"stance": stance, "confidence": 3, "public_reason": "Synthetic reason."}
    names = (
        ("stance", "confidence", "public_reason")
        if case.field_order_id == "stance-confidence-reason"
        else ("public_reason", "confidence", "stance")
    )
    return json.dumps({name: values[name] for name in names}, separators=(",", ":"))


@lru_cache(maxsize=1)
def complete_inputs():
    gate_algorithm = algorithm(required_challenges())
    semantic_policy = replace(
        review_policy(),
        classifier_id=gate_algorithm.classifier_id,
        classifier_version=gate_algorithm.classifier_version,
        classifier_hash=gate_algorithm.classifier_hash,
    )
    runtime = runtime_policy()
    payload = probe_spec_payload()
    payload["replicates"] = [
        {"replicate_id": index, "requested_seed": 100 + index} for index in range(4)
    ]
    payload["policy_hashes"] = {
        "gate_algorithm": gate_algorithm.record_hash,
        "semantic_review_policy": semantic_policy.record_hash,
        "runtime_policy": runtime.record_hash,
    }
    specification = load_probe_specification(payload)
    cases = expand_probe_cases(specification)
    steps = {
        (case.probe_case_id, 1): ProbeScriptStep(
            "response", _raw(case, 2 + case.replicate_id % 4), None, None
        )
        for case in cases
    }
    projection = execute_probe_run(
        run_instance_id="phase0a-report-test",
        specification_hash=specification.output_hash,
        cases=cases,
        runtime_policy=runtime,
        adapter=ScriptedProbeAdapter(steps),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    parses = tuple(
        attempt.parse_evidence for attempt in projection.attempts if attempt.parse_evidence
    )
    pending = export_blind_review(specification, cases, projection, semantic_policy)
    codes = list(complete_codes(pending))
    review = import_review_codes(pending, tuple(codes))
    bridge = to_semantic_gate_evidence(review, specification, cases, projection, parses)
    reports = tuple(
        evaluate_quality_gates(
            specification,
            cases,
            projection,
            gate_algorithm,
            bridge,
            candidate_key=key,
        )
        for key in ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
    )
    selection = select_topic(reports)
    artifact = ProposalArtifact(
        decision_id="P1_TOPIC_PRIMARY",
        artifact_id="phase0a-gate-report",
        artifact_hash=reports[0].record_hash,
        evidence_uri="s3://example-bucket/phase0a/report.json",
    )
    report = build_probe_report(
        specification=specification,
        cases=cases,
        projection=projection,
        parse_evidence=parses,
        semantic_review=review,
        semantic_gate_evidence=bridge,
        gate_algorithm=gate_algorithm,
        gate_reports=reports,
        topic_selection=selection,
        proposed_values={"P1_TOPIC_PRIMARY": selection.primary},
        proposal_artifacts=(artifact,),
        unresolved_decision_ids=tuple(sorted(set(payload["decision_ids"]) - {"P1_TOPIC_PRIMARY"})),
    )
    return report


@lru_cache(maxsize=1)
def complete_bundle():
    return build_probe_bundle(
        complete_inputs(),
        manifest_algorithms={
            "report_builder": "paper1.calibration.report.v1",
            "bundle_writer": "paper1.calibration.bundle.v1",
        },
        external_archive_locator="s3://example-bucket/phase0a/phase0a-report-test",
    )


def test_freeze_proposal_has_no_decision_authority() -> None:
    report = complete_inputs()
    proposal = report.freeze_proposal
    assert proposal.metadata == {
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
    }
    assert proposal.status == "proposal_only"
    assert "decision_record_id" not in json.dumps(proposal.to_payload())
    rebuilt = build_freeze_proposal(
        completeness=report.completeness,
        specification_hash=report.specification_hash,
        case_inventory_hash=report.case_inventory_hash,
        run_evidence_hash=report.run_evidence_hash,
        gate_report=report.gate_report,
        topic_selection=report.topic_selection,
        proposed_values=report.source.proposed_values,
        proposal_artifacts=report.source.proposal_artifacts,
        unresolved_decision_ids=report.source.unresolved_decision_ids,
        registered_decision_ids=tuple(report.source.specification.payload["decision_ids"]),
    )
    assert rebuilt == proposal


def test_report_hash_layers_are_order_invariant_and_distinct() -> None:
    report = complete_inputs()
    source = report.source
    reordered = build_probe_report(
        specification=source.specification,
        cases=tuple(reversed(source.cases)),
        projection=source.projection,
        parse_evidence=tuple(reversed(source.parse_evidence)),
        semantic_review=source.semantic_review,
        semantic_gate_evidence=tuple(reversed(source.semantic_gate_evidence)),
        gate_algorithm=source.gate_algorithm,
        gate_reports=tuple(reversed(source.gate_reports)),
        topic_selection=source.topic_selection,
        proposed_values=dict(source.proposed_values),
        proposal_artifacts=tuple(reversed(source.proposal_artifacts)),
        unresolved_decision_ids=tuple(reversed(source.unresolved_decision_ids)),
    )
    assert reordered.to_payload() == report.to_payload()
    assert (
        len(
            {
                report.specification_hash,
                report.case_inventory_hash,
                report.report_projection_hash,
                report.run_evidence_hash,
            }
        )
        == 4
    )


def test_review_score_change_changes_projection_and_full_run_evidence_hash() -> None:
    report = complete_inputs()
    projection = report.to_payload()
    projection = {
        key: projection[key]
        for key in (
            "completeness",
            "gate_report",
            "gate_reports",
            "topic_selection",
            "freeze_proposal",
        )
    }
    changed_projection = json.loads(json.dumps(projection))
    changed_projection["gate_reports"][0]["metrics"][0]["distribution"]["4"] += 1
    assert canonical_payload_hash(projection) == report.report_projection_hash
    assert canonical_payload_hash(changed_projection) != report.report_projection_hash
    review_payload = report.source.semantic_review.to_payload()
    changed_review = json.loads(json.dumps(review_payload))
    changed_review["independent_codes"][0]["raw_evidence_hash"] = "0" * 64
    assert canonical_payload_hash(review_payload) != canonical_payload_hash(changed_review)


class _ChangedResponseAdapter(ProbeAdapter):
    def __init__(self, field: str, value: str):
        self.field = field
        self.value = value

    def generate(self, request):
        base = ScriptedProbeAdapter(
            {
                (request.probe_case_id, request.attempt_index): ProbeScriptStep(
                    "response", _raw_for_request(request), None, None
                )
            }
        ).generate(request)
        payload = base.to_payload()
        payload[self.field] = self.value
        if self.field == "raw_response":
            payload["raw_response_hash"] = canonical_payload_hash(self.value)
        identity = {
            key: value
            for key, value in payload.items()
            if key not in {"response_id", "record_hash"}
        }
        payload["response_id"] = "probe-response-" + canonical_payload_hash(identity)
        payload["record_hash"] = canonical_payload_hash(
            {**identity, "response_id": payload["response_id"]}
        )
        return ProbeResponse.from_payload(payload)


def _raw_for_request(request) -> str:
    values = {"stance": 4, "confidence": 3, "public_reason": "Synthetic reason."}
    names = (
        ("stance", "confidence", "public_reason")
        if request.field_order_id == "stance-confidence-reason"
        else ("public_reason", "confidence", "stance")
    )
    return json.dumps({name: values[name] for name in names}, separators=(",", ":"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_request_id", "provider-changed"),
        ("started_at", "1969-12-31T23:59:59Z"),
        ("ended_at", "1970-01-01T00:00:01Z"),
        ("raw_response", '{"stance":5,"confidence":3,"public_reason":"Changed."}'),
    ],
)
def test_response_provider_or_time_change_changes_full_run_hash(field: str, value: str) -> None:
    report = complete_inputs()
    source = report.source
    case = source.cases[0]
    common = dict(
        run_instance_id="hash-layer-test",
        specification_hash=source.specification.output_hash,
        cases=(case,),
        runtime_policy=source.projection.runtime_policy,
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    baseline = execute_probe_run(
        **common,
        adapter=_ChangedResponseAdapter("provider_request_id", "provider-baseline"),
    )
    changed = execute_probe_run(**common, adapter=_ChangedResponseAdapter(field, value))
    assert compute_run_evidence_hash(baseline, None) != compute_run_evidence_hash(changed, None)


@pytest.mark.parametrize("field", sorted(FORBIDDEN_REPORT_KEYS))
def test_report_recursively_rejects_forbidden_proposal_fields(field: str) -> None:
    report = complete_inputs()
    source = report.source
    with pytest.raises(ValueError, match="forbidden"):
        build_probe_report(
            specification=source.specification,
            cases=source.cases,
            projection=source.projection,
            parse_evidence=source.parse_evidence,
            semantic_review=source.semantic_review,
            semantic_gate_evidence=source.semantic_gate_evidence,
            gate_algorithm=source.gate_algorithm,
            gate_reports=source.gate_reports,
            topic_selection=source.topic_selection,
            proposed_values={"P1_TOPIC_PRIMARY": {"nested": {field: 1}}},
            proposal_artifacts=source.proposal_artifacts,
            unresolved_decision_ids=source.unresolved_decision_ids,
        )


def test_missing_evidence_is_incomplete_and_suppresses_selection() -> None:
    report = complete_inputs()
    source = report.source
    with pytest.raises(ValueError, match="parse evidence|complete"):
        build_probe_report(
            specification=source.specification,
            cases=source.cases,
            projection=source.projection,
            parse_evidence=source.parse_evidence[:-1],
            semantic_review=source.semantic_review,
            semantic_gate_evidence=source.semantic_gate_evidence,
            gate_algorithm=source.gate_algorithm,
            gate_reports=source.gate_reports,
            topic_selection=source.topic_selection,
            proposed_values=dict(source.proposed_values),
            proposal_artifacts=source.proposal_artifacts,
            unresolved_decision_ids=source.unresolved_decision_ids,
        )


def test_proposal_requires_exact_registered_decision_and_artifact_coverage() -> None:
    report = complete_inputs()
    source = report.source
    assert set(source.proposed_values) | set(source.unresolved_decision_ids) <= ALLOWED_DECISION_IDS
    with pytest.raises(ValueError, match="decision|artifact"):
        build_probe_report(
            specification=source.specification,
            cases=source.cases,
            projection=source.projection,
            parse_evidence=source.parse_evidence,
            semantic_review=source.semantic_review,
            semantic_gate_evidence=source.semantic_gate_evidence,
            gate_algorithm=source.gate_algorithm,
            gate_reports=source.gate_reports,
            topic_selection=source.topic_selection,
            proposed_values={"P1_UNKNOWN": "x"},
            proposal_artifacts=source.proposal_artifacts,
            unresolved_decision_ids=source.unresolved_decision_ids,
        )


@pytest.mark.parametrize("duplicate", ["artifact_id", "artifact_hash"])
def test_freeze_proposal_rejects_duplicate_artifact_ids_or_hashes(duplicate: str) -> None:
    first = ProposalArtifact(
        "P1_TOPIC_PRIMARY",
        "artifact-one",
        canonical_payload_hash("artifact-one"),
        "s3://example-bucket/one",
    )
    second = ProposalArtifact(
        "P1_STANCE_SCALE",
        "artifact-one" if duplicate == "artifact_id" else "artifact-two",
        first.artifact_hash
        if duplicate == "artifact_hash"
        else canonical_payload_hash("artifact-two"),
        "s3://example-bucket/two",
    )
    with pytest.raises(ValueError, match="duplicate|unique"):
        FreezeProposal.create(
            status="proposal_only",
            specification_hash=canonical_payload_hash("spec"),
            case_inventory_hash=canonical_payload_hash("cases"),
            run_evidence_hash=canonical_payload_hash("run"),
            gate_report_hash=canonical_payload_hash("gates"),
            selection_hash=canonical_payload_hash("selection"),
            proposed_values=dict(sorted({"P1_TOPIC_PRIMARY": "a", "P1_STANCE_SCALE": "b"}.items())),
            supporting_artifacts=tuple(
                sorted((first, second), key=lambda item: (item.decision_id, item.artifact_id))
            ),
            unresolved_decision_ids=(),
        )


def test_audit_import_changes_full_run_evidence_hash() -> None:
    report = complete_inputs()
    source = report.source
    cases = source.cases[:3]
    steps = {
        (case.probe_case_id, 1): ProbeScriptStep("response", _raw(case, 4), None, None)
        for case in cases
    }
    projection = execute_probe_run(
        run_instance_id="audit-hash-test",
        specification_hash=source.specification.output_hash,
        cases=cases,
        runtime_policy=source.projection.runtime_policy,
        adapter=ScriptedProbeAdapter(steps),
        generation_settings=GENERATION_SETTINGS,
        runtime_identity=RUNTIME_IDENTITY,
        model_identity=MODEL_IDENTITY,
        tokenizer_identity=TOKENIZER_IDENTITY,
        chat_template_hash=CHAT_TEMPLATE_HASH,
    )
    pending = export_blind_review(
        source.specification, cases, projection, source.semantic_review.policy
    )
    imported = import_review_codes(pending, complete_codes(pending))
    assert compute_run_evidence_hash(projection, pending) != compute_run_evidence_hash(
        projection, imported
    )


def test_manifest_free_form_recursively_rejects_forbidden_keys() -> None:
    report = complete_inputs()
    with pytest.raises(ValueError, match="forbidden"):
        build_probe_bundle(
            report,
            manifest_algorithms={"p_value": "1.0.0"},
            external_archive_locator="s3://example-bucket/phase0a/test",
        )


def test_bundle_write_load_exact_atomic_and_non_overwriting(tmp_path: Path) -> None:
    bundle = complete_bundle()
    target = tmp_path / "probe-run-1"
    write_probe_bundle_atomic(target, bundle)
    assert {path.name for path in target.iterdir()} == set(PROBE_BUNDLE_FILES)
    restored = load_probe_bundle(target)
    assert restored.to_payloads() == bundle.to_payloads()
    with pytest.raises(FileExistsError):
        write_probe_bundle_atomic(target, bundle)


@pytest.mark.parametrize("mutation", ["missing", "extra", "tampered", "swapped", "manifest"])
def test_bundle_load_rejects_inventory_hash_and_cross_file_drift(
    tmp_path: Path, mutation: str
) -> None:
    bundle = complete_bundle()
    target = tmp_path / "probe-run"
    write_probe_bundle_atomic(target, bundle)
    if mutation == "missing":
        (target / "parse-evidence.json").unlink()
    elif mutation == "extra":
        (target / "extra.json").write_text("{}", encoding="utf-8")
    elif mutation == "tampered":
        (target / "parse-evidence.json").write_text("[]", encoding="utf-8")
    elif mutation == "swapped":
        left = (target / "requests.json").read_text(encoding="utf-8")
        right = (target / "raw-responses.json").read_text(encoding="utf-8")
        (target / "requests.json").write_text(right, encoding="utf-8")
        (target / "raw-responses.json").write_text(left, encoding="utf-8")
    else:
        payload = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        payload["run_evidence_hash"] = "0" * 64
        (target / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValueError, TypeError), match="inventory|hash|payload|file|complete"):
        load_probe_bundle(target)


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"value":NaN}', '{"value":Infinity}'])
def test_bundle_load_rejects_duplicate_keys_and_nonfinite_json(tmp_path: Path, text: str) -> None:
    bundle = complete_bundle()
    target = tmp_path / "probe-run"
    write_probe_bundle_atomic(target, bundle)
    (target / "manifest.json").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate|constant|JSON|payload|file"):
        load_probe_bundle(target)


def test_partial_collision_and_injected_failure_leave_no_owned_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = complete_bundle()
    target = tmp_path / "probe-run"
    partial = tmp_path / "probe-run.partial"
    partial.mkdir()
    with pytest.raises(FileExistsError):
        write_probe_bundle_atomic(target, bundle)
    assert partial.is_dir() and not target.exists()
    partial.rmdir()

    import agent_ex.calibration.bundle as bundle_module

    original = bundle_module._write_json_file
    calls = 0

    def fail_after_one(path, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected write failure")
        return original(path, payload)

    monkeypatch.setattr(bundle_module, "_write_json_file", fail_after_one)
    with pytest.raises(OSError, match="injected"):
        write_probe_bundle_atomic(target, bundle)
    assert not target.exists() and not partial.exists()


def test_bundle_write_does_not_touch_authority_files(tmp_path: Path) -> None:
    bundle = complete_bundle()
    root = Path(__file__).parents[2]
    protected = (
        root / "docs" / "decisions.md",
        root / "docs" / "paper1-protocol.md",
        root / "platform" / "configs" / "paper1" / "paper1-formal.yaml",
    )
    before = {path: path.read_bytes() for path in protected if path.exists()}
    write_probe_bundle_atomic(tmp_path / "only-explicit-target", bundle)
    assert {path: path.read_bytes() for path in before} == before
