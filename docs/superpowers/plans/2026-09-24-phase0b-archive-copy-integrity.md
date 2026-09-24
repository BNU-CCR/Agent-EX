# Phase 0B Judge Archive Copy Integrity Implementation Plan

Execution checkpoint (2026-09-24): Task 1's exact tree inventory is implemented and independently re-reviewed (`7 passed, 1 skipped` on Windows; real symlink negative case awaits Linux). Junction and path-swap negatives were added test-first. Task 2's destination `JudgeRunStore.open` replay gate is not implemented. An equal source/destination tree is not yet a valid migration proof.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove a copied judge `run-store` has the exact source directory/file tree and byte-identical regular files, then require the copied store's own terminal replay before claiming a valid migration copy.

**Architecture:** A read-only tree inventory scans source and destination without following links, includes empty directories, and computes streaming SHA-256 for every regular file. A small verifier requires exact inventory equality and then calls the existing `JudgeRunStore.open` on the *destination*, which already checks exact staging layout and full journal/projection replay. Because `open` may recover transactions, a final inventory check detects any mutation and fails rather than silently accepting a changed copy.

**Tech Stack:** Python 3.12 pathlib/os/hashlib; existing `JudgeRunStore` and canonical hash; pytest/Ruff.

---

## Task 1: Exact read-only tree inventory

**Files:** Create `platform/src/agent_ex/phase0b/archive_copy.py` and `platform/tests/test_phase0b_archive_copy.py`.

- [x] Add tests using `tmp_path`: an empty directory plus two files yields sorted relative directory/file entries and stable SHA-256; changed bytes, a missing file, an extra file, an extra empty directory, and a symlink must not be treated as the same archive. Example core assertion: `assert inventory_tree(source).record_hash == inventory_tree(copy).record_hash` before changing the copy, then `with pytest.raises(ValueError): verify_tree_copy(source, copy)` after the change.
- [x] Run the new test module with the project test Python and a fresh `--basetemp`; observe RED because `agent_ex.phase0b.archive_copy` is missing.
- [x] Implement `ArchiveTreeInventory` with `directories: tuple[str, ...]`, `files: tuple[tuple[str, int, str], ...]`, `record_hash`, and `inventory_tree(root: Path)`. Reject root links, all linked/special children, and path collisions. Hash each regular file in fixed-size blocks; include relative POSIX paths and empty directories in the canonical record hash. `verify_tree_copy(source, destination)` returns the one verified typed inventory shared by both trees or raises on any mismatch.
- [x] Re-run the new test module and record GREEN. Commit only the new module/tests after `ruff check`, `ruff format --check`, and `git diff --check`.

## Task 2: Destination judge replay gate

**Files:** Extend `platform/src/agent_ex/phase0b/archive_copy.py` and `platform/tests/test_phase0b_archive_copy.py`.

- [ ] Add a failing test where source and destination contain the same deliberately incomplete `staging` tree: tree hashes match, but `verify_judge_archive_copy(source, destination)` must reject because the store is not openable. Add a positive fixture using an existing small judge-store builder if available; the positive result must bind the destination terminal projection hash and 797 unique coded items with zero unresolved intents.
- [ ] Observe RED for the missing `verify_judge_archive_copy` function or its absent replay gate.
- [ ] Implement `verify_judge_archive_copy` as: compare whole-tree inventories; call `JudgeRunStore.open(destination)`; require `staging/projection.json`, exactly 797 unique coded terminal items and no unresolved intent; inventory the destination again and require it unchanged; return the inventory record hash and verified projection record hash. Do not open source in a mode that may recover or rewrite it, and do not read or print raw response contents.
- [ ] Run the new module plus `test_phase0b_cold_handoff.py` and `test_phase0b_service_bridge.py`, then Ruff and staged `git diff --check`. Commit only touched files and the planning/progress entries.

## Explicit boundary

This local implementation does not copy data, inspect the old host, prove the source tree was already complete, or authorize Phase 0B dispatch. In real migration the source must first be quiescent and independently verified; the destination must be verified on Linux with actual copied bytes and a new host/service identity. Large inventory and raw files remain outside Git.
