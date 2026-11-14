"""Stage 1 <-> Stage 2 coupling: does adding operating carbon and water change which sites are selected?

Stage 1 ranks cells by a static suitability score and applies utility caps (stage1_optimizer.py).
Stage 2 (the scheduler) determines what a project emits and consumes once it runs. This script gives every
eligible cell an annual operating footprint for a P MW project and re-solves the Stage 1 problem with it.

Footprint per cell (all scenario estimates, not measurements):
  balancing authority   serving utility -> BA: APS->AZPS, SRP->SRP, TEP->TEPC. Other utilities have no BA
                        operating data in this project and are EXCLUDED from the coupled problem (assumption).
  carbon                PUE * mean carbon intensity of the BA, 2021-2024, flagged hours excluded
                        (production-based, so SRP looks clean mainly because Palo Verde is reported there).
  generation water      PUE * generation-weighted consumption factors of the BA's mix (water_frontier.WF).
  on-site cooling water hourly curve W_on(Tw) from water_frontier, applied to the NASA POWER hourly wet-bulb of
                        the nearest of PHX / TUS / HAV shifted by (cell mean wet-bulb - station mean wet-bulb).
                        The shift is an assumption: the cell wet-bulb is an annual mean, not an hourly series.
  scheduling credit     a fraction F_FLEX of load is carbon-aware (8 h preemptible job, 2025 test, savings vs
                        random timing from results/schedule_savings.csv, LightGBM resid_demand column).
                        Applied to carbon only; it is deployable savings, not the oracle.

Coupled selection: maximise sum_i [ (1-w) * score_i + w * (1 - footprint_i) ] under the Stage 1 caps, where footprint_i
is min-max-scaled over the eligible cells: 'both' = mean of carbon and water, or carbon only / water only. w is swept,
not chosen. Carbon and generation water are constants within a BA, so only on-site water separates cells of one BA.
Comparison: overlap of selected sets and the regret each selection incurs on the other's objective.

Variant: carbon from consumption_ci.parquet (flow-traced) with the matching scheduling credit -> results/stage2_coupling_consumption.csv
and a 'consumption CI' case in the sensitivity runs.

Outputs: results/stage2_cell_footprint.csv, results/stage2_coupling.csv, results/stage2_coupling_consumption.csv, results/figures/stage2_coupling.png
"""
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage1_optimizer as s1
import water_frontier as wf

UTIL_BA = {803: "AZPS", 16572: "SRP", 24211: "TEPC"}
STATIONS = {"PHX": (33.43, -112.01), "TUS": (32.12, -110.94), "HAV": (34.57, -113.58)}
F_FLEX, K_JOB = 0.3, 8
P, K_SITES = 500, 3
WEIGHTS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)


def nearest_station(lat, lon):
    return min(STATIONS, key=lambda s: (STATIONS[s][0] - lat) ** 2 + ((STATIONS[s][1] - lon) * 0.84) ** 2)


def ba_operating(factors=None, carbon: str = "prod") -> pd.DataFrame:
    """carbon='prod': production-based intensity and LightGBM scheduling savings (schedule_savings.csv).
    carbon='cons': flow-traced consumption-based intensity (consumption_ci.parquet) over the same valid hours, and the
    persistence-decision savings evaluated on consumption (consumption_scheduling.csv). Water is production-side in both."""
    d = wf.build(wf=wf.WF if factors is None else factors)
    t = d[(d.local.dt.year >= 2021) & (d.local.dt.year <= 2024)].dropna(subset=["C", "W_off"])
    ops = t.groupby("respondent").agg(C_kg_kwh=("C", "mean"), W_off_l_kwh=("W_off", "mean"))
    sv = pd.read_csv(ROOT / "results/schedule_savings.csv")
    sv = sv[(sv.job == "preemptible") & (sv.k == K_JOB)].set_index("ba")
    # schedule_savings.csv holds % saved vs run-immediately; convert to a fraction saved vs random timing
    ops["sched_saving_frac"] = 1 - (1 - sv["resid_demand"] / 100) / (1 - sv["random"] / 100)
    if carbon == "cons":
        c = pd.read_parquet(ROOT / "data/processed/consumption_ci.parquet")
        c = c[c.valid & (c.ts - pd.Timedelta(hours=7)).dt.year.between(2021, 2024)]
        ops["C_kg_kwh"] = wf.PUE * c.groupby("respondent").ci_cons.mean() / 1000.0
        same = wf.PUE * c.groupby("respondent").ci_prod.mean() / 1000.0
        print("Carbon per kWh IT (kg), same valid hours: production vs consumption\n",
              pd.DataFrame({"prod": same, "cons": ops.C_kg_kwh}).dropna().round(3).to_string())
        cs = pd.read_csv(ROOT / "results/consumption_scheduling.csv").set_index(["decision", "evaluated_on"])
        ops["sched_saving_frac"] = cs.loc[("decide_cons", "eval_cons")].reindex(ops.index).astype(float) / 100.0
    return ops


