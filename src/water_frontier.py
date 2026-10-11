"""Carbon-vs-water tradeoff for flexible workloads in Arizona.

Water per kWh of IT energy (L/kWh), scenario estimates (NOT measured):
  on-site cooling  W_on(Tw)  = WUE_MAX * clip((Tw - TW_LO)/(TW_HI - TW_LO), 0, 1)
      evaporative share of heat rejection rises with wet-bulb temperature Tw (economiser at low Tw).
      WUE_MAX = 1.85 L/kWh ~ latent heat of evaporation x 5 cycles of concentration (physics-based).
  off-site (generation) W_off = PUE * sum_f(gen_f * wf_f)/sum_f(gen_f), operational consumption factors
      (approximate literature medians, e.g. Macknick et al. 2012; VERIFY before publishing):
      coal 2.60, gas 0.75, nuclear 2.54, oil 1.9, solar PV 0.10, wind 0, other 0.75, hydro 0 (base)
      hydro reservoir evaporation is contested -> 'hydro17' sensitivity sets hydro = 17 L/kWh.
Carbon per kWh of IT energy: PUE * average carbon intensity (kg/MWh -> kg/kWh = /1000).
Constant PUE = 1.2.

Frontier: for each BA-day (2025) a k-hour job picks hours minimising  a*C/Cbar + (1-a)*W/Wbar.
Decision uses (i) oracle values and (ii) persistence (yesterday's same hour); results are scored on actuals.
Savings are vs 'random timing' (window mean) and vs 'run immediately at local midnight'.
Outputs: results/water_*.csv, results/figures/*.png
"""
import glob
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
PUE, WUE_MAX, TW_LO, TW_HI = 1.2, 1.85, 4.0, 20.0
WF = {"COL": 2.60, "NG": 0.75, "NUC": 2.54, "OIL": 1.9, "SUN": 0.10, "WND": 0.0, "OTH": 0.75, "WAT": 0.0}
SITE = {"AZPS": "PHX", "SRP": "PHX", "TEPC": "TUS", "WALC": "HAV"}
BAS = ["AZPS", "SRP", "TEPC", "WALC"]
ALPHAS = np.round(np.linspace(0, 1, 11), 2)
KS = [4, 8, 12]


