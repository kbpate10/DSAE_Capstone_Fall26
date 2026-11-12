"""Pull every OpenStreetMap feature tagged as a data center in the United States, state by state.

Tags: telecom=data_center or building=data_center (nodes and ways; ways use their centre point). Same tags as the Arizona set used by
revealed_preference.py. OSM carries no opening date for most of these, so the result is a cross-section of mapped facilities, not a time series.
Limits to carry downstream: mapping completeness varies by region and mapper, enterprise/colocation rooms and some mis-tagged IT businesses are
included, and hyperscale campuses may be a single polygon or missing.

Usage: .venv/bin/python src/pull_osm_datacenters_us.py
Writes one JSON per state to data/raw/osm_dc_us/ (skips existing files; safe to re-run) and data/raw/osm_dc_us.parquet when all are present.
Overpass is often busy: each state retries with backoff and alternates between the two public servers.
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/osm_dc_us"
HOSTS = ["https://overpass-api.de/api/interpreter", "https://z.overpass-api.de/api/interpreter"]
HEAD = {"User-Agent": "capstone-research-client"}
STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()


def query(st: str) -> str:
    return (f'[out:json][timeout:180];area["ISO3166-2"="US-{st}"]->.a;'
            '(node["telecom"="data_center"](area.a);way["telecom"="data_center"](area.a);'
            'node["building"="data_center"](area.a);way["building"="data_center"](area.a););out center tags;')


def fetch(st: str):
    for attempt in range(8):
        host = HOSTS[attempt % 2]
        try:
            r = requests.post(host, data={"data": query(st)}, timeout=240, headers=HEAD)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return r.json()["elements"]
        except requests.RequestException:
            pass
        time.sleep(min(10 * (attempt + 1), 60))
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for st in STATES:
        f = OUT / f"{st}.json"
        if f.exists():
            continue
        el = fetch(st)
        if el is None:
            print(f"{st}: FAILED after retries (re-run to try again)", flush=True)
            continue
        json.dump(el, open(f, "w"))
        print(f"{st}: {len(el)} features", flush=True)
    if all((OUT / f"{s}.json").exists() for s in STATES):
        rows = []
        for st in STATES:
            for e in json.load(open(OUT / f"{st}.json")):
                lat = e.get("lat", e.get("center", {}).get("lat"))
                lon = e.get("lon", e.get("center", {}).get("lon"))
                t = e.get("tags", {})
                rows.append({"state": st, "osm_id": e["id"], "type": e["type"], "lat": lat, "lon": lon, "name": t.get("name"),
                             "operator": t.get("operator"), "telecom": t.get("telecom"), "building": t.get("building")})
        d = pd.DataFrame(rows).dropna(subset=["lat", "lon"]).drop_duplicates(["type", "osm_id"])
        d.to_parquet(ROOT / "data/raw/osm_dc_us.parquet", index=False)
        print(f"all states done: {len(d)} features")


if __name__ == "__main__":
    main()
