---
status: proposed fast-track implementation plan; preliminary/diagnostic only
authority: Phase 0B N=20 execution plan; subordinate to the frozen specification chain and evidence chain
date: 2026-09-20
---

# Paper 1 Phase 0B N=20 Real-Qwen Fast Track

> **Execution boundary:** this plan is for a first **preliminary/diagnostic** real-model dynamics run. It does not freeze unresolved research parameters, authorize the formal N=1000/T=50 matrix, or turn Phase 4B mock fixtures into Paper 1 results.

## Outcome and fastest defensible scope

Build the smallest auditable bridge from the verified Phase 4B serial event engine to the already smoke-tested local Qwen3-8B/vLLM service, then run one matched seed across all 12 cells at `N=20, T=2`.

- Exact planned inventory: `20 agents × 2 sweeps × 12 cells = 480` logical activation events and normally 480 model requests.
- Hard diagnostic ceiling: at most one explicitly authorized same-event retry, so no more than 960 transports. A retry never advances state, feed cursor, event ordinal, or model-seed identity.
- Matrix: all `identity 2 × continuity 2 × exposure 3` cells. Do not save time by dropping the shuffled comparator or collapsing persona cells.
- Inputs: explicitly approved diagnostic candidate artifacts only. Preserve their `mock_only/not_frozen` provenance as synthetic calibration inputs; do not relabel them as frozen population, network, persona, or protocol artifacts.
- Model execution: real pinned Qwen3-8B, BF16, non-thinking, vLLM loopback. Bind the actual Phase 0A environment lock, model/tokenizer revision, chat-template hash, service identity, Git SHA, and request parameters in a new diagnostic authorization record.
- Interpretation: descriptive feasibility and mechanism diagnostics only. One matched seed is not an inferential replicate and cannot support a p-value, confidence interval, primary-effect claim, or formal topic/parameter freeze.

`T=2` is deliberate. `T=1` is mostly an initialization/transport check; `T=2` permits within-agent history and event-updated public exposure to affect a later sweep while keeping the first reportable run small. If the 480-event run is healthy, extend with a **new immutable authorization** to `T=3` (720 events) rather than silently changing this run.

## Phase 0: Documentation and implementation discovery

### Allowed APIs and code paths verified

1. `StrictSerialLifecycleEngine.execute(...)` is the reusable provider-neutral transaction kernel. It accepts callbacks for prepare, invoke, finalize, commit, and optional reconciliation (`platform/src/agent_ex/engine.py:255-380`). Its current surrounding records still hard-code mock-only authorization and types, so the kernel is reusable but its boundary records need a diagnostic-real variant.
2. `MockEventPipeline.execute(...)` already assembles exposure, memory, persona, prompt, parser, event evidence, and atomic state commit (`platform/src/agent_ex/pipeline.py:187-301`). The preparation path builds the correct event-level inputs (`pipeline.py:303-522`) and the commit path mutates private/public state only after a successful parse (`pipeline.py:524-659`). Reuse this logic; do not create a second dynamics loop.
3. `RunStorage` SQLite v6, compact checkpoint v5, and close/open recovery are release-verified. The Phase 4B handoff documents zero-resend recovery and 50,000-event mock capacity (`logs/2026-09-04-phase4b-handoff.md`).
4. `build_mock_matched_seed_matrix(...)` validates the 12-cell matched-seed artifact invariants (`platform/src/agent_ex/mock_matrix.py:501-761`). The convenient N=20 artifact builder currently lives only in `platform/tests/helpers/mock_matrix.py:1099-1180`; production code must not import from `tests`.
5. `VllmProbeAdapter` already implements exact loopback/no-redirect transport, request-ID propagation, response-body/header/status preservation, overall/connect/read timeouts, response-size bounds, and deterministic request fields (`platform/src/agent_ex/calibration/vllm_adapter.py:197-471`). Copy its verified transport pattern into a provider-neutral event adapter or extract a shared transport primitive; do not wrap `ProbeRequest` around an event request.
6. Cloud dispatch intent and resolution logic already prevents blind replay after an indeterminate send (`platform/src/agent_ex/calibration/cloud_run.py:91-243`). Copy this append-before-send pattern for event attempts.
7. The service lifecycle script binds start/stop evidence to a manifest/environment-lock hash and exact port 8000 (`platform/scripts/phase0a1-service.sh:277-461`). Reuse it with the Phase 0B diagnostic manifest; do not launch a second unmanaged vLLM process. The currently running 797-item judge owns that service until its client reaches a verified terminal state and the service is explicitly handed over.
8. The permitted vLLM body fields and required non-thinking setting are listed in `docs/allowed-apis-v1.md`: `model`, `messages`, `temperature`, `top_p`, `max_tokens`, `seed`, and `chat_template_kwargs.enable_thinking=false`. No additional request field is allowed without a new documented smoke gate.
9. `build_mock_process_audit(...)` and `build_mock_comparable_run_projection(...)` already expose sweep-level private state, public stock, public flow, exposure diagnostics, and final comparable state (`platform/src/agent_ex/process_audit.py:504-746,896-1032`). These can seed a diagnostic projection, but the exported schema/name must state hybrid preliminary provenance rather than pretend to be a formal real-run analysis.

