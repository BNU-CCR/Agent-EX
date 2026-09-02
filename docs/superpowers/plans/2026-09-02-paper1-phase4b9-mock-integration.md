---
status: approved implementation plan; independently reviewed with no P0-P2 on 2026-09-02
authority: Phase 4B-9 implementation plan; subordinate to the approved 2026-09-02 design and specification chain
date: 2026-09-02
---

# Paper 1 Phase 4B-9 Mock Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the deterministic mock-only 12-cell integration, N=20/100/1000 recovery and scale gates, process-evidence interfaces, and reproducible Phase 4B handoff without freezing unresolved research parameters or calling a real model.

**Architecture:** Add a pure matrix-contract module, a thin run-level orchestrator that only calls the existing `MockEventPipeline`, and a read-only process-audit module over authoritative v6 storage. Keep all mock execution inputs explicit and versioned; use test helpers to assemble deterministic inputs, never add runtime defaults for B/K/retry/timeout/model seeds/checkpoint cadence. Separate N=1000/T=50 shape validation from one genuine 50,000-event mock execution gate.

**Tech Stack:** Python 3.12, frozen dataclasses, existing `agent_ex` typed contracts, SQLite v6 storage, checkpoint v4 with legacy v3 validation, pytest, pytest-cov, Ruff.

**Approved specification:** `docs/superpowers/specs/2026-09-02-paper1-phase4b9-mock-integration-design.md`, subordinate to the approved 2026-07-29 Phase 4B plan and frozen protocol chain.

**Command working-directory contract:** Every fenced command block runs in a fresh PowerShell process with an explicit tool `workdir`. Blocks containing `.\.venv\Scripts\python.exe` use `<worktree>/platform`; blocks containing `git add`, `git commit`, `git push`, `git status` or `git ls-files` use `<worktree>`. A preceding `cd` never carries into another block. `git diff --check` may run from either explicitly selected directory.

---

## File map

- Create `platform/src/agent_ex/mock_matrix.py`: scale-case, cell-binding, matched-seed matrix and exact cross-cell invariant validation.
- Create `platform/src/agent_ex/mock_run.py`: explicit invocation ledger, thin serial run orchestration and run report.
- Create `platform/src/agent_ex/process_audit.py`: immutable private/public/process snapshots and deterministic comparable projection built only from committed v6 evidence.
- Modify `platform/src/agent_ex/pipeline.py`: expose only a read-only bound `run_id` used to prevent harness/storage cross-wiring.
- Create `platform/tests/helpers/mock_matrix.py`: test-only deterministic builders for typed artifacts, manifests, adapters and explicit per-event invocation ledgers.
- Create `platform/tests/test_mock_matrix.py`: matrix contract and attack tests.
- Create `platform/tests/test_mock_run.py`: run harness, stop/recovery/checkpoint and projection tests.
- Create `platform/tests/test_process_audit.py`: snapshot/process/provenance and tamper tests.
- Create `platform/tests/test_mock_matrix_integration.py`: N=20 recovery and N=100 full 12-cell integration.
- Create `platform/tests/test_mock_scale_release.py`: N=1000/T=50 shape and marked 50,000-event release gate.
- Modify `platform/tests/fixtures/paper1/mock_scale_cases.artifact.json`: explicit v2 scale cases; mock-only/not-frozen values only.
- Modify `platform/tests/test_paper1_mock_fixtures.py`: strict v2 fixture validation.
- Modify `platform/src/agent_ex/__init__.py` and `platform/tests/test_domain.py`: public exports and exact API surface.
- Modify `docs/paper1-protocol.md`, `docs/reproducibility.md`, `docs/project-overview.md`, `task_plan.md`, `progress.md`, `findings.md`: verified Phase 4B boundary and next gates.
- Create `logs/2026-09-02-phase4b-handoff.md`: exact release evidence and desktop/cloud recovery instructions.

## Task 0: Close the Phase 4B-8C-3 release gate

**Files:**
- Review: `logs/2026-09-01-phase4b8c3-evidence-pipeline.md`
- Review: `platform/src/agent_ex/execution_evidence.py`
- Review: `platform/src/agent_ex/pipeline.py`
- Review: `platform/src/agent_ex/storage.py`
- Review: `platform/src/agent_ex/checkpoint.py`
- Review: `platform/tests/test_execution_evidence.py`
- Review: `platform/tests/test_pipeline.py`
- Review: `platform/tests/test_storage.py`
- Review: `platform/tests/test_checkpoint.py`

- [x] **Step 1: Re-dispatch the three failed final reviewers after subagent credits recover**

Require one verification reviewer, one specification/anti-pattern reviewer, and one code-quality reviewer. Give each the exact boundary `7e90fbb..705b9a8` plus the uncommitted evidence log. Require exact P0–P3 findings and no file edits.

- [x] **Step 2: Fix every confirmed P0–P2 with RED/GREEN evidence**

For each confirmed issue, first add one minimal regression that fails against the current implementation, then patch the smallest owning module. Do not change `engine.py` unless the finding proves the lifecycle kernel itself is wrong. Re-run the finding's focused suite and re-dispatch the affected reviewer.

- [x] **Step 3: Run a fresh isolated release verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp="$env:TEMP\phase4b8c3-task9-final"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: the full platform suite passes with only the two documented Windows-condition skips; all static gates pass.

- [x] **Step 4: Update and commit the final 8C-3 evidence log**

Change its status to `complete / independently reviewed`, append the three reviewer results and fresh counts, then run:

```powershell
git add logs/2026-09-01-phase4b8c3-evidence-pipeline.md task_plan.md progress.md findings.md
git commit -m "feat(platform): complete Phase 4B-8C-3 evidence pipeline"
git push origin codex/paper1-phase4b
```

Expected: local HEAD and `@{u}` are identical and the worktree is clean before Task 1 starts.

## Task 1: Versioned mock scale cases

