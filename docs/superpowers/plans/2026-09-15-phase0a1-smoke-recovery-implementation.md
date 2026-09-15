# Phase 0A-1 Smoke Recovery Implementation Plan

## Fast-track execution amendment (2026-09-15)

The owner has made time-to-first-formal-experiment the primary objective. Tasks 5–7 are
therefore one continuous local release batch, followed immediately by Task 8 and the already
specified 816/Phase 0B gates. Only evidence needed to block unsafe or scientifically invalid
execution remains on the critical path.

The following are **deferred, not treated as preconditions**: the approximately 80-minute full
historical suite, cosmetic documentation work, removal of unreachable compatibility internals,
nonessential refactors, and duplicate slow checks already covered by a fresh focused gate. Each
changed component still requires its red/green test, lint/format check, a combined focused release
gate, a clean commit, and an exact deployment hash.

The amendment does **not** waive the new clean preflight, exact owner-approved complete
`SmokeManifest.record_hash`, manifest-authorized complete environment lock, 9+stop+restart+1
real smoke boundary, raw append-only evidence, separate authorization for the 816 probes, Phase
0B N=20/50/100 and scale gate, or the frozen N=1000/T=50 formal protocol. Those are the shortest
valid route to a reportable formal result and remain fail-closed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fail-closed, hash-bound ten-request smoke that proves deterministic loopback transport classification and a real vLLM stop/restart recovery boundary without granting authority to the 816-case probe.

**Architecture:** Add a small transport-diagnostics module that owns only controlled loopback endpoints and immutable diagnostic records; keep Qwen requests in `smoke.py`, but replace the one-shot loop with explicit phase-1 (ordinals 1–9), restart-boundary, phase-2 (ordinal 10), and finalize transitions reconstructed from append-only state. Keep installation, downloads, and service lifecycle outside Python smoke functions behind narrow scripts/CLI commands; bind every runtime phase to one owner-approved new `SmokeManifest.record_hash` and one post-health `EnvironmentLock` whose `authorization_hash` is exactly that manifest hash.

**Tech Stack:** Python 3.12, dataclasses, `http.client`, `http.server`, JSON/SHA-256 canonical records, create-only filesystem writes, pytest 9.1.1, Bash with `set -euo pipefail`/`trap`, vLLM 0.23.0 CUDA 12.9 wheels, Git bundles, PowerShell/OpenSSH.

---

## File structure

- Create `platform/src/agent_ex/calibration/transport_diagnostics.py`: define the three diagnostic cases, strict/hash-bound evidence, controlled local endpoints, and a runner that never accepts the vLLM endpoint or a `ProbeRequest`.
- Create `platform/tests/test_calibration_transport_diagnostics.py`: prove closed-port, timeout, HTTP 429/`Retry-After`, one-attempt behavior, append-only persistence, endpoint separation, and zero model-request accounting.
- Modify `platform/src/agent_ex/calibration/store.py`: add public, create-only smoke-state/diagnostic/service-stop append and replay APIs; no caller may use `_load_records` for smoke recovery.
- Modify `platform/tests/test_calibration_store.py`: prove state/diagnostic persistence and immutable replay across close/reopen and simulated projection interruption.
- Modify `platform/src/agent_ex/calibration/smoke.py`: define strict `SmokeProgress` and `ServiceStopEvidence` records plus explicit `run_smoke_diagnostics`, `run_smoke_phase_one`, `mark_smoke_service_stopped`, `run_smoke_phase_two`, and `finalize_probe_smoke` entry points.
- Modify `platform/tests/test_calibration_smoke.py`: replace the in-process pseudo-recovery test with exact 9/stop/reopen/10 behavior, duplicate/skip/reorder rejection, lock checks at every boundary, and exact final counts.
- Modify `platform/src/agent_ex/calibration/environment.py`: separate preliminary package inspection from complete observations and require a strict `SmokeManifest` when creating a smoke `EnvironmentLock`.
- Modify `platform/tests/test_calibration_environment.py`: prove lock timing, exact authorization equality, wrong-hash rejection, and repeated drift verification.
- Modify `platform/src/agent_ex/calibration/cli.py`: expose manifest materialization, diagnostics, phase-1, stop-boundary, phase-2, and finalize as separate create-only commands; do not start/stop services or execute shell.
- Modify `platform/tests/test_calibration_cli.py`: prove exact parser surface, source/preflight/manifest/hash gates, CLI phase isolation, and no model or lifecycle side effects.
- Modify `platform/scripts/phase0a1-serve.sh`: fail before `exec` if any proxy variable is present and retain absolute/no-symlink inputs.
- Create `platform/scripts/phase0a1-download.sh`: provide only the two approved dependency/model download operations inside a `source /etc/network_turbo` subshell with cleanup traps.
- Create `platform/scripts/phase0a1-install.sh`: install only from a verified offline wheelhouse into one absent Python 3.12 environment; it never enables network access.
- Create `platform/scripts/phase0a1-service.sh`: start/status/stop only the fixed serve script, with absolute/no-symlink paths, create-only PID/identity evidence, loopback health, and exact process-identity checks.

## Non-negotiable execution gates

- This plan authorizes implementation and focused verification only. It does not authorize installation, download, server startup, any model request, or access to the 816-case inventory.
- The historical manifest hash `9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304` is always rejected by the new smoke path.
- Local code and focused tests must be committed first. Only then may the owner start the host so a new exact-clean deployment can produce a fresh read-only preflight and a new complete `SmokeManifest`.
- Installation, model download, first health, and lock creation occur only after the owner explicitly approves the new manifest's full 64-character `record_hash`; `EnvironmentLock.authorization_hash` must equal that exact value.
- The roughly 80-minute full suite remains deferred at the owner's request. Focused results must never be reported as the full suite.
- A successful smoke prepares an approval packet only. The 816 cases remain a separate later authorization and are never invoked by these commands or scripts.

### Task 1: Add deterministic loopback transport diagnostics

**Files:**
- Create: `platform/src/agent_ex/calibration/transport_diagnostics.py`
- Create: `platform/tests/test_calibration_transport_diagnostics.py`

- [x] **Step 1: Write strict-record and endpoint-isolation red tests**

Create `platform/tests/test_calibration_transport_diagnostics.py` with these public-contract tests first:

