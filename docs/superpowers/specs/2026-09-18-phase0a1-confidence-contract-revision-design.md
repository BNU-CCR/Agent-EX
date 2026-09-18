---
status: approved design; first independent-review issues addressed; pending re-review and user written-spec review
authority: Phase 0A-1 calibration measurement-contract revision; subordinate to the frozen protocol chain
approved-by: user
approved-date: 2026-09-18
supersedes: only the underspecified response-format wording and stateless format-repair construction used by the first Phase 0A-1 816-case diagnostic run
---

# Phase 0A-1 Confidence Contract Revision Design

## 1. Purpose and boundary

The first real 816-case run completed all scheduled cases and preserved 1,511 transport
responses, but it is ineligible for candidate comparison: the prompt never declared that
`confidence` is a separate JSON integer on `1..5`, and the format-repair request did not
include the first raw response. The run is already terminally marked
`diagnostic incomplete` and remains immutable external evidence.

This revision fixes that common measurement contract before any candidate is compared. It
does not change the candidate topics, personas, stance anchors, case inventory dimensions,
generation settings, parser acceptance rules, gate thresholds, topic priority, or formal
parameter authority. It does not inspect candidate outcomes to tune the wording.

## 2. Chosen approach

Use one uniform prompt-and-repair contract for every candidate and every case. Do not add
guided decoding or provider-specific JSON schema, because that would broaden the runtime
intervention and reduce comparability with the already approved adapter. Do not relax,
coerce, or clip parser values, because doing so would alter recorded model answers and hide
contract violations.

The change has two parts:

1. Every semantic request explicitly defines all three fields and keeps the stance and
   confidence ranges distinct.
2. A format-repair request includes the immediately preceding raw model response as an
   `assistant` message, followed by a narrowly scoped repair instruction.

## 3. Semantic request contract

The existing system persona, fact card, statement, optional continuity history, stance
anchors, and predeclared field-order challenge remain unchanged. The final user instruction
must additionally state, uniformly across all 816 cases:

- `stance` is a JSON integer on the declared stance scale: `1..7` for the seven-point
  condition or `0..10` for its challenger;
- `confidence` is independent of the stance scale and is a JSON integer from `1` to `5`;
- `public_reason` is non-empty text no longer than 2,048 characters;
- the response is exactly one JSON object, uses the predeclared field order, contains no
  extra keys, and contains no Markdown or commentary.

The wording must not define confidence by reference to agreement intensity. It represents
the model's certainty in its answer and therefore cannot inherit the stance range.

## 4. Format-repair contract and provenance

`ProbeRequest.create` must require a run-bound repair context when creating a
`format_repair` request and must reject repair context for a semantic request. The context
has two distinct roles:

- the **repair origin** is the unique semantic `ProbeAttempt` whose transport outcome is a
  string response, whose bound parse evidence failed format validation, and whose resulting
  case status is `format_pending`;
- the **immediate predecessor** is the last durable attempt in the same case chain. For the
  first repair request it is the repair origin. For a transport retry of that repair, it is
  the preceding repair transport failure with `pending` status, while the repair origin
  remains unchanged.

A parsed semantic response, an explicit refusal, a semantic response without its exact
run-bound parse evidence, and a failed or successful prior repair cannot become a repair
origin. The context must fail closed if the origin or predecessor belongs to another case,
is not the correct prior attempt index, has drifted request/response/parse hashes, or is not
consistent with the durable case-status transition.

The rendered message sequence is:

1. the exact original system message;
2. the exact original user message;
3. an `assistant` message containing the exact first raw response;
4. a final `user` message that requests format repair only.

The repair instruction must preserve the substantive stance and reason, require confidence
to be expressed on the separate `1..5` scale, restate the exact case-specific stance range
and field order, and prohibit extra keys, Markdown, and commentary. It authorizes only the
minimal schema correction needed to express the same answer under the declared contract.

The full rendered message list remains hash-bound into the request identity. In addition,
the request schema and identity must bind the repair origin's attempt ID, attempt record hash,
attempt index, response ID, response record hash, parse-evidence ID, and parse-evidence record
hash. They must also bind the immediate predecessor's attempt ID, attempt record hash, and
attempt index. Semantic requests carry none of these repair fields. Consequently, two
response records with identical text cannot produce indistinguishable repair provenance,
and a repair transport retry cannot hide or skip its preceding failed attempt.

The runner and resume path derive both roles only from the durable per-case attempt chain.
They locate the unique semantic `format_pending` origin and require the chain tail to be the
valid immediate predecessor for the requested transition. The review bridge reconstructs a
repaired request from the same durable origin and chain tail and fails closed on missing,
reordered, cross-case, duplicated, or hash-drifted evidence.

Transport retries retain their current purpose. A retry of a semantic attempt does not gain
repair context. A transport retry of a format-repair attempt binds its immediately preceding
repair transport failure but reuses the same repair-origin semantic response. It therefore
keeps identical assistant history and repair-origin provenance while receiving the next
already-recorded attempt index. Crash/resume must derive exactly the same origin binding as
an uninterrupted run.

## 5. Evidence isolation and re-approval

The prior archive
`/root/autodl-tmp/agent-ex-phase0a1-probe-816-v1` and its control directory remain untouched.
No failed case is selectively replayed and no old response enters the replacement run.

After implementation and verification, the complete specification and case inventory are
re-materialized from scratch. Any affected combined, probe, runtime, semantic, candidate,
credential, or archive-control artifact is rehashed. Execution is blocked until the owner
approves the new source bundle and all six final approval groups by exact full SHA-256.

The replacement run uses a new archive path, run instance identity, environment lock, and
immutable manifest. It executes all 816 cases. Only that isolated run may proceed to
candidate comparison, semantic review, selection, and seal if its existing gates pass.

## 6. Test and verification design

Implementation follows test-first red/green cycles. Regression tests must prove:

- every expanded case declares `confidence` as an independent JSON integer on `1..5`;
- both stance scales retain their own exact integer ranges and cannot be confused with the
  confidence range;
- the requested JSON field-order challenge is still rendered exactly;
- a repair request carries the exact first raw response as assistant history;
- repair creation rejects missing, non-response, non-immediate, cross-case, and hash-drifted
  origins or predecessors, while semantic creation rejects repair context;
- parsed responses, explicit refusals, missing parse evidence, and parse evidence not bound
  to the semantic response cannot become repair origins;
- a repair transport failure followed by a repair retry preserves the original semantic
  origin, binds the new immediate predecessor, and behaves identically across crash/resume;
- live execution, crash/resume, projection validation, strict JSON round-trip, and review
  bridge reconstruction preserve the same predecessor binding;
- the one-repair limit and all runtime budgets remain unchanged;
- old diagnostic evidence is never read as input to the new run.

Focused calibration tests run first, followed by the repository's release checks appropriate
to the touched surface: full tests, Ruff, format check, dependency check, tracked-artifact
hygiene, and an independent specification/code-quality review. No success claim or commit of
implementation is made without fresh verification evidence.

## 7. Acceptance boundary

This subproject is complete only when the revised contract is committed, independently
reviewed, re-materialized, exactly approved, uploaded, and a fresh all-816 cloud run reaches
a valid terminal state under the unchanged calibration gates. Passing local tests alone does
not complete Phase 0A-1, and a structurally complete cloud projection with failed measurement
validity cannot be promoted.
