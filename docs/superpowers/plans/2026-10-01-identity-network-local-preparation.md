# Identity-network 2x3 Local Preparation Implementation Plan

> **For agentic workers:** Use executing-plans task-by-task. Execute inline.
> The independent spec reviewer returned Approved; the user's ten decisions
> authorize this work without another conceptual approval round.

**Goal:** Implement six-cell definitions, exact minimal groups, label visibility,
matched randomized networks and bounded manipulation-check materialization.

**Architecture:** Add `identity_network/` inside the existing platform package.
Reuse canonical hashes, ArtifactEnvelope, RNG, WS generator and diagnostics.
Keep old schemas/renderers intact; runtime integration follows preparation.

**Tech Stack:** Python 3.12, NetworkX 3.6.1, pytest 9.1.1, Ruff 0.15.20.

## Baseline and execution

Legacy tag: `legacy-2x2x3-2026-10-01`. It includes phase0 e3c0696 and main
28421fa with original Git parents. Persona/network/candidate baseline: 86 passed.
Set PYTHONPATH to the new worktree's `platform/src` and use the phase0
`.test-venv/Scripts/python.exe`; all tests use a fresh system temporary directory.

## Task 1 — Register the approved study

Files: AGENTS, decisions, research-qa, `docs/identity-network-protocol.md`, README,
task_plan. Add the new route, ten decisions and stable `SIS_*` unresolved IDs.
Do not change the legacy machine YAML/schema or impersonate frozen parameters.

- [ ] Write the documentation, check new-file whitespace and commit.

## Task 2 — Contracts and groups

Create `platform/src/agent_ex/identity_network/{__init__,contracts,groups}.py` and
`platform/tests/test_identity_network_groups.py`. Add only new namespaces to rng.

- [ ] Write tests using these exact APIs and observe missing-feature RED:

```python
cells = study_cells()
assert tuple(c.cell_id for c in cells) == (
    "SIS-A0-B0", "SIS-A0-B1", "SIS-A0-B2",
    "SIS-A1-B0", "SIS-A1-B1", "SIS-A1-B2",
)
artifact = build_group_assignment(initial_stances=stances, matched_seed=7)
groups = GroupContext.from_artifact(artifact)
assert groups.group_for("agent-001") in {"blue", "green"}
```

- [ ] Cover exact per-stance balance, input-order-independent replay, odd-stratum
  rejection, rehashed tampering, strict types and unchanged old RNG seeds.
- [ ] Implement deterministic per-stratum shuffling; validate GroupContext once
  and keep O(1), immutable membership lookups.
- [ ] Run groups, legacy RNG and artifact tests; lint/format and commit.

## Task 3 — Prompt visibility

Create `identity_network/prompts.py` and `test_identity_network_prompts.py`.

- [ ] Test `ShownPost` and `render_study_prompt` with fixed identical inputs:
  blind omits self/source group fields; salient adds them; all other content,
  history, persona, slots and output fields are identical.
- [ ] Test salient B0 self label, empty social feed, unknown sources, model-hidden
  backend membership and preservation of arbitrary original post content.
- [ ] Observe RED, implement immutable hashed StudyPrompt, then run new and
  legacy prompt/persona tests. No consistency instruction is introduced.

## Task 4 — Matched randomized graph

Create `identity_network/networks.py` and `test_identity_network_networks.py`.

- [ ] Test `build_randomized_counterpart(ws_artifact, matched_seed=seed,
  swap_target=target, max_trials=budget)`: exact per-node degree, connected
  simple graph, explicit source hash/budgets and deterministic replay.
- [ ] Test original-edge overlap is allowed, incomplete swaps fail, and rehashed
  edge/diagnostic drift fails `validate_randomized_counterpart`.
- [ ] Observe RED; implement bounded connected double-edge swaps with dedicated
  provenance; reuse existing structural report. Run new/legacy network tests.

## Task 5 — Manipulation-check pack

Create `identity_network/manipulation.py` and `test_identity_network_manipulation.py`.

- [ ] Test `build_manipulation_pack`: each explicit case yields Blue/Green
  receiver × same/other source, identical content/source IDs and paired sampling
  seeds, and fixed pre-state without shared carry-over updates.
- [ ] Test exact inventory, duplicate-case rejection, dispatch-order RNG, stage-2
  refusal without report/criteria approval receipt, and the one fixed neutral
  shared-group sentence from the spec.
- [ ] Observe RED; implement pure materialization with no HTTP, sample-size or
  success-threshold defaults. Run new preparation and targeted legacy tests.

## Task 6 — Handoff

- [ ] Record actual test evidence, commit and push the new branch; verify remote
  tip and archived tag. Do not merge into main or change the tag.
- [ ] Document the remaining runtime subproject: shared event-input/SQLite union
  integration, reconstructable committed traces, six-cell fake-HTTP execution,
  safe resume, CLI/report, then actual identity check and six-cell pilot.

The preparation milestone alone does not produce a runnable six-cell cloud
experiment. AutoDL is needed after runtime verification and an explicit small
candidate pack, not for any task in this local plan.