**Files:**
- Modify: `platform/tests/fixtures/paper1/mock_scale_cases.artifact.json`
- Modify: `platform/tests/test_paper1_mock_fixtures.py`
- Create: `platform/src/agent_ex/mock_matrix.py`
- Create: `platform/tests/test_mock_matrix.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [ ] **Step 1: Write strict v2 fixture RED tests**

Add tests asserting exact fields and values:

```python
EXPECTED_CASES = (
    {
        "case_id": "mock-n20-fault-recovery",
        "population_size": 20,
        "stance_counts": [1, 2, 4, 6, 4, 2, 1],
        "integration_sweeps": 2,
        "recovery_sweeps": 2,
        "shape_sweeps": 2,
        "full_matrix_execution": False,
        "release_execution": False,
        "stress_cell_id": None,
        "mock_feed_capacity": 6,
        "mock_memory_window": 3,
        "mock_clock_start": "2040-01-01T00:00:00Z",
        "mock_clock_step_seconds": 1,
    },
    {
        "case_id": "mock-n100-full-matrix",
        "population_size": 100,
        "stance_counts": [5, 10, 20, 30, 20, 10, 5],
        "integration_sweeps": 1,
        "recovery_sweeps": 1,
        "shape_sweeps": 1,
        "full_matrix_execution": True,
        "release_execution": False,
        "stress_cell_id": None,
        "mock_feed_capacity": 6,
        "mock_memory_window": 3,
        "mock_clock_start": "2040-01-01T00:00:00Z",
        "mock_clock_step_seconds": 1,
    },
    {
        "case_id": "mock-n1000-release-shape",
        "population_size": 1000,
        "stance_counts": [50, 100, 200, 300, 200, 100, 50],
        "integration_sweeps": 1,
        "recovery_sweeps": 1,
        "shape_sweeps": 50,
        "full_matrix_execution": False,
        "release_execution": True,
        "stress_cell_id": "P1-I1-C1-E2",
        "mock_feed_capacity": 6,
        "mock_memory_window": 3,
        "mock_clock_start": "2040-01-01T00:00:00Z",
        "mock_clock_step_seconds": 1,
    },
)

def test_scale_fixture_v2_is_explicit_mock_only_and_has_no_runtime_defaults():
    artifact = load_artifact("mock_scale_cases.artifact.json")
    assert artifact.payload["schema_version"] == "paper1.mock-scale-cases.v2"
    assert tuple(artifact.payload["cases"]) == EXPECTED_CASES
    assert artifact.payload["metadata"] == {
        "mock_only": True,
        "research_parameter_status": "not_frozen",
        "formal_parameter_authority": False,
    }
```

Also parameterize missing/extra/bool-for-int/invalid stance counts/invalid UTC clock/duplicate case ID/unknown cell attacks against `MockScaleCase.from_payload`. Update the existing all-fixtures metadata test so the scale artifact alone requires the additional `formal_parameter_authority: false` marker while every other checked mock artifact retains its exact existing metadata; do not weaken the test to a subset assertion.

- [ ] **Step 2: Run the RED tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_paper1_mock_fixtures.py tests\test_mock_matrix.py
```

Expected: FAIL because the fixture is v1 and `agent_ex.mock_matrix` does not exist.

- [ ] **Step 3: Add the immutable scale contract**

Implement the public shape without defaults:

```python
@dataclass(frozen=True, slots=True)
class MockScaleCase:
    case_id: str
    population_size: int
    stance_counts: tuple[int, ...]
    integration_sweeps: int
    recovery_sweeps: int
    shape_sweeps: int
    full_matrix_execution: bool
    release_execution: bool
    stress_cell_id: str | None
    mock_feed_capacity: int
    mock_memory_window: int
    mock_clock_start: str
    mock_clock_step_seconds: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "MockScaleCase":
        expected = {
            "case_id", "population_size", "stance_counts", "integration_sweeps", "recovery_sweeps",
            "shape_sweeps", "full_matrix_execution", "release_execution",
            "stress_cell_id", "mock_feed_capacity", "mock_memory_window",
            "mock_clock_start", "mock_clock_step_seconds",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError("mock scale case fields do not match v2")
        integer_fields = (
            "population_size", "integration_sweeps", "recovery_sweeps",
            "shape_sweeps", "mock_feed_capacity", "mock_memory_window",
            "mock_clock_step_seconds",
        )
        if any(type(payload[name]) is not int or payload[name] < 1 for name in integer_fields):
            raise ValueError("mock scale integer fields must be positive strict integers")
        stance_counts = payload["stance_counts"]
        if (
            type(stance_counts) is not list
            or len(stance_counts) != 7
            or any(type(value) is not int or value < 0 for value in stance_counts)
            or sum(stance_counts) != payload["population_size"]
        ):
            raise ValueError("mock stance counts must be seven strict counts summing to population")
        if type(payload["full_matrix_execution"]) is not bool:
            raise TypeError("full matrix execution flag must be boolean")
        if type(payload["release_execution"]) is not bool:
            raise TypeError("release execution flag must be boolean")
        if payload["stress_cell_id"] is not None and type(payload["stress_cell_id"]) is not str:
            raise TypeError("mock stress cell ID must be text or null")
        if type(payload["mock_clock_start"]) is not str:
            raise TypeError("mock clock start must be an explicit UTC timestamp")
        return cls(**{**payload, "stance_counts": tuple(stance_counts)})

    def to_payload(self) -> dict[str, object]:
        payload = {field.name: getattr(self, field.name) for field in fields(self)}
        payload["stance_counts"] = list(self.stance_counts)
        return payload


def load_mock_scale_cases(artifact: ArtifactEnvelope) -> tuple[MockScaleCase, ...]:
    if artifact.artifact_type != "paper1.mock_scale_cases":
        raise ValueError("scale cases must use the paper1 mock scale artifact type")
    if artifact.algorithm_id != "paper1.mock_fixture":
        raise ValueError("scale cases must use the checked mock fixture algorithm")
    payload = artifact.payload
    if set(payload) != {"schema_version", "cases", "metadata"}:
        raise ValueError("scale case artifact must contain the exact v2 fields")
    if payload["schema_version"] != "paper1.mock-scale-cases.v2":
        raise ValueError("scale case artifact must use schema v2")
    required_metadata = {
        "mock_only": True,
        "research_parameter_status": "not_frozen",
        "formal_parameter_authority": False,
    }
    if dict(payload["metadata"]) != required_metadata:
        raise ValueError("scale cases must remain mock-only and not frozen")
    cases = tuple(MockScaleCase.from_payload(dict(item)) for item in payload["cases"])
    if {case.population_size for case in cases} != {20, 100, 1000}:
        raise ValueError("scale cases must exactly cover N=20/100/1000")
    if len(cases) != 3 or len({case.case_id for case in cases}) != 3:
        raise ValueError("scale cases must have three unique case IDs")
    return cases
```

