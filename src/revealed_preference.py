"""Revealed-preference siting: what distinguishes places where data centers actually exist?

Unit: 0.05-degree cells (about 5 km) whose centre lies inside a retail service territory of an Arizona utility
(the plausible domain for a new connection). Presence = a cell containing >= 1 OpenStreetMap-mapped data center.

Features (all computed per cell centre; none is a constructed label):
  log_pop_10km   log(1 + 2020 census population of tracts whose centroid is within 10 km)
  dist_sub_km    km to nearest mapped substation (OSM)
  dist_hv_km     km to nearest substation tagged >= 115 kV (OSM; voltage tag is often missing)
  gw_depth_ft    median depth to water of the 5 nearest ADWR GWSI sites measured since 2015
  wetbulb_c      summer wet-bulb (NASA POWER, nearest of the 192 climate points; coarse)
  ghi_kwh        solar irradiance (same source)
Models: logistic regression (L2, balanced classes) on three feature sets - environmental only, infrastructure
only, and both. Validation: repeated random CV and spatial-block CV (0.5-degree blocks). With few positives,
all positives in one metro area, intervals are wide: read coefficients and AUCs with that in mind.

Outputs: data/processed/fine_cells_features.parquet, results/revealed_*.csv
"""
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, RepeatedStratifiedKFold
from sklearn.neighbors import BallTree
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
STEP = 0.05
LAT0, LAT1, LON0, LON1 = 31.3, 37.0, -114.85, -109.0
R = 6371.0


def haversine_tree(lat, lon):
    return BallTree(np.radians(np.column_stack([lat, lon])), metric="haversine")


def build_cells():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import build_territories as bt
    feats = json.load(open(ROOT / "data/raw/rq2/territories_az.geojson"))["features"]
    keep = bt.az_retail_ids() - bt.WHOLESALE_IDS
    geoms, uids = [], []
    for f in feats:
        try:
            u = int(f["properties"]["id"])
        except (TypeError, ValueError):
            continue
        if u in keep and f.get("geometry"):
            g = shape(f["geometry"]); g = g if g.is_valid else g.buffer(0)
            geoms.append(g); uids.append(u)
    tree = STRtree(geoms)
    lats = np.arange(LAT0, LAT1, STEP) + STEP / 2
    lons = np.arange(LON0, LON1, STEP) + STEP / 2
    rows = []
    for la in lats:
        for lo in lons:
            pt = Point(lo, la)
            cand = [i for i in tree.query(pt) if geoms[i].contains(pt)]
            if cand:
                rows.append({"lat": la, "lon": lo, "util_num": uids[min(cand, key=lambda i: geoms[i].area)]})
    return pd.DataFrame(rows)


def add_features(c: pd.DataFrame) -> pd.DataFrame:
    xy = np.radians(c[["lat", "lon"]].values)
    # population
    t = pd.read_parquet(ROOT / "data/raw/rq2/tracts_az_pop.parquet")
    tt = haversine_tree(t.INTPTLAT.values, t.INTPTLON.values)
    idx = tt.query_radius(xy, r=10 / R)
    c["log_pop_10km"] = [np.log1p(t.POP100.values[i].sum()) for i in idx]
    # substations
    subs = json.load(open(ROOT / "data/raw/rq2/osm_substations_az.json"))
    S = []
    for e in subs:
        ctr = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        v = [int(x) for x in re.findall(r"\d+", str(e.get("tags", {}).get("voltage", "")))]
        S.append({"lat": ctr["lat"], "lon": ctr["lon"], "kv": (max(v) / 1000 if v else np.nan)})
    S = pd.DataFrame(S).dropna(subset=["lat", "lon"])
    d, _ = haversine_tree(S.lat.values, S.lon.values).query(xy, k=1)
    c["dist_sub_km"] = d[:, 0] * R
    H = S[S.kv >= 115]
    d, _ = haversine_tree(H.lat.values, H.lon.values).query(xy, k=1)
    c["dist_hv_km"] = d[:, 0] * R
    # groundwater depth: 5 nearest recently measured GWSI sites
    g = pd.read_parquet(ROOT / "data/raw/rq2/adwr_gwsi_sites.parquet")
    g = g[(g.LASTWLDATE.dt.year >= 2015) & g.DD_LAT.notna() & (g.WL_DTW > 0)]
    d, i = haversine_tree(g.DD_LAT.values, g.DD_LONG.values).query(xy, k=5)
    c["gw_depth_ft"] = np.median(g.WL_DTW.values[i], axis=1)
    # climate (coarse): nearest of the 192 climate points
    s = pd.read_parquet(ROOT / "data/processed/sites_az.parquet")
    d, i = haversine_tree(s.lat.values, s.lon.values).query(xy, k=1)
    c["wetbulb_c"] = s.wetbulb_summer_c.values[i[:, 0]]
    c["ghi_kwh"] = s.ghi_kwh.values[i[:, 0]]
    c["coarse_cell"] = [f"{int(np.floor(la/0.25))}_{int(np.floor(lo/0.25))}" for la, lo in zip(c.lat, c.lon)]
    c["block"] = [f"{int(np.floor(la/0.5))}_{int(np.floor(lo/0.5))}" for la, lo in zip(c.lat, c.lon)]
    return c


