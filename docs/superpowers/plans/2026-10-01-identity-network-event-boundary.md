# Identity-network Event Boundary Implementation Plan

> **For agentic workers:** Execute inline using executing-plans and TDD.
> User approved proceeding with the shared execution path on 2026-10-01.

**Goal:** Connect new study prompts to existing topic/state/provider contracts
without weakening legacy validators or claiming a durable six-cell run.

**Architecture:** Step 5a of the approved 2x3 design. Version new renderer to v2,
bind a typed TopicPackage, and use its label strings and 1–5 integer confidence.
Prepare an immutable study event and shared Phase0BVllmEventRequest; finalize
with existing DiagnosticParseEvidence and PrivateUpdate/PrivateState/PublicPost.
No SQLite write or HTTP orchestration is introduced at this boundary.

**Tech Stack:** Existing Python 3.12, pytest, canonical hashes, shared state,
topic and vLLM event adapter.

## Task 1 — Repair the provider-contract mismatch

Files: identity_network/prompts.py, groups.py and their tests; manipulation tests.

- [x] Reproduce incompatibility before fixing:
  `assert "confidence (a JSON integer from 1 to 5)" in prompt.messages[0]["content"]`.
  Pass the existing `topic()` fixture as `topic_package`; initial/current/history
  and shown post stance values are `label-0`…`label-6`, not integer guesses.
- [x] Replace free topic fields with typed `topic_package: TopicPackage`; take
  fact card, statement and allowed labels from it. Bind its ID/hash in backend
  evidence. Version renderer `paper1.identity-network.prompt.v2`.
- [x] Add strict homogeneous integer-or-string strata support in group creation
  for explicit diagnostic integer fixtures and actual topic labels. Refuse mixed
  or empty string strata. Never coerce labels or confidence.
- [x] Run preparation + legacy topic/parser tests; existing parser remains byte-identical.

## Task 2 — Pure shared event bridge

Create identity_network/execution.py and test_identity_network_execution.py.

- [x] Write missing-feature tests around this API:

```python
prepared = prepare_study_event(
    run_id=run_id, event_ordinal=0, attempt_index=1,
    previous_event_hash=genesis_hash, publish_flag=False,
    prompt=prompt, private_state=initial_state, topic_package=topic(),
    parser_limits=limits, model_seed=17,
    generation_settings={"temperature": 0.0, "top_p": 1.0, "max_tokens": 128},
    adapter_binding_hash=binding_hash,
)
result = finalize_study_response(prepared=prepared, response=response)
assert result.public_post is None
assert result.private_state.confidence == 4
assert result.trace.payload["metadata"]["committed"] is False
```

- [x] Prepare validates explicit run/ordinal/attempt, previous hash, typed state,
  matching topic/receiver/pre-state, prompt renderer/version and exact messages.
  Derive shared event/attempt identities; no new main loop or implicit model seeds.
- [x] Finalize checks full request/response and raw/transport binding before parsing.
  Reuse DiagnosticParseEvidence and state construction; no parser repair/coercion.
  Failed responses return the same state object and no private update/public post.
- [x] Successful responses construct prospective state/update/public post using the
  externally supplied publish flag. Trace binds prompt, pre-state confidence,
  prior event hash, request/response/transport/parse hashes and prospective output.
  Output is explicitly uncommitted; durable commit and feed-cursor writes are excluded.
- [x] Test all six cells with fake HTTP through the real shared adapter and journal;
  test success, no-publish, invalid JSON/stance/confidence, foreign response and topic,
  retry same event identity, round-trip trace hash and immutable pre-state.

## Task 3 — Evidence and handoff

- [x] Run targeted legacy adapter/parser/state/preparation regression, Ruff and diff checks.
- [x] Use one focused independent review; fix important findings and regression-test them.
- [x] Record actual results in progress/findings.
- [x] Commit source/doc changes with the completed Step 5a milestone.

## Remaining gates

This milestone is not the complete step 5. Shared RunStorage still validates
legacy P1 cells. Next integration must add SIS-specific discriminated bindings,
input/trace reader unions, serial atomic commit, exact-cover/reopen/resume and
six-cell materialization. Actual publication exists only after a successful
durable state commit. No model request is sent to AutoDL in this local step.
Manipulation checks still require explicit sample/criteria/runtime configuration.
