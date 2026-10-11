# Data dictionary

All sources are free, public, and contain no personal information. Row counts are from the files
as pulled for this project. "Flag, don't impute" is the default policy for gaps.

## Sources

| # | Dataset | Structure | Access | Rows / coverage | Used for |
|---|---|---|---|---|---|
| 1 | **EIA-930** hourly net generation by fuel | Hourly time series | EIA API v2 (`rto/fuel-type-data`), `src/pull_eia930.py` | 1,063,744 fuel-hour records (175,208 BA-hours); 4 BAs (AZPS, SRP, TEPC, WALC); 2021-01-01 to 2025-12-31 | Carbon intensity, generation-side water |
| 2 | **EIA-930** demand (D) and day-ahead demand forecast (DF) | Hourly time series | EIA API v2 (`rto/region-data`), `src/pull_demand.py` | 344,758 rows; same BAs and years | Forecast features |
| 3 | **EPA eGRID 2023** plant file (`PLNT23`) | Plant-level annual table | `src/download_static.sh` | 12,612 plants nationally, 157 in Arizona | CO2 emission factor per BA and fuel |
| 4 | **EIA-861** (2013-2024): `Reliability_*`, `Sales_Ult_Cust_*` | Annual utility panel | `src/download_static.sh` | 24,308 utility-state-years (outer join); 2,923 utilities; 12,111 with both reliability and sales | RQ3 outcome and exposure proxy |
| 5 | **LBNL Queued Up** (data through end of 2025) | Project-level records (spatial points by county) | `src/download_static.sh` | 38,201 projects; 1,049 in Arizona | Generator-queue strain (RQ2) |
| 6 | **ADWR GWSI** "Well Sites" layer | Spatial points | ADWR ArcGIS FeatureServer, `src/pull_adwr_gwsi.py` | 45,985 sites; 9,675 with a water level measured since 2015 | Groundwater depth (RQ2) |
| 7 | **USGS-hosted ADWR water-level series** (parameter 72019) | Per-well time series | USGS Water Data OGC API, `src/pull_groundwater.py`, `src/pull_wells_geo.py` | 29,652 measurements, 3,585 wells (all 15 counties; Greenlee has none) | Groundwater trend (RQ2) |
| 8 | **NASA POWER** climatology and hourly weather | Gridded (point queries) | NASA POWER API, `src/build_sites.py`, `src/pull_weather_hourly.py` | 192 cell climatologies; 3 sites x 43,824 hours (2021-2025) | Solar, wet-bulb (RQ2, water model) |

Heterogeneity: hourly time series (1, 2, 8), annual panel (4), plant table (3), spatial points (5, 6),
per-well time series (7), gridded climate (8).

## Derived tables (`data/processed/`)

Unified analysis tables built by `src/build_master.py`: `master_ba_hour.parquet` (BA x hour, 175,208 rows),
`master_utility_year.parquet` (utility x year, 11,845 rows). See [EDA.md](EDA.md) for their contents.

| File | Grain | Rows | Key columns |
|---|---|---|---|
| `carbon_intensity.parquet` | BA x hour (UTC) | 174,740 | `ci_kg_per_mwh`, `clean_share`, `gen_mwh`, `data_flag` |
| `emission_factors.csv` | BA x fuel | 32 | `ef` (kg CO2/MWh), `ef_source` (ba / az / us fallback) |
| `eia861_panel.parquet` | utility x state x year | 24,308 | SAIDI/SAIFI with and without major events, customers, C&I MWh, `_merge` |
| `rq3_panel.parquet` | utility x state x year | 11,845 | cleaned outcomes (`ln_saidi_nomed`, ...), `d_ln_ci_pc` (exposure), controls |
| `lbnl_queue_all.parquet` | project | 38,201 | `state`, `county`, `q_status`, `mw_1`, `type_clean` |
| `sites_az.parquet` / `sites_scored.parquet` | 0.25-degree cell | 192 | `gw_depth_med`, `gw_trend`, `ghi_kwh`, `wetbulb_summer_c`, `q_active_mw`, `score`, `rank` |

## Cleaning rules and known gaps

**EIA-930**
- Gaps are flagged, not interpolated: TEPC 2021 has 8,388 of 8,760 hours; AZPS 2025 has 8,664.
- 1,351 null values; 50,086 negative values (battery charging, solar auxiliary load at night).
- Storage and behind-the-meter codes (`BAT`, `UES`, `SNB`) are excluded from the generation mix;
  remaining negatives are clipped to 0.
- 667 BA-hours (0.4%) carry `data_flag = True` and are excluded from model targets.
- `D` for SRP in 2022 is incomplete (13,458 of 17,520 demand+forecast rows).

**Carbon intensity**
- Production-based: it describes electricity generated inside each BA, not what a load there consumes.
  SRP looks clean (217 kg/MWh) largely because Palo Verde nuclear is reported in SRP's area.
- eGRID 2023 factors are applied to all years (standard simplification).
- Small fuel categories fall back from BA to Arizona to national factors (`ef_source`).

