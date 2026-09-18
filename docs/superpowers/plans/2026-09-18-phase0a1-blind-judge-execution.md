# Phase 0A-1 Blind Judge Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a blinded, hash-bound, crash-safe Qwen judge pipeline for all 797 eligible Phase 0A-1 items, convert the independent 174-item human form, and admit only one fully evidenced 971-record review import.

**Architecture:** A trusted materializer validates the existing full review bundle and emits a byte-equivalent judge-only view; a separate runner receives only that view plus two owner-approved execution records. Judge requests, responses, parses, dispatch reconciliation, service lifecycle, human records, and final v2 code sets remain create-only and content-addressed outside Git. Existing v1 synthetic review behavior remains available, while real Phase 0A-1 evidence must pass the new v2 dereference chain.

**Tech Stack:** Python 3.12, frozen dataclasses, strict canonical JSON/SHA-256, urllib loopback HTTP, pytest 9, Ruff, Bash service lifecycle, Git bundles, AutoDL vLLM/Qwen3-8B.

---

## File map

- Create `platform/src/agent_ex/calibration/judge_contracts.py`: renderer, authorization, manifest, request/response/parse, lifecycle, completion, reconciliation, evidence-index, human-record, and v2 code-set contracts.
- Create `platform/src/agent_ex/calibration/judge_materialize.py`: trusted full-bundle validation and byte-equivalent runner-only view creation.
- Create `platform/src/agent_ex/calibration/judge_adapter.py`: loopback-only single-item transport with raw-byte preservation.
- Create `platform/src/agent_ex/calibration/judge_store.py`: create-only content-addressed judge archive and exact projection.
- Create `platform/src/agent_ex/calibration/judge_runner.py`: parser, retry state machine, execution, resume, reconciliation, verify, and completion.
- Create `platform/src/agent_ex/calibration/judge_review.py`: judge code export, human import, 971-record composition, and v2 evidence dereference.
- Modify `platform/src/agent_ex/calibration/review.py`: retain v1 records and accept verified v2 records only through the new bridge.
- Modify `platform/src/agent_ex/calibration/cli.py`: add the narrow judge/human/materialization/composition commands and v2 review-import arguments.
- Modify `platform/src/agent_ex/calibration/__init__.py`: export only stable judge entry points.
- Create `platform/tests/fixtures/paper1/phase0a1_judge_rendered_request.golden.json`: complete immutable renderer fixture and expected content hash.
- Create `platform/scripts/phase0a1-judge-service.sh`: judge-specific start/status/stop lifecycle; leave the existing probe service script unchanged.
- Create focused tests in `platform/tests/test_calibration_judge_*.py`; extend CLI, review, cloud-script, and public-import tests.
- Create `logs/2026-09-18-phase0a1-blind-judge-execution.md` and update `progress.md` only after fresh verification.

### Task 1: Freeze the exact renderer and two-stage authorization

**Files:**
- Create: `platform/src/agent_ex/calibration/judge_contracts.py`
- Create: `platform/tests/fixtures/paper1/phase0a1_judge_rendered_request.golden.json`
- Test: `platform/tests/test_calibration_judge_contracts.py`

- [ ] **Step 1: Write the failing renderer and authorization tests**

```python
def test_renderer_golden_binds_roles_schema_labels_and_seed(valid_judge_item, valid_policy):
    renderer = JudgeRequestRenderer.create(valid_policy)
    rendered = renderer.render(valid_judge_item, attempt_index=1, repair=False)
    assert tuple(message["role"] for message in rendered.messages) == ("system", "user")
    assert tuple(rendered.response_schema["properties"]) == tuple(valid_policy.dimension_labels)
    assert rendered.seed == derive_judge_seed(renderer.record_hash, valid_judge_item.item_id, 1)
    assert rendered.record_hash == canonical_payload_hash(rendered.content_payload())
    fixture = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
    assert rendered.to_payload() == fixture["rendered_request"]
    assert rendered.record_hash == fixture["record_hash"]


def test_authorization_rejects_missing_renderer_or_runtime_value(valid_authorization_payload):
    for field in ("renderer_hash", "old_environment_lock_hash", "max_attempts_per_item"):
        payload = dict(valid_authorization_payload)
        del payload[field]
        with pytest.raises(ValueError, match="exact fields"):
            JudgeAuthorization.from_payload(payload)
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_contracts.py -k "renderer or authorization"
```

Expected: collection fails because the judge contracts do not exist.

- [ ] **Step 3: Add canonical renderer and authorization contracts**

```python
VISIBLE_FIELDS = ("topic_text", "history_text", "identity_text", "response_text")
DIMENSIONS = (
    "refusal", "stance_consistency", "single_construct", "identity_use",
    "stereotyping", "continuity_coherence", "change_appropriateness",
    "information_fidelity",
)


def derive_judge_seed(renderer_hash: str, item_id: str, attempt_index: int) -> int:
    digest = canonical_payload_hash(
        {"renderer_hash": renderer_hash, "item_id": item_id, "attempt_index": attempt_index}
    )
    return int(digest[:16], 16)


@dataclass(frozen=True, slots=True)
class JudgeAuthorization:
    authorization_id: str
    export_hash: str
    review_bundle_hash: str
    judge_pack_hash: str
    judge_pack_index_hash: str
    old_judge_prompt_hash: str
    renderer_hash: str
    coder_contract_hash: str
    ordering_policy_hash: str
    classifier_contract_hash: str
    old_environment_lock_hash: str
    model_id: str
    model_revision: str
    tokenizer_id: str
    tokenizer_revision: str
    tokenizer_hash: str
    chat_template_hash: str
    runtime_version: str
    non_thinking: bool
    connect_timeout_seconds: float
    read_timeout_seconds: float
    total_timeout_seconds: float
    max_attempts_per_item: int
    retryable_codes: tuple[str, ...]
    retry_backoff_seconds: tuple[float, ...]
    request_identity_derivation: str
    idempotency_key_derivation: str
    one_item_per_request: bool
    strict_approved_order: bool
    generation_settings: Mapping[str, object]
    archive_uri: str
    source_commit: str
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-authorization.v1"
```

