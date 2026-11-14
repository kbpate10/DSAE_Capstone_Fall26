"""Marginal vs average emissions: does the scheduling conclusion change with the signal?

Marginal emission rate (MEF, kg CO2 per MWh of demand) per BA is the slope of the hourly change in
in-BA generation CO2 on the hourly change in BA demand, estimated separately for each local hour of day and
season (summer = Jun-Sep, else other), with day-block bootstrap intervals. Same regression for each fuel gives
the marginal fuel mix (MWh of each fuel per MWh of demand change).

Limits stated up front:
  * Production-based, in-BA only. EIA-930 interchange is not used, so an hour in which a BA meets demand
    by imports is read as "no marginal generation". AZPS and SRP trade heavily; MEFs here describe the
    generation inside each BA, not the grid that would respond to the load.
  * Demand changes are not exogenous (they co-move with temperature, solar ramps and dispatch), so the slope is an
    association, not a causal effect of a new load. Standard in this literature but it should be said.
  * Flagged hours and hours next to a flagged hour are dropped (no interpolation).

Scheduling comparison (2025 test year, 8 h preemptible job, same BA-days as schedule_eval):
  decision signals  : average-CI persistence (yesterday's same hour, as in schedule_eval) | MEF profile estimated
                      on 2021-2024 only | oracle on actual average CI
  evaluation        : (a) actual average CI, (b) MEF profile re-estimated on 2025 (the stand-in for truth)
  Chronological: decisions use information before 2025; evaluation uses 2025.
Savings are % vs choosing k hours at random (window mean), per BA.

Hour-of-day bins: 1 h and 6 h (the 6 h run tests whether coarser bins are stable enough to use).

Outputs: results/mef_by_hour.csv, results/mef_marginal_fuel.csv, results/mef_scheduling.csv,
         results/figures/mef_profiles.png
"""
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
BAS = ["AZPS", "SRP", "TEPC", "WALC"]
FUELS = ["COL", "NG", "NUC", "SUN", "WND", "WAT", "OIL", "OTH"]
K, NBOOT = 8, 300
BLOCKS = (1, 6)          # hour-of-day bin width: hourly profile, and 6-hour blocks to trade resolution for noise
rng = np.random.default_rng(0)


def load() -> pd.DataFrame:
    m = pd.read_parquet(ROOT / "data/processed/master_ba_hour.parquet")
    ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet")[["respondent", "ts", "co2_kg"]]
    m = m.merge(ci, on=["respondent", "ts"], how="left").sort_values(["respondent", "ts"])
    # Demand QC: EIA-930 demand contains glitches (e.g. SRP 70,313 MWh against a median of 3,407; WALC from -50,457 to +94,444; 53 hours across the four BAs).
    # A single such value has huge leverage in the dCO2 ~ dD regression, so demand that is not positive or exceeds 5 x the BA's median is set to missing
    # (the hour and its neighbouring difference then drop out via `ok`). Added after the multi-BA scan's QC found the same problem in PJM; see docs/MARGINAL.md.
    med = m.groupby("respondent").demand_mwh.transform("median")
    glitch = (m.demand_mwh <= 0) | (m.demand_mwh > 5 * med)
    m.loc[glitch, "demand_mwh"] = np.nan
    m.attrs["n_demand_glitch"] = glitch.groupby(m.respondent).sum().to_dict()
    m["season"] = np.where(m.month.between(6, 9), "summer", "other")
    m["day"] = m.ts_local.dt.floor("D")
    bad = m.data_flag.fillna(True).astype(bool) | m.demand_mwh.isna() | m.co2_kg.isna()
    g = m.assign(bad=bad).groupby("respondent")
    # drop an hour if it or the previous hour is bad, and require consecutive timestamps
    prev_bad = g.bad.shift(1).fillna(True).astype(bool)
    gap = g.ts.diff() != pd.Timedelta(hours=1)
    m["ok"] = ~bad & ~prev_bad & ~gap
    m["dD"] = g.demand_mwh.diff()
    m["dCO2"] = g.co2_kg.diff() / 1000.0                       # tonnes -> kept in t, slope is t/MWh x 1000 = kg/MWh
    for f in FUELS:
        m[f"d_{f}"] = g[f"gen_{f}_mwh"].diff()
    return m


def slope(x, y):
    xc = x - x.mean()
    d = (xc ** 2).sum()
    return np.nan if d == 0 else float((xc * (y - y.mean())).sum() / d)


