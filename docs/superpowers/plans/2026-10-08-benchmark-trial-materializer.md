# Benchmark trial materializer implementation plan

> Execute inline in the existing isolated worktree using TDD; no HTTP, no service startup.

**Goal:** Bind the approved thirty cases to 240 immutable offline trial identities and sixty seeds.
**Architecture:** Reuse frozen-content validation and ArtifactEnvelope. Store full fixed content once per case,
then bind each ordered trial to that content hash. Inventory is not a prompt/wire request or cloud receipt.
**Tech Stack:** Python 3.12, SHA-256 canonical JSON, pytest, existing ArtifactEnvelope.

## Task 1 — Deterministic pure inventory

Files: create `platform/src/agent_ex/identity_network/benchmark_trials.py`,
`platform/tests/test_identity_network_benchmark_trials.py`.

- [x] RED: verify 30×2×4 identities, exact fixed content, common quartet seeds, 60 unique pair seeds,
  immutable records, no caller mutation, rejection of wrong approval and changed/rehashed rows.
- [x] Run only the named test file with existing .test-venv Python, PYTHONPATH=platform/src;
  basetemp/cache_dir are new task-specific temporary directories. Expect missing-module failures.
- [x] GREEN: `build_benchmark_trial_inventory(benchmark, expected_hash=...)` validates first;
  `derive_generation_seed(case_id, repeat_id)` computes project canonical SHA-256 over
  `{namespace:'sis-mc-stage-a-v1',case_id,repeat_id}`, first 8 hex digits as big-endian uint32,
  masked by 0x7fffffff. Reject 60-key seed collisions, no repair or effect-driven seed changes.
- [x] Ordering: frozen case order, repeat 1 then 2, BB/BG/GG/GB. Every trial carries case/ref/hash,
  labels, anonymous source_id=case_id, repeat and seed; source_id never depends on group.
  `replay_benchmark_trial_inventory` rebuilds from approved benchmark and compares the exact artifact.
- [x] Verify scoped tests, Ruff and diff. Save derivation and inventory hashes, not inferred runtime approvals.

Future transport materialization must bind exact renderer/prompt, model/generation limits and runtime
authorization. Retry store/CLI and statistics are separate components; this inventory cannot launch them.
