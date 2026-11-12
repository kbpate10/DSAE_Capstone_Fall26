"""Check the hourly CO2 estimate (EIA-930 fuel mix x eGRID 2023 emission factors) against measured plant emissions (EPA CAMPD hourly CEMS).

Run with isolated Python because the inputs are downloaded files:  .venv/bin/python -I src/measured_emissions_check.py

Inputs
  data/raw/campd_az/emissions-hourly-{2021..2025}-{az,nm}.csv   EPA CAMPD per-state hourly emissions (public bulk files, no key; NM is needed because EIA-923
                                                           assigns Four Corners, in New Mexico, to AZPS). One row per unit-hour,
                                                           measured CO2 mass (short tons) for fossil units of 25 MW or more (Part 75 reporters)
  data/raw/eia923/...Schedules_2_3_4_5...2025...xlsx       Page 1: plant -> balancing authority (2025 assignment; applied to all years: assumption)
  data/raw/eia930/*.parquet, data/processed/emission_factors.csv, data/processed/carbon_intensity.parquet   the current estimate
Assumptions to check, not trust: CAMPD hours are local standard time (Arizona has no DST, so UTC = local + 7 h; the lag check below tests this);
CAMPD Facility ID equals the EIA plant code.

PRE-SPECIFIED DECISION RULE (written before any comparison was computed)
  The existing carbon-intensity series is "confirmed" for a BA if, over 2021-2025 hours with unflagged EIA-930 data, (a) the estimated fossil CO2 is within +-10%
  of measured CO2 in total, and (b) the hourly correlation is at least 0.95. Otherwise it is "not confirmed" and the downstream results (forecasts, scheduling, marginal
  profiles) are re-checked on the measured series (second step, separate script). The estimate covers ALL fossil generation in the BA; CAMPD covers units of
  25 MW or more, so a small estimate-above-measured gap is expected from small units and is not itself a failure. Thresholds are not tuned after seeing results.

Outputs: results/measured_emissions_check.csv (per BA and year), results/measured_emissions_hourblock.csv (bias by 6 h block), results/measured_emissions_lagcheck.csv,
         data/processed/ci_measured.parquet (BA-hour measured CO2 and intensity, for the second step)
"""
import glob
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
SHORT_TON_KG = 907.18474
BAS = ["AZPS", "SRP", "TEPC", "WALC"]
FOSSIL = ["COL", "NG", "OIL", "OTH"]
EXCLUDE = {"BAT", "UES", "SNB"}


def plant_ba() -> pd.Series:
    g = pd.read_excel(ROOT / "data/raw/eia923/EIA923_Schedules_2_3_4_5_M_12_2025_Final.xlsx",
                      sheet_name="Page 1 Generation and Fuel Data", header=5)
    g.columns = [" ".join(str(c).split()) for c in g.columns]
    g = g[["Plant Id", "Balancing Authority Code"]].dropna()
    g["Plant Id"] = pd.to_numeric(g["Plant Id"], errors="coerce")
    return g.drop_duplicates("Plant Id").set_index("Plant Id")["Balancing Authority Code"]


def load_cems(pba: pd.Series) -> pd.DataFrame:
    parts = []
    for f in sorted(glob.glob(str(ROOT / "data/raw/campd_az/emissions-hourly-*.csv"))):
        d = pd.read_csv(f, usecols=["Facility ID", "Date", "Hour", "CO2 Mass (short tons)", "Gross Load (MW)"])
        d = d.rename(columns={"Facility ID": "plant", "CO2 Mass (short tons)": "co2_st", "Gross Load (MW)": "gross_mw"})
        d["co2_kg"] = pd.to_numeric(d.co2_st, errors="coerce") * SHORT_TON_KG
        d["gross_mw"] = pd.to_numeric(d.gross_mw, errors="coerce")
        d["ba"] = d.plant.map(pba)
        d = d[d.ba.isin(BAS)]
        d["ts_local"] = pd.to_datetime(d.Date) + pd.to_timedelta(d.Hour, unit="h")
        parts.append(d.groupby(["ba", "ts_local"], as_index=False).agg(co2_kg=("co2_kg", "sum"), gross_mw=("gross_mw", "sum"),
                                                                         n_plants=("plant", "nunique")))
    m = pd.concat(parts).groupby(["ba", "ts_local"], as_index=False).agg(co2_kg=("co2_kg", "sum"), gross_mw=("gross_mw", "sum"),
                                                                           n_plants=("n_plants", "sum"))   # AZ and NM files both feed AZPS
    m["ts"] = m.ts_local + pd.Timedelta(hours=7)          # local standard time -> UTC
    return m


