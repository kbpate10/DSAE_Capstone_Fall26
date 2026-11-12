"""Does the carbon-water conclusion change when generation-side water uses measured EIA-860/923 plant data instead of literature medians?

Same frontier machinery and scenario set as water_scarcity.py (8 h preemptible job, persistence forecasts, 2025 test days; savings vs random
timing; alpha = 1 carbon-only, 0.5 balanced, 0 water-only), with these generation-side factor sets (build_water_factors.py):
  literature     Macknick et al. (2012) medians, one factor per fuel for every BA (water_frontier.WF): the Midpoint 1 base case
  measured M1    BA x fuel factors from plant cooling-water consumption; non-reporting fossil generation at 0 L/kWh (lower bound)
  measured M2    same, non-reporting fossil generation at the literature factor (upper bound)
  M1, CSP as PV  M1 with solar fixed at the PV literature factor: isolates what separating the solar-thermal plant (Solana) changes
Each is run with the nuclear and hydro variants of the earlier scarcity analysis (Palo Verde is cooled with reclaimed wastewater; hydro reservoir
evaporation is contested): nuclear counted as freshwater (x1) or treated as free (x0); hydro 0 or 17 L/kWh.
On-site cooling water, PUE (1.2) and the carbon side are unchanged. Measured 2025 factors are applied to every year (assumption).

Outputs: results/water_measured_cases.csv, results/water_measured_levels.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import water_frontier as wf

wf.KS = [8]


def table(version: str, nuc: float = 1.0, hydro: float = 0.0, csp_as_pv: bool = False) -> pd.DataFrame:
    t = pd.read_parquet(ROOT / "data/processed/water_factors_measured.parquet")
    t = t[t.version == version].drop(columns=["version", "coverage"]).copy()
    t.loc[t.fueltype == "NUC", "wf"] *= nuc
    t.loc[t.fueltype == "WAT", "wf"] = hydro
    if csp_as_pv:
        t.loc[t.fueltype == "SUN", "wf"] = wf.WF["SUN"]
    return t


def cases() -> dict:
    out = {"literature | nuclear x1, hydro 0": {**wf.WF}, "literature | nuclear x0, hydro 0": {**wf.WF, "NUC": 0.0},
           "literature | nuclear x1, hydro 17": {**wf.WF, "WAT": 17.0}}
    for v in ("M1", "M2"):
        out[f"measured {v} | nuclear x1, hydro 0"] = table(v)
        out[f"measured {v} | nuclear x0, hydro 0"] = table(v, nuc=0.0)
        out[f"measured {v} | nuclear x1, hydro 17"] = table(v, hydro=17.0)
    out["M1, CSP counted as PV | nuclear x1, hydro 0"] = table("M1", csp_as_pv=True)
    return out


def main() -> None:
    rows, lev = [], []
    for name, fac in cases().items():
        d = wf.build(fac, wf.WUE_MAX)
        desc = wf.describe(d).set_index("ba")
        F = wf.frontier(d)
        S = wf.summarize(F, by=("ba", "job", "k", "mode", "alpha"))
        P = wf.summarize(F, by=("job", "k", "mode", "alpha"))
        for ba in wf.BAS:
            lev.append({"case": name, "ba": ba, "W_off_L_per_kWh": desc.loc[ba, "W_off_L_per_kWh"], "W_on_L_per_kWh": desc.loc[ba, "W_on_L_per_kWh"],
                        "W_total": desc.loc[ba, "W_total"], "C_kg_per_kWh": desc.loc[ba, "C_kg_per_kWh"],
                        "within_day_corr_C_W": desc.loc[ba, "within_day_corr_C_W"], "within_day_corr_C_Woff": desc.loc[ba, "within_day_corr_C_Woff"]})
        for scope, tbl in [("pooled", P)] + [(b, S[S.ba == b]) for b in wf.BAS]:
            t = tbl[(tbl.job == "preemptible") & (tbl.k == 8) & (tbl["mode"] == "persist")].set_index("alpha")
            rows.append({"case": name, "scope": scope,
                         "carbonOnly_carbon": t.loc[1.0, "carbon_saved_vs_random_pct"], "carbonOnly_water": t.loc[1.0, "water_saved_vs_random_pct"],
                         "balanced_carbon": t.loc[0.5, "carbon_saved_vs_random_pct"], "balanced_water": t.loc[0.5, "water_saved_vs_random_pct"],
                         "waterOnly_carbon": t.loc[0.0, "carbon_saved_vs_random_pct"], "waterOnly_water": t.loc[0.0, "water_saved_vs_random_pct"],
                         "within_day_corr_C_W": desc.within_day_corr_C_W.mean() if scope == "pooled" else desc.loc[scope, "within_day_corr_C_W"]})
        print("done", name, flush=True)
    R, L = pd.DataFrame(rows), pd.DataFrame(lev)
    R.round(3).to_csv(ROOT / "results/water_measured_cases.csv", index=False)
    L.round(4).to_csv(ROOT / "results/water_measured_levels.csv", index=False)
    pd.set_option("display.width", 230)
    print("\n=== Generation-side water per kWh of IT energy (L/kWh incl. PUE), mean 2021-2025, by case ===")
    print(L.pivot(index="case", columns="ba", values="W_off_L_per_kWh")[wf.BAS].round(2).to_string())
    print("\n=== Carbon-only policy: change in water (%, + = saves water; vs random timing) ===")
    print(R.pivot(index="case", columns="scope", values="carbonOnly_water")[["pooled"] + wf.BAS].round(1).to_string())
    print("\n=== Balanced policy (alpha = 0.5): water saved (%) ===")
    print(R.pivot(index="case", columns="scope", values="balanced_water")[["pooled"] + wf.BAS].round(1).to_string())
    print("\n=== Water-only policy: carbon saved (%) ===")
    print(R.pivot(index="case", columns="scope", values="waterOnly_carbon")[["pooled"] + wf.BAS].round(1).to_string())
    print("\n=== Within-day correlation of carbon and total water ===")
    print(R.pivot(index="case", columns="scope", values="within_day_corr_C_W")[["pooled"] + wf.BAS].round(2).to_string())


if __name__ == "__main__":
    main()
