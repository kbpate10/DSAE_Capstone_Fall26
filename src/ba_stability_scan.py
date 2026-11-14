"""Multi-BA scan: does import dependence predict the out-of-sample instability of in-BA regression marginal-emission estimates?

Implements docs/MEF_SCAN_PREREG.md. Read that file first: the hypothesis, inclusion rule, metrics and the decision rule were fixed before the data were analysed.

Per BA (EIA-930, 2021-2025; data from pull_ba_panel.py and the earlier Arizona pulls):
  * hourly CO2 = sum over fuels of generation x eGRID emission factor (BA-specific, falling back to the US factor of that fuel; NOT the Arizona factor);
    an hour is flagged and dropped if any fuel value is missing, a demand/NG/TI value is an EIA-930 sentinel or implausible under eia930_qc.py (primary 'band' rule; --legacy-qc runs the secondary 5 x median rule), total generation is not positive, demand or net interchange is missing, or the previous hour is missing.
  * MEF profile = slope of the hourly change in CO2 on the hourly change in demand, by 6 h local block x summer/other season (as marginal_emissions.py, base
    specification). Local time is FIXED STANDARD TIME per BA (Eastern -5, Central -6, Mountain -7, Pacific -8): daylight saving is ignored and a BA's zone is assigned by hand
    (MISO is set to Eastern, an assumption), so block boundaries can be off by an hour in summer; the effect on 6 h blocks is small but not zero.
  * Two splits: train 2021-2023 / test 2024 and train 2021-2024 / test 2025.
  * S = correlation of train and test profiles over the block-season cells (mean over the two splits); D = mean absolute train-test difference as % of the train mean.
  * A = absorption by net interchange = -slope(change in net export on change in demand), mean over cells and splits. Secondary: net import share, net export share
    of demand, fuel concentration (Herfindahl of generation shares), clean share.
Inclusion (pre-specified): >= 90% valid hours in 2021-2024 and mean carbon intensity >= 50 kg/MWh over 2021-2024. Verdict computed on included BAs excluding the four
Arizona BAs; the full sample is secondary. Spearman correlations, one-sided permutation p (10,000).

Outputs: results/mef_scan_by_ba.csv, results/mef_scan_tests.csv, results/figures/mef_scan.png
"""
import glob
import re
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
import eia930_qc as qc
import pull_ba_panel as pb

SHORT_TON_KG = 907.18474
FUEL_MAP = {"COL": "COAL", "NG": "GAS", "NUC": "NUCLEAR", "OIL": "OIL", "SUN": "SOLAR", "WND": "WIND", "WAT": "HYDRO", "OTH": "OTHF"}
CLEAN = {"SUN", "WND", "WAT", "NUC"}
TZ = {"PJM": -5, "MISO": -5, "ERCO": -6, "NYIS": -5, "ISNE": -5, "SWPP": -6, "SOCO": -5, "TVA": -6, "DUK": -5, "FPL": -5, "FPC": -5, "TEC": -5, "SC": -5,
      "SCEG": -5, "CPLE": -5, "LGEE": -5, "AECI": -6, "BPAT": -8, "PACW": -8, "NEVP": -8, "IPCO": -7, "PSCO": -7, "AVA": -8, "NWMT": -7, "PGE": -8, "LDWP": -8,
      "TPWR": -8, "AZPS": -7, "SRP": -7, "TEPC": -7, "WALC": -7, "PNM": -7, "WACM": -7, "EPE": -7, "PACE": -7, "IID": -8, "CISO": -8}
AZ = ["AZPS", "SRP", "TEPC", "WALC"]
BLOCK, NPERM = 6, 10000
QC_MODE = "legacy5x" if "--legacy-qc" in sys.argv else "band"          # primary rule: 'band'; secondary sensitivity: --legacy-qc (see eia930_qc.py)
SPLITS = ((2024, range(2021, 2024)), (2025, range(2021, 2025)))
rng = np.random.default_rng(0)


def emission_factors(bas: list) -> pd.DataFrame:
    p = pd.read_excel(ROOT / "data/raw/egrid/egrid2023_data_rev2.xlsx", sheet_name="PLNT23", header=1)[["BACODE", "PLFUELCT", "PLNGENAN", "PLCO2AN"]]
    p["PLNGENAN"] = pd.to_numeric(p.PLNGENAN, errors="coerce")
    p["PLCO2AN"] = pd.to_numeric(p.PLCO2AN, errors="coerce")
    p = p[p.PLNGENAN > 0]
    ba = (p.groupby(["BACODE", "PLFUELCT"])[["PLCO2AN", "PLNGENAN"]].sum().pipe(lambda g: g.PLCO2AN * SHORT_TON_KG / g.PLNGENAN)).rename("ef_ba").reset_index()
    us = (p.groupby("PLFUELCT")[["PLCO2AN", "PLNGENAN"]].sum().pipe(lambda g: g.PLCO2AN * SHORT_TON_KG / g.PLNGENAN)).rename("ef_us").reset_index()
    rows = [{"respondent": b, "fueltype": c, "PLFUELCT": f} for b in bas for c, f in FUEL_MAP.items()]
    t = pd.DataFrame(rows).merge(ba, left_on=["respondent", "PLFUELCT"], right_on=["BACODE", "PLFUELCT"], how="left").merge(us, on="PLFUELCT", how="left")
    t["ef"] = t.ef_ba.fillna(t.ef_us).fillna(0.0)
    t["src"] = np.where(t.ef_ba.notna(), "ba", "us")
    return t[["respondent", "fueltype", "ef", "src"]]


