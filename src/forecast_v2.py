"""Carbon-intensity forecasting v2: ablation of residual target and day-ahead demand features.

Variants (all LightGBM, direct horizon h, same split as forecast_baseline.py):
  raw_lags      : raw target, lag features only              (= v1)
  resid_lags    : target = y - persistence, lag features only
  raw_demand    : raw target, lags + demand features
  resid_demand  : residual target, lags + demand features
Demand features use the EIA day-ahead demand forecast (DF) for the target hour, which is
published the day before, so it is available at the forecast origin for h in {1, 24}.

Metrics are computed on the rows where persistence, seasonal-naive and every model exist.
Outputs: results/forecast_v2_metrics.csv, data/processed/forecast_v2_test_preds.parquet
"""
import glob
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
HORIZONS = [1, 24]


def load_demand() -> pd.DataFrame:
    d = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930_demand/*.parquet")))
    d["ts"] = pd.to_datetime(d["period"], format="%Y-%m-%dT%H")
    return d.pivot_table(index=["respondent", "ts"], columns="type", values="value").reset_index()


def build(g: pd.DataFrame, h: int) -> pd.DataFrame:
    s = g.set_index("ts").sort_index()
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="h"))
    ok = ~s["data_flag"].fillna(True).astype(bool)
    ci, cs = s["ci_kg_per_mwh"].where(ok), s["clean_share"].where(ok)
    X = pd.DataFrame(index=s.index)
    X["y"] = ci
    for lag in sorted({h, h + 1, h + 2, 24, 48, 168}):
        X[f"ci_lag{lag}"] = ci.shift(lag)
    X["clean_lagh"] = cs.shift(h)
    for w in (6, 24, 168):
        X[f"ci_mean{w}"] = ci.shift(h).rolling(w, min_periods=max(1, w // 2)).mean()
    X["ci_std24"] = ci.shift(h).rolling(24, min_periods=12).std()
    local = X.index - pd.Timedelta(hours=7)  # Arizona: no DST
    X["hour"], X["dow"], X["month"] = local.hour, local.dayofweek, local.month
    X["doy_sin"] = np.sin(2 * np.pi * local.dayofyear / 365.25)
    X["doy_cos"] = np.cos(2 * np.pi * local.dayofyear / 365.25)
    X["persist"], X["snaive"] = ci.shift(h), ci.shift(168)
    # demand features (known at origin)
    D, DF = s["D"], s["DF"]
    X["df_t"] = DF
    X["d_lagh"] = D.shift(h)
    X["df_minus_dlagh"] = DF - D.shift(h)
    X["df_minus_df24"] = DF - DF.shift(24)
    X["df_minus_d168"] = DF - D.shift(168)
    X["df_rank24"] = DF.rolling(24, min_periods=12).rank(pct=True)  # position within the day
    return X


def metrics(y, p):
    e = p - y
    big = y > 50
    return {"n": len(y), "MAE": e.abs().mean(), "RMSE": float(np.sqrt((e ** 2).mean())),
            "MAPE": (e[big].abs() / y[big]).mean() * 100}


def main() -> None:
    ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet")
    ci = ci.merge(load_demand(), on=["respondent", "ts"], how="left")
    demand_cols = ["df_t", "d_lagh", "df_minus_dlagh", "df_minus_df24", "df_minus_d168", "df_rank24"]
    rows, preds = [], []
    for ba, g in ci.groupby("respondent"):
        for h in HORIZONS:
            X = build(g, h)
            base = [c for c in X.columns if c not in ["y", "persist", "snaive", *demand_cols]]
            variants = {"raw_lags": (base, False), "resid_lags": (base, True),
                        "raw_demand": (base + demand_cols, False),
                        "resid_demand": (base + demand_cols, True)}
            te = X[X.index.year == 2025].copy()
            for name, (feats, resid) in variants.items():
                d = X[X.persist.notna() & X.y.notna()]
                tr, va = d[d.index.year <= 2023], d[d.index.year == 2024]
                off = lambda df: df.persist if resid else 0.0
                m = lgb.LGBMRegressor(n_estimators=2000, learning_rate=0.03, num_leaves=31,
                                      min_child_samples=40, subsample=0.8, subsample_freq=1,
                                      colsample_bytree=0.8, verbose=-1)
                m.fit(tr[feats], tr.y - off(tr), eval_set=[(va[feats], va.y - off(va))],
                      eval_metric="l1", callbacks=[lgb.early_stopping(100, verbose=False)])
                te[name] = m.predict(te[feats]) + (te.persist if resid else 0.0)
                print(f"{ba} h={h} {name}: iters={m.best_iteration_}", flush=True)
            cols = ["persist", "snaive", *variants]
            c = te[te.y.notna() & te[cols].notna().all(axis=1)]
            for col in cols:
                rows.append({"ba": ba, "horizon_h": h, "model": col, **metrics(c.y, c[col])})
            out = c[["y", *cols]].copy()
            out["ba"], out["horizon_h"] = ba, h
            preds.append(out.reset_index(names="ts"))

    res = pd.DataFrame(rows)
    (ROOT / "results").mkdir(exist_ok=True)
    res.to_csv(ROOT / "results/forecast_v2_metrics.csv", index=False)
    pd.concat(preds).to_parquet(ROOT / "data/processed/forecast_v2_test_preds.parquet", index=False)
    pd.set_option("display.width", 220)
    order = ["persist", "snaive", "raw_lags", "resid_lags", "raw_demand", "resid_demand"]
    for h in HORIZONS:
        for metric in ("MAE", "MAPE"):
            t = res[res.horizon_h == h].pivot(index="ba", columns="model", values=metric)[order]
            print(f"\n=== Test 2025, h={h}h, {metric} ===")
            print(t.round(1).to_string())


if __name__ == "__main__":
    main()
