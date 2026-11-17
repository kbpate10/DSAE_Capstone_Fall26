import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core as c
import recs

c.setup("Recommendations")
r = c.role()
R = recs.recommendations()
e = recs.evidence()
mine = recs.for_role(R, r)

top = mine.head(3)
lead = "; ".join(f"<b>{t.title.lower()}</b>" for t in top.itertuples())
c.header("What should Arizona <em>do</em>?",
         f"{len(R)} recommendations follow from the analysis. For {'every reader' if r == 'Everyone' else r}, the "
         f"first three are: {lead}. Each one below shows the action, the evidence behind it and how sure we are.")

c.for_you({
    "Everyone": "Pick your role in the sidebar to see only the recommendations meant for you.",
    "Regulator (ACC staff)": "These are conditions and screening rules the Commission could apply to large-load "
                             "applications and tariffs.",
    "Lawmaker / AG office": "These target the policy choices on the table: pauses, surcharges and incentives.",
    "Utility planner": "These cover how much large load to accept, where, and how to keep carbon comparisons current.",
    "Data-center operator": "These cover where to connect, how to phase, cool and schedule a campus.",
    "Water manager": "These cover cooling design, surcharges and groundwater reviews.",
    "Resident / ratepayer advocate": "These are the questions to press on: bills, water and who takes the risk.",
})

# ---------------- where the big levers are ----------------
st.subheader("Where the big levers are")
st.caption("Each pair compares the strong lever with the weak one, for one 500 MW campus or the state pipeline.")
g1, g2, g3 = st.columns(3)


def pair(col, title, labels, values, fmt, colors, note):
    big = [v >= 0.4 * max(values) for v in values]
    fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color=colors,
                           text=[fmt(v) for v in values], textangle=0,
                           textposition=["inside" if b else "outside" for b in big], insidetextanchor="start",
                           textfont=dict(color=["white" if b else c.INK for b in big], size=13), cliponaxis=False,
                           hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.update_layout(title=dict(text=title, font=dict(size=15)), xaxis=dict(visible=False, range=[0, max(values) * 1.05]),
                      yaxis=dict(autorange="reversed"), showlegend=False, bargap=0.25)
    with col:
        st.plotly_chart(c.style(fig, 210), width="stretch")
        st.caption(note)


pair(g1, "Grid", ["Coming", "Tested"],
     [e["pipeline"], e["headroom"]], lambda v: f"{v:,.0f} MW", [c.CARBON, c.G700],
     "Load coming (ACC pipeline) vs load the reliability evidence covers (25% of each utility's business load).")
pair(g2, "Carbon", ["Where", "When"],
     [e["loc_kt"], e["sched_kt"]], lambda v: f"{v:,.0f} kt", [c.G700, c.G500],
     "CO2 saved a year: choosing the cleanest region (where) vs scheduling 10% of work (when).")
pair(g3, "Water", ["Cooling", "Timing"],
     [e["evap_cut"], abs(e["sched_water_hi"])], lambda v: f"{v:.0f}%", [c.WATER, "#5FA3AE"],
     "Largest water cut: drier cooling design (100% to 25% evaporative) vs the best scheduling case.")

# ---------------- the recommendations ----------------
st.subheader("The recommendations")
f1, f2 = st.columns([1.4, 1])
topic = f1.segmented_control("Topic", ["All"] + recs.TOPICS, default="All", key="rec_topic")
only_mine = f2.toggle("Only those for my role", value=(r != "Everyone"), disabled=(r == "Everyone"),
                      help="Uses the role chosen in the sidebar.")
show = mine if only_mine else R
if topic and topic != "All":
    show = show[show.topic == topic]
if show.empty:
    st.info("No recommendation matches this filter.")
for t in recs.TOPICS:
    block = show[show.topic == t]
    if block.empty:
        continue
    st.markdown(f'<div class="rec-group">{t}</div>', unsafe_allow_html=True)
    cols = st.columns(2, gap="medium")
    for i, row in enumerate(block.itertuples()):
        with cols[i % 2]:
            recs.card(row)
            st.page_link(recs.PAGES[row.page], label=f"See the evidence on the {row.page} page")

# ---------------- summary table ----------------
st.subheader("All recommendations in one table")
tbl = R.assign(**{"For": R.who.apply(", ".join),
                  "How sure": R.confidence.map({"solid": "Solid", "dep": "Depends on assumptions",
                                                "approx": "Approximate"})})
c.table(tbl[["id", "topic", "title", "action", "number", "evidence", "For", "How sure"]]
        .rename(columns={"id": "ID", "topic": "Topic", "title": "Recommendation", "action": "Action",
                         "number": "Key number", "evidence": "Evidence"}), "recommendations")
c.source("Computed from the team's results files each time the page loads (grid, carbon, water, siting and framework "
         "results in results/).")

# ---------------- what would make them stronger ----------------
st.subheader("What would make these recommendations stronger")
w1, w2 = st.columns(2, gap="large")
w1.markdown("""
- **Household bills.** No analysis yet links large-load growth to residential rates, which is the cost question in
  the public debate.
- **Real interconnection capacity.** Substation distance stands in for capacity; utility study data would replace it.
""")
w2.markdown("""
- **Metered water use at data centers.** Water figures are scenario estimates; metered cooling water would confirm them.
- **A tested marginal-emissions signal.** Marginal estimates disagree with average ones and have no ground truth yet.
""")
st.caption("Recommendations rest on public data and the assumptions listed on the Users, methods, assumptions page. "
           "They are decision aids, not a siting decision.")