def have(ba: str) -> bool:
    reg = all((pb.OUT / "region" / f"{ba}_{y}.parquet").exists() for y in range(2021, 2026))
    fuel = all(((pb.OUT / "fuel" / f"{ba}_{y}.parquet").exists() or (ROOT / "data/raw/eia930" / f"{ba}_{y}.parquet").exists()
                or (ROOT / "data/raw/eia930_neighbors" / f"{ba}_{y}.parquet").exists()) for y in range(2021, 2026))
    return reg and fuel


def read(ba: str, kind: str) -> pd.DataFrame:
    dirs = [pb.OUT / kind] if kind == "region" else [pb.OUT / "fuel", ROOT / "data/raw/eia930", ROOT / "data/raw/eia930_neighbors"]
    fs = [f for d in dirs for f in glob.glob(str(d / f"{ba}_*.parquet"))]
    return pd.concat(pd.read_parquet(f) for f in fs)


def hourly(ba: str, ef: pd.DataFrame) -> pd.DataFrame:
    f = read(ba, "fuel")
    f = f[f.fueltype.isin(FUEL_MAP)].copy()
    f["ts"] = pd.to_datetime(f.period, format="%Y-%m-%dT%H")
    e = ef[ef.respondent == ba].set_index("fueltype").ef
    f["e"] = f.fueltype.map(e)
    f["g"] = f.value.clip(lower=0)
    f["co2"] = f.g * f.e / 1000.0                                  # tonnes
    g = f.groupby("ts").agg(gen=("g", "sum"), co2=("co2", lambda s: s.sum(min_count=1)), n_null=("value", lambda s: int(s.isna().sum())))
    clean = f[f.fueltype.isin(CLEAN)].groupby("ts").g.sum().rename("clean")
    shares = f.pivot_table(index="ts", columns="fueltype", values="g", aggfunc="sum")
    hhi = ((shares.div(shares.sum(axis=1), axis=0)) ** 2).sum(axis=1).rename("hhi")
    r = read(ba, "region")
    r["ts"] = pd.to_datetime(r.period, format="%Y-%m-%dT%H")
    r = r.pivot_table(index="ts", columns="type", values="value", aggfunc="first")
    r, qc_counts = qc.clean_region(r, TZ[ba], QC_MODE)
    d = g.join(clean).join(hhi).join(r, how="outer").sort_index()
    full = pd.date_range(d.index.min(), d.index.max(), freq="h")
    d = d.reindex(full)
    bad = d.gen.isna() | (d.gen <= 0) | (d.n_null > 0) | d.co2.isna() | d.D.isna() | d.TI.isna()
    d["bad"] = bad
    d["ok"] = ~bad & ~bad.shift(1, fill_value=True)
    d["dD"], d["dCO2"], d["dTI"] = d.D.diff(), d.co2.diff(), d.TI.diff()
    local = d.index + pd.Timedelta(hours=TZ[ba])
    d["year"] = d.index.year
    d["hb"] = local.hour // BLOCK * BLOCK
    d["season"] = np.where(local.month.isin([6, 7, 8, 9]), "summer", "other")
    d["ci"] = d.co2 * 1000.0 / d.gen
    d.attrs["n_sentinel"] = sum(v for k, v in qc_counts.items() if k.endswith("sentinel"))
    d.attrs["n_implausible"] = sum(v for k, v in qc_counts.items() if k.endswith("implausible"))
    return d


def slope(x, y):
    xc = x - x.mean()
    den = (xc ** 2).sum()
    return np.nan if den == 0 else float((xc * (y - y.mean())).sum() / den)


def profile(d: pd.DataFrame, years, ycol: str, minobs: int) -> pd.Series:
    t = d[d.ok & d.year.isin(list(years))]
    out = {}
    for (s, hb), g in t.groupby(["season", "hb"]):
        if len(g) >= minobs:
            out[(s, hb)] = slope(g.dD.to_numpy(), g[ycol].to_numpy()) * (1000.0 if ycol == "dCO2" else 1.0)
    return pd.Series(out, dtype=float)


