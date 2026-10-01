---
status: approved research direction; implementation in progress
authority: user decisions of 2026-10-01; new study family, not a reinterpretation of legacy runs
supersedes: legacy I x C x E matrix and its fixed sample size for future main-study work only
---

# Social identity salience × communication network structure

## Approved boundary

The user approved ten decisions on 2026-10-01: the main study is 2×3;
demographic persona and memory are common; explicit consistency is off;
publication remains externally scheduled; minimal groups are balanced and
orthogonal to initial stance; pure-label manipulation checks precede a single
predefined neutral framing stage; randomized networks use degree-preserving
rewiring; actual event evidence is reconstructable; no automatic sycophancy
classifier; formal sizes and the primary metric are frozen later; complete
phase0 implementation and legacy reproducibility are preserved.

The source discussion is `docs/2026-10-01-latest-research-and-code-handoff.md`.
When that document differs (for example, LLM-autonomous publication), these
explicit decisions govern. Example K=3/B=6 values are not formal defaults.

## Git and source identity

Legacy source is archived at tag `legacy-2x2x3-2026-10-01` and branch
`codex/legacy-experiment-20261001`. It includes phase0 source e3c0696, main
documentation 28421fa, submission versions and separately archived uncommitted
exporter source. The new branch is `codex/social-identity-network-2x3`, based on
that snapshot. No `platform1/` copy is created. Old schemas, cell IDs, RNG
derivations, authorization and report meanings remain available for old runs.

## Study definition and compatibility

Use a new study ID `paper1.identity-network.v1` and six namespaced cell IDs
`SIS-A0-B0`, `SIS-A0-B1`, `SIS-A0-B2`, `SIS-A1-B0`, `SIS-A1-B1`, `SIS-A1-B2`.
A0 is group-blind, A1 is group-salient. B0 has no social feed, B1 reads the
randomized graph, B2 reads the WS graph. Never pass these IDs through old
12-cell validators or relabel a P1-I/C/E result as a new-study result.

Add study-specific preparation modules under `platform/src/agent_ex/identity_network/`.
Share canonical hashing, RNG provenance, TopicPackage, initialization, serial
engine, private/public state, feed/memory selection, provider transport and
storage transaction primitives. Version new prompt/evidence contracts where
legacy types encode factor semantics; extend storage union readers only with
discriminated schemas and legacy replay tests. Do not weaken a legacy validator
to accept unrelated data. Preparation modules alone are not a cloud runner.

## Common inputs and groups

Within one matched seed the six cells reuse population, initial private states,
round-0 reasons/posts, neutral member IDs, group membership, WS/randomized
graphs and mapping, attention weights, publication propensity, activation and
publish schedule, memory/feed policy, topic, model revision and generation
settings. Each cell maintains independent mutable state and a separate store.
The common demographic persona is the existing identity-present rendering with
continuity absent; membership visibility is the only identity treatment.

Use Blue and Green groups. Assignment is deterministic from a dedicated RNG
namespace and shuffled independently inside each initial stance stratum, with
exactly half assigned to each group. Exact equal stance distributions require
even counts in every nonempty stratum. If this is impossible, fail before a run;
do not silently change initial opinions, round quotas, drop agents or relax
orthogonality. Pilot input counts will be explicitly chosen to meet the contract.
Report demographic/reason-family balance diagnostics; stance balance does not
automatically prove balance on every other characteristic.

## Prompt treatment

Build a structured social message from the exact selected public post and its
stable anonymous source ID. Backend source-group metadata is saved in both A
conditions. A0 prompt contains neither self group nor source group fields,
membership hashes, treatment IDs or group-derived member IDs. A1 adds the
receiver's group and each shown post's source label. For a fixed input the two
renderings must otherwise be identical, including persona, history, content,
message selection/order, fact card and output contract. B0 has an empty social
feed even in A1; A1B0 still displays self membership.

Do not add trust, favoritism, loyalty, group stance or directional consistency
instructions. Natural-language posts are untrusted data. Hidden confidence and
unpublished reasons never enter another agent's social context. User-provided
post text may itself mention a group: visibility rules suppress system metadata,
not naturally generated message content; any such mentions must be auditable.

## Matched networks

