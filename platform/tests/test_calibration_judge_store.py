from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_ex.calibration.judge_contracts import (
    JudgeExecutionManifest,
    JudgePreflightEvidence,
    JudgeRequestEvidence,
    JudgeRequestRenderer,
    JudgeServiceEvidence,
)
from agent_ex.calibration.judge_runner import (
    AmbiguousJudgeDispatchError,
    JudgeDispatchIntent,
    JudgeDispatchReconciliation,
    JudgeNegativeDispatchEvidence,
    JudgeNegativeVerifierContract,
    JudgeProviderNegativeLogArtifact,
    JudgeApprovedOrder,
    reconstruct_judge_projection,
)
from agent_ex.calibration.judge_store import JudgeRunStore
import agent_ex.calibration.judge_store as judge_store_module
from agent_ex.calibration.review import BlindReviewItem, SemanticReviewPolicy
from agent_ex.domain import canonical_payload_hash


SHA = "a" * 64
POLICY_PATH = (
    Path(__file__).parents[1]
    / "configs"
    / "paper1"
    / "phase0a1-approval-proposal-v2"
    / "semantic_review_policy.json"
)


def _manifest(
    *, pack_hash: str, index_hash: str, renderer_hash: str, preflight_hash: str
) -> JudgeExecutionManifest:
    values: dict[str, object] = {
        "run_id": "judge-run-test",
        "authorization_hash": SHA,
        "review_bundle_hash": SHA,
        "export_hash": SHA,
        "judge_pack_hash": pack_hash,
        "judge_pack_index_hash": index_hash,
        "judge_coder_contract_hash": SHA,
        "old_judge_prompt_hash": SHA,
        "renderer_hash": renderer_hash,
        "ordering_policy_hash": SHA,
        "classifier_contract_hash": SHA,
        "environment_lock_hash": SHA,
        "preflight_hash": preflight_hash,
        "service_start_identity_hash": SHA,
        "runner_view_hash": SHA,
        "old_environment_lock_hash": SHA,
        "model_id": "Qwen/Qwen3-8B",
        "model_revision": "revision",
        "model_artifacts_hash": SHA,
        "tokenizer_hash": SHA,
        "tokenizer_id": "Qwen/Qwen3-8B",
        "tokenizer_revision": "revision",
        "tokenizer_artifacts_hash": SHA,
        "chat_template_hash": SHA,
        "runtime_version": "0.10.2",
        "non_thinking": True,
        "generation_settings": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 512},
        "connect_timeout_seconds": 10.0,
        "read_timeout_seconds": 120.0,
        "total_timeout_seconds": 120.0,
        "retryable_codes": ["timeout", "parse_invalid_json"],
        "retry_backoff_seconds": [0.0, 1.0],
        "max_attempts_per_item": 3,
        "one_item_per_request": True,
        "strict_approved_order": True,
        "archive_uri": "file:///root/autodl-tmp/phase0a1/judge-test",
        "source_commit": "1" * 40,
        "expected_item_count": 797,
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    content = {
        "schema_version": JudgeExecutionManifest._SCHEMA,
        **values,
        "metadata": {
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
        },
    }
    return JudgeExecutionManifest.from_payload(
        {**content, "record_hash": canonical_payload_hash(content)}
    )


