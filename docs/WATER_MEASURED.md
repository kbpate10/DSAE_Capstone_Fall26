# Generation-side water from measured plant data (EIA-860 / EIA-923)

Question: the water side of the carbon-water analysis used literature medians (Macknick et al. 2012), one factor per fuel for every BA, with all solar
treated as PV. EIA collects plant cooling-system data and cooling-water consumption. What do the measured values say, and does the carbon-water conclusion
change? Code: `src/build_water_factors.py` (run with `.venv/bin/python -I`, because it reads downloaded files), `src/water_measured.py`; the generalised
`water_frontier.build` accepts a BA-specific factor table (default behaviour is bit-identical: verified by a fingerprint of its output).
Outputs: `data/processed/water_factors_measured.parquet`, `results/water_plant_cooling_az.csv`, `results/water_measured_factors.csv`,
`results/water_factors_crosscheck.csv`, `results/water_measured_cases.csv`, `results/water_measured_levels.csv`.

## Data
| Source | Used for | Notes |
|---|---|---|
| EIA-923 Schedule 8D, 2025 | monthly cooling-water consumption (million gallons) per cooling system | Collected for plants with combustible-fuel steam capacity of 100 MW or more, plus nuclear; small turbines, PV, wind and hydro do not report. EIA writes "." for missing months (42 of 468 Arizona-plant rows) |
| EIA-923 Page 1, 2025 | monthly net generation by plant, fuel and prime mover, with the plant's BA | prime mover `CP` is concentrating solar, `PV` photovoltaic |
| EIA-860 Schedule 6D / 2 Plant, 2025 | cooling type, plant-to-BA link | |
Files are downloaded by `src/download_static.sh` (the 2025 data year; the 2024 paths on eia.gov returned errors when tried).

## Findings
**1. Every reporting Arizona thermal plant is wet-cooled.** Reporting plants use recirculating induced-draft cooling towers (most), recirculating
cooling ponds (Four Corners, Cholla) or, in retired or out-of-service units at Kyrene, once-through cooling with zero hours. None reports dry cooling.

**2. Measured consumption per kWh differs from the literature factors** (L/kWh, 2025; `results/water_plant_cooling_az.csv`):
| Fuel | Measured, reporting plants | Literature factor used |
|---|---|---|
| Natural gas (combined cycle) | 0.98 to 1.72 (Agua Fria, a small peaker, 3.60) | 0.75 |
| Coal | 1.08 (Springerville), 1.95 (Four Corners), 2.03 (Coronado) | 2.60 |
| Nuclear (Palo Verde) | 2.75 | 2.54 |
| Solar thermal (Solana) | 3.36 | solar PV 0.10 |
So gas uses roughly 1.3 to 2.3 times the literature factor and coal about 40 to 80% of it, nuclear is 8% higher, and Solana, which is 15% of AZPS's 2025 solar
generation (846 of 5,586 GWh), uses about 34 times the PV factor.

**3. BA-level generation-side water per kWh of IT energy** (incl. PUE 1.2 and the hourly mix, 2021-2025 mean; `results/water_measured_levels.csv`):
| BA | Literature | Measured M1 (non-reporting fossil = 0) | Measured M2 (non-reporting fossil at literature) |
|---|---|---|---|
| AZPS | 1.56 | 1.51 | 1.65 |
| SRP | 2.19 | 2.44 | 2.44 |
| TEPC | 1.49 | 1.09 | 1.10 |
| WALC | 0.41 | 0.69 | 0.72 |
Levels move by -27% (TEPC) to +68% (WALC); AZPS's total barely moves because lower coal water offsets higher gas and solar-thermal water.

