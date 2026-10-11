"""Figure: environmental suitability vs revealed feasibility, by candidate cell."""
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import stage1_revealed as sr

cells = pd.read_parquet(ROOT / "data/processed/sites_scored.parquet").set_index("cell_id").join(sr.feasibility_table())
fine = pd.read_parquet(ROOT / "data/processed/fine_cells_features.parquet")
sel = pd.read_csv(ROOT / "results/stage1_revealed_selection.csv")
sel = sel[(sel.mapping == "all") & (sel.P_MW == 250)]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
a = ax[0]
d = cells.dropna(subset=["share_top10"])
a.scatter(d.score, d.share_top10, s=26, c="#b8c4cf", edgecolor="white", lw=.4, label="candidate cell")
h = d[d.hosts > 0]
a.scatter(h.score, h.share_top10, s=70, c="#d1495b", edgecolor="white", label="contains mapped data center(s)")
unc = sel[sel.screen.str.startswith("no screen")]
fe = sel[sel.screen.str.contains("top 10%")]
a.scatter(unc.score, unc.share_top10, s=110, facecolor="none", edgecolor="#1b6ca8", lw=2, label="chosen, environmental only (250 MW)")
a.scatter(fe.score, fe.share_top10, s=110, marker="D", facecolor="none", edgecolor="#2a9d8f", lw=2, label="chosen, feasible top 10% (250 MW)")
a.set_xlabel("environmental suitability score"); a.set_ylabel("feasibility: share of cell in top 10% propensity")
a.set_title("Where operators build vs where it scores well", fontsize=10.5); a.legend(frameon=False, fontsize=8, loc="upper right"); a.grid(alpha=.25)
a = ax[1]
f = fine
a.scatter(f.lon, f.lat, s=3, c="#d9dee3", marker="s")
h = f[sr.rp.presence(f, "all") == 1]
a.scatter(h.lon, h.lat, s=22, c="#d1495b", label="host cells (OSM)")
a.set_aspect(1.2); a.set_xlabel("longitude"); a.set_ylabel("latitude")
a.set_title("Host cells sit where population and substations are", fontsize=10.5); a.legend(frameon=False, fontsize=8, loc="lower left")
fig.tight_layout(); fig.savefig(ROOT / "results/figures/revealed_feasibility_vs_suitability.png", dpi=150)
print("saved")
