"""Calibrated prediction intervals for the carbon-intensity forecasts (online split-conformal, chronological).

For each BA, horizon (1 h, 24 h) and model (persistence, and LightGBM residual-over-persistence `resid_lags`, the
primary model), a prediction interval is  yhat +/- q  where q is the finite-sample conformal quantile of the absolute
residuals |y - yhat| in the same LOCAL HOUR OF DAY (Mondrian bins, because the error scale differs by hour).

No leakage: the interval for a target on local day D uses only residuals of targets that ended at least 24 h before the
start of D (conservative for h = 1, exact for h = 24), so it could have been computed at decision time. The calibration set
is expanding: all such residuals since 2025-01-01. The first 59 days (to Feb 28) are warm-up; coverage is scored on the
targets from Mar 1 to Dec 31 2025 (local), i.e. on days the intervals were not fitted to.

Inputs: data/processed/forecast_v2_test_preds.parquet (the 2025 test predictions; the 2021-2024 predictions were not saved, so
the calibration pool is 2025 itself, chronologically earlier than each scored target).
Limits: conformal guarantees assume exchangeable residuals; time series are not, so empirical coverage is what is reported,
by season and by month. Intervals are clipped at 0 (intensity cannot be negative), which can only help coverage.

Outputs: results/forecast_conformal.csv, results/forecast_conformal_by_month.csv, results/figures/forecast_calibration.png
"""
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
LEVELS = (0.50, 0.80, 0.90, 0.95)
MODELS = {"persist": "persistence", "resid_lags": "LightGBM"}
START = pd.Timestamp("2025-03-01")


def conformal_q(res: np.ndarray, level: float) -> float:
    n = len(res)
    k = int(np.ceil((n + 1) * level))
    return np.inf if k > n else float(np.sort(res)[k - 1])


def intervals(g: pd.DataFrame, col: str) -> pd.DataFrame:
    g = g.dropna(subset=["y", col]).sort_values("ts").copy()
    g["err"] = (g.y - g[col]).abs()
    g["local"] = g.ts - pd.Timedelta(hours=7)
    g["day"], g["hr"] = g.local.dt.floor("D"), g.local.dt.hour
    out = []
    for day, tgt in g[g.day >= START].groupby("day"):
        cutoff = day + pd.Timedelta(hours=7) - pd.Timedelta(hours=24)       # ts (UTC) of local midnight minus 24 h
        cal = g[g.ts < cutoff]
        calh = {h: v.err.to_numpy() for h, v in cal.groupby("hr")}
        for _, r in tgt.iterrows():
            res = calh.get(r.hr, np.array([]))
            row = {"ts": r.ts, "local": r.local, "hr": r.hr, "y": r.y, "yhat": r[col], "n_cal": len(res)}
            for lv in LEVELS:
                q = conformal_q(res, lv) if len(res) else np.inf
                row[f"lo{int(lv * 100)}"], row[f"hi{int(lv * 100)}"] = max(r[col] - q, 0.0), r[col] + q
            out.append(row)
    return pd.DataFrame(out)


def main() -> None:
    p = pd.read_parquet(ROOT / "data/processed/forecast_v2_test_preds.parquet")
    rows, monthly, keep = [], [], {}
    for (ba, h), g in p.groupby(["ba", "horizon_h"]):
        for col, name in MODELS.items():
            iv = intervals(g, col)
            iv = iv[np.isfinite(iv.hi95)]
            iv["season"] = np.where(iv.local.dt.month.between(6, 9), "summer", "other")
            keep[(ba, h, name)] = iv
            for lv in LEVELS:
                k = int(lv * 100)
                cov = ((iv.y >= iv[f"lo{k}"]) & (iv.y <= iv[f"hi{k}"]))
                w = iv[f"hi{k}"] - iv[f"lo{k}"]
                rec = {"ba": ba, "horizon_h": h, "model": name, "level": lv, "n": len(iv), "coverage": cov.mean(),
                       "mean_width": w.mean(),
                       "coverage_summer": cov[iv.season == "summer"].mean(), "coverage_other": cov[iv.season == "other"].mean()}
                rows.append(rec)
                if lv == 0.90:
                    m = cov.groupby(iv.local.dt.month).mean()
                    monthly += [{"ba": ba, "horizon_h": h, "model": name, "month": mo, "coverage90": c} for mo, c in m.items()]
    R = pd.DataFrame(rows)
    R.round(3).to_csv(ROOT / "results/forecast_conformal.csv", index=False)
    pd.DataFrame(monthly).round(3).to_csv(ROOT / "results/forecast_conformal_by_month.csv", index=False)

    pd.set_option("display.width", 200)
    print("Empirical coverage of conformal intervals, targets Mar-Dec 2025 (nominal in columns):")
    print(R.pivot_table(index=["horizon_h", "ba", "model"], columns="level", values="coverage").round(3).to_string())
    print("\nMean interval width at 90% (kg CO2/MWh): persistence vs LightGBM")
    w = R[R.level == 0.90].pivot_table(index=["horizon_h", "ba"], columns="model", values="mean_width")
    w["LightGBM_narrower_pct"] = 100 * (1 - w.LightGBM / w.persistence)
    print(w.round(1).to_string())
    print("\n90% interval coverage by season (LightGBM): summer (Jun-Sep) vs other")
    print(R[(R.level == 0.90) & (R.model == "LightGBM")][["horizon_h", "ba", "coverage_summer", "coverage_other"]].round(3).to_string(index=False))
    print("\nWorst month for 90% coverage (LightGBM):")
    M = pd.DataFrame(monthly)
    M = M[M.model == "LightGBM"]
    print(M.loc[M.groupby(["ba", "horizon_h"]).coverage90.idxmin()].round(3).to_string(index=False))

    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.4))
    cols = {"AZPS": "#1b6ca8", "SRP": "#edae49", "TEPC": "#2a9d8f", "WALC": "#d1495b"}
    for a, h in zip(ax, (1, 24)):
        a.plot([0.4, 1], [0.4, 1], color="#999", lw=1, ls="--")
        for ba, c in cols.items():
            s = R[(R.ba == ba) & (R.horizon_h == h) & (R.model == "LightGBM")].sort_values("level")
            a.plot(s.level, s.coverage, marker="o", color=c, label=ba)
        a.set_title(f"{h}-hour-ahead LightGBM intervals: nominal vs empirical coverage", fontsize=10)
        a.set_xlabel("nominal coverage"); a.set_ylabel("empirical coverage (Mar-Dec 2025)"); a.grid(alpha=.25)
    ax[0].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/forecast_calibration.png", dpi=150); plt.close(fig)

    iv = keep[("AZPS", 24, "LightGBM")]
    wk = iv[(iv.local >= "2025-07-14") & (iv.local < "2025-07-21")]
    fig, a = plt.subplots(figsize=(10, 3.6))
    a.fill_between(wk.local, wk.lo90, wk.hi90, color="#1b6ca8", alpha=.2, label="90% interval")
    a.fill_between(wk.local, wk.lo50, wk.hi50, color="#1b6ca8", alpha=.35, label="50% interval")
    a.plot(wk.local, wk.yhat, color="#1b6ca8", lw=1.2, label="LightGBM 24 h forecast")
    a.plot(wk.local, wk.y, color="#222", lw=1, label="actual")
    a.set_ylabel("kg CO2/MWh"); a.set_title("AZPS, one July 2025 week: 24 h-ahead forecast with conformal intervals", fontsize=10)
    a.legend(frameon=False, fontsize=8, ncol=4); a.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/forecast_intervals_example.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