Implement exact-field `from_payload`, sorted/canonical `to_payload`, immutable mappings, SHA-256 checks, loopback-only runtime declaration, positive attempt budget, and calibration-only/no-formal-authority metadata using the conventions in `review.py`. `JudgeRequestRenderer` must store complete system/normal-user/repair templates, roles, field order, label enums, exact response schema, canonical serialization version, chat-template hash, response-byte ceiling, and the checked-in full golden fixture hash. Add a tamper test that changes one role, label, field order, or escape sequence and proves fixture verification fails.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_contracts.py -k "renderer or authorization"
& .\.test-venv\Scripts\python.exe -m ruff check platform/src/agent_ex/calibration/judge_contracts.py platform/tests/test_calibration_judge_contracts.py
git add -- platform/src/agent_ex/calibration/judge_contracts.py platform/tests/fixtures/paper1/phase0a1_judge_rendered_request.golden.json platform/tests/test_calibration_judge_contracts.py
git diff --cached --check
git commit -m "freeze phase0a1 judge request authorization"
```

### Task 2: Materialize a strictly blinded runner-only view

**Files:**
- Create: `platform/src/agent_ex/calibration/judge_materialize.py`
- Test: `platform/tests/test_calibration_judge_materialize.py`

- [ ] **Step 1: Write failing parity and information-boundary tests**

```python
def test_materializer_emits_byte_equivalent_approved_judge_pack(tmp_path, review_inputs):
    result = materialize_judge_view(**review_inputs, output_root=tmp_path / "runner")
    assert result.pack_hash == review_inputs["approved_pack_hash"]
    assert result.index_hash == review_inputs["approved_index_hash"]
    assert (tmp_path / "runner" / "judge-pack.json").read_bytes() == review_inputs["pack_bytes"]


def test_runner_view_excludes_hidden_and_human_material(tmp_path, review_inputs):
    materialize_judge_view(**review_inputs, output_root=tmp_path / "runner")
    names = {path.name for path in (tmp_path / "runner").iterdir()}
    assert names == {"judge-pack.json", "index.json", "materialization.json"}
    payload = (tmp_path / "runner" / "judge-pack.json").read_text(encoding="utf-8")
    for forbidden in ("hidden_bindings", "human_audit_selected", "candidate_id"):
        assert forbidden not in payload
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_materialize.py
```

- [ ] **Step 3: Implement the trusted materializer**

```python
@dataclass(frozen=True, slots=True)
class JudgeMaterialization:
    review_bundle_hash: str
    export_hash: str
    pack_hash: str
    index_hash: str
    item_count: int
    record_hash: str


def materialize_judge_view(
    *, bundle: SemanticReviewBundle, pack_bytes: bytes, index_bytes: bytes,
    approved_pack_hash: str, approved_index_hash: str, output_root: Path,
) -> JudgeMaterialization:
    pack = load_exact_json_bytes(pack_bytes)
    index = load_exact_json_bytes(index_bytes)
    validate_existing_judge_pack(bundle, pack, index)
    pack_content = {key: value for key, value in pack.items() if key != "record_hash"}
    index_content = {key: value for key, value in index.items() if key != "record_hash"}
    if pack.get("record_hash") != canonical_payload_hash(pack_content):
        raise ValueError("judge pack embedded record hash is invalid")
    if index.get("record_hash") != canonical_payload_hash(index_content):
        raise ValueError("judge pack index embedded record hash is invalid")
    if pack["record_hash"] != approved_pack_hash:
        raise ValueError("judge pack differs from its approved hash")
    if index["record_hash"] != approved_index_hash:
        raise ValueError("judge pack index differs from its approved hash")
    write_directory_create_only(
        output_root,
        {"judge-pack.json": pack_bytes, "index.json": index_bytes},
    )
    result = JudgeMaterialization.create(bundle, pack, index)
    write_json_create_only(output_root / "materialization.json", result.to_payload())
    return result
```

The validator must prove exactly 797 items, original order, four visible fields only, matching item/export/policy/coder hashes, and no human or hidden fields. It copies original canonical bytes; it never rebuilds or reorders the approved pack.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_materialize.py
git add -- platform/src/agent_ex/calibration/judge_materialize.py platform/tests/test_calibration_judge_materialize.py
git diff --cached --check
git commit -m "materialize blinded phase0a1 judge view"
```

### Task 3: Bind judge-specific fresh environment and service lifecycle into the final manifest

**Files:**
- Modify: `platform/src/agent_ex/calibration/judge_contracts.py`
- Modify: `platform/src/agent_ex/calibration/cli.py`
- Create: `platform/scripts/phase0a1-judge-service.sh`
- Test: `platform/tests/test_calibration_judge_contracts.py`
- Test: `platform/tests/test_phase0a1_cloud_scripts.py`

- [ ] **Step 1: Write failing manifest/lifecycle tests**

```python
def test_manifest_binds_authorization_fresh_lock_preflight_and_start(valid_lifecycle):
    manifest = JudgeExecutionManifest.create(**valid_lifecycle)
    assert manifest.authorization_hash == valid_lifecycle["authorization"].record_hash
    assert manifest.environment_lock_hash == valid_lifecycle["environment_lock"].record_hash
    assert manifest.preflight_hash == valid_lifecycle["preflight_hash"]
    assert manifest.service_start_identity_hash == valid_lifecycle["start_hash"]


def test_manifest_rejects_environment_drift(valid_lifecycle):
    valid_lifecycle["environment_lock"] = EnvironmentLock.create(
        valid_lifecycle["environment_observation"], authorization_hash="f" * 64
    )
    with pytest.raises(ValueError, match="authorization|environment"):
        JudgeExecutionManifest.create(**valid_lifecycle)


@pytest.mark.parametrize(
    "field",
    (
        "review_bundle_hash", "export_hash", "judge_pack_hash", "judge_pack_index_hash",
        "judge_coder_contract_hash", "old_judge_prompt_hash", "renderer_hash",
        "ordering_policy_hash", "classifier_contract_hash", "model_id", "model_revision",
        "tokenizer_id", "tokenizer_revision", "tokenizer_hash", "chat_template_hash",
        "runtime_version", "non_thinking", "generation_settings",
        "connect_timeout_seconds", "read_timeout_seconds", "total_timeout_seconds",
        "retryable_codes", "retry_backoff_seconds", "max_attempts_per_item",
        "one_item_per_request", "strict_approved_order", "archive_uri", "source_commit",
    ),
)
def test_manifest_rejects_every_authorization_field_drift(valid_lifecycle, field):
    manifest_values = manifest_values_from_authorization(valid_lifecycle["authorization"])
    manifest_values[field] = distinct_valid_value(field, manifest_values[field])
    with pytest.raises(ValueError, match="authorization|drift"):
        JudgeExecutionManifest.create(**valid_lifecycle, **manifest_values)


def test_pre_manifest_abort_binds_authorization_start_and_optional_lock(valid_lifecycle):
    abort = JudgePreManifestAbortEvidence.create(
        authorization_hash=valid_lifecycle["authorization"].record_hash,
        service_start_identity_hash=valid_lifecycle["start_hash"],
        environment_lock_hash=None,
        process_exit_observed=True,
        loopback_listener_absent=True,
        gpu_idle_observation_hash="a" * 64,
    )
    assert abort.environment_lock_hash is None
    with pytest.raises(ValueError, match="abort|completion"):
        JudgeRunCompletion.create_from_abort(abort)
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_contracts.py platform/tests/test_phase0a1_cloud_scripts.py -k "judge and service"
```

