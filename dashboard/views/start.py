import streamlit as st

import core as c

c.setup("Plate 00 · Overview")
r = c.role()

# ---- live headline numbers
u = c.utility_load_2024()
headroom = c.headroom_mw(u.ci_mwh, 0.25).sum()
pipeline = c.ACC_UNDER_CONSTRUCTION_MW + c.ACC_PLANNED_MW
ci = c.carbon_by_ba()["consumed"]
E = c.campus_mwh(500)
loc_save = E * (ci.max() - ci.min()) / 1000
sched_save = E * ci.max() / 1000 * 0.10 * c.sched_saving()[ci.idxmax()]
w = c.csv("water_scarcity.csv")
w = w[(w.scope == "pooled") & w.case.str.startswith("A")].iloc[0]
s = c.sites().dropna(subset=["propensity_mean"])
rho = s.score.rank().corr(s.propensity_mean.rank())

c.header("Arizona's AI data-center boom, in <em>four questions</em>",
         "Arizona has more than 5 GW of data centers under construction or planned. This tool brings together "
         "grid, carbon, water and siting evidence so regulators, utilities, operators, water managers and "
         "residents can see the same facts, which choices matter most, and what each answer depends on.")

st.subheader("What this is about")
i1, i2 = st.columns([1.15, 1], gap="large")
with i1:
    st.markdown(
        "Arizona is in the middle of an AI data-center boom. The Arizona Corporation Commission reports about "
        "**1,300 MW of data centers under construction** and **more than 4,000 MW in planning**, arriving at the "
        "same time as declining groundwater and cuts to Colorado River supplies. Each new campus uses as much "
        "electricity as a small city, around the clock, and many cool their servers with water.\n\n"
        "Regulators, lawmakers, utilities and residents are deciding what to approve, where, and on what terms, "
        "often with little hard evidence about what these projects mean for the grid, for carbon emissions and "
        "for water. This tool puts that evidence in one place.")
with i2:
    st.markdown(
        "**What we did.** We combined 12 free public datasets: hourly electricity generation for Arizona's four "
        "grid regions (2021 to 2025), sales and outage records for every US utility (2013 to 2024), groundwater "
        "measurements from about 46,000 Arizona well sites, weather, power-plant water use, the power-plant "
        "connection queue, and the locations of existing data centers and substations. With them we answer four "
        "questions:\n"
        "1. Can Arizona's grid absorb the data centers already coming?\n"
        "2. What actually cuts a data center's carbon: where it connects, or when it runs?\n"
        "3. Does chasing clean electricity cost water?\n"
        "4. Where are sites both environmentally sound and realistically buildable?")

st.subheader("How to use it")
u1, u2, u3 = st.columns(3, gap="large")
u1.markdown("**Pick who you are.** Choose your role in the sidebar under *I am a...*. Every page then adds a short "
            "field note written for that reader, from regulators to residents.")
u2.markdown("**Read the finding, then the evidence.** Each page opens with its main finding in one sentence, followed "
            "by the charts behind it. Sliders let you change the assumptions and watch the answer move.")
u3.markdown(f"**Check how sure we are.** Numbers carry a tag: {c.badge('solid')} measured and robust, "
            f"{c.badge('dep')} changes with a stated assumption, {c.badge('approx')} a rough estimate. Every chart "
            f"names the file it comes from.", unsafe_allow_html=True)
st.caption("This is a decision aid built on public data and stated assumptions, not a siting recommendation. "
           "Water figures are scenario estimates, and the reliability analysis works at the utility level.")

st.subheader("The four answers at a glance")
st.markdown(f"**Viewing as: {r}.** Change this in the sidebar; every page adds a takeaway "
            f"written for you.")

cards = [
    ("", "Can the grid take it?", f"{pipeline/headroom:,.1f}x",
     f"The pipeline ({pipeline:,} MW) is {pipeline/headroom:,.1f} times the headroom our reliability evidence "
     f"covers ({headroom:,.0f} MW at a 25% cap).", "views/grid.py"),
    ("", "What cuts carbon?", f"{loc_save/sched_save:,.0f}x",
     f"For a 500 MW campus, choosing the cleanest region saves about {c.fmt_t(loc_save)} CO2 a year, "
     f"about {loc_save/sched_save:,.0f} times more than scheduling 10% of its work.", "views/carbon.py"),
    ("", "Does clean cost water?", f"{w.carbonOnly_carbon:.0f}% vs {round(w.carbonOnly_water)}%",
     f"A carbon-only schedule cuts carbon {w.carbonOnly_carbon:.0f}% but water about {round(w.carbonOnly_water)}%: "
     f"the cleanest hours are the hottest.", "views/water.py"),
    ("", "Where should they go?", f"{rho:+.2f}",
     "Green sites and buildable sites point in opposite directions; only a short list of places is both.",
     "views/siting.py"),
]
cols = st.columns(4)
for col, (icon, q, big, text, page) in zip(cols, cards):
    with col:
        st.markdown(f'<div class="kpi"><div class="label">{q}</div><div class="value">{big}</div>'
                    f'<div class="note" style="font-size:0.85rem;color:#33463B">{text}</div></div>',
                    unsafe_allow_html=True)
        st.page_link(page, label="See the evidence", icon=":material/arrow_forward:")

