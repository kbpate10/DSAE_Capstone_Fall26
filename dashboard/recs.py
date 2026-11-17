"""Recommendations built from the team's results. Every evidence number is computed from the result files at
load time, so the recommendations stay in step with the analysis."""
import numpy as np
import pandas as pd
import streamlit as st

import core as c

TOPICS = ["Grid", "Carbon", "Water", "Siting"]
PAGES = {"Grid": "views/grid.py", "Carbon": "views/carbon.py", "Water": "views/water.py",
         "Siting": "views/siting.py", "What-if": "views/whatif.py"}


@st.cache_data
def evidence() -> dict:
    e = {}
    u = c.utility_load_2024()
    u["h"] = c.headroom_mw(u.ci_mwh, 0.25)
    e["headroom"] = u.h.sum()
    e["pipeline"] = c.ACC_UNDER_CONSTRUCTION_MW + c.ACC_PLANNED_MW
    e["hosts_500"] = [n.replace(" Co", "") for n in u[u.h >= 500].util_name]
    r3 = c.csv("rq3_results.csv")
    r = r3[(r3.outcome == "ln_saidi_nomed") & r3.spec.str.startswith("S2")].iloc[0]
    e["rq3_hi"] = 100 * (np.exp(r.d_ln_ci_pc_hi * np.log(1.1)) - 1)
    sw = c.csv("framework_stage1_sweep.csv")
    e["sites_100"] = int(sw[(sw.P_MW == 100) & (sw.tau_R == 100)].n_sites.iloc[0])
    e["sites_500"] = int(sw[(sw.P_MW == 500) & (sw.tau_R == 100)].n_sites.iloc[0])
    e["tep_at_100"] = "TUCSON" in sw[(sw.P_MW == 100) & (sw.tau_R == 100)].sites.iloc[0].upper()
    ci = c.carbon_by_ba()["consumed"]
    E = c.campus_mwh(500)
    e["loc_kt"] = E * (ci.max() - ci.min()) / 1e6
    e["sched_kt"] = E * ci.max() / 1e6 * 0.10 * c.sched_saving()[ci.idxmax()]
    m = c.csv("forecast_v2_metrics.csv")
    m = m[(m.horizon_h == 24) & m.model.isin(["persist", "resid_lags"])].pivot(index="ba", columns="model", values="MAE")
    e["ml_gain_max"] = float((100 * (1 - m.resid_lags / m.persist)).max())
    s = c.csv("schedule_savings.csv")
    s = s[(s.job == "preemptible") & (s.k == 8)][["persist", "resid_lags"]].mean()
    e["sched_simple"], e["sched_ml"] = s.persist, s.resid_lags
    y = c.carbon_by_year().pivot(index="year", columns="respondent", values="produced")
    e["aps_drop"] = 100 * (1 - y.loc[y.index.max(), "AZPS"] / y.loc[2021, "AZPS"])
    e["tep_drop"] = 100 * (1 - y.loc[y.index.max(), "TEPC"] / y.loc[2021, "TEPC"])
    ws = c.csv("water_scarcity.csv")
    ws = ws[ws.case.str.startswith("A")].set_index("scope")
    e["srp_co_water"], e["tep_co_water"] = ws.loc["SRP", "carbonOnly_water"], ws.loc["TEPC", "carbonOnly_water"]
    e["srp_bal_water"], e["tep_bal_water"] = ws.loc["SRP", "balanced_water"], ws.loc["TEPC", "balanced_water"]
    e["srp_co_carbon"], e["srp_bal_carbon"] = ws.loc["SRP", "carbonOnly_carbon"], ws.loc["SRP", "balanced_carbon"]
    fb = c.csv("water_frontier_by_ba.csv")
    fb = fb[(fb["mode"] == "persist") & (fb.job == "preemptible") & (fb.k == 8)]
    e["sched_water_lo"], e["sched_water_hi"] = fb.water_saved_vs_random_pct.min(), fb.water_saved_vs_random_pct.max()
    sc = c.csv("case_study_surcharge.csv")
    d = sc[sc.group.str.startswith("default")]
    e["fee_lo"] = d[d.evaporative_share == 1.0]["usd_million_at_0.01"].min()
    e["fee_hi"] = d[d.evaporative_share == 1.0]["usd_million_at_0.01"].max()
    e["evap_cut"] = 100 * (1 - d.evaporative_share.min() / d.evaporative_share.max())
    isc = c.csv("stage1_interconnection.csv")
    e["sub_cost"] = float(isc[(isc.node_cap == "none") & (isc.V_min_kv == 230) & (isc.D_max_km == 30)]
                          .suitability_loss_pct.iloc[0])
    st_ = c.sites()
    m_ = st_.dropna(subset=["propensity_mean"]).copy()
    green = m_.score >= m_.score.quantile(2 / 3)
    build = m_.propensity_mean >= m_.propensity_mean.quantile(0.75)
    e["targets"] = int((green & build).sum())
    e["rho"] = m_.score.rank().corr(m_.propensity_mean.rank())
    gw = st_.groupby("county_short").gw_depth_med.median()
    e["gw_maricopa"], e["gw_pinal"], e["gw_state"] = gw.get("Maricopa"), gw.get("Pinal"), st_.gw_depth_med.median()
    return e


