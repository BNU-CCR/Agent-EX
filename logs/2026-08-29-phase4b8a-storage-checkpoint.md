---
status: implementation checkpoint; uncommitted
authority: Phase 4B-8A SQLite storage implementation evidence; subordinate to frozen protocol and Phase 4A completion design
date: 2026-08-29
branch: codex/paper1-phase4b
baseline: 57d0fd4
---

# Phase 4B-8A SQLite transaction storage checkpoint

## Scope completed

- Added `platform/src/agent_ex/storage.py` with one SQLite database per run.
- Bound schema version, baseline manifest, run identity, protocol identity, frozen schedule,
  and explicit artifact hashes at database creation and reopen.
- Added append-only, same-run, current-event, continuous attempt storage.
- Added round-0 typed state initialization for private state, public stock, and feed cursor.
- Added one success transaction containing the succeeded event, private update/current state,
  optional public post/latest pointer, feed cursor, event-chain head, and manifest progress.
- Added typed readback and strict replay checks for attempts, events, private state, public
  stock, and cursors.
- Added explicit external raw-response URI+SHA-256 support. In this mode the database omits
  the raw body and requires a hash-matching body for strict typed replay.
- Added reopen integrity replay for the schedule, baseline manifest, continuous succeeded
  prefix, failed-then-success attempt chain, private state, cursor state, publish evidence,
  and event-chain head.
- Added main-path completion gating that accepts only all expected events succeeded.

## TDD evidence

The implementation followed observed RED then minimal GREEN cycles in
`platform/tests/test_storage.py`:

1. Missing storage module: collection RED (`ModuleNotFoundError`), then create/reopen binding
   GREEN (`1 passed`).
2. Missing attempt API: two RED failures (`append_attempt` absent), then append-only/order/run
   binding and failed-attempt no-mutation GREEN (`3 passed`).
3. Missing state initialization: one RED failure (`initialize_agent` absent), then atomic
   unpublished success GREEN (`4 passed`).
4. Missing completeness gate: two RED failures (`assert_complete` absent), then publish-true
   replacement and complete/incomplete gating GREEN (`6 passed`).
5. Reopen tamper was not rejected: one RED failure, then integrity verification GREEN
   (`11 passed`, including four injected transaction failure points).
6. Missing external response reference: collection RED (`ImportError`), then URI+hash-only
   storage and strict replay GREEN (`12 passed`).
7. Schedule and chain-head tamper were not rejected: two RED failures, then full recovery
   replay GREEN (`16 passed`).

## Fault and recovery evidence

SQLite abort triggers were injected at:

- private-state replacement;
- public-post insertion;
- feed-cursor replacement;
- progress/event-chain update.

For every injected failure, event, private update/current private state, public post/latest
pointer, cursor, and progress all rolled back. The already append-only attempt remained intact
by design and the same event was then committed successfully after removing the trigger.

## Verification

From `platform/` using the project `.venv`:

- `python -m pytest tests/test_storage.py tests/test_domain.py tests/test_state.py tests/test_feed.py -q`
  -> `115 passed in 16.72s`.
- `python -m ruff check src/agent_ex/storage.py tests/test_storage.py` -> passed.
- `python -m ruff format --check src/agent_ex/storage.py tests/test_storage.py` -> passed.
- `git diff --check` -> passed.

No full suite or coverage run was performed in this subphase.

## Explicitly not implemented

- event engine or retry loop;
- checkpoint file/export layer;
- timeout, retry-count, or checkpoint-frequency defaults;
- model-seed pairing semantics;
- concurrent writers within one run;
- network access or real adapters/models;
- formal research-parameter freezing.

No SQLite database, checkpoint, cache, or raw large response was added to Git. Nothing in
this checkpoint was committed or pushed.

## Independent re-review repair (2026-08-29)

The first independent review returned `NOT APPROVED`. The following repairs supersede the
earlier 16-test candidate while preserving the storage-only boundary.

### RED to GREEN evidence by finding