- [ ] **Step 3: Add lifecycle contracts and preserve old service modes**

```python
@dataclass(frozen=True, slots=True)
class JudgeExecutionManifest:
    run_id: str
    authorization_hash: str
    review_bundle_hash: str
    export_hash: str
    judge_pack_hash: str
    judge_pack_index_hash: str
    judge_coder_contract_hash: str
    old_judge_prompt_hash: str
    renderer_hash: str
    ordering_policy_hash: str
    classifier_contract_hash: str
    environment_lock_hash: str
    preflight_hash: str
    service_start_identity_hash: str
    runner_view_hash: str
    old_environment_lock_hash: str
    model_id: str
    model_revision: str
    tokenizer_hash: str
    tokenizer_id: str
    tokenizer_revision: str
    chat_template_hash: str
    runtime_version: str
    non_thinking: bool
    generation_settings: Mapping[str, object]
    connect_timeout_seconds: float
    read_timeout_seconds: float
    total_timeout_seconds: float
    retryable_codes: tuple[str, ...]
    retry_backoff_seconds: tuple[float, ...]
    max_attempts_per_item: int
    one_item_per_request: bool
    strict_approved_order: bool
    archive_uri: str
    source_commit: str
    expected_item_count: int
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    _SCHEMA = "paper1.calibration.judge-execution-manifest.v1"
```

Add `judge-preflight` and `judge-lock` CLI commands. Authorization construction must load the approved supporting material and require `old_judge_prompt_hash` equality before computing its hash. `judge-preflight` is a static preliminary inspection that does not require a live health check. Start the service bound only to `JudgeAuthorization.record_hash`; then `judge-lock` collects the live loopback HTTP-200 health observation and creates an `EnvironmentLock` whose authorization hash is exactly `JudgeAuthorization.record_hash`, rather than reusing the probe lock command. Add `JudgeServiceEvidence` wrappers for preliminary/start/live-observation/stop and `JudgeRunCompletion`. Manifest construction must compare every repeated static/runtime field above against the authorization and reject drift; the repetition is deliberate, not a transitive shortcut.

Create a separate `phase0a1-judge-service.sh` with `start`, `status`, `abort-pre-manifest`, and `stop` commands. `start` binds only the authorization hash and emits a judge start-identity schema, because a health-bearing environment lock cannot exist until the service is live. `abort-pre-manifest` requires authorization/start hashes, accepts an optional live environment-lock hash, stops the process, and emits immutable `JudgePreManifestAbortEvidence` with port/GPU-idle proof; it never requires or invents a manifest hash. `stop` is reserved for post-manifest runs, requires the final manifest hash, and emits a judge stop schema containing process exit, loopback listener absence, a separately measured GPU compute-process observation hash, environment-lock hash, start-identity hash, and manifest hash. Completion/export reject abort evidence. Do not change `phase0a1-service.sh` or `paper1.calibration.service-stop-evidence.v1`.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_contracts.py platform/tests/test_phase0a1_cloud_scripts.py platform/tests/test_calibration_cli.py
git add -- platform/src/agent_ex/calibration/judge_contracts.py platform/src/agent_ex/calibration/cli.py platform/scripts/phase0a1-judge-service.sh platform/tests/test_calibration_judge_contracts.py platform/tests/test_phase0a1_cloud_scripts.py platform/tests/test_calibration_cli.py
git diff --cached --check
git commit -m "bind judge service lifecycle evidence"
```

### Task 4: Add the loopback judge adapter and strict parser

**Files:**
- Create: `platform/src/agent_ex/calibration/judge_adapter.py`
- Modify: `platform/src/agent_ex/calibration/judge_contracts.py`
- Test: `platform/tests/test_calibration_judge_adapter.py`

- [ ] **Step 1: Write failing success and failure tests**

```python
@pytest.mark.parametrize("endpoint", ["http://example.com/v1", "http://0.0.0.0:8000/v1"])
def test_adapter_rejects_non_loopback(endpoint):
    with pytest.raises(ValueError, match="loopback"):
        JudgeVllmAdapter(endpoint=endpoint, model_id="qwen", limits=LIMITS)


def test_parser_requires_exact_eight_dimension_object(valid_policy):
    labels = {name: values[0] for name, values in valid_policy.dimension_labels.items()}
    parsed = parse_judge_response(json.dumps(labels).encode(), valid_policy)
    assert parsed.success is True
    failed = parse_judge_response(json.dumps({"refusal": "no"}).encode(), valid_policy)
    assert failed.success is False
    assert failed.failure_code == "parse_missing_dimensions"