### Components that are not yet reusable as-is

- `AdapterRequest`, `AdapterResponse`, `MockAttemptPolicyBinding`, `MockAdapterExecutionBinding`, `AttemptAuthorization`, `PreparedAttempt`, `MockEventPipeline`, and `MockEventInvocation` are type- or schema-bound to mock execution (`adapters/base.py:27-29,120-420`; `execution_evidence.py:40-47,102-345`; `engine.py:72-195`; `mock_run.py:31-88`).
- `MockEventPipeline` requires a concrete `MockAdapter`, compares a scripted binding, and writes mock-only authorization (`pipeline.py:194-229,430-520`). A real adapter cannot be safely substituted by duck typing.
- State, feed, memory, prompt, parser, population, network, schedule, and topic artifacts remain `mock_only/not_frozen`. For this fast track they may be used only as transparently named **synthetic diagnostic inputs**. Generalizing every research artifact to formal-capable v2 is intentionally deferred; that is a separate Phase 0B-to-formal upgrade.
- There is no production N=20 real-run materializer, diagnostic run authorization, event vLLM adapter, cloud event CLI, bounded retry/resume controller, or preliminary metrics bundle.
- The draft formal protocol still contains `UNRESOLVED[...]` fields. The fast track must not call the formal protocol loader or replace unresolved values with coder defaults.

### Anti-pattern guards

- Never instantiate `MockAdapter` with real response bytes or synthesize a `script_hash` for Qwen.
- Never mark real provider execution as `mock_only=true`; instead record the split explicitly: synthetic diagnostic input artifacts plus real model execution.
- Never import builders from `platform/tests/helpers` into production.
- Never continue after an unresolved pre-dispatch intent, resend a successful event, change request parameters on retry outside an approved policy, or treat a failed attempt as a state update.
- Never use the Phase 0A probe runner as the dynamics runner. It operates on independent `ProbeCase` records, not network events.
- Never describe the N=20/T=2 output as a formal experiment, primary result, causal estimate, or seed-level uncertainty estimate.

## File map for the minimum implementation

### Create

- `platform/src/agent_ex/phase0b/__init__.py` — exact public diagnostic API.
- `platform/src/agent_ex/phase0b/contracts.py` — `DiagnosticRunAuthorization`, `DiagnosticAttemptPolicy`, `DiagnosticAdapterBinding`, and terminal run report; all require `calibration_only=true`, `formal_parameter_authority=false`, `research_parameter_status=not_frozen`.
- `platform/src/agent_ex/phase0b/vllm_event_adapter.py` — real event adapter using the verified loopback transport contract and durable pre-dispatch hook.
- `platform/src/agent_ex/phase0b/matrix.py` — production N=20 synthetic diagnostic artifact/matrix materializer copied from the tested helper patterns, with every candidate value explicit and hash-bound.
- `platform/src/agent_ex/phase0b/run.py` — thin 12-cell serial orchestrator, same-event retry/resume, checkpoints, and terminal verification.
- `platform/src/agent_ex/phase0b/report.py` — sanitized preliminary metrics bundle; raw prompt/response text stays outside Git.
- `platform/src/agent_ex/phase0b/cli.py` — `materialize`, `run`, `resume`, `verify`, and `report` commands with create-only outputs.
- `platform/tests/test_phase0b_contracts.py`
- `platform/tests/test_phase0b_vllm_event_adapter.py`
- `platform/tests/test_phase0b_matrix.py`
- `platform/tests/test_phase0b_run.py`
- `platform/tests/test_phase0b_report.py`
- `platform/scripts/phase0b-n20-run.sh` — cloud wrapper that verifies hashes, starts the existing service lifecycle, launches one client, and never auto-resumes ambiguity.

