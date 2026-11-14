# Pre-specified test: does import dependence predict the instability of regression marginal-emission estimates?

Written before any new balancing-authority (BA) data were pulled or analysed. It is self-imposed (no registry; file times are the only timestamp), so its value is that
the rules below were fixed before the multi-BA numbers were seen. The four Arizona BAs motivated the hypothesis, so they are not an independent test of it.

## Hypothesis
H1. In-BA regression marginal emission rates (hourly change in generation CO2 on hourly change in demand, by 6 h block and season, `marginal_emissions.py` base specification) are less
stable out of sample in BAs where a larger share of a demand change is absorbed by net interchange.

## Sample
EIA-930 BAs with fuel-type and demand data, 2021-2025: the four Arizona BAs, the six neighbours already pulled (PNM, WACM, EPE, PACE, IID, CISO) and 27 further BAs chosen for size and variety
(listed in `src/pull_ba_panel.py`). Inclusion rule, fixed now: at least 90% valid hours in the training years and a mean carbon intensity of at least 50 kg/MWh over the training years (near-zero-emission
BAs have no thermal signal for the regression to recover). BAs failing the rule are reported and excluded.

## Measures (per BA, two test years)
- Train 2021-2023 and test 2024; train 2021-2024 and test 2025. Estimator and bins as in `marginal_emissions.py` (6 h blocks x summer/other, base specification, no controls).
- **S** (primary stability): correlation between the train profile and the test-year profile across the 8 block-season cells, averaged over the two test years.
- **D** (secondary): mean absolute train-test difference as a percentage of the train mean, averaged over the two test years (lower is more stable).
- **A** (primary predictor): absorption by net interchange = minus the slope of the hourly change in net export on the change in demand, averaged over blocks and seasons in the training years.
- Secondary predictors: net import share of demand, net export share of demand, fuel concentration (Herfindahl), clean share.

## Which BAs decide the verdict
The four Arizona BAs motivated H1, so they cannot also confirm it. **The verdict below is computed on the included BAs excluding AZPS, SRP, TEPC and WALC.** Results on the full included sample
(Arizona BAs added) are reported as secondary. (Amendment made before any multi-BA data were analysed.)

## Decision rule (Spearman rank correlation across BAs, permutation p-value, 10,000 permutations)
- **Support:** corr(S, A) <= -0.33 with one-sided p <= 0.05, AND corr(D, A) >= +0.33 with one-sided p <= 0.05.
- **Kill (no paper on this question):** |corr| < 0.20 for both S and D against A.
- Anything else is **inconclusive**: report it as such and do not extend the sample selectively.
Both outcomes are reported with the sample size and the excluded BAs. No predictor, metric, bin width or threshold is changed after seeing results; any change is reported as a deviation.

## What a positive result would and would not show
It would show that, across these BAs, the estimates are less stable where interchange absorbs more of the demand change. It would not show that the estimator is wrong or right in any BA (there is no
ground truth for the marginal response), and it is an association over about 30 BAs, so it is a screening result, not a causal one.

## Deviations (recorded as they happen)
1. **Sentinel values.** A smoke test on PJM alone (no association examined; one BA) showed EIA-930 demand and net generation contain the value 2,147,483,647 (the 32-bit maximum), which would corrupt
   the demand-change regression. Such values are now set to missing and counted per BA (`n_sentinel_values` in `results/mef_scan_by_ba.csv`). Added before any multi-BA correlation was computed.
2. **Implausible values.** The sentinel rule was not enough: PJM still had a demand value of 431 million (4,805 times the median). Demand and net generation are now also set to missing when
   they are not positive or exceed 5 times the BA's median demand, and net interchange when its magnitude exceeds 5 times median demand; counts are reported per BA (`n_implausible_values`).
   Found with a QC-only run (`--qc`) that computes no stability metric or association, before any multi-BA correlation was computed.
3. **The motivating Arizona pattern was a data artifact.** Applying the same demand QC to the Arizona BAs (`docs/MARGINAL.md`, correction) removed the observation that motivated H1: AZPS, the BA with the highest net import share (37%), is stable at 6 h
   (profile correlation 0.61 / 0.57), while WALC (high absorption in the training years) is unstable in 2025. The hypothesis, sample, metrics and decision rule above are unchanged; the Arizona BAs remain excluded from the verdict.
4. **Stricter demand QC (primary), 5x-median rule kept as a sensitivity.** The QC-only run on all 37 BAs (computing no stability metric and no association) showed that the 5-times-median rule still leaves glitches (for example FPL demand of 72,201 against a median of
   15,358 and a minimum of 39; PSCO 19,352; WACM 12,708; hundreds of near-zero hours in LDWP, IID, WACM, TEPC). A diagnostic of demand relative to the median of the same BA, month and hour of day showed natural variation inside about 0.55-1.95 and glitches
   below 0.3 or above 2.5. **Primary rule:** demand outside [0.3, 2.5] times that median (or not positive) is set to missing, and net interchange above 3 times its 99.5th percentile of magnitude (`src/eia930_qc.py`). Net generation is not used in the analysis and legitimately varies by large factors in hydro- and wind-heavy BAs, so only its sentinels are removed.
   **Secondary:** the earlier 5-times-median rule (`--legacy-qc`). The verdict uses the primary rule; the scan is also run under the secondary rule, and if the two verdicts differ the result is reported as **inconclusive**. Chosen before any correlation was computed.
