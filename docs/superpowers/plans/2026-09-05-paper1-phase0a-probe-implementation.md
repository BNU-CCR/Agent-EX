---
status: implementation plan; self-reviewed; pending execution selection
authority: Phase 0A-0 offline probe implementation plan; subordinate to the approved 2026-09-05 design and specification chain
date: 2026-09-05
---

# Paper 1 Phase 0A Offline Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, calibration-only dry-run platform for the three-topic and four-Persona Phase 0A probe without calling a real model, weakening Phase 4B mock guards, or freezing research parameters.

**Architecture:** Add a separate `agent_ex.calibration` package with its own immutable specification, case, request/response, parse, runtime, scoring, review, and report contracts. Reuse only canonical hashing and immutable artifact primitives; calibration types never accept `GenerationEvent`, run/feed/state identity, and all outputs carry `calibration_only: true` plus `formal_parameter_authority: false`.

**Tech Stack:** Python 3.12, frozen dataclasses, standard-library JSON/statistics, existing `ArtifactEnvelope` and `canonical_payload_hash`, pytest, pytest-cov, Ruff.

**Approved specification:** `docs/superpowers/specs/2026-09-05-paper1-phase0a-probe-design.md` at commit `28eafee` or a reviewed descendant.

**Command working-directory contract:** Python commands run from `<phase0-worktree>/platform`; Git commands run from `<phase0-worktree>`. On this desktop, create the local environment from the verified Phase 4B Python 3.12 interpreter. On another machine, substitute an installed Python 3.12 interpreter, never Python 3.14.

---

## File map

- Create `platform/src/agent_ex/calibration/__init__.py`: calibration-only public surface.
- Create `platform/src/agent_ex/calibration/contracts.py`: strict immutable topic, persona, case, request, response, parse, policy, attempt and run records.
- Create `platform/src/agent_ex/calibration/specification.py`: specification validation and exact case inventory expansion.
- Create `platform/src/agent_ex/calibration/render.py`: topic/persona rendering and factor-only byte-diff validation.
- Create `platform/src/agent_ex/calibration/adapters.py`: probe adapter interface and deterministic scripted adapter.
- Create `platform/src/agent_ex/calibration/parser.py`: bounded strict JSON parser independent of the event parser.
- Create `platform/src/agent_ex/calibration/runner.py`: transport/format attempt state machine and resumable run projection.
- Create `platform/src/agent_ex/calibration/gates.py`: versioned gate algorithm, denominators, `d_z`, TV and deterministic selection.
- Create `platform/src/agent_ex/calibration/review.py`: blinded semantic-review export/import and adjudication validation.
- Create `platform/src/agent_ex/calibration/report.py`: completeness, gate report and non-authoritative freeze proposal.
- Create `platform/src/agent_ex/calibration/bundle.py`: atomic immutable evidence-bundle write/load validation.
- Create `platform/tests/helpers/calibration.py`: synthetic, explicitly calibration-only builders.
- Create `platform/tests/test_calibration_contracts.py`.
- Create `platform/tests/test_calibration_specification.py`.
- Create `platform/tests/test_calibration_adapter_parser.py`.
- Create `platform/tests/test_calibration_runner.py`.
- Create `platform/tests/test_calibration_gates.py`.
- Create `platform/tests/test_calibration_review.py`.
- Create `platform/tests/test_calibration_report.py`.
- Create `platform/tests/test_calibration_integration.py`.
- Create `platform/tests/fixtures/paper1/phase0a_probe_spec.mock.json`: synthetic three-topic/four-Persona dry-run fixture.
- Create `platform/configs/paper1/phase0a-probe.draft.yaml`: non-runnable real-probe draft retaining stable `UNRESOLVED[...]` markers.
- Modify `platform/src/agent_ex/__init__.py`: export only reviewed calibration entry points.
- Modify `platform/tests/test_domain.py`: assert the exact new public surface.
- Modify `docs/project-overview.md`, `task_plan.md`, `progress.md`, and `findings.md`: Phase 0A-0 evidence and Phase 0A-1 boundary.
- Create `logs/2026-09-05-phase0a0-offline-probe.md`: final verified counts, hashes and next-run instructions.

## Task 0: Establish the isolated Python 3.12 baseline

**Files:**
- Create locally, never track: `platform/.venv/`
- Verify: `platform/requirements-dev.lock`

- [x] **Step 1: Create the Phase 0 worktree environment**

Run from `platform/` on this desktop:

```powershell
& '..\..\codex-paper1-phase4b\platform\.venv\Scripts\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Expected: `.venv\Scripts\python.exe --version` reports Python 3.12.x and both installation commands succeed.

- [x] **Step 2: Verify dependency closure and clean baseline**

```powershell
.\.venv\Scripts\python.exe -m pip list --format=json
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q tests\test_topic.py tests\test_persona.py tests\test_parser.py tests\test_mock_adapter.py
.\.venv\Scripts\python.exe -m ruff check .
```

Compare `pip list --format=json` against every non-comment `name==version` line in
`requirements-dev.lock`, normalizing distribution names with the packaging canonical-name rule.
The gate passes only when every locked distribution is present exactly once at the locked version
(all 18 distributions in the current lock file, including `coverage==7.15.2`, `packaging==26.2`,
`Pygments==2.20.0`, and `setuptools==83.0.0`) and no locked version differs. Expected: the complete
locked distribution set matches exactly; `pip check` and Ruff pass; the focused inherited suite
reports 0 failures.

- [x] **Step 3: Prove the environment remains untracked**

```powershell
git status --short
git check-ignore -v platform/.venv
```

Expected: no tracked changes and `.gitignore` identifies the venv exclusion. Do not commit an environment-only task.

## Task 1: Define calibration-only contracts

**Files:**
- Create: `platform/src/agent_ex/calibration/contracts.py`
- Create: `platform/src/agent_ex/calibration/__init__.py`
- Create: `platform/tests/test_calibration_contracts.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [x] **Step 1: Write RED tests for authority and identity separation**

Add tests with these exact assertions:

```python
def test_probe_case_is_calibration_only_and_has_no_event_identity(probe_case):
    payload = probe_case.to_payload()
    assert payload["metadata"] == {
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
    }
    forbidden = {"event_id", "run_id", "cell_id", "feed_cursor", "private_state"}
    assert forbidden.isdisjoint(payload)


def test_probe_contract_roundtrip_and_hash_binding(probe_case):
    restored = ProbeCase.from_payload(probe_case.to_payload())
    assert restored == probe_case
    assert restored.record_hash == canonical_payload_hash(restored.content_payload())


@pytest.mark.parametrize("cls", [ProbeTopicCandidate, ProbePersonaView, ProbeCase])
def test_probe_contracts_reject_formal_authority(cls, valid_payloads):
    payload = valid_payloads[cls]
    payload["metadata"]["formal_parameter_authority"] = True
    with pytest.raises(ValueError, match="calibration-only"):
        cls.from_payload(payload)
```

- [x] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_contracts.py
```

Expected: collection fails because `agent_ex.calibration` does not exist.

- [x] **Step 3: Implement strict frozen records**

Create frozen/slots dataclasses with no defaults for research-bearing fields:

```python
CALIBRATION_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}


@dataclass(frozen=True, slots=True)
class ProbeTopicCandidate:
    candidate_id: str
    construct: str
    fact_card: str
    statements: tuple[str, str, str]
    stance_labels_1_7: tuple[str, ...]
    statement_hashes: tuple[str, str, str]
    record_hash: str


@dataclass(frozen=True, slots=True)
class ProbePersonaView:
    persona_view_id: str
    identity_present: bool
    continuity_present: bool
    common_skeleton: str
    identity_block: str
    continuity_block: str
    rendered_text: str
    record_hash: str


@dataclass(frozen=True, slots=True)
class ProbeCase:
    probe_case_id: str
    specification_hash: str
    candidate_id: str
    case_family: str
    scenario_id: str
    variant_index: int
    scale_id: str
    field_order_id: str
    replicate_id: int
    requested_seed: int | None
    persona_view_id: str
    rendered_messages: tuple[Mapping[str, str], ...]
    rendered_messages_hash: str
    record_hash: str
```

For each class, implement exact-field `from_payload`, JSON-safe `to_payload`, `content_payload`, canonical record-hash verification, tuple/list transport conversion, strict bool-vs-int rejection, nonempty IDs/text, SHA-256 validation, and exact `CALIBRATION_METADATA`. Derive identities from the full content payload excluding `record_hash`; never accept caller-supplied authority metadata.

- [x] **Step 4: Export only the three reviewed primitives**

In `calibration/__init__.py` export `ProbeTopicCandidate`, `ProbePersonaView`, and `ProbeCase`. Add the same names to root `agent_ex.__all__`; update `test_domain.py` to compare the new names and reject accidental `GenerationEvent` inheritance with:

```python
assert not issubclass(agent_ex.ProbeCase, agent_ex.GenerationEvent)
```

- [x] **Step 5: Run GREEN and regression tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_contracts.py tests\test_domain.py tests\test_topic.py tests\test_persona.py
```

Expected: all pass; existing mock guard tests remain unchanged.

- [x] **Step 6: Commit**

