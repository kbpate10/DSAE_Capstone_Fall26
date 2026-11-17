import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core as c

c.setup("Plate 01 · The grid")
u = c.utility_load_2024()

cap = st.sidebar.slider("Load cap (share of a utility's business load)", 0.10, 0.50, 0.25, 0.05, format="%.2f",
                        help="The largest load increase the project's reliability data covers. "
                             "Beyond it, history cannot say whether the grid stays reliable.")
lf = st.sidebar.slider("Data-center load factor", 0.5, 1.0, c.LOAD_FACTOR, 0.05,
                       help="Average share of the time a data center runs at full power.")

u["headroom_mw"] = c.headroom_mw(u.ci_mwh, cap, lf)
total = u.headroom_mw.sum()
pipeline = c.ACC_UNDER_CONSTRUCTION_MW + c.ACC_PLANNED_MW

# ---- historical growth (for "is this normal growth?")
hist = c.az_ci_by_year()
tot = hist.groupby("year").ci_mwh.sum()
mw_per_yr = lambda a, b: (tot[b] - tot[a]) / (b - a) / (lf * c.HOURS)
g_long, g_recent = mw_per_yr(2013, 2024), mw_per_yr(2021, 2024)
yrs_long, yrs_recent = pipeline / g_long, pipeline / g_recent

c.header("Can Arizona's grid absorb the data centers <em>already coming</em>?",
         f"At a {cap:.0%} cap, all Arizona utilities together can take about <b>{total/1000:,.1f} GW</b> of new "
         f"data-center load inside the range our reliability evidence covers. The ACC reports about "
         f"<b>1.3 GW under construction</b> and <b>more than 4 GW planned</b>.")

k1, k2, k3, k4 = st.columns(4)
c.kpi(k1, "Grid headroom, all AZ utilities", f"{total:,.0f} MW", f"at a {cap:.0%} cap", "dep",
      "Depends on the load cap, a policy choice")
c.kpi(k2, "Under construction (ACC)", "1,300 MW", "ACC workshop, April 2026", "solid", "Commission statement")
c.kpi(k3, "Under construction + planned", "5,300+ MW", "more than 4,000 MW planned", "solid", "Commission statement")
c.kpi(k4, "Pipeline vs headroom", f"{pipeline/total:,.1f}x", "how far the pipeline exceeds headroom", "dep",
      "Depends on the load cap")
st.write("")
c.for_you({
    "Everyone": f"The data centers already coming are about <b>{pipeline/total:,.1f} times</b> what the reliability "
                f"evidence covers. That does not predict outages; it means most of the wave is untested ground.",
    "Regulator (ACC staff)": f"Treat about <b>{total:,.0f} MW</b> as the tested range at this cap. Applications beyond "
                             f"it rely on engineering studies, not historical evidence, so ask for interconnection "
                             f"studies and phased energization as conditions.",
    "Lawmaker / AG office": f"The pipeline equals about <b>{yrs_long:,.0f} years</b> of Arizona's average business-load "
                            f"growth since 2013 (or {yrs_recent:,.0f} years at the faster 2021-2024 pace). That is "
                            f"the scale of the decision, whatever the policy response.",
    "Utility planner": "Use the table below for your utility. One 500 MW campus is about 19% of APS's or SRP's "
                       "business load and about 70% of TEP's; the cap slider shows how many fit under your own limit.",
    "Data-center operator": "Only APS and SRP territories can take a 500 MW campus inside the tested range. Elsewhere, "
                            "expect longer interconnection studies or a smaller first phase.",
    "Water manager": "Grid headroom pushes large projects toward APS and SRP territory, which means the Phoenix and "
                     "Pinal groundwater basins are where the water pressure will concentrate.",
    "Resident / ratepayer advocate": "So far the data show no link between business-load growth and outage minutes, "
                                     "but the coming wave is several times larger than anything in the data. "
                                     "Whether bills rise is not yet analyzed.",
})

# ---- headroom vs pipeline
top = u.head(3).copy()
rest = u.iloc[3:].headroom_mw.sum()
fig = go.Figure()
shades = [c.G900, c.G500, "#B08968"]
for (_, r), col in zip(top.iterrows(), shades):
    fig.add_bar(y=["Grid headroom"], x=[r.headroom_mw], orientation="h", name=r.util_name.replace(" Co", ""),
                marker_color=col, hovertemplate=f"{r.util_name}: %{{x:,.0f}} MW<extra></extra>")
fig.add_bar(y=["Grid headroom"], x=[rest], orientation="h", name=f"{len(u)-3} smaller utilities",
            marker_color=c.G200, hovertemplate="Smaller utilities: %{x:,.0f} MW<extra></extra>")
fig.add_bar(y=["Under construction"], x=[c.ACC_UNDER_CONSTRUCTION_MW], orientation="h", name="Under construction",
            marker_color=c.CARBON_L, hovertemplate="%{x:,.0f} MW<extra></extra>")