The loader must require artifact type `paper1.mock_scale_cases`, algorithm `paper1.mock_fixture`, exact v2 fields, `mock_only is True`, `not_frozen`, `formal_parameter_authority is False`, unique case IDs, the exact population set `{20, 100, 1000}`, seven stance counts summing to each population, and a parseable UTC clock start. It must not expose module constants as execution defaults; values only come from the validated artifact. The clock fields are mock evidence controls, not formal cadence or model parameters. Update the existing population/initialization fixture test to consume `population_size` while preserving its exact stance-count assertion.

- [ ] **Step 4: Update the fixture and artifact envelope hash**

Replace the payload with the exact three cases above, set schema v2 metadata, recompute `output_hash` and `artifact_id` using `ArtifactEnvelope`, and keep the file small enough for Git review.

- [ ] **Step 5: Export and verify**

Export `MockScaleCase` and `load_mock_scale_cases` from package root, extend the exact public API test, then run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_paper1_mock_fixtures.py tests\test_mock_matrix.py tests\test_domain.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add platform/tests/fixtures/paper1/mock_scale_cases.artifact.json platform/tests/test_paper1_mock_fixtures.py platform/src/agent_ex/mock_matrix.py platform/tests/test_mock_matrix.py platform/src/agent_ex/__init__.py platform/tests/test_domain.py
git commit -m "feat(platform): define explicit mock scale cases"
```

## Task 2: Canonical matched-seed matrix and invariant audit

**Files:**
- Modify: `platform/src/agent_ex/mock_matrix.py`
- Modify: `platform/tests/test_mock_matrix.py`
- Create: `platform/tests/helpers/mock_matrix.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [ ] **Step 1: Write canonical exact-cover RED tests**

Create one fully typed N=20 artifact family and assert:

```python
matrix = build_mock_matched_seed_matrix(
    scale_case=scale_case,
    matched_seed=101,
    topic_package=topic,
    population_artifact=population,
    initial_stance_artifact=stances,
    initial_reason_artifact=reasons,
    persona_template=persona_template,
    ws_artifact=ws,
    shadow_artifact=shadow,
    agent_node_mapping=mapping,
    structural_gate_artifact=structural_gate,
    attention_artifact=attention,
    expression_artifact=expression,
    activation_artifact=activation,
    publish_artifact=publish,
    schedules_by_cell=schedules,
    manifests_by_cell=manifests,
    adapter_bindings_by_cell=adapter_bindings,
)
assert tuple(binding.cell_id for binding in matrix.cells) == CANONICAL_CELL_IDS
validate_mock_matched_seed_matrix(matrix)
```

Add one attack per invariant: missing/duplicate cell, foreign seed, changed population/stance/reason/mapping/schedule, swapped E1/E2 graph, E0 graph present, persona/exposure mismatch, changed publish flag, changed runtime/script binding and manifest cell drift. Each attack must fail before any SQLite file is created.

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_matrix.py -k "matrix or invariant or attack"
```

Expected: FAIL because matrix types and validator do not exist.

- [ ] **Step 3: Implement typed bindings and validator**

Use immutable types:

```python
@dataclass(frozen=True, slots=True)
class MockCellBinding:
    cell_id: str
    identity_present: bool
    continuity_present: bool
    exposure_mode: str
    exposure_graph_hash: str | None
    artifact_hashes: Mapping[str, str]
    manifest: RunManifest
    adapter_binding: MockAdapterExecutionBinding
    clock_sequence_id: str
    clock_sequence_hash: str


@dataclass(frozen=True, slots=True)
class MockMatchedSeedMatrix:
    schema_version: str
    matched_seed: int
    scale_case: MockScaleCase
    cells: tuple[MockCellBinding, ...]
    matrix_hash: str = field(init=False)
```

Derive the canonical IDs mechanically from `(I0/I1, C0/C1, E0/E1/E2)` in fixed order. Replay all typed artifacts with their existing validators. Compare only approved shared hashes. Validate each manifest and binding against its cell and graph. Return `None` on success; do not return a score or outcomes.
Implement `build_mock_matched_seed_matrix` with the exact keyword arguments used in the RED test and implement `validate_mock_matched_seed_matrix(matrix)` as the only public validator. Neither function accepts a variadic keyword bag or an optional default.

- [ ] **Step 4: Build reusable test-only factories**

In `tests/helpers/mock_matrix.py`, load the five checked-in mock artifacts and expose test-only `build_mock_artifact_family(*, n: int, sweeps: int, matched_seed: int)` and `build_mock_matrix_fixture(tmp_path: Path, *, case_id: str, sweeps: int)`. Build a replayable callable clock from the scale case's explicit start/step, give the sequence a canonical ID/hash, bind those fields into each `MockCellBinding`, and pass the callable only through the existing `MockEventPipeline(..., clock=...)` constructor. Matrix validation rejects missing/drifted clock bindings before storage creation.

Every helper argument is required. Test helpers may derive deterministic mock-only graph/schedule inputs, but must preserve artifact metadata and never be imported by production modules.

- [ ] **Step 5: Run matrix/public suites**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_matrix.py tests\test_paper1_mock_fixtures.py tests\test_domain.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add platform/src/agent_ex/mock_matrix.py platform/tests/test_mock_matrix.py platform/tests/helpers/mock_matrix.py platform/src/agent_ex/__init__.py platform/tests/test_domain.py
git commit -m "feat(platform): audit canonical mock matrices"
```

## Task 3: Thin strict-serial run harness

**Files:**
- Create: `platform/src/agent_ex/mock_run.py`
- Create: `platform/tests/test_mock_run.py`
- Modify: `platform/src/agent_ex/pipeline.py`
- Modify: `platform/tests/helpers/mock_matrix.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [ ] **Step 1: Write no-default and delegation RED tests**

Assert the exact required signature and that every event delegates once to the pipeline:

```python
def test_execute_mock_run_has_no_execution_policy_defaults():
    signature = inspect.signature(execute_mock_run)
    assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())


