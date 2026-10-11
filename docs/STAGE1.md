# Stage 1: siting optimizer

Chooses which candidate sites to develop, maximizing environmental suitability subject to a reliability
guardrail on the serving utility. Code: `src/build_territories.py`, `src/stage1_optimizer.py`. Outputs:
`results/stage1_*.csv`, `results/figures/stage1_frontier.png`.

## Formulation
```
maximize    sum_i score_i * x_i
subject to  sum_i x_i <= K                                   site budget
            sum_{i served by u} x_i <= n_max(u)               per-utility cap
            x_i in {0, 1}
```
`n_max(u)` is the largest number of projects utility `u` can host such that **both**
1. *Guardrail:* projected SAIDI = `baseline_u * (1 + n*E/CI_u)^beta <= tau_R`, and
2. *Evidence support:* added load `n*E/CI_u <= A_max`,

with `E = P * 0.8 * 8760` MWh/yr (project size `P` MW, load factor 0.8) and `CI_u` the utility's 2024
commercial and industrial sales. Solved exactly with PuLP/CBC; the solution matches a greedy check in all
144 tested cases (it is a small problem).

## What each input is, and how firm it is
| Input | Source | Firmness |
|---|---|---|
| `score_i` | `rq2_siting.py` (default weights) | Constructed, assumed weights; stability tested by sampling weights |
| Serving utility of a cell | HIFLD retail service-territory polygons (PNNL-hosted), "most specific territory wins" at 25 points per cell, joined to EIA-861 by utility number | Approximate. HIFLD uses identical generic polygons for several small districts, so two mappings are run: all retail utilities, and only utilities with at least 500 GWh sales |
| `baseline_u` | Median 2021-2024 SAIDI without major events (fallback: with-events / 1.44, flagged) | From data; missing for utilities with no reliability record, which are ineligible |
| `CI_u` | EIA-861 2024 commercial + industrial MWh | From data |
| `beta` | Upper 95% bound of the RQ3 fixed-effects elasticity (0.257) | Deliberately conservative: the point estimate is about zero |
| `tau_R` | Default 100 min = national median SAIDI | Policy lever; swept 60-300 |
| `A_max` | 25% | Assumption: RQ3 covers load changes of roughly this size; beyond it a safe outcome cannot be shown |
| `P`, load factor | 500 MW default (the proposal's example), 0.8 | Assumptions; swept 100-1,000 MW |

## Results
Default scenario (500 MW, K = 5, tau_R = 100, A_max = 25%):

| | Mapping "all" | Mapping "large" |
|---|---|---|
| Sites selected | 2 (K = 5 cannot be met) | 2 |
| Which | APS-served Cochise cell (rank 7); SRP-served Maricopa cell (rank 133) | Same Cochise cell; SRP-served Maricopa cell (rank 131) |
| Sum of scores | 1.15 | 1.15 |

1. **Utility size, not reliability, is the binding constraint.** A 500 MW, 80%-load-factor project is about
   3.5 TWh/yr, roughly 19% of APS's or SRP's commercial and industrial load but 70% of TEP's and far more of
   the cooperatives'. Only APS and SRP can host one at the 25% support limit. The reliability guardrail itself
   only binds between about 60 and 100 minutes (APS's baseline is 83), then the frontier is flat.
2. **The most suitable cells are served by utilities too small to host a large project.** None of the five
   highest-scoring cells is eligible at 500 MW: they sit in Santa Cruz, Cochise and Gila and are served by TEP,
   Sulphur Springs, Trico and the San Carlos project (project would be 70% to 3,300% of their C&I load).
3. **The picture changes with project size.** At 100 MW five sites are selectable (APS and TEP territory,
   mean rank 18); at 250 MW, four (APS and SRP, mean rank 82); at 1,000 MW, none.
4. **Cost of the guardrail** at equal site count (K = 2, 500 MW): constrained 1.15 vs unconstrained 1.56
   total suitability, a 26% loss.
5. **Selection is not stable to the weights.** Over 300 random weight vectors the default top cell is chosen
   in 57% of draws (mapping "all") and 21% ("large"); the second site varies more.

## Reading this honestly
- This is a **framework demonstration** on assumed inputs, not a siting recommendation. The cells are 25 km
  squares, the score has no transmission, fiber or land features, and several utility assignments are
  approximate.
- The "reliability risk" is mostly the utility's own baseline reliability plus a small, bounded effect,
  because RQ3 found no detectable load-growth effect. That is the evidence-honest version of the guardrail,
  and it is why the optimizer is dominated by the scale constraint.
- Eligibility depends on the 25% support limit. Relaxing it to 50% lets 4 sites through at 500 MW; tightening
  it to 10% excludes every site. That sensitivity is the finding.
- Water enters only through the suitability score (depth, wet-bulb). A county water budget would be a
  natural next constraint but no budget data is in the project.

## Next
- Plant-level and interconnection capacity constraints (the real limit on a 500 MW load).
- Replace the constructed score with a model fitted to real data-center locations.
- Connect to Stage 2 so the chosen sites feed the scheduler's per-site carbon and water forecasts.
