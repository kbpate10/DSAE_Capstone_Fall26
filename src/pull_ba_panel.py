"""Pull hourly EIA-930 fuel-type generation and region data (demand D, net generation NG, total interchange TI) for a larger set of balancing authorities.

Used by the multi-BA scan (docs/MEF_SCAN_PREREG.md). TI is the net interchange of the BA (positive = net export). The four Arizona BAs and six neighbours
already have fuel-type files (data/raw/eia930, data/raw/eia930_neighbors); for those only region data are pulled.

Usage: .venv/bin/python src/pull_ba_panel.py [start_year] [end_year]
Writes data/raw/ba_panel/{fuel,region}/{BA}_{year}.parquet (skips existing files; safe to re-run). One progress line per BA when all its years are done.
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
BASE = "https://api.eia.gov/v2/electricity/rto/"
PAGE = 5000
OUT = ROOT / "data/raw/ba_panel"

HAVE_FUEL = ["AZPS", "SRP", "TEPC", "WALC", "PNM", "WACM", "EPE", "PACE", "IID", "CISO"]
NEW = ["PJM", "MISO", "ERCO", "NYIS", "ISNE", "SWPP", "SOCO", "TVA", "DUK", "FPL", "FPC", "TEC", "SC", "SCEG", "CPLE", "LGEE", "AECI", "BPAT",
       "PACW", "NEVP", "IPCO", "PSCO", "AVA", "NWMT", "PGE", "LDWP", "TPWR"]


def fetch(route: str, ba: str, start: str, end: str, types: list | None = None) -> pd.DataFrame:
    rows, offset = [], 0
    while True:
        params = {"api_key": API_KEY, "frequency": "hourly", "data[0]": "value", "facets[respondent][]": ba, "start": start, "end": end,
                  "sort[0][column]": "period", "sort[0][direction]": "asc", "length": PAGE, "offset": offset}
        for i, t in enumerate(types or []):
            params[f"facets[type][{i}]"] = t
        for attempt in range(6):
            r = requests.get(BASE + route + "/data/", params=params, timeout=90)
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
    for kind in ("fuel", "region"):
        (OUT / kind).mkdir(parents=True, exist_ok=True)
    for ba in NEW + HAVE_FUEL:
        for kind, route, types, skip in (("region", "region-data", ["D", "NG", "TI"], False), ("fuel", "fuel-type-data", None, ba in HAVE_FUEL)):
            if skip:
                continue
            for year in range(y0, y1 + 1):
                f = OUT / kind / f"{ba}_{year}.parquet"
                if f.exists():
                    continue
                df = fetch(route, ba, f"{year}-01-01T00", f"{year}-12-31T23", types)
                if df.empty:
                    print(f"{ba} {kind} {year}: no data", flush=True)
                    continue
                df["value"] = pd.to_numeric(df["value"], errors="coerce")
                df.to_parquet(f, index=False)
        print(f"BA done: {ba}", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
