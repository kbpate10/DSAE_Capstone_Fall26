"""Does EIA-930 interchange explain the unstable in-BA marginal emission estimates?

Identity (EIA-930): net generation = demand + net interchange (positive = net export), up to reporting error.
So a demand change is met either by in-BA generation or by a change in net interchange.

Inputs: data/raw/eia930_interchange/ (pull_interchange.py), the marginal_emissions.py panel (demand, CO2 by BA-hour).
Net export of a BA-hour = sum of reported flows from that BA to all counterparties. Hours where the BA reports no
interchange row are left missing (not zero) and dropped.

Checks and estimates (per BA, season, 6 h block; 2021-2024 train, 2025 held out):
  1. identity residual:   gen_total - demand - net_export  (is the accounting consistent enough to use?)
  2. pair antisymmetry:   flow A->B + flow B->A for pairs of Arizona BAs (should be about 0)
  3. import absorption:   slope of change in net export on change in demand; -slope = share of a demand change met
                          by imports (or reduced exports) instead of in-BA generation
  4. MEF with and without controlling for the change in net export; stability = correlation of the train profile
     with the 2025 profile, and share of train estimates that are negative.
     MEF_total (as in marginal_emissions.py) mixes the in-BA fuel response with the interchange response; the
     controlled slope is the emission rate of in-BA generation when interchange is held fixed.
Limits: interchange is net by BA and carries no carbon content here, so this does NOT produce a consumption-based
intensity; the carbon of imports would need the exporting BAs' fuel mix (not pulled).

Outputs: results/interchange_checks.csv, results/interchange_absorption.csv, results/interchange_mef.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import marginal_emissions as me

BLOCK = 6


def load_interchange() -> pd.DataFrame:
    f = sorted((ROOT / "data/raw/eia930_interchange").glob("*.parquet"))
    x = pd.concat(pd.read_parquet(p) for p in f)
    x["ts"] = pd.to_datetime(x.period, format="%Y-%m-%dT%H")
    x["value"] = pd.to_numeric(x.value, errors="coerce")
    return x


def net_export(x: pd.DataFrame) -> pd.DataFrame:
    g = x.dropna(subset=["value"]).groupby(["fromba", "ts"]).agg(net_export=("value", "sum"), n_cp=("toba", "nunique"))
    return g.reset_index().rename(columns={"fromba": "respondent"})


def mask_ne(d: pd.DataFrame) -> pd.DataFrame:
    """Net-export QC, same rule as the demand QC in marginal_emissions.load: |net export| above 5 x the BA's median demand is set to missing
    (found: an AZPS value of 24,000 MWh against a median of -1,337)."""
    med = d.groupby("respondent").demand_mwh.transform("median")
    d.loc[d.net_export.abs() > 5 * med, "net_export"] = np.nan
    return d


def ols2(y, X):
    A = np.column_stack([np.ones(len(y)), X])
    return np.linalg.lstsq(A, y, rcond=None)[0][1:]


def main() -> None:
    x = load_interchange()
    ne = net_export(x)
    d = mask_ne(me.load().merge(ne, on=["respondent", "ts"], how="left"))
    g = d.groupby("respondent")
    d["dNE"] = g.net_export.diff()
    d["ok2"] = d.ok & d.net_export.notna() & g.net_export.shift(1).notna()

    # ---- 1. identity residual and coverage
    t = d[d.year.between(2021, 2025) & ~d.data_flag.fillna(True).astype(bool) & d.net_export.notna()].copy()
    t["resid"] = t.gen_total_mwh - t.demand_mwh - t.net_export
    chk = t.groupby("respondent").agg(hours=("resid", "size"), mean_demand=("demand_mwh", "mean"),
                                      mean_net_export=("net_export", "mean"), resid_mean=("resid", "mean"),
                                      resid_abs_med=("resid", lambda s: s.abs().median()),
                                      resid_abs_p95=("resid", lambda s: s.abs().quantile(.95)))
    chk["resid_abs_med_pct_demand"] = 100 * chk.resid_abs_med / chk.mean_demand
    cov = d[d.year.between(2021, 2025)].groupby("respondent").apply(lambda s: s.net_export.notna().mean())
    chk["share_hours_with_interchange"] = cov
    chk["import_share_of_demand_pct"] = 100 * (-t.groupby("respondent").net_export.apply(lambda s: s.clip(upper=0).mean())) / chk.mean_demand
    # antisymmetry among Arizona pairs
    az = x[x.fromba.isin(me.BAS) & x.toba.isin(me.BAS)]
    pv = az.pivot_table(index=["ts", "fromba", "toba"], values="value").reset_index()
    rev = pv.rename(columns={"fromba": "toba", "toba": "fromba", "value": "rev"})
    pp = pv.merge(rev, on=["ts", "fromba", "toba"])
    pp = pp[pp.fromba < pp.toba]
    anti = (pp.value + pp.rev).abs().groupby([pp.fromba, pp.toba]).median()
    flow = pp.value.abs().groupby([pp.fromba, pp.toba]).median()
    print("Identity check and coverage (2021-2025, unflagged hours with interchange):")
    print(chk.round(2).to_string())
    print("\nAZ-pair antisymmetry: median |A->B + B->A| vs median |A->B| (MWh):")
    print(pd.DataFrame({"abs_sum_median": anti, "abs_flow_median": flow}).round(1).to_string())
    chk.round(3).to_csv(ROOT / "results/interchange_checks.csv")

    # ---- 3 & 4. absorption and MEF with/without interchange control
    d["blk"] = d.hour_local // BLOCK * BLOCK
    rows_a, rows_m = [], []
    for (ba, season, blk), gg in d[d.ok2].groupby(["respondent", "season", "blk"]):
        tr, te = gg[gg.year.between(2021, 2024)], gg[gg.year == 2025]
        if len(tr) < 100 or len(te) < 30:
            continue
        ab_tr = me.slope(tr.dD.to_numpy(), tr.dNE.to_numpy())
        ab_te = me.slope(te.dD.to_numpy(), te.dNE.to_numpy())
        rows_a.append({"ba": ba, "season": season, "block": blk, "n_train": len(tr),
                       "absorbed_by_imports_train": -ab_tr, "absorbed_by_imports_2025": -ab_te})
        res = {"ba": ba, "season": season, "block": blk}
        for tag, df in (("train", tr), ("2025", te)):
            res[f"mef_total_{tag}"] = me.slope(df.dD.to_numpy(), df.dCO2.to_numpy()) * 1000
            res[f"mef_fixedNE_{tag}"] = ols2(df.dCO2.to_numpy(), np.column_stack([df.dD, df.dNE]))[0] * 1000
        rows_m.append(res)
    A, M = pd.DataFrame(rows_a), pd.DataFrame(rows_m)
    A.round(3).to_csv(ROOT / "results/interchange_absorption.csv", index=False)
    M.round(1).to_csv(ROOT / "results/interchange_mef.csv", index=False)
    print(f"\nShare of a demand change met by imports / reduced exports ({BLOCK} h blocks; negative = exports rise with demand):")
    print(A.groupby("ba")[["absorbed_by_imports_train", "absorbed_by_imports_2025"]].agg(["mean", "min", "max"]).round(2).to_string())
    print("\nMEF (kg CO2/MWh): in-BA total vs holding interchange fixed")
    out = []
    for ba, s in M.groupby("ba"):
        out.append({"ba": ba,
                    "total_mean": s.mef_total_train.mean(), "fixedNE_mean": s.mef_fixedNE_train.mean(),
                    "total_corr_train_vs_2025": s.mef_total_train.corr(s.mef_total_2025),
                    "fixedNE_corr_train_vs_2025": s.mef_fixedNE_train.corr(s.mef_fixedNE_2025),
                    "total_share_negative": (s.mef_total_train < 0).mean(),
                    "fixedNE_share_negative": (s.mef_fixedNE_train < 0).mean()})
    print(pd.DataFrame(out).set_index("ba").round(2).to_string())


if __name__ == "__main__":
    main()
