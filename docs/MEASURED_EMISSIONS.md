# Estimated vs measured CO2: does the carbon-intensity series hold up against plant measurements?

Question: every RQ1 number rests on hourly CO2 built from EIA-930 fuel mix times annual eGRID 2023 emission factors (`src/carbon_intensity.py`). EPA's Clean Air Markets (CAMPD) publishes
**measured** hourly CO2 for fossil units of 25 MW or more. How close is the estimate, and does the scheduling conclusion change if measured values are used?
Code: `src/measured_emissions_check.py`, `src/measured_emissions_downstream.py` (run with `.venv/bin/python -I`: downloaded inputs). Outputs: `results/measured_emissions_*.csv`,
`data/processed/ci_measured.parquet`. Both decision rules were written in the script docstrings before the comparisons were computed; one post hoc variant is labelled below.

## Data
EPA CAMPD per-state hourly bulk files, 2021-2025, Arizona and New Mexico (public, no key; `src/download_static.sh`). New Mexico is needed because EIA-923 assigns **Four Corners (NM)** to AZPS: with Arizona
files alone the estimate looked 3.3 times the measurement for AZPS, which was a coverage error in my first run, not a property of the estimate. Plants are mapped to BAs by the 2025 EIA-923 assignment and
that map is applied to all years (assumption). CAMPD Facility ID is treated as the EIA plant code (it matched).

## Step A: estimated fossil CO2 vs measured CO2 (2021-2025, hours with unflagged EIA-930 data)
Pre-specified rule: "confirmed" if the estimate is within +-10% of measured in total and the hourly correlation is at least 0.95.

| BA | Estimate / measured (total) | Hourly Pearson | After dropping glitch hours (share of hours) Pearson / Spearman | Confirmed? |
|---|---|---|---|---|
| AZPS | 0.95 | 0.937 | 0.941 / 0.940 (0.7%) | no (correlation just short; level within 10%) |
| SRP | 0.80 | 0.622 | 0.909 / 0.897 (0.2%) | no |
| TEPC | 0.81 | 0.684 | 0.687 / 0.675 (1.0%) | no |
| WALC | 0.70 | 0.564 | 0.837 / 0.844 (0.5%) | no |
By year the ratio is 0.91-1.00 (AZPS), 0.74-0.83 (SRP), 0.64-1.00 (TEPC), 0.58-0.77 (WALC) (`results/measured_emissions_check.csv`). The gap is nearly flat across the day (by 6 h block: AZPS 0.90-0.99, SRP 0.75-0.81, TEPC 0.76-0.84, WALC
0.68-0.71; `results/measured_emissions_hourblock.csv`), so it behaves like a level offset, not a distortion of the daily shape.

What it means, and what it does not:
- **Not confirmed on the rule, for every BA.** The estimate is 20-30% below measured on SRP, TEPC and WALC. I cannot say which side is wrong: CEMS reports whole plants, while EIA-930 reports each BA's share of jointly owned plants
  (Springerville, Four Corners and others), so measured CO2 can overstate a BA's share. Attribution is the likely reason (the same kind of mismatch appeared in the water cross-check, `docs/WATER_MEASURED.md`), but I did not test it.
- **The low Pearson correlations are driven by a few glitch hours in the EIA-930 fuel series** (0.2-1.0% of hours; the estimate reaches 29.6 million kg an hour on SRP against a typical 1.4 million). They are the fuel-series counterpart of the demand
  glitches found earlier. `carbon_intensity.py` flags only null fuel values, not implausible ones.
- **TEPC stays weak** (Spearman 0.675 even after dropping glitches; 0.39 against gas-plus-coal generation): the TEPC fuel mix and the plants mapped to TEPC do not line up well.
- **Timing.** Measured CO2 matches EIA-930 best when CEMS hour h is paired with EIA-930 label h+1, in all four BAs (SRP Spearman 0.885 at shift 0, 0.916 at +1; `results/measured_emissions_lagcheck.csv`). That is what
  hour-ending EIA-930 labels would produce, **if** CAMPD hours are hour-beginning local standard time (assumed, not verified here). It is evidence on the open timestamp convention, not a resolution; the pipeline is unchanged
  (the weather shift test already showed results robust to one hour).

