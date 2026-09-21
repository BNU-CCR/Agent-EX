from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_ex.calibration.judge_contracts import JudgeExecutionManifest, JudgeRequestRenderer
from agent_ex.calibration.judge_runner import JudgeItemState, JudgeProjection
from agent_ex.calibration.review import SemanticReviewPolicy


pytest_plugins = ("test_calibration_judge_contracts",)


SCRIPT = Path(__file__).parents[1] / "scripts" / "phase0a1-judge-prefix-snapshot.py"
SHA_A = "a" * 64
SHA_B = "b" * 64


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def source_files(
    tmp_path: Path,
    policy: SemanticReviewPolicy,
    renderer: JudgeRequestRenderer,
    valid_lifecycle: dict[str, object],
) -> dict[str, object]:
    manifest = JudgeExecutionManifest.create(**valid_lifecycle)
    states = {
        "blind-item-000": JudgeItemState(
            item_id="blind-item-000",
            item_hash=SHA_A,
            order_index=0,
            status="coded",
            attempt_count=1,
            attempt_ids=("attempt-000",),
            unresolved_intent_hash=None,
            last_reconciliation_hash=SHA_A,
            completed_attempt_hash=SHA_A,
            resolution_hash=SHA_A,
            last_error=None,
        ),
        "blind-item-001": JudgeItemState(
            item_id="blind-item-001",
            item_hash=SHA_B,
            order_index=1,
            status="dispatch_unresolved",
            attempt_count=1,
            attempt_ids=("attempt-001",),
            unresolved_intent_hash=SHA_B,
            last_reconciliation_hash=None,
            completed_attempt_hash=None,
            resolution_hash=None,
            last_error=None,
        ),
    }
    projection = JudgeProjection.create(
        manifest_hash=manifest.record_hash,
        preflight_hash=manifest.preflight_hash,
        service_start_identity_hash=manifest.service_start_identity_hash,
        sequence=5,
        previous_projection_hash=SHA_A,
        item_order=tuple(states),
        item_states=states,
    )
    paths = {
        "projection": tmp_path / "projection.json",
        "manifest": tmp_path / "manifest.json",
        "policy": tmp_path / "policy.json",
        "renderer": tmp_path / "renderer.json",
    }
    _write(paths["projection"], projection.to_payload())
    _write(paths["manifest"], manifest.to_payload())
    _write(paths["policy"], policy.to_payload())
    _write(paths["renderer"], renderer.to_payload())
    return {
        "paths": paths,
        "projection": projection,
        "manifest": manifest,
        "policy": policy,
        "renderer": renderer,
    }


def _command(source: dict[str, object]) -> list[str]:
    paths = source["paths"]
    manifest = source["manifest"]
    policy = source["policy"]
    renderer = source["renderer"]
    return [
        sys.executable,
        str(SCRIPT),
        "--projection",
        str(paths["projection"]),
        "--manifest",
        str(paths["manifest"]),
        "--policy",
        str(paths["policy"]),
        "--renderer",
        str(paths["renderer"]),
        "--approved-manifest-hash",
        manifest.record_hash,
        "--approved-policy-hash",
        policy.record_hash,
        "--approved-renderer-hash",
        renderer.record_hash,
        "--cutoff",
        "1",
        "--captured-at",
        "2026-09-21T08:00:00+08:00",
        "--source-locator",
        "ssh://example.invalid/root/run-store/staging/projections/projection.json",
    ]


def test_snapshot_uses_formal_contracts_and_exports_metadata_only(
    source_files: dict[str, object],
) -> None:
    completed = subprocess.run(_command(source_files), check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)

    assert payload["labels"] == {
        "calibration_only": True,
        "formal_parameter_authority": False,
        "incomplete": True,
        "preliminary": True,
        "research_parameter_status": "not_frozen",
    }
    assert payload["snapshot"]["cutoff"] == 1
    assert payload["snapshot"]["expected_total"] == 797
    assert payload["snapshot"]["status_counts"] == {
        "coded": 1,
        "dispatch_unresolved": 1,
    }
    assert (
        payload["analysis_method"]["script_sha256"]
        == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    )
    encoded = json.dumps(payload, sort_keys=True)
    for forbidden in ("dimensions", "labels_count", "raw_bytes", "response", "prompt"):
        assert forbidden not in encoded


