"""End-to-end decision framework: Stage 1 (siting under a reliability guardrail) feeding Stage 2 (carbon/water scheduling).

Stage 1: stage1_optimizer.run() with its default assumptions (500 MW projects, load factor 0.8, A_max 25%, beta = upper 95%
RQ3 elasticity, site budget K = 3, utility-territory mapping 'all'), swept over the reliability guardrail tau_R and project size.
Every selected cell is mapped to the balancing authority of its serving utility (APS -> AZPS, SRP -> SRP, TEP -> TEPC; other
utilities have no operating data here and are reported as "no Stage 2 data").

Stage 2: for the BA of each selected site, the deployable scheduling policies from water_frontier_by_ba.csv (8 h preemptible job
inside a 24 h window, 2025 days, decision on yesterday's same-hour values) against the baselines of the context document:
  naive        run immediately at local midnight (0% by construction)
  carbon-only  alpha = 1   (minimise carbon)
  balanced     alpha = 0.5 (equal weight on carbon and water, each normalised by its 2021-2024 mean)
  water-only   alpha = 0
  oracle       balanced weights with realised values: a non-deployable upper bound
alpha is a named assumption, not a fitted value: the full alpha sweep is plotted so the choice can be judged.
Savings are % vs run-immediately, on actual (production-based) intensities; water is a scenario estimate.

Outputs: results/framework_stage1_sweep.csv, results/framework_stage2_policies.csv, results/framework_scenario_default.csv,
         results/figures/framework_endtoend.png
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
from stage2_coupling import UTIL_BA

TAUS = (60, 80, 100, 120, 150, 200, 300)
SIZES = (100, 250, 500)
K_SITES = 3
POLICIES = {"carbon-only": (1.0, "persist"), "balanced": (0.5, "persist"), "water-only": (0.0, "persist"),
            "oracle (balanced, not deployable)": (0.5, "oracle")}


def stage2_policies() -> pd.DataFrame:
    f = pd.read_csv(ROOT / "results/water_frontier_by_ba.csv")
    f = f[(f.job == "preemptible") & (f.k == 8)]
    rows = [{"ba": ba, "policy": "naive (run immediately)", "alpha": np.nan, "carbon_saved_pct": 0.0, "water_saved_pct": 0.0,
             "days": int(f[f.ba == ba].days.max())} for ba in f.ba.unique()]
    for name, (a, mode) in POLICIES.items():
        g = f[(f.alpha == a) & (f["mode"] == mode)]
        for _, r in g.iterrows():
            rows.append({"ba": r.ba, "policy": name, "alpha": a, "carbon_saved_pct": r.carbon_saved_vs_immediate_pct,
                         "water_saved_pct": r.water_saved_vs_immediate_pct, "days": int(r.days)})
    return pd.DataFrame(rows)


def main() -> None:
    cells = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    util = s1.utility_table()
    tau0, beta = s1.national_median_saidi(), s1.beta_upper()
    sites = cells.join(s1.assign("all", util).set_index("cell_id"), how="inner")
    sites = sites[sites.util_num.notna()].copy()
    sites["ba"] = sites.util_num.astype(int).map(UTIL_BA)
    uu = util.loc[sorted(set(sites.util_num.astype(int)))]
    pol = stage2_policies()
    pol.round(2).to_csv(ROOT / "results/framework_stage2_policies.csv", index=False)

    rows = []
    for P in SIZES:
        for tau in TAUS:
            ch, obj, _ = s1.run(sites, uu, K_SITES, tau, s1.DEFAULT["A_max"], P, beta)
            sel = sites.loc[ch]
            cov = sel[sel.ba.notna()]
            bal = pol[(pol.policy == "balanced") & pol.ba.isin(cov.ba)]
            per_site = cov.ba.map(bal.set_index("ba").carbon_saved_pct) if len(cov) else pd.Series(dtype=float)
            per_site_w = cov.ba.map(bal.set_index("ba").water_saved_pct) if len(cov) else pd.Series(dtype=float)
            rows.append({"P_MW": P, "tau_R": tau, "n_sites": len(ch), "sum_suitability": obj,
                         "mean_rank": sel["rank"].mean() if len(sel) else np.nan,
                         "sites": ";".join(f"{i}({sel.loc[i, 'county_short']},{sel.loc[i, 'util_name']})" for i in ch),
                         "sites_with_stage2_data": len(cov),
                         "balanced_carbon_saved_pct_mean": per_site.mean() if len(cov) else np.nan,
                         "balanced_water_saved_pct_mean": per_site_w.mean() if len(cov) else np.nan})
    S = pd.DataFrame(rows)
    S.round(3).to_csv(ROOT / "results/framework_stage1_sweep.csv", index=False)
    pd.set_option("display.width", 220)
    print(f"Stage 1 reliability-tolerance sweep (K = {K_SITES}, A_max {s1.DEFAULT['A_max']:.0%}, beta {beta:.3f}); national median SAIDI {tau0:.0f} min")
    print(S.drop(columns="sites").round(2).to_string(index=False))

    # default scenario end to end
    P0 = 500
    ch, obj, _ = s1.run(sites, uu, K_SITES, tau0, s1.DEFAULT["A_max"], P0, beta)
    sel = sites.loc[ch]
    fp = pd.read_csv(ROOT / "results/stage2_cell_footprint.csv").set_index("cell_id")
    rec = []
    for cid, r in sel.iterrows():
        for _, q in pol[pol.ba == r.ba].iterrows():
            rec.append({"cell_id": cid, "county": r.county_short, "utility": r.util_name, "ba": r.ba, "suitability": r.score, "rank": int(r["rank"]),
                        "baseline_saidi_min": r.baseline_saidi,
                        "carbon_kt_yr_500MW_30pct_flexible": fp.carbon_kt.get(cid, np.nan),
                        "water_Mm3_yr_500MW": fp.water_Mm3.get(cid, np.nan),
                        "policy": q.policy, "carbon_saved_pct": q.carbon_saved_pct, "water_saved_pct": q.water_saved_pct})
    D = pd.DataFrame(rec)
    D.round(2).to_csv(ROOT / "results/framework_scenario_default.csv", index=False)
    print(f"\nDefault scenario: P = {P0} MW, K = {K_SITES}, tau_R = {tau0:.0f} min")
    print(sel[["county_short", "util_name", "ba", "score", "rank", "baseline_saidi"]].round(2).to_string())
    print(D.pivot_table(index=["ba", "policy"], values=["carbon_saved_pct", "water_saved_pct"]).round(1).to_string())

    f = pd.read_csv(ROOT / "results/water_frontier_by_ba.csv")
    f = f[(f.job == "preemptible") & (f.k == 8) & (f["mode"] == "persist")]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    for P, c in zip(SIZES, ("#2a9d8f", "#1b6ca8", "#d1495b")):
        g = S[S.P_MW == P].sort_values("tau_R")
        ax[0].plot(g.tau_R, g.n_sites, marker="o", color=c, label=f"{P} MW")
    ax[0].axvline(tau0, color="#888", ls=":", lw=1)
    ax[0].set_xlabel("reliability guardrail tau_R (SAIDI minutes per year)"); ax[0].set_ylabel(f"sites selected (budget K = {K_SITES})")
    ax[0].set_title("Stage 1: how many sites survive the guardrail", fontsize=10); ax[0].legend(frameon=False); ax[0].grid(alpha=.25)
    for ba, c in zip(sorted(set(sel.ba.dropna())), ("#1b6ca8", "#edae49", "#2a9d8f")):
        g = f[f.ba == ba].sort_values("alpha")
        ax[1].plot(g.water_saved_vs_immediate_pct, g.carbon_saved_vs_immediate_pct, marker="o", ms=4, color=c, label=f"{ba} (selected site)")
        for a, lab in ((0.0, "water-only"), (0.5, "balanced"), (1.0, "carbon-only")):
            r = g[g.alpha == a].iloc[0]
            ax[1].annotate(lab, (r.water_saved_vs_immediate_pct, r.carbon_saved_vs_immediate_pct), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax[1].axhline(0, color="#999", lw=.8); ax[1].axvline(0, color="#999", lw=.8)
    ax[1].set_xlabel("water saved vs run-immediately (%)"); ax[1].set_ylabel("carbon saved vs run-immediately (%)")
    ax[1].set_title("Stage 2: carbon-water frontier at the selected sites (deployable, 2025)", fontsize=10)
    ax[1].legend(frameon=False, fontsize=8); ax[1].grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/framework_endtoend.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
