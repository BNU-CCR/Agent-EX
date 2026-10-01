# SIS shared execution-input artifact

> **For agentic workers:** Implement inline with test-driven-development; retain the independent SIS branch.

**Goal:** Replace an opaque common-input reference with a verifiable candidate execution-input artifact before durable-prefix integration.

**Architecture:** A new pure builder records rendered persona for each agent, complete round-0 updates, explicit feed/memory/parser policy, generation settings, per-event model seeds, diagnostic adapter identity and retry policy. It binds the cell-independent parts of StudyRunBinding. A strict validator reconstructs the artifact and checks its output hash against common_inputs_hash. A read-only store entry derives request parameters from this artifact and verifies actual round-0 content before using the existing snapshot-request bridge. Legacy storage and event-write gates remain unchanged.

**Tech Stack:** Python, content-addressed ArtifactEnvelope, existing typed state/parser/diagnostic contracts and SQLite read interfaces.

## Task 1

- [x] Add `platform/tests/test_identity_network_execution_inputs.py`: missing builder/validator and store method RED, six-cell common hash, exact roster/initial-state and seed coverage, rehashed metadata/content rejection, actual SQLite initialization mismatch, bound request and no writes.
- [x] Run that file with isolated pytest temp/cache; observed 15 absent-module failures.
- [x] Add `identity_network/execution_inputs.py` with `build_execution_inputs` and `validate_execution_inputs`. Exact cell-independent binding fields: matched seed, group/topic/schedule identities, node roster, aliases, both graph hashes. Require initial-update exact cover and matching seed/topic/stance/round-0 semantics. Require positive explicit supported capacities/windows, parser/adapter/policy typed replay, full model-seed schedule cover, request generation settings validated by the existing request type. Rebuild and compare all envelope identities and payload metadata.
- [x] Add `StudyRunStorage.prepare_bound_snapshot_event(snapshot, common_inputs, *, attempt_index)`: lease, full common-artifact validation, exact actual round-0 update comparison, resolve current scheduled receiver and model seed, then call existing read-only bridge using only artifact settings. It does not authorize dispatch/retry or add writes.
- [x] Targeted SIS tests, Ruff/format/diff checks and focused review. Final storage regression: 353 passed, 2 environment skips. Independent review no Critical/Important. Documented precisely that attention/expression provenance and formal authorization remain separate requirements; no cloud run or complete durable prefix is claimed.

## Performance refinement, tested RED → GREEN

Repeated bound preparation originally reconstructed the full static artifact and rescanned round-0 rows twice. Counter test failed with 2 artifact validations/4 scans; immutable-object cache and reuse of the parent sealed integrity-replay cache reduced this to 1/1. Each preparation still checks database integrity first. Added same-connection/external-connection tamper detection and retained unsealed partial-store validation; reopened stores begin uncached. This is not a claim about actual model-loop throughput.
