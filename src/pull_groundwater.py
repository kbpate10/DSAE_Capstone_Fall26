"""Pull Arizona depth-to-water measurements (USGS parameter 72019, includes ADWR GWSI wells).

Source: USGS Water Data OGC API (waterservices.usgs.gov was decommissioned in 2025).
Writes data/raw/rq2/gw_levels_az.parquet : one row per measurement (2005-2025).
"""
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/field-measurements/items"
COUNTIES = [f"{i:03d}" for i in range(1, 28, 2)] + ["012"]  # 15 AZ counties; La Paz is FIPS 012 (even)


def get(url, params=None):
    for a in range(6):
        r = requests.get(url, params=params, timeout=120)
        if r.status_code == 200:
            return r.json()
        time.sleep(2 ** a)
    r.raise_for_status()


def main() -> None:
    rows = []
    for c in COUNTIES:
        url, params, n = BASE, {"f": "json", "parameter_code": "72019", "state_code": "04",
                                "county_code": c, "limit": 10000,
                                "time": "2005-01-01T00:00:00Z/2025-12-31T23:59:59Z"}, 0
        while url:
            j = get(url, params)
            for f in j.get("features", []):
                p = f["properties"]
                rows.append({"site": p.get("monitoring_location_id"), "time": p.get("time"),
                             "depth_ft": p.get("value"), "county_code": c,
                             "approval": p.get("approval_status"), "agency": p.get("measuring_agency"),
                             "obs_proc": p.get("observing_procedure_code")})
                n += 1
            url = next((l["href"] for l in j.get("links", []) if l.get("rel") == "next"), None)
            params = None
        print(f"county {c}: {n} measurements", flush=True)
    df = pd.DataFrame(rows)
    df["depth_ft"] = pd.to_numeric(df["depth_ft"], errors="coerce")
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    out = ROOT / "data/raw/rq2/gw_levels_az.parquet"
    df.to_parquet(out, index=False)
    print("total", len(df), "sites", df.site.nunique(), df.time.min(), df.time.max())


if __name__ == "__main__":
    main()