def test_run_harness_delegates_each_event_and_never_writes_storage_directly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    report = execute_mock_run(
        pipeline=pipeline,
        storage=storage,
        invocations=invocations,
        control=MockRunControl(
            target_event_ordinal=40,
            checkpoint_ordinals=(20, 40),
            checkpoint_paths=(path20, path40),
        ),
    )
    assert pipeline.execute_calls == 40
    assert report.next_event_ordinal == 40
    assert report.checkpoint_hashes.keys() == {20, 40}
```

Add RED tests for invocation gap/duplicate/foreign event, target behind/ahead, mismatched checkpoint arrays, duplicate/unordered checkpoint ordinals, checkpoint ordinal `<= start` or `> target`, duplicate checkpoint paths, non-committed outcome stop, propagated lifecycle failure, no auto-retry, and exact checkpoint write ordinals. Assert `MockEventInvocation` has no timestamp field and that the harness neither accepts nor consumes a clock; all timestamp evidence must come from the constructor-bound pipeline clock or a typed reconciliation result.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_run.py
```

Expected: collection FAIL because `agent_ex.mock_run` does not exist.

- [ ] **Step 3: Implement explicit invocation/control/report types**

```python
@dataclass(frozen=True, slots=True)
class MockEventInvocation:
    event_ordinal: int
    event_id: str
    feed_capacity: int
    memory_window: int
    parser_limits: ParserLimits
    prompt_limits: PromptLimits
    policy: MockAttemptPolicyBinding
    model_identity: Mapping[str, str]
    request_parameters: Mapping[str, object]
    model_seed: int
    adapter: MockAdapter
    reconciliation: AttemptInvocationResult | None
    http_status: int | None
    usage: Mapping[str, object]
    finish_reason: str | None


@dataclass(frozen=True, slots=True)
class MockRunControl:
    target_event_ordinal: int
    checkpoint_ordinals: tuple[int, ...]
    checkpoint_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class MockRunReport:
    run_id: str
    starting_event_ordinal: int
    next_event_ordinal: int
    executed_event_count: int
    completed: bool
    checkpoint_hashes: Mapping[int, str]
    final_checkpoint_hash: str
    final_storage_projection_hash: str


def execute_mock_run(
    pipeline: MockEventPipeline,
    storage: RunStorage,
    invocations: Sequence[MockEventInvocation],
    control: MockRunControl,
) -> MockRunReport:
    if pipeline.run_id != storage.binding.run_id:
        raise ValueError("pipeline and storage must belong to the same run")
    start = storage.progress.next_event_ordinal
    expected = tuple(range(start, control.target_event_ordinal))
    if tuple(item.event_ordinal for item in invocations) != expected:
        raise ValueError("mock invocation ledger must exact-cover the requested prefix")
    if any(
        item.event_id != derive_event_id(storage.binding.run_id, item.event_ordinal)
        for item in invocations
    ):
        raise ValueError("mock invocation event identity drifts from the bound run")
    checkpoint_ordinals = control.checkpoint_ordinals
    checkpoint_paths = control.checkpoint_paths
    if len(checkpoint_ordinals) != len(checkpoint_paths):
        raise ValueError("checkpoint ordinal/path arrays must have equal length")
    if checkpoint_ordinals != tuple(sorted(set(checkpoint_ordinals))):
        raise ValueError("checkpoint ordinals must be unique and strictly increasing")
    if any(
        ordinal <= start or ordinal > control.target_event_ordinal
        for ordinal in checkpoint_ordinals
    ):
        raise ValueError("checkpoint ordinals must lie inside the newly executed prefix")
    if len(set(checkpoint_paths)) != len(checkpoint_paths):
        raise ValueError("checkpoint paths must be unique")
    targets = dict(zip(checkpoint_ordinals, checkpoint_paths, strict=True))
    checkpoint_hashes = {}
    for invocation in invocations:
        outcome = pipeline.execute(
            feed_capacity=invocation.feed_capacity,
            memory_window=invocation.memory_window,
            parser_limits=invocation.parser_limits,
            prompt_limits=invocation.prompt_limits,
            policy=invocation.policy,
            model_identity=invocation.model_identity,
            request_parameters=invocation.request_parameters,
            model_seed=invocation.model_seed,
            adapter=invocation.adapter,
            http_status=invocation.http_status,
            usage=invocation.usage,
            finish_reason=invocation.finish_reason,
            reconciliation=invocation.reconciliation,
        )
        if outcome.lifecycle.state not in {"committed", "complete"}:
            raise RuntimeError("mock run stopped before a successful commit")
        ordinal = storage.progress.next_event_ordinal
        if ordinal in targets:
            checkpoint = build_checkpoint(storage)
            checkpoint_hashes[ordinal] = write_checkpoint_atomic(targets[ordinal], checkpoint)
    final_checkpoint = build_checkpoint(storage)
    if set(checkpoint_hashes) != set(targets):
        raise RuntimeError("mock run did not write the exact requested checkpoint set")
    return MockRunReport(
        run_id=storage.binding.run_id,
        starting_event_ordinal=start,
        next_event_ordinal=storage.progress.next_event_ordinal,
        executed_event_count=len(invocations),
        completed=final_checkpoint.resume_action == "complete",
        checkpoint_hashes=checkpoint_hashes,
        final_checkpoint_hash=final_checkpoint.checkpoint_hash,
        final_storage_projection_hash=canonical_payload_hash(storage.recovery_evidence()),
    )
```

Deep-freeze mappings, reject bool-as-int, and exact-cover ordinals from current storage progress to target. Checkpoint arrays must be one-to-one, unique, strictly increasing and wholly inside `(start, target]`; after the loop the written-key set must equal the requested set exactly. The loop calls only `pipeline.execute`; checkpoint calls use `build_checkpoint`/`write_checkpoint_atomic`. If an outcome is not `committed` or final `complete`, raise without consuming the next invocation.
Add a read-only `MockEventPipeline.run_id` property returning the constructor-bound manifest run ID; it must not expose mutable storage or lifecycle controls.

- [ ] **Step 4: Add deterministic test ledger builder**

In tests only, add `explicit_success_invocations(fixture: MatrixCellFixture, *, start: int, stop: int, feed_capacity: int, memory_window: int) -> tuple[MockEventInvocation, ...]`.

