"""Stage 2 scheduler evaluation (carbon-only, beta = 0).

For every local day D in the 2025 test set, a flexible job needing k run-hours (1 MWh/hour,
so E = k) must finish within the 24 local hours of D, decided at local midnight. Forecasts
are the 24h-ahead predictions made before midnight (h=24 targets only use info up to t-24).

Policies (cost is always evaluated on ACTUAL carbon intensity):
  immediate  : run in the first k hours of the window (what happens with no optimisation)
  random     : expected cost of choosing k hours uniformly at random
  persist    : choose the k cheapest hours by persistence forecast (yesterday's same hour)
  lgbm_*     : choose the k cheapest hours by LightGBM forecast
  oracle     : choose the k cheapest hours by actual values (non-deployable upper bound)
Two job types: preemptible (any k hours, the closed-form sort) and contiguous (one block).

Outputs: results/schedule_savings.csv, results/schedule_paired.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KS = [4, 8, 12]
FORECASTS = ["persist", "resid_lags", "resid_demand"]
rng = np.random.default_rng(0)


def pick_sorted(f, k):
    return np.argsort(f, kind="stable")[:k]


def pick_block(f, k):
    c = np.convolve(f, np.ones(k), mode="valid")
    s = int(np.argmin(c))
    return np.arange(s, s + k)


def main() -> None:
    p = pd.read_parquet(ROOT / "data/processed/forecast_v2_test_preds.parquet")
    p = p[p.horizon_h == 24].copy()
    p["local"] = p.ts - pd.Timedelta(hours=7)
    p["day"] = p.local.dt.floor("D")
    p["hr"] = p.local.dt.hour
    rows = []
    for (ba, day), g in p.groupby(["ba", "day"]):
        if len(g) != 24 or g.hr.nunique() != 24:
            continue
        g = g.sort_values("hr")
        y = g.y.to_numpy()
        for k in KS:
            for kind, pick in (("preemptible", pick_sorted), ("contiguous", pick_block)):
                rec = {"ba": ba, "day": day, "k": k, "job": kind}
                rec["immediate"] = y[:k].sum()
                rec["random"] = y.mean() * k
                rec["oracle"] = y[pick(y, k)].sum()
                for fc in FORECASTS:
                    rec[fc] = y[pick(g[fc].to_numpy(), k)].sum()
                rows.append(rec)
    d = pd.DataFrame(rows)
    pols = ["immediate", "random", *FORECASTS, "oracle"]
    for pol in pols:
        d[f"sav_{pol}"] = 100 * (1 - d[pol] / d["immediate"])  # % saved vs run-immediately
    d["n_days"] = 1
    summ = (d.groupby(["job", "k", "ba"])[[f"sav_{x}" for x in pols]].mean().round(1))
    summ.columns = pols
    summ.to_csv(ROOT / "results/schedule_savings.csv")

    # paired comparison across days: policy cost minus persistence-policy cost (negative = better)
    pr = []
    for (job, k, ba), g in d.groupby(["job", "k", "ba"]):
        for fc in ["resid_lags", "resid_demand"]:
            diff = (g[fc] - g["persist"]) / g["immediate"] * 100
            boot = [rng.choice(diff.to_numpy(), len(diff)).mean() for _ in range(1000)]
            pr.append({"job": job, "k": k, "ba": ba, "model": fc, "days": len(g),
                       "mean_diff_pp": diff.mean(), "lo": np.percentile(boot, 2.5),
                       "hi": np.percentile(boot, 97.5)})
    pr = pd.DataFrame(pr)
    pr.to_csv(ROOT / "results/schedule_paired.csv", index=False)

    pd.set_option("display.width", 200)
    print("Days evaluated per BA:", d.groupby("ba").day.nunique().to_dict())
    print("\n% carbon saved vs run-immediately (mean over 2025 days)")
    print(summ.to_string())
    print("\nAll BAs pooled (preemptible & contiguous):")
    print(d.groupby(["job", "k"])[[f"sav_{x}" for x in pols]].mean().round(1)
          .set_axis(pols, axis=1).to_string())
    print("\nLightGBM(resid_lags) minus persistence, in pp of immediate-run carbon (95% bootstrap CI)")
    print(pr[pr.model == "resid_lags"].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
