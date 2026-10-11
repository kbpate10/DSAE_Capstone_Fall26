"""Stage 1 (siting) optimizer: choose sites that maximise suitability under a reliability guardrail.

    maximise   sum_i score_i * x_i
    subject to sum_i x_i <= K                                  (site budget)
               sum_{i in u} x_i <= n_max(u; tau_R, A_max, P)   (per serving utility)
               x_i in {0, 1}

Everything below is an input assumption unless it comes from a file; each is a parameter.
  score_i      environmental suitability from rq2_siting.py (default weights; weights sampled for stability).
  serving u(i) dominant retail utility of the cell from service-territory polygons (two mappings: 'all'
               utilities, and 'large' = >= 500 GWh sales only, because HIFLD uses generic polygons for small districts).
  project      P MW at load factor 0.8 -> E = P * 0.8 * 8760 MWh/yr.
  reliability  baseline_u = median 2021-2024 SAIDI without major events (fallback: with-MED / 1.44, flagged).
               Projected SAIDI after n projects = baseline_u * (1 + n * E / CI_u) ** beta, where CI_u is the utility's
               2024 commercial+industrial sales and beta is the UPPER 95% bound of the fixed-effects elasticity (RQ3),
               i.e. a deliberately conservative reading of an evidence base whose point estimate is ~0.
  guardrail    projected SAIDI <= tau_R minutes (default: median SAIDI across US utilities).
  support      n * E / CI_u <= A_max (default 25%): the RQ3 evidence only covers load changes of roughly that size,
               so larger additions are treated as unsupported (ineligible), not as safe.
The per-utility cap n_max is the largest n satisfying both the guardrail and the support limit.

Outputs: results/stage1_*.csv, results/figures/stage1_*.png
"""
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pulp

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rq2_siting as r2

LF, HRS = 0.8, 8760
DEFAULT = dict(P=500, A_max=0.25, K=5, tau=None)


def utility_table() -> pd.DataFrame:
    p = pd.read_parquet(ROOT / "data/processed/eia861_panel.parquet")
    p = p[(p.state == "AZ") & (p.year >= 2021)].copy()
    valid = (p.saidi_nomed >= 1) & (p.saidi_nomed <= p.saidi_med * 1.001)
    p["saidi_use"] = np.where(valid, p.saidi_nomed, p.saidi_med / 1.44)
    p["fallback"] = ~valid & p.saidi_med.notna()
    base = p.groupby("util_num").agg(baseline_saidi=("saidi_use", "median"), used_fallback=("fallback", "mean"),
                                     n_years=("saidi_use", lambda s: s.notna().sum()))
    last = p[p.year == p.year.max()].copy()
    last["ci_mwh"] = last.com_mwh + last.ind_mwh
    ci = last.groupby("util_num").agg(ci_mwh=("ci_mwh", "sum"), customers=("total_cust", "sum"))
    t = base.join(ci, how="outer")
    t.index = t.index.astype(int)
    return t


def national_median_saidi() -> float:
    u = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet")
    u = u[u.year >= 2021]
    return float(u.saidi_nomed.median())


def beta_upper() -> float:
    r = pd.read_csv(ROOT / "results/rq3_results.csv")
    return float(r[r.spec.str.startswith("S2")].query("outcome == 'ln_saidi_nomed'").d_ln_ci_pc_hi.iloc[0])


def assign(tag: str, util: pd.DataFrame) -> pd.DataFrame:
    S = pd.read_parquet(ROOT / f"data/processed/cell_utility_shares_{tag}.parquet")
    S = S[S.util_num.notna()].sort_values(["cell_id", "area_share"], ascending=[True, False])
    top = S.groupby("cell_id").head(1)[["cell_id", "util_num", "util_name", "area_share"]].copy()
    top["util_num"] = top.util_num.astype(int)
    return top.merge(util, left_on="util_num", right_index=True, how="left")


