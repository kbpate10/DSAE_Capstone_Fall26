"""Pull coordinates for the Arizona groundwater monitoring wells that appear in gw_levels_az.parquet."""
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/monitoring-locations/items"


def main() -> None:
    gw = pd.read_parquet(ROOT / "data/raw/rq2/gw_levels_az.parquet")
    sites = sorted(gw.site.dropna().unique())
    rows = []
    for i in range(0, len(sites), 100):
        chunk = sites[i:i + 100]
        for a in range(6):
            r = requests.get(URL, params={"f": "json", "id": ",".join(chunk), "limit": 1000,
                                          "properties": "id,county_name,county_code,agency_code,altitude,well_constructed_depth"},
                             timeout=120)
            if r.status_code == 200:
                break
            time.sleep(2 ** a)
        r.raise_for_status()
        for f in r.json().get("features", []):
            lon, lat = f["geometry"]["coordinates"][:2] if f.get("geometry") else (None, None)
            p = f["properties"]
            rows.append({"site": p.get("id") or f.get("id"), "lat": lat, "lon": lon,
                         "county_name": p.get("county_name"), "agency_code": p.get("agency_code")})
        print(i, len(rows), flush=True)
    out = pd.DataFrame(rows).drop_duplicates("site")
    out.to_parquet(ROOT / "data/raw/rq2/wells_geo.parquet", index=False)
    print("wells with coords:", out.lat.notna().sum(), "of", len(sites))


if __name__ == "__main__":
    main()
