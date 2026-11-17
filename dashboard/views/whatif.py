import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core as c

c.setup("Plate 05 · Decision what-if")

TAUS = [60, 80, 100, 120, 150, 200, 300]


@st.cache_data
def frontier():
    f = c.csv("stage1_frontier.csv")
    return f[f.mapping == "all"]


@st.cache_data
def sweep():
    return c.csv("framework_stage1_sweep.csv")


def parse_sites(text: str) -> pd.DataFrame:
    rows = [{"cell_id": m[0], "county": m[1], "utility": m[2]}
            for m in re.findall(r"([0-9]+_-?[0-9]+)\(([^,]+),([^)]+)\)", str(text))]
    return pd.DataFrame(rows, columns=["cell_id", "county", "utility"])


# ---------------- controls ----------------
c.plate("What happens under <em>your</em> rules?")
st.markdown("Set the rules a regulator would set, and see which sites the team's framework approves, what they would "
            "emit and use, and what happens to outage risk.")
k1, k2, k3, k4 = st.columns(4)
P = k1.select_slider("Project size (MW)", options=[100, 250, 500, 1000], value=500,
                     help="Size of each proposed data-center campus.")
tau = k2.select_slider("Reliability limit (outage minutes per year)", options=TAUS, value=100,
                       help="A site is approved only if its utility's projected outage minutes stay under this limit. "
                            "100 is roughly the US median.")
A = k3.select_slider("Load cap (share of utility business load)", options=[0.10, 0.25, 0.50], value=0.25,
                     format_func=lambda x: f"{x:.0%}",
                     help="Largest load increase allowed per utility; the reliability evidence covers about 25%.")
K = k4.select_slider("Maximum number of sites", options=[1, 3, 5, 10], value=3)

f = frontier()
row = f[(f.P_MW == P) & (f.A_max == A) & (f.tau_R == tau) & (f.K == K)]
n_sel = int(row.n_selected.iloc[0]) if len(row) else 0
mean_score = float(row.mean_score.iloc[0]) if len(row) and n_sel else np.nan
# what the same rules would allow with no reliability limit (the most lenient tau in the sweep)
loose = f[(f.P_MW == P) & (f.A_max == A) & (f.tau_R == max(TAUS)) & (f.K == K)]
n_loose = int(loose.n_selected.iloc[0]) if len(loose) else 0
g = f[(f.P_MW == P) & (f.A_max == A) & (f.K == K)].sort_values("tau_R")
binding = g[g.n_selected < n_loose].tau_R.max() if (g.n_selected < n_loose).any() else None

if n_sel == 0:
    answer = (f"<b>No site can be approved.</b> A {P:,} MW campus adds more than {A:.0%} of every Arizona utility's "
              f"business load, so it falls outside what the reliability evidence covers.")
elif binding is not None and tau <= binding:
    answer = (f"<b>{n_sel} site{'s' if n_sel != 1 else ''} approved.</b> The reliability limit is what holds this back: "
              f"loosening it past {binding} minutes would allow {n_loose}.")
else:
    answer = (f"<b>{n_sel} site{'s' if n_sel != 1 else ''} approved.</b> Here the reliability limit is not the "
              f"constraint; utility size is. Only utilities large enough to absorb a {P:,} MW campus under the "
              f"{A:.0%} cap can host one.")
st.markdown(f'<div class="answer">{answer}</div>', unsafe_allow_html=True)

c.for_you({
    "Everyone": "Move the sliders to see how much each rule matters. For most settings, project size relative to "
                "the utility decides more than the outage limit does.",
    "Regulator (ACC staff)": "The outage limit only bites between about 60 and 100 minutes; above that, the load cap "
                             "and utility size decide. A cap is the stronger lever, and its 25% default reflects the "
                             "limit of the reliability evidence, not an engineering rating.",
    "Lawmaker / AG office": "Rules framed as outage limits approve almost the same sites as no limit at all, because "
                            "historical data show no measurable outage effect. Size caps per utility change the "
                            "outcome much more.",
    "Utility planner": "The table shows each approved site's serving utility, today's outage minutes, and the worst "
                       "case after the project, using the upper end of the team's reliability estimate.",
    "Data-center operator": "Large single campuses fit only in APS and SRP territory. Splitting a project into 100 MW "
                            "phases opens more sites, including TEP territory.",
    "Water manager": "Adding a water weight to siting (bottom of the page) saves a few percent of water at a small "
                     "cost in suitability; it changes the site choice more than carbon does.",
    "Resident / ratepayer advocate": "Even the worst case adds only a few outage minutes a year for existing customers "
                                     "at the approved sites, according to the evidence the team has.",
})

