---
status: owner-approved concept; pending written-spec review
authority: performance and evidence-storage design for future Phase 0A judge runs only
approved-by: user
approved-date: 2026-09-25
supersedes: none; completed judge-v2 run using v1 store schema remains immutable
---

# Future judge-run storage without per-append full replay

## Scope and reason

The completed 797-item Phase 0A-1 judge v2 run, which uses the v1 judge-store
schema, remains a historical, read-only archive. Its `JudgeRunStore.append` reads all earlier records and replays them
twice per append. `replay_judge_records` constructs and hashes a full item-state
projection after each record even when only the last projection is returned.
The append path also scans prepared transactions and projection filenames and
writes a growing full-state projection into each prepared transaction and the
projection directory. The `bf2f63a` change removed one historical-projection
read but did not remove these growth paths. The runner also calls
`reconstruct_judge_projection(store)` after every resolved attempt, performing
another full-journal replay. No measured speedup is claimed.

This design replaces the storage format **for newly authorized judge runs**. It
does not modify or resume the completed 797-item archive, change judge prompts
or labels, or authorize another model request. Phase 0B N=20 event execution
uses its own SQLite `RunStorage`; it does not call `JudgeRunStore.append` and is
outside this storage-format change. Phase 0B requires a separate local
synthetic timing check and real-cloud preflight before throughput claims.

## Alternatives considered

1. Cache the latest v1 projection and reduce redundant replay. Smallest code
   change, but v1 still writes a full projection for every record, so cumulative
   storage and serialization grow with the run. Rejected as a complete fix.
2. Keep a custom append-only file log of deltas and periodically snapshot.
   Preserves the existing file style but retains complex cross-file crash
   recovery and many directory synchronizations. Rejected for new runs.
3. **Selected:** a versioned SQLite judge store with one transactional,
   hash-chained record per state transition and one terminal full projection.
   This reuses the project's already-tested SQLite operational model while
   keeping judge evidence separate from the Phase 0B experiment database.

## New-store contract

- The new schema has a distinct identity and manifest binding. Opening an old
  v1 archive with the new writer must fail; the existing v1 reader/verifier
  continues to verify historical archives. There is no implicit conversion or
  rewrite of the completed 797-item run.
- Before each outbound judge request, commit its dispatch intent. After a
  response, atomically append each required response/audit/attempt/resolution
  transition and advance the in-memory state using only that newly committed
  record. The runner must consume this current validated state; it must not
  call `reconstruct_judge_projection` or otherwise replay the whole journal
  between normal requests. Each stored record contains the previous record
  hash, its own canonical payload hash, sequence and manifest binding;
  item/attempt identity is required for item-level records, not preflight or
  service-start records. A terminal judge projection is written once after
  exact completion, not on every append.
- Raw response bytes may reside in an access-restricted SQLite BLOB and must
  have an exact recorded SHA-256. They stay outside Git and must never appear
  in progress logs, test output, chat, or aggregate reports. The database and
  manifest/lock are a single archive unit; export/backup must use a quiesced
  database or SQLite's consistent backup operation, not a live file copy.
- A normal append must not read or replay the full journal, enumerate all
  earlier files, or serialize the full item-state map. It may validate the
  current manifest, sequence and hash-chain tip and the affected item/attempt.
  The in-memory state is not authority after a restart.
- On open/resume, rebuild state by one sequential replay of the committed
  journal, validating the hash chain and all judge transition semantics. An
  unresolved dispatch intent is a fail-closed boundary: never silently resend
  it. Explicit reconciliation uses the existing approved policy and retains
  the same item/attempt identity. A corrupted or ambiguous archive is not
  repaired by inventing evidence.
- If the final resolution transaction committed but terminal sealing did not,
  open/resume must replay to the exact completed state and permit one
  create-only terminal seal without sending a new request. Reopening an
  already sealed store must verify and return the existing terminal projection,
  never create a second seal.
- At terminal verification, independently replay all records, require exact
  approved item coverage, no unresolved intents and complete attempt/resolution
  linkage, and compare the resulting full projection with the sealed terminal
  projection. The report may expose hashes and counts, not raw responses.
- SQLite transactions must preserve create-only logical semantics: duplicate
  sequence, hash, item/attempt identity or incompatible retry transitions are
  rejected. A crash before commit leaves no completed transition; a crash
  after commit exposes exactly one. Filesystem/host durability settings and
  actual Linux behavior must be recorded and verified before a cloud run.

## Acceptance and measurement

1. First collect a storage-only synthetic baseline for the existing v1 path
   at increasing prefix sizes, separating record replay, file inventory,
   projection serialization and durable write time. Use no real raw responses.
2. Test the new store against the same deterministic synthetic judge records:
   exact typed transitions, dispatch-before-send, interruption at each commit
   boundary, restart/replay, duplicate rejection, tamper rejection, unresolved
   intent refusal, and terminal projection verification. Independently compare
   final semantic state with the old replay logic on small fixtures.
3. Instrument the complete new-store **runner path** and assert that a normal
   append and the subsequent request decision invoke no full-history replay,
   full projection serialization or history directory traversal. Report
   early/middle/late per-attempt wall time, total storage
   bytes and durable write count for at least 100, 400 and 800 synthetic items
   on the same host. A claimed performance fix requires observed improvement
   without loss of evidence integrity; no model/GPU throughput claim follows
   from a storage-only benchmark.
4. Run targeted tests, Ruff and diff checks locally, then repeat the storage
   benchmark and crash/reopen cases on Linux before using the new format in a
   future authorized cloud judge run. Preserve the v1 archive and verifier.

## Non-goals and release boundary

No new 797-item judge run, no modification of the existing old-host archive,
no change to Phase 0B study parameters, no N=1000 authorization and no cloud
upload are implied by this design. Phase 0B may proceed independently once
its own performance and authorization gates pass. If the new store does not
meet its integrity or performance checks, use neither a silent fallback nor a
weakened verification rule; report the measured bottleneck and revisit the
storage design.
