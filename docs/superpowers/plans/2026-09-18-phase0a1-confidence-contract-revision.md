# Phase 0A-1 Confidence Contract Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Replace the underspecified calibration response/repair contract with a uniformly rendered, hash-bound, resume-safe contract; regenerate a fresh six-group packet; and execute an isolated 816-case cloud run only after exact approval.

**Architecture:** A shared renderer is the single source of truth for semantic and repair wording. ProbeRequest v2 binds repair provenance, and shared durable-chain validation derives the semantic repair origin plus immediate predecessor across execution, retry, replay, resume, and review. The v1 diagnostic run/packet stay immutable; replacements use v2 identities.

**Tech Stack:** Python 3.12, frozen dataclasses, strict JSON/SHA-256, pytest, Ruff, Git bundles, AutoDL loopback vLLM/Qwen3-8B.

---

## File map

- Create platform/src/agent_ex/calibration/response_contract.py for exact scale/order-aware wording.
- Modify specification.py, contracts.py, runner.py, and review.py.
- Modify the packet materializer; create phase0a1-approval-proposal-v2 while retaining v1.
- Extend focused tests for prompt, request, retry, resume, cloud persistence, review, and packet parity.
- Create logs/2026-09-18-phase0a1-confidence-contract-revision.md and update progress.md only with verified evidence.

### Task 1: Render one exact response contract for every case

**Files:**
- Create: platform/src/agent_ex/calibration/response_contract.py
- Modify: platform/src/agent_ex/calibration/specification.py:389-414
- Test: platform/tests/test_calibration_specification.py:61

- [ ] **Step 1: Write the failing all-cases test**

~~~python
@pytest.mark.parametrize(
    ("scale_id", "range_text"),
    (("stance-1-7", "from 1 to 7"), ("stance-0-10", "from 0 to 10")),
)
def test_every_case_declares_distinct_stance_confidence_and_json_contract(
    scale_id: str, range_text: str
) -> None:
    cases = expand_probe_cases(load_probe_specification(probe_spec_payload()))
    selected = tuple(case for case in cases if case.scale_id == scale_id)
    assert selected
    for case in selected:
        text = case.rendered_messages[-1]["content"]
        assert f"stance must be a JSON integer {range_text}" in text
        assert "confidence is independent of the stance scale" in text
        assert "must be a JSON integer from 1 to 5" in text
        assert "public_reason must be non-empty text of at most 2048 characters" in text
        assert "return exactly one JSON object" in text
        assert "no extra keys, Markdown, or commentary" in text
        order = (
            "stance,confidence,public_reason"
            if case.field_order_id == "stance-confidence-reason"
            else "public_reason,confidence,stance"
        )
        assert f"exact field order: {order}" in text
~~~

- [ ] **Step 2: Run RED**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_specification.py::test_every_case_declares_distinct_stance_confidence_and_json_contract
~~~

Expected: both parameters fail because confidence/reason/exact-JSON wording is absent.

- [ ] **Step 3: Add the shared renderer**

~~~python
"""Exact provider-neutral response wording for Phase 0A calibration probes."""

from __future__ import annotations

_SCALE_RANGES = {"stance-1-7": (1, 7), "stance-0-10": (0, 10)}
_FIELD_ORDERS = {
    "stance-confidence-reason": ("stance", "confidence", "public_reason"),
    "reason-confidence-stance": ("public_reason", "confidence", "stance"),
}


def _declarations(scale_id: str, field_order_id: str) -> tuple[int, int, str]:
    if scale_id not in _SCALE_RANGES:
        raise ValueError("scale_id is not supported")
    if field_order_id not in _FIELD_ORDERS:
        raise ValueError("field_order_id is not supported")
    minimum, maximum = _SCALE_RANGES[scale_id]
    return minimum, maximum, ",".join(_FIELD_ORDERS[field_order_id])


