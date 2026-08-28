---
status: in_progress; review repairs implemented; pending independent re-review
authority: Phase 4B-7 implementation checkpoint; subordinate to protocol/specification chain
date: 2026-08-27
---

# Phase 4B-7 implementation checkpoint

## Boundary

This checkpoint covers only prompt view construction/rendering, strict response parsing, and a
deterministic script-only mock adapter. It does not implement retries, event execution, SQLite,
checkpoint recovery, vLLM/OpenAI clients, or formal model/runtime values.

## Implemented contracts

- `ValidatedPromptRunContext` independently replays the typed `FrozenSchedule`, `RunManifest`,
  source events, and source attempts once, then registers the complete validator-owned snapshot
  behind an exact-owner `id + weakref` handle. The public handle exposes scalar identity/metadata
  only: no schedule slots, event records, attempts, or mutable indexes. Consumers perform an O(1)
  owner lookup and never reserialize/hash the full source graph. `dataclasses.replace`, manual
  copies, foreign-cell handles, and scalar mutation fail closed. The weakref callback removes stale
  entries and checks the exact stored weakref before deletion, preventing a late callback from
  deleting a future ID-reuse registration.
- `advance_validated_prompt_run_context(...)` atomically appends one continuous succeeded event and
  its exact failed-then-successful attempt chain. It validates the frozen slot and all typed content
  hashes before mutation, advances in O(attempts-per-event), keeps the owner identity stable, and
  updates an incremental prefix commitment. A failed advance leaves the cursor, indexes, and
  commitment unchanged. Attempts may carry different explicit integer model seeds; this API does
  not define retry or model-seed pairing. Checkpoint recovery still creates a fresh context by
  replaying one typed `RunManifest`.
  Initial recovery registration requires the event/attempt indexes to exactly cover the manifest's
  complete succeeded prefix, so a later prompt cannot need an older source that was omitted from
  the owner snapshot.
  Registration and advancement now share one commitment algorithm: a stable run/seed/cell/schedule
  genesis followed by an ordinal fold over each canonical event hash and its ordered canonical
  attempt hashes. Re-registering the same complete evidence from a later manifest therefore
  reproduces the exact logical context ID and current prefix hash, while any legal event/attempt
  content change (including a different explicit `model_seed`) changes the prefix hash without
  imposing a seed-pairing rule.
  Concurrent readers now capture one immutable cursor/prefix version per operation. Advancement
  validates under a per-context writer lock, appends only new event/attempt keys, and publishes the
  new immutable version last. Thus metadata and prompt construction cannot combine an old cursor
  with a new prefix or expose newly appended indexes through an old version. Registry validation
  retains its short global lock, so validation of one run does not hold a global cross-run lock;
  there is no per-read or per-advance prefix copy.
  `PromptView` binds the baseline manifest hash, logical context identity, current prefix
  commitment, and the complete canonical pending
  `GenerationEvent`, matched seed, canonical cell, frozen schedule slot, topic,
  trusted population/template/persona replay, complete successful private-update history,
  replayed latest-K memory, event/topic-bound `ExposureRecord`, explicit mock context limits, and
  template identity/version. Rendering is a two-role message pair whose natural-language inputs
  are one deterministic JSON data payload; newline, pipe, role-marker, and Unicode line-separator
  text cannot create new prompt sections.
- `ParseEvidence` binds trusted adapter response/request/event/attempt, topic, explicit parser
  limits, raw response, and success/failure hashes. Parsing is exact ordered JSON with bounded UTF-8
  bytes and nesting; duplicate/extra fields, numeric or unknown labels, bool/nonfinite confidence,
  empty reasons, and `publish_flag` are rejected without repair or defaults. A public validator
  reparses the raw response and compares the complete evidence record.
- `AdapterRequest` carries a validator-issued integrity sentinel derived from a validated
  `PromptView`; deserialized, stale-ID, or accidentally mutated requests fail closed. This sentinel
  is not an authorization or sandbox boundary against arbitrary same-process Python code.
  `MockAdapter` returns one scripted response or
  exact-key timeout for the explicit attempt. A public validator replays request, script, attempt,
  mock seed, model/runtime identity, provider ID, raw response/error, and all hashes.
- `PromptView` and `AdapterResponse` deserialization is deliberately untrusted. Public validators
  replay all typed sources before returning new sealed records; `AdapterRequest.create` and the
  parser reject values without their integrity sentinel. All four cells share one byte-identical
  system contract. A versioned `trusted_control` JSON object carries only replay-derived factor
  booleans; absent identity/continuity are true omissions, while C0 still receives the same memory.
  Persona, population and all other natural text remain exclusively inside user JSON data.
- Prompt construction replays manifest run/seed/cell/recovery provenance. Every non-round-0
  private or social source must belong to the same run, precede the receiver event, exactly match
  its frozen schedule slot, and bind the final successful attempt. The final attempt's exact
  stance/confidence/public_reason must equal the committed `PrivateUpdate`; frozen publish status
  remains bound through event, update, and post evidence. Round 0 retains only its
  existing typed seed/topic/agent/hash exception with absent event/attempt fields.