st.write("")
QUESTIONS = {
    "Everyone": [("What should Arizona do, based on the evidence?", "views/recommend.py"),
                  ("What happens to approvals under different rules?", "views/whatif.py"),
                 ("Is Arizona building more than its grid evidence covers?", "views/grid.py"),
                 ("Which choice cuts a data center's carbon most?", "views/carbon.py"),
                 ("Is there a carbon versus water tradeoff?", "views/water.py"),
                 ("Which places are both green and buildable?", "views/siting.py")],
    "Regulator (ACC staff)": [("What conditions should large-load approvals carry?", "views/recommend.py"),
                              ("Which sites would our approval rules let through, and at what outage risk?", "views/whatif.py"),
                              ("How much large load can each utility absorb before we leave tested ground?", "views/grid.py"),
                              ("How do two applications compare, e.g. Pinal vs Flagstaff?", "views/siting.py"),
                              ("Which conditions would cut a project's carbon most?", "views/carbon.py"),
                              ("What do the reliability data actually rule out?", "views/grid.py")],
    "Lawmaker / AG office": [("Which policy options does the evidence support?", "views/recommend.py"),
                             ("Do outage limits or size caps change approvals more?", "views/whatif.py"),
                             ("Is the pipeline normal growth or something new?", "views/grid.py"),
                             ("What would a per-gallon water surcharge cost a large campus?", "views/water.py"),
                             ("Would steering projects to certain regions cut emissions?", "views/carbon.py"),
                             ("Do the data show households losing reliability?", "views/grid.py")],
    "Utility planner": [("What should we do about large-load requests?", "views/recommend.py"),
                        ("How many campuses could my territory host under different rules?", "views/whatif.py"),
                        ("What is my utility's headroom, and how many projects fit?", "views/grid.py"),
                        ("How fast has my business load grown?", "views/grid.py"),
                        ("How dependent is my region on imports, and is it getting cleaner?", "views/carbon.py"),
                        ("Where in my territory do data centers want to be?", "views/siting.py")],
    "Data-center operator": [("How should we site, phase, cool and schedule a campus?", "views/recommend.py"),
                             ("Would smaller project phases open more sites?", "views/whatif.py"),
                             ("Which region gives the lowest-carbon power, now and over time?", "views/carbon.py"),
                             ("When should flexible jobs run, by season?", "views/carbon.py"),
                             ("What is my water bill under a surcharge, and the carbon cost of saving water?", "views/water.py"),
                             ("Which sites are both buildable and environmentally sound?", "views/siting.py")],
    "Water manager": [("Which water rules would actually reduce use?", "views/recommend.py"),
                      ("How much water would a large campus use a year?", "views/water.py"),
                      ("Does chasing clean power raise water use?", "views/water.py"),
                      ("Where is groundwater shallow and stable versus deep?", "views/siting.py"),
                      ("Which accounting choices change the water answer?", "views/water.py")],
    "Resident / ratepayer advocate": [("What should residents ask decision-makers for?", "views/recommend.py"),
                                      ("Is the grid being asked to take more than it has shown it can?", "views/grid.py"),
                                      ("How much water is that in household terms?", "views/water.py"),
                                      ("Do the data show more outages where load grows?", "views/grid.py"),
                                      ("Are data centers going where people already live?", "views/siting.py")],
}
st.subheader(f"Questions this tool answers for: {r}")
for q, page in QUESTIONS[r]:
    st.page_link(page, label=q, icon=":material/help:")

st.subheader("What this tool does that existing tools don't")
a, b = st.columns(2)
a.markdown("""
- **One view across carbon, water and grid capacity.** Carbon trackers, water maps and load studies usually
  live in separate tools.
- **Levers compared in the same units.** Where to build, when to run and what it costs in water, all in tonnes
  or liters per year for the same campus.
- **Recommendations tied to evidence.** Each action shows the number behind it and how sure we are.
- **A regulator what-if.** Set the approval rules and see which sites pass, with their carbon, water and
  outage risk.
- **Evidence headroom.** Instead of predicting outages, it shows how much planned growth sits beyond what
  history can vouch for.
""")
b.markdown("""
- **A price on the carbon-water tradeoff**, in kg of CO2 per liter of water saved, by region.
- **Green versus buildable**, using where data centers are actually built, not only environmental scores.
- **Honest about assumptions.** Every number has a confidence badge, and the contested choices are controls
  you can flip.
""")
st.caption("FSE 570 Capstone, Arizona State University, Fall 2026. Kashish Patel, Manya Tiwari, Mounusha Metti, Anamika Ghorpade.")
