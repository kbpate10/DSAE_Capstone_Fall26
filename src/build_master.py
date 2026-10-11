"""Unified analysis tables that every arm can read from (the 'one pipeline' the plan describes).

1. master_ba_hour.parquet    grain: balancing authority x hour (UTC), 2021-2025
     generation by fuel (wide), carbon intensity, clean share, quality flags, demand (D), EIA day-ahead
     demand forecast (DF), weather at the BA load-centre proxy (T2M, RH2M, T2MWET), local-time calendar.
2. master_utility_year.parquet  grain: utility-state x year, 2013-2024
     cleaned reliability panel (rq3_panel) + the utility's balancing authority + BA-year context
     (mean carbon intensity, mean demand, mean wet-bulb) for the four Arizona BAs.
3. sites_scored.parquet (already built) grain: 0.25-degree cell, 192 cells.

Join keys: BA code (respondent) + UTC timestamp for (1); utility number + state + year for (2);
BA code links (2) to (1) through BA-year aggregates.
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE = {"AZPS": "PHX", "SRP": "PHX", "TEPC": "TUS", "WALC": "HAV"}


def ba_hour() -> pd.DataFrame:
    gen = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930/*.parquet")))
    gen["ts"] = pd.to_datetime(gen.period, format="%Y-%m-%dT%H")
    w = gen.pivot_table(index=["respondent", "ts"], columns="fueltype", values="value", aggfunc="sum")
    w.columns = [f"gen_{c}_mwh" for c in w.columns]
    ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet").set_index(["respondent", "ts"])
    ci = ci[["gen_mwh", "ci_kg_per_mwh", "clean_share", "n_null_fuel", "data_flag"]].rename(
        columns={"gen_mwh": "gen_total_mwh", "n_null_fuel": "n_null_fuel_types"})
    dem = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930_demand/*.parquet")))
    dem["ts"] = pd.to_datetime(dem.period, format="%Y-%m-%dT%H")
    dem = dem.pivot_table(index=["respondent", "ts"], columns="type", values="value").rename(
        columns={"D": "demand_mwh", "DF": "demand_forecast_mwh"})
    m = w.join(ci, how="outer").join(dem, how="outer").reset_index()
    wx = []
    for ba, site in SITE.items():
        x = pd.read_parquet(ROOT / f"data/raw/weather/nasa_hourly_{site}.parquet")
        x["ts"] = x.ts_local + pd.Timedelta(hours=7)
        x["respondent"] = ba
        wx.append(x[["respondent", "ts", "T2M", "RH2M", "T2MWET"]].rename(
            columns={"T2M": "temp_c", "RH2M": "rh_pct", "T2MWET": "wetbulb_c"}))
    m = m.merge(pd.concat(wx), on=["respondent", "ts"], how="left")
    m["ts_local"] = m.ts - pd.Timedelta(hours=7)      # Arizona: no DST, UTC-7 year-round
    m["year"], m["month"], m["hour_local"] = m.ts_local.dt.year, m.ts_local.dt.month, m.ts_local.dt.hour
    m["dow_local"] = m.ts_local.dt.dayofweek
    return m.sort_values(["respondent", "ts"]).reset_index(drop=True)


def utility_year(m: pd.DataFrame) -> pd.DataFrame:
    u = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet")
    p = pd.read_parquet(ROOT / "data/processed/eia861_panel.parquet")[["util_num", "state", "year", "ba_code"]]
    u = u.merge(p.drop_duplicates(["util_num", "state", "year"]), on=["util_num", "state", "year"], how="left", suffixes=("", "_861"))
    ctx = (m[m.respondent.isin(SITE)].groupby(["respondent", "year"])
           .agg(ba_ci_mean=("ci_kg_per_mwh", "mean"), ba_demand_mean_mwh=("demand_mwh", "mean"),
                ba_wetbulb_mean_c=("wetbulb_c", "mean")).reset_index()
           .rename(columns={"respondent": "ba_code"}))
    return u.merge(ctx, on=["ba_code", "year"], how="left")


def main() -> None:
    m = ba_hour()
    assert not m.duplicated(["respondent", "ts"]).any(), "duplicate BA-hours"
    m.to_parquet(ROOT / "data/processed/master_ba_hour.parquet", index=False)
    u = utility_year(m)
    assert not u.duplicated(["key", "year"]).any(), "duplicate utility-years"
    u.to_parquet(ROOT / "data/processed/master_utility_year.parquet", index=False)
    print(f"master_ba_hour: {len(m):,} rows x {m.shape[1]} cols | BAs {m.respondent.unique().tolist()} | "
          f"{m.ts.min()} .. {m.ts.max()}")
    full = m.groupby("respondent").ts.agg(["min", "max", "size"])
    full["expected"] = ((full["max"] - full["min"]).dt.total_seconds() / 3600 + 1).astype(int)
    full["missing_hours"] = full.expected - full["size"]
    print(full.to_string())
    print("\ncompleteness by column (share non-null):")
    print(m[["ci_kg_per_mwh", "demand_mwh", "demand_forecast_mwh", "wetbulb_c", "gen_NG_mwh", "gen_SUN_mwh"]]
          .notna().mean().round(3).to_string())
    print(f"\nmaster_utility_year: {len(u):,} rows x {u.shape[1]} cols | "
          f"AZ with BA context: {u[(u.state=='AZ')].ba_ci_mean.notna().sum()} of {(u.state=='AZ').sum()} AZ rows")
    print("AZ utility BA codes:", u[u.state == "AZ"].groupby("util_name").ba_code.agg(lambda s: s.dropna().mode().iat[0] if s.notna().any() else None).to_dict())


if __name__ == "__main__":
    main()
