"""Stage 1 with a feasibility screen learned from real data-center locations.

Two scores answer two different questions:
  feasibility    where operators actually build: propensity from population and substation proximity
                 (infrastructure-only logistic model fitted to OpenStreetMap-mapped data centers; revealed_preference.py)
  suitability    environmental score (water depth, heat, solar, queue strain; rq2_siting.py)
A candidate cell is feasible if at least half of its 0.05-degree sub-cells fall in the top q of propensity.
The optimizer is the same as stage1_optimizer.py (per-utility reliability/absorption caps, site budget K);
the objective stays environmental suitability, now restricted to feasible cells.

Outputs: results/stage1_revealed_*.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import revealed_preference as rp
import stage1_optimizer as s1

INF = ["log_pop_10km", "dist_sub_km", "dist_hv_km"]


def feasibility_table() -> pd.DataFrame:
    c = pd.read_parquet(ROOT / "data/processed/fine_cells_features.parquet")
    y = rp.presence(c, "all")
    mdl = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000)).fit(c[INF].values, y)
    c["propensity"] = mdl.predict_proba(c[INF].values)[:, 1]
    out = pd.DataFrame(index=sorted(c.coarse_cell.unique()))
    for q in (0.25, 0.10, 0.05):
        thr = c.propensity.quantile(1 - q)
        out[f"share_top{int(q*100)}"] = c.groupby("coarse_cell").propensity.apply(lambda s: (s >= thr).mean())
    out["hosts"] = pd.Series(y, index=c.index).groupby(c.coarse_cell).sum()
    return out


def main() -> None:
    cells = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    feas = feasibility_table()
    cells = cells.join(feas)
    util = s1.utility_table(); tau0 = s1.national_median_saidi(); beta = s1.beta_upper()
    rows, picks = [], []
    for tag in ("all", "large"):
        a = s1.assign(tag, util).set_index("cell_id")
        sites = cells.join(a, how="inner")
        sites = sites[sites.util_num.notna()]
        uu = util.loc[sorted(set(sites.util_num.astype(int)))]
        for P in (100, 250, 500):
            for label, mask in (("no screen (environmental only)", pd.Series(True, index=sites.index)),
                                ("feasible: top 25% propensity", sites.share_top25 >= 0.5),
                                ("feasible: top 10% propensity", sites.share_top10 >= 0.5),
                                ("feasible: top 5% propensity", sites.share_top5 >= 0.5)):
                s = sites[mask.fillna(False)]
                ch, obj, _ = s1.run(s, uu, 5, tau0, 0.25, P, beta) if len(s) else ([], 0.0, {})
                sel = s.loc[ch] if ch else s.iloc[0:0]
                rows.append({"mapping": tag, "P_MW": P, "screen": label, "feasible_cells": int(len(s)),
                             "sites_selected": len(ch), "sum_score": obj,
                             "mean_score": obj / len(ch) if ch else np.nan,
                             "mean_rank": sel["rank"].mean() if ch else np.nan,
                             "mean_feasibility_top10": sel.share_top10.mean() if ch else np.nan,
                             "known_hosts_in_selected_cells": int(sel.hosts.sum()) if ch else 0,
                             "counties": ", ".join(sorted(set(sel.county_short))) if ch else ""})
                if P == 250:
                    picks.append(sel.assign(mapping=tag, screen=label, P_MW=P))
    R = pd.DataFrame(rows)
    R.to_csv(ROOT / "results/stage1_revealed_summary.csv", index=False)
    pd.concat(picks).reset_index().to_csv(ROOT / "results/stage1_revealed_selection.csv", index=False)
    pd.set_option("display.width", 230)
    print(R[R.mapping == "all"][["P_MW", "screen", "feasible_cells", "sites_selected", "mean_score", "mean_rank",
                                 "mean_feasibility_top10", "known_hosts_in_selected_cells", "counties"]].round(2).to_string(index=False))
    both = cells.dropna(subset=["share_top10"])
    print("\nCoarse cells and the two scores:")
    print("  cells feasible at top-10% screen:", int((cells.share_top10 >= 0.5).sum()),
          "| their mean environmental rank:", round(cells[cells.share_top10 >= 0.5]["rank"].mean(), 0), "of 192",
          "| best rank among them:", int(cells[cells.share_top10 >= 0.5]["rank"].min()))
    print("  corr(environmental score, feasibility share_top10):", round(float(both[["score", "share_top10"]].corr().iloc[0, 1]), 2))


if __name__ == "__main__":
    main()
