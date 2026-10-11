"""Build a utility x state x year panel from EIA-861 (2013-2024): reliability + retail sales.

Reliability: IEEE-standard SAIDI/SAIFI (with and without Major Event Days); where a utility
reports only under 'other standard', that block is used and flagged (std = 'other').
Sales: commercial and industrial MWh/customers, Parts A (bundled) + C (delivery-only) summed
so wires-served customers are counted once.

Output: data/processed/eia861_panel.parquet
"""
import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/eia861"


def find(year: int, stem: str) -> str:
    fs = [f for f in glob.glob(str(RAW / str(year) / f"{stem}_{year}.xls*"))]
    if not fs:
        raise FileNotFoundError(f"{stem} {year}")
    return fs[0]


def read_with_header(path: str):
    raw = pd.read_excel(path, header=None)
    h = next(i for i in range(8) if str(raw.iloc[i, 0]).strip().startswith("Data Year"))
    hdr = [re.sub(r"\s+", " ", str(c)).strip() for c in raw.iloc[h]]
    body = raw.iloc[h + 1:].reset_index(drop=True)
    return hdr, body


def num(s):
    return pd.to_numeric(s.replace({".": np.nan, "NA": np.nan, " ": np.nan}), errors="coerce")


def reliability(year: int) -> pd.DataFrame:
    hdr, b = read_with_header(find(year, "Reliability"))
    if "Short Form" in hdr:
        i = hdr.index("Short Form")
        b = b.drop(columns=b.columns[i]).reset_index(drop=True)
        hdr = hdr[:i] + hdr[i + 1:]
    b.columns = range(b.shape[1])
    out = pd.DataFrame({"year": year, "util_num": pd.to_numeric(b[1], errors="coerce"),
                        "util_name": b[2], "state": b[3], "ownership": b[4]})
    ieee = {"saidi_med": 5, "saifi_med": 6, "saidi_nomed": 8, "saifi_nomed": 9, "customers": 14}
    other = {"saidi_med": 17, "saifi_med": 18, "saidi_nomed": 20, "saifi_nomed": 21, "customers": 23}
    for k in ieee:
        a, o = num(b[ieee[k]]), num(b[other[k]])
        out[k] = a.fillna(o)
        if k == "saidi_nomed":
            out["std"] = np.where(a.notna(), "ieee", np.where(o.notna(), "other", None))
    return out


def sales(year: int) -> pd.DataFrame:
    hdr, b = read_with_header(find(year, "Sales_Ult_Cust"))
    b.columns = range(b.shape[1])
    mwh = [i for i, c in enumerate(hdr) if c.startswith("Megawatthours")]
    cnt = [i for i, c in enumerate(hdr) if c == "Count"]
    part = hdr.index("Part") if "Part" in hdr else 3
    ba = hdr.index("BA Code") if "BA Code" in hdr else None
    # class order in the file: residential, commercial, industrial, transportation, total
    d = pd.DataFrame({
        "year": year, "util_num": pd.to_numeric(b[1], errors="coerce"),
        "state": b[hdr.index("State")], "part": b[part],
        "ba_code": b[ba] if ba is not None else None})
    for j, cls in enumerate(["res", "com", "ind", "trans", "total"]):
        d[f"{cls}_mwh"] = num(b[mwh[j]])
        d[f"{cls}_cust"] = num(b[cnt[j]])
    d = d[d.part.astype(str).str.strip().isin(["A", "C"])]
    agg = d.groupby(["year", "util_num", "state"]).agg(
        ba_code=("ba_code", lambda s: s.dropna().astype(str).mode().iat[0] if s.notna().any() else None),
        **{c: (c, "sum") for c in d.columns if c.endswith("_mwh") or c.endswith("_cust")}).reset_index()
    return agg


def main() -> None:
    rel = pd.concat([reliability(y) for y in range(2013, 2025)], ignore_index=True)
    sal = pd.concat([sales(y) for y in range(2013, 2025)], ignore_index=True)
    rel = rel[rel.util_num.notna()]
    panel = rel.merge(sal, on=["year", "util_num", "state"], how="outer", indicator=True)
    panel.to_parquet(ROOT / "data/processed/eia861_panel.parquet", index=False)
    print("rows:", len(panel)); print(panel["_merge"].value_counts().to_string())
    has = panel[panel.saidi_nomed.notna() | panel.saidi_med.notna()]
    print("rows with reliability:", len(has), "| utilities:", has.util_num.nunique())
    print(has.groupby("year").agg(n=("util_num", "nunique"), saidi_med=("saidi_med", "median"),
                                  saidi_nomed=("saidi_nomed", "median")).round(1).to_string())
    az = panel[(panel.state == "AZ")]
    print("\nAZ utilities with reliability:")
    print(az[az.saidi_med.notna()].groupby(["util_num", "util_name"]).year.agg(["count", "min", "max"]).to_string())


if __name__ == "__main__":
    main()
