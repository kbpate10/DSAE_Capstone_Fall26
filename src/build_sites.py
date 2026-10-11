"""Candidate-site table for RQ2: 0.25-degree cells over Arizona with water, solar and grid features.

Cells are kept if they hold >= 5 ADWR GWSI sites with a depth-to-water measured since 2015
(a site with no groundwater data cannot be scored). Features:
  gw_depth_med   median latest depth-to-water (ft), GWSI sites measured since 2015 (deeper = more stressed)
  gw_trend       median per-well trend (ft/yr, + = water level falling) from USGS-hosted ADWR series;
                 NaN where < 2 wells have a usable series (kept NaN, flagged, not imputed)
  ghi_kwh        all-sky surface shortwave, annual mean at the cell centre (NASA POWER climatology)
  wetbulb_c      annual mean wet-bulb temp (NASA POWER T2MWET), for the water model
  q_active_mw    active generation-queue MW (sum of mw_1..mw_3) in the cell's county (LBNL), a COUNTY-level proxy
  q_active_n     number of active queue entries in the county
Output: data/processed/sites_az.parquet
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.neighbors import BallTree

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/rq2"
STEP = 0.25


def cell_ids(lat, lon):
    return np.floor(lat / STEP).astype(int), np.floor(lon / STEP).astype(int)


def gw_features() -> pd.DataFrame:
    g = pd.read_parquet(RAW / "adwr_gwsi_sites.parquet")
    g = g[(g.LASTWLDATE.dt.year >= 2015) & g.DD_LAT.notna()].copy()
    g["ci"], g["cj"] = cell_ids(g.DD_LAT.values, g.DD_LONG.values)
    agg = g.groupby(["ci", "cj"]).agg(n_sites=("WL_DTW", "size"), gw_depth_med=("WL_DTW", "median"),
                                      lat=("DD_LAT", "median"), lon=("DD_LONG", "median")).reset_index()
    return agg[agg.n_sites >= 5]


def trend_features() -> pd.DataFrame:
    s = pd.read_parquet(RAW / "gw_levels_az.parquet").merge(pd.read_parquet(RAW / "wells_geo.parquet"), on="site")
    s = s[s.depth_ft.notna() & (s.depth_ft >= 0)].copy()
    s["yr"] = s.time.dt.year + s.time.dt.dayofyear / 365.25
    rows = []
    for site, d in s.groupby("site"):
        if len(d) >= 3 and d.yr.max() - d.yr.min() >= 5:
            b = np.polyfit(d.yr, d.depth_ft, 1)[0]
            if abs(b) < 50:  # drop obvious artifacts
                rows.append((site, d.lat.iloc[0], d.lon.iloc[0], b))
    t = pd.DataFrame(rows, columns=["site", "lat", "lon", "slope"])
    t["ci"], t["cj"] = cell_ids(t.lat.values, t.lon.values)
    return t.groupby(["ci", "cj"]).agg(gw_trend=("slope", "median"), n_trend=("slope", "size")).reset_index()


def solar(cells: pd.DataFrame) -> pd.DataFrame:
    """Per-cell climatology from NASA POWER (no key). Native resolution (~0.5-1 deg) is coarser than the
    0.25-deg cells, so neighbouring cells can share values. Cached incrementally."""
    cache = RAW / "cell_climate_nasa.parquet"
    done = pd.read_parquet(cache) if cache.exists() else pd.DataFrame(columns=["ci", "cj"])
    have = set(zip(done.ci, done.cj))
    todo = [r for r in cells.itertuples() if (r.ci, r.cj) not in have]
    print(f"climate: {len(have)} cached, {len(todo)} to fetch", flush=True)
    out = done.to_dict("records")
    for k, r in enumerate(todo):
        lat, lon = (r.ci + 0.5) * STEP, (r.cj + 0.5) * STEP
        params = {"parameters": "ALLSKY_SFC_SW_DWN,T2M,T2MWET", "community": "RE",
                  "latitude": lat, "longitude": lon, "format": "JSON"}
        for a_ in range(8):
            resp = requests.get("https://power.larc.nasa.gov/api/temporal/climatology/point",
                                params=params, timeout=120)
            if resp.status_code == 200:
                break
            time.sleep(5 * (a_ + 1))
        resp.raise_for_status()
        p_ = resp.json()["properties"]["parameter"]
        summer = lambda v: np.mean([v["JUN"], v["JUL"], v["AUG"]])
        out.append({"ci": r.ci, "cj": r.cj, "ghi_kwh": p_["ALLSKY_SFC_SW_DWN"]["ANN"],
                    "wetbulb_c": p_["T2MWET"]["ANN"], "wetbulb_summer_c": summer(p_["T2MWET"]),
                    "temp_c": p_["T2M"]["ANN"]})
        pd.DataFrame(out).to_parquet(cache, index=False)
        if k % 25 == 0:
            print(f"  {k + 1}/{len(todo)}", flush=True)
        time.sleep(0.2)
    return pd.DataFrame(out)


def queue_by_county() -> pd.DataFrame:
    q = pd.read_parquet(ROOT / "data/processed/lbnl_queue_all.parquet")
    q = q[(q.state == "AZ")].copy()
    # mw_1..mw_3 are the capacities of up to three resource types of one (hybrid) project: total = sum
    q["mw"] = q[["mw_1", "mw_2", "mw_3"]].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    q["county"] = q.county.replace({"Mojave": "Mohave"})   # typo variant present in the LBNL file
    act = q[q.q_status == "active"]
    a = act.groupby("county").agg(q_active_mw=("mw", "sum"), q_active_n=("mw", "size"))
    tot = q.groupby("county").agg(q_total_n=("mw", "size"))
    return a.join(tot, how="outer").fillna(0).reset_index().rename(columns={"county": "county_name_short"})


def county_by_point(cells: pd.DataFrame) -> pd.Series:
    """Point-in-polygon county via Census TIGERweb (replaces nearest-USGS-well labelling, which was up to
    ~100 km off and could not see counties with no wells in the USGS list). Cached per cell."""
    cache = RAW / "cell_county_tiger.parquet"
    have = pd.read_parquet(cache) if cache.exists() else pd.DataFrame(columns=["cell_id", "county_tiger"])
    done = dict(zip(have.cell_id, have.county_tiger))
    for r in cells.itertuples():
        cid = f"{r.ci}_{r.cj}"
        if cid in done:
            continue
        params = {"geometry": f"{r.lon},{r.lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                  "spatialRel": "esriSpatialRelIntersects", "outFields": "NAME", "returnGeometry": "false", "f": "json"}
        for a in range(6):
            resp = requests.get("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/11/query",
                                params=params, timeout=60)
            if resp.status_code == 200 and "features" in resp.json():
                break
            time.sleep(3 * (a + 1))
        feats = resp.json().get("features", [])
        done[cid] = feats[0]["attributes"]["NAME"].replace(" County", "") if feats else None
    pd.DataFrame({"cell_id": list(done), "county_tiger": list(done.values())}).to_parquet(cache, index=False)
    return pd.Series([done[f"{r.ci}_{r.cj}"] for r in cells.itertuples()], index=cells.index)


def main() -> None:
    cells = gw_features().merge(trend_features(), on=["ci", "cj"], how="left")
    cells = cells.merge(solar(cells), on=["ci", "cj"], how="left")
    cells["county_short"] = county_by_point(cells)
    cells["county"] = cells.county_short + " County"
    cells = cells.merge(queue_by_county(), left_on="county_short", right_on="county_name_short", how="left")
    for c in ["q_active_mw", "q_active_n", "q_total_n"]:
        cells[c] = cells[c].fillna(0)
    cells["cell_id"] = cells.ci.astype(str) + "_" + cells.cj.astype(str)
    cells.to_parquet(ROOT / "data/processed/sites_az.parquet", index=False)
    pd.set_option("display.width", 220)
    print("candidate cells:", len(cells), "| with trend:", cells.gw_trend.notna().sum())
    print(cells.groupby("county_short").agg(cells=("cell_id", "size"), depth=("gw_depth_med", "median"),
          ghi=("ghi_kwh", "mean"), tw=("wetbulb_summer_c", "mean"), q_mw=("q_active_mw", "first"),
          trend=("gw_trend", "median")).round(1).to_string())
    print(cells[["gw_depth_med", "gw_trend", "ghi_kwh", "wetbulb_summer_c", "q_active_mw"]].describe().round(1).to_string())


if __name__ == "__main__":
    main()