**EIA-861**
- Parts A (bundled) and C (delivery-only) of the sales file are summed so wires-served customers
  count once.
- SAIDI/SAIFI without major events is missing for 12% of reporting rows (20% in 2013, 5% in 2024).
  Zeros and values exceeding the with-events value are treated as invalid.
- Utilities that report only under a non-IEEE standard are kept and flagged (`std = other`, 2,655 rows).
- RQ3 cleaning: drop utility-years whose customer count moved more than 25% in a year (13 rows);
  set outcome values more than 12x from the utility's own median to missing (about 0.5% of rows,
  probable unit errors); winsorize logged outcomes and the exposure at the 1st/99th percentile.

**LBNL Queued Up**
- Contains generation, storage, upgrade and replacement requests only. It does **not** contain load or
  data-center interconnection requests, so it cannot measure large-load growth.

**Groundwater**
- GWSI gives the latest depth-to-water only, not a time series. 11,019 sites (24%) carry a depth of exactly 0
  with no measurement date: these are placeholders and are excluded by the 2015+ date filter (only 33 zeros
  remain among 9,675 recently measured sites). Trends come from the smaller
  USGS-hosted series: 425 wells with at least 3 measurements spanning 5 or more years, of which
  3 are in Pinal County and 54 in Maricopa. The trend feature exists for 64 of 192 cells and is left
  missing elsewhere.
- Greenlee County has no water-level series.

**Site table**
- Cells are kept only if they hold at least 5 GWSI sites measured since 2015, so un-monitored
  places cannot be scored.
- Generator-queue strain is county-level (sum of `mw_1`..`mw_3` for active projects; the "Mojave" typo is
  merged into Mohave); every cell in a county receives the same value.
- NASA POWER's native resolution is coarser than 0.25 degrees, so neighbouring cells can share values.
- Cell-to-county assignment uses the nearest USGS-listed well.

## Water model inputs (scenario estimates, not measurements)
- On-site cooling water: `1.85 L/kWh x clip((wet-bulb - 4 C) / 16 C, 0, 1)`; the 1.85 comes from latent heat
  of evaporation and 5 cycles of concentration. The curve shape is an assumption, not a literature fit.
- Generation-side consumption factors (L/kWh), verified against the median operational water consumption in
  Macknick et al. (2012), *Environmental Research Letters* 7, 045802 (converted at 0.003785 L/kWh per gal/MWh):
  coal, tower, generic 687 gal/MWh = 2.60; natural gas, combined cycle, tower 198 = 0.75; nuclear, tower,
  generic 672 = 2.54; utility-scale PV 26 = 0.10; wind 0. Hydropower, aggregated in-stream and reservoir:
  median 4,491 gal/MWh (17.0 L/kWh), range 1,425 to 18,000, from only 3 studies; the base case sets hydro to 0
  and the scenarios use 5.4, 17.0 and 68.1 L/kWh.
- **Not covered by that table:** oil (1.9 L/kWh, an assumption; negligible share) and "other" (0.75, assumed
  like gas). All solar is treated as PV; Arizona's CSP plant (Solana, wet-cooled trough, 865 gal/MWh = 3.3 L/kWh
  in the paper) cannot be separated in EIA-930, so AZPS generation-side water is probably understated by
  roughly 5-10%.
- Gas is treated as wet-cooled combined cycle (198). Dry-cooled plants use about 2 gal/MWh, so a plant-level
  cooling-type lookup (EIA-860) would refine this.
- PUE is held constant at 1.2.

## Corrections after the self-audit
- County of each cell now comes from a Census TIGERweb point-in-polygon lookup (earlier: nearest USGS well).
- La Paz County (FIPS 012) was missing from the groundwater pull and is now included.
- EIA-930 timestamp labels are documented by EIA as hour-ending; the pipeline treats the label as a UTC hour.
- eGRID `PLCO2AN` is in short tons (verified); "other" fuel uses the national eGRID "other fossil" factor
  (under 0.4% of intensity).
- See [AUDIT.md](AUDIT.md) for the full list.

## Stage 1 inputs
- `data/raw/rq2/territories_az.geojson`: HIFLD electric retail service territories intersecting Arizona (61 polygons;
  `id` is the EIA utility number). Several small districts share identical generic polygons (2.31 square degrees),
  so cell-to-utility links are approximate; `cell_utility_shares_{all,large}.parquet` hold the two mappings.

## Revealed-preference inputs
- `osm_datacenters_az.parquet`: 65 OpenStreetMap features tagged as data centers (fetched via Overpass; incomplete,
  some mis-tagged businesses). `osm_substations_az.json`: 1,461 substations, voltage tag often missing.
- `tracts_az_pop.parquet`: Census 2020 tract population, housing units and centroids (TIGERweb).
- `fine_cells_features.parquet`: 10,563 cells of 0.05 degrees inside retail territories, with population,
  substation distance, groundwater depth and coarse climate.
