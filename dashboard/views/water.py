import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import core as c

c.setup("Plate 03 · Water")

sb = st.sidebar
alpha = sb.select_slider("Priority", options=[round(x, 1) for x in np.arange(0, 1.01, 0.1)], value=0.5,
                         format_func=lambda a: {1.0: "Carbon only", 0.0: "Water only", 0.5: "Balanced"}.get(
                             a, f"{a:.0%} carbon"),
                         help="How much the scheduler weighs carbon versus water when picking hours.")
k = sb.select_slider("Job length (hours per day)", options=[4, 8, 12], value=8)

fb = c.csv("water_frontier_by_ba.csv")
fb = fb[(fb["mode"] == "persist") & (fb.job == "preemptible") & (fb.k == k)]
pooled = c.csv("water_scarcity.csv")
base = pooled[(pooled.scope == "pooled") & pooled.case.str.startswith("A")].iloc[0]

c.header("Does chasing clean electricity <em>cost water</em>?",
         f"Yes. The cleanest hours are sunny afternoons, which are also the hottest, so cooling uses the most water "
         f"then. A carbon-only schedule saves about <b>{base.carbonOnly_carbon:.0f}% carbon</b> but about "
         f"<b>{round(base.carbonOnly_water)}% water</b>; a balanced one saves {base.balanced_carbon:.0f}% carbon and "
         f"{base.balanced_water:.0f}% water.")

cur = fb[np.isclose(fb.alpha, alpha)].set_index("ba")
cols = st.columns(4)
for col, b in zip(cols, ["AZPS", "SRP", "TEPC", "WALC"]):
    r = cur.loc[b]
    c.kpi(col, c.BA_LONG[b], f"{r.carbon_saved_vs_random_pct:+.1f}% CO2",
          f"water {r.water_saved_vs_random_pct:+.1f}% vs random hours", "dep",
          "Water is modeled from literature factors")
st.write("")
c.for_you({
    "Everyone": "Lowest-carbon and lowest-water are different plans. Use the priority slider to see what each region "
                "gives up, and the footprint calculator below to see a campus's water in everyday terms.",
    "Regulator (ACC staff)": "If water is a condition of approval, a carbon-only scheduling commitment does not help "
                             "it; in SRP and TEP territory it can raise water use. Ask for both numbers.",
    "Lawmaker / AG office": "The surcharge calculator below shows what a per-gallon water fee would cost a large "
                            "campus a year at an illustrative rate. Scheduling alone saves only a few percent of water.",
    "Utility planner": "Power-plant water is part of the footprint: shifting load changes which of your plants run, "
                       "and therefore their cooling water too.",
    "Data-center operator": "Balancing carbon and water costs some carbon savings. The exchange-rate table tells you "
                            "how much CO2 you give up per liter saved in each region; cooling design is the bigger lever.",
    "Water manager": "Most of a campus's water footprint is set by its cooling design and climate, not its timing. "
                     "Carbon-driven schedules move work into the hottest hours, when evaporative cooling uses the most.",
    "Resident / ratepayer advocate": "The calculator below converts a campus's water use into households and "
                                     "swimming pools. These are scenario estimates, not measured values.",
})

