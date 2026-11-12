# RQ3 power analysis: what could the public data detect?

Question: RQ3 found no reliability effect of load growth. Is that informative, or could the design not have seen an effect of the size that matters?
Code: `src/rq3_power.py` (uses `data/processed/rq3_panel.parquet`, built by `src/rq3_model.py`). Outputs: `results/rq3_power.csv`,
`results/rq3_power_sim.csv`, `results/rq3_extremes.csv`, `results/figures/rq3_power_curve.png`.

Design: the main specification (utility effects + state-by-year effects, SEs clustered by utility; outcome log SAIDI without major
events; 9,245 utility-years, 1,080 utilities). Minimum detectable effect (MDE) = (1.96 + 0.84) x SE, i.e. 80% power at a 5% two-sided test.
Effects are % change in SAIDI.

## 1. A check on the original analysis: the exposure was clipped
`rq3_model.py` winsorises the exposure at the 1st/99th percentile (99th = 0.27 log points). That clips 106 utility-years, including every
one of the 28 with growth above 50% (largest: a Kentucky utility at +128% in 2023): the events closest to data-center-scale load.
The unclipped exposure is now kept as `d_ln_ci_pc_raw` (an added column; the model's results are numerically unchanged, max difference 2.4e-15; a
pre-change snapshot is in `results/_audit_before/`).

| Estimate of +10% C&I load on SAIDI | Effect | 95% interval | MDE (80% power) |
|---|---|---|---|
| Winsorised 1/99 (main spec) | +0.66% | -1.13% to +2.45% | 2.56% |
| **Unclipped** | +0.58% | -0.70% to +1.86% | 1.83% |
| Clipped at 99.9th percentile | +0.61% | -0.84% to +2.05% | 2.07% |
| Extremes dropped (growth beyond +-0.5) | +0.63% | -1.13% to +2.40% | 2.53% |

The null does not depend on the clipping. Using the unclipped data tightens the bound (upper end +1.9% instead of +2.5%), because the large surges carry information.
(The Midpoint 1 report quotes +0.5% [-0.7, +1.7] from the Bayesian model, and +2.5% as the largest upper bound over the fixed-effects
specifications; those figures are unchanged.)

## 2. What the design can detect
| Design | Treated utility-years | MDE (80% power) |
|---|---|---|
| Continuous exposure, all utilities, main spec | n/a | 2.6% SAIDI per +10% C&I load |
| Continuous exposure, unclipped | n/a | 1.8% per +10% |
| Surge year, growth above 10% | 527 (295 utilities) | 7.8% in the surge year |
| Surge year, growth above 25% | 115 (95 utilities) | 17.0% |
| Surge year, growth above 50% | 26 (24 utilities) | 24.9% |
| **Arizona only**, continuous | 105 utility-years, 14 utilities | 28% per +10% |

- **Simulation check.** Removing the fitted effect, injecting a known elasticity, resampling utilities and refitting (120 repetitions each) gives power of
  0.07, 0.21, 0.51 and 0.87 at elasticities 0.05, 0.10, 0.20 and 0.30, against analytic values of 0.08, 0.18, 0.55 and 0.88. The analytic MDEs above are reliable.
- **Arizona cannot be tested on its own.** Of Arizona's 105 utility-years only 2 have growth above 10% and none above 25%. The Arizona-only estimate in this analysis (year effects, no lag) is +13.1% per +10% with a standard error of 10.1%; S6 in the
  Midpoint 1 results (with a lag term) is similarly noisy. Both are noise, and the national estimate is applied to Arizona by assumption.
- **The surge tests are far weaker than the continuous design.** A surge-year test cannot see an effect below about 8% (growth above 10%) to 25%
  (growth above 50%). The conservative bound for a single 500 MW project at APS or SRP (about +4.6% SAIDI, `results/case_study_reliability_bound.csv`) is below every
  surge-test MDE, so a surge-indicator design could not have confirmed or ruled out an effect of that size.

## 3. Where the large surges are
The 28 utility-years above +50% growth fall mostly in 2022-2024 (18 of 28) and in KY (5), TN (4), VA (3), GA (2), MI (2), ND (2), with one or two each in
ten other states. Their median size (about 23,700 customers) matches the panel's (about 24,200). The data cannot say what caused them: data centers, cryptocurrency mining,
manufacturing and other industrial additions all look the same in C&I sales.

## 4. Reading it honestly
- The RQ3 null is **robust to the clipping** and slightly more informative than reported: the data rule out effects above about +1.9% (unclipped) to +2.5% (main
  spec) SAIDI per +10% C&I load, on this proxy.
- The proxy is diluted. C&I sales per customer mixes data centers with everything else, and a large data-center addition to a big utility is a small
  percentage change in its C&I load. Power for a data-center-specific effect is lower than the figures above, by an amount that cannot be computed without
  knowing the data-center share of the exposure.
- Nothing here is a finding about data centers. The panel has no data-center identifier, so even the 28 largest surges are of unknown origin.
- Not a validation of the guardrail: the Stage 1 guardrail uses the upper confidence bound of the main-spec elasticity (0.257); the unclipped estimate would lower it
  to about 0.20 (the interval end of +1.86% per +10% divided by ln 1.1 = 0.195), which would loosen the guardrail. Stage 1 was not re-run with this value.

## 5. What would make RQ3 informative about data centers
A data-center-specific exposure: a variable that marks which utility-years received data-center load, so that the surge test has a defined treatment. Options, in
order of feasibility from public data: (a) utility-level counts of mapped data centers from OpenStreetMap joined to national service-territory polygons (no dates, so
cross-sectional exposure interacted with the post-2019 period); (b) an event study of named clusters (for example Northern Virginia, central Ohio, ERCOT) using utility
reports. Both need new data pulls; neither is built.
