import pandas as pd
import streamlit as st

import core as c

c.setup("Appendix · Methods")
c.header("About this dashboard and its <em>assumptions</em>",
         "Arizona is deciding how to handle a wave of AI data centers. This dashboard turns the team's analysis "
         "into four questions a regulator would ask, and shows what each answer depends on.")

st.subheader("Who this is for, and what each user needs")
c.table(pd.DataFrame([
    ["Regulator (ACC staff)", "Screen large-load applications; set conditions; defend decisions",
     "Evidence headroom per utility; head-to-head site comparison; levers ranked in tonnes",
     "Can the grid take it?, Where should they go?"],
    ["Lawmaker / AG office", "Judge pauses, surcharges and incentives with numbers, not anecdotes",
     "Pipeline as years of normal growth; water-fee calculator; regional emissions comparison",
     "Can the grid take it?, Does clean cost water?"],
    ["Utility planner", "Know how much large load fits, how fast load is growing, how clean supply is",
     "Headroom table with projects that fit; growth history; import dependence; cleaner-grid trend",
     "Can the grid take it?, What cuts carbon?"],
    ["Data-center operator", "Pick region, cooling and timing; report carbon and water credibly",
     "Lever ranking; seasonal clean-hour heatmap; carbon-water exchange rate; target-site shortlist",
     "What cuts carbon?, Does clean cost water?, Where should they go?"],
    ["Water manager", "Protect groundwater and river supplies; understand data-center water demand",
     "Campus water in pools and households; carbon versus water tradeoff; groundwater-weighted siting",
     "Does clean cost water?, Where should they go?"],
    ["Resident / ratepayer advocate", "Understand effects on bills, outages and local water in plain terms",
     "Plain-language takeaways; outage evidence; water in household terms; where data centers cluster",
     "All pages (choose this role in the sidebar)"],
], columns=["User", "What they need", "What the tool gives them", "Where"]), "users_and_requirements")

st.subheader("How sure are we? The three badges")
st.markdown(
    f"{c.badge('solid')} measured from data and robust in the project's checks<br>"
    f"{c.badge('dep')} the result moves if a stated assumption changes<br>"
    f"{c.badge('approx')} rough estimate or incomplete data", unsafe_allow_html=True)

st.subheader("Assumptions")
st.dataframe(pd.DataFrame([
    ["Load cap", "25%", "Largest load jump the reliability data covers; a policy choice", "Can the grid take it?"],
    ["Data-center load factor", "0.8", "docs/STAGE1.md", "Grid, Carbon"],
    ["ACC pipeline", "1,300 MW building, 4,000+ MW planned", "ACC workshop, April 2026 (fact-checked)", "Grid"],
    ["Carbon accounting", "Consumed (counts imports)", "data/processed/consumption_ci.parquet", "Carbon"],
    ["Emissions method", "Average", "Marginal estimate shown as a check (docs/MARGINAL.md); no ground truth exists", "Carbon"],
    ["Measured checks", "EPA plant CO2; EIA-860/923 plant water", "docs/MEASURED_EMISSIONS.md, docs/WATER_MEASURED.md", "Carbon, Water"],
    ["Cooling design", "100% evaporative (adjustable)", "Electricity cost of drier cooling not modelled", "Water"],
    ["Interconnection", "Distance to 115-345 kV substations", "Proximity only; real capacity data are not public", "Where"],
    ["Flexible share of work", "10%", "Illustrative; no data on real flexibility", "Carbon"],
    ["Water factors", "Literature medians (Macknick et al. 2012), PUE 1.2", "docs/data_dictionary.md", "Water"],
    ["Hydro water", "0 in base case", "Reservoir evaporation is contested", "Water"],
    ["Siting weights", "Depth .30, trend .10, heat .20, sun .15, queue .25", "src/rq2_siting.py", "Where"],
    ["Queue direction", "Long queue = strain", "Could instead mean more supply", "Where"],
], columns=["Assumption", "Default", "Source or reason", "Page"]), hide_index=True, width="stretch")

st.subheader("Data sources")
st.markdown("""
- **EIA-930**: hourly electricity generation by fuel and flows between regions, 2021 to 2025
- **EPA eGRID 2023**: CO2 emission rate of each type of power plant
- **EIA-861**: every US utility's yearly sales, customers and outage minutes, 2013 to 2024
- **LBNL Queued Up**: power plants waiting to connect to the grid
- **ADWR and USGS**: groundwater depth and trends from about 46,000 Arizona well sites
- **NASA POWER**: temperature, humidity and sunshine
- **OpenStreetMap**: mapped data centers and substations
- **US Census 2020**: population
""")

st.subheader("Known limitations")
st.markdown("""
- Carbon uses **average** emissions. A marginal-emissions estimate is shown as a check; it disagrees with the average
  and has no ground truth. Estimated CO2 runs 20-30% below EPA's measured values on SRP, TEP and WALC.
- Water is a **scenario estimate**, not measured, and hourly weather exists at only three points
  (Phoenix, Tucson, Lake Havasu).
- Reliability is measured at the **utility level**; it cannot link any outage to a specific data center, and
  outage minutes mostly reflect local causes such as storms.
- Siting squares are about 25 km wide and have **no transmission, fiber or land data**.
- OpenStreetMap misses some data centers and mislabels some IT offices.
""")

st.subheader("Glossary")
st.markdown("""
- **Balancing authority (BA) / region**: the operator that runs a part of the grid. Arizona's four are APS, SRP,
  TEP and WALC.
- **Carbon intensity**: kilograms of CO2 released per megawatt-hour of electricity.
- **Business (C&I) load**: electricity sold to commercial and industrial customers in a year.
- **Headroom**: how much new data-center load fits under the load cap.
- **SAIDI / outage minutes**: average minutes per year a customer is without power.
- **PUE**: total facility power divided by the power the computers use (1.2 means 20% overhead).
- **Wet-bulb temperature**: a measure of heat plus humidity; it drives how much water evaporative cooling uses.
- **Persistence / simple guess**: forecasting that tomorrow looks like today at the same hour.
""")
st.caption("FSE 570 Capstone, Arizona State University, Fall 2026. Kashish Patel, Manya Tiwari, Mounusha Metti, Anamika Ghorpade.")
