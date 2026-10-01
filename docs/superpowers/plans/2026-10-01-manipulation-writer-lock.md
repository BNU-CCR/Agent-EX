# Manipulation Writer Lock Implementation Plan

> **For agentic workers:** Use subagent-driven-development for this focused task, with spec review then code-quality review. Preserve all other changes in the existing isolated worktree.

**Goal:** Provide a Linux-only, nonblocking kernel lock which spans an independent manipulation runner session, including HTTP, without modifying legacy or granting dispatch.

**Architecture:** A focused lock module owns one persistent regular lock file in an existing trusted run root. An acquired lease checks owner PID and file identity; close releases the file descriptor without deleting/truncating evidence. Dedicated SQLite storage will consume this lease; neither store nor runner is claimed complete here.

**Tech Stack:** Python standard library (`fcntl`, `os`, `stat`, `pathlib`), pytest, existing Python/Ruff. No packages or cloud.

## Task 1 — Exclusive run lease

Create `platform/src/agent_ex/identity_network/manipulation_lock.py` and
`platform/tests/test_identity_network_manipulation_lock.py`. Public interface:

```python
with ManipulationRunLock.acquire(existing_root) as lease:
    lease.assert_held(existing_root)
# Closed leases must fail assert_held. acquire is Linux-only.
```

- [x] Write tests first: missing module; unsupported OS fails before any filesystem mutation;
  explicit simulated syscall boundary covers nonblocking contention, failure cleanup,
  context-exception close, repeated close, wrong root, replaced lock file and owner PID change.
  Add Linux-only real subprocess tests for contention and reacquisition after process death,
  plus rejection of symlink/nonregular lock files. Non-Linux must skip kernel tests, not emulate acceptance.
- [x] Run `python -m pytest platform/tests/test_identity_network_manipulation_lock.py -q --tb=short` and observe the missing-feature RED before implementing.
- [x] Implement the lease with the following exact safety behavior. `acquire` rejects non-Linux
  before opening/creating anything. Resolve an existing nonsymlink directory root; do not create
  the run root. Open `.manipulation-writer.lock` with `O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC`
  and mode `0o600`, without truncation. Verify regular file and pathname/fd inode identity.
  Acquire `fcntl.flock(fd, LOCK_EX | LOCK_NB)`; contention fails promptly, closes fd, preserves file.
  Check identity again after locking; any error closes fd. Descriptor is non-inheritable.
  Lease stores root, owner PID, fd/inode; `assert_held(root)` rejects closed lease, other root,
  other PID or replaced path. A directly constructed object must remain unacquired and fail
  `assert_held`; only a successfully completed `acquire` marks the lease held.
  It is a cooperative single-writer boundary, not protection against
  malicious directories/processes or SQLite writers ignoring the lease.

```python
# Operational shape, implemented with cleanup around all failure paths:
fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
# Keep descriptor open for the whole context, including future network calls.
# close uses os.close, never deletes the persistent file or truncates contents.
```

- [x] `close()` is idempotent, closes only the owned descriptor; no explicit `LOCK_UN`
  on a fork child's inherited open-file description. Reject use from a different PID.
  A reused `__enter__` must not silently reacquire a closed lease. If `__enter__` validation
  fails after acquisition, close the descriptor before rethrowing: Python will not call
  `__exit__` on entry failure. Cover this interval with a regression test.
- [x] Run the targeted tests, Ruff lint/format and `git diff --check`. Obtain separate spec
  and quality reviews. Fix significant issues with new RED tests and rerun. Controller saves
  docs/progress and commits after verification; worker does not commit unrelated files.

## Scope and next required deliveries

This realizes only the writer boundary in the approved independent-runner design.
The exact immutable SQLite plan, short durable intent/response/terminal transactions and
full prefix replay remain next. Runner/CLI/origin/240 source and research decisions remain
required; this lock never changes `cloud_launch_eligible=false` on the v1 request inventory.
Linux subprocess acceptance is explicitly pending when this plan is executed on Windows.