Build one invocation per ordinal with explicit model seed, response script, request parameters and policy. Construct the run-level deterministic clock separately from the versioned scale case and inject it when the pipeline is built. Add call-sequence tests for the exact existing behavior: fresh/retry/pending-resume success consumes started + finished; the corresponding failure additionally consumes failure `recorded_at`; IN_PROGRESS reconciliation/rehydration success replays the persisted started value only and uses the typed/persisted finished value, while failure additionally consumes failure `recorded_at`; landed-success and already-complete consume zero. Close/open recovery must rebuild the state-dependent position—not merely take an unused suffix, because IN_PROGRESS must first return the persisted started value—and reproduce timestamp evidence/hash without a second per-invocation time channel. The helper name and metadata must contain `mock`; it must not claim model-seed pairing authority.

- [ ] **Step 5: Run focused and combined suites**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_run.py tests\test_pipeline.py tests\test_engine.py tests\test_checkpoint.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add platform/src/agent_ex/mock_run.py platform/src/agent_ex/pipeline.py platform/tests/test_mock_run.py platform/tests/helpers/mock_matrix.py platform/src/agent_ex/__init__.py platform/tests/test_domain.py
git commit -m "feat(platform): orchestrate explicit mock runs"
```

## Task 4: Process audit and deterministic recovery projection

**Files:**
- Create: `platform/src/agent_ex/process_audit.py`
- Create: `platform/tests/test_process_audit.py`
- Modify: `platform/src/agent_ex/storage.py` only if a narrowly typed read-only audit reader is proven necessary.
- Modify: `platform/src/agent_ex/mock_run.py`
- Modify: `platform/tests/test_mock_run.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [ ] **Step 1: Write process-boundary RED tests**

Execute a small E2 run containing empty feed, repeated sender, expired candidate and publish-false events. Assert:

```python
audit = build_mock_process_audit(
    storage=store,
    cell_id="P1-I1-C1-E2",
    topic_package=topic,
    boundary_event_ordinal=store.progress.next_event_ordinal,
    outcome_labels={
        "private_state": "primary",
        "public_stock": "required_secondary",
        "public_flow": "required_secondary",
        "expression_gap": "required_secondary_definition_unresolved",
    },
    terminology_map_id="paper1.phase4a1.terminology.v1",
    terminology_map={
        "identity": "人口身份线索可见性",
        "continuity": "历史立场一致性要求",
        "private_state": "非公开Agent立场状态",
        "public_post": "Agent可见话语分布",
    },
    model_provenance=model_provenance,
    prompt_provenance=prompt_provenance,
    robustness_provenance=robustness_provenance,
)
assert audit.round_zero.agent_count == len(store.binding.expected_agent_ids)
assert tuple(item.sweep_index for item in audit.sweeps) == (1, 2)
assert audit.sweeps[-1].process.selected_message_count == sum(
    audit.sweeps[-1].process.per_event_message_counts
)
assert audit.sweeps[-1].process.empty_feed_count == 1
assert set(audit.sweeps[-1].private_label_count_delta) == set(topic.stance_labels)
assert audit.outcome_labels["expression_gap"].endswith("definition_unresolved")
assert "effect" not in audit.to_payload()
```

Add attacks for boundary beyond committed prefix, failed/current attempt, missing evidence, non-positive event-backed age, altered sender IDs, reordered event evidence, wrong outcome labels, changed/incomplete terminology mapping and any raw private-state leak into public stock. Include positive cases for a legal `RUNNING` sweep prefix with no unresolved attempt and the exact final `COMPLETE` prefix; reject FAILED, mid-sweep and nonterminal-at-boundary states.

- [ ] **Step 2: Write comparable projection RED tests**

Run two semantically identical tiny runs with different launch nonce, paths and timestamps. Assert raw checkpoint hashes differ but:

```python
left = build_mock_comparable_run_projection(left_store, left_audit)
right = build_mock_comparable_run_projection(right_store, right_audit)
assert left.projection_hash == right.projection_hash
```

Then alter a prompt response, publish flag, feed cursor, model seed or parsed update and assert hashes differ. Add an exact field-set test proving callers cannot supply arbitrary ignored fields.

- [ ] **Step 3: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_process_audit.py tests\test_mock_run.py -k "audit or projection"
```

Expected: FAIL because the audit/projection APIs do not exist.

- [ ] **Step 4: Implement immutable audit types**

```python
@dataclass(frozen=True, slots=True)
class ExposureProcessSummary:
    analysis_label: str
    per_event_message_counts: tuple[int, ...]
    event_backed_message_ages: tuple[int, ...]
    round0_message_count: int
    unique_source_agent_ids: tuple[str, ...]
    repeated_source_message_count: int
    empty_feed_count: int
    expired_message_count: int
    sender_activity_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class RoundZeroBaseline:
    agent_count: int
    private_state_snapshot: tuple[Mapping[str, object], ...]
    public_stock_snapshot: tuple[Mapping[str, object], ...]
    private_label_counts: Mapping[str, int]
    public_label_counts: Mapping[str, int]
    baseline_hash: str = field(init=False)


@dataclass(frozen=True, slots=True)
class SweepProcessAudit:
    sweep_index: int
    boundary_event_ordinal: int
    private_state_snapshot: tuple[Mapping[str, object], ...]
    public_stock_snapshot: tuple[Mapping[str, object], ...]
    public_flow_snapshot: tuple[Mapping[str, object], ...]
    process: ExposureProcessSummary
    private_label_count_delta: Mapping[str, int]
    public_stock_label_count_delta: Mapping[str, int]
    public_flow_label_count_delta: Mapping[str, int]
    label_count_delta_analysis_label: str
    sweep_hash: str = field(init=False)


@dataclass(frozen=True, slots=True)
class MockProcessAudit:
    schema_version: str
    run_id: str
    cell_id: str
    boundary_event_ordinal: int
    round_zero: RoundZeroBaseline
    sweeps: tuple[SweepProcessAudit, ...]
    outcome_labels: Mapping[str, str]
    terminology_map_id: str
    terminology_map_hash: str
    terminology_map: Mapping[str, str]
    provenance: Mapping[str, object]
    checkpoint_hash: str
    audit_hash: str = field(init=False)
