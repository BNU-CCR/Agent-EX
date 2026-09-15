---
status: focused local release gates passed; cloud smoke not executed
authority: Phase 0A-1 smoke-recovery Task 7 local evidence only
comparison-baseline: c9ad22a75a97368338946ba69124e76bfe6b88e5
verified-implementation-head: b197ba2b259be8715a82e4ca8504ed94a55b9012
last-verified: 2026-09-15
---

# Phase 0A-1 smoke-recovery local release

## Boundary

This record covers only the focused Windows/local release gates for the recoverable
ten-request smoke command and host-lifecycle surface. It does not claim a current cloud
preflight, installation, model download, running vLLM service, real-model response,
authorization for the 816-case calibration inventory, Phase 0B, or the formal Paper 1
experiment.

The owner requested the shortest scientifically valid path to formal execution. The
approximately 80-minute full historical suite is therefore **DEFERRED by owner request;
no pass claim**. Cosmetic documentation, unreachable compatibility cleanup, nonessential
refactors, and duplicate slow checks are outside this release's critical path.

## Exact verification evidence

- Focused smoke-recovery suite: `297 passed in 440.25s (0:07:20)`; this was not
  the full suite.
- Ruff check: passed.
- Ruff format check: `27 files already formatted`.
- Dependency consistency: `No broken requirements found`.
- Baseline-to-head and worktree whitespace checks: passed.
- Tracked SSH and known-host material: no tracked match.
- Tracked raw response, attempt, sealed/staging store, service-generation, SQLite,
  database, and coverage artifact scan: no match.
- Verified implementation head before this evidence-only commit:
  `b197ba2b259be8715a82e4ca8504ed94a55b9012`.
- The exact clean release commit and deployment bundle SHA-256 are captured in the
  create-only receipt stored beside the bundle after this evidence commit. They cannot
  be embedded in this commit without changing the commit they identify.

## Result and next gate

The focused local gates passed. The cloud instance must remain off until the exact clean
deployment bundle is created and verified immediately after this record is committed. The
next external action is then a new read-only preflight on a current AutoDL endpoint,
followed by materialization and explicit owner approval of one complete new
`SmokeManifest.record_hash` before any installation, download, service startup,
diagnostic, or model request.

Even a passing ten-request smoke grants no authority to execute the separately approved
816-case calibration inventory, Phase 0B, or the frozen N=1000/T=50 formal protocol.