Reuse the original WS generator where its explicit candidate inputs apply.
Add a new randomized graph algorithm using bounded, connected double-edge
swaps. Preserve every node's degree, disallow loops/parallel edges and require
connectivity. Unlike legacy shadow, overlapping original WS edges are allowed.
Budget and accepted swap target are explicit candidate inputs; failure to reach
the target is an error. Record attempted/accepted swaps, RNG provenance and
source WS identity. Report clustering, mean shortest path, full degree sequence,
components and connectivity for both graphs. Successful rewiring alone does
not guarantee a low clustering comparison or identify a pure clustering effect.
Any structural acceptance criterion is bound before model outcomes are read.

## Publication, serial events and evidence

The existing externally generated publish flag governs publication. Model
output remains stance, confidence and reason. When publishing, the existing
protocol makes this event's stance/reason the public output; no second model
call or autonomous publish decision is introduced. A nonpublishing event still
updates private state and leaves the public stock unchanged.

Each committed event must bind run/study/cell identity, event ordinal and
activation, pre-state and confidence, potential neighbor IDs, candidate post IDs,
expired/selected IDs, exact shown text and slot order, source IDs and groups,
visible stance context, post-state/reason/confidence, publish flag, public output
or its absence, request/response/parse hashes and prior event hash. Derived local
means, majority ties and group counts have explicit definitions and are computed
only from actually shown messages. Empty-feed context is null/empty, not zero.
Keep raw evidence outside Git; export descriptive summaries with provenance.

State commits remain strictly serial inside a run; failed attempts do not change
state or cursors. Pre-dispatch intent persists before sending; ambiguity stops
without resending. Independent cells may run concurrently only after a measured
performance gate. Existing journal/checkpoint/SQLite logic is retained.

## Manipulation check

Preparation is independent of the old 816/797 calibration. A case fixes topic,
persona, pre-state/history, anonymous source, message content and model seed.
Create four paired variants: receiver Blue/Green × same-/other-group source.
Source identity/content is held constant within each receiver's pair; only the
source-group label changes. Counterbalance receiver labels and randomize
dispatch order with a separate registered namespace. Do not update a shared
agent state between variants. Bind the pack identity, renderer version and
generation parameters before launch. Evidence preserves reason and confidence;
descriptive movement alone is not a sycophancy label or proof of persuasion.

Stage 1 uses pure labels. The one permitted stage 2 uses this fixed, stance-neutral
sentence: `You participate in a stable discussion group called {label} throughout
this discussion.` It does not claim a completed shared task, instruction to
favor a group, or a pre-existing shared opinion. Stage 2 requires an independently
recorded stage-1 report hash, preregistered criteria hash and researcher decision
that the stage-1 check has no signal. Sample size, success/no-signal criteria and
stage transition receipts must be concrete before a real check. No automatic
prompt search or threshold selection from attractive results is allowed.

## Analysis and remaining freeze

Private state remains the primary state layer; public stock, public flow and
expression gap remain available. Descriptive mean/distribution/dispersion,
middle/endpoint share and event movements are separate from a formal primary
metric. Formal N, T, seeds, primary outcome/estimand and inference are unresolved
under `SIS_*` IDs in research-qa. Old N=1000/T=50/10-seed authority is not silently
inherited. All new output is preliminary/not_frozen until a new formal protocol
passes its own complete freeze. There is no automatic sycophancy classifier.

## Delivery order and acceptance

1. Archive and verify GitHub refs; register this spec and the approved decisions.
2. Implement six-cell contracts, exact group assignment, common persona and
   visible prompt projections; test blindness and deterministic round trips.
3. Implement matched rewiring and diagnostics; verify degree and connectivity
   without looking at opinion outcomes.
4. Materialize the fixed stage-1/stage-2 manipulation variants and transitions;
   test content/seed matching and rejection of unapproved stage 2.
5. Connect new prompt/evidence schemas to shared serial execution and SQLite;
   test complete six-cell synthetic execution, atomic failures, reopen/resume and
   reconstructable event traces; produce a standalone run/verify/report entry.
6. Prepare a small explicit manipulation-check candidate and measure inference
   and storage time when the user starts a server. Existing source backup and
   local preparation do not require AutoDL.
7. Run a six-cell pilot with a separately bound candidate config, analyze real
   trajectories, then freeze the formal study before increasing scale.

Completion of steps 2–4 is a local preparation milestone. It must not be described
as completion of steps 5–7 or production of new-model experimental data.