@pytest.mark.parametrize(
    ("server_outcome", "expected_code"),
    (
        ("invalid_provider_json", "provider_invalid_json"),
        ("timeout", "timeout"),
        ("http_429", "http_429"),
        ("http_500", "http_5xx"),
        ("oom", "provider_oom"),
        ("oversize", "response_size_exceeded"),
        ("missing_request_id", "provider_request_identity_missing"),
        ("model_drift", "provider_model_identity_drift"),
    ),
)
def test_adapter_maps_one_typed_failure_without_internal_retry(
    fake_judge_server, valid_request, server_outcome, expected_code
):
    fake_judge_server.outcome = server_outcome
    evidence = fake_judge_server.adapter.generate(valid_request)
    assert evidence.failure_code == expected_code
    assert fake_judge_server.request_count == 1


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (("invalid_json", "parse_invalid_json"),
     ("illegal_label", "parse_illegal_label"),
     ("missing_dimension", "parse_missing_dimensions")),
)
def test_parser_maps_typed_failures(mutation, expected_code, valid_labels, valid_policy):
    labels = dict(valid_labels)
    if mutation == "invalid_json":
        raw = b"not-json"
    elif mutation == "illegal_label":
        labels["refusal"] = "outside-policy"
        raw = canonical_json_bytes(labels)
    else:
        labels.pop("information_fidelity")
        raw = canonical_json_bytes(labels)
    evidence = parse_judge_response(raw, valid_policy)
    assert evidence.success is False
    assert evidence.failure_code == expected_code


def test_valid_refusal_label_is_preserved_not_transport_failure(valid_labels, valid_policy):
    valid_labels["refusal"] = "refusal"
    evidence = parse_judge_response(canonical_json_bytes(valid_labels), valid_policy)
    assert evidence.success is True
    assert evidence.labels["refusal"] == "refusal"
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_adapter.py
```

- [ ] **Step 3: Implement one-request/one-item transport**

```python
class JudgeVllmAdapter:
    def generate(self, request: JudgeRequestEvidence) -> JudgeResponseEvidence:
        body = canonical_json_bytes(request.provider_payload())
        self._before_dispatch(request, body)
        response = self._client.send(body, timeout=self._limits.total_timeout_seconds)
        return JudgeResponseEvidence.create(
            request=request,
            provider_request_id=response.headers.get("x-request-id"),
            status_code=response.status,
            raw_bytes=response.body,
            model_id=response.model_id,
            termination=response.finish_reason,
        )
```

Map timeout, 429/retry-after, HTTP 5xx, OOM, size ceiling, invalid provider JSON, missing request ID, and model drift into the exact typed response outcomes asserted above without internal retries. Parse invalid JSON, missing dimensions, illegal labels, and a legal refusal label into the exact parse evidence asserted above. The runner persists every failed `JudgeParseEvidence` before consulting retry policy; parser contract failures return typed evidence rather than raising. Preserve exact raw bytes in the returned evidence; never log them.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_adapter.py
git add -- platform/src/agent_ex/calibration/judge_adapter.py platform/src/agent_ex/calibration/judge_contracts.py platform/tests/test_calibration_judge_adapter.py
git diff --cached --check
git commit -m "add loopback phase0a1 judge adapter"
```

### Task 5: Create the append-only store, projection, and reconciliation

**Files:**
- Create: `platform/src/agent_ex/calibration/judge_store.py`
- Create: `platform/src/agent_ex/calibration/judge_runner.py`
- Test: `platform/tests/test_calibration_judge_store.py`
- Test: `platform/tests/test_calibration_judge_runner.py`

- [ ] **Step 1: Write failing crash-window tests**

```python
def test_unresolved_dispatch_requires_typed_reconciliation(judge_store):
    judge_store.append_intent(INTENT)
    with pytest.raises(AmbiguousJudgeDispatchError):
        reconstruct_judge_projection(judge_store)


@pytest.mark.parametrize("decision", ["recovered_response", "proved_not_sent", "ambiguous"])
def test_reconciliation_has_only_three_outcomes(judge_store, decision):
    judge_store.append_intent(INTENT)
    record = JudgeDispatchReconciliation.create(INTENT, decision, RECONCILIATION_EVIDENCE)
    judge_store.append_reconciliation(record)
    projection = reconstruct_judge_projection(judge_store)
    assert projection.item_states[INTENT.item_id].status == EXPECTED_STATUS[decision]


@pytest.mark.parametrize(
    "crash_point", ("after_intent", "after_provider_response", "after_raw", "after_attempt")
)
def test_each_dispatch_crash_window_fails_closed(judge_store, provider_audit, crash_point):
    simulate_dispatch_crash(judge_store, provider_audit, crash_point)
    with pytest.raises(AmbiguousJudgeDispatchError):
        reconstruct_judge_projection(judge_store)


def test_provider_log_recovery_preserves_exact_bytes(judge_store, provider_audit):
    intent = append_unresolved_sent_intent(judge_store, provider_audit)
    recovered = reconcile_from_provider_log(judge_store, intent, provider_audit)
    assert recovered.decision == "recovered_response"
    assert recovered.response_bytes_hash == provider_audit.response_bytes_hash


def test_proved_not_sent_retry_gets_new_attempt_but_same_item_identity(judge_store):
    intent = append_unresolved_unsent_intent(judge_store)
    reconciliation = reconcile_proved_not_sent(judge_store, intent)
    retry = build_retry_after_not_sent(intent, reconciliation)
    assert retry.item_id == intent.item_id
    assert retry.attempt_id != intent.attempt_id
    assert retry.idempotency_key != intent.idempotency_key
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_store.py platform/tests/test_calibration_judge_runner.py -k "projection or reconciliation or dispatch"
```

- [ ] **Step 3: Implement create-only layout and exact projection**

```python
LAYOUT = (
    "attempts", "dispatch", "reconciliation", "raw",
    "service/preflight", "service/start", "service/stop",
)


class JudgeRunStore:
    @classmethod
    def create(cls, root: Path, manifest: JudgeExecutionManifest) -> "JudgeRunStore":
        create_exact_tree(root, LAYOUT)
        write_json_create_only(root / "staging/manifest.json", manifest.to_payload())
        write_projection_snapshot(root, empty_projection(manifest))
        return cls.open(root)

    def append(self, kind: str, record: HashedJudgeRecord) -> None:
        if kind not in LAYOUT:
            raise ValueError("unsupported judge evidence kind")
        write_json_create_only(self.root / "staging" / kind / f"{record.record_hash}.json", record.to_payload())
        write_projection_snapshot(self.root, reconstruct_from_append_only_records(self.root))
```

