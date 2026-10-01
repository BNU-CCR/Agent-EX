# SIS SQLite input snapshot implementation plan

> **For agentic workers:** Execute inline with executing-plans and test-driven-development.

**Goal:** Construct the next SIS prompt from actual committed SQLite state without dispatching or modifying it.

**Architecture:** StudyRunStorage holds the writer lease and reads one SQLite snapshot. It derives neighbors from the bound graph, reuses finite unread feed and private memory primitives, and returns a preliminary ArtifactEnvelope containing all causal source rows and exact prompt evidence. Event persistence remains gated.

**Tech Stack:** Python, SQLite v6, pytest, shared feed/memory and SIS renderer v2.

## Task 1: Snapshot and boundaries

- [x] Add `platform/tests/test_identity_network_snapshot.py`: six cells, actual graph neighbors/public rows, private history, deterministic replay, no mutation, lease and round-0 rejection.
- [x] Run `python -m pytest platform/tests/test_identity_network_snapshot.py -q`; observed 7 missing-method failures (RED).
- [x] Add `StudyRunStorage.snapshot_next_input(*, persona_text, feed_capacity, memory_window)`. Require lease/seal/nonterminal schedule; BEGIN read transaction, verify store, derive graph neighbors by frozen node mapping, load unread public posts and receiver history, select via shared feed/memory, render exact SIS prompt, package source rows/policies/binding/chain head. ROLLBACK read transaction in finally. No network, no database writes, no defaults.
- [x] Run snapshot, SIS storage/input/execution and shared feed/memory tests; 114 passed in 24.18s; Ruff/format/diff checks passed.
- [x] Focused independent review: no Critical/Important; optional oversubscription coverage added. Updated progress and handoff. This stage does not authorize a cloud run or complete causal-prefix persistence.
