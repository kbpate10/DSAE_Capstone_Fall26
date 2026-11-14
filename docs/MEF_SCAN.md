# Multi-BA scan: does import dependence predict the instability of regression marginal-emission estimates?

Pre-specified in [MEF_SCAN_PREREG.md](MEF_SCAN_PREREG.md) (read it for the hypothesis, rules and the four recorded QC deviations). Code: `src/pull_ba_panel.py`, `src/eia930_qc.py`, `src/ba_stability_scan.py`.
Outputs: `results/mef_scan_by_ba*.csv`, `results/mef_scan_tests*.csv`, `results/mef_scan_exploratory*.csv`, `results/figures/mef_scan*.png` (files ending `_legacyqc` use the secondary QC rule).

## Verdict: INCONCLUSIVE under both QC rules (not a kill, not support)
Sample: 37 BAs pulled (EIA-930, 2021-2025); BPAT and TPWR excluded by the pre-specified rule (mean carbon intensity below 50 kg/MWh); 31 included BAs outside Arizona decide the verdict (35 with the four Arizona BAs).
The rule needed **both** corr(S, A) <= -0.33 and corr(D, A) >= +0.33, each with one-sided p <= 0.05. S = train-test profile correlation (shape), D = train-test level disagreement as % of the train mean, A = absorption of demand changes by net interchange.

| QC rule | corr(S, A) | p | corr(D, A) | p | Verdict |
|---|---|---|---|---|---|
| Primary ('band') | -0.18 | 0.175 | +0.59 | <0.001 | inconclusive |
| Secondary (5x median) | -0.03 | 0.44 | +0.52 | 0.002 | inconclusive |
Other predictors (primary rule, verdict sample): net import share vs S -0.13 (p 0.24), vs D +0.20 (p 0.14); net export share vs S -0.09, vs D +0.28 (p 0.064); fuel concentration vs S -0.02, vs D +0.19; clean share vs S -0.15, vs D +0.11. None meets the criteria.
The kill condition (both |corr| below 0.20) was not met because corr(D, A) is large, so by the rule the result is "inconclusive", not "no effect".

## What the data show, in plain terms
1. **Import dependence does not predict whether the daily shape of the marginal profile is stable.** corr(S, A) is -0.18 and -0.03.
2. **It does correlate with how much the profile's level moves, but mostly through a normalisation artefact.** (Exploratory, post hoc, not part of the verdict.) A is strongly negatively related to a BA's mean in-BA marginal rate (rho -0.52 primary, -0.48 secondary): where interchange absorbs
   much of a demand change, the in-BA rate is small, so a percentage-of-mean metric is inflated. Re-expressed as a percentage of the BA's average carbon intensity the link falls to rho +0.37 (nominal p 0.020; secondary +0.34, p 0.031), and on the absolute difference in kg/MWh it is +0.19 (p 0.16;
   secondary +0.16, p 0.20), not significant. The level result is therefore weak and depends on how it is normalised.
3. **Descriptively, 6 h profile shapes are reproducible in most BAs.** Of the 31 non-Arizona BAs, 22 (primary rule; 20 under the secondary) have a train-test correlation of at least 0.5 in both test years; the median is 0.72; the median level disagreement is 26% of the train mean.
   Unstable in at least one test year (correlation below 0.3): SOCO, TEC, PACW, NEVP, PSCO, NWMT, EPE. The four Arizona BAs under both rules: AZPS 0.61 / 0.59, SRP 0.69, TEPC 0.68, WALC -0.02 / 0.03, matching the corrected Arizona analysis (`docs/MARGINAL.md`).
   The per-BA stability ranking agrees across the two QC rules (Spearman 0.84).

## Limits
- Screening result on about 31 BAs: low power, one hypothesis tested, and an association, not a cause. Interchange is net (not gross), local time is fixed standard time per BA (assigned by hand, MISO assumed Eastern), and hourly CO2 uses BA-level eGRID factors (69% of BA-fuel factors come from the BA's own plants, the rest from the national average).
- **The result depends on data cleaning.** EIA-930 demand needed two QC rules found only after looking at the data (PJM had a 32-bit sentinel and a value of 431 million; several BAs had stretches of near-zero demand). The verdict is the same under both rules, but a third reasonable rule could differ, and the first smoke test on PJM alone showed how much a single glitch can matter.
- Stability here means agreement between two estimates from the same regression method on different years. It does not show that either estimate is the true marginal response, and there is no ground truth in this analysis (see "Ground truth" below).
- The exploratory checks were chosen after seeing the primary result.
- **Fuel-series plausibility cap not applied here.** On 2026-11-10 the Arizona pipeline began flagging implausible EIA-930 fuel values (`docs/MARGINAL.md`, second correction). The scan builds its own hourly CO2 for 37 BAs and applies only the demand and interchange rules of this pre-registration, so fuel spikes in other BAs may still be present. I did not re-run it: changing the QC after seeing the result would be another deviation. A re-run would need to be recorded as one.

## What this means for a paper
The premise that motivated the scan (import dependence explains marginal-estimate instability) is **not supported** by the pre-specified test; the Arizona pattern that suggested it was a data artefact (`docs/MARGINAL.md`, correction). By the pre-specified rule I do not extend the sample or change the metrics to rescue it.
What is left is descriptive (shapes are mostly stable at 6 h, levels move by about a quarter) and not novel on its own. A paper would need a different question, for example the decision regret from scheduling on the wrong signal across many BAs, which was not tested here.

## Ground truth (what is publicly available; first-pass search, partly unverified)
PJM's site describes hourly marginal-fuel shares for its real-time market (five-minute price-setting units), but its file links go through a PJM sign-in, so I could not confirm the files can be downloaded without an account. It is a price-setting margin, a plausibility benchmark and not the consequential response. I found no equivalent feed for ERCOT, NYISO, MISO, ISO-NE or CAISO, and no study that benchmarks regression estimators against observed marginal-unit data
(only dispatch-model benchmarks); a more targeted search would be needed before calling that a gap.