`write_projection_snapshot` writes `staging/projections/<zero-padded-sequence>-<record_hash>.json` with `previous_projection_hash`; it never overwrites a snapshot. `open` accepts exactly one contiguous hash chain and treats the last snapshot as the current derived projection. A terminal `staging/projection.json` is written create-only only by verification and must equal the last snapshot. Projection replay requires contiguous approved item order, intent-before-send, response/raw/attempt/resolution exact cover, monotonically accumulated per-item budgets, immutable coded state, and service preflight/start hashes equal to the manifest. `proved_not_sent` authorizes a new attempt identity; `recovered_response` rejoins parsing; `ambiguous` is terminal incomplete.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_store.py platform/tests/test_calibration_judge_runner.py -k "projection or reconciliation or dispatch"
git add -- platform/src/agent_ex/calibration/judge_store.py platform/src/agent_ex/calibration/judge_runner.py platform/tests/test_calibration_judge_store.py platform/tests/test_calibration_judge_runner.py
git diff --cached --check
git commit -m "persist resumable judge evidence chain"
```

### Task 6: Execute and resume the deterministic 797-item run

**Files:**
- Modify: `platform/src/agent_ex/calibration/judge_runner.py`
- Test: `platform/tests/test_calibration_judge_runner.py`

- [ ] **Step 1: Write failing uninterrupted/resume equivalence tests**

```python
@pytest.mark.parametrize("cut", [1, 313, 796])
def test_resume_matches_uninterrupted_projection(tmp_path, judge_fixture, cut):
    full = run_judge(**judge_fixture, root=tmp_path / "full")
    run_judge(**judge_fixture, root=tmp_path / "resumed", stop_after_attempts=cut)
    resumed = resume_judge(**judge_fixture, root=tmp_path / "resumed")
    assert resumed.content_payload() == full.content_payload()
    assert len(resumed.coded_item_ids) == judge_fixture.manifest.expected_item_count


def test_retry_budget_never_resets_across_resume(judge_fixture):
    projection = run_scripted_failures(judge_fixture, failures=("timeout", "invalid_json", "success"))
    assert projection.attempt_counts[projection.item_order[0]] == 3
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_runner.py -k "resume or budget or 797"
```

- [ ] **Step 3: Implement the state machine**

```python
def next_judge_action(state: JudgeItemState, authorization: JudgeAuthorization) -> str:
    if state.status in {"coded", "terminal_failed", "ambiguous_incomplete"}:
        return "stop"
    if state.unresolved_intent_hash is not None:
        return "reconcile"
    if state.attempt_count >= authorization.max_attempts_per_item:
        return "terminal_failed"
    if state.last_error in authorization.retryable_codes:
        return "repair" if state.last_error.startswith("parse_") else "retry"
    return "initial"
```

Run strictly in approved pack order. Before every network call append the intent atomically; after response append raw artifact, response/parse/attempt, then resolution. Resume reopens the same manifest/store, verifies service identity and full prefix, and refuses unresolved intent or terminal rerun. Output/control files are create-only.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_runner.py
git add -- platform/src/agent_ex/calibration/judge_runner.py platform/tests/test_calibration_judge_runner.py
git diff --cached --check
git commit -m "execute deterministic resumable judge run"
```

### Task 7: Verify completion and export 797 judge codes with evidence index

**Files:**
- Create: `platform/src/agent_ex/calibration/judge_review.py`
- Modify: `platform/src/agent_ex/calibration/judge_contracts.py`
- Test: `platform/tests/test_calibration_judge_review.py`

- [ ] **Step 1: Write failing completion and tamper tests**

```python
def test_export_requires_completion_and_unique_stop(complete_judge_store):
    completion = verify_judge_completion(complete_judge_store)
    codes, index = export_judge_codes(complete_judge_store, completion)
    assert len(codes) == 797
    assert index.judge_run_completion_hash == completion.record_hash


@pytest.mark.parametrize("missing", ["raw", "service/index.json", "service/stop", "completion.json"])
def test_export_rejects_missing_or_tampered_evidence(complete_judge_store, missing):
    remove_or_tamper(complete_judge_store, missing)
    with pytest.raises(ValueError, match="evidence|completion|stop"):
        export_judge_codes_from_root(complete_judge_store.root)


@pytest.mark.parametrize("extra", ["preflight", "start", "stop", "projection"])
def test_completion_rejects_extra_lifecycle_or_projection_evidence(complete_judge_store, extra):
    append_extra_evidence(complete_judge_store, extra)
    with pytest.raises(ValueError, match="exact|inventory|extra"):
        verify_judge_completion(complete_judge_store)
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_review.py -k "completion or export or tamper"
```

- [ ] **Step 3: Implement completion and index export**

```python
@dataclass(frozen=True, slots=True)
class JudgeEvidenceIndex:
    judge_run_completion_hash: str
    judge_run_completion_locator: str
    entries: tuple[JudgeEvidenceEntry, ...]
    record_hash: str


def verify_judge_completion(store: JudgeRunStore) -> JudgeRunCompletion:
    projection = reconstruct_judge_projection(store)
    service = store.load_service_index()
    manifest = store.load_manifest()
    if (
        len(projection.coded_item_ids) != manifest.expected_item_count
        or len(service.stop_hashes) != 1
    ):
        raise ValueError("judge completion lacks exact terminal/service cover")
    stop = store.load_stop(service.stop_hashes[0])
    if not (stop.process_exit_observed and stop.loopback_listener_absent and stop.gpu_idle):
        raise ValueError("judge service stop evidence is incomplete")
    return JudgeRunCompletion.create(projection, service, stop)
```

Each index entry maps one code hash to manifest, request, intent, attempt, response, parse, raw, and resolution identities/hashes. Export only completed labels; no failed code can be silently omitted or replaced.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_review.py -k "completion or export or tamper"
git add -- platform/src/agent_ex/calibration/judge_review.py platform/src/agent_ex/calibration/judge_contracts.py platform/tests/test_calibration_judge_review.py
git diff --cached --check
git commit -m "export evidenced phase0a1 judge codes"
```

### Task 8: Convert the human form and compose one 971-record v2 set

**Files:**
- Modify: `platform/src/agent_ex/calibration/judge_review.py`
- Modify: `platform/src/agent_ex/calibration/judge_contracts.py`
- Test: `platform/tests/test_calibration_judge_review.py`

- [ ] **Step 1: Write failing human import and compose tests**

```python
def test_human_form_to_971_record_v2_set(human_form, judge_export, review_inputs):
    human_codes, human_index = import_human_form(human_form, **review_inputs)
    combined = compose_review_codes(
        judge_codes=judge_export.codes,
        judge_index=judge_export.index,
        human_codes=human_codes,
        human_index=human_index,
        review_bundle=review_inputs["bundle"],
    )
    assert len(human_codes) == 174
    assert len(combined.records) == 971
    assert combined.judge_run_completion_hash == judge_export.index.judge_run_completion_hash