1. **Independent manifest/schedule replay, exact schema, and safe open**
   - Tests: `test_create_independently_replays_manifest_and_schedule_before_writing`,
     `test_open_rejects_drifted_storage_schema_version`, and
     `test_open_missing_path_fails_without_creating_database`.
   - RED: `3 failed`; reflected cached schedule state, a drifted binding schema version, and a
     missing path were not handled correctly.
   - GREEN: `3 passed`. Create/open now independently replay typed schedule and manifest records,
     use the replayed records thereafter, require the exact storage schema, and use an existence
     precheck plus SQLite `mode=rw`.

2. **External raw-response recovery resolver**
   - Test: `test_external_response_commit_reopens_only_with_explicit_hash_checked_resolver`.
   - RED: `1 failed`; reopen had no explicit resolver interface.
   - GREEN: `1 passed`. Reopen accepts only an explicit no-network resolver, checks returned
     content against the stored URI-bound SHA-256, and fails closed without a resolver.

3. **Append-only attempt lifecycle and exact-cover recovery**
   - Tests: `test_attempt_transition_journal_is_monotonic_append_only_and_terminal`,
     `test_reopen_rejects_orphan_terminal_attempt_not_covered_by_transition_journal`,
     `test_reopen_rejects_gap_in_current_event_attempt_transition_prefix`, and
     `test_landed_success_attempt_reopens_and_commits_without_reissuing_attempt`.
   - RED: lifecycle `1 failed`; current-event exact-cover `2 failed`.
   - GREEN: lifecycle `1 passed`; exact-cover `2 passed`; landed-success recovery passes in the
     complete storage suite. An append-only transition journal now enforces
     `PENDING -> IN_PROGRESS -> FAILED|SUCCEEDED` for one attempt identity, preserves immutable
     request evidence, permits a new attempt only after failure, and forbids all appends after
     success. Recovery validates all succeeded-prefix attempts plus the current event prefix and
     rejects future, foreign, orphan, duplicate, gap, and terminal/journal drift.

4. **Exact-cover state and public evidence**
   - Test: `test_reopen_requires_exact_cover_of_round0_public_latest_and_current_state` (four
     tamper cases).
   - RED: `4 failed`; deleted round-0 public stock/latest pointer and orphan public/private rows
     were ignored.
   - GREEN: `4 passed`. Replay now exact-covers round-0 posts, every event update/post, all current
     private states/cursors, all latest pointers, and all history IDs. Event ordinals are unique in
     private-update and public-post history.

5. **Seed, provenance, and exposure binding**
   - Tests: `test_initialize_agent_rejects_cursor_seed_drift_from_run`,
     `test_success_commit_rejects_attempt_exposure_drift_from_event`, and
     `test_reopen_rejects_exposure_drift_even_when_row_and_chain_hashes_are_recomputed`.
   - RED: runtime seed/exposure `2 failed`; recomputed-hash recovery attack `1 failed`.
   - GREEN: `2 passed` plus `1 passed`. Every round-0 record, including `FeedCursor`, binds the run
     seed; typed factories replay topic/agent/source provenance; every terminal attempt in the retry
     chain binds `event.exposure_id` both at commit and recovery.

6. **Complete gate and structural performance**
   - Tests: `test_assert_complete_runs_full_integrity_replay_before_accepting_counts` and
     `test_n50000_schedule_slot_is_cached_and_recovery_queries_use_indexes`.
   - RED: complete gate `1 failed`; N=50,000 cached slot API `1 failed`.
   - GREEN: each `1 passed`. `assert_complete()` now begins with full integrity replay. The typed
     frozen schedule is replayed once and cached; per-event slot access is tuple-index O(1) and does
     not parse JSON. Query plans use indexes for `private_updates(event_ordinal)`,
     `public_posts(event_ordinal)`, and `public_posts(agent_id,event_ordinal)`.

### Final verification for the repaired snapshot

All commands used the project `platform/.venv` and were run sequentially because the project fixes
pytest's base temp path to `.pytest-tmp`:

- complete storage suite: `33 passed in 2.54s`;
- storage + domain + state + feed: `132 passed in 19.00s`;
- protocol + installation gates: `144 passed in 11.26s`;
- explicit N=50,000 structure/query-plan regression: `1 passed in 1.30s`;
- Ruff check: passed;
- Ruff format check: `2 files already formatted`;
- `git diff --check`: passed.

An earlier attempt to run two pytest processes concurrently produced only a shared `.pytest-tmp`
directory race; both suites passed when rerun sequentially. No code change was made for that test
runner conflict.

