# Paper 1 Phase 0A-1 Cloud Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the independently reviewed Phase 0A calibration contracts to a controlled Linux/vLLM/Qwen3-8B environment, execute an auditable 816-case real-model probe, and produce a proposal-only handoff without granting formal experiment authority.

**Architecture:** Keep real-model access inside `agent_ex.calibration`: a read-only preflight contract precedes a separately authorized smoke manifest; a loopback-only vLLM adapter writes append-only attempt evidence to a staging store; only a fully approved six-group run manifest may execute the 816-case inventory; a terminal run is sealed through the existing bundle/report boundary. The formal event engine, Agent state, network, and `docs/decisions.md` remain inaccessible to the probe path.

**Tech Stack:** Python 3.12, stdlib HTTP/JSON/path/subprocess primitives, existing `agent_ex.calibration` contracts, pytest 9.1.1, Ruff 0.15.20, Linux, Qwen/Qwen3-8B BF16 at immutable revision `b968826d9c46dd6066d109eabc6255188de91218`, candidate vLLM 0.23.0 with CUDA 12.9 wheels.

---

## Non-negotiable execution gates

- Cloud preflight is read-only and makes no model request.
- Smoke requires a separately approved smoke manifest and cannot load the 816-case inventory.
- The 816-case run requires the six approved artifact groups and a bound gate algorithm.
- `top_k` and `min_p` are not sent because they do not yet have stable project decision IDs.
- Any `UNRESOLVED[...]` in an executable artifact makes loading fail.
- Real outputs, secrets, databases, and bundles remain outside Git.
- Phase 0A-1 cannot launch the formal event engine or authorize Phase 0B/scale runs.

### Task 1: Record the approved Phase 0A-1 specification checkpoint

**Files:**
- Add: `docs/superpowers/plans/2026-09-10-paper1-phase0a1-cloud-probe-implementation.md`
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `docs/project-overview.md`
- Reference: `docs/superpowers/specs/2026-09-10-paper1-phase0a1-cloud-probe-design.md`

- [ ] **Step 1: Verify the written specification and branch identity**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse '@{u}'
```

Expected: branch `codex/paper1-phase0`, clean worktree, local and upstream at `672687e` or a descendant containing it.

- [ ] **Step 2: Record the transition without claiming model execution**

Add one dated checkpoint to each project document stating:

```text
Phase 0A-1 design approved and independently reviewed. The read-only cloud preflight is complete,
passwordless SSH passed, and the observed host baseline is RTX 5090 32GB, Ubuntu 22.04,
Python 3.12.3, PyTorch 2.8.0+cu128, with a 150GB data disk.
No real model response, runtime freeze, decision record, or formal experiment exists yet;
Phase 0A-1 remains in progress.
```

- [ ] **Step 3: Check documentation boundaries**

Run:

```powershell
git diff --check
rg -n "Phase 0A-1.*(complete|formal ready)|正式实验.*完成" task_plan.md progress.md docs/project-overview.md
```

Expected: diff check passes; the search returns no new completion overclaim.

- [ ] **Step 4: Commit**

```powershell
git add docs/superpowers/plans/2026-09-10-paper1-phase0a1-cloud-probe-implementation.md task_plan.md progress.md docs/project-overview.md
git commit -m "docs(platform): start Phase 0A cloud probe"
```

### Task 2: Add strict cloud preflight and smoke-manifest contracts

**Files:**
- Create: `platform/src/agent_ex/calibration/cloud.py`
- Modify: `platform/src/agent_ex/calibration/__init__.py`
- Create: `platform/tests/test_calibration_cloud.py`

- [ ] **Step 1: Write failing contract tests**

Create tests that construct only exact-key payloads:

```python
from agent_ex.calibration.cloud import CloudPreflight, SmokeManifest


def test_cloud_preflight_round_trip_is_strict_and_non_authoritative() -> None:
    record = CloudPreflight.create(
        os_release="Ubuntu 22.04",
        kernel="6.8.0",
        python_version="3.12.11",
        gpu_name="NVIDIA GeForce RTX 5090",
        gpu_memory_bytes=34_359_738_368,
        driver_version="595.71.05",
        reported_cuda_version="13.2",
        free_disk_bytes=120_000_000_000,
        git_commit="0" * 40,
        git_dirty=False,
    )
    assert CloudPreflight.from_payload(record.to_payload()) == record
    assert record.formal_parameter_authority is False


