---
status: user-approved; three written review iterations addressed; human-released for implementation
authority: Phase 4B-8C-3 implementation design; subordinate to the frozen protocol chain
supersedes: informal Phase 4B-8C-3 handoff notes
last-verified: 2026-09-01
---

# Paper 1 Phase 4B-8C-3 Evidence Pipeline Design

## 1. Purpose

Phase 4B-8C-3 connects the already implemented feed, memory, prompt, mock adapter,
parser, lifecycle, and storage components into one strictly serial mock event pipeline.
Its central deliverable is an independently replayable evidence chain:

`ExposureRecord -> MemoryView -> PromptView -> AdapterRequest -> AdapterResponse -> ParseEvidence -> terminal attempt`

This slice does not introduce a second event loop. It supplies typed preparation,
invocation, finalization, and commit callbacks to `StrictSerialLifecycleEngine` and
extends `RunStorage` so that every material input and output survives interruption.

## 2. Authority and non-negotiable constraints

This design implements the 2026-07-29 Phase 4A completion design and decisions
`D-2026-07-29-08` through `D-2026-07-29-19`. If this document conflicts with the
frozen protocol chain, the protocol chain wins.

- Events read the state produced by the preceding successful commit and commit in
  strict event-ordinal order.
- A failed invocation or parse changes no private state, public post, feed cursor,
  publish flag, or event cursor.
- Recovery and retry preserve the same event identity. Each retry has a new attempt
  identity and its own request, response, and parse evidence.
- Social exposure reads public posts only. Neighbor private state, private reason,
  confidence, demographics, node number, and treatment identity never enter the
  social feed.
- The frozen schedule supplies `publish_flag`; runtime code never chooses it.
- Formal configuration remains fail closed while any required value contains
  `UNRESOLVED[...]`.
- B, K, timeout, retry policy, model-seed pairing, request parameters, model identity,
  parser limits, prompt limits, and checkpoint frequency have no runtime defaults.
- This slice is mock-only. It performs no network request and does not connect vLLM,
  Qwen, or an external API.
- Raw large-scale results remain outside Git. Only code, tests, schemas, manifests,
  hashes, and archive locations are versioned.

## 3. Chosen architecture

### 3.1 Thin pipeline, existing lifecycle owner

Add a focused execution module that constructs callbacks for
`StrictSerialLifecycleEngine.execute()`. The lifecycle engine remains the only owner
of attempt transitions and successful state commits. The new module may coordinate
existing public functions, but it must not duplicate feed selection, memory selection,
prompt rendering, adapter validation, parsing, retry authorization, checkpointing, or
commit ordering.

The public entry point accepts all unresolved and run-specific inputs explicitly. It
returns an immutable `MockEventPipelineOutcome` containing the existing
`AttemptOutcome` and an `EventEvidenceReferences` value. References contain the
available event-input, request, invocation, parse, terminal-attempt, and committed-event
IDs/hashes; fields are explicitly `None` when the corresponding lifecycle prefix has
not landed. Reopening the same prefix must reproduce the same references. The entry
point does not invent policy values.

### 3.2 SQLite storage version 6

Upgrade `paper1.run-storage.v5` to v6 with six evidence groups. Payloads use canonical
JSON, stable typed IDs, schema/algorithm versions where the source type defines them,
and SHA-256 hashes computed by the existing canonical hashing rules.

1. `event_input_evidence`
   - one canonical row per event identity;
   - stores `ExposureSelection`, `ExposureRecord`, `MemoryView`, `PromptView`, and the
     complete typed `ParserLimits` payload/hash that must be used after invocation;
   - binds their payload hashes and the state/progress context from which they were
     constructed;
   - all attempts under one event must reference the exact same row and hash.
2. `adapter_requests`
   - one row per attempt;
   - stores the complete sealed `AdapterRequest` payload and record hash;
   - binds event ID, attempt ID/index, rendered prompt hash, model identity, request
     parameters, model seed, parser-limits hash, and attempt-policy hash.
3. `invocation_evidence`
   - zero or one row per attempt;
   - written immediately after a mock adapter result is available and before parsing;
   - stores the complete canonical `AdapterResponse` payload/hash plus explicit
     execution evidence and the request/parser-limit/policy hashes;
   - supports recovery after response arrival but before parsing or terminal append.
