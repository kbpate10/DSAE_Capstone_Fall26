"""Does the residual-target LightGBM advantage hold on a test year chosen BEFORE the design was fixed?

The residual target and demand features were chosen after seeing 2025 test results. Here the same models are
re-fit with train 2021-2022, early-stop 2023, test 2024 (2024 was only used for early stopping before).
Outputs MAE by BA and horizon for persistence / raw LightGBM / residual LightGBM / residual + demand.
"""
import sys
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import forecast_v2 as f2

ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet").merge(f2.load_demand(), on=["respondent", "ts"], how="left")
demand_cols = ["df_t", "d_lagh", "df_minus_dlagh", "df_minus_df24", "df_minus_d168", "df_rank24"]
rows = []
for ba, g in ci.groupby("respondent"):
    for h in (1, 24):
        X = f2.build(g, h)
        base = [c for c in X.columns if c not in ["y", "persist", "snaive", *demand_cols]]
        variants = {"raw_lags": (base, False), "resid_lags": (base, True), "resid_demand": (base + demand_cols, True)}
        d = X[X.persist.notna() & X.y.notna()]
        tr, va, te = d[d.index.year <= 2022], d[d.index.year == 2023], d[d.index.year == 2024].copy()
        for name, (feats, resid) in variants.items():
            off = lambda df: df.persist if resid else 0.0
            m = lgb.LGBMRegressor(n_estimators=2000, learning_rate=0.03, num_leaves=31, min_child_samples=40,
                                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
            m.fit(tr[feats], tr.y - off(tr), eval_set=[(va[feats], va.y - off(va))], eval_metric="l1",
                  callbacks=[lgb.early_stopping(100, verbose=False)])
            te[name] = m.predict(te[feats]) + (te.persist if resid else 0.0)
        cols = ["persist", *variants]
        c = te[te.y.notna() & te[cols].notna().all(axis=1)]
        for col in cols:
            rows.append({"ba": ba, "h": h, "model": col, "MAE": (c[col] - c.y).abs().mean(), "n": len(c)})
R = pd.DataFrame(rows)
t = R.pivot_table(index=["h", "ba"], columns="model", values="MAE")[["persist", "raw_lags", "resid_lags", "resid_demand"]]
for m in ["raw_lags", "resid_lags", "resid_demand"]:
    t[f"{m}_gain%"] = 100 * (1 - t[m] / t["persist"])
pd.set_option("display.width", 200)
print("Rolling-origin check: train 2021-22, early-stop 2023, TEST 2024 (MAE, kg/MWh)")
print(t.round(1).to_string())
R.to_csv(ROOT / "results/audit_rolling_origin_2024.csv", index=False)
