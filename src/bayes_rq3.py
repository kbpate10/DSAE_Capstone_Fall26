"""Shared Bayesian hierarchical model (PyMC) applied to the RQ3 reliability panel.

y_it = a_i + g_{state,year} + b_i * x_it + d1*dcust_it + d2*lncust_it + e,  e ~ StudentT
  a_i        ~ N(mu_a, sig_a)                      utility intercepts (partial pooling)
  g_{s,t}    ~ N(0, sig_g)                         state x year shocks (weather/storm severity)
  b_i        ~ N(mu_b + tau_b * u_state(i), sig_b) utility-specific large-load effect,
                                                   pooled within state and across states
x = change in log C&I MWh/customer (per 1 SD); y = log SAIDI without major events.

Usage: bayes_rq3.py full|holdout2024
  full        : fit all years (inference)
  holdout2024 : fit 2013-2023, predict 2024 -> credible-interval calibration check
Outputs: results/bayes_{mode}_*.csv, data/processed/bayes_{mode}_trace.nc
"""
import sys
import warnings
from pathlib import Path

import arviz as az
import numpy as np
import pandas as pd
import pymc as pm

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
mode = sys.argv[1] if len(sys.argv) > 1 else "full"

p = pd.read_parquet(ROOT / "data/processed/rq3_panel.parquet")
p = p.dropna(subset=["ln_saidi_nomed", "d_ln_ci_pc", "d_ln_cust"]).reset_index(drop=True)
sx = p.d_ln_ci_pc.std()
p["x"] = p.d_ln_ci_pc / sx
p["c1"] = (p.d_ln_cust - p.d_ln_cust.mean()) / p.d_ln_cust.std()
p["c2"] = (p.ln_cust - p.ln_cust.mean()) / p.ln_cust.std()          # size level (noise scale only)
p["c2w"] = p.ln_cust - p.groupby("key").ln_cust.transform("mean")    # within-utility size change (mean)
p["c2w"] = p.c2w / p.c2w.std()

keys, uidx = np.unique(p.key, return_inverse=True)
p["uidx"] = uidx
ust = p.groupby("uidx").state.first().sort_index()
states, sidx_u = np.unique(ust.values, return_inverse=True)
sy_keys, syidx = np.unique(p.state_year, return_inverse=True)
p["syidx"] = syidx

train = p if mode == "full" else p[p.year <= 2023]
test = p[p.year == 2024] if mode != "full" else None
if test is not None:
    # evaluate only utilities seen in training (a brand-new utility has no estimable intercept)
    n_all = len(test)
    test = test[test.key.isin(train.key.unique())].copy()
    print(f"holdout rows: {len(test)} of {n_all} (dropped {n_all - len(test)} from utilities unseen in training)")
y_mu = train.ln_saidi_nomed.mean()

with pm.Model() as m:
    mu_a = pm.Normal("mu_a", y_mu, 2)
    sig_a = pm.HalfNormal("sig_a", 1)
    z_a = pm.Normal("z_a", 0, 1, shape=len(keys))
    a = pm.Deterministic("a", mu_a + sig_a * z_a)
    sig_g = pm.HalfNormal("sig_g", 0.5)
    z_g = pm.Normal("z_g", 0, 1, shape=len(sy_keys))
    g = pm.Deterministic("g", sig_g * z_g)
    mu_b = pm.Normal("mu_b", 0, 0.5)
    tau_b = pm.HalfNormal("tau_b", 0.3)
    u_s = pm.Normal("u_s", 0, 1, shape=len(states))
    sig_b = pm.HalfNormal("sig_b", 0.3)
    z_b = pm.Normal("z_b", 0, 1, shape=len(keys))
    b = pm.Deterministic("b", mu_b + tau_b * u_s[sidx_u] + sig_b * z_b)
    d1 = pm.Normal("d1", 0, 0.5)
    d2 = pm.Normal("d2", 0, 0.5)
    s0 = pm.Normal("s0", np.log(0.4), 1)      # log noise sd at average utility size
    s1 = pm.Normal("s1", 0, 0.5)              # noise falls (s1<0) with utility size
    nu = pm.Gamma("nu", 2, 0.1) + 2
    mu = (a[train.uidx.values] + g[train.syidx.values] + b[train.uidx.values] * train.x.values
          + d1 * train.c1.values + d2 * train.c2w.values)
    sig_y = pm.math.exp(s0 + s1 * train.c2.values)
    pm.StudentT("y", nu=nu, mu=mu, sigma=sig_y, observed=train.ln_saidi_nomed.values)
    idata = pm.sample(draws=600, tune=800, chains=4, cores=4, target_accept=0.9,
                      random_seed=1, progressbar=False)

az.to_netcdf(idata, ROOT / f"data/processed/bayes_{mode}_trace.nc") if hasattr(az, "to_netcdf") else idata.to_netcdf(ROOT / f"data/processed/bayes_{mode}_trace.nc")
post = idata.posterior
S = lambda v: post[v].stack(s=("chain", "draw")).values  # (..., samples)

