"""Audit checks added after a self-review. Each block tests an assumption made earlier.

1. OSM: where are mapped data centers relative to the siting score? (replaces an unverified hub list)
2. RQ3: results when only utilities with a consistent reliability-reporting standard are used.
3. Timestamp offset: sensitivity of the water/carbon results to a +-1 hour offset between EIA-930 labels
   and the NASA POWER weather series.
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
STEP = 0.25
pd.set_option("display.width", 200)


def osm_check():
    print("=== 1. OSM mapped data centers vs siting score ===")
    s = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    o = pd.read_parquet(ROOT / "data/raw/rq2/osm_datacenters_az.parquet")
    o["cell_id"] = (np.floor(o.lat / STEP).astype(int)).astype(str) + "_" + (np.floor(o.lon / STEP).astype(int)).astype(str)
    inside = o[o.cell_id.isin(s.index)]
    print(f"  OSM features: {len(o)} | inside a candidate cell: {len(inside)} | outside (cannot be scored): {len(o) - len(inside)}")
    for label, sub in [("all mapped", inside), ("with operator tag", inside[inside.operator.notna()])]:
        cells = sub.groupby("cell_id").size()
        r = s.loc[cells.index, "rank"]
        others = s.loc[~s.index.isin(cells.index), "rank"]
        u = mannwhitneyu(r, others, alternative="greater")
        print(f"  {label}: {len(sub)} features in {len(cells)} cells | median rank of those cells {r.median():.0f} of 192 "
              f"(other cells: {others.median():.0f}) | share of cells in bottom third: {(r > 128).mean():.0%} | "
              f"Mann-Whitney p (hosting cells rank worse) = {u.pvalue:.4f}")
    top = inside.groupby("cell_id").size().sort_values(ascending=False).head(8)
    print("  cells with most mapped data centers (cell, n, county, rank, depth ft, summer wet-bulb C):")
    for c, n in top.items():
        print(f"    {c}  n={n:2d}  {s.loc[c,'county_short']:9s} rank {int(s.loc[c,'rank']):3d}  depth {s.loc[c,'gw_depth_med']:.0f}  tw {s.loc[c,'wetbulb_summer_c']:.1f}")
    print("  mapped data centers in the 192 cells' top tercile:", int((s.loc[inside.cell_id, 'suitable'] == 1).sum()), "of", len(inside))
    sub = inside[inside.operator.notna()]
    sub = sub.assign(rank=s.loc[sub.cell_id, "rank"].values, county=s.loc[sub.cell_id, "county_short"].values)
    print("  named operators and ranks (sample):")
    print(sub[["name", "operator", "county", "rank"]].drop_duplicates(["operator", "county", "rank"]).head(14).to_string(index=False))


def rq3_standard():
    print("\n=== 2. RQ3 with consistent reporting standard ===")
    from linearmodels.panel import PanelOLS
    u = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet")
    nstd = u.dropna(subset=["std"]).groupby("key")["std"].nunique()
    switchers = set(nstd[nstd > 1].index)
    print(f"  utilities that switch ieee/other: {len(switchers)} of {len(nstd)}")

    def fit(df, xs, label):
        d = df.dropna(subset=["ln_saidi_nomed", *xs]).copy()
        d = d[d.groupby("state_year").key.transform("size") > 1].set_index(["key", "year"])
        r = PanelOLS(d.ln_saidi_nomed, d[xs], entity_effects=True, other_effects=d["state_year"]).fit(
            cov_type="clustered", cluster_entity=True)
        b, se = r.params["d_ln_ci_pc"], r.std_errors["d_ln_ci_pc"]
        pct = lambda x: (np.exp(x * np.log(1.10)) - 1) * 100
        print(f"  {label:48s} n={int(r.nobs):5d}  effect per +10% load: {pct(b):+.2f}% [{pct(b-1.96*se):+.2f}, {pct(b+1.96*se):+.2f}]")
    xs = ["d_ln_ci_pc", "d_ln_cust", "ln_cust"]
    fit(u, xs, "main specification (all rows)")
    fit(u[~u.key.isin(switchers)], xs, "drop utilities that switch standards")
    fit(u[u["std"] == "ieee"], xs, "IEEE-standard rows only")
    u2 = u.copy(); u2["is_other"] = (u2["std"] == "other").astype(float)
    fit(u2, xs + ["is_other"], "all rows + 'other standard' indicator")


def timestamp_offset():
    print("\n=== 3. Offset between EIA-930 hour labels and weather (carbon-only policy, pooled, 8h) ===")
    import water_frontier as wf
    wf.KS = [8]
    base = wf.build()
    out = []
    for k in (-1, 0, 1):
        d = base.sort_values(["respondent", "ts"]).copy()
        tw = d.groupby("respondent").T2MWET.shift(k)
        d["W_on"] = wf.WUE_MAX * ((tw - wf.TW_LO) / (wf.TW_HI - wf.TW_LO)).clip(0, 1)
        d["W"] = d.W_on + d.W_off
        d.loc[d.data_flag.fillna(True).astype(bool), ["W", "W_on"]] = np.nan
        desc = wf.describe(d).set_index("ba")
        F = wf.frontier(d)
        S = wf.summarize(F, by=("job", "k", "mode", "alpha"))
        t = S[(S.job == "preemptible") & (S.k == 8) & (S["mode"] == "persist")].set_index("alpha")
        out.append({"weather_shift_h": k, "corr_C_Won_AZPS": desc.loc["AZPS", "within_day_corr_C_Won"],
                    "corr_C_Won_SRP": desc.loc["SRP", "within_day_corr_C_Won"],
                    "carbonOnly_carbon%": t.loc[1.0, "carbon_saved_vs_random_pct"], "carbonOnly_water%": t.loc[1.0, "water_saved_vs_random_pct"],
                    "balanced_carbon%": t.loc[0.5, "carbon_saved_vs_random_pct"], "balanced_water%": t.loc[0.5, "water_saved_vs_random_pct"]})
    print(pd.DataFrame(out).round(2).to_string(index=False))


if __name__ == "__main__":
    osm_check(); rq3_standard(); timestamp_offset()
