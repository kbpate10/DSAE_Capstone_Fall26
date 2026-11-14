# Marginal vs average emissions

Question: does the carbon-aware scheduling conclusion (RQ1) change when the signal is the marginal emission rate instead of average carbon intensity?
Code: `src/marginal_emissions.py`, `src/interchange_analysis.py`, `src/mef_robustness.py`. Outputs: `results/mef_*.csv`, `results/interchange_*.csv`, `results/figures/mef_profiles.png`.

## Correction (read this first)
**Every marginal-emissions number in earlier versions of this document and in the Midpoint 2 report was computed on demand data that contained glitches, and several conclusions were wrong.**
EIA-930 demand has non-positive and absurd values (SRP 70,313 MWh against a median of 3,407; WALC from -50,457 to +94,444; 53 hours across the four BAs fail a plausibility rule; one AZPS net-export value of 24,000 MWh
against a median of -1,337). In a regression of the hourly change in CO2 on the hourly change in demand a single such hour has large leverage. I found the problem while running a multi-BA scan (PJM contains a 32-bit sentinel
2,147,483,647 and a value of 431 million), then checked the Arizona series. Demand is now set to missing when it is not positive or exceeds 5 times the BA's median, and net export is masked by the same rule
(`marginal_emissions.load`, `interchange_analysis.mask_ne`). Pre-correction outputs are in `results/_audit_before/*_before_demand_qc.csv`.

What changed (6 h bins, base specification, profile correlation train 2021-24 vs 2025):
| BA | Before | After |
|---|---|---|
| AZPS | -0.58 | **+0.57** |
| SRP | 0.62 | 0.70 |
| TEPC | 0.66 | 0.76 |
| WALC | +0.60 | **-0.61** |
Claims withdrawn: "AZPS has no stable marginal signal", "only SRP replicates", "SRP's demand changes are met by gas (0.98-0.99)", "WALC's by hydro (0.86-0.99)", "interchange control helps AZPS and SRP",
and "the marginal-profile decision wins under marginal accounting does not replicate" (it does, see below). Not affected: the average and consumption-based carbon series (they use fuel mix, not demand), the RQ1 forecasts
from the primary model (`resid_lags` uses only carbon lags). Not re-run: the secondary forecast variant that uses demand features (`resid_demand`).

## Second correction (2026-11-10): implausible fuel values
The EIA-930 *fuel* series also has isolated spikes (SRP natural gas up to 69,905 MWh against a 99th percentile of 4,519; WALC hydro 94,562 against 1,364). `src/carbon_intensity.py` now sets any fuel value above 3 times that BA-fuel's 99th percentile to missing,
which flags the hour (105 BA-hours, 84 on SRP; no other hour changed). Everything below was recomputed; the earlier numbers are in `results/_audit_before/before_fuel_qc_2026-11-10/`. What moved: the SRP gas response (0.69 to 0.63), the AZPS 2025 profile correlation (0.57 to 0.67) and
level disagreement (75% to 59%), the effect of the interchange control (now helps SRP and AZPS 2025), and above all the **marginal-accounting scheduling numbers: AZPS 2025 went from 17.4% to 49.1% on five flagged AZPS hours**, so the "about 40-55% carries over" statement is withdrawn (see point 5). Forecasts, scheduling under average accounting, consumption-based carbon and water results moved by 0.2 points or less.

## Method
- **MEF** (kg CO2 per MWh of demand change) per BA is the slope of the hourly change in in-BA generation CO2 on the hourly change in BA demand (EIA-930, eGRID-based emission factors), by local hour-of-day bin and
  season (summer = Jun-Sep). Flagged hours, the hour after a flagged hour, and gaps are dropped, not interpolated. The same regression per fuel gives the marginal fuel response.
- **Scheduling comparison**, 8 h preemptible job, same BA-days as `schedule_eval.py`. Decision signals use information before the test year: average-CI persistence, or the MEF profile estimated on the training years.
  Savings are % vs random timing, under two accountings: average CI (as in RQ1) and the MEF re-estimated on the test year.