m1, m2, m3, m4 = st.columns(4)
c.kpi(m1, "Sites approved", f"{n_sel} of {K}", f"{P:,} MW each, {tau} min limit, {A:.0%} cap", "dep",
      "Assumed inputs: suitability weights, cap, load factor")
c.kpi(m2, "Average environmental score", "n/a" if np.isnan(mean_score) else f"{mean_score:.2f}",
      "0 to 1, higher is better", "dep", "Team-chosen siting weights")
c.kpi(m3, "Total new load approved", f"{n_sel * P:,} MW", "vs 5,300+ MW in the ACC pipeline", "dep",
      "Pipeline: ACC workshop, April 2026")
c.kpi(m4, "Allowed with no outage limit", f"{n_loose} site{'s' if n_loose != 1 else ''}",
      "same size, cap and budget", "dep", "Most lenient limit in the team's sweep (300 min)")
st.write("")

# ---------------- which sites ----------------
st.subheader("Which sites, and what they mean")
sw = sweep()
srow = sw[(sw.P_MW == P) & (sw.tau_R == tau)]
detail_ok = (K == 3) and (A == 0.25) and len(srow) and P in (100, 250, 500)
if not detail_ok:
    st.info("Site-by-site detail exists for the team's default rules: at most 3 sites and a 25% cap, for 100, 250 "
            "or 500 MW projects. Set those to see which sites are approved; the counts above work for every setting.")
else:
    srow = srow.iloc[0]
    sites = parse_sites(srow.sites)
    sc = c.csv("rq2_scores.csv").set_index("cell_id")
    fp = c.csv("stage2_cell_footprint.csv").set_index("cell_id")
    rb = c.csv("case_study_reliability_bound.csv")
    rb = rb[rb.P_MW == P]
    rb = rb.set_index(rb.util_name.str.upper())
    scale = P / 500
    rows = []
    for _, s in sites.iterrows():
        u = s.utility.upper()
        rows.append({
            "Site": f"{s.county} County",
            "Utility": s.utility.title().replace(" Co", ""),
            "Environmental rank (of 192)": int(sc.loc[s.cell_id, "rank"]),
            "Carbon (kt CO2/yr)": fp.loc[s.cell_id, "carbon_kt"] * scale if s.cell_id in fp.index else np.nan,
            "Water (million m3/yr)": fp.loc[s.cell_id, "water_Mm3"] * scale if s.cell_id in fp.index else np.nan,
            "Outage minutes today": rb.loc[u, "baseline_saidi_min"] if u in rb.index else np.nan,
            "Worst case after (min)": rb.loc[u, "projected_saidi_min_upper_bound"] if u in rb.index else np.nan,
            "lat": sc.loc[s.cell_id, "lat"], "lon": sc.loc[s.cell_id, "lon"],
        })
    T = pd.DataFrame(rows)
    left, right = st.columns([1.35, 1])
    with left:
        c.table(T.drop(columns=["lat", "lon"]), "whatif_approved_sites",
                column_config={"Carbon (kt CO2/yr)": st.column_config.NumberColumn(format="%,.0f"),
                               "Water (million m3/yr)": st.column_config.NumberColumn(format="%.1f"),
                               "Outage minutes today": st.column_config.NumberColumn(format="%.0f"),
                               "Worst case after (min)": st.column_config.NumberColumn(format="%.1f")})
        c.source("results/framework_stage1_sweep.csv (sites), stage2_cell_footprint.csv (carbon by local plants, and water, scaled "
                 "from 500 MW), case_study_reliability_bound.csv (outage minutes)")
        st.markdown(
            f"**Totals:** about **{T['Carbon (kt CO2/yr)'].sum():,.0f} kt CO2** and "
            f"**{T['Water (million m3/yr)'].sum():.1f} million m3 of water** a year. With a balanced carbon-water "
            f"schedule, these sites save about **{srow.balanced_carbon_saved_pct_mean:.0f}% carbon** and "
            f"**{srow.balanced_water_saved_pct_mean:+.1f}% water** on average "
            f"{c.badge('dep', 'Average emissions, modeled water, 30% of work flexible')}.", unsafe_allow_html=True)
    with right:
        allc = c.csv("rq2_scores.csv")
        fig = go.Figure()
        fig.add_trace(go.Scattermap(lat=allc.lat, lon=allc.lon, mode="markers", name="Candidate squares",
                                    marker=dict(size=7, color=c.G200, opacity=0.7), hoverinfo="skip"))
        fig.add_trace(go.Scattermap(lat=T.lat, lon=T.lon, mode="markers+text", name="Approved sites",
                                    marker=dict(size=18, color=c.G900), text=T.Site, textposition="top right",
                                    hovertemplate="%{text}<extra></extra>"))
        fig.update_layout(map=dict(style="carto-positron", center=dict(lat=34.0, lon=-111.6), zoom=5.2),
                          margin=dict(l=0, r=0, t=0, b=0), height=380, showlegend=False)
        st.plotly_chart(fig, width="stretch")

