"""Quality control for EIA-930 region-data series (demand D, net generation NG, total interchange TI).

EIA-930 region data contain glitches that wreck regressions on demand changes: 32-bit sentinels (2,147,483,647), non-positive demand, values tens to hundreds of
times the typical level, and long stretches of near-zero demand in some BAs. Two rules, both setting a bad value to NaN (flag, do not impute):

  'band'    (primary)   D: bad if <= 0 or outside [0.3, 2.5] times the median of the same series for the same BA, local standard-time month and hour of day
                        (natural variation in clean BAs stays within about 0.55-1.95 of that median; glitches sit below 0.3 or above 2.5).
                        TI: bad if |TI| exceeds 3 times the 99.5th percentile of |TI| for that BA.
  'legacy5x' (secondary) D: bad if <= 0 or above 5 times the BA's median demand; TI: bad if |TI| above 5 times the median demand.
NG is not used in the stability analysis and, unlike demand, legitimately varies by large factors in hydro- and wind-heavy BAs, so only its sentinels are removed.
Sentinels (|value| >= 1e9) are removed first under both rules.

The bands and the percentile multiplier were chosen from a diagnostic of the ratio distribution across BAs that computed no stability metric and no association with
anything (docs/MEF_SCAN_PREREG.md, deviation 4). Local time is fixed standard time (caller supplies the UTC offset).
"""
import numpy as np
import pandas as pd

LO, HI, TI_MULT, TI_Q = 0.3, 2.5, 3.0, 0.995


def clean_region(r: pd.DataFrame, tz: int, mode: str = "band") -> tuple[pd.DataFrame, dict]:
    """r: index = UTC timestamp, columns D, NG, TI. Returns the cleaned frame and counts of values removed per series."""
    r = r.copy()
    n = {}
    for c in ("D", "NG", "TI"):
        sent = r[c].abs() >= 1e9
        n[f"{c}_sentinel"] = int(sent.sum())
        r.loc[sent, c] = np.nan
    med_d = r.D.median()
    if mode == "legacy5x":
        bad = (r.D <= 0) | (r.D > 5 * med_d)
        n["D_implausible"] = int(bad.sum())
        r.loc[bad, "D"] = np.nan
        bad = r.TI.abs() > 5 * med_d
    else:
        loc = r.index + pd.Timedelta(hours=tz)
        key = pd.Series(list(zip(loc.month, loc.hour)), index=r.index)
        m = r.D.groupby(key).transform("median")
        ratio = r.D / m
        bad = r.D.notna() & ((r.D <= 0) | (ratio < LO) | (ratio > HI))
        n["D_implausible"] = int(bad.sum())
        r.loc[bad, "D"] = np.nan
        bad = r.TI.abs() > TI_MULT * r.TI.abs().quantile(TI_Q)
    n["TI_implausible"] = int(bad.sum())
    r.loc[bad, "TI"] = np.nan
    return r, n
