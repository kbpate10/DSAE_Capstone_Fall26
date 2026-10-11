# Self-audit: what was re-checked, what was wrong, what remains assumed

Scope: every result and claim in the midpoint-1 package was re-checked against the code and the files. The goal
was to find places where something was assumed rather than shown. Checks are reproducible from
`src/audit_checks.py`, `src/audit_rolling_origin.py` and `results/audit_checks.txt`.

## A. Errors found and fixed

| # | Problem | Evidence | Effect | Fix |
|---|---|---|---|---|
| 1 | La Paz County (FIPS 012) was skipped in the groundwater pull: the loop used only odd county codes | pull returned 751 more measurements and 283 more wells once added | Trend feature missing for a region of the map; trend wells 414 to 425 | Added code 012 and re-pulled |
| 2 | County of each cell was taken from the nearest USGS well, up to 105 km away (35% of cells more than 10 km) | Census point-in-county lookup disagreed for 22 of 192 cells; Greenlee and La Paz were invisible; Maricopa had 41 cells, now 29 | County-level queue strain assigned to the wrong cells | Replaced with a TIGERweb point-in-polygon lookup |
| 3 | Queue capacity used `mw_1` only, ignoring `mw_2` and `mw_3` of hybrid projects; "Mojave" typo split Mohave County | Active Arizona queue is 106.6 GW summed vs 89.8 GW with `mw_1` alone (+19%) | Queue-strain feature understated, mostly for hybrids | Summed all three columns; merged the typo |
| 4 | The list of data-center hubs used in the siting "face validity" bullet came from general knowledge, not from a source | No dataset in the project contained those locations | A headline-style statement rested on an unverified input | Replaced with 65 OpenStreetMap features; Tucson, Marana and Casa Grande are not supported by OSM and were dropped |
| 5 | Headline forecast gains (15-32% at 1 hour, 4-5% at 24 hours) were the neural net's, which was the better model on the test year and is a single seed | LightGBM-only: 13-26% at 1 hour; 24 hours: AZPS -0.2%, SRP 3.9%, TEPC 2.1%, WALC 4.0% | Gains were stated as larger than the primary model supports | Report LightGBM as primary; neural net as secondary with its own column |
| 6 | RQ3 upper bound was quoted as "about +2%" | Largest 95% upper bound across specifications is +2.5% | Slightly optimistic bound | Quoted as +2.5% |
| 7 | "1.06M hourly rows" reads as 1.06M hours | Those are fuel-by-hour records; the unit of analysis is 175,208 BA-hours | Overstated apparent size | Reworded |

Effect of fixes 1-3 on the siting results: the old and new default rankings correlate at 0.988, 11 of the top 12
cells are unchanged, the rank-stability numbers are unchanged (median 0.82), and AUC moved from 0.96-0.99 to
0.96-0.99. Conclusions stand; counts per county and some ranks changed.

## B. Assumptions tested and found robust

| Assumption | Test | Result |
|---|---|---|
| Residual-over-persistence design (chosen after seeing 2025 results) generalises | Rolling-origin: train 2021-22, early-stop 2023, test 2024 | Raw-level model again loses to persistence at 24 h (TEPC -56%, AZPS -13%); residual model is -3% to +6% vs persistence. Day-ahead gains stay marginal |
| RQ3 null is not an artifact of mixing reliability-reporting standards (15% of utilities switch between IEEE and other) | Drop switchers; IEEE only; add indicator | +0.5% [-1.5, +2.5], +0.1% [-1.9, +2.2], +0.6% [-1.2, +2.5]: null holds |
| Weather and EIA-930 hours are aligned | Shift weather by +-1 hour and re-run the frontier | Within-day correlation of carbon with on-site water stays -0.4 to -0.6; carbon-only water effect -0.1% to +0.5%; balanced 3.7-4.1% |
| eGRID CO2 tons are short tons | Compare reported lb/MWh rate with `PLCO2AN * 2000 / PLNGENAN` | Ratio 1.000, so short tons (907.18 kg) are correct |
| Treating EIA-930 "other" as eGRID "other fossil" matters | Share of generation times the factor | Under 0.4% of mean carbon intensity on every BA |
| Forecast features leak the future | Reviewed lags, rolling windows and demand features against the forecast origin | None found; all lags are at or before t-h and calendar/demand-forecast features are known in advance |
| Scheduling uses only information available at decision time | Checked that 24-hour-ahead values for every hour of a local day derive from times before local midnight | Holds |

## C. Still assumed or unverified

| Item | Why it matters | What would resolve it |
|---|---|---|
| EIA-930 timestamp convention (EIA documents hour-ending labels; the API's time zone is treated as UTC) | A one-hour offset between generation and weather | Compare a raw API response across a known event; results are robust to +-1 h |
| eGRID biogenic exclusion in `PLCO2AN` | Small effect on a few plants | eGRID technical documentation |
| Outlier thresholds and winsorising for RQ3 use all years, including the 2024 holdout | Minor leakage in the Bayesian calibration check | Recompute thresholds on the training years only |
| Siting weights and queue-strain direction | The ranking depends on them | Revealed-preference model with real data-center locations |
| OSM completeness | Only 65 features statewide; some mis-tagged | A curated list of facilities |
| Exposure proxy is C&I load per *total* customer, not data-center load | Diluted; cannot isolate data centers | A data-center-specific measure |
| Water model: on-site curve shape, PUE 1.2, all solar as PV, gas as wet-cooled | Shifts the water side of the frontier | EIA-860 cooling types; literature fit |
| Regulatory claims | Fact-checked by web search only | eDocket and session laws |
| Neural net is a single seed | Differences near 1 kg/MWh are noise | Multi-seed run |
| Carbon intensity is production-based | Not what a load actually consumes | Interchange-based intensity |

## D. Checked and correct
Panel keys (no duplicate BA-hours or utility-years), unit conversions (gal/MWh to L/kWh, short tons to kg),
time-zone arithmetic (Arizona has no daylight saving; solar generation peaks around local noon and demand
around 18-19 h), chronological train/validation/test splits, the paired bootstrap and the common-sample
design of the baseline ladder, and Palo Verde's water use against its reported effluent purchases.
