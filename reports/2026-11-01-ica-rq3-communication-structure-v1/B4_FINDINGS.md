# ICA2027: empirical findings from completed Qwen trajectories

Each network summary first gives A0 and A1 equal weight within a matched seed, then gives matched seeds equal weight. Paired identity effects are A1−A0 within seed/network. Brackets show the observed seed range, not confidence intervals. Undefined rates are retained as NA; valid-seed counts can therefore differ. Retirement T30 (10 seeds) and T60 (3 continuing seeds) are separate panels; each other T60 issue has 2 seeds. T60 prefixes are not additional replications. A round contains 500 weighted-with-replacement activations, not one activation of every agent. All private distributions contain 500 agents.

## From private opinions to visible public expressions

Canonical public stock retains only the latest public post per agent (500 posts), including unreplaced round-zero posts. New expression is the current round's publication flow; realized exposure is the multiset of selected feed slots. Neither is replaced by the cumulative archive of every historical post.

| Panel | Network | Agent absolute gap | Private/stock TV | Ordinal Wasserstein | Stock mean age | Stock age≥5 | Last-round stock TV change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI job loss T60 (n=2 seeds) | B0 | 0.04 [0.04, 0.04]; n=2 | 0.03 [0.03, 0.03]; n=2 | 0.04 [0.04, 0.04]; n=2 | 16.71 [16.65, 16.77]; n=2 | 46.40% [44.20%, 48.60%]; n=2 | 0.00 [0.00, 0.00]; n=2 |
| AI job loss T60 (n=2 seeds) | B1 | 0.37 [0.35, 0.38]; n=2 | 0.15 [0.14, 0.16]; n=2 | 0.34 [0.32, 0.35]; n=2 | 16.71 [16.65, 16.77]; n=2 | 46.40% [44.20%, 48.60%]; n=2 | 0.00 [0.00, 0.00]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | 0.35 [0.34, 0.36]; n=2 | 0.14 [0.14, 0.15]; n=2 | 0.32 [0.31, 0.33]; n=2 | 16.71 [16.65, 16.77]; n=2 | 46.40% [44.20%, 48.60%]; n=2 | 0.00 [0.00, 0.00]; n=2 |
| GM market sales T60 (n=2 seeds) | B0 | 0.08 [0.07, 0.08]; n=2 | 0.05 [0.04, 0.05]; n=2 | 0.08 [0.07, 0.08]; n=2 | 16.71 [16.65, 16.77]; n=2 | 46.40% [44.20%, 48.60%]; n=2 | 0.00 [0.00, 0.00]; n=2 |
| GM market sales T60 (n=2 seeds) | B1 | 0.33 [0.32, 0.35]; n=2 | 0.14 [0.13, 0.15]; n=2 | 0.30 [0.27, 0.32]; n=2 | 16.71 [16.65, 16.77]; n=2 | 46.40% [44.20%, 48.60%]; n=2 | 0.00 [0.00, 0.01]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | 0.31 [0.30, 0.32]; n=2 | 0.13 [0.12, 0.13]; n=2 | 0.22 [0.21, 0.24]; n=2 | 16.71 [16.65, 16.77]; n=2 | 46.40% [44.20%, 48.60%]; n=2 | 0.00 [0.00, 0.00]; n=2 |
| Retirement T30 (n=10 seeds) | B0 | 0.03 [0.02, 0.05]; n=10 | 0.03 [0.02, 0.05]; n=10 | 0.03 [0.02, 0.05]; n=10 | 9.78 [9.26, 10.52]; n=10 | 44.72% [42.00%, 49.00%]; n=10 | 0.00 [0.00, 0.00]; n=10 |
| Retirement T30 (n=10 seeds) | B1 | 0.26 [0.22, 0.29]; n=10 | 0.13 [0.11, 0.14]; n=10 | 0.21 [0.19, 0.24]; n=10 | 9.78 [9.26, 10.52]; n=10 | 44.72% [42.00%, 49.00%]; n=10 | 0.01 [0.00, 0.01]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | 0.23 [0.19, 0.26]; n=10 | 0.12 [0.10, 0.13]; n=10 | 0.18 [0.15, 0.21]; n=10 | 9.78 [9.26, 10.52]; n=10 | 44.72% [42.00%, 49.00%]; n=10 | 0.01 [0.00, 0.01]; n=10 |
| Retirement T60 (n=3 seeds) | B0 | 0.03 [0.03, 0.05]; n=3 | 0.03 [0.02, 0.04]; n=3 | 0.03 [0.03, 0.05]; n=3 | 16.61 [16.42, 16.77]; n=3 | 45.73% [44.20%, 48.60%]; n=3 | 0.00 [0.00, 0.00]; n=3 |
| Retirement T60 (n=3 seeds) | B1 | 0.28 [0.27, 0.28]; n=3 | 0.13 [0.12, 0.13]; n=3 | 0.23 [0.22, 0.24]; n=3 | 16.61 [16.42, 16.77]; n=3 | 45.73% [44.20%, 48.60%]; n=3 | 0.00 [0.00, 0.00]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | 0.25 [0.22, 0.27]; n=3 | 0.12 [0.12, 0.13]; n=3 | 0.18 [0.16, 0.21]; n=3 | 16.61 [16.42, 16.77]; n=3 | 45.73% [44.20%, 48.60%]; n=3 | 0.00 [0.00, 0.00]; n=3 |