@lru_cache(maxsize=1)
def context() -> tuple[
    JudgeExecutionManifest,
    JudgeApprovedOrder,
    JudgeRequestRenderer,
    tuple[BlindReviewItem, ...],
    JudgePreflightEvidence,
    JudgeServiceEvidence,
    dict[str, object],
    dict[str, object],
]:
    policy = SemanticReviewPolicy.from_payload(json.loads(POLICY_PATH.read_text(encoding="utf-8")))
    items = tuple(
        BlindReviewItem.create(
            item_id=f"blind-item-{index:03d}",
            policy_hash=policy.record_hash,
            visible_payload={
                "topic_text": "测试议题",
                "history_text": "",
                "identity_text": "",
                "response_text": f"响应 {index}",
            },
        )
        for index in range(797)
    )
    renderer = JudgeRequestRenderer.create(
        policy,
        chat_template_hash=SHA,
        response_byte_ceiling=4096,
        generation_settings={"temperature": 0.0, "top_p": 1.0, "max_tokens": 512},
        golden_fixture_content={
            "schema_version": "paper1.calibration.judge-rendered-request-golden-input.v1",
            "item": items[0].to_payload(),
            "attempt_index": 1,
            "repair": False,
        },
    )
    pack_content = {
        "schema_version": "paper1.calibration.blind-coder-pack.v1",
        "coder_id": "judge",
        "coder_role": "judge",
        "coder_contract_hash": SHA,
        "policy_id": policy.policy_id,
        "policy_hash": policy.record_hash,
        "export_hash": SHA,
        "items": [item.to_payload() for item in items],
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    pack = {**pack_content, "record_hash": canonical_payload_hash(pack_content)}
    index_content = {
        "schema_version": "paper1.calibration.blind-coder-pack-index.v1",
        "review_bundle_hash": SHA,
        "packs": [
            {"coder_id": "judge", "filename": "judge-pack.json", "record_hash": pack["record_hash"]}
        ],
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    index = {**index_content, "record_hash": canonical_payload_hash(index_content)}
    preflight_content = {
        "schema_version": JudgePreflightEvidence._SCHEMA,
        "authorization_hash": SHA,
        "supporting_material_hash": SHA,
        "old_judge_prompt_hash": SHA,
        "preliminary_inspection_hash": SHA,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "metadata": {
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
        },
    }
    preflight = JudgePreflightEvidence.from_payload(
        {**preflight_content, "record_hash": canonical_payload_hash(preflight_content)}
    )
    manifest = _manifest(
        pack_hash=pack["record_hash"],
        index_hash=index["record_hash"],
        renderer_hash=renderer.record_hash,
        preflight_hash=preflight.record_hash,
    )
    order = JudgeApprovedOrder.from_manifest_bound_payloads(manifest, pack, index)
    start = JudgeServiceEvidence.create(
        phase="start", authorization_hash=SHA, evidence_hash=SHA, service_start_identity_hash=SHA
    )
    return manifest, order, renderer, items, preflight, start, pack, index


def manifest() -> JudgeExecutionManifest:
    return context()[0]


def intent(*, order_index: int = 0, attempt_index: int = 1) -> JudgeDispatchIntent:
    manifest_value, _, renderer, items, _, _, _, _ = context()
    item = items[order_index]
    request = JudgeRequestEvidence.create(
        rendered_request=renderer.render(item, attempt_index, repair=attempt_index > 1),
        manifest_hash=manifest_value.record_hash,
        order_index=order_index,
        model_id=manifest_value.model_id,
    )
    return JudgeDispatchIntent.create(
        request=request,
        created_at="2026-09-19T00:00:00Z",
    )


def negative_evidence(
    dispatch: JudgeDispatchIntent, *, observation_id: str
) -> JudgeNegativeDispatchEvidence:
    manifest_value = context()[0]
    verifier = JudgeNegativeVerifierContract.create(manifest_value)
    provider_log = json.dumps(
        {
            "schema_version": "paper1.calibration.provider-negative-log.v1",
            "request_id": dispatch.request_id,
            "observation_id": observation_id,
            "dispatch_found": False,
            "verifier_contract_hash": verifier.record_hash,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    artifact = JudgeProviderNegativeLogArtifact.create(
        dispatch,
        verifier=verifier,
        observation_id=observation_id,
        provider_log_bytes=provider_log,
        observed_at="2026-09-19T00:01:00Z",
    )
    return JudgeNegativeDispatchEvidence.create(
        dispatch,
        manifest=manifest_value,
        verifier=verifier,
        provider_log_artifact=artifact,
    )


@pytest.fixture
def judge_store(tmp_path: Path) -> JudgeRunStore:
    manifest_value, _, _, _, preflight, start, pack, index = context()
    store = JudgeRunStore.create(tmp_path / "judge", manifest_value, pack, index)
    store.append_preflight(preflight)
    store.append_service_start(start)
    return store


def test_store_creates_exact_append_only_layout_and_initial_projection(
    judge_store: JudgeRunStore,
) -> None:
    assert (judge_store.root / "staging" / "manifest.json").is_file()
    for relative in (
        "attempts",
        "dispatch",
        "reconciliation",
        "raw",
        "service/preflight",
        "service/start",
        "service/stop",
        "journal",
        "projections",
    ):
        assert (judge_store.root / "staging" / relative).is_dir()
    snapshots = tuple((judge_store.root / "staging" / "projections").iterdir())
    assert len(snapshots) == 3
    assert sorted(snapshots)[0].name.startswith("000000000000-")
    assert judge_store.current_projection.preflight_hash == judge_store.manifest.preflight_hash
    assert (
        judge_store.current_projection.service_start_identity_hash
        == judge_store.manifest.service_start_identity_hash
    )


def test_store_creation_and_record_append_are_create_only(
    judge_store: JudgeRunStore,
) -> None:
    with pytest.raises(FileExistsError):
        JudgeRunStore.create(judge_store.root, manifest(), context()[6], context()[7])
    record = intent()
    judge_store.append_intent(record)
    with pytest.raises(FileExistsError):
        judge_store.append_intent(record)


def test_unresolved_dispatch_requires_typed_reconciliation(judge_store: JudgeRunStore) -> None:
    judge_store.append_intent(intent())
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        reconstruct_judge_projection(judge_store)


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("recovered_response", "recovered_response"),
        ("ambiguous", "ambiguous_incomplete"),
    ],
)
def test_reconciliation_has_only_three_outcomes(
    judge_store: JudgeRunStore, decision: str, expected_status: str
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    evidence: dict[str, object] = {
        "provider_audit_hash": SHA,
        "checked_at": "2026-09-19T00:01:00Z",
    }
    if decision == "recovered_response":
        response = b"recovered"
        response_hash = hashlib.sha256(response).hexdigest()
        provider_audit = {
            "provider_audit_hash": SHA,
            "request_id": dispatch.request_id,
            "response_bytes_base64": base64.b64encode(response).decode("ascii"),
            "response_bytes_hash": response_hash,
            "checked_at": "2026-09-19T00:01:00Z",
        }
        judge_store.append_raw_provider_audit(dispatch, provider_audit)
        evidence["response_bytes_hash"] = response_hash
    record = JudgeDispatchReconciliation.create(dispatch, decision, evidence)
    judge_store.append_reconciliation(record)
    projection = judge_store.current_projection
    assert projection.item_states[dispatch.item_id].status == expected_status
    if decision == "recovered_response":
        with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
            reconstruct_judge_projection(judge_store)


def test_open_replays_and_rejects_a_tampered_projection_chain(
    judge_store: JudgeRunStore,
) -> None:
    dispatch = intent()
    judge_store.append_intent(dispatch)
    judge_store.append_reconciliation(
        JudgeDispatchReconciliation.create(
            dispatch,
            "ambiguous",
            {
                "provider_audit_hash": SHA,
                "checked_at": "2026-09-19T00:01:00Z",
            },
        )
    )
    reopened = JudgeRunStore.open(judge_store.root)
    assert reopened.current_projection.record_hash == judge_store.current_projection.record_hash

    latest = sorted((judge_store.root / "staging" / "projections").iterdir())[-1]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    payload["previous_projection_hash"] = "b" * 64
    latest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="projection|hash chain"):
        JudgeRunStore.open(judge_store.root)


def test_append_refuses_to_extend_a_tampered_projection_chain(
    judge_store: JudgeRunStore,
) -> None:
    latest = next((judge_store.root / "staging" / "projections").iterdir())
    payload = json.loads(latest.read_text(encoding="utf-8"))
    payload["record_hash"] = "b" * 64
    latest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="projection|hash"):
        judge_store.append_intent(intent())


def test_append_does_not_rescan_every_historical_projection(
    judge_store: JudgeRunStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_full_projection_scan(self: JudgeRunStore) -> tuple[object, ...]:
        raise AssertionError("append must not reload the full projection history")

    monkeypatch.setattr(JudgeRunStore, "_read_projections", reject_full_projection_scan)
    judge_store.append_intent(intent())


def test_journal_manifest_hash_is_checked_even_when_entry_is_rehashed(
    judge_store: JudgeRunStore,
) -> None:
    judge_store.append_intent(intent())
    journal = sorted((judge_store.staging / "journal").iterdir())[-1]
    payload = json.loads(journal.read_text(encoding="utf-8"))
    payload["manifest_hash"] = "b" * 64
    content = {name: value for name, value in payload.items() if name != "journal_hash"}
    payload["journal_hash"] = canonical_payload_hash(content)
    replacement = journal.with_name(f"{payload['sequence']:012d}-{payload['journal_hash']}.json")
    journal.rename(replacement)
    replacement.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="journal manifest"):
        JudgeRunStore.open(judge_store.root)


def test_child_directory_symlink_escape_is_rejected(
    judge_store: JudgeRunStore, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    dispatch = judge_store.staging / "dispatch"
    dispatch.rmdir()
    try:
        dispatch.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(ValueError, match="link|inventory|directory"):
        JudgeRunStore.open(judge_store.root)


def test_nested_evidence_inventory_rejects_unrecognized_directory(
    judge_store: JudgeRunStore,
) -> None:
    (judge_store.staging / "dispatch" / "unexpected").mkdir()
    with pytest.raises(ValueError, match="inventory|regular file"):
        JudgeRunStore.open(judge_store.root)


def test_partial_prepared_write_never_publishes_a_torn_final_file(
    judge_store: JudgeRunStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_write = judge_store_module.os.write
    injected = False

    def torn_write(descriptor: int, data: bytes) -> int:
        nonlocal injected
        if not injected and len(data) > 32:
            injected = True
            original_write(descriptor, data[:17])
            raise OSError("injected torn temporary write")
        return original_write(descriptor, data)

    monkeypatch.setattr(judge_store_module.os, "write", torn_write)
    with pytest.raises(OSError, match="torn"):
        judge_store.append_intent(intent())
    monkeypatch.setattr(judge_store_module.os, "write", original_write)
    reopened = JudgeRunStore.open(judge_store.root)
    assert reopened.current_projection.item_order == ()
    assert not any(
        path.name.startswith(".tmp-")
        for path in (reopened.staging / "transactions" / "prepared").iterdir()
    )


def test_nonterminal_projection_file_is_rejected_and_seals_append(
    judge_store: JudgeRunStore,
) -> None:
    terminal = judge_store.staging / "projection.json"
    terminal.write_bytes(
        judge_store_module._canonical_json_bytes(judge_store.current_projection.to_payload())
    )
    with pytest.raises(ValueError, match="terminal|cover"):
        JudgeRunStore.open(judge_store.root)
    with pytest.raises(ValueError, match="sealed|terminal"):
        judge_store.append_intent(intent())


def test_dangling_terminal_projection_symlink_is_rejected(
    judge_store: JudgeRunStore,
    tmp_path: Path,
) -> None:
    terminal = judge_store.staging / "projection.json"
    try:
        terminal.symlink_to(tmp_path / "missing-projection.json")
    except OSError:
        pytest.skip("file symlinks unavailable")
    with pytest.raises(ValueError, match="terminal|link|inventory"):
        JudgeRunStore.open(judge_store.root)
    with pytest.raises(ValueError, match="sealed|terminal"):
        judge_store.append_intent(intent())


def test_publish_exact_rejects_existing_symlink_even_when_bytes_match(
    tmp_path: Path,
) -> None:
    payload = {"schema_version": "test.v1", "value": 1}
    target = tmp_path / "outside.json"
    target.write_bytes(judge_store_module._canonical_json_bytes(payload))
    link = tmp_path / "inside.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks unavailable")
    with pytest.raises(ValueError, match="regular|link|cannot be read"):
        judge_store_module._publish_json_exact(link, payload)


@pytest.mark.parametrize(
    "relative",
    (
        "manifest.json",
        "approved-pack.json",
        "approved-index.json",
        "approved-order.json",
        ".append.lock",
    ),
)
def test_authoritative_base_file_symlink_is_rejected(
    judge_store: JudgeRunStore,
    tmp_path: Path,
    relative: str,
) -> None:
    target = tmp_path / f"outside-{relative.replace('.', '-')}.json"
    source = judge_store.staging / relative
    target.write_bytes(source.read_bytes())
    source.unlink()
    try:
        source.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks unavailable")
    with pytest.raises(ValueError, match="link|regular file|authoritative"):
        JudgeRunStore.open(judge_store.root)


def test_concurrent_append_has_one_winner_and_archive_remains_replayable(
    judge_store: JudgeRunStore,
) -> None:
    record = intent()
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda _: _append_outcome(judge_store, record),
                range(2),
            )
        )
    assert sorted(outcomes) == ["exists", "ok"]
    reopened = JudgeRunStore.open(judge_store.root)
    with pytest.raises(AmbiguousJudgeDispatchError):
        reconstruct_judge_projection(reopened)