```powershell
git add platform/src/agent_ex/calibration platform/src/agent_ex/__init__.py platform/tests/test_calibration_contracts.py platform/tests/test_domain.py
git commit -m "feat(platform): define Phase 0A calibration contracts"
```

## Task 2: Validate specifications and expand exact case inventories

**Files:**
- Create: `platform/src/agent_ex/calibration/specification.py`
- Create: `platform/src/agent_ex/calibration/render.py`
- Create: `platform/tests/helpers/calibration.py`
- Create: `platform/tests/test_calibration_specification.py`
- Create: `platform/tests/fixtures/paper1/phase0a_probe_spec.mock.json`

- [x] **Step 1: Write RED tests for the complete synthetic inventory**

The fixture must contain exactly three synthetic-text candidates ordered
`retirement-delay`, `gm-soybean-oil`, `ai-net-employment`; three statement variants each;
the 1--7 main scale and 0--10 challenger; two field orders; four Persona factor combinations;
two continuity wordings; three continuity scenarios; and explicit replicate IDs/seeds.

```python
def test_expand_cases_is_complete_unique_and_order_invariant(mock_probe_spec):
    first = expand_probe_cases(mock_probe_spec)
    reordered = expand_probe_cases(reverse_nonsemantic_arrays(mock_probe_spec))
    assert {case.probe_case_id for case in first} == {
        case.probe_case_id for case in reordered
    }
    assert len(first) == len({case.probe_case_id for case in first})
    assert {case.case_family for case in first} == {
        "topic_quality", "identity", "continuity"
    }
```

Add rejection tests for missing/extra fields, duplicate candidates, wrong preselection order, absent
statement variants, unknown `P1_*` IDs, missing gate/review/runtime policy hashes, implicit seeds,
and any event/run/feed/state field.

- [x] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_specification.py
```

Expected: FAIL because specification validation and expansion do not exist.

- [x] **Step 3: Implement specification validation**

Implement:

```python
EXPECTED_TOPIC_ORDER = (
    "retirement-delay",
    "gm-soybean-oil",
    "ai-net-employment",
)
ALLOWED_DECISION_IDS = {
    "P1_TOPIC_PRIMARY", "P1_STANCE_SCALE", "P1_PERSONA_TEMPLATES",
    "P1_CONTINUITY_MC_SCORING", "P1_CONTINUITY_LOCK_THRESHOLD",
    "P1_REFUSAL_THRESHOLD", "P1_PARSE_FAILURE_THRESHOLD",
    "P1_TEMPERATURE", "P1_TOP_P", "P1_REQUEST_SEED",
    "P1_TIMEOUT_RETRY",
}


def load_probe_specification(payload: Mapping[str, object]) -> ArtifactEnvelope:
    """Validate an exact calibration-only v1 payload and return a hash-bound envelope."""


def expand_probe_cases(specification: ArtifactEnvelope) -> tuple[ProbeCase, ...]:
    """Expand all declared families, canonical-sort by case ID, and reject duplicates."""
```

The validator must require exact candidate order, all policy hashes, explicit arrays, no defaults,
and calibration metadata. `expand_probe_cases` derives IDs from semantic dimensions, not iteration
position, then returns `tuple(sorted(cases, key=attrgetter("probe_case_id")))`.

- [x] **Step 4: Implement calibration rendering and byte-diff checks**

Implement `render_probe_persona(...) -> ProbePersonaView` so absent blocks are empty and present
blocks are mechanically inserted. Implement:

```python
def validate_probe_persona_factor_diff(
    views: tuple[ProbePersonaView, ...],
) -> Mapping[str, object]:
    allowed = {"identity_present", "continuity_present", "identity_block",
               "continuity_block", "rendered_text", "persona_view_id", "record_hash"}
    # Compare every other payload field byte-for-byte and reject forbidden locking phrases.
```

The forbidden phrase list includes the approved Chinese locking language from D-2026-07-29-06.
Do not call `render_persona`; its mock artifact contract must remain untouched.

- [x] **Step 5: Run GREEN and mock-guard regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_specification.py tests\test_persona.py tests\test_topic.py
```

Expected: all pass.

- [x] **Step 6: Commit**

```powershell
git add platform/src/agent_ex/calibration/specification.py platform/src/agent_ex/calibration/render.py platform/tests/helpers/calibration.py platform/tests/test_calibration_specification.py platform/tests/fixtures/paper1/phase0a_probe_spec.mock.json
git commit -m "feat(platform): expand deterministic Phase 0A cases"
```

## Task 3: Add probe request, response, parser, and scripted adapter evidence