```python
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agent_ex.calibration.transport_diagnostics import (
    DiagnosticCase,
    TransportDiagnosticEvidence,
    diagnostic_cases,
    run_transport_diagnostics,
)
from test_calibration_smoke import manifest, runtime_policy


def test_diagnostic_cases_are_fixed_and_never_name_vllm() -> None:
    cases = diagnostic_cases(timeout_seconds=0.05)
    assert tuple(case.diagnostic_id for case in cases) == (
        "closed-port",
        "controlled-timeout",
        "http-429-retry-after",
    )
    assert tuple(case.expected_error_code for case in cases) == (
        "provider_unreachable",
        "timeout",
        "provider_busy",
    )
    assert all(case.endpoint != "http://127.0.0.1:8000/v1/chat/completions" for case in cases)


def test_diagnostic_record_round_trip_rejects_hash_or_classification_drift() -> None:
    case = DiagnosticCase.closed_port(port=65431)
    evidence = TransportDiagnosticEvidence.create(
        case=case,
        actual_error_code="provider_unreachable",
        started_at="2026-09-15T00:00:00Z",
        ended_at="2026-09-15T00:00:00Z",
        duration_seconds=0.0,
        response_headers={},
        raw_body=b"",
        raw_error="ConnectionRefusedError",
    )
    assert TransportDiagnosticEvidence.from_payload(evidence.to_payload()) == evidence
    with pytest.raises(ValueError, match="classification"):
        replace(evidence, actual_error_code="timeout")


def test_diagnostics_classify_once_and_do_not_count_as_model_requests(tmp_path: Path) -> None:
    policy = runtime_policy(timeout_seconds=0.05)
    run_root = tmp_path / "smoke"
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)
    records = run_transport_diagnostics(
        manifest=approved,
        environment_lock=lock,
        current_observation=valid_observation(),
        policy=policy,
        vllm_endpoint="http://127.0.0.1:8000/v1/chat/completions",
    )
    assert tuple(record.actual_error_code for record in records) == (
        "provider_unreachable",
        "timeout",
        "provider_busy",
    )
    assert records[2].response_headers["retry-after"] == "17"
    assert all(record.transport_attempt_count == 1 for record in records)
    assert all(record.model_request_count == 0 for record in records)
```

- [x] **Step 2: Run the new file and verify red**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_transport_diagnostics.py
```

Expected: collection fails because `agent_ex.calibration.transport_diagnostics` does not exist.

- [x] **Step 3: Implement the complete diagnostic API**

Create `platform/src/agent_ex/calibration/transport_diagnostics.py` with the exact fields and signatures below. This is an interface map; the behavior immediately after it is mandatory.

```text
@dataclass(frozen=True, slots=True)
class DiagnosticCase:
    diagnostic_id: str
    endpoint: str
    expected_error_code: str
    timeout_seconds: float
    retry_after_header: str | None

    @classmethod
    def closed_port(cls, *, port: int) -> DiagnosticCase

    @classmethod
    def controlled_timeout(cls, *, port: int, timeout_seconds: float) -> DiagnosticCase

    @classmethod
    def http_429(cls, *, port: int, retry_after_header: str) -> DiagnosticCase


@dataclass(frozen=True, slots=True)
class TransportDiagnosticEvidence:
    schema_version: str
    diagnostic_id: str
    endpoint: str
    endpoint_identity_hash: str
    input_hash: str
    expected_error_code: str
    actual_error_code: str
    transport_attempt_count: int
    started_at: str
    ended_at: str
    duration_seconds: float
    http_status: int | None
    response_headers: Mapping[str, str]
    raw_body_base64: str
    raw_body_sha256: str
    raw_error: str | None
    model_request_count: int
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    @classmethod
    def create(
        cls, *, case: DiagnosticCase, actual_error_code: str, started_at: str,
        ended_at: str, duration_seconds: float, response_headers: Mapping[str, str],
        raw_body: bytes, raw_error: str | None, http_status: int | None = None,
    ) -> TransportDiagnosticEvidence

    def content_payload(self) -> dict[str, object]
    def to_payload(self) -> dict[str, object]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> TransportDiagnosticEvidence


def diagnostic_cases(*, timeout_seconds: float) -> tuple[DiagnosticCase, ...]


def run_transport_diagnostics(
    *, manifest: SmokeManifest, environment_lock: EnvironmentLock,
    current_observation: EnvironmentObservation, policy: ProbeRuntimePolicy,
    vllm_endpoint: str,
) -> tuple[TransportDiagnosticEvidence, ...]
```

Implement the mapped interface as follows: reserve each port by binding `127.0.0.1:0`; release and verify the closed-port candidate is not listening immediately before its one connection; run the timeout and 429 endpoints with `ThreadingHTTPServer` context managers whose handlers never import or call `VllmProbeAdapter`; use `HTTPConnection` directly; set the controlled delay to `policy.timeout_seconds + 0.05`; return `Retry-After: 17`; always shut down and join endpoint threads in `finally`. `TransportDiagnosticEvidence.__post_init__` must enforce exact schema `paper1.calibration.transport-diagnostic.v1`, exact expected/actual equality, one attempt, zero model requests, loopback-only endpoint, endpoint not equal to port 8000 `/v1/chat/completions`, lowercase string headers, byte/hash agreement, exact keys, calibration-only metadata, and canonical `record_hash`. `run_transport_diagnostics` is the low-level classifier only: it must require strict manifest/lock/observation types, call `verify_current_environment` before and after every diagnostic, assert `environment_lock.authorization_hash == manifest.record_hash`, require the three smoke policy codes, `obey_retry_after is False`, empty backoff, and per-code budget 1. It returns exactly three immutable records but does not know a store. Task 2 adds create-only storage, and Task 3's `run_smoke_diagnostics` rejects pre-existing/partial diagnostics, appends each returned record, reopens all three, and owns the surrounding `ready -> diagnostics_complete` transitions so a crash can never make partial diagnostics look complete.

- [x] **Step 4: Run diagnostic tests green**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_transport_diagnostics.py tests/test_calibration_vllm_adapter.py
```

Expected: all selected tests pass; the controlled timeout takes only the test policy's 0.05 seconds, not 120 seconds.

- [x] **Step 5: Commit the diagnostic unit**

```powershell
git add platform/src/agent_ex/calibration/transport_diagnostics.py platform/tests/test_calibration_transport_diagnostics.py
git commit -m "feat(platform): add deterministic smoke diagnostics"
```

### Task 2: Add strict smoke records and append-only diagnostic replay

**Files:**
- Modify: `platform/src/agent_ex/calibration/smoke.py`
- Modify: `platform/tests/test_calibration_smoke.py`
- Modify: `platform/src/agent_ex/calibration/store.py`
- Modify: `platform/tests/test_calibration_store.py`

**Public-replay amendment (2026-09-15):** Task 2's no-private-recovery rule also requires a
public `ProbeRunStore.load_attempt_records()` projection-ordered replay API. Add and test that
API in this task before the phase runners use it; smoke recovery must never call `_load_records`.
- Modify: `platform/src/agent_ex/calibration/store.py`
- Modify: `platform/tests/test_calibration_store.py`

