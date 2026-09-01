# Paper 1 Phase 4B-8C-3 Evidence Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and replay the complete mock event evidence chain while preserving strict serial commit, exact retry identity, and zero-resend crash recovery.

**Architecture:** Add immutable execution-evidence contracts, upgrade `RunStorage` to v6 with normalized evidence tables, and extend the existing lifecycle kernel with atomic prepare/invocation/finalization operations. A thin `MockEventPipeline` composes the existing feed, memory, prompt, mock adapter, parser, and state factories; it does not create a second event loop.

**Tech Stack:** Python 3.11+, frozen dataclasses, SQLite, pytest, Ruff, existing Agent-EX canonical JSON/hash and capability seals.

---

## File structure

- Create `platform/src/agent_ex/execution_evidence.py`: immutable policy, adapter attestation, event-input, invocation/finalization, parser-N/A, and evidence-reference contracts.
- Create `platform/src/agent_ex/pipeline.py`: thin mock event preparation/finalization coordinator and public pipeline-outcome wrapper.
- Create `platform/tests/test_execution_evidence.py`: contract, hashing, deep-freeze, and formal-fail-closed tests.
- Create `platform/tests/test_pipeline.py`: end-to-end, retry, recovery, privacy, and tamper tests.
- Modify `platform/src/agent_ex/adapters/base.py`: internal persisted-response resealing boundary.
- Modify `platform/src/agent_ex/adapters/mock.py`: typed pre-invocation attestation and zero-call persisted-response verification.
- Modify `platform/src/agent_ex/storage.py`: storage v6 schema, atomic evidence APIs, readers, prefix integrity, and checkpoint evidence projection.
- Modify `platform/src/agent_ex/engine.py`: consume typed prepared/finalized evidence and call atomic storage operations.
- Modify `platform/src/agent_ex/checkpoint.py`: include v6 evidence roots in recovery evidence.
- Modify `platform/src/agent_ex/__init__.py`: export only approved public contracts.
- Modify `platform/tests/test_domain.py`, `test_mock_adapter.py`, `test_storage.py`, `test_engine.py`, and `test_checkpoint.py`: focused regression coverage.
- Create `logs/2026-09-01-phase4b8c3-evidence-pipeline.md`: final evidence and remaining 4B-9 gates.

### Task 1: Immutable execution-evidence contracts

**Files:**
- Create: `platform/src/agent_ex/execution_evidence.py`
- Create: `platform/tests/test_execution_evidence.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [ ] **Step 1: Write failing construction, tamper, and deep-freeze tests**

```python
def test_mock_policy_is_explicit_deeply_frozen_and_not_formal() -> None:
    allowed = {"request_parameters.temperature": True}
    policy = MockAttemptPolicyBinding.create(
        research_qa_ids=("P1_MODEL_SEED_PAIRING", "P1_TIMEOUT_RETRY"),
        allowed_difference_fields=allowed,
        mock_only=True,
        formal_eligible=False,
    )
    allowed["request_parameters.top_p"] = True
    assert tuple(policy.allowed_difference_fields) == ("request_parameters.temperature",)
    with pytest.raises(ValueError, match="formal"):
        policy.require_formal_eligible()


def test_timeout_parse_na_binds_response_and_parser_limits() -> None:
    evidence = ParseNotApplicableEvidence.create(
        attempt_id="attempt-1",
        request_id="request-1",
        request_hash="a" * 64,
        response_id="response-1",
        response_hash="b" * 64,
        timeout_error={"code": "timeout", "message": "expired"},
        parser_limits_hash="c" * 64,
    )
    assert evidence.reason_code == "adapter_timeout_no_response"
    assert evidence.record_hash == canonical_payload_hash(evidence.content_payload())
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_execution_evidence.py`

Expected: collection fails because `execution_evidence` and its contracts do not exist.

- [ ] **Step 3: Implement the minimal contracts**

```python
@dataclass(frozen=True, slots=True)
class MockAttemptPolicyBinding:
    research_qa_ids: tuple[str, str]
    allowed_difference_fields: tuple[str, ...]
    mock_only: bool
    formal_eligible: bool
    record_hash: str

    @classmethod
    def create(cls, *, research_qa_ids, allowed_difference_fields,
               mock_only: bool, formal_eligible: bool):
        fields = tuple(sorted(allowed_difference_fields))
        payload = {
            "schema_version": "paper1.mock-attempt-policy.v1",
            "research_qa_ids": tuple(research_qa_ids),
            "allowed_difference_fields": fields,
            "mock_only": mock_only,
            "formal_eligible": formal_eligible,
        }
        return cls(tuple(research_qa_ids), fields, mock_only, formal_eligible,
                   canonical_payload_hash(payload))