def load_estimate() -> pd.DataFrame:
    ef = pd.read_csv(ROOT / "data/processed/emission_factors.csv")
    df = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930/*.parquet")))
    df = df[~df.fueltype.isin(EXCLUDE)][["period", "respondent", "fueltype", "value"]]
    df["value"] = df.value.clip(lower=0)
    df = df.merge(ef, on=["respondent", "fueltype"], how="left")
    df["co2"] = df.value * df.ef
    df["ts"] = pd.to_datetime(df.period, format="%Y-%m-%dT%H")
    fos = df[df.fueltype.isin(FOSSIL)].groupby(["respondent", "ts"], as_index=False).agg(est_fossil_kg=("co2", "sum"))
    fos = fos.rename(columns={"respondent": "ba"})
    gas = df[df.fueltype.isin(["NG", "COL"])].groupby(["respondent", "ts"], as_index=False).agg(gas_coal_mwh=("value", "sum")).rename(columns={"respondent": "ba"})
    ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet").rename(columns={"respondent": "ba"})
    return ci.merge(fos, on=["ba", "ts"], how="left").merge(gas, on=["ba", "ts"], how="left")


def main() -> None:
    pba = plant_ba()
    m = load_cems(pba)
    e = load_estimate()
    d = e.merge(m[["ba", "ts", "co2_kg", "gross_mw", "n_plants"]].rename(columns={"co2_kg": "meas_kg"}), on=["ba", "ts"], how="left")
    d["meas_kg"] = d.meas_kg.fillna(0.0)               # no CEMS row in an hour = no reporting unit running
    d["year"] = (d.ts - pd.Timedelta(hours=7)).dt.year
    d["hour_local"] = (d.ts - pd.Timedelta(hours=7)).dt.hour
    d = d[(d.year >= 2021) & ~d.data_flag.fillna(True).astype(bool) & d.est_fossil_kg.notna()]
    print("CEMS BA-hours by BA:", m.groupby("ba").size().to_dict(), "| max reporting plants in an hour:", m.groupby("ba").n_plants.max().to_dict())

    # ---- timing check: correlation of measured CEMS CO2 with EIA-930 gas+coal generation at shifts of -3..+3 h (a shift of 0 = assumed convention)
    lag = []
    for ba, g in d.groupby("ba"):
        g = g.set_index("ts")
        for s in range(-3, 4):
            x = g.meas_kg.shift(s, freq="h").reindex(g.index)
            lag.append({"ba": ba, "shift_hours": s, "corr": x.corr(g.gas_coal_mwh), "spearman": x.corr(g.gas_coal_mwh, method="spearman")})
    L = pd.DataFrame(lag)
    L.round(4).to_csv(ROOT / "results/measured_emissions_lagcheck.csv", index=False)
    print("\nTiming check, corr(measured CO2 shifted by s hours, EIA-930 gas+coal MWh); by shift (Spearman):")
    print(L.pivot(index="ba", columns="shift_hours", values="spearman").round(3).to_string())

    # ---- level and hourly agreement
    rows = []
    for (ba, yr), g in d.groupby(["ba", "year"]):
        rows.append({"ba": ba, "year": yr, "hours": len(g),
                     "measured_kt": g.meas_kg.sum() / 1e6, "estimated_fossil_kt": g.est_fossil_kg.sum() / 1e6,
                     "ratio_est_over_meas": g.est_fossil_kg.sum() / g.meas_kg.sum(),
                     "hourly_corr": g.meas_kg.corr(g.est_fossil_kg),
                     "mean_abs_gap_pct_of_measured": 100 * (g.est_fossil_kg - g.meas_kg).abs().sum() / g.meas_kg.sum()})
    R = pd.DataFrame(rows)
    R.round(3).to_csv(ROOT / "results/measured_emissions_check.csv", index=False)
    tot = d.groupby("ba").apply(lambda g: pd.Series({"ratio_est_over_meas": g.est_fossil_kg.sum() / g.meas_kg.sum(),
                                                       "hourly_corr": g.meas_kg.corr(g.est_fossil_kg)}))
    tot["confirmed_by_prespecified_rule"] = (tot.ratio_est_over_meas.sub(1).abs() <= 0.10) & (tot.hourly_corr >= 0.95)
    print("\nPer BA, pooled 2021-2025 (estimate = all fossil in the BA; measured = CEMS units of 25 MW or more):")
    print(tot.round(3).to_string())
    print("\nBy year:")
    print(R.pivot_table(index="ba", columns="year", values="ratio_est_over_meas").round(2).to_string())

    # ---- where does the gap sit: by 6 h local block
    d["blk"] = d.hour_local // 6 * 6
    B = d.groupby(["ba", "blk"]).apply(lambda g: pd.Series({"ratio_est_over_meas": g.est_fossil_kg.sum() / g.meas_kg.sum(),
                                                              "corr": g.meas_kg.corr(g.est_fossil_kg)})).reset_index()
    B.round(3).to_csv(ROOT / "results/measured_emissions_hourblock.csv", index=False)
    print("\nBias by 6 h local block (ratio est/meas):")
    print(B.pivot(index="ba", columns="blk", values="ratio_est_over_meas").round(2).to_string())

    # ---- glitch share in the estimate (exploratory): hours where the estimate is more than 3x or less than 1/3 of measured
    d["ratio_h"] = d.est_fossil_kg / d.meas_kg.where(d.meas_kg > 0)
    med = d.groupby("ba").ratio_h.transform("median")
    d["outlier"] = (d.ratio_h > 3 * med) | (d.ratio_h < med / 3)
    print("\nShare of hours where the estimate is >3x or <1/3 of its own typical ratio to measured:")
    print(d.groupby("ba").outlier.mean().round(4).to_string())
    clean = d[~d.outlier]
    print("Pearson / Spearman hourly correlation after dropping those hours:")
    print(clean.groupby("ba").apply(lambda g: pd.Series({"pearson": g.meas_kg.corr(g.est_fossil_kg),
          "spearman": g.meas_kg.corr(g.est_fossil_kg, method="spearman")})).round(3).to_string())

    # ---- intensity comparison and output for the second step
    d["ci_cems_kg_mwh"] = d.meas_kg / d.gen_mwh.where(d.gen_mwh > 0)
    print("\nIntensity: mean estimated vs mean CEMS-only (kg/MWh) and hourly correlation")
    print(d.groupby("ba").apply(lambda g: pd.Series({"ci_est": g.ci_kg_per_mwh.mean(), "ci_cems_only": g.ci_cems_kg_mwh.mean(),
                                                       "corr": g.ci_kg_per_mwh.corr(g.ci_cems_kg_mwh)})).round(3).to_string())
    d[["ba", "ts", "gen_mwh", "co2_kg", "est_fossil_kg", "meas_kg", "ci_kg_per_mwh", "ci_cems_kg_mwh", "n_plants"]].to_parquet(
        ROOT / "data/processed/ci_measured.parquet", index=False)


if __name__ == "__main__":
    main()