## Limits (read before using any number)
- **In-BA, production-based only**: an hour met by imports reads as "no marginal generation". AZPS and SRP trade heavily; these MEFs describe generation inside each BA, not the grid that would respond to a new load.
- **Association, not a causal effect.** Demand changes co-move with temperature, solar ramps and dispatch.
- **There is no observed truth for marginal emissions.** The "marginal accounting" is itself an estimate (from the test year, same method), so savings under it measure agreement between two estimates, not which signal is right.
- **Percent savings under the MEF accounting can be ill-conditioned.** AZPS's 2025 test-year profile has a negative cell (-77 kg/MWh, summer midday) and an extreme one (605), so its savings against that baseline can exceed 100%.
  Read the sign and rough size, not the percentage.
- The `mef_oracle_eval` rows pick hours from the same numbers they are scored on (in-sample). Ignore them. With 6 h bins, hours inside a bin tie; ties are broken by hour order.

## Results (cleaned data)
1. **Marginal fuel response** (`mef_marginal_fuel.csv`, MWh of fuel per MWh of demand change, 2021-2024; the totals are below 1 because interchange absorbs part of the change). Gas is the largest response on AZPS (0.55 other seasons, 0.47 summer),
   SRP (0.63, 0.49) and TEPC (0.62, 0.34), with small coal (0.02-0.08) and solar and wind movements that reflect ramp timing, not causation (AZPS solar -0.10 other / +0.13 summer, TEPC -0.20 other). WALC is different: little gas (0.08, 0.21) and
   hydro that rises in summer (0.06, 0.43).
2. **Hourly MEF profiles are not stable**: train 2021-24 vs 2025 correlation 0.26 (AZPS), 0.13 (SRP), 0.07 (TEPC), 0.08 (WALC). An hourly signal cannot be used from this data.
3. **6 h blocks are usable on three of four BAs.** Profile correlation train vs test, base specification: AZPS 0.60 (test 2024) / 0.67 (2025), SRP 0.70 / 0.70, TEPC 0.60 / 0.76, WALC 0.65 / **-0.60**. Level disagreement (mean absolute train-test difference as % of the train mean):
   AZPS 20% / 59%, SRP 32% / 30%, TEPC 65% / 37%, WALC 33% / 66%. Mean MEF against average intensity (kg/MWh, 2021-24): AZPS 236 vs 529, SRP 395 vs 216, TEPC 247 vs 538, WALC 53 vs 188. The shape is stable on AZPS, SRP and TEPC; the level moves by a third to three quarters.
   Only 8 block-season cells enter each correlation.
4. **Controls do not reliably help.** Weather (change in temperature and wet-bulb) leaves TEPC about the same and lowers AZPS (0.51 / 0.42 against 0.60 / 0.67) and SRP (0.34 / 0.26 against 0.70 / 0.70); it raises WALC's profile (0.77 / -0.20 against 0.65 / -0.60), which is still unstable in 2025.
   Holding net interchange fixed is mixed: it raises SRP (0.75 / 0.79 against 0.70 / 0.70) and AZPS in 2025 (0.79 against 0.67) but lowers AZPS in 2024 (-0.29 against 0.60) and TEPC (0.27 / 0.12 against 0.60 / 0.76), and WALC gets 0.19 / 0.07. With both controls the correlations are mostly lower (SRP 0.75 / 0.62 is the exception).
   The base specification is the most stable overall.