## Step B: does the scheduling conclusion survive? (`measured_emissions_downstream.py`)
Alternative series: fossil CO2 replaced by measured CO2 (aligned with the +1 h shift), non-fossil CO2 and denominator unchanged. It is a sensitivity series, not the truth (same attribution caveat). Design as in RQ1: 8 h preemptible job,
persistence decision, % saved against random timing. Pre-specified rule: robust if (a) savings on the alternative series are within 3 points of the savings on the estimated series and (b) the decision from the estimated series keeps at
least 90% of the saving when scored on the alternative.

| BA, year | Saving, estimated series | Saving, alternative series | Gap (pts) | Share kept by the estimated decision | As specified | Post hoc band variant |
|---|---|---|---|---|---|---|
| AZPS 2024 | 15.7 | 11.4 | -4.3 | 0.99 | not robust | not robust |
| AZPS 2025 | 25.5 | 11.8 | -13.8 | 1.03 | not robust | robust (25.3 vs 23.1) |
| SRP 2024 / 2025 | 17.7 / 18.2 | 16.9 / 18.4 | -0.8 / +0.2 | 0.96 / 0.96 | robust | robust |
| TEPC 2024 | 8.2 | 7.2 | -1.0 | 0.30 | not robust | not robust |
| TEPC 2025 | 11.9 | 5.3 | -6.6 | 0.93 | not robust | not robust |
| WALC 2024 / 2025 | 11.5 / 13.8 | 10.0 / 11.7 | -1.6 / -2.0 | 0.98 / 0.95 | robust | robust |
(`results/measured_emissions_scheduling.csv`.) The post hoc variant sets hours outside [0.3, 2.5] times the BA's month-and-hour median to missing in both series and uses the same days for both. I added it after seeing that four extreme hours in the
alternative AZPS series (up to 70,652 kg/MWh) dominated its mean-based saving; the as-specified result stands as the primary one.

Reading it:
- **The qualitative conclusion holds**: scheduling by yesterday's same-hour intensity saves carbon on every BA and year under either series (5-25%), and SRP and WALC are robust to the swap by the rule.
- **The size is sensitive on AZPS and TEPC.** AZPS 2025 halves unless the glitch hours are removed, and AZPS 2024 loses 4 points under both versions. TEPC's saving falls to about 5-7%, and in 2024 the estimated-series decision keeps only 30% of what a
  measured-series decision would save. A pooled "about 24%" headline is therefore best read as an upper-range figure for AZPS and TEPC.
- Mean levels also differ (kg/MWh, estimated vs alternative: AZPS 509 vs 544, SRP 217 vs 279, TEPC 519 vs 681, WALC 189 vs 277), which matters for any absolute carbon number, not for the ranking of hours.

## Re-run after the fuel cap (2026-11-10)
After `carbon_intensity.py` began flagging implausible fuel values (`docs/MARGINAL.md`, second correction) both scripts were re-run (earlier outputs: `results/_audit_before/before_fuel_qc_2026-11-10/measured/`). The verdicts do not change. SRP's hourly correlation with measured CO2 rises from 0.62 to 0.91 because its 84 spike hours are gone, the totals are
0.95 / 0.78 / 0.81 / 0.69 (AZPS / SRP / TEPC / WALC), and the pre-specified rule still fails on all four. The scheduling table above is unchanged to within 0.1 point except AZPS 2025 (25.6% and 11.8%) and WALC 2024 (11.5% and 9.9%). The glitch-hour counts and the 29.6-million-kg example in Step A describe the series before the cap.

## Limits
- CEMS covers fossil units of 25 MW or more; small units, solar, wind, hydro, nuclear and storage are not measured here. The estimate covers all fossil generation in the BA, so a small gap in the estimate's favour is expected.
- The plant-to-BA map is the 2025 EIA-923 assignment applied to 2021-2025. Jointly owned plants are attributed whole to one BA.
- Not done: LightGBM forecasts and the marginal-emission profiles on the alternative series (only persistence decisions were tested), consumption-based carbon on measured values, earlier plant-to-BA maps.
- Two test years only; a few percentage points of difference are not conclusive.

## What changes elsewhere
- `docs/AUDIT.md` row on the production-based carbon assumption; `docs/FINAL_REPORT.md` sections 2, 3 and 9. The RQ1 headline is stated as a range for AZPS and TEPC.
- `src/carbon_intensity.py` is unchanged. A plausibility flag for fuel-series values (the band rule used here) would be the natural fix; it was not applied to the series that earlier results were built on.