The repaired snapshot still does not implement the event engine, retry policy, checkpoint export,
timeout/retry/checkpoint defaults, model-seed pairing, network access, or a real model adapter. No
full suite or coverage run was performed. Nothing was committed or pushed.

## Second independent review repair (2026-08-29)

The second review combined the remaining specification, quality, and Windows release-stability
findings. The following tests and implementation changes close that review without expanding into
engine, retry-policy, checkpoint, network, or adapter work.

### RED to GREEN evidence by finding

1. **Live external resolver and append boundary**
   - Tests: `test_live_create_resolver_replays_external_failed_prefix_before_success_commit` and
     `test_append_rejects_next_attempt_until_prior_terminal_and_after_complete`.
   - RED: `2 failed`. A live store did not retain its explicit resolver, and an unfinished prior
     attempt did not block the next attempt identity.
   - GREEN: `2 passed`. Create/live/open use the same explicit no-network resolver contract; the
     external body remains absent from SQLite. A new PENDING attempt is accepted only after the
     previous attempt is terminal FAILED, while PENDING/IN_PROGRESS, SUCCEEDED, completed runs,
     negative/future ordinals, and ordinals outside the frozen schedule fail closed.

2. **Round-0 recovery authority and seed/provenance binding**
   - Tests: `test_reopen_derives_cursor_seed_from_manifest_not_stored_cursor` and
     `test_initialize_agent_rejects_round0_seed_not_bound_to_manifest`.
   - RED: forged current-cursor seed was accepted by recovery.
   - GREEN: `2 passed`. An immutable initial-cursor row is exact-covered; recovery derives the
     authoritative matched seed from the typed baseline manifest and cross-checks round-0 private
     update/state, public post/latest pointer, agent, topic provenance, and cursor provenance.

3. **Redundant-column exact binding**
   - Tests: `test_reopen_exact_binds_redundant_row_identity_and_status_columns` (three attacks),
     `test_reopen_exact_binds_event_run_id_column`, and
     `test_reopen_exact_binds_initial_private_update_agent_column`.
   - RED: the event table had no redundant run ID, and a forged round-0 private-update agent column
     was accepted even though its typed payload remained intact.
   - GREEN: `5 passed`. Attempts and lifecycle transitions bind row attempt/event/index/status plus
     external URI/hash to typed payloads; events bind ordinal/event/run/status; private updates,
     public posts, current state/pointers/cursors, and immutable initial cursors exact-bind their
     redundant keys and are exact-covered by replay.

4. **Frozen-slot and shared success-bundle replay**
   - Tests: `test_reopen_replays_every_frozen_schedule_slot_field_after_hash_recompute` and
     `test_reopen_revalidates_final_attempt_content_against_private_update`.
   - RED: `2 failed`. A self-consistent event could drift from its frozen slot, and a private update
     could be rebound to unrelated final-attempt content after recomputing downstream hashes.
   - GREEN: `2 passed`. One pure validator is now called by both commit and full recovery. It binds
     the full frozen slot, every attempt exposure, exact final successful attempt, private-update
     source/content/publish fields, replayed private state/cursor, and optional public post/pointer.

5. **Lifecycle timestamps and typed ordinal checks**
   - Test: `test_attempt_terminal_started_at_must_equal_in_progress_started_at`; schedule bounds are
     also covered by `test_append_rejects_next_attempt_until_prior_terminal_and_after_complete`.
   - RED: a terminal transition could change `started_at` after IN_PROGRESS.
   - GREEN: `2 passed`. PENDING has no timestamps, IN_PROGRESS establishes `started_at`, terminal
     evidence preserves that exact start and has `finished_at >= started_at`; boolean, negative, and
     out-of-range schedule ordinals are rejected.

6. **Exception-path connection release on Windows**
   - Tests: `test_open_closes_connection_when_pragma_initialization_fails` and
     `test_repeated_failed_open_releases_database_for_replace_and_unlink`.
   - RED: the injected pre-verification PRAGMA failure bypassed the original close boundary.
   - GREEN: `2 passed`. PRAGMA, binding, and integrity failures all close their connection. Three
     consecutive failed opens can each be followed immediately by database replace, and the final
     file can be unlinked. One intermediate WinError32 was traced to the test's own SQLite tamper
     connection (`sqlite3.Connection` context commits but does not close); using explicit
     `closing(...)` removed that unrelated handle and confirmed the production path releases cleanly.

