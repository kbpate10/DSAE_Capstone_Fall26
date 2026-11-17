import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core as c

c.setup("Plate 02 · Carbon")

sb = st.sidebar
P = sb.slider("Campus size (MW)", 100, 1000, 500, 50)
lf = sb.slider("Load factor", 0.5, 1.0, c.LOAD_FACTOR, 0.05)
flex = sb.slider("Flexible share of work", 0.0, 0.40, 0.10, 0.05, format="%.2f",
                 help="Share of computing that can wait a few hours, such as model training.")
acct = sb.radio("Carbon accounting", ["consumed", "produced"],
                format_func=lambda x: {"consumed": "What customers consume (counts imports)",
                                       "produced": "What local plants emit"}[x])
here = sb.selectbox("Campus connects to", list(c.BA_LONG), format_func=c.BA_LONG.get, index=0)
sb.caption("Numbers on this page use average emissions. The marginal-emissions check is at the bottom of the page.")

ci = c.carbon_by_ba()[acct]
E = c.campus_mwh(P, lf)
co2 = E * ci / 1000                                   # tonnes per year
s_simple, s_oracle = c.sched_saving(policy="persist"), c.sched_saving(policy="oracle")
cleanest = co2.idxmin()

lev = pd.DataFrame({
    "lever": ["Connect in the cleanest region", "Schedule flexible work (simple forecast)",
              "Schedule flexible work (perfect foresight)"],
    "tonnes": [co2[here] - co2[cleanest], co2[here] * flex * s_simple[here], co2[here] * flex * s_oracle[here]],
})
ratio = lev.tonnes[0] / lev.tonnes[1] if lev.tonnes[1] > 0 else float("nan")

c.header("What <em>actually</em> cuts a data center's carbon?",
         "Where a data center connects matters far more than when it runs its flexible work. "
         + (f"For this campus, moving from {c.BA_NAMES[here]} to {c.BA_NAMES[cleanest]} saves about "
            f"<b>{c.fmt_t(lev.tonnes[0])} CO2 a year</b>, roughly <b>{ratio:,.0f}x</b> what smart scheduling saves."
            if here != cleanest else
            f"{c.BA_NAMES[here]} is already the cleanest region under this accounting; pick another region to compare."))

k1, k2, k3 = st.columns(3)
c.kpi(k1, f"Campus emissions in {c.BA_NAMES[here]}", c.fmt_t(co2[here]) + " CO2/yr",
      f"{P} MW at {lf:.0%} load factor", "dep", "Average emissions; accounting choice in the sidebar")
c.kpi(k2, "Saved by changing region", c.fmt_t(lev.tonnes[0]), f"to {c.BA_NAMES[cleanest]}", "dep",
      "Depends on import accounting")
c.kpi(k3, "Saved by scheduling", c.fmt_t(lev.tonnes[1]), f"{flex:.0%} of work moved to cleaner hours", "dep",
      "Average emissions; marginal could be smaller")
st.write("")
yr = c.carbon_by_year()
first, last = yr[yr.year == yr.year.min()].set_index("respondent")[acct], yr[yr.year == yr.year.max()].set_index("respondent")[acct]
gap0, gap1 = first.max() / first.min(), last.max() / last.min()
c.for_you({
    "Everyone": "Location is the big carbon lever; scheduling is a small one. The gap between regions is shrinking "
                "as APS and TEP add solar and retire coal, so today's ranking will not hold forever.",
    "Regulator (ACC staff)": "If carbon matters in a large-load decision, where the load connects matters far more "
                             "than any promise to shift work in time. Ask applicants for annual emissions by region, "
                             "not only scheduling commitments.",
    "Lawmaker / AG office": "Steering new load toward cleaner regions cuts far more CO2 than scheduling rules. But the "
                            "regional gap is narrowing each year, so a policy built on today's gap ages quickly.",
    "Utility planner": f"Your region's import dependence and trend are below. The dirtiest-to-cleanest gap went from "
                       f"{gap0:.1f}x in {int(yr.year.min())} to {gap1:.1f}x in {int(yr.year.max())}.",
    "Data-center operator": "Pick the region first; scheduling is a refinement. The simple 'same hour yesterday' "
                            "forecast gets almost all of the scheduling benefit, so a costly forecasting service "
                            "adds little in Arizona. Use the heatmap for seasonal timing.",
    "Water manager": "Carbon-driven timing pushes work into hot afternoons; see the water page for what that costs.",
    "Resident / ratepayer advocate": "A data center's carbon depends mostly on which grid it joins. Arizona's grid is "
                                     "getting cleaner, fastest in APS and TEP territory.",
})