def recommendations() -> pd.DataFrame:
    e = evidence()
    R = [
        # topic, title, who, action, evidence number, evidence text, confidence, page
        ("Grid", "Treat the tested headroom as the line for fast approvals",
         ["Regulator (ACC staff)", "Utility planner", "Lawmaker / AG office"],
         f"Approve large loads quickly up to about {e['headroom']:,.0f} MW statewide (25% of each utility's business "
         f"load). Beyond that, require phased energization and an interconnection study for each project.",
         f"{e['pipeline'] / e['headroom']:.1f}x",
         f"The pipeline ({e['pipeline']:,} MW) is {e['pipeline'] / e['headroom']:.1f} times the load the reliability "
         f"evidence covers.", "dep", "Grid"),
        ("Grid", "Screen projects by size relative to the utility, not by outage limits",
         ["Regulator (ACC staff)", "Utility planner"],
         "Use a per-utility cap on new load as the main screening rule. Outage-minute limits barely change which "
         "projects pass, because the data show no measurable outage effect.",
         f"{e['sites_500']} sites",
         f"At 500 MW only {' and '.join(e['hosts_500'])} can host a campus; the outage limit matters only between "
         f"about 60 and 100 minutes.", "dep", "What-if"),
        ("Grid", "Encourage phased projects of 100 to 250 MW",
         ["Data-center operator", "Regulator (ACC staff)", "Utility planner"],
         "Build or approve large campuses in phases. Smaller phases fit more utilities and spread the load.",
         f"{e['sites_100']} sites",
         f"At 100 MW the framework approves {e['sites_100']} sites"
         + (", including one in TEP territory" if e["tep_at_100"] else "") + f", versus {e['sites_500']} at 500 MW.",
         "dep", "What-if"),
        ("Grid", "Study household bills before deciding on a pause",
         ["Lawmaker / AG office", "Resident / ratepayer advocate", "Regulator (ACC staff)"],
         "Commission an analysis of residential rates against large-load growth. Outage data show no harm so far, "
         "but outages are the wrong measure for the cost question in the public debate.",
         f"< +{e['rq3_hi']:.1f}%",
         f"Outage minutes rise by at most about {e['rq3_hi']:.1f}% per 10% load growth; bills are not yet analyzed.",
         "solid", "Grid"),
        ("Carbon", "Make the grid region the main carbon condition",
         ["Regulator (ACC staff)", "Lawmaker / AG office", "Data-center operator"],
         "Ask applicants for annual emissions in the grid region they will join, and weigh location ahead of "
         "promises to shift workloads in time.",
         f"{e['loc_kt'] / e['sched_kt']:.0f}x",
         f"For a 500 MW campus, the cleanest region saves about {e['loc_kt']:,.0f} kt CO2 a year versus the dirtiest; "
         f"scheduling 10% of its work saves about {e['sched_kt']:,.0f} kt.", "dep", "Carbon"),
        ("Carbon", "Schedule with a simple same-hour-yesterday rule",
         ["Data-center operator"],
         "Run flexible jobs in the hours that were cleanest the day before. A machine-learning forecast adds almost "
         "nothing in Arizona.",
         f"{e['sched_simple']:.0f}% vs {e['sched_ml']:.0f}%",
         f"The simple rule saves about {e['sched_simple']:.0f}% of carbon on an 8-hour job; machine learning, "
         f"{e['sched_ml']:.1f}%. Day-ahead forecast error improves by at most {e['ml_gain_max']:.0f}%.",
         "solid", "Carbon"),
        ("Carbon", "Require carbon claims to state their accounting",
         ["Regulator (ACC staff)", "Lawmaker / AG office"],
         "Accept scheduling-based carbon claims only when they state the method (average, imports counted, "
         "measured or marginal). The saving shrinks or flips under some methods.",
         "4 methods", "The scheduling saving holds when imports are counted but shrinks on TEP and APS with measured "
         "plant data, and is unstable under marginal emissions.", "dep", "Carbon"),
        ("Carbon", "Revisit regional carbon rankings every year",
         ["Utility planner", "Regulator (ACC staff)", "Data-center operator"],
         "Update siting carbon comparisons yearly. The gap between regions is closing as coal retires.",
         f"-{e['aps_drop']:.0f}%",
         f"APS's carbon intensity fell about {e['aps_drop']:.0f}% and TEP's about {e['tep_drop']:.0f}% from 2021 to "
         f"2025 (local plants).", "solid", "Carbon"),
        ("Water", "Regulate cooling design, not schedules",
         ["Water manager", "Regulator (ACC staff)", "Lawmaker / AG office"],
         "Set water conditions on cooling technology and metered on-site use. Scheduling is a weak water lever.",
         f"{e['evap_cut']:.0f}%",
         f"Cutting the evaporative share from 100% to 25% cuts on-site water by about {e['evap_cut']:.0f}%; "
         f"scheduling changes water by {e['sched_water_lo']:+.0f}% to {e['sched_water_hi']:+.0f}% depending on region.",
         "approx", "Water"),
        ("Water", "Use balanced carbon-water schedules in SRP and TEP territory",
         ["Data-center operator", "Water manager"],
         "Do not schedule for carbon alone where clean hours are the hottest hours; a balanced weighting avoids the "
         "extra water use.",
         f"{e['srp_co_water']:+.1f}%",
         f"A carbon-only schedule changes water by {e['srp_co_water']:+.1f}% (SRP) and {e['tep_co_water']:+.1f}% (TEP); "
         f"a balanced one, {e['srp_bal_water']:+.1f}% and {e['tep_bal_water']:+.1f}%, at some cost in carbon "
         f"(SRP {e['srp_co_carbon']:.0f}% to {e['srp_bal_carbon']:.0f}% saved).", "dep", "Water"),
        ("Water", "If a water fee is adopted, base it on metered on-site use",
         ["Lawmaker / AG office", "Water manager"],
         "Tie any surcharge to measured cooling water so it rewards drier cooling designs.",
         f"${e['fee_lo']:.0f} to {e['fee_hi']:.0f}M",
         f"A hypothetical $0.01 per gallon fee would cost one 500 MW campus about ${e['fee_lo']:.1f}M to "
         f"${e['fee_hi']:.1f}M a year at full evaporative cooling, about half at 50%.", "approx", "Water"),
        ("Siting", "Focus incentives on the short list that is both green and buildable",
         ["Regulator (ACC staff)", "Lawmaker / AG office", "Data-center operator"],
         "Steer development toward sites that score well environmentally and resemble places where data centers "
         "are actually built, rather than remote top-scoring sites.",
         f"{e['targets']} squares",
         f"Environmental score and buildability point in opposite directions (rank correlation {e['rho']:+.2f}); "
         f"only {e['targets']} squares are both under default settings.", "dep", "Siting"),
        ("Siting", "Require a nearby high-voltage substation",
         ["Regulator (ACC staff)", "Utility planner", "Data-center operator"],
         "Prefer sites within about 30 km of a 230 kV substation; the rule costs little and cuts grid build-out.",
         f"{e['sub_cost']:.0f}%",
         f"Requiring a 230 kV substation within 30 km gives up only about {e['sub_cost']:.0f}% of total suitability.",
         "approx", "Siting"),
        ("Siting", "Give groundwater extra weight in Phoenix and Pinal reviews",
         ["Water manager", "Regulator (ACC staff)"],
         "Where demand concentrates, add a groundwater review to approvals; these basins have deep water tables.",
         f"{e['gw_maricopa']:.0f} ft",
         f"Median groundwater depth is about {e['gw_maricopa']:.0f} ft in Maricopa and {e['gw_pinal']:.0f} ft in "
         f"Pinal squares, against {e['gw_state']:.0f} ft statewide.", "dep", "Siting"),
    ]
    df = pd.DataFrame(R, columns=["topic", "title", "who", "action", "number", "evidence", "confidence", "page"])
    df.insert(0, "id", [f"R{i}" for i in range(1, len(df) + 1)])
    return df


