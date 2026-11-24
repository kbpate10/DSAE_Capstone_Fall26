# Carbon, Water, and Reliability: A Decision Framework for Arizona's AI Data Center Boom

FSE 570 Data Science Capstone, Arizona State University, Fall 2026. Final report (draft 1, 2026-11-10).

**Sourcing rule.** Every number below is taken from a document or file named next to it (documents in `docs/`, tables in `results/`). Numbers that come from web search or memory are labelled
as such. Nothing here is called "validated" unless it was tested against data the method never saw; the siting score and all water and scenario figures are not.

## Abstract
Arizona is adding AI data centers while its grid, water supply and regulators are under pressure. This project builds one framework from public data for three linked decisions:
**when** to run flexible computing (RQ1), **where** to site it (RQ2), and **who bears the reliability risk** (RQ3), with water as an extension. Main results, each with its limit:
(1) Timing matters and forecast sophistication barely does: an 8 h job placed by yesterday's same-hour carbon intensity saves about 24% against running at midnight, and perfect foresight adds about 3 points (the size of the saving is lower on AZPS and TEPC when measured plant emissions replace the estimated fossil CO2).
The saving is an average-intensity saving; scored on a marginal-emissions estimate the share that remains is unstable (pooled 8% in 2024, 14% in 2025, and much of the 2025 figure rests on one ill-conditioned BA), and the two accountings disagree.
(2) Commercial and industrial load growth shows no detectable effect on utility reliability (SAIDI), bounded at +2.5% per +10% load, but the proxy cannot see data centers specifically and the study has
little power in surge-year settings. (3) Real data-center locations follow population and substations, not the environmental criteria in the siting score; the score ranks existing host cells low. (4) Combining
the pieces, project size relative to the serving utility's load decides which sites are even feasible before carbon or water enter. (5) Carbon-aware scheduling and cooling water pull in opposite directions at SRP and TEPC
(measured plant data keep this conclusion, and remove it for AZPS only under one timing assumption). The framework is a scenario demonstration on assumed inputs, not a siting recommendation.

## 1. Problem and scope
Data-center growth in Arizona raises three questions that are usually studied separately: carbon (which hours and which grid), water (cooling and generation), and reliability and cost for other customers.
The decision framework links them: Stage 1 chooses sites under a utility-level reliability guardrail; Stage 2 schedules flexible work at the chosen sites under a carbon-water weighting (alpha, swept, not fitted).
Public data only; solo project; one machine (CPU). Policy context and what the framework can and cannot say about it: `docs/ARIZONA_CASE_STUDY.md`.

## 2. Data
Twelve free public sources: EIA-930 hourly grid data for four Arizona balancing authorities (AZPS, SRP, TEPC, WALC), 2021-2025; EPA eGRID emission factors; EIA-861 utility panel 2013-2024 (11,845 usable utility-state-years);
ADWR/USGS groundwater (45,985 sites); LBNL Queued Up; NASA POWER weather; OpenStreetMap data centers and substations; Census population; HIFLD utility territories; EIA-860/923 plant data. Details, cleaning rules and gaps: `docs/data_dictionary.md`, `docs/EDA.md`.

Data findings that changed the design:
- LBNL Queued Up contains **generation and storage requests only**, no load or data-center requests. RQ3's exposure is therefore EIA-861 commercial and industrial (C&I) MWh per total customer, a diluted proxy.
- EIA-930 demand contains glitches (a 32-bit sentinel, non-positive values, values 20-90 times the median). Gaps and glitches are flagged and excluded, not imputed. This affected marginal-emission results (section 8).
- Carbon intensity is production-based by default; a flow-traced consumption-based version exists (`docs/CONSUMPTION.md`). It was checked against measured EPA plant CO2 (CAMPD), which it does not reproduce within the pre-specified tolerance (section 3, `docs/MEASURED_EMISSIONS.md`).

## 3. RQ1: when to run flexible workloads
**Forecasting.** Day-ahead and hour-ahead carbon-intensity forecasts. Chronological split: train 2021-2023, early-stop 2024, test 2025; all models on identical rows. Primary model, named before the test set was examined for this question:
LightGBM predicting the residual over persistence. The temporal CNN is secondary and single-seed. The residual target was chosen after seeing 2025 results and was re-tested on 2024 (rolling origin, `docs/AUDIT.md` section B), where the raw-level model again loses to persistence at 24 h.

