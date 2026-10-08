# MC case-level analysis implementation plan

**Goal:** Implement the approved arithmetic and stratified bootstrap without transport or Stage-B activation.
**Architecture:** Pure analysis cold-replays the offline inventory and checks exact normalized outcome identity.
No raw text, model calling or provenance authentication; eventual CLI must verify durable transport evidence first.
**Tech Stack:** Python 3.12 standard-library random.Random (MT19937), percentile linear interpolation, pytest.

Files: `platform/src/agent_ex/identity_network/benchmark_analysis.py`,
`platform/tests/test_identity_network_benchmark_analysis.py`.

- [x] RED: synthetic all-positive/all-zero, 17/18-positive boundary, incomplete/invalid sets,
  duplicate/unknown identities, strict stance integers, exact two-repeat aggregation and deterministic CI.
- [x] Run named tests in the task-specific temp/cache directory; expect missing module failures.
- [x] GREEN: `analyze_benchmark_outcomes(benchmark,inventory,outcomes,expected_hash=...)` first cold-replays
  inventory. Each outcome has only trial_id/status/post_stance; identity is unique and in inventory.
  Fewer than 240 VALID records returns INCOMPLETE without substantive signal or bootstrap.
- [x] Complete input: shift=abs(4-source)-abs(post-source), repeat=(BB+GG-BG-GB)/2,
  case=mean(two repeats), equal-weight 30case mean, case>0 positive, at least18 positive.
  Resample within each ordered six strata, 5 cases with replacement, 10,000 iterations;
  random.Random(20261008), randrange(5), percentile at h=(n-1)*p with linear interpolation.
- [x] Return descriptive distance/direction means only; pass requires positive mean, CI lower>0,
  >=18 positives. Mathematical status does not grant execution provenance or Stage-B dispatch.
- [x] Ruff/format/diff and scoped regression only. Bind algorithm/version and input hashes in report.
