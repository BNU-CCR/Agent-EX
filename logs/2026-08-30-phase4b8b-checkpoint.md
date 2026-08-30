---
status: implementation checkpoint; uncommitted
authority: Phase 4B-8B checkpoint/recovery implementation evidence; subordinate to frozen protocol, Phase 4A completion design, and SQLite execution truth
date: 2026-08-30
branch: codex/paper1-phase4b
baseline: 0c5f9f3
---

# Phase 4B-8B checkpoint and recovery checkpoint

## Scope completed

- Added `platform/src/agent_ex/checkpoint.py` with a canonical, hash-bound
  `Checkpoint` record and the public APIs `build_checkpoint`, `validate_checkpoint`,
  `write_checkpoint_atomic`, and `load_checkpoint`.
- Added a read-only `RunStorage.recovery_evidence()` projection. It always begins with
  full SQLite integrity replay, reconstructs any committed historical prefix, and returns
  immutable canonical private-state, public-stock, latest-pointer, cursor, event-chain, and
  current-attempt evidence. It does not expose the SQLite connection or mutate storage.
- Bound checkpoint version; storage schema; run, protocol, and schedule identities; artifact,
  graph, source-graph, roster, and round-0 hashes; baseline/current manifest projection hashes;
  next ordinal/current event; all state collection roots; event-chain head; and the complete
  current-event attempt-transition prefix.
- Distinguished current, trustworthy stale, ahead, and conflicting checkpoints. A stale
  checkpoint is accepted only after full storage verification and historical prefix replay;
  rebuilding it requires a fresh `build_checkpoint()` from current SQLite truth.
- Preserved same-event recovery semantics for pending/in-progress/failed attempts and exposed
  the already-landed-success action needed to complete an event transaction without issuing a
  new attempt. No retry budget or model-seed pairing policy was chosen.
- External raw responses remain external: checkpoint evidence binds URI and SHA-256 but does
  not inline the resolved body.
- Atomic writes use a same-directory temporary file, flush, file `fsync`, and `os.replace`.
  Failures before creation, during flush, or during replace preserve the prior checkpoint and
  remove the temporary file.
- Canonical JSON loading rejects duplicate keys, noncanonical bytes, invalid UTF-8, excessive
  size/depth, URI input in place of a local path, unsupported versions, malformed lifecycle
  prefixes, and recomputed-hash structural tampering.

Checkpoint remains a derived recovery artifact. It cannot update or override SQLite storage,
the frozen protocol, schedule, baseline manifest, or research decisions. It is intentionally a
checkpoint-boundary full replay rather than a per-event hot-path operation.

## TDD evidence

The work used observed RED then minimal GREEN cycles in `platform/tests/test_checkpoint.py`:

1. Missing checkpoint module produced collection RED; deterministic empty sealed-run build and
   current validation then passed.
2. Current PENDING, IN_PROGRESS, FAILED, and SUCCEEDED-uncommitted transition prefixes plus
   stale classification produced five RED failures, then passed with the read-only historical
   recovery projection.
3. Missing canonical load/write APIs produced collection RED, then canonical round-trip,
   hash tamper, duplicate/noncanonical input, and atomic failure injection passed.
4. Protocol/graph/source binding and a failed-prefix stale checkpoint produced two RED failures,
   then passed with exact immutable binding and transition-prefix comparison.
5. A regression test observed two full storage verifications per build; the implementation was
   reduced to exactly one full replay.
6. Four malformed attempt-prefix cases (missing transitions, attempt-index gap, illegal
   lifecycle, and row-envelope drift) were accepted in RED, then rejected during load.
7. An untrusted dataclass could encode a structurally incomplete stale prefix in RED, then was
   closed by mandatory typed payload replay before validation.
8. Adding the package-root API caused the existing exact `__all__` test to fail, then the public
   API contract was updated and restored to green.

## Recovery and integrity boundaries verified

- empty sealed run, successful prefix, complete run, and close/reopen;
- pending, in-progress, failed, and succeeded-uncommitted current attempts;
- failed attempt followed by a later successful retry on the same event;
- committed ordinal advance and no current event after completion;
- tampering of version/schema, run/protocol/schedule, roster/round-0, artifacts, manifest
  projections, state/public/pointer/cursor roots, event chain, event identity, and attempt data;
- stale versus ahead/conflict behavior and a storage attempt-journal gap;
- external response URI/hash binding without response-body duplication;
- atomic failures before temp creation, at `fsync`, and at replace;
- local path, maximum byte size, JSON depth, duplicate-key, and canonical-byte gates;
- direct storage recovery projection and checkpoint state-root equivalence.

## Verification

All commands used `platform/.venv` and isolated pytest temp/cache directories:

- checkpoint suite (fresh closeout rerun): `47 passed in 7.11s`;
- checkpoint + storage + domain + state + feed: `236 passed in 40.26s`;
- protocol + installation: `144 passed in 11.70s`;
- package-root public API targeted closeout rerun: `1 passed in 0.67s`;
- explicit N=50,000 schedule checkpoint boundary: `1 passed in 2.05s` including fixture and
  database construction; checkpoint construction itself remained below the frozen 8-second gate;
- Ruff check: passed;
- Ruff format check: five files already formatted after the public-API test update;
- `pip check`: no broken requirements;
- `git diff --check`: passed, with only Git's existing LF-to-CRLF working-copy warnings.

