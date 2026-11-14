"""Consumption-based carbon intensity for the Arizona BAs by flow tracing, and what it does to the scheduling result.

Method (flow tracing, hourly). For BA b with generation G_b (MWh, CO2 Q_b kg from carbon_intensity.parquet) and imports
I_jb from BA j (MWh, from b's own interchange report: -value when value < 0), the intensity of everything b supplies
(its own consumption AND its exports) is
        c_b = (Q_b + sum_j I_jb * c_j) / (G_b + sum_j I_jb)
For the four Arizona BAs the c_j are unknowns, so each hour is a 4x4 linear system; for external BAs j, c_j is their own
production-based intensity (eGRID emission factors, same method as carbon_intensity.py; fallbacks BA -> AZ -> US
per fuel, so an external BA with an unusual fuel may borrow an Arizona factor).
This is consumption-based in the "average mix delivered" sense, not marginal.

Choices and limits:
  * Imports from BAs without a computed intensity (no fuel data, or a flagged hour) are dropped from the supply and the
    BA-hour is kept only if the known share of its import MWh is >= 95% (renormalising over the known part assumes the
    unknown <= 5% looks like the known part). Otherwise the hour is flagged and excluded, not imputed.
  * An hour is valid only if every Arizona BA's generation is unflagged (the four are coupled), and all four solve.
  * Reported flows between two Arizona BAs differ by up to a few percent between the two reports; each BA's own report is
    used for its imports.
  * Hydro/clean attribution follows the EIA fuel codes, unchanged from the production-based series.

Scheduling check (2025 test year, 8 h preemptible job, decision on yesterday's same-hour intensity, % saved vs random):
  decision signal x accounting = {production, consumption}^2, to see whether the RQ1 savings depend on the accounting.

Outputs: data/processed/consumption_ci.parquet, results/consumption_ci_summary.csv, results/consumption_scheduling.csv,
         results/figures/consumption_ci.png
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
import carbon_intensity as ci

AZ = ["AZPS", "SRP", "TEPC", "WALC"]
NEIGH = ["PNM", "WACM", "EPE", "GRIF", "GRID", "DEAA", "HGMA", "PACE", "IID", "CISO"]
MIN_COVER, K = 0.95, 8


def neighbor_ci() -> pd.DataFrame:
    import glob
    ci.BAS = AZ + NEIGH                        # emission_factors() builds factors for ci.BAS
    ef = ci.emission_factors()
    df = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930_neighbors/*.parquet")))
    df = df[~df.fueltype.isin(ci.EXCLUDE) & df.respondent.isin(NEIGH)][["period", "respondent", "fueltype", "value"]]
    df["value"] = df.value.clip(lower=0)
    df = df.merge(ef, on=["respondent", "fueltype"], how="left")
    df["co2"] = df.value * df.ef
    g = df.groupby(["respondent", "period"])
    out = pd.DataFrame({"gen": g.value.sum(min_count=1), "co2": g.co2.sum(min_count=1),
                        "n_null": g.value.apply(lambda s: s.isna().sum())}).reset_index()
    out["ci"] = out.co2 / out.gen.where(out.gen > 0)
    out["ts"] = pd.to_datetime(out.period, format="%Y-%m-%dT%H")
    out.loc[(out.n_null > 0) | out.ci.isna(), "ci"] = np.nan
    print("External BAs: share of hours with a usable intensity, mean intensity (kg/MWh):")
    print(out.groupby("respondent").agg(hours=("ci", "size"), usable=("ci", lambda s: s.notna().mean()),
                                        mean_ci=("ci", "mean")).round(2).to_string())
    return out[["respondent", "ts", "ci"]]


def trace() -> pd.DataFrame:
    prod = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet")
    prod = prod[prod.respondent.isin(AZ)]
    nb = neighbor_ci()
    x = pd.concat(pd.read_parquet(f) for f in (ROOT / "data/raw/eia930_interchange").glob("*.parquet"))
    x["ts"] = pd.to_datetime(x.period, format="%Y-%m-%dT%H")
    x["imp"] = (-pd.to_numeric(x.value, errors="coerce")).clip(lower=0)
    x = x[x.fromba.isin(AZ)]
    ext_ci = nb.rename(columns={"respondent": "toba", "ci": "ci_j"})
    x = x.merge(ext_ci, on=["toba", "ts"], how="left")
    x["is_az"] = x.toba.isin(AZ)
    x["known"] = x.is_az | x.ci_j.notna()

    ts = np.sort(prod.ts.unique())
    ix = {t: i for i, t in enumerate(ts)}
    T = len(ts)
    bi = {b: i for i, b in enumerate(AZ)}
    G, Q, FL = np.full((T, 4), np.nan), np.full((T, 4), np.nan), np.ones((T, 4), bool)
    for b, g in prod.groupby("respondent"):
        i = g.ts.map(ix).to_numpy()
        G[i, bi[b]], Q[i, bi[b]], FL[i, bi[b]] = g.gen_mwh, g.co2_kg, g.data_flag.fillna(True).to_numpy()
    M = np.zeros((T, 4, 4))                    # M[t, b, j] imports of b from Arizona BA j
    ext_q = np.zeros((T, 4))                   # sum over external j of I_jb * c_j
    imp_known, imp_all = np.zeros((T, 4)), np.zeros((T, 4))
    xi = x.dropna(subset=["imp"])
    t_idx = xi.ts.map(ix).to_numpy()
    b_idx = xi.fromba.map(bi).to_numpy()
    imp = xi.imp.to_numpy()
    np.add.at(imp_all, (t_idx, b_idx), imp)
    k = xi.known.to_numpy()
    np.add.at(imp_known, (t_idx[k], b_idx[k]), imp[k])
    az = xi.is_az.to_numpy()
    j_idx = xi.toba.map(bi).fillna(-1).astype(int).to_numpy()
    np.add.at(M, (t_idx[az], b_idx[az], j_idx[az]), imp[az])
    e = k & ~az
    np.add.at(ext_q, (t_idx[e], b_idx[e]), imp[e] * xi.ci_j.to_numpy()[e])

    cover = np.where(imp_all > 0, imp_known / np.where(imp_all > 0, imp_all, 1), 1.0)
    S = G + imp_known                          # own generation + all imports with a known source intensity
    A = -M.copy()
    for b in range(4):
        A[:, b, b] += S[:, b]
    rhs = Q + ext_q
    valid = ~FL.any(axis=1) & (cover >= MIN_COVER).all(axis=1) & np.isfinite(rhs).all(axis=1) & np.isfinite(S).all(axis=1) & (S > 0).all(axis=1)
    c = np.full((T, 4), np.nan)
    if valid.any():
        c[valid] = np.linalg.solve(A[valid], rhs[valid][..., None])[..., 0]
    out = []
    for b in AZ:
        i = bi[b]
        out.append(pd.DataFrame({"respondent": b, "ts": ts, "ci_prod": np.where(FL[:, i], np.nan, Q[:, i] / np.where(G[:, i] > 0, G[:, i], np.nan)),
                                 "ci_cons": c[:, i], "import_cover": cover[:, i], "imports_mwh": imp_all[:, i],
                                 "supply_mwh": S[:, i], "valid": valid}))
    res = pd.concat(out, ignore_index=True)
    res.loc[~res.valid, "ci_cons"] = np.nan
    res["local"] = res.ts - pd.Timedelta(hours=7)
    return res


def schedule(d: pd.DataFrame) -> pd.DataFrame:
    d = d.sort_values(["respondent", "ts"]).copy()
    for s in ("prod", "cons"):
        d[f"{s}_p"] = d.groupby("respondent")[f"ci_{s}"].shift(24)
    t = d[d.local.dt.year == 2025].copy()
    t["day"], t["hr"] = t.local.dt.floor("D"), t.local.dt.hour
    rows = []
    for (ba, day), g in t.groupby(["respondent", "day"]):
        g = g.set_index("hr").reindex(range(24))
        if g[["ci_prod", "ci_cons", "prod_p", "cons_p"]].isna().any().any():
            continue
        rec = {"ba": ba, "day": day}
        for dec in ("prod", "cons"):
            idx = np.argsort(g[f"{dec}_p"].to_numpy(), kind="stable")[:K]
            for ev in ("prod", "cons"):
                y = g[f"ci_{ev}"].to_numpy()
                rec[f"decide_{dec}|eval_{ev}"] = 100 * (1 - y[idx].sum() / (y.mean() * K))
        rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    d = trace()
    d.drop(columns="local").to_parquet(ROOT / "data/processed/consumption_ci.parquet", index=False)
    v = d[d.valid & (d.local.dt.year >= 2021)]
    print(f"\nValid system-hours: {int(d[d.respondent == 'AZPS'].valid.sum())} of {int((d.respondent == 'AZPS').sum())}")
    rows = []
    for ba, g in v.groupby("respondent"):
        dm = g.assign(day=g.local.dt.floor("D"))
        for c in ("ci_prod", "ci_cons"):
            dm[c + "_d"] = dm[c] - dm.groupby("day")[c].transform("mean")
        rows.append({"ba": ba, "hours": len(g), "import_share_pct": 100 * g.imports_mwh.sum() / g.supply_mwh.sum(),
                     "prod_mean": g.ci_prod.mean(), "cons_mean": g.ci_cons.mean(),
                     "corr_hourly": g.ci_prod.corr(g.ci_cons), "corr_within_day": dm.ci_prod_d.corr(dm.ci_cons_d),
                     "cons_p5": g.ci_cons.quantile(.05), "cons_p95": g.ci_cons.quantile(.95)})
    R = pd.DataFrame(rows).set_index("ba")
    R.round(2).to_csv(ROOT / "results/consumption_ci_summary.csv")
    print("\nProduction vs consumption-based intensity (kg CO2/MWh), valid hours 2021-2025:")
    print(R.round(2).to_string())
    print("\nImport coverage (share of import MWh with a known source intensity), all hours:")
    print(d.groupby("respondent").import_cover.describe().round(3).to_string())

    S = schedule(d)
    cols = [c for c in S.columns if "|" in c]
    out = S.groupby("ba")[cols].mean().T
    out["pooled"] = S[cols].mean().values
    out.index = pd.MultiIndex.from_tuples([tuple(i.split("|")) for i in out.index], names=["decision", "evaluated_on"])
    out.round(1).to_csv(ROOT / "results/consumption_scheduling.csv")
    print(f"\nSavings (% vs random timing, {K} h preemptible, 2025), by decision signal and accounting:")
    print(out.round(1).to_string())
    print("days per BA:", S.groupby("ba").day.nunique().to_dict())

    fig, ax = plt.subplots(1, 4, figsize=(13, 3.6), sharey=True)
    for a, ba in zip(ax, AZ):
        g = v[v.respondent == ba]
        h = g.groupby(g.local.dt.hour)[["ci_prod", "ci_cons"]].mean()
        a.plot(h.index, h.ci_prod, label="production", color="#1b6ca8")
        a.plot(h.index, h.ci_cons, label="consumption", color="#d1495b")
        a.set_title(ba, fontsize=10); a.set_xlabel("local hour"); a.grid(alpha=.25)
    ax[0].set_ylabel("kg CO2 per MWh"); ax[0].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/consumption_ci.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
