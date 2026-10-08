# Stage-A local runner Implementation Plan

> **For agentic workers:** Execute inline with test-driven-development; scoped review before acceptance. No cloud/model calls.

**Goal:** Implement the approved 240-request benchmark and separate two-request technical preflight.
**Architecture:** Keep legacy v1 untouched. A benchmark-only adapter adds frozen top_k/min_p to exact wire; a dedicated SQLite v2 journal stores intent before HTTP, saved response before parsing, and replay-verified resolution. CLI performs cold source/runtime/approval validation before network dispatch.
**Tech Stack:** Python 3.12, stdlib SQLite/HTTP, existing Linux writer lease and typed vLLM transport evidence.

**Local acceptance:** Tasks 1–3 below implemented and scoped tests passed (103 passed,
2 Linux kernel-only skips on Windows, 2026-10-08). Original checklist retained as the
test-first plan; actual evidence is in progress.md. Native Linux/service/preflight
acceptance remains pending separate cloud authorization, not hidden by local tests.

## Task 1: renderer and sampling binding

Files: benchmark_transport.py, new benchmark_adapter.py, test_identity_network_benchmark_transport.py.
- [ ] Add regression: exact approved system and five parameters are present in every wire.
- [ ] Run named test (must fail with old triple/control).
- [ ] Implement benchmark adapter with fixed parameter equality, old typed request retains triple but adapter binding includes complete sampling policy.
- [ ] Cold rebuild saved candidate; reject drift. Preflight changes event/request identities and uses first BB/BG only, never adds to 240 outcomes.
- [ ] Run transport and wire tests.

## Task 2: saved response / SQLite v2

Files: benchmark_store.py, benchmark_response.py, test_identity_network_benchmark_store.py.
- [ ] Tests: durable INTENT before HTTP; crash after INTENT cannot resend; saved response parsed on reopen without HTTP; 3 parse-invalid attempts stop; readonly replay detects changed response/hash/schema.
- [ ] Implement SQLite FULL/DELETE with Linux lease. Short transactions only; append intent/response/result separately. Full cold replay on open/verify; normal operation checks only current prefix/database generation, no per-event full scan.
- [ ] Strict output: duplicate keys/extra text/extra fields/wrong order/type/label refused; confidence is strict 1..5; Chinese reason string retained as secondary, not auto-sycophancy code.
- [ ] Verify saved transport bindings/classification before retry decisions; timeout/unresolved/5xx ambiguous stop.
- [ ] Run named tests, keep legacy SQLite contract unchanged.

## Task 3: runtime authorization, CLI and report

Files: benchmark_cli.py, benchmark_run.py, test_identity_network_benchmark_cli.py.
- [ ] Tests: no approval/no complete runtime => no HTTP; wrong source/packet hash rejected; preflight independent IDs; run/resume/verify/report replay identical counts; partial result cannot pass or enable Stage-B.
- [ ] Require explicit runtime identity (model revision, tokenizer/chat-template hashes, vLLM version, BF16/nonthinking), source commit and user receipt binding packet/runtime/source hashes.
- [ ] CLI materialize/inspect offline; run/resume Linux-only with lease; verify/report read-only. Reports omit response text; complete verified 240 only enters frozen analysis.
- [ ] Save exact ingroup/outgroup examples and command guide without real outputs.
- [ ] Run bounded acceptance, Ruff and diff checks. Record Linux kernel-lock/service acceptance still requires cloud preflight; do not claim empirical results.

## Authorization boundary

Renderer/sampling approval is not launch approval. No SSH, upload, service start or model request in local implementation. Stop after local verification and ask user separately to start server/authorize preflight. Stage-B disabled throughout.
