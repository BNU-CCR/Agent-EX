"""Synthetic source inputs only; materialization must never perform HTTP."""

import hashlib
import json

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import _json_ready, canonical_payload_hash
from agent_ex.identity_network.launch import StudyApprovalReceipt
from test_identity_network_manipulation_authorization import arguments
from test_identity_network_materialization import rebuild


@pytest.fixture(scope="module")
def bound():
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_authorization,
    )

    evidence = arguments()
    auth = build_manipulation_authorization(**evidence)
    receipt = StudyApprovalReceipt.create(
        target_hash=auth.output_hash,
        scope="diagnostic_dispatch",
        researcher="Synthetic",
        approved_at="2026-10-01T00:04:00Z",
    )
    return dict(auth=auth, receipt=receipt, evidence=evidence, checked_at="2026-10-01T00:05:00Z")


def test_request_inventory_preserves_frozen_trials_and_exact_wire(bound):
    from agent_ex.identity_network.manipulation_requests import build_manipulation_request_plan

    plan = build_manipulation_request_plan(**bound)
    pack = bound["evidence"]["source_pack"].payload["pack"]["payload"]
    entries = plan.payload["entries"]
    assert len(entries) == bound["auth"].payload["trial_count"] == 4
    assert tuple(e["trial_id"] for e in entries) == tuple(t["trial_id"] for t in pack["trials"])
    assert len({e["request"]["request_id"] for e in entries}) == 4
    for entry, trial in zip(entries, pack["trials"], strict=True):
        request, wire = entry["request"], entry["wire_payload"]
        assert request["rendered_messages"] == trial["messages"]
        assert request["model_seed"] == trial["sampling_seed"]
        assert request["prompt_hash"] == trial["prompt_hash"]
        assert dict(request["generation_settings"]) == dict(pack["generation_settings"])
        assert wire["messages"] == trial["messages"]
        assert wire["seed"] == trial["sampling_seed"]
        assert wire["model"] == bound["auth"].payload["served_model_name"]
        assert wire["chat_template_kwargs"] == {"enable_thinking": False}
        body = json.dumps(
            _json_ready(entry["wire_payload"]),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        assert entry["wire_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert plan.payload["dispatch_authorized"] is False
    assert plan.payload["formal_parameter_authority"] is False
    assert plan.payload["cloud_launch_eligible"] is False
    assert plan.payload["inventory_contract"] == "quartet-v1-local-contract-only"


def test_cold_json_replay_returns_immutable_reusable_transport_requests(bound):
    from agent_ex.identity_network.manipulation_requests import (
        build_manipulation_request_plan,
        validate_manipulation_request_plan,
    )

    plan = build_manipulation_request_plan(**bound)
    cold = ArtifactEnvelope.from_payload(json.loads(json.dumps(plan.to_payload())))
    requests = validate_manipulation_request_plan(cold, checked_at=bound["checked_at"])
    assert isinstance(requests, tuple)
    assert len(requests) == 4
    assert tuple(r.request_id for r in requests) == tuple(
        e["request"]["request_id"] for e in plan.payload["entries"]
    )
    with pytest.raises(TypeError):
        requests[0].generation_settings["temperature"] = 42


def test_fully_rehashed_inventory_substitutions_fail_cold_derivation(bound):
    from agent_ex.phase0b.vllm_event_adapter import Phase0BVllmEventRequest
    from agent_ex.identity_network.manipulation_requests import (
        build_manipulation_request_plan,
        validate_manipulation_request_plan,
    )

    plan = build_manipulation_request_plan(**bound)
    for change in ("seed", "messages", "order", "model", "timeout", "authority"):
        payload = plan.to_payload()["payload"]
        if change == "seed":
            values = payload["entries"][0]["request"]
            new = Phase0BVllmEventRequest.create(
                **{
                    k: values[k]
                    for k in (
                        "event_id",
                        "attempt_index",
                        "prompt_hash",
                        "generation_settings",
                        "adapter_binding_hash",
                    )
                },
                rendered_messages=tuple(values["rendered_messages"]),
                model_seed=values["model_seed"] + 1,
            )
            payload["entries"][0]["request"] = new.to_payload()
            payload["entries"][0]["wire_payload"]["seed"] = new.model_seed
        elif change == "messages":
            payload["entries"][0]["wire_payload"]["messages"][1]["content"] = "substituted"
        elif change == "order":
            payload["entries"].reverse()
        elif change == "model":
            payload["entries"][0]["wire_payload"]["model"] = "foreign-model"
        elif change == "timeout":
            payload["attempt_policy"]["total_timeout_seconds"] += 1
            policy = payload["attempt_policy"]
            policy["record_hash"] = canonical_payload_hash(
                {k: v for k, v in policy.items() if k != "record_hash"}
            )
        else:
            payload["dispatch_authorized"] = True
        wire = payload["entries"][0]["wire_payload"]
        payload["entries"][0]["wire_sha256"] = hashlib.sha256(
            json.dumps(wire, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        with pytest.raises(ValueError):
            validate_manipulation_request_plan(
                rebuild(plan, payload), checked_at=bound["checked_at"]
            )