**Dependency-order amendment (2026-09-15):** Before Step 1 below, add red tests and then
implement only the strict, exact-key, canonical-hash `SmokeProgress` and
`ServiceStopEvidence` record classes mapped in Task 3 Step 3. This moves those two data
contracts earlier because the store must import and validate them; it does not move any phase
runner or shell/service lifecycle behavior. Commit the contracts with the recovery storage at
the end of this task. Task 3 must reuse, not recreate, the two records.

- [x] **Step 1: Write crash/reopen and immutability red tests**

Append these tests to `platform/tests/test_calibration_store.py`:

```python
def test_smoke_progress_and_diagnostics_survive_reopen(tmp_path: Path) -> None:
    root = tmp_path / "smoke"
    store = ProbeRunStore.create(root, manifest=valid_manifest())
    progress = valid_smoke_progress(sequence=1, phase="ready", completed_ordinals=())
    diagnostic = valid_transport_diagnostic()
    store.append_smoke_progress(progress.to_payload())
    store.append_transport_diagnostic(diagnostic.to_payload())
    del store

    reopened = ProbeRunStore.open(root)
    assert reopened.load_smoke_progress() == (progress,)
    assert reopened.load_transport_diagnostics() == (diagnostic,)


def test_smoke_progress_is_create_only_and_strictly_contiguous(tmp_path: Path) -> None:
    store = ProbeRunStore.create(tmp_path / "smoke", manifest=valid_manifest())
    ready = valid_smoke_progress(sequence=1, phase="ready", completed_ordinals=())
    store.append_smoke_progress(ready.to_payload())
    with pytest.raises(FileExistsError):
        store.append_smoke_progress(ready.to_payload())
    with pytest.raises(ValueError, match="sequence"):
        store.append_smoke_progress(
            valid_smoke_progress(sequence=3, phase="phase_one_complete", completed_ordinals=tuple(range(1, 10))).to_payload()
        )
```

- [x] **Step 2: Run both tests and verify red**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_store.py -k "smoke_progress or diagnostics_survive"
```

Expected: failures report missing smoke-state and diagnostic store methods.

- [x] **Step 3: Add dedicated store directories and public replay methods**

Extend `ProbeRunStore.create` to create `staging/smoke-progress`, `staging/transport-diagnostics`, and `staging/service-stops` before writing the projection. Extend open/seal equivalence checks to include all three directories. Add the progress/diagnostic methods below and parallel `append_service_stop`/`load_service_stops` methods that validate `ServiceStopEvidence`, reject duplicate `record_hash` or `service_start_identity_hash`, and preserve create-only order:

```python
def append_smoke_progress(self, payload: Mapping[str, object]) -> None:
    from .smoke import SmokeProgress

    with self._lock:
        staging = self._require_staging()
        record = SmokeProgress.from_payload(payload)
        existing = self.load_smoke_progress()
        if record.sequence != len(existing) + 1:
            raise ValueError("smoke progress sequence must be contiguous")
        _write_create_only(
            staging / "smoke-progress" / f"{record.record_hash}.json",
            record.to_payload(),
        )


def load_smoke_progress(self) -> tuple[SmokeProgress, ...]:
    from .smoke import SmokeProgress

    records = self._load_records(
        self.root / ("sealed/evidence" if self._sealed else "staging") / "smoke-progress",
        "smoke progress",
    )
    ordered = tuple(sorted((SmokeProgress.from_payload(item) for item in records.values()), key=lambda item: item.sequence))
    if tuple(item.sequence for item in ordered) != tuple(range(1, len(ordered) + 1)):
        raise ValueError("smoke progress sequence must be contiguous")
    return ordered


def append_transport_diagnostic(self, payload: Mapping[str, object]) -> None:
    from .transport_diagnostics import TransportDiagnosticEvidence

    with self._lock:
        staging = self._require_staging()
        record = TransportDiagnosticEvidence.from_payload(payload)
        existing = self.load_transport_diagnostics()
        if any(item.diagnostic_id == record.diagnostic_id for item in existing):
            raise ValueError("transport diagnostic already complete")
        _write_create_only(
            staging / "transport-diagnostics" / f"{record.record_hash}.json",
            record.to_payload(),
        )


def load_transport_diagnostics(self) -> tuple[TransportDiagnosticEvidence, ...]:
    from .transport_diagnostics import TransportDiagnosticEvidence

    records = self._load_records(
        self.root / ("sealed/evidence" if self._sealed else "staging") / "transport-diagnostics",
        "transport diagnostic",
    )
    by_id = {item.diagnostic_id: item for item in (TransportDiagnosticEvidence.from_payload(value) for value in records.values())}
    order = ("closed-port", "controlled-timeout", "http-429-retry-after")
    return tuple(by_id[item] for item in order if item in by_id)
```

Do not add any of these three record families to `attempt_hashes`; they remain separately inventoried and copied create-only into sealed evidence.

- [x] **Step 4: Run store and diagnostic recovery tests green**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_store.py tests/test_calibration_transport_diagnostics.py
```

Expected: all selected tests pass, including reopen after the original object is discarded.

- [x] **Step 5: Commit append-only recovery storage**

```powershell
git add platform/src/agent_ex/calibration/store.py platform/tests/test_calibration_store.py
git commit -m "feat(platform): persist recoverable smoke progress"
```

### Task 3: Replace the one-shot smoke loop with an explicit two-phase state machine

**Files:**
- Modify: `platform/src/agent_ex/calibration/smoke.py`
- Modify: `platform/tests/test_calibration_smoke.py`

- [x] **Step 1: Write exact phase and fail-closed red tests**

Replace calls to the one-shot `run_probe_smoke` in `platform/tests/test_calibration_smoke.py` with tests that use these signatures:

