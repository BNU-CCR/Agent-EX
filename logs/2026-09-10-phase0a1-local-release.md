---
status: complete local release verification; cloud smoke not executed
authority: Phase 0A-1 Task 8 local verification evidence
comparison-baseline: 672687e765320238bdbeb362b13e66cc43e9bd36
verified-head: 277f9ef7159759d8d868ce72b6e99a63d741db63
last-verified: 2026-09-14
---

# Phase 0A-1 local release verification

## Boundary

This record closes only Task 8 of the approved Phase 0A-1 implementation plan: the
Windows/local release gates for the cloud-probe command surface. It does not claim a
current cloud preflight, a model download, a running vLLM service, a real-model smoke
response, approval of the six 816-run artifact groups, a frozen runtime, or authority
to start the formal Paper 1 experiment.

The comparison-baseline ancestor check passed for
`672687e765320238bdbeb362b13e66cc43e9bd36`. The verified implementation head was
`277f9ef7159759d8d868ce72b6e99a63d741db63`. At verification time the branch was one
commit ahead of `origin/codex/paper1-phase0`; this evidence record is the next planned
commit.

## Exact verification evidence

- Phase 0A-1 focused suite: `86 passed in 351.37s`; no skip or xfail.
- Fresh full suite: `1580 passed, 2 skipped, 1 deselected in 3815.22s (1:03:35)`.
- Fresh coverage suite: `1580 passed, 2 skipped, 1 deselected in 10743.04s
  (2:59:03)`; production total `16,991 statements / 2,693 missed / 84%`.
- Ruff check: passed.
- Ruff format check: `91 files already formatted`.
- Dependency consistency: `No broken requirements found`.
- Baseline-to-head and worktree `git diff --check`: passed.
- Tracked runtime-artifact scan for raw responses, attempts, sealed/staging stores,
  coverage databases and SQLite files: no match.

The plan's broad credential-assignment expression matched five pre-existing internal
Python identifiers in `protocol.py` and `prompt.py` named `token`. These are placeholder
parsing and in-process validation-seal objects, not credentials and not secret values.
The baseline-to-head diff matched only adversarial test fixtures containing literal
fake secret text; production-source inspection found no API key, authentication token,
or secret-value assignment introduced by Phase 0A-1.

## Result and next gate

Task 8 local release verification is complete. The cloud instance should remain off
until Task 9 begins. Task 9 must start from a newly rented/current host endpoint and run
the versioned read-only `agent-ex-phase0a1 preflight` before any environment install or
model request. The ten real smoke prompts remain separately authorized and must not be
confused with the 816-case run; the latter remains blocked on six exact-hash approvals.