def response_contract_text(scale_id: str, field_order_id: str) -> str:
    minimum, maximum, order = _declarations(scale_id, field_order_id)
    return (
        f"Response contract: stance must be a JSON integer from {minimum} to {maximum} "
        "on the declared stance scale; confidence is independent of the stance scale and "
        "must be a JSON integer from 1 to 5; public_reason must be non-empty text of at "
        f"most 2048 characters; return exactly one JSON object with exact field order: "
        f"{order}; no extra keys, Markdown, or commentary."
    )


def format_repair_instruction(scale_id: str, field_order_id: str) -> str:
    return (
        "FORMAT REPAIR ONLY: preserve the substantive stance and public_reason from your "
        "immediately preceding answer; express intended confidence on the separate 1-to-5 "
        "scale without changing the substantive position or reason. "
        + response_contract_text(scale_id, field_order_id)
    )
~~~

Import response_contract_text in specification.py, preserve the anchors, then append:

~~~python
user_parts.append(scale_instruction)
user_parts.append(response_contract_text(scale["scale_id"], field_order["field_order_id"]))
~~~

- [ ] **Step 4: Run GREEN and commit**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_specification.py
& .\.test-venv\Scripts\python.exe -m ruff check platform/src/agent_ex/calibration/response_contract.py platform/src/agent_ex/calibration/specification.py platform/tests/test_calibration_specification.py
git add -- platform/src/agent_ex/calibration/response_contract.py platform/src/agent_ex/calibration/specification.py platform/tests/test_calibration_specification.py
git diff --cached --check
git commit -m "declare phase0a1 confidence response contract"
~~~

### Task 2: Bind repair origin and predecessor in ProbeRequest v2

**Files:**
- Modify: platform/src/agent_ex/calibration/contracts.py:514-668,1444-1668
- Test: platform/tests/test_calibration_adapter_parser.py:85-230
- Test: platform/tests/test_calibration_runner.py:239-287,883-1030

- [ ] **Step 1: Write failing provenance tests**

Create a real format_pending origin with execute_probe_run(..., stop_after_attempts=1), then assert:

~~~python
origin = projection.attempts[0]
repair = ProbeRequest.create(
    case,
    attempt_index=2,
    attempt_kind="format_repair",
    generation_settings=GENERATION_SETTINGS,
    repair_origin_attempt=origin,
    repair_predecessor_attempt=origin,
)
assert repair.repair_binding["origin_attempt_id"] == origin.attempt_id
assert repair.repair_binding["origin_response_hash"] == origin.response.record_hash
assert repair.repair_binding["origin_parse_evidence_hash"] == origin.parse_evidence.record_hash
assert repair.repair_binding["predecessor_attempt_id"] == origin.attempt_id
assert tuple(message["role"] for message in repair.rendered_messages) == (
    "system", "user", "assistant", "user"
)
assert repair.rendered_messages[2]["content"] == origin.response.raw_response
assert ProbeRequest.from_payload(repair.to_payload()) == repair
~~~

Add rejection tests for semantic-with-context, repair-without-context, parsed/refused origin, cross-case context, non-immediate predecessor, and recomputed hash drift. Prove the missing-parse boundary by asserting ProbeAttempt itself rejects response evidence with parse_evidence=None.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_adapter_parser.py platform/tests/test_calibration_runner.py -k "repair_binding or repair_origin or repair_context"
~~~

- [ ] **Step 3: Add strict binding and schema v2**

~~~python
_REPAIR_BINDING_FIELDS = (
    "origin_attempt_id",
    "origin_attempt_hash",
    "origin_attempt_index",
    "origin_response_id",
    "origin_response_hash",
    "origin_parse_evidence_id",
    "origin_parse_evidence_hash",
    "predecessor_attempt_id",
    "predecessor_attempt_hash",
    "predecessor_attempt_index",
)
~~~

Add repair_binding: Mapping[str, object] | None before record_hash; bump to paper1.calibration.probe-request.v2; include/freeze it in identity. Semantic requests require null. Repair requests require the exact keys, valid IDs/hashes/positive indexes, predecessor index attempt_index-1, and roles system/user/assistant/user. from_payload accepts only object or null.

