"""Stage 1 with an interconnection screen: a voltage-and-proximity eligibility rule plus a shared-node cap.

NO CAPACITY DATA ARE PUBLIC at node level (headroom, queue studies for loads), so this is NOT a capacity model. What is built, from OSM substations
(data/raw/rq2/osm_substations_az.json; 1,266 of 1,461 carry a voltage tag), is:
  1. Eligibility screen: a cell is eligible only if a substation of at least V_MIN kV lies within D_MAX km of the cell centre
     (a 0.25-degree cell has a half-diagonal of about 18 km, so D_MAX of 20-30 km means "in or next to the cell"; the grid goes from 10 to 60 km
     because results at a single cutoff can be knife-edge: the default Maricopa cell is 25.5 km from its node).
  2. Node cap: at most M selected projects may share the same nearest qualifying substation (a stand-in for "one node cannot host two large loads";
     M is an assumption, swept).
The thresholds are assumptions, not data: a 500 MW load normally needs a transmission-voltage (roughly 230 kV or above) point of interconnection, but the
required voltage and distance depend on utility studies that are not public. They are swept, and results are shown as a price of interconnection,
not a recommendation. OSM voltage tags can be incomplete or wrong, and substations at power plants are included (a generator switchyard is not a load node).

Everything else is the Stage 1 default: 500 MW, load factor 0.8, A_max 25%, tau_R = national median SAIDI, beta = upper 95% RQ3 elasticity, K = 3, 'all' mapping.
The final block re-runs the Stage 2 coupling (carbon and water weights) on the interconnection-eligible cells: does the footprint start to matter once interconnection binds?

Outputs: results/stage1_cell_interconnection.csv, results/stage1_interconnection.csv, results/stage1_interconnection_coupling.csv,
         results/figures/stage1_interconnection.png
"""
import json
import re
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pulp
from sklearn.neighbors import BallTree

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage1_optimizer as s1
import stage2_coupling as s2

R_EARTH = 6371.0
VOLTS = (115, 230, 345, 500)
D_GRID = (10, 15, 20, 25, 30, 40, 60)
M_GRID = (1, 2, None)
K, P = 3, 500


def load_substations() -> pd.DataFrame:
    el = json.load(open(ROOT / "data/raw/rq2/osm_substations_az.json"))
    el = el if isinstance(el, list) else el.get("elements", [])
    rows = []
    for e in el:
        t = e.get("tags", {})
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        nums = [int(x) for x in re.findall(r"\d+", t.get("voltage", ""))]
        nums = [x * 1000 if x < 1000 else x for x in nums]
        rows.append({"id": e["id"], "lat": c["lat"], "lon": c["lon"], "kv": max(nums) / 1000 if nums else np.nan, "name": t.get("name")})
    return pd.DataFrame(rows).dropna(subset=["lat", "lon"])


def distances(cells: pd.DataFrame, subs: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=cells.index)
    xy = np.radians(cells[["lat", "lon"]].to_numpy())
    for v in VOLTS:
        s = subs[subs.kv >= v].reset_index(drop=True)
        d, i = BallTree(np.radians(s[["lat", "lon"]].to_numpy()), metric="haversine").query(xy, k=1)
        out[f"d{v}_km"] = d[:, 0] * R_EARTH
        out[f"node{v}"] = s.id.to_numpy()[i[:, 0]]
    return out


