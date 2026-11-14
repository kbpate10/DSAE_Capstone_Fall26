# Consumption-based carbon intensity (flow tracing)

Question: the production-based intensity says AZPS and TEPC are dirty and SRP and WALC are clean, partly because of where
plants are reported. Does a consumption-based intensity (carbon of the power a BA actually receives) change that picture,
and does it change the RQ1 scheduling result? Code: `src/pull_neighbor_fuel.py`, `src/consumption_carbon.py`.
Outputs: `data/processed/consumption_ci.parquet`, `results/consumption_ci_summary.csv`, `results/consumption_scheduling.csv`,
`results/figures/consumption_ci.png`.

## Method
Hourly flow tracing. The intensity of everything a BA supplies (its own consumption and its exports) is
`c_b = (CO2_b + sum_j I_jb * c_j) / (G_b + sum_j I_jb)`, with G_b generation, I_jb imports from BA j (from b's own interchange
report). For the four Arizona BAs the c_j are unknowns, so each hour is a 4x4 linear system; external BAs use their own
production-based intensity (eGRID factors, same method as `carbon_intensity.py`). External BAs pulled: PNM, WACM, EPE, GRIF, GRID,
DEAA, HGMA, PACE, IID, CISO (the sources of nearly all imports; NEVP and LDWP are small and left out).

## Limits
- An hour is valid only if every Arizona BA's generation is unflagged and each BA's known-source share of imports is at least 95%.
  Invalid hours are excluded, not imputed. **40,308 of 43,824 hours (92%) are valid, but only 243 of the 2025 days are complete
  for each BA** (vs 353-363 in earlier scheduling runs), so the scheduling check uses a different, smaller set of days.
- External intensities use eGRID BA factors with fallback to Arizona and then US factors per fuel. Usable hours: HGMA 41%,
  DEAA 82%, GRIF 89% (and GRIF data covers only 24,824 hours), others 99-100%. SRP depends most on those three small BAs.
- Average-mix delivered, not marginal. Interchange between two Arizona BAs is reported by both and differs by a few percent
  (`data_dictionary.md`); each BA's own report is used for its imports.
- "Imports" here are gross (flows into the BA), including power that passes through and is exported again. They are larger
  than the net imports in `MARGINAL.md` (for AZPS, 60% of supply gross vs 37.5% of demand net).

## Results (valid hours, 2021-2025)
| BA | Gross imports, % of supply | Production (kg/MWh) | Consumption (kg/MWh) | Hourly corr. | Within-day corr. |
|---|---|---|---|---|---|
| AZPS | 60.5 | 508 | 364 | 0.81 | 0.84 |
| SRP | 19.0 | 216 | 250 | 0.96 | 0.97 |
| TEPC | 32.9 | 515 | 455 | 0.94 | 0.90 |
| WALC | 57.0 | 191 | 320 | 0.69 | 0.58 |

1. **The ranking changes.** Production-based: WALC < SRP << AZPS ~ TEPC. Consumption-based: SRP < WALC < AZPS < TEPC.
   AZPS is 28% cleaner than its production figure because most of what it receives comes from SRP; WALC is 67% dirtier because it
   imports from AZPS and from the higher-intensity WACM, GRID and GRIF. Since the caveat in the project notes that "SRP looks clean mainly
   because Palo Verde is reported there" is about the BA's own generation, consumption accounting is the check on it: SRP stays the cleanest of the
   four (250), though 16% above its production figure.
2. **The hourly shape is mostly preserved except for WALC.** Within-day correlation between the two signals is 0.84-0.97 for
   AZPS, SRP and TEPC and 0.58 for WALC.
3. **The scheduling savings mostly survive the change of accounting.** 8 h preemptible job, 2025, % vs random timing,
   decision on yesterday's same-hour intensity:

   | Decision signal | Evaluated on production | Evaluated on consumption |
   |---|---|---|
   | Production | 18.1 pooled (AZPS 25.8, SRP 20.1, TEPC 11.7, WALC 14.8) | 14.1 (AZPS 20.9, SRP 18.0, TEPC 15.8, WALC 2.0) |
   | Consumption | 15.0 (AZPS 25.8, SRP 20.4, TEPC 12.0, WALC 1.7) | 15.5 (AZPS 21.0, SRP 18.4, TEPC 16.6, WALC 6.2) |

   Savings stay at 12-26% for AZPS, SRP and TEPC under either accounting; WALC falls to 2-6% when its signal is judged on consumption.
   Together with `MARGINAL.md` (corrected for a demand data-quality problem): the savings are **robust to average-mix accounting (production vs consumption)**; scored on the marginal
   estimate the share that carries over is not stable (pooled 8.3% in 2024 and 14.4% in 2025, against 14.0% and 18.2% by average accounting; see `MARGINAL.md`), with sign flips by BA in single years.

## What this does not settle
- The result is for persistence decisions, not the LightGBM forecast.
- The Stage 2 siting coupling was re-run with this intensity (`STAGE2.md`): selections are unchanged, and the carbon of the Stage 1 set falls 15%
  (2,905 -> 2,456 kt/yr) because AZPS gets cleaner and SRP dirtier. Water remains production-side.
- Consumption accounting for a **new** load is itself an approximation: adding a large load changes flows, which this
  average-mix measure does not capture. That needs the marginal view, whose grid-response version still lacks a stable estimate.

## Next
- Add the external BAs' marginal fuel response to complete a grid-response marginal rate (needs the same interchange and fuel data).