- [ ] **Step 4: Add run-bound validation and rendering**

Add this helper after ProbeAttempt; ProbeRequest.create additionally checks both attempts against the supplied case and requires predecessor.attempt_index == attempt_index - 1:

~~~python
def _repair_binding_from_attempts(
    origin: ProbeAttempt, predecessor: ProbeAttempt
) -> dict[str, object]:
    if type(origin) is not ProbeAttempt or type(predecessor) is not ProbeAttempt:
        raise TypeError("repair context requires ProbeAttempt records")
    if (
        origin.probe_run_id != predecessor.probe_run_id
        or origin.run_instance_id != predecessor.run_instance_id
        or origin.specification_hash != predecessor.specification_hash
        or origin.case_inventory_hash != predecessor.case_inventory_hash
        or origin.runtime_policy_hash != predecessor.runtime_policy_hash
        or origin.probe_case_id != predecessor.probe_case_id
        or origin.probe_case_hash != predecessor.probe_case_hash
    ):
        raise ValueError("repair origin and predecessor are not from one case chain")
    if origin.attempt_kind != "semantic" or origin.response.outcome != "response":
        raise ValueError("repair origin must be a semantic response")
    if origin.parse_evidence is None or origin.parse_evidence.success:
        raise ValueError("repair origin requires a failed bound parse")
    if (
        origin.parse_evidence.error["code"] == "refusal"
        or origin.case_status_after != "format_pending"
        or origin.response.raw_response is None
    ):
        raise ValueError("repair origin is not format-repair eligible")
    if predecessor.attempt_id != origin.attempt_id:
        binding = predecessor.request.repair_binding
        if (
            predecessor.attempt_kind != "format_repair"
            or predecessor.case_status_after != "pending"
            or binding is None
            or binding["origin_attempt_id"] != origin.attempt_id
            or binding["origin_attempt_hash"] != origin.record_hash
        ):
            raise ValueError("repair retry predecessor changed its semantic origin")
    return {
        "origin_attempt_id": origin.attempt_id,
        "origin_attempt_hash": origin.record_hash,
        "origin_attempt_index": origin.attempt_index,
        "origin_response_id": origin.response.response_id,
        "origin_response_hash": origin.response.record_hash,
        "origin_parse_evidence_id": origin.parse_evidence.parse_evidence_id,
        "origin_parse_evidence_hash": origin.parse_evidence.record_hash,
        "predecessor_attempt_id": predecessor.attempt_id,
        "predecessor_attempt_hash": predecessor.record_hash,
        "predecessor_attempt_index": predecessor.attempt_index,
    }
~~~

ProbeRequest.create accepts nullable repair_origin_attempt and repair_predecessor_attempt. Semantic calls reject either. Repair calls validate the case IDs/hashes, immediate index, call the helper, and render:

~~~python
rendered_messages = case.rendered_messages + (
    {"role": "assistant", "content": repair_origin_attempt.response.raw_response},
    {
        "role": "user",
        "content": format_repair_instruction(case.scale_id, case.field_order_id),
    },
)
~~~

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_adapter_parser.py platform/tests/test_calibration_runner.py -k "repair_binding or repair_origin or repair_context"
& .\.test-venv\Scripts\python.exe -m ruff check platform/src/agent_ex/calibration/contracts.py platform/tests/test_calibration_adapter_parser.py platform/tests/test_calibration_runner.py
git add -- platform/src/agent_ex/calibration/contracts.py platform/tests/test_calibration_adapter_parser.py platform/tests/test_calibration_runner.py
git diff --cached --check
git commit -m "bind phase0a1 format repair provenance"
~~~

### Task 3: Enforce the chain through runner, replay, resume, cloud, and review

**Files:**
- Modify: contracts.py:1779-1903, runner.py:268-414, review.py:1790-1842
- Test: test_calibration_runner.py, test_calibration_cloud_run.py, test_calibration_review.py, test_calibration_vllm_adapter.py

