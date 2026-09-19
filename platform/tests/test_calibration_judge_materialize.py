from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from agent_ex.calibration.judge_materialize import (
    JudgeMaterialization,
    materialize_judge_view,
)
from agent_ex.calibration.review import items_for_coder
from agent_ex.domain import canonical_payload_hash
from test_calibration_review import prepared


def canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def rehash(payload: dict[str, object]) -> None:
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )


@pytest.fixture
def review_inputs() -> dict[str, object]:
    bundle = __import__(
        "agent_ex.calibration.review", fromlist=["export_blind_review"]
    ).export_blind_review(*prepared())
    judge = next(contract for contract in bundle.policy.coder_contracts if contract.role == "judge")
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.blind-coder-pack.v1",
        "coder_id": judge.coder_id,
        "coder_role": judge.role,
        "coder_contract_hash": judge.record_hash,
        "policy_id": bundle.policy.policy_id,
        "policy_hash": bundle.policy.record_hash,
        "export_hash": bundle.review_export.export_hash,
        "items": [item.to_payload() for item in items_for_coder(bundle, judge.coder_id)],
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    pack = {**content, "record_hash": canonical_payload_hash(content)}
    index_content: dict[str, object] = {
        "schema_version": "paper1.calibration.blind-coder-pack-index.v1",
        "review_bundle_hash": bundle.record_hash,
        "packs": [
            {
                "coder_id": judge.coder_id,
                "filename": "coder-approved.json",
                "record_hash": pack["record_hash"],
            }
        ],
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    index = {**index_content, "record_hash": canonical_payload_hash(index_content)}
    return {
        "bundle": bundle,
        "pack_bytes": canonical_bytes(pack),
        "index_bytes": canonical_bytes(index),
        "approved_pack_hash": pack["record_hash"],
        "approved_index_hash": index["record_hash"],
    }


def materialize(tmp_path: Path, review_inputs: dict[str, object]) -> JudgeMaterialization:
    return materialize_judge_view(**review_inputs, output_root=tmp_path / "runner")


def mutate_json_bytes(source: bytes, mutation) -> bytes:
    payload = json.loads(source)
    mutation(payload)
    return canonical_bytes(payload)


def test_materializer_emits_byte_equivalent_approved_judge_view(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    result = materialize(tmp_path, review_inputs)
    root = tmp_path / "runner"
    assert result.pack_hash == review_inputs["approved_pack_hash"]
    assert result.index_hash == review_inputs["approved_index_hash"]
    assert result.item_count == len(items_for_coder(review_inputs["bundle"], "coder-b"))
    assert (root / "judge-pack.json").read_bytes() == review_inputs["pack_bytes"]
    assert (root / "index.json").read_bytes() == review_inputs["index_bytes"]
    assert {path.name for path in root.iterdir()} == {
        "judge-pack.json",
        "index.json",
        "materialization.json",
    }


def test_embedded_hashes_exclude_record_hash_field(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    result = materialize(tmp_path, review_inputs)
    pack = json.loads(review_inputs["pack_bytes"])
    assert result.pack_hash == canonical_payload_hash(
        {name: value for name, value in pack.items() if name != "record_hash"}
    )
    assert result.pack_file_sha256 == hashlib.sha256(review_inputs["pack_bytes"]).hexdigest()
    assert result.pack_hash != result.pack_file_sha256


@pytest.mark.parametrize("change", ["reorder", "missing", "extra"])
def test_item_inventory_must_exactly_match_bundle_order(
    tmp_path: Path, review_inputs: dict[str, object], change: str
) -> None:
    def mutate(pack: dict[str, object]) -> None:
        items = pack["items"]
        if change == "reorder":
            items.reverse()
        elif change == "missing":
            items.pop()
        else:
            items.append(deepcopy(items[0]))
        rehash(pack)

    attacked = dict(review_inputs)
    attacked["pack_bytes"] = mutate_json_bytes(review_inputs["pack_bytes"], mutate)
    attacked["approved_pack_hash"] = json.loads(attacked["pack_bytes"])["record_hash"]
    with pytest.raises(ValueError, match="item|order|exact"):
        materialize(tmp_path, attacked)
    assert not (tmp_path / "runner").exists()


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("index", "review_bundle_hash", "f" * 64, "bundle"),
        ("pack", "export_hash", "f" * 64, "export"),
        ("pack", "policy_hash", "f" * 64, "policy"),
        ("pack", "coder_contract_hash", "f" * 64, "coder"),
    ],
)
def test_wrong_bundle_export_policy_or_coder_binding_is_rejected(
    tmp_path: Path,
    review_inputs: dict[str, object],
    target: str,
    field: str,
    value: str,
    message: str,
) -> None:
    attacked = dict(review_inputs)
    key = f"{target}_bytes"

    def mutate(payload: dict[str, object]) -> None:
        payload[field] = value
        rehash(payload)

    attacked[key] = mutate_json_bytes(review_inputs[key], mutate)
    attacked[f"approved_{target}_hash"] = json.loads(attacked[key])["record_hash"]
    with pytest.raises(ValueError, match=message):
        materialize(tmp_path, attacked)


def test_wrong_embedded_or_owner_approved_hash_is_rejected(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    attacked = dict(review_inputs)
    attacked["pack_bytes"] = mutate_json_bytes(
        review_inputs["pack_bytes"], lambda payload: payload.update(record_hash="f" * 64)
    )
    with pytest.raises(ValueError, match="embedded|record hash"):
        materialize(tmp_path, attacked)
    attacked = dict(review_inputs, approved_index_hash="f" * 64)
    with pytest.raises(ValueError, match="approved"):
        materialize(tmp_path, attacked)


def test_human_pack_is_rejected(tmp_path: Path, review_inputs: dict[str, object]) -> None:
    def mutate(pack: dict[str, object]) -> None:
        pack["coder_role"] = "human"
        rehash(pack)

    attacked = dict(review_inputs)
    attacked["pack_bytes"] = mutate_json_bytes(review_inputs["pack_bytes"], mutate)
    attacked["approved_pack_hash"] = json.loads(attacked["pack_bytes"])["record_hash"]
    with pytest.raises(ValueError, match="judge"):
        materialize(tmp_path, attacked)


@pytest.mark.parametrize("extra", ["candidate_id", "condition", "human_audit_selected"])
def test_hidden_or_extra_item_fields_are_rejected(
    tmp_path: Path, review_inputs: dict[str, object], extra: str
) -> None:
    def mutate(pack: dict[str, object]) -> None:
        pack["items"][0][extra] = "secret"
        rehash(pack)

    attacked = dict(review_inputs)
    attacked["pack_bytes"] = mutate_json_bytes(review_inputs["pack_bytes"], mutate)
    attacked["approved_pack_hash"] = json.loads(attacked["pack_bytes"])["record_hash"]
    with pytest.raises(ValueError, match="item|field|contract"):
        materialize(tmp_path, attacked)


def test_visible_payload_requires_exact_four_fields(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    def mutate(pack: dict[str, object]) -> None:
        pack["items"][0]["visible_payload"]["aggregate"] = "secret"
        rehash(pack)

    attacked = dict(review_inputs)
    attacked["pack_bytes"] = mutate_json_bytes(review_inputs["pack_bytes"], mutate)
    attacked["approved_pack_hash"] = json.loads(attacked["pack_bytes"])["record_hash"]
    with pytest.raises(ValueError, match="visible|allowlist|field"):
        materialize(tmp_path, attacked)


def test_noncanonical_and_duplicate_key_json_are_rejected(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    attacked = dict(review_inputs)
    attacked["pack_bytes"] = json.dumps(
        json.loads(review_inputs["pack_bytes"]), ensure_ascii=False, indent=2
    ).encode()
    with pytest.raises(ValueError, match="canonical"):
        materialize(tmp_path, attacked)
    assert not (tmp_path / "runner").exists()

    text = review_inputs["pack_bytes"].decode()
    attacked["pack_bytes"] = text.replace("{", '{"schema_version":"duplicate",', 1).encode()
    with pytest.raises(ValueError, match="duplicate"):
        materialize(tmp_path, attacked)


@pytest.mark.parametrize(
    "filename", ["../outside.json", "nested/outside.json", r"nested\outside.json"]
)
def test_index_filename_cannot_escape_source_directory(
    tmp_path: Path, review_inputs: dict[str, object], filename: str
) -> None:
    attacked = dict(review_inputs)

    def mutate(index: dict[str, object]) -> None:
        index["packs"][0]["filename"] = filename
        rehash(index)

    attacked["index_bytes"] = mutate_json_bytes(review_inputs["index_bytes"], mutate)
    attacked["approved_index_hash"] = json.loads(attacked["index_bytes"])["record_hash"]
    with pytest.raises(ValueError, match="escape|filename"):
        materialize(tmp_path, attacked)


def test_item_record_tamper_is_rejected(tmp_path: Path, review_inputs: dict[str, object]) -> None:
    def mutate(pack: dict[str, object]) -> None:
        pack["items"][0]["record_hash"] = "f" * 64
        rehash(pack)

    attacked = dict(review_inputs)
    attacked["pack_bytes"] = mutate_json_bytes(review_inputs["pack_bytes"], mutate)
    attacked["approved_pack_hash"] = json.loads(attacked["pack_bytes"])["record_hash"]
    with pytest.raises(ValueError, match="item|record hash"):
        materialize(tmp_path, attacked)


def test_existing_or_symlink_output_root_is_rejected(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        materialize_judge_view(**review_inputs, output_root=existing)

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises((FileExistsError, ValueError), match="exist|symlink"):
        materialize_judge_view(**review_inputs, output_root=link)


def test_failed_write_rolls_back_partial_directory(
    tmp_path: Path, review_inputs: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = os.write
    calls = 0

    def fail_second_file(fd: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("synthetic write failure")
        return original(fd, data)

    monkeypatch.setattr(os, "write", fail_second_file)
    with pytest.raises(OSError, match="synthetic"):
        materialize(tmp_path, review_inputs)
    assert not (tmp_path / "runner").exists()


def test_rollback_never_deletes_replaced_output_directory(
    tmp_path: Path,
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "runner"
    moved_root = tmp_path / "moved-root"
    replacement_marker = "replacement-must-survive"
    real_write = __import__(
        "agent_ex.calibration.judge_materialize", fromlist=["_write_bytes_create_only"]
    )._write_bytes_create_only
    calls = 0

    def replace_after_first_write(path: Path, content: bytes) -> None:
        nonlocal calls
        real_write(path, content)
        calls += 1
        if calls == 1:
            output_root.rename(moved_root)
            output_root.mkdir()
            (output_root / "sentinel.txt").write_text(replacement_marker, encoding="utf-8")
        else:
            raise OSError("synthetic write failure after directory replacement")

    monkeypatch.setattr(
        "agent_ex.calibration.judge_materialize._write_bytes_create_only",
        replace_after_first_write,
    )
    with pytest.raises((OSError, ValueError), match="directory replacement|identity"):
        materialize_judge_view(**review_inputs, output_root=output_root)
    assert (moved_root / "judge-pack.json").is_file()
    assert (output_root / "sentinel.txt").read_text(encoding="utf-8") == replacement_marker


def test_materialization_round_trip_hash_and_information_boundary(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    result = materialize(tmp_path, review_inputs)
    payload = json.loads((tmp_path / "runner" / "materialization.json").read_bytes())
    assert JudgeMaterialization.from_payload(payload) == result
    assert result.record_hash == canonical_payload_hash(result.content_payload())
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "hidden_bindings",
        "human_audit_selected",
        "candidate_id",
        "condition",
        "aggregate",
    ):
        assert forbidden not in serialized
    assert payload["metadata"] == {
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
    }


def test_materialization_tamper_breaks_round_trip_hash(
    tmp_path: Path, review_inputs: dict[str, object]
) -> None:
    materialize(tmp_path, review_inputs)
    payload = json.loads((tmp_path / "runner" / "materialization.json").read_bytes())
    payload["item_count"] += 1
    with pytest.raises(ValueError, match="record hash|content"):
        JudgeMaterialization.from_payload(payload)
