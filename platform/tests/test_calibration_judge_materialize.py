from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import errno
from pathlib import Path
import stat

import pytest

from agent_ex.calibration.judge_materialize import (
    EXPECTED_JUDGE_ITEM_COUNT,
    JudgeMaterialization,
    SecureMaterializationUnsupportedError,
    materialize_judge_view,
)
import agent_ex.calibration.review as review_module
from agent_ex.calibration.review import items_for_coder
from agent_ex.domain import canonical_payload_hash
from test_calibration_review import prepared


@pytest.fixture(autouse=True)
def _require_posix_secure_backend(request: pytest.FixtureRequest) -> None:
    allowed = (
        "test_windows_materialization_fails_closed",
        "test_exact797_validator",
        "test_fsync_handle_propagates_oserror",
    )
    if os.name == "nt" and not request.node.name.startswith(allowed):
        pytest.skip("materialization requires the POSIX handle-relative backend")


def test_windows_materialization_fails_closed_before_staging(
    tmp_path: Path, review_inputs: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    monkeypatch.setattr(materializer.os, "name", "nt")
    output_root = tmp_path / "runner"
    with pytest.raises(SecureMaterializationUnsupportedError, match="handle-relative"):
        materialize_judge_view(**review_inputs, output_root=output_root)
    assert not output_root.exists()
    assert not list(tmp_path.glob(".runner.staging-*"))


def test_exact797_validator_and_canonical_pack_contract(
    review_inputs: dict[str, object],
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    pack = materializer._load_canonical_json(review_inputs["pack_bytes"], "judge pack")
    _, _, items = materializer._validate_pack(review_inputs["bundle"], pack)
    assert len(items) == EXPECTED_JUDGE_ITEM_COUNT


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


def _bundle_with_exact_judge_item_count():
    specification, cases, run, policy = prepared()
    bundle = review_module.export_blind_review(specification, cases, run, policy)
    source_binding = bundle.hidden_bindings[0]
    source_case = next(case for case in cases if case.probe_case_id == source_binding.probe_case_id)
    source_parse = next(
        attempt.parse_evidence
        for attempt in run.attempts
        if attempt.parse_evidence is not None
        and attempt.parse_evidence.request_id == source_binding.request_id
    )
    source_item = bundle.review_export.items[0]
    items = []
    bindings = []
    for index in range(EXPECTED_JUDGE_ITEM_COUNT):
        visible = dict(source_item.visible_payload)
        visible["response_text"] = f"{visible['response_text']} item-{index}"
        visible_hash = canonical_payload_hash(visible)
        item_id = review_module._opaque_item_id(
            policy_id=policy.policy_id,
            policy_hash=policy.record_hash,
            randomization_seed=policy.randomization_seed,
            randomization_domain=policy.randomization_domain,
            stratum_id=source_binding.stratum_id,
            probe_case_id=source_binding.probe_case_id,
            probe_case_hash=source_binding.probe_case_hash,
            request_id=source_binding.request_id,
            request_hash=source_binding.request_hash,
            response_id=source_binding.response_id,
            response_hash=source_binding.response_hash,
            raw_response_hash=source_binding.raw_response_hash,
            parse_id=source_binding.parse_id,
            parse_hash=source_binding.parse_hash,
            visible_payload_hash=visible_hash,
        )
        item = review_module.BlindReviewItem.create(
            item_id=item_id,
            policy_hash=policy.record_hash,
            visible_payload=visible,
        )
        binding = review_module.HiddenReviewBinding.create(
            policy,
            item,
            source_binding.stratum_id,
            source_case,
            source_parse,
            human_audit_selected=index < 3,
        )
        items.append(item)
        bindings.append(binding)
    export_values = {
        "policy_id": bundle.review_export.policy_id,
        "policy_version": bundle.review_export.policy_version,
        "policy_hash": bundle.review_export.policy_hash,
        "specification_hash": bundle.review_export.specification_hash,
        "specification_semantic_review_policy_hash": bundle.review_export.specification_semantic_review_policy_hash,
        "run_id": bundle.review_export.run_id,
        "run_evidence_hash": bundle.review_export.run_evidence_hash,
        "items": tuple(items),
    }
    export_content = {
        "schema_version": review_module.BlindReviewExport._SCHEMA,
        **{**export_values, "items": [item.to_payload() for item in items]},
        "metadata": bundle.review_export.metadata,
    }
    export = review_module.BlindReviewExport(
        **export_values,
        export_hash=canonical_payload_hash(export_content),
    )
    return review_module.SemanticReviewBundle(
        policy,
        export,
        tuple(bindings),
        (),
        (),
        None,
        "awaiting_codes",
        (),
    )


def _pack_and_index(bundle):
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
        "pack_bytes": canonical_bytes(pack),
        "index_bytes": canonical_bytes(index),
        "approved_pack_hash": pack["record_hash"],
        "approved_index_hash": index["record_hash"],
    }


@pytest.fixture
def review_inputs() -> dict[str, object]:
    bundle = _bundle_with_exact_judge_item_count()
    return {"bundle": bundle, **_pack_and_index(bundle)}


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


@pytest.mark.parametrize("count", [776, 798])
def test_judge_pack_requires_exact_797_items(
    tmp_path: Path, review_inputs: dict[str, object], count: int
) -> None:
    def mutate(pack: dict[str, object]) -> None:
        if count < EXPECTED_JUDGE_ITEM_COUNT:
            pack["items"] = pack["items"][:count]
        else:
            pack["items"] = pack["items"] + [deepcopy(pack["items"][0])]
        rehash(pack)

    attacked = dict(review_inputs)
    attacked["pack_bytes"] = mutate_json_bytes(review_inputs["pack_bytes"], mutate)
    attacked["approved_pack_hash"] = json.loads(attacked["pack_bytes"])["record_hash"]
    with pytest.raises(ValueError, match="797"):
        materialize(tmp_path, attacked)


def test_self_consistent_small_bundle_is_rejected_by_formal_count(tmp_path: Path) -> None:
    specification, cases, run, policy = prepared()
    bundle = review_module.export_blind_review(specification, cases, run, policy)
    inputs = {"bundle": bundle, **_pack_and_index(bundle)}
    with pytest.raises(ValueError, match="797"):
        materialize_judge_view(**inputs, output_root=tmp_path / "runner")


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
    with pytest.raises(OSError, match="synthetic") as caught:
        materialize(tmp_path, review_inputs)
    assert not (tmp_path / "runner").exists()
    partial = next(tmp_path.glob(".runner.staging-*"))
    assert {path.name for path in partial.iterdir()} == {"judge-pack.json"}
    assert "staging quarantine retained at" in " ".join(caught.value.__notes__)


def test_failed_materialization_retains_staging_quarantine(
    tmp_path: Path,
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    output_root = tmp_path / "runner"
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    sibling_marker = sibling / "must-survive.txt"
    sibling_marker.write_text("sibling-must-survive", encoding="utf-8")
    real_write = materializer._write_bytes_create_only
    replaced = False
    staging_holder: list[Path] = []

    def replace_after_first_write(
        path: Path, content: bytes, staging_fd: int, staging_identity: tuple[int, int]
    ) -> tuple[int, int]:
        nonlocal replaced
        identity = real_write(path, content, staging_fd, staging_identity)
        staging_holder.append(path.parent)
        replaced = True
        return identity

    monkeypatch.setattr(
        "agent_ex.calibration.judge_materialize._write_bytes_create_only",
        replace_after_first_write,
    )

    def fail_after_first_verify(*args, **kwargs):
        raise ValueError("synthetic identity verification failure")

    monkeypatch.setattr(
        "agent_ex.calibration.judge_materialize._verify_staged_files",
        fail_after_first_verify,
    )
    with pytest.raises(ValueError, match="identity"):
        materialize_judge_view(**review_inputs, output_root=output_root)
    assert staging_holder and (staging_holder[0] / "judge-pack.json").is_file()
    assert {path.name for path in staging_holder[0].iterdir()} == {
        "judge-pack.json",
        "index.json",
        "materialization.json",
    }
    assert sibling_marker.read_text(encoding="utf-8") == "sibling-must-survive"


def test_rollback_never_follows_real_replaced_output_directory(
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tempfile
    import agent_ex.calibration.judge_materialize as materializer

    with tempfile.TemporaryDirectory(prefix="agent-ex-judge-rollback-") as temporary_root:
        base = Path(temporary_root)
        output_root = base / "runner"
        moved_original = base / "moved-original"
        target_sibling = base / "target-sibling"
        target_sibling.mkdir()
        target_marker = target_sibling / "must-survive.txt"
        target_marker.write_text("target-sibling-must-survive", encoding="utf-8")
        real_write = materializer._write_bytes_create_only
        calls = 0

        def replace_after_first_write(
            path: Path, content: bytes, staging_fd: int, staging_identity: tuple[int, int]
        ) -> tuple[int, int]:
            nonlocal calls
            identity = real_write(path, content, staging_fd, staging_identity)
            calls += 1
            if calls == 1:
                path.parent.rename(moved_original)
                path.parent.mkdir()
                (path.parent / "replacement-sentinel.txt").write_text(
                    "replacement-must-survive", encoding="utf-8"
                )
            return identity

        monkeypatch.setattr(
            "agent_ex.calibration.judge_materialize._write_bytes_create_only",
            replace_after_first_write,
        )
        with pytest.raises(FileNotFoundError):
            materialize_judge_view(**review_inputs, output_root=output_root)
        assert (moved_original / "judge-pack.json").is_file()
        assert (output_root / "replacement-sentinel.txt").read_text(
            encoding="utf-8"
        ) == "replacement-must-survive"
        assert target_marker.read_text(encoding="utf-8") == "target-sibling-must-survive"


def test_publish_swap_before_return_is_detected_without_cleanup(
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tempfile

    import agent_ex.calibration.judge_materialize as materializer

    with tempfile.TemporaryDirectory(prefix="agent-ex-judge-return-") as temporary_root:
        base = Path(temporary_root)
        output_root = base / "runner"
        moved_original = base / "moved-original"
        real_fsync = materializer._fsync_handle
        swapped = False

        def swap_after_publish(descriptor: int) -> None:
            nonlocal swapped
            real_fsync(descriptor)
            if output_root.exists() and not swapped:
                output_root.rename(moved_original)
                output_root.mkdir()
                (output_root / "replacement-sentinel.txt").write_text(
                    "replacement-must-survive", encoding="utf-8"
                )
                swapped = True

        monkeypatch.setattr(
            "agent_ex.calibration.judge_materialize._fsync_handle",
            swap_after_publish,
        )
        with pytest.raises(ValueError, match="before return|identity"):
            materialize_judge_view(**review_inputs, output_root=output_root)
        assert swapped
        assert (moved_original / "judge-pack.json").is_file()
        assert (output_root / "replacement-sentinel.txt").read_text(encoding="utf-8") == (
            "replacement-must-survive"
        )


def test_open_swap_quarantines_replaced_staging_directory(
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tempfile

    import agent_ex.calibration.judge_materialize as materializer

    with tempfile.TemporaryDirectory(prefix="agent-ex-judge-open-") as temporary_root:
        base = Path(temporary_root)
        output_root = base / "runner"
        moved_original = base / "moved-original"
        real_open = materializer.os.open
        swapped = False

        def swap_before_open(path, flags, *args, **kwargs):
            nonlocal swapped
            candidate = Path(path)
            if candidate.name == "judge-pack.json" and flags & os.O_CREAT and not swapped:
                staging_root = next(base.glob(".runner.staging-*"))
                staging_root.rename(moved_original)
                staging_root.mkdir()
                (staging_root / "replacement-sentinel.txt").write_text(
                    "replacement-must-survive", encoding="utf-8"
                )
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(materializer.os, "open", swap_before_open)
        with pytest.raises(FileNotFoundError):
            materialize_judge_view(**review_inputs, output_root=output_root)
        assert swapped
        assert not output_root.exists()
        assert (moved_original / "judge-pack.json").exists()
        assert (
            next(path for path in base.iterdir() if path.name.startswith(".runner.staging-"))
            / "replacement-sentinel.txt"
        ).read_text(encoding="utf-8") == "replacement-must-survive"
        assert not (
            next(path for path in base.iterdir() if path.name.startswith(".runner.staging-"))
            / "judge-pack.json"
        ).exists()


def test_failed_write_keeps_partial_staging_without_cleanup(
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tempfile
    import agent_ex.calibration.judge_materialize as materializer

    with tempfile.TemporaryDirectory(prefix="agent-ex-judge-unlink-") as temporary_root:
        base = Path(temporary_root)
        output_root = base / "runner"
        calls = 0
        real_write = materializer._write_bytes_create_only

        def fail_on_second_write(
            path: Path, content: bytes, staging_fd: int, staging_identity: tuple[int, int]
        ) -> tuple[int, int]:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic failure before rollback")
            return real_write(path, content, staging_fd, staging_identity)

        monkeypatch.setattr(
            "agent_ex.calibration.judge_materialize._write_bytes_create_only",
            fail_on_second_write,
        )
        with pytest.raises(OSError, match="synthetic failure") as caught:
            materialize_judge_view(**review_inputs, output_root=output_root)
        assert not output_root.exists()
        assert "staging quarantine retained at" in " ".join(caught.value.__notes__)
        partial = next(base.glob(".runner.staging-*"))
        assert (partial / "judge-pack.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="requires real POSIX directory handles")
@pytest.mark.parametrize("failure", [errno.EIO, errno.EBADF])
def test_fsync_failure_is_fail_closed_and_retains_quarantine(
    tmp_path: Path,
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    failure: int,
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    def fail_fsync(descriptor: int) -> None:
        raise OSError(failure, "synthetic fsync failure")

    monkeypatch.setattr(materializer.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="synthetic fsync failure") as caught:
        materialize_judge_view(**review_inputs, output_root=tmp_path / "runner")
    assert not (tmp_path / "runner").exists()
    assert any(tmp_path.glob(".runner.staging-*"))
    assert "staging quarantine retained at" in " ".join(caught.value.__notes__)


def test_fsync_handle_propagates_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    def fail_fsync(descriptor: int) -> None:
        raise OSError(errno.EIO, "synthetic fsync failure")

    monkeypatch.setattr(materializer.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="synthetic fsync failure"):
        materializer._fsync_handle(123)


@pytest.mark.skipif(os.name != "posix", reason="requires real POSIX directory handles")
def test_extra_file_injected_after_first_inventory_is_rejected(
    tmp_path: Path,
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    real_listdir = materializer.os.listdir
    inventories = 0

    def inject_after_first_inventory(path):
        nonlocal inventories
        names = real_listdir(path)
        inventories += 1
        if inventories == 1:
            descriptor = materializer.os.open(
                "injected-extra", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=path
            )
            try:
                materializer.os.write(descriptor, b"unexpected")
            finally:
                materializer.os.close(descriptor)
        return names

    monkeypatch.setattr(materializer.os, "listdir", inject_after_first_inventory)
    with pytest.raises(ValueError, match="inventory"):
        materialize_judge_view(**review_inputs, output_root=tmp_path / "runner")
    assert not (tmp_path / "runner").exists()
    partial = next(tmp_path.glob(".runner.staging-*"))
    assert (partial / "injected-extra").read_bytes() == b"unexpected"


@pytest.mark.skipif(os.name != "posix", reason="requires real POSIX directory handles")
def test_posix_staging_symlink_entry_is_rejected(
    tmp_path: Path,
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    staging = tmp_path / "staging"
    staging.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    link = staging / "payload"
    link.symlink_to(outside)
    staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    identity = materializer._stable_identity(os.fstat(staging_fd))
    assert identity is not None and stat.S_ISDIR(os.fstat(staging_fd).st_mode)
    try:
        with pytest.raises(OSError):
            materializer._write_bytes_create_only(link, b"overwrite", staging_fd, identity)
    finally:
        os.close(staging_fd)
    assert outside.read_bytes() == b"outside"


@pytest.mark.skipif(os.name != "posix", reason="requires real POSIX directory handles")
def test_posix_staged_file_open_is_handle_relative_and_nofollow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    staging = tmp_path / "staging"
    staging.mkdir()
    target = staging / "payload"
    real_open = materializer.os.open
    staging_fd = real_open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    staging_stat = os.fstat(staging_fd)
    assert stat.S_ISDIR(staging_stat.st_mode)
    staging_identity = materializer._stable_identity(staging_stat)
    assert staging_identity is not None
    observed: list[tuple[int, int | None]] = []

    def record_open(path, flags, *args, **kwargs):
        if Path(path).name == "payload" and flags & os.O_CREAT:
            observed.append((flags, kwargs.get("dir_fd")))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(materializer.os, "open", record_open)
    try:
        materializer._write_bytes_create_only(target, b"payload", staging_fd, staging_identity)
    finally:
        os.close(staging_fd)

    assert observed
    flags, dir_fd = observed[0]
    assert dir_fd == staging_fd
    assert flags & os.O_NOFOLLOW
    assert flags & os.O_EXCL


def test_materializer_ignores_ctime_changes_when_identity_is_stable(
    tmp_path: Path,
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    real_lstat = materializer.os.lstat
    ticks = 0

    class CtimeChangingStat:
        def __init__(self, original: os.stat_result) -> None:
            self._original = original

        def __getattr__(self, name: str) -> object:
            return getattr(self._original, name)

        @property
        def st_ctime_ns(self) -> int:
            nonlocal ticks
            ticks += 1
            return self._original.st_ctime_ns + ticks

    def changing_lstat(path: str | os.PathLike[str]) -> CtimeChangingStat:
        return CtimeChangingStat(real_lstat(path))

    monkeypatch.setattr(materializer.os, "lstat", changing_lstat)
    result = materialize(tmp_path, review_inputs)
    assert result.item_count == len(items_for_coder(review_inputs["bundle"], "coder-b"))
    assert (tmp_path / "runner" / "judge-pack.json").read_bytes() == review_inputs["pack_bytes"]


def test_zero_inode_identity_fails_closed_without_cleanup(
    tmp_path: Path,
    review_inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_ex.calibration.judge_materialize as materializer

    real_lstat = materializer.os.lstat

    class ZeroInodeStat:
        def __init__(self, original: os.stat_result) -> None:
            self._original = original

        def __getattr__(self, name: str) -> object:
            return getattr(self._original, name)

        @property
        def st_ino(self) -> int:
            return 0

    def zero_inode_lstat(path: str | os.PathLike[str]) -> ZeroInodeStat:
        return ZeroInodeStat(real_lstat(path))

    monkeypatch.setattr(materializer.os, "lstat", zero_inode_lstat)
    with pytest.raises(ValueError, match="parent|identity"):
        materialize(tmp_path, review_inputs)
    assert not (tmp_path / "runner").exists()


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