def mef_table(d: pd.DataFrame, boot: bool, block: int) -> pd.DataFrame:
    rows = []
    for (ba, season, hr), g in d.assign(hb=d.hour_local // block * block).groupby(["respondent", "season", "hb"]):
        g = g[g.ok]
        if len(g) < 30:
            continue
        b = slope(g.dD.to_numpy(), g.dCO2.to_numpy()) * 1000.0     # kg CO2 per MWh
        row = {"ba": ba, "season": season, "hour": hr, "mef_kg_mwh": b, "n": len(g)}
        if boot:
            # day-block bootstrap from per-day sufficient statistics (one hour per day in this cell, so a block is a day)
            S = np.column_stack([np.ones(len(g)), g.dD, g.dCO2, g.dD ** 2, g.dD * g.dCO2])
            w = rng.multinomial(len(g), np.ones(len(g)) / len(g), size=NBOOT)
            n, sx, sy, sxx, sxy = (w @ S).T
            with np.errstate(divide="ignore", invalid="ignore"):
                est = (sxy - sx * sy / n) / (sxx - sx ** 2 / n) * 1000.0
            row["lo"], row["hi"] = np.nanpercentile(est, [2.5, 97.5])
        rows.append(row)
    return pd.DataFrame(rows)


def marginal_fuel(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (ba, season), g in d[(d.year.between(2021, 2024)) & d.ok].groupby(["respondent", "season"]):
        r = {"ba": ba, "season": season, "n": len(g)}
        for f in FUELS:
            gf = g.dropna(subset=[f"d_{f}"])
            r[f] = slope(gf.dD.to_numpy(), gf[f"d_{f}"].to_numpy()) if len(gf) > 30 else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def schedule(d: pd.DataFrame, mef_train: pd.DataFrame, mef_eval: pd.DataFrame, block: int, year: int = 2025) -> pd.DataFrame:
    mt = mef_train.set_index(["ba", "season", "hour"]).mef_kg_mwh
    me = mef_eval.set_index(["ba", "season", "hour"]).mef_kg_mwh
    t = d[(d.year == year)].copy()
    t["ci_p"] = t.groupby("respondent").ci_kg_per_mwh.shift(24)
    rows = []
    for (ba, day), g in t.groupby(["respondent", "day"]):
        g = g.set_index("hour_local").reindex(range(24))
        if len(g) != 24 or g.ci_kg_per_mwh.isna().any() or g.ci_p.isna().any() or g.data_flag.fillna(True).astype(bool).any():
            continue
        s = g.season.iloc[0] if isinstance(g.season.iloc[0], str) else "other"
        try:
            mtr = np.array([mt[(ba, s, h // block * block)] for h in range(24)])
            mev = np.array([me[(ba, s, h // block * block)] for h in range(24)])
        except KeyError:
            continue
        ci, cip = g.ci_kg_per_mwh.to_numpy(), g.ci_p.to_numpy()
        pick = lambda sig: np.argsort(sig, kind="stable")[:K]
        choice = {"avg_persist": pick(cip), "mef_profile": pick(mtr), "avg_oracle": pick(ci), "mef_oracle_eval": pick(mev)}
        rec = {"ba": ba, "day": day, "season": s}
        for acct, sig in (("avg_ci", ci), ("mef_eval", mev)):
            rand = sig.mean() * K
            for name, idx in choice.items():
                rec[f"{acct}|{name}"] = 100 * (1 - sig[idx].sum() / rand) if abs(rand) > 1e-9 else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    d = load()
    train = d[d.year.between(2021, 2024)]
    mf = marginal_fuel(d)
    mf.round(3).to_csv(ROOT / "results/mef_marginal_fuel.csv", index=False)
    print("Marginal fuel response (MWh of fuel per MWh of demand change, 2021-2024):")
    print(mf.round(2).to_string(index=False))
    ci_mean = train[train.ok].groupby("respondent").ci_kg_per_mwh.mean()
    prof, sched = [], []
    for block in BLOCKS:
        mef_tr = mef_table(train, boot=True, block=block)
        mef_ev = mef_table(d[d.year == 2025], boot=False, block=block)
        allm = mef_tr.merge(mef_ev[["ba", "season", "hour", "mef_kg_mwh"]], on=["ba", "season", "hour"],
                            how="left", suffixes=("", "_2025"))
        allm["block_h"] = block
        allm["sig"] = (allm.lo > 0) | (allm.hi < 0)
        prof.append(allm)
        st = allm.groupby("ba").apply(lambda g: pd.Series({
            "mef_mean": g.mef_kg_mwh.mean(), "mef_min": g.mef_kg_mwh.min(), "mef_max": g.mef_kg_mwh.max(),
            "share_sig": g.sig.mean(), "corr_train_vs_2025": g.mef_kg_mwh.corr(g.mef_kg_mwh_2025)}))
        st["avg_ci_2021_24"] = ci_mean
        print(f"\n=== {block}-hour bins: MEF (kg CO2/MWh) vs average CI, 2021-2024; stability vs 2025 ===")
        print(st.round(2).to_string())
        S = schedule(d, mef_tr, mef_ev, block)
        cols = [c for c in S.columns if "|" in c]
        out = S.groupby("ba")[cols].mean().T
        out["pooled"] = S[cols].mean().values
        out.index = pd.MultiIndex.from_tuples([tuple(i.split("|")) for i in out.index], names=["evaluated_on", "decision"])
        out["block_h"] = block
        sched.append(out.reset_index())
        print(f"Savings (% vs random timing, {K} h preemptible, 2025), by decision signal and accounting:")
        print(out.drop(columns="block_h").round(1).to_string())
    allm = pd.concat(prof)
    allm.round(1).to_csv(ROOT / "results/mef_by_hour.csv", index=False)
    pd.concat(sched).round(1).to_csv(ROOT / "results/mef_scheduling.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    allm = allm[allm.block_h == 1]
    for ax, season in zip(axes, ("summer", "other")):
        for ba, c in zip(BAS, ("#1b6ca8", "#edae49", "#2a9d8f", "#d1495b")):
            g = allm[(allm.ba == ba) & (allm.season == season)].sort_values("hour")
            ax.plot(g.hour, g.mef_kg_mwh, color=c, label=ba)
            ax.fill_between(g.hour, g.lo, g.hi, color=c, alpha=.12)
        ax.set_title(f"Marginal emission rate by local hour ({season}, 2021-2024)", fontsize=10)
        ax.set_xlabel("local hour"); ax.grid(alpha=.25)
    axes[0].set_ylabel("kg CO2 per MWh of demand change"); axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/mef_profiles.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