**Files:**
- Modify: `platform/src/agent_ex/calibration/contracts.py`
- Create: `platform/src/agent_ex/calibration/adapters.py`
- Create: `platform/src/agent_ex/calibration/parser.py`
- Create: `platform/tests/test_calibration_adapter_parser.py`

- [x] **Step 1: Write RED request/response/parser tests**

```python
def test_scripted_response_binds_case_request_runtime_and_raw_hash(probe_case):
    request = ProbeRequest.create(probe_case, attempt_index=1, attempt_kind="semantic")
    response = scripted_adapter().generate(request)
    assert response.probe_case_id == probe_case.probe_case_id
    assert response.request_hash == request.record_hash
    assert response.raw_response_hash == canonical_payload_hash(response.raw_response)
    assert response.metadata["formal_parameter_authority"] is False


@pytest.mark.parametrize("raw,code", [
    ('{"stance":4,"confidence":3}', "fields"),
    ('{"stance":true,"confidence":3,"public_reason":"x"}', "stance"),
    ('{"stance":8,"confidence":3,"public_reason":"x"}', "stance"),
    ('{"stance":4,"confidence":3,"public_reason":"x","extra":1}', "fields"),
    ('{"stance":NaN,"confidence":3,"public_reason":"x"}', "json"),
])
def test_probe_parser_fails_closed(raw, code, probe_request):
    evidence = parse_probe_response(response_with(raw), probe_request, limits())
    assert evidence.success is False
    assert evidence.error_code == code
```

Also cover duplicate keys, raw char/byte bounds, JSON depth, 0--10 range, field-order variants,
provider seed support/echo, timeout/OOM/provider-error responses, and strict round trips.

- [x] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_adapter_parser.py
```

Expected: FAIL on missing request/response/parser symbols.

- [x] **Step 3: Implement the probe adapter contract**

Add `ProbeRequest`, `ProbeResponse`, and `ProbeParseEvidence` frozen records to `contracts.py`.
Their identities bind case hash, attempt index/kind, rendered messages, generation settings,
requested seed, provider seed declaration/echo, runtime/model/tokenizer/chat-template identities,
raw response or typed error, and calibration metadata.

Create:

```python
class ProbeAdapter(ABC):
    @abstractmethod
    def generate(self, request: ProbeRequest) -> ProbeResponse:
        """Execute exactly one pre-authorized calibration attempt."""


@dataclass(frozen=True, slots=True)
class ProbeScriptStep:
    outcome: str
    raw_response: str | None
    error_code: str | None


class ScriptedProbeAdapter(ProbeAdapter):
    def __init__(self, scripts: Mapping[str, tuple[ProbeScriptStep, ...]]):
        self._scripts = {case_id: tuple(steps) for case_id, steps in scripts.items()}

    def generate(self, request: ProbeRequest) -> ProbeResponse:
        try:
            step = self._scripts[request.probe_case_id][request.attempt_index - 1]
        except (KeyError, IndexError) as error:
            raise ValueError("no scripted step for probe attempt") from error
        return ProbeResponse.from_script_step(
            request=request,
            step=step,
            runtime_identity={"provider": "scripted-probe", "runtime_version": "1.0.0"},
            model_identity={"model": "synthetic", "revision": "offline-v1"},
            tokenizer_identity={"tokenizer": "synthetic", "revision": "offline-v1"},
            chat_template_hash=canonical_payload_hash("synthetic-chat-template-v1"),
            provider_request_id=f"scripted-{request.request_id}",
            provider_seed_supported=True,
            provider_seed_echo=request.requested_seed,
        )
```

The scripted adapter consumes the exact step for `(probe_case_id, attempt_index)` and never
uses the Phase 4B `MockAdapter` or its seals.

- [x] **Step 4: Implement the bounded strict parser**

`parse_probe_response` must use `json.loads` with duplicate-key and NaN/Infinity rejection,
check exact field set and declared field order, reject bool-as-int, enforce the case scale,
confidence 1--5, nonblank bounded public reason, and bind evidence to request/response hashes.
It returns evidence for invalid responses; resource-limit violations raise before unbounded encoding.

- [x] **Step 5: Run GREEN and event-parser regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_adapter_parser.py tests\test_parser.py tests\test_mock_adapter.py
```

Expected: all pass.

- [x] **Step 6: Commit**

```powershell
git add platform/src/agent_ex/calibration/contracts.py platform/src/agent_ex/calibration/adapters.py platform/src/agent_ex/calibration/parser.py platform/tests/test_calibration_adapter_parser.py
git commit -m "feat(platform): record Phase 0A probe responses"
```

## Task 4: Implement the attempt state machine and recovery projection