### Final verification for the second repaired snapshot

All commands used `platform/.venv` and ran sequentially:

- complete storage suite: three consecutive runs at `47 passed` (`4.40s`, `4.79s`, `4.82s`),
  followed by a post-format confirmation at `47 passed in 4.81s`;
- storage + domain + state + feed: two consecutive runs at `146 passed` (`21.13s`, `20.96s`);
- protocol + installation gates: `144 passed in 11.31s`;
- explicit N=50,000 structure/query-plan regression: `1 passed in 1.39s`;
- Ruff check: passed;
- Ruff format check: `2 files already formatted`;
- `git diff --check`: passed.

No full suite or coverage run was performed. No SQLite database, raw large response, cache, or
checkpoint payload was added to Git. Nothing was committed or pushed.

## Third independent review repair (2026-08-29)

The final storage re-review identified three remaining evidence-binding gaps. Each reported attack
was first reproduced against the repaired 47-test candidate and observed as a trustworthy RED
(`3 failed, 47 deselected`) before production changes.

1. **External raw-response URI immutability**
   - Tests:
     `test_reopen_rejects_terminal_external_uri_drift_between_journal_and_attempt` and
     `test_reopen_rejects_coordinated_external_uri_drift_without_chain_reseal`.
   - RED: changing only the terminal `attempts` URI was accepted when both URIs resolved to the
     same hash-matching body. A stronger separate RED proved that changing both terminal tables'
     URIs together was also accepted while leaving the event chain untouched.
   - GREEN: terminal transition and terminal attempt evidence now exact-bind the complete
     `(event_id, attempt_index, status, raw_response_uri, raw_response_hash)` tuple. Every terminal
     attempt contributes its typed payload plus either an explicit URI/SHA-256 pair or explicit
     `None` to the successful event chain, so coordinated location drift cannot pass silently.

2. **Round-0 manifest and frozen-schedule cross-binding**
   - Test: `test_reopen_rejects_self_consistent_round0_bundle_with_foreign_seed`.
   - RED: keeping the authoritative initial cursor intact while replacing the initial private
     update/state, public post, and latest pointer with a self-consistent seed+1 bundle and
     synchronized row IDs/hashes was accepted.
   - GREEN: recovery now directly binds every initial private update to the baseline manifest seed
     and to an agent present in the independently replayed frozen schedule. Topic package ID/hash
     must be consistent across initialized round-0 agents; the typed
     update-to-state-to-post-to-pointer replay continues to exact-bind topic, agent, and source
     provenance without deriving authority from mutable current rows.

3. **Transition row event identity**
   - Test: `test_reopen_rejects_transition_row_event_id_different_from_typed_payload`.
   - RED: a current PENDING transition whose typed payload and row attempt ID were changed to a
     future event remained grouped under the unchanged current row event ID and was accepted.
   - GREEN: recovery now selects and exact-compares every transition row's event ID, attempt ID,
     attempt index, and status to the typed payload. Terminal rows receive the same identity check
     plus URI/hash tuple comparison.

### Verification for the third repaired snapshot

All commands used `platform/.venv` and ran sequentially:

- four new malicious regressions: `4 passed, 47 deselected in 0.70s`;
- complete storage suite after final formatting: three clean runs at `51 passed` (`3.49s`,
  `3.21s`, and `4.21s`); an earlier pair exposed and then removed an accidental test-edit
  placement error before these clean results and did not require a production behavior change;
- storage + domain + state + feed: `150 passed in 19.50s`;
- explicit N=50,000 structure/query-plan regression: `1 passed in 1.39s`;
- protocol + isolated-installation gates: `144 passed in 10.91s`;
- Ruff check: passed;
- Ruff format check after applying the formatter: `2 files already formatted`;
- pip check: `No broken requirements found`;
- `git diff --check`: passed.

No full suite or coverage run was performed. No engine, checkpoint layer, retry policy, model-seed
pairing, network path, or real model adapter was added. No SQLite database, raw response, cache, or
checkpoint payload was added to Git. Nothing was committed or pushed.

## Fourth independent review repair: frozen roster and round-0 seal (2026-08-29)