| MAE gain over persistence, test 2025 | AZPS | SRP | TEPC | WALC |
|---|---|---|---|---|
| LightGBM, 1 h | +26.0% | +23.1% | +25.1% | +13.6% |
| LightGBM, 24 h | -1.2% | +3.3% | +2.0% | +4.7% |

Source: `results/forecast_v2_metrics.csv` (recomputed 2026-11-10 after a plausibility cap on EIA-930 fuel values; the earlier Midpoint 1 values were 20.6% for SRP at 1 h and -0.2% for AZPS at 24 h, `results/_audit_before/before_fuel_qc_2026-11-10/`). Gains are large at 1 hour and small at 24 hours; Arizona's solar cycle is so repeatable that persistence is hard to beat. Conformal 90% intervals cover 87-92% of 2025 targets (95% intervals 93-97%),
but coverage falls to 70-83% in single worst months and LightGBM's 24 h intervals are only 2-8% narrower than persistence's (`docs/MIDPOINT2_REPORT.md` section 4). The calibration pool is 2025 itself, and conformal guarantees assume exchangeable residuals, so empirical coverage is the claim.

**Scheduling.** A job needs k run-hours inside a 24 h window decided at local midnight, using only information available then. For an 8 h preemptible job, pooled over BAs, saving versus running immediately: random timing 8.2%, persistence 24.3%,
LightGBM 24.5%, perfect foresight 27.5%. Timing matters; the forecaster adds little over "same hour yesterday". Paired bootstrap over days: LightGBM beats persistence by 0.1-0.25 points on SRP and 0.3-1.3 on WALC, with no clear difference on AZPS and TEPC.

**Which carbon number?** The result depends on the accounting:
- *Consumption-based* (flow tracing of interchange) changes the carbon ranking and AZPS's level (508 to 364 kg/MWh) but scheduling savings stay at 12-26% on AZPS, SRP and TEPC (`docs/CONSUMPTION.md`).
- *Measured plant emissions* (`docs/MEASURED_EMISSIONS.md`). Against EPA's measured hourly CO2 the estimated series misses the pre-specified tolerance on all four BAs (it is 20-30% below measured on SRP, TEPC and WALC; AZPS agrees within 5% once Four Corners in New Mexico is included), and it contains a few glitch hours. The level offset is flat across the day. Re-scoring persistence scheduling on a series with measured fossil CO2 keeps the saving on SRP and WALC (gaps under 2.1 points) but lowers it on TEPC (11.9% to 5.3% in 2025) and on AZPS (15.7% to 11.4% in 2024; 2025 depends on removing four extreme hours), so the headline saving is a range for those two BAs. Plant-to-BA attribution of jointly owned plants is untested.
- *Marginal* (regression of the change in in-BA CO2 on the change in demand, `docs/MARGINAL.md`): hourly profiles are not reproducible between years (train-test correlation 0.07-0.26); 6 h profile shapes are (AZPS 0.60 / 0.67 for test years 2024 / 2025, SRP 0.70 / 0.70, TEPC 0.60 / 0.76) except WALC (0.65, then -0.60), while levels move by a third to three quarters.
  Yesterday's average intensity saves 14-18% by average accounting and 8-14% pooled by the marginal estimate; a marginal-profile decision saves 5% by average and 27-43% by marginal accounting. **Each signal wins on its own accounting, and there is no ground truth for the marginal response**,
  so these numbers measure agreement between two estimates. Report RQ1 savings as average-intensity savings. The share that carries over to a marginal estimate is not stable: 59% pooled in 2024 and 79% in 2025, but 95% and 20% excluding AZPS, whose 2025 percentages are ill-conditioned (17% became 49% when five flagged hours were excluded).