def test_smoke_manifest_cannot_reference_probe_inventory() -> None:
    payload = valid_smoke_manifest_payload()
    payload["case_inventory_hash"] = "0" * 64
    with pytest.raises(ValueError, match="exact fields"):
        SmokeManifest.from_payload(payload)


def test_smoke_manifest_binds_only_a_sanitized_credential_boundary_hash() -> None:
    payload = valid_smoke_manifest_payload()
    assert len(payload["credential_boundary_hash"]) == 64
    assert not ({"credential", "token", "api_key", "secret"} & payload.keys())
    payload["credential_boundary_hash"] = "not-a-hash"
    with pytest.raises(ValueError, match="credential_boundary_hash"):
        SmokeManifest.from_payload(payload)
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_cloud.py -q
Set-Location ..
```

Expected: import failure because `calibration.cloud` does not exist.

- [ ] **Step 3: Implement exact contracts**

Implement frozen dataclasses with canonical `record_hash`, exact-key loaders, positive finite numeric checks, 40/64-character lowercase hex checks, and these immutable fields:

```python
@dataclass(frozen=True, slots=True)
class CloudPreflight:
    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    os_release: str
    kernel: str
    python_version: str
    gpu_name: str
    gpu_memory_bytes: int
    driver_version: str
    reported_cuda_version: str
    free_disk_bytes: int
    git_commit: str
    git_dirty: bool
    record_hash: str


@dataclass(frozen=True, slots=True)
class SmokeManifest:
    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    preflight_hash: str
    model_repository: str
    model_revision_candidate: str
    tokenizer_revision_candidate: str
    vllm_version_candidate: str
    endpoint: str
    served_model_name: str
    chat_template_hash: str
    runtime_policy_hash: str
    smoke_prompt_set_hash: str
    credential_boundary_hash: str
    archive_uri: str
    record_hash: str
```

`SmokeManifest` must require `endpoint == "http://127.0.0.1:8000/v1/chat/completions"`, both revisions equal the approved candidate, `vllm_version_candidate == "0.23.0"`, and no case/specification inventory field.
`credential_boundary_hash` is the SHA-256 of a separately approved, sanitized declaration of the secret-injection boundary. The declaration may state the injection mechanism and permitted secret names, but neither it nor the manifest may contain credential values. Exact-key loading rejects credential/token/API-key/secret value fields rather than hashing or logging them.

- [ ] **Step 4: Run GREEN and regressions**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_cloud.py tests/test_calibration_specification.py tests/test_calibration_runner.py -q
& '.\.venv\Scripts\python.exe' -m ruff check src tests
& '.\.venv\Scripts\python.exe' -m ruff format --check src tests
Set-Location ..
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
Set-Location (git rev-parse --show-toplevel)
git add platform/src/agent_ex/calibration/cloud.py platform/src/agent_ex/calibration/__init__.py platform/tests/test_calibration_cloud.py
git commit -m "feat(platform): add cloud probe preflight contracts"
```

### Task 3: Add append-only staging and terminal sealing

**Files:**
- Create: `platform/src/agent_ex/calibration/store.py`
- Modify: `platform/src/agent_ex/calibration/__init__.py`
- Create: `platform/tests/test_calibration_store.py`
- Reference: `platform/src/agent_ex/calibration/bundle.py`

- [ ] **Step 1: Write failing storage tests**

```python
def test_attempt_records_are_create_only_and_budget_survives_reopen(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "run", manifest=manifest_payload())
    store.append_attempt(attempt_payload(index=0))
    with pytest.raises(FileExistsError):
        store.append_attempt(attempt_payload(index=0))
    reopened = ProbeRunStore.open(tmp_path / "run")
    assert reopened.consumed_attempts("case-1") == 1


def test_sealed_store_rejects_all_new_records(tmp_path: Path) -> None:
    store = populated_store(tmp_path / "run")
    store.seal(bundle=valid_bundle())
    with pytest.raises(RuntimeError, match="sealed"):
        store.append_review(valid_review_payload())
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_store.py -q
Set-Location ..
```

Expected: import failure because `ProbeRunStore` does not exist.

