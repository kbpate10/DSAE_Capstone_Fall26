"""RQ3 power analysis: what reliability effect could the public panel detect?

RQ3 found no effect. Whether that is informative depends on how small an effect the design could see. This script uses the
actual panel (data/processed/rq3_panel.parquet, built by rq3_model.py) and the same estimator (utility effects + state-by-year
effects, SEs clustered by utility, outcome log SAIDI without major events) and reports:

  1. Minimum detectable effect (MDE) at 80% power, 5% two-sided test:  MDE = (1.96 + 0.84) * SE.
  2. Power curves from the estimated SE, for
       a. the continuous exposure (change in log C&I MWh per customer), all utilities and Arizona only
       b. surge indicators (growth above 10%, 25%, 50% log points in a year), which is the data-center-like event
  3. A simulation check of (2a): pure-noise outcomes are rebuilt by removing the fitted exposure effect, a known effect is
     injected, utilities are resampled with replacement (cluster bootstrap), the model is refit, and the share of fits whose
     95% interval excludes zero is the power.
  4. How many utility-years and utilities actually carry large surges.
  5. Extremes check. rq3_model.py winsorises the exposure at the 1st/99th percentile (99th = 0.27 log points), which clips 106
     utility-years, including every one of the 28 with growth above 50%: the events closest to data-center-scale load. The
     unclipped exposure (d_ln_ci_pc_raw) is re-estimated with no clipping, with clipping at the 99.9th percentile, and with
     the extremes (|growth| > 0.5) dropped, and surge indicators use the unclipped growth.

Effects are reported as % change in SAIDI: per +10% C&I load for the continuous exposure (elasticity x ln 1.1), and per surge year
for the indicators. The question is then whether the effect a large project could plausibly have is above the MDE.
Limits: the power is for THIS proxy. Most C&I growth is not data centers, so power for a data-center-specific effect is lower still
if only a small share of the proxy's variation comes from data centers (attenuation).

Outputs: results/rq3_power.csv, results/rq3_power_sim.csv, results/rq3_extremes.csv, results/figures/rq3_power_curve.png
"""
import sys
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rq3_model as m

Z = norm.ppf(0.975) + norm.ppf(0.80)
CTL = ["d_ln_cust", "ln_cust"]
Y = "ln_saidi_nomed"
NSIM = 120
SIM_ELASTICITIES = (0.05, 0.10, 0.20, 0.30)       # injected true elasticities of SAIDI on d_ln_ci_pc
LN110 = np.log(1.10)


def power(delta, se):
    z = abs(delta) / se
    return norm.cdf(z - norm.ppf(0.975)) + norm.cdf(-z - norm.ppf(0.975))


