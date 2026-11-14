# Stage 1 with an interconnection screen

Question: does Stage 1's answer change once a site must be able to connect to the grid? Code: `src/stage1_interconnection.py`. Outputs:
`results/stage1_cell_interconnection.csv`, `results/stage1_interconnection.csv`, `results/stage1_interconnection_coupling.csv`,
`results/figures/stage1_interconnection.png`.

**What this is not: a capacity model.** Node-level headroom and load-interconnection study results are not public, so nothing here says whether a given substation
can actually serve 500 MW. What is built is a **voltage-and-proximity screen** from OpenStreetMap substations plus a **shared-node cap**, with every threshold an assumption that is swept.

## Method
- Substations: the 1,461 OpenStreetMap `power=substation` features already in the project; 1,266 carry a voltage tag (maximum value used). By class: 375 at 115 kV or above, 213 at 230 kV or above, 79 at 345 kV or above, 55 at 500 kV or above.
- For each of the 186 cells with a serving utility, the distance from the cell centre to the nearest substation of at least V kV, for V = 115, 230, 345, 500.
- Eligibility: a qualifying substation within D_max km. Node cap: at most M selected projects per nearest qualifying substation (M = 1, 2, or none).
- Everything else is the Stage 1 default (500 MW, load factor 0.8, 25% support limit, tau_R = national median SAIDI, K = 3, 'all' territory mapping).

## Results
**Cells are far from high-voltage nodes.** Median distance from a cell centre: 15.9 km to a 115 kV substation, 20.4 km to 230 kV, 31.1 km to 345 kV, 52.0 km to 500 kV (75th percentiles 27, 37, 55, 105 km).

**The default Stage 1 sites are not equally connectable.**
| Default cell | Utility | Rank of 192 | To 115 kV | To 230 kV | To 345 kV |
|---|---|---|---|---|---|
| Cochise (125_-438) | APS | 7 | 27.3 km | **92.8 km** | 128.5 km |
| Maricopa (134_-447) | SRP | 133 | 25.5 km | 25.5 km | 25.5 km |
The best-scoring cell is 93 km from the nearest 230 kV substation, which puts a number on the earlier caveat that the highest-scoring cells in the remote south-east are probably not buildable.

**Price of the screen** (suitability lost against the unscreened total of 1.15; node cap does not matter, see below):
| D_max | >= 115 kV | >= 230 kV | >= 345 kV | >= 500 kV |
|---|---|---|---|---|
| 10 km | 13.4% | 42.5% (1 site) | 47.3% (1 site) | 47.3% (1 site) |
| 15 km | 13.4% | 13.4% | 47.3% (1 site) | 47.3% (1 site) |
| 20 km | 13.4% | 13.4% | 13.4% | 13.4% |
| 25 km | 12.4% | 12.4% | 12.4% | 12.4% |
| 30 km and above | 0.0% | 6.5% | 6.5% | 6.5% |
- At 230 kV or above within 30 km (and up to 60 km) the APS pick moves from Cochise (rank 7) to **Coconino (rank 26, 23.5 km from a 230/345 kV node)**; the SRP pick stays at Maricopa. Suitability is 1.08, mean rank 79.5.
- At 20 km the Maricopa cell (25.5 km) also fails and the pair becomes Pinal/SRP (rank 162) and Yavapai/APS (rank 33), suitability 1.00.
- Results change in steps because the 192 cells are coarse and the Maricopa cell sits at 25.5 km: read the table as a range (about 6% to 13% for moderate thresholds, 42-47% for very strict ones), not a point.

**The node cap never binds.** At 500 MW the utility caps already allow only one APS-served and one SRP-served site, so the two selected sites never share a node.

**Does the carbon-water footprint matter once interconnection binds?** Not for carbon. On the cells that pass the screen, the carbon of the selected set is 2,905 kt/yr in every case except the strictest (345 kV, 15 km, cap 1: one AZPS site, 2,051 kt), because the selection is still one
AZPS-served and one SRP-served site. Water weighting changes which cell is picked and the water of the set moves between 17.6 and 18.2 Mm3/yr (17.99 at zero weight, 230 kV and 30 km), at a suitability cost of up to 0.2.
This is the same structural result as before: utility scale decides the BA mix, and carbon cannot move it.

## Reading it honestly
- The screen is an eligibility rule on assumed thresholds. It says which cells are plausibly near transmission-voltage infrastructure, not which can interconnect 500 MW. A real capacity constraint needs utility load-interconnection studies.
- OSM voltage tags can be incomplete or wrong (13% of substations have none), and the substations include power-plant switchyards, which are not load nodes.
- Distances are from the cell centre; cells are 0.25 degrees (about 25 km), so a cell can contain a qualifying substation while its centre is farther away than D_max.
- This agrees with the revealed-preference result (`docs/REVEALED_PREFERENCE.md`), where distance to a substation separates real data-center cells: remote cells that score well on environmental criteria are not where connection is easy.

## Next
- Replace the proximity screen with real capacity data if any becomes available (utility cluster studies, FERC filings), or at least use line-level voltage and circuit counts.
- Run the screen at the finer 0.05-degree cells used in the revealed-preference model, which would remove the centre-distance artefact.