left, right = st.columns([1, 1])
with left:
    st.subheader("The levers, ranked")
    l2 = lev.sort_values("tonnes")
    fig = go.Figure(go.Bar(x=l2.tonnes, y=l2.lever, orientation="h",
                           marker_color=[c.G200 if "perfect" in s else (c.G700 if "region" in s else c.G500)
                                         for s in l2.lever],
                           text=[c.fmt_t(v) for v in l2.tonnes], textposition="outside",
                           hovertemplate="%{y}: %{x:,.0f} t CO2/yr<extra></extra>"))
    fig.update_traces(cliponaxis=False)
    fig.update_layout(xaxis=dict(title="tonnes of CO2 saved per year",
                                 range=[0, max(lev.tonnes.max(), 1) * 1.25]))
    st.plotly_chart(c.style(fig, 300), width="stretch")
    c.source("data/processed/carbon_intensity.parquet, consumption_ci.parquet, results/schedule_savings.csv")
with right:
    st.subheader("Campus emissions by region")
    allc = c.carbon_by_ba()
    fig = go.Figure()
    for col, name, colr in (("produced", "What local plants emit", c.CARBON_L),
                            ("consumed", "What customers consume", c.CARBON)):
        fig.add_bar(x=[c.BA_NAMES[b] for b in allc.index], y=E * allc[col] / 1000, name=name, marker_color=colr,
                    hovertemplate="%{x}: %{y:,.0f} t CO2/yr<extra></extra>")
    fig.update_layout(barmode="group", yaxis_title="tonnes CO2 per year")
    st.plotly_chart(c.style(fig, 300), width="stretch")
    c.source("data/processed/carbon_intensity.parquet, consumption_ci.parquet")

st.markdown(
    f"**Why two accountings?** Regions trade electricity. Counting only local plants, the dirtiest region is "
    f"{allc.produced.max()/allc.produced.min():.1f}x the cleanest; counting imports, {allc.consumed.max()/allc.consumed.min():.1f}x, "
    f"and WALC moves from cleanest to the middle. SRP looks clean largely because the Palo Verde nuclear plant is reported "
    f"there. Location still dominates either way {c.badge('dep', 'Accounting choice; see the check at the bottom')}.",
    unsafe_allow_html=True)

st.divider()
st.subheader("When is the grid cleanest?")
h = c.carbon_hourly().groupby(["respondent", "hour"])[acct].mean().reset_index()
fig = go.Figure()
fig.add_vrect(x0=9, x1=16, fillcolor=c.G200, opacity=0.35, line_width=0, annotation_text="solar hours",
              annotation_position="top left")
for b, g in h.groupby("respondent"):
    fig.add_scatter(x=g.hour, y=g[acct], name=c.BA_NAMES[b], line=dict(color=c.BA_COLORS[b], width=3),
                    hovertemplate=f"{c.BA_NAMES[b]} %{{x}}:00: %{{y:,.0f}} kg/MWh<extra></extra>")
fig.update_layout(xaxis=dict(title="hour of day (Arizona time)", dtick=2), yaxis_title="kg CO2 per MWh")
st.plotly_chart(c.style(fig, 340), width="stretch")
c.source("data/processed/carbon_intensity.parquet / consumption_ci.parquet, 2021 to 2025")

