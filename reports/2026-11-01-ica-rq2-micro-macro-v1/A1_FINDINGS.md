# ICA2027: empirical findings from completed Qwen trajectories

Each network summary first gives A0 and A1 equal weight within a matched seed, then gives matched seeds equal weight. Paired identity effects are A1−A0 within seed/network. Brackets show the observed seed range, not confidence intervals. Undefined rates are retained as NA; valid-seed counts can therefore differ. Retirement T30 (10 seeds) and T60 (3 continuing seeds) are separate panels; each other T60 issue has 2 seeds. T60 prefixes are not additional replications. A round contains 500 weighted-with-replacement activations, not one activation of every agent. All private distributions contain 500 agents.

## RQ2-A: How do asymmetric updates accumulate into redistribution?

Networked interaction redistributes opinions toward stance 3, but its endpoint dominance is sharply issue-dependent rather than a universal consensus outcome.

### Magnitudes

| Panel | Network | Endpoint share 3 | Endpoint share 5 | Net count3 change | Net count5 change | Direct 5→3 events | Direct 3→5 events |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI job loss T60 (n=2 seeds) | B0 | 14.45% [14.40%, 14.50%]; n=2 | 28.30% [28.30%, 28.30%]; n=2 | 0.25 [0.00, 0.50]; n=2 | 69.50 [69.50, 69.50]; n=2 | 0.25 [0.00, 0.50]; n=2 | 0.00 [0.00, 0.00]; n=2 |
| AI job loss T60 (n=2 seeds) | B1 | 82.00% [80.10%, 83.90%]; n=2 | 3.05% [2.50%, 3.60%]; n=2 | 338.00 [328.50, 347.50]; n=2 | -56.75 [-59.50, -54.00]; n=2 | 168.50 [162.50, 174.50]; n=2 | 18.25 [17.00, 19.50]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | 72.60% [71.20%, 74.00%]; n=2 | 6.10% [6.00%, 6.20%]; n=2 | 291.00 [284.00, 298.00]; n=2 | -41.50 [-42.00, -41.00]; n=2 | 144.00 [143.50, 144.50]; n=2 | 15.00 [14.50, 15.50]; n=2 |
| GM market sales T60 (n=2 seeds) | B0 | 20.80% [20.40%, 21.20%]; n=2 | 15.85% [15.70%, 16.00%]; n=2 | 32.00 [30.00, 34.00]; n=2 | 7.25 [6.50, 8.00]; n=2 | 0.00 [0.00, 0.00]; n=2 | 5.00 [5.00, 5.00]; n=2 |
| GM market sales T60 (n=2 seeds) | B1 | 69.80% [67.70%, 71.90%]; n=2 | 21.35% [18.80%, 23.90%]; n=2 | 277.00 [266.50, 287.50]; n=2 | 34.75 [22.00, 47.50]; n=2 | 95.75 [87.00, 104.50]; n=2 | 16.50 [13.50, 19.50]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | 57.50% [54.40%, 60.60%]; n=2 | 24.85% [24.30%, 25.40%]; n=2 | 215.50 [200.00, 231.00]; n=2 | 52.25 [49.50, 55.00]; n=2 | 55.75 [51.50, 60.00]; n=2 | 16.00 [16.00, 16.00]; n=2 |
| Retirement T30 (n=10 seeds) | B0 | 15.07% [14.60%, 15.40%]; n=10 | 14.47% [14.40%, 14.60%]; n=10 | 3.35 [1.00, 5.00]; n=10 | 0.35 [0.00, 1.00]; n=10 | 0.00 [0.00, 0.00]; n=10 | 0.00 [0.00, 0.00]; n=10 |
| Retirement T30 (n=10 seeds) | B1 | 45.85% [43.50%, 50.10%]; n=10 | 35.86% [33.10%, 38.70%]; n=10 | 157.25 [145.50, 178.50]; n=10 | 107.30 [93.50, 121.50]; n=10 | 33.20 [26.00, 44.00]; n=10 | 4.80 [1.50, 10.50]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | 41.79% [37.70%, 44.90%]; n=10 | 37.42% [35.30%, 40.70%]; n=10 | 136.95 [116.50, 152.50]; n=10 | 115.10 [104.50, 131.50]; n=10 | 18.70 [12.50, 24.00]; n=10 | 4.35 [2.50, 7.00]; n=10 |
| Retirement T60 (n=3 seeds) | B0 | 15.17% [14.90%, 15.40%]; n=3 | 14.50% [14.40%, 14.60%]; n=3 | 3.83 [2.50, 5.00]; n=3 | 0.50 [0.00, 1.00]; n=3 | 0.00 [0.00, 0.00]; n=3 | 0.00 [0.00, 0.00]; n=3 |
| Retirement T60 (n=3 seeds) | B1 | 54.00% [50.50%, 56.90%]; n=3 | 33.47% [31.40%, 36.50%]; n=3 | 198.00 [180.50, 212.50]; n=3 | 95.33 [85.00, 110.50]; n=3 | 59.00 [43.00, 68.50]; n=3 | 6.17 [5.50, 6.50]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | 49.63% [48.20%, 51.10%]; n=3 | 36.90% [36.00%, 38.00%]; n=3 | 176.17 [169.00, 183.50]; n=3 | 112.50 [108.00, 118.00]; n=3 | 32.50 [27.00, 38.00]; n=3 | 5.67 [5.50, 6.00]; n=3 |

Figures: FigureA1_Asymmetric_Flows; Figure6_Realized_Exposure_Updating.

### Results

Serial event accounting links individual updates to population reorganization without treating repeated updates as new agents. AI job loss T60 (n=2 seeds): B2 endpoint shares were 0.726 at stance 3 and 0.061 at stance 5; GM market sales T60 (n=2 seeds): B2 endpoint shares were 0.575 at stance 3 and 0.248 at stance 5; Retirement T30 (n=10 seeds): B2 endpoint shares were 0.418 at stance 3 and 0.374 at stance 5; Retirement T60 (n=3 seeds): B2 endpoint shares were 0.496 at stance 3 and 0.369 at stance 5. The accompanying cell-level table reports direct 5→3 and 3→5 event counts separately from endpoint shares. These counts need not equal changes in group size because agents can leave, re-enter, or move through other stances. For every run and round, stance-specific cumulative inflow minus outflow equals its population change from round zero. Thus the dynamic concentration is supported by an exact accounting relationship, while its magnitude and direction remain specific to the issue, topology, and matched seed.

### Discussion

The flow decomposition treats collective agreement as a redistribution process rather than merely a smaller variance. A growing stance can attract agents from several origins while simultaneously losing some earlier occupants, so endpoint similarity alone obscures the underlying turnover. The contrast between direct updates and net accumulation is particularly important under attention-weighted repeated activation. These findings are compatible with recursive social influence because updated public posts may re-enter later feeds, but conservation itself does not identify amplification or persuasion. Issue semantics, initial-position dependence, unequal activation opportunity, and publication selectivity remain competing contributors to the observed macroscopic trajectory.

Competing mechanisms: Issue-specific response tendencies; initial-position dependence; repeated activation; selective publication; indirect paths through stance4; recursive re-exposure.