left, right = st.columns([1.1, 1])
with left:
    st.subheader("The daily pattern")
    a1, a2 = st.columns(2)
    ba = a1.selectbox("Region", ["SRP", "AZPS"], format_func=c.BA_LONG.get)
    season = a2.selectbox("Season", ["Summer (Jun-Aug)", "Winter (Dec-Feb)"])
    prof = c.csv("water_diurnal_profiles.csv").rename(columns={"Unnamed: 0": "key"})
    d = prof[prof.key == f"{ba}|{season}"]
    best = d.nsmallest(k, "C").hr
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for h in best:
        fig.add_shape(type="rect", xref="x", yref="paper", x0=h - 0.5, x1=h + 0.5, y0=0, y1=1,
                      fillcolor=c.G200, opacity=0.55, line_width=0, layer="below")
    fig.add_scatter(x=d.hr, y=d.C, name="Carbon (kg per kWh)", line=dict(color=c.CARBON, width=3),
                    hovertemplate="%{x}:00 carbon %{y:.2f} kg/kWh<extra></extra>")
    fig.add_scatter(x=d.hr, y=d.W_on, name="Cooling water (L per kWh)", line=dict(color=c.WATER, width=3, dash="dot"),
                    secondary_y=True, hovertemplate="%{x}:00 cooling water %{y:.2f} L/kWh<extra></extra>")
    fig.update_xaxes(title="hour of day (green = the cleanest hours a carbon-only scheduler picks)", dtick=2)
    fig.update_yaxes(title_text="carbon", secondary_y=False, color=c.CARBON)
    fig.update_yaxes(title_text="cooling water", secondary_y=True, color=c.WATER, showgrid=False,
                     tickformat=".2f")
    fig.update_yaxes(tickformat=".2f", secondary_y=False)
    st.plotly_chart(c.style(fig, 360), width="stretch")
    c.source("results/water_diurnal_profiles.csv (daily profiles exist for SRP and APS only)")
with right:
    st.subheader("The tradeoff curve")
    fig = go.Figure()
    for b, g in fb.groupby("ba"):
        g = g.sort_values("alpha")
        fig.add_scatter(x=g.water_saved_vs_random_pct, y=g.carbon_saved_vs_random_pct, mode="lines+markers",
                        name=c.BA_NAMES[b], line=dict(color=c.BA_COLORS[b], width=2.5), marker=dict(size=5),
                        customdata=g.alpha, hovertemplate="priority %{customdata:.0%} carbon: "
                                                          "%{y:.1f}% CO2, %{x:.1f}% water<extra></extra>")
        p = g[np.isclose(g.alpha, alpha)]
        fig.add_scatter(x=p.water_saved_vs_random_pct, y=p.carbon_saved_vs_random_pct, mode="markers",
                        marker=dict(size=15, color=c.BA_COLORS[b], line=dict(color="white", width=2)),
                        showlegend=False, hoverinfo="skip")
    fig.add_vline(x=0, line_color=c.NEUTRAL)
    fig.update_layout(xaxis_title="% water saved vs random hours", yaxis_title="% carbon saved vs random hours")
    st.plotly_chart(c.style(fig, 400), width="stretch")
    c.source("results/water_frontier_by_ba.csv (simple forecast, 2025). Big dots = current priority.")

st.subheader("The exchange rate: what a liter of water costs in carbon")
rows = []
for b, g in fb.groupby("ba"):
    one, a = g[np.isclose(g.alpha, 1.0)].iloc[0], g[np.isclose(g.alpha, alpha)].iloc[0]
    dw, dc = one.W - a.W, a.C - one.C
    rows.append({"Region": c.BA_LONG[b],
                 "Extra carbon vs carbon-only (%)": 100 * dc / one.C,
                 "Water saved vs carbon-only (%)": 100 * dw / one.W,
                 "kg CO2 given up per liter saved": dc / dw if dw > 0 and alpha < 1 else np.nan})
ex = pd.DataFrame(rows)
st.dataframe(ex, hide_index=True, width="stretch",
             column_config={c_: st.column_config.NumberColumn(format="%.2f") for c_ in ex.columns[1:]})
c.source("results/water_frontier_by_ba.csv. Move the priority slider in the sidebar to change the comparison.")
st.markdown(
    f"**Reading it.** SRP and TEP show a real conflict: their cleanest hours are the thirstiest, and this holds under "
    f"every water accounting the team tested. APS's answer depends on how the Solana solar-thermal plant is counted "
    f"(see the measured-data check below). These are scenario estimates, not meter readings "
    f"{c.badge('dep', 'Modeled water')}.",
    unsafe_allow_html=True)

