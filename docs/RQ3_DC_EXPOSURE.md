# RQ3 with a data-center-specific exposure (OpenStreetMap x utility territories)

Question: the EIA-861 proxy (C&I sales per customer) cannot tell data centers from other load. Does a data-center-specific exposure show a reliability
effect? Code: `src/pull_osm_datacenters_us.py`, `src/pull_territories_us.py`, `src/rq3_datacenter_exposure.py`. Outputs: `data/processed/dc_by_utility.parquet`,
`results/rq3_dc_exposure.csv`, `results/rq3_dc_descriptives.csv`.

**Bottom line: still no detectable harm, but this exposure is too weak to count as a test of data-center load.** The first-stage F-statistic is 2.8 (a Wald ratio
is not reported), the first stage mostly disappears once utility size is controlled, and the design cannot detect an extra effect below about 6% SAIDI per +10% load.

## Construction
- **Data centers:** 1,841 OpenStreetMap features tagged `telecom=data_center` or `building=data_center` across 51 states (0 pull failures). Largest counts: VA 403, TX 221,
  OR 133, CA 116, OH 93, WA 72, AZ 64: a plausible geography. 66% carry an operator tag. OSM has no opening dates.
- **Territories:** 2,949 national HIFLD retail territories (geometry simplified to about 100 m). Each data center goes to the smallest-area territory that contains it
  and belongs to a utility in the RQ3 panel; 1,806 of 1,841 (98%) were assigned, to 207 of 1,188 panel utilities (1,176 territories used).
- **Exposure:** `any_dc` (at least one mapped data center) and `ln_dc` = log1p(mapped data centers per 100,000 customers), interacted with post = year >= 2019 (named before
  looking at results; 2018, 2020 and a linear trend are robustness). Utility effects + state-by-year effects, SEs clustered by utility, as in the main RQ3 model.
- Utilities with a mapped data center are much larger: median 76,034 customers against 15,691.

## Results
**Is the exposure relevant? (first stage: C&I growth per customer on exposure x post)**
- Coefficient +0.0048 log points per year (SE 0.0028, p = 0.094); F-like statistic 2.8, below the usual threshold of 10. Other timing definitions: +0.0053 (post 2018, p = 0.09),
  +0.0030 (post 2020, p = 0.33), +0.0012 per year (trend, p = 0.11), +0.0014 (log density, p = 0.24).
- **With a utility-size x post control it falls to +0.0022 (SE 0.0033, p = 0.50)**: most of the link is larger utilities growing C&I load faster after 2019.
- Large surges are not concentrated where data centers are mapped: 5 of the 28 utility-years above +50% growth are in utilities with a mapped data center, against a base
  rate of 23% of utility-years (about 6 expected). Among utility-years in 2019-2024 the share with growth above 25% is 1.3% (data-center utilities) vs 1.4% (others).
  So the big C&I surges in the panel are mostly not in places with mapped data centers (OSM is incomplete, so this is evidence about the proxy, not proof). This supports the
  dilution caveat for the C&I proxy.

**Reduced form: ln SAIDI on exposure x post**
| Exposure | Coefficient (approx. % change in SAIDI) | 95% interval | p |
|---|---|---|---|
| any data center x post 2019 | -4.1% | -10.2% to +1.9% | 0.18 |
| any data center x post 2019, with size x post | -3.4% | -10.8% to +4.0% | 0.36 |
| log density x post 2019 | -3.0% per unit | -5.7% to -0.3% | 0.032 |
| log density x post 2019, with size x post | -2.9% per unit | -5.7% to -0.1% | 0.040 |
| any x post 2018 / post 2020 | -4.2% / -5.5% | -10.6% to +2.2% / -11.3% to +0.3% | 0.20 / 0.065 |
| any x linear trend since 2018 | -1.4% per year | -2.8% to 0.0% | 0.055 |
All estimates are negative: no sign of reliability deterioration where data centers are mapped. Two of the eight reduced-form tests pass p < 0.05 (the same density exposure, with and without the size control) and none is adjusted for multiple
testing, so I do not read this as an improvement either: bigger, urban utilities may be investing in reliability for unrelated reasons, and the exposure is time-invariant.

**Heterogeneity: does load growth matter more in data-center utilities?** Interaction of C&I growth with `any_dc`: +0.26 elasticity (interval -0.17 to +0.69, p = 0.24), i.e. an extra
+2.5% SAIDI per +10% load (-1.6% to +6.5%). The minimum detectable interaction is 0.61 (about 5.8% per +10% load), so the design cannot detect anything smaller.

## Reading it honestly
- This tests "being in a territory with mapped data centers after 2019", not "receiving data-center load". OSM gives location, not timing or megawatts, and misses or mislabels facilities.
- The first stage is weak, so no causal ratio is reported. The reduced-form estimates are associations confounded by utility size and urbanity.
- Combined with `docs/RQ3_POWER.md`, RQ3's honest statement is: no detectable harm from C&I load growth (bounded at about +1.9% to +2.5% per +10% load) and no detectable difference in utilities that
  host mapped data centers; neither design can see an effect smaller than the limits above, and neither identifies data-center load directly.

## What would make it informative
Dated facility openings or capacities (utility interconnection filings, state incentive records, commercial databases, or an event study of named clusters with known energization years), so that treatment has a
timing and a size. None is in the public data used here.

**Feasibility check (2026-11-10, from Cleanview's public coverage, pricing and API pages and web search; I did not scrape, register or download anything):**
- The only national source I found with both operating year and capacity per building is the commercial tracker Cleanview. Its coverage page lists 4,729 records, of which 1,425 operating, with operating year present for 99.3% of
  operating records, capacity for 97.4% and retail utility for 92.7%. It costs $4,900 for a one-time download or $9,000 a year; there is no free full download (a free sample extract is advertised, not checked). Coverage and license terms are the vendor's own statements.
- Free sources are too thin for a utility-panel test: the OpenStreetMap-based PNNL atlas has locations only; interconnection.fyi lists 97 Arizona records with status and capacity but (per search snippets) no opening dates, and Arizona alone cannot be tested
  (`docs/RQ3_POWER.md`); Epoch AI's open tables cover a few dozen frontier AI sites (counts from search snippets, not checked).
- Even with dated megawatts the power question is open: the OSM design could not detect an interaction below about 6% SAIDI per +10% load, and dated exposure would help the first stage but not the small number of treated utility-years.
  I would only pursue it if a university licence or a free academic extract is available, and I would rerun the power calculation on the real treated-utility counts before building anything.