| Panel | Network | Layer | Count | Mean | Population variance | Share3 | Share5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI job loss T60 (n=2 seeds) | B0 | private_state | 500.00 [500.00, 500.00]; n=2 | 3.79 [3.79, 3.79]; n=2 | 3.18 [3.17, 3.19]; n=2 | 14.45% [14.40%, 14.50%]; n=2 | 28.30% [28.30%, 28.30%]; n=2 |
| AI job loss T60 (n=2 seeds) | B0 | public_flow | 133.50 [130.00, 137.00]; n=2 | 3.69 [3.64, 3.74]; n=2 | 3.33 [2.84, 3.82]; n=2 | 14.36% [9.49%, 19.23%]; n=2 | 30.50% [29.62%, 31.39%]; n=2 |
| AI job loss T60 (n=2 seeds) | B0 | public_stock | 500.00 [500.00, 500.00]; n=2 | 3.83 [3.83, 3.83]; n=2 | 3.35 [3.35, 3.35]; n=2 | 14.45% [14.40%, 14.50%]; n=2 | 25.45% [25.30%, 25.60%]; n=2 |
| AI job loss T60 (n=2 seeds) | B0 | realized_exposure | 0.00 [0.00, 0.00]; n=2 | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) |
| AI job loss T60 (n=2 seeds) | B1 | private_state | 500.00 [500.00, 500.00]; n=2 | 3.15 [3.11, 3.19]; n=2 | 0.29 [0.25, 0.32]; n=2 | 82.00% [80.10%, 83.90%]; n=2 | 3.05% [2.50%, 3.60%]; n=2 |
| AI job loss T60 (n=2 seeds) | B1 | public_flow | 133.50 [130.00, 137.00]; n=2 | 3.16 [3.10, 3.23]; n=2 | 0.42 [0.28, 0.56]; n=2 | 80.94% [79.20%, 82.69%]; n=2 | 3.56% [3.46%, 3.65%]; n=2 |
| AI job loss T60 (n=2 seeds) | B1 | public_stock | 500.00 [500.00, 500.00]; n=2 | 3.30 [3.26, 3.34]; n=2 | 1.14 [1.06, 1.21]; n=2 | 67.20% [64.90%, 69.50%]; n=2 | 5.95% [5.30%, 6.60%]; n=2 |
| AI job loss T60 (n=2 seeds) | B1 | realized_exposure | 441.00 [439.00, 443.00]; n=2 | 3.16 [3.06, 3.26]; n=2 | 0.36 [0.22, 0.51]; n=2 | 81.48% [76.98%, 85.99%]; n=2 | 2.43% [1.25%, 3.61%]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | private_state | 500.00 [500.00, 500.00]; n=2 | 3.23 [3.21, 3.25]; n=2 | 0.44 [0.42, 0.46]; n=2 | 72.60% [71.20%, 74.00%]; n=2 | 6.10% [6.00%, 6.20%]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | public_flow | 133.50 [130.00, 137.00]; n=2 | 3.22 [3.22, 3.23]; n=2 | 0.49 [0.46, 0.51]; n=2 | 73.53% [71.15%, 75.91%]; n=2 | 6.56% [6.20%, 6.92%]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | public_stock | 500.00 [500.00, 500.00]; n=2 | 3.38 [3.37, 3.39]; n=2 | 1.25 [1.19, 1.32]; n=2 | 59.20% [58.10%, 60.30%]; n=2 | 9.00% [9.00%, 9.00%]; n=2 |
| AI job loss T60 (n=2 seeds) | B2 | realized_exposure | 436.00 [419.00, 453.00]; n=2 | 3.24 [3.22, 3.27]; n=2 | 0.44 [0.38, 0.50]; n=2 | 72.60% [70.86%, 74.34%]; n=2 | 6.42% [5.01%, 7.84%]; n=2 |
| GM market sales T60 (n=2 seeds) | B0 | private_state | 500.00 [500.00, 500.00]; n=2 | 4.06 [4.06, 4.06]; n=2 | 2.62 [2.58, 2.66]; n=2 | 20.80% [20.40%, 21.20%]; n=2 | 15.85% [15.70%, 16.00%]; n=2 |
| GM market sales T60 (n=2 seeds) | B0 | public_flow | 133.50 [130.00, 137.00]; n=2 | 3.93 [3.92, 3.93]; n=2 | 2.83 [2.53, 3.12]; n=2 | 21.57% [20.44%, 22.69%]; n=2 | 18.01% [16.79%, 19.23%]; n=2 |
| GM market sales T60 (n=2 seeds) | B0 | public_stock | 500.00 [500.00, 500.00]; n=2 | 4.04 [4.03, 4.04]; n=2 | 2.90 [2.82, 2.97]; n=2 | 19.65% [19.10%, 20.20%]; n=2 | 15.35% [15.20%, 15.50%]; n=2 |
| GM market sales T60 (n=2 seeds) | B0 | realized_exposure | 0.00 [0.00, 0.00]; n=2 | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) |
| GM market sales T60 (n=2 seeds) | B1 | private_state | 500.00 [500.00, 500.00]; n=2 | 3.47 [3.43, 3.51]; n=2 | 0.95 [0.92, 0.98]; n=2 | 69.80% [67.70%, 71.90%]; n=2 | 21.35% [18.80%, 23.90%]; n=2 |
| GM market sales T60 (n=2 seeds) | B1 | public_flow | 133.50 [130.00, 137.00]; n=2 | 3.58 [3.55, 3.61]; n=2 | 1.01 [0.91, 1.12]; n=2 | 64.42% [64.23%, 64.62%]; n=2 | 26.31% [22.63%, 30.00%]; n=2 |
| GM market sales T60 (n=2 seeds) | B1 | public_stock | 500.00 [500.00, 500.00]; n=2 | 3.60 [3.57, 3.62]; n=2 | 1.63 [1.59, 1.67]; n=2 | 55.95% [55.00%, 56.90%]; n=2 | 21.70% [19.90%, 23.50%]; n=2 |
| GM market sales T60 (n=2 seeds) | B1 | realized_exposure | 441.00 [439.00, 443.00]; n=2 | 3.48 [3.47, 3.50]; n=2 | 0.99 [0.91, 1.07]; n=2 | 66.32% [65.60%, 67.04%]; n=2 | 24.16% [22.46%, 25.85%]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | private_state | 500.00 [500.00, 500.00]; n=2 | 3.68 [3.65, 3.71]; n=2 | 1.41 [1.33, 1.49]; n=2 | 57.50% [54.40%, 60.60%]; n=2 | 24.85% [24.30%, 25.40%]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | public_flow | 133.50 [130.00, 137.00]; n=2 | 3.63 [3.51, 3.75]; n=2 | 1.39 [1.25, 1.53]; n=2 | 59.91% [52.31%, 67.52%]; n=2 | 23.35% [18.25%, 28.46%]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | public_stock | 500.00 [500.00, 500.00]; n=2 | 3.74 [3.72, 3.76]; n=2 | 1.96 [1.92, 2.00]; n=2 | 46.80% [44.00%, 49.60%]; n=2 | 22.85% [22.40%, 23.30%]; n=2 |
| GM market sales T60 (n=2 seeds) | B2 | realized_exposure | 436.00 [419.00, 453.00]; n=2 | 3.70 [3.63, 3.76]; n=2 | 1.49 [1.35, 1.63]; n=2 | 55.21% [49.56%, 60.86%]; n=2 | 26.28% [23.87%, 28.70%]; n=2 |
| Retirement T30 (n=10 seeds) | B0 | private_state | 500.00 [500.00, 500.00]; n=10 | 3.87 [3.87, 3.88]; n=10 | 3.22 [3.19, 3.27]; n=10 | 15.07% [14.60%, 15.40%]; n=10 | 14.47% [14.40%, 14.60%]; n=10 |
| Retirement T30 (n=10 seeds) | B0 | public_flow | 138.40 [127.00, 154.00]; n=10 | 3.85 [3.55, 4.24]; n=10 | 3.29 [2.80, 3.84]; n=10 | 14.16% [7.09%, 21.27%]; n=10 | 13.16% [9.49%, 16.33%]; n=10 |
| Retirement T30 (n=10 seeds) | B0 | public_stock | 500.00 [500.00, 500.00]; n=10 | 3.90 [3.88, 3.92]; n=10 | 3.39 [3.32, 3.47]; n=10 | 14.92% [14.50%, 15.20%]; n=10 | 14.44% [14.40%, 14.50%]; n=10 |
| Retirement T30 (n=10 seeds) | B0 | realized_exposure | 0.00 [0.00, 0.00]; n=10 | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) |
| Retirement T30 (n=10 seeds) | B1 | private_state | 500.00 [500.00, 500.00]; n=10 | 3.69 [3.64, 3.73]; n=10 | 1.58 [1.46, 1.75]; n=10 | 45.85% [43.50%, 50.10%]; n=10 | 35.86% [33.10%, 38.70%]; n=10 |
| Retirement T30 (n=10 seeds) | B1 | public_flow | 138.40 [127.00, 154.00]; n=10 | 3.65 [3.55, 3.78]; n=10 | 1.60 [1.35, 2.03]; n=10 | 46.19% [34.65%, 53.31%]; n=10 | 35.27% [29.47%, 42.52%]; n=10 |
| Retirement T30 (n=10 seeds) | B1 | public_stock | 500.00 [500.00, 500.00]; n=10 | 3.77 [3.69, 3.79]; n=10 | 2.16 [1.99, 2.30]; n=10 | 37.26% [35.10%, 40.90%]; n=10 | 31.52% [28.80%, 34.00%]; n=10 |
| Retirement T30 (n=10 seeds) | B1 | realized_exposure | 448.10 [416.00, 506.00]; n=10 | 3.71 [3.55, 3.93]; n=10 | 1.59 [1.24, 2.09]; n=10 | 45.14% [33.14%, 58.32%]; n=10 | 37.11% [28.63%, 45.90%]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | private_state | 500.00 [500.00, 500.00]; n=10 | 3.80 [3.76, 3.88]; n=10 | 1.69 [1.57, 1.85]; n=10 | 41.79% [37.70%, 44.90%]; n=10 | 37.42% [35.30%, 40.70%]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | public_flow | 138.40 [127.00, 154.00]; n=10 | 3.76 [3.45, 3.93]; n=10 | 1.67 [1.45, 1.94]; n=10 | 43.83% [32.28%, 51.09%]; n=10 | 36.66% [28.52%, 42.91%]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | public_stock | 500.00 [500.00, 500.00]; n=10 | 3.85 [3.80, 3.91]; n=10 | 2.23 [2.10, 2.36]; n=10 | 34.67% [31.40%, 38.40%]; n=10 | 32.04% [29.20%, 34.20%]; n=10 |
| Retirement T30 (n=10 seeds) | B2 | realized_exposure | 453.90 [417.00, 504.00]; n=10 | 3.80 [3.61, 3.97]; n=10 | 1.65 [1.43, 1.79]; n=10 | 43.54% [36.00%, 49.54%]; n=10 | 37.76% [31.88%, 45.31%]; n=10 |
| Retirement T60 (n=3 seeds) | B0 | private_state | 500.00 [500.00, 500.00]; n=3 | 3.87 [3.87, 3.88]; n=3 | 3.21 [3.20, 3.23]; n=3 | 15.17% [14.90%, 15.40%]; n=3 | 14.50% [14.40%, 14.60%]; n=3 |
| Retirement T60 (n=3 seeds) | B0 | public_flow | 136.00 [130.00, 141.00]; n=3 | 3.89 [3.72, 4.12]; n=3 | 3.16 [2.73, 3.90]; n=3 | 14.57% [9.85%, 20.38%]; n=3 | 18.61% [16.79%, 20.57%]; n=3 |
| Retirement T60 (n=3 seeds) | B0 | public_stock | 500.00 [500.00, 500.00]; n=3 | 3.90 [3.89, 3.92]; n=3 | 3.39 [3.34, 3.44]; n=3 | 15.00% [14.70%, 15.30%]; n=3 | 14.43% [14.40%, 14.50%]; n=3 |
| Retirement T60 (n=3 seeds) | B0 | realized_exposure | 0.00 [0.00, 0.00]; n=3 | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) | NA (no defined opportunities) |
| Retirement T60 (n=3 seeds) | B1 | private_state | 500.00 [500.00, 500.00]; n=3 | 3.62 [3.57, 3.70]; n=3 | 1.38 [1.29, 1.46]; n=3 | 54.00% [50.50%, 56.90%]; n=3 | 33.47% [31.40%, 36.50%]; n=3 |
| Retirement T60 (n=3 seeds) | B1 | public_flow | 136.00 [130.00, 141.00]; n=3 | 3.69 [3.56, 3.83]; n=3 | 1.49 [1.17, 1.89]; n=3 | 48.91% [44.33%, 54.23%]; n=3 | 36.92% [31.02%, 43.97%]; n=3 |
| Retirement T60 (n=3 seeds) | B1 | public_stock | 500.00 [500.00, 500.00]; n=3 | 3.71 [3.66, 3.77]; n=3 | 2.00 [1.84, 2.12]; n=3 | 44.33% [41.90%, 45.80%]; n=3 | 30.23% [27.70%, 31.90%]; n=3 |
| Retirement T60 (n=3 seeds) | B1 | realized_exposure | 450.67 [439.00, 470.00]; n=3 | 3.66 [3.59, 3.76]; n=3 | 1.42 [1.28, 1.65]; n=3 | 51.27% [49.21%, 55.24%]; n=3 | 35.58% [32.57%, 40.74%]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | private_state | 500.00 [500.00, 500.00]; n=3 | 3.78 [3.75, 3.80]; n=3 | 1.46 [1.43, 1.50]; n=3 | 49.63% [48.20%, 51.10%]; n=3 | 36.90% [36.00%, 38.00%]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | public_flow | 136.00 [130.00, 141.00]; n=3 | 3.81 [3.69, 3.90]; n=3 | 1.46 [1.36, 1.55]; n=3 | 48.52% [48.18%, 48.94%]; n=3 | 39.44% [37.96%, 41.13%]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | public_stock | 500.00 [500.00, 500.00]; n=3 | 3.82 [3.78, 3.85]; n=3 | 2.02 [1.96, 2.11]; n=3 | 42.47% [41.50%, 43.80%]; n=3 | 31.63% [30.60%, 32.80%]; n=3 |
| Retirement T60 (n=3 seeds) | B2 | realized_exposure | 440.67 [419.00, 453.00]; n=3 | 3.77 [3.64, 3.85]; n=3 | 1.50 [1.41, 1.55]; n=3 | 48.11% [45.92%, 50.44%]; n=3 | 38.52% [36.40%, 40.62%]; n=3 |

Age is measured in 500-event rounds. Age≥1/5/10 are post-hoc reporting bins. Empty expression/reading layers have count0 and undefined moments, not zero-valued opinions. Stock change is a before/after distributional description, not a causal effect of a message. Repeated posts within a receiver and re-use across receivers are distinguished in the source tables. FigureS1_Private_to_Visible displays the separate trajectories; Figure5_Communication_Structure links visibility to the structural comparisons.