def _append_outcome(store: JudgeRunStore, record: JudgeDispatchIntent) -> str:
    try:
        store.append_intent(record)
    except FileExistsError:
        return "exists"
    return "ok"


@pytest.mark.parametrize("crash_phase", ["prepared", "record", "journal", "projection", "commit"])
def test_prepared_transaction_is_deterministically_recovered(
    judge_store: JudgeRunStore,
    monkeypatch: pytest.MonkeyPatch,
    crash_phase: str,
) -> None:
    def crash(phase: str) -> None:
        if phase == crash_phase:
            raise RuntimeError("injected crash")

    monkeypatch.setattr(judge_store_module, "_transaction_checkpoint", crash)
    with pytest.raises(RuntimeError, match="injected crash"):
        judge_store.append_intent(intent())
    monkeypatch.setattr(judge_store_module, "_transaction_checkpoint", lambda phase: None)
    recovered = JudgeRunStore.open(judge_store.root)
    with pytest.raises(AmbiguousJudgeDispatchError, match="unresolved dispatch"):
        reconstruct_judge_projection(recovered)


def test_terminal_projection_is_create_only_and_requires_exact_terminal_cover(
    judge_store: JudgeRunStore,
) -> None:
    with pytest.raises(ValueError, match="terminal|cover"):
        judge_store.verify_terminal_projection()
    assert not (judge_store.staging / "projection.json").exists()