def main() -> None:
    p = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet")
    rows = []

    # ---- 4. how much surge variation exists
    d = p.dropna(subset=["d_ln_ci_pc", Y])
    print(f"estimation sample: {len(d)} utility-years, {d.key.nunique()} utilities; exposure sd {d.d_ln_ci_pc.std():.3f} (log points)")
    for g in (0.10, 0.25, 0.50):
        s = d[d.d_ln_ci_pc_raw > g]
        print(f"  unclipped growth > {g:.0%} (log points): {len(s)} utility-years in {s.key.nunique()} utilities; in Arizona {int((s.state == 'AZ').sum())}")
    print(f"  Arizona utility-years: {int((d.state == 'AZ').sum())} in {d[d.state == 'AZ'].key.nunique()} utilities")

    # ---- 1/2a continuous exposure
    for lab, sub in (("all utilities", p), ("Arizona only", p[p.state == "AZ"])):
        fe = "state_year" if lab == "all utilities" else "year"
        r, _ = m.fit(sub, Y, ["d_ln_ci_pc"] + CTL, fe)
        b, se = r.params["d_ln_ci_pc"], r.std_errors["d_ln_ci_pc"]
        rows.append({"design": f"continuous exposure, {lab}", "n": int(r.nobs), "utilities": int(r.entity_info["total"]),
                     "estimate_pct": 100 * b * LN110, "se_pct": 100 * se * LN110, "mde80_pct": 100 * Z * se * LN110,
                     "unit": "% SAIDI per +10% C&I load"})

    # ---- 5 extremes check (S2 specification, continuous exposure)
    ext = []
    q99 = p.d_ln_ci_pc_raw.quantile(0.999)
    variants = {
        "winsorised 1/99 (main spec)": (p, "d_ln_ci_pc"),
        "unclipped": (p, "d_ln_ci_pc_raw"),
        "clipped at 99.9th pct": (p.assign(x999=p.d_ln_ci_pc_raw.clip(upper=q99, lower=p.d_ln_ci_pc_raw.quantile(0.001))), "x999"),
        "extremes dropped (|growth| > 0.5)": (p[p.d_ln_ci_pc_raw.abs() <= 0.5], "d_ln_ci_pc_raw"),
    }
    for lab, (sub, col) in variants.items():
        r, _ = m.fit(sub, Y, [col] + CTL, "state_year")
        b, se = r.params[col], r.std_errors[col]
        ext.append({"variant": lab, "n": int(r.nobs), "elasticity": b, "se": se,
                    "effect_pct_per_10pct_load": 100 * b * LN110, "lo": 100 * (b - 1.96 * se) * LN110, "hi": 100 * (b + 1.96 * se) * LN110,
                    "mde80_pct": 100 * Z * se * LN110})
    E = pd.DataFrame(ext)
    E.round(3).to_csv(ROOT / "results/rq3_extremes.csv", index=False)
    print("\nExtremes check: effect of +10% C&I load on SAIDI (%), S2 specification:")
    print(E.round(2).to_string(index=False))
    rows.append({"design": "continuous exposure, all utilities, unclipped", "n": int(E.n[1]), "estimate_pct": E.effect_pct_per_10pct_load[1],
                 "se_pct": 100 * E.se[1] * LN110, "mde80_pct": E.mde80_pct[1], "unit": "% SAIDI per +10% C&I load"})

    # ---- 2b surge indicators on the UNCLIPPED growth
    for g in (0.10, 0.25, 0.50):
        q = p.copy()
        q["surge_g"] = (q.d_ln_ci_pc_raw > g).astype(float).where(q.d_ln_ci_pc_raw.notna())
        if q.surge_g.sum() < 5:
            continue
        r, dd = m.fit(q, Y, ["surge_g"] + CTL, "state_year")
        b, se = r.params["surge_g"], r.std_errors["surge_g"]
        treated = dd[dd.surge_g == 1]
        rows.append({"design": f"surge indicator, growth > {g:.0%}", "n": int(r.nobs), "utilities": int(r.entity_info["total"]),
                     "treated_utility_years": len(treated), "treated_utilities": treated.index.get_level_values(0).nunique(),
                     "estimate_pct": 100 * (np.exp(b) - 1), "se_pct": 100 * se,
                     "mde80_pct": 100 * (np.exp(Z * se) - 1), "unit": "% SAIDI in a surge year"})
    R = pd.DataFrame(rows)
    R.round(2).to_csv(ROOT / "results/rq3_power.csv", index=False)
    pd.set_option("display.width", 220)
    print("\nMinimum detectable effect (80% power, 5% two-sided):")
    print(R.round(2).to_string(index=False))

    # ---- 3 simulation check of the continuous design
    r0, d0 = m.fit(p, Y, ["d_ln_ci_pc"] + CTL, "state_year")
    b0 = r0.params["d_ln_ci_pc"]
    base = p.copy()
    base[Y] = base[Y] - b0 * base.d_ln_ci_pc                         # remove the fitted exposure effect
    groups = {k: g for k, g in base.groupby("key")}
    keys = np.array(list(groups))
    rng = np.random.default_rng(0)
    sim = []
    t0 = time.time()
    for el in SIM_ELASTICITIES:
        hit = []
        for i in range(NSIM):
            pick = rng.choice(keys, len(keys))
            bs = pd.concat([groups[k].assign(key=f"{k}#{j}") for j, k in enumerate(pick)], ignore_index=True)
            bs[Y] = bs[Y] + el * bs.d_ln_ci_pc
            try:
                r, _ = m.fit(bs, Y, ["d_ln_ci_pc"] + CTL, "state_year")
                b, se = r.params["d_ln_ci_pc"], r.std_errors["d_ln_ci_pc"]
                hit.append((b - 1.96 * se > 0) or (b + 1.96 * se < 0))
            except Exception:
                continue
        sim.append({"true_elasticity": el, "true_effect_pct_per_10pct_load": 100 * el * LN110, "reps": len(hit),
                    "simulated_power": float(np.mean(hit)),
                    "analytic_power": float(power(el, r0.std_errors["d_ln_ci_pc"]))})
        print(f"  simulated elasticity {el}: power {np.mean(hit):.2f} (analytic {sim[-1]['analytic_power']:.2f})  [{time.time() - t0:.0f}s]")
    S = pd.DataFrame(sim)
    S.round(3).to_csv(ROOT / "results/rq3_power_sim.csv", index=False)

    # ---- figure
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    x = np.linspace(0, 12, 200)
    for _, r_ in R[R.design.str.startswith("continuous")].iterrows():
        ax[0].plot(x, [power(v / 100, r_.se_pct / 100) for v in x], label=r_.design.replace("continuous exposure, ", ""))
    ax[0].plot(S.true_effect_pct_per_10pct_load, S.simulated_power, "ko", ms=5, label="simulation check")
    ax[0].axhline(0.8, color="#888", ls=":", lw=1)
    ax[0].set_xlabel("true effect: % change in SAIDI per +10% C&I load"); ax[0].set_ylabel("power (5% two-sided)")
    ax[0].set_title("Continuous exposure: power vs true effect", fontsize=10); ax[0].legend(frameon=False, fontsize=8); ax[0].grid(alpha=.25)
    x2 = np.linspace(0, 40, 200)
    for _, r_ in R[R.design.str.startswith("surge")].iterrows():
        ax[1].plot(x2, [power(np.log1p(v / 100), r_.se_pct / 100 / (1 + r_.estimate_pct / 100)) for v in x2],
                   label=r_.design.replace("surge indicator, ", "") + f" ({int(r_.treated_utility_years)} yrs)")
    ax[1].axhline(0.8, color="#888", ls=":", lw=1)
    ax[1].set_xlabel("true effect: % change in SAIDI in a surge year"); ax[1].set_ylabel("power (5% two-sided)")
    ax[1].set_title("Surge years (data-center-like events): power vs true effect", fontsize=10)
    ax[1].legend(frameon=False, fontsize=8); ax[1].grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/rq3_power_curve.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
