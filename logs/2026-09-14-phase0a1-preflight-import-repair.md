---
status: authoritative preflight complete; stopped at smoke authorization boundary
authority: sanitized Phase 0A-1 cloud execution checkpoint; raw evidence remains outside Git
last-verified: 2026-09-15
---

# 2026-09-14｜Phase 0A-1 preflight import-boundary repair checkpoint

## Outcome and authority boundary

The failed source-bound cloud preflight was sealed as a separate failure receipt. An
exact repaired Git bundle was then used to create a clean checkout at
`6711a6d767cc1993db1d823d183bb125070c107e`, and the authoritative source-bound
preflight completed successfully before project installation.

The resulting record is `calibration_only: true` and
`formal_parameter_authority: false`. It grants no authority to install dependencies,
download a model, start vLLM, send a model request, or run smoke. Execution stopped at
Task 9 Step 2 of
`docs/superpowers/plans/2026-09-10-paper1-phase0a1-cloud-probe-implementation.md`,
where a separately approved smoke manifest is still required. The server has since
been shut down by the owner.

## Sealed failed attempt

- Failed checkout commit: `14cffa67bcdc36d2e4f2f8628812259a322bb9d1`.
- Preserved failed checkout: `/root/autodl-tmp/agent-ex-phase0a1-failed-14cffa6`.
- Cloud receipt:
  `/root/autodl-tmp/agent-ex-phase0a1-evidence/failed-preflight-14cffa6.json`.
- Local external copy:
  `C:\Users\Bai Yuexi\AppData\Local\Temp\agent-ex-phase0a1-evidence\failed-preflight-14cffa6.json`.
- Receipt SHA-256:
  `491a88c6bc4eb342c479b32a73e2e00732aa1298cbc65698cb94f15841c61bd0`.

The receipt records a clean checkout, Python 3.12.3, NetworkX 3.5, exit code 1, the
expected dependency-guard error, an absent preflight output, and false values for
install, model-download, server-start, model-request, and smoke authority.

## Exact repaired deployment

- Local bundle:
  `C:\Users\Bai Yuexi\AppData\Local\Temp\agent-ex-phase0a1-6711a6d.bundle`.
- Cloud bundle: `/root/autodl-tmp/agent-ex-phase0a1-6711a6d.bundle`.
- Bundle size: `2,140,185` bytes.
- Bundle SHA-256:
  `a52870ac6b811e1e182132cb245593b25606c7df5c21730c54a81d598a8f3786`.
- Repaired checkout: `/root/autodl-tmp/agent-ex-phase0a1`.
- Repaired clean HEAD: `6711a6d767cc1993db1d823d183bb125070c107e`.
- Verified source binding:
  `/root/autodl-tmp/agent-ex-phase0a1/platform/src/agent_ex/__init__.py`.

The bundle's actual archived name above differs from the illustrative
`agent-ex-phase0a1-repaired.bundle` name in the implementation plan; its exact commit,
size, and equal local/cloud hash provide the binding used for this execution.

## Authoritative preflight evidence

- Cloud record: `/root/autodl-tmp/agent-ex-phase0a1-evidence/preflight.json`.
- Local external copy:
  `C:\Users\Bai Yuexi\AppData\Local\Temp\agent-ex-phase0a1-evidence\preflight-6711a6d.json`.
- File SHA-256:
  `d6c599570b91d8f29905e454618be6b61a2f1850e62d936b5792975867d5da31`.
- Canonical `record_hash`:
  `5e51819d3e6a8b9e1232b1142c77f06d16fa29620eccb84d6bc296d80e9f685e`.
- Git binding: commit `6711a6d767cc1993db1d823d183bb125070c107e`,
  `git_dirty: false`.
- Observed accelerator: exactly one NVIDIA GeForce RTX 5090.
- Authority flags: `calibration_only: true`,
  `formal_parameter_authority: false`.

The local external copy reopened successfully through `CloudPreflight.from_payload`,
including the canonical hash, exact clean Git binding, single-GPU observation, and
authority flags. Neither raw JSON artifact nor the Git bundle is tracked in Git.

## Local release-gate status

The first complete non-release-scale suite attempt reported
`1726 passed, 2 failed, 2 skipped, 1 deselected in 4716.74s`. Both failures were the
adapter-facade import cycle subsequently repaired in Task 3A. After the repair, the
five-test minimal cycle gate passed and the focused compatibility gate reported
`182 passed`.

The owner explicitly requested that the roughly 80-minute complete suite not be rerun
before cloud preflight. Accordingly, that full gate is deferred, Task 4 remains open,
and neither the failed first attempt nor the focused gates are recorded as proof that
the complete suite passes after the repair.

## Prohibited actions confirmed absent

Before and during both preflight attempts, no dependency was installed, no model was
downloaded, no vLLM server was started, and no model request was sent. Smoke authority
was not granted or exercised. The next allowed action remains review and separate
approval of the smoke manifest; preflight completion alone does not cross that boundary.