- *Cross-BA check (pre-registered, inconclusive).* Does import dependence predict marginal-estimate instability? Across 31 non-Arizona BAs the pre-specified test came out inconclusive under both data-cleaning rules (shape stability vs interchange absorption: correlation -0.18, p 0.175, needed -0.33;
  level disagreement: +0.59, but mostly a normalisation artefact, +0.19 and not significant on absolute differences). The Arizona pattern that motivated the hypothesis was a data artefact. Descriptively, 6 h shapes are reproducible in 22 of 31 BAs (`docs/MEF_SCAN.md`, `docs/MEF_SCAN_PREREG.md`).

## 4. RQ3: who bears reliability risk
Utility-state-year panel, 2013-2024; outcome log SAIDI without major events; exposure the change in log C&I MWh per total customer; utility fixed effects with year or state-by-year effects, SEs clustered by utility; PyMC hierarchical model as a second layer.

| Specification (effect of +10% C&I load per customer on SAIDI) | Estimate | 95% interval |
|---|---|---|
| Utility + state-by-year effects (main) | +0.7% | -1.1% to +2.5% |
| Bayesian hierarchical | +0.5% | -0.7% to +1.7% |
| Pooled OLS, exposure only (naive) | +8.8% | +5.7% to +12.0% |

The naive comparison finds harm; it disappears once size, customer growth, ownership and utility effects are controlled, so it reflects which utilities grow, not what growth does (`docs/MIDPOINT1_REPORT.md` section 4).
**This is a null result with bounds**: effects above about +2.5% per +10% load are ruled out (+1.9% with the unclipped exposure). The null survives IEEE-only reporting, dropping switchers, and removing the 1/99 clipping.
Limits stated plainly:
- **Power** (`docs/RQ3_POWER.md`): the design can detect 1.8-2.6% per +10% load nationally but only 8-25% in surge-year tests, and Arizona alone cannot be tested.
- **The proxy is diluted.** A data-center exposure built from mapped facilities per utility territory has a weak first stage (F 2.8, gone with a size control) and shows no sign of harm; it cannot test data-center load (`docs/RQ3_DC_EXPOSURE.md`).
- The point estimate is unstable to removing 0.5% of rows as probable unit errors (sign changed); the conclusion is not. Outcomes including major-event days show negative associations, which I read as reverse causation (not tested).
- The Bayesian model is slightly overconfident on held-out 2024 (91.8% coverage at 95%) and matches, but does not beat, naive predictions. It says nothing about rates or cost allocation, the focus of the ACC docket.

## 5. RQ2: where to site
**Constructed score.** 192 cells (0.25 degrees) scored on groundwater depth and trend, wet-bulb temperature, solar and county queue strain with assumed weights. Models trained on a top-tercile label reach AUC 0.96-0.99,
but the label is a function of the same features: **a reconstruction check, not validation.** Rank stability is the honest uncertainty: median rank correlation 0.82 across 2,000 random weight vectors; only 2 cells stay in the top 10% in 80% of draws.

**Revealed preference** (`docs/REVEALED_PREFERENCE.md`). Where data centers actually are (25 host cells at 5 km resolution, 92% in the Phoenix metro, from OpenStreetMap): population within 10 km alone gives AUC 0.89 within the metro under spatial-block cross-validation; substation distance 0.81;
environmental features 0.46. The constructed suitability score runs the wrong way statewide (AUC 0.19). Feasibility and environmental suitability correlate -0.28. Limits: few positives, one metro, incomplete OSM data, population stands for several unseparated factors (latency, fiber, land, workforce), and "feasible" here means
"looks like existing hosts", not "can be interconnected".

