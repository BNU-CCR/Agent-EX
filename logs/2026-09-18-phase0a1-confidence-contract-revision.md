---
status: local-release-verified; pending exact approval and isolated cloud rerun
authority: Phase 0A-1 calibration measurement-contract correction checkpoint; no formal parameter authority
last-verified: 2026-09-18
---

# 2026-09-18｜Phase 0A-1 confidence contract revision

The first 816-case cloud run remains immutable and diagnostic-only. This checkpoint
replaces neither its evidence nor any frozen Paper 1 protocol. It records the local
release of a uniformly rendered confidence/format contract and a new, isolated v2
approval packet for a fresh 816-case calibration rerun.

## Implemented contract

- `6326f10` introduced one scale- and field-order-aware response renderer. Every
  semantic request now states that `stance` uses its declared stance scale,
  `confidence` represents certainty in the answer and is independent of stance,
  `confidence` is a JSON integer from 1 through 5, and `public_reason` is non-empty
  text of at most 2,048 characters.
- `e0c35d2` upgraded requests to `paper1.calibration.probe-request.v2` and bound each
  format repair to the original failed semantic attempt plus its immediate durable
  predecessor, including attempt, response, and parse-evidence hashes.
- `3c99b67`, `b3af351`, and `bc2e774` propagated that chain through transport retry,
  replay, resume, cloud persistence, and semantic review; required the exact
  `system/user/assistant/user` repair history; and materialized the v2 packet.
- `9f33821` synchronized the non-runnable human-readable draft with the already
  registered `P1_MAX_TOKENS` decision. The value remains
  `UNRESOLVED[P1_MAX_TOKENS]`; this does not grant formal parameter authority.
- The approved-specification group uses schema
  `paper1.calibration.approved-specification.v2`, response-contract version `2.0.0`,
  response-contract hash
  `d103b008af95117a72fa18e6f04eb5c268f33e6a05b54d1f2656cf5e50f8dfff`, and full
  case-inventory hash
  `93927a7266d6a7de115581d34e4efe054532e8d47c902e985151cf142c6908d1`.

## Replacement packet

- checked-in path:
  `platform/configs/paper1/phase0a1-approval-proposal-v2/`
- fresh archive URI:
  `/root/autodl-tmp/agent-ex-phase0a1-probe-816-v2`
- inventory: exactly 816 cases: 144 topic-quality, 96 identity, and 576 continuity
- combined packet hash:
  `3023380d393b4e1a50fbc6ae174281712111f706d2ffa6dce337419c7cf5e5b0`
- archive declaration:
  `341cb87a2b76147c17c6e32781589bc5dd64618eee9ef2db51cc8c9822e46a73`
- candidate manifest:
  `479fc2e5cb1864a04bb3c155abc00d56683de5b3125b6c4b3337c824e8b118a1`
- credential boundary:
  `595a19eb5f33ab0357177f30a233e54b6bfbc6608789fb765793cb3bf9cd3105`
- probe specification:
  `8c3541f0f38cd52aa29c30b60c6b7ad336e6ad22c079aeaf466a5f5f974cedce`
- runtime policy:
  `6f8a2d98316eb3eb87c217dedc460b258459c1c39209c0bf36d6742141675c80`
- semantic-review policy:
  `12012960c93b9c55c3ddeff0d7075d0bb5faec5e29b7a35bed7dbb13e2b4e6f9`

The v1 archive at `/root/autodl-tmp/agent-ex-phase0a1-probe-816-v1` remains excluded
from candidate comparison and must never be read as input to the replacement run.

## Verification evidence

- Combined confidence-contract suite:
  `237 passed in 375.98s` across specification, adapter/parser, runner, cloud run,
  review, vLLM adapter, and approval-packet tests.
- Initial full release run exposed two independent baseline defects while otherwise
  producing `1817 passed, 2 skipped, 1 deselected`: the old draft omitted the already
  registered max-token decision, and the local test environment lacked the locked
  build backend `setuptools==83.0.0`. After the draft synchronization and local
  environment repair, both exact regressions passed (`2 passed in 5.39s`).
- Fresh final full release run:
  `1819 passed, 2 skipped, 1 deselected in 3535.09s (0:58:55)`.
- Ruff lint passed for `platform/src`, `platform/tests`, and `platform/scripts`.
- Ruff format passed for all files touched by this revision. The full-tree format
  audit continues to report only the pre-existing, untouched
  `platform/tests/test_phase0a1_cloud_scripts.py` baseline mismatch (`97 files`
  already formatted); it is not silently rewritten in this release.
- `pip check` reported no broken requirements; `git diff --check` passed.
- Independent specification and code-quality re-reviews of `bc2e774` both returned
  `APPROVED`, with no P0--P3 findings. Their fresh focused verification also passed.

All pytest runs used an external temporary base directory because OneDrive can deny
cleanup of repository-local `.pytest-tmp`; that host behavior is not a product-test
failure.

## Remaining gate

No upload or cloud execution is authorized by this checkpoint. Before the fresh
816-case run, the owner must explicitly approve the exact final source bundle and
all six group hashes above. The uploaded bytes must match that approval, the v2
archive must be absent before launch, the actual-host environment lock and immutable
manifest must be rebuilt, and all 816 cases must execute into v2 only. Passing that
calibration gate still does not authorize Phase 0B or the formal N=1000/T=50 matrix.