def test_human_export_is_blank_and_human_verify_checks_exact_cover(review_inputs, tmp_path):
    template = export_human_form(
        bundle=review_inputs["bundle"],
        human_pack=review_inputs["human_pack"],
        human_pack_hash=review_inputs["human_pack_hash"],
    )
    assert len(template.items) == 174
    assert all(record.labels == {} and record.encoded_at is None for record in template.records)
    completed = complete_human_fixture(template, review_inputs["policy"])
    verified = verify_human_form(completed, bundle=review_inputs["bundle"])
    assert verified.source_template_hash == template.record_hash
    assert len(verified.records) == 174


def test_compose_rejects_partial_duplicate_or_manual_json(human_form, judge_export, review_inputs):
    human_codes, human_index = import_human_form(human_form, **review_inputs)
    with pytest.raises(ValueError, match="exact cover"):
        compose_review_codes(judge_codes=judge_export.codes[:-1], judge_index=judge_export.index,
                             human_codes=human_codes, human_index=human_index,
                             review_bundle=review_inputs["bundle"])
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_review.py -k "human or compose or 971"
```

- [ ] **Step 3: Add human and v2 contracts**

```python
@dataclass(frozen=True, slots=True)
class HumanCodingRecord:
    item_id: str
    item_hash: str
    coder_id: str
    coder_contract_hash: str
    labels: Mapping[str, str]
    encoded_at: str
    source_form_hash: str
    record_hash: str


@dataclass(frozen=True, slots=True)
class HumanCodingTemplate:
    review_bundle_hash: str
    export_hash: str
    human_pack_hash: str
    coder_contract_hash: str
    items: tuple[BlindReviewItem, ...]
    records: tuple[Mapping[str, object], ...]
    record_hash: str


@dataclass(frozen=True, slots=True)
class CompletedHumanCodingForm:
    template_hash: str
    review_bundle_hash: str
    export_hash: str
    human_pack_hash: str
    coder_id: str
    coder_contract_hash: str
    records: tuple[HumanCodingRecord, ...]
    completed_at: str
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    _SCHEMA = "paper1.calibration.completed-human-coding-form.v1"


@dataclass(frozen=True, slots=True)
class IndependentCodeSetV2:
    review_bundle_hash: str
    export_hash: str
    judge_evidence_index_hash: str
    judge_evidence_index_locator: str
    human_evidence_index_hash: str
    human_evidence_index_locator: str
    judge_run_completion_hash: str
    judge_run_completion_locator: str
    judge_coder_contract_hash: str
    human_coder_contract_hash: str
    records: tuple[IndependentCode, ...]
    record_hash: str

    _SCHEMA = "paper1.calibration.independent-code-set.v2"
```

`export_human_form` validates the approved human pack and creates a `HumanCodingTemplate` in bundle-derived order with empty label mappings and null timestamps; it cannot accept labels. `CompletedHumanCodingForm.from_payload` enforces the exact fields above, canonical record hash, template/bundle/export/pack/coder bindings, calibration-only metadata, and a tuple of fully hashed `HumanCodingRecord` values. `verify_human_form` accepts only that type, requires template/item/order/coder hashes, exactly covers the bundle-derived human assignments (174 for the real bundle), contains all legal labels and timestamps, and contains no extra fields. `import_human_form(form, *, bundle, human_pack, human_pack_hash)` calls that verifier and converts records into `IndependentCode` plus `HumanEvidenceIndex`, binding source-template and completed-form hashes with no judge provenance. `compose_review_codes` derives expected judge/human counts and pairs from the bundle assignments (797/174 for the real bundle), binds both coder-contract hashes, and writes the only valid v2 set; no generic JSON constructor or caller-supplied cardinality override is exposed. Small integration fixtures use their own internally consistent bundle assignments, so they exercise the same exact-cover rule without weakening production validation.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_review.py -k "human or compose or 971"
git add -- platform/src/agent_ex/calibration/judge_review.py platform/src/agent_ex/calibration/judge_contracts.py platform/tests/test_calibration_judge_review.py
git diff --cached --check
git commit -m "compose complete phase0a1 review codes"
```

### Task 9: Extend review-import with real v2 dereferencing

**Files:**
- Modify: `platform/src/agent_ex/calibration/review.py`
- Modify: `platform/src/agent_ex/calibration/cli.py`
- Test: `platform/tests/test_calibration_review.py`
- Test: `platform/tests/test_calibration_cli.py`

- [ ] **Step 1: Write failing v2 import tests**

```python
def test_v2_import_dereferences_every_external_evidence(v2_review_fixture):
    updated = import_review_code_set_v2(**v2_review_fixture)
    assert len(updated.independent_codes) == 971


@pytest.mark.parametrize("mutation", ["raw", "parse", "completion", "service_index", "stop"])
def test_v2_import_rejects_missing_or_tampered_external_evidence(v2_review_fixture, mutation):
    mutate_external_evidence(v2_review_fixture, mutation)
    with pytest.raises(ValueError, match="hash|evidence|completion|stop"):
        import_review_code_set_v2(**v2_review_fixture)


def test_v2_import_rejects_extra_unindexed_external_evidence(v2_review_fixture):
    add_unindexed_raw_artifact(v2_review_fixture["evidence_root"])
    with pytest.raises(ValueError, match="extra|inventory"):
        import_review_code_set_v2(**v2_review_fixture)


def test_real_judge_rejects_v1_but_legacy_synthetic_v1_still_imports(real_bundle, synthetic_bundle):
    with pytest.raises(ValueError, match="v2"):
        import_review_codes(real_bundle, real_judge_v1_records(real_bundle))
    assert import_review_codes(synthetic_bundle, synthetic_v1_records(synthetic_bundle))
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_review.py platform/tests/test_calibration_cli.py -k "v1 or v2 or dereference"
```

- [ ] **Step 3: Add the strict v2 bridge**

