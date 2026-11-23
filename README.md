# Carbon, Water, and Reliability: A Decision Framework for Arizona's AI Data-Center Boom

FSE 570 Data Science Capstone, Arizona State University, Fall 2026.

One framework for three linked decisions about AI data centers in Arizona:

| Question | Method | Status (midpoint 1) |
|---|---|---|
| **When** to run flexible workloads (carbon, water) | Gradient-boosted + neural forecasters, scheduler | Working, evaluated on held-out 2025 |
| **Where** to site capacity | Transparent multi-criteria score, logistic regression / LightGBM + SHAP | Baseline working (constructed label) |
| **Who pays** (reliability for existing customers) | Fixed-effects panel regression, Bayesian hierarchical model | Working; honest null result |

**Start here:** [docs/MIDPOINT1_REPORT.md](docs/MIDPOINT1_REPORT.md) (results and caveats) and
[docs/data_dictionary.md](docs/data_dictionary.md) (every dataset, its coverage and cleaning rules),
[docs/EDA.md](docs/EDA.md) (exploratory analysis) and
[docs/regulatory_context_check.md](docs/regulatory_context_check.md) (fact check of policy claims) and
[docs/AUDIT.md](docs/AUDIT.md) (self-audit: errors fixed, assumptions tested, what remains unverified) and
[docs/STAGE1.md](docs/STAGE1.md) (siting optimizer),
[docs/STAGE2.md](docs/STAGE2.md) (siting x operating carbon and water coupling),
[docs/MARGINAL.md](docs/MARGINAL.md) (marginal vs average emissions),
[docs/CONSUMPTION.md](docs/CONSUMPTION.md) (consumption-based intensity by flow tracing),
[docs/LITERATURE.md](docs/LITERATURE.md) (first-pass literature check, unverified),
[docs/ARIZONA_CASE_STUDY.md](docs/ARIZONA_CASE_STUDY.md) (framework vs the 2026 policy debate),
[docs/RQ3_POWER.md](docs/RQ3_POWER.md) (what the reliability data can detect),
[docs/RQ3_DC_EXPOSURE.md](docs/RQ3_DC_EXPOSURE.md) (data-center-specific exposure),
[docs/WATER_MEASURED.md](docs/WATER_MEASURED.md) (measured plant cooling water),
[docs/MEF_SCAN_PREREG.md](docs/MEF_SCAN_PREREG.md) and [docs/MEF_SCAN.md](docs/MEF_SCAN.md) (pre-registered multi-BA marginal-estimate stability test and its inconclusive result),
[docs/STAGE1_INTERCONNECTION.md](docs/STAGE1_INTERCONNECTION.md) (interconnection screen for siting) and
[docs/MIDPOINT2_REPORT.md](docs/MIDPOINT2_REPORT.md) (Checkpoint 2 status report) and
[docs/REVEALED_PREFERENCE.md](docs/REVEALED_PREFERENCE.md) (siting from real data-center locations).

## Layout
```
src/        pipeline and model scripts (run order below)
data/raw/   downloaded source data (git-ignored)
data/processed/  cleaned tables used by the models (git-ignored)
results/    metrics CSVs; results/figures/ for plots
docs/       report and data dictionary
.env        EIA_API_KEY=...   (git-ignored; free key from eia.gov/opendata)
```

## Reproduce
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "EIA_API_KEY=your_key" > .env
bash src/download_static.sh                       # eGRID, LBNL, EIA-861 files

# data
.venv/bin/python src/pull_eia930.py 2021 2025     # hourly generation by fuel, 4 Arizona BAs
.venv/bin/python src/pull_demand.py 2021 2025     # demand + day-ahead demand forecast
.venv/bin/python src/carbon_intensity.py          # hourly carbon intensity (eGRID factors)
.venv/bin/python src/build_eia861.py              # utility x state x year panel
.venv/bin/python src/build_lbnl.py                # LBNL queue workbook -> parquet