def test_snapshot_rejects_tampered_policy_hash(source_files: dict[str, object]) -> None:
    completed = subprocess.run(
        [
            value if value != source_files["policy"].record_hash else SHA_A
            for value in _command(source_files)
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "approved policy hash" in completed.stderr


def test_snapshot_rejects_duplicate_item_ids(source_files: dict[str, object]) -> None:
    path = source_files["paths"]["projection"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["item_order"] = ["blind-item-000", "blind-item-000"]
    _write(path, payload)

    completed = subprocess.run(_command(source_files), capture_output=True, text=True)
    assert completed.returncode != 0
    assert "unique" in completed.stderr


def test_snapshot_rejects_forged_method_hash_argument(
    source_files: dict[str, object],
) -> None:
    completed = subprocess.run(
        [*_command(source_files), "--method-sha256", SHA_A],
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "unrecognized arguments" in completed.stderr


def test_snapshot_rejects_raw_bearing_input(source_files: dict[str, object]) -> None:
    path = source_files["paths"]["projection"]
    payload = deepcopy(json.loads(path.read_text(encoding="utf-8")))
    payload["raw_bytes_base64"] = "forbidden"
    _write(path, payload)

    completed = subprocess.run(_command(source_files), capture_output=True, text=True)
    assert completed.returncode != 0
    assert "raw-bearing" in completed.stderr


@pytest.mark.parametrize(
    ("status", "completed_attempt_hash", "resolution_hash", "expected"),
    [
        ("unknown_terminal", SHA_A, SHA_A, "formal replay state enum"),
        ("coded", None, None, "coded state violates formal replay invariants"),
    ],
)
def test_snapshot_rejects_rehashed_semantically_invalid_state(
    source_files: dict[str, object],
    status: str,
    completed_attempt_hash: str | None,
    resolution_hash: str | None,
    expected: str,
) -> None:
    projection = source_files["projection"]
    original = projection.item_states["blind-item-000"]
    states = dict(projection.item_states)
    states["blind-item-000"] = JudgeItemState(
        item_id=original.item_id,
        item_hash=original.item_hash,
        order_index=original.order_index,
        status=status,
        attempt_count=original.attempt_count,
        attempt_ids=original.attempt_ids,
        unresolved_intent_hash=None,
        last_reconciliation_hash=original.last_reconciliation_hash,
        completed_attempt_hash=completed_attempt_hash,
        resolution_hash=resolution_hash,
        last_error=None,
    )
    malformed = JudgeProjection.create(
        manifest_hash=projection.manifest_hash,
        preflight_hash=projection.preflight_hash,
        service_start_identity_hash=projection.service_start_identity_hash,
        sequence=projection.sequence,
        previous_projection_hash=projection.previous_projection_hash,
        item_order=projection.item_order,
        item_states=states,
    )
    _write(source_files["paths"]["projection"], malformed.to_payload())

    completed = subprocess.run(_command(source_files), capture_output=True, text=True)
    assert completed.returncode != 0
    assert expected in completed.stderr


def test_complete_snapshot_is_not_labelled_incomplete(
    source_files: dict[str, object],
) -> None:
    path = source_files["paths"]["projection"]
    projection = source_files["projection"]
    states = {
        f"blind-item-{index:03d}": JudgeItemState(
            item_id=f"blind-item-{index:03d}",
            item_hash=SHA_A,
            order_index=index,
            status="coded",
            attempt_count=1,
            attempt_ids=(f"attempt-{index:03d}",),
            unresolved_intent_hash=None,
            last_reconciliation_hash=SHA_A,
            completed_attempt_hash=SHA_A,
            resolution_hash=SHA_A,
            last_error=None,
        )
        for index in range(797)
    }
    complete = JudgeProjection.create(
        manifest_hash=projection.manifest_hash,
        preflight_hash=projection.preflight_hash,
        service_start_identity_hash=projection.service_start_identity_hash,
        sequence=3188,
        previous_projection_hash=projection.record_hash,
        item_order=tuple(states),
        item_states=states,
    )
    _write(path, complete.to_payload())
    command = _command(source_files)
    command[command.index("--cutoff") + 1] = "797"

    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    assert json.loads(completed.stdout)["labels"]["incomplete"] is False