```python
def test_smoke_runs_exactly_nine_then_only_recovery_prompt_after_reopen(tmp_path: Path) -> None:
    run_root = tmp_path / "smoke"
    policy = runtime_policy()
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)
    diagnostic_progress = run_smoke_diagnostics(
        approved,
        lock,
        run_root,
        policy,
        current_observation=valid_observation(),
    )
    assert diagnostic_progress.phase == "diagnostics_complete"
    first_server = FakeVllmServer(port=8000)
    try:
        first = run_smoke_phase_one(approved, lock, vllm_adapter(first_server.endpoint), run_root, policy, current_observation=valid_observation())
        assert len(first_server.requests) == 9
        assert first.phase == "phase_one_complete"
        stop_evidence = valid_service_stop_evidence(approved, lock)
        stopped = mark_smoke_service_stopped(approved, lock, run_root, stop_evidence=stop_evidence)
        assert stopped.phase == "service_stopped"
    finally:
        first_server.close()

    second_server = FakeVllmServer(port=8000)
    try:
        second = run_smoke_phase_two(approved, lock, vllm_adapter(second_server.endpoint), run_root, policy, current_observation=valid_observation())
        assert len(second_server.requests) == 1
        assert second_server.requests[0]["body"]["messages"][1]["content"].startswith("After the client recovery boundary")
        result = finalize_probe_smoke(approved, lock, run_root, current_observation=valid_observation())
    finally:
        second_server.close()
    assert result.smoke_prompt_count == 10
    assert len(result.attempt_hashes) == 10


@pytest.mark.parametrize("operation", ["phase_two_before_stop", "phase_one_twice", "stop_before_nine", "finalize_before_ten"])
def test_smoke_rejects_duplicate_skip_or_early_finalize(tmp_path: Path, operation: str) -> None:
    run_root = tmp_path / operation
    policy = runtime_policy()
    approved = manifest(run_root, policy_hash=policy.record_hash)
    lock = environment_lock_for_smoke(approved)
    with pytest.raises((RuntimeError, ValueError), match="phase|ordinal|pending|already"):
        exercise_invalid_transition(operation, approved, lock, run_root, policy)
```

Also add assertions that every transition rejects a lock whose `authorization_hash` differs from `approved.record_hash`, that ordinals 1–9 hashes are byte-for-byte unchanged after phase 2, and that the only pending ID at `service_stopped` is `service-identity-recovery`.

- [x] **Step 2: Run the phase tests and verify red**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_smoke.py
```

Expected: failures report missing explicit phase APIs and the old one-shot behavior sends the tenth request without a real stop boundary.

- [x] **Step 3: Implement the phase APIs using the strict Task 2 records**

Use this exact public interface map in `smoke.py`; `SmokeProgress` and
`ServiceStopEvidence` were implemented first in Task 2, while this task adds the five phase
functions. The transition rules below provide the complete required behavior:

```text
@dataclass(frozen=True, slots=True)
class SmokeProgress:
    schema_version: str
    manifest_hash: str
    environment_lock_hash: str
    sequence: int
    phase: str
    completed_ordinals: tuple[int, ...]
    pending_smoke_ids: tuple[str, ...]
    attempt_hashes: tuple[str, ...]
    service_stop_evidence_hash: str | None
    previous_progress_hash: str | None
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    @classmethod
    def create(
        cls, *, manifest_hash: str, environment_lock_hash: str, sequence: int,
        phase: str, completed_ordinals: tuple[int, ...], pending_smoke_ids: tuple[str, ...],
        attempt_hashes: tuple[str, ...], service_stop_evidence_hash: str | None,
        previous_progress_hash: str | None,
    ) -> SmokeProgress

    def content_payload(self) -> dict[str, object]
    def to_payload(self) -> dict[str, object]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> SmokeProgress


@dataclass(frozen=True, slots=True)
class ServiceStopEvidence:
    schema_version: str
    manifest_hash: str
    environment_lock_hash: str
    service_start_identity_hash: str
    pid: int
    process_exit_observed: bool
    loopback_listener_absent: bool
    stopped_at: str
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    def content_payload(self) -> dict[str, object]
    def to_payload(self) -> dict[str, object]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ServiceStopEvidence


def run_smoke_diagnostics(
    manifest: SmokeManifest, environment_lock: EnvironmentLock, archive_root: Path,
    runtime_policy: ProbeRuntimePolicy, *, current_observation: EnvironmentObservation,
) -> SmokeProgress


def run_smoke_phase_one(
    manifest: SmokeManifest, environment_lock: EnvironmentLock, adapter: VllmProbeAdapter,
    archive_root: Path, runtime_policy: ProbeRuntimePolicy,
    *, current_observation: EnvironmentObservation,
) -> SmokeProgress


def mark_smoke_service_stopped(
    manifest: SmokeManifest, environment_lock: EnvironmentLock, archive_root: Path,
    *, stop_evidence: ServiceStopEvidence,
) -> SmokeProgress


def run_smoke_phase_two(
    manifest: SmokeManifest, environment_lock: EnvironmentLock, adapter: VllmProbeAdapter,
    archive_root: Path, runtime_policy: ProbeRuntimePolicy,
    *, current_observation: EnvironmentObservation,
) -> SmokeProgress


def finalize_probe_smoke(
    manifest: SmokeManifest, environment_lock: EnvironmentLock, archive_root: Path,
    *, current_observation: EnvironmentObservation,
) -> SmokeResult
```

Implement `SmokeProgress.__post_init__` with exact schema `paper1.calibration.smoke-progress.v1`; allowed phases and exact shapes are `ready/()/all ten pending/no stop hash`, `diagnostics_complete/()/all ten pending/no stop hash`, `phase_one_complete/(1..9)/(only recovery pending)/no stop hash`, `service_stopped/(1..9)/(only recovery pending)/one stop hash`, `phase_two_complete/(1..10)/()/the same stop hash`, and `finalized/(1..10)/()/the same stop hash`. Require contiguous sequence, hash chaining, attempt hashes aligned with completed ordinals, and exact manifest/lock hashes. `run_smoke_diagnostics` alone creates the absent store, appends `ready`, executes and reopens the three diagnostics, and appends `diagnostics_complete`; phase 1 requires that terminal progress and cannot create or bypass it. `ServiceStopEvidence` must be exact-key, canonical-hash bound, require both stop booleans true, bind the same manifest and lock, and bind the verified start identity and positive PID produced by the lifecycle script. `mark_smoke_service_stopped` rejects an absent, mismatched, or replayed stop record and persists its hash in the next progress record. Extract the current single-request body into `_execute_smoke_item`; phase 1 iterates `_SMOKE_PROMPTS[:9]`, phase 2 executes only `_SMOKE_PROMPTS[9]`; no function opens subprocesses or invokes shell. Before and after diagnostics, phase 1, phase 2, restart recovery, and finalization call one helper that performs `verify_current_environment(environment_lock, current_observation)` and asserts `environment_lock.authorization_hash == manifest.record_hash`. Reopen `ProbeRunStore` at the start of every public phase, replay progress plus attempts and stop evidence, and reject any mismatch before constructing an adapter call.

- [x] **Step 4: Run smoke, store, adapter, and diagnostic tests green**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_smoke.py tests/test_calibration_store.py tests/test_calibration_vllm_adapter.py tests/test_calibration_transport_diagnostics.py
```

Expected: all selected tests pass; request counts are 9 then 1; no diagnostic appears in `attempt_hashes`.

- [x] **Step 5: Commit the two-phase smoke state machine**

```powershell
git add platform/src/agent_ex/calibration/smoke.py platform/tests/test_calibration_smoke.py
git commit -m "feat(platform): enforce smoke restart recovery"
```

