# SIS Storage Binding Implementation Plan

> Execute inline with executing-plans and TDD in the existing feature worktree.

**Goal:** Create, atomically initialize/seal and reopen six SIS cell stores using
the shared SQLite implementation, without admitting SIS through legacy validation.

**Architecture:** StudyRunBinding binds groups, neutral aliases, node/agent mapping,
topic, schedule and matched graphs. StudyRunStorage subclasses RunStorage only
at the exposure-validation strategy and initial-state validation boundary.
The binding payload is retained inside run_spec and therefore manifest identity.
This batch does not yet authorize provider attempts or event commits.

**Tech Stack:** Existing SQLite v6 transactions, immutable typed records, pytest.

## Task 1 — Binding and explicit shared strategy

- [x] Create test_identity_network_storage.py before production edits: six cells
  must create/seal/reopen; RunStorage.create must still reject the same SIS manifest.
  Write bounded tests for schedule/group/graph/alias drift and incorrect round-0 stance.
- [x] Add identity_network/storage.py with StudyRunBinding.create/from_payload,
  strict schema/metadata/hash, balanced group replay, fixed graph replay and exact
  roster/node/alias/schedule/topic identity. Candidate common_inputs_hash is explicit.
- [x] Add a class strategy to shared RunStorage for exposure validation, defaulting
  to its existing validator. The SIS subclass validates explicit manifest binding.

```python
binding = StudyRunBinding.create(cell=cell, matched_seed=17,
    groups=groups, aliases=aliases, node_agent_ids=agents, topic_package=topic,
    schedule=schedule, ws=ws, randomized=randomized, common_inputs_hash='a'*64)
store = StudyRunStorage.create(path, manifest=manifest, **binding.storage_arguments())
```

## Task 2 — Initial state and reopen

- [x] Enforce bound seed/topic/initial stance before initialize_agent changes SQLite.
  Override round-0 replay to enforce the same check on reopen; reuse transaction,
  database identity, lease and exact-cover seal logic rather than copying it.
- [x] Keep legacy attempt/event entry points blocked until SIS event integration.
- [x] Verify six-cell round-0 replay, incomplete initialization/failed initialization
  leave state unchanged, mismatched reopen fails, legacy store tests pass.

## Task 3 — Review and record

- [x] Independent focused review, regression cases for Important findings.
- [x] Targeted tests, Ruff and diff checks; update handoff in this milestone commit.

Next batch: persist SIS pre-dispatch prefix, finalize evidence and atomic successful
event commits, then reopen/resume/checkpoint with full feed provenance. No cloud
dispatch, final protocol freeze or network dynamics result is claimed here.
