# Revealed-preference siting: real data-center locations

Replaces the circular "constructed label" with an outside source: where data centers are actually mapped.
Code: `src/revealed_preference.py`, `src/stage1_revealed.py`, `src/make_revealed_figure.py`.
Outputs: `results/revealed_*.csv`, `results/stage1_revealed_*.csv`,
`results/figures/revealed_feasibility_vs_suitability.png`.

## Data
| Input | Source | Size |
|---|---|---|
| Data-center locations | OpenStreetMap (`telecom=data_center`, `building=data_center`) | 65 features, 64 inside candidate cells |
| Substations | OpenStreetMap `power=substation` | 1,461 (voltage tag present on only some) |
| Population | Census 2020 tracts (TIGERweb), 10 km neighbourhood | 1,765 tracts, 7.15M people |
| Water, heat, solar | ADWR GWSI (5 nearest sites), NASA POWER (coarse) | as before |
| Domain | 0.05-degree cells (about 5 km) inside an Arizona retail service territory | 10,563 cells |

Presence = a cell containing at least one mapped data center: **25 host cells** (13 using only features with an
operator tag), **92% inside the Maricopa metro box**, in 6 half-degree blocks.

## Findings
**1. Statewide, infrastructure explains host locations; the environmental score runs the wrong way.**

| Model (host vs non-host cell) | AUC, random CV | AUC, spatial-block CV |
|---|---|---|
| Environmental features only | 0.92 | 0.80 |
| Infrastructure only (population, substations) | 0.99 | 0.97 |
| Both | 0.99 | 0.96 |
| The constructed environmental *score* | 0.19 | n/a |

An AUC of 0.19 means host cells score *lower* on the constructed suitability score (equivalent to 0.81 in
reverse). The environmental features do separate hosts from non-hosts statewide, but only because warm,
low-lying cells are where the metro is; they carry no signal within it (next point).

**2. Within the Phoenix metro the choice is population and grid proximity.** 432 cells, 23 hosts:

| Predictor | AUC (random / spatial block) |
|---|---|
| Population within 10 km alone | 0.91 / 0.89 |
| Distance to nearest substation alone | 0.84 / 0.81 |
| Infrastructure features together | 0.90 / 0.87 |
| Environmental features together | 0.63 / 0.46 |

Hosts have a geometric-mean population neighbourhood about 36 times larger (mean log 12.9 vs 9.3) and are on
average 1.3 km vs 4.8 km from a substation, but groundwater depth, wet-bulb and irradiance are indistinguishable. Standardised
coefficients (statewide, 95% bootstrap interval): population +4.2 (2.8 to 6.1), substation distance -3.8
(-6.1 to -1.1); all environmental coefficients include zero.

**3. The tension for siting is large and now measured.** Across candidate cells, environmental suitability and
feasibility correlate -0.28. The 27 cells that look feasible (half or more of their sub-cells in the top 10% of
propensity) have a mean environmental rank of 133 of 192, though the best has rank 12.

| Stage 1 result (mapping "all", K = 5) | Environmental only | + feasibility screen (top 10%) |
|---|---|---|
| 100 MW: mean score / mean rank | 0.71 / 18 | 0.47 / 110 |
| 250 MW: sites, mean score / mean rank | 4, 0.54 / 82 | 3, 0.48 / 105 |
| 500 MW: sites, mean score / mean rank | 2, 0.58 / 70 | 2, 0.49 / 96 |

Requiring both feasibility and environmental suitability changes where the optimizer builds: it moves from
the remote south-east toward Yavapai, Coconino, Yuma, Pima and Maricopa cells. The framework therefore
reports a **price of feasibility** (about 0.1 to 0.25 in mean score, depending on project size), not a single
answer.

## What this does and does not show
- **Few positives, one metro.** 25 host cells, 92% in one metro area. Spatial-block CV tests nearby holdouts,
  not a different region. Intervals are wide.
- **Population is a bundle.** It stands for latency, workforce, fiber, land and tax regime; the model cannot
  separate them. "Feasibility" here means "looks like existing host cells", not "can be interconnected".
- **Incomplete and noisy map data.** OSM misses facilities and includes some mis-tagged IT businesses; many
  features are enterprise or colocation space, not hyperscale AI campuses.
- **Weak environmental resolution.** Climate comes from the nearest of 192 coarse points, so heat and solar
  barely vary inside the metro; groundwater depth is the only environmental feature with local variation.
  The environmental null within the metro is partly a resolution limit.
- **Descriptive, not causal.** It shows what operators have done, not what they should do or what a
  regulator would prefer; that is why feasibility and suitability are kept as separate scores.

## Next
- Add real interconnection-capacity data (transmission lines, queue study results) and land or zoning.
- Add hyperscale facilities from a curated list; test whether they differ from enterprise colocation.
- Extend the same screen to other metros (Tucson, Flagstaff) once more positives exist.