def presence(c, subset="all"):
    o = pd.read_parquet(ROOT / "data/raw/rq2/osm_datacenters_az.parquet")
    if subset == "operator":
        o = o[o.operator.notna()]
    key = lambda la, lo: (np.floor((la - LAT0) / STEP).astype(int), np.floor((lo - LON0) / STEP).astype(int))
    oi, oj = key(o.lat.values, o.lon.values)
    ci, cj = key(c.lat.values, c.lon.values)
    hosts = set(zip(oi, oj))
    return np.array([(a, b) in hosts for a, b in zip(ci, cj)]).astype(int)


def evaluate(X, y, groups, name, rows):
    pipe = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000))
    aucs = []
    for tr, te in RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=0).split(X, y):
        m = pipe().fit(X[tr], y[tr]); aucs.append(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1]))
    sp = []
    for tr, te in GroupKFold(n_splits=6).split(X, y, groups):
        if y[te].sum() == 0 or y[tr].sum() == 0:
            continue
        m = pipe().fit(X[tr], y[tr]); sp.append(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1]))
    rows.append({"model": name, "auc_random_cv": np.mean(aucs), "auc_random_sd": np.std(aucs),
                 "auc_spatial_block_cv": np.mean(sp) if sp else np.nan, "n_spatial_folds": len(sp)})


def main() -> None:
    c = add_features(build_cells())
    c.to_parquet(ROOT / "data/processed/fine_cells_features.parquet", index=False)
    print(f"fine cells inside AZ retail territories: {len(c)}")
    env = ["gw_depth_ft", "wetbulb_c", "ghi_kwh"]
    inf = ["log_pop_10km", "dist_sub_km", "dist_hv_km"]
    out_rows, coef_rows = [], []
    for subset in ("all", "operator"):
        y = presence(c, subset)
        print(f"\n--- positives ({subset}): {int(y.sum())} cells of {len(c)} | in blocks: {c.block[y == 1].nunique()}")
        print("   share of positive cells in Maricopa-metro box (33.0-33.9N, 112.7-111.5W):",
              round(float(((c.lat[y == 1].between(33.0, 33.9)) & (c.lon[y == 1].between(-112.7, -111.5))).mean()), 2))
        rows = []
        for name, feats in (("environmental only", env), ("infrastructure only", inf), ("both", env + inf)):
            X = c[feats].values
            evaluate(X, y, c.block.values, name, rows)
        r = pd.DataFrame(rows).assign(positives=subset)
        out_rows.append(r)
        # coefficients with bootstrap CIs (full model)
        X = c[env + inf].values
        rng = np.random.default_rng(0)
        co = []
        pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
        for _ in range(300):
            ix = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, min(len(neg), 4000))])
            m = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000)).fit(X[ix], y[ix])
            co.append(m[-1].coef_[0])
        co = np.array(co)
        for k, f in enumerate(env + inf):
            coef_rows.append({"positives": subset, "feature": f, "coef_std": np.mean(co[:, k]),
                              "lo": np.percentile(co[:, k], 2.5), "hi": np.percentile(co[:, k], 97.5)})
        print(r.round(3).to_string(index=False))
    pd.concat(out_rows).to_csv(ROOT / "results/revealed_auc.csv", index=False)
    C = pd.DataFrame(coef_rows); C.to_csv(ROOT / "results/revealed_coefficients.csv", index=False)
    print("\nStandardised logistic coefficients (all positives), 95% bootstrap interval:")
    print(C[C.positives == "all"].round(2).to_string(index=False))

    # does the constructed environmental score separate hosts from non-hosts?
    sc = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    y = presence(c, "all")
    s = c.coarse_cell.map(sc.score)
    m = s.notna()
    print(f"\nAUC of the constructed environmental score for 'is a host cell' (0.5 = no info, <0.5 = hosts score LOWER): "
          f"{roc_auc_score(y[m], s[m]):.2f}  (n cells with a score: {int(m.sum())}, positives: {int(y[m].sum())})")

    # propensity (no environmental features) for Stage 1 feasibility
    X = c[inf].values
    mdl = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000)).fit(X, y)
    c["propensity"] = mdl.predict_proba(X)[:, 1]
    q = c.propensity.quantile(0.90)
    agg = c.groupby("coarse_cell").agg(fine_cells=("lat", "size"), propensity_mean=("propensity", "mean"),
                                       propensity_max=("propensity", "max"),
                                       share_top10=("propensity", lambda s: (s >= q).mean()),
                                       hosts=("propensity", lambda s: 0))
    agg["hosts"] = pd.Series(y, index=c.index).groupby(c.coarse_cell).sum()
    agg.to_csv(ROOT / "results/revealed_cell_propensity.csv")
    print("\ntop coarse cells by mean propensity (infrastructure features only):")
    top = agg.sort_values("propensity_mean", ascending=False).head(8).join(sc[["county_short", "score", "rank"]])
    print(top.round(2).to_string())
    print("\ncorrelation between environmental score and infrastructure propensity (coarse cells):",
          round(float(agg.join(sc.score, how="inner")[["propensity_mean", "score"]].corr().iloc[0, 1]), 2))


if __name__ == "__main__":
    main()