**Files:**
- Modify: `platform/src/agent_ex/calibration/contracts.py`
- Create: `platform/src/agent_ex/calibration/runner.py`
- Create: `platform/tests/test_calibration_runner.py`

- [x] **Step 1: Write RED lifecycle tests**

```python
def test_format_retry_is_once_and_does_not_consume_transport_budget(run_fixture):
    report = execute_probe_run(run_fixture.adapter, run_fixture.inventory, run_fixture.policy)
    attempts = report.attempts_for("case-format-repair")
    assert [a.attempt_kind for a in attempts] == ["semantic", "format_repair"]
    assert report.case_status("case-format-repair") == "complete"


def test_exhausted_runtime_failure_is_irreversible_in_same_run(run_fixture):
    first = execute_probe_run(run_fixture.failing_adapter, run_fixture.inventory, run_fixture.policy)
    assert first.case_status("case-timeout") == "runtime_failed"
    with pytest.raises(ValueError, match="irreversible"):
        resume_probe_run(first, run_fixture.success_adapter)


def test_resume_does_not_reset_attempt_budget(crash_fixture):
    resumed = resume_probe_run(crash_fixture.snapshot, crash_fixture.adapter)
    assert resumed.transport_attempt_count("case-provider-error") == 2
```

Also test retryable/nonretryable errors, Retry-After/backoff evidence, OOM classification,
model/runtime/spec/hash drift, only-unstarted and budget-remaining recovery, canonical report order,
and refusal not triggering format retry.

- [x] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_runner.py
```

Expected: FAIL because runner functions are absent.

- [x] **Step 3: Implement explicit policy and immutable state projection**

Add exact records:

```python
@dataclass(frozen=True, slots=True)
class ProbeRuntimePolicy:
    policy_id: str
    retryable_error_codes: tuple[str, ...]
    nonretryable_error_codes: tuple[str, ...]
    max_transport_attempts_by_code: Mapping[str, int]
    timeout_seconds: float
    obey_retry_after: bool
    backoff_seconds: tuple[float, ...]
    record_hash: str


@dataclass(frozen=True, slots=True)
class ProbeRunProjection:
    probe_run_id: str
    specification_hash: str
    case_inventory_hash: str
    runtime_policy_hash: str
    case_statuses: Mapping[str, str]
    attempts: tuple[ProbeAttempt, ...]
    status: str
    run_evidence_hash: str
```

No policy field has a default. Validate that code sets partition all adapter errors and budgets are
strict positive integers. Derive projection state only by replaying ordered hash-bound attempts.

- [x] **Step 4: Implement execution and resume rules**

Implement `execute_probe_run(...)` and `resume_probe_run(...)`. A semantic response can lead to
one format repair; transport failures use only the bound policy. `runtime_failed` is irreversible.
Resume verifies all input hashes and remaining budget before invoking the adapter. Any exhausted
case forces run `incomplete`; never merge evidence from another run.

- [x] **Step 5: Run GREEN tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_runner.py tests\test_calibration_adapter_parser.py
```

Expected: all pass.

- [x] **Step 6: Commit**

```powershell
git add platform/src/agent_ex/calibration/contracts.py platform/src/agent_ex/calibration/runner.py platform/tests/test_calibration_runner.py
git commit -m "feat(platform): execute recoverable Phase 0A probes"
```

## Task 5: Implement deterministic gate algorithms and precommitted topic selection

**Files:**
- Create: `platform/src/agent_ex/calibration/gates.py`
- Create: `platform/tests/test_calibration_gates.py`

- [ ] **Step 1: Write RED boundary and denominator tests**

```python
def test_endpoint_gate_checks_each_endpoint_not_combined(valid_evidence):
    evidence = distribution_evidence({1: 45, 7: 45, 4: 10})
    result = evaluate_quality_gates(evidence, gate_algorithm())
    assert result.metrics["lower_endpoint_share"] == Fraction(45, 100)
    assert result.metrics["upper_endpoint_share"] == Fraction(45, 100)
    assert result.gates["single_endpoint_max"].passed is True


def test_parse_and_refusal_use_all_scheduled_cases_as_denominator(evidence):
    result = evaluate_quality_gates(evidence_with_counts(100, parsed=99, refusals=1), gate_algorithm())
    assert result.metrics["parse_rate"] == Fraction(99, 100)
    assert result.metrics["refusal_rate"] == Fraction(1, 100)


def test_dz_zero_variance_rules():
    assert paired_dz([0, 0, 0]) == 0.0
    with pytest.raises(GateFailure, match="zero variance"):
        paired_dz([1, 1, 1])
```

