import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import core as c
import recs

c.setup("Plate 04 · Siting")

sb = st.sidebar
sb.markdown("**Environmental weights**")
w = {k: sb.slider(lbl, 0.0, 1.0, wt, 0.05) for k, (_, wt, lbl) in c.CRIT.items()}
queue = sb.radio("A long power-plant queue in the county is...", ["a bad sign (grid strain)",
                                                                  "a good sign (more supply coming)"])
sb.markdown("**Thresholds**")
g_top = sb.slider("'Green' = top share of environmental score", 0.10, 0.50, 0.33, 0.01, format="%.2f")
b_top = sb.slider("'Buildable' = top share of buildability", 0.10, 0.50, 0.25, 0.01, format="%.2f")

d = c.sites().copy()
d["score_live"] = c.suitability(d, w, queue_sign=-1 if queue.startswith("a bad") else +1)
d["rank_live"] = d.score_live.rank(ascending=False, method="first").astype(int)
m = d.dropna(subset=["propensity_mean"]).copy()
m["green"] = m.score_live >= m.score_live.quantile(1 - g_top)
m["buildable"] = m.propensity_mean >= m.propensity_mean.quantile(1 - b_top)
QUAD = {(True, True): "Target: green and buildable", (False, True): "Where industry goes",
        (True, False): "Green but remote", (False, False): "Neither"}
QCOL = {"Target: green and buildable": c.G700, "Where industry goes": c.CARBON,
        "Green but remote": c.G200, "Neither": "#E3E7E4"}
m["quadrant"] = [QUAD[(g, b)] for g, b in zip(m.green, m.buildable)]
d = d.merge(m[["cell_id", "quadrant"]], on="cell_id", how="left")
d["quadrant"] = d.quadrant.fillna("Neither")
targets = m[m.quadrant.str.startswith("Target")].sort_values("score_live", ascending=False)
rho = m.score_live.rank().corr(m.propensity_mean.rank())

c.header("Where are sites both environmentally sound <em>and</em> buildable?",
         f"Green sites and buildable sites point in opposite directions (rank correlation <b>{rho:+.2f}</b>). "
         f"The best environmental squares are remote; real data centers cluster near people and substations. "
         f"Only <b>{len(targets)}</b> of {len(m)} squares are both, under the current settings.")

k1, k2, k3 = st.columns(3)
c.kpi(k1, "Green vs buildable link", f"{rho:+.2f}", "rank correlation across squares", "dep", "Weights are team choices")
c.kpi(k2, "Target squares (both)", f"{len(targets)}", f"top {g_top:.0%} green and top {b_top:.0%} buildable", "dep",
      "Depends on weights and thresholds")
c.kpi(k3, "Existing data centers", f"{int(d.hosts.fillna(0).sum())}", "mapped in OpenStreetMap", "approx",
      "OpenStreetMap is incomplete")
st.write("")
c.for_you({
    "Everyone": "There is no site that wins on everything. The map shows the tradeoff; the shortlist and the "
                "head-to-head comparison at the bottom turn it into concrete places.",
    "Regulator (ACC staff)": "Use the head-to-head at the bottom to compare two applications on carbon, grid fit, "
                             "water and buildability side by side. The rank ranges show how much a site's standing "
                             "depends on the weights you choose.",
    "Lawmaker / AG office": "Incentives that reward green sites would push projects away from where the industry "
                            "currently builds. The shortlist shows the few places where both goals line up.",
    "Utility planner": "Buildability tracks population and substations, so demand will keep clustering where your "
                       "network is already dense. Target squares outside metros may need new transmission.",
    "Data-center operator": "Target squares are buildable and environmentally sound under the current settings. "
                            "Adjust the weights to your own priorities and check whether a site stays on the list.",
    "Water manager": "Raise the groundwater weight in the sidebar to see where water-stressed basins drop out. "
                     "Deep groundwater around Phoenix and Pinal is the main reason metro squares score low.",
    "Resident / ratepayer advocate": "Data centers cluster near where people already live, in the Phoenix area. "
                                     "The map shows which neighborhoods' squares host them today.",
})


