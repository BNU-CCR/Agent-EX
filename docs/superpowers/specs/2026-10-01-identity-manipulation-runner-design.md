# Independent identity-manipulation runner design

Status: independent written review Approved; human approved 2026-10-01.
Human approval authorizes local implementation, not upload or cloud execution.
Authority: operational extension of the approved identity-network 2×3 design.
Research choices remain in `docs/research-qa.md`; no statistical/sample defaults here.

## Purpose and alternatives

Deliver a standalone `run / resume / verify / report` entry for approved identity-check
requests. All input variants are independent: no agent state, feed cursor or public
stock is changed between paired trials. Preserve the six-cell study runner and legacy.

Recommended: a dedicated SQLite check store, reusing the existing loopback vLLM
transport and typed parser contracts. It can durably retain exact requests, dispatch
intent, responses and parse results without inventing study event semantics.

Rejected alternatives: adapting six-cell StudyRunStorage would fabricate network
events/state advancement; adapting the 797 judge store would reuse incompatible
judge-item/coding semantics. Reuse transport/validation utilities, not those run IDs,
storage schemas, authorizations or datasets.

## Input and approval boundary

The runner consumes a fully source-bound approved manipulation inventory. Current
v1 four-pair pack is only a contract/test path; it cannot authorize the proposed
240-request run. The two-repeat version must first be designed/confirmed and bind
case, replicate, focal/source label, exact messages, sampling seed and fixed order.
Do not duplicate case IDs to impersonate additional independent cases.

Before sending, replay the exact candidate/source pack/preregistration/service bridge
and scoped dispatch receipt, verify actual approved bundle and clean runtime checkout,
and collect current service identity/health using the existing preflight. Never create
human receipts automatically. The service-start approval does not grant dispatch.

The real CLI starts from a fresh interpreter in the approved checkout and checks the
origin of its loaded `agent_ex` Python modules against that checkout. Reject foreign,
untracked or ignored package source; compare source-file hashes to approved tracked
content. This is an execution-origin check, not proof of arbitrary installed third-party
packages: those remain bound by the environment inspection/profile. Do not claim
protection against a malicious kernel, mutated process memory or hostile directories.

`run` requires the exact authorized archive root and a fresh absent run directory;
`resume` requires the same immutable full source/approval/plan, an existing valid store
and no ambiguous dispatch. Do not overwrite, merge or reset an old run. Preserve all
raw response evidence outside Git and never print it to conversations or summary CLI.

## Request materialization and parser

Reconstruct all trials in frozen order once. Derive a study-specific check request/event
identity from authorization hash and trial identity; use attempt index 1. Reuse
Phase0BVllmEventRequest only as a transport contract, not a Phase0B study authorization.
Exact messages, prompt hash, model seed, generation parameters and adapter binding
must match the approved trial. Bind wire model name and `enable_thinking=false`.

Use the candidate's explicit parser limits, topic/ordered stance mapping, adapter model
and operational timeout values. No inferred seed, generation value or parser threshold.
Even if the shared attempt policy supports retries, this runner stops on failure and
does not automatically exercise that retry capability. A separate future retry gate
would be needed; it is out of this implementation.

Transport evidence must match request ID/hash, attempt identity, exact wire bytes and
response hash before any parse is accepted. Parse the actual saved response using
the shared typed non-thinking response/parser boundary; retain stance, reason and
confidence. A valid parse does not itself label sycophancy or establish a signal.
The manipulation checker never calls the study state-commit pipeline.

## Dedicated store and single-writer boundary

One fresh SQLite database per check run; never change legacy or StudyRunStorage tables.
Immutable metadata contains the exact full source plan, its hash, authorization and
receipt identities, ordered trial/request inventory, parser/adapter/timeout identities.
Retain full requests and transport/parse evidence in access-controlled files; summaries
expose hashes/counts/status only. Cross-check each row against the immutable inventory.

Use SQLite transactional writes with FULL durability and the existing directory-fsync
pattern for new archive creation. A Linux kernel-backed exclusive, nonblocking run
lock spans the session, including HTTP; it is released by process death. SQLite commits
remain short and occur BEFORE HTTP. Never hold an uncommitted intent transaction
across transport. Production CLI requires Linux locking, with no silent platform fallback.
Local tests use explicit lock/HTTP boundaries and must not be reported as Linux acceptance.