def station_tw() -> dict:
    out = {}
    for s in STATIONS:
        w = pd.read_parquet(ROOT / f"data/raw/weather/nasa_hourly_{s}.parquet")
        out[s] = w[w.ts_local.dt.year.between(2021, 2024)].T2MWET.to_numpy()
    return out


def onsite_water(tw_hourly: np.ndarray, shift: float) -> float:
    tw = tw_hourly + shift
    return float((wf.WUE_MAX * np.clip((tw - wf.TW_LO) / (wf.TW_HI - wf.TW_LO), 0, 1)).mean())


def footprint(sites, ops, tw, st_mean, P, f_flex, pue) -> pd.DataFrame:
    """Per-cell annual footprint. ops is built at wf.PUE; carbon and generation water scale linearly in PUE."""
    E_mwh = P * s1.LF * s1.HRS
    k = pue / wf.PUE
    rows = []
    for cid, r in sites.iterrows():
        st = nearest_station(r.lat, r.lon)
        w_on = onsite_water(tw[st], r.wetbulb_c - st_mean[st])
        o = ops.loc[r.ba]
        rows.append({"cell_id": cid, "station": st, "wb_shift_c": r.wetbulb_c - st_mean[st],
                     "carbon_kt": k * o.C_kg_kwh * (1 - f_flex * o.sched_saving_frac) * E_mwh / 1000,
                     "water_on_Mm3": w_on * E_mwh / 1e6,
                     "water_off_Mm3": k * o.W_off_l_kwh * E_mwh / 1e6})
    fp = pd.DataFrame(rows).set_index("cell_id")
    fp["water_Mm3"] = fp.water_on_Mm3 + fp.water_off_Mm3
    return fp


