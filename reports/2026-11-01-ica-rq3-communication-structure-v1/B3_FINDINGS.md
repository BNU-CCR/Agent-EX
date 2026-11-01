# ICA2027: empirical findings from completed Qwen trajectories

Each network summary first gives A0 and A1 equal weight within a matched seed, then gives matched seeds equal weight. Paired identity effects are A1−A0 within seed/network. Brackets show the observed seed range, not confidence intervals. Undefined rates are retained as NA; valid-seed counts can therefore differ. Retirement T30 (10 seeds) and T60 (3 continuing seeds) are separate panels; each other T60 issue has 2 seeds. T60 prefixes are not additional replications. A round contains 500 weighted-with-replacement activations, not one activation of every agent. All private distributions contain 500 agents.

## RQ3: How do topology, cues, and visibility organize opinions?

Across the issue-horizon means, stronger global convergence in B1 coexists with stronger distribution-adjusted local alignment in B2: collective concentration and local clustering are distinct outcomes.

### Magnitudes

| Panel | Variance B2−B1 | Excess alignment B2−B1 | Variance A1−A0, B1 | Variance A1−A0, B2 | Private/stock TV, B2 |
| --- | --- | --- | --- | --- | --- |
| AI job loss T60 (n=2 seeds) | 0.15 [0.14, 0.17]; n=2 | 0.08 [0.08, 0.09]; n=2 | 0.23 [0.14, 0.31]; n=2 | 0.16 [0.02, 0.29]; n=2 | 0.14 [0.14, 0.15]; n=2 |
| GM market sales T60 (n=2 seeds) | 0.46 [0.41, 0.52]; n=2 | 0.10 [0.08, 0.12]; n=2 | 0.26 [0.14, 0.38]; n=2 | -0.16 [-0.24, -0.08]; n=2 | 0.13 [0.12, 0.13]; n=2 |
| Retirement T30 (n=10 seeds) | 0.11 [-0.15, 0.38]; n=10 | 0.03 [-0.05, 0.05]; n=10 | 0.00 [-0.30, 0.22]; n=10 | 0.03 [-0.18, 0.13]; n=10 | 0.12 [0.10, 0.13]; n=10 |
| Retirement T60 (n=3 seeds) | 0.08 [-0.03, 0.21]; n=3 | 0.03 [0.02, 0.04]; n=3 | -0.04 [-0.31, 0.17]; n=3 | 0.05 [0.02, 0.08]; n=3 | 0.12 [0.12, 0.13]; n=3 |

Figures: Figure5_Communication_Structure; FigureS1_Private_to_Visible.

### Results

Matched-seed comparisons separate global concentration from fixed-network local alignment. AI job loss T60 (n=2 seeds): B2 variance was higher (Δ=0.155), and excess alignment was higher (Δ=0.084); GM market sales T60 (n=2 seeds): B2 variance was higher (Δ=0.463), and excess alignment was higher (Δ=0.098); Retirement T30 (n=10 seeds): B2 variance was higher (Δ=0.107), and excess alignment was higher (Δ=0.026); Retirement T60 (n=3 seeds): B2 variance was higher (Δ=0.081), and excess alignment was higher (Δ=0.029). Positive variance contrasts indicate weaker contraction in B2, whereas positive local contrasts indicate stronger excess same-stance alignment in B2. Negative contrasts imply the opposite ordering and are retained rather than interpreted through an assumed small-world advantage. Identity effects are the observed A1−A0 differences within issue, seed, and network; their raw ranges document heterogeneity without assigning causal mediation. Private opinions, newly published posts, the latest one public post per agent, and actually read slots are summarized separately. Thus endpoint agreement, adjacent-node similarity, and the public information encountered by receivers are related but nonidentical empirical objects.

### Discussion

Communication structure can influence the organization of agreement through both who is connected and which public posts are encountered. The fixed-count permutation baseline isolates excess adjacent similarity from the mechanical effect of a dominant population stance; it is a descriptive network reference, not a seed-level significance test. Public visibility also depends on publication and retention: the latest-post stock contains one post per agent, whereas feed slots can repeat older material. Identity contrasts remain conditional associations because the original joint Stage-A/B manipulation admission did not pass. Topology, evolving selection into exposure, content differences, and differential expression remain competing explanations that require separate controls.

Competing mechanisms: Global stance concentration; clustering and topology; endogenous exposure histories; publication/retention; joint identity-prompt differences. B0 edge metrics and edgeDID are undefined, not zero.

## Identity-cue conditional differences