4. `parse_evidence`
   - zero or one row per attempt;
   - response outcomes require complete `ParseEvidence`, including parser version,
     limits, response binding, parsed value or structured parse failure;
   - timeout outcomes store `ParseNotApplicableEvidence` rather than a fabricated
     parse result. This immutable tagged record contains its schema version,
     attempt/request/response IDs and hashes, timeout outcome and error hash,
     parser-limits hash, fixed reason code `adapter_timeout_no_response`, and its own
     canonical payload hash.

5. `attempt_policy_evidence`
   - one immutable row per event, written before attempt 1 and exact-matched on retry;
   - stores a typed mock retry/model-seed policy binding with stable research-QA IDs
     `P1_MODEL_SEED_PAIRING` and `P1_TIMEOUT_RETRY`, an explicit allowed-difference
     field set, policy payload/hash, and `mock_only=true` / `formal_eligible=false`;
   - determines whether a later attempt may change the model seed or named request
     fields. Any unlisted difference is rejected.

6. `adapter_execution_bindings`
   - immutable pre-invocation mock adapter attestation referenced by every request;
   - stores the expected adapter kind/version, runtime identity/hash, model identity
     hash, mock script hash, and its own canonical payload hash;
   - is created before the first request and exact-matched for the run. `MockAdapter`
     exposes a typed read-only attestation method; storage and recovery never read the
     private `_script_hash` attribute.

The Phase 4B mock policy is an explicit test artifact, not a frozen formal decision.
Formal execution rejects `formal_eligible=false`, `mock_only=true`, any
`UNRESOLVED[...]` value, or missing decision-provenance approval. The pipeline cannot
infer allowed retry differences merely from two attempt payloads.

The existing attempt, event, private/public state, cursor, execution-state, halt, and
resume tables remain authoritative for lifecycle and research state. Evidence tables
do not independently advance the event cursor.

### 3.3 No lossy evidence envelope

The `GenerationAttempt.provider_metadata` compatibility envelope remains useful for
cross-checking terminal evidence, but it is not the authoritative copy of a complete
adapter response. The v6 evidence rows preserve the full typed payloads required to
recompute their record hashes after reopen.

### 3.4 Trusted persisted-response capability

An adapter-produced response loses its in-memory factory seal when serialized. Add an
internal storage-rehydration boundary, not a public constructor shortcut. It accepts a
persisted response only after canonical payload/hash verification, exact request and
attempt identity matching, outcome/error/raw consistency, runtime identity/script hash
validation against the independently persisted pre-invocation
`adapter_execution_binding`, and row-level causal checks. Only then does it issue an
internal `VerifiedPersistedAdapterResponse` capability.

The lifecycle recovery branch accepts either the original sealed adapter response or
this verified persisted capability. Ordinary callers cannot construct the capability.
Rehydration never calls `MockAdapter.generate()` or another provider. Tests instrument
the adapter and require zero `generate()` calls after reopen.

## 4. Storage API and transaction boundaries

Names may be adjusted to follow local conventions, but the responsibilities and
atomicity below are fixed.

### 4.1 Prepare transaction

`record_prepared_attempt(...)` atomically:

- inserts or exact-matches event input, attempt-policy, and adapter-execution-binding
  evidence, including the complete typed parser limits available before invocation;
- inserts or exact-matches the sealed adapter request;
- appends the PENDING transition using the lifecycle engine's current event identity.

On retry, event input evidence must compare equal byte-for-byte after canonicalization.
A changed exposure, memory, prompt, parser limits, state context, publish flag, policy,
or adapter binding is rejected before invocation. Retry comparison first normalizes
mandatory derived identities: `attempt_index`, `attempt_id`, `request_id`, and request
record hash must be re-derived exactly for the new attempt and are not policy choices.
Event input, prompt view/messages, topic, parser limits, policy, and adapter binding are
invariant. Only model seed and named request-parameter paths may differ according to
the stored `allowed_difference_fields`; all other semantic fields exact-match. Tests
exercise permitted seed/request drift, deterministic derived-ID changes, and rejection
of every unlisted difference. Formal execution remains blocked until the policy points
to frozen approved decisions rather than the mock-only artifact.