This repair supersedes the 51-test third-review snapshot. It keeps the implementation inside
Phase 4B-8A storage and does not add engine or checkpoint behavior.

### Storage schema v2

The unpublished internal storage schema is now `paper1.run-storage.v2` with SQLite
`user_version = 2`; no migration path was added because no v1 database has been released. The run
binding now stores:

- the caller-supplied expected population roster as a canonical sorted JSON list;
- its canonical SHA-256;
- a nullable `round0_root` that is written exactly once by explicit sealing.

`RunStorage.create()` and `RunStorage.open()` both require `expected_agent_ids`. IDs must be
non-empty, unique, valid, and have cardinality equal to the frozen schedule's population size.
Every schedule slot must reference a roster member, but roster membership is never inferred from
the with-replacement schedule draws. Open requires the caller's normalized roster and hash to
exact-match the stored binding. The duplicate-ID rejection test was added after verifying that the
implementation already failed closed; it is contract-coverage evidence rather than a new RED cycle.

### RED to GREEN evidence

1. **Explicit roster and seal lifecycle**
   - Initial new-suite RED: `9 failed, 51 deselected` because the old API had no explicit roster.
   - After adding the roster binding, the with-replacement population test advanced to a precise
     RED because `seal_initial_state()` did not exist.
   - GREEN: four focused roster/seal/root tests passed. Initialization rejects agents outside the
     roster, sealing requires exact coverage, attempts are forbidden before sealing, and no
     initialization can be added or changed after sealing.
   - A separate roster-cardinality attack first produced `1 failed` and then passed after binding
     roster length to `FrozenSchedule.population_size`.

2. **Round-0 root and event-chain genesis**
   - Attack: keep seed/topic/agent provenance unchanged, replace stance/reason across the complete
     private update/state/public post/latest pointer bundle, and recompute every row ID/hash.
   - GREEN: sealing canonicalizes every expected agent's complete round-0 bundle in agent-ID order,
     including private update, derived initial private state, public post, derived latest pointer,
     feed cursor, initial cursor, and all nested hashes/provenance. Its `round0_root`, together with
     the roster hash, is included in event-chain genesis. Open independently recomputes the root
     from immutable initial evidence. Event-time current state is not mistaken for initial state.

3. **Canonical JSON bytes and duplicate-key rejection**
   - Tests for leading whitespace, noncanonical key order, and a duplicate manifest key first
     produced the expected `3 failed` because ordinary `json.loads` accepted them.
   - GREEN: `3 passed`. All binding and payload JSON read paths now share one duplicate-key
     rejecting loader and require the stored text to equal canonical serialization byte-for-byte
     before hashes and typed replay are evaluated.

4. **Provider lifecycle monotonicity**
   - Provider request-ID drift and provider-metadata value replacement first produced the expected
     `2 failed`.
   - GREEN: `2 passed`. Once `provider_request_id` first becomes non-null it cannot change or clear.
     Provider metadata may gain new top-level keys as execution evidence arrives, but an existing
     key cannot be removed or have its value changed. The validator is shared by live append and
     recovery replay; an additional recovery tamper test covers transition-history rewriting.
   - This matches the actual domain/mock contract: PENDING carries no provider metadata;
     IN_PROGRESS may begin carrying provider identity/metadata; terminal evidence may add fields.

### Fixture migration and final verification

All existing storage fixtures now explicitly pass `expected_agent_ids`; fixtures that exercise
attempts explicitly initialize the full frozen roster and call the seal before the first append.
No production auto-seal or schedule-derived population fallback was introduced.

Final sequential verification using `platform/.venv`:

- focused provider/duplicate-roster recovery checks: `4 passed, 59 deselected in 0.76s`;
- complete storage suite, two consecutive runs: `63 passed in 10.15s` and
  `63 passed in 10.21s`;
- storage + domain + state + feed: `162 passed in 23.86s`;
- explicit N=50,000 structure/query-plan regression: `1 passed, 62 deselected in 8.07s`;
- protocol + isolated-installation gates: `144 passed in 10.04s`;
- Ruff check: passed;
- Ruff format check: `2 files already formatted`;
- pip check: `No broken requirements found`;
- `git diff --check`: passed.

