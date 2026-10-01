from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from agent_ex.domain import canonical_payload_hash


SCRIPT = Path(__file__).parents[1] / "scripts" / "phase0a1-safe-label-export.py"
MODULE = Path(__file__).parents[1] / "src" / "agent_ex" / "calibration" / "safe_label_export.py"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
RECEIPT_SCHEMA = "paper1.calibration.judge-safe-label-export-approval-receipt.v1"
OUTPUT_SCHEMA = "paper1.calibration.judge-safe-label-export.v2"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_content() -> dict[str, object]:
    return {
        "schema_version": RECEIPT_SCHEMA,
        "packet_path": "controls/export-packet.json",
        "approved_packet_hash": SHA_A,
        "production_authorization_hash": SHA_B,
        "combined_packet_hash": SHA_C,
        "reviewed_module_sha256": _hash(MODULE),
        "reviewed_script_sha256": _hash(SCRIPT),
        "blind_pack_hash": "1" * 64,
        "blind_index_hash": "2" * 64,
        "approved_order_hash": "3" * 64,
        "policy_hash": "4" * 64,
        "vocabulary_hash": "5" * 64,
        "dimension_count": 2,
        "label_counts": [2, 3],
        "preliminary": True,
        "incomplete": True,
        "not_frozen": True,
        "formal_parameter_authority": False,
    }


def _receipt() -> dict[str, object]:
    content = _receipt_content()
    return {**content, "record_hash": canonical_payload_hash(content)}


def _output() -> dict[str, object]:
    content = {
        "schema_version": OUTPUT_SCHEMA,
        "status": {
            "preliminary": True,
            "incomplete": True,
            "not_frozen": True,
            "formal_parameter_authority": False,
        },
        "source": {
            "approval_receipt_hash": SHA_A,
            "production_authorization_hash": SHA_B,
            "combined_packet_hash": SHA_C,
            "manifest_hash": "6" * 64,
            "projection_hash": "7" * 64,
            "blind_pack_hash": "1" * 64,
            "blind_index_hash": "2" * 64,
            "approved_order_hash": "3" * 64,
            "policy_hash": "4" * 64,
            "renderer_hash": "8" * 64,
        },
        "snapshot": {"cutoff": 1, "expected_total": 797},
        "analysis": {
            "module_sha256": _hash(MODULE),
            "script_sha256": _hash(SCRIPT),
        },
        "vocabulary": {
            "vocabulary_hash": "5" * 64,
            "dimension_count": 2,
            "label_counts": [2, 3],
        },
        "items": [
            {
                "ordinal": 0,
                "item_hash": "9" * 64,
                "completed_attempt_hash": "a" * 64,
                "resolution_hash": "b" * 64,
                "parse_record_hash": "c" * 64,
                "source_output_sha256": "d" * 64,
                "label_ordinals": [1, 2],
            }
        ],
        "aggregate_counts": [[0, 1], [0, 0, 1]],
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def test_receipt_is_an_independent_owner_approval_trust_root() -> None:
    from agent_ex.calibration.safe_label_export import validate_approval_receipt_payload

    receipt = _receipt()
    validate_approval_receipt_payload(receipt, approved_receipt_hash=receipt["record_hash"])
    attacked = deepcopy(receipt)
    attacked["approved_packet_hash"] = "f" * 64
    attacked_content = {k: v for k, v in attacked.items() if k != "record_hash"}
    attacked["record_hash"] = canonical_payload_hash(attacked_content)
    with pytest.raises(ValueError, match="approved receipt hash"):
        validate_approval_receipt_payload(attacked, approved_receipt_hash=receipt["record_hash"])


@pytest.mark.parametrize(
    "field",
    [
        "approved_packet_hash",
        "production_authorization_hash",
        "combined_packet_hash",
        "reviewed_module_sha256",
        "reviewed_script_sha256",
        "blind_pack_hash",
        "blind_index_hash",
        "approved_order_hash",
        "policy_hash",
        "vocabulary_hash",
    ],
)
def test_receipt_requires_every_trust_binding(field: str) -> None:
    from agent_ex.calibration.safe_label_export import validate_approval_receipt_payload

    receipt = _receipt()
    del receipt[field]
    with pytest.raises(ValueError, match="exact fields"):
        validate_approval_receipt_payload(receipt, approved_receipt_hash=SHA_A)


@pytest.mark.parametrize(
    "packet_path",
    ["../escape.json", "/absolute.json", "controls\\packet.json", "controls/\x00packet.json"],
)
def test_receipt_rejects_path_escape_or_control_characters(packet_path: str) -> None:
    from agent_ex.calibration.safe_label_export import validate_approval_receipt_payload

    content = _receipt_content()
    content["packet_path"] = packet_path
    receipt = {**content, "record_hash": canonical_payload_hash(content)}
    with pytest.raises(ValueError, match="packet path"):
        validate_approval_receipt_payload(receipt, approved_receipt_hash=receipt["record_hash"])


@pytest.mark.parametrize(
    ("dimension_count", "label_counts"),
    [(0, []), (17, [2] * 17), (2, [1, 2]), (2, [2, 17]), (2, [2]), (True, [2])],
)
def test_receipt_enforces_strict_vocabulary_shape_limits(
    dimension_count: object, label_counts: object
) -> None:
    from agent_ex.calibration.safe_label_export import validate_approval_receipt_payload

    content = _receipt_content()
    content["dimension_count"] = dimension_count
    content["label_counts"] = label_counts
    receipt = {**content, "record_hash": canonical_payload_hash(content)}
    with pytest.raises(ValueError, match="vocabulary shape"):
        validate_approval_receipt_payload(receipt, approved_receipt_hash=receipt["record_hash"])


def test_output_contains_only_hashes_booleans_integers_and_ordinal_arrays() -> None:
    from agent_ex.calibration.safe_label_export import validate_safe_label_export_payload

    payload = _output()
    validate_safe_label_export_payload(payload)
    encoded = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "source_locator",
        "item_id",
        '"labels"',
        "dimension_labels",
        "prompt",
        "response",
        "reason",
        "captured_at",
        "method_id",
    ):
        assert forbidden not in encoded