### Task 4: Enforce preliminary inspection and manifest-authorized lock timing

**Files:**
- Modify: `platform/src/agent_ex/calibration/environment.py`
- Modify: `platform/tests/test_calibration_environment.py`

- [x] **Step 1: Write red tests for lock timing and authorization equality**

Append:

```python
def test_preliminary_inspection_cannot_be_promoted_to_environment_lock() -> None:
    preliminary = PreliminaryEnvironmentInspection.create(
        python_version="3.12.3", package_lock=valid_observation().package_lock,
        wheel_entries=(WheelEntry(name="vllm", version="0.23.0", sha256="5" * 64, source="official-cuda-12.9"),),
        torch_source="fresh-vllm-environment",
    )
    with pytest.raises(TypeError, match="complete EnvironmentObservation"):
        EnvironmentLock.create(preliminary, authorization_hash="a" * 64)


def test_smoke_lock_requires_exact_owner_approved_manifest_hash() -> None:
    approved = strict_smoke_manifest()
    observation = valid_observation()
    lock = EnvironmentLock.create_for_smoke(observation, manifest=approved, authorization_hash=approved.record_hash)
    assert lock.authorization_hash == approved.record_hash
    for wrong in (approved.preflight_hash, approved.runtime_policy_hash, approved.smoke_prompt_set_hash, approved.credential_boundary_hash, "9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304"):
        with pytest.raises(ValueError, match="manifest record_hash"):
            EnvironmentLock.create_for_smoke(observation, manifest=approved, authorization_hash=wrong)
```

- [x] **Step 2: Run timing tests and verify red**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_environment.py -k "preliminary or owner_approved_manifest"
```

Expected: collection fails on missing preliminary/wheel records and `create_for_smoke`.

- [x] **Step 3: Implement strict preliminary records and smoke lock constructor**

Add frozen, exact-key, canonical-hash `WheelEntry` and `PreliminaryEnvironmentInspection` records with these signatures:

```text
@dataclass(frozen=True, slots=True)
class WheelEntry:
    name: str
    version: str
    sha256: str
    source: str


@dataclass(frozen=True, slots=True)
class PreliminaryEnvironmentInspection:
    schema_version: str
    python_version: str
    package_lock: tuple[PackageEntry, ...]
    wheel_entries: tuple[WheelEntry, ...]
    torch_source: str
    calibration_only: bool
    formal_parameter_authority: bool
    record_hash: str

    @classmethod
    def create(
        cls, *, python_version: str, package_lock: tuple[PackageEntry, ...],
        wheel_entries: tuple[WheelEntry, ...], torch_source: str,
    ) -> PreliminaryEnvironmentInspection

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PreliminaryEnvironmentInspection
```

Require Python `3.12.x`, exactly one vLLM 0.23.0 wheel whose source is `official-cuda-12.9`, a fresh-environment torch provenance string, canonical sorted packages/wheels, no symlinks/secrets, and schema `paper1.calibration.preliminary-environment-inspection.v1`. Add:

```python
@classmethod
def create_for_smoke(
    cls, observation: EnvironmentObservation, *, manifest: SmokeManifest,
    authorization_hash: str,
) -> EnvironmentLock:
    if not isinstance(manifest, SmokeManifest):
        raise TypeError("smoke lock requires a strict SmokeManifest")
    if authorization_hash != manifest.record_hash:
        raise ValueError("authorization_hash must equal the owner-approved manifest record_hash")
    return cls.create(observation, authorization_hash=authorization_hash)
```

Keep the existing generic `EnvironmentLock.create` for the separately authorized six-group path; smoke CLI code must call only `create_for_smoke`. A complete `EnvironmentObservation` remains impossible until model/tokenizer artifacts, chat template and rendered non-thinking hashes, vLLM/image identity, exact serve arguments, and first HTTP 200 health evidence all exist.

- [x] **Step 4: Run environment and smoke authorization tests green**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_environment.py tests/test_calibration_smoke.py
```

Expected: all selected tests pass and every wrong hash is rejected before smoke progress changes.

- [x] **Step 5: Commit lock-order enforcement**

```powershell
git add platform/src/agent_ex/calibration/environment.py platform/tests/test_calibration_environment.py
git commit -m "feat(platform): bind smoke lock to owner manifest"
```

### Task 5: Add phase-isolated CLI commands and fresh manifest materialization

**Files:**
- Modify: `platform/src/agent_ex/calibration/cli.py`
- Modify: `platform/tests/test_calibration_cli.py`

- [x] **Step 1: Write parser, manifest, and command-isolation red tests**

Add tests asserting the smoke command family is exactly `smoke-manifest`, `smoke-preliminary-inspection`, `smoke-lock`, `smoke-diagnostics`, `smoke-phase-one`, `smoke-mark-stopped`, `smoke-phase-two`, and `smoke-finalize`. Add this manifest gate:

```python
def test_smoke_manifest_materialization_requires_new_clean_preflight(tmp_path: Path) -> None:
    preflight = valid_preflight()
    old = replace(preflight, git_commit="6711a6d767cc1993db1d823d183bb125070c107e", record_hash=rehashed(replace(preflight, git_commit="6711a6d767cc1993db1d823d183bb125070c107e")))
    with pytest.raises(ValueError, match="superseded source"):
        invoke_smoke_manifest(old, tmp_path)
    current = replace(preflight, git_commit=current_clean_commit(), record_hash=rehashed(replace(preflight, git_commit=current_clean_commit())))
    created = invoke_smoke_manifest(current, tmp_path)
    assert created.preflight_hash == current.record_hash
    assert created.record_hash != "9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304"
```

For each phase command, monkeypatch all other phase functions to raise if called and assert only the named function runs. Assert `smoke-manifest` and preflight never call package managers, network, vLLM, store creation, or model adapters.