No full suite or coverage run was performed. No engine, checkpoint export, retry policy/default,
model-seed pairing, network access, or real model adapter was added. No SQLite database, raw large
response, cache, or checkpoint payload was added to Git. Nothing was committed or pushed.

## Fifth independent review repair: exposure provenance and transition API (2026-08-29)

This final quality repair retains storage schema v2 and the explicit roster/seal lifecycle. It adds
no engine, checkpoint, retry, network, or model-adapter behavior.

### Authoritative exposure binding

The reviewed domain has no separate `CanonicalCell` object and no frozen E1/E2-specific artifact
key. The authoritative cell is the exact Paper 1 cell ID in `manifest.run_spec["cell_id"]`; the
artifact binding remains the caller-supplied generic artifact map. Storage therefore does not
invent an artifact key or coder default. `RunStorage.create()` and `RunStorage.open()` now require
an explicit expected exposure mode and graph hash, validate the mode against E0/E1/E2 in that
canonical cell, require E0 `self_history_only` to have no graph hash, and require each social graph
hash to be a valid SHA-256 already present among the run's frozen artifact hashes.

Both values are stored in the canonical run binding and included in event-chain genesis. Agent
initialization, initial-state sealing, and recovery compare every cursor against that independent
run binding. Recovery reconstructs the authoritative round-0 cursor from the binding instead of
deriving its mode or graph from a stored cursor.

### RED to GREEN evidence

1. **FeedCursor provenance**
   - Initial attacks:
     `test_e0_storage_rejects_ws_cursor_provenance_before_seal` and the transition API attack below.
   - RED: `2 failed`; the storage API did not accept an explicit exposure binding and therefore
     could not enforce the requested run-level provenance contract.
   - Initial GREEN: `2 passed, 63 deselected`. The E0 attack is rejected before sealing.
   - Stronger GREEN coverage adds an E2 two-agent run where the second agent tries either E0 mode
     or a different valid artifact hash, an open call that supplies an alternate artifact-bound
     graph hash, and direct rewrites of both current and initial sealed cursor rows. All variants
     are rejected without weakening roster or round-0-root validation.

2. **Public `attempt_transitions()` envelope validation**
   - Attack: rewrite a transition row's `event_id` while leaving its typed payload intact, then
     query that attempt without reopening storage.
   - GREEN: the public query now selects every redundant envelope field, requires transition
     indexes to be exactly consecutive from one, replays canonical typed payloads, and exact-binds
     query attempt ID, row/payload attempt ID, event ID, attempt index, and status. Provider
     lifecycle validation is also applied across the returned progression. The forged row is
     rejected immediately.

### Fixture migration and final verification

All 84 `RunStorage.create()` / `RunStorage.open()` calls in the storage suite now pass explicit
exposure mode/hash values; no auto-default or schedule-derived exposure fallback was introduced.
The local event-genesis test helper was updated to include both new binding fields.

Final verification used `platform/.venv`. Each pytest invocation used a distinct explicit
`--basetemp`; another process held the configured shared pytest cache directory and caused a
WinError 5 cache-write warning, but no test used that shared directory for its temporary database
and the warning did not affect collection or results.

- focused exposure/transition attacks: `7 passed, 63 deselected in 0.89s`;
- complete storage suite, two consecutive runs: `70 passed in 11.21s` and
  `70 passed in 10.18s`;
- storage + domain + state + feed: `169 passed in 24.50s`;
- explicit N=50,000 structure/query-plan regression: `1 passed, 69 deselected in 8.16s`;
- protocol + isolated-installation gates: `144 passed in 9.97s`;
- Ruff check: passed;
- Ruff format check: `2 files already formatted`;
- pip check: `No broken requirements found`;
- `git diff --check`: passed.

No full suite or coverage run was performed. No engine, checkpoint export, retry policy/default,
model-seed pairing, network access, or real model adapter was added. No SQLite database or raw
response was added to Git. Nothing was committed or pushed.

## Sixth independent review repair: typed graph role and lifecycle-prefix query (2026-08-30)

This final recovery pass keeps storage schema v2 and the Phase 4B-8A-only boundary. It adds no
engine, checkpoint, retry-policy/default, model-seed-pairing, network-access, or adapter behavior.

### RED to GREEN evidence