- [ ] **Step 3: Implement storage layout and atomic writes**

Use this fixed layout:

```text
run-root/
  staging/manifest.json
  staging/projection.json
  staging/attempts/<attempt-id>.json
  staging/reviews/<review-id>.json
  sealed/manifest.json
  sealed/files/*.json
```

Every record write must use same-directory temporary creation, file `fsync`, atomic replace for the projection only, and directory `fsync`. Attempt/review filenames are content-addressed and create-only. `open()` reconstructs consumed budgets from append-only records and rejects gaps, duplicates, hash drift, a sealed-plus-staging conflict, or a projection claiming records that do not exist.

- [ ] **Step 4: Run GREEN and bundle regressions**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_store.py tests/test_calibration_report.py tests/test_calibration_runner.py -q
Set-Location ..
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
Set-Location (git rev-parse --show-toplevel)
git add platform/src/agent_ex/calibration/store.py platform/src/agent_ex/calibration/__init__.py platform/tests/test_calibration_store.py
git commit -m "feat(platform): persist append-only probe evidence"
```

### Task 4: Implement the loopback-only vLLM probe adapter

**Files:**
- Create: `platform/src/agent_ex/calibration/vllm_adapter.py`
- Modify: `platform/src/agent_ex/calibration/__init__.py`
- Create: `platform/tests/test_calibration_vllm_adapter.py`

- [ ] **Step 1: Write failing adapter tests with a local fake server**

The fake server must bind `127.0.0.1` on an ephemeral port and return deterministic raw bytes. Cover success, timeout, invalid JSON, HTTP 429 with `Retry-After`, HTTP 500, redirects, wrong model identity, missing request ID, and response size limits.

```python
def test_adapter_preserves_raw_success_and_identity(fake_vllm_server) -> None:
    adapter = VllmProbeAdapter(fake_vllm_server.endpoint, expected_model="qwen3-8b-paper1")
    response = adapter.generate(valid_request(), timeout_seconds=3.0)
    assert response.outcome == "response"
    assert response.provider_request_id == "req-test-1"
    assert response.model_identity["revision"] == MODEL_REVISION
    assert response.raw_response == VALID_RAW_RESPONSE


def test_adapter_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="loopback"):
        VllmProbeAdapter("https://example.com/v1/chat/completions", expected_model="x")
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_vllm_adapter.py -q
Set-Location ..
```

Expected: import failure.

- [ ] **Step 3: Implement the adapter without a new runtime dependency**

Use stdlib `http.client.HTTPConnection`; disable redirects; accept only hostname `127.0.0.1`, scheme `http`, exact path `/v1/chat/completions`, and the manifest port. Serialize only the allowed request keys. Do not send `top_k` or `min_p`. Preserve status, headers, and raw bytes before parsing. Map transport results to existing error codes without retrying inside the adapter; the runner owns retry timing and budgets.

- [ ] **Step 4: Run GREEN and existing runner regressions**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_vllm_adapter.py tests/test_calibration_runner.py tests/test_calibration_adapter_parser.py -q
& '.\.venv\Scripts\python.exe' -m ruff check src tests
Set-Location ..
```

Expected: all pass and no external network request.

- [ ] **Step 5: Commit**

```powershell
Set-Location (git rev-parse --show-toplevel)
git add platform/src/agent_ex/calibration/vllm_adapter.py platform/src/agent_ex/calibration/__init__.py platform/tests/test_calibration_vllm_adapter.py
git commit -m "feat(platform): add loopback vLLM probe adapter"
```

### Task 5: Add smoke orchestration and a strict environment lock

**Files:**
- Create: `platform/src/agent_ex/calibration/smoke.py`
- Create: `platform/src/agent_ex/calibration/environment.py`
- Modify: `platform/src/agent_ex/calibration/__init__.py`
- Create: `platform/tests/test_calibration_smoke.py`
- Create: `platform/tests/test_calibration_environment.py`
- Create: `platform/configs/paper1/phase0a1-smoke.draft.yaml`

- [ ] **Step 1: Write failing smoke and environment-lock tests**