with st.expander("What would change this? Water accounting scenarios"):
    sc = c.csv("water_scarcity.csv")
    t = sc.pivot(index="case", columns="scope", values="carbonOnly_water")[["pooled", "AZPS", "SRP", "TEPC", "WALC"]]
    t.columns = ["All regions", "APS", "SRP", "TEP", "WALC"]
    st.markdown("Water change (%) under a carbon-only schedule. Positive = saves water, negative = uses more.")
    st.dataframe(t.round(1), width="stretch")
    c.source("results/water_scarcity.csv")
    st.markdown("Counting hydro reservoir evaporation (rows D and E) flips WALC into a large water penalty. "
                "A reservoir evaporates whether or not a job runs at 2pm, so that accounting should not drive "
                "hour-by-hour scheduling.")

st.divider()
st.subheader("A campus's water footprint, in everyday terms")
f1, f2, f3, f4 = st.columns(4)
P_mw = f1.slider("Campus size (MW)", 100, 1000, 500, 50, key="w_mw")
reg = f2.selectbox("Region", list(c.BA_LONG), format_func=c.BA_LONG.get, key="w_reg")
evap = f3.select_slider("Cooling design: evaporative share", options=[0.25, 0.5, 1.0], value=1.0,
                        format_func=lambda x: f"{x:.0%}",
                        help="Share of heat rejected by evaporation. Hybrid or dry cooling lowers it, at the cost of "
                             "more electricity on hot days (not modelled here).")
fee = f4.slider("Illustrative water fee ($ per 1,000 gallons)", 0.0, 20.0, 5.0, 0.5,
                help="Hypothetical rate to show scale. Check the actual surcharge proposal before quoting a number.")
wd = c.csv("water_descriptives.csv").set_index("ba")
it_kwh = c.campus_mwh(P_mw) * 1000 / 1.2                          # IT energy (PUE 1.2)
onsite_L, plant_L = it_kwh * wd.loc[reg, "W_on_L_per_kWh"] * evap, it_kwh * wd.loc[reg, "W_off_L_per_kWh"]
POOL_L, HOUSE_L, GAL = 2.5e6, 300 * 3.785 * 365, 3.785          # Olympic pool; household at 300 gal/day; L per gal
w1, w2, w3, w4 = st.columns(4)
c.kpi(w1, "On-site cooling water", f"{onsite_L/1e9:,.2f} billion L/yr", f"{onsite_L/POOL_L:,.0f} Olympic pools",
      "dep", "Modeled with literature factors")
c.kpi(w2, "Same, in households", f"{onsite_L/HOUSE_L:,.0f}", "homes' yearly indoor and outdoor use", "approx",
      "Assumes 300 gallons per household per day (EPA WaterSense)")
c.kpi(w3, "Plus power-plant water", f"{plant_L/1e9:,.2f} billion L/yr", "water used to generate its electricity",
      "dep", "Literature factors by fuel")
c.kpi(w4, "Fee on on-site water", f"${onsite_L/GAL/1000*fee/1e6:,.1f}M/yr", f"at ${fee:.2f} per 1,000 gallons",
      "approx", "Illustrative rate only")
st.write("")
st.markdown(
    f"**Reading it.** These are scenario estimates for a campus running at 80% load with {evap:.0%} evaporative cooling and "
    f"PUE 1.2, using the region's average weather {c.badge('dep', 'Cooling design changes this most')}. Power-plant "
    f"water is consumed wherever the electricity is made, often outside the local basin. Smart scheduling changes "
    f"these totals by only a few percent; cooling design and location change them far more.",
    unsafe_allow_html=True)
sc_ = c.csv("case_study_surcharge.csv")
d1 = sc_[sc_.group.str.startswith("default") & (sc_.evaporative_share == 1.0)]
st.markdown(
    f"**Team cross-check.** The team's case study for the two default Stage 1 sites finds a hypothetical $0.01 per gallon "
    f"fee would cost ${d1['usd_million_at_0.01'].min():.1f}M to ${d1['usd_million_at_0.01'].max():.1f}M a year for one "
    f"500 MW project at full evaporative cooling, and half that at 50% evaporative "
    f"{c.badge('approx', 'Illustrative rate; actual use may be far lower')}. Cooling design, not scheduling, is the "
    f"big water lever. The electricity cost of drier cooling is not modelled yet.", unsafe_allow_html=True)