1. **Typed social graph artifact role and immutable binding**
   - Focused tests cover accepting the real typed WS/shadow artifact for the matching E2/E1 role;
     rejecting the wrong artifact type; rejecting artifact-map ID/hash drift; rejecting a
     reflection-mutated envelope; and rejecting an alternate typed artifact on reopen.
   - GREEN: all seven graph-role variants passed. Social storage requires a typed
     `ArtifactEnvelope`, independently replays its payload, validates the expected `ws_graph` or
     `shadow_graph` role from the canonical cell, and binds its ID, type, and output hash into the
     run binding. E0 continues to require no graph artifact.

2. **Public transition query validates the whole legal prefix**
   - RED: after changing the sole persisted PENDING row into a self-consistent IN_PROGRESS row,
     `attempt_transitions()` accepted the single-row lifecycle (`1 failed, 7 passed`).
   - GREEN: the public query now invokes the existing shared lifecycle-prefix validator after
     exact row-envelope replay. The focused attack set then passed `8 passed`.

3. **Earlier social-exposure fixture migration**
   - The first complete storage run exposed five older cursor-provenance tests that still passed
     only a string graph hash. They were rejected by the newly strengthened typed-artifact gate
     before reaching their intended cursor attacks.
   - Only those test fixtures were migrated to real typed WS artifacts; production validation was
     not weakened. The five intended attacks then passed.

### Final sequential verification

All commands used `platform/.venv` with explicit `.pytest-tmp-role-red` or
`.pytest-tmp-role-green` base temp directories:

- complete storage suite, two consecutive runs: `79 passed in 14.68s` and
  `79 passed in 13.97s`;
- storage + domain + state + feed: `178 passed in 28.91s`;
- explicit N=50,000 structure/query-plan regression: `1 passed, 78 deselected in 8.44s`;
- protocol + isolated-installation gates: `144 passed in 11.69s`;
- Ruff check: passed;
- Ruff format check: `2 files already formatted`;
- pip check: `No broken requirements found`;
- `git diff --check`: passed.

Pytest emitted only a cache-write warning because another process held the project's separately
configured shared `.pytest-tmp` cache. The explicit base temp directories were unaffected. Both
role-specific temp directories were resolved and verified to be exact children of this
worktree's `platform/` directory, then removed. No full suite or coverage run was performed. No
SQLite database, raw response, cache, or checkpoint payload was added to Git. Nothing was
committed or pushed.

## Seventh independent review repair: semantic network validation and full transition chain (2026-08-30)

This repair retains the unpublished storage schema label `paper1.run-storage.v2` while extending
its binding columns. It remains strictly inside Phase 4B-8A storage: no engine, checkpoint,
retry-policy/default, model-seed-pairing, network access, or real adapter was added.

### RED to GREEN evidence

1. **Network artifact semantics, matched seed, and population size**
   - RED: storage accepted a typed envelope whose `artifact_type` string claimed WS while its
     payload was not a network; a valid WS artifact from matched seed 18 for a seed-17 run; and a
     valid 40-node WS artifact for a 42-agent roster. It also accepted E1 without independently
     binding the source WS. Together with missing-API legal/open cases, the focused suite produced
     `9 failed`.
   - GREEN: E2 independently replays the typed envelope and calls the existing
     `validate_ws_artifact`. E1 requires an explicit typed source WS, validates it with
     `validate_ws_artifact`, and calls `validate_shadow_artifact(shadow, source_ws)`. Both graph
     roles must match the manifest seed and exact roster/population node count. The artifact map
     exact-binds every graph/source ID to its output hash. E0 rejects every network envelope.
   - The binding and event-chain genesis now include exposure graph and source WS artifact
     ID/type/hash. For E2 the source is the single exposure WS; for E1 the shadow/source
     relationship, input hash, and source artifact ID are delegated to the existing strict shadow
     validator. Wrong source, foreign seed, wrong N, fake type label, alternate reopen artifact,
     and reflection mutation all fail closed.

