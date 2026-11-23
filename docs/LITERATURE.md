# Literature check (first pass, 2026-11-01)

**How reliable this is:** one round of web searches (10 queries) plus the abstract pages of four papers. Everything below comes from search
excerpts and abstract pages, not full papers. Nothing here has been verified against the papers' methods or results, and the search was not
exhaustive. Treat each row as "someone has worked on this", not as a statement of exactly what they did. Check the full paper before citing.

## What already exists, by project piece
| Piece of this project | Prior work found | Implication |
|---|---|---|
| Average vs marginal carbon signals for scheduling | Sukprasert, Bashir, Souza, Irwin, Shenoy, "On the Implications of Choosing Average versus Marginal Carbon Intensity Signals on Carbon-aware Optimizations", ACM e-Energy 2024: 65 regions; signals differ statistically, have very low correlation, and optimizing one can raise emissions measured by the other (abstract page only; data and methods not read) | The general question is taken. An Arizona case study with a two-test-year check and an interchange analysis is incremental, unless the full paper shows it lacks these |
| Temporal shifting with forecasts | Wiesner et al., "Let's Wait Awhile" (Middleware 2021); simulations for Germany, Great Britain, France, California | Foundational; cite, do not claim |
| Carbon-intensity forecasting (LightGBM, neural nets) | CarbonCast and DACF (UMass); an Oxford workshop comparison of linear, ARIMA, Prophet, LightGBM and XGBoost on UK data; a 2026 Nordic preprint with pre-registered baselines | No methodological novelty in forecasting here. The value is the audit discipline (named primary model, rolling origin), not the models |
| Carbon vs water scheduling | WaterWise (Jiang et al., arXiv 2501.17944): joint carbon-water scheduler across geographically distributed data centers; Attenni et al., arXiv 2512.08725: spatio-temporal shifting of carbon, water and land use; a 2026 e-Energy paper (UT Arlington) on stress-adjusted water scheduling that notes carbon and water optimized separately can conflict | The general idea is crowded. Arizona-specific hourly wet-bulb cooling plus generation water, with scarcity cases (Palo Verde effluent), would be an application, not a new method |
| Consumption-based hourly carbon by flow tracing | An input-output study of 66 US BAs (2016 data); an EPA presentation using EIA-930 interchange with multi-region input-output (citing Chalendar et al. 2019) | Method exists. Our 2021-2025 Arizona series is a replication and data product |
| Regression marginal emission factors | Siler-Evans et al. 2012; Holland and Mansur 2008; Holland et al. 2024 (regularised estimator); 2025-2026 preprints on regime switching and a validation rubric (RSER 2025) | I found no paper that quantifies year-to-year stability of regression MEFs from in-BA EIA-930 data with an interchange control. This may be a small gap, but one search does not establish it |
| Reliability effects of data-center load | Searches found no utility-panel study of SAIDI/SAIFI on data-center load; only bulk-system adequacy studies (e.g. a Pennsylvania PUC study) and load-forecast work | A possible real gap, but our RQ3 uses a diluted proxy and is a null. The gap is only fillable with a data-center-specific exposure measure |
| Arizona context | Western Resource Advocates fact sheet (2025); ASU Kyl Center report (Feb 2026) finding no increase in electricity suppliers' water use in central Arizona; SRP cluster study; ACC docket | Advocacy and utility sources: check against IRPs and the docket before citing numbers |

## Not searched yet
Siting-optimization literature for data centers; reliability-constrained siting; ERCOT/Virginia data-center event studies; ACC docket text.

## Reading for the paper
No single piece is clearly novel in method. The defensible angles are (a) a regional case study that reports where standard signals fail
(the instability of hourly marginal-rate estimates, the partial transfer of savings to marginal accounting), (b) a data-center-specific reliability
analysis if an exposure measure can be built, and (c) a policy-facing brief for the ACC docket where Arizona relevance matters more than novelty.
