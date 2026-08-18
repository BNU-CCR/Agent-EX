---
status: resolved; superseded by completed Phase 4B-5 implementation checkpoint
authority: operational recovery record; subordinate to AGENTS.md and the Paper 1 specification chain
created: 2026-08-01
branch: codex/paper1-phase4b
verified-head: b2fe2d69f72bf114b019cf926b449070258452dd
resolved: 2026-08-18
superseded-by: logs/2026-08-01-phase4b5-implementation-checkpoint.md
---

# Phase 4B-5 interruption handoff

## Resolution notice

本断点已于2026-08-18完成恢复并解决，现由
`logs/2026-08-01-phase4b5-implementation-checkpoint.md`中的`complete / independently reviewed`
检查点取代。以下内容作为当时断线状态、恢复顺序和审计要求的历史证据保留，不再表示当前
待办状态。最终独立结果为full `402 passed in 69.92s`、coverage
`402 passed in 204.17s`（2876/419/85%，schedule 638/96/85%）、定向`275 passed`；
规格/反模式与代码质量审查均`APPROVED`，release verification为`PASS`。draft仍含88个
`UNRESOLVED[...]`，制品仍为`mock_only / not_frozen`。完成文档更新前的已验证候选
canonical snapshot为`dc1b81a27919ec9e606c58342fb8771ba6e5ba962bf6c20006ba8f3168d6ea2c`；
文档后release将产生新的最终snapshot。Phase 4B-6尚未开始。

## Safe restart point

- Worktree: `E:\OneDrive\Claude Code\Agent ex\.worktrees\codex-paper1-phase4b`
- Branch: `codex/paper1-phase4b`
- Local/remote committed HEAD before Phase 4B-5: `b2fe2d69f72bf114b019cf926b449070258452dd`
- That commit is the completed and pushed Phase 4B-4 commit: `feat: complete Paper 1 Phase 4B-4 network artifacts`.
- Phase 4B-5 has **not** been committed or pushed. Do not reset, stash, discard, or overwrite the current worktree.
- Phase 4B-6 has not started.

Read, in order, before resuming:

1. root `AGENTS.md`
2. `logs/2026-07-29-phase3a-handoff.md`
3. `docs/project-overview.md`
4. `docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md`
5. `docs/superpowers/plans/2026-07-29-paper1-phase4b-implementation-plan.md`
6. `logs/2026-08-01-phase4b5-implementation-checkpoint.md`
7. this handoff

## Current expected worktree changes

Tracked modifications:

- `docs/superpowers/plans/2026-07-29-paper1-phase4b-implementation-plan.md`
- `platform/protocols/paper1.schema.json`
- `platform/src/agent_ex/__init__.py`
- `platform/src/agent_ex/rng.py`
- `platform/src/agent_ex/schemas/paper1.schema.json`
- `platform/tests/test_domain.py`
- `platform/tests/test_protocol.py`
- `progress.md`
- `task_plan.md`

Untracked Phase 4B-5 files:

- `logs/2026-08-01-phase4b5-implementation-checkpoint.md`
- `platform/src/agent_ex/schedule.py`
- `platform/tests/test_schedule.py`
- this handoff

Interrupted pytest left two untracked temporary directories. They are not project artifacts and must be removed after verifying the exact resolved paths remain inside this worktree:

- `platform/.pytest-tmp-p1-full-final/`
- `platform/.pytest-tmp-p1-cov-final/`

Do not stage either temporary directory.

## Implemented Phase 4B-5 scope

The current uncommitted implementation provides explicit mock-only, not-frozen artifacts for:

- positive attention weights, with primary truncated lognormal and explicit Pareto/equal-weight mock sensitivity families;
- hurdle-Beta expression probabilities and lurker semantics;
- weighted-with-replacement activation schedules;
- externally pregenerated publish flags;
- complete `FrozenSchedule` construction and JSON transport;
- canonical `identity 2 x continuity 2 x exposure 3 = 12` cell reuse with explicit expected matched seed;
- N <= 1000, T <= 50, and events <= 50,000 Phase 4B platform capacity limits;
- compact, auditable event RNG ledgers.

All exact research parameters remain unresolved. Mock candidate values are explicit inputs and must not be represented as formal defaults or frozen choices. Formal draft validation must continue to fail closed while the relevant `UNRESOLVED[P1_*]` values remain.

## Review issues already fixed

Earlier review rounds found and the current code addresses:

1. Winsorization mislabeled as truncation: replaced by versioned, finite-budget true rejection sampling.
2. Floating residuals producing zero/negative attention weights: replaced by stable positive normalization and post-build validation.
3. Missing lognormal location parameter: `log_location` is explicit, finite, required, has no schema default, and participates in payload/input/RNG hashes.
4. Whole-table ordinal-zero RNG: activation and publish use event keys containing each event ordinal.
5. Weak activation/publish source binding: attention, expression, activation, runtime, diagnostics, IDs, hashes, and expected coordinates are deterministically rebound and revalidated.
6. Fake 12-cell coverage: validation requires all twelve canonical distinct cell identities and an explicit expected matched seed.
7. Unbounded public schedule size: Phase 4B capacity limits reject bools and values beyond N=1000, T=50, or 50,000 events.
8. O(N x events) publish diagnostics: replaced by a linear `Counter`-style computation.
9. Repeated 50,000-entry provenance payloads: replaced by compact ledgers. The fixed N=1000/T=50 benchmark shrank from approximately 35.1/50.0 MB to approximately 4.13/5.13 MB for activation/publish JSON.
10. Stdlib `betavariate` internal unbounded loops: replaced by a versioned custom bounded gamma-ratio Beta sampler with an explicit `max_beta_attempts_per_agent` contract and bounded primitive RNG work per attempt.
11. Self-described and O(E) public ledger reconstruction: raw ledgers must be validated once against a trusted root and expected common/source coordinates, producing an immutable validated ledger; `provenance_at(ordinal)` is then O(1).

