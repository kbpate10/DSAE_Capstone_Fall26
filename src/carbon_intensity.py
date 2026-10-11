"""Build hourly carbon intensity (kg CO2/MWh) per Arizona BA from EIA-930 + eGRID 2023.

Emission factor per (BA, fuel) = sum(plant CO2) / sum(plant net generation) from eGRID PLNT23.
Falls back to the Arizona-wide, then national, factor for that fuel when a BA has no plants of it.

Choices (documented so the report can state them):
  * Storage / behind-the-meter codes (BAT, UES, SNB) are excluded from the mix: they move
    energy rather than generate it, and BAT goes negative when charging.
  * Remaining negative values (e.g. solar auxiliary load at night) are clipped to 0.
  * eGRID biogenic CO2 is not counted (PLCO2AN is combustion CO2 excluding biogenic).
  * Hours with a missing fuel value or zero total generation get ci = NaN and a flag.

Output: data/processed/carbon_intensity.parquet (one row per BA-hour)
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHORT_TON_KG = 907.18474

# EIA-930 fuel code -> eGRID PLFUELCT
FUEL_MAP = {"COL": "COAL", "NG": "GAS", "NUC": "NUCLEAR", "OIL": "OIL",
            "SUN": "SOLAR", "WND": "WIND", "WAT": "HYDRO", "OTH": "OTHF"}
EXCLUDE = {"BAT", "UES", "SNB"}
BAS = ["AZPS", "SRP", "TEPC", "WALC"]


def emission_factors() -> pd.DataFrame:
    p = pd.read_excel(ROOT / "data/raw/egrid/egrid2023_data_rev2.xlsx",
                      sheet_name="PLNT23", header=1)
    p = p[["BACODE", "PSTATABB", "PLFUELCT", "PLNGENAN", "PLCO2AN"]].copy()
    p["PLNGENAN"] = pd.to_numeric(p["PLNGENAN"], errors="coerce")
    p["PLCO2AN"] = pd.to_numeric(p["PLCO2AN"], errors="coerce")
    p = p[p["PLNGENAN"] > 0]

    def ef(group_cols):
        g = p.groupby(group_cols)[["PLCO2AN", "PLNGENAN"]].sum()
        return (g["PLCO2AN"] * SHORT_TON_KG / g["PLNGENAN"]).rename("ef")

    ba = ef(["BACODE", "PLFUELCT"]).reset_index()
    az = ef(["PSTATABB", "PLFUELCT"]).reset_index()
    az = az[az["PSTATABB"] == "AZ"].drop(columns="PSTATABB").rename(columns={"ef": "ef_az"})
    us = ef(["PLFUELCT"]).reset_index().rename(columns={"ef": "ef_us"})

    rows = []
    for b in BAS:
        for code, cat in FUEL_MAP.items():
            rows.append({"respondent": b, "fueltype": code, "PLFUELCT": cat})
    f = pd.DataFrame(rows)
    f = (f.merge(ba, left_on=["respondent", "PLFUELCT"], right_on=["BACODE", "PLFUELCT"], how="left")
          .merge(az, on="PLFUELCT", how="left").merge(us, on="PLFUELCT", how="left"))
    f["ef_source"] = np.where(f["ef"].notna(), "ba", np.where(f["ef_az"].notna(), "az", "us"))
    f["ef"] = f["ef"].fillna(f["ef_az"]).fillna(f["ef_us"])
    return f[["respondent", "fueltype", "ef", "ef_source"]]


def main() -> None:
    ef = emission_factors()
    ef.to_csv(ROOT / "data/processed/emission_factors.csv", index=False)

    df = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930/*.parquet")))
    df = df[~df["fueltype"].isin(EXCLUDE)][["period", "respondent", "fueltype", "value"]]
    df["value"] = df["value"].clip(lower=0)
    df = df.merge(ef, on=["respondent", "fueltype"], how="left")
    df["co2"] = df["value"] * df["ef"]

    g = df.groupby(["respondent", "period"])
    out = pd.DataFrame({
        "gen_mwh": g["value"].sum(min_count=1),
        "co2_kg": g["co2"].sum(min_count=1),
        "n_null_fuel": g["value"].apply(lambda s: s.isna().sum()),
    }).reset_index()
    out["ci_kg_per_mwh"] = out["co2_kg"] / out["gen_mwh"].where(out["gen_mwh"] > 0)
    out["ts"] = pd.to_datetime(out["period"], format="%Y-%m-%dT%H")
    out["data_flag"] = out["ci_kg_per_mwh"].isna() | (out["n_null_fuel"] > 0)

    # clean-energy share (non-emitting) as an extra feature
    clean = df[df["fueltype"].isin(["SUN", "WND", "WAT", "NUC"])].groupby(["respondent", "period"])["value"].sum()
    out = out.merge(clean.rename("clean_mwh").reset_index(), on=["respondent", "period"], how="left")
    out["clean_share"] = out["clean_mwh"] / out["gen_mwh"].where(out["gen_mwh"] > 0)

    out = out.sort_values(["respondent", "ts"]).drop(columns="period")
    out.to_parquet(ROOT / "data/processed/carbon_intensity.parquet", index=False)
    print(ef.to_string(index=False))
    print(out.groupby("respondent")["ci_kg_per_mwh"].describe().round(1).to_string())
    print("flagged hours:", int(out["data_flag"].sum()), "of", len(out))


if __name__ == "__main__":
    main()
