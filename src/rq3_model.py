"""RQ3: does large-load growth degrade reliability for existing customers?

Panel: utility-state x year, EIA-861 2013-2024.
Large-load proxy: change in log commercial+industrial MWh per customer (data centers are billed
in these classes). It is a PROXY for large-load growth, not a data-center measure.

Cleaning (all documented in the report):
  * keep rows with reliability reported and >= 100 customers
  * drop utility-years whose customer count moved > 25% in a year (mergers / reclassification)
  * SAIDI/SAIFI no-MED values that are 0 or exceed the with-MED value are treated as invalid
  * outcome values > 12x from the utility's own median (|ln dev| > 2.5, >= 4 obs) are set missing
    as probable reporting-unit errors (about 0.5% of rows)
  * outcomes are logged and winsorised at 1/99 pct; the regressor is winsorised at 1/99 pct

Model: PanelOLS, utility effects + (year | state x year) effects, SEs clustered by utility.
state x year effects absorb regional weather/storm severity, standing in for PRISM data.

Outputs: results/rq3_results.csv, results/rq3_robustness.csv, data/processed/rq3_panel.parquet
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]


def winsor(s, lo=0.01, hi=0.99):
    a, b = s.quantile([lo, hi])
    return s.clip(a, b)


def build() -> pd.DataFrame:
    p = pd.read_parquet(ROOT / "data/processed/eia861_panel.parquet")
    p = p[(p["_merge"] == "both") & p.saidi_med.notna() & (p.total_cust >= 100)].copy()
    p["key"] = p.util_num.astype(int).astype(str) + "_" + p.state
    p["ci_mwh"] = p.com_mwh + p.ind_mwh
    p = p[p.ci_mwh > 0].sort_values(["key", "year"]).reset_index(drop=True)
    p["ln_cust"] = np.log(p.total_cust)
    p["ln_ci_pc"] = np.log(p.ci_mwh / p.total_cust)
    g = p.groupby("key")
    consec = g.year.diff() == 1
    p["d_ln_ci_pc"] = g.ln_ci_pc.diff().where(consec)
    p["d_ln_cust"] = g.ln_cust.diff().where(consec)
    p["d_ln_ci_pc_l1"] = p.groupby("key").d_ln_ci_pc.shift(1).where(g.year.diff() == 1)
    n0 = len(p)
    p = p[~(p.d_ln_cust.abs() > 0.25)]
    # outcomes
    ok_nomed = (p.saidi_nomed >= 1) & (p.saidi_nomed <= p.saidi_med * 1.001)
    p["ln_saidi_nomed"] = np.log(p.saidi_nomed.where(ok_nomed))
    p["ln_saidi_med"] = np.log(p.saidi_med.where(p.saidi_med >= 1))
    ok_f = (p.saifi_nomed >= 0.01) & (p.saifi_nomed <= p.saifi_med * 1.001)
    p["ln_saifi_nomed"] = np.log(p.saifi_nomed.where(ok_f))
    p["ln_saifi_med"] = np.log(p.saifi_med.where(p.saifi_med >= 0.01))
    # reporting-error rule: > 12x (|ln dev| > 2.5) from the utility's own median, utilities with >= 4 obs.
    # Catches hours-vs-minutes style errors; ~0.5% of rows.
    for c in ["ln_saidi_nomed", "ln_saidi_med", "ln_saifi_nomed", "ln_saifi_med"]:
        dev = p[c] - p.groupby("key")[c].transform("median")
        cnt = p.groupby("key")[c].transform("count")
        p.loc[(dev.abs() > 2.5) & (cnt >= 4), c] = np.nan
        p[c] = winsor(p[c])
    for c in ["d_ln_ci_pc", "d_ln_ci_pc_l1", "d_ln_cust"]:
        p[c] = winsor(p[c])
    p["surge"] = (p.d_ln_ci_pc > 0.10).astype(float).where(p.d_ln_ci_pc.notna())
    p["surge_l1"] = p.groupby("key").surge.shift(1)
    p["state_year"] = p.state + "_" + p.year.astype(str)
    print(f"panel rows {n0} -> {len(p)} after dropping customer jumps >25%")
    return p


def fit(d, y, xs, fe="state_year"):
    d = d.dropna(subset=[y, *xs]).copy()
    # singleton state-year cells carry no information; drop so effects are estimable
    d = d[d.groupby("state_year").key.transform("size") > 1] if fe == "state_year" else d
    d = d.set_index(["key", "year"])
    kw = {"entity_effects": True}
    if fe == "year":
        kw["time_effects"] = True
    else:
        kw["other_effects"] = d["state_year"]
    r = PanelOLS(d[y], d[xs], **kw).fit(cov_type="clustered", cluster_entity=True)
    return r, d


def row(label, y, r, xs, d):
    out = {"spec": label, "outcome": y, "n": int(r.nobs), "utilities": int(r.entity_info["total"])}
    for x in xs:
        if x in ("d_ln_ci_pc", "d_ln_ci_pc_l1", "surge", "surge_l1"):
            b, se = r.params[x], r.std_errors[x]
            out.update({f"{x}_coef": b, f"{x}_se": se, f"{x}_p": r.pvalues[x],
                        f"{x}_lo": b - 1.96 * se, f"{x}_hi": b + 1.96 * se})
    return out


def main() -> None:
    (ROOT / "results").mkdir(exist_ok=True)
    p = build()
    p.to_parquet(ROOT / "data/processed/rq3_panel.parquet", index=False)
    ctl = ["d_ln_cust", "ln_cust"]
    res = []

    # ---- primary outcome, full specification ladder
    y = "ln_saidi_nomed"
    for lab, xs, fe, sub in [
        ("S1 entity+year", ["d_ln_ci_pc"] + ctl, "year", p),
        ("S2 entity+state*year", ["d_ln_ci_pc"] + ctl, "state_year", p),
        ("S3 +lag", ["d_ln_ci_pc", "d_ln_ci_pc_l1"] + ctl, "state_year", p),
        ("S4 2020+ only", ["d_ln_ci_pc", "d_ln_ci_pc_l1"] + ctl, "state_year", p[p.year >= 2020]),
        ("S5 surge dummy", ["surge", "surge_l1"] + ctl, "state_year", p),
        ("S6 Arizona only", ["d_ln_ci_pc", "d_ln_ci_pc_l1"] + ctl, "year", p[p.state == "AZ"]),
    ]:
        try:
            r, d = fit(sub, y, xs, fe)
            res.append(row(lab, y, r, xs, d))
        except Exception as e:  # small subsamples can be rank-deficient
            res.append({"spec": lab, "outcome": y, "error": str(e)[:80]})

    # ---- other outcomes, S2 and S3
    for y2 in ["ln_saidi_med", "ln_saifi_nomed", "ln_saifi_med"]:
        for lab, xs in [("S2 entity+state*year", ["d_ln_ci_pc"] + ctl),
                        ("S3 +lag", ["d_ln_ci_pc", "d_ln_ci_pc_l1"] + ctl)]:
            r, d = fit(p, y2, xs, "state_year")
            res.append(row(lab, y2, r, xs, d))
    R = pd.DataFrame(res)
    R.to_csv(ROOT / "results/rq3_results.csv", index=False)

    # ---- robustness on S3 / primary outcome
    rob = []
    xs = ["d_ln_ci_pc", "d_ln_ci_pc_l1"] + ctl
    r0, d0 = fit(p, "ln_saidi_nomed", xs, "state_year")
    for yr in sorted(p.year.unique()):  # leave one year out
        r, _ = fit(p[p.year != yr], "ln_saidi_nomed", xs, "state_year")
        rob.append({"test": "leave-year-out", "dropped": yr, "coef": r.params["d_ln_ci_pc"],
                    "se": r.std_errors["d_ln_ci_pc"], "n": int(r.nobs)})
    for k in p[p.state == "AZ"].key.unique():  # leave one Arizona utility out
        r, _ = fit(p[p.key != k], "ln_saidi_nomed", xs, "state_year")
        rob.append({"test": "leave-AZ-utility-out", "dropped": k, "coef": r.params["d_ln_ci_pc"],
                    "se": r.std_errors["d_ln_ci_pc"], "n": int(r.nobs)})
    cut = p.d_ln_ci_pc.abs().quantile(0.95)  # drop the most extreme growth observations
    r, _ = fit(p[p.d_ln_ci_pc.abs().fillna(0) <= cut], "ln_saidi_nomed", xs, "state_year")
    rob.append({"test": "drop top5% |growth|", "dropped": "", "coef": r.params["d_ln_ci_pc"],
                "se": r.std_errors["d_ln_ci_pc"], "n": int(r.nobs)})
    # cross-fit: coefficient estimated on random half of utilities, tested on the other half
    rng = np.random.default_rng(0)
    keys = p.key.unique()
    halves = []
    for _ in range(200):
        a = set(rng.choice(keys, len(keys) // 2, replace=False))
        r, _ = fit(p[p.key.isin(a)], "ln_saidi_nomed", xs, "state_year")
        halves.append(r.params["d_ln_ci_pc"])
    rob.append({"test": "200 random half-utility splits", "dropped": "",
                "coef": float(np.mean(halves)), "se": float(np.std(halves)), "n": np.nan})
    ROB = pd.DataFrame(rob)
    ROB.to_csv(ROOT / "results/rq3_robustness.csv", index=False)

    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    show = ["spec", "outcome", "n", "utilities", "d_ln_ci_pc_coef", "d_ln_ci_pc_se", "d_ln_ci_pc_p",
            "d_ln_ci_pc_lo", "d_ln_ci_pc_hi", "d_ln_ci_pc_l1_coef", "d_ln_ci_pc_l1_p", "surge_coef", "surge_p"]
    print("\n=== RQ3 results (coef = change in ln outcome per unit change in ln C&I MWh/customer) ===")
    print(R[[c for c in show if c in R.columns]].round(3).to_string(index=False))
    print("\n=== Robustness (primary outcome, S3 contemporaneous coef) ===")
    print(f"baseline coef = {r0.params['d_ln_ci_pc']:.3f} (se {r0.std_errors['d_ln_ci_pc']:.3f})")
    print(ROB.groupby("test").coef.agg(["count", "min", "median", "max"]).round(3).to_string())
    print("\nMDE (80% power, 5% two-sided) for S3 contemporaneous = 2.8 x se =",
          round(2.8 * r0.std_errors["d_ln_ci_pc"], 3))
    print("sd of regressor (winsorised):", round(p.d_ln_ci_pc.std(), 3))


if __name__ == "__main__":
    main()