def minmax(s):
    return (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else s * 0


def select(sites, fp, uu, w, K, tau, A_max, P, beta, kind="both"):
    t = sites.join(fp)
    f = {"both": 0.5 * minmax(t.carbon_kt) + 0.5 * minmax(t.water_Mm3),
         "carbon": minmax(t.carbon_kt), "water": minmax(t.water_Mm3)}[kind]
    t["obj"] = (1 - w) * t.score + w * (1 - f)
    ch, _, _ = s1.run(t, uu, K, tau, A_max, P, beta, "obj")
    return t, ch


def weight_table(sites, uu, tau, beta):
    """Sweep the footprint weight for each footprint kind; sites must carry carbon_kt and water_Mm3."""
    mm = minmax
    FOOT = {"both": 0.5 * mm(sites.carbon_kt) + 0.5 * mm(sites.water_Mm3), "carbon": mm(sites.carbon_kt),
            "water": mm(sites.water_Mm3)}
    out, sel = [], {}
    for kind, fcol in FOOT.items():
        for w in WEIGHTS:
            t = sites.assign(obj=(1 - w) * sites.score + w * (1 - fcol))
            ch, _, _ = s1.run(t, uu, K_SITES, tau, s1.DEFAULT["A_max"], P, beta, "obj")
            sel[(kind, w)] = set(ch)
            c = sites.loc[ch]
            out.append({"footprint": kind, "w": w, "n_selected": len(ch), "sum_score": c.score.sum(),
                        "sum_carbon_kt": c.carbon_kt.sum(), "sum_water_Mm3": c.water_Mm3.sum(),
                        "cells": ";".join(f"{i}({c.loc[i, 'ba']},{c.loc[i, 'county_short']})" for i in ch)})
    R = pd.DataFrame(out)
    base = sel[("both", 0.0)]
    R["jaccard_vs_stage1"] = [len(sel[(k, w)] & base) / len(sel[(k, w)] | base) if (sel[(k, w)] | base) else np.nan
                              for k, w in zip(R.footprint, R.w)]
    return R


def sweeps(sites, uu, ops_cases, tw, st_mean, tau, beta) -> pd.DataFrame:
    """One-at-a-time sensitivity around the default. Reports, at w = 0.5 ('both') vs w = 0 (Stage 1 alone):
    overlap of the selected sets, % water saved, % suitability lost, and carbon change."""
    D = dict(P=P, K=K_SITES, A=s1.DEFAULT["A_max"], f=F_FLEX, pue=wf.PUE, case="base")
    grid = ([("P", v) for v in (100, 250, 500, 1000)] + [("K", v) for v in (1, 2, 3, 5)] +
            [("A", v) for v in (0.10, 0.25, 0.50)] + [("f", v) for v in (0.0, 0.3, 0.6)] +
            [("pue", v) for v in (1.1, 1.2, 1.5)] + [("case", v) for v in ops_cases])
    rows = []
    for name, v in grid:
        c = {**D, name: v}
        fp = footprint(sites, ops_cases[c["case"]], tw, st_mean, c["P"], c["f"], c["pue"])
        t0, ch0 = select(sites, fp, uu, 0.0, c["K"], tau, c["A"], c["P"], beta)
        t1, ch1 = select(sites, fp, uu, 0.5, c["K"], tau, c["A"], c["P"], beta)
        a, b = t0.loc[ch0], t1.loc[ch1]
        u = set(ch0) | set(ch1)
        rows.append({"param": name, "value": v, "n_stage1": len(ch0), "n_coupled": len(ch1),
                     "jaccard": len(set(ch0) & set(ch1)) / len(u) if u else np.nan,
                     "score_loss_pct": 100 * (1 - b.score.sum() / a.score.sum()) if len(a) else np.nan,
                     "water_saved_pct": 100 * (1 - b.water_Mm3.sum() / a.water_Mm3.sum()) if len(a) else np.nan,
                     "carbon_change_pct": 100 * (b.carbon_kt.sum() / a.carbon_kt.sum() - 1) if len(a) else np.nan,
                     "stage1_cells": ";".join(ch0), "coupled_cells": ";".join(ch1)})
    return pd.DataFrame(rows)


def main() -> None:
    cells = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    util = s1.utility_table()
    ops = ba_operating()
    print("BA operating profile (2021-2024):\n", ops.round(3).to_string())
    tw = station_tw()
    st_mean = {s: v.mean() for s, v in tw.items()}

    a = s1.assign("all", util).set_index("cell_id")
    sites = cells.join(a, how="inner")
    sites = sites[sites.util_num.notna()].copy()
    sites["ba"] = sites.util_num.astype(int).map(UTIL_BA)
    sites = sites[sites.ba.notna() & sites.baseline_saidi.notna()].copy()
    print(f"\n{len(sites)} cells have both a BA-mapped utility and reliability data")

    fp = footprint(sites, ops, tw, st_mean, P, F_FLEX, wf.PUE)
    sites = sites.join(fp)
    mm = minmax
    sites["footprint"] = 0.5 * mm(sites.carbon_kt) + 0.5 * mm(sites.water_Mm3)
    FOOT = {"both": sites.footprint, "carbon": mm(sites.carbon_kt), "water": mm(sites.water_Mm3)}
    sites[["county_short", "util_name", "ba", "score", "rank", "carbon_kt", "water_on_Mm3", "water_off_Mm3",
           "water_Mm3", "footprint"]].round(3).sort_values("rank").to_csv(ROOT / "results/stage2_cell_footprint.csv")

    uu = util.loc[sorted(set(sites.util_num.astype(int)))]
    tau, beta = s1.national_median_saidi(), s1.beta_upper()
    R = weight_table(sites, uu, tau, beta)
    R.round(3).to_csv(ROOT / "results/stage2_coupling.csv", index=False)
    print(f"\nCoupled selection (P={P} MW, K={K_SITES}, tau_R={tau:.0f}, A_max={s1.DEFAULT['A_max']:.0%}):")
    print(R.drop(columns="cells").round(3).to_string(index=False))
    print(R[["footprint", "w", "cells"]].to_string(index=False))

    print("\nBA footprint spread across eligible cells (kt CO2/yr, Mm3 water/yr):")
    print(sites.groupby("ba")[["carbon_kt", "water_on_Mm3", "water_off_Mm3"]].agg(["mean", "min", "max"]).round(2).to_string())
    print("\nRank correlation between Stage 1 score and footprint across eligible cells:",
          round(sites.score.corr(sites.footprint, method="spearman"), 3))

    base_cols = ["lat", "lon", "wetbulb_c", "score", "util_num", "ba", "baseline_saidi", "ci_mwh", "county_short"]
    ss = sites[base_cols]
    ops_c = ba_operating(carbon="cons")
    sites_c = sites.drop(columns=fp.columns).join(footprint(sites, ops_c, tw, st_mean, P, F_FLEX, wf.PUE))
    Rc = weight_table(sites_c, uu, tau, beta)
    Rc.round(3).to_csv(ROOT / "results/stage2_coupling_consumption.csv", index=False)
    print("\nSame sweep with consumption-based carbon (and its scheduling credit):")
    print(Rc.drop(columns="cells").round(3).to_string(index=False))
    print(Rc[["footprint", "w", "cells"]].to_string(index=False))
    print("Per-BA carbon (kt/yr, 500 MW) production -> consumption:",
          sites.groupby("ba").carbon_kt.first().round(0).to_dict(), "->", sites_c.groupby("ba").carbon_kt.first().round(0).to_dict())
    meas = pd.read_parquet(ROOT / "data/processed/water_factors_measured.parquet")
    ops_w = ba_operating(meas[meas.version == "M1"].drop(columns=["version", "coverage"]))     # EIA-860/923 measured generation-side water
    cases = {"base": ops, "consumption CI": ops_c, "measured generation water (EIA-860/923, M1)": ops_w,
             "nuclear x0": ba_operating({**wf.WF, "NUC": 0.0}),
             "hydro 17 L/kWh": ba_operating({**wf.WF, "WAT": 17.0})}
    SW = sweeps(ss, uu, cases, tw, st_mean, tau, beta)
    SW.round(2).to_csv(ROOT / "results/stage2_sensitivity.csv", index=False)
    print("\nSensitivity (coupled w=0.5 vs Stage 1 alone, one parameter changed at a time):")
    print(SW.drop(columns=["stage1_cells", "coupled_cells"]).round(2).to_string(index=False))

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].scatter(sites.footprint, sites.score, c=sites.ba.map({"AZPS": "#1b6ca8", "SRP": "#edae49", "TEPC": "#2a9d8f"}), s=26)
    ax[0].set_xlabel("operating footprint (0 = lowest, 1 = highest)"); ax[0].set_ylabel("Stage 1 suitability score")
    ax[0].set_title("Eligible cells: suitability vs operating footprint", fontsize=10); ax[0].grid(alpha=.25)
    Rb = R[R.footprint == "both"]
    ax[1].plot(Rb.w, Rb.sum_carbon_kt, marker="o", color="#d1495b")
    ax2 = ax[1].twinx()
    ax2.plot(Rb.w, Rb.sum_score, marker="s", color="#1b6ca8")
    ax[1].set_xlabel("weight on footprint w"); ax[1].set_ylabel("carbon of selected sites (kt/yr)"); ax2.set_ylabel("suitability of selected sites")
    ax[1].set_title("What coupling trades off", fontsize=10); ax[1].grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/stage2_coupling.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