def solve(sites: pd.DataFrame, caps: dict, node_col: str | None, m: int | None, score="score", weights=None):
    prob = pulp.LpProblem("ic", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{k}", cat="Binary") for k, i in enumerate(sites.index)}
    prob += pulp.lpSum(sites.loc[i, score] * x[i] for i in x)
    prob += pulp.lpSum(x.values()) <= K
    for u, idx in sites.groupby("util_num").groups.items():
        prob += pulp.lpSum(x[i] for i in idx) <= caps.get(u, 0)
    if node_col and m is not None:
        for _, idx in sites.groupby(node_col).groups.items():
            prob += pulp.lpSum(x[i] for i in idx) <= m
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    ch = [i for i in x if x[i].value() and x[i].value() > 0.5]
    return ch


def main() -> None:
    cells = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    util = s1.utility_table()
    tau, beta = s1.national_median_saidi(), s1.beta_upper()
    sites = cells.join(s1.assign("all", util).set_index("cell_id"), how="inner")
    sites = sites[sites.util_num.notna()].copy()
    sites["ba"] = sites.util_num.astype(int).map(s2.UTIL_BA)
    subs = load_substations()
    print(f"substations: {len(subs)}; with voltage: {int(subs.kv.notna().sum())}; >=115 kV: {int((subs.kv >= 115).sum())}, >=230: {int((subs.kv >= 230).sum())}, "
          f">=345: {int((subs.kv >= 345).sum())}, >=500: {int((subs.kv >= 500).sum())}")
    sites = sites.join(distances(sites, subs))
    sites[["county_short", "util_name", "ba", "score", "rank", *[f"d{v}_km" for v in VOLTS]]].round(2).sort_values("rank").to_csv(ROOT / "results/stage1_cell_interconnection.csv")
    print("\nDistance from cell centre to the nearest substation of at least V kV (km), over the", len(sites), "cells with a serving utility:")
    print(sites[[f"d{v}_km" for v in VOLTS]].describe(percentiles=[.25, .5, .75]).round(1).to_string())

    uu = util.loc[sorted(set(sites.util_num.astype(int)))]
    E = P * s1.LF * s1.HRS
    caps = {u: s1.n_max(r, tau, s1.DEFAULT["A_max"], E, beta) for u, r in uu.iterrows()}
    el0 = sites[sites.util_num.map(lambda u: caps.get(int(u), 0) > 0)]
    base = s1.run(sites, uu, K, tau, s1.DEFAULT["A_max"], P, beta)[0]
    base_obj = sites.loc[base].score.sum()
    print(f"\nStage 1 default (no interconnection screen): {len(base)} sites, suitability {base_obj:.3f}: {base}")
    print("Default cells vs the screens:", sites.loc[base, [f'd{v}_km' for v in VOLTS]].round(1).to_dict("index"))

    rows = []
    for v in VOLTS:
        for dmax in D_GRID:
            for m in M_GRID:
                s = sites[sites[f"d{v}_km"] <= dmax]
                if s.empty or not any(caps.get(int(u), 0) > 0 for u in s.util_num):
                    ch = []
                else:
                    s = s[s.util_num.map(lambda u: caps.get(int(u), 0) > 0)]
                    ch = solve(s, caps, f"node{v}", m) if len(s) else []
                sel = sites.loc[ch]
                rows.append({"V_min_kv": v, "D_max_km": dmax, "node_cap": "none" if m is None else m, "eligible_cells_all_utilities": int((sites[f"d{v}_km"] <= dmax).sum()),
                             "eligible_cells_utility_can_host": int(len(s)) if len(s) else 0, "n_selected": len(ch), "sum_suitability": sel.score.sum(),
                             "suitability_loss_pct": 100 * (1 - sel.score.sum() / base_obj) if base_obj else np.nan, "mean_rank": sel["rank"].mean() if len(sel) else np.nan,
                             "bas": ";".join(sorted(set(sel.ba.dropna()))), "cells": ";".join(f"{i}({sel.loc[i, 'county_short']},{sel.loc[i, 'util_name'][:18]})" for i in ch)})
    T = pd.DataFrame(rows)
    T.round(3).to_csv(ROOT / "results/stage1_interconnection.csv", index=False)
    pd.set_option("display.width", 240)
    print(f"\nStage 1 under the interconnection screen (P = {P} MW, K = {K}; suitability loss vs the unscreened {base_obj:.2f}):")
    print(T.drop(columns=["cells", "bas"]).round(2).to_string(index=False))

    # does the footprint (carbon/water) matter once interconnection binds?
    ops = s2.ba_operating()
    tw = s2.station_tw()
    st_mean = {k: v.mean() for k, v in tw.items()}
    bm = sites[sites.ba.notna() & sites.baseline_saidi.notna()].copy()
    bm = bm.join(s2.footprint(bm, ops, tw, st_mean, P, s2.F_FLEX, s2.wf.PUE))
    out = []
    for v, dmax, m in ((230, 30, None), (230, 30, 1), (345, 30, None), (345, 15, 1)):
        sub = bm[bm[f"d{v}_km"] <= dmax]
        if sub.empty:
            continue
        sub = sub.copy()
        sub["node"] = sub[f"node{v}"]
        mm = s2.minmax
        foot = {"both": 0.5 * mm(sub.carbon_kt) + 0.5 * mm(sub.water_Mm3), "carbon": mm(sub.carbon_kt), "water": mm(sub.water_Mm3)}
        for kind, f in foot.items():
            for w in (0.0, 0.5, 1.0):
                t = sub.assign(obj=(1 - w) * sub.score + w * (1 - f))
                ucap = {u: caps.get(int(u), 0) for u in t.util_num.unique()}
                t = t[t.util_num.map(lambda u: ucap.get(u, 0) > 0)]
                ch = solve(t, caps, "node", m, score="obj") if len(t) else []
                c = bm.loc[ch]
                out.append({"V_min_kv": v, "D_max_km": dmax, "node_cap": "none" if m is None else m, "footprint": kind, "w": w, "n_selected": len(ch),
                            "sum_suitability": c.score.sum(), "sum_carbon_kt": c.carbon_kt.sum(), "sum_water_Mm3": c.water_Mm3.sum(), "bas": ";".join(sorted(set(c.ba))),
                            "cells": ";".join(ch)})
    C = pd.DataFrame(out)
    C.round(3).to_csv(ROOT / "results/stage1_interconnection_coupling.csv", index=False)
    print("\nCoupled selection on interconnection-eligible cells (BA-mapped utilities only):")
    print(C.drop(columns=["cells"]).round(2).to_string(index=False))

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    for v, c in zip(VOLTS, ("#999", "#1b6ca8", "#edae49", "#d1495b")):
        ax[0].plot(np.sort(sites[f"d{v}_km"]), np.arange(1, len(sites) + 1) / len(sites), color=c, label=f">= {v} kV")
    ax[0].set_xlabel("distance from cell centre to nearest substation (km)"); ax[0].set_ylabel("share of cells within distance"); ax[0].set_xlim(0, 120)
    ax[0].set_title("How close are cells to transmission-voltage substations?", fontsize=10); ax[0].legend(frameon=False); ax[0].grid(alpha=.25)
    g = T[T.node_cap == "none"]
    for v, c in zip(VOLTS, ("#999", "#1b6ca8", "#edae49", "#d1495b")):
        s = g[g.V_min_kv == v].sort_values("D_max_km")
        ax[1].plot(s.D_max_km, s.sum_suitability, marker="o", color=c, label=f">= {v} kV")
    ax[1].axhline(base_obj, color="#222", ls=":", lw=1); ax[1].text(15.5, base_obj + 0.02, "no screen", fontsize=8)
    ax[1].set_xlabel("maximum distance to a qualifying substation, D_max (km)"); ax[1].set_ylabel("suitability of selected sites (K = 3, 500 MW)")
    ax[1].set_title("Price of the interconnection screen", fontsize=10); ax[1].legend(frameon=False, fontsize=8); ax[1].grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/stage1_interconnection.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