# ---- population-level summary (effects reported per 1 SD of C&I-per-customer growth and per +10%)
summ = az.summary(idata, var_names=["mu_b", "tau_b", "sig_b", "sig_a", "sig_g", "s0", "s1", "nu", "d1", "d2"],
                  hdi_prob=0.95)
summ.to_csv(ROOT / f"results/bayes_{mode}_summary.csv")
print(summ.round(3).to_string())
mb = S("mu_b")
per10 = mb / sx * 0.10
print(f"\nPopulation effect of +10% C&I load/customer on SAIDI(no MED): "
      f"{100*np.mean(per10):+.2f}% [95% CrI {100*np.percentile(per10,2.5):+.2f}, {100*np.percentile(per10,97.5):+.2f}]"
      f"  P(effect>0)={np.mean(per10>0):.2f}")
print(f"between-utility sd of effect (sig_b, per 1 SD): {S('sig_b').mean():.3f}; between-state tau_b: {S('tau_b').mean():.3f}")

# ---- utility-level effects, Arizona
B = S("b") / sx * 0.10 * 100  # % change in SAIDI per +10% load
info = p.groupby("uidx").agg(key=("key", "first"), state=("state", "first"), name=("util_name", "last"),
                             n_obs=("year", "size"))
info["post_mean_pct_per10"] = B.mean(axis=1)
info["lo"] = np.percentile(B, 2.5, axis=1)
info["hi"] = np.percentile(B, 97.5, axis=1)
info["P_harm"] = (B > 0).mean(axis=1)
info.to_csv(ROOT / f"results/bayes_{mode}_utility_effects.csv")
az_ = info[info.state == "AZ"].sort_values("post_mean_pct_per10", ascending=False)
print("\nArizona utilities: % change in SAIDI per +10% C&I load/customer (partial-pooling posterior)")
print(az_[["name", "n_obs", "post_mean_pct_per10", "lo", "hi", "P_harm"]].round(2).to_string(index=False))
print("\nShare of all utilities with 95% CrI excluding zero:",
      round(float(((info.lo > 0) | (info.hi < 0)).mean()), 3))

# ---- calibration on held-out 2024 (posterior predictive, new state-year shocks drawn from prior where unseen)
if test is not None:
    rng = np.random.default_rng(0)
    a_s, b_s, g_s = S("a"), S("b"), S("g")
    d1s, d2s, s0s, s1s, nus = S("d1"), S("d2"), S("s0"), S("s1"), S("nu") + 2  # model: nu = Gamma + 2
    ns = a_s.shape[1]
    sel = rng.choice(ns, 400, replace=False)
    preds = np.empty((len(test), len(sel)))
    mus = np.empty_like(preds)
    for j, s in enumerate(sel):
        mu_t = (a_s[test.uidx.values, s] + g_s[test.syidx.values, s] + b_s[test.uidx.values, s] * test.x.values
                + d1s[s] * test.c1.values + d2s[s] * test.c2w.values)
        sd_t = np.exp(s0s[s] + s1s[s] * test.c2.values)
        mus[:, j] = mu_t
        preds[:, j] = mu_t + sd_t * rng.standard_t(nus[s], len(test))
    y = test.ln_saidi_nomed.values
    out = []
    for lv in (0.5, 0.8, 0.9, 0.95):
        lo, hi = np.percentile(preds, [(1 - lv) / 2 * 100, (1 + lv) / 2 * 100], axis=1)
        out.append({"nominal": lv, "empirical_coverage": float(np.mean((y >= lo) & (y <= hi))), "n": len(y)})
    cal = pd.DataFrame(out)
    cal.to_csv(ROOT / "results/bayes_calibration_2024.csv", index=False)
    print("\nHeld-out 2024 credible-interval calibration (n=%d):" % len(y))
    print(cal.round(3).to_string(index=False))
    prev = (test[["key"]].merge(p[p.year == 2023][["key", "ln_saidi_nomed"]], on="key", how="left")
            .ln_saidi_nomed.values)
    util_mean = train.groupby("key").ln_saidi_nomed.mean()
    um = test.key.map(util_mean).values
    both = ~np.isnan(prev)
    rm = lambda e: float(np.sqrt(np.mean(e ** 2)))
    pm_ = mus.mean(axis=1)  # posterior mean of the location (point forecast)
    print("held-out RMSE (log SAIDI), same rows (n=%d with a 2023 value):" % both.sum())
    print("   bayes hierarchical      : %.3f" % rm((pm_ - y)[both]))
    print("   persistence (2023 value): %.3f" % rm((prev - y)[both]))
    print("   utility training mean   : %.3f" % rm((um - y)[both]))
    print("   bayes on all %d rows     : %.3f" % (len(y), rm(pm_ - y)))
div = int(idata.sample_stats.diverging.sum())
print("\ndivergences:", div, "| max Rhat:", float(az.rhat(idata, var_names=["mu_b", "sig_b", "tau_b", "sig_a", "s0", "s1", "nu", "d2"]).to_array().max()),
      "| min ESS(bulk) mu_b:", float(az.ess(idata, var_names=["mu_b"]).mu_b))