@dataclass(frozen=True, slots=True)
class EventEvidenceReferences:
    event_input_hash: str | None
    request_hash: str | None
    invocation_hash: str | None
    parse_hash: str | None
    terminal_attempt_id: str | None
    committed_event_id: str | None


@dataclass(frozen=True, slots=True)
class FinalizedAttemptEvidence:
    terminal_attempt: GenerationAttempt
    parse_or_not_applicable: ParseEvidence | ParseNotApplicableEvidence
    terminal_failure: TerminalFailureEvidence | None
```

Also implement canonical `to_payload`/`from_payload` and strict validation for
`MockAdapterExecutionBinding`, `EventInputEvidence`, `PersistedInvocationEvidence`,
`ParseNotApplicableEvidence`, `FinalizedAttemptEvidence`, and
`EventEvidenceReferences`. `EventInputEvidence` owns the typed exposure selection,
exposure record, memory view, prompt view, parser limits, state-context hash, and frozen
publish flag. Do not define `MockEventPipelineOutcome` here; Task 7 defines it beside
`MockEventPipeline` to prevent `execution_evidence -> engine -> execution_evidence`
circular imports.
Reuse `_freeze`, `_require_payload_hash`, `_require_sha256`, and `_require_json_transport`;
do not create alternate hashing rules.

- [ ] **Step 4: Run focused and public-export tests**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_execution_evidence.py tests\test_domain.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/execution_evidence.py platform/src/agent_ex/__init__.py platform/tests/test_execution_evidence.py platform/tests/test_domain.py
git commit -m "feat(platform): add Phase 4B execution evidence contracts"
```

### Task 2: Pre-invocation mock attestation and persisted-response capability

**Files:**
- Modify: `platform/src/agent_ex/adapters/base.py`
- Modify: `platform/src/agent_ex/adapters/mock.py`
- Modify: `platform/tests/test_mock_adapter.py`

- [ ] **Step 1: Write failing zero-call and independent-tamper tests**

```python
def test_persisted_response_rehydrates_without_generate(request, adapter, monkeypatch):
    binding = adapter.execution_binding()
    response = adapter.generate(request)
    payload = response.to_payload()
    monkeypatch.setattr(adapter, "generate", lambda _: pytest.fail("resent"))
    restored = verify_persisted_mock_response(
        request=request, response_payload=payload, binding=binding
    )
    assert _has_trusted_response_seal(restored)


@pytest.mark.parametrize("target", ["response", "binding"])
def test_persisted_response_rejects_independent_script_tamper(target, request, adapter):
    # Recompute the changed object's local hash; cross-binding verification must still fail.
    with pytest.raises(ValueError, match="binding|script"):
        verify_changed_pair(target, request, adapter)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_mock_adapter.py -k "persisted or binding"`

Expected: FAIL because attestation and verification APIs do not exist.

- [ ] **Step 3: Implement the internal capability boundary**

```python
# adapters/base.py -- private; callers cannot bypass mock attestation verification.
def _reseal_verified_persisted_response(response: AdapterResponse) -> AdapterResponse:
    return replace(response, _factory_seal=_issue_response_seal(response.record_hash))


# adapters/mock.py
def verify_persisted_mock_response(*, request: AdapterRequest,
                                   response_payload: Mapping[str, object],
                                   binding: MockAdapterExecutionBinding) -> AdapterResponse:
    response = AdapterResponse.from_payload(response_payload)
    if response.request_id != request.request_id or response.request_hash != request.record_hash:
        raise ValueError("persisted response does not bind request")
    if response.runtime_identity_hash != binding.runtime_identity_hash:
        raise ValueError("persisted response runtime binding drifted")
    if response.model_identity_hash != binding.model_identity_hash:
        raise ValueError("persisted response model binding drifted")
    if response.script_hash != binding.script_hash:
        raise ValueError("persisted response script binding drifted")
    return _reseal_verified_persisted_response(response)
```

`MockAdapter.execution_binding()` must expose a typed immutable value derived before
generation; it must not expose `_script_hash` directly.

