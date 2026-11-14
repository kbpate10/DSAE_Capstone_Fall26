"""Numbers behind docs/ARIZONA_CASE_STUDY.md, computed from project files (nothing typed in by hand except the labelled assumptions).

1. Water-surcharge illustration. The Governor's proposed per-gallon fee on data-center water has no enacted rate (amount to be
   set by the ADWR director; docs/regulatory_context_check.md). The rates below are HYPOTHETICAL. Gallons come from the
   scenario on-site cooling water of a 500 MW project (stage2_cell_footprint.csv: water_on_Mm3, which uses the evaporative-cooling
   curve of water_frontier.py, WUE_MAX 1.85 L/kWh). Because real facilities may use closed-loop or dry cooling, the evaporative
   share is varied (100%, 50%, 25%). Generation-side (off-site) water is excluded: a data-center surcharge would not apply to it.
   Reference point from the press estimate in regulatory_context_check.md: a penny a gallon ~ $6.5 million a year, i.e. an implied
   base of about 650 million gallons a year (derived here, source figure not verified).
2. Reliability bound for a large project. For each utility that can host a project (stage1_optimizer.n_max >= 1), projected SAIDI =
   baseline * (1 + E / CI_u) ** beta with beta the UPPER 95% RQ3 elasticity (0.257): a conservative bound, not a forecast. Only
   valid where E / CI_u is within the 25% support limit.

Outputs: results/case_study_surcharge.csv, results/case_study_reliability_bound.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage1_optimizer as s1

GAL_PER_MM3 = 264.172e6          # US gallons per million cubic metres
RATES = (0.001, 0.005, 0.01)     # hypothetical $/gallon
SHARES = (1.0, 0.5, 0.25)        # evaporative share of the modelled on-site water
PRESS_USD, PRESS_RATE = 6.5e6, 0.01


def main() -> None:
    fp = pd.read_csv(ROOT / "results/stage2_cell_footprint.csv")
    default = pd.read_csv(ROOT / "results/stage1_selection_default.csv")
    default = default[default["mapping"] == "all"].cell_id.tolist()
    rows = []
    groups = {"default Stage 1 cells": fp[fp.cell_id.isin(default)], "all BA-mapped eligible cells (min)": fp, "all BA-mapped eligible cells (max)": fp}
    for label, g in groups.items():
        if label.endswith("(min)"):
            g = g.loc[[g.water_on_Mm3.idxmin()]]
        elif label.endswith("(max)"):
            g = g.loc[[g.water_on_Mm3.idxmax()]]
        for _, r in g.iterrows():
            for share in SHARES:
                gal = r.water_on_Mm3 * share * GAL_PER_MM3
                row = {"group": label, "cell_id": r.cell_id, "ba": r.ba, "county": r.county_short, "evaporative_share": share,
                       "on_site_Mm3_yr": r.water_on_Mm3 * share, "gallons_million_yr": gal / 1e6}
                for rate in RATES:
                    row[f"usd_million_at_{rate}"] = gal * rate / 1e6
                rows.append(row)
    S = pd.DataFrame(rows)
    S.round(3).to_csv(ROOT / "results/case_study_surcharge.csv", index=False)
    pd.set_option("display.width", 220)
    print(f"Press-implied base: ${PRESS_USD / 1e6:.1f}M at ${PRESS_RATE}/gal = {PRESS_USD / PRESS_RATE / 1e6:.0f} million gallons/yr")
    print("\nOn-site water and illustrative surcharge, one 500 MW project (hypothetical rates):")
    print(S.round(1).to_string(index=False))

    util = s1.utility_table()
    beta = s1.beta_upper()
    rows = []
    for P in (100, 250, 500):
        E = P * s1.LF * s1.HRS
        for u, r in util.iterrows():
            if not np.isfinite(r.baseline_saidi) or not np.isfinite(r.ci_mwh) or r.ci_mwh <= 0:
                continue
            a = E / r.ci_mwh
            if a > s1.DEFAULT["A_max"]:
                continue
            f = (1 + a) ** beta
            rows.append({"utility_num": u, "P_MW": P, "added_load_share_of_CI": a, "baseline_saidi_min": r.baseline_saidi,
                         "projected_saidi_min_upper_bound": r.baseline_saidi * f, "increase_pct_upper_bound": 100 * (f - 1)})
    B = pd.DataFrame(rows)
    nm = pd.read_parquet(ROOT / "data/processed/cell_utility_shares_all.parquet")[["util_num", "util_name"]].dropna().drop_duplicates("util_num")
    B = B.merge(nm.assign(utility_num=nm.util_num.astype(int))[["utility_num", "util_name"]], on="utility_num", how="left")
    B.round(3).to_csv(ROOT / "results/case_study_reliability_bound.csv", index=False)
    print(f"\nReliability bound (beta upper = {beta:.3f}); projects within the 25% support limit only:")
    print(B.sort_values(["P_MW", "added_load_share_of_CI"]).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
