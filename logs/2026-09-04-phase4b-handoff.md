---
status: complete / independently reviewed; ready for Phase 0A/0B
authority: verified Phase 4B implementation evidence and recovery handoff
last-verified: 2026-09-04
---

# Paper 1 Phase 4B implementation handoff

## Boundary

Phase 4B is a mock-only engineering release. It does not freeze any
`UNRESOLVED[...]` research value, connect Qwen/vLLM, call a real API, or produce a Paper 1
result. Passing this handoff means the platform may enter Phase 0A/0B calibration; it does
not authorize the formal N=1000/T=50 matrix.

## Code and commits

- Worktree: `E:\OneDrive\Claude Code\Agent ex\.worktrees\codex-paper1-phase4b`
- Branch/upstream: `codex/paper1-phase4b` / `origin/codex/paper1-phase4b`
- Task 0 baseline: `705b9a8` (`fix(platform): expose reconciliation and version checkpoints`)
- 4B-9 plan: `3443226`
- Task 1: `9011cd3`; Task 2: `c76c294`; Task 3: `44ef94c`; Task 4: `0c4ec46`
- Task 5: `c128ca8`; Task 6: `c5e071f`; Task 7: `7749609`
- Task 0--7 implementation range: `705b9a8..7749609`

Resume without secrets:

```powershell
git fetch origin
git switch codex/paper1-phase4b
git pull --ff-only origin codex/paper1-phase4b
cd platform
.\.venv\Scripts\python.exe -m pytest -q
```

On a cloud/Linux checkout, create a Python 3.12 environment from the locked project
metadata rather than copying `.venv`, then rerun the release gates before any real-model
calibration.

## Verified matrix and recovery evidence

- N=20/T=2 recovery covers `after_pending`, `after_in_progress_reconciled`,
  `after_invocation`, `after_terminal_success`, `after_sqlite_commit_before_context`, and
  `after_checkpoint_write`. All six recovered comparable projection hashes equal their
  uninterrupted controls. Exact recovery adapter-call counts are: `after_pending=1`;
  `after_in_progress_reconciled=0`; `after_invocation=0`; `after_terminal_success=0`;
  `after_sqlite_commit_before_context=0`; `after_checkpoint_write=0`. The first branch
  legitimately performs its not-yet-made invocation; every later branch rejects resend.
- N=100/T=1 executes all 12 canonical cells and 1,200 genuine mock events. Every cell has
  a distinct run ID and SQLite file. Shared schedule hash is
  `da387ac2021d6ccca6292bcaef7ad80c0296dd27f2217edbeda202eb7fbeb45d`; shared artifact-set
  hash is `0b9a5baf90de39dd974589a0a32196e1677ab5e7e5d0113f077f82c26c4a4a1e`.
  E2 WS hash is `df05870b3a77957b4d08a458946f3eb42ca1143667ffed1e715d3f8945705728`;
  E1 shadow hash is `f20a551abc9fd48a84e414b6e7143c0573246f03f6ff0eff36c4b3a84a9f2ba0`.
  A separate N=100/T=1 cell executes events 0--49, closes/reopens, then makes exactly 50
  adapter calls for events 50--99; its completed comparable projection hash equals the
  uninterrupted 100-event control.
- N=1000/T=50 shape validation exact-covers 12 cells, each with 50,000 continuous event
  slots and a unique run ID. N=1000/T=1 recovery closes/opens at ordinals 1 and 500,
  injects a post-invocation crash at 500, proves zero resend, completes at 1,000, reopens,
  and matches the uninterrupted comparable projection hash.
- The explicit release cell `P1-I1-C1-E2` passed 50,000 real mock pipeline events:
  `1 passed, 4 deselected in 20708.39s (5:45:08)`. Measurement:
  `elapsed_seconds=20555.347`, `peak_memory_bytes=3236920043`,
  `sqlite_bytes=2969907200`, `checkpoint_count=1`,
  `checkpoint_bytes=20405320`, `audit_bytes=98414822`.
- Before deletion, the release SQLite SHA-256 was
  `ab2fdee487797a44f79cb14a41a214566c3b1c72914c16a7c5cc4af73e37662d`; the checkpoint
  file SHA-256 was `494877d6314bd65c310fe09289dfeb46bdd9f180b8e290385d9d68b0f7533e1`.
  The temporary SQLite/checkpoint files were then removed and are not Git artifacts.

The first 50,000-event attempt completed its event prefix but exposed a genuine generic
defect: checkpoint v4's 250,001 ordered v6 evidence hashes plus execution IDs exceeded the
old 16 MiB I/O ceiling. A RED regression reproduced the valid large payload and initially
raised the ceiling to 32 MiB. Final review correctly rejected merely raising it again for
retry history. New writes therefore use compact checkpoint v5: historical failure and
authorization bodies remain in authoritative SQLite, while the checkpoint stores their
ordered content hashes plus minimal causal references. Legacy v3/v4 remain readable and
validatable. A real synthetic 50,000-event/one-authorized-retry-per-event v5 envelope is
81,119,908 bytes, passes typed construction plus atomic write/load round-trip under a 96 MiB
file bound and a 1.5 GiB measured peak-memory budget. This is a capacity envelope, not a
retry-policy default; formal retry limits must be rebound at freeze. The original v4 database
reopened and produced a 20,405,320-byte `complete/current` checkpoint before the migration.