def n_max(row, tau, A_max, E, beta):
    if not np.isfinite(row.baseline_saidi) or not np.isfinite(row.ci_mwh) or row.ci_mwh <= 0:
        return 0
    a = E / row.ci_mwh
    n_support = int(np.floor(A_max / a + 1e-9))
    if tau <= row.baseline_saidi:
        return 0
    n_risk = int(np.floor(((tau / row.baseline_saidi) ** (1.0 / beta) - 1.0) / a + 1e-9))
    return max(0, min(n_support, n_risk))


def solve(sites: pd.DataFrame, K: int, caps: dict, score_col="score"):
    prob = pulp.LpProblem("stage1", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{k}", cat="Binary") for k, i in enumerate(sites.index)}
    prob += pulp.lpSum(sites.loc[i, score_col] * x[i] for i in x)
    prob += pulp.lpSum(x.values()) <= K
    for u, idx in sites.groupby("util_num").groups.items():
        prob += pulp.lpSum(x[i] for i in idx) <= caps.get(u, 0)
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    chosen = [i for i in x if x[i].value() and x[i].value() > 0.5]
    return chosen, float(sum(sites.loc[i, score_col] for i in chosen))


def run(sites, util_caps_fn, K, tau, A_max, P, beta, score_col="score"):
    E = P * LF * HRS
    caps = {u: n_max(r, tau, A_max, E, beta) for u, r in util_caps_fn.iterrows()}
    s = sites[sites.util_num.map(lambda u: caps.get(u, 0) > 0)]
    if s.empty:
        return [], 0.0, caps
    chosen, obj = solve(s, K, caps, score_col)
    return chosen, obj, caps


def main() -> None:
    cells = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    util = utility_table()
    tau0 = national_median_saidi()
    beta = beta_upper()
    print(f"national median SAIDI (no MED, 2021+): {tau0:.0f} min | beta (upper 95% elasticity, RQ3 main spec): {beta:.3f}")
    out = []
    res_default = {}
    for tag in ("all", "large"):
        a = assign(tag, util).set_index("cell_id")
        sites = cells.join(a, how="inner")
        sites = sites[sites.util_num.notna()]
        uu = util.loc[sorted(set(sites.util_num.astype(int)))]
        K, A, P = DEFAULT["K"], DEFAULT["A_max"], DEFAULT["P"]
        print(f"\n===== mapping '{tag}': {len(sites)} scored cells with a serving utility "
              f"({int(sites.baseline_saidi.notna().sum())} with reliability data) =====")
        # unconstrained benchmark
        unc = cells.sort_values("score", ascending=False).head(K)
        chosen, obj, caps = run(sites, uu, K, tau0, A, P, beta)
        print(f"Default scenario: P={P} MW, K={K}, tau_R={tau0:.0f} min, A_max={A:.0%}")
        capsdf = uu.assign(n_max=pd.Series(caps)).round(1)
        print(capsdf[["baseline_saidi", "ci_mwh", "n_max"]].sort_values("n_max", ascending=False).head(10).to_string())
        sel = sites.loc[chosen].sort_values("score", ascending=False)
        print("Selected:")
        print(sel[["county_short", "util_name", "score", "rank", "baseline_saidi"]].round(2).to_string())
        print(f"objective {obj:.2f} vs unconstrained top-{K} {unc.score.sum():.2f} "
              f"(guardrail cost {100*(1-obj/unc.score.sum()):.1f}%)")
        print("unconstrained top-K cells that are reliability-eligible:",
              int(sum(i in sel.index for i in unc.index)), "of", K)
        res_default[tag] = sel.assign(mapping=tag)

        # frontier: tau x A_max for several K and P
        for P_ in (100, 250, 500, 1000):
            for A_ in (0.10, 0.25, 0.50):
                for tau in (60, 80, 100, 120, 150, 200, 300):
                    for K_ in (1, 3, 5, 10):
                        ch, ob, cp = run(sites, uu, K_, tau, A_, P_, beta)
                        out.append({"mapping": tag, "P_MW": P_, "A_max": A_, "tau_R": tau, "K": K_,
                                    "n_selected": len(ch), "objective": ob,
                                    "mean_score": ob / len(ch) if ch else np.nan})
    F = pd.DataFrame(out)
    F.to_csv(ROOT / "results/stage1_frontier.csv", index=False)
    pd.concat(res_default.values()).reset_index().to_csv(ROOT / "results/stage1_selection_default.csv", index=False)

    # ---- selection stability across random weights (default scenario)
    rng = np.random.default_rng(0)
    freq = {}
    for tag in ("all", "large"):
        a = assign(tag, util).set_index("cell_id")
        base_sites = cells.join(a, how="inner")
        base_sites = base_sites[base_sites.util_num.notna()]
        uu = util.loc[sorted(set(base_sites.util_num.astype(int)))]
        cnt = pd.Series(0, index=base_sites.index, dtype=float)
        N = 300
        for _ in range(N):
            w = dict(zip(r2.CRIT, rng.dirichlet(np.ones(len(r2.CRIT)))))
            sc, _ = r2.score(cells.reset_index(), w)
            tmp = base_sites.copy()
            tmp["score_w"] = pd.Series(sc, index=cells.index).loc[tmp.index].values
            ch, _, _ = run(tmp, uu, DEFAULT["K"], tau0, DEFAULT["A_max"], DEFAULT["P"], beta, "score_w")
            cnt.loc[ch] += 1
        freq[tag] = cnt / N
    sf = pd.DataFrame(freq).fillna(0)
    sf = sf.join(cells[["county_short", "score", "rank"]])
    sf.sort_values("all", ascending=False).head(25).to_csv(ROOT / "results/stage1_selection_frequency.csv")
    print("\nSelection frequency across 300 random weight vectors (default scenario), top cells:")
    print(sf.sort_values("all", ascending=False).head(10).round(2).to_string())

    # ---- headline frontier summary (K=5, P=500)
    h = F[(F.P_MW == 500) & (F.K == 5) & (F.mapping == "all")]
    print("\nObjective (sum of scores, K=5, P=500 MW, mapping 'all') by tau_R and A_max:")
    print(h.pivot(index="tau_R", columns="A_max", values="n_selected").to_string())
    print(h.pivot(index="tau_R", columns="A_max", values="objective").round(2).to_string())

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    ax = axes[0]
    for A_, c in zip((0.10, 0.25, 0.50), ("#d1495b", "#1b6ca8", "#2a9d8f")):
        g = F[(F.mapping == "all") & (F.P_MW == 500) & (F.K == 5) & (F.A_max == A_)].sort_values("tau_R")
        ax.plot(g.tau_R, g.objective, marker="o", color=c, label=f"A_max {A_:.0%}")
    ax.set_xlabel("reliability guardrail tau_R (SAIDI minutes per year)"); ax.set_ylabel("total suitability of selected sites (K = 5)")
    ax.set_title("500 MW projects: value of the selection vs guardrail", fontsize=10); ax.legend(frameon=False); ax.grid(alpha=.25)
    ax = axes[1]
    for P_, c in zip((100, 250, 500, 1000), ("#2a9d8f", "#1b6ca8", "#edae49", "#d1495b")):
        g = F[(F.mapping == "all") & (F.P_MW == P_) & (F.K == 5) & (F.A_max == 0.25)].sort_values("tau_R")
        ax.plot(g.tau_R, g.n_selected, marker="o", color=c, label=f"{P_} MW")
    ax.set_xlabel("reliability guardrail tau_R (SAIDI minutes per year)"); ax.set_ylabel("sites that can be selected (K = 5)")
    ax.set_title("How many sites survive, by project size (A_max 25%)", fontsize=10); ax.legend(frameon=False); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/stage1_frontier.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