def one_ba(ba: str, ef: pd.DataFrame) -> dict:
    d = hourly(ba, ef)
    tr = d[d.year.between(2021, 2024)]
    valid = float(tr.ok.mean())
    rec = {"ba": ba, "n_sentinel_values": d.attrs["n_sentinel"], "n_implausible_values": d.attrs["n_implausible"], "valid_share_2021_24": valid, "mean_ci_2021_24": float(tr.loc[~tr.bad, "ci"].mean()), "mean_demand_mwh": float(tr.D.mean())}
    S, Dm, A, MAD, MTR = [], [], [], [], []
    for test, train in SPLITS:
        ptr, pte = profile(d, train, "dCO2", 100), profile(d, [test], "dCO2", 30)
        j = pd.concat([ptr.rename("tr"), pte.rename("te")], axis=1).dropna()
        if len(j) >= 4:
            S.append(j.tr.corr(j.te))
            Dm.append(100 * (j.tr - j.te).abs().mean() / abs(j.tr.mean()) if j.tr.mean() != 0 else np.nan)
            MAD.append((j.tr - j.te).abs().mean())
            MTR.append(j.tr.mean())
        A.append(-profile(d, train, "dTI", 100).mean())
    rec.update({"mef_mean_train": np.nanmean(MTR) if MTR else np.nan, "mad_abs_kg_mwh": np.nanmean(MAD) if MAD else np.nan,
                "D_over_mean_ci_pct": 100 * np.nanmean(MAD) / rec["mean_ci_2021_24"] if MAD and rec["mean_ci_2021_24"] > 0 else np.nan})
    rec.update({"S_corr": np.nanmean(S) if S else np.nan, "D_mad_pct": np.nanmean(Dm) if Dm else np.nan, "A_absorption": np.nanmean(A)})
    for k, (test, train) in zip(("s2024", "s2025"), SPLITS):
        rec[f"S_{test}"] = S[0 if test == 2024 else 1] if len(S) == 2 else np.nan
    t = d[d.year.between(2021, 2024) & ~d.bad]
    dem = t.D.mean()
    rec.update({"net_import_share": float(np.clip(-t.TI, 0, None).mean() / dem), "net_export_share": float(np.clip(t.TI, 0, None).mean() / dem),
                "hhi": float(t.hhi.mean()), "clean_share": float((t.clean / t.gen).mean())})
    return rec


def perm_p(x: pd.Series, y: pd.Series, sign: int) -> tuple[float, float]:
    j = pd.concat([x, y], axis=1).dropna()
    if len(j) < 8:
        return np.nan, np.nan
    rho = j.iloc[:, 0].rank().corr(j.iloc[:, 1].rank())
    r = j.iloc[:, 1].rank().to_numpy()
    xr = j.iloc[:, 0].rank().to_numpy()
    null = np.array([np.corrcoef(xr, rng.permutation(r))[0, 1] for _ in range(NPERM)])
    p = (null <= rho).mean() if sign < 0 else (null >= rho).mean()
    return float(rho), float(p)


