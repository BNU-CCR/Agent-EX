---
status: complete; independently reviewed
authority: Phase 4B-6 implementation evidence; subordinate to the protocol/specification chain
last-verified: 2026-08-18
---

# 2026-08-18 | Phase 4B-6 implementation checkpoint

## Acceptance boundary before implementation

Phase 4B-6 is limited to immutable, versioned mock-only/not-frozen state, feed, memory and
exposure evidence primitives. It must provide:

- separate `PrivateState` / append-only `PrivateUpdate` and `PublicPost` / latest-public pointer
  records; social inputs cannot carry private reasons or confidence;
- a receiver- and exposure-graph-bound `FeedCursor` that never regresses;
- a finite unread feed over public posts only: first activation may see neighbor round-0 posts,
  later activations see only posts after the prior cursor and before the current event;
- latest-B overflow with explicit expiry, no backfill, legal empty feeds and repeated senders;
- a message-slot permutation from the independent `message_slot` RNG namespace whose key binds
  matched seed, receiver and global event ordinal but not cell/exposure content;
- exposure evidence binding candidates, selected/expired posts, source event/post IDs, original
  order, message age, slot, rendered public text, hashes, cursor before/after and provenance;
- a read-only oldest-to-newest memory view over the latest K successful private updates,
  independent of whether each update was published, with full input-history evidence hash;
- strict JSON round-trip, canonical hash binding, bool/int and cross-seed/source/hash/cursor/future
  post attack rejection, plus explicit B={4,6,8}, K={1,3,5} mock challenge inputs;
- N=20/100/1000 carrying capacity without model calls or opinion-result selection.

Out of scope: prompt rendering/parser/model adapters (4B-7), transaction/rollback/strict serial
engine/checkpoint recovery (4B-8), real data/model calls, formal parameter freezing, or any result
analysis. B=6 and K=3 may appear only as explicitly supplied mock candidates and never as defaults.

## TDD ledger

- State slice: RED was `ModuleNotFoundError: agent_ex.state`; GREEN was `9 passed` before the
  matched-seed hardening. The implemented records are `PrivateUpdate`, `PrivateState`,
  `PublicPost` and `LatestPublicPointer`, with strict JSON/hash/mock-only validation.
- Memory slice: RED was `ModuleNotFoundError: agent_ex.memory`; GREEN was `9 passed`. The view
  takes explicit K in `{1,3,5}`, includes unpublished successful private updates, orders oldest to
  newest, allows round 0 to roll out, and binds the complete source-history hash.
- Feed slice: RED was `ModuleNotFoundError: agent_ex.feed`; GREEN was `12 passed`. It covers first
  activation round-0 candidates, latest-B overflow, explicit expiry, no backfill, legal empty
  feeds, repeated senders, future-post/cursor/cross-graph rejection and N=1000 public posts.
- Extended exposure slice: RED was missing `build_exposure_record`; GREEN migrated the Phase 4B-2
  minimal `ExposureRecord` to a hash-bound record containing candidate/selected/expired post IDs,
  cursor hashes, source event/post IDs, ages, original order, display slots and rendered hashes.
- Public API slice: the exact-export test failed with all new names absent, then passed after the
  tested Phase 4B-6 surface was exported.
- Attack RED/GREEN: state/public/memory/feed initially did not bind `matched_seed`; the entire
  source chain now binds it and feed rejects cross-seed public posts. A second RED showed that
  message-slot provenance changed when E1/E2 selected counts differed; its key is now exactly the
  common `matched_seed × receiver × event_ordinal` scope (plus registered artifact kind), so sparse
  and dense E1/E2 selections share the same slot seed without sharing content. A third RED showed
  a forged cross-seed cursor reached only a downstream selection-ID error; selection construction
  now directly validates cursor seed/receiver/mode/graph/advance, source seed, input hashes and
  exact slot-RNG coordinates.

## Implementation candidate and verification

The first independent review correctly reproduced source-replay, selection-replay, round-0
evidence and accumulated-log performance gaps. Each reproduced defect became a regression test
before its repair:

- source records now bind a `TopicPackage` ID/hash and its exact seven textual labels;
  `PrivateState`, `PublicPost` and `MemoryView` have trusted-source replay validators; confidence
  is restricted to 1..5, round 0 must publish, and post event ID/ordinal are an exact pair;
- `ExposureSelection` can be accepted only by deterministic replay from the trusted incremental
  unread slice. Round-0 inputs are normalized by stable post ID before seeded admission, and
  diagnostics, latest-B partition, source fields, age/order, input hashes and both RNG provenance
  records are compared exactly;
- `ExposureRecord` now binds graph, capacity, round-0 provenance and source post/update hashes.
  Evidence-graph validation binds exposure seed to the manifest and fails closed for round-0
  sources unless trusted post/update evidence is supplied;