c.source("results/case_study_surcharge.csv")

st.divider()
st.subheader("Do measured power-plant data change the answer?")
st.markdown("The base water model uses literature factors per fuel. The team also measured each Arizona plant's actual "
            "cooling water from EIA-860/923 (2025). Pick an accounting to see how a carbon-only schedule changes water use.")
wm = c.csv("water_measured_cases.csv")
cases = [x for x in wm.case.unique() if "hydro 0" in x]
pretty = {"literature | nuclear x1, hydro 0": "Literature factors (base)",
          "literature | nuclear x0, hydro 0": "Literature, Palo Verde water treated as free",
          "measured M1 | nuclear x1, hydro 0": "Measured plants, method 1",
          "measured M1 | nuclear x0, hydro 0": "Measured method 1, Palo Verde free",
          "measured M2 | nuclear x1, hydro 0": "Measured plants, method 2",
          "measured M2 | nuclear x0, hydro 0": "Measured method 2, Palo Verde free",
          "M1, CSP counted as PV | nuclear x1, hydro 0": "Measured method 1, Solana counted as solar PV"}
pick = st.multiselect("Accountings to compare", cases, default=cases[:1] + [x for x in cases if x.startswith("measured M1 | nuclear x1")]
                      + [x for x in cases if x.startswith("M1, CSP")], format_func=lambda x: pretty.get(x, x))
fig = go.Figure()
for i, cs_ in enumerate(pick):
    g = wm[(wm.case == cs_) & (wm.scope != "pooled")].set_index("scope").reindex(["AZPS", "SRP", "TEPC", "WALC"])
    fig.add_bar(x=[c.BA_NAMES[b] for b in g.index], y=g.carbonOnly_water, name=pretty.get(cs_, cs_),
                marker_color=[c.WATER, c.WATER_L, c.G500, c.G200, "#B08968", c.CARBON_L, c.AMBER][i % 7],
                hovertemplate="%{x}: %{y:+.1f}% water<extra></extra>")
fig.add_hline(y=0, line_color=c.NEUTRAL)
fig.update_layout(barmode="group", yaxis_title="% water saved by a carbon-only schedule (negative = uses more)")
st.plotly_chart(c.style(fig, 380), width="stretch")
c.source("results/water_measured_cases.csv (2025, vs random hours; hydro evaporation excluded)")
wf = c.csv("water_measured_factors.csv")
wf = wf[wf.group.isin(["COL", "NG", "NUC"])].copy()
wf["Plant type"] = wf.group.map({"COL": "Coal", "NG": "Gas", "NUC": "Nuclear"})
wf["Region"] = wf.ba.map(c.BA_NAMES)
c.table(wf[["Region", "Plant type", "L_per_kWh_M1", "literature_L_per_kWh", "plants_reporting", "coverage"]]
        .rename(columns={"L_per_kWh_M1": "Measured (L/kWh)", "literature_L_per_kWh": "Literature (L/kWh)",
                         "plants_reporting": "Plants reporting", "coverage": "Generation covered"})
        .dropna(subset=["Measured (L/kWh)"]), "water_factors_measured_vs_literature",
        column_config={"Measured (L/kWh)": st.column_config.NumberColumn(format="%.2f"),
                       "Literature (L/kWh)": st.column_config.NumberColumn(format="%.2f"),
                       "Generation covered": st.column_config.NumberColumn(format="percent")})
c.source("results/water_measured_factors.csv (EIA-860/923, 2025)")
st.markdown(
    f"**Reading it.** SRP and TEP use more water under a carbon-only schedule in every accounting. APS flips between a "
    f"small saving and a small penalty depending on whether Solana, a wet-cooled solar-thermal plant, is counted with "
    f"solar PV; public data do not give its hourly timing {c.badge('dep', 'Solana timing unknown')}. Every reporting "
    f"Arizona thermal plant is wet-cooled; measured gas plants use more water than the literature factor and coal "
    f"plants less.", unsafe_allow_html=True)
