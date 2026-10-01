# Manipulation SQLite Store Implementation Plan

> **For agentic workers:** Use subagent-driven-development, TDD and separate spec/quality review in the existing isolated worktree. Preserve other edits; do not run cloud or full-repo tests.

**Goal:** Persist an exact independent manipulation inventory and atomic intent/response/terminal history, with cold replay and safe local-only saved-response recovery.

**Architecture:** `manipulation_evidence.py` owns typed response binding and pure parser replay. `manipulation_store.py` owns a dedicated SQLite database, immutable full-plan inventory and append-only phase records. It requires the already-implemented Linux writer lease for mutations; local tests explicitly simulate only this OS boundary, using real SQLite and full input derivation.

**Tech Stack:** Python sqlite3/os/pathlib, existing ArtifactEnvelope, transport/parser contracts, pytest/Ruff. No new dependencies or model calls.

## Task 1 — Dedicated store and evidence replay

Create `platform/src/agent_ex/identity_network/manipulation_evidence.py`,
`platform/src/agent_ex/identity_network/manipulation_store.py` and
`platform/tests/test_identity_network_manipulation_store.py`. Approved runner spec remains
`docs/superpowers/specs/2026-10-01-identity-manipulation-runner-design.md`.

Integration bug amendment: also update `manipulation_requests.py` and its named test file
only for sorted-JSON wire portability. Controller reproduced cold replay failure after
`json.dumps(plan.to_payload(), sort_keys=True)`; the first entry differs only in wire SHA
because message keys change role/content → content/role. Source messages already validate
exact fields. Normalize them to `{"role": m["role"], "content": m["content"]}` both when
building and returning typed requests; no shared adapter or legacy wire change. Add a RED
sorted-JSON roundtrip test which checks returned request encoding against saved wire hash,
then verify GREEN. This changes no message, seed, model, treatment or research setting.

Review amendment: protect the post-COMMIT hot-cache guard as well as the cold read snapshot.
An external committed edit between the append COMMIT and guard capture must not become a
trusted baseline without source/history replay. Add a deterministic RED→GREEN injection
for metadata/older-transition corruption at that boundary; retain O(1) normal writes.

- [x] Write tests first using full source fixture `bound` from manipulation-request tests,
  typed transport evidence and explicitly mocked syscall lease fixture from writer-lock tests.
  Real SQLite must prove create/reopen plan equality, exact ordered inventory, no overwrite,
  permission/closed/wrong-root lease rejection, and this public API:

```python
store = ManipulationStore.create(root, plan=plan, checked_at=checked_at, lease=lease)
request = store.requests[0]
store.record_before_dispatch(request, exact_wire_bytes)
assert store.summary()["phase"] == "INTENT"
store.close()
store = ManipulationStore.open(root, plan=plan, checked_at=checked_at, lease=lease)
# New dispatch is forbidden while the saved INTENT has no response.
store.store_response(synthetic_typed_response)
assert store.summary()["phase"] == "RESPONSE_STORED"
store.terminalize_saved_response()
assert store.summary()["valid_count"] == 1
store.close()
summary = ManipulationStore.verify(root, plan=plan, checked_at=checked_at)
assert summary["formal_parameter_authority"] is False
```

`root` is an existing trusted archive directory containing the held lock; storage requires
fresh absent `manipulation.sqlite3`, not a new root. Future operator CLI creates the exact
authorized fresh directory before acquiring its lease. These lower-level fixture APIs are
not launch authority; v1 remains cloud-ineligible.

- [x] Run the named test file and observe missing-feature RED before production code.
- [x] Implement immutable metadata and inventory with this exact logical schema:

```sql
CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), schema_version TEXT NOT NULL,
                       plan_json TEXT NOT NULL, plan_hash TEXT NOT NULL);
CREATE TABLE trials (ordinal INTEGER PRIMARY KEY, trial_id TEXT NOT NULL UNIQUE,
                     request_id TEXT NOT NULL UNIQUE, entry_json TEXT NOT NULL);
CREATE TABLE transitions (seq INTEGER PRIMARY KEY, ordinal INTEGER NOT NULL REFERENCES trials,
                          kind TEXT NOT NULL CHECK(kind IN ('INTENT','RESPONSE_STORED','VALID','INVALID')),
                          record_json TEXT NOT NULL, UNIQUE(ordinal,kind));
```

