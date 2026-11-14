"""Figures for Checkpoint 2 that did not exist yet: an Arizona map of suitability and reliability risk, and a SHAP summary.

Map (two panels, 0.25-degree cells, utility territories drawn as thin outlines):
  left   Stage 1 environmental suitability score (rq2_siting default weights; a constructed score, not validated);
         mapped OpenStreetMap data centers as black dots.
  right  reliability risk of the serving utility = its baseline SAIDI without major events (2021-2024 median, minutes); cells
         whose utility can host a 500 MW project under the Stage 1 guardrail (tau_R = national median, A_max 25%) carry a black
         outline; cells whose serving utility has no reliability record are grey.
The map joins cells to utilities with the 'all' territory mapping (approximate where HIFLD uses generic polygons).

SHAP: mean |SHAP| of the full-data LightGBM and the standardised logistic coefficient from results/rq2_importance.csv. The label is a
function of the same features, so these recover the assumed weights; they are not evidence about what drives real siting.

Outputs: results/figures/map_suitability_reliability.png, results/figures/rq2_shap_summary.png
"""
import json
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon, Rectangle

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage1_optimizer as s1

HALF = 0.125


def territory_patches():
    g = json.load(open(ROOT / "data/raw/rq2/territories_az.geojson"))
    out = []
    for f in g["features"]:
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for p in polys:
            out.append(Polygon(np.array(p[0]), closed=True))
    return out


def main() -> None:
    cells = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id")
    util = s1.utility_table()
    tau, beta = s1.national_median_saidi(), s1.beta_upper()
    a = s1.assign("all", util).set_index("cell_id")
    d = cells.join(a[["util_num", "util_name", "baseline_saidi", "ci_mwh"]], how="left")
    E = 500 * s1.LF * s1.HRS
    caps = {u: s1.n_max(r, tau, s1.DEFAULT["A_max"], E, beta) for u, r in util.iterrows()}
    d["eligible"] = d.util_num.map(lambda u: caps.get(int(u), 0) > 0 if pd.notna(u) else False)
    print(f"cells: {len(d)}, with a reliability record: {int(d.baseline_saidi.notna().sum())}, eligible at 500 MW: {int(d.eligible.sum())}")
    dc = pd.read_parquet(ROOT / "data/raw/rq2/osm_datacenters_az.parquet")
    terr = territory_patches()

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 6.2), sharey=True)
    for a_ in ax:
        a_.add_collection(PatchCollection(terr, facecolor="none", edgecolor="#bbb", linewidth=0.4))
        a_.set_xlim(-115.0, -108.9); a_.set_ylim(31.2, 37.1); a_.set_aspect(1.2)
        a_.set_xlabel("longitude")
    ax[0].set_ylabel("latitude")
    cm = plt.cm.viridis
    for _, r in d.iterrows():
        ax[0].add_patch(Rectangle((r.lon - HALF, r.lat - HALF), 2 * HALF, 2 * HALF, facecolor=cm(r.score), edgecolor="none", alpha=.9))
    ax[0].scatter(dc.lon, dc.lat, s=8, color="black", label=f"mapped data centers (OSM, n={len(dc)})", zorder=5)
    sm = plt.cm.ScalarMappable(cmap=cm, norm=plt.Normalize(d.score.min(), d.score.max()))
    fig.colorbar(sm, ax=ax[0], fraction=0.04, pad=0.02, label="environmental suitability score (constructed)")
    ax[0].legend(loc="lower left", frameon=True, fontsize=8)
    ax[0].set_title("Environmental suitability and mapped data centers", fontsize=10)

    vmax = np.nanpercentile(d.baseline_saidi, 95)
    cm2 = plt.cm.YlOrRd
    for _, r in d.iterrows():
        col = "#d9d9d9" if pd.isna(r.baseline_saidi) else cm2(min(r.baseline_saidi / vmax, 1.0))
        ax[1].add_patch(Rectangle((r.lon - HALF, r.lat - HALF), 2 * HALF, 2 * HALF, facecolor=col,
                                  edgecolor="black" if r.eligible else "none", linewidth=1.6 if r.eligible else 0, alpha=.95,
                                  zorder=4 if r.eligible else 2))
    sm2 = plt.cm.ScalarMappable(cmap=cm2, norm=plt.Normalize(0, vmax))
    fig.colorbar(sm2, ax=ax[1], fraction=0.04, pad=0.02, label="serving utility baseline SAIDI, no major events (min/yr)")
    ax[1].set_title("Reliability risk of the serving utility; outline = can host 500 MW\nunder the guardrail (grey = no reliability record)", fontsize=10)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/map_suitability_reliability.png", dpi=150); plt.close(fig)

    imp = pd.read_csv(ROOT / "results/rq2_importance.csv", index_col=0).sort_values("mean_abs_shap")
    fig, a_ = plt.subplots(figsize=(7.2, 3.8))
    a_.barh(imp.index, imp.mean_abs_shap, color="#1b6ca8")
    for i, (v, c) in enumerate(zip(imp.mean_abs_shap, imp.logit_coef_std)):
        a_.text(v + 0.05, i, f"{v:.2f}  (logit coef {c:+.2f})", va="center", fontsize=8)
    a_.set_xlim(0, imp.mean_abs_shap.max() * 1.6)
    a_.set_xlabel("mean |SHAP| (LightGBM, top-tercile label)")
    a_.set_title("RQ2 feature importance: recovers the assumed weights (constructed label)", fontsize=10)
    a_.grid(axis="x", alpha=.25)
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/rq2_shap_summary.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