- [x] **Step 2: Run CLI tests and verify red**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_cli.py -k "smoke or manifest_materialization"
```

Expected: failures show the old single `smoke` command and missing manifest/phase handlers.

- [x] **Step 3: Implement exact CLI boundaries**

Replace the old `smoke` parser/handler with the eight commands named above. Every command takes absolute `--archive-root`, strict hashed input files, and a create-only `--output`. Use these handler signatures:

```text
def _smoke_manifest_command(args: argparse.Namespace) -> int
def _smoke_preliminary_inspection_command(args: argparse.Namespace) -> int
def _smoke_lock_command(args: argparse.Namespace) -> int
def _smoke_diagnostics_command(args: argparse.Namespace) -> int
def _smoke_phase_one_command(args: argparse.Namespace) -> int
def _smoke_mark_stopped_command(args: argparse.Namespace) -> int
def _smoke_phase_two_command(args: argparse.Namespace) -> int
def _smoke_finalize_command(args: argparse.Namespace) -> int
```

`_smoke_manifest_command` must reopen `CloudPreflight.from_payload`, require `git_dirty is False`, independently compare `preflight.git_commit` with the exact clean checkout's current 40-character Git identity, reject source commit `6711a6d767cc1993db1d823d183bb125070c107e`, construct `SmokeManifest` with the approved model/revision/service fields and these invariant hashes: chat template `41d5929bf73796beb66809ac700b2cf3ff81694f933e5c14d52b7fd6963c947d`, runtime policy `e0c72256eb39927f0e76565bb95b7b570c5930c22c40a28267ec872d97af0f13`, prompt set `da354eaeda9d83a018d6022a6e094cf03f4a461cc5576ea0c339fc8555608ea5`, credential boundary `4522015a0a1aaf3d1fc14ad295d88bd4e1bd519bb9abf2f23ff29ade0cd8fffa`; it accepts one explicit new empty archive URI and writes the full canonical manifest create-only. `smoke-preliminary-inspection` runs under the new environment's Python with the exact checkout on `PYTHONPATH`, reads an affirmatively hashed wheel manifest plus local installed-package metadata, proves Python 3.12/vLLM 0.23.0/fresh PyTorch provenance, and writes exactly one `PreliminaryEnvironmentInspection`; it performs no network or model call. `smoke-lock` reopens the owner-approved manifest by its affirmative full hash, binds the affirmative preliminary inspection, collects the complete post-health observation, and calls `EnvironmentLock.create_for_smoke`. Every later command reopens both records, verifies their affirmative hashes and equality, collects a fresh complete observation where the service must be live, and calls exactly one phase function. `smoke-mark-stopped` is the only exception: it requires and strictly reopens the lifecycle script's create-only `ServiceStopEvidence`, passes it to `mark_smoke_service_stopped`, and reads no live health endpoint. No handler imports `subprocess`, calls `os.system`, or starts/stops a service.

- [x] **Step 4: Run focused CLI integration green**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_cli.py tests/test_calibration_cloud.py tests/test_calibration_environment.py tests/test_calibration_smoke.py
```

Expected: all selected tests pass, old manifest/preflight hashes fail closed, and no command crosses its phase boundary.

- [x] **Step 5: Commit the CLI authorization surface**

```powershell
git add platform/src/agent_ex/calibration/cli.py platform/tests/test_calibration_cli.py
git commit -m "feat(platform): expose recoverable smoke phases"
```

### Task 6: Add narrow download and service lifecycle scripts

**Files:**
- Modify: `platform/scripts/phase0a1-serve.sh`
- Create: `platform/scripts/phase0a1-download.sh`
- Create: `platform/scripts/phase0a1-install.sh`
- Create: `platform/scripts/phase0a1-service.sh`
- Create: `platform/tests/test_phase0a1_cloud_scripts.py`

- [x] **Step 1: Write static and controlled-process red tests**

Add platform-neutral static tests that require: `phase0a1-download.sh` contains `source /etc/network_turbo` only inside a child subshell, installs cleanup traps, and exposes only `packages` and `model` modes; `phase0a1-install.sh` has no network-turbo or index URL and accepts only an absent environment plus an affirmatively hashed wheel manifest; `phase0a1-serve.sh` and `phase0a1-service.sh` fail if any proxy variable is set; service inputs and PID/evidence paths must be absolute, existing, non-symlink, and equal to `realpath -e`; stop refuses stale PID or command-line mismatch and emits a strict `ServiceStopEvidence`. These Windows tests inspect exact script tokens/branches and execute the embedded wheel-manifest producer/verifier against disposable files, including tamper rejection; they do not claim Bash syntax or Linux lifecycle execution. The existing preflight wrapper remains untouched and remains forbidden before installation.

- [x] **Step 2: Run script tests and verify red**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_phase0a1_cloud_scripts.py
```

Expected: failures report missing scripts and missing proxy/output assertions.

- [x] **Step 3: Implement the fixed script contracts**

`phase0a1-download.sh` must accept exactly `packages ABSOLUTE_PYTHON ABSOLUTE_WHEELHOUSE` or `model ABSOLUTE_PYTHON ABSOLUTE_MODEL_DIR`, start a child subshell whose EXIT trap clears `http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `all_proxy`, and any additional variable whose name matches `proxy` case-insensitively, install separate HUP/INT/TERM traps that preserve the nonzero signal exit, source `/etc/network_turbo`, and run only the reviewed fixed downloader for that mode. Package mode downloads vLLM `0.23.0` and its resolved CUDA 12.9 wheel set into the absent wheelhouse and writes a sorted SHA-256 wheel manifest create-only; model mode downloads `Qwen/Qwen3-8B` at revision `b968826d9c46dd6066d109eabc6255188de91218` into the absent model directory without a token. Because the accelerated environment exists only in the child process, it cannot mutate the caller; the separate install and service scripts must independently fail if any proxy-named variable is present.

`phase0a1-install.sh` must accept exactly `ABSOLUTE_PYTHON ABSOLUTE_WHEELHOUSE ABSOLUTE_WHEEL_MANIFEST WHEEL_MANIFEST_SHA256 ABSOLUTE_NEW_ENV`. It verifies all paths are absolute/non-symlink, the environment is absent, the manifest's supplied affirmative SHA-256 and every listed wheel hash match, creates the environment with Python 3.12, installs vLLM 0.23.0 and its dependencies only with `--no-index --find-links`, rejects reuse of any base-environment PyTorch path, and runs package identity plus `pip check` verification. It contains no `source /etc/network_turbo`, HTTP client, index URL, or fallback network branch.

`phase0a1-service.sh` must accept only `start-first ABSOLUTE_SERVE_SCRIPT ABSOLUTE_VLLM ABSOLUTE_MODEL ABSOLUTE_EVIDENCE_DIR MANIFEST_HASH PRELIMINARY_INSPECTION_HASH`, `start-recovery ABSOLUTE_SERVE_SCRIPT ABSOLUTE_VLLM ABSOLUTE_MODEL ABSOLUTE_EVIDENCE_DIR MANIFEST_HASH LOCK_HASH`, `status ABSOLUTE_EVIDENCE_DIR`, or `stop ABSOLUTE_EVIDENCE_DIR MANIFEST_HASH LOCK_HASH`; this avoids requiring an EnvironmentLock before the first health observation needed to create it. Serialize lifecycle changes with `flock` on one fixed file, create a new exclusive `service-generations/0001` for `start-first` and `0002` for `start-recovery`, and reject mode/generation mismatches or more than two generations. `status` and `stop` must discover exactly one generation that has start evidence but no stop evidence and fail on zero or multiple active generations; they may not use a mutable PID pointer. Each generation stores create-only PID and identity JSON, hashes the exact `/proc/$pid/cmdline`, requires the listener only on `127.0.0.1:8000`, and polls `/health` without redirects. Generation 1 binds the owner-approved manifest plus preliminary inspection; after first health the CLI creates the immutable lock. `stop` then requires that lock hash, verifies PID, start time, executable, command hash, listener, manifest hash, preliminary evidence where applicable, and lock authorization before sending TERM. It must wait for exit and listener absence, write canonical create-only `ServiceStopEvidence` in that generation containing the verified start identity/PID and manifest/lock hashes, and never use `pkill`, wildcard process selection, or an unverified PID. The first generation's stop evidence is the only record accepted by `smoke-mark-stopped`; the second is terminal service cleanup evidence. `phase0a1-serve.sh` must check the proxy-name set immediately before `exec`.