fig.add_bar(y=["Under construction + planned"], x=[c.ACC_UNDER_CONSTRUCTION_MW], orientation="h",
            marker_color=c.CARBON_L, showlegend=False, hovertemplate="Under construction: %{x:,.0f} MW<extra></extra>")
fig.add_bar(y=["Under construction + planned"], x=[c.ACC_PLANNED_MW], orientation="h", name="Planned",
            marker_color=c.CARBON, hovertemplate="Planned: %{x:,.0f}+ MW<extra></extra>")
fig.add_vline(x=total, line_dash="dash", line_color=c.RED,
              annotation_text=f"headroom {total:,.0f} MW", annotation_position="top")
fig.update_layout(barmode="stack", xaxis_title="megawatts of data-center load",
                  yaxis=dict(categoryorder="array",
                             categoryarray=["Under construction + planned", "Under construction", "Grid headroom"]))
st.plotly_chart(c.style(fig, 330), width="stretch")
c.source("data/processed/eia861_panel.parquet (2024 commercial + industrial sales), "
         "docs/regulatory_context_check.md (ACC pipeline)")
c.how_to_read("The top bar is how much new data-center load each utility could add while staying under the cap "
              "(its share of 2024 business load). The two bars below are the data centers the Arizona Corporation "
              "Commission reports as under construction and planned. Where the brown bars cross the red line, the "
              "planned load goes beyond the range the reliability data covers.")

# ---- per utility
left, right = st.columns([1.15, 1])
with left:
    st.subheader("How many projects fit in each utility?")
    t = u.head(8).copy()
    t["Business load (TWh)"] = t.ci_mwh / 1e6
    t["Headroom (MW)"] = t.headroom_mw
    for p in (100, 500):
        t[f"{p} MW projects that fit"] = np.floor(t.headroom_mw / p).astype(int)
    t["Share one 500 MW project adds"] = c.campus_mwh(500, lf) / t.ci_mwh
    c.table(t[["util_name", "Business load (TWh)", "Headroom (MW)", "100 MW projects that fit",
               "500 MW projects that fit", "Share one 500 MW project adds"]]
            .rename(columns={"util_name": "Utility"}), "utility_headroom",
            column_config={"Business load (TWh)": st.column_config.NumberColumn(format="%.2f"),
                                "Headroom (MW)": st.column_config.NumberColumn(format="%d"),
                                "Share one 500 MW project adds": st.column_config.ProgressColumn(
                                    format="percent", min_value=0, max_value=1)})
    c.source("data/processed/eia861_panel.parquet")
    st.caption("Only APS and SRP can host even one 500 MW campus at a 25% cap. For TEP a single one would add "
               "about 70% to its business load.")
with right:
    st.subheader("Why a cap? What the reliability data shows")
    lad = c.csv("rq3_baseline_ladder.csv")
    lad["label"] = lad.rung.str.replace(r"^\w+\s+", "", regex=True)
    lad["pc"] = lad["pct_change"]
    fig2 = go.Figure(go.Scatter(
        x=lad.pc, y=lad.label, mode="markers", marker=dict(size=10, color=c.G700),
        error_x=dict(type="data", symmetric=False, array=lad.hi - lad.pc, arrayminus=lad.pc - lad.lo,
                     color=c.G500, thickness=1.6),
        hovertemplate="%{y}: %{x:+.1f}%<extra></extra>"))
    fig2.add_vline(x=0, line_color=c.NEUTRAL)
    fig2.update_layout(xaxis_title="% change in outage minutes", yaxis=dict(autorange="reversed"))
    st.plotly_chart(c.style(fig2, 360), width="stretch")
    c.source("results/rq3_baseline_ladder.csv")

st.markdown(
    f"**Reading it.** A naive comparison says fast-growing utilities have about 40% more outage minutes. Once each "
    f"utility is compared with itself over time, the effect is about zero, and the data rules out anything above "
    f"about +2.5% per +10% load {c.badge('solid', 'Robust across specifications')}. That evidence only covers load "
    f"jumps up to roughly 25%. Past the headroom line, the grid will not necessarily fail; there is simply no "
    f"history to say it will be fine.", unsafe_allow_html=True)

st.divider()
st.subheader("Is this normal growth, or something new?")
g1, g2, g3 = st.columns(3)
c.kpi(g1, "Average yearly growth, 2013-2024", f"{g_long:,.0f} MW/yr", "Arizona business load, as constant MW",
      "solid", "EIA-861 sales")
c.kpi(g2, "Recent yearly growth, 2021-2024", f"{g_recent:,.0f} MW/yr", "the first data-center years", "solid",
      "EIA-861 sales")
c.kpi(g3, "The pipeline equals", f"{yrs_long:,.0f} years", f"of average growth ({yrs_recent:,.0f} at the recent pace)",
      "dep", "ACC pipeline figure; load factor")
