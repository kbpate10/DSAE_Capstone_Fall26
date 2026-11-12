"""Does swapping measured plant CO2 (EPA CAMPD CEMS) for the estimated fossil CO2 change the scheduling conclusion?

Run with isolated Python:  .venv/bin/python -I src/measured_emissions_downstream.py
Inputs: data/processed/ci_measured.parquet (from measured_emissions_check.py).

Alternative series: co2_alt = co2_kg - est_fossil_kg + meas_kg(aligned), ci_alt = co2_alt / gen_mwh. Fossil CO2 is replaced by the measured value and the non-fossil
part and the denominator are unchanged. CEMS hour h is taken to describe the EIA-930 label h+1 (measured_emissions_check.py timing check: the best-aligned shift is +1 h in all
four BAs), so meas_kg is shifted by one hour. The plant-to-BA mapping is the 2025 EIA-923 assignment and CEMS reports whole plants, so for jointly owned plants the measured
value can overstate the BA's share: this is a sensitivity series, not the truth.

Test (same design as schedule_eval.py; 8 h preemptible job, 24 h windows decided at local midnight, persistence = yesterday's same local hour, test years 2024 and 2025,
cost always evaluated on the series named): % saved against random timing.

PRE-SPECIFIED RULE (written before running): the RQ1 scheduling conclusion is "robust to measured emissions" if, for each BA and test year, (a) the saving of the
persistence decision evaluated on ci_alt is within 3 percentage points of its saving evaluated on ci_est, and (b) deciding on ci_est and evaluating on ci_alt keeps at least
90% of the saving of deciding on ci_alt and evaluating on ci_alt. Otherwise it is reported as sensitive to the emissions series for that BA.

POST HOC VARIANT ('band', added after seeing that a few extreme hours in ci_alt, up to 70,652 kg/MWh on AZPS, dominate mean-based savings; reported next to the pre-specified
result, never instead of it): for both series, hours outside [0.3, 2.5] x the BA's median for the same local month and hour are set to missing (the band rule of
eia930_qc.py, applied to intensity), and a day is used only if both series are complete on it and on the previous day. The pre-specified rule is applied to both variants.

Outputs: results/measured_emissions_scheduling.csv (column `variant`: as_specified or band)
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
K = 8


def prepare() -> pd.DataFrame:
    d = pd.read_parquet(ROOT / "data/processed/ci_measured.parquet").sort_values(["ba", "ts"])
    out = []
    for ba, g in d.groupby("ba"):
        g = g.set_index("ts")
        g = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="h"))
        g["ba"] = ba
        g["meas_aligned"] = g.meas_kg.shift(1)
        g["co2_alt"] = g.co2_kg - g.est_fossil_kg + g.meas_aligned
        g["ci_alt"] = g.co2_alt / g.gen_mwh.where(g.gen_mwh > 0)
        out.append(g)
    x = pd.concat(out).rename_axis("ts").reset_index()
    x["ci_est"] = x.ci_kg_per_mwh
    x["local"] = x.ts - pd.Timedelta(hours=7)
    x["day"], x["hr"] = x.local.dt.floor("D"), x.local.dt.hour
    x["year"] = x.local.dt.year
    return x


def day_matrix(x: pd.DataFrame, col: str) -> pd.DataFrame:
    return x.pivot_table(index=["ba", "day"], columns="hr", values=col, aggfunc="first")


def band(x: pd.DataFrame) -> pd.DataFrame:
    x = x.copy()
    key = [x.ba, x.local.dt.month, x.hr]
    for c in ("ci_est", "ci_alt"):
        ratio = x[c] / x.groupby(key)[c].transform("median")
        x.loc[(ratio < 0.3) | (ratio > 2.5) | (x[c] <= 0), c] = np.nan
    both = x.ci_est.notna() & x.ci_alt.notna()
    x.loc[~both, ["ci_est", "ci_alt"]] = np.nan
    return x


def run(x: pd.DataFrame, variant: str) -> pd.DataFrame:
    est, alt = day_matrix(x, "ci_est"), day_matrix(x, "ci_alt")
    rows = []
    for ba in est.index.get_level_values(0).unique():
        e, a = est.loc[ba], alt.loc[ba]
        for yr in (2024, 2025):
            days = [d for d in e.index if d.year == yr and (d - pd.Timedelta(days=1)) in e.index]
            res = {k: [] for k in ("rand_e", "per_e_on_e", "rand_a", "per_a_on_a", "per_e_on_a", "per_a_on_e")}
            for d in days:
                p = d - pd.Timedelta(days=1)
                ye, ya, pe, pa = e.loc[d].to_numpy(), a.loc[d].to_numpy(), e.loc[p].to_numpy(), a.loc[p].to_numpy()
                if len(ye) != 24 or np.isnan(ye).any() or np.isnan(ya).any() or np.isnan(pe).any() or np.isnan(pa).any():
                    continue
                pick_e, pick_a = np.argsort(pe, kind="stable")[:K], np.argsort(pa, kind="stable")[:K]
                res["rand_e"].append(ye.mean() * K); res["rand_a"].append(ya.mean() * K)
                res["per_e_on_e"].append(ye[pick_e].sum()); res["per_a_on_a"].append(ya[pick_a].sum())
                res["per_e_on_a"].append(ya[pick_e].sum()); res["per_a_on_e"].append(ye[pick_a].sum())
            n = len(res["rand_e"])
            if n < 100:
                continue
            r = {k: np.mean(v) for k, v in res.items()}
            s_ee = 100 * (1 - r["per_e_on_e"] / r["rand_e"])
            s_aa = 100 * (1 - r["per_a_on_a"] / r["rand_a"])
            s_ea = 100 * (1 - r["per_e_on_a"] / r["rand_a"])
            rows.append({"variant": variant, "ba": ba, "year": yr, "days": n, "save_decide_est_eval_est": s_ee, "save_decide_alt_eval_alt": s_aa,
                         "save_decide_est_eval_alt": s_ea, "gap_a_minus_e_pts": s_aa - s_ee,
                         "kept_share_est_decision_on_alt": s_ea / s_aa if s_aa else np.nan})
    return pd.DataFrame(rows)


def main() -> None:
    x = prepare()
    R = pd.concat([run(x, "as_specified"), run(band(x), "band")], ignore_index=True)
    R["rule_a_within_3pts"] = R.gap_a_minus_e_pts.abs() <= 3
    R["rule_b_keeps_90pct"] = R.kept_share_est_decision_on_alt >= 0.90
    R["robust"] = R.rule_a_within_3pts & R.rule_b_keeps_90pct
    R.round(3).to_csv(ROOT / "results/measured_emissions_scheduling.csv", index=False)
    pd.set_option("display.width", 200)
    print(R.round(2).to_string(index=False))
    print("\nmean level of the two series (kg/MWh), 2021-2025 hours with both defined:")
    print(x.dropna(subset=["ci_est", "ci_alt"]).groupby("ba")[["ci_est", "ci_alt"]].mean().round(0).to_string())
    print("hourly correlation ci_est vs ci_alt:", x.dropna(subset=["ci_est", "ci_alt"]).groupby("ba").apply(lambda g: round(g.ci_est.corr(g.ci_alt), 3)).to_dict())


if __name__ == "__main__":
    main()