**4. The carbon-water conclusion changes for AZPS only.** 8 h preemptible job, persistence forecasts, 2025, change in water under a carbon-only schedule
(+ = saves water; vs random timing; `results/water_measured_cases.csv`), nuclear counted as freshwater, hydro 0:
| | Pooled | AZPS | SRP | TEPC | WALC |
|---|---|---|---|---|---|
| Literature (Midpoint 1 base; reproduced) | -0.1 | **+4.1** | -5.3 | -2.5 | +8.6 |
| Measured M1 | -0.7 | **-1.6** | -4.3 | -2.1 | +9.5 |
| Measured M2 | -0.2 | **-0.1** | -4.2 | -1.9 | +9.6 |
| M1 with Solana counted as PV | +0.8 | +4.6 | -4.3 | -2.1 | +9.5 |
- **SRP and TEPC keep a modest conflict** (carbon-only uses about 2-5% more water than random timing) and WALC still saves water unless hydro reservoir evaporation is
  counted (-16.9% with hydro at 17 L/kWh, against -17.8% in the literature case). These conclusions are robust to measured factors.
- **AZPS no longer shows "no conflict".** The Midpoint 1 statement that AZPS has no conflict in any scenario is **not supported** once Solana is separated from PV: AZPS goes from
  +4.1% to between -1.6% and -0.1%. The comparison with the last row shows the cause is the solar-thermal plant, not the gas factors (with Solana counted as PV, AZPS stays at +4.6%).
  Within-day correlation of carbon and water on AZPS changes from +0.28 to -0.18.
- The balanced weighting (alpha = 0.5) saves 2.5% to 2.7% of water pooled (literature 3.7%).
- Stage 2 siting coupling with measured generation water: water saving from weighting water at 0.5 is 5.28%, against 5.46% for the base case; selections and carbon are unchanged
  (`results/stage2_sensitivity.csv`, case "measured generation water").

## Limits (read before using any number)
- **CSP timing is not resolved.** EIA-930 has one solar category, so Solana's water is spread over that month's solar hours in proportion to generation. Solana has thermal storage and
  generates into the evening, so the true water is later in the day than this assumes. Putting its water on the midday hours that are cleanest overstates the carbon-water conflict on
  AZPS. The two bounds are -1.6% (as built) and +4.6% (Solana counted as PV); the truth lies somewhere between, and an hourly CSP profile would be needed to say where.
- **Plant-to-BA generation does not match EIA-930.** 2025 generation by BA and fuel from EIA-923 against EIA-930 (`results/water_factors_crosscheck.csv`): SRP nuclear 1.00,
  solar 1.09 to 1.16 on the three large BAs, wind 0.85 to 1.00, but AZPS coal 1.30, AZPS gas 0.51, SRP coal 0.61, SRP gas 1.63, TEPC coal 1.82, TEPC gas 0.55, and WALC solar 6.2 (WALC's
  hydro 1.7). I did not establish the cause; jointly owned plants and how each BA's series attributes their output are the likely reasons. The factors are intensities per plant, so the
  mismatch matters through the weights within a BA and fuel, not the volumes; it is a risk for AZPS gas (one reporting plant out of six, coverage 0.84).
- **Coverage.** Reporting plants cover 84-100% of gas, 95-100% of coal and all nuclear generation; non-reporting fossil generation is bounded by M1 (zero) and M2 (literature factor).
  PV, wind and hydro have no measured water (PV keeps the 0.10 literature value).
- **2025 factors are applied to 2021-2025.** Earlier EIA-923 years were not pulled.
- Missing months ("." in EIA-923) are dropped from numerator and denominator, not imputed (for example Coronado and Harquahala have 11 valid months; Cholla, with 9 of 12 months missing, does not enter the reporting set and so counts as non-reporting coal).
- On-site data-center cooling water is not in EIA data; the evaporative curve and PUE 1.2 remain assumptions.
- The 2025 test year is the only evaluation year for the scheduling rows, so differences of a point or two are not conclusive.

## What changes in the other documents
- Midpoint 1, section 6: "AZPS has no conflict in any scenario" is superseded by the table above; the SRP, TEPC and WALC statements stand.
- `docs/ARIZONA_CASE_STUDY.md` water-scheduling figures use the literature factors; the measured case moves them by a few points and does not change its conclusion that cooling design is a larger water lever than timing.