def for_role(df: pd.DataFrame, role: str) -> pd.DataFrame:
    return df if role == "Everyone" else df[df.who.apply(lambda w: role in w)]


def card(r):
    st.markdown(
        f'<div class="rec"><div class="rec-head"><span class="rec-id">{r.id}</span>'
        f'<span class="rec-topic">{r.topic}</span>{c.badge(r.confidence)}</div>'
        f'<div class="rec-title">{r.title}</div>'
        f'<div class="rec-body"><div class="rec-num">{r.number}</div><div>'
        f'<p class="rec-action">{r.action}</p><p class="rec-evidence"><b>Evidence:</b> {r.evidence}</p>'
        f'<p class="rec-who">For: {", ".join(r.who)}</p></div></div></div>', unsafe_allow_html=True)


def callout(topic: str):
    """Short 'what to do' box at the bottom of a question page."""
    df = for_role(recommendations(), c.role())
    df = df[df.topic == topic]
    if df.empty:
        df = recommendations()[lambda d: d.topic == topic]
    items = "".join(f"<li><b>{r.id}. {r.title}.</b> {r.action}</li>" for r in df.itertuples())
    st.markdown(f'<div class="todo"><span class="who">What to do</span><ul>{items}</ul></div>', unsafe_allow_html=True)
    st.page_link("views/recommend.py", label="See all recommendations and their evidence")