```python
def test_smoke_never_loads_probe_case_inventory(tmp_path: Path) -> None:
    result = run_probe_smoke(valid_smoke_manifest(), scripted_smoke_adapter(), tmp_path)
    assert result.case_count == 0
    assert result.smoke_prompt_count == 10


def test_smoke_fails_when_thinking_content_is_observed(tmp_path: Path) -> None:
    adapter = scripted_smoke_adapter(content="<think>hidden</think>{\"stance\":4}")
    with pytest.raises(SmokeFailure, match="non-thinking"):
        run_probe_smoke(valid_smoke_manifest(), adapter, tmp_path)


@pytest.mark.parametrize(
    "changed_field",
    [
        "git_commit", "git_dirty", "os_release", "kernel", "gpu", "driver_version",
        "reported_cuda_version", "python_version", "package_lock", "model_artifacts",
        "tokenizer_artifacts", "chat_template_text", "rendered_non_thinking_hash",
        "vllm_identity", "image_identity", "serve_arguments", "health_check",
    ],
)
def test_environment_lock_rejects_every_observed_drift(changed_field: str) -> None:
    lock, observed = valid_environment_lock_and_observation()
    observed = mutate_observation(observed, changed_field)
    with pytest.raises(EnvironmentDriftError, match=changed_field):
        verify_current_environment(lock, observed)


def test_environment_lock_round_trip_recomputes_nested_hashes() -> None:
    lock, _ = valid_environment_lock_and_observation()
    assert EnvironmentLock.from_payload(lock.to_payload()) == lock
    assert lock.record_hash == canonical_sha256(lock.payload_without_record_hash())
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_smoke.py tests/test_calibration_environment.py -q
Set-Location ..
```

Expected: import failure because the smoke/environment-lock implementations do not exist.

- [ ] **Step 3: Implement the fixed ten-case smoke set**

The ten smoke prompts cover: valid JSON twice, field-order challenge, one intentionally malformed-output instruction, neutral refusal opportunity, short max-token termination, seed replay pair, Unicode Chinese text, service identity, and recovery after a controlled client interruption. The manifest binds their exact UTF-8 payload and hash. Smoke output contains operational observations only and cannot call topic selection or freeze-proposal builders.

Create the draft with exact fail-closed markers:

```yaml
schema_version: paper1.calibration.smoke-manifest.v1
metadata:
  calibration_only: true
  formal_parameter_authority: false
model_revision_candidate: b968826d9c46dd6066d109eabc6255188de91218
tokenizer_revision_candidate: b968826d9c46dd6066d109eabc6255188de91218
vllm_version_candidate: 0.23.0
runtime_policy_hash: UNRESOLVED[P1_TIMEOUT_RETRY]
credential_boundary_hash: REPLACE_WITH_APPROVED_64_HEX_CREDENTIAL_BOUNDARY_HASH
archive_uri: UNRESOLVED[P1_DATA_ARCHIVE_URI]
```

The credential placeholder is operational approval metadata, not a research-parameter value; materialization replaces it only with the SHA-256 of the approved sanitized declaration. It must never be replaced with, or computed from, a credential value.

- [ ] **Step 4: Implement strict environment-lock construction and verification**

Implement frozen, exact-key `EnvironmentLock` and typed nested records. Its canonical payload and `record_hash` must bind all of the following actual observations:

- Git commit, dirty flag, and—only when the separately approved dirty-worktree exception is used—the archived diff hash;
- OS release, kernel, GPU name/memory, driver and reported CUDA version;
- Python version plus the canonical, sorted full package lock and its hash;
- model and tokenizer repositories, exact revisions, and sorted artifact entries containing relative path, byte size and SHA-256;
- chat-template UTF-8 source text and recomputed hash, plus the rendered non-thinking smoke hash;
- vLLM version/wheel hash, immutable image repository/digest, canonical ordered serve arguments, and the loopback health-check evidence/hash.

`EnvironmentLock.create()` accepts only typed inspection results, canonicalizes unordered package/artifact collections, recomputes every nested hash, and rejects symlinks, duplicate paths/packages, moving revisions, non-loopback health evidence, secrets, and invalid hashes. `EnvironmentLock.from_payload()` enforces exact keys and recomputes all nested and top-level hashes. `verify_current_environment()` takes a fresh observation produced by the same versioned inspection algorithm and requires exact equality for every bound field; any drift invalidates the old lock and forbids starting or resuming its run.

