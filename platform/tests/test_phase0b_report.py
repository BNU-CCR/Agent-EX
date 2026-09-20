from __future__ import annotations

import json

from agent_ex.mock_matrix import CANONICAL_CELL_IDS
from agent_ex.phase0b.report import build_phase0b_preliminary_report
from test_phase0b_run import (
    FakePhase0BAdapter,
    _authorization,
    _binding,
    _candidate,
    _policy,
)
from agent_ex.phase0b.run import run_fake_diagnostic_matrix


def test_preliminary_report_summarizes_complete_matrix_without_raw_content(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    run_root = tmp_path / "run"
    run_fake_diagnostic_matrix(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        adapter=FakePhase0BAdapter(),
        run_root=run_root,
    )

    report = build_phase0b_preliminary_report(
        run_root=run_root,
        authorization=authorization,
        matrix_candidate=candidate,
    )

    assert report["calibration_only"] is True
    assert report["formal_parameter_authority"] is False
    assert report["research_parameter_status"] == "not_frozen"
    assert report["terminal_status"] == "complete"
    assert report["committed_event_count"] == 480
    assert report["transport_count"] == 480
    assert report["parse_failure_count"] == 0
    assert report["provider_failure_count"] == 0
    assert set(report["per_cell_committed_counts"]) == set(CANONICAL_CELL_IDS)
    assert all(value == 40 for value in report["per_cell_committed_counts"].values())

    serialized = json.dumps(report, sort_keys=True)
    assert "raw_body" not in serialized
    assert "rendered_messages" not in serialized
    assert "public_reason" not in serialized


def test_preliminary_report_refuses_incomplete_or_tampered_run(tmp_path) -> None:
    candidate = _candidate()
    binding = _binding()
    policy = _policy()
    authorization = _authorization(candidate, binding, policy)
    run_root = tmp_path / "run"
    run_fake_diagnostic_matrix(
        authorization=authorization,
        matrix_candidate=candidate,
        adapter_binding=binding,
        attempt_policy=policy,
        adapter=FakePhase0BAdapter(),
        run_root=run_root,
    )
    attempts_path = run_root / "staging" / "attempts.jsonl"
    attempts = attempts_path.read_text(encoding="utf-8").splitlines()
    attempts_path.write_text("\n".join(attempts[:-1]) + "\n", encoding="utf-8")

    try:
        build_phase0b_preliminary_report(
            run_root=run_root,
            authorization=authorization,
            matrix_candidate=candidate,
        )
    except ValueError as error:
        assert "480" in str(error) or "40 attempts per cell" in str(error)
    else:
        raise AssertionError("tampered diagnostic run should not produce a report")
