"""Synthetic final gate evidence; no human approval or service truth is inferred."""

import pytest

from agent_ex.identity_network.launch import StudyApprovalReceipt
from test_identity_network_service_bridge import fixture


def arguments():
    from agent_ex.identity_network.candidate import validate_six_cell_candidate
    from agent_ex.identity_network.manipulation_sources import build_source_bound_manipulation_pack
    from agent_ex.identity_network.service_bridge import build_service_bridge
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_preregistration,
    )

    evidence = fixture()
    candidate = evidence["packet"]
    agents = validate_six_cell_candidate(candidate)[1].node_agent_ids
    pack = build_source_bound_manipulation_pack(
        candidate=candidate,
        selections=(
            dict(case_id="test-case", receiver_id=agents[0], source_id=agents[1], sampling_seed=71),
        ),
        stage="pure_label",
        matched_seed=23,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
    )
    criteria = build_manipulation_preregistration(
        source_pack=pack,
        candidate=candidate,
        created_at="2026-10-01T00:01:00Z",
        sample_definition="Synthetic fixed single case, one four-trial pairing.",
        analysis_plan="Synthetic paired analysis specification, not an empirical protocol.",
        success_rule="Synthetic success rule for contract test only.",
        no_signal_rule="Synthetic no-signal rule for contract test only.",
    )
    return dict(
        source_pack=pack,
        candidate=candidate,
        preregistration=criteria,
        bridge=build_service_bridge(**evidence),
        service_evidence=evidence,
    )


def test_final_stage_one_gate_replays_sources_rules_bridge_and_scoped_receipt():
    from agent_ex.artifacts import ArtifactEnvelope
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_authorization,
        validate_manipulation_dispatch_approval,
    )

    kwargs = arguments()
    auth = build_manipulation_authorization(**kwargs)
    receipt = StudyApprovalReceipt.create(
        target_hash=auth.output_hash,
        scope="diagnostic_dispatch",
        researcher="Synthetic",
        approved_at="2026-10-01T00:04:00Z",
    )
    validate_manipulation_dispatch_approval(
        ArtifactEnvelope.from_payload(auth.to_payload()),
        receipt,
        checked_at="2026-10-01T00:05:00Z",
        **kwargs,
    )
    assert auth.payload["trial_count"] == 4
    assert auth.payload["dispatch_authorized"] is False
    assert auth.payload["formal_parameter_authority"] is False


@pytest.mark.parametrize(
    "change", ["scope", "target", "before_bridge", "future", "rehash_authorized"]
)
def test_final_gate_rejects_wrong_approval_scope_identity_and_time(change):
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_authorization,
        validate_manipulation_dispatch_approval,
    )
    from test_identity_network_materialization import rebuild

    kwargs = arguments()
    auth = build_manipulation_authorization(**kwargs)
    receipt = StudyApprovalReceipt.create(
        target_hash="a" * 64 if change == "target" else auth.output_hash,
        scope="service_start" if change == "scope" else "diagnostic_dispatch",
        researcher="Synthetic",
        approved_at="2026-10-01T00:02:00Z" if change == "before_bridge" else "2026-10-01T00:04:00Z",
    )
    if change == "rehash_authorized":
        p = auth.to_payload()["payload"]
        p["dispatch_authorized"] = True
        auth = rebuild(auth, p)
    with pytest.raises(ValueError):
        validate_manipulation_dispatch_approval(
            auth,
            receipt,
            checked_at="2026-10-01T00:03:30Z" if change == "future" else "2026-10-01T00:05:00Z",
            **kwargs,
        )


def test_criteria_unresolved_or_trial_inventory_drift_cannot_pass_final_gate():
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_authorization,
        build_manipulation_preregistration,
    )
    from test_identity_network_materialization import rebuild

    kwargs = arguments()
    p = kwargs["preregistration"].to_payload()["payload"]
    with pytest.raises(ValueError):
        build_manipulation_preregistration(
            source_pack=kwargs["source_pack"],
            candidate=kwargs["candidate"],
            created_at=p["created_at"],
            sample_definition=p["sample_definition"],
            analysis_plan=p["analysis_plan"],
            success_rule="UNRESOLVED[SIS_MC_CRITERIA]",
            no_signal_rule=p["no_signal_rule"],
        )
    p["trial_count"] = 8
    kwargs["preregistration"] = rebuild(kwargs["preregistration"], p)
    with pytest.raises(ValueError):
        build_manipulation_authorization(**kwargs)


def test_bridge_must_replay_full_current_evidence_not_just_have_valid_hashes():
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_authorization,
    )

    kwargs = arguments()
    kwargs["service_evidence"]["current_host_identity_hash"] = "e" * 64
    with pytest.raises(ValueError):
        build_manipulation_authorization(**kwargs)


def test_stage_two_receipt_shape_is_not_sufficient_to_authorize_dispatch():
    from agent_ex.identity_network.manipulation import StageTwoReceipt
    from agent_ex.identity_network.manipulation_sources import build_source_bound_manipulation_pack
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_authorization,
    )

    kwargs = arguments()
    kwargs["source_pack"] = build_source_bound_manipulation_pack(
        candidate=kwargs["candidate"],
        selections=tuple(dict(s) for s in kwargs["source_pack"].payload["selections"]),
        stage="shared_group_framing",
        matched_seed=23,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
        stage_two_receipt=StageTwoReceipt("a" * 64, "b" * 64, "no_signal", "Synthetic"),
    )
    with pytest.raises(ValueError, match="completed stage-one"):
        build_manipulation_authorization(**kwargs)