- [ ] **Step 1: Write failing retry/resume tests**

Script semantic invalid -> repair timeout -> repair success. Assert three kinds semantic/format_repair/format_repair; both repairs bind the same origin; attempt 3 binds attempt 2 as predecessor; both assistant messages equal the first raw response. Compare uninterrupted execution with serialized stop/resume at format_pending and pending-repair boundaries. Add a cloud-store reopen/resume case.

- [ ] **Step 2: Write failing replay/HTTP/review tests**

Add hash-consistent origin/predecessor drift, reorder, and cross-case attacks; ProbeRunProjection.from_payload must fail. Verify the provider receives exact four messages. Extend the review bridge through repair transport retry.

- [ ] **Step 3: Run RED**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_runner.py -k "repair or resume or projection"
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_cloud_run.py -k "persist or recoverable or resume"
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_review.py -k bridge
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_vllm_adapter.py -k "repair or preserves_raw"
~~~

- [ ] **Step 4: Add the shared chain helper**

~~~python
def repair_context_for_next_request(
    chain: tuple[ProbeAttempt, ...], attempt_kind: str
) -> tuple[ProbeAttempt | None, ProbeAttempt | None]:
    if attempt_kind == "semantic":
        return None, None
    if attempt_kind != "format_repair" or not chain:
        raise ValueError("format repair requires a durable prior chain")
    predecessor = chain[-1]
    if predecessor.case_status_after == "format_pending":
        origin = predecessor
    elif predecessor.case_status_after == "pending" and predecessor.attempt_kind == "format_repair":
        binding = predecessor.request.repair_binding
        if binding is None:
            raise ValueError("pending repair lacks origin binding")
        matches = tuple(
            item for item in chain
            if item.attempt_id == binding["origin_attempt_id"]
            and item.record_hash == binding["origin_attempt_hash"]
        )
        if len(matches) != 1:
            raise ValueError("repair origin is missing or duplicated")
        origin = matches[0]
    else:
        raise ValueError("case chain is not eligible for format repair")
    return origin, predecessor
~~~

Add the full replay validator:

~~~python
def validate_request_against_prior_chain(
    request: ProbeRequest, chain: tuple[ProbeAttempt, ...]
) -> None:
    origin, predecessor = repair_context_for_next_request(chain, request.attempt_kind)
    if request.attempt_kind == "semantic":
        if request.repair_binding is not None:
            raise ValueError("semantic request carries repair provenance")
        return
    assert origin is not None and predecessor is not None
    if (
        request.probe_case_id != origin.probe_case_id
        or request.probe_case_hash != origin.probe_case_hash
        or request.attempt_index != predecessor.attempt_index + 1
    ):
        raise ValueError("repair request is outside its bound case chain")
    expected_binding = _repair_binding_from_attempts(origin, predecessor)
    expected_messages = origin.request.rendered_messages + (
        {"role": "assistant", "content": origin.response.raw_response},
        {
            "role": "user",
            "content": format_repair_instruction(request.scale_id, request.field_order_id),
        },
    )
    if dict(request.repair_binding or {}) != expected_binding:
        raise ValueError("repair request provenance differs from the durable chain")
    if tuple(request.rendered_messages) != expected_messages:
        raise ValueError("repair request messages differ from the durable origin")
~~~

- [ ] **Step 5: Wire execution/replay/review**

Runner calls repair_context_for_next_request before ProbeRequest.create and passes both attempts. Projection replay maintains per-case chains and validates each request before applying it. Review groups attempts by case and derives context from the prefix before reconstructing the final request.

~~~python
origin, predecessor = repair_context_for_next_request(tuple(chain), next_kind)
request = ProbeRequest.create(
    case,
    attempt_index=len(chain) + 1,
    attempt_kind=next_kind,
    generation_settings=generation_settings,
    repair_origin_attempt=origin,
    repair_predecessor_attempt=predecessor,
)
~~~