Add exact tests for 98/100 parse failure, 2/100 refusal failure, three-versus-four classes,
80% pass and 81% fail on either endpoint, `abs(d_z)=.20` pass, TV calculation, fewer than two
pairs, contradiction 5% pass/6% fail, indeterminate contradiction causing incomplete, 0--10 not
using the 4-of-7 gate, and runtime/review incomplete suppressing selection.

- [ ] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_gates.py
```

Expected: FAIL because gate symbols are absent.

- [ ] **Step 3: Implement exact metrics**

Implement `paired_dz`, `total_variation`, `fold_case_attempts`, and
`evaluate_quality_gates`. Use `fractions.Fraction` for threshold comparisons, `statistics.stdev`
for paired deltas, explicit zero-variance branches, and exact count provenance. Every metric includes
numerator, denominator, universe case IDs, algorithm ID/version and input hash.

- [ ] **Step 4: Implement deterministic selection**

```python
TOPIC_PRESELECTION = (
    "retirement-delay",
    "gm-soybean-oil",
    "ai-net-employment",
)


def select_topic(gate_reports: Mapping[str, GateReport]) -> TopicSelection:
    eligible = [topic for topic in TOPIC_PRESELECTION if gate_reports[topic].all_hard_gates_pass]
    if not eligible:
        return TopicSelection(status="no_candidate", primary=None, robustness=None)
    return TopicSelection(
        status="proposal_only",
        primary=eligible[0],
        robustness=eligible[1] if len(eligible) > 1 else None,
    )
```

Selection must reject unknown/missing candidates, runtime/review incomplete, and any input containing
forbidden outcome/contrast fields. It never reads means as relative topic quality beyond registered
invariance gates.

- [ ] **Step 5: Run GREEN tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_gates.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add platform/src/agent_ex/calibration/gates.py platform/tests/test_calibration_gates.py
git commit -m "feat(platform): score Phase 0A quality gates"
```

## Task 6: Add blinded semantic-review evidence

**Files:**
- Create: `platform/src/agent_ex/calibration/review.py`
- Create: `platform/tests/test_calibration_review.py`

- [ ] **Step 1: Write RED blind export/import tests**

```python
def test_blind_export_contains_only_policy_allowlist(review_fixture):
    item = export_blind_review(review_fixture)[0]
    assert set(item.visible_payload) == {
        "topic_text", "history_text", "identity_text", "response_text"
    }
    assert "condition" not in item.visible_payload
    assert "topic_priority" not in item.visible_payload
    assert "requested_seed" not in item.visible_payload


def test_adjudication_appends_without_overwriting_independent_codes(review_fixture):
    bundle = import_review_codes(review_fixture.independent_codes, review_policy())
    final = append_adjudication(bundle, review_fixture.adjudication)
    assert final.independent_codes == bundle.independent_codes
    assert final.adjudication is not None
```

Add tests for strata completeness, stable randomized item IDs, judge failure, missing required coder,
invalid label, agreement threshold, disagreement trigger, unauthorized fields, hash drift, and
`review_incomplete` suppressing gates.

- [ ] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_review.py
```

Expected: FAIL because review contracts are absent.

- [ ] **Step 3: Implement the exact policy-bound review flow**

Create `SemanticReviewPolicy`, `BlindReviewItem`, `IndependentCode`, `Adjudication`, and
`SemanticReviewBundle` frozen records. Implement stratified deterministic sampling, allowlisted
exports, exact label validation, the policy-selected agreement statistic, threshold comparison,
adjudication triggers, and final label aggregation. Missing/invalid required evidence sets
`review_incomplete`; it never becomes a favorable score.

- [ ] **Step 4: Run GREEN tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_review.py tests\test_calibration_gates.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/calibration/review.py platform/tests/test_calibration_review.py
git commit -m "feat(platform): bind blinded Phase 0A review"
```

## Task 7: Build reports, immutable bundles, and non-authoritative freeze proposals

**Files:**
- Create: `platform/src/agent_ex/calibration/report.py`
- Create: `platform/src/agent_ex/calibration/bundle.py`
- Create: `platform/tests/test_calibration_report.py`

- [ ] **Step 1: Write RED authority, hash-layer and forbidden-output tests**

```python
def test_freeze_proposal_has_no_decision_authority(complete_inputs):
    proposal = build_freeze_proposal(complete_inputs)
    assert proposal.metadata["formal_parameter_authority"] is False
    assert proposal.status == "proposal_only"
    assert "decision_record_id" not in proposal.to_payload()


def test_hash_layers_have_distinct_semantics(complete_inputs):
    a = build_probe_report(complete_inputs)
    b = build_probe_report(reorder_files_and_records(complete_inputs))
    assert a.specification_hash == b.specification_hash
    assert a.case_inventory_hash == b.case_inventory_hash
    assert a.report_projection_hash == b.report_projection_hash
    assert a.run_evidence_hash == b.run_evidence_hash


@pytest.mark.parametrize("field", ["polarization", "ws_shadow", "p_value", "cell_mean"])
def test_report_rejects_forbidden_result_fields(complete_inputs, field):
    with pytest.raises(ValueError, match="forbidden"):
        build_probe_report(inject_field(complete_inputs, field))
```

