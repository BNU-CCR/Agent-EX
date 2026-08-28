---
status: resumed 2026-08-27; blockers implemented; superseded by implementation checkpoint
authority: Phase 4B-7 interruption handoff; supersedes completion implications in the implementation checkpoint
date: 2026-08-18
branch: codex/paper1-phase4b
head: d4176c3fd6571f9ae300aa870888743150946397
---

# Phase 4B-7 interruption handoff

> 2026-08-27恢复注：下述暂停状态仅保留为历史证据。manifest/cell/frozen-schedule
> provenance及persona控制语义已实现并验证；当前权威恢复点为同目录
> `2026-08-18-phase4b7-implementation-checkpoint.md`，阶段仍待独立复审，未提交或推送。

## Stop state

Work stopped at the user's request to conserve quota. Phase 4B-7 is **not complete**, has not been
committed or pushed, and Phase 4B-8 has not started. Preserve the current working tree; do not reset
or discard it.

The working tree contains the expected Phase 4B-7 implementation, review repairs, tests, and status
documents. At pause time `git diff --check` passed (apart from existing line-ending warnings), and
`platform/tests/test_prompt.py` compiled successfully.

## Implemented before the pause

- Prompt construction, deterministic JSON rendering, strict response parsing, and the script-only
  mock adapter exist as `mock_only / not_frozen` capabilities.
- Prompt, request, and response consumers require validator-issued integrity sentinels; objects do
  not carry the HMAC key and deserialization remains untrusted. This is not a security boundary:
  arbitrary same-process Python code is inside the trusted computing base and can call validators.
- Topic identity is carried through prompt, request, response, parsing, and parse-evidence replay.
- Exposure text is replayed against typed selection/post/update evidence rather than trusted by
  self-consistent hashes alone.
- The system message is static; natural population/topic/state/memory/social text is serialized as
  JSON data. Prompt/parser size preflights occur before the large serialization/UTF-8 copy.
- The previous public rendering bypass and readable-seal-material bypass have RED-to-GREEN tests.

## Current RED and remaining blockers

The newest test is intentionally RED:

- `test_prompt_requires_manifest_bound_run_cell_and_frozen_schedule_provenance`
- observed result: `1 failed, 20 deselected`
- reason: `build_prompt_view` does not yet accept and validate a typed `RunManifest`.

Two specification blockers remain:

1. **Same-run/cell provenance.** Private history/state/memory and non-round-0 social post/update
   sources must be anchored to the receiver's typed `RunManifest`, frozen schedule, actual earlier
   `GenerationEvent`s, and final successful attempts. Reuse `validate_evidence_graph` or an equally
   strong validated capability. Round 0 is the sole cross-cell exception within a matched seed and
   must retain its existing typed seed/topic/agent/hash checks with empty event/attempt fields.
2. **Persona manipulation semantics.** Approved identity/continuity semantics must remain effective
   as trusted mock instructions, while all population-provided natural text remains data-only. The
   exact persona wording is not frozen: use a versioned `mock_only / not_frozen` template artifact,
   keep formal paths fail-closed, and do not claim the mock wording as a formal research value.

Do **not** add a retry/model-seed rule: `P1_MODEL_SEED_PAIRING` is still unresolved. Do not rename
`public_reason`; `D-2026-07-29-02` freezes that output field.

## Evidence caveat

Earlier full/coverage results (`503` or `505` passed, and the previously reported 91% coverage) are
historical intermediate-snapshot evidence only. Subsequent seal/topic/test edits changed the code
and test hashes. They must not be cited as final Phase 4B-7 evidence.

The latest lightweight evidence is:

- Integrity/topic/prompt/parser/mock targeted tests: `49 passed` before the newest manifest RED;
- existing persona plus cross-run focused tests: `3 passed`;
- newest manifest provenance test: expected RED, `1 failed, 20 deselected`;
- `git diff --check`: pass, with line-ending warnings only;
- `py_compile platform/tests/test_prompt.py`: pass.

## Recovery order

1. Confirm branch/HEAD and compare `git status --short` with this handoff; preserve all listed
   Phase 4B-7 changes.
2. Read `AGENTS.md`, the Phase 4B plan, this handoff, and
   `logs/2026-08-18-phase4b7-implementation-checkpoint.md`.
3. Turn the manifest/cell RED green by adding typed run/schedule/evidence provenance to both
   `build_prompt_view` and `validate_prompt_view`.
4. Add the persona-semantics RED, implement only a versioned explicit mock template solution, and
   keep population natural text in JSON data.
5. Run focused tests, then a fresh continuous full suite, production-source coverage, scale/deep/
   long-input checks, Ruff/format/pip/diff, schema/formal gates, and hygiene checks.
6. Obtain fresh independent specification, code-quality, and release approvals on the exact same
   stable snapshot. Only then mark 4B-7 complete, commit, and push. Stop before Phase 4B-8.