- memory replay recomputes the complete ordered successful-update history hash and exact latest-K
  items, including seed, source update hash and private text;
- the feed API accepts only a storage-provided round-0 neighbor set or cursor-after
  `unread_public_posts` slice. It rejects non-neighbors, round-0 after first activation, posts at or
  before the cursor and current/future posts; it no longer receives or rehashes cumulative logs.

The final re-review then closed one remaining P1 and two P2 boundaries, again with observed REDs
before implementation:

- evidence-graph validation now requires real typed `PublicPost` and `PrivateUpdate` mappings plus
  the bound `TopicPackage` whenever an exposure contains selected social sources or any round-0
  candidate, including candidates that all expired. It replays every public post from its update
  and checks seed/topic/agent/hash plus the exact succeeded source event ID, ordinal, frozen
  publish flag and source attempt. Duck-typed `SimpleNamespace` evidence is rejected;
- `validate_latest_public_pointer(...)` replays the exact latest post and optional previous pointer,
  binding post ID/hash, seed, topic, agent and monotone round-0/event ordinal semantics; it is part
  of the tested public API;
- neighbor IDs are validated for uniqueness and then sorted before input hashing/replay, so two
  orderings of the same graph-neighbor set produce byte-identical selection IDs and hashes.

Two final P1 attacks were then reproduced and closed: event-backed updates must bind the source
event's last attempt, which must belong to that event and be `SUCCEEDED`; and every candidate now
has an exact ordered `candidate_post_hash`. This rejects binding an earlier failed retry and
rejects expired round-0 content substitution that preserves deterministic update/post IDs, plus
missing, reordered, forged or boolean candidate hashes.

The last expired-event P1 was handled with a clean TDD restart: the premature implementation was
removed, and dedicated tests first demonstrated that a normal event candidate could expire while
its typed evidence was omitted, replaced under the same deterministic ID, moved across seeds or
bound to a failed retry. The unified validator now iterates every ordered candidate ID/hash and
applies the same typed post/update, topic, seed, actual event and final-successful-attempt replay;
selected arrays are then checked as additional display/source evidence rather than as the only
source-validation path.

Finally, typed candidates now reconstruct the actual round-0 candidate ID tuple in original
candidate order. That tuple must exactly equal the recorded `round0_candidate_post_ids`; clearing
the IDs and RNG hash cannot hide a real round-0 post, and an event post cannot be mislabeled as
round 0. Round-0 event-field rules apply to the reconstructed set.

The final receiver-self P1 also followed a dedicated RED/GREEN cycle. A normal event-backed post
could previously remain as an expired candidate authored by the receiver while another valid post
was selected. The all-candidate typed replay now rejects receiver authorship before its round-0 or
event branch, so the same rule covers selected and expired candidates from both namespaces.

- New modules: `state.py`, `memory.py`, `feed.py`; extended `domain.ExposureRecord`; tested public
  exports added in `agent_ex.__init__`.
- Post-repair targeted state/memory/feed/domain/initialization suite: `121 passed`.
- Final independent fresh full suite: `459 passed in 68.59s`, with no skips or xfails.
- Final independent coverage suite: `459 passed in 218.13s`;
  `3922 statements / 566 missed / 86%` overall.
  New modules: `feed.py 84%`, `memory.py 87%`, `state.py 88%`; extended `domain.py 81%`.
- The explicit N=1000/T=50 incremental call-shape test made 50,000 empty-slice selections in
  `12.99s`; each call supplied only its event-local unread slice, never the cumulative post log.
- Independent specification/anti-pattern and code-quality re-reviews are both `APPROVED`; the
  independent release verification is `PASS`. The two supplemental attack suites passed as
  `18 passed` and `2 passed`; the combined protocol/installation gate passed as `144 passed`.
- Ruff check, repository format check, `pip check`, `git diff --check`, schema mirror, draft
  unresolved markers, formal fail-closed and generated human-summary sync all pass. The explicit
  five protocol gates and all four installation tests passed.
- The canonical pre-documentation verified candidate snapshot SHA-256 is
  `3563f328c7f749b423b7e8bb01aa99d7bf20ffe92d458c454f9f6a67ccf9fe36`; documentation changes
  require a new release snapshot. Both schema mirrors have SHA-256
  `3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`.
- No real model, prompt/parser/adapter, SQLite, checkpoint or engine was added. No schema,
  protocol-YAML, research-QA or formal value changed. The draft still contains 88
  `UNRESOLVED[...]` markers; every artifact remains `mock_only / not_frozen`, and B/K remain
  caller-supplied mock candidates rather than frozen formal values.

Phase 4B-6 is therefore `complete / independently reviewed`. Phase 4B-7 has not started.