def test_output_validator_recomputes_ordinal_aggregate_counts() -> None:
    from agent_ex.calibration.safe_label_export import validate_safe_label_export_payload

    payload = _output()
    payload["aggregate_counts"][0] = [1, 0]
    content = {k: v for k, v in payload.items() if k != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    with pytest.raises(ValueError, match="aggregate counts"):
        validate_safe_label_export_payload(payload)


@pytest.mark.parametrize(
    "label_ordinals",
    [[1], [1, 3], [True, 1], [0, -1]],
)
def test_output_rejects_invalid_label_ordinals(label_ordinals: list[object]) -> None:
    from agent_ex.calibration.safe_label_export import validate_safe_label_export_payload

    payload = _output()
    payload["items"][0]["label_ordinals"] = label_ordinals
    content = {k: v for k, v in payload.items() if k != "record_hash"}
    payload["record_hash"] = canonical_payload_hash(content)
    with pytest.raises(ValueError, match="label ordinal"):
        validate_safe_label_export_payload(payload)


def test_output_is_always_preliminary_incomplete_and_not_frozen() -> None:
    from agent_ex.calibration.safe_label_export import validate_safe_label_export_payload

    for field, bad in (
        ("preliminary", False),
        ("incomplete", False),
        ("not_frozen", False),
        ("formal_parameter_authority", True),
    ):
        payload = _output()
        payload["status"][field] = bad
        content = {k: v for k, v in payload.items() if k != "record_hash"}
        payload["record_hash"] = canonical_payload_hash(content)
        with pytest.raises(ValueError, match="status"):
            validate_safe_label_export_payload(payload)


def test_cli_has_fixed_failure_surface_and_never_echoes_inputs(tmp_path: Path) -> None:
    secret = "DO_NOT_ECHO_SECRET_PATH"
    command = [
        sys.executable,
        str(SCRIPT),
        "--run-root",
        str(tmp_path / secret),
        "--approval-receipt",
        str(tmp_path / secret / "receipt.json"),
        "--approved-receipt-hash",
        SHA_A,
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "SAFE_LABEL_EXPORT_FAILED:E001\n"
    assert secret not in completed.stderr


def test_cli_does_not_accept_packet_or_packet_hash_arguments() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--approval-packet",
            "packet.json",
            "--approved-packet-hash",
            SHA_A,
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert completed.stderr == "SAFE_LABEL_EXPORT_FAILED:E001\n"


def test_formal_exporter_fails_closed_off_linux_posix(tmp_path: Path) -> None:
    if os.name == "posix" and sys.platform.startswith("linux"):
        pytest.skip("non-Linux rejection is not applicable")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-root",
            str(tmp_path.resolve()),
            "--approval-receipt",
            str((tmp_path / f"{SHA_A}.json").resolve()),
            "--approved-receipt-hash",
            SHA_A,
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert completed.stderr == "SAFE_LABEL_EXPORT_FAILED:E001\n"


def test_build_api_does_not_allow_approval_root_injection() -> None:
    from agent_ex.calibration.safe_label_export import build_safe_label_export

    assert "approval_root" not in inspect.signature(build_safe_label_export).parameters


def test_reviewed_source_hashes_use_the_real_module_and_platform_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_ex.calibration import safe_label_export

    receipt = _receipt()
    observed: list[Path] = []

    def secure_read(path: Path) -> bytes:
        observed.append(path)
        return open(path, "rb").read()

    monkeypatch.setattr(safe_label_export, "_read_absolute_regular_file", secure_read)
    safe_label_export.verify_reviewed_exporter_sources(receipt)
    assert observed == [MODULE.resolve(), SCRIPT.resolve()]
    receipt["reviewed_module_sha256"] = SHA_A
    with pytest.raises(ValueError, match="reviewed exporter source"):
        safe_label_export.verify_reviewed_exporter_sources(receipt)


def test_build_checks_real_exporter_paths_before_run_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_ex.calibration import safe_label_export

    class ReachedRunEvidence(Exception):
        pass

    receipt = _receipt()
    receipt_path = tmp_path.resolve() / f"{receipt['record_hash']}.json"
    reads = iter((receipt, ReachedRunEvidence()))
    observed: list[Path] = []

    def read_json(*args: object, **kwargs: object) -> dict[str, object]:
        value = next(reads)
        if isinstance(value, Exception):
            raise value
        return value

    def secure_read(path: Path) -> bytes:
        observed.append(path)
        with open(path, "rb") as source:
            return source.read()

    monkeypatch.setattr(safe_label_export, "APPROVAL_ROOT", tmp_path.resolve())
    monkeypatch.setattr(safe_label_export, "_require_linux_backend", lambda: None)
    monkeypatch.setattr(
        safe_label_export,
        "_open_absolute_directory",
        lambda path: os.open(os.devnull, os.O_RDONLY),
    )
    monkeypatch.setattr(safe_label_export, "_read_json", read_json)
    monkeypatch.setattr(safe_label_export, "_read_absolute_regular_file", secure_read)
    with pytest.raises(ReachedRunEvidence):
        safe_label_export.build_safe_label_export(
            run_root=tmp_path.resolve(),
            approval_receipt_path=receipt_path,
            approved_receipt_hash=receipt["record_hash"],
        )
    assert observed == [MODULE.resolve(), SCRIPT.resolve()]


def test_build_rejects_unreviewed_real_exporter_before_run_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_ex.calibration import safe_label_export

    receipt = _receipt()
    receipt["reviewed_script_sha256"] = SHA_A
    content = {key: value for key, value in receipt.items() if key != "record_hash"}
    receipt["record_hash"] = canonical_payload_hash(content)
    receipt_path = tmp_path.resolve() / f"{receipt['record_hash']}.json"
    monkeypatch.setattr(safe_label_export, "APPROVAL_ROOT", tmp_path.resolve())
    monkeypatch.setattr(safe_label_export, "_require_linux_backend", lambda: None)
    monkeypatch.setattr(
        safe_label_export,
        "_open_absolute_directory",
        lambda path: os.open(os.devnull, os.O_RDONLY),
    )
    monkeypatch.setattr(safe_label_export, "_read_json", lambda *args, **kwargs: receipt)
    monkeypatch.setattr(
        safe_label_export,
        "_read_absolute_regular_file",
        lambda path: open(path, "rb").read(),
    )
    with pytest.raises(ValueError, match="reviewed exporter source"):
        safe_label_export.build_safe_label_export(
            run_root=tmp_path.resolve(),
            approval_receipt_path=receipt_path,
            approved_receipt_hash=receipt["record_hash"],
        )


@pytest.mark.parametrize("suffix", ["../escape", "bad\x00root", "bad\x1froot"])
def test_trusted_absolute_roots_reject_unsafe_components(suffix: str) -> None:
    from agent_ex.calibration.safe_label_export import _validate_trusted_absolute_root

    root = Path("C:/trusted") if os.name == "nt" else Path("/trusted")
    with pytest.raises(ValueError, match="trusted root"):
        _validate_trusted_absolute_root(root / suffix)


def test_secure_source_reader_rejects_symlinks(tmp_path: Path) -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        pytest.skip("secure dirfd source reader is Linux-only")
    from agent_ex.calibration.safe_label_export import _read_absolute_regular_file

    source = tmp_path / "source.py"
    source.write_bytes(b"print('reviewed')\n")
    assert _read_absolute_regular_file(source) == b"print('reviewed')\n"
    link = tmp_path / "link.py"
    link.symlink_to(source)
    with pytest.raises(OSError):
        _read_absolute_regular_file(link)


def test_json_schema_gate_recursively_rejects_raw_markers_in_keys_and_values() -> None:
    from agent_ex.calibration.safe_label_export import validate_nonraw_json_tree

    validate_nonraw_json_tree({"safe": ["value", 1, True, None]})
    for attacked in (
        {"raw_bytes": "x"},
        {"nested": [{"safe": "response_bytes"}]},
        {"nested": {"output_bytes_base64": "x"}},
        {"nested": "contains raw_bytes marker"},
    ):
        with pytest.raises(ValueError, match="raw marker"):
            validate_nonraw_json_tree(attacked)