def build(wf=WF, wuemax=WUE_MAX) -> pd.DataFrame:
    ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet")
    raw = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930/*.parquet")))
    raw = raw[raw.fueltype.isin(wf)].copy()
    raw["ts"] = pd.to_datetime(raw.period, format="%Y-%m-%dT%H")
    raw["gen"] = raw.value.clip(lower=0)
    raw["w"] = raw.gen * raw.fueltype.map(wf)
    mix = raw.groupby(["respondent", "ts"]).agg(w=("w", "sum"), g=("gen", "sum")).reset_index()
    mix["w_off_per_kwh_grid"] = mix.w / mix.g.where(mix.g > 0)
    d = ci.merge(mix[["respondent", "ts", "w_off_per_kwh_grid"]], on=["respondent", "ts"], how="left")
    out = []
    for ba in BAS:
        wx = pd.read_parquet(ROOT / f"data/raw/weather/nasa_hourly_{SITE[ba]}.parquet")
        wx["ts"] = wx.ts_local + pd.Timedelta(hours=7)          # LST (UTC-7) -> UTC
        g = d[d.respondent == ba].merge(wx[["ts", "T2MWET", "T2M"]], on="ts", how="left")
        out.append(g)
    d = pd.concat(out, ignore_index=True)
    d["local"] = d.ts - pd.Timedelta(hours=7)
    d["C"] = PUE * d.ci_kg_per_mwh / 1000.0                       # kg CO2 per kWh IT
    d["W_on"] = wuemax * ((d.T2MWET - TW_LO) / (TW_HI - TW_LO)).clip(0, 1)
    d["W_off"] = PUE * d.w_off_per_kwh_grid
    d["W"] = d.W_on + d.W_off
    d.loc[d.data_flag.fillna(True).astype(bool), ["C", "W", "W_off", "W_on"]] = np.nan
    return d


def describe(d):
    t = d[d.local.dt.year >= 2021]
    rows = []
    for ba, g in t.groupby("respondent"):
        gg = g.dropna(subset=["C", "W"])
        dm = gg.assign(day=gg.local.dt.floor("D"))
        dm["Cd"] = dm.C - dm.groupby("day").C.transform("mean")
        dm["Wd"] = dm.W - dm.groupby("day").W.transform("mean")
        dm["Wond"] = dm.W_on - dm.groupby("day").W_on.transform("mean")
        dm["Woffd"] = dm.W_off - dm.groupby("day").W_off.transform("mean")
        rows.append({"ba": ba, "C_kg_per_kWh": gg.C.mean(), "W_on_L_per_kWh": gg.W_on.mean(),
                     "W_off_L_per_kWh": gg.W_off.mean(), "W_total": gg.W.mean(),
                     "corr_C_W_hourly": gg.C.corr(gg.W),
                     "within_day_corr_C_W": dm.Cd.corr(dm.Wd),
                     "within_day_corr_C_Won": dm.Cd.corr(dm.Wond),
                     "within_day_corr_C_Woff": dm.Cd.corr(dm.Woffd)})
    return pd.DataFrame(rows)


def window_pick(cost, k, contiguous):
    if contiguous:
        s = int(np.argmin(np.convolve(cost, np.ones(k), mode="valid")))
        return np.arange(s, s + k)
    return np.argsort(cost, kind="stable")[:k]


def frontier(d, year=2025, hydro_note="", multi_site=False):
    base = d[(d.local.dt.year >= 2021) & (d.local.dt.year <= 2024)]
    Cbar = base.groupby("respondent").C.mean()
    Wbar = base.groupby("respondent").W.mean()
    cb, wb = Cbar.mean(), Wbar.mean()  # common normalisers so cross-BA comparison is meaningful
    d = d.sort_values(["respondent", "ts"]).copy()
    d["C_p"] = d.groupby("respondent").C.shift(24)
    d["W_p"] = d.groupby("respondent").W.shift(24)
    t = d[d.local.dt.year == year].copy()
    t["day"] = t.local.dt.floor("D")
    t["hr"] = t.local.dt.hour
    rows = []
    groups = [(ba, g) for ba, g in t.groupby("respondent")] if not multi_site else None
    if multi_site:
        piv = {v: t.pivot_table(index=["day", "hr"], columns="respondent", values=v) for v in ["C", "W", "C_p", "W_p"]}
        days = sorted(set(piv["C"].index.get_level_values(0)))
        for day in days:
            try:
                M = {v: piv[v].loc[day].reindex(range(24)) for v in piv}
            except KeyError:
                continue
            if any(M[v].isna().any().any() for v in M):
                continue
            for k in KS:
                for contiguous in (False,):
                    for a in ALPHAS:
                        for mode in ("oracle", "persist"):
                            cC, cW = (M["C"], M["W"]) if mode == "oracle" else (M["C_p"], M["W_p"])
                            cost = (a * cC / cb + (1 - a) * cW / wb).values.ravel()   # (24*nBA)
                            pick = np.argsort(cost, kind="stable")[:k]
                            rows.append({"ba": "multi", "day": day, "k": k, "job": "preemptible", "alpha": a,
                                         "mode": mode, "C": M["C"].values.ravel()[pick].sum(),
                                         "W": M["W"].values.ravel()[pick].sum(),
                                         "C_rand": M["C"].values.mean() * k, "W_rand": M["W"].values.mean() * k,
                                         "C_imm": M["C"].iloc[:k].mean(axis=1).sum(), "W_imm": M["W"].iloc[:k].mean(axis=1).sum()})
        return pd.DataFrame(rows)
    for ba, g in groups:
        for day, w in g.groupby("day"):
            w = w.set_index("hr").reindex(range(24))
            need = ["C", "W", "C_p", "W_p"]
            if w[need].isna().any().any():
                continue
            for k in KS:
                for job, contiguous in (("preemptible", False), ("contiguous", True)):
                    for a in ALPHAS:
                        for mode in ("oracle", "persist"):
                            cC, cW = (w.C, w.W) if mode == "oracle" else (w.C_p, w.W_p)
                            cost = (a * cC / cb + (1 - a) * cW / wb).values
                            pick = window_pick(cost, k, contiguous)
                            rows.append({"ba": ba, "day": day, "k": k, "job": job, "alpha": a, "mode": mode,
                                         "C": w.C.values[pick].sum(), "W": w.W.values[pick].sum(),
                                         "C_rand": w.C.mean() * k, "W_rand": w.W.mean() * k,
                                         "C_imm": w.C.values[:k].sum(), "W_imm": w.W.values[:k].sum()})
    return pd.DataFrame(rows)


def summarize(F, by=("job", "k", "mode", "alpha")):
    g = F.groupby(list(by)).agg(C=("C", "sum"), W=("W", "sum"), Cr=("C_rand", "sum"), Wr=("W_rand", "sum"),
                                Ci=("C_imm", "sum"), Wi=("W_imm", "sum"), days=("day", "nunique")).reset_index()
    g["carbon_saved_vs_random_pct"] = 100 * (1 - g.C / g.Cr)
    g["water_saved_vs_random_pct"] = 100 * (1 - g.W / g.Wr)
    g["carbon_saved_vs_immediate_pct"] = 100 * (1 - g.C / g.Ci)
    g["water_saved_vs_immediate_pct"] = 100 * (1 - g.W / g.Wi)
    return g


def main() -> None:
    d = build()
    D = describe(d)
    D.to_csv(ROOT / "results/water_descriptives.csv", index=False)
    pd.set_option("display.width", 220)
    print("=== Mean per kWh of IT energy, 2021-2025 (scenario estimates) ===")
    print(D.round(3).to_string(index=False))

    # diurnal profiles by season
    d["month"] = d.local.dt.month
    d["hr"] = d.local.dt.hour
    prof = {}
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for j, (name, months) in enumerate([("Summer (Jun-Aug)", [6, 7, 8]), ("Winter (Dec-Feb)", [12, 1, 2])]):
        for i, ba in enumerate(["AZPS", "SRP"]):
            g = d[(d.respondent == ba) & d.month.isin(months)].groupby("hr")[["C", "W_on", "W_off", "W"]].mean()
            prof[(ba, name)] = g
            ax = axes[i, j]
            ax.plot(g.index, g.C / g.C.mean(), color="#1b6ca8", lw=2.2, label="Carbon")
            ax.plot(g.index, g.W / g.W.mean(), color="#d1495b", lw=2.2, label="Water (total)")
            ax.plot(g.index, g.W_on / g.W.mean(), color="#d1495b", lw=1.2, ls="--", label="  on-site cooling")
            ax.plot(g.index, g.W_off / g.W.mean(), color="#edae49", lw=1.2, ls="--", label="  generation")
            ax.set_title(f"{ba} - {name}", fontsize=10)
            ax.grid(alpha=.25); ax.set_ylim(0, None)
            if j == 0:
                ax.set_ylabel("relative to own mean")
            if i == 1:
                ax.set_xlabel("local hour of day")
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.suptitle("Carbon and water per kWh of IT load by hour of day (2021-2025)", fontsize=12)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/diurnal_carbon_water.png", dpi=150); plt.close(fig)
    pd.concat({f"{k[0]}|{k[1]}": v for k, v in prof.items()}).to_csv(ROOT / "results/water_diurnal_profiles.csv")

    # frontier (fixed site)
    F = frontier(d)
    S = summarize(F)
    S.to_csv(ROOT / "results/water_frontier_by_alpha.csv", index=False)
    SB = summarize(F, by=("ba", "job", "k", "mode", "alpha"))
    SB.to_csv(ROOT / "results/water_frontier_by_ba.csv", index=False)
    sel = S[(S.job == "preemptible") & (S.k == 8)]
    print("\n=== Frontier, 2025, 8-hour preemptible job, pooled over BAs (savings vs random timing) ===")
    for mode in ("oracle", "persist"):
        print(f"-- decisions use {mode} values")
        print(sel[sel["mode"] == mode][["alpha", "carbon_saved_vs_random_pct", "water_saved_vs_random_pct",
                                         "carbon_saved_vs_immediate_pct", "water_saved_vs_immediate_pct", "days"]]
              .round(1).to_string(index=False))
    # per-BA endpoints
    e = SB[(SB.job == "preemptible") & (SB.k == 8) & (SB["mode"] == "persist") & SB.alpha.isin([0.0, 0.5, 1.0])]
    print("\n=== Per-BA endpoints (persistence forecasts, 8h preemptible; % vs random timing) ===")
    print(e.pivot(index="ba", columns="alpha", values=["carbon_saved_vs_random_pct", "water_saved_vs_random_pct"])
          .round(1).to_string())

    # figure: frontier
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    ax = axes[0]
    for mode, ls, col in (("oracle", "--", "#7a7a7a"), ("persist", "-", "#1b6ca8")):
        s = sel[sel["mode"] == mode].sort_values("alpha")
        ax.plot(s.water_saved_vs_random_pct, s.carbon_saved_vs_random_pct, ls, color=col, lw=2, marker="o", ms=4,
                label=f"{'perfect foresight' if mode == 'oracle' else 'persistence forecast'}")
        if mode == "persist":
            for a in (0.0, 0.5, 1.0):
                r = s[s.alpha == a].iloc[0]
                ax.annotate({0.0: "water-only", 0.5: "balanced", 1.0: "carbon-only"}[a],
                            (r.water_saved_vs_random_pct, r.carbon_saved_vs_random_pct), fontsize=8,
                            xytext=(6, 6), textcoords="offset points")
    ax.axhline(0, color="k", lw=.6); ax.axvline(0, color="k", lw=.6)
    ax.set_xlabel("water saved vs random timing (%)"); ax.set_ylabel("carbon saved vs random timing (%)")
    ax.set_title("Carbon-water frontier, 8 h job, all BAs (2025)", fontsize=10); ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.25)
    ax = axes[1]
    for ba, col in zip(BAS, ["#1b6ca8", "#d1495b", "#edae49", "#2a9d8f"]):
        s = SB[(SB.ba == ba) & (SB.job == "preemptible") & (SB.k == 8) & (SB["mode"] == "persist")].sort_values("alpha")
        ax.plot(s.water_saved_vs_random_pct, s.carbon_saved_vs_random_pct, color=col, lw=2, marker="o", ms=3, label=ba)
    ax.axhline(0, color="k", lw=.6); ax.axvline(0, color="k", lw=.6)
    ax.set_xlabel("water saved vs random timing (%)"); ax.set_ylabel("carbon saved vs random timing (%)")
    ax.set_title("By balancing authority (persistence forecast)", fontsize=10); ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/frontier_carbon_water.png", dpi=150); plt.close(fig)

    # multi-site (choose BA and hour)
    M = frontier(d, multi_site=True)
    SM = summarize(M, by=("job", "k", "mode", "alpha"))
    SM.to_csv(ROOT / "results/water_frontier_multisite.csv", index=False)
    m8 = SM[(SM.k == 8) & (SM["mode"] == "persist") & SM.alpha.isin([0.0, 0.5, 1.0])]
    print("\n=== Multi-site (choose among 4 BAs and hours), 8h, persistence; % vs random site+time ===")
    print(m8[["alpha", "carbon_saved_vs_random_pct", "water_saved_vs_random_pct", "days"]].round(1).to_string(index=False))

    # sensitivity of the headline to the water assumptions
    sens = []
    cases = {"base": (WF, WUE_MAX),
             "hydro_17_L_per_kWh": ({**WF, "WAT": 17.0}, WUE_MAX),
             "offsite_x0.5": ({k: v * 0.5 for k, v in WF.items()}, WUE_MAX),
             "offsite_x2": ({k: v * 2 for k, v in WF.items()}, WUE_MAX),
             "onsite_x0.5": (WF, WUE_MAX * 0.5), "onsite_x1.5": (WF, WUE_MAX * 1.5)}
    for name, (wf, wm) in cases.items():
        dd = build(wf, wm)
        Fs = frontier(dd)
        Ss = summarize(Fs)
        s = Ss[(Ss.job == "preemptible") & (Ss.k == 8) & (Ss["mode"] == "persist")]
        r0, r5, r1 = (s[s.alpha == a].iloc[0] for a in (0.0, 0.5, 1.0))
        dsc = describe(dd)
        sens.append({"case": name, "mean_W_total": dsc.W_total.mean(),
                     "within_day_corr_C_W": dsc.within_day_corr_C_W.mean(),
                     "carbonOnly_carbon": r1.carbon_saved_vs_random_pct, "carbonOnly_water": r1.water_saved_vs_random_pct,
                     "balanced_carbon": r5.carbon_saved_vs_random_pct, "balanced_water": r5.water_saved_vs_random_pct,
                     "waterOnly_carbon": r0.carbon_saved_vs_random_pct, "waterOnly_water": r0.water_saved_vs_random_pct})
    SS = pd.DataFrame(sens)
    SS.to_csv(ROOT / "results/water_sensitivity.csv", index=False)
    print("\n=== Sensitivity of the tradeoff to water assumptions (8h preemptible, persistence, pooled) ===")
    print(SS.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