@st.cache_data
def squares(ids):
    feats = []
    for cid in ids:
        ci_, cj_ = (int(x) for x in cid.split("_"))
        la, lo = ci_ / 4, cj_ / 4
        ring = [[lo, la], [lo + .25, la], [lo + .25, la + .25], [lo, la + .25], [lo, la]]
        feats.append({"type": "Feature", "id": cid, "properties": {"id": cid},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}


layer = st.radio("Map layer", ["Quadrant", "Environmental score", "Buildability", "Distance to 230 kV substation"],
                 horizontal=True)
ic = c.csv("stage1_cell_interconnection.csv")[["cell_id", "d115_km", "d230_km", "d345_km"]]
d = d.merge(ic, on="cell_id", how="left")
gj = squares(tuple(d.cell_id))
hover = {"county_short": True, "rank_live": True, "quadrant": True, "cell_id": False}
if layer == "Environmental score":
    fig = px.choropleth_map(d, geojson=gj, locations="cell_id", color="score_live", hover_data=hover,
                            color_continuous_scale=["#F1F8F3", c.G500, c.G900], opacity=0.8)
elif layer == "Buildability":
    d["build_log"] = np.log10(d.propensity_mean.clip(lower=1e-6))
    fig = px.choropleth_map(d, geojson=gj, locations="cell_id", color="build_log", hover_data=hover,
                            color_continuous_scale=["#F3EDE2", "#C9A27E", c.CARBON], opacity=0.8)
    fig.update_coloraxes(colorbar_title="buildability (log)")
elif layer == "Distance to 230 kV substation":
    fig = px.choropleth_map(d, geojson=gj, locations="cell_id", color="d230_km", hover_data=hover,
                            color_continuous_scale=[c.G900, c.G500, "#F3EDE2"], range_color=(0, 100), opacity=0.8)
    fig.update_coloraxes(colorbar_title="km to 230 kV")
else:
    fig = px.choropleth_map(d, geojson=gj, locations="cell_id", color="quadrant", hover_data=hover,
                            color_discrete_map=QCOL, opacity=0.85,
                            category_orders={"quadrant": list(QCOL)})
h = d[d.hosts.fillna(0) > 0]
fig.add_trace(go.Scattermap(lat=h.lat, lon=h.lon, mode="markers", name="Existing data centers",
                            marker=dict(size=8 + 3 * h.hosts, color=c.RED, opacity=0.85),
                            text=[f"{int(n)} mapped data center(s)" for n in h.hosts], hoverinfo="text"))
fig.update_layout(map=dict(style="carto-positron", center=dict(lat=34.2, lon=-111.7), zoom=5.3),
                  margin=dict(l=0, r=0, t=10, b=0), height=560, legend=dict(orientation="h", y=1.02, title=None))

left, right = st.columns([1.35, 1])
with left:
    st.plotly_chart(fig, width="stretch")
    c.source("results/rq2_scores.csv (192 squares about 25 km wide), results/revealed_cell_propensity.csv")
with right:
    fig2 = go.Figure()
    for q, g in m.groupby("quadrant"):
        fig2.add_scatter(x=g.score_live, y=g.propensity_mean.clip(lower=1e-6), mode="markers", name=q,
                         marker=dict(color=QCOL[q], size=9, line=dict(color="#9AA79F", width=0.5)),
                         text=g.county_short, hovertemplate="%{text}: score %{x:.2f}<extra>" + q + "</extra>")
    hh = m[m.hosts > 0]
    fig2.add_scatter(x=hh.score_live, y=hh.propensity_mean, mode="markers", name="Has a data center",
                     marker=dict(size=14, color="rgba(0,0,0,0)", line=dict(color=c.RED, width=2)), hoverinfo="skip")
    fig2.add_vline(x=m.score_live.quantile(1 - g_top), line_dash="dot", line_color=c.NEUTRAL)
    fig2.add_hline(y=m.propensity_mean.quantile(1 - b_top), line_dash="dot", line_color=c.NEUTRAL)
    fig2.update_layout(xaxis_title="environmental score (higher = greener)",
                       yaxis=dict(title="buildability (log scale)", type="log"),
                       legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(c.style(fig2, 520), width="stretch")
    c.source("Buildability = how much a square resembles where data centers are actually built "
             "(population within 10 km, distance to substations).")

st.subheader(f"The shortlist: {len(targets)} target squares")
if len(targets):
    st.dataframe(targets[["county_short", "rank_live", "score_live", "propensity_mean", "gw_depth_med",
                          "wetbulb_summer_c", "q_active_mw", "rank_lo", "rank_hi"]]
                 .rename(columns={"county_short": "County", "rank_live": "Green rank (of 192)",
                                  "score_live": "Green score", "propensity_mean": "Buildability",
                                  "gw_depth_med": "Groundwater depth (ft)", "wetbulb_summer_c": "Summer wet-bulb (C)",
                                  "q_active_mw": "County queue (MW)", "rank_lo": "Best rank seen",
                                  "rank_hi": "Worst rank seen"}),
                 hide_index=True, width="stretch",
                 column_config={"Green score": st.column_config.NumberColumn(format="%.2f"),
                                "Buildability": st.column_config.NumberColumn(format="%.3f"),
                                "Summer wet-bulb (C)": st.column_config.NumberColumn(format="%.1f"),
                                "County queue (MW)": st.column_config.NumberColumn(format="%d")})
    st.caption("'Best/Worst rank seen' comes from 2,000 random weightings in the team's analysis: a wide range means "
               "the square's rank depends heavily on the weights.")
else:
    st.info("No square is both green and buildable under these settings. Loosen a threshold in the sidebar.")

st.markdown(
    f"**Reading it.** Try flipping the queue switch: Maricopa's huge power-plant queue counts against it by default, "
    f"and treating the queue as new supply instead reshuffles the map. The ranking depends on team-chosen weights "
    f"{c.badge('dep', 'Weights are assumptions')}, and buildability reflects where data centers are, not where the "
    f"grid can connect them; transmission capacity is not assessed {c.badge('approx', 'No transmission data')}.",
    unsafe_allow_html=True)

st.divider()
st.subheader("Head-to-head: compare two proposed sites")
st.caption("Your proposal's own example: two 500 MW applications, one in Pinal County and one near Flagstaff.")
names = list(c.PRESETS)
x1, x2, x3 = st.columns([1, 1, 0.8])
A = x1.selectbox("Site A", names, index=0)
B = x2.selectbox("Site B", names, index=1)
P_mw = x3.slider("Project size (MW)", 100, 1000, 500, 50, key="h2h_mw")
ci_c = c.carbon_by_ba()["consumed"]
u24 = c.utility_load_2024().set_index("util_name").ci_mwh
build_pct = m.set_index("cell_id").propensity_mean.rank(pct=True)
E = c.campus_mwh(P_mw)


fp = c.csv("stage2_cell_footprint.csv").set_index("cell_id").water_Mm3


def profile(name):
    la, lo, ba, util = c.PRESETS[name]
    cell = c.nearest_cell(la, lo)
    live = d.set_index("cell_id").loc[cell.cell_id]
    share = E / u24.get(util, np.nan)
    return {
        "Grid region / utility": f"{c.BA_NAMES[ba]} / {util.replace(' Co', '')}",
        "Campus CO2 (t per year)": E * ci_c[ba] / 1000,
        "Share of utility's business load": share,
        "Fits under a 25% cap": "Yes" if share <= 0.25 else "No",
        "Green rank (of 192, lower is better)": int(live.rank_live),
        "Buildability (percentile)": build_pct.get(cell.cell_id, np.nan),
        "Groundwater depth (ft)": cell.gw_depth_med,
        "Summer wet-bulb (C)": cell.wetbulb_summer_c,
        "Peak cooling water (L per kWh)": c.cooling_index(cell.wetbulb_summer_c),
        "Distance to a 230 kV substation (km)": live.d230_km,
        "Water, on-site + power plant (million m3/yr, 500 MW, team)": fp.get(cell.cell_id, np.nan),
        "Mapped data centers in the square": int(cell.hosts) if not np.isnan(cell.hosts) else 0,
        "_dist": cell.dist_km, "_county": cell.county_short,
    }


pa, pb = profile(A), profile(B)
LOWER = {"Campus CO2 (t per year)", "Share of utility's business load", "Green rank (of 192, lower is better)",
         "Groundwater depth (ft)", "Summer wet-bulb (C)", "Peak cooling water (L per kWh)",
         "Distance to a 230 kV substation (km)", "Water, on-site + power plant (million m3/yr, 500 MW, team)"}
HIGHER = {"Buildability (percentile)"}
FMT = {"Campus CO2 (t per year)": lambda v: f"{v:,.0f}", "Share of utility's business load": lambda v: f"{v:.0%}",
       "Buildability (percentile)": lambda v: f"{v:.0%}", "Groundwater depth (ft)": lambda v: f"{v:,.0f}",
       "Summer wet-bulb (C)": lambda v: f"{v:.1f}", "Peak cooling water (L per kWh)": lambda v: f"{v:.2f}",
       "Distance to a 230 kV substation (km)": lambda v: f"{v:.0f}",
       "Water, on-site + power plant (million m3/yr, 500 MW, team)": lambda v: "n/a" if np.isnan(v) else f"{v:.1f}"}
rows = []
for k in pa:
    if k.startswith("_"):
        continue
    a, b = pa[k], pb[k]
    better = ""
    if k in LOWER | HIGHER and a != b and not (pd.isna(a) or pd.isna(b)):
        better = A if ((a < b) == (k in LOWER)) else B
    if k == "Fits under a 25% cap" and a != b:
        better = A if a == "Yes" else B
    f_ = FMT.get(k, str)
    rows.append({"Measure": k, A: f_(a), B: f_(b), "Better": better})
cmp = pd.DataFrame(rows)
wins = cmp.Better.value_counts()
st.dataframe(cmp, hide_index=True, width="stretch",
             column_config={"Better": st.column_config.TextColumn("Better on this measure")})
st.download_button("Download comparison (CSV)", cmp.to_csv(index=False).encode(), "site_comparison.csv",
                   "text/csv", type="tertiary", icon=":material/download:")
st.markdown(
    f"**{A}** is better on **{wins.get(A, 0)}** measures and **{B}** on **{wins.get(B, 0)}**. "
    f"Sites are matched to the nearest 25 km square ({pa['_county']}, {pa['_dist']:.0f} km away; "
    f"{pb['_county']}, {pb['_dist']:.0f} km away). Utility assignments are approximate "
    f"{c.badge('approx', 'Check the actual serving utility')}. Peak cooling water uses each square's summer "
    f"wet-bulb with the project's cooling curve; the region-level water numbers elsewhere use city weather.",
    unsafe_allow_html=True)

st.divider()
st.subheader("From site to schedule: the full framework")
st.markdown("The team's two-stage framework first picks sites (Stage 1, under the grid caps), then schedules flexible "
            "work at each chosen site (Stage 2). Default scenario: 500 MW projects, up to 5 sites.")
fw = c.csv("framework_scenario_default.csv")
site_lbl = fw.county + " (" + fw.ba.map(c.BA_NAMES) + ", rank " + fw["rank"].astype(str) + ")"
fw = fw.assign(Site=site_lbl)
s1, s2 = st.columns([1.3, 1])
with s1:
    pol = fw[~fw.policy.str.startswith("naive")]
    fig = go.Figure()
    for metric, name, colr in (("carbon_saved_pct", "Carbon saved", c.CARBON), ("water_saved_pct", "Water saved", c.WATER)):
        fig.add_bar(x=[pol.Site, pol.policy.str.replace(" (balanced, not deployable)", " (not deployable)", regex=False)],
                    y=pol[metric], name=name, marker_color=colr,
                    hovertemplate="%{x}: %{y:+.1f}%<extra>" + name + "</extra>")
    fig.add_hline(y=0, line_color=c.NEUTRAL)
    fig.update_layout(barmode="group", yaxis_title="% saved vs running immediately", xaxis_tickfont_size=10)
    st.plotly_chart(c.style(fig, 400), width="stretch")
    c.source("results/framework_scenario_default.csv (30% of work flexible)")
with s2:
    base = fw[fw.policy.str.startswith("naive")]
    c.table(base[["Site", "utility", "baseline_saidi_min", "carbon_kt_yr_500MW_30pct_flexible", "water_Mm3_yr_500MW"]]
            .rename(columns={"utility": "Utility", "baseline_saidi_min": "Outage minutes today",
                             "carbon_kt_yr_500MW_30pct_flexible": "Carbon (kt/yr)",
                             "water_Mm3_yr_500MW": "Water (million m3/yr)"}), "framework_default_sites",
            column_config={"Outage minutes today": st.column_config.NumberColumn(format="%.0f"),
                           "Carbon (kt/yr)": st.column_config.NumberColumn(format="%,.0f"),
                           "Water (million m3/yr)": st.column_config.NumberColumn(format="%.1f")})
    sens = c.csv("stage2_sensitivity.csv")
    st.markdown(f"Adding carbon and water to the site choice changes water by "
                f"**{sens.water_saved_pct.min():.0f}% to {sens.water_saved_pct.max():.0f}%** across the team's "
                f"sensitivity runs and carbon by **{sens.carbon_change_pct.abs().max():.0f}%**: the grid region, "
                f"not the exact site, fixes the carbon.")
    c.source("results/stage2_sensitivity.csv")
st.markdown(
    f"**Reading it.** At the APS site, carbon-only and balanced schedules both save about 38% carbon and a little water. "
    f"At the SRP site the carbon-only schedule saves 27% carbon but uses about 10% more water; a balanced schedule "
    f"gives up 9 points of carbon to cut that penalty to about 4%. These are the Stage 1 picks under the default "
    f"assumptions, a demonstration rather than a recommendation {c.badge('dep', 'Assumed inputs: 500 MW, PUE 1.2, 25% cap')}.",
    unsafe_allow_html=True)

st.subheader("What does requiring a nearby high-voltage substation cost?")
isc = c.csv("stage1_interconnection.csv")
isc = isc[isc.node_cap == "none"]
fig = go.Figure()
for v, colr in zip(sorted(isc.V_min_kv.unique()), [c.G200, c.G500, c.G700, c.G900]):
    g = isc[isc.V_min_kv == v].sort_values("D_max_km")
    fig.add_scatter(x=g.D_max_km, y=g.suitability_loss_pct, mode="lines+markers", name=f"{v} kV or higher",
                    line=dict(color=colr, width=3),
                    hovertemplate=f"{v} kV within %{{x}} km: %{{y:.0f}}% suitability lost<extra></extra>")
fig.update_layout(xaxis_title="substation must be within (km)", yaxis_title="% of total suitability given up")
st.plotly_chart(c.style(fig, 340), width="stretch")
c.source("results/stage1_interconnection.csv (default 500 MW scenario; proximity screen, not real capacity data)")
st.markdown(
    f"**Reading it.** Requiring a 230 kV substation within 30 km costs about 7% of suitability; tighter rules cost more. "
    f"This is a proximity screen only: real interconnection capacity data are not public "
    f"{c.badge('approx', 'Proximity is not capacity')}.", unsafe_allow_html=True)

recs.callout("Siting")