- [ ] **Step 4: Run adapter tests**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_mock_adapter.py`

Expected: PASS, including zero `generate()` calls after reopen simulation.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/adapters/base.py platform/src/agent_ex/adapters/mock.py platform/tests/test_mock_adapter.py
git commit -m "feat(platform): verify persisted mock responses"
```

### Task 3: SQLite v6 schema and byte-identical v5 rejection

**Files:**
- Modify: `platform/src/agent_ex/storage.py`
- Modify: `platform/tests/test_storage.py`

- [ ] **Step 1: Write failing schema and v5 rejection tests**

```python
def test_new_store_has_v6_evidence_tables(tmp_path):
    store, _ = create_store(tmp_path / "v6.sqlite3")
    assert store.schema_version == "paper1.run-storage.v6"
    assert set(store._table_names()) >= {
        "event_input_evidence", "attempt_policy_evidence",
        "adapter_execution_bindings", "adapter_requests",
        "invocation_evidence", "parse_evidence",
    }


def test_v5_rejection_is_byte_identical(tmp_path):
    path = make_v5_store(tmp_path / "v5.sqlite3")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="version"):
        RunStorage.open(path, expected_binding=binding_for(path))
    assert path.read_bytes() == before
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_storage.py -k "v6_evidence_tables or v5_rejection"`

Expected: FAIL with v5 schema/table expectations.

- [ ] **Step 3: Add v6 tables and constraints**

```sql
CREATE TABLE event_input_evidence (
  event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE attempt_policy_evidence (
  event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, record_hash TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES event_input_evidence(event_id)
);
CREATE TABLE adapter_execution_bindings (
  binding_id TEXT PRIMARY KEY, payload TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE adapter_requests (
  attempt_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, adapter_binding_hash TEXT NOT NULL,
  parser_limits_hash TEXT NOT NULL, policy_hash TEXT NOT NULL,
  payload TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE invocation_evidence (
  attempt_id TEXT PRIMARY KEY, response_payload TEXT NOT NULL,
  execution_payload TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE parse_evidence (
  attempt_id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('parsed','not_applicable')),
  payload TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE
);
```

Set `_STORAGE_SCHEMA = "paper1.run-storage.v6"` and `_SQLITE_USER_VERSION = 6`.
Perform the version read before any write PRAGMA/transaction in `open()`.

- [ ] **Step 4: Run creation/open/storage regressions**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_storage.py -k "create or open or version or evidence_tables"`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/storage.py platform/tests/test_storage.py
git commit -m "feat(platform): add run storage v6 evidence schema"
```

### Task 4: Atomic evidence writes and readers

**Files:**
- Modify: `platform/src/agent_ex/storage.py`
- Modify: `platform/tests/test_storage.py`

- [ ] **Step 1: Write failing atomicity/idempotency tests**

```python
def test_prepare_writes_input_policy_binding_request_and_pending_atomically(store, prepared):
    store.record_prepared_attempt(prepared)
    assert store.event_input_evidence(prepared.authorization.event_id) == prepared.event_input
    assert store.adapter_request(prepared.request.attempt_id) == prepared.request
    assert store.current_event_journal().latest_transition.status is EventStatus.PENDING


def test_conflicting_prepare_rolls_back_every_row(store, prepared):
    with injected_sql_failure("adapter_requests"):
        with pytest.raises(sqlite3.DatabaseError):
            store.record_prepared_attempt(prepared)
    assert store.evidence_references(prepared.authorization.event_id).request_hash is None
    assert store.current_event_journal().latest_transition is None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_storage.py -k "prepared_attempt or invocation_evidence or finalized_attempt"`

Expected: FAIL because atomic v6 APIs do not exist.

- [ ] **Step 3: Implement atomic APIs using existing write guards**