# ---------------- how the answer moves ----------------
st.subheader("How the answer moves as you change the rules")
fig = go.Figure()
for p_, colr in zip([100, 250, 500, 1000], [c.G200, c.G500, c.G900, c.CARBON]):
    gg = f[(f.P_MW == p_) & (f.A_max == A) & (f.K == K)].sort_values("tau_R")
    fig.add_scatter(x=gg.tau_R, y=gg.n_selected, mode="lines+markers", name=f"{p_:,} MW",
                    line=dict(color=colr, width=3 if p_ == P else 1.5), marker=dict(size=7),
                    hovertemplate=f"{p_:,} MW, %{{x}} min: %{{y}} sites<extra></extra>")
fig.add_scatter(x=[tau], y=[n_sel], mode="markers", name="Your rules",
                marker=dict(size=18, color="rgba(0,0,0,0)", line=dict(color=c.RED, width=3)), hoverinfo="skip")
fig.update_layout(xaxis_title="reliability limit (outage minutes per year)",
                  yaxis=dict(title="sites approved", dtick=1, rangemode="tozero"))
st.plotly_chart(c.style(fig, 360), width="stretch")
c.source(f"results/stage1_frontier.csv (load cap {A:.0%}, up to {K} sites)")
st.markdown(
    "**Reading it.** Each line is one project size. Lines go flat once the outage limit stops mattering; from there, "
    "only the load cap and utility size decide. Bigger projects flatten lower because fewer utilities can absorb them, "
    f"and at 1,000 MW no Arizona utility can under a 25% cap {c.badge('dep', 'Cap reflects the evidence, not engineering')}.",
    unsafe_allow_html=True)

# ---------------- coupling ----------------
st.divider()
st.subheader("What if siting also counted carbon and water?")
st.caption("The team's Stage 2 coupling, for the default 500 MW scenario: the site score is blended with each site's "
           "yearly carbon and water footprint.")
j1, j2, j3 = st.columns(3)
fpt = j1.radio("Footprint to add", ["both", "water", "carbon"], horizontal=True,
               format_func=lambda x: {"both": "Carbon and water", "water": "Water only", "carbon": "Carbon only"}[x])
w = j2.select_slider("Weight on footprint", options=[0.0, 0.1, 0.25, 0.5, 0.75, 1.0], value=0.5,
                     format_func=lambda x: f"{x:.0%}")
acct = j3.radio("Carbon accounting", ["consumption", "production"], horizontal=True,
                format_func=lambda x: {"consumption": "Counting imports", "production": "Local plants"}[x])
cp = c.csv("stage2_coupling_consumption.csv" if acct == "consumption" else "stage2_coupling.csv")
cp = cp[cp.footprint == fpt].set_index("w")
base, cur = cp.loc[0.0], cp.loc[w]
q1, q2, q3, q4 = st.columns(4)
c.kpi(q1, "Same sites as without footprint", f"{cur.jaccard_vs_stage1:.0%}", "overlap with the Stage 1 choice", "dep",
      "Weight is a policy choice")
c.kpi(q2, "Suitability given up", f"{100 * (1 - cur.sum_score / base.sum_score):.1f}%", "of the environmental score",
      "dep", "Team-chosen siting weights")
c.kpi(q3, "Carbon change", f"{100 * (cur.sum_carbon_kt / base.sum_carbon_kt - 1):+.1f}%",
      f"{cur.sum_carbon_kt:,.0f} kt CO2/yr", "dep", "Average emissions")
c.kpi(q4, "Water change", f"{100 * (cur.sum_water_Mm3 / base.sum_water_Mm3 - 1):+.1f}%",
      f"{cur.sum_water_Mm3:.1f} million m3/yr", "dep", "Modeled water")
st.write("")
picked = ", ".join(f"{cty} ({ba})" for _, ba, cty in re.findall(r"([0-9]+_-?[0-9]+)\(([A-Z]+),([^)]+)\)", cur.cells))
st.markdown(
    f"**Sites chosen:** {picked}. **Reading it.** Carbon stays the same at almost every weight, because the utility caps already "
    f"force one APS site and one SRP site and carbon is set by the grid region, not the exact square. Water moves a "
    f"few percent, because cooling water depends on each site's local heat {c.badge('dep', 'Scenario estimates')}.",
    unsafe_allow_html=True)
c.source(f"results/{'stage2_coupling_consumption.csv' if acct == 'consumption' else 'stage2_coupling.csv'}")
st.caption("This page shows the team's framework run on assumed inputs (load factor 0.8, PUE 1.2, team-chosen siting "
           "weights). It shows how the rules change the outcome; it is not a siting recommendation.")
