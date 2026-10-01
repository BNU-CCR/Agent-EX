# Identity-network Storage Input Implementation Plan

> Execute inline with executing-plans and TDD in the existing feature worktree.

**Goal:** Make SIS event inputs reconstructable and immutable across retries,
and introduce explicit schema decoding without authorizing SIS in legacy stores.

**Architecture:** A separate typed input excludes attempt request identity. It
contains the full topic, parser, pre-state and prompt evidence needed for reopen.
Shared storage gets a discriminated decoder; existing stores still reject SIS.
This is Step 5b-1, not atomic runtime integration or a new standalone database.

**Tech Stack:** Python dataclasses, existing typed records, canonical hashes, pytest.

## Task 1 — Immutable event input

Files: identity_network/evidence.py, test_identity_network_evidence.py.

- [x] Test the absent API first:

```python
p1 = prepared(study_cells()[0], attempt_index=1)
p2 = prepared(study_cells()[0], attempt_index=2)
a = StudyEventInputEvidence.from_prepared(p1)
b = StudyEventInputEvidence.from_prepared(p2)
assert a.record_hash == b.record_hash
assert StudyEventInputEvidence.from_payload(a.to_payload()) == a
```

- [x] Implement strict fields and schema paper1.identity-network.event-input.v1;
  reject wrong hash, metadata, event/run identity, topic, actor, pre-state and
  visible projection, including rehashed tampering. Keep topic payload, not hash only.
- [x] Run six-cell JSON round trips, retries and negative cases.

## Task 2 — Shared discriminated reader

Files: storage.py and test_identity_network_evidence.py.

- [x] Test legacy decoding returns the original EventInputEvidence unchanged;
  SIS returns its own type; unknown schema fails.
- [x] Implement decode_event_input_payload by exact schema dispatch. Route the
  existing reader through it but reject SIS on legacy stores before returning it.
- [x] Test an inserted SIS row cannot be accepted as legacy execution evidence.

## Task 3 — Verify and record limits

- [x] Run new evidence, execution, legacy storage/diagnostic storage tests,
  Ruff lint/format and git diff check. Focused independent review.
- [x] Record actual results and remaining work in the feature branch milestone.

Next: SIS run binding and atomic writer/serial lifecycle, feed provenance,
checkpoint/reopen/resume, six-cell materializer. No dispatch or AutoDL in this step.
