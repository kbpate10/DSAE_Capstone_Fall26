"""Measured generation-side water factors for the Arizona BAs from EIA-860 / EIA-923 (replaces literature medians where plants report).

Sources (2025 data year; downloaded to data/raw/eia860/ and data/raw/eia923/ by download_static.sh):
  * EIA-923 Schedule 8D "Cooling System Information": monthly water consumption (million gallons) per cooling system. Collected for plants with
    combustible-fuel steam capacity of 100 MW or more (and nuclear), so most small gas turbines, PV, wind and hydro do not report.
  * EIA-923 Page 1: monthly net generation by plant, fuel and prime mover, with the plant's balancing authority.
  * EIA-860 Schedule 6D "Cooling": cooling-system type (used for the descriptive table; the 8D sheet carries a text type too).
Run with isolated Python because these are downloaded files:  .venv/bin/python -I src/build_water_factors.py

Method
  * plant-month consumption is the sum over the plant's cooling systems; a plant-month is valid only if every system reports a number
    (EIA writes "." for missing). Invalid months are dropped from BOTH numerator and denominator (flagged, not imputed).
  * plant intensity (L/kWh) = valid-month consumption / valid-month net generation of the plant's main fuel group.
  * fuel groups follow EIA-930: COL (BIT SUB LIG ANT WC RC), NG, NUC, OIL (DFO RFO JF KER WO), WND, WAT, OTH (anything else except storage),
    and solar split into SUN_PV (prime mover PV) and SUN_CSP (prime mover CP, concentrating solar).
  * BA x fuel factor, two versions for the generation that does NOT report:
      M1: non-reporting fossil/nuclear/other generation uses 0 L/kWh (dry or small units), PV uses the literature 0.10 (water_frontier.WF["SUN"]);
      M2: non-reporting fossil generation uses the literature factor of its fuel (water_frontier.WF), the upper bound.
    The share of each BA x fuel generation that reports is kept as `coverage`.
  * solar: the EIA-930 series has one SUN category, so the factor is a monthly blend of CSP (measured) and PV (literature) weighted by that
    month's 923 generation. The hourly timing of CSP water within a day is NOT resolved (storage shifts CSP output to the evening).
  * 2025 factors are applied to every year 2021-2025 downstream: an assumption, because earlier 923 files were not pulled and plant mixes change.
Checks written to results/water_factors_crosscheck.csv: 923 annual generation by BA and fuel vs the EIA-930 series for 2025.

Outputs: data/processed/water_factors_measured.parquet, results/water_plant_cooling_az.csv, results/water_measured_factors.csv,
         results/water_factors_crosscheck.csv
"""
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import water_frontier as wf