a, b = st.columns([1.2, 1])
with a:
    st.subheader("You don't need AI to schedule AI")
    s = c.csv("schedule_savings.csv")
    s = s[(s.job == "preemptible") & (s.k == 8)].set_index("ba")
    fig = go.Figure()
    for col, name, colr in (("random", "Random hours", c.AMBER), ("persist", "Simple guess: same as yesterday", c.G500),
                            ("resid_lags", "Machine learning (LightGBM)", c.G900),
                            ("oracle", "Perfect foresight", c.G200)):
        fig.add_bar(x=[c.BA_NAMES[i] for i in s.index], y=s[col], name=name, marker_color=colr,
                    hovertemplate="%{x}: %{y:.1f}% saved<extra></extra>")
    fig.update_layout(barmode="group", yaxis_title="% carbon saved vs midnight start")
    st.plotly_chart(c.style(fig, 340), width="stretch")
    c.source("results/schedule_savings.csv (8-hour flexible job, 2025)")
with b:
    st.write("")
    st.write("")
    m = c.csv("forecast_v2_metrics.csv")
    m = m[(m.horizon_h == 24) & m.model.isin(["persist", "resid_lags"])].pivot(index="ba", columns="model", values="MAE")
    m["gain"] = 100 * (1 - m.resid_lags / m.persist)
    st.markdown(
        f"Arizona's solar cycle repeats so reliably that the simple guess captures almost all the scheduling benefit. "
        f"A day ahead, machine learning cuts forecast error by only "
        f"<b>{m.gain.min():.0f}% to {m.gain.max():.0f}%</b> {c.badge('solid', 'Tested on two held-out years')}.",
        unsafe_allow_html=True)
    st.dataframe(m.rename(index=c.BA_NAMES).rename(columns={"persist": "Simple guess error", "resid_lags": "ML error",
                                                           "gain": "ML gain %"}).round(1),
                 width="stretch")
    c.source("results/forecast_v2_metrics.csv (MAE, kg/MWh, 24 hours ahead)")
    cf = c.csv("forecast_conformal.csv")
    cf = cf[(cf.model == "LightGBM") & (cf.horizon_h == 24) & (cf.level == 0.9)].set_index("ba")
    st.markdown("**How wide is a day-ahead forecast's 90% range?**")
    st.dataframe(pd.DataFrame({"Range width (kg/MWh)": cf.mean_width.round(0),
                               "Share of 2025 hours inside": (cf.coverage * 100).round(0).astype(int).astype(str) + "%"})
                 .rename(index=c.BA_NAMES), width="stretch")
    c.source("results/forecast_conformal.csv (conformal intervals, LightGBM, 24 hours ahead)")

st.divider()
st.subheader("Is the grid getting cleaner?")
y1, y2 = st.columns([1.4, 1])
with y1:
    fig = go.Figure()
    for b, g in yr.groupby("respondent"):
        fig.add_scatter(x=g.year, y=g[acct], name=c.BA_NAMES[b], mode="lines+markers",
                        line=dict(color=c.BA_COLORS[b], width=3), marker=dict(size=8),
                        hovertemplate=f"{c.BA_NAMES[b]} %{{x}}: %{{y:,.0f}} kg/MWh<extra></extra>")
    fig.update_layout(xaxis=dict(title="year", dtick=1), yaxis_title="average kg CO2 per MWh")
    st.plotly_chart(c.style(fig, 340), width="stretch")
    c.source("data/processed/carbon_intensity.parquet / consumption_ci.parquet (yearly averages)")
with y2:
    imp = c.import_share()
    st.markdown("**How much of each region's power is imported?**")
    for b in ["AZPS", "SRP", "TEPC", "WALC"]:
        st.progress(float(min(imp[b], 1.0)), text=f"{c.BA_LONG[b]}: {imp[b]:.0%} imported")
    c.source("data/processed/consumption_ci.parquet (imports / total supply, 2021 to 2025)")
    st.markdown(f"The more a region imports, the more its 'clean' or 'dirty' label depends on its neighbors. "
                f"That is why the two accountings differ {c.badge('dep', 'Import-adjusted data is new')}.",
                unsafe_allow_html=True)
