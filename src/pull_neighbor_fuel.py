"""Pull hourly EIA-930 net generation by fuel for the BAs that exchange power with the Arizona BAs.

Why these: ranked by 2021-2025 import volume into AZPS, SRP, TEPC and WALC (pull_interchange.py data), the
non-Arizona sources are PNM, WACM, EPE, GRIF, GRID, DEAA, HGMA (SRP's neighbours), PACE, IID, CISO.
(NEVP, LDWP and others are small and left out; the coverage of imported MWh is reported by consumption_carbon.py.)

Usage: .venv/bin/python src/pull_neighbor_fuel.py [start_year] [end_year]
Writes one parquet per BA-year to data/raw/eia930_neighbors/ (skips existing files). Reuses pull_eia930.fetch.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pull_eia930 as base

ROOT = Path(__file__).resolve().parents[1]
NEIGHBORS = ["PNM", "WACM", "EPE", "GRIF", "GRID", "DEAA", "HGMA", "PACE", "IID", "CISO"]
OUT = ROOT / "data" / "raw" / "eia930_neighbors"


def main() -> None:
    y0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2021
    y1 = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    OUT.mkdir(parents=True, exist_ok=True)
    for ba in NEIGHBORS:
        for year in range(y0, y1 + 1):
            f = OUT / f"{ba}_{year}.parquet"
            if f.exists():
                continue
            df = base.fetch(ba, f"{year}-01-01T00", f"{year}-12-31T23")
            if df.empty:
                print(f"{ba} {year}: no data")
                continue
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df.to_parquet(f, index=False)
            print(f"{ba} {year}: {len(df):,} rows, fuels {sorted(df.fueltype.unique())}")


if __name__ == "__main__":
    main()