```python
def import_review_code_set_v2(
    bundle: SemanticReviewBundle,
    code_set: IndependentCodeSetV2,
    evidence_root: Path,
) -> SemanticReviewBundle:
    judge_index = load_hashed_record(evidence_root, code_set.judge_evidence_index_locator)
    human_index = load_hashed_record(evidence_root, code_set.human_evidence_index_locator)
    completion = load_hashed_record(evidence_root, code_set.judge_run_completion_locator)
    verified = verify_v2_hash_chain(
        code_set, judge_index, human_index, completion, evidence_root
    )
    return _import_verified_review_codes(bundle, code_set.records, verified=verified)
```

`verify_v2_hash_chain` returns a private `VerifiedV2Evidence` capability containing the bundle hash, code-set hash, exact record hashes, and completion hash only after dereferencing every judge entry and human source record, then completion -> manifest/projection/service index -> unique stop -> port/GPU-idle. `_import_verified_review_codes` is private, requires that capability to match the exact records, and directly constructs the updated `SemanticReviewBundle`; it does not call the public v1 path. Keep public `import_review_codes` unchanged for existing offline/synthetic identities but make it reject the real approved judge coder identity, forcing that identity through v2.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_review.py platform/tests/test_calibration_cli.py
git add -- platform/src/agent_ex/calibration/review.py platform/src/agent_ex/calibration/cli.py platform/tests/test_calibration_review.py platform/tests/test_calibration_cli.py
git diff --cached --check
git commit -m "verify phase0a1 review evidence v2"
```

### Task 10: Expose the narrow CLI and public boundary

**Files:**
- Modify: `platform/src/agent_ex/calibration/cli.py`
- Modify: `platform/src/agent_ex/calibration/__init__.py`
- Test: `platform/tests/test_calibration_cli.py`
- Test: `platform/tests/test_public_api_import_boundary.py`

- [ ] **Step 1: Write failing parser and create-only output tests**

```python
COMMANDS = (
    "review-materialize-judge", "judge-authorization", "judge-preflight", "judge-lock",
    "judge-manifest", "judge-run",
    "judge-resume", "judge-reconcile", "judge-verify", "judge-verify-completion",
    "judge-export-codes", "human-export", "human-import", "human-verify",
    "review-compose-codes",
)


@pytest.mark.parametrize("command", COMMANDS)
def test_cli_registers_judge_command(command):
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    assert command in subparsers.choices


@pytest.mark.parametrize("forbidden", ["--review-bundle", "--human-pack", "--hidden-bindings"])
def test_runner_commands_reject_unblinded_inputs(forbidden):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["judge-run", forbidden, "secret.json"])


def test_runner_view_rejects_symlink_or_path_escape(tmp_path):
    outside = tmp_path / "full-review-bundle.json"
    outside.write_text("{}", encoding="utf-8")
    view = tmp_path / "view"
    view.mkdir()
    (view / "judge-pack.json").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink|runner view"):
        open_runner_view(view)


@pytest.mark.parametrize("extra_name", ["blind-review-import.json", "human-pack.json", "extra.json"])
def test_runner_view_rejects_extra_or_substituted_inventory(tmp_path, valid_runner_view, extra_name):
    (valid_runner_view / extra_name).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="exact inventory|materialization"):
        open_runner_view(valid_runner_view)


def test_runner_view_requires_materialization_hash_match(valid_runner_view):
    replace_with_full_bundle(valid_runner_view / "judge-pack.json")
    with pytest.raises(ValueError, match="pack|materialization|hash"):
        open_runner_view(valid_runner_view)
```

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_cli.py platform/tests/test_public_api_import_boundary.py -k "judge or human or compose"
```

- [ ] **Step 3: Wire commands to typed functions**

```python
judge_handlers = {
    "review-materialize-judge": _review_materialize_judge_command,
    "judge-authorization": _judge_authorization_command,
    "judge-preflight": _judge_preflight_command,
    "judge-lock": _judge_lock_command,
    "judge-manifest": _judge_manifest_command,
    "judge-run": _judge_run_command,
    "judge-resume": _judge_resume_command,
    "judge-reconcile": _judge_reconcile_command,
    "judge-verify": _judge_verify_command,
    "judge-verify-completion": _judge_verify_completion_command,
    "judge-export-codes": _judge_export_codes_command,
    "human-export": _human_export_command,
    "human-import": _human_import_command,
    "human-verify": _human_verify_command,
    "review-compose-codes": _review_compose_codes_command,
}
```

Every command accepts explicit existing input plus affirmative SHA-256, confines paths to the declared archive root, and uses create-only output paths. Runner commands accept only the runner-view root, authorization, manifest, and judge store; they have no full-bundle/human-pack arguments.

- [ ] **Step 4: Run GREEN and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_cli.py platform/tests/test_public_api_import_boundary.py
git add -- platform/src/agent_ex/calibration/cli.py platform/src/agent_ex/calibration/__init__.py platform/tests/test_calibration_cli.py platform/tests/test_public_api_import_boundary.py
git diff --cached --check
git commit -m "expose phase0a1 judge execution commands"
```

### Task 11: Run integration, regression, independent reviews, and build the release bundle

**Files:**
- Create: `platform/tests/test_calibration_judge_integration.py`
- Create: `logs/2026-09-18-phase0a1-blind-judge-execution.md`
- Modify: `progress.md`

- [ ] **Step 1: Add one local 3-item end-to-end integration fixture**

```python
def test_local_judge_human_v2_import_end_to_end(tmp_path, three_item_fixture):
    materialized = materialize_judge_view(**three_item_fixture.materialization)
    projection = run_judge(**three_item_fixture.execution, runner_view=materialized)
    stop = three_item_fixture.record_stop(projection)
    completion = verify_judge_completion(three_item_fixture.store)
    judge_export = export_judge_codes(three_item_fixture.store, completion)
    human_codes, human_index = import_human_form(
        three_item_fixture.completed_human_form,
        bundle=three_item_fixture.bundle,
        human_pack=three_item_fixture.human_pack,
        human_pack_hash=three_item_fixture.human_pack_hash,
    )
    code_set = compose_review_codes(
        judge_codes=judge_export.codes, judge_index=judge_export.index,
        human_codes=human_codes, human_index=human_index,
        review_bundle=three_item_fixture.bundle,
    )
    updated = import_review_code_set_v2(
        three_item_fixture.bundle, code_set, three_item_fixture.evidence_root
    )
    assert len(updated.independent_codes) == 4
    assert stop.loopback_listener_absent is True
