"""Pull hourly EIA-930 interchange (flows between balancing authorities) for the Arizona BAs.

Usage: .venv/bin/python src/pull_interchange.py [start_year] [end_year]
Each row is the reported flow from `fromba` to `toba` in MWh for that hour (EIA convention: positive = out of
fromba). Writes one parquet per BA-year to data/raw/eia930_interchange/ (skips files that already exist).
Net interchange of a BA (positive = net export) is the sum over its counterparties, computed downstream.
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
API_KEY = os.environ["EIA_API_KEY"]

URL = "https://api.eia.gov/v2/electricity/rto/interchange-data/data/"
BAS = ["AZPS", "SRP", "TEPC", "WALC"]
PAGE = 5000
OUT = ROOT / "data" / "raw" / "eia930_interchange"


def fetch(ba: str, start: str, end: str) -> pd.DataFrame:
    rows, offset = [], 0
    while True:
        params = {
            "api_key": API_KEY,
            "frequency": "hourly",
            "data[0]": "value",
            "facets[fromba][]": ba,
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": PAGE,
            "offset": offset,
        }
        for attempt in range(5):
            r = requests.get(URL, params=params, timeout=60)
            if r.status_code == 200:
                break
            time.sleep(2 ** attempt)
        r.raise_for_status()
        data = r.json()["response"]["data"]
        rows.extend(data)
        if len(data) < PAGE:
            break
        offset += PAGE
    return pd.DataFrame(rows)


def main() -> None:
    y0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2021
    y1 = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    OUT.mkdir(parents=True, exist_ok=True)
    for ba in BAS:
        for year in range(y0, y1 + 1):
            f = OUT / f"{ba}_{year}.parquet"
            if f.exists():
                continue
            df = fetch(ba, f"{year}-01-01T00", f"{year}-12-31T23")
            if df.empty:
                print(f"{ba} {year}: no data")
                continue
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df.to_parquet(f, index=False)
            print(f"{ba} {year}: {len(df):,} rows, counterparties {sorted(df.toba.unique())}")


if __name__ == "__main__":
    main()
