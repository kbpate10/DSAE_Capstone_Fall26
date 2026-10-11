"""Pull hourly demand (D) and EIA day-ahead demand forecast (DF) for Arizona BAs.

Usage: .venv/bin/python src/pull_demand.py [start_year] [end_year]
Writes data/raw/eia930_demand/{BA}_{year}.parquet (skips existing).
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
URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
BAS = ["AZPS", "SRP", "TEPC", "WALC"]
PAGE = 5000
OUT = ROOT / "data" / "raw" / "eia930_demand"


def fetch(ba, start, end):
    rows, offset = [], 0
    while True:
        params = {"api_key": API_KEY, "frequency": "hourly", "data[0]": "value",
                  "facets[respondent][]": ba, "facets[type][]": ["D", "DF"],
                  "start": start, "end": end, "sort[0][column]": "period",
                  "sort[0][direction]": "asc", "length": PAGE, "offset": offset}
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


def main():
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
            df[["period", "respondent", "type", "value"]].to_parquet(f, index=False)
            print(f"{ba} {year}: {len(df):,} rows", flush=True)


if __name__ == "__main__":
    main()
