"""Robustness of the marginal-emission findings: a second held-out year and weather / interchange controls.

marginal_emissions.py trained on 2021-2024 and tested on 2025 only. Here every specification is also run with
train 2021-2023 / test 2024, so a stability or scheduling claim has to hold in two test years, not one.

Specifications (6 h hour-of-day bins x season, per BA, slope on the change in demand dD):
  base      dCO2 ~ dD                          (as marginal_emissions.py)
  weather   dCO2 ~ dD + dT + dWB               temperature and wet-bulb change (NASA POWER via master_ba_hour)
  inter     dCO2 ~ dD + dNE                    holding the change in net export fixed (interchange_analysis.py)
  both      dCO2 ~ dD + dT + dWB + dNE
Weather enters as a control for co-movement of demand with heat (cooling load, plant derating, solar ramp timing); it cannot
separate those from demand itself, so a change from base to weather is evidence of confounding, not a corrected causal effect.
Irradiance is not in the project, so solar-ramp confounding is only partly absorbed.

Per BA and test year it reports: mean MEF, correlation of the train profile with the test-year profile (only 8 points per BA, so
treat as indicative), mean absolute difference between them as % of the train mean, and the share of train estimates that are negative.
Scheduling (8 h preemptible job, same decision/accounting design as marginal_emissions.py) is repeated for test year 2024 with
the base specification, to see whether the accounting-dependence finding replicates.

Outputs: results/mef_robustness.csv, results/mef_scheduling_2024.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import interchange_analysis as ia
import marginal_emissions as me

BLOCK = 6
SPECS = {"base": [], "weather": ["dT", "dWB"], "inter": ["dNE"], "both": ["dT", "dWB", "dNE"]}
TESTS = {2024: range(2021, 2024), 2025: range(2021, 2025)}


def panel() -> pd.DataFrame:
    d = ia.mask_ne(me.load().merge(ia.net_export(ia.load_interchange()), on=["respondent", "ts"], how="left"))
    g = d.groupby("respondent")
    d["dNE"] = g.net_export.diff()
    d["dT"], d["dWB"] = g.temp_c.diff(), g.wetbulb_c.diff()
    d["hb"] = d.hour_local // BLOCK * BLOCK
    return d


def coef(df: pd.DataFrame, controls: list) -> float:
    y = df.dCO2.to_numpy()
    if not controls:
        return me.slope(df.dD.to_numpy(), y) * 1000
    return ia.ols2(y, np.column_stack([df.dD] + [df[c] for c in controls]))[0] * 1000


def profile(d: pd.DataFrame, controls: list, years) -> pd.DataFrame:
    need = ["dD", "dCO2"] + controls
    t = d[d.ok & d.year.isin(list(years))].dropna(subset=need)
    rows = []
    for (ba, season, hb), g in t.groupby(["respondent", "season", "hb"]):
        if len(g) >= 100 or (len(g) >= 30 and len(list(years)) == 1):
            rows.append({"ba": ba, "season": season, "hour": hb, "mef_kg_mwh": coef(g, controls), "n": len(g)})
    return pd.DataFrame(rows)


def main() -> None:
    d = panel()
    out = []
    for test_year, train_years in TESTS.items():
        for spec, controls in SPECS.items():
            tr, te = profile(d, controls, train_years), profile(d, controls, [test_year])
            m = tr.merge(te, on=["ba", "season", "hour"], suffixes=("_tr", "_te"))
            for ba, g in m.groupby("ba"):
                out.append({"test_year": test_year, "spec": spec, "ba": ba, "cells": len(g),
                            "mef_mean_train": g.mef_kg_mwh_tr.mean(), "mef_mean_test": g.mef_kg_mwh_te.mean(),
                            "corr_train_test": g.mef_kg_mwh_tr.corr(g.mef_kg_mwh_te),
                            "mad_pct_of_train_mean": 100 * (g.mef_kg_mwh_tr - g.mef_kg_mwh_te).abs().mean() / abs(g.mef_kg_mwh_tr.mean()),
                            "share_negative_train": (g.mef_kg_mwh_tr < 0).mean()})
    R = pd.DataFrame(out)
    R.round(2).to_csv(ROOT / "results/mef_robustness.csv", index=False)
    pd.set_option("display.width", 200)
    for col, label in (("corr_train_test", "profile correlation, train vs test year"),
                       ("mad_pct_of_train_mean", "mean abs difference, % of train mean"),
                       ("mef_mean_train", "mean MEF over train years (kg/MWh)")):
        print(f"\n{label}")
        print(R.pivot_table(index=["ba", "spec"], columns="test_year", values=col).round(2).to_string())

    # scheduling replication for test year 2024 (base spec, 6 h bins)
    mef_tr = me.mef_table(d[d.year.between(2021, 2023)], boot=False, block=BLOCK)
    mef_te = me.mef_table(d[d.year == 2024], boot=False, block=BLOCK)
    S = me.schedule(d, mef_tr, mef_te, BLOCK, year=2024)
    cols = [c for c in S.columns if "|" in c and "mef_oracle_eval" not in c]
    sc = S.groupby("ba")[cols].mean().T
    sc["pooled"] = S[cols].mean().values
    sc.index = pd.MultiIndex.from_tuples([tuple(i.split("|")) for i in sc.index], names=["evaluated_on", "decision"])
    sc.round(1).to_csv(ROOT / "results/mef_scheduling_2024.csv")
    print("\nScheduling replicate, test year 2024 (% saved vs random, 8 h preemptible; in-sample 'mef_oracle_eval' omitted):")
    print(sc.round(1).to_string())
    print("days per BA:", S.groupby("ba").day.nunique().to_dict())


if __name__ == "__main__":
    main()
