"""Real tiny Git source checks, synthetic evidence/procfs and mocked health."""

from dataclasses import replace
import hashlib

import pytest

from test_identity_network_source_bundle import bundle, git  # noqa: F401
from test_identity_network_service_live import proc_fixture  # noqa: F401


@pytest.fixture
def joined_evidence(bundle, proc_fixture, tmp_path, monkeypatch):  # noqa: F811
    from agent_ex.identity_network.launch import build_service_launch_intent, StudyApprovalReceipt
    from agent_ex.identity_network.manipulation_authorization import (
        build_manipulation_authorization,
        build_manipulation_preregistration,
    )
    from agent_ex.identity_network.manipulation_sources import build_source_bound_manipulation_pack
    from agent_ex.identity_network.service_bridge import build_service_bridge, build_service_vacancy
    from agent_ex.identity_network.service_inputs import bind_candidate_service
    from test_identity_network_manipulation_authorization import arguments
    from test_identity_network_service_bridge import rehash

    repo, _, delta, _, commit = bundle
    live, _, actual_start, _ = proc_fixture
    monkeypatch.setattr(live, "_utcnow", lambda: "2026-10-01T00:05:00Z")
    host = live.observe_linux_host().payload["host_identity_hash"]
    original = arguments()
    e = original["service_evidence"]
    config = dict(e["intent"].payload["service_config"])
    config.update(
        executable=actual_start["executable"], cmdline_sha256=actual_start["cmdline_sha256"]
    )
    intent = build_service_launch_intent(
        packet=e["packet"],
        source_commit=commit,
        source_bundle_hash=hashlib.sha256(delta).hexdigest(),
        source_bundle_size=len(delta),
        service_config=config,
        archive_root=e["intent"].payload["archive_root"],
    )
    approval = StudyApprovalReceipt.create(
        target_hash=intent.output_hash,
        scope="service_start",
        researcher="Synthetic",
        approved_at="2026-10-01T00:00:00Z",
    )
    start = dict(
        e["new_start"],
        manifest_hash=intent.output_hash,
        **{k: actual_start[k] for k in ("pid", "proc_start_time", "executable", "cmdline_sha256")},
    )
    rehash(start)
    candidate = bind_candidate_service(
        e["packet"], service_start_identity_hash=start["record_hash"]
    )
    e.update(
        intent=intent,
        approval=approval,
        packet=candidate,
        new_start=start,
        current_observation=replace(e["current_observation"], git_commit=commit),
        current_host_identity_hash=host,
        vacancy=build_service_vacancy(
            intent=intent,
            inspection=e["inspection"],
            host_identity_hash=host,
            observed_at="2026-10-01T00:01:00Z",
            loopback_listener_absent=True,
            gpu_compute_process_observation_hash=hashlib.sha256(b"").hexdigest(),
        ),
    )
    pack = build_source_bound_manipulation_pack(
        candidate=candidate,
        selections=tuple(dict(s) for s in original["source_pack"].payload["selections"]),
        stage="pure_label",
        matched_seed=23,
        generation_settings={"temperature": 0, "top_p": 1, "max_tokens": 128},
    )
    p = original["preregistration"].payload
    criteria = build_manipulation_preregistration(
        source_pack=pack,
        candidate=candidate,
        **{
            k: p[k]
            for k in (
                "created_at",
                "sample_definition",
                "analysis_plan",
                "success_rule",
                "no_signal_rule",
            )
        },
    )
    evidence = dict(
        source_pack=pack,
        candidate=candidate,
        preregistration=criteria,
        bridge=build_service_bridge(**e),
        service_evidence=e,
    )
    auth = build_manipulation_authorization(**evidence)
    receipt = StudyApprovalReceipt.create(
        target_hash=auth.output_hash,
        scope="diagnostic_dispatch",
        researcher="Synthetic",
        approved_at="2026-10-01T00:04:00Z",
    )
    bundle_path = tmp_path / "approved.bundle"
    bundle_path.write_bytes(delta)
    return dict(
        auth=auth, receipt=receipt, evidence=evidence, bundle_path=bundle_path, runtime_repo=repo
    )


def test_preflight_composes_real_source_scoped_approval_and_live_health(
    joined_evidence, monkeypatch
):
    from agent_ex.identity_network import preflight, service_health

    monkeypatch.setattr(preflight, "_utcnow", lambda: "2026-10-01T00:05:00Z")
    monkeypatch.setattr(service_health, "_read_health", lambda: b"healthy")
    result = preflight.preflight_manipulation(**joined_evidence)
    assert result.input_hashes["authorization"] == joined_evidence["auth"].output_hash
    assert result.input_hashes["receipt"] == joined_evidence["receipt"].record_hash
    assert result.payload["dispatch_authorized"] is False
    assert result.payload["trial_count"] == 4
    assert "healthy" not in str(result.to_payload())


def test_preflight_refuses_wrong_receipt_and_bundle_before_health(joined_evidence, monkeypatch):
    from agent_ex.identity_network import preflight, service_health
    from agent_ex.identity_network.launch import StudyApprovalReceipt

    monkeypatch.setattr(preflight, "_utcnow", lambda: "2026-10-01T00:05:00Z")

    def forbidden():
        pytest.fail("unapproved or corrupted source must not reach HTTP")

    monkeypatch.setattr(service_health, "_read_health", forbidden)
    wrong = dict(
        joined_evidence,
        receipt=StudyApprovalReceipt.create(
            target_hash="f" * 64,
            scope="diagnostic_dispatch",
            researcher="Synthetic",
            approved_at="2026-10-01T00:04:00Z",
        ),
    )
    with pytest.raises(ValueError):
        preflight.preflight_manipulation(**wrong)
    joined_evidence["bundle_path"].write_bytes(b"not the approved bundle")
    with pytest.raises(ValueError):
        preflight.preflight_manipulation(**joined_evidence)


def test_preflight_refuses_runtime_change_during_health(joined_evidence, monkeypatch):
    from agent_ex.identity_network import preflight, service_health

    monkeypatch.setattr(preflight, "_utcnow", lambda: "2026-10-01T00:05:00Z")

    def changed():
        (joined_evidence["runtime_repo"] / "extra.txt").write_text("untracked")
        return b""

    monkeypatch.setattr(service_health, "_read_health", changed)
    with pytest.raises(ValueError, match="clean commit"):
        preflight.preflight_manipulation(**joined_evidence)


@pytest.mark.parametrize("change", ["dirty", "head", "subdirectory", "hidden", "skip"])
def test_runtime_checkout_refuses_non_exact_or_dirty_source(bundle, change):  # noqa: F811
    from agent_ex.identity_network.preflight import observe_runtime_checkout

    repo, _, _, base, commit = bundle
    if change == "dirty":
        (repo / "extra.txt").write_text("untracked")
    elif change == "head":
        git(repo, "checkout", "--detach", base)
    elif change in ("hidden", "skip"):
        git(
            repo,
            "update-index",
            "--assume-unchanged" if change == "hidden" else "--skip-worktree",
            "code.txt",
        )
        (repo / "code.txt").write_text("unreported edit")
    else:
        repo = repo / ".git"
    with pytest.raises(ValueError):
        observe_runtime_checkout(repo, expected_commit=commit)