# unified tables and EDA
.venv/bin/python src/build_master.py              # master BA-hour and utility-year tables
.venv/bin/python src/eda.py > results/eda_stats.txt

# RQ1: forecasting and scheduling
.venv/bin/python src/forecast_baseline.py         # v1: LightGBM vs persistence
.venv/bin/python src/forecast_v2.py               # residual target + demand features (ablation)
.venv/bin/python src/forecast_nn.py               # neural net (CPU, ~15 min)
.venv/bin/python src/schedule_eval.py             # Stage-2 scheduler savings

# RQ3: reliability
.venv/bin/python src/rq3_model.py                 # fixed-effects ladder + robustness
.venv/bin/python src/rq3_baseline.py              # naive baseline ladder
.venv/bin/python src/rq3_power.py                 # power analysis and the clipped-exposure check
.venv/bin/python src/pull_osm_datacenters_us.py && .venv/bin/python src/pull_territories_us.py   # slow: Overpass is rate-limited
.venv/bin/python src/rq3_datacenter_exposure.py   # data-center-specific exposure
.venv/bin/python src/bayes_rq3.py full            # PyMC hierarchical model
.venv/bin/python src/bayes_rq3.py holdout2024     # calibration check

# RQ2: siting
.venv/bin/python src/pull_groundwater.py && .venv/bin/python src/pull_wells_geo.py
.venv/bin/python src/pull_adwr_gwsi.py
.venv/bin/python src/build_sites.py && .venv/bin/python src/rq2_siting.py

# Stage 1 siting optimizer
.venv/bin/python src/build_territories.py        # cell -> serving utility (HIFLD polygons)
.venv/bin/python src/stage1_optimizer.py
.venv/bin/python src/stage1_interconnection.py   # voltage-and-proximity interconnection screen (needs OSM substations in data/raw/rq2)
.venv/bin/python src/stage2_coupling.py        # needs water_frontier inputs and schedule_savings.csv
.venv/bin/python src/marginal_emissions.py
.venv/bin/python src/pull_interchange.py && .venv/bin/python src/interchange_analysis.py
.venv/bin/python src/pull_neighbor_fuel.py && .venv/bin/python src/consumption_carbon.py
.venv/bin/python src/mef_robustness.py          # second held-out year, weather and interchange controls
.venv/bin/python src/pull_ba_panel.py                 # 37 BAs, 2021-2025 (slow); then:
.venv/bin/python src/ba_stability_scan.py --qc      # data-quality diagnostics only
.venv/bin/python src/ba_stability_scan.py           # pre-registered multi-BA test (docs/MEF_SCAN_PREREG.md)
.venv/bin/python -I src/measured_emissions_check.py && .venv/bin/python -I src/measured_emissions_downstream.py   # estimated vs measured (EPA CEMS) CO2; docs/MEASURED_EMISSIONS.md

# Checkpoint 2
.venv/bin/python src/forecast_conformal.py      # calibrated forecast intervals (needs forecast_v2 test predictions)
.venv/bin/python src/framework_endtoend.py      # Stage 1 -> Stage 2 end to end (needs stage1, stage2_coupling, water_frontier outputs)
.venv/bin/python src/case_study_numbers.py
.venv/bin/python src/make_checkpoint2_figures.py

# revealed-preference siting (real data-center locations)
.venv/bin/python src/revealed_preference.py
.venv/bin/python src/stage1_revealed.py
.venv/bin/python src/make_revealed_figure.py

# audit checks
.venv/bin/python src/audit_checks.py > results/audit_checks.txt
.venv/bin/python src/audit_rolling_origin.py

# water (preliminary) and figures
.venv/bin/python src/pull_weather_hourly.py && .venv/bin/python src/water_frontier.py
.venv/bin/python -I src/build_water_factors.py   # measured generation-side water from EIA-860/923 (-I: reads downloaded files)
.venv/bin/python src/water_measured.py          # carbon-water frontier under measured factors
.venv/bin/python src/make_midpoint_figures.py
```
No GPU is needed; everything ran on a laptop CPU (Apple M4).