- [x] **Step 4: Run script syntax and lifecycle tests green**

Run:

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_phase0a1_cloud_scripts.py
```

Expected: all platform-neutral static and embedded manifest tests pass. Do not claim Bash syntax or Linux process-lifecycle verification on this Windows host; Task 8 performs those checks on the exact cloud checkout before any installation or model access.

- [x] **Step 5: Commit lifecycle boundaries**

```powershell
git add platform/scripts/phase0a1-download.sh platform/scripts/phase0a1-install.sh platform/scripts/phase0a1-serve.sh platform/scripts/phase0a1-service.sh platform/tests/test_phase0a1_cloud_scripts.py
git commit -m "feat(platform): constrain smoke host lifecycle"
```

### Task 7: Run focused local release gates and create the exact deployment bundle

**Files:**
- Create: `logs/2026-09-15-phase0a1-smoke-recovery-local-release.md`
- Modify: `docs/superpowers/plans/2026-09-15-phase0a1-smoke-recovery-implementation.md`
- Create outside Git: an exact Git bundle and SHA-256 receipt in the user's external evidence directory.

- [x] **Step 1: Run the complete smoke-recovery focused test set**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m pytest -q tests/test_calibration_transport_diagnostics.py tests/test_calibration_store.py tests/test_calibration_vllm_adapter.py tests/test_calibration_smoke.py tests/test_calibration_environment.py tests/test_calibration_cloud.py tests/test_calibration_cli.py tests/test_phase0a1_cloud_scripts.py tests/test_public_api_import_boundary.py tests/test_installation.py
```

Expected: every selected test passes. Record the exact count and duration; do not label this the full suite.

- [x] **Step 2: Run focused static and package checks**

```powershell
Set-Location platform
& .\.venv\Scripts\python.exe -m ruff check src/agent_ex/calibration tests/test_calibration_transport_diagnostics.py tests/test_calibration_store.py tests/test_calibration_vllm_adapter.py tests/test_calibration_smoke.py tests/test_calibration_environment.py tests/test_calibration_cli.py tests/test_phase0a1_cloud_scripts.py
& .\.venv\Scripts\python.exe -m ruff format --check src/agent_ex/calibration tests/test_calibration_transport_diagnostics.py tests/test_calibration_store.py tests/test_calibration_vllm_adapter.py tests/test_calibration_smoke.py tests/test_calibration_environment.py tests/test_calibration_cli.py tests/test_phase0a1_cloud_scripts.py
& .\.venv\Scripts\python.exe -m pip check
```

Expected: every Windows-available command exits 0. Bash syntax and Linux lifecycle checks are explicitly deferred to Task 8 on the exact cloud checkout because this host has no Bash runtime.

- [x] **Step 3: Explicitly record the deferred full gate**

Do not run `python -m pytest -q` over the full suite. Record: `Full approximately 80-minute suite: DEFERRED by owner request; no pass claim.` The earlier `1726 passed, 2 failed, 2 skipped, 1 deselected` attempt remains historical failed evidence and is not reused as a pass.

- [x] **Step 4: Record focused evidence, verify hygiene, and commit the release checkpoint**

```powershell
Set-Location ..
git diff --check c9ad22a75a97368338946ba69124e76bfe6b88e5 HEAD
git status --short
git ls-files .ssh_local .tmp_autodl_known_hosts
git add logs/2026-09-15-phase0a1-smoke-recovery-local-release.md docs/superpowers/plans/2026-09-15-phase0a1-smoke-recovery-implementation.md
git commit -m "test(platform): verify smoke recovery release"
```

Expected: no whitespace errors or tracked SSH material; Tasks 1–6 already have their own reviewed implementation commits, while this commit contains only the sanitized test record and accurate checklist updates. Capture the new exact 40-character release commit.

- [x] **Step 5: Build and hash an exact clean deployment bundle**

```powershell
git status --porcelain=v1 --untracked-files=all
git bundle create ..\phase0a1-smoke-recovery.bundle codex/paper1-phase0
Get-FileHash ..\phase0a1-smoke-recovery.bundle -Algorithm SHA256
git bundle verify ..\phase0a1-smoke-recovery.bundle
```

Expected: status is empty; bundle verification names the new commit and branch; save the bundle SHA-256 outside Git. Do not connect to the cloud in this task.

### Task 8: Cross the external owner gates and execute only the authorized smoke

**Files:**
- Create outside Git on the cloud host: new read-only preflight, complete new SmokeManifest, preliminary inspection, full EnvironmentLock, progress/diagnostic/request evidence, PID/identity/health records, and final SmokeResult under one new empty smoke archive.
- Create after execution: one sanitized `logs/YYYY-MM-DD-phase0a1-smoke-recovery.md` containing hashes, external locations, exact commit, focused-test statement, and explicit authorization boundaries; never add raw evidence, model files, databases, or bundles to Git.

- [ ] **Step 1: Stop and request the current host endpoint**

Ask the owner to start the AutoDL instance and supply the current endpoint. Do not reuse an earlier hostname/port. This request grants permission only for read-only source/host checks and deployment of the exact bundle, not installation, download, server startup, diagnostics, or model requests.

- [ ] **Step 2: Deploy exact clean source and rerun preflight before installation**

Verify the transferred bundle SHA-256, clone it into a new absolute non-symlink checkout, check exact Task 7 commit and empty `git status --porcelain=v1 --untracked-files=all`, prove `agent_ex` imports from that checkout, and run `bash -n` on the download, install, serve, and service scripts. Then execute the sole permitted pre-install bootstrap directly with the image Python, `PYTHONDONTWRITEBYTECODE=1`, and an absolute `PYTHONPATH=<exact-checkout>/platform/src`: `python -m agent_ex.calibration.cli preflight --output <absent-absolute-external-path>`. Do not use the installed console entry point or `phase0a1-preflight.sh`. Reopen with `CloudPreflight.from_payload`, verify its canonical hash, file SHA-256, exact clean source commit, calibration-only authority, GPU/host observations, and that no install/download/server/model request occurred. Any Bash syntax or source-binding failure stops before manifest materialization.