```python
def record_prepared_attempt(self, prepared: PreparedAttempt) -> None:
    self._require_write_lease()
    with self._write_transaction() as connection:
        self._insert_or_exact_match_event_input(connection, prepared.event_input)
        self._insert_or_exact_match_policy(connection, prepared.policy)
        self._insert_or_exact_match_binding(connection, prepared.adapter_binding)
        self._insert_or_exact_match_request(connection, prepared)
        self._append_attempt_in_transaction(connection, prepared.pending_attempt)

def record_invocation_evidence(self, attempt_id, response, execution) -> None:
    self._require_write_lease()
    with self._write_transaction() as connection:
        journal = self._current_event_journal_in_transaction(connection)
        if (journal.latest_transition is None
                or journal.latest_transition.attempt_id != attempt_id
                or journal.latest_transition.status is not EventStatus.IN_PROGRESS):
            raise ValueError("invocation evidence requires the current IN_PROGRESS attempt")
        payload = invocation_payload(response=response, execution=execution)
        self._insert_or_exact_match_payload(
            connection, table="invocation_evidence", key_name="attempt_id",
            key=attempt_id, payload=payload,
        )

def record_finalized_attempt(self, finalized: FinalizedAttemptEvidence) -> None:
    self._require_write_lease()
    with self._write_transaction() as connection:
        self._validate_finalized_against_invocation(connection, finalized)
        self._insert_or_exact_match_payload(
            connection, table="parse_evidence", key_name="attempt_id",
            key=finalized.terminal_attempt.attempt_id,
            payload=finalized.parse_or_not_applicable.to_payload(),
        )
        self._append_attempt_in_transaction(connection, finalized.terminal_attempt)
        if finalized.terminal_attempt.status is EventStatus.FAILED:
            self._insert_terminal_failure_in_transaction(
                connection, finalized.terminal_failure
            )
```

Factor existing `append_attempt()` SQL into `_append_attempt_in_transaction()`; do not
nest SQLite transactions or weaken file/lease identity checks. Add typed readers for
every row and `evidence_references(event_id)`.

- [ ] **Step 4: Run storage and lifecycle regressions**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_storage.py tests\test_engine.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/storage.py platform/tests/test_storage.py
git commit -m "feat(platform): persist event evidence atomically"
```

### Task 5: Status-conditioned integrity and checkpoint roots

**Files:**
- Modify: `platform/src/agent_ex/storage.py`
- Modify: `platform/src/agent_ex/checkpoint.py`
- Modify: `platform/tests/test_storage.py`
- Modify: `platform/tests/test_checkpoint.py`

- [ ] **Step 1: Write failing prefix-matrix and checkpoint tamper tests**

```python
@pytest.mark.parametrize("prefix", VALID_V6_PREFIXES)
def test_integrity_accepts_every_valid_durable_prefix(tmp_path, prefix):
    store = build_store_at_prefix(tmp_path, prefix)
    store.verify_integrity()

@pytest.mark.parametrize("mutation", ["delete", "orphan", "extra", "wrong_hash"])
def test_integrity_rejects_invalid_evidence_cover(tmp_path, mutation):
    store = build_tampered_v6_store(tmp_path, mutation)
    with pytest.raises(ValueError, match="evidence|cover|hash"):
        store.verify_integrity()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_storage.py tests\test_checkpoint.py -k "prefix or evidence_cover or v6_evidence"`

Expected: FAIL because v6 evidence is not in integrity/checkpoint projections.

- [ ] **Step 3: Implement the exact-cover state machine**

```python
def _verify_v6_evidence_prefix(self, journal: EventJournalState) -> None:
    history = self._load_attempt_evidence_history(journal.event_id)
    _verify_closed_prior_attempts(history.prior_attempts)
    _verify_current_prefix(journal.resume_state, history.current_attempt)
```

Cover `new_attempt`, complete run, failed-awaiting-authorization,
authorization-landed, retry PENDING/IN_PROGRESS, invocation-landed, terminal FAILED,
landed SUCCEEDED, and committed historical prefixes. Hash the ordered v6 evidence
roots into checkpoint recovery evidence; do not add per-event full-history replay.

- [ ] **Step 4: Run storage/checkpoint suites**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_storage.py tests\test_checkpoint.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/storage.py platform/src/agent_ex/checkpoint.py platform/tests/test_storage.py platform/tests/test_checkpoint.py
git commit -m "feat(platform): verify v6 evidence prefixes"
```

### Task 6: Lifecycle evidence hooks and zero-resend recovery

**Files:**
- Modify: `platform/src/agent_ex/engine.py`
- Modify: `platform/tests/test_engine.py`

- [ ] **Step 1: Write failing lifecycle recovery tests**