```

Read only committed evidence via public `RunStorage` methods inside one explicit read snapshot. If a missing public reader blocks this, add the narrowest typed read-only method to `RunStorage`; do not expose `_connection` or arbitrary SQL.
Implement `build_mock_process_audit` with exactly the required keyword arguments shown in the RED test: `storage`, `cell_id`, `topic_package`, `boundary_event_ordinal`, `outcome_labels`, `terminology_map_id`, `terminology_map`, `model_provenance`, `prompt_provenance`, and `robustness_provenance`. It accepts no defaults or extra keyword mapping. Require the exact approved Chinese mappings copied verbatim from the 07-29 Phase 4A.1 table for `identity`, `continuity`, `private_state`, and `public_post`; do not substitute machine-friendly English tokens. Compute `terminology_map_hash` from the canonical payload and bind ID/hash/payload into the audit.
Require `boundary_event_ordinal` to be a committed multiple of population size. Accept either a verified `RUNNING` prefix with no unresolved/nonterminal attempt at that boundary or a verified `COMPLETE` exact full-schedule prefix; reject `FAILED`, tampered/incomplete and non-sweep prefixes. Rebuild round 0 once, then emit exactly sweeps `1..boundary/population_size`; compute only integer seven-label count deltas from round 0. Set both the exposure summary and mechanical delta label to the exact constant `exploratory/process_diagnostic`; tests reject any primary/secondary promotion.

- [ ] **Step 5: Implement fixed comparable projection schema**

```python
@dataclass(frozen=True, slots=True)
class MockComparableRunProjection:
    schema_version: str
    matched_seed: int
    cell_id: str
    schedule_hash: str
    committed_event_semantics: tuple[Mapping[str, object], ...]
    final_private_states: tuple[Mapping[str, object], ...]
    final_public_stock: tuple[Mapping[str, object], ...]
    final_feed_cursors: tuple[Mapping[str, object], ...]
    process_audit_semantics: Mapping[str, object]
    projection_hash: str = field(init=False)
```

The schema itself excludes run ID, launch nonce, URI/path and wall-clock timestamps. It retains event ordinals, agent IDs, statuses, published flags, request/model-seed/prompt/response/parse semantic hashes and process evidence. No `ignore_fields` parameter is allowed.
Implement `build_mock_comparable_run_projection(storage: RunStorage, audit: MockProcessAudit) -> MockComparableRunProjection` with those two required positional arguments only.

- [ ] **Step 6: Run focused and storage suites**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_process_audit.py tests\test_mock_run.py tests\test_storage.py tests\test_checkpoint.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add platform/src/agent_ex/process_audit.py platform/tests/test_process_audit.py platform/src/agent_ex/mock_run.py platform/tests/test_mock_run.py platform/src/agent_ex/storage.py platform/src/agent_ex/__init__.py platform/tests/test_domain.py
git commit -m "feat(platform): audit mock process evidence"
```

## Task 5: N=20 fault and recovery integration

**Files:**
- Create: `platform/tests/test_mock_matrix_integration.py`
- Modify: `platform/tests/helpers/mock_matrix.py`
- Modify: `platform/src/agent_ex/mock_run.py` only if a RED proves a generic harness defect.

- [ ] **Step 1: Add uninterrupted/reopened RED matrix**

Parameterize explicit prefixes:

```python
@pytest.mark.parametrize(
    "crash_point",
    (
        "after_pending",
        "after_in_progress_reconciled",
        "after_invocation",
        "after_terminal_success",
        "after_sqlite_commit_before_context",
        "after_checkpoint_write",
    ),
)
def test_n20_recovery_matches_uninterrupted_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
):
    uninterrupted = run_n20_fixture(
        tmp_path / "continuous",
        monkeypatch=monkeypatch,
        crash_point=None,
    )
    resumed = run_n20_fixture(
        tmp_path / "resumed",
        monkeypatch=monkeypatch,
        crash_point=crash_point,
    )
    assert resumed.projection.projection_hash == uninterrupted.projection.projection_hash
    assert resumed.final_checkpoint.next_event_ordinal == 40
```

For each branch, run the explicit N=20/T=2 fixture to completion both uninterrupted and with real close/open at the prefix. Compare `MockComparableRunProjection.projection_hash`, not raw run IDs. Instrument adapter calls: after invocation and later must be zero-resend; IN_PROGRESS/no-invocation requires exact explicit reconciliation.

- [ ] **Step 2: Add failure/atomicity RED matrix**

Cover timeout, malformed response, request drift, unauthorized model-seed change, finalization mismatch, checkpoint tamper and retry authorization. Assert failed attempt changes no private/public/cursor/event progress and the run stops at the same event. No test helper may silently auto-authorize retry.

- [ ] **Step 3: Run RED against current generic APIs**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_matrix_integration.py -k "n20"
```

Expected: at least one integration branch fails until the fixture/harness wiring is complete.

- [ ] **Step 4: Add only minimal generic fixes**

Fix production code only when a failure applies to all callers. Fixture-specific crash injection, mock response scripts and reconciliation construction remain in test helpers. Do not add sleeps or monkeypatch private storage state to simulate a durable prefix; use existing public operations plus narrowly scoped fault injection at established transaction boundaries.

- [ ] **Step 5: Verify N=20 plus full regression**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_matrix_integration.py -k "n20"
.\.venv\Scripts\python.exe -m pytest -q tests\test_pipeline.py tests\test_engine.py tests\test_storage.py tests\test_checkpoint.py tests\test_mock_run.py tests\test_process_audit.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add platform/tests/test_mock_matrix_integration.py platform/tests/helpers/mock_matrix.py platform/src/agent_ex/mock_run.py
git commit -m "test(platform): integrate N20 mock recovery"
```

## Task 6: N=100 complete 12-cell integration

**Files:**
- Modify: `platform/tests/test_mock_matrix_integration.py`
- Modify: `platform/tests/helpers/mock_matrix.py`
- Modify: `platform/pyproject.toml`
- Modify: `platform/src/agent_ex/mock_matrix.py` only for proven matrix-validator defects.
- Modify: `platform/src/agent_ex/process_audit.py` only for proven audit defects.

- [ ] **Step 1: Write full matrix RED test**

First register the two release markers under `[tool.pytest.ini_options]` so strict-marker collection remains fail closed:

```toml
markers = [
    "release_integration: executes the complete N=100 twelve-cell mock matrix",
    "release_scale: executes the explicit N=1000/T=50 fifty-thousand-event mock gate",
]
addopts = "--strict-config --strict-markers --basetemp=.pytest-tmp -m 'not release_scale'"
```