def main() -> None:
    sample = [b for b in pb.NEW + pb.HAVE_FUEL if have(b)]
    missing = [b for b in pb.NEW + pb.HAVE_FUEL if b not in sample]
    print(f"BAs with complete data: {len(sample)} of {len(pb.NEW + pb.HAVE_FUEL)}; waiting for: {missing}")
    if not sample:
        raise SystemExit("no BA has all five years of fuel and region data yet; run pull_ba_panel.py")
    ef = emission_factors(sample)
    print("share of (BA, fuel) emission factors taken from the BA's own eGRID plants:", round((ef.src == "ba").mean(), 2))
    if "--qc" in sys.argv:                      # data-quality diagnostics only: no stability metric or association is computed
        q = []
        for b in sample:
            d = hourly(b, ef)
            q.append({"ba": b, "hours": len(d), "sentinel_values": d.attrs["n_sentinel"], "implausible_values": d.attrs["n_implausible"], "share_bad_hours": d.bad.mean(), "D_min": d.D.min(), "D_median": d.D.median(),
                      "D_max": d.D.max(), "D_max_over_median": d.D.max() / d.D.median(), "TI_min": d.TI.min(), "TI_max": d.TI.max(),
                      "gen_median": d.gen.median(), "ci_min": d.ci.min(), "ci_max": d.ci.max(), "ci_p99.9": d.ci.quantile(.999), "years_present": sorted(d.index.year.unique().tolist())[0:1] + sorted(d.index.year.unique().tolist())[-1:]})
        pd.set_option("display.width", 250)
        print(pd.DataFrame(q).round(2).to_string(index=False))
        return
    rows = []
    for b in sample:
        try:
            rows.append(one_ba(b, ef))
        except Exception as e:
            print("FAILED", b, str(e)[:100])
    T = pd.DataFrame(rows)
    T["included"] = (T.valid_share_2021_24 >= 0.90) & (T.mean_ci_2021_24 >= 50)
    T["arizona"] = T.ba.isin(AZ)
    T.round(4).to_csv(ROOT / f"results/mef_scan_by_ba{'_legacyqc' if QC_MODE == 'legacy5x' else ''}.csv", index=False)
    pd.set_option("display.width", 230)
    print("\nPer-BA results (S = profile correlation, D = MAD %, A = absorption by net interchange):")
    print(T.sort_values("A_absorption").round(3).to_string(index=False))
    print("\nExcluded by the pre-specified rule:", T[~T.included][["ba", "valid_share_2021_24", "mean_ci_2021_24"]].round(2).to_dict("records"))

    tests = []
    for label, sub in (("VERDICT: included, excluding Arizona BAs", T[T.included & ~T.arizona]), ("secondary: included, all", T[T.included])):
        for pred in ("A_absorption", "net_import_share", "net_export_share", "hhi", "clean_share"):
            for metric, sign in (("S_corr", -1), ("D_mad_pct", +1)):
                rho, p = perm_p(sub[pred], sub[metric], sign)
                tests.append({"sample": label, "n": len(sub), "predictor": pred, "metric": metric, "spearman": rho, "p_one_sided": p})
    Tt = pd.DataFrame(tests)
    Tt.round(4).to_csv(ROOT / f"results/mef_scan_tests{'_legacyqc' if QC_MODE == 'legacy5x' else ''}.csv", index=False)
    print("\nSpearman correlations and one-sided permutation p (expected sign: S negative, D positive with absorption/imports):")
    print(Tt.round(3).to_string(index=False))

    v = Tt[(Tt["sample"].str.startswith("VERDICT")) & (Tt.predictor == "A_absorption")].set_index("metric")
    sS, sD = v.loc["S_corr"], v.loc["D_mad_pct"]
    support = (sS.spearman <= -0.33 and sS.p_one_sided <= 0.05 and sD.spearman >= 0.33 and sD.p_one_sided <= 0.05)
    kill = (abs(sS.spearman) < 0.20 and abs(sD.spearman) < 0.20)
    print(f"\nPRE-SPECIFIED VERDICT (n = {int(sS.n)}): corr(S, A) = {sS.spearman:.2f} (p = {sS.p_one_sided:.3f}); corr(D, A) = {sD.spearman:.2f} (p = {sD.p_one_sided:.3f})"
          f" -> {'SUPPORT' if support else 'KILL' if kill else 'INCONCLUSIVE'}")

    # EXPLORATORY, post hoc (not part of the pre-specified verdict): D is a percentage of each BA's mean MEF, so BAs with a small in-BA rate get a small denominator. Check
    # whether absorption is tied to the size of the mean MEF, and re-express the level disagreement as % of the average carbon intensity instead.
    sub = T[T.included & ~T.arizona]
    ex = []
    for lab, x, y, sg in (("A vs mean train MEF (denominator check)", "A_absorption", "mef_mean_train", 0), ("A vs level disagreement as % of average CI", "A_absorption", "D_over_mean_ci_pct", +1),
                          ("A vs absolute level disagreement (kg/MWh)", "A_absorption", "mad_abs_kg_mwh", +1)):
        rho, p = perm_p(sub[x], sub[y], sg if sg else +1)
        ex.append({"exploratory_check": lab, "n": len(sub), "spearman": rho, "p_one_sided": p})
    EX = pd.DataFrame(ex)
    EX.round(4).to_csv(ROOT / f"results/mef_scan_exploratory{'_legacyqc' if QC_MODE == 'legacy5x' else ''}.csv", index=False)
    print("\nEXPLORATORY (post hoc; does not change the verdict):")
    print(EX.round(3).to_string(index=False))

    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.4))
    inc = T[T.included]
    for a, m, lab in zip(ax, ("S_corr", "D_mad_pct"), ("profile correlation, train vs test (S)", "mean abs train-test difference, % (D)")):
        a.scatter(inc[~inc.arizona].A_absorption, inc[~inc.arizona][m], color="#1b6ca8", label="other BAs")
        a.scatter(inc[inc.arizona].A_absorption, inc[inc.arizona][m], color="#d1495b", label="Arizona BAs (motivated H1)")
        for _, r in inc.iterrows():
            a.annotate(r.ba, (r.A_absorption, r[m]), fontsize=7, xytext=(3, 3), textcoords="offset points")
        a.set_xlabel("absorption of demand changes by net interchange (A)"); a.set_ylabel(lab); a.grid(alpha=.25)
    ax[0].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(ROOT / f"results/figures/mef_scan{'_legacyqc' if QC_MODE == 'legacy5x' else ''}.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