```python
def test_invocation_landed_recovery_does_not_invoke(store, prepared, persisted_result):
    store.seed_in_progress_with_invocation(prepared, persisted_result)
    calls = 0
    with StrictSerialLifecycleEngine(store) as engine:
        outcome = engine.execute(
            prepare=prepare_existing, invoke=lambda _: pytest.fail("resent"),
            finalize=finalize_persisted, build_commit=commit_for,
        )
    assert outcome.state == "committed"

def test_failed_finalization_persists_parse_terminal_and_failure_atomically(
    lifecycle_scenario,
):
    lifecycle_scenario.adapter.queue_raw_response("not-json")
    outcome = lifecycle_scenario.execute_once()
    attempt_id = outcome.attempt.attempt_id
    assert outcome.state == "failed"
    assert lifecycle_scenario.store.parse_evidence(attempt_id).parsed is None
    assert lifecycle_scenario.store.attempt(attempt_id).status is EventStatus.FAILED
    assert lifecycle_scenario.store.terminal_failure(attempt_id) is not None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_engine.py -k "invocation_landed or finalized_atomically"`

Expected: FAIL because the engine still appends attempt-only transitions.

- [ ] **Step 3: Replace attempt-only writes with typed storage operations**

```python
if journal.resume_state in {"new_attempt", "retry_same_event"}:
    self._storage.record_prepared_attempt(value)
    self._storage.append_attempt(value.in_progress_attempt)
    result = invoke(value.request)
    self._validate_invocation(value, result)
    self._storage.record_invocation_evidence(value.request.attempt_id, result)
elif journal.resume_state == "in_progress_with_persisted_invocation":
    result = self._storage.verified_invocation_result(value.request.attempt_id)

finalized = finalize(value, result)
self._storage.record_finalized_attempt(finalized)
```

Keep explicit reconciliation for IN_PROGRESS without persisted invocation. Landed
SUCCEEDED recovery must rebuild commit input from persisted evidence and call the
adapter zero times.

- [ ] **Step 4: Run engine + storage + checkpoint tests**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_engine.py tests\test_storage.py tests\test_checkpoint.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/engine.py platform/tests/test_engine.py
git commit -m "feat(platform): make lifecycle evidence crash recoverable"
```

### Task 7: Thin feed-memory-prompt-adapter-parser pipeline

**Files:**
- Create: `platform/src/agent_ex/pipeline.py`
- Create: `platform/tests/test_pipeline.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [ ] **Step 1: Write failing E0/E2 success and privacy tests**

```python
def test_e2_mock_pipeline_persists_complete_chain_and_commits(tmp_path, inputs):
    outcome = run_one_mock_event(tmp_path, exposure="E2", **inputs)
    assert outcome.lifecycle.state == "committed"
    assert all((outcome.evidence.event_input_hash,
                outcome.evidence.request_hash,
                outcome.evidence.invocation_hash,
                outcome.evidence.parse_hash))

def test_social_prompt_never_contains_neighbor_private_fields(tmp_path, inputs):
    outcome, prompt = run_and_read_prompt(tmp_path, **inputs)
    rendered = json.dumps(prompt.to_payload(), ensure_ascii=False)
    assert inputs.neighbor_private_reason not in rendered
    assert "confidence" not in rendered
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_pipeline.py -k "e0 or e2 or private"`

Expected: FAIL because `MockEventPipeline` does not exist.

- [ ] **Step 3: Implement the thin coordinator**

```python
class MockEventPipeline:
    def execute(self, *, feed_capacity: int, memory_window: int,
                parser_limits: ParserLimits, prompt_limits: PromptLimits,
                policy: MockAttemptPolicyBinding,
                model_identity: Mapping[str, object],
                request_parameters: Mapping[str, object], model_seed: int,
                adapter: MockAdapter) -> MockEventPipelineOutcome:
        prepared = self._prepare(
            feed_capacity=feed_capacity, memory_window=memory_window,
            parser_limits=parser_limits, prompt_limits=prompt_limits,
            policy=policy, model_identity=model_identity,
            request_parameters=request_parameters, model_seed=model_seed,
            adapter_binding=adapter.execution_binding(),
        )
        with StrictSerialLifecycleEngine(self._storage) as engine:
            lifecycle = engine.execute(
                prepare=lambda journal: prepared,
                invoke=self._invoke(adapter),
                finalize=self._finalize,
                build_commit=self._build_commit,
            )
        return MockEventPipelineOutcome(
            lifecycle=lifecycle,
            evidence=self._storage.evidence_references(lifecycle.event_id),
        )


@dataclass(frozen=True, slots=True)
class MockEventPipelineOutcome:
    lifecycle: AttemptOutcome
    evidence: EventEvidenceReferences
```

