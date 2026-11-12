"""Pull the national HIFLD electric retail service-territory polygons (PNNL-hosted ArcGIS layer; attribute `id` = EIA utility number).

Same layer as build_territories.py (which fetched only polygons intersecting Arizona). Geometry is simplified server-side to about 0.001
degrees (about 100 m) to keep the download small; that is far finer than needed to place a point in a territory, but boundaries are approximate.
Territories overlap, and several small districts share identical generic polygons (see docs/STAGE1.md); the join downstream handles both.

Usage: .venv/bin/python src/pull_territories_us.py
Writes data/raw/territories_us.geojson (skips if present).
"""
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://eedgis.pnnl.gov/arcgis/rest/services/Hosted/Electric_Service_Territories/FeatureServer/0/query"
OUT = ROOT / "data/raw/territories_us.geojson"
PAGE = 50


def main() -> None:
    if OUT.exists():
        print("already present:", OUT)
        return
    feats, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "id,name,state,type,customers,retail_mwh,cntrl_area", "outSR": 4326,
                  "returnGeometry": "true", "maxAllowableOffset": 0.001, "f": "geojson", "resultOffset": offset,
                  "resultRecordCount": PAGE, "orderByFields": "objectid"}
        for a in range(8):
            try:
                r = requests.get(URL, params=params, timeout=240)
                if r.status_code == 200 and "features" in r.json():
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (a + 1))
        else:
            raise SystemExit(f"failed at offset {offset}; re-run")
        got = r.json()["features"]
        feats += got
        print(f"fetched {len(feats)}", flush=True)
        if len(got) < PAGE:
            break
        offset += PAGE
    json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"))
    print("saved", len(feats), "territories")


if __name__ == "__main__":
    main()
