# Stage 2 coupling: siting and operating carbon and water

Tests whether adding what a project emits and consumes while running (Stage 2: the scheduler and the water
model) changes which sites Stage 1 selects. Code: `src/stage2_coupling.py`. Outputs: `results/stage2_cell_footprint.csv`,
`results/stage2_coupling.csv`, `results/stage2_sensitivity.csv`, `results/figures/stage2_coupling.png`.

## Formulation
Same problem as Stage 1 (site budget K, per-utility caps from the reliability guardrail and the 25% support limit),
with objective `(1 - w) * score_i + w * (1 - footprint_i)`. `footprint_i` is min-max scaled over eligible cells;
"both" is the mean of scaled carbon and scaled water, or each alone. `w = 0` reproduces Stage 1 exactly
(Cochise/APS plus Maricopa/SRP, suitability 1.151). `w` is swept, never fitted.

## Footprint per cell (500 MW, load factor 0.8, scenario estimates)
| Term | How | Firmness |
|---|---|---|
| BA of a cell | APS -> AZPS, SRP -> SRP, TEP -> TEPC; other utilities dropped (53 cells remain) | Assumption; UNS Electric and cooperatives have no BA data here |
| Carbon | PUE 1.2 x mean 2021-2024 carbon intensity of the BA (flagged hours excluded) | Production-based in the main run; SRP is low mainly because Palo Verde is reported there. A consumption-based variant is below |
| Scheduling credit | 30% of load carbon-aware; saving vs random timing from `schedule_savings.csv` (LightGBM, 8 h preemptible), 12-26% by BA | The 30% is my choice; savings are 2025 test-year values |
| Generation water | PUE x generation-weighted Macknick consumption factors of the BA mix | Literature medians, unverified here |
| On-site cooling water | `water_frontier` curve on hourly wet-bulb of the nearest of PHX/TUS/HAV, shifted by (cell mean wet-bulb - station mean) | The shift is an assumption; the cell wet-bulb is an annual mean |

## Results
1. **Carbon cannot move the selection.** The utility caps allow one APS-served and one SRP-served 500 MW site, so
   the carbon of the selected set is 2,905 kt/yr at every weight below 1.0 and in every sensitivity run
   (change 0.0%). Carbon-only weighting changes the selection only at w = 1.
2. **Water is the only lever and it is small.** Carbon and generation water are single values per BA, so only
   on-site cooling water varies between cells of one BA. At w = 0.5 the default run keeps one of the two Stage 1 sites
   (Jaccard 0.33), saves 5.5% of water (19.0 to 18.0 Mm3/yr) and loses 6.5% of suitability. Reaching 17.6 Mm3 costs
   12 to 24%.
3. **Across sensitivity runs** (P 100-1,000 MW, K 1-5, A_max 10-50%, flexible share 0-60%, PUE 1.1-1.5, nuclear and
   hydro water cases) the water saving stays between 2.8% and 12.9% for 3.5% to 10% of suitability. The largest
   saving (12.9%, with a 10% loss) is at K = 1. Nuclear counted as free effluent raises it to 7.9%.
   At 1,000 MW, or A_max 10%, nothing is eligible, so the comparison is undefined.
4. Rank correlation between Stage 1 score and footprint across eligible cells is -0.29.

## With consumption-based carbon (`results/stage2_coupling_consumption.csv`)
Same sweep with carbon from the flow-traced intensity (`docs/CONSUMPTION.md`) and its own scheduling credit (persistence decision
evaluated on consumption: AZPS 21.0%, SRP 18.4%, TEPC 16.6%). Water stays production-side. On the same valid hours, carbon per kWh
of IT (kg) moves AZPS 0.635 -> 0.446, SRP 0.258 -> 0.299, TEPC 0.640 -> 0.564.
- **Selections are identical** at every weight and footprint kind, and the sensitivity runs give the same overlap, suitability loss and water saving
  (the `consumption CI` case in `stage2_sensitivity.csv`). Carbon is a per-BA constant, and the caps allow one AZPS-served and one SRP-served site either way.
- **The carbon level changes**: the Stage 1 default set falls from 2,905 to 2,456 kt CO2/yr (-15%). Per BA at 500 MW: AZPS 2,051 -> 1,465,
  SRP 854 -> 991, TEPC 2,178 -> 1,878 kt/yr. The AZPS-to-SRP carbon ratio shrinks from 2.4 to 1.5.
- So the structural conclusion does not depend on the accounting; the size of the carbon figure does. The consumption figure is also an
  average-mix measure, so it does not capture how a new 500 MW load would change flows.

## Reading this honestly
- The coupling is mostly **structural**: the utility-scale constraint fixes which BAs can host a project before carbon
  or water enter. This supports "scale and interconnection limits dominate", not "the three decisions interact".
- The footprint is mostly a **BA label**. Do not read the SRP vs APS carbon gap as a siting recommendation.
- Within-BA water differences come from an assumed on-site cooling curve and an assumed wet-bulb shift; they are
  not measured.
- Sweeps are one parameter at a time around the default, not a joint sensitivity.
- No weights are justified; the trade-off curve is the result, not a chosen point.

## Next
- Interconnection and plant-level capacity constraints (does the footprint matter once those bind?).
- Marginal emissions, so the carbon term can vary with the choice of site and hour.
- Time-varying coupling: let the scheduler's hourly flexibility change the load a utility must support.
