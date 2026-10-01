# Manipulation Request Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans inline in the existing isolated worktree; limited independent review after the task. Preserve other edits.

**Goal:** Cold-derive an immutable ordered transport inventory from exact Stage-A sources and scoped approval, with reusable request objects and no I/O or send permission.

**Architecture:** A focused `manipulation_requests.py` owns one-time materialization and cold validation. It reuses typed vLLM requests and wire encoding, retains full source evidence in its plan, and never advances study state. This is the first independently testable part of the human-approved runner, not its completion.

**Tech Stack:** Existing Python runtime, ArtifactEnvelope, Phase0BVllmEventRequest/Adapter, pytest, Ruff. No new package or server.

## Task 1 — Source-bound ordered requests

Execution status: implementation and limited independent review complete. Initial three
missing-module failures were observed before implementation; final targeted run: 3 passed.
All acceptance steps below are satisfied; final format/diff checks and local save follow.

Files: create `platform/src/agent_ex/identity_network/manipulation_requests.py` and
`platform/tests/test_identity_network_manipulation_requests.py`; update this plan and progress.

- [x] Write missing-feature tests using this exact API:

```python
plan = build_manipulation_request_plan(auth=auth, receipt=receipt, evidence=evidence,
                                       checked_at="2026-10-01T00:05:00Z")
requests = validate_manipulation_request_plan(plan, checked_at="2026-10-01T00:05:00Z")
assert len(requests) == auth.payload["trial_count"]
assert plan.payload["dispatch_authorized"] is False
assert len({r.request_id for r in requests}) == len(requests)
```

- [x] Run `python -m pytest platform/tests/test_identity_network_manipulation_requests.py -q --tb=short`; expect missing module/function failures.
- [x] Implement builder: full `validate_manipulation_dispatch_approval` once; read the already-validated inner pack from source evidence, common parser/adapter/policy from candidate, and typed topic from candidate binding. Build one ordered request for every frozen trial:

```python
event_id = "sis-check-event-" + canonical_payload_hash(
    {"authorization": auth.output_hash, "trial_id": trial["trial_id"]})
request = Phase0BVllmEventRequest.create(
    event_id=event_id, attempt_index=1, prompt_hash=trial["prompt_hash"],
    rendered_messages=tuple(dict(m) for m in trial["messages"]),
    generation_settings={"temperature": float(settings["temperature"]),
                         "top_p": float(settings["top_p"]),
                         "max_tokens": settings["max_tokens"]},
    model_seed=trial["sampling_seed"], adapter_binding_hash=adapter.record_hash)
```

Record original approved settings separately: numeric float normalization is transport typing, not a new research value. Encode exact wire bytes through the existing no-network adapter `_request_body`; retain SHA-256 and JSON wire payload. No default seed, timeout, generation, parser limit or model.

- [x] Plan schema `paper1.identity-network.manipulation-request-plan.v1`: full preflight request, ordered `{trial_id, request, wire_payload, wire_sha256}` entries, explicit adapter/parser/policy/topic, source/input hashes and false-authority metadata. IDs must be unique. Source receipt and order are immutable; no synthetic authority or retry.
- [x] Cold validator parses the complete saved preflight request, runs the same source/approval replay and builder, then requires whole-plan equality. Reject fully rehashed message, seed, order, wire model, timeout/policy or metadata substitutions. Return only typed requests, not mutable wire dictionaries.
- [x] Test exact original messages, seeds, generation and wire fields for all four synthetic trials; same cold result across JSON roundtrip; repeated hot request access does not re-invoke the builder. Tests use actual source fixtures, not mock validators.
- [x] Run the named tests, Ruff lint/format and `git diff --check`, request limited independent review, fix Important/Critical with RED→GREEN, commit the module/tests/progress only after fresh checks.

## Subsequent runner deliveries mapped to the approved spec

This plan intentionally covers only the input component; do not label the complete runner done.
The following separately testable implementation batches retain the full goal:

| Batch | Files/responsibility | Required acceptance |
|---|---|---|
| Dedicated store | `manipulation_store.py`, `manipulation_lock.py`, corresponding tests | immutable full plan, single writer, READY/INTENT/RESPONSE_STORED/VALID/INVALID, intent before HTTP, exact prefix and transport/body/parse replay, fresh/no-overwrite |
| Transport loop | `manipulation_runner.py`, corresponding tests | same validated inventory, explicit policy timeouts, no shared state, saved response local resume, ambiguity/invalid stops, no automatic retries, crash injections and O(n) cold/O(1) incremental path |
| Standalone operator | `execution_origin.py`, `manipulation_cli.py`, corresponding tests/runbook | clean approved loaded package source, strict full request, exact authorized root, run/resume/readonly verify/report, no raw output, Linux lock/health gates |
| Real candidate | versioned repetition/analysis/source files after human research decisions | user240 proposal, actual30case provenance, explicit repeat seeds, no StageB/no-signal defaults; exact approved bundle/receipt/operator packet before cloud startup |

Write each next batch's concrete TDD plan before its production changes. The approved design supplies their invariants; no extra conceptual approval is required for implementing it. Research sampling/statistics choices still need their own decisions.
