---
status: smoke passed; six-group 816-run packet proposed, not yet approved
authority: execution evidence handoff; subordinate to frozen specifications and sealed evidence
last-verified: 2026-09-17
---

# Phase 0A-1 real smoke pass and 816-run approval proposal

## Real smoke result

The controlled AutoDL Qwen3-8B smoke completed successfully at source commit
`d99819a31357e6526d24ba9f0659ece9a806f803`. The run contains three correctly classified
transport diagnostics and ten unique first-attempt model responses split across the required
`9 -> verified stop -> recovery -> 1` lifecycle. The service was then stopped and port 8000 was
free; no model server remains running.

- evidence root: `/root/autodl-tmp/agent-ex-phase0a1-evidence-d99819a-20260917`
- run archive: `/root/autodl-tmp/agent-ex-phase0a1-evidence-d99819a-20260917/smoke-run-d99819a`
- smoke result hash: `4eee264bad889d17582d535dc688310a4b7b665c173c187cd8289fc45b39e53e`
- environment lock hash: `c4070d3848da73aa0a16fa1db0c9a4755bdc0238c12b7e84499bbbf00e7d3e91`
- smoke manifest hash: `e9c31e6db652dba4e4b8c872d8b0316ddb7fc89ef7873d71234c0936468d8770`
- sanitized Git log hash: `42fe5d0735fd9ec0fedec93265d4a3c2fd5b86f84166d3fc77e9e07634039b91`

This evidence authorizes no 816-case run, Phase 0B run, formal parameter freeze, or main
experiment by itself.

## Pre-run rendering correction

Approval-packet materialization found that the specification retained the seven main-scale
labels but the case renderer did not include them in request text. The renderer now includes all
seven topic-specific 1--7 anchors and explicit generic 0/10 agreement anchors for the challenger
scale. A regression test proves that every expanded request exposes its declared scale anchors.
The logical inventory remains exactly 816 cases.

## Proposal-only six-group packet

The deterministic materializer is
`platform/scripts/materialize_phase0a1_approval_packet.py`. The generated packet is stored under
`platform/configs/paper1/phase0a1-approval-proposal-v1/` and passes the production
`load_cloud_run_artifacts` loader with exact family counts 144 topic-quality, 96 identity, and
576 continuity.

The six proposal record hashes are:

- probe specification including gate algorithm:
  `89da9f9b1a9272773deab90456e45eca75b0ba40cfa90c5804b61c9a721ce1a2`
- runtime policy:
  `fd0b257747525dc79bd634ace413698ebfc1e95653b687c13c26dadf00e9d896`
- semantic-review policy:
  `12012960c93b9c55c3ddeff0d7075d0bb5faec5e29b7a35bed7dbb13e2b4e6f9`
- candidate model/runtime/generation manifest:
  `479fc2e5cb1864a04bb3c155abc00d56683de5b3125b6c4b3337c824e8b118a1`
- sanitized credential boundary:
  `595a19eb5f33ab0357177f30a233e54b6bfbc6608789fb765793cb3bf9cd3105`
- archive declaration:
  `ec7178c9ed68d9f3ff182cbe337e8a91192334fd069b68c951d7101785945342`

The combined proposal packet record hash is
`8467cc55fee0600e0f165531f1de0731dd5a09c3536ab4f70ce2f469e8937002`.

The semantic-review proposal assigns a fixed same-revision Qwen3-8B blind judge to every eligible
item and one human coder to a deterministic 174-item stratified sample. This is a proposal, not an
approval. The 816-case inventory must not execute until the owner explicitly approves all six
record hashes. After approval, a fresh actual-host environment lock and immutable run manifest
must be created before any request.

Raw smoke responses and future probe results remain outside Git.