No full suite or coverage run was performed in this subphase.

## Explicitly not implemented

- event engine, adapter invocation, network access, or real model execution;
- retry-count, timeout, checkpoint-frequency, or model-seed-pairing defaults;
- concurrent writers within one run;
- formal research-parameter freezing or any bypass of unresolved formal gates;
- checkpoint authority over SQLite, manifest, protocol, or schedule;
- committing SQLite databases, checkpoint payloads, raw responses, or caches to Git.

Nothing in this work was committed or pushed.

## Terminal-review repair

The terminal review found six recovery-boundary gaps. Each repair was driven by an
observed failing test before the implementation was changed:

1. Same-ordinal checkpoints now classify a strict, structurally valid attempt-transition
   prefix as `stale`; exact equality remains `current`, while a future or forked prefix is
   rejected as a conflict. This covers empty-to-pending, pending-to-in-progress,
   failed-to-next-retry, and succeeded-but-uncommitted progress. An old checkpoint retained
   after an injected atomic-write failure closes the loop by validating as stale.
2. Every checkpoint transition now has an exact row envelope and a separate canonical
   checkpoint-payload hash. Inline transitions undergo `GenerationAttempt` domain replay;
   external-response transitions undergo a strict redacted replay that validates all
   non-body domain fields, lifecycle/timestamps, provider progression, URI/hash, status, and
   row bindings. Removing `request_id` and recomputing the outer hash is rejected.
   `resume_action` first replays the complete checkpoint structure and cannot operate on a
   dataclass assembled with unvalidated nested data.
3. `RunStorage.recovery_evidence()` recursively freezes nested mappings, sequences, and sets.
   The checkpoint builder explicitly thaws this projection into canonical values rather than
   retaining mutable references.
4. Loading uses one opened file descriptor for `fstat` and a bounded `MAX_BYTES + 1` read;
   POSIX adds `O_NOFOLLOW`. The opened handle, not a later path lookup, is authoritative, so a
   path replacement cannot select a second file after opening.
5. A string- and escape-aware preflight depth scan rejects even a 100,000-level JSON nesting
   bomb as `ValueError`; parser recursion failures are normalized to the same public error
   family.
6. Atomic replacement now fsyncs the parent directory on POSIX. If directory fsync fails after
   replacement, the call fails closed but preserves the already-replaced, valid target and
   removes the temporary file. This gives the intended rename durability boundary on cloud
   Linux. Windows still guarantees temp-file flush, file fsync, and atomic replace; Python and
   Windows do not expose a portable directory-fsync equivalent, so the helper records that
   narrower local durability boundary explicitly.

Fresh post-repair gates (all with isolated pytest temp/cache directories):

- checkpoint suite: `66 passed in 9.10s`;
- storage suite: `90 passed in 13.01s`;
- domain + state + feed: `99 passed in 17.44s`;
- combined focused total: `255 passed` across the preceding three fresh runs;
- explicit N=50,000 boundary: `1 passed in 1.60s`;
- protocol + installation: `144 passed in 11.84s`;
- Ruff check, `pip check`, and `git diff --check`: passed;
- Ruff format identified and formatted the two review-touched checkpoint files; the final
  post-format checkpoint rerun passed `66 passed in 6.45s`.

No full suite or coverage run was performed during review repair.

## Final quality-review repair

A subsequent independent quality review found two trust-boundary bypasses and one Windows
path boundary. Each production change again followed an observed RED before minimal GREEN:

1. A custom mapping whose equality always returned true could make an untrusted `Checkpoint`
   compare equal to verified SQLite evidence, and a mapping that changed between reads could
   make atomic write validation inspect different bytes from those serialized. The two attack
   tests produced `2 failed, 66 deselected`. Both `validate_checkpoint()` and
   `write_checkpoint_atomic()` now continue exclusively with the normalized object returned by
   `Checkpoint.from_payload()`. The focused rerun passed `2 passed, 66 deselected`.
2. A redacted external `FAILED` transition with non-empty usage could omit `total_tokens` after
   recomputing all checkpoint-visible hashes. The attack test produced
   `1 failed, 68 deselected`. Redacted replay now applies the same required-key, integer, and
   total-equality usage contract to every non-empty usage payload, including failures. The
   external-response focused rerun passed `3 passed, 66 deselected`.
3. Windows previously rejected stable symlinks only through a path precheck and then used a
   following CRT open. Because the review host lacks file-symlink privilege, the RED test used
   an actual NTFS junction plus a simulated missed precheck; it failed with a followed-handle
   `PermissionError` (`1 failed, 69 deselected`). Windows loading now opens exactly one native
   handle with `CreateFileW(FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS)`, inspects
   `FileAttributeTagInfo`, rejects `FILE_ATTRIBUTE_REPARSE_POINT`, and transfers only an
   ordinary handle to the bounded CRT reader. The handle/path boundary rerun passed
   `4 passed, 66 deselected` and includes ordinary-file loading on Windows.

Fresh post-fix verification with isolated temp/cache directories:

- checkpoint suite: `70 passed in 6.78s`;
- storage suite: `90 passed in 14.31s`;
- domain + state + feed: `99 passed in 19.98s`;
- related focused total: `259 passed` across those three fresh gates;
- Ruff check: passed;
- Ruff format check: both touched Python files already formatted;
- `git diff --check`: passed with only existing LF-to-CRLF working-copy warnings.

No files were committed or pushed by this repair.