The implementation may integrate this transaction into the lifecycle engine through a
typed storage callback or a narrowly extended storage method. It must not append a
second PENDING transition or bypass the engine journal.

### 4.2 Invocation transaction

`record_invocation_evidence(...)` atomically stores the sealed response and execution
evidence for the current IN_PROGRESS attempt. It exact-matches an existing identical
row and rejects any conflicting replay. It does not create a terminal transition and
does not mutate research state.

### 4.3 Finalization transaction

`record_finalized_attempt(...)` atomically stores parse evidence or the explicit
timeout not-applicable record together with the FAILED/SUCCEEDED attempt transition.
For FAILED it also atomically stores the existing typed `TerminalFailureEvidence`
needed by the halt/resume authorization chain. The terminal validator must cross-check
the complete persisted request, response, execution, parse, attempt, and failure
evidence. There is no valid durable `FAILED-without-failure-evidence` state.

If current storage transaction boundaries make a combined insert impractical, the
implementation must first extend `RunStorage`; it may not accept a crash window in
which a terminal attempt exists without its required parse evidence.

### 4.4 Successful research-state commit

The existing `commit_success(...)` remains the only operation that advances research
state. Before commit it must verify:

- the event and terminal attempt bind the persisted event input, request, response,
  and parse evidence;
- the parsed update exactly matches the attempt's parsed response;
- the committed feed cursor equals `ExposureSelection.cursor_after`;
- private update/state derive from the parsed update for the scheduled receiver;
- public replacement occurs only when the frozen `publish_flag` is true;
- the public payload contains no private-only fields;
- Prompt run context is a disposable post-commit cache, never part of SQLite atomicity.

SQLite commits first. After commit, the pipeline may advance the in-memory validated
prompt context. If that step fails, or whenever a process reopens, the next preparation
rebuilds context from the complete succeeded storage prefix before use. A crash after
the SQLite commit therefore cannot expose stale prompt context, and context is never
advanced before durable research state.

## 5. Event data flow

### 5.1 Preparation

1. Read the current journal and preceding successful research state while holding the
   full-run lease.
2. Read public posts eligible under the frozen exposure graph and current feed cursor.
3. Call `select_unread_feed(...)` and `build_exposure_record(...)` with explicit B and
   frozen slot RNG provenance.
4. Call `build_memory_view(...)` with explicit K using the receiver's latest successful
   private updates, ordered oldest to newest.
5. Build and validate the `PromptView`, render messages, and create the sealed
   `AdapterRequest`. Then create the separate authorization/request-row envelope that
   binds explicit model identity, request parameters, model seed, prompt-limits
   binding, parser-limits hash, policy hash, and adapter-execution-binding hash.
   These fields are not misrepresented as members of `AdapterRequest`.
6. Persist event input evidence, parser limits, attempt policy, request, and PENDING
   evidence before invoking.

E0 produces a legal explicit empty social feed. E1/E2 use their already frozen graph
artifacts; the pipeline does not choose or repair a graph.

### 5.2 Invocation and parsing

1. Move the attempt to IN_PROGRESS through the lifecycle engine.
2. Invoke the mock adapter exactly once.
3. Persist the complete sealed response and execution evidence immediately.
4. For a response outcome, parse with the explicitly supplied limits and persist the
   complete `ParseEvidence` with the terminal attempt.
5. For timeout, persist explicit timeout/not-applicable parse evidence with FAILED.
6. A malformed response remains FAILED with raw response and parse diagnostics intact;
   no repair, fallback, imputation, or silent default is permitted.

### 5.3 Commit

Only a valid SUCCEEDED terminal attempt builds `SuccessfulEventCommit`. The state
update uses the scheduled `publish_flag`; then the existing atomic commit writes the
event, private history/current state, optional public replacement, latest public
pointer, and new feed cursor. Subsequent events may observe the commit immediately.

## 6. Recovery semantics

Recovery decisions are evidence-driven and fail closed.

- PENDING without IN_PROGRESS: exact-match the stored event input and request, append
  IN_PROGRESS, then invoke once.
- IN_PROGRESS without invocation evidence: require explicit provider reconciliation;
  never blindly resend.
- IN_PROGRESS with complete invocation evidence but no terminal attempt: rehydrate the
  internal verified persisted-response capability, parse only with the stored
  `ParserLimits`, persist parse/terminal/failure evidence atomically, and invoke the
  adapter zero times.
