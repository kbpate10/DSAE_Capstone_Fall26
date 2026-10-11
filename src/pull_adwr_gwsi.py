"""Pull ADWR Groundwater Site Inventory (GWSI) 'Well Sites' layer: site coords, well depth,
latest depth-to-water (WL_DTW) and date (LASTWLDATE). Cross-sectional (latest value only).

Output: data/raw/rq2/adwr_gwsi_sites.parquet
"""
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://services3.arcgis.com/iuNbZYJOrAYBrPyC/ArcGIS/rest/services/Well_Sites/FeatureServer/1/query"


def main() -> None:
    rows, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json",
                  "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": "FID"}
        for a in range(6):
            r = requests.get(URL, params=params, timeout=120)
            if r.status_code == 200 and "features" in r.json():
                break
            time.sleep(2 ** a)
        feats = r.json()["features"]
        rows += [f["attributes"] for f in feats]
        print(offset, len(rows), flush=True)
        if len(feats) < 2000:
            break
        offset += 2000
    df = pd.DataFrame(rows)
    df["LASTWLDATE"] = pd.to_datetime(df["LASTWLDATE"], unit="ms", errors="coerce")
    df.to_parquet(ROOT / "data/raw/rq2/adwr_gwsi_sites.parquet", index=False)
    print(len(df), "sites;", df.WL_DTW.notna().sum(), "with depth-to-water")


if __name__ == "__main__":
    main()