## Clock, audit, and storage contracts

- The N=100 deterministic clock binding is
  `mock-clock-060a4210fe9336e22182a7a43fcac1919fafaeb0b0b4767237bdbe4257be9324` with hash
  `060a4210fe9336e22182a7a43fcac1919fafaeb0b0b4767237bdbe4257be9324`.
  Tests cover fresh success; failed attempt plus authorized retry; pending and IN_PROGRESS
  reconciliation; persisted invocation success/failure; landed success; and already-complete
  recovery. Clock consumption is rebuilt from durable typed evidence and remains owned by
  the constructor-bound pipeline, not by the run harness.
- Process outputs retain the fixed label `exploratory/process_diagnostic`. The terminology
  map ID is `paper1.phase4a1.terminology.v1`, hash
  `b3444ae6e4c0ab563b9eb593f52315104c1bde8b767fe651e0e76402124885b2`, and payload is
  `{identity: 人口身份线索可见性, continuity: 历史立场一致性要求,
  private_state: 非公开Agent立场状态, public_post: Agent可见话语分布}`.
- Runtime storage is SQLite schema v6. New checkpoints write compact v5; legacy v3 and
  full-history v4 are accepted only through their historical projections and are tested as
  exact/current or valid stale prefixes, never silently upgraded into v5 semantics.

## Release gates

- Task 7 focused scale suite: `4 passed, 1 deselected in 580.98s`.
- Matrix/run/process suite: `130 passed in 247.51s`.
- Checkpoint suite after compact v5 migration: `102 passed in 89.92s`; the genuine large
  v5 atomic write/load capacity node, now using 50,000 consecutive event identities and one
  failed attempt plus authorization per event, passed in `94.19s`; the same run directly
  verified a legacy full-history v4 stale prefix.
- Final default full: `1124 passed, 2 skipped, 1 deselected in 1031.80s`; the deselected
  node is the explicitly excluded 50,000-event release gate.
- Final coverage: `1124 passed, 2 skipped, 1 deselected in 2940.43s`; production total is
  `10,795 statements / 1,589 missed / 85%`.
- Exact draft/formal, generated-summary, schema-mirror, packaged-schema and isolated-wheel
  nodes: final independent verification `6 passed in 6.39s`. Ruff check, Ruff format check
  (56 files), `pip check`,
  `git diff --check`, and tracked-artifact hygiene: pass.
- Independent specification, code-quality and final-verification re-reviews are `APPROVED`/
  `PASS` with no P0--P3. The final verifier independently reran the six exact nodes
  (`6 passed in 6.39s`), three critical compact-v5/atomicity/snapshot nodes
  (`3 passed in 1.52s`), static gates and tracked-artifact hygiene.

## Completion audit

1. Phase 4B-8C-3 is complete and independently reviewed with no P0--P2; its three release
   reviews and fresh `979 passed, 2 skipped` evidence are preserved in
   `logs/2026-09-01-phase4b8c3-evidence-pipeline.md`.
2. The three typed scale fixtures and every assembled run retain exact
   `mock_only: true`, `research_parameter_status: not_frozen`, and
   `formal_parameter_authority: false` validation.
3. N=100 completes all 12 canonical cells and 1,200 strictly serial events; matrix invariant
   and pre-execution attack tests bind every approved shared/differing artifact.
4. N=1000/T=50 has separate 12-cell shape evidence and one genuine 50,000-event single-run
   pipeline execution; the latter is not rerun by default full/coverage.
5. N=20 six-prefix, N=100 close/open at event 50, and N=1000/T=1 post-invocation recovery
   tests match uninterrupted comparable projections and prove the recorded resend counts.
6. Process-audit tests cover private state, public stock/flow, exposure diagnostics and
   mechanical label deltas without choosing an outcome direction.
7. Audit provenance binds the approved terminology-map ID/hash/payload plus model, prompt,
   topic and robustness identities.
8. The six exact protocol/schema/summary/formal/install/wheel nodes pass while unresolved
   formal values remain fail closed.
9. Fresh full, coverage, static, format, dependency and diff gates all pass with the exact
   counts above.
10. This handoff records branch/commit recovery, environment, hashes, resource observations,
    Windows limitations and the Phase 0A/0B next boundary.
11. The strict tracked-artifact scan has zero SQLite, checkpoint, raw-response, cache,
    coverage or `.codex/` matches; large runtime artifacts remain outside Git.

## Remaining boundary

Windows 11, Python 3.12.13, and SQLite 3.53.1 produced the evidence above. Windows tests do
not prove Linux filesystem, CUDA, vLLM, GPU-memory, driver, container, or real-model behavior.
Phase 0B must rerun the platform gates on the selected cloud/Linux image and then perform
real N=20/50/100 calibration. Formal config remains deliberately fail closed until all
research-QA decisions, model/tokenizer revision, chat-template and image/dependency hashes,
B/K, retry/timeout, generation parameters, performance gates, analysis formulae, and archive
URI are frozen and approved.
