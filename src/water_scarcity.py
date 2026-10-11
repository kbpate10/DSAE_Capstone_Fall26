"""Scarcity-weighted water scenarios: does the carbon-water conflict survive different water accounting?

Palo Verde (the nuclear plant reported in SRP's BA) cools with reclaimed municipal wastewater, not
potable or groundwater. Scenarios scale the nuclear consumption factor by a scarcity weight (1.0 = count it
like freshwater, 0.25, 0.0 = effluent treated as free) and optionally count hydro reservoir evaporation.

Same frontier machinery as water_frontier.py (8-hour preemptible job, persistence forecasts, 2025).
Outputs: results/water_scarcity.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import water_frontier as wf

ROOT = Path(__file__).resolve().parents[1]
wf.KS = [8]
NUC = wf.WF["NUC"]
CASES = {
    "A  base (nuclear counted as freshwater, hydro 0)": dict(NUC=NUC, WAT=0.0),
    "B  nuclear x0.25 (mostly effluent)": dict(NUC=NUC * 0.25, WAT=0.0),
    "C  nuclear x0 (effluent treated as free)": dict(NUC=0.0, WAT=0.0),
    "D  hydro 17 L/kWh, nuclear counted": dict(NUC=NUC, WAT=17.0),
    "E  hydro 17 L/kWh, nuclear x0": dict(NUC=0.0, WAT=17.0),
}


def main() -> None:
    rows = []
    for name, ov in CASES.items():
        fac = {**wf.WF, **ov}
        d = wf.build(fac, wf.WUE_MAX)
        desc = wf.describe(d).set_index("ba")
        F = wf.frontier(d)
        S = wf.summarize(F, by=("ba", "job", "k", "mode", "alpha"))
        P = wf.summarize(F, by=("job", "k", "mode", "alpha"))
        for scope, tbl in [("pooled", P)] + [(b, S[S.ba == b]) for b in wf.BAS]:
            t = tbl[(tbl.job == "preemptible") & (tbl.k == 8) & (tbl["mode"] == "persist")].set_index("alpha")
            rows.append({"case": name, "scope": scope,
                         "carbonOnly_carbon": t.loc[1.0, "carbon_saved_vs_random_pct"],
                         "carbonOnly_water": t.loc[1.0, "water_saved_vs_random_pct"],
                         "balanced_carbon": t.loc[0.5, "carbon_saved_vs_random_pct"],
                         "balanced_water": t.loc[0.5, "water_saved_vs_random_pct"],
                         "waterOnly_carbon": t.loc[0.0, "carbon_saved_vs_random_pct"],
                         "waterOnly_water": t.loc[0.0, "water_saved_vs_random_pct"],
                         "within_day_corr_C_W": desc.within_day_corr_C_W.mean() if scope == "pooled" else desc.loc[scope, "within_day_corr_C_W"],
                         "mean_W": desc.W_total.mean() if scope == "pooled" else desc.loc[scope, "W_total"]})
        print("done", name, flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(ROOT / "results/water_scarcity.csv", index=False)
    pd.set_option("display.width", 220)
    print("\n=== Carbon-only policy: water change (%, + = saves water), by BA ===")
    print(R.pivot(index="case", columns="scope", values="carbonOnly_water")[["pooled", "AZPS", "SRP", "TEPC", "WALC"]].round(1).to_string())
    print("\n=== Water-only policy: carbon change (%, + = saves carbon), by BA ===")
    print(R.pivot(index="case", columns="scope", values="waterOnly_carbon")[["pooled", "AZPS", "SRP", "TEPC", "WALC"]].round(1).to_string())
    print("\n=== Within-day correlation, carbon vs total water, by BA ===")
    print(R.pivot(index="case", columns="scope", values="within_day_corr_C_W")[["pooled", "AZPS", "SRP", "TEPC", "WALC"]].round(2).to_string())
    print("\n=== Balanced policy (alpha=0.5): carbon / water saved, pooled ===")
    print(R[R.scope == "pooled"][["case", "balanced_carbon", "balanced_water", "carbonOnly_carbon", "waterOnly_water"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