## 6. Integrated framework (Stages 1 and 2)
**Stage 1** is an integer program that maximises suitability subject to per-utility caps from the reliability guardrail (projected SAIDI at or below tau_R, added load at most 25% of the utility's C&I sales) on HIFLD utility territories (`docs/STAGE1.md`).
**Stage 2** schedules the job at each chosen site's BA and can feed back into the site objective (`docs/STAGE2.md`).

At the default scenario (500 MW, tau_R 100 min, mapping "all") the optimizer picks a Cochise cell served by APS (rank 7 of 192) and a Maricopa cell served by SRP (rank 133), suitability 1.15
(`results/framework_stage1_sweep.csv`; `docs/MIDPOINT2_REPORT.md` section 3).
- **Project size against utility size decides first.** A 500 MW project at load factor 0.8 is about 3.5 TWh a year, about 19% of APS's or SRP's C&I load and 70% of TEP's. At 100 MW five sites qualify; at 1,000 MW none.
- The guardrail binds only between about 60 and 100 minutes of SAIDI; at equal site count it costs 26% of suitability (1.15 vs 1.56).
- Adding operating carbon and water to the siting objective cannot change carbon (one APS and one SRP site either way) and moves water by 3-13%.
- A voltage-and-proximity interconnection screen costs 6-13% of suitability at moderate thresholds; the default Cochise cell is 93 km from a 230 kV substation (`docs/STAGE1_INTERCONNECTION.md`). Real interconnection-capacity data are not public.
- The selection is not stable to the siting weights (the top cell is chosen in 57% of random-weight draws under mapping "all").
- Carbon-only scheduling at the chosen sites saves 38.2% (AZPS site) and 27.1% (SRP site) of carbon against running immediately; balanced weighting saves 37.6% and 18.0% (`results/framework_scenario_default.csv`). The "oracle" row is not deployable.

This is a demonstration on assumed inputs (500 MW, PUE 1.2, the on-site cooling curve, the 25% support limit). It is **not a siting recommendation**: the cells are 25 km squares without transmission, fiber or land features, and several utility assignments are approximate.

## 7. Water (extension)
On-site cooling water uses an evaporative curve driven by hourly wet-bulb temperature (an assumption; PUE 1.2); generation-side water uses fuel factors. Base factors are Macknick et al. (2012) medians; measured EIA-860/923 factors for 2025 are a sensitivity (`docs/WATER_MEASURED.md`).
- On-site water is anti-correlated with carbon within a day (-0.5 to -0.6 on AZPS, SRP, TEPC) because the cleanest solar hours are the hottest; generation-side water moves with carbon. They largely offset on AZPS and TEPC.
- **Carbon-only scheduling uses about 2-7% more water than random timing at SRP and TEPC under every tested accounting** (SRP 4.2-7.3%, TEPC 1.9-2.5%), including measured plant factors and discounted Palo Verde water. WALC saves water unless hydro reservoir evaporation is counted.
- **AZPS "has no conflict" (Midpoint 1) does not hold** once the Solana solar-thermal plant is separated from PV: AZPS moves from +4.1% to between -1.6% and -0.1%, or +4.6% if Solana is treated as PV. The truth depends on Solana's hourly timing, which public data do not give.
- Every reporting Arizona thermal plant is wet-cooled. Measured gas water per kWh is 1.3-2.3 times, and coal 40-80% of, the literature factors.
- Scheduling moves water by at most about 7%; cooling design is the larger water lever. A hypothetical $0.01 per gallon fee on one 500 MW project's modelled on-site water is $3.6-9.4 million a year; actual use may be far lower.
  No price-to-weight calibration was done, so the frontier (alpha swept 0-1) is the output.
- Multi-site shifting results (44-54% savings) are artefacts of production-based accounting and the hydro assumption and are not used.

## 8. Errors found and claims withdrawn
Kept in the report because they are part of the result (`docs/AUDIT.md`):
- **Fuel-series spikes (2026-11-10).** EIA-930 fuel values contained isolated spikes (SRP gas up to 69,905 MWh against a 99th percentile of 4,519). A cap flags 105 BA-hours (84 on SRP); everything was recomputed. Forecast MAE gains moved by up to 2.5 points (SRP at 1 h 20.6% to 23.1%; AZPS at 24 h -0.2% to -1.2%), scheduling, conformal, consumption, water and framework results by 0.2 points or less, and the marginal-accounting results more (`docs/MARGINAL.md`, second correction). The earlier "40-55% carries over" statement is withdrawn.
- County labels were taken from the nearest well, up to 105 km away; replaced with a point-in-polygon lookup (22 of 192 cells changed; default ranking correlation 0.99 with the old one). La Paz County was missing from the groundwater pull. Queue capacity ignored hybrid-project columns (+19%).
- An unsourced list of data-center hubs was replaced by OpenStreetMap features.
- Headline forecast gains had been quoted from the neural net (one seed); LightGBM is the primary model and its gains are lower.
- **EIA-930 demand glitches contaminated the marginal-emission analysis.** Withdrawn: "AZPS has no stable marginal signal", "only SRP replicates", the marginal-fuel attributions for SRP and WALC, and "the interchange control helps AZPS and SRP". Corrected results are in section 3 and `docs/MARGINAL.md`.
- "AZPS has no carbon-water conflict" (section 7) and "SRP's water conflict is mainly a Palo Verde accounting artefact" (not supported) are superseded.

## 9. Limitations
- All framework outputs are scenarios on assumed inputs; none is validated. The siting score has no ground truth; revealed-preference evidence covers 25 cells in one metro.
- RQ3 is an association study with a diluted exposure; it cannot attribute outages to data centers and Arizona alone cannot be tested.
- Marginal emissions have no observed truth in this project; every marginal number is an estimate compared with another estimate, and results depend on EIA-930 cleaning rules (two were tried; a third could differ).
- Carbon intensity is production-based by default and does not reproduce measured plant CO2 within tolerance (above); EIA-930 timestamps are treated as UTC hours (results robust to +-1 hour; convention unresolved, though measured CO2 aligns best with a one-hour shift in all four BAs, consistent with hour-ending labels if CAMPD hours are hour-beginning).
- Water: plant-to-BA generation does not match EIA-930 for several BAs and fuels (AZPS gas 0.51, SRP gas 1.63); CSP timing unresolved; 2025 factors applied to 2021-2025; on-site cooling is an assumption.
- The neural network is single-seed with no intervals; RQ3 outlier thresholds used all years including the 2024 holdout; the forecast variant using demand features (`resid_demand`) was re-run after the fuel cap but not studied further.
- Policy facts come from web search only (checked 2026-10-11); the eDocket and statutes were not read (`docs/regulatory_context_check.md`).

## 10. What the project does and does not contribute
No single piece is a new method (`docs/LITERATURE.md`, a first pass from search excerpts, not full papers): carbon-aware scheduling, average-versus-marginal signals (Sukprasert et al., e-Energy 2024, 65 regions), carbon-water scheduling and flow-traced
consumption carbon all have prior work. What this project adds is a **single audited pipeline for Arizona** that connects the three decisions, reports its nulls and withdrawn claims, and shows how conclusions depend on assumptions:
the carbon figure depends on the accounting, the water conclusion on the cooling and CSP assumptions, and the siting answer on project size and the weights. The one possibly open gap found, a utility-panel study of reliability effects of data-center load, cannot be filled with the public data used here
(no dated openings or capacities; a commercial tracker has them at $4,900 one-time, not used; `docs/RQ3_DC_EXPOSURE.md`).

## 11. Reproducibility
Run order and commands: `README.md`. Scripts take no required arguments and use the project venv (`.venv/bin/python src/<script>.py`); `data/` is git-ignored and rebuilt by the download scripts; the EIA API key lives in `.env` (never committed).
CPU only (Apple M4 was sufficient). Pre-fix outputs are kept in `results/_audit_before/`. The one pre-registered test and its four recorded deviations are in `docs/MEF_SCAN_PREREG.md`.

## 12. Still to do before submission
1. Confirm ACC docket facts against the eDocket and statutes; correct the proposal's citations and the Colorado River figure (about 27% for 2027-28, from web search).
2. Finish the literature check (siting optimization, ERCOT/Virginia event studies, full reads of the closest papers) and fill the reference list from verified sources.
3. Figure pass: choose the final figure set from `results/figures/`, and caption each with its limit.
4. Presentation deck built from sections 1, 3-7 with section 8's corrections visible.

## References (to be verified against the papers before submission)
Named in `docs/LITERATURE.md` from search results and abstract pages, not full reads: Macknick et al. (2012) water factors; Sukprasert, Bashir, Souza, Irwin, Shenoy (ACM e-Energy 2024); Wiesner et al. (Middleware 2021);
Siler-Evans et al. (2012); Holland and Mansur (2008); Chalendar et al. (2019). Data sources: EIA-930, EIA-860, EIA-861, EIA-923, EPA eGRID, LBNL Queued Up, USGS/ADWR GWSI, NASA POWER, OpenStreetMap, Census TIGERweb, HIFLD.
