"""RQ3 naive baselines and the 'ladder' from unconditional comparison to fixed effects.

All rungs use the SAME sample (rows with outcome, exposure and controls present) so differences between
rungs come from the specification, not the sample. Exposure = change in log C&I MWh per customer.
Reported as % change in SAIDI (no major events) for a +10% change in exposure; 'surge' rows report the
% difference between utility-years with >10% growth and all others.
Outputs: results/rq3_baseline_ladder.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from linearmodels.panel import PanelOLS

ROOT = Path(__file__).resolve().parents[1]
p = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet")
need = ["ln_saidi_nomed", "d_ln_ci_pc", "d_ln_cust", "ln_cust", "ownership", "surge"]
d = p.dropna(subset=need).copy()
d["ownership"] = d.ownership.astype(str)
d["yr"] = d.year.astype(int).astype(str)
print(f"common sample: {len(d)} utility-years, {d.key.nunique()} utilities")
pct = lambda b: (np.exp(b * np.log(1.10)) - 1) * 100
rows = []


def add(label, b, lo, hi, p_, kind="exposure"):
    f = (lambda x: (np.exp(x) - 1) * 100) if kind == "surge" else pct
    rows.append({"rung": label, "pct_change": f(b), "lo": f(lo), "hi": f(hi), "p": p_, "n": len(d), "kind": kind})


def ols(formula, label, var, kind="exposure"):
    m = smf.ols(formula, d).fit(cov_type="cluster", cov_kwds={"groups": d.key})
    ci = m.conf_int().loc[var]
    add(label, m.params[var], ci[0], ci[1], m.pvalues[var], kind)


# unconditional
ols("ln_saidi_nomed ~ surge", "U1  Surge utility-years vs all others (no controls)", "surge", "surge")
ols("ln_saidi_nomed ~ d_ln_ci_pc", "U2  Pooled OLS, exposure only", "d_ln_ci_pc")
# adding controls
ols("ln_saidi_nomed ~ d_ln_ci_pc + ln_cust + d_ln_cust + C(ownership)", "C1  + size, customer growth, ownership", "d_ln_ci_pc")
ols("ln_saidi_nomed ~ d_ln_ci_pc + ln_cust + d_ln_cust + C(ownership) + C(yr)", "C2  + year effects", "d_ln_ci_pc")
ols("ln_saidi_nomed ~ d_ln_ci_pc + ln_cust + d_ln_cust + C(ownership) + C(yr) + C(state)", "C3  + state effects", "d_ln_ci_pc")
# fixed effects
dd = d.set_index(["key", "year"])
for label, kw in [("F1  Utility fixed effects", dict(entity_effects=True)),
                  ("F2  + year effects", dict(entity_effects=True, time_effects=True)),
                  ("F3  + state x year effects (main spec)", dict(entity_effects=True, other_effects=dd["state_year"]))]:
    r = PanelOLS(dd.ln_saidi_nomed, dd[["d_ln_ci_pc", "d_ln_cust", "ln_cust"]], **kw).fit(cov_type="clustered", cluster_entity=True)
    b, se = r.params["d_ln_ci_pc"], r.std_errors["d_ln_ci_pc"]
    add(label, b, b - 1.96 * se, b + 1.96 * se, r.pvalues["d_ln_ci_pc"])
R = pd.DataFrame(rows)
R.to_csv(ROOT / "results/rq3_baseline_ladder.csv", index=False)
pd.set_option("display.width", 200)
print(R[["rung", "pct_change", "lo", "hi", "p"]].round(2).to_string(index=False))
print("\nRaw group means (ln SAIDI, no-MED): surge vs non-surge, and SAIDI minutes")
g = d.groupby("surge").agg(n=("ln_saidi_nomed", "size"), mean_ln=("ln_saidi_nomed", "mean"), median_saidi=("saidi_nomed", "median"))
print(g.round(2).to_string())
print("\ncorr(exposure, ln SAIDI level):", round(d.d_ln_ci_pc.corr(d.ln_saidi_nomed), 3),
      "| corr(exposure, ln_cust):", round(d.d_ln_ci_pc.corr(d.ln_cust), 3))
