"""Midpoint-1 figures, built only from files in results/ and data/processed/ (no re-modelling)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results/figures"
BLUE, RED, GOLD, GREY, TEAL = "#1b6ca8", "#d1495b", "#edae49", "#8a8a8a", "#2a9d8f"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def fig_forecast():
    r = pd.read_csv(ROOT / "results/forecast_nn_metrics.csv")
    models = [("persist", "Persistence", GREY), ("resid_lags", "LightGBM (residual)", BLUE), ("nn", "Neural net (TCN)", TEAL)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    bas = ["AZPS", "SRP", "TEPC", "WALC"]
    for ax, h, title in zip(axes, [1, 24], ["1 hour ahead", "24 hours ahead (day-ahead)"]):
        t = r[r.horizon_h == h].pivot(index="ba", columns="model", values="MAE").loc[bas]
        x = np.arange(len(bas)); w = 0.26
        for i, (m, lab, c) in enumerate(models):
            ax.bar(x + (i - 1) * w, t[m], w, color=c, label=lab)
        for j, ba in enumerate(bas):
            best = t.loc[ba, "nn"]; base = t.loc[ba, "persist"]
            ax.text(j + w, best + 0.6, f"{100*(1-best/base):+.0f}%", ha="center", fontsize=8, color=TEAL)
        ax.set_xticks(x); ax.set_xticklabels(bas); ax.set_title(title, fontsize=11)
        ax.set_ylabel("MAE, kg CO$_2$/MWh (2025 test)"); ax.grid(axis="y", alpha=.25)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Grid carbon-intensity forecasts vs persistence (labels: neural net's gain over persistence)", fontsize=11)
    fig.tight_layout(); fig.savefig(FIG / "m1_forecast_vs_baselines.png", dpi=160); plt.close(fig)


def fig_schedule():
    s = pd.read_csv(ROOT / "results/schedule_savings.csv")
    s = s[(s.job == "preemptible") & (s.k == 8)].set_index("ba")
    bas = ["AZPS", "SRP", "TEPC", "WALC"]
    pols = [("random", "Random timing", GREY), ("persist", "Persistence forecast", BLUE),
            ("resid_lags", "LightGBM forecast", TEAL), ("oracle", "Perfect foresight (bound)", GOLD)]
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    x = np.arange(len(bas)); w = 0.2
    for i, (m, lab, c) in enumerate(pols):
        ax.bar(x + (i - 1.5) * w, s.loc[bas, m], w, color=c, label=lab)
    ax.set_xticks(x); ax.set_xticklabels(bas)
    ax.set_ylabel("carbon saved vs running immediately (%)"); ax.grid(axis="y", alpha=.25)
    ax.set_title("Carbon-aware scheduling of an 8-hour flexible job, 2025 (carbon only)", fontsize=11)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "m1_scheduling_savings.png", dpi=160); plt.close(fig)


def fig_rq3():
    r = pd.read_csv(ROOT / "results/rq3_results.csv")
    r = r[(r.outcome == "ln_saidi_nomed") & r.d_ln_ci_pc_coef.notna()].copy()
    k = np.log(1.10) * 100   # elasticity -> % change in SAIDI for +10% C&I load per customer
    pct = lambda b: (np.exp(b * np.log(1.10)) - 1) * 100
    rows = [(f"{s}", pct(c), pct(lo), pct(hi)) for s, c, lo, hi in
            zip(r.spec, r.d_ln_ci_pc_coef, r.d_ln_ci_pc_lo, r.d_ln_ci_pc_hi) if "Arizona" not in s]
    import arviz as az
    idata = az.from_netcdf(ROOT / "data/processed/bayes_full_trace.nc")  # unrounded posterior samples
    pan = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet").dropna(subset=["ln_saidi_nomed", "d_ln_ci_pc", "d_ln_cust"])
    sx = pan.d_ln_ci_pc.std()
    mb = idata.posterior["mu_b"].values.ravel() / sx * 0.10 * 100
    m, lo, hi = mb.mean(), np.percentile(mb, 2.5), np.percentile(mb, 97.5)
    rows.append(("Bayesian hierarchical (PyMC)", m, lo, hi))
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    for i, (lab, c, l, h) in enumerate(rows[::-1]):
        col = TEAL if "Bayes" in lab else BLUE
        ax.plot([l, h], [i, i], color=col, lw=2.4); ax.plot(c, i, "o", color=col)
    ax.axvline(0, color="k", lw=.8)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([x[0] for x in rows[::-1]], fontsize=9)
    ax.set_xlabel("change in SAIDI (no major events) per +10% C&I load per customer\n(%, 95% interval; Arizona-only fit omitted: 14 utilities, too wide)")
    ax.set_title("RQ3: no detectable reliability effect of load growth (null result, honestly bounded)", fontsize=11)
    ax.set_xlim(-6, 6); ax.grid(axis="x", alpha=.25)
    fig.tight_layout(); fig.savefig(FIG / "m1_rq3_reliability_effect.png", dpi=160); plt.close(fig)
    return rows


def fig_siting():
    s = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet")
    osm = pd.read_parquet(ROOT / "data/raw/rq2/osm_datacenters_az.parquet")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    sc = ax.scatter(s.lon, s.lat, c=s.score, cmap="viridis", s=95, marker="s", edgecolor="white", lw=.4)
    ax.scatter(osm.lon, osm.lat, s=14, c=RED, edgecolor="white", lw=.3, label="mapped data centers (OpenStreetMap)", zorder=3)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    plt.colorbar(sc, ax=ax, label="environmental suitability score", shrink=.8)
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude"); ax.set_aspect(1.2)
    ax.set_title("Candidate cells (0.25 deg) scored on water, heat, solar, grid strain", fontsize=10)
    ax = axes[1]
    c = s.groupby("county_short").score.agg(["mean", "min", "max", "size"]).sort_values("mean")
    ax.barh(c.index, c["mean"], color=BLUE)
    ax.errorbar(c["mean"], range(len(c)), xerr=[c["mean"] - c["min"], c["max"] - c["mean"]], fmt="none", ecolor=GREY, lw=1)
    ax.set_xlabel("mean score (bar) and range across cells"); ax.grid(axis="x", alpha=.25)
    ax.set_title("By county", fontsize=10)
    fig.suptitle("RQ2: transparent siting score. Mapped data centers sit in low-scoring cells. Constructed label, not ground truth.", fontsize=10.5)
    fig.tight_layout(); fig.savefig(FIG / "m1_siting_score.png", dpi=160); plt.close(fig)


def fig_ladder():
    r = pd.read_csv(ROOT / "results/rq3_baseline_ladder.csv")
    r = r[r.kind == "exposure"].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    n = len(r)
    for i, row in r.iterrows():
        y = n - 1 - i
        col = RED if row.rung.startswith(("U", "C")) else BLUE
        ax.plot([row.lo, row.hi], [y, y], color=col, lw=2.4); ax.plot(row["pct_change"], y, "o", color=col)
        ax.text(row.hi + 0.3, y, f'{row["pct_change"]:+.1f}%', va="center", fontsize=8.5, color=col)
    ax.axvline(0, color="k", lw=.8)
    ax.set_yticks(range(n)); ax.set_yticklabels([x.split("  ", 1)[0] + "  " + x.split("  ", 1)[1].strip() for x in r.rung][::-1], fontsize=8.5)
    ax.set_xlabel("change in SAIDI (no major events) per +10% C&I load per customer (%, 95% interval)")
    ax.set_title("Naive comparison suggests harm; controls remove it. Why fixed effects are needed.", fontsize=10.5)
    ax.grid(axis="x", alpha=.25); ax.set_xlim(-4, 15)
    fig.tight_layout(); fig.savefig(FIG / "m1_rq3_baseline_ladder.png", dpi=160); plt.close(fig)


if __name__ == "__main__":
    fig_forecast(); fig_schedule(); rows = fig_rq3(); fig_siting(); fig_ladder()
    print("figures done"); [print(f"{l:34s} {c:+.2f}% [{lo:+.2f}, {hi:+.2f}]") for l, c, lo, hi in rows]