```python
@pytest.mark.release_integration
def test_n100_executes_complete_twelve_cell_matrix_without_result_selection(tmp_path):
    fixture = build_mock_matrix_fixture(
        tmp_path,
        case_id="mock-n100-full-matrix",
        sweeps=1,
    )
    results = execute_all_cells(fixture)
    assert tuple(results) == CANONICAL_CELL_IDS
    assert all(result.run_report.completed for result in results.values())
    assert all(result.run_report.executed_event_count == 100 for result in results.values())
    assert all(result.process_audit.outcome_labels == EXPECTED_LABELS for result in results.values())
```

Define a test-helper-only frozen `MockCellExecutionResult(run_report: MockRunReport, process_audit: MockProcessAudit)` and type `execute_all_cells` as `Mapping[str, MockCellExecutionResult]`; do not add audit state to the production run report. Add assertions that all shared artifact/schedule hashes are equal, E0/E1/E2 graph bindings are exact, persona blocks differ only as approved, each SQLite path is unique, and audit payloads contain no ranking/effect/significance fields.

- [ ] **Step 2: Add pre-execution cross-cell attack tests**

Parameterize one changed population member, stance/reason, mapping edge, attention weight, expression flag, activation slot, publish flag, graph hash, manifest cell and mock script. Each must fail matrix validation before the first `MockEventPipeline.execute` call.

- [ ] **Step 3: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_matrix_integration.py -k "n100"
```

Expected: FAIL until complete fixture assembly and cell execution are connected.

- [ ] **Step 4: Complete fixture assembly without production shortcuts**

Use the existing artifact builders and one independent `RunStorage`/pipeline per cell. `execute_all_cells` lives in test helpers and calls `execute_mock_run`; it must not write storage directly. Reuse the same typed schedule/artifact objects where the protocol requires sharing, but create distinct manifests/run IDs/databases.

- [ ] **Step 5: Verify N=100 and all matrix modules**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_matrix.py tests\test_mock_run.py tests\test_process_audit.py tests\test_mock_matrix_integration.py -k "not n1000"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

Expected: PASS with 1,200 actual mock events in the N=100 full matrix test.

- [ ] **Step 6: Commit**

```powershell
git add platform/tests/test_mock_matrix_integration.py platform/tests/helpers/mock_matrix.py platform/src/agent_ex/mock_matrix.py platform/src/agent_ex/process_audit.py platform/pyproject.toml
git commit -m "test(platform): execute the N100 twelve-cell matrix"
```

## Task 7: N=1000/T=50 shape and 50,000-event release gate

The `release_scale` marker is default-excluded by the Task 6 `addopts`; ordinary focused, full and coverage runs may collect but must not execute it. Only Step 6 overrides `addopts`, for one explicit release invocation.

**Files:**
- Create: `platform/tests/test_mock_scale_release.py`
- Modify: `platform/tests/helpers/mock_matrix.py`
- Modify: `platform/src/agent_ex/mock_run.py` only for measured generic complexity defects.
- Modify: `platform/src/agent_ex/process_audit.py` only for measured generic complexity defects.
- Modify: `platform/pyproject.toml` to register an explicit release marker if needed.

- [ ] **Step 1: Write the 12-cell shape gate**

```python
def test_n1000_t50_builds_twelve_bound_50000_event_shapes(tmp_path):
    fixture = build_mock_matrix_fixture(
        tmp_path,
        case_id="mock-n1000-release-shape",
        sweeps=50,
    )
    validate_mock_matched_seed_matrix(fixture.matrix)
    assert all(cell.manifest.schedule.count == 50_000 for cell in fixture.matrix.cells)
    assert all(
        tuple(slot.event_ordinal for slot in cell.manifest.schedule.slots) == tuple(range(50_000))
        for cell in fixture.matrix.cells
    )
```

Avoid materializing twelve duplicate ordinal tuples in the final implementation: test first/last/count and stream the sequence comparison. Assert schedule/artifact reuse and unique cell run IDs.

- [ ] **Step 2: Write a genuine marked 50,000-event gate**

```python
@pytest.mark.release_scale
def test_n1000_t50_stress_cell_executes_50000_real_mock_events(tmp_path):
    fixture = build_stress_cell_fixture(
        tmp_path,
        case_id="mock-n1000-release-shape",
        cell_id="P1-I1-C1-E2",
    )
    measurement = measure_mock_release_run(fixture)
    assert measurement.report.completed is True
    assert measurement.report.executed_event_count == 50_000
    assert measurement.final_checkpoint.next_event_ordinal == 50_000
    assert measurement.final_checkpoint.resume_action == "complete"
    assert measurement.audit.boundary_event_ordinal == 50_000
    assert measurement.adapter_calls == 50_000
```

Measure elapsed monotonic seconds, Python peak memory with `tracemalloc`, SQLite bytes, checkpoint bytes and audit bytes. Record values but do not assert unfrozen throughput/memory/duration thresholds. Build the final audit from the authoritative `COMPLETE` storage and assert the versioned terminology mapping and exploratory/process-diagnostic labels survive canonical replay.

- [ ] **Step 3: Write one-sweep N=1000 recovery equivalence gate**

Execute N=1000/T=1 uninterrupted and close/open at explicit ordinals `(1, 500, 1000)`. Assert the final comparable projection hashes match and post-invocation recovery has zero adapter resend. This satisfies the N=1000 recovery comparison without duplicating two full 50,000-event runs.

- [ ] **Step 4: Run shape and recovery RED/GREEN first**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_scale_release.py -k "shape or recovery"
```

Expected: PASS after fixture wiring; do not start the expensive release gate until these structural tests are green.

- [ ] **Step 5: Profile a bounded prefix before optimizing**

Run 100, then 1,000, then 5,000 events with the same stress fixture and record elapsed/memory/SQLite growth. If growth is superlinear, use profiler evidence to locate repeated full-history scans. Add a regression that counts the offending public call or measures normalized operation count; do not weaken validation or batch-write state.