`_prepare()` must call only existing public feed, memory, prompt, rendering, and request
factories. `_finalize()` must call `parse_agent_update()` and construct typed parse/N/A
plus terminal/failure evidence. `_build_commit()` must use the frozen schedule's
receiver and `publish_flag`; no value may default.

- [ ] **Step 4: Run pipeline plus component suites**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_pipeline.py tests\test_feed.py tests\test_memory.py tests\test_prompt.py tests\test_parser.py tests\test_mock_adapter.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/pipeline.py platform/src/agent_ex/__init__.py platform/tests/test_pipeline.py platform/tests/test_domain.py
git commit -m "feat(platform): connect mock event evidence pipeline"
```

### Task 8: Failure, retry, context rebuild, and tamper integration matrix

**Files:**
- Modify: `platform/tests/test_pipeline.py`
- Modify: `platform/tests/test_storage.py`
- Modify: `platform/tests/test_checkpoint.py`
- Modify: `platform/src/agent_ex/pipeline.py`
- Modify: `platform/src/agent_ex/storage.py`
- Modify: `platform/src/agent_ex/prompt.py`
- Modify: `platform/tests/test_prompt.py`

- [ ] **Step 1: Add the remaining failing integration tests**

```python
@pytest.mark.parametrize("crash_point", [
    "after_pending", "after_in_progress", "after_invocation",
    "after_terminal_success", "after_sqlite_commit_before_context",
])
def test_reopen_resumes_exact_prefix_without_blind_resend(crash_point, scenario):
    scenario.crash_at(crash_point)
    calls_before = scenario.adapter.calls
    outcome = scenario.reopen_and_resume()
    if crash_point in {"after_invocation", "after_terminal_success",
                       "after_sqlite_commit_before_context"}:
        assert scenario.adapter.calls == calls_before
    assert outcome.lifecycle.state in {"committed", "failed"}


def test_authorized_retry_reuses_input_and_allows_only_policy_fields(scenario):
    first = scenario.fail_parse()
    scenario.authorize_retry(first)
    second = scenario.retry(model_seed=scenario.allowed_seed)
    assert second.event_input_hash == first.event_input_hash
```

- [ ] **Step 2: Run the matrix and verify RED branches**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q tests\test_pipeline.py tests\test_storage.py tests\test_checkpoint.py -k "reopen or retry or tamper or timeout or context"`

Expected: at least one newly introduced crash/tamper branch fails before the minimal fix.

- [ ] **Step 3: Implement only the missing recovery/integrity branches**

Use `rebuild_validated_prompt_run_context()` from the complete succeeded SQLite prefix
after reopen or post-commit cache failure. Reject IN_PROGRESS without invocation unless
explicit reconciliation is supplied. Preserve raw malformed output and parser evidence;
never modify private/public/cursor state on FAILED. Add no timeout, retry, seed, B, K,
prompt, parser, request, or checkpoint defaults.

```python
def rebuild_validated_prompt_run_context(
    *, initial_context: ValidatedPromptRunContext,
    succeeded_prompt_views: tuple[PromptView, ...],
) -> ValidatedPromptRunContext:
    context = initial_context
    for view in succeeded_prompt_views:
        context = advance_validated_prompt_run_context(context=context, prompt_view=view)
    return context

def _validated_context(self) -> ValidatedPromptRunContext:
    succeeded = self._storage.succeeded_event_prompt_prefix()
    return rebuild_validated_prompt_run_context(
        initial_context=self._initial_prompt_context,
        succeeded_prompt_views=succeeded,
    )

def _recover_invocation(self, attempt_id: str) -> AttemptInvocationResult:
    persisted = self._storage.invocation_evidence(attempt_id)
    if persisted is None:
        raise RuntimeError("IN_PROGRESS requires explicit provider reconciliation")
    response = verify_persisted_mock_response(
        request=self._storage.adapter_request(attempt_id),
        response_payload=persisted.response_payload,
        binding=self._storage.adapter_execution_binding(attempt_id),
    )
    return AttemptInvocationResult(response=response, evidence=persisted.execution)
```

- [ ] **Step 4: Run focused, combined, and full gates**