Also prove actual response/time/provider-ID changes alter `run_evidence_hash`; score changes alter
`report_projection_hash`; missing evidence gives completeness failure; and report building cannot
write protocol/config/decision files.

Add bundle tests:

```python
def test_bundle_write_is_atomic_complete_and_non_overwriting(tmp_path, complete_inputs):
    target = tmp_path / "probe-run-1"
    write_probe_bundle_atomic(target, complete_inputs)
    assert set(path.name for path in target.iterdir()) == set(PROBE_BUNDLE_FILES)
    assert load_probe_bundle(target).run_evidence_hash == complete_inputs.run_evidence_hash
    with pytest.raises(FileExistsError):
        write_probe_bundle_atomic(target, complete_inputs)


def test_bundle_load_rejects_missing_or_hash_drift(tmp_path, complete_inputs):
    target = tmp_path / "probe-run-1"
    write_probe_bundle_atomic(target, complete_inputs)
    (target / "parse-evidence.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="hash|complete"):
        load_probe_bundle(target)
```

- [ ] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_report.py
```

Expected: FAIL because report builders are absent.

- [ ] **Step 3: Implement the four report layers**

Implement immutable `ProbeCompletenessReport`, `ProbeGateReport`, `TopicSelection`,
`ProbeReport`, `FreezeProposal`, and `ProbeBundle`. `ProbeBundle.payload_for(name)` maps every
exact bundle filename to one hash-bound payload and `ProbeBundle.from_payloads(...)` rejects
missing/extra files or cross-file identity drift. `build_probe_report` canonical-sorts by case/item
ID and computes the three distinct hashes. `build_freeze_proposal` lists proposed values, stable
`P1_*` IDs, artifact hashes, evidence URIs and unresolved decisions, always with proposal-only
metadata.

Define and enforce:

```python
FORBIDDEN_REPORT_KEYS = {
    "polarization", "homogenization", "directional_drift", "two_tier_structure",
    "ws_shadow", "continuity_did", "primary_contrast", "confidence_interval",
    "p_value", "significance", "cell_mean",
}
```

In `bundle.py`, define the exact file inventory and atomic API:

```python
PROBE_BUNDLE_FILES = (
    "manifest.json", "specification.json", "case-inventory.json", "requests.json",
    "raw-responses.json", "parse-evidence.json", "machine-metrics.json",
    "blind-review-export.json", "blind-review-import.json", "gate-report.json",
    "freeze-proposal.json",
)


def write_probe_bundle_atomic(target: Path, bundle: ProbeBundle) -> None:
    if target.exists():
        raise FileExistsError(target)
    staging = target.with_name(target.name + ".partial")
    if staging.exists():
        raise FileExistsError(staging)
    staging.mkdir(parents=False)
    try:
        for name in PROBE_BUNDLE_FILES:
            payload = bundle.payload_for(name)
            (staging / name).write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def load_probe_bundle(target: Path) -> ProbeBundle:
    if {path.name for path in target.iterdir()} != set(PROBE_BUNDLE_FILES):
        raise ValueError("probe bundle file inventory is incomplete")
    return ProbeBundle.from_payloads({
        name: json.loads((target / name).read_text(encoding="utf-8"))
        for name in PROBE_BUNDLE_FILES
    })
```

`ProbeBundle.from_payloads` must revalidate every content hash and the manifest's three hash layers.
The writer accepts an explicit new target only; it never selects “latest” or overwrites a run.

- [ ] **Step 4: Run GREEN tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_report.py tests\test_calibration_gates.py tests\test_calibration_review.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/calibration/report.py platform/src/agent_ex/calibration/bundle.py platform/tests/test_calibration_report.py
git commit -m "feat(platform): report Phase 0A probe evidence"
```

## Task 8: Complete the offline end-to-end dry run and fail-closed real draft

**Files:**
- Create: `platform/tests/test_calibration_integration.py`
- Create: `platform/configs/paper1/phase0a-probe.draft.yaml`
- Modify: `platform/src/agent_ex/calibration/__init__.py`
- Modify: `platform/src/agent_ex/__init__.py`
- Modify: `platform/tests/test_domain.py`

- [ ] **Step 1: Write RED end-to-end tests**

