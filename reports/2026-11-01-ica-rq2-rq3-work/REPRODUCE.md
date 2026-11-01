# Reproducing the ICA evidence

## Data access levels

The Review Packet is designed for independent checking of the supplied numerical results and figure construction. It intentionally excludes private reason full texts and original databases. The full RQ2 package adds150 selected genuine private-text cases for controlled human review. Full original-record replay additionally requires access to the frozen archive locations listed in SOURCE_MANIFEST.json. A ZIP of summaries alone does not replace those raw archives.

## Completed cohort coverage

There are102 horizon trajectories:60 retirement T30,18 retirement T60,12 GM T60 and12 AI T60. Deduplicating the continued retirement prefixes gives1,890,000 unique network events. P0's1,512 fixed-step research cases are separate. Do not pool T30/T60 endpoints or the1512 P0 cases as additional network replications.

## Commands

Use an existing Python environment with numpy/pandas for metrics and matplotlib for graphics; no new model or experiment runtime is needed. `scripts/plot_figures.py --tables <unpacked tables> --output <output>` rebuilds all four figure sets directly from the packaged numerical CSV.gz tables. Set `MPLCONFIGDIR` to an appropriate local writable cache when reproducing outside the original Windows host. Figure script options override original table/output defaults. `summarize_results.py --tables <tables> --package-a <A> --package-b <B> --summary-output <summary.json>` rebuilds numerical briefs after validating complete coverage.

On the original controlled Windows host, `extract_originals.py --cohort core --seed <seed>` reads each frozen T30 archive; `--cohort tail` adds the corresponding continued tail and `--cohort cross --topic <topic>` reads the fresh cross-topic archive. Run `run_analysis.py --all --aggregate` to rebuild per-run statistics and seed pairings in a separate output root. Do not reuse an already frozen result directory for changed inputs or code. `verify_numeric_results.py` independently checks replay, flows, exposure response numerators and local edge arithmetic. `compare_legacy_endpoints.py` compares newly replayed endpoints against previously plotted distributions without using those older tables to compute the new results.

## Local runtimes used

Numerical extraction/metrics use the Codex bundled Python environment. The bundled runtime has no matplotlib on this host, so graphics use the already-installed Python3.14 environment with matplotlib3.10.9; no package was installed. Both runtime paths and dependency versions are recorded with delivery verification. The source tests and numerical comparisons are unchanged by the rendering environment. One older-pandas all-NA concat deprecation warning can arise in a synthetic test fixture under that rendering runtime; it does not denote a failed test or a changed experimental record.

## Checksums and interpretation

Each package has SHA256SUMS covering all content members except the checksum file itself. External package receipts also record the complete ZIP SHA-256, exact member coverage, streamed per-member hashes, CRC and a restored CSV check. SOURCE_MANIFEST binds topic/seed/condition/horizon to original archive/member/database hashes and analysis signatures.

Review results at the matched-seed level. A/B identity averaging is explicit where used. A conditional exact i-to-j rate is not a toward-j rate; an event denominator is not a selected-slot denominator. B0's edge alignment is undefined. Private opinion, latest public stock, new expression and realized exposure are different denominators. Original Stage-A/B manipulation admission remains unchanged. Mechanism casebook codes are pending human review, and directional movement is not a sycophancy label.