BAS = ["AZPS", "SRP", "TEPC", "WALC"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
COAL = {"BIT", "SUB", "LIG", "ANT", "WC", "RC"}
OIL = {"DFO", "RFO", "JF", "KER", "WO"}
L_PER_MGAL = 3.78541e6          # litres per million gallons
KWH_PER_MWH = 1000.0


def clean_cols(d):
    d.columns = [re.sub(r"\\s+", " ", str(c)).strip() for c in d.columns]
    d.columns = [re.sub(r"\s+", " ", c) for c in d.columns]
    return d


def fuel_group(fuel: str, pm: str) -> str | None:
    if fuel in COAL:
        return "COL"
    if fuel == "NG":
        return "NG"
    if fuel == "NUC":
        return "NUC"
    if fuel in OIL:
        return "OIL"
    if fuel == "WND":
        return "WND"
    if fuel == "WAT":
        return "WAT"
    if fuel == "SUN":
        return "SUN_CSP" if pm == "CP" else "SUN_PV"
    if fuel == "MWH":
        return None                         # storage: not generation (excluded in carbon_intensity.py too)
    return "OTH"


def load_generation(d923: Path) -> pd.DataFrame:
    f = d923 / "EIA923_Schedules_2_3_4_5_M_12_2025_Final.xlsx"
    g = clean_cols(pd.read_excel(f, sheet_name="Page 1 Generation and Fuel Data", header=5))
    g = g[g["Balancing Authority Code"].isin(BAS)].copy()
    cols = [f"Netgen {m}" for m in MONTHS]
    for c in cols:
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g["group"] = [fuel_group(a, b) for a, b in zip(g["Reported Fuel Type Code"], g["Reported Prime Mover"])]
    g = g[g.group.notna()]
    long = g.melt(id_vars=["Plant Id", "Plant Name", "Balancing Authority Code", "group"], value_vars=cols, var_name="m", value_name="mwh")
    long["month"] = long.m.str.replace("Netgen ", "").map({m: i + 1 for i, m in enumerate(MONTHS)})
    long = long.groupby(["Plant Id", "Plant Name", "Balancing Authority Code", "group", "month"], as_index=False).mwh.sum()
    return long.rename(columns={"Plant Id": "plant", "Plant Name": "plant_name", "Balancing Authority Code": "ba"})


def load_cooling(d923: Path, plants: set) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = d923 / "EIA923_Schedule_8_Annual_Envir_Infor_2025_Final.xlsx"
    d = clean_cols(pd.read_excel(f, sheet_name="8D Cooling System Information", header=4))
    d = d[d["Plant ID"].isin(plants)].copy()
    d["cons"] = pd.to_numeric(d["Consumption Volume (million gallons)"], errors="coerce")
    d["wdr"] = pd.to_numeric(d["Withdrawal Volume (million gallons)"], errors="coerce")
    d["hours"] = pd.to_numeric(d["Hours in Service"], errors="coerce")
    pm = d.groupby(["Plant ID", "Month"]).agg(cons=("cons", lambda s: s.sum(min_count=1) if s.notna().all() else np.nan),
                                              wdr=("wdr", lambda s: s.sum(min_count=1) if s.notna().all() else np.nan)).reset_index()
    pm.columns = ["plant", "month", "cons_Mgal", "wdr_Mgal"]
    return pm, d


def main(d860: Path, d923: Path) -> None:
    gen = load_generation(d923)
    plants = set(gen.plant)
    pm, raw8d = load_cooling(d923, plants)

    # main fuel group per plant (largest annual generation)
    main_grp = gen.groupby(["plant", "group"]).mwh.sum().reset_index().sort_values("mwh", ascending=False).drop_duplicates("plant").set_index("plant").group
    gp = gen.merge(main_grp.rename("main"), left_on="plant", right_index=True)
    gp = gp[gp.group == gp.main]                                       # generation of each plant's main fuel group
    pmg = gp.groupby(["plant", "plant_name", "ba", "group", "month"], as_index=False).mwh.sum()
    jm = pmg.merge(pm, on=["plant", "month"], how="left")
    jm["valid"] = jm.cons_Mgal.notna() & (jm.mwh > 0)

    plant = jm.groupby(["plant", "plant_name", "ba", "group"]).apply(lambda t: pd.Series({
        "gen_mwh_year": t.mwh.sum(), "gen_mwh_valid": t.loc[t.valid, "mwh"].sum(), "months_valid": int(t.valid.sum()),
        "cons_Mgal_valid": t.loc[t.valid, "cons_Mgal"].sum(), "wdr_Mgal_valid": t.loc[t.valid, "wdr_Mgal"].sum()})).reset_index()
    plant["reports"] = plant.months_valid > 0
    plant["L_per_kWh"] = np.where(plant.reports, plant.cons_Mgal_valid * L_PER_MGAL / (plant.gen_mwh_valid * KWH_PER_MWH), np.nan)
    plant["withdrawal_L_per_kWh"] = np.where(plant.reports, plant.wdr_Mgal_valid * L_PER_MGAL / (plant.gen_mwh_valid * KWH_PER_MWH), np.nan)
    ctype = (raw8d.groupby("Plant ID")["Type of Cooling System"].agg(lambda s: "; ".join(sorted(set(s.dropna())))).rename("cooling_type"))
    plant = plant.merge(ctype, left_on="plant", right_index=True, how="left")
    plant.round(4).sort_values(["ba", "group", "gen_mwh_year"], ascending=[True, True, False]).to_csv(ROOT / "results/water_plant_cooling_az.csv", index=False)

    lit = {"COL": wf.WF["COL"], "NG": wf.WF["NG"], "NUC": wf.WF["NUC"], "OIL": wf.WF["OIL"], "OTH": wf.WF["OTH"],
           "WND": wf.WF["WND"], "WAT": wf.WF["WAT"], "SUN_PV": wf.WF["SUN"], "SUN_CSP": np.nan}
    rows = []
    for (ba, grp), t in plant.groupby(["ba", "group"]):
        rep = t[t.reports]
        gen_all = t.gen_mwh_year.sum()
        gen_rep = rep.gen_mwh_year.sum()
        rep_water = (rep.L_per_kWh * rep.gen_mwh_year).sum()               # plant intensity x annual generation (L per kWh x MWh)
        nonrep = gen_all - gen_rep
        f_lit = lit[grp] if np.isfinite(lit[grp]) else np.nan
        nonrep_m1 = lit["SUN_PV"] if grp == "SUN_PV" else 0.0
        nonrep_m2 = f_lit if np.isfinite(f_lit) else 0.0
        rows.append({"ba": ba, "group": grp, "gen_mwh_2025": gen_all, "coverage": gen_rep / gen_all if gen_all else np.nan,
                     "plants": len(t), "plants_reporting": int(t.reports.sum()),
                     "L_per_kWh_reported_only": rep_water / gen_rep if gen_rep else np.nan,
                     "L_per_kWh_M1": (rep_water + nonrep * nonrep_m1) / gen_all if gen_all else np.nan,
                     "L_per_kWh_M2": (rep_water + nonrep * nonrep_m2) / gen_all if gen_all else np.nan,
                     "literature_L_per_kWh": f_lit})
    F = pd.DataFrame(rows)

    # 930-fuel table: SUN is a monthly blend of CSP (measured, M1/M2 same) and PV (literature)
    out = []
    for ba in BAS:
        for grp in ["COL", "NG", "NUC", "OIL", "OTH", "WND", "WAT"]:
            r = F[(F.ba == ba) & (F.group == grp)]
            for v, col in (("M1", "L_per_kWh_M1"), ("M2", "L_per_kWh_M2")):
                if len(r):
                    out.append({"respondent": ba, "fueltype": grp if grp != "OTH" else "OTH", "month": 0, "version": v, "wf": float(r[col].iloc[0]),
                                "coverage": float(r.coverage.iloc[0])})
                else:
                    out.append({"respondent": ba, "fueltype": grp, "month": 0, "version": v, "wf": float(lit[grp]), "coverage": np.nan})
        csp = F[(F.ba == ba) & (F.group == "SUN_CSP")]
        f_csp = float(csp.L_per_kWh_M1.iloc[0]) if len(csp) else np.nan
        sg = gen[(gen.ba == ba) & gen.group.isin(["SUN_PV", "SUN_CSP"])].pivot_table(index="month", columns="group", values="mwh", aggfunc="sum")
        for mth in range(1, 13):
            pv = float(sg.SUN_PV.get(mth, 0.0)) if "SUN_PV" in sg else 0.0
            cp = float(sg.SUN_CSP.get(mth, 0.0)) if "SUN_CSP" in sg else 0.0
            tot = pv + cp
            f = (cp * (f_csp if np.isfinite(f_csp) else 0.0) + pv * lit["SUN_PV"]) / tot if tot > 0 else lit["SUN_PV"]
            for v in ("M1", "M2"):
                out.append({"respondent": ba, "fueltype": "SUN", "month": mth, "version": v, "wf": f, "coverage": (cp / tot if tot > 0 else 0.0)})
    T = pd.DataFrame(out)
    T.to_parquet(ROOT / "data/processed/water_factors_measured.parquet", index=False)

    pd.set_option("display.width", 220)
    show = F.copy()
    show["gen_GWh_2025"] = show.gen_mwh_2025 / 1000
    print("Plant-level cooling water intensity, reporting plants (L of consumption per kWh of net generation, 2025):")
    print(plant[plant.reports].assign(GWh=lambda t: t.gen_mwh_year / 1000)[["plant_name", "ba", "group", "GWh", "months_valid", "L_per_kWh", "cooling_type"]]
          .sort_values(["ba", "group", "GWh"], ascending=[True, True, False]).round(2).to_string(index=False))
    print("\nBA x fuel factors (L/kWh): measured vs literature (water_frontier.WF); coverage = share of generation that reports:")
    print(show[["ba", "group", "gen_GWh_2025", "coverage", "plants", "plants_reporting", "L_per_kWh_reported_only", "L_per_kWh_M1", "L_per_kWh_M2", "literature_L_per_kWh"]]
          .round(2).to_string(index=False))
    F.round(4).to_csv(ROOT / "results/water_measured_factors.csv", index=False)

    # cross-check against EIA-930 2025 generation
    m = pd.read_parquet(ROOT / "data/processed/master_ba_hour.parquet")
    m = m[(m.ts.dt.year == 2025) & m.respondent.isin(BAS)]
    chk = []
    for ba in BAS:
        for f930, grps in (("COL", ["COL"]), ("NG", ["NG"]), ("NUC", ["NUC"]), ("SUN", ["SUN_PV", "SUN_CSP"]), ("WND", ["WND"]), ("WAT", ["WAT"])):
            e930 = m[m.respondent == ba][f"gen_{f930}_mwh"].sum()
            e923 = gen[(gen.ba == ba) & gen.group.isin(grps)].mwh.sum()
            chk.append({"ba": ba, "fuel": f930, "eia930_GWh": e930 / 1000, "eia923_GWh": e923 / 1000, "ratio_923_over_930": e923 / e930 if e930 else np.nan})
    C = pd.DataFrame(chk)
    C.round(3).to_csv(ROOT / "results/water_factors_crosscheck.csv", index=False)
    print("\nCross-check, 2025 generation (GWh): EIA-923 plant data vs EIA-930 BA series")
    print(C.round(2).to_string(index=False))


if __name__ == "__main__":
    main(ROOT / "data/raw/eia860", ROOT / "data/raw/eia923")
