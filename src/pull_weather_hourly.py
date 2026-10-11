"""Hourly dry-bulb, RH and wet-bulb temperature (NASA POWER, local standard time) at BA load centres.

AZPS and SRP -> Phoenix; TEPC -> Tucson; WALC -> Lake Havasu City (lower-Colorado proxy, an assumption).
Output: data/raw/weather/nasa_hourly_{site}.parquet  (ts is local standard time = UTC-7, no DST)
"""
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/weather"
SITES = {"PHX": (33.45, -112.07), "TUS": (32.22, -110.97), "HAV": (34.48, -114.32)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (lat, lon) in SITES.items():
        f = OUT / f"nasa_hourly_{name}.parquet"
        if f.exists():
            continue
        frames = []
        for year in range(2021, 2026):
            params = {"parameters": "T2M,RH2M,T2MWET", "community": "RE", "latitude": lat, "longitude": lon,
                      "start": f"{year}0101", "end": f"{year}1231", "format": "JSON", "time-standard": "LST"}
            for a in range(8):
                r = requests.get("https://power.larc.nasa.gov/api/temporal/hourly/point", params=params, timeout=300)
                if r.status_code == 200:
                    break
                time.sleep(10 * (a + 1))
            r.raise_for_status()
            p = r.json()["properties"]["parameter"]
            df = pd.DataFrame(p)
            df.index = pd.to_datetime(df.index, format="%Y%m%d%H")
            frames.append(df)
            print(name, year, len(df), flush=True)
        out = pd.concat(frames).sort_index().rename_axis("ts_local").reset_index()
        out = out.replace(-999, float("nan"))
        out.to_parquet(f, index=False)
        print(name, "saved", len(out), "rows; missing wet-bulb:", int(out.T2MWET.isna().sum()))


if __name__ == "__main__":
    main()