```powershell
cd platform
.\.venv\Scripts\python.exe -m pytest -q tests\test_pipeline.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_engine.py tests\test_storage.py tests\test_checkpoint.py tests\test_pipeline.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: all tests pass; only documented Windows-condition skips remain; all static,
format, dependency, and diff gates pass.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/pipeline.py platform/src/agent_ex/storage.py platform/src/agent_ex/prompt.py platform/tests/test_pipeline.py platform/tests/test_storage.py platform/tests/test_checkpoint.py platform/tests/test_prompt.py
git commit -m "test(platform): close Phase 4B-8C-3 recovery matrix"
```

### Task 9: Evidence log, independent review, and milestone push

**Files:**
- Create: `logs/2026-09-01-phase4b8c3-evidence-pipeline.md`
- Modify: `docs/superpowers/specs/2026-09-01-paper1-phase4b8c3-evidence-pipeline-design.md` only if implementation reveals an approved clarification.

- [ ] **Step 1: Write the implementation evidence log**

Record exact commit boundaries, test counts, crash-prefix coverage, storage version,
mock-only limitations, and the remaining 4B-9 12-cell/N=20/100/1000 and 50,000-event
performance gates. Do not claim formal-experiment readiness.

```markdown
# Phase 4B-8C-3 Evidence

## Boundary
- Storage schema: paper1.run-storage.v6
- Runtime: mock-only; no network or real model

## Verified recovery prefixes
- Record each tested prefix and exact test name/count.

## Gates
- Record focused, combined, full-suite, Ruff, formatting, pip, and diff results.

## Deferred to Phase 4B-9
- 12-cell mock matrix; N=20/100/1000 invariants; 50,000-event performance.
```

- [ ] **Step 2: Run fresh verification in an isolated pytest temp directory**

Run: `cd platform; .\.venv\Scripts\python.exe -m pytest -q --basetemp="$env:TEMP\phase4b8c3-final"`

Expected: full PASS with only platform-conditional skips.

- [ ] **Step 3: Request bounded independent reviews**

Dispatch one verification reviewer, one specification/anti-pattern reviewer, and one
code-quality reviewer. Require exact P0-P3 findings, not general approval. Fix every
P0-P2 with a new RED/GREEN test and re-run affected reviews.

- [ ] **Step 4: Commit the final log and any reviewed corrections**

```powershell
git add logs/2026-09-01-phase4b8c3-evidence-pipeline.md platform/src/agent_ex/execution_evidence.py platform/src/agent_ex/pipeline.py platform/src/agent_ex/adapters/base.py platform/src/agent_ex/adapters/mock.py platform/src/agent_ex/storage.py platform/src/agent_ex/engine.py platform/src/agent_ex/checkpoint.py platform/src/agent_ex/prompt.py platform/src/agent_ex/__init__.py platform/tests/test_execution_evidence.py platform/tests/test_pipeline.py platform/tests/test_domain.py platform/tests/test_mock_adapter.py platform/tests/test_storage.py platform/tests/test_engine.py platform/tests/test_checkpoint.py platform/tests/test_prompt.py docs/superpowers/specs/2026-09-01-paper1-phase4b8c3-evidence-pipeline-design.md
git commit -m "feat(platform): complete Phase 4B-8C-3 evidence pipeline"
```

- [ ] **Step 5: Push and verify the remote boundary**

```powershell
git push
git status --short
git rev-parse HEAD
git rev-parse '@{u}'
```

Expected: clean worktree and identical local/upstream commit hashes.

## Self-review

- Spec coverage: Tasks 1-8 cover all six evidence groups, parser limits before
  invocation, adapter attestation, atomic failure evidence, valid lifecycle prefixes,
  retry normalization, disposable prompt context, zero-resend recovery, v5 rejection,
  checkpoint hashes, privacy, and explicit unresolved inputs. Task 9 covers evidence
  and independent release gates.
- Placeholder scan: no `TBD`, `TODO`, “similar to”, omitted method body, or unspecified
  production error handling remains. The only ellipsis token is Python's concrete
  variable-length tuple annotation `tuple[str, ...]`.
- Type consistency: `MockAttemptPolicyBinding`, `MockAdapterExecutionBinding`,
  `EventInputEvidence`, `PersistedInvocationEvidence`,
  `ParseNotApplicableEvidence`, `FinalizedAttemptEvidence`,
  `EventEvidenceReferences`, `MockEventPipelineOutcome`, `PreparedAttempt`, and
  `AttemptOutcome` retain the same names and roles across all tasks.
