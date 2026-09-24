# Phase 0B Cold Handoff Contract Implementation Plan

Execution checkpoint (2026-09-24): Tasks 1-2 were implemented test-first in one local batch. Initial missing-module and missing-verifier RED checks were observed; an invalid-calendar-date RED also exposed and closed a validation gap. Independent review identified missing manifest-chain and unique-ID checks; targeted negative tests were added before the fix. The combined old-normal/cold suite reached 28 passed; lint, formatting, and diff checks passed. The checklist below preserves the original planned steps; the commit records the final verification.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, fail-closed evidence contract for observing the old judge service absent after a retained instance restarts, without forging normal-stop evidence.

**Architecture:** A new `cold_handoff.py` owns only the immutable observation record and verification against the historical judge start/projection identity chain. The existing `Phase0BServiceBridge` remains the normal-stop v1 path. Cross-host archive inventory and a v2 migration bridge are separate later units; this plan does not authorize a cloud restart or model request.

**Tech Stack:** Python 3.12 dataclasses; existing canonical JSON hash helpers; pytest and Ruff.

---

## File map

- Create `platform/src/agent_ex/phase0b/cold_handoff.py`: typed cold observation and its verifier. It does not collect evidence or claim an observed machine state by itself.
- Create `platform/tests/test_phase0b_cold_handoff.py`: accepted round-trip and rejected missing/mixed/forged identity, terminal projection, port and GPU states.
- Modify `progress.md`: record precisely which contract is implemented and what remains unverified.

## Task 1: Immutable cold observation

- [x] **Step 1: Write failing tests** in `platform/tests/test_phase0b_cold_handoff.py`. Use the existing `_fixture()` from `test_phase0b_service_bridge.py` for a 797-item typed projection and original start record. Define one valid observation with `instance_id`, `observed_boot_id`, UTC `observed_at`, `old_service_start_identity_hash`, `judge_terminal_projection_hash`, `old_manifest_hash`, `old_environment_lock_hash`, `old_pid`, `process_absent`, `loopback_listener_absent`, and `gpu_compute_process_observation_hash`. Assert `ColdPoweroffObservation.create(...)` round-trips through `to_payload()` and `from_payload()`, retains `preliminary/not_frozen/formal=false`, and has a distinct schema from normal-stop evidence. Parametrize false/invalid absence fields, invalid boot/UTC/hash/PID, and extra fields; each must raise `ValueError` or `TypeError`.
- [x] **Step 2: Run RED** with `python -m pytest tests/test_phase0b_cold_handoff.py -q -p no:cacheprovider -o addopts='' --basetemp=<new isolated temp dir>` from `platform/`. Expected failure: `agent_ex.phase0b.cold_handoff` is not importable.
- [x] **Step 3: Implement** a frozen, slotted `ColdPoweroffObservation` in `platform/src/agent_ex/phase0b/cold_handoff.py`, with exact-field `from_payload`, content-addressed `record_hash`, and `create` that requires the literal absence observations and preliminary metadata. Use `_require_json_transport`, `_require_sha256`, `_require_payload_hash`, and `canonical_payload_hash`; reject unknown keys and malformed UTC/boot/instance identifiers. Do not accept or emit a `judge-service-stop-evidence.v1` schema.
- [x] **Step 4: Run GREEN** using the same targeted command and a fresh isolated temp directory. Expected: all new tests pass.
- [x] **Step 5: Commit** only the new module and new tests with `git add -- platform/src/agent_ex/phase0b/cold_handoff.py platform/tests/test_phase0b_cold_handoff.py` then `git commit -m "feat: record phase0b cold service absence"`.

## Task 2: Bind the observation to the historical judge run

- [x] **Step 1: Write failing tests** in `platform/tests/test_phase0b_cold_handoff.py` for `verify_cold_poweroff_handoff(observation, old_start, old_manifest, judge_projection, replay_verified_projection_hash, old_manifest_hash, old_environment_lock_hash)`. Accept the valid 797-coded fixture. Reject a different original start identity even when observation hashes are recomputed; mismatched projection manifest; wrong replay hash; unresolved dispatch; and a normal-stop record passed as the observation.
- [x] **Step 2: Run RED** using the same targeted pytest command in a new isolated temp directory. Expected failure: verifier not defined, or the valid pair is not accepted.
- [x] **Step 3: Implement** the verifier in the same module. Reuse `_verified_record`, `_JUDGE_START_FIELDS`, `_positive_int` from `service_bridge.py` and `JudgeProjection.from_payload`. Recheck original start schema/hash, `projection.service_start_identity_hash`, `projection.manifest_hash`, exact 797 coded items with zero unresolved intents, and equality to an independently supplied replay hash. Check observation fields against those verified objects and the supplied environment lock. Return the typed observation only on success; do not invent a graceful stop time.
- [x] **Step 4: Run GREEN** using the targeted pytest command; then run `python -m pytest tests/test_phase0b_service_bridge.py tests/test_phase0b_cold_handoff.py -q -p no:cacheprovider -o addopts='' --basetemp=<new isolated temp dir>` to ensure the existing normal-stop path remains unchanged.
- [x] **Step 5: Run quality checks and commit**: `python -m ruff check src/agent_ex/phase0b/cold_handoff.py tests/test_phase0b_cold_handoff.py`; `python -m ruff format --check` on those files; `git diff --check`. Commit only touched production/test files and the progress update.

## Boundary after this plan

Passing local tests proves only the record and identity-verifier logic on synthetic fixtures. It does not prove the retained instance was restarted, that its service is absent, that the copied archive is complete, or that a new host is ready. Those require a separate archive inventory/migration-bridge plan and real Linux evidence after the user supplies a new server. The old instance remains off throughout this plan.
