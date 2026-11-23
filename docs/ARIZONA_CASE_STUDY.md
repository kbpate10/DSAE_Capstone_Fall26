# Arizona case study: what the framework says about the 2026 policy debate

**Sourcing.** Policy facts come from `docs/regulatory_context_check.md` (web search, checked 2026-10-11; the ACC eDocket and session
laws were not accessed, and some items are marked unverified there). Every number about the framework comes from a file in `results/`
(named in each row). The water-surcharge dollar figures use **hypothetical** rates: no rate has been set.

## 1. The decisions being debated (as of the fact-check)
- **ACC inquiry** into data-center rate classifications (opened April 2025; the docket number is not verified); a large-load workshop
  on 16 April 2026; the Commission stated about 1,300 MW under construction and over 4,000 MW in planning.
- **Attorney General's call (31 Aug 2026)** for a statewide pause on approving and building new data centers.
- **Governor's proposed per-gallon water fee** on data centers (January 2026 agenda; amount to be set by the ADWR director; a penny a gallon
  was estimated at about $6.5 million a year; no enactment found).
- **Tax:** a three-year pause on *new* sales-tax exemptions in the June 2026 budget.
- **Colorado River:** a federal cut of about 760,000 acre-feet a year in 2027-28 (roughly 27% of the 2.8 million acre-foot allotment; sources range
  20-31% depending on the measure).

## 2. What the framework can and cannot say

| Question | What the framework says | Source in this project | What it cannot say |
|---|---|---|---|
| **Where to site; the pause** | The binding limit is project size against the serving utility's load, not the environmental score. A 500 MW project at a 0.8 load factor is about 3.5 TWh a year, roughly 19% of APS's or SRP's commercial and industrial load and 70% of TEP's. At the default guardrail only APS and SRP can host one; at 100 MW five sites qualify, at 1,000 MW none. | `docs/STAGE1.md`; `results/stage1_frontier.csv`; `results/framework_stage1_sweep.csv` | Whether any specific application is acceptable: no transmission, interconnection-capacity or land data in the score |
| **Whether an environmental score is a good screen** | No. Real data-center locations follow population and substations (within the Phoenix metro: population alone AUC 0.89, spatial-block CV; environmental features 0.46). The constructed score ranks existing host cells low (median rank 160 of 192). Feasibility and suitability disagree (correlation -0.28); requiring both costs about 0.1-0.25 of mean score | `docs/REVEALED_PREFERENCE.md`; `docs/MIDPOINT1_REPORT.md` | Where operators *should* build; 25 host cells, 92% in one metro; OSM is incomplete |
| **Reliability for existing customers** | No detectable harm from commercial and industrial load growth: +0.5% SAIDI per +10% C&I load (95% interval -0.7% to +1.7%); the largest upper bound over specifications is +2.5%. As a conservative bound (not a forecast) a 500 MW project adds at most 4.6% to SAIDI at APS (83.1 to 86.9 min) and SRP (49.6 to 51.8 min); a 250 MW project 2.4%; a 100 MW project 3.4% at TEP (65.1 to 67.3 min) | `results/rq3_results.csv`; `results/case_study_reliability_bound.csv` | Anything specific to data centers (the proxy is diluted), and anything about **rates or who pays**: this project measures reliability, not cost allocation, which is the rate-class focus of the ACC docket |
| **The water fee** | On-site cooling water for one 500 MW project, under the assumed evaporative-cooling curve, is 364-942 million gallons a year depending on the cell (default cells: 639 million at the Cochise/APS cell, 857 million at the Maricopa/SRP cell). At a hypothetical $0.01 a gallon that is $3.6-9.4 million a year; at $0.001 it is $0.4-0.9 million. The press estimate ($6.5 million at a penny) implies a base of about 650 million gallons a year, so one project at full evaporative cooling would be comparable to that whole base. With half or a quarter of the modelled evaporative share (closed-loop or dry designs) the cost falls proportionally | `results/case_study_surcharge.csv`; `results/stage2_cell_footprint.csv` | Actual water use: the on-site curve (WUE up to 1.85 L/kWh) and PUE 1.2 are assumptions, and real facilities may use far less. Generation-side water (not covered by a data-center fee) is excluded |
| **Can scheduling reduce water?** | Only a little. Water-only scheduling saves 6.8% on AZPS, 0.9% on SRP, 1.3% on TEPC versus running immediately; carbon-only scheduling *raises* water on SRP (9.7%) and TEPC (7.3%). Cooling design is the larger water lever than timing | `results/framework_stage2_policies.csv` | The effect of a price on water: no price-to-weight calibration was done (alpha is swept, not fitted). These figures use literature generation-side water factors; with measured EIA-860/923 factors AZPS also shows a small carbon-water conflict (`docs/WATER_MEASURED.md`) |
| **Colorado River, tax pause** | Not modelled. The framework does not track the source of water | n/a | Everything |

## 3. Recommendations by stakeholder
These follow from the scenario results above. They are the project's reading of model output on assumed inputs, not validated advice.

**Data-center operators (flexible workloads).**
1. Schedule by yesterday's same-hour carbon intensity. It captures nearly all the achievable benefit (about 24% saved against running at midnight for an
   8 h job, versus 27.5% with perfect foresight; `docs/MIDPOINT1_REPORT.md`).
2. At SRP and TEPC use a balanced carbon-water weighting instead of carbon-only: balanced saves 18.0% of carbon at SRP while carbon-only saves 27.1% but
   uses 9.7% more water than running immediately (`results/framework_scenario_default.csv`). AZPS shows no conflict with literature water factors, but a small one (-1.6% to -0.1%) if Solana's solar-thermal water is counted at midday (`docs/WATER_MEASURED.md`).
3. Report the savings as **average-intensity** savings. They survive production-to-consumption accounting (12-26% on AZPS, SRP, TEPC); scored on a marginal estimate an unstable share of them carries over (pooled 8-14%), with sign flips by BA in single years
   (`docs/MARGINAL.md`, `docs/CONSUMPTION.md`).

**ACC staff reviewing large-load applications.**
1. Screen first on project size against the serving utility's load and on interconnection capacity: these decide the outcome before environmental criteria do.
2. Do not rely on an environmental suitability score alone: mapped data centers follow population and grid proximity. Report feasibility and suitability
   separately.
3. Treat the reliability evidence as a bound, not as an all-clear: it covers load changes up to about 25% of a utility's C&I sales and cannot see data
   centers specifically. Requiring utilities to report large-load connections by date would allow an event study.

**Utilities (APS, SRP, TEP).** The reliability-tolerance frontier is flat above about 100 minutes of SAIDI and binds between about 60 and 100:
at 60 minutes only SRP (49.6) can host a 500 MW project and at 100 minutes both APS (83.1) and SRP can
(`results/framework_stage1_sweep.csv`).

**Water policy.** The per-gallon fee acts on cooling design, not on workload timing, because scheduling moves water by at most about 7%. How much a fee
matters depends on how much evaporative cooling a facility uses, which is not observable in the public data used here (EIA-860 cooling types are not yet added).

## 4. Limits
- Policy facts are from web search and may be out of date or inconsistent between outlets; confirm against the eDocket and statutes before quoting.
- All framework results are scenarios on assumed inputs: project size 500 MW, load factor 0.8, PUE 1.2, the on-site cooling curve, the 25% support limit, utility
  territory polygons that are approximate for small districts.
- The reliability bound extrapolates RQ3's elasticity to a single large project; the data contain no data-center-specific variation.
- The recommendations rank evidence strength unevenly: strongest for scheduling timing, weakest for siting and the water fee.
