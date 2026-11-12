"""RQ3 with a data-center-specific exposure: mapped data centers per utility territory x the post-2019 period.

The EIA-861 proxy (C&I sales per customer) cannot tell data centers from other load. Here each utility gets a time-invariant
data-center exposure from OpenStreetMap, interacted with a post period, in a utility + state-by-year fixed-effects panel.

Construction
  * data centers: data/raw/osm_dc_us.parquet (pull_osm_datacenters_us.py); territories: data/raw/territories_us.geojson (pull_territories_us.py).
  * each data center goes to the smallest-area retail territory that contains it AND belongs to a utility in the RQ3 panel
    ("most specific wins", as in build_territories.py); points inside no such territory are dropped and counted.
  * exposure: any_dc = 1 if the territory holds at least one mapped data center; dc_per100k = mapped data centers per 100,000 customers
    (log1p used in the model). OSM has no opening dates, so exposure is a cross-section; time enters through post = year >= 2019
    (named before looking at results; 2018, 2020 and a linear trend are reported as robustness).
  * multi-state utilities: the count is attached to every state row of the utility (the territory polygon is not split by state).

Models (rq3_model.fit: utility effects + state-by-year effects, SEs clustered by utility)
  FS  first stage     d_ln_ci_pc ~ exposure x post          (is data-center presence tied to faster C&I growth after 2019?)
  RF  reduced form    ln SAIDI (no major events) ~ exposure x post
  HET heterogeneity   ln SAIDI ~ d_ln_ci_pc + d_ln_ci_pc x any_dc    (does load growth matter more where data centers sit?)
  Size control: the same FS and RF with baseline log customers x post, because utilities with mapped data centers are much larger.
  A Wald ratio RF / FS is NOT reported unless the first stage is strong (F > 10), because a ratio with a weak first stage is not interpretable.

Limits: OSM completeness varies by region; mapped facilities include enterprise rooms and mis-tagged businesses, and hyperscale campuses may be one
polygon or absent; there are no opening dates, so exposure x post assumes data-center growth is concentrated after 2019; the exposure is
time-invariant, so it measures where data centers are, not when load arrived.

Outputs: data/processed/dc_by_utility.parquet, results/rq3_dc_exposure.csv, results/rq3_dc_descriptives.csv
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rq3_model as m

CTL = ["d_ln_cust", "ln_cust"]
Y = "ln_saidi_nomed"
POST_YEAR = 2019


def assign_data_centers(retail_ids: set) -> tuple[pd.DataFrame, dict]:
    g = json.load(open(ROOT / "data/raw/territories_us.geojson"))["features"]
    geoms, ids = [], []
    for f in g:
        try:
            geom = shape(f["geometry"])
            geom = geom if geom.is_valid else geom.buffer(0)
            uid = int(f["properties"]["id"])
        except Exception:
            continue
        if uid in retail_ids and not geom.is_empty:
            geoms.append(geom)
            ids.append(uid)
    areas = np.array([x.area for x in geoms])
    tree = STRtree(geoms)
    dc = pd.read_parquet(ROOT / "data/raw/osm_dc_us.parquet")
    pts = [Point(x, y) for x, y in zip(dc.lon, dc.lat)]
    pi, gi = tree.query(pts, predicate="within")
    hit = pd.DataFrame({"pt": pi, "geom": gi, "area": areas[gi], "util": np.array(ids)[gi]})
    best = hit.sort_values("area").groupby("pt").head(1)
    dc["util_num"] = np.nan
    dc.loc[dc.index[best.pt.values], "util_num"] = best.util.values
    info = {"features": len(dc), "assigned": int(dc.util_num.notna().sum()), "territories_used": len(geoms)}
    return dc, info


def main() -> None:
    p = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet")
    p["util_num"] = p.key.str.split("_").str[0].astype(int)
    dc, info = assign_data_centers(set(p.util_num))
    print(f"OSM data centers: {info['features']}, assigned to a panel utility: {info['assigned']} ({100 * info['assigned'] / info['features']:.0f}%), "
          f"territories used: {info['territories_used']}")
    cnt = dc.dropna(subset=["util_num"]).groupby("util_num").size().rename("n_dc")
    cust = p.sort_values("year").groupby("util_num").total_cust.last().rename("customers")
    U = pd.concat([cust, cnt], axis=1).fillna({"n_dc": 0})
    U["dc_per100k"] = U.n_dc / (U.customers / 1e5)
    U["any_dc"] = (U.n_dc >= 1).astype(float)
    U["ln_dc"] = np.log1p(U.dc_per100k)
    U.reset_index().to_parquet(ROOT / "data/processed/dc_by_utility.parquet", index=False)
    print(f"panel utilities (ids): {len(U)}; with >= 1 mapped data center: {int(U.any_dc.sum())}; total mapped in them: {int(U.n_dc.sum())}")

    q = p.merge(U[["any_dc", "ln_dc", "n_dc"]], left_on="util_num", right_index=True, how="left")
    q["any_post"] = q.any_dc * (q.year >= POST_YEAR)
    q["ln_dc_post"] = q.ln_dc * (q.year >= POST_YEAR)
    q["any_post2018"] = q.any_dc * (q.year >= 2018)
    q["any_post2020"] = q.any_dc * (q.year >= 2020)
    q["any_trend"] = q.any_dc * (q.year - 2018).clip(lower=0)
    q["dc_x_growth"] = q.any_dc * q.d_ln_ci_pc
    # size confound: utilities with data centers are much larger; let size have its own post-2019 shift
    q["ln_cust_base"] = q.groupby("key").ln_cust.transform("first")
    q["size_post"] = q.ln_cust_base * (q.year >= POST_YEAR)

    # descriptives: C&I growth and surges by group and period
    d = q.dropna(subset=["d_ln_ci_pc_raw"])
    rows = []
    for g, lab in ((1, "utilities with a mapped data center"), (0, "utilities without")):
        for per, sel in (("2014-2018", d.year <= 2018), ("2019-2024", d.year >= 2019)):
            s = d[(d.any_dc == g) & sel]
            rows.append({"group": lab, "period": per, "utility_years": len(s), "utilities": s.key.nunique(),
                         "mean_ci_growth_pc": s.d_ln_ci_pc_raw.mean(), "share_growth_gt_25pct": (s.d_ln_ci_pc_raw > 0.25).mean(),
                         "share_growth_gt_50pct": (s.d_ln_ci_pc_raw > 0.50).mean()})
    Dd = pd.DataFrame(rows)
    Dd.round(4).to_csv(ROOT / "results/rq3_dc_descriptives.csv", index=False)
    pd.set_option("display.width", 220)
    print("\nC&I growth by group and period (log points per year; raw, unclipped):")
    print(Dd.round(4).to_string(index=False))
    big = d[d.d_ln_ci_pc_raw > 0.5]
    print(f"\nthe {len(big)} utility-years with growth above 50%: {int((big.any_dc == 1).sum())} are in utilities with a mapped data center "
          f"(group share of all panel utility-years: {100 * d.any_dc.mean():.0f}%)")

    res = []

    def run(label, y, xs, key, df=q):
        r, dd = m.fit(df, y, xs, "state_year")
        b, se = r.params[key], r.std_errors[key]
        F = (b / se) ** 2
        res.append({"model": label, "outcome": y, "term": key, "coef": b, "se": se, "lo": b - 1.96 * se, "hi": b + 1.96 * se,
                    "p": r.pvalues[key], "F_like": F, "n": int(r.nobs), "utilities": int(r.entity_info["total"]),
                    "dc_utilities": int(dd[dd.any_dc == 1].index.get_level_values(0).nunique())})
        return b, se

    for lab, term in (("post2019, any data center", "any_post"), ("post2019, log1p per 100k customers", "ln_dc_post"),
                      ("post2018, any data center", "any_post2018"), ("post2020, any data center", "any_post2020"),
                      ("linear trend since 2018, any data center", "any_trend")):
        run(f"FS first stage: {lab}", "d_ln_ci_pc", [term] + CTL, term)
        run(f"FS first stage (unclipped growth): {lab}", "d_ln_ci_pc_raw", [term] + CTL, term)
        run(f"RF reduced form: {lab}", Y, [term] + CTL, term)
    run("FS first stage + size x post: post2019, any data center", "d_ln_ci_pc", ["any_post", "size_post"] + CTL, "any_post")
    run("RF reduced form + size x post: post2019, any data center", Y, ["any_post", "size_post"] + CTL, "any_post")
    run("RF reduced form + size x post: post2019, log1p per 100k customers", Y, ["ln_dc_post", "size_post"] + CTL, "ln_dc_post")
    run("HET load growth x data-center utility", Y, ["d_ln_ci_pc", "dc_x_growth"] + CTL, "dc_x_growth")
    run("HET load growth (main term, same model)", Y, ["d_ln_ci_pc", "dc_x_growth"] + CTL, "d_ln_ci_pc")
    R = pd.DataFrame(res)
    R.round(4).to_csv(ROOT / "results/rq3_dc_exposure.csv", index=False)
    print("\nEstimates (utility + state-by-year effects, clustered by utility):")
    print(R[["model", "term", "coef", "se", "lo", "hi", "p", "n", "dc_utilities"]].round(4).to_string(index=False))
    fs = R[(R.model.str.startswith("FS first stage:")) & (R.term == "any_post")].iloc[0]
    print(f"\nprimary first stage (any data center x post{POST_YEAR}): coefficient {fs.coef:.4f}, t = {fs.coef / fs.se:.2f}, F-like = {fs.F_like:.1f}"
          f" -> {'strong enough to report a Wald ratio' if fs.F_like > 10 else 'weak: no Wald ratio reported'}")


if __name__ == "__main__":
    main()