### Modify minimally

- `platform/src/agent_ex/adapters/base.py` — add provider-neutral v2 event request/response contracts without weakening or reinterpreting mock v1 records.
- `platform/src/agent_ex/engine.py` — add provider-neutral diagnostic prepared/authorization unions while leaving existing mock paths byte-for-byte replayable.
- `platform/src/agent_ex/execution_evidence.py` — add diagnostic policy/binding capability seals; retain mock v1/v2 deserialization unchanged.
- `platform/src/agent_ex/pipeline.py` — extract shared event preparation/finalization/commit behavior into a provider-neutral internal core, then keep `MockEventPipeline` as a compatibility wrapper and add a diagnostic-real wrapper. Do not duplicate the event semantics.
- `platform/src/agent_ex/storage.py` — implement the selected **方案 A**: extend SQLite v6 with diagnostic-v2 discriminated unions for request/response/policy/binding records while preserving every legacy mock row, schema projection, reopen path, and replay result byte-for-byte. Do not create a second store.
- `platform/src/agent_ex/process_audit.py` — add a diagnostic projection label that preserves the existing descriptive snapshots but cannot be mistaken for formal analysis.
- `platform/src/agent_ex/__init__.py` and exact API-surface tests — export only the intended Phase 0B types.
- `platform/pyproject.toml` — register the Phase 0B CLI only if the project uses console entry points; otherwise invoke `python -m agent_ex.phase0b.cli`.
- `platform/tests/test_storage.py`, `platform/tests/test_checkpoint.py`, and `platform/tests/test_pipeline.py` — add diagnostic-v2 tamper, close/open, checkpoint/reopen, mixed-schema rejection, and legacy replay regressions.

No task/progress/findings document is part of this implementation plan. A later execution session may update them under its own ownership.

## Phase 1: Freeze a diagnostic authorization, not formal parameters

### What to implement

Create a content-addressed `DiagnosticRunAuthorization` with exact fields:

- scope: `phase0b_preliminary_diagnostic_n20_t2`;
- matrix inventory: 12 canonical cell IDs, one matched seed, N=20, T=2, 480 expected events;
- provenance split: `input_artifact_mode=synthetic_phase4b_candidate`, `model_execution_mode=real_qwen_vllm`;
- hashes for topic/population/persona/network/shadow/mapping/attention/expression/activation/publish/schedule artifacts;
- exact B and K candidate values plus their stable research-QA IDs (`P1_MAX_NEIGHBORS`, `P1_MEMORY_WINDOW`), explicitly marked candidate/not frozen;
- actual model/tokenizer revision, chat-template hash, vLLM/package/image/environment lock, service start identity, source commit, dirty/diff evidence, endpoint, served model name;
- explicit generation fields, seed-pairing candidate rule, timeout/error/retry policy, max 960 transports, disk/token/wall-clock stop limits, checkpoint cadence, and archive URI;
- interpretation labels and forbidden claims.

The authorization may bind values already approved for the Phase 0A diagnostic packet (`temperature=0.7`, `top_p=0.8`, `max_tokens=128`) only after the owner approves their reuse for this Phase 0B diagnostic. That reuse remains non-formal. B=6 and K=3 are specification-named Phase 0 candidates, not defaults; they also require explicit diagnostic approval in this record.

### Verification checklist

