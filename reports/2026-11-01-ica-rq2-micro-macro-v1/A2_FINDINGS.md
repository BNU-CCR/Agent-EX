# ICA2027: empirical findings from completed Qwen trajectories

Each network summary first gives A0 and A1 equal weight within a matched seed, then gives matched seeds equal weight. Paired identity effects are A1−A0 within seed/network. Brackets show the observed seed range, not confidence intervals. Undefined rates are retained as NA; valid-seed counts can therefore differ. Retirement T30 (10 seeds) and T60 (3 continuing seeds) are separate panels; each other T60 issue has 2 seeds. T60 prefixes are not additional replications. A round contains 500 weighted-with-replacement activations, not one activation of every agent. All private distributions contain 500 agents.

## RQ2-B: What do realized exposure and directional response show?

With realized pure opposite-stance feeds, exact 5-to-3 adoption is more frequent than mirrored 3-to-5 adoption across the issue-network means, although the asymmetry varies markedly by issue.

### Magnitudes

| Panel | Network | 5→3 exact \| pure3 | 3→5 exact \| pure5 | Toward3 \| pure3 | Toward5 \| pure5 | Exact down−up (pp) |
| --- | --- | --- | --- | --- | --- | --- |
| AI job loss T60 (n=2 seeds) | B1 | 28.03% [25.71%, 30.34%]; n=2 | 0.15% [0.00%, 0.31%]; n=2 | 28.09% [25.71%, 30.47%]; n=2 | 0.15% [0.00%, 0.31%]; n=2 | 27.87pp [25.40pp, 30.34pp]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | 25.34% [20.82%, 29.85%]; n=2 | 0.30% [0.29%, 0.31%]; n=2 | 25.34% [20.82%, 29.85%]; n=2 | 0.30% [0.29%, 0.31%]; n=2 | 25.04pp [20.51pp, 29.57pp]; n=2 |
| GM market sales T60 (n=2 seeds) | B1 | 9.16% [8.52%, 9.80%]; n=2 | 1.07% [0.88%, 1.25%]; n=2 | 9.16% [8.52%, 9.80%]; n=2 | 1.07% [0.88%, 1.25%]; n=2 | 8.09pp [7.27pp, 8.91pp]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | 5.85% [5.35%, 6.36%]; n=2 | 1.14% [1.14%, 1.14%]; n=2 | 5.85% [5.35%, 6.36%]; n=2 | 1.14% [1.14%, 1.14%]; n=2 | 4.72pp [4.21pp, 5.23pp]; n=2 |
| Retirement T30 (n=10 seeds) | B1 | 5.54% [3.50%, 7.44%]; n=10 | 0.46% [0.09%, 1.13%]; n=10 | 5.54% [3.50%, 7.44%]; n=10 | 0.46% [0.09%, 1.13%]; n=10 | 5.09pp [3.29pp, 6.84pp]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | 3.06% [1.98%, 4.51%]; n=10 | 0.40% [0.00%, 0.75%]; n=10 | 3.06% [1.98%, 4.51%]; n=10 | 0.40% [0.00%, 0.75%]; n=10 | 2.66pp [1.56pp, 3.76pp]; n=10 |
| Retirement T60 (n=3 seeds) | B1 | 4.49% [2.54%, 5.56%]; n=3 | 0.29% [0.20%, 0.36%]; n=3 | 4.49% [2.54%, 5.56%]; n=3 | 0.29% [0.20%, 0.36%]; n=3 | 4.19pp [2.34pp, 5.24pp]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | 2.26% [1.93%, 2.57%]; n=3 | 0.26% [0.20%, 0.31%]; n=3 | 2.26% [1.93%, 2.57%]; n=3 | 0.26% [0.20%, 0.31%]; n=3 | 2.00pp [1.73pp, 2.26pp]; n=3 |

Figures: Figure6_Realized_Exposure_Updating.

### Results

We compared events starting at stance 5 with nonempty pure-3 feeds against events starting at stance 3 with nonempty pure-5 feeds. AI job loss T60 (n=2 seeds): the B2 exact-update contrast was 0.250; GM market sales T60 (n=2 seeds): the B2 exact-update contrast was 0.047; Retirement T30 (n=10 seeds): the B2 exact-update contrast was 0.027; Retirement T60 (n=3 seeds): the B2 exact-update contrast was 0.020. Contrasts are downward minus upward probabilities, expressed on the probability scale here and in percentage points in the table. Exact target adoption is reported separately from any strict reduction in distance to that target. Each condition retains its original numerator and opportunity denominator in the seed-level data; rates are not pooled across unequal exposure counts. Feeds consist of the public posts actually selected for each event, including legitimate older posts, rather than the current private states of all neighbors. The comparison therefore describes directional responsiveness within evolving exposure environments, not a fixed-message causal effect.

### Discussion

Unequal update probabilities can accumulate into substantial redistribution even when an individual response is uncommon. The pure-feed comparison holds the observed target stance fixed within each directional opportunity, but it does not equalize the endogenous histories producing those opportunities. Original P0 no-feed retention was 150/168, 153/168, and 161/168 for retirement, GM sales, and AI job loss, respectively; these are fixed one-step cases, not network replications. Selective agreement and conformity remain possible explanations, but numerical movement toward a local opinion is not sufficient evidence of sycophancy. No completed human semantic coding or experimentally identified sycophancy claim is made here.

Competing mechanisms: Starting-position and opportunity selection; unequal prior exposure; repeated sources or older posts; argument content; selective agreement; conformity. Semantic mechanism categories are not coded outcomes.