- [ ] **Step 6: Run GREEN and commit**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_runner.py platform/tests/test_calibration_cloud_run.py platform/tests/test_calibration_review.py platform/tests/test_calibration_vllm_adapter.py
& .\.test-venv\Scripts\python.exe -m ruff check platform/src/agent_ex/calibration/contracts.py platform/src/agent_ex/calibration/runner.py platform/src/agent_ex/calibration/review.py platform/tests/test_calibration_runner.py platform/tests/test_calibration_cloud_run.py platform/tests/test_calibration_review.py platform/tests/test_calibration_vllm_adapter.py
git add -- platform/src/agent_ex/calibration/contracts.py platform/src/agent_ex/calibration/runner.py platform/src/agent_ex/calibration/review.py platform/tests/test_calibration_runner.py platform/tests/test_calibration_cloud_run.py platform/tests/test_calibration_review.py platform/tests/test_calibration_vllm_adapter.py
git diff --cached --check
git commit -m "replay phase0a1 repair context across resume"
~~~

### Task 4: Materialize an isolated v2 approval packet

**Files:**
- Modify: platform/scripts/materialize_phase0a1_approval_packet.py:488-590
- Create: platform/configs/paper1/phase0a1-approval-proposal-v2/*
- Modify: platform/tests/test_phase0a1_approval_packet.py

- [ ] **Step 1: Write failing packet-parity test**

Point PACKET_DIR to v2 and add:

~~~python
def test_checked_in_v2_packet_equals_fresh_materializer_and_excludes_v1() -> None:
    packet = json.loads(
        (PACKET_DIR / "approved-cloud-artifacts.proposal.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (PACKET_DIR / "approval-summary.json").read_text(encoding="utf-8")
    )
    assert packet == build_packet()
    artifacts = load_cloud_run_artifacts(packet)
    assert len(artifacts.cases) == 816
    assert artifacts.archive_uri == "/root/autodl-tmp/agent-ex-phase0a1-probe-816-v2"
    assert artifacts.archive_uri != "/root/autodl-tmp/agent-ex-phase0a1-probe-816-v1"
    assert summary["packet_hash"] == packet["record_hash"]
    assert summary["group_hashes"] == packet["approved_group_hashes"]
    for case in artifacts.cases:
        text = case.rendered_messages[-1]["content"]
        assert "confidence is independent of the stance scale" in text
        assert "must be a JSON integer from 1 to 5" in text
~~~

Do not duplicate old v1 constants.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_phase0a1_approval_packet.py
~~~

- [ ] **Step 3: Change archive URI and materialize from scratch**

~~~powershell
& .\.test-venv\Scripts\python.exe platform/scripts/materialize_phase0a1_approval_packet.py platform/configs/paper1/phase0a1-approval-proposal-v2
~~~

Retain v1 unchanged.

- [ ] **Step 4: Verify and commit**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_phase0a1_approval_packet.py platform/tests/test_calibration_cloud_run.py::test_cloud_run_artifact_packet_rejects_group_or_top_hash_drift platform/tests/test_calibration_cloud_run.py::test_cloud_run_manifest_binds_816_case_inventory_and_round_trips
git add -- platform/scripts/materialize_phase0a1_approval_packet.py platform/configs/paper1/phase0a1-approval-proposal-v2 platform/tests/test_phase0a1_approval_packet.py
git diff --cached --check
git commit -m "materialize phase0a1 confidence contract packet"
~~~

Expected: 816 cases, 144/96/576 families, one combined and six full SHA-256 values.

### Task 5: Release verification, reviews, log, and bundle

**Files:**
- Create: logs/2026-09-18-phase0a1-confidence-contract-revision.md
- Modify: progress.md

- [ ] **Step 1: Run combined focused tests**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_specification.py platform/tests/test_calibration_adapter_parser.py platform/tests/test_calibration_runner.py platform/tests/test_calibration_cloud_run.py platform/tests/test_calibration_review.py platform/tests/test_calibration_vllm_adapter.py platform/tests/test_phase0a1_approval_packet.py
~~~

- [ ] **Step 2: Run full release checks**

~~~powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests
& .\.test-venv\Scripts\python.exe -m ruff check platform/src platform/tests platform/scripts
& .\.test-venv\Scripts\python.exe -m ruff format --check platform/src platform/tests platform/scripts
& .\.test-venv\Scripts\python.exe -m pip check
git diff --check
~~~

Record exact counts/times only after reading complete fresh output.

- [ ] **Step 3: Independent review**

Dispatch separate specification and code-quality reviewers. Fix every P0-P2 issue with a new red/green cycle; repeat until both approve.

- [ ] **Step 4: Record and commit checkpoint**

The log/progress entry records commits, exact tests, request schema v2, packet path, combined/six hashes, counts, old-run exclusion, v2 archive, no-formal-authority boundary, and remaining approval/cloud gate.

~~~powershell
git add -- logs/2026-09-18-phase0a1-confidence-contract-revision.md progress.md
git diff --cached --check
git commit -m "record phase0a1 confidence contract release"
~~~

- [ ] **Step 5: Build and verify without uploading**

~~~powershell
git bundle create phase0a1-confidence-contract-v2.bundle codex/paper1-phase0
git bundle verify phase0a1-confidence-contract-v2.bundle
Get-Item -LiteralPath phase0a1-confidence-contract-v2.bundle | Select-Object Name,Length
Get-FileHash -Algorithm SHA256 -LiteralPath phase0a1-confidence-contract-v2.bundle
~~~

Stop before upload. Present exact bundle bytes/SHA/destination, combined hash, and six hashes.

### Task 6: Exact approval, cloud deployment, fresh 816, and terminal evidence

**External artifacts:**
- Bundle: phase0a1-confidence-contract-v2.bundle
- Packet: platform/configs/paper1/phase0a1-approval-proposal-v2/approved-cloud-artifacts.proposal.json
- Run root: /root/autodl-tmp/agent-ex-phase0a1-probe-816-v2

- [ ] **Step 1:** Obtain explicit approval for the exact bundle and all six changed group hashes. Old approvals do not transfer.
- [ ] **Step 2:** Require AutoDL running; read-only verify host/GPU/disk/port, clean checkout, HEAD, and absent v2 archive. Leave v1 untouched.
- [ ] **Step 3:** Upload only the approved bundle, verify remote bytes/SHA, fetch it, and fast-forward the clean checkout.
- [ ] **Step 4:** Reuse venv/model only after fresh inspection; create new environment lock/manifest; start and identity-check loopback vLLM.
- [ ] **Step 5:** Execute all 816 into v2. Resume only its append-only store; never replay old failures or read old responses as input.
- [ ] **Step 6:** Verify exactly 816 terminal cases, complete intent/attempt/resolution evidence, and unchanged gates. Invalid measurement becomes explicit incomplete.
- [ ] **Step 7:** Stop vLLM, record stop evidence, confirm port/GPU idle, keep raw evidence outside Git, then allow instance shutdown.
- [ ] **Step 8:** Only if valid, export blind Qwen judge work and deterministic 174-item human sample; do not import partial codes or seal.
- [ ] **Step 9:** Commit only log/progress hashes/counts/archive/next step; never add raw responses, model files, venvs, or run archives.

## Self-review record

- Spec coverage: Tasks 1-3 cover wording, confidence, assistant history, origin/predecessor hashes, retry, resume, replay, and review. Task 4 covers new identities/six groups. Tasks 5-6 cover verification, approval, isolated 816, and evidence.
- Placeholder scan: no unresolved marker or invented hash; runtime hashes are read from generated artifacts before approval.
- Type consistency: repair_binding, repair_origin_attempt, repair_predecessor_attempt, repair_context_for_next_request, and validate_request_against_prior_chain are consistent.
- Scope: parser ranges, gates, generation settings, topics/personas, and formal authority remain unchanged.
