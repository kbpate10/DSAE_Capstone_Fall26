"""Exploratory data analysis: figures to results/figures/eda_*.png and key statistics to stdout."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results/figures"
BLUE, RED, GOLD, GREY, TEAL = "#1b6ca8", "#d1495b", "#edae49", "#8a8a8a", "#2a9d8f"
COL = {"AZPS": BLUE, "SRP": RED, "TEPC": GOLD, "WALC": TEAL}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
pd.set_option("display.width", 200)


def carbon():
    m = pd.read_parquet(ROOT / "data/processed/master_ba_hour.parquet")
    m = m[m.year >= 2021]  # local-time year includes 7 h of Dec-2020 at the series start
    fig, ax = plt.subplots(2, 3, figsize=(14, 7.5))
    # (a,b) hour x month heatmaps
    for a, ba in zip(ax[0, :2], ["AZPS", "SRP"]):
        h = m[m.respondent == ba].pivot_table(index="hour_local", columns="month", values="ci_kg_per_mwh")
        im = a.imshow(h.values, aspect="auto", origin="lower", cmap="RdYlBu_r")
        a.set_xticks(range(12)); a.set_xticklabels(range(1, 13)); a.set_xlabel("month"); a.set_ylabel("local hour")
        a.set_title(f"{ba}: mean carbon intensity by hour and month")
        plt.colorbar(im, ax=a, label="kg CO$_2$/MWh")
    # (c) annual trend
    a = ax[0, 2]
    t = m.groupby(["respondent", "year"]).ci_kg_per_mwh.mean().unstack(0)
    for ba in t: a.plot(t.index, t[ba], marker="o", color=COL[ba], label=ba)
    a.set_title("Annual mean carbon intensity"); a.set_ylabel("kg CO$_2$/MWh"); a.legend(frameon=False)
    a.set_xticks(range(2021, 2026))
    # (d) generation mix by year
    a = ax[1, 0]
    fuels = ["gen_COL_mwh", "gen_NG_mwh", "gen_NUC_mwh", "gen_SUN_mwh", "gen_WND_mwh", "gen_WAT_mwh"]
    w = m[m.respondent == "AZPS"].groupby("year")[fuels].sum().clip(lower=0)
    w = w.div(w.sum(axis=1), axis=0)
    bottom = np.zeros(len(w))
    for f, c in zip(fuels, [GREY, "#555555", "#8e6bbf", GOLD, TEAL, BLUE]):
        a.bar(w.index, w[f], bottom=bottom, color=c, label=f.split("_")[1]); bottom += w[f].values
    a.set_title("AZPS generation mix by year (share)"); a.legend(ncol=6, frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.06))
    # (e) autocorrelation
    a = ax[1, 1]
    for ba in ["AZPS", "SRP"]:
        s = m[m.respondent == ba].set_index("ts").ci_kg_per_mwh.asfreq("h")
        acf = [s.autocorr(l) for l in range(1, 200)]
        a.plot(range(1, 200), acf, color=COL[ba], label=ba)
    for l in (24, 48, 168): a.axvline(l, color=GREY, ls=":", lw=.8)
    a.set_title("Autocorrelation of carbon intensity (dotted: 24, 48, 168 h)"); a.set_xlabel("lag (hours)"); a.legend(frameon=False)
    # (f) data-quality flags
    a = ax[1, 2]
    f = m.assign(flag=m.data_flag.fillna(True).astype(bool)).groupby(["respondent", "year"]).flag.mean().unstack(0) * 100
    f.plot.bar(ax=a, color=[COL[c] for c in f.columns], width=.8)
    a.set_title("Share of BA-hours flagged (missing / null fuel), %"); a.set_xlabel(""); a.legend(title=None, frameon=False)
    fig.suptitle("EDA 1: Grid carbon intensity and generation mix (EIA-930 + eGRID, 2021-2025)", fontsize=12)
    fig.tight_layout(); fig.savefig(FIG / "eda_carbon.png", dpi=150); plt.close(fig)

    print("=== CARBON ===")
    print("annual mean CI:\n", t.round(0).to_string())
    print("diurnal range (max-min hourly mean, all years):",
          m.groupby(["respondent", "hour_local"]).ci_kg_per_mwh.mean().groupby("respondent").agg(lambda s: s.max() - s.min()).round(0).to_dict())
    print("ACF lag 1/24/168:", {ba: [round(m[m.respondent == ba].set_index("ts").ci_kg_per_mwh.asfreq("h").autocorr(l), 2) for l in (1, 24, 168)] for ba in ["AZPS", "SRP", "TEPC", "WALC"]})
    print("solar share of generation by year, AZPS:", (m[m.respondent == "AZPS"].groupby("year").gen_SUN_mwh.sum() / m[m.respondent == "AZPS"].groupby("year").gen_total_mwh.sum()).round(3).to_dict())
    print("solar share by year, SRP:", (m[m.respondent == "SRP"].groupby("year").gen_SUN_mwh.sum() / m[m.respondent == "SRP"].groupby("year").gen_total_mwh.sum()).round(3).to_dict())
    d = m.dropna(subset=["demand_mwh", "demand_forecast_mwh"])
    d = d[d.demand_mwh > 0]
    print("EIA day-ahead demand forecast MAPE % by BA:", (100 * ((d.demand_forecast_mwh - d.demand_mwh).abs() / d.demand_mwh).groupby(d.respondent).median()).round(1).to_dict(), "(median APE)")
    print("corr(wet-bulb, demand) by BA:", {ba: round(g.wetbulb_c.corr(g.demand_mwh), 2) for ba, g in m.groupby("respondent")})
    print("flagged share by BA:", (100 * m.data_flag.fillna(True).astype(bool).groupby(m.respondent).mean()).round(2).to_dict())
    print("negative-value share by fuel (SUN):", round((m.gen_SUN_mwh < 0).mean() * 100, 1), "%")


def reliability():
    u = pd.read_parquet(ROOT / "data/processed/master_utility_year.parquet")
    p = pd.read_parquet(ROOT / "data/processed/eia861_panel.parquet")
    rel = p[(p["_merge"] != "right_only")].copy()
    fig, ax = plt.subplots(2, 3, figsize=(14, 7.5))
    # (a) ln SAIDI by ownership
    a = ax[0, 0]
    own = u.dropna(subset=["ln_saidi_nomed"]).groupby("ownership").filter(lambda g: len(g) > 150)
    order = own.groupby("ownership").ln_saidi_nomed.median().sort_values().index
    a.boxplot([own[own.ownership == o].ln_saidi_nomed for o in order], tick_labels=[o[:14] for o in order], showfliers=False)
    a.set_title("log SAIDI (no major events) by ownership"); a.tick_params(axis="x", labelrotation=20)
    # (b) medians by year
    a = ax[0, 1]
    r = rel[rel.saidi_med.notna()]
    a.plot(*zip(*r.groupby("year").saidi_med.median().items()), marker="o", color=RED, label="with major events")
    a.plot(*zip(*r.groupby("year").saidi_nomed.median().items()), marker="o", color=BLUE, label="without")
    a.set_title("Median SAIDI by year (minutes)"); a.legend(frameon=False)
    # (c) missingness by year
    a = ax[0, 2]
    miss = r.groupby("year").saidi_nomed.apply(lambda s: s.isna().mean() * 100)
    a.bar(miss.index, miss.values, color=GOLD); a.set_title("SAIDI (no major events) missing, % of reporting utilities")
    # (d) SAIDI vs size
    a = ax[1, 0]
    q = u.dropna(subset=["ln_saidi_nomed", "ln_cust"])
    a.hexbin(q.ln_cust, q.ln_saidi_nomed, gridsize=40, cmap="Blues", mincnt=1)
    a.set_xlabel("ln customers"); a.set_ylabel("ln SAIDI"); a.set_title("Reliability vs utility size (noise falls with size)")
    # (e) exposure distribution
    a = ax[1, 1]
    x = u.d_ln_ci_pc.dropna()
    a.hist(x, bins=80, color=BLUE); a.axvline(0, color="k", lw=.7)
    a.set_title("Exposure: change in ln C&I MWh per customer"); a.set_xlabel("winsorised at 1/99 pct")
    # (f) AZ C&I load
    a = ax[1, 2]
    az = p[(p.state == "AZ") & p.util_name.isin(["Arizona Public Service Co", "Salt River Project", "Tucson Electric Power Co", "UNS Electric, Inc"])].copy()
    az["ci_twh"] = (az.com_mwh + az.ind_mwh) / 1e6
    for n, g in az.groupby("util_name"):
        g = g.sort_values("year"); a.plot(g.year, g.ci_twh, marker=".", label=n.replace(" Co", "").replace(", Inc", ""))
    a.set_title("Arizona C&I sales (TWh)"); a.legend(frameon=False, fontsize=7)
    fig.suptitle("EDA 2: Reliability and load panel (EIA-861, 2013-2024)", fontsize=12)
    fig.tight_layout(); fig.savefig(FIG / "eda_reliability.png", dpi=150); plt.close(fig)

    print("\n=== RELIABILITY PANEL ===")
    print("rows (cleaned):", len(u), "| utilities:", u.key.nunique(), "| years:", u.year.min(), "-", u.year.max())
    print("obs per utility: median", int(u.groupby("key").size().median()), "| share with all 12 yrs:", round((u.groupby("key").size() == 12).mean() * 100, 1), "%")
    print("ownership counts:", u.ownership.value_counts().to_dict())
    print("median SAIDI by ownership (no MED):", u.groupby("ownership").saidi_nomed.median().round(0).to_dict())
    print("SAIDI no-MED: quantiles", u.saidi_nomed.quantile([.05, .25, .5, .75, .95]).round(0).to_dict())
    print("with-MED/no-MED ratio median:", round((u.saidi_med / u.saidi_nomed).median(), 2))
    cs = u.dropna(subset=["ln_saidi_nomed", "ln_cust"])
    big = cs.ln_cust > cs.ln_cust.median()
    print("within-utility sd of ln SAIDI: large utilities %.2f vs small %.2f" % (
        cs[big].groupby("key").ln_saidi_nomed.std().mean(), cs[~big].groupby("key").ln_saidi_nomed.std().mean()))
    print("exposure: sd %.3f | share > +10%%: %.1f%% | share > +20%%: %.1f%%" % (x.std(), (x > .10).mean() * 100, (x > .20).mean() * 100))
    print("exposure by year (mean, share>10%):", u.groupby("year").d_ln_ci_pc.agg(lambda s: f"{s.mean():+.3f}, {(s>.1).mean()*100:.1f}%").to_dict())
    print("AZ C&I TWh 2020 -> 2024:", {n: (round(g.set_index('year').ci_twh.get(2020, np.nan), 1), round(g.set_index('year').ci_twh.get(2024, np.nan), 1)) for n, g in az.groupby("util_name")})


def water_queue():
    g = pd.read_parquet(ROOT / "data/raw/rq2/adwr_gwsi_sites.parquet")
    q = pd.read_parquet(ROOT / "data/processed/lbnl_queue_all.parquet")
    s = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet")
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.4))
    a = ax[0]
    r = g[(g.LASTWLDATE.dt.year >= 2015) & (g.WL_DTW > 0)]
    boxes = {"Phoenix metro": (33.2, 33.7, -112.5, -111.6), "Pinal / Casa Grande": (32.6, 33.1, -112.1, -111.2),
             "Tucson": (31.9, 32.5, -111.2, -110.6)}
    bins = np.logspace(0, 3.3, 45)
    a.hist(r.WL_DTW, bins=bins, color=GREY, alpha=.5, density=True, label="all AZ")
    for (n, (la0, la1, lo0, lo1)), c in zip(boxes.items(), [BLUE, RED, TEAL]):
        b = r[r.DD_LAT.between(la0, la1) & r.DD_LONG.between(lo0, lo1)]
        a.hist(b.WL_DTW, bins=bins, histtype="step", lw=2, color=c, density=True, label=f"{n} (n={len(b)})")
    a.set_xscale("log"); a.set_xlabel("depth to water (ft, log)"); a.set_title("Groundwater depth, wells measured since 2015"); a.legend(frameon=False, fontsize=7)
    a = ax[1]
    yr = g.LASTWLDATE.dt.year.dropna().astype(int)
    a.hist(yr[yr >= 1980], bins=np.arange(1980, 2027), color=BLUE)
    a.set_title("Year of last water-level measurement (GWSI sites)"); a.set_xlabel("year")
    a = ax[2]
    z = q[q.state == "AZ"].copy(); z["mw"] = z[["mw_1", "mw_2", "mw_3"]].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    t = z.pivot_table(index="type_clean", columns="q_status", values="mw", aggfunc="sum").fillna(0) / 1000
    t = t.loc[t.sum(axis=1).sort_values().index].tail(7)
    t.plot.barh(stacked=True, ax=a, color=[BLUE, GREY, GOLD, RED][:t.shape[1]], width=.75)
    a.set_title("AZ generator queue by type (GW)"); a.set_ylabel(""); a.legend(frameon=False, fontsize=7)
    fig.suptitle("EDA 3: Groundwater coverage and the generator interconnection queue", fontsize=12)
    fig.tight_layout(); fig.savefig(FIG / "eda_water_queue.png", dpi=150); plt.close(fig)

    print("\n=== WATER / QUEUE ===")
    print("GWSI sites:", len(g), "| last measured since 2015:", int((g.LASTWLDATE.dt.year >= 2015).sum()),
          "| before 2000:", int((g.LASTWLDATE.dt.year < 2000).sum()))
    print("depth-to-water (since 2015) quantiles ft:", r.WL_DTW.quantile([.1, .25, .5, .75, .9]).round(0).to_dict())
    for n, (la0, la1, lo0, lo1) in boxes.items():
        b = r[r.DD_LAT.between(la0, la1) & r.DD_LONG.between(lo0, lo1)]
        print(f"  {n}: n={len(b)} median depth {b.WL_DTW.median():.0f} ft, p90 {b.WL_DTW.quantile(.9):.0f} ft")
    print("negative depth (flowing) share:", round((g.WL_DTW < 0).mean() * 100, 1), "% | zero:", round((g.WL_DTW == 0).mean() * 100, 1), "%")
    print("AZ queue GW by status:", (z.groupby("q_status").mw.sum() / 1000).round(1).to_dict())
    print("AZ active queue GW by type:", (z[z.q_status == "active"].groupby("type_clean").mw.sum() / 1000).round(1).sort_values(ascending=False).head(6).to_dict())
    print("AZ queue entries by status:", z.q_status.value_counts().to_dict(), "| withdrawn share: %.0f%%" % (100 * (z.q_status == "withdrawn").mean()))
    print("candidate cells score: mean %.2f sd %.2f | corr(depth, wetbulb) %.2f | corr(depth, queue) %.2f | corr(ghi, wetbulb) %.2f" % (
        s.score.mean(), s.score.std(), s.gw_depth_med.corr(s.wetbulb_summer_c), s.gw_depth_med.corr(s.q_active_mw), s.ghi_kwh.corr(s.wetbulb_summer_c)))


if __name__ == "__main__":
    carbon(); reliability(); water_queue()