- Terminal FAILED: stop until exact external retry authorization is recorded.
- Terminal SUCCEEDED without research-state commit: reuse the landed attempt and
  persisted evidence, reconstruct the commit solely from that evidence, then perform
  the atomic commit with zero adapter calls.
- Conflicting duplicate evidence, missing exact-cover rows, hash mismatch, or a broken
  causal link makes open/integrity verification fail.

Checkpoint writing remains explicit. Checkpoint evidence must cover the new v6 tables
and hashes, but this design does not select checkpoint frequency.

## 7. Integrity and replay

`RunStorage.verify_integrity()` must additionally prove:

- status-conditioned exact cover between event attempts and their evidence rows;
- one immutable event-input row per event and exact reuse across retries;
- request -> response -> parse -> terminal cross-hash consistency;
- response outcomes have parse evidence and timeout outcomes have explicit
  not-applicable evidence;
- successful event commits bind the same exposure and parsed update as the terminal
  attempt;
- feed cursor and prompt context advance only across the successful event prefix;
- ordinary rehydrated typed objects pass their existing validators after reopen;
  persisted adapter responses instead pass the new attestation-backed capability
  verifier, which never calls the existing replay validator or `generate()`;
- tampering any stored payload, hash, ID, version, or causal reference is detected.

Two valid global boundaries contain no current attempt:

| Global journal state | Required history | Current-event evidence |
|---|---|---|
| ready/new event | complete closed successful-event prefix ending immediately before the current ordinal; run adapter binding may already exist | none: no event input, policy, request, or attempt evidence |
| complete run | every expected event is in the complete closed successful-event prefix | none: no current event or attempt evidence |

Exact cover is otherwise evaluated per attempt while retaining the event's append-only history.
Every completed earlier retry attempt remains a closed failed prefix: request,
invocation, exactly one of ParseEvidence/N/A, FAILED, TerminalFailureEvidence, and
exactly one adjacent `ResumeAuthorizationEvidence` pointing to the next attempt. The
current attempt is then evaluated by this matrix:

| Current event/attempt state | Required current-prefix evidence | Forbidden current-prefix evidence |
|---|---|---|
| failed awaiting authorization | complete FAILED response/timeout prefix and failure evidence | authorization, next attempt, commit |
| authorization landed awaiting retry | complete FAILED prefix and exact resume authorization | next-attempt evidence, commit |
| retry/new PENDING | event input, parser limits, policy, adapter binding, current request, PENDING; retain all closed prior-attempt prefixes | current invocation, parse/N/A, terminal, failure, commit |
| IN_PROGRESS before result | all current PENDING evidence, IN_PROGRESS | current invocation, parse/N/A, terminal, failure, commit |
| IN_PROGRESS after result | all current prior evidence, invocation | current parse/N/A, terminal, failure, commit |
| terminal response SUCCEEDED | all current prior evidence, ParseEvidence, SUCCEEDED | current timeout N/A and failure; commit may be absent until recovery |
| terminal response FAILED | all current prior evidence, ParseEvidence, FAILED, TerminalFailureEvidence | current timeout N/A and commit |
| terminal timeout FAILED | all current prior evidence, ParseNotApplicableEvidence, FAILED, TerminalFailureEvidence | current ParseEvidence and commit |
| landed SUCCEEDED awaiting commit | complete current SUCCEEDED prefix; retain zero or more closed prior failed/authorized attempts | current failure evidence; event/state commit absent |

`verify_integrity()` runs before recovery and must accept exactly these event-history
plus current-prefix combinations. It rejects deleted required rows, extra rows, orphan
rows, mixed parse/N/A evidence, non-adjacent or duplicate failure/authorization edges,
an authorization not preceded by its exact failure or not matched by the next derived
attempt once that attempt exists, or evidence belonging to a later lifecycle state.
Reopen tests cover the points immediately after authorization and
during retry-attempt PENDING and IN_PROGRESS.

`commit_success()` atomically converts the landed-SUCCEEDED current prefix into a
closed historical successful-event prefix and advances progress. There is no durable
state in which a committed event remains the current attempt. The resulting journal is
either `ready/new event` or `complete run`.