st.write("")
top3 = ["Salt River Project", "Arizona Public Service Co", "Tucson Electric Power Co"]
h2 = hist.assign(group=hist.util_name.where(hist.util_name.isin(top3), "All other utilities"))
h2 = h2.groupby(["year", "group"], as_index=False).ci_mwh.sum()
fig3 = go.Figure()
for grp, col in zip(top3 + ["All other utilities"], [c.G500, c.G900, "#B08968", c.G200]):
    d = h2[h2.group == grp]
    fig3.add_bar(x=d.year, y=d.ci_mwh / 1e6, name=grp.replace(" Co", ""), marker_color=col,
                 hovertemplate=f"{grp} %{{x}}: %{{y:.2f}} TWh<extra></extra>")
fig3.add_annotation(x=2022.5, y=tot.max() / 1e6 * 1.06, text="flat for 8 years, then a jump",
                    showarrow=False, font=dict(color=c.G900))
fig3.update_layout(barmode="stack", yaxis_title="business (C&I) electricity sold, TWh", xaxis=dict(dtick=1))
st.plotly_chart(c.style(fig3, 360), width="stretch")
c.source("data/processed/eia861_panel.parquet (Arizona utilities, excluding EIA's state adjustment row)")
st.markdown(
    f"Arizona's business electricity use was flat from 2013 to 2021 and then climbed about "
    f"{(tot[2024]-tot[2021])/1e6:,.1f} TWh in three years, mostly at APS, as the first large data centers came "
    f"online. The {pipeline:,} MW pipeline would add about {c.campus_mwh(pipeline, lf)/1e6:,.0f} TWh a year on "
    f"top of today's {tot[2024]/1e6:,.0f} TWh {c.badge('dep', 'Assumes the planned load runs at this load factor')}.",
    unsafe_allow_html=True)
st.write("")

st.divider()
st.subheader("What the reliability evidence can and cannot see")
r1, r2 = st.columns([1, 1])
with r1:
    st.markdown("**Worst case: outage minutes after one project** (upper end of the reliability estimate)")
    rb = c.csv("case_study_reliability_bound.csv")
    rb = rb.assign(Utility=rb.util_name.str.title().str.replace(" Co", ""),
                   **{"Project (MW)": rb.P_MW, "Adds to business load": rb.added_load_share_of_CI,
                      "Outage minutes today": rb.baseline_saidi_min,
                      "Worst-case minutes after": rb.projected_saidi_min_upper_bound,
                      "Worst-case increase": rb.increase_pct_upper_bound / 100})
    c.table(rb[["Utility", "Project (MW)", "Adds to business load", "Outage minutes today", "Worst-case minutes after",
                "Worst-case increase"]], "reliability_worst_case",
            column_config={"Adds to business load": st.column_config.NumberColumn(format="percent"),
                           "Worst-case increase": st.column_config.NumberColumn(format="percent"),
                           "Outage minutes today": st.column_config.NumberColumn(format="%.0f"),
                           "Worst-case minutes after": st.column_config.NumberColumn(format="%.1f")})
    c.source("results/case_study_reliability_bound.csv (uses the 95% upper bound of the main reliability estimate)")
    st.caption("Even at the top of the plausible range, one 500 MW campus adds about 4 minutes a year for APS or "
               "SRP customers. Projects that exceed the 25% cap are left out because the evidence does not cover them.")
with r2:
    st.markdown("**Smallest effect the data could have detected** (80% power)")
    pw = c.csv("rq3_power.csv")
    pw = pw.assign(Design=pw.design.str.replace("continuous exposure", "Load growth").str.replace(
        "surge indicator", "Surge year"))
    fig = go.Figure(go.Bar(x=pw.mde80_pct, y=pw.Design, orientation="h",
                           marker_color=[c.G700 if v < 5 else (c.AMBER if v < 15 else c.RED) for v in pw.mde80_pct],
                           text=[f"{v:.1f}%" for v in pw.mde80_pct], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: could detect %{x:.1f}% or more<extra></extra>"))
    fig.update_layout(xaxis=dict(title="minimum detectable change in outage minutes (%)",
                                 range=[0, pw.mde80_pct.max() * 1.25]), yaxis=dict(autorange="reversed"))
    st.plotly_chart(c.style(fig, 330), width="stretch")
    c.source("results/rq3_power.csv")
dc = c.csv("rq3_dc_exposure.csv")
rf = dc[dc.model == "RF reduced form: post2019, any data center"].iloc[0]
st.markdown(
    f"**Reading it.** Nationally the data could catch an effect of about 2 to 3% per +10% load, and found none. "
    f"For sudden surge years or Arizona alone it can only catch very large effects, so silence there means little "
    f"{c.badge('solid', 'Power analysis')}. A data-center-specific test (utilities with mapped data centers after 2019) "
    f"also finds no harm: outage minutes changed by about {rf.coef*100:+.1f}% ({rf.lo*100:+.1f}% to {rf.hi*100:+.1f}%). "
    f"But that test is weak, because mapped locations say little about how much load each utility actually took on "
    f"{c.badge('approx', 'First stage F about 2.8')}.", unsafe_allow_html=True)
st.write("")