- [ ] **Step 5: Run GREEN and guard tests**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_smoke.py tests/test_calibration_environment.py tests/test_calibration_cloud.py tests/test_calibration_report.py -q
Set-Location ..
```

Expected: all pass; draft remains unrunnable.

- [ ] **Step 6: Commit**

```powershell
Set-Location (git rev-parse --show-toplevel)
git add platform/src/agent_ex/calibration/smoke.py platform/src/agent_ex/calibration/environment.py platform/src/agent_ex/calibration/__init__.py platform/tests/test_calibration_smoke.py platform/tests/test_calibration_environment.py platform/configs/paper1/phase0a1-smoke.draft.yaml
git commit -m "feat(platform): add controlled model smoke gate"
```

### Task 6: Build the approved run-artifact loader and real execution facade

**Files:**
- Create: `platform/src/agent_ex/calibration/cloud_run.py`
- Modify: `platform/src/agent_ex/calibration/__init__.py`
- Create: `platform/tests/test_calibration_cloud_run.py`
- Modify: `platform/configs/paper1/phase0a-probe.draft.yaml`

- [ ] **Step 1: Write failing six-group authorization tests**

```python
def test_cloud_run_requires_all_six_bound_artifact_groups() -> None:
    payload = approved_run_artifacts_payload()
    del payload["semantic_review_policy"]
    with pytest.raises(ValueError, match="six artifact groups"):
        load_cloud_run_artifacts(payload)


def test_cloud_run_rejects_any_unresolved_marker() -> None:
    payload = approved_run_artifacts_payload()
    payload["runtime_policy"]["timeout_seconds"] = "UNRESOLVED[P1_TIMEOUT_RETRY]"
    with pytest.raises(ValueError, match="UNRESOLVED"):
        load_cloud_run_artifacts(payload)


def test_run_manifest_requires_environment_lock_after_six_group_approval() -> None:
    groups = approved_run_artifacts_payload()
    with pytest.raises(ValueError, match="environment lock"):
        build_cloud_run_manifest(groups, environment_lock=None)


def test_resume_rejects_environment_lock_drift() -> None:
    manifest, observed = valid_manifest_and_current_observation()
    observed = mutate_observation(observed, "chat_template_text")
    with pytest.raises(EnvironmentDriftError, match="chat_template_text"):
        resume_cloud_probe(manifest=manifest, current_environment=observed)


def test_terminal_incomplete_store_builds_audit_report_without_candidate() -> None:
    store = reopened_terminal_incomplete_store()
    report = build_cloud_probe_report(store)
    assert report.status == "incomplete"
    assert report.selected_candidate is None


def test_recoverable_staging_store_cannot_build_or_seal_report() -> None:
    store = reopened_recoverable_staging_store()
    with pytest.raises(RuntimeError, match="recoverable staging"):
        build_cloud_probe_report(store)


def test_cloud_facade_cannot_accept_formal_engine_types() -> None:
    with pytest.raises(TypeError):
        execute_cloud_probe(run_artifacts=valid_artifacts(), adapter=mock_event_adapter())
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_cloud_run.py -q
Set-Location ..
```

Expected: import failure.

- [ ] **Step 3: Implement the facade**

First load and approve exactly six artifact groups: probe specification including `gate_algorithm`, runtime policy, semantic-review policy, model/tokenizer/runtime/generation candidate manifest, sanitized credential-boundary declaration, and archive declaration. Recompute every nested hash. Require 816 cases with family counts 144/96/576, `calibration_only=true`, `formal_parameter_authority=false`, `research_parameter_status=not_frozen`, and no forbidden formal/network-outcome fields.

Enforce this construction order: approved six-group packet -> fresh `EnvironmentLock` from the actual host -> immutable cloud run manifest. The run manifest binds all six group hashes, the `environment_lock_hash`, case inventory hash/counts, and the versioned environment-inspection algorithm. It cannot be constructed from a pre-approval lock. Before every `run` or `resume`, take a fresh observation and call `verify_current_environment()`; any lock drift makes the old manifest unusable and requires a new approval/lock/run identity.

`execute_cloud_probe()` and `resume_cloud_probe()` delegate to the existing runner and persist each returned attempt before advancing. A reopened store may produce and seal a report only after reaching an explicit terminal state: terminal complete produces the normal candidate gate, while irreversible policy/budget exhaustion produces terminal incomplete with no candidate decision but a sealable audit report. A crash/interruption remains recoverable staging and must not build or seal a terminal report. Adapter-return failures must persist the last valid recoverable projection through `ProbeRunCrash` unless the frozen policy classifies the failure as irreversible terminal incomplete.

- [ ] **Step 4: Run GREEN and integration regressions**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_cloud_run.py tests/test_calibration_runner.py tests/test_calibration_gates.py tests/test_calibration_review.py tests/test_calibration_report.py -q
Set-Location ..
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
Set-Location (git rev-parse --show-toplevel)
git add platform/src/agent_ex/calibration/cloud_run.py platform/src/agent_ex/calibration/__init__.py platform/tests/test_calibration_cloud_run.py platform/configs/paper1/phase0a-probe.draft.yaml
git commit -m "feat(platform): authorize controlled cloud probe runs"
```