Store phases:

1. READY: immutable request exists, no dispatch intent. May send once after current gates.
2. INTENT: exact request/body hash committed before network. No response yet is ambiguous;
   stop, retain evidence, do not resend on resume.
3. RESPONSE_STORED: full typed response and transport committed before parsing. A crash
   here permits LOCAL parse/terminalization using saved evidence, without another HTTP.
4. VALID / INVALID: terminal parse/provider outcome committed, no state/cursor updates.
   INVALID stops the run; do not advance to the remaining trials or shrink denominator.

Only one unresolved prefix is allowed; future-row intent/response or missing historical
intent is corruption. A saved response is not a license to redo transport. Transactional
compare-and-set transitions prevent duplicate intent/response/terminal records.

## Loop, resume and verification

Cold validate complete source graph/inventory and durable prefix at start. Materialize
requests once, cache immutable reconstruction, and maintain an incremental verified
prefix. Do not scan the full archive or rehash the entire population for every request.
Unexpected SQLite data-version or immutable file changes invalidate the cache and
force cold replay before another send. Check service process/listener identity directly
before each dispatch; use bounded service health at entry/checkpoint, not full source
replay per event. Benchmark reconstruction, storage, pre-send check and inference
separately; do not change protocol parameters merely to achieve speed.

Resume first resolves already-saved responses locally. Any INTENT without a saved
response, terminal INVALID, missing intent history or differing plan/receipt stops
before network. No automatic retry/restart/Stage-B transition. Complete runs are
idempotent: resume produces the same summary without additional requests.

`verify` performs independent read-only cold replay of inventory, every request,
intent/transport/response/parse/terminal and exact prefix. Only exact expected inventory
and all VALID records may yield execution-complete. `report` emits safe descriptive
counts, status, evidence hashes and timings; no statistical pass/no-signal decision yet.
All output remains preliminary/not_frozen/formal_parameter_authority=false.

## Research decisions outside this operational design

`UNRESOLVED[SIS_MC_BOOTSTRAP]`, `UNRESOLVED[SIS_MC_SEED_POLICY]`,
`UNRESOLVED[SIS_MC_BENCHMARK_CONTENT]`, `UNRESOLVED[SIS_MC_FAILURE_POLICY]`
must be resolved for the actual 240-request candidate. Existing user proposal is retained:
30 cases, six balanced strata, four cells and two generations, toward-source-shift and
three signal criteria. This spec neither picks bootstrap settings nor silently approves
case averaging/seed pairing/Stage-B sample reuse. See the 240-candidate document.

Full valid execution is distinct from a statistical no-signal result. No INVALID run
may trigger Stage-B. Stage-B dispatch remains disabled until the actual complete Stage-A
report, frozen criteria and explicit transition approval are independently verified.
Implementation of that transition and statistical evaluator is a later approved task.

## Acceptance and delivery

Implement and verify, in order:

1. Deterministic request inventory bound to approved source/auth; reject rehashed message,
   order, seed, generation/model/body drift. Keep v1 as fixture only, not a cloud candidate.
2. Dedicated store cold replay, exclusive writer and atomic intent/response/terminal writes.
3. Runner with fake HTTP and crash injection at before-send/after-send/after-response/
   after-parse boundaries; reopen never resends saved or ambiguous requests.
4. Strict independent CLI and execution-origin check, safe verify/report; test foreign
   Python source, wrong plan/receipt/root, occupied writer lock and corrupt late prefix.
5. A complete synthetic inventory roundtrip, bounded continuation, provider/parse failure,
   all-history replay and read-only summaries. Test reconstruction counts to detect
   per-request full-pack scans. Run scoped pytest/Ruff/diff only, not full-repo suites.
6. Only after real 240 input/analysis design and source choices are confirmed, produce
   exact source bundle, candidate/receipt targets and operator commands. Ask for cloud
   startup then perform Linux lock/origin/service acceptance and actual Stage-A inference.

No upload, service start/stop or experiment execution is authorized by this design.