st.markdown(f"**Reading it.** APS and TEP have cut their carbon intensity sharply since 2021 as solar grew and coal "
            f"retired, while SRP and WALC stayed roughly flat. The dirtiest-to-cleanest gap went from "
            f"**{gap0:.1f}x** to **{gap1:.1f}x**. A data center lasts 20 years or more, so siting on today's gap "
            f"overstates the long-run benefit.")

st.divider()
st.subheader("When are the clean hours, through the year?")
hm_ba = st.selectbox("Region for the heatmap", list(c.BA_LONG), format_func=c.BA_LONG.get, key="hm_ba")
hm = c.heatmap(hm_ba, acct)
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
fig = go.Figure(go.Heatmap(z=hm.values, x=hm.columns, y=[months[m - 1] for m in hm.index],
                           colorscale=[[0, c.G500], [0.5, "#F1F3E8"], [1, c.CARBON]],
                           colorbar=dict(title="kg/MWh"),
                           hovertemplate="%{y}, %{x}:00: %{z:,.0f} kg/MWh<extra></extra>"))
fig.update_layout(xaxis=dict(title="hour of day (Arizona time)", dtick=2), yaxis=dict(autorange="reversed"))
st.plotly_chart(c.style(fig, 420), width="stretch")
c.source("data/processed/carbon_intensity.parquet / consumption_ci.parquet, 2021 to 2025 averages")
c.how_to_read("Each square is the average carbon intensity for one hour of the day in one month. Green is cleaner, "
              "brown is dirtier. Spring middays are usually the cleanest; summer evenings, when air conditioning "
              "peaks after sunset, are usually the dirtiest. A scheduler should follow the green, which moves by season.")

st.divider()
st.subheader("Does scheduling still save carbon if you count it differently?")
st.markdown("The savings above use each hour's **average** carbon intensity. The team re-scored the same simple "
            "schedule four ways. Each bar is the % of carbon saved versus random hours for an 8-hour job in 2025.")
cs = c.csv("consumption_scheduling.csv").set_index(["decision", "evaluated_on"])
me = c.csv("measured_emissions_scheduling.csv")
me = me[(me.variant == "as_specified") & (me.year == 2025)].set_index("ba")
mf = c.csv("mef_scheduling.csv")
mf = mf[(mf.block_h == 6) & (mf.evaluated_on == "mef_eval") & (mf.decision == "avg_persist")].iloc[0]
bas = ["AZPS", "SRP", "TEPC", "WALC"]
acc = pd.DataFrame({
    "Average, local plants (headline)": [cs.loc[("decide_prod", "eval_prod"), b] for b in bas],
    "Average, counting imports": [cs.loc[("decide_cons", "eval_cons"), b] for b in bas],
    "Measured plant CO2 (EPA)": [me.loc[b, "save_decide_est_eval_alt"] for b in bas],
    "Marginal estimate": [mf[b] for b in bas],
}, index=[c.BA_NAMES[b] for b in bas])
fig = go.Figure()
for col, colr in zip(acc.columns, [c.G900, c.G500, "#B08968", c.AMBER]):
    fig.add_bar(x=acc.index, y=acc[col], name=col, marker_color=colr,
                hovertemplate="%{x}: %{y:.1f}% saved<extra>" + col + "</extra>")
fig.add_hline(y=0, line_color=c.NEUTRAL)
fig.update_layout(barmode="group", yaxis_title="% carbon saved vs random hours")
st.plotly_chart(c.style(fig, 380), width="stretch")
c.source("results/consumption_scheduling.csv, measured_emissions_scheduling.csv (2025), mef_scheduling.csv "
         "(6-hour blocks, decided on yesterday's average intensity)")
st.markdown(
    f"**Reading it.** Counting imports barely changes the saving on APS, SRP and TEP. Measured plant emissions keep it "
    f"on SRP and WALC but cut it on TEP and APS, so quote those two as a range {c.badge('dep', 'Measured CO2 check')}. "
    f"Under a **marginal** estimate the saving shrinks and can flip sign (WALC), and APS's 2025 value is "
    f"ill-conditioned {c.badge('approx', 'No ground truth exists for marginal emissions')}. The team's conclusion: "
    f"report scheduling savings as average-intensity savings, and treat the marginal share as unstable.",
    unsafe_allow_html=True)

