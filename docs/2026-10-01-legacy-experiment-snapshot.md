# 2026-10-01 legacy experiment snapshot

This is a reproducibility checkpoint of the previous experiment, before the
approved social-identity/network 2x3 implementation begins. It preserves Git
history; it does not certify that a formal real-model experiment has finished.

- Source implementation: `codex/paper1-phase0`, commit
  `e3c0696cd398d4636e67b87ce2ee2f34c9f0a5a6`.
- Main documentation: `28421fae9b8ee3adfec7d3b39cdc5e700c3e26e0`, merged with
  both parents retained. Before integration these branches had 29 phase0-only
  commits and one main-only commit.
- GitHub archive branch: `codex/legacy-experiment-20261001`.
- Archive tag: `legacy-2x2x3-2026-10-01` (points at the completed snapshot).
- New implementation branch: `codex/social-identity-network-2x3`.

## Evidence status

The legacy protocol is demographic identity 2 x continuity 2 x exposure 3.
The N=20/T=2 480-event SQLite path has local synthetic HTTP tests; a real
480-event network experiment has not been executed. Phase0A-1 judge v2 has
797 terminal coded items; that calibration is distinct from dynamics data.
Historical pilot results and new submission figures must retain their original
design and provenance.

## Additional files preserved

`submission/` contains the local proposal versions, the final-named DOCX/PDF,
and the associated image as they existed on 2026-10-01. Presence here does not
prove email submission or validate the reported pilot results.

The latest research handoff and 09-28 feedback are in `docs/`. They are source
discussion documents, not changes to this archived protocol.

Three untracked source files from the phase0 worktree are copied byte-for-byte
under `docs/archive/2026-10-01-uncommitted-source/`, with their relative paths:

- `platform/scripts/phase0a1-safe-label-export.py`
- `platform/src/agent_ex/calibration/safe_label_export.py`
- `platform/tests/test_phase0a1_safe_label_export.py`

These are unfinished working-copy material, not installed runtime code and not
release-verified. Their original working copies remain in the phase0 worktree.
They are archived separately so the tracked runtime baseline is unchanged.

## Exclusions and recovery

Credentials (`ssh.txt`, keys, environment files), `.codex/`, virtual environments,
test scratch directories, raw model responses, cloud result stores and generated
transfer bundles are not included. This is a source/history backup; external
experiment data still require their separate archive copies and manifests.

To inspect this snapshot without changing an existing worktree:

```sh
git fetch origin refs/tags/legacy-2x2x3-2026-10-01:refs/tags/legacy-2x2x3-2026-10-01
git worktree add --detach ../agent-ex-legacy legacy-2x2x3-2026-10-01
```

The local Git object store has a missing Codex internal checkpoint object which
currently makes ordinary fetch fail. The project branch histories can still be
read and pushed explicitly; no internal refs or user work were removed. A fresh
GitHub checkout does not depend on these local Codex-only refs.