- RED tests reject missing hashes, unknown cells, event count other than 480, `formal_parameter_authority=true`, formal status, unresolved strings, an unapproved candidate value, or an archive inside Git.
- Round-trip and record-hash tests pass.
- A formal protocol loader still rejects the unresolved draft exactly as before.

## Phase 2: Add an honest real-event adapter boundary

### What to implement

Introduce v2 event request/response records with neutral field names (`model_seed`, `adapter_binding_hash`) and execution metadata. Preserve v1 mock payload loaders. Implement `VllmEventAdapter` against those records, following `VllmProbeAdapter` for:

- exact `http://127.0.0.1:8000/v1/chat/completions` endpoint;
- no redirect following;
- exact allow-listed body fields and `enable_thinking=false`;
- `X-Request-Id` request and response binding;
- raw bytes, all response headers, HTTP status, usage, finish reason, timing, provider request ID, and response hash;
- one monotonic overall deadline plus bounded connect/read deadlines;
- size limit and typed timeout/busy/OOM/fatal/schema errors;
- create-only dispatch intent before any HTTP bytes are sent.

The adapter performs exactly one transport per `generate` call. Retry decisions remain in the run controller.

### Verification checklist

- Copy the fake-server cases from `tests/test_calibration_vllm_adapter.py:144-411`: success identity, timeout, invalid JSON, 429/Retry-After, 500/OOM, redirect rejection, model/request-ID mismatch, response-size limit, and append-only evidence.
- Add a crash after dispatch-intent and prove resume refuses automatic resend.
- Confirm request body has exactly the allowed keys and the event request ID, prompt hash, model seed, and generation settings are evidence-bound.

## Phase 3: Reuse the serial dynamics core without laundering mock records

### What to implement

Refactor `MockEventPipeline` into a shared internal event core plus two narrow wrappers:

- mock wrapper: unchanged behavior and existing schemas/tests;
- diagnostic-real wrapper: accepts only `DiagnosticRunAuthorization`, `DiagnosticAttemptPolicy`, `DiagnosticAdapterBinding`, and `VllmEventAdapter`.

The diagnostic wrapper reuses the existing exposure/memory/persona/prompt/parser/commit sequence. It must write explicit hybrid provenance beside every attempt: synthetic calibration input hashes plus real provider/runtime/model hashes. It may consume the current mock-only candidate artifacts but may not rewrite their metadata or expose them as formal artifacts.

Do not generalize network/population/state artifacts to formal-capable schemas in this fast track. That larger migration is unnecessary for a preliminary result and creates avoidable regression risk.

Use **storage方案 A**, not an independent Phase 0B store. SQLite v6 remains the single authoritative event/state store, and each polymorphic execution record gains an explicit schema discriminator selecting either the existing mock representation or the new diagnostic-v2 representation. This is preferable to方案 B because event ordering, transaction atomicity, cursor/state commit, checkpoint construction, and recovery invariants are already proven together in v6; a parallel store would duplicate precisely the highest-risk code and make cross-store crash atomicity ambiguous. The migration is additive: existing mock table payloads and hashes are not rewritten, existing rows deserialize through their historical schema, diagnostic rows require the new discriminator, and unknown or cross-wired variants fail closed.

### Verification checklist

- All pre-existing mock pipeline tests remain green.
- New fake-real adapter test proves one successful response commits exactly one event and advances one cursor.
- Timeout, malformed response, or provider error writes an attempt/failure prefix but leaves private state, public post, feed cursor, and next event ordinal unchanged.
- Post-invocation crash recovery performs zero resend when durable transport evidence exists.
- Provider/model/environment identity drift fails before dispatch.
- Open a legacy mock database/checkpoint created before this change and prove its typed records, projection hash, next ordinal, and comparable replay remain byte-for-byte unchanged.
- Close/reopen a diagnostic-v2 database at pending, in-progress, post-invocation, terminal-success, SQLite-commit-before-context, and checkpoint-write boundaries; verify the exact remaining provider-call counts and final projection equality.
- Tamper the schema discriminator, diagnostic payload, binding hash, dispatch intent, or checkpoint reference and prove reopen fails before state mutation or network dispatch.

## Phase 4: Promote only the N=20 diagnostic materializer

### What to implement