st.subheader("Which plants respond when demand rises?")
m1, m2 = st.columns([1.2, 1])
with m1:
    season = st.radio("Season", ["other", "summer"], horizontal=True, key="mef_season",
                      format_func=lambda x: {"other": "Oct to May", "summer": "Jun to Sep"}[x])
    mb = c.csv("mef_by_hour.csv")
    mb = mb[(mb.block_h == 6) & (mb.season == season)]
    hc = c.carbon_hourly()
    hc = hc.assign(month=(hc.ts - pd.Timedelta(hours=7)).dt.month)
    hc = hc[hc.month.between(6, 9)] if season == "summer" else hc[~hc.month.between(6, 9)]
    avg6 = hc.assign(block=hc.hour // 6 * 6).groupby(["respondent", "block"]).produced.mean()
    labels = {0: "0-6h", 6: "6-12h", 12: "12-18h", 18: "18-24h"}
    fig = go.Figure()
    for b in bas:
        g = mb[mb.ba == b]
        fig.add_bar(x=[f"{c.BA_NAMES[b]}<br>{labels[h]}" for h in g.hour], y=g.mef_kg_mwh, name=c.BA_NAMES[b],
                    marker_color=c.BA_COLORS[b],
                    error_y=dict(type="data", symmetric=False, array=g.hi - g.mef_kg_mwh,
                                 arrayminus=g.mef_kg_mwh - g.lo, color="#9AA79F"),
                    hovertemplate="%{x}: marginal %{y:,.0f} kg/MWh<extra></extra>")
        fig.add_scatter(x=[f"{c.BA_NAMES[b]}<br>{labels[h]}" for h in g.hour],
                        y=[avg6.get((b, h), np.nan) for h in g.hour], mode="markers", showlegend=b == "AZPS",
                        name="Average intensity", marker=dict(symbol="line-ew-open", size=22, color=c.CARBON,
                                                               line=dict(width=3)),
                        hovertemplate="%{x}: average %{y:,.0f} kg/MWh<extra></extra>")
    fig.update_layout(yaxis_title="kg CO2 per MWh", xaxis_tickfont_size=10)
    st.plotly_chart(c.style(fig, 400), width="stretch")
    c.source("results/mef_by_hour.csv (6-hour blocks, 2021-2024, 95% intervals); average from carbon_intensity.parquet")
with m2:
    fu = c.csv("mef_marginal_fuel.csv")
    fu = fu[fu.season == season].set_index("ba")
    fig = go.Figure()
    for fuel, name, colr in (("NG", "Gas", c.CARBON), ("COL", "Coal", "#3E3A35"), ("WAT", "Hydro", c.WATER),
                             ("SUN", "Solar", c.G500), ("WND", "Wind", c.G200), ("OTH", "Other", c.NEUTRAL)):
        fig.add_bar(x=[c.BA_NAMES[b] for b in fu.index], y=fu[fuel].fillna(0), name=name, marker_color=colr,
                    hovertemplate=f"{name}: %{{y:.2f}} MWh per MWh of demand change<extra></extra>")
    fig.update_layout(barmode="relative", yaxis_title="MWh of fuel per MWh of extra demand")
    st.plotly_chart(c.style(fig, 400), width="stretch")
    c.source("results/mef_marginal_fuel.csv (2021-2024)")
st.markdown(
    "**Reading it.** Bars are the estimated marginal rate (the plants that ramp when demand rises); the brown dash is "
    "the average rate in the same hours. Gas does most of the ramping in APS, SRP and TEP; WALC leans on hydro in "
    "summer. The rest of a demand change is met by imports, which these in-region estimates cannot see, so the "
    f"marginal numbers describe local plants, not the whole grid {c.badge('approx', 'Association, not a causal effect')}.",
    unsafe_allow_html=True)
