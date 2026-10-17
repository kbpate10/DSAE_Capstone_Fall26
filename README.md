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
[docs/STAGE1.md](docs/STAGE1.md) (siting optimizer) and
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
.venv/bin/python src/bayes_rq3.py full            # PyMC hierarchical model
.venv/bin/python src/bayes_rq3.py holdout2024     # calibration check

# RQ2: siting
.venv/bin/python src/pull_groundwater.py && .venv/bin/python src/pull_wells_geo.py
.venv/bin/python src/pull_adwr_gwsi.py
.venv/bin/python src/build_sites.py && .venv/bin/python src/rq2_siting.py

# Stage 1 siting optimizer
.venv/bin/python src/build_territories.py        # cell -> serving utility (HIFLD polygons)
.venv/bin/python src/stage1_optimizer.py

# revealed-preference siting (real data-center locations)
.venv/bin/python src/revealed_preference.py
.venv/bin/python src/stage1_revealed.py
.venv/bin/python src/make_revealed_figure.py

# audit checks
.venv/bin/python src/audit_checks.py > results/audit_checks.txt
.venv/bin/python src/audit_rolling_origin.py

# water (preliminary) and figures
.venv/bin/python src/pull_weather_hourly.py && .venv/bin/python src/water_frontier.py
.venv/bin/python src/make_midpoint_figures.py
```
No GPU is needed; everything ran on a laptop CPU (Apple M4).