| Panel | Network | Variance A1−A0 | Mean A1−A0 | Share3 A1−A0 | Share5 A1−A0 | Change rate A1−A0 | Excess alignment A1−A0 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI job loss T60 (n=2 seeds) | B0 | 0.05 [-0.02, 0.13]; n=2 | 0.02 [0.00, 0.03]; n=2 | -0.00 [-0.00, 0.00]; n=2 | -0.01 [-0.02, -0.00]; n=2 | -0.00 [-0.00, -0.00]; n=2 | NA (no defined opportunities) |
| AI job loss T60 (n=2 seeds) | B1 | 0.23 [0.14, 0.31]; n=2 | 0.17 [0.14, 0.21]; n=2 | -0.15 [-0.18, -0.13]; n=2 | 0.02 [0.01, 0.03]; n=2 | -0.00 [-0.00, -0.00]; n=2 | 0.08 [0.07, 0.09]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | 0.16 [0.02, 0.29]; n=2 | 0.08 [0.03, 0.14]; n=2 | -0.10 [-0.14, -0.06]; n=2 | 0.00 [-0.02, 0.03]; n=2 | -0.00 [-0.00, 0.00]; n=2 | 0.06 [0.06, 0.07]; n=2 |
| GM market sales T60 (n=2 seeds) | B0 | -0.01 [-0.04, 0.01]; n=2 | 0.02 [0.02, 0.03]; n=2 | -0.01 [-0.01, -0.00]; n=2 | 0.01 [0.01, 0.01]; n=2 | 0.00 [0.00, 0.00]; n=2 | NA (no defined opportunities) |
| GM market sales T60 (n=2 seeds) | B1 | 0.26 [0.14, 0.38]; n=2 | 0.16 [0.15, 0.17]; n=2 | -0.12 [-0.13, -0.12]; n=2 | 0.06 [0.06, 0.07]; n=2 | -0.00 [-0.00, -0.00]; n=2 | 0.04 [0.03, 0.05]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | -0.16 [-0.24, -0.08]; n=2 | 0.02 [-0.03, 0.07]; n=2 | 0.02 [-0.02, 0.06]; n=2 | 0.00 [-0.02, 0.03]; n=2 | -0.00 [-0.00, -0.00]; n=2 | -0.04 [-0.08, -0.01]; n=2 |
| Retirement T30 (n=10 seeds) | B0 | -0.05 [-0.11, 0.01]; n=10 | 0.00 [-0.01, 0.02]; n=10 | 0.00 [-0.00, 0.01]; n=10 | 0.00 [-0.00, 0.00]; n=10 | 0.00 [0.00, 0.00]; n=10 | NA (no defined opportunities) |
| Retirement T30 (n=10 seeds) | B1 | 0.00 [-0.30, 0.22]; n=10 | -0.03 [-0.17, 0.15]; n=10 | -0.01 [-0.10, 0.09]; n=10 | -0.01 [-0.07, 0.05]; n=10 | -0.00 [-0.00, 0.00]; n=10 | 0.01 [-0.03, 0.04]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | 0.03 [-0.18, 0.13]; n=10 | 0.03 [-0.04, 0.12]; n=10 | -0.02 [-0.06, 0.01]; n=10 | -0.01 [-0.04, 0.04]; n=10 | -0.00 [-0.01, 0.00]; n=10 | 0.00 [-0.02, 0.03]; n=10 |
| Retirement T60 (n=3 seeds) | B0 | -0.04 [-0.09, -0.01]; n=3 | 0.00 [-0.01, 0.01]; n=3 | 0.00 [-0.00, 0.01]; n=3 | 0.00 [0.00, 0.00]; n=3 | 0.00 [0.00, 0.00]; n=3 | NA (no defined opportunities) |
| Retirement T60 (n=3 seeds) | B1 | -0.04 [-0.31, 0.17]; n=3 | 0.04 [-0.21, 0.22]; n=3 | -0.02 [-0.10, 0.11]; n=3 | 0.01 [-0.09, 0.09]; n=3 | -0.00 [-0.00, 0.00]; n=3 | -0.00 [-0.01, 0.00]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | 0.05 [0.02, 0.08]; n=3 | 0.08 [0.06, 0.13]; n=3 | -0.06 [-0.07, -0.04]; n=3 | 0.02 [-0.03, 0.05]; n=3 | -0.00 [-0.00, -0.00]; n=3 | 0.01 [-0.00, 0.03]; n=3 |

Signs and seed ranges, rather than a universal cue effect, are the result. B0-based edge DID is undefined because B0 has no social edges; the separate B2−B1 paired identity contrast is a valid alternative, not a zero-filled B0 DID. The original Stage-A/B joint admission did not pass, and this report does not revise that verdict. Same-group/other-group source-conditioned updating is event-level association within an endogenous feed, not the fixed-message source-label control experiment.
