"""Link candidate cells to serving electric utilities via retail service-territory polygons.

Source: HIFLD Electric Retail Service Territories, PNNL-hosted ArcGIS layer (attribute `id` = EIA utility number).
Territories overlap and include wholesale entities, so:
  * polygons intersecting Arizona are fetched in full;
  * only utilities that report retail sales in Arizona in EIA-861 (Parts A/C, 2024) are kept;
  * for each 0.25-degree cell, the share of the cell's area inside each kept territory is computed
    (shares are normalised across kept utilities, because overlapping territories would otherwise sum above 1).
Cells with no kept territory are flagged (no retail utility, treated as ineligible downstream).

Two mappings are written because HIFLD uses generic, identically sized polygons for several small districts:
  cell_utility_shares_all.parquet    every AZ retail utility with sales in EIA-861
  cell_utility_shares_large.parquet  only utilities with >= 500 GWh of 2024 retail sales (cells fall back to the
                                     next most specific territory, usually APS)
Outputs: data/raw/rq2/territories_az.geojson, data/processed/cell_utility_shares_{all,large}.parquet
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, box, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
URL = "https://eedgis.pnnl.gov/arcgis/rest/services/Hosted/Electric_Service_Territories/FeatureServer/0/query"
STEP = 0.25
BBOX = "-114.9,31.3,-108.9,37.1"


def fetch() -> list[dict]:
    cache = ROOT / "data/raw/rq2/territories_az.geojson"
    if cache.exists():
        return json.load(open(cache))["features"]
    feats, offset = [], 0
    while True:
        params = {"where": "1=1", "geometry": BBOX, "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                  "spatialRel": "esriSpatialRelIntersects", "outFields": "id,name,state,type,customers,retail_mwh,cntrl_area",
                  "outSR": 4326, "returnGeometry": "true", "f": "geojson", "resultOffset": offset, "resultRecordCount": 50}
        for a in range(6):
            r = requests.get(URL, params=params, timeout=180)
            if r.status_code == 200 and "features" in r.json():
                break
            time.sleep(5 * (a + 1))
        got = r.json()["features"]
        feats += got
        print(f"  fetched {len(feats)}", flush=True)
        if len(got) < 50:
            break
        offset += 50
    json.dump({"type": "FeatureCollection", "features": feats}, open(cache, "w"))
    return feats


def az_retail_ids() -> set[int]:
    p = pd.read_parquet(ROOT / "data/processed/eia861_panel.parquet")
    a = p[(p.state == "AZ") & (p.year == 2024) & p.total_mwh.notna() & (p.total_mwh > 0)]
    return set(a.util_num.dropna().astype(int))


WHOLESALE_IDS = {27000}  # WAPA marketing area (165 sq-degrees): a wholesale marketer, not a retail distributor


def az_sales_gwh() -> pd.Series:
    p = pd.read_parquet(ROOT / "data/processed/eia861_panel.parquet")
    a = p[(p.state == "AZ") & (p.year == 2024) & p.total_mwh.notna()]
    return a.groupby(a.util_num.astype(int)).total_mwh.sum() / 1000.0


def shares(feats, keep, tag):
    geoms, meta = [], []
    for f in feats:
        try:
            uid = int(f["properties"]["id"])
        except (TypeError, ValueError):
            continue
        if uid in keep and f.get("geometry"):
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            geoms.append(g)
            meta.append({"util_num": uid, "util_name": f["properties"]["name"], "poly_area": g.area})
    tree = STRtree(geoms)
    cells = pd.read_parquet(ROOT / "data/processed/sites_az.parquet")
    offs = (np.arange(5) + 0.5) / 5 * STEP   # most-specific-territory rule on a 5x5 grid of points per cell
    rows = []
    for c in cells.itertuples():
        hits = []
        for dy in offs:
            for dx in offs:
                pt = Point(c.cj * STEP + dx, c.ci * STEP + dy)
                cand = [i for i in tree.query(pt) if geoms[i].contains(pt)]
                hits.append(meta[min(cand, key=lambda i: meta[i]["poly_area"])]["util_num"] if cand else None)
        for u, n in pd.Series(hits, dtype="object").value_counts(dropna=False).items():
            rows.append({"cell_id": c.cell_id, "util_num": u, "area_share": n / len(hits)})
    S = pd.DataFrame(rows).merge(pd.DataFrame(meta).drop_duplicates("util_num")[["util_num", "util_name"]], on="util_num", how="left")
    S.to_parquet(ROOT / f"data/processed/cell_utility_shares_{tag}.parquet", index=False)
    ok = S[S.util_num.notna()]
    top = ok.sort_values(["cell_id", "area_share"], ascending=[True, False]).groupby("cell_id").head(1)
    unc = int(len(cells) - top.cell_id.nunique())
    print(f"[{tag}] territories kept: {len(geoms)} | utilities: {len(set(m['util_num'] for m in meta))} | cells with no territory: {unc}")
    print(top.util_name.value_counts().head(12).to_string())
    return S


def main() -> None:
    feats = fetch()
    keep_all = az_retail_ids() - WHOLESALE_IDS
    gwh = az_sales_gwh()
    keep_large = {u for u in keep_all if gwh.get(u, 0) >= 500}
    print(f"polygons intersecting AZ bbox: {len(feats)} | AZ retail utilities (excl. wholesale): {len(keep_all)} | with >=500 GWh sales: {len(keep_large)}")
    shares(feats, keep_all, "all")
    shares(feats, keep_large, "large")


if __name__ == "__main__":
    main()