### Task 7: Add a safe command-line entrypoint and deployment scripts

**Files:**
- Create: `platform/src/agent_ex/calibration/cli.py`
- Modify: `platform/pyproject.toml`
- Create: `platform/scripts/phase0a1-preflight.sh`
- Create: `platform/scripts/phase0a1-serve.sh`
- Create: `platform/tests/test_calibration_cli.py`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_preflight_command_has_no_network_or_install_side_effect(monkeypatch, tmp_path: Path) -> None:
    completed = run_cli(["preflight", "--output", str(tmp_path / "preflight.json")])
    assert completed == 0
    assert not any(call.name in {"pip", "uv", "curl", "wget"} for call in recorded_commands())


def test_run_requires_explicit_manifest_and_archive_root() -> None:
    with pytest.raises(SystemExit):
        run_cli(["run"])


def test_lock_requires_approved_six_group_packet_and_fresh_observation() -> None:
    with pytest.raises(SystemExit):
        run_cli(["lock"])


def test_manifest_requires_verified_environment_lock() -> None:
    with pytest.raises(SystemExit):
        run_cli(["manifest", "--approved-artifacts", "approved.json"])
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_cli.py -q
Set-Location ..
```

Expected: CLI import failure.

- [ ] **Step 3: Implement explicit subcommands**

Expose only `preflight`, `smoke`, `lock`, `manifest`, `run`, `resume`, `review-export`, `review-import`, `seal`, and `verify`. `preflight` calls no package manager or network utility. `lock` requires the exact approved six-group packet and its affirmative hash, obtains a fresh current-host observation, verifies it against the approved model/runtime/generation candidate group, and writes an immutable `EnvironmentLock`. `manifest` requires that same approved packet plus the freshly verified lock and writes the immutable cloud run manifest binding both. Neither command may contact the model or read credential values. Every evidence-producing command requires an absolute archive root, exact approved input paths and affirmative hashes appropriate to that stage. Reject symlinks, paths outside the archive root, dirty Git state unless its diff is separately archived, and all endpoints except the manifest loopback endpoint.

Register:

```toml
[project.scripts]
agent-ex-phase0a1 = "agent_ex.calibration.cli:main"
```

`phase0a1-serve.sh` must use the exact approved vLLM command from `docs/allowed-apis-v1.md`; it reads paths from positional arguments, binds `127.0.0.1`, and never embeds a credential.

- [ ] **Step 4: Run GREEN and shell syntax checks**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_cli.py tests/test_calibration_cloud_run.py -q
& '.\.venv\Scripts\python.exe' -m ruff check src tests
Set-Location ..
```

On Linux:

```bash
cd "$(git rev-parse --show-toplevel)"
bash -n platform/scripts/phase0a1-preflight.sh
bash -n platform/scripts/phase0a1-serve.sh
```

Expected: all checks pass.

- [ ] **Step 5: Commit**

```powershell
Set-Location (git rev-parse --show-toplevel)
git add platform/pyproject.toml platform/src/agent_ex/calibration/cli.py platform/scripts/phase0a1-preflight.sh platform/scripts/phase0a1-serve.sh platform/tests/test_calibration_cli.py
git commit -m "feat(platform): add Phase 0A cloud commands"
```

### Task 8: Run local release verification before cloud transfer