## Latest completed evidence before the interruption

These results came from the latest bounded-Beta/validated-ledger code unless noted otherwise:

- Schedule tests: `35 passed in 33.43s`.
- Domain + protocol targeted tests: `192 passed in 9.04s` before the final added distribution sanity test.
- Continuous fresh full suite: `354 passed in 68.78s`.
- The most recent completed coverage run was one pure-test addition behind the 354-test snapshot: `353 passed in 210.18s`, `2732 statements / 397 missed / 85%`, schedule module `85%`.
- A final 354-test coverage rerun was running when the connection/allowance ended. It did not produce a trustworthy completion result and must be rerun.
- N=1000/T=50: 50,000 events, build about `26.526s`.
- Trusted 50,000-event ledger one-time validation: about `4.116s`.
- After validation, reconstruction of ordinal 49,999: about `55 microseconds` and structurally verified not to rescan the full digest.
- Activation JSON: about `4,125,549 bytes`.
- Publish JSON: about `5,133,014 bytes`.
- JSON round-trip equality passed.
- Bounded Beta sanity: 2,000 explicit mock Beta(2,2) draws were strictly inside `(0,1)` and had mean within `0.5 +/- 0.03`.
- Extreme `alpha=beta=1e308` with a tiny attempt budget failed closed quickly without calling stdlib `betavariate`.
- Ruff and format checks passed on the latest code before the interrupted coverage run.

Do not treat these as final release evidence until the fresh reruns below complete on the current snapshot.

## Exact next actions

1. Verify `git status` and remove only the two exact interrupted pytest temporary directories listed above.
2. Re-run the schedule targeted suite.
3. Re-run a continuous fresh full suite with a workspace-local `--basetemp`.
4. Re-run fresh full coverage on all 354 tests; record statements, misses, total percent, and schedule percent.
5. Re-run the N=1000/T=50 benchmark, JSON round-trip, compact sizes, one-time trusted-ledger validation, and O(1) single-ordinal reconstruction.
6. Re-run Ruff check, Ruff format check, `pip check`, `git diff --check`, schema mirror equality/hash, formal unresolved gates, and Git hygiene.
7. Obtain fresh independent reviews on the **current** snapshot:
   - code quality re-review of bounded Beta and validated typed ledger;
   - specification/anti-pattern review confirming the compact ledger still preserves per-event ordinal keys and that the explicit Beta attempt budget remains mock-only/not-frozen;
   - independent release verification with hash-consistent tampering attacks.
8. If all reviews approve, update the checkpoint/plan/progress/task plan from `pending re-review` to `complete / independently reviewed`, then run one final release verification after documentation changes.
9. Commit only the verified Phase 4B-5 files. Suggested message: `feat: complete Paper 1 Phase 4B-5 frozen schedules`.
10. Push `codex/paper1-phase4b`, verify local HEAD equals the remote branch, and only then consider Phase 4B-6.

## Required attack cases for the final reviewers

- Extreme Beta shapes cannot hang and exhaust a true primitive-work budget.
- Non-lurker expression probabilities are always strictly inside `(0,1)`; lurkers remain exactly zero.
- Missing or changed `log_location`, Beta attempt budget, runtime, diagnostics, source IDs/hashes, or RNG coordinates are rejected even after rebuilding a hash-consistent envelope.
- A raw ledger with changed common/source coordinates and a recomputed digest/root is rejected against trusted expected coordinates.
- Raw mappings cannot use the public single-event reconstruction path; only validated typed ledgers can.
- Validated single-event reconstruction performs no full-ledger digest scan.
- Ledger counts reject bool, negative, nonzero start, and values over 50,000.
- N=1001, T=51, oversized events, wrong matched seed, duplicate/missing/noncanonical cells, and cross-cell redraws fail closed.
- Long but otherwise valid agent IDs are not rejected merely by benchmark JSON-size thresholds.
- Publish remains externally pregenerated, lurkers never publish, attention and expression remain independent in the primary mock path, and no opinion/private-state input is read.

## Prohibited recovery shortcuts

- Do not reset or regenerate the implementation from the Phase 4B-4 commit.
- Do not use the earlier 346/348/350-test approvals as final approval for the latest bounded-Beta/validated-ledger snapshot.
- Do not stage pytest temporary directories.
- Do not introduce formal defaults to make tests pass.
- Do not mark any mock artifact as frozen.
- Do not start feed, memory, event-engine, or other Phase 4B-6 work before Phase 4B-5 is independently approved, committed, and pushed.