- Every social candidate is replayed from typed `PublicPost`/`PrivateUpdate` evidence before any
  selected content is rendered, including expired round-0 candidates. This is one linear pass over
  candidate indexes. Attempts retain explicit integer `model_seed` evidence, but the public RNG
  registry exposes no `model_sampling` namespace while `P1_MODEL_SEED_PAIRING` remains unresolved;
  deriving it fails closed, so no equality/reuse/drift rule is introduced implicitly.
- Prompt budgets preflight every individual visible string plus memory/social counts before JSON
  serialization. Parser budgets require an exact raw string, reject both the character limit and a
  conservative `len(raw) > max_raw_bytes` condition before UTF-8 allocation or seal/hash work,
  then make one bounded strict UTF-8 encoding and enforce the exact byte count before response
  capability validation. These resource-limit failures are explicit fail-closed
  exceptions; ordinary malformed, Unicode-scalar, and depth failures retain evidence records.
- All artifacts are explicit `mock_only / not_frozen`. Determinism is an engineering property of
  this mock adapter and is not claimed for a future real model.

## Verification evidence

- 2026-08-28 final context-lifecycle/parser repair: focused regressions cover scalar-only opaque
  handles, point-lookup-only source maps, three consecutive succeeded events on one owner, atomic
  failure, varied explicit model seeds, a 50,000-slot no-replay counter, baseline/current prefix
  binding, and pre-encode byte-budget rejection.
- 2026-08-28 recovery-fold RED: the two new focused tests produced `2 failed` because checkpoint
  registration and live advancement used different prefix algorithms, and restored attempt-content
  drift did not affect the registered prefix. GREEN: `2 passed in 0.55s`; expanded context focused
  suite: `15 passed in 1.44s`.
- GREEN prompt/parser/mock/domain/feed focused suite: `159 passed in 18.42s`.
- 2026-08-28 deterministic concurrency RED: the coordinated prompt reader bound the post-advance
  prefix to its pre-advance event (`1 failed`), while the metadata regression failed because no
  single-version capture existed (`1 failed`). Both use `threading.Event` coordination and no
  timing sleeps. GREEN: both new regressions `2 passed in 0.61s`; context focused
  `17 passed in 1.41s`; expanded prompt/parser/mock/domain/feed focused suite
  `161 passed in 18.74s`.
- GREEN lifecycle subset: `13 passed in 1.35s`; parser resource subset: `3 passed in 0.55s`.
- Ruff check passed; Ruff format was applied to `prompt.py` and the exact focused file set then
  passed format check. `git diff --check` passes apart from repository line-ending warnings.
- No full suite or coverage was run during this repair, by design; those remain a one-time release
  action after independent re-review.

- 2026-08-28 final-blocker RED: four focused regressions failed for the intended reasons: source
  graph reserialization on every consumer, stale cached schedule acceptance, registered
  `model_sampling` derivation, and oversized raw input reaching response seal/hash work.
- 2026-08-28 GREEN: prompt/parser/mock/domain/feed focused suite: `151 passed in 16.29s`.
- The full-suite, coverage, and scale numbers below are historical evidence from the preceding
  snapshot and must be rerun once after independent re-review; they are not final evidence for the
  current owner-registry/parser/RNG snapshot.

- Prompt/parser/mock/domain/feed focused suite: `145 passed in 16.31s`; the final three-blocker
  regressions separately passed `9 passed` after their observed RED failures.
- Final fresh continuous full suite: `522 passed in 75.45s`.
- Production-source coverage: `522 passed in 232.90s`; `5004 statements / 728 missed / 85%`.
- New module coverage: adapter base 90%, adapter mock 87%, parser 87%, prompt 81%.
- N=1000 prompt construction plus rendering benchmark: `10.0010 seconds`.
- N=50,000 one-time run-context validation, now including the content-bound sentinel digest:
  `0.9033 seconds`; three sparse event-ID membership lookups: `0.0000031 seconds`.
- The 10,000-level JSON attack returned bounded failure evidence (`1 passed` focused); a
  50,000-character valid reason parsed successfully in `0.0153 seconds` under explicit limits.
- Protocol/installation gates: `144 passed`. Ruff check, Ruff format check, `pip check`, and
  `git diff --check`: pass.
- Canonical and packaged schema SHA-256:
  `3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`.
- Draft unresolved marker count: 88.

## Review state and next action

The first review rounds failed and every reported P1/P2 plus the resumed manifest provenance
blocker now has a regression. The latest 3 P1 + 1 P2 context-lifecycle/parser repair set is
focused-green, but Phase 4B-7 is not closed.
Fresh independent specification/
anti-pattern and code-quality re-reviews plus release verification must approve the same working
tree before commit/push. Phase 4B-8 has not started.