```python
def test_mock_three_topic_four_persona_probe_is_reproducible(mock_probe_spec):
    first = run_offline_probe(mock_probe_spec, scripted_probe_adapter())
    second = run_offline_probe(mock_probe_spec, scripted_probe_adapter())
    assert first.to_payload() == second.to_payload()
    assert first.status == "proposal_only"
    assert first.metadata["formal_parameter_authority"] is False


def test_real_draft_is_not_runnable():
    payload = yaml.safe_load(DRAFT_PATH.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="UNRESOLVED"):
        load_runnable_probe_specification(payload)
```

Add integration cases for all-topics-pass, partial-pass, no-pass, one format repair, permanent
runtime failure, review incomplete, order-independent projection, evidence tamper, and confirmation
that no SQLite/checkpoint/event/feed/state object is created.

- [ ] **Step 2: Run RED tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_integration.py
```

Expected: FAIL because the facade and draft do not exist.

- [ ] **Step 3: Add the facade and draft**

Export one orchestration entry point:

```python
def run_offline_probe(
    specification: ArtifactEnvelope,
    adapter: ProbeAdapter,
) -> ProbeReport:
    cases = expand_probe_cases(specification)
    projection = execute_probe_run(adapter, cases, runtime_policy_from(specification))
    parses = parse_completed_cases(projection, specification)
    review = import_scripted_review(specification, projection)
    return build_probe_report(specification, cases, projection, parses, review)
```

The real draft contains the three approved candidate IDs and stable decision IDs, but every actual
topic text, persona text, generation value, runtime-policy value, semantic-review threshold and
artifact hash remains its exact `UNRESOLVED[P1_*]` marker. The loader rejects any unresolved runnable
specification. Do not add network libraries or credentials.

- [ ] **Step 4: Run integration and inherited guard suites**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_calibration_integration.py tests\test_calibration_contracts.py tests\test_calibration_specification.py tests\test_topic.py tests\test_persona.py tests\test_prompt.py tests\test_parser.py tests\test_mock_adapter.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add platform/src/agent_ex/calibration platform/src/agent_ex/__init__.py platform/configs/paper1/phase0a-probe.draft.yaml platform/tests/test_domain.py platform/tests/test_calibration_integration.py
git commit -m "feat(platform): complete Phase 0A offline probe dry run"
```

## Task 9: Release verification, documentation, and Phase 0A-1 handoff

**Files:**
- Modify: `docs/project-overview.md`
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`
- Create: `logs/2026-09-05-phase0a0-offline-probe.md`

- [ ] **Step 1: Run the complete verification suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest --cov=agent_ex --cov-report=term-missing -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: full and coverage suites pass with only documented platform-condition skips and the
explicit 50,000-event release-scale deselection; static, format, dependency and diff gates pass.

- [ ] **Step 2: Run authority and artifact hygiene gates**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_protocol.py tests\test_installation.py tests\test_calibration_integration.py
git ls-files platform | Select-String -Pattern '\.(sqlite|db|checkpoint|raw|coverage)$|__pycache__|\.pytest'
```

Expected: tests pass; tracked-artifact scan returns no matches. Verify the real draft remains
unrunnable and `docs/decisions.md` still has `records: []` unless separate owner approval occurred.

- [ ] **Step 3: Perform three independent read-only reviews**

Dispatch one specification reviewer, one code-quality reviewer, and one final-verification reviewer.
Give each the approved 2026-09-05 spec, this plan, exact implementation commit range and fresh test
evidence. Require P0--P3 findings, forbid edits, repair every confirmed P0--P2 with RED/GREEN evidence,
and re-dispatch the affected reviewer until approved.

- [ ] **Step 4: Record the verified handoff**

Use `logs/2026-09-05-phase0a0-offline-probe.md`. Record commit range, Python and
dependency identities, exact test counts, fixture/specification/case inventory/report hashes,
review outcomes, proof that no real model/network call occurred, and exact Phase 0A-1 blockers:
approved topic/persona text candidates, runtime policy, semantic-review policy, Qwen/vLLM candidate
stack, cloud credentials and archive location.

Update project docs to say `Phase 0A-0 complete / independently reviewed`; do not claim Phase 0A,
Phase 0B, formal readiness, or experimental results.

- [ ] **Step 5: Commit and push the verified checkpoint**

```powershell
git add docs/project-overview.md task_plan.md progress.md findings.md logs/2026-09-05-phase0a0-offline-probe.md
git commit -m "feat(platform): complete Phase 0A offline probe"
git push -u origin codex/paper1-phase0
git status --short --branch
```

Expected: branch and upstream are identical, worktree is clean, and `main` remains unchanged until
the Phase 0 branch is independently integrated.