This slice does not claim 50,000-event performance. The storage v6 design must avoid
adding an unnecessary full-history verification call to each event, while the actual
N=1000, T=50 scale and memory/throughput gates remain Phase 4B-9 work.

## 8. Testing strategy

Implementation follows test-driven development. The minimum integration matrix is:

1. E2 single-event success from feed through successful atomic commit, followed by
   reopen and exact replay validation.
2. Malformed response produces complete parse failure evidence while private state,
   public post, feed cursor, publish flag, and event cursor remain unchanged.
3. Explicitly authorized retry keeps event input evidence identical, appends a new
   attempt evidence chain, and commits only the successful attempt.
4. Simulated interruption after invocation persistence and before parse resumes with
   zero adapter calls.
5. E0 explicit empty-feed success proves empty exposure is legal and recorded.
6. Parameterized tampering of exposure, memory, prompt, request, response, execution,
   parse, and cross-reference hashes fails at the integrity/open gate.
7. A persisted-response reopen test instruments `MockAdapter.generate()` and proves
   zero calls while rehydrating the internal verified capability and parsing with the
   stored parser limits.

Additional focused tests cover:

- first-activation round-0 feed, latest-B expiry, no backfill, same-source repeated
  posts, and deterministic slot ordering;
- memory from latest K successful private updates, not public posts;
- public-feed privacy exclusions;
- frozen publish false preserving the prior public post;
- deep immutability of all new public typed evidence;
- lease release and retry/recovery exception branches;
- crash after prepare/PENDING before IN_PROGRESS;
- IN_PROGRESS without invocation evidence blocking blind resend;
- parse evidence and terminal transition atomicity;
- timeout/N/A evidence creation, reopen, and tamper rejection;
- landed SUCCEEDED recovery before research-state commit;
- prompt-context rebuild after a completed SQLite commit;
- deleted, orphan, and extra rows for every status-conditioned evidence prefix;
- allowed and forbidden retry request/model-seed drift against stored policy;
- formal fail-closed behavior for mock-only or unresolved policy bindings;
- checkpoint creation/reopen covering all v6 evidence rows and hashes;
- parser-limit tampering in the invocation-before-parse recovery window;
- independent response and pre-invocation adapter-binding tampering, including runtime
  identity and mock script hash;
- stable `MockEventPipelineOutcome` references across reopen;
- v5 rejection before mutation, according to the migration decision below.

The complete 12-cell mock matrix and N=20/100/1000 deterministic, invariant, memory,
and throughput gates remain Phase 4B-9.

## 9. Migration decision

Phase 4B research stores are development artifacts, but silent reinterpretation is
not allowed. Storage v6 uses an explicit version gate:

- a new v6 store is created with all evidence tables and constraints;
- every normal v6 open/execution path rejects v5 with a clear version error before
  mutation and leaves the v5 file byte-identical;
- no automatic backfill fabricates evidence that v5 never recorded.

8C-3 adds no v5 diagnostic opener and no automatic migration. If a later operational
need requires migration, it must be a separate audited tool that labels missing
historical evidence rather than inventing it.

## 10. Rejected alternatives

### 10.1 One opaque JSON evidence bundle

This is faster to add but weakens exact-cover constraints, targeted replay, tamper
localization, and interruption recovery. It is rejected for the authoritative store.

### 10.2 Continue embedding summaries only in `GenerationAttempt`

This cannot independently reconstruct complete exposure, prompt, request, response,
or parse hashes after reopen and cannot safely resume between invocation and parsing.
It fails the 8C-3 evidence requirement and is rejected.

### 10.3 A second end-to-end event loop

Duplicating lifecycle behavior would create competing retry, recovery, and commit
semantics. The new pipeline must compose the existing lifecycle kernel instead.

## 11. Completion criteria

Phase 4B-8C-3 is complete only when:

- the complete typed evidence chain is persisted and independently replayable;
- interruption after response persistence resumes without adapter resend;
- success is the only path that advances research state and cursor;
- all unresolved research/runtime parameters remain explicit and fail closed;
- v6 integrity verification rejects payload, hash, and causal-link tampering;
- focused, combined storage/lifecycle, and full platform test suites pass;
- lint, formatting, dependency, and diff checks pass;
- an implementation log records exact tests, environment limitations, and remaining
  Phase 4B-9 gates without claiming formal-experiment readiness.
