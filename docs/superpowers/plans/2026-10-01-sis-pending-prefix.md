# SIS atomic PENDING prefix

> **For agentic workers:** Execute inline using test-driven-development; independent review before commit.

**Goal:** Persist a genuine SIS input/policy/adapter/request/PENDING prefix in existing SQLite v6 tables, with cold reopen and atomic rollback.

**Architecture:** A discriminated stored-input v2 wraps the typed SIS input plus full causal snapshot. Shared diagnostic code consumes a protected neutral input projection; the default still requires legacy EventInputEvidence. SIS validates its actual current SQLite sources, common execution artifact and explicit candidate authorization hash before and during replay. This stage deliberately allows only an uncommitted current-event PENDING prefix, not dispatch/response/terminal/commit or past-event replay.

**Tech Stack:** Python, SQLite v6, existing diagnostic contracts and generation-attempt lifecycle.

- [x] Write `platform/tests/test_identity_network_prefix.py`: six cells persist/close/open, exact table cover, same-event PENDING idempotency, wrong authorization rollback, SQLite insert interruption rollback, legacy reader rejection and cold evidence tamper rejection. Run isolated pytest; expect absent stored-input API RED.
- [x] Add `identity_network/stored_input.py` with exact schema, nested input/snapshot hash and feed/memory replay. Preserve source rows, selected/expired IDs, cursor and prompt evidence.
- [x] Add neutral `_diagnostic_input_projection` and request-contract hook to shared storage, using them only in diagnostic prefix/replay; legacy defaults remain strict. Extend schema decoder explicitly, not field duck typing.
- [x] In SIS storage load full `identity_network_execution_inputs` and `sis_diagnostic_authorization_hash` from manifest when present. Validate stored inputs against current state/chain/schedule/graph/alias/groups and actual public/private rows, render exact expected prompt, verify explicit artifact policies/request settings/model seed/authorization. Reuse the existing atomic prefix transaction. Reject incomplete manifests and legacy inputs before writing.
- [x] Verify prefix and legacy storage suites, Ruff/format/diff, independent review, record boundary. No cloud or successful event commit is claimed. Later response/finalization/commit work must extend historical input replay before opening later events.

Final: 371 passed, 2 Windows/POSIX environment skips; Ruff/format/diff clean.
Review finding closed with explicit PENDING-only lifecycle guard and response-write gates.