- [ ] **Step 6: Run the explicit 50,000-event release gate once**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -o addopts="--strict-config --strict-markers" -m release_scale tests\test_mock_scale_release.py --basetemp="$env:TEMP\phase4b9-n1000-t50"
```

Expected: one complete 50,000-event test passes. Preserve only the concise measurement output in the handoff log; delete the temporary SQLite/checkpoints after verifying their hashes.

- [ ] **Step 7: Run focused regression and static gates**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_scale_release.py -m "not release_scale"
.\.venv\Scripts\python.exe -m pytest -q tests\test_mock_matrix.py tests\test_mock_run.py tests\test_process_audit.py tests\test_mock_matrix_integration.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add platform/tests/test_mock_scale_release.py platform/tests/helpers/mock_matrix.py platform/src/agent_ex/mock_run.py platform/src/agent_ex/process_audit.py platform/pyproject.toml
git commit -m "test(platform): pass Phase 4B mock scale gates"
```

## Task 8: Documentation, independent review and Phase 4B handoff

**Files:**
- Modify: `docs/paper1-protocol.md`
- Modify: `docs/reproducibility.md`
- Modify: `docs/project-overview.md`
- Create: `logs/2026-09-02-phase4b-handoff.md`
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`
- Modify: `docs/superpowers/specs/2026-09-02-paper1-phase4b9-mock-integration-design.md`

- [ ] **Step 1: Write exact implementation evidence**

Record:

- commit range for Tasks 0–7;
- exact focused/full/coverage counts;
- N=20 crash prefixes and zero-resend call counts;
- N=100 12-cell/event counts and invariant hashes;
- N=1000/T=50 shape count and genuine execution measurement;
- constructor-bound deterministic clock-sequence identity/hash plus retry/reconciliation timestamp replay evidence;
- process-diagnostic exploratory labels and versioned terminology-map ID/hash/payload;
- storage v6/checkpoint v4 plus legacy v3 boundary;
- Windows limitations and required Linux/cloud rerun;
- mock-only/not-frozen limitation and remaining Phase 0A/0B/formal gates;
- exact local/remote branch and resume commands without secrets.

- [ ] **Step 2: Update durable project documents**

Update protocol/reproducibility/overview only with verified engineering facts. Keep every `UNRESOLVED[...]` token and formal fail-closed statement. Mark Phase 4B complete only after all release reviews pass. Do not write raw performance databases or response content into Markdown.

- [ ] **Step 3: Run all release gates in fresh locations**

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp="$env:TEMP\phase4b9-final-full"
.\.venv\Scripts\python.exe -m pytest -q --cov=agent_ex --cov-report=term-missing --basetemp="$env:TEMP\phase4b9-final-cov"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

The configured default exclusion means both full and coverage runs above skip `release_scale`; they must report that deselection. Do not override it here and do not execute the 50,000-event gate again. Then run the existing schema byte-identity, generated human summary, draft validation, formal fail-closed, isolated wheel install and Git hygiene tests by their exact pytest node IDs discovered in the current suite.

- [ ] **Step 4: Request three bounded independent reviews**

Dispatch:

1. verification reviewer: reproduce full/static/protocol/install/hygiene and scale evidence;
2. specification/anti-pattern reviewer: compare every Phase 4B completion criterion, search old synchronization semantics and coder defaults;
3. code-quality reviewer: inspect correctness, atomicity, complexity, public API and test false positives.

Require exact P0–P3. Fix every P0–P2 with a new RED/GREEN test and re-run the affected reviewer. Keep non-blocking P3 in the handoff with an owner or explicit rationale.

- [ ] **Step 5: Final completion audit**

Map each numbered Phase 4B completion criterion to an authoritative test, file, reviewer result or measured run. Treat missing/indirect evidence as incomplete. Confirm:

```powershell
git status --short
git diff --check
git ls-files | Select-String -Pattern '\.sqlite|checkpoint|raw.response|\.codex|__pycache__|\.pytest_cache'
```

Expected: only intended source/docs/tests/fixtures are staged; no raw runtime artifact is tracked.

- [ ] **Step 6: Commit and push**

```powershell
git add platform/src/agent_ex/mock_matrix.py platform/src/agent_ex/mock_run.py platform/src/agent_ex/process_audit.py platform/src/agent_ex/pipeline.py platform/src/agent_ex/storage.py platform/src/agent_ex/__init__.py platform/tests/helpers/mock_matrix.py platform/tests/test_mock_matrix.py platform/tests/test_mock_run.py platform/tests/test_process_audit.py platform/tests/test_mock_matrix_integration.py platform/tests/test_mock_scale_release.py platform/tests/test_paper1_mock_fixtures.py platform/tests/test_domain.py platform/tests/fixtures/paper1/mock_scale_cases.artifact.json platform/pyproject.toml docs/paper1-protocol.md docs/reproducibility.md docs/project-overview.md logs/2026-09-02-phase4b-handoff.md task_plan.md progress.md findings.md docs/superpowers/specs/2026-09-02-paper1-phase4b9-mock-integration-design.md docs/superpowers/plans/2026-09-02-paper1-phase4b9-mock-integration.md
git commit -m "feat(platform): complete Phase 4B mock integration"
git push origin codex/paper1-phase4b
git status --short --branch
git rev-parse HEAD
git rev-parse '@{u}'
```

Expected: clean worktree and identical local/upstream hashes.

## Self-review

- **Specification coverage:** Tasks 1–2 cover explicit three-scale fixtures and all 12-cell sharing rules; Task 3 provides only the approved outer orchestration; Task 4 covers private/public/process/provenance output without selecting results; Tasks 5–7 cover N=20/100/1000 recovery, matrix and true 50,000-event gates; Task 8 covers all Phase 4B release and handoff criteria.
- **No hidden research defaults:** production APIs require all values. B=6, K=3, small T values and the stress cell exist only in a versioned `mock_only/not_frozen` fixture and cannot validate as formal configuration.
- **No second lifecycle:** only `MockEventPipeline.execute` creates attempts, invokes/parses, records terminal evidence and commits research state. The run harness loops and stops; it never writes lifecycle tables.
- **No placeholder implementation steps:** every task identifies exact files, public types, RED assertions, commands, expected results and commit boundary. The only ellipsis tokens are concrete Python variable-length tuple annotations such as `tuple[int, ...]`.
- **Type consistency:** `MockScaleCase`, `MockCellBinding`, `MockMatchedSeedMatrix`, `MockEventInvocation`, `MockRunControl`, `MockRunReport`, `ExposureProcessSummary`, `MockProcessAudit` and `MockComparableRunProjection` retain the same roles throughout all tasks.
