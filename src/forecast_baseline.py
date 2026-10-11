"""Carbon-intensity forecasting: persistence / seasonal-naive vs LightGBM.

Direct forecasting at horizon h (hours ahead): to predict ci[t], only information available
at t-h is used (lags >= h, rolling stats shifted by h, calendar). No weather yet.

Split (chronological): train 2021-2023, validation 2024 (early stopping), test 2025.
Metrics on hours with an observed, unflagged target; MAPE only where ci > 50 kg/MWh.

Outputs: results/forecast_metrics.csv, data/processed/forecast_test_preds.parquet
"""
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HORIZONS = [1, 24]


def build(ba_df: pd.DataFrame, h: int) -> pd.DataFrame:
    s = ba_df.set_index("ts").sort_index()
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="h"))
    ok = ~s["data_flag"].fillna(True).astype(bool)
    ci = s["ci_kg_per_mwh"].where(ok)
    cs = s["clean_share"].where(ok)
    X = pd.DataFrame(index=s.index)
    X["y"] = ci
    # lags relative to the forecast origin (t-h)
    for lag in sorted({h, h + 1, h + 2, 24, 48, 168}):
        if lag >= h:
            X[f"ci_lag{lag}"] = ci.shift(lag)
    X["clean_lagh"] = cs.shift(h)
    for w in (6, 24, 168):
        r = ci.shift(h).rolling(w, min_periods=max(1, w // 2))
        X[f"ci_mean{w}"] = r.mean()
    X["ci_std24"] = ci.shift(h).rolling(24, min_periods=12).std()
    # calendar of the target hour (known in advance). Arizona has no DST, so UTC-7 is exact.
    local = X.index - pd.Timedelta(hours=7)
    X["hour"] = local.hour
    X["dow"] = local.dayofweek
    X["month"] = local.month
    X["doy_sin"] = np.sin(2 * np.pi * local.dayofyear / 365.25)
    X["doy_cos"] = np.cos(2 * np.pi * local.dayofyear / 365.25)
    X["persist"] = ci.shift(h)
    X["snaive"] = ci.shift(168)
    return X


def metrics(y, p):
    m = y.notna() & p.notna()
    y, p = y[m], p[m]
    e = p - y
    big = y > 50
    return {"n": int(m.sum()), "MAE": e.abs().mean(), "RMSE": float(np.sqrt((e ** 2).mean())),
            "MAPE": (e[big].abs() / y[big]).mean() * 100}


def main() -> None:
    ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet")
    (ROOT / "results").mkdir(exist_ok=True)
    rows, preds = [], []
    for ba, g in ci.groupby("respondent"):
        for h in HORIZONS:
            X = build(g, h)
            feats = [c for c in X.columns if c not in ("y", "persist", "snaive")]
            tr = X[(X.index.year <= 2023) & X.y.notna()]
            va = X[(X.index.year == 2024) & X.y.notna()]
            te = X[(X.index.year == 2025)]
            model = lgb.LGBMRegressor(
                n_estimators=2000, learning_rate=0.03, num_leaves=31, min_child_samples=40,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
            model.fit(tr[feats], tr.y, eval_set=[(va[feats], va.y)], eval_metric="l1",
                      callbacks=[lgb.early_stopping(100, verbose=False)])
            te = te.assign(lgbm=model.predict(te[feats]))
            for name, col in [("persistence", "persist"), ("seasonal_naive", "snaive"), ("lightgbm", "lgbm")]:
                rows.append({"ba": ba, "horizon_h": h, "model": name, **metrics(te.y, te[col])})
            out = te[["y", "persist", "snaive", "lgbm"]].copy()
            out["ba"], out["horizon_h"] = ba, h
            preds.append(out.reset_index(names="ts"))
            print(f"{ba} h={h}: best_iter={model.best_iteration_}", flush=True)

    res = pd.DataFrame(rows)
    res.to_csv(ROOT / "results/forecast_metrics.csv", index=False)
    pd.concat(preds).to_parquet(ROOT / "data/processed/forecast_test_preds.parquet", index=False)
    pd.set_option("display.width", 200)
    for h in HORIZONS:
        print(f"\n=== Test 2025, horizon {h}h ===")
        print(res[res.horizon_h == h].pivot(index="ba", columns="model", values=["MAE", "MAPE"]).round(1).to_string())


if __name__ == "__main__":
    main()
