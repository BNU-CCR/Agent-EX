---
status: preliminary-aggregate-ready; semantic review incomplete
authority: Phase 0A-1 fast-track handoff; no formal parameter or candidate-selection authority
source-run: /root/autodl-tmp/agent-ex-phase0a1-probe-816-v2
last-verified: 2026-09-20
---

# 2026-09-20 | Phase 0A-1 preliminary report fast track

## Purpose and boundary

This checkpoint exposes only deterministic, non-text aggregates from the completed real-Qwen
Phase 0A-1 calibration run so that a preliminary school report can be prepared without waiting
for the semantic-review pipeline. It is **not** a social-network experiment, a topic-selection
decision, a persona freeze, a final gate report, or evidence for a Paper 1 treatment effect.
Raw responses and `public_reason` text were neither printed nor copied into this checkpoint.

## Authoritative cloud artifacts

- archive: `/root/autodl-tmp/agent-ex-phase0a1-probe-816-v2`
- controls: `/root/autodl-tmp/agent-ex-phase0a1-probe-816-v2-controls`
- approved-artifacts record hash:
  `3023380d393b4e1a50fbc6ae174281712111f706d2ffa6dce337419c7cf5e5b0`
- run-manifest record hash:
  `edbc8afedecf5f9a964b7108a5e29b9e3d86c1ff122ba41e4693b62ff09a808f`
- case-inventory hash:
  `93927a7266d6a7de115581d34e4efe054532e8d47c902e985151cf142c6908d1`
- control projection file SHA-256:
  `d526beb57e962dda094b7222fc051cc366fd683dc084b2a76dc21ea3a8359135`
- reconstructed run-evidence hash:
  `2a5c713b10c0e9b2dec677507aa2230f9a34845828f4605f6b569f5d75783399`
- semantic-review bundle record hash:
  `b91c9bb2f77d450ea4b85d01b1cdda74ea67f611447523df2c49162faaff626a`
- blind-review export hash:
  `11e2cb9f8ae6d511401fd25cbed190cc6970cd575ec1754e2ece9cd7e3cf8d8d`
- blind coder-pack index record hash:
  `ae88ca478791b0304f52268170466e3a2b50ce84c55dfaaa6666edc5ed286575`

The run projection is `complete`, but the semantic-review bundle is still `awaiting_codes`.
There is no final `ProbeReport`, gate report, sealed bundle, or irreversible cloud terminal
record yet.

## Fresh reconstruction and deterministic results

The platform's strict loaders reopened the approved artifacts and manifest, the append-only
store was replayed with `reconstruct_cloud_projection`, the result was byte-for-structure
compared with `projection-run.json`, and `fold_case_attempts` revalidated the complete case
inventory and attempt bindings.

- scheduled cases: 816 exactly
- family inventory: 144 topic-quality, 96 identity, 576 continuity
- terminal machine statuses: 797 parsed, 19 parse-failed
- all 19 parse failures are in topic-quality; identity and continuity are 96/96 and 576/576
  parsed respectively
- attempts: 841 total = 816 semantic + 25 format repair
- transport: 841/841 returned responses; no typed transport error
- termination: 839 `stop`, 2 `length`
- input/output/total tokens: 312,720 / 68,944 / 381,664
- response latency: mean 0.874 s, p50 0.894 s, p95 1.173 s, max 1.361 s
- observed run wall clock: 1,386.418 s (about 23.1 minutes)
- semantic assignments already materialized: 797 judge items and 174 human items
- imported semantic codes, adjudications, and final labels: 0 / 0 / 0

Candidate-key mapping and purely mechanical terminal counts are:

| candidate | all cases | parsed | parse-failed |
|---|---:|---:|---:|
| retirement-delay | 272 | 262 | 10 |
| gm-soybean-oil | 272 | 272 | 0 |
| ai-net-employment | 272 | 263 | 9 |

This table may be presented only as **mechanical parse performance**. It is not a semantic
quality ranking and does not authorize selecting `gm-soybean-oil`; the approved preselection
rule still requires completed semantic review and the final gate algorithm.

## Preliminary aggregate artifact

The aggregate is stored outside Git and contains counts, token/latency summaries, and stance/
confidence frequency tables only:

- path:
  `/root/autodl-tmp/agent-ex-phase0a1-preliminary-20260920/machine-aggregate-v1.json`
- file SHA-256:
  `a099c45e57eaf965e2f9e24abd806fc2836ed9fb5dcd1ae1afeb1e14c4d999d9`
- canonical record hash:
  `fb40c60199398b8f50294ffdc0f792327e15733130f24cf0a14bf339388dc8c1`
- aggregation inline-script SHA-256:
  `0d13ccf5ce4fac1e04b4d5abab38b6fbe857da50ac88c047620e44f92baab6d6`

The exact execution boundary was:

```bash
cd /root/autodl-tmp/agent-ex-judge-perf-bf2f63a
PYTHONPATH=platform/src \
  /root/autodl-tmp/phase0a1-venv-d1f72f9/bin/python < aggregate-script-0d13ccf5ce4fac1e04b4d5abab38b6fbe857da50ac88c047620e44f92baab6d6.py
```

The script was supplied over standard input rather than saved as a separate executable; the
hash above identifies the exact UTF-8 script bytes. Its only write target was the create-or-
exact-match aggregate path above.

## Existing CLI/report capability and minimum gap

The existing CLI can reconstruct the durable projection, but `verify` proceeds immediately to
`build_cloud_probe_report`. Because the cloud store intentionally has no terminal marker while
semantic review is pending, that command ends with:

`RuntimeError: recoverable staging store cannot build or seal a terminal report`

Accordingly:

1. Existing validated domain loaders can safely rebuild deterministic machine aggregates now.
2. The final `ProbeReport`, candidate gate result, freeze proposal, and sealed bundle cannot be
   built until judge/human codes, any adjudication, and final labels are imported.
3. The repository has no validated chart-rendering command for this intermediate state. Charts
   for the school report should therefore be thin views over the hash-bound aggregate and carry
   the same `preliminary / diagnostic` label; they must not recompute or reinterpret gates.

## Earliest deliverables and blockers

- Available immediately: a one-slide execution/measurement summary based on the aggregate:
  816 real calibration cases, 97.67% final parse success, 25 repairs, 23.1-minute wall clock,
  no transport errors, and the explicit semantic-review disclaimer.
- Available immediately: mechanical parse-performance and token/latency charts derived from
  `machine-aggregate-v1.json`.
- Blocked pending 797 judge codes and 174 human codes: semantic quality pass/fail, agreement,
  adjudication, candidate selection, persona freeze, final gate report, and sealing.
- Independently blocked from these 816 calibration artifacts: any claim about network dynamics,
  polarization, treatment effects, confidence intervals, or p-values. Those require the separate
  Phase 0B real event-adapter run.