- [ ] **Step 3: Materialize the new full SmokeManifest and stop for owner approval**

Choose a new absolute empty smoke archive URI that cannot contain old attempts. Run `smoke-manifest` from the exact deployed source, reopen it with `SmokeManifest.from_payload`, and independently verify the full canonical `record_hash`, new `preflight_hash`, all four invariant hashes, pinned model/tokenizer revision, vLLM 0.23.0, loopback endpoint, served name, and archive URI. Explicitly reject old hash `9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304`. Send the owner the complete manifest payload plus its full 64-character `record_hash`, then stop. No install, download, server start, diagnostics, or model request is allowed until the owner approves that exact full hash in writing.

- [ ] **Step 4: After approval, revalidate bindings and perform isolated downloads only**

Reopen the approved manifest with its affirmative full hash; revalidate credential boundary, runtime policy, prompt set, preflight, source/clean status, and archive emptiness. Use `phase0a1-download.sh packages` and `phase0a1-download.sh model` only; verify trap cleanup on success, a controlled failure, and interrupt in a disposable directory. Assert no proxy variable remains before installation or service startup. Use `phase0a1-install.sh` with the affirmatively hashed wheel manifest to build a fresh Python 3.12 environment offline from the vLLM 0.23.0 CUDA 12.9 wheel set without reusing installed PyTorch. Under that new interpreter and the exact checkout `PYTHONPATH`, run `smoke-preliminary-inspection` once, reopen its `PreliminaryEnvironmentInspection`, and verify wheel/package/source hashes. Then verify pinned model/tokenizer files, response source headers, `tokenizer_config.json` SHA-256 `d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101`, `X-Repo-Commit`, `ETag`, template length 4168 bytes, template canonical hash, rendered non-thinking hash, and every artifact hash. Any mismatch stops before service startup.

- [ ] **Step 5: Start the first service, collect first health, then create exactly one lock**

With all proxy assertions clean, start only through `phase0a1-service.sh start-first`, binding the owner-approved manifest and preliminary inspection hashes. Verify PID/command identity, loopback listener, serve arguments, request-ID headers, BF16, length 32768, generation config, non-thinking setting, model/tokenizer/template/vLLM/image identity, packages/source/host, and first health. Only now run `smoke-lock` once. Reopen the lock, prove completeness and immutability, and assert character-for-character `EnvironmentLock.authorization_hash == owner-approved SmokeManifest.record_hash`. Do not create a second lock or update this lock.

- [ ] **Step 6: Run diagnostics and phase 1 under repeated lock verification**

Before and after each diagnostic, freshly observe and verify the same lock plus authorization equality; execute only the three controlled diagnostic endpoints and prove zero Qwen requests. Then reverify and run `smoke-phase-one`; require exactly nine unique first-attempt successes in fixed order, each with immediate intent, raw response, headers, parsing, identity, and hash evidence. On any failure, stop the verified service, preserve evidence, and do not retry a prompt.

- [ ] **Step 7: Close every client/store handle, stop, and prove the persisted boundary**

Run no stop transition until progress says ordinals 1–9 terminal-success and only `service-identity-recovery` pending. Close adapter/client/store processes and file handles, then stop only via verified `phase0a1-service.sh stop`, supplying the approved manifest and immutable lock hashes. Reopen and validate the first generation's strict stop evidence, pass it to `smoke-mark-stopped`, then reopen the archive read-only while the service is absent; prove the first nine records and hashes are unchanged and no tenth request exists.

- [ ] **Step 8: Restart exact service and run only phase 2**

Restart through `phase0a1-service.sh start-recovery` with the same fixed serve contract and the approved manifest/immutable lock hashes. Reobserve every lock-bound field and health evidence, verify the same lock and authorization equality, then open a new store/client and run only `smoke-phase-two`. Require exactly one request for `service-identity-recovery`, ordinal 10, first attempt, while preserving the first nine hashes byte-for-byte. Any identity drift, duplicate, gap, reordered ordinal, or additional pending item stops the service and preserves failure evidence.

- [ ] **Step 9: Finalize, stop, and retain the 816-case approval boundary**

Freshly verify the same lock and authorization equality, run `smoke-finalize`, and require exactly ten unique successful Qwen attempts plus exactly three diagnostic records that are absent from model request counts. Verify the complete archive and hashes, then stop the service regardless of pass/fail. Create only a sanitized Git log and, on success, prepare the six-group 816-case approval packet. Do not load or execute the 816 inventory; its 816 cases remain a separate owner approval even after a passing smoke.

## Completion evidence

- Focused pytest/static/package/script gates: exact commands and observed counts recorded; all pass before deployment.
- Full approximately 80-minute suite: explicitly `DEFERRED by owner request`, never represented as passing.
- Local release: exact clean commit, verified bundle hash, and no tracked credentials/raw evidence.
- External gates: new source-bound preflight, new full `SmokeManifest.record_hash` owner approval, post-first-health complete `EnvironmentLock`, and exact authorization equality at every phase.
- Smoke terminal invariant: 3 diagnostics, 10 unique first-attempt Qwen successes split 9/stop/restart/1, service stopped, evidence retained, 816 execution not authorized.

## Specification coverage self-check

| Approved requirement | Plan owner |
|---|---|
| Closed port, controlled timeout, 429 plus `Retry-After`, one attempt, no Qwen access | Task 1 |
| Create-only/hash-bound diagnostic and progress evidence across process/store/service closure | Tasks 2–3 |
| Exactly 9 requests, verified stop, exact restart, only ordinal 10 after recovery | Tasks 3 and 8 |
| Duplicate, skip, reorder, retry, identity drift, and incomplete evidence fail closed | Tasks 1–3 and 8 |
| Preliminary package evidence before a complete post-health lock | Task 4 |
| `EnvironmentLock.authorization_hash == owner-approved SmokeManifest.record_hash` at construction and every phase | Tasks 3–5 and 8 |
| No arbitrary shell in Python smoke orchestration; absolute/no-symlink PID and identity lifecycle | Tasks 5–6 |
| Download-only network-turbo scope, trap cleanup, and no-proxy service assertion | Tasks 6 and 8 |
| Local focused release first, exact clean bundle, then fresh source-bound read-only preflight and a new full manifest approval | Tasks 7–8 |
| Superseded manifest rejected; no automatic install/download/start/request before external gates | Tasks 5 and 8 |
| Full approximately 80-minute suite honestly deferred | Task 7 |
| Smoke success grants no 816-case, Phase 0B, formal, protocol, schema, state, network, or main-experiment authority | Non-negotiable gates and Task 8 |