Copy the deterministic artifact-building patterns from `platform/tests/helpers/mock_matrix.py:813-1180` into `phase0b/matrix.py`, removing test-only conveniences and making every input explicit. Build all 12 cells from one shared matched seed and verify:

- identical population, initial state/reason, activation, publish, and applicable RNG namespaces across cells;
- only approved identity/continuity prompt blocks differ across persona cells;
- E0 has no social graph, E1 uses frozen degree-matched shadow, E2 uses frozen WS;
- schedules contain exactly 40 contiguous event ordinals per cell;
- every cell has a unique run ID/database but the expected cross-cell shared hashes match;
- no artifact is selected after viewing an outcome.

### Verification checklist

- Exact inventory: 12 cells, 20 agents each, 40 events each, 480 total.
- Re-run the existing matrix attack patterns from `test_mock_matrix_integration.py:653-753` against the diagnostic materializer.
- Assert the production module never imports `tests` or fixture helper modules.

## Phase 5: Add bounded run/resume and terminal verification

### What to implement

Implement a thin cell-by-cell runner over the diagnostic event pipeline:

1. verify authorization, environment lock, service evidence, archive absence, free disk, and exact matrix before first dispatch;
2. run one cell at a time, strictly serial within each run;
3. checkpoint after each completed sweep and cell;
4. permit one same-event retry only for the approved error classes and only with a durable retry authorization that preserves event ID, prompt/input hashes, and model seed;
5. stop on unresolved dispatch, identity drift, exhausted retry, disk/token/time ceiling, or evidence mismatch;
6. resume only from the first not-successfully-committed event and never merge archives;
7. terminal verify exactly 12 complete databases, 480 successful committed events, no unresolved dispatch intents, and matching schedule/artifact/authorization hashes.

The fastest initial launch should not add concurrency inside one social event chain. Cross-cell concurrency is also deferred for the first run because one 32 GB GPU serving Qwen3-8B can batch requests internally, but independent cell clients complicate recovery and are not required to obtain the first data.

### Verification checklist

- N=2/T=2 fake-vLLM 12-cell integration completes exactly 48 events.
- Six recovery points retain the Phase 4B zero-resend properties.
- Storage-focused tests cover diagnostic-v2 create/reopen/replay, checkpoint recovery, discriminator/payload/hash tampering, and mixed mock/diagnostic record rejection.
- Legacy mock storage/recovery fixtures reopen through their original schemas and reproduce their pre-change payload bytes and projection hashes exactly.
- A duplicate launch, changed manifest, changed endpoint/model, or partial archive fails closed.
- `verify` reads durable evidence only and does not contact the model.

## Phase 6: Produce a sanitized preliminary report bundle

### Allowed report outputs

Produce tables/figures from committed states only:

- completion, parse failure, provider failure, refusal proxy, retry, and unresolved-dispatch counts;
- request latency, input/output tokens, requests/minute, wall clock, SQLite/checkpoint size, and GPU/service identity;
- per-cell and per-sweep private stance distribution, mean, variance, mean absolute change, and fraction changing stance;
- public stock and public flow stance distributions and publication counts;
- exposure message counts, unique sources, expiry, and empty-feed incidence;
- expression gap as a descriptive private-versus-public difference only if its exact diagnostic formula is stated in the bundle; do not promote it to the unresolved formal outcome;
- descriptive matched-seed `E2-E1` and `E2-E0` differences averaged over the four persona cells, clearly labeled single-seed exploratory contrasts;
- identity/continuity cell differences and trajectory plots labeled descriptive.

### Forbidden outputs

- no p-values, inferential confidence intervals, power claims, formal primary endpoint, formal shape class, or claim that N=20 agents are independent replicates;
- no raw prompt, raw model response, identity card, or unrestricted reason text in Git/report figures;
- no topic or parameter selection based on these network outcomes.

### Verification checklist

- Report builder refuses incomplete or mixed-authorization matrices.
- Every number is recomputed from durable committed evidence and binds a source projection hash.
- Sanitized report contains no raw-response/prompt fields and is safe to commit; raw archives remain on AutoDL/external storage.

## Phase 7: Cloud launch sequence