```

- [ ] **Step 2: Run focused tests**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests/test_calibration_judge_contracts.py platform/tests/test_calibration_judge_materialize.py platform/tests/test_calibration_judge_adapter.py platform/tests/test_calibration_judge_store.py platform/tests/test_calibration_judge_runner.py platform/tests/test_calibration_judge_review.py platform/tests/test_calibration_judge_integration.py platform/tests/test_calibration_cli.py platform/tests/test_calibration_review.py platform/tests/test_phase0a1_cloud_scripts.py
```

Expected: all focused tests pass; no network or AutoDL is used.

- [ ] **Step 3: Run full release checks**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q platform/tests
& .\.test-venv\Scripts\python.exe -m ruff check platform/src platform/tests platform/scripts
& .\.test-venv\Scripts\python.exe -m ruff format --check platform/src platform/tests platform/scripts
& .\.test-venv\Scripts\python.exe -m pip check
git diff --check
```

Record the exact fresh counts and durations only from completed commands. Preserve the known historical formatting baseline in `platform/tests/test_phase0a1_cloud_scripts.py` if it remains untouched.

- [ ] **Step 4: Perform two-stage independent review**

Dispatch one specification-compliance reviewer and one code-quality reviewer. For every P0-P2 finding, add a failing regression test, make the smallest correction, rerun focused tests, and obtain both approvals before release.

- [ ] **Step 5: Record the checkpoint and build a local bundle**

```powershell
git add -- logs/2026-09-18-phase0a1-blind-judge-execution.md progress.md
git diff --cached --check
git commit -m "record phase0a1 blind judge release"
git bundle create phase0a1-blind-judge-execution.bundle codex/paper1-phase0
git bundle verify phase0a1-blind-judge-execution.bundle
Get-Item -LiteralPath phase0a1-blind-judge-execution.bundle | Select-Object Name,Length
Get-FileHash -Algorithm SHA256 -LiteralPath phase0a1-blind-judge-execution.bundle
```

Stop before upload and before starting AutoDL. Present exact bundle bytes/SHA-256 and all newly materialized authorization hashes for owner approval.

### Task 12: Approved cloud execution and offline human handoff

**External artifacts:**
- Local bundle: `phase0a1-blind-judge-execution.bundle`
- Existing cloud checkout: `/root/autodl-tmp/agent-ex-phase0a1-b5320d8`
- New judge archive: `/root/autodl-tmp/agent-ex-phase0a1-judge-v1`

- [ ] **Step 1:** Obtain explicit owner approval for bundle bytes/SHA-256 and the complete `JudgeAuthorization.record_hash`; no previous approval transfers.
- [ ] **Step 2:** Ask the user to start AutoDL, then read-only verify host/GPU/disk/port, remote HEAD, model artifacts, old environment lock, existing 797/174 export hashes, and absence of the new judge archive.
- [ ] **Step 3:** Upload only the approved bundle, verify remote bytes/SHA-256, fast-forward the clean checkout, and rerun focused cloud-safe tests.
- [ ] **Step 4:** Materialize the byte-equivalent runner view and confirm the approved pack/index hashes. Run static `judge-preflight`, which verifies host/model/runtime expectations and the old approved environment-lock reference without requiring HTTP health.
- [ ] **Step 5:** Start vLLM with `phase0a1-judge-service.sh start`, bound only to the approved authorization hash; capture and validate the judge-specific start identity. With the service live, run `judge-lock` to collect the loopback HTTP-200 health observation and create the fresh environment lock bound to that authorization. Create `JudgeExecutionManifest` from authorization, runner view, static preflight, live fresh lock, and start identity; stop before the first request and obtain explicit owner approval for its complete hash.
- [ ] **Step 6:** Execute exactly 797 items. Monitor at low frequency; resume only after typed reconciliation permits it, never blindly resend an unresolved intent, and never display raw responses.
- [ ] **Step 7:** Verify 797 coded items and exact evidence cover. Stop with `phase0a1-judge-service.sh stop`, verify the judge-specific stop record plus port/GPU idle observation, create `JudgeRunCompletion`, export judge codes/index, then allow AutoDL shutdown.
- [ ] **Step 8:** Export the 174-item human form for offline completion. Do not fill human labels automatically, compose partial records, call `review-import`, adjudicate, or seal.
- [ ] **Step 9:** After the human form is returned, run `human-import`, `human-verify`, `review-compose-codes`, and exactly one v2 `review-import`; proceed to adjudication only if the frozen policy requires it.
- [ ] **Step 10:** Commit only source, tests, logs, hashes, counts, and external archive locators. Never add raw responses, human-identifying form content, model files, environments, or run archives to Git.

Failure branch for Steps 5-7: if `judge-lock`, manifest construction, or manifest approval fails before a final manifest exists, invoke `phase0a1-judge-service.sh abort-pre-manifest`, binding authorization/start and the lock hash when available. If a manifest exists and execution reaches a terminal failure or is manually aborted, invoke `phase0a1-judge-service.sh stop` with that manifest. In both branches append the immutable abort/stop record plus port/GPU-idle observation to the current archive and verify the service is down. Mark the run incomplete; pre-manifest abort evidence must never satisfy completion, and neither branch may export judge codes, compose records, or call `review-import`.

## Self-review record

- Spec coverage: Tasks 1-3 cover full renderer authorization and fresh lifecycle binding; Tasks 4-6 cover loopback transport, state machine, retries, recovery, and resume; Tasks 7-9 cover completion, evidence indexes, human conversion, 971-record composition, and dereferenced v2 import; Tasks 10-12 cover narrow CLI, release gates, cloud execution, and human handoff.
- Placeholder scan: no unresolved implementation marker, invented runtime hash, or deferred validation remains. Runtime hashes are computed from artifacts and approved before use.
- Type consistency: `JudgeAuthorization`, `JudgeExecutionManifest`, `JudgeRunCompletion`, `JudgeEvidenceIndex`, `HumanCodingRecord`, `HumanEvidenceIndex`, and `IndependentCodeSetV2` retain the same names and hash links throughout.
- Boundary check: the runner receives only the approved runner view, authorization, manifest, and its store; full bundle, hidden bindings, human pack, partial import, and formal Paper 1 authority remain outside its interface.
- Compatibility: v1 offline/synthetic review remains supported; the real Phase 0A-1 judge identity is required to use v2 evidence.
