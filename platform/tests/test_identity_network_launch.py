"""SIS service-start approval is source-bound and never dispatch approval."""

from copy import deepcopy
import hashlib

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from test_identity_network_initialization import candidate
from test_phase0b_service_bridge import _fixture


def kwargs():
    bundle = b"synthetic-source-bundle-for-contract-test"
    return dict(
        packet=candidate(),
        source_commit="c" * 40,
        source_bundle_hash=hashlib.sha256(bundle).hexdigest(),
        source_bundle_size=len(bundle),
        service_config=_fixture()["service_config"],
        archive_root="/root/autodl-tmp/sis-check-test",
    )


def rebuild(artifact, payload):
    return ArtifactEnvelope.create(
        artifact_type=artifact.artifact_type,
        schema_version=artifact.schema_version,
        algorithm_id=artifact.algorithm_id,
        algorithm_version=artifact.algorithm_version,
        input_hashes=artifact.input_hashes,
        rng_provenance=artifact.rng_provenance,
        payload=payload,
    )


def receipt(intent, scope="service_start"):
    from agent_ex.identity_network.launch import StudyApprovalReceipt

    return StudyApprovalReceipt.create(
        target_hash=intent.output_hash,
        scope=scope,
        researcher="Synthetic researcher test",
        approved_at="2026-10-01T00:00:00Z",
    )


def test_service_intent_cold_replay_and_human_receipt_bind_exact_source_bytes():
    from agent_ex.identity_network.launch import (
        build_service_launch_intent,
        validate_service_launch_intent,
        validate_service_start_approval,
        StudyApprovalReceipt,
    )

    values = kwargs()
    intent = build_service_launch_intent(**values)
    cold = ArtifactEnvelope.from_payload(intent.to_payload())
    validate_service_launch_intent(cold, values["packet"])
    approval = StudyApprovalReceipt.from_payload(receipt(intent).to_payload())
    validate_service_start_approval(
        intent,
        approval,
        packet=values["packet"],
        actual_source_commit=values["source_commit"],
        bundle_bytes=b"synthetic-source-bundle-for-contract-test",
    )
    assert intent.payload["dispatch_authorized"] is False
    assert intent.payload["formal_parameter_authority"] is False
    assert "service_start_identity_hash" not in intent.payload
    assert approval.scope == "service_start"


def test_start_only_intent_remains_valid_after_mechanical_actual_identity_binding():
    from agent_ex.identity_network.launch import (
        build_service_launch_intent,
        validate_service_launch_intent,
    )
    from agent_ex.identity_network.service_inputs import bind_candidate_service

    values = kwargs()
    intent = build_service_launch_intent(**values)
    rebound = bind_candidate_service(values["packet"], service_start_identity_hash="f" * 64)
    validate_service_launch_intent(intent, rebound)


@pytest.mark.parametrize("change", ("bundle", "size", "commit", "scope", "target"))
def test_service_approval_rejects_wrong_source_or_receipt(change):
    from agent_ex.identity_network.launch import (
        build_service_launch_intent,
        validate_service_start_approval,
        StudyApprovalReceipt,
    )

    values = kwargs()
    intent = build_service_launch_intent(**values)
    approval = receipt(intent)
    commit = values["source_commit"]
    bundle = b"synthetic-source-bundle-for-contract-test"
    if change == "bundle":
        bundle = bytes([bundle[0] ^ 1]) + bundle[1:]
    elif change == "size":
        bundle += b"more"
    elif change == "commit":
        commit = "e" * 40
    elif change == "scope":
        approval = receipt(intent, "diagnostic_dispatch")
    else:
        approval = StudyApprovalReceipt.create(
            target_hash="e" * 64,
            scope="service_start",
            researcher="Synthetic",
            approved_at="2026-10-01T00:00:00Z",
        )
    with pytest.raises((ValueError, TypeError)):
        validate_service_start_approval(
            intent,
            approval,
            packet=values["packet"],
            actual_source_commit=commit,
            bundle_bytes=bundle,
        )


@pytest.mark.parametrize("change", ("git", "size", "archive", "config", "unresolved"))
def test_service_intent_requires_explicit_bounded_resolved_inputs(change):
    from agent_ex.identity_network.launch import build_service_launch_intent

    values = kwargs()
    if change == "git":
        values["source_commit"] = "bad"
    elif change == "size":
        values["source_bundle_size"] = True
    elif change == "archive":
        values["archive_root"] = "/root/autodl-tmp"
    elif change == "config":
        values["service_config"]["unexpected"] = "extra"
    else:
        values["service_config"]["model_path"] = "UNRESOLVED[SIS_MODEL_PATH]"
    with pytest.raises((ValueError, TypeError)):
        build_service_launch_intent(**values)


def test_rehashed_intent_cannot_escalate_to_dispatch_or_change_fixed_sources():
    from agent_ex.identity_network.launch import (
        build_service_launch_intent,
        validate_service_launch_intent,
    )

    values = kwargs()
    original = build_service_launch_intent(**values)
    for field, value in (("dispatch_authorized", True), ("fixed_inputs_hash", "e" * 64)):
        payload = deepcopy(original.to_payload()["payload"])
        payload[field] = value
        with pytest.raises(ValueError):
            validate_service_launch_intent(rebuild(original, payload), values["packet"])


@pytest.mark.parametrize(
    "field,value", (("researcher", ""), ("approved_at", "bad"), ("scope", "formal_run"))
)
def test_receipt_requires_attribution_time_and_supported_scope(field, value):
    from agent_ex.identity_network.launch import StudyApprovalReceipt

    args = dict(
        target_hash="a" * 64,
        scope="service_start",
        researcher="Synthetic",
        approved_at="2026-10-01T00:00:00Z",
    )
    args[field] = value
    with pytest.raises((ValueError, TypeError)):
        StudyApprovalReceipt.create(**args)