5. **The two signals disagree, and each wins on its own accounting.** 8 h preemptible job, 6 h bins, % saved vs random timing (decision signal from the training years; `mef_scheduling.csv`, `mef_scheduling_2024.csv`):

   | Test year | Decision signal | Evaluated on average CI (pooled; AZPS / SRP / TEPC / WALC) | Evaluated on the MEF estimate (pooled; AZPS / SRP / TEPC / WALC) |
   |---|---|---|---|
   | 2025 | average-CI persistence | 18.2 (26.2 / 20.6 / 12.5 / 13.8) | 14.4 (49.1* / 10.5 / 5.4 / -6.5) |
   | 2025 | MEF profile | 4.7 (1.3 / 13.0 / -0.6 / 5.1) | 42.8 (103.3* / 35.0 / 42.8 / -7.9) |
   | 2024 | average-CI persistence | 14.0 (16.4 / 19.0 / 8.5 / 11.6) | 8.3 (-3.8 / 18.6 / 2.6 / 16.1) |
   | 2024 | MEF profile | 4.6 (-0.3 / 12.7 / -0.4 / 6.4) | 26.7 (18.6 / 22.0 / 21.6 / 45.5) |
   *ill-conditioned, see limits. Reading it: scheduling on yesterday's average intensity saves 14-18% by average accounting and 8-14% pooled by the marginal estimate; scheduling on the marginal profile saves 5% by average accounting and 27-43% by the marginal one.
   The MEF-profile decision beats average persistence under marginal accounting on AZPS, SRP and TEPC in both years; WALC (stable in 2024, not in 2025) is mixed. So a "carbon saved" figure from RQ1 is specific to average accounting: the share that carries over is not stable: pooled 59% (2024) and 79% (2025), but 95% and 20% excluding AZPS, whose 2025 percentages are ill-conditioned (they moved from 17% to 49% when five flagged hours were excluded); sign flips by BA in single years (AZPS -3.8 in 2024; WALC -6.5 in 2025). Treat the carry-over as unstable, not as a fraction.

## Interchange (`interchange_analysis.py`, `pull_interchange.py`)
Identity: net generation = demand + net export. A demand change is met by in-BA generation or by a change in net interchange.
1. **The accounting is consistent enough to use.** Median generation - demand - net-export residual is 0 for AZPS and TEPC, 2 MWh for WALC, 19 MWh (0.5% of demand) for SRP; the 95th percentile is 376-824 MWh, so some hours are poor.
2. **Imports are large for AZPS and TEPC; SRP is a big exporter.** Mean net imports are 37.5% of demand for AZPS, 21.4% for TEPC, 10.0% for WALC and 0% for SRP, whose mean net export (2,811 MWh/h) is 72% of its mean demand.
3. **Share of a demand change absorbed by interchange** (6 h blocks, mean; train 2021-24 / 2025): AZPS 0.34 / 0.19, TEPC 0.21 / 0.40, SRP 0.11 / 0.11, WALC 0.54 / 0.01. The absorption is itself unstable year to year on AZPS, TEPC and WALC.
4. **Holding interchange fixed** raises the in-BA rate on every BA (kg/MWh: AZPS 236 to 335, SRP 429 to 471, TEPC 246 to 311, WALC 53 to 93), consistent with imports displacing in-BA generation. It does not reliably improve stability (results, point 4).
5. The fixed-interchange slope is the emission rate of in-BA generation, not a grid marginal rate: the grid response also includes the carbon of the imported power (exporting BAs' fuel mix, pulled for consumption-based carbon but not used here).

## What this does and does not change
- RQ1's headline savings are **average-intensity savings**: they survive production-to-consumption accounting (12-26% on AZPS, SRP, TEPC; `CONSUMPTION.md`) and carry over to the marginal estimate only partly and unstably (8.3% pooled in 2024, 14.4% in 2025; see results point 5).
- A 6 h marginal profile is usable on AZPS, SRP and TEPC; its level is unstable (a third to three quarters), so it supports ranking hours within a day, not absolute savings.
- The pattern that motivated the multi-BA hypothesis (AZPS, with the highest import share, looked unstable) was a data artifact. The pre-registered multi-BA test of whether import dependence predicts instability came out inconclusive (`docs/MEF_SCAN.md`): shape stability is not related to absorption; level disagreement is, mostly through a normalisation artefact.

## Next
- Compare the 6 h profiles with PJM's published marginal-fuel shares if the files can be downloaded (needs a PJM account; a price-setting margin, not a consequential response).
- Irradiance as a control for solar-ramp timing; more test years (2022, 2023).