2. **Successful event chain commits the complete transition history**
   - RED: a valid successful event used
     `PENDING -> IN_PROGRESS(provider identity/metadata) -> SUCCEEDED`. Clearing the historical
     IN_PROGRESS provider identity/metadata and recomputing that row's payload hash still allowed
     reopen because the event chain committed only terminal attempts.
   - GREEN: one shared helper now exact-replays every ordered transition and returns its canonical
     typed payload plus row envelope, transition index, payload hash, URI, and response hash. The
     successful event chain commits that complete sequence together with the terminal attempt row
     envelope. Recovery rebuilds the identical structure, so a self-consistent but historically
     reduced provider record no longer matches the committed chain.
   - External-response live commit passes the already supplied terminal raw body only into this
     strict replay helper. Reopen still requires the explicit hash-checking resolver; no network or
     fallback retrieval was added.

3. **Fixture migration**
   - Older E2 cursor attacks used N=1/2 stores with a 40-node WS artifact, and older E1 tests did
     not supply the source WS. Only those fixtures were migrated to valid matching populations and
     typed source artifacts. Production validators were not weakened.

### Final sequential verification

All commands used `platform/.venv` with explicit role-specific base temp directories:

- focused semantic-network and transition-history attacks: `9 passed, 79 deselected in 0.84s`;
- complete storage suite, two consecutive post-format runs: `88 passed in 14.35s` and
  `88 passed in 14.32s`;
- storage + domain + state + feed: `187 passed in 28.56s`;
- explicit N=50,000 structure/query-plan regression: `1 passed, 87 deselected in 8.42s`;
- protocol + isolated-installation gates: `144 passed in 13.00s`;
- Ruff check: passed;
- Ruff format check: `2 files already formatted`;
- pip check: `No broken requirements found`;
- `git diff --check`: passed.

Pytest again emitted only the known shared-cache warning caused by another process holding the
separately configured `.pytest-tmp` cache. The explicit base temp directories and results were
unaffected. No full suite or coverage run was performed. No SQLite database, raw response, cache,
or checkpoint payload was added to Git. Nothing was committed or pushed.

## Eighth independent review repair: pre-commit external URI equality (2026-08-30)

This repair remains inside Phase 4B-8A storage and preserves the complete transition-chain and
strict network-artifact validation introduced above.

### RED to GREEN evidence

1. **One-sided terminal URI drift before commit**
   - RED: after a valid external terminal attempt was appended, changing only the `attempts` row
     to a different valid file URI while leaving the terminal transition at its original URI still
     allowed `commit_success()` to advance research state.
   - GREEN: the shared `_attempt_chain_entries()` path now exact-compares the terminal attempt row
     and terminal transition row on event ID, attempt index, status, raw-response URI, and
     raw-response hash, in addition to requiring equality of the typed terminal attempt. The
     mismatch is rejected before the success transaction begins.

2. **Coordinated invalid URI cannot use an in-memory body bypass**
   - RED: changing both terminal tables to the same relative, contract-invalid URI still allowed
     commit because the provided in-memory raw body/hash bypassed `ExternalResponseReference`
     construction.
   - GREEN: `_replay_attempt_payload()` now constructs and validates
     `ExternalResponseReference(uri, sha256)` whenever a row carries external URI/hash evidence,
     before consulting an in-memory body mapping or resolver. Correct body/hash evidence can no
     longer legitimize an invalid location.

Both attacks assert that rejection leaves progress, event-chain head, private state, latest public
pointer, feed cursor, and event history unchanged. The initial focused run was the expected
`2 failed`; the repaired run passed `2 passed`, and the combined existing URI/resolver focused set
passed `5 passed`.

### Final sequential verification

All commands used `platform/.venv` with explicit role-specific base temp directories:

- complete storage suite, two consecutive runs: `90 passed in 12.36s` and
  `90 passed in 11.67s`;
- storage + domain + state + feed: `189 passed in 37.79s`;
- explicit N=50,000 structure/query-plan regression: `1 passed, 89 deselected in 13.49s`;
- protocol + isolated-installation gates: `144 passed in 17.01s`;
- Ruff check: passed;
- Ruff format check: `2 files already formatted`;
- pip check: `No broken requirements found`;
- `git diff --check`: passed.

The only pytest warning remained the known shared-cache lock from another process; explicit base
temp directories and all test results were unaffected. No full suite or coverage run was
performed. No engine, checkpoint, retry-policy/default, model-seed pairing, network access, or
real adapter was added. No SQLite database or raw response was added to Git. Nothing was committed
or pushed.