Run only after the owner approves the final source bundle hash and the exact diagnostic authorization hash.

Local implementation and tests may proceed while the 797-item blind judge runs. Cloud execution may not: the two-event Phase 0B preflight and the 480-event run must wait until the judge client reaches a verified terminal state, its durable projection and dispatch journal are checked, and service ownership is explicitly handed from the judge manifest to the Phase 0B manifest. Never stop or restart a service still owned by the active judge, never bind Phase 0B evidence to the judge's service identity, and never launch a second process on port 8000. If the judge exits ambiguously or retains an unresolved dispatch, Phase 0B cloud launch remains blocked while local work continues.

1. Apply the verified source bundle to a clean cloud checkout and rerun the focused Linux suite.
2. Materialize the N=20/T=2 authorization/matrix in a fresh absent archive root.
3. After verified judge/service handoff, reuse the existing pinned Qwen/vLLM model files and create a fresh service start identity bound to the new diagnostic manifest.
4. Run a two-event preflight in a separate archive. Verify parsing, raw evidence, stop/resume, and provider identity; do not splice it into the 480-event run.
5. Launch the 480-event run once. Monitor every 20 minutes or on process exit; never restart while the client is healthy.
6. Verify the terminal matrix, build the sanitized report, record hashes and archive location, then stop the service if no next job is queued.

### Expected wall clock

- Implementation plus focused tests: approximately 4-8 engineering hours if no core storage-schema defect appears; 8-12 hours if provider-neutral v2 replay requires broader migration.
- Two-event cloud preflight: 5-15 minutes including service verification.
- 480-event real run: approximately 30-90 minutes at 2-8 seconds per request including serial evidence overhead; hard-retry worst case is up to roughly 2 hours.
- Terminal verification and preliminary report: 20-45 minutes.

These are planning ranges, not promises. After the first 20 successful events, compute a blind operational ETA from latency and evidence-write time only; do not inspect condition outcomes to decide whether to continue.

## Phase 8: Upgrade path after the first reportable diagnostic

1. If N=20/T=2 is mechanically healthy, authorize N=20/T=3 or T=5 to inspect short trajectory stability without changing the completed archive.
2. Freeze the outstanding Phase 0B runtime candidates and exact retry/seed-pairing rules from operational evidence, without using effect directions.
3. Generalize mock-only research artifacts into calibration/formal-capable versioned schemas, with legacy replay retained.
4. Run N=50 then N=100 calibration with multiple matched seeds as budget permits; estimate failure, throughput, storage, and seed-level variance.
5. Freeze primary outcome/formula, shape thresholds, formal seeds, archive policy, and scale gates before any N=200/500/1000 limited-scale or N=1000/T=50 formal run.

## Fresh discovery verification performed for this plan

The following read-only/lightweight evidence was obtained on 2026-09-20 in the Phase 0 worktree:

- runtime signature inspection successfully imported and printed `StrictSerialLifecycleEngine.execute`, `MockEventPipeline.execute`, `ModelAdapter.generate`, `AdapterRequest.create`, `VllmProbeAdapter.generate`, and `build_mock_matched_seed_matrix`;
- focused tests passed: vLLM success/evidence identity, the parameterized N=20 recovery equivalence set, and exact mock-run public API (`8 passed in 48.89s`);
- the audit confirms the blocking gap is the honest real-event adapter/schema/run layer, not the serial engine, SQLite recovery, prompt construction, or vLLM transport behavior.

## Go/no-go decisions still requiring explicit owner approval

Before the first 480-event launch, approve one immutable diagnostic authorization containing:

1. reuse of the Phase 0A candidate generation settings (`temperature=0.7`, `top_p=0.8`, `max_tokens=128`) for this diagnostic only;
2. B=6 and K=3 as diagnostic candidates only;
3. one exact matched seed and the diagnostic model-seed pairing rule;
4. timeout/error classes and at most one same-event retry;
5. N=20, T=2, all 12 cells, 480 expected events and 960-transport hard ceiling;
6. the exact source bundle, environment lock, service identity, archive URI, and authorization record hashes.

No other research decision needs to be silently filled to obtain the first preliminary dynamics data.