**Files:**
- Modify: `progress.md`
- Create: `logs/2026-09-10-phase0a1-local-release.md`

- [ ] **Step 1: Run focused tests**

```powershell
Set-Location (git rev-parse --show-toplevel)
$phase0a1Baseline = '672687e765320238bdbeb362b13e66cc43e9bd36'
git merge-base --is-ancestor $phase0a1Baseline HEAD
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest tests/test_calibration_cloud.py tests/test_calibration_store.py tests/test_calibration_vllm_adapter.py tests/test_calibration_smoke.py tests/test_calibration_cloud_run.py tests/test_calibration_cli.py -q
Set-Location ..
```

Expected: all pass with no skip/xfail.
Record `672687e765320238bdbeb362b13e66cc43e9bd36` as the Phase 0A-1 comparison baseline in the release log after the ancestor check passes.

- [ ] **Step 2: Run full and coverage suites once**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m pytest --cov=agent_ex --cov-report=term-missing -q
Set-Location ..
```

Expected: no failure; record exact pass/skip/deselection and coverage counts rather than copying old counts.

- [ ] **Step 3: Run static and hygiene gates**

```powershell
Set-Location (git rev-parse --show-toplevel)
Set-Location platform
& '.\.venv\Scripts\python.exe' -m ruff check src tests
& '.\.venv\Scripts\python.exe' -m ruff format --check src tests
& '.\.venv\Scripts\python.exe' -m pip check
Set-Location ..
$phase0a1Baseline = '672687e765320238bdbeb362b13e66cc43e9bd36'
git diff --check $phase0a1Baseline HEAD
git diff --check
git ls-files | rg "(^|/)(raw|responses|attempts|sealed|staging|\.coverage|.*\.sqlite)($|/)"
rg -n "(api[_-]?key|secret|token)\s*[:=]" platform -g '!platform/tests/**'
```

Expected: quality commands pass; artifact and credential searches return no tracked runtime artifact or credential assignment.

- [ ] **Step 4: Record exact evidence and commit**

```powershell
Set-Location (git rev-parse --show-toplevel)
git add progress.md logs/2026-09-10-phase0a1-local-release.md
git commit -m "test(platform): verify Phase 0A cloud release"
git push
```

### Task 9: Execute cloud preflight and smoke

**Files:**
- Create after execution: `logs/2026-09-10-phase0a1-cloud-preflight.md`
- Do not add cloud raw artifacts to Git.

The Task 1 checkpoint records an earlier manual preliminary observation only. It is not the versioned `CloudPreflight` artifact and grants no smoke or run authority. This task must use the newly implemented `agent-ex-phase0a1 preflight` command to take a fresh current-host observation, validate its exact schema/hash, and write the authoritative sanitized preflight record before the separately approved smoke action. This is evidence formalization under the existing read-only preflight permission, not a second smoke/run authorization.

- [ ] **Step 1: Verify the rented instance without changing it**

Run `agent-ex-phase0a1 preflight` over SSH without changing the host. Record: host identifier, OS/kernel, GPU name and memory, driver/CUDA, free disk, Python availability, network reachability needed for Git/model access, and current process/GPU occupancy. Reopen the emitted record and verify its canonical hash. Do not print environment variables or credential contents.

Expected candidate: one RTX 5090 32GB, Linux, at least 90GB free data storage, and a driver capable of running CUDA 12.9 wheels.

- [ ] **Step 2: Review and approve the smoke manifest**

Materialize the smoke manifest from the preflight evidence. It must remain separate from the 816-case specification and name a temporary smoke archive URI.
Bind `credential_boundary_hash` to the separately approved sanitized credential-boundary declaration, verify the declaration contains no credential value, and keep the declaration/hash distinct from the secret injection channel.

- [ ] **Step 3: Install a fresh locked environment**

Use Python 3.12 and the vLLM 0.23.0 CUDA 12.9 wheel path supported by the official documentation. Do not reuse a preinstalled PyTorch environment. Capture package versions, wheel identities and environment hash after installation.

- [ ] **Step 4: Fetch and verify the immutable model candidate**

Fetch `Qwen/Qwen3-8B` at revision `b968826d9c46dd6066d109eabc6255188de91218`; record resolved revision and artifact hashes. Do not use `main` or another moving alias.

- [ ] **Step 5: Start loopback vLLM and execute smoke**

Start with the exact candidate serve contract, then execute the ten bound smoke prompts. Record non-thinking evidence, JSON behavior, request ID, usage, finish reason, seed observability, error mapping, service restart and archive verification.

- [ ] **Step 6: Stop or freeze candidates**

If any smoke gate fails, stop the service, retain the failed smoke bundle, and revise the candidate in a new manifest. If all pass, prepare the six-group 816-run decision packet; do not start it automatically.

- [ ] **Step 7: Commit the sanitized preflight record**

```powershell
git add logs/2026-09-10-phase0a1-cloud-preflight.md
git commit -m "docs(platform): record Phase 0A cloud preflight"
git push
```

### Task 10: Execute, review, and seal the 816-case probe

**Files:**
- Modify after approval: `docs/research-qa.md`
- Modify only after separate owner/method/runtime approval: `docs/decisions.md`
- Create after execution: `logs/2026-09-10-phase0a1-cloud-probe.md`
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `docs/project-overview.md`

- [ ] **Step 1: Obtain written approval for all six run-artifact groups**

The approval must identify exact hashes for specification/gate algorithm, runtime policy, semantic-review policy, model/tokenizer/runtime/generation candidate manifest, credential boundary and archive declaration. No executable artifact may contain `UNRESOLVED[...]`.

- [ ] **Step 2: Generate and verify the current-host lock, then build the run manifest**

Run `agent-ex-phase0a1 lock` with the approved six-group packet and its exact approved hash. It must collect a fresh observation on the current host, strictly validate every environment field and nested hash against the approved candidate group, and write a new immutable `EnvironmentLock` outside Git. Then run `agent-ex-phase0a1 manifest` with that same approved packet and the verified lock; require it to build an immutable cloud run manifest that binds all six group hashes and `environment_lock_hash`. Reopen and verify both artifacts before any model request. A pre-approval, stale, drifted, or differently hosted lock cannot be reused.

- [ ] **Step 3: Execute or resume the 816-case inventory**

Run through `agent-ex-phase0a1 run`; after interruption use only `resume` with the identical manifest hash. Verify 144 topic-quality, 96 identity and 576 continuity cases. Never reset attempt budgets or merge evidence from another run.

- [ ] **Step 4: Complete semantic review**

Export the blind package, execute the fixed model judge, import the pre-registered human codes, append adjudications for every required disagreement, and verify all item/response hashes. Missing required review makes the report incomplete.

- [ ] **Step 5: Build and independently verify the report**

Build deterministic metrics, semantic gate evidence, topic selection and freeze proposal. Reopen the store in a fresh process, rebuild the report, and require matching report projection and run evidence hashes. Confirm no forbidden network outcome or inferential field exists.

- [ ] **Step 6: Seal and archive**

Seal the terminal bundle, make it read-only, compute the external archive hash and verify from a fresh process. Keep raw artifacts outside Git.

- [ ] **Step 7: Review proposal without automatic freezing**

Present the gate report and freeze proposal to the user/method/runtime reviewers. Only separately approved records may be written to `docs/decisions.md`; a report alone cannot authorize formal config.

- [ ] **Step 8: Run three independent final reviews**

Dispatch specification, code-quality and final-verification reviewers with the exact commit range and fresh evidence. Repair every confirmed P0--P2 with RED/GREEN evidence and repeat the affected review.

- [ ] **Step 9: Record and push the checkpoint**

```powershell
git add docs/research-qa.md docs/decisions.md docs/project-overview.md task_plan.md progress.md logs/2026-09-10-phase0a1-cloud-probe.md
git commit -m "feat(platform): complete Phase 0A cloud probe"
git push
git status --short --branch
```

Expected: clean branch equal to upstream; documents say `Phase 0A-1 complete / independently reviewed` only if all acceptance criteria actually passed. Otherwise record the precise incomplete state and recovery command.

## Post-Phase 0A-1 boundary

Do not launch N=200/500 from this plan. First create and approve a separate Phase 0B specification for real N=20/50/100 gates, close all required mechanism/runtime/statistical decisions, and then approve `P1_SCALE_GATE_DESIGN` before any N=200/500 preliminary run.