Use exact schema/version checks, FULL synchronous, DELETE journal, foreign keys and short
explicit transactions. Create with exclusive file reservation and restrictive mode; existing,
symlink/nonregular/hardlinked DB rejected. Linux directory fsync after fresh archive creation.
On failure close all resources, retain incomplete artifact rather than overwrite/delete it.
`open` uses existing-only SQLite URI; `verify` uses mode=ro/query_only and never creates DB.

- [x] Cold derive plan via `validate_manipulation_request_plan` once per create/open/readonly
  verify. Store full plan JSON/hash and every ordered entry; compare whole metadata/inventory
  with the supplied derived plan. Reject missing/extra/reordered rows and altered receipts.
  Cache typed requests and exact encoder wire bytes. The live hot path must not rebuild full
  source on each mutation. Detect external DB data_version/total_changes/file-identity changes
  and cold replay before permitting the next mutation; tests count source reconstruction calls.
- [x] Append one phase record transactionally with exact fields:

```python
content = {"schema_version": "paper1.identity-network.manipulation-transition.v1",
           "plan_hash": plan.output_hash, "seq": next_seq, "ordinal": ordinal,
           "trial_id": trial_id, "request_id": request.request_id,
           "kind": kind, "evidence": evidence_payload, "previous_record_hash": previous_hash}
record = {**content, "record_hash": canonical_payload_hash(content)}
```

`record_before_dispatch` validates exact typed request and exact wire bytes, current READY
prefix, and held lease; commit INTENT before returning, with no transaction held for HTTP.
Duplicate intent or future trial forbidden. `store_response` requires current INTENT and
exact request/attempt/transport/wire/raw bindings, commits complete typed response before
parsing. Duplicate response forbidden. No automatic resend or retry.

- [x] In evidence helper reconstruct strictly typed response/transport, verify all request
  and attempt identities, outcome/error/provider/raw consistency and exact model/non-thinking
  wire body before accepting response. Reuse shared bounded typed non-thinking parser
  (`identity_network.execution._parse_bounded_response` is pure and accepts an explicit
  check parser/topic context; do not fabricate PreparedStudyEvent or call state finalization).
  Reject provider-envelope model drift. Parser results retain stance/reason/confidence and
  full parse evidence. Full provider/parse failure is INVALID; it is never a no-signal result.
- [x] `terminalize_saved_response` parses only the persisted current response and appends
  deterministic VALID/INVALID evidence; no HTTP or shared-state updates. Cold replay verifies
  each phase transition/evidence/hash chain and recomputes parser terminal from saved response.
  Legal history: zero or more complete VALID trials, at most one INTENT/RESPONSE_STORED/INVALID,
  then READY suffix. No missing historical intent or future-row phase accepted. Transactional
  read/compare-and-set prevents duplicate transitions and stale prefix writes.
- [x] `summary` exposes only counts/current phase/plan and tail hashes, execution_complete
  only for exact all-VALID inventory, preliminary/not_frozen/formal_parameter_authority=false.
  No raw messages/responses/reasons exported by summary. `verify` cold replay is readonly.
  Add negative tests for hash-recomputed seed/request/wire/response/parse substitution,
  late-prefix corruption, provider/parse failure stopping suffix, external SQLite edits,
  crash-like reopen at INTENT/RESPONSE_STORED and exact complete synthetic inventory.
- [x] Run named store tests plus request/lock regressions, Ruff lint/format and diff check;
  two-stage independent review. Fix significant issues with RED→GREEN before controller commit.

Delivery evidence: controller final scoped regression 40 passed / 2 Linux-only skipped,
122.48s; Ruff lint/format and diff check clean. Spec review's post-COMMIT generation race
was reproduced RED and fixed GREEN before compliant re-review; separate quality review
approved the bounded persistence delivery. Linux acceptance and the full runner remain pending.

## Scope audit

This plan completes the dedicated persistence boundary, not the transport loop or operator CLI.
Real fake-HTTP runner crash injections, loaded-source origin, exact authorized-root/service
preflight and standalone run/resume/verify/report remain mandatory next deliveries. Actual240
content/repetition/statistics decisions remain unresolved; no automatic defaults or Stage-B.
