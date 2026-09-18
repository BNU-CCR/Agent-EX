---
status: diagnostic-incomplete
authority: observed AutoDL run evidence; not a formal parameter decision
source-commit: 34cc5d49e275b26d48bd6eed6ff06a0d8ed19e6c
last-verified: 2026-09-18
---

# Phase 0A-1 first 816-case cloud run: diagnostic incomplete

The owner approved the exact six-group packet with combined record hash
`57abb85edbb7b1d28949ca523abaef6c4c4639a7744ca3bc7b5f5f57056f44bc`.
AutoDL applied the verified source bundle at commit
`34cc5d49e275b26d48bd6eed6ff06a0d8ed19e6c`, created an actual-host
environment lock and immutable run manifest, and executed the complete 816-case
inventory against the fixed Qwen3-8B revision.

## Cloud evidence

- checkout: `/root/autodl-tmp/agent-ex-phase0a1-b5320d8`
- run store: `/root/autodl-tmp/agent-ex-phase0a1-probe-816-v1`
- controls: `/root/autodl-tmp/agent-ex-phase0a1-probe-816-v1-controls`
- environment lock: `3ac170ee330bf409c2525aca8c958ce0a6ffc0d7f2a1517b3571ef3770d1d6b9`
- run manifest: `1811a2e4eedddebdacd4954103d2926e6540c8860265403679481f6787ac05af`
- projection file SHA-256: `4d35a4caad71233d7443c6d1ac6f128ef947ce4e1f0f62cdefccbdac570138a1`
- run evidence hash: `a1a30aacd609fab09feef1b6b673847fa3487c2689934be24935967e1076a0ba`
- terminal record: `78e521c40d638022be429ad6862b29d60740b96f0d186132c6ecf61d54250cd4`
- diagnostic audit report: `6e010a4d18d8a825bab01936623410d4a95122eb129812db25ee0110bd399f19`

The durable store contains exactly 816 unique cases and 1,511 attempts: 816
semantic attempts plus 695 format-repair attempts. Every request has a durable
dispatch intent, attempt, and resolution. All 1,511 transports returned a model
response. Inventory counts remain 144 topic-quality, 96 identity, and 576
continuity cases.

## Diagnostic outcome

The final projection is structurally complete but not eligible for candidate
comparison: 142 cases parsed and 674 ended in `parse_failed`. By family, the
final counts are:

- topic quality: 4 parsed, 140 parse-failed;
- identity: 0 parsed, 96 parse-failed;
- continuity: 138 parsed, 438 parse-failed.

The dominant failures are `confidence_type` and `confidence_range`. The
approved request renderer exposed stance anchors but omitted the independent
confidence contract (`JSON integer 1..5`). The format-repair request also did
not include the first raw answer as assistant history and only appended a
generic reminder, so the stateless endpoint could not reliably preserve the
substantive answer while repairing its format.

This is a common measurement-contract defect affecting every candidate and
case family, not evidence for comparing or rejecting topics. In accordance
with the predeclared rule that a dry/real pre-run defect must be revised before
candidate comparison, the run was irreversibly marked `incomplete` with reason
`measurement_contract_defect_missing_confidence_1_to_5_and_stateless_repair_context`.
No candidate was selected and the raw results remain outside Git.

## Required continuation

Create one uniform, versioned correction before inspecting candidate-level
substantive results: state that confidence is independent of stance and must be
an integer from 1 to 5; include the first raw answer in format-repair history;
restate the exact field order and both value ranges; add full-inventory and
repair-history regression tests. The corrected specification changes the
approval hashes and therefore requires a new source bundle, six-group approval,
actual-host environment lock, immutable manifest, and a fresh full 816-case
run. The diagnostic run must never be merged into that rerun or into formal
analysis.
