"""Shared data loaders, formulas, colors and page styling for the dashboard.

Reads only from the repo's results/ and data/processed/ folders. Nothing is written back.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
R, P = ROOT / "results", ROOT / "data" / "processed"

# ---------- design tokens (green-centric) ----------
G900, G700, G500, G200, G50 = "#1F3A2C", "#3F6B4C", "#7FA37A", "#C9D6BD", "#ECEBDD"
CARBON, CARBON_L = "#8C4A2F", "#D9B79E"
WATER, WATER_L = "#2C7A86", "#A9D0D3"
AMBER, RED, NEUTRAL = "#D4A03C", "#A8322A", "#7D7466"
BA_COLORS = {"AZPS": "#1F3A2C", "SRP": "#7FA37A", "TEPC": "#B4532A", "WALC": "#2C7A86"}
BA_NAMES = {"AZPS": "APS", "SRP": "SRP", "TEPC": "TEP", "WALC": "WALC"}
BA_LONG = {"AZPS": "APS (Arizona Public Service)", "SRP": "SRP (Salt River Project)",
           "TEPC": "TEP (Tucson Electric Power)", "WALC": "WALC (Western Area Power, hydro)"}

# ---------- assumptions ----------
LOAD_FACTOR = 0.8
HOURS = 8760
ACC_UNDER_CONSTRUCTION_MW = 1300   # docs/regulatory_context_check.md (ACC workshop, April 2026)
ACC_PLANNED_MW = 4000              # "more than 4,000 MW" in planning, same source
CRIT = {  # mirrors src/rq2_siting.py: (direction, default weight, plain label)
    "gw_depth_med": (-1, 0.30, "Groundwater depth (shallower is better)"),
    "gw_trend": (-1, 0.10, "Groundwater trend (falling less is better)"),
    "wetbulb_summer_c": (-1, 0.20, "Summer heat and humidity (cooler is better)"),
    "ghi_kwh": (+1, 0.15, "Sunshine (more is better)"),
    "q_active_mw": (-1, 0.25, "County power-plant queue"),
}


# ---------- loaders ----------
@st.cache_data
def carbon_hourly() -> pd.DataFrame:
    """Hourly carbon intensity, both accountings, with Arizona local hour."""
    ci = pd.read_parquet(P / "carbon_intensity.parquet")
    ci = ci.loc[~ci.data_flag, ["respondent", "ts", "ci_kg_per_mwh"]]
    cc = pd.read_parquet(P / "consumption_ci.parquet")
    cc = cc.loc[cc.valid, ["respondent", "ts", "ci_cons"]]
    d = ci.merge(cc, on=["respondent", "ts"], how="outer")
    d["hour"] = (d.ts - pd.Timedelta(hours=7)).dt.hour      # Arizona: UTC-7, no DST
    return d.rename(columns={"ci_kg_per_mwh": "produced", "ci_cons": "consumed"})


@st.cache_data
def carbon_by_ba() -> pd.DataFrame:
    return carbon_hourly().groupby("respondent")[["produced", "consumed"]].mean()


@st.cache_data
def csv(name: str) -> pd.DataFrame:
    return pd.read_csv(R / name)


@st.cache_data
def utility_load_2024() -> pd.DataFrame:
    """2024 commercial + industrial MWh per Arizona utility (EIA-861)."""
    p = pd.read_parquet(P / "eia861_panel.parquet")
    a = p[(p.state == "AZ") & (p.year == 2024) & p.util_name.notna()].copy()
    a["ci_mwh"] = a.com_mwh.fillna(0) + a.ind_mwh.fillna(0)
    g = a.groupby("util_name", as_index=False).ci_mwh.sum()
    return g[g.ci_mwh > 0].sort_values("ci_mwh", ascending=False).reset_index(drop=True)


@st.cache_data
def sites() -> pd.DataFrame:
    s = csv("rq2_scores.csv")
    pr = csv("revealed_cell_propensity.csv").rename(columns={"coarse_cell": "cell_id"})
    return s.merge(pr[["cell_id", "propensity_mean", "hosts"]], on="cell_id", how="left")


# ---------- formulas ----------
def headroom_mw(ci_mwh, cap, lf=LOAD_FACTOR):
    """Largest data-center load (MW) that adds at most `cap` of the utility's C&I load."""
    return cap * ci_mwh / (lf * HOURS)


def campus_mwh(p_mw, lf=LOAD_FACTOR):
    return p_mw * lf * HOURS


def sched_saving(job="preemptible", k=8, policy="persist") -> pd.Series:
    """Fraction of carbon saved vs RANDOM hours, per BA (schedule_savings is vs midnight start)."""
    s = csv("schedule_savings.csv")
    s = s[(s.job == job) & (s.k == k)].set_index("ba")
    return 1 - (1 - s[policy] / 100) / (1 - s["random"] / 100)


def suitability(d: pd.DataFrame, w: dict, queue_sign: int = -1) -> pd.Series:
    """Weighted mean of percentile ranks, as in src/rq2_siting.py (missing trend = neutral 0.5)."""
    comp = {}
    for c, (sign, _, _) in CRIT.items():
        sign = queue_sign if c == "q_active_mw" else sign
        r = d[c].rank(pct=True, method="average")
        comp[c] = r if sign > 0 else 1 - r
    comp = pd.DataFrame(comp)
    comp["gw_trend"] = comp["gw_trend"].where(d.gw_trend.notna(), 0.5)
    W = np.array([w[c] for c in CRIT], dtype=float)
    W = W / W.sum() if W.sum() > 0 else np.full(len(W), 1 / len(W))
    return pd.Series(comp.values @ W, index=d.index)


# ---------- UI helpers ----------
HEAD_FONT = "'Plus Jakarta Sans', 'Helvetica Neue', Arial, sans-serif"
BODY_FONT = "'Plus Jakarta Sans', 'Helvetica Neue', Arial, sans-serif"
MONO_FONT = BODY_FONT  # labels share the body font; kept as a name so the CSS reads the same
INK, PAPER, PAPER_HI, RULE = "#1C2621", "#F3EDE2", "#FBF8F1", "#D8CDB8"


def _svg_uri(svg: str) -> str:
    return "url(\"data:image/svg+xml;utf8," + svg.replace("#", "%23").replace('"', "'") + "\")"


def _contours(color: str, opacity: float, size: int = 320) -> str:
    """Topographic contour lines as an inline SVG pattern."""
    paths = "".join(
        f"<path d='M-20 {y} C {size*0.22} {y-24}, {size*0.48} {y+22}, {size*0.72} {y-8} S {size+20} {y-18}, {size+20} {y}'/>"
        for y in range(20, size + 30, 30))
    return _svg_uri(f"<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}' viewBox='0 0 {size} {size}'>"
                    f"<g fill='none' stroke='{color}' stroke-opacity='{opacity}' stroke-width='1'>{paths}</g></svg>")


SIDEBAR_PATTERN = _contours("#F3EDE2", 0.06)
PAPER_CONTOURS = _contours("#B4532A", 0.05, 420)

# Desert skyline drawn as line art: mesas, saguaros, a transmission line and the sun.
HORIZON_SVG = """
<svg class="horizon" viewBox="0 0 1200 90" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <circle cx="1010" cy="40" r="22" fill="#D4A03C" opacity="0.28"/>
  <circle cx="1010" cy="40" r="13" fill="#D4A03C" opacity="0.55"/>
  <path d="M0 78 L90 78 L118 50 L238 50 L262 78 L470 78 L492 60 L566 60 L582 78 L1200 78" fill="none" stroke="#1C2621" stroke-width="1.3"/>
  <path d="M118 50 L238 50 L262 78 L90 78 Z" fill="#B4532A" opacity="0.10"/>
  <path d="M492 60 L566 60 L582 78 L470 78 Z" fill="#B4532A" opacity="0.10"/>
  <g stroke="#3F6B4C" stroke-width="3.2" stroke-linecap="round" fill="none">
    <path d="M330 78 V44 M330 62 H321 V52 M330 57 H339 V47"/>
    <path d="M660 78 V52 M660 66 H653 V59 M660 62 H667 V55"/>
    <path d="M1110 78 V48 M1110 64 H1102 V55 M1110 59 H1118 V51"/>
  </g>
  <g stroke="#1C2621" stroke-width="1.1" fill="none" opacity="0.8">
    <path d="M760 78 L770 30 L780 78 M764 60 H776 M766 46 H774 M756 36 H784"/>
    <path d="M880 78 L890 30 L900 78 M884 60 H896 M886 46 H894 M876 36 H904"/>
    <path d="M784 36 Q832 50 876 36 M784 40 Q832 54 876 40" stroke-width="0.8"/>
    <path d="M904 36 Q960 50 1200 38 M904 40 Q960 54 1200 42" stroke-width="0.8"/>
    <path d="M600 40 Q680 52 756 36 M600 44 Q680 56 756 40" stroke-width="0.8"/>
  </g>
  <path d="M0 86 Q150 82 300 86 T600 86 T900 86 T1200 86" fill="none" stroke="#2C7A86" stroke-width="1.2" opacity="0.6"/>
</svg>
"""

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, .stApp, p, li, label, input, textarea, td, th, .stMarkdown, [data-testid="stCaptionContainer"] {{
    font-family: {BODY_FONT};
}}
.stApp {{
    color: {INK};
    background: {PAPER};
}}
[data-testid="stHeader"] {{background: transparent;}}
.block-container {{padding-top: 1.6rem; max-width: 1240px;}}

h1, h2, h3, h4 {{font-family: {HEAD_FONT} !important; font-weight: 600 !important; color: {INK}; letter-spacing: -0.01em;}}
h2, h3 {{font-size: 1.55rem !important; line-height: 1.15 !important; padding-bottom: 0.35rem !important;
         border-bottom: 1px solid {RULE}; margin-top: 0.6rem !important;}}
h3 em, h2 em {{color: #B4532A;}}
p, li {{line-height: 1.6;}}
strong, b {{font-weight: 600;}}

/* ---------- sidebar: desert night ---------- */
[data-testid="stSidebar"] > div:first-child {{
    background: {SIDEBAR_PATTERN}, linear-gradient(180deg, #1C2621 0%, #22302A 60%, #2A2620 100%);
    border-right: 1px solid #000;
}}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] [data-testid="stSliderTickBarMin"],
[data-testid="stSidebar"] [data-testid="stSliderTickBarMax"],
[data-testid="stSidebar"] [data-testid="stSliderThumbValue"] {{color: #EDE5D5 !important;}}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{color: #B9B09D !important;}}
[data-testid="stSidebarNav"] a span {{font-family: {MONO_FONT} !important; font-size: 0.8rem; font-weight: 600; text-transform: uppercase;
                                      letter-spacing: 0.06em;}}
[data-testid="stSidebarNav"] a {{border-left: 3px solid transparent; border-radius: 0 !important;}}
[data-testid="stSidebarNav"] a:hover {{background: rgba(243,237,226,0.06) !important;}}
[data-testid="stSidebarNav"] a[aria-current="page"] {{background: rgba(180,83,42,0.18) !important; border-left-color: #D97A4A;}}
[data-testid="stSidebar"] hr {{border-color: rgba(243,237,226,0.15) !important;}}
.side-title {{font-family: {HEAD_FONT}; font-size: 1.3rem; font-weight: 700; line-height: 1.15; color: {PAPER}; margin: 0.1rem 0 0.2rem 0;}}
.side-sub {{font-family: {MONO_FONT}; font-size: 0.66rem; letter-spacing: 0.14em; text-transform: uppercase;
            color: #D97A4A; margin-bottom: 0.9rem;}}

/* ---------- atlas plate (page header) ---------- */
.plate {{position: relative; padding: 0.4rem 0 0 0; margin: 0 0 0.6rem 0;}}
.plate-meta {{display: flex; flex-wrap: wrap; gap: 0.4rem 1.4rem; font-family: {MONO_FONT}; font-size: 0.7rem;
              letter-spacing: 0.14em; text-transform: uppercase; color: #6F675A; border-top: 2px solid {INK};
              border-bottom: 1px solid {RULE}; padding: 0.45rem 0;}}
.plate-meta .num {{color: #B4532A; font-weight: 600;}}
.plate h1 {{font-family: {HEAD_FONT} !important; font-size: 2.6rem; font-weight: 700 !important; line-height: 1.08; letter-spacing: -0.02em; margin: 0.2rem 0 0.2rem 0;
            padding: 0; color: {INK} !important; max-width: 22ch;}}
.plate h1 em {{color: #B4532A; font-style: normal;}}
.horizon {{display: block; width: 100%; height: 64px; margin-top: 0.4rem;}}

.answer {{position: relative; background: {PAPER_HI}; border: 1px solid {RULE}; border-left: 4px solid #B4532A;
          padding: 0.95rem 1.15rem 0.95rem 1.15rem; border-radius: 2px; font-size: 1.05rem; color: {INK};
          margin: 0.2rem 0 1.2rem 0;}}
.answer::before {{content: "FINDING"; display: block; font-family: {MONO_FONT}; font-size: 0.64rem; letter-spacing: 0.18em;
                  color: #B4532A; margin-bottom: 0.3rem;}}

/* ---------- data plates (number cards) ---------- */
.kpi, .kpi * {{word-break: normal !important; overflow-wrap: normal !important;}}
.kpi {{background: {PAPER_HI}; border: 1px solid {RULE}; border-top: 3px solid {INK}; border-radius: 2px;
       padding: 0.8rem 0.95rem 0.85rem 0.95rem; height: 100%; transition: border-color .15s ease, transform .15s ease;}}
.kpi:hover {{border-top-color: #B4532A; transform: translateY(-1px);}}
.kpi .label {{font-family: {MONO_FONT}; font-size: 0.7rem; font-weight: 600; word-break: normal; overflow-wrap: normal; hyphens: none; letter-spacing: 0.08em; text-transform: uppercase;
              color: #5E584C; line-height: 1.45;}}
.kpi .value {{font-family: {HEAD_FONT}; font-size: clamp(1.35rem, 2.1vw, 2.05rem); font-weight: 700; letter-spacing: -0.01em; white-space: normal; color: {INK}; line-height: 1.08; margin: 0.25rem 0 0.15rem 0;}}
.kpi .note {{font-size: 0.8rem; color: #6F675A; line-height: 1.4;}}

.badge {{display: inline-block; font-family: {MONO_FONT}; font-size: 0.6rem; letter-spacing: 0.08em; text-transform: uppercase;
         padding: 1px 6px; border: 1px solid currentColor; border-radius: 2px; margin-left: 6px; vertical-align: 1px;
         background: transparent;}}
.b-solid {{color: #3F6B4C;}}
.b-dep {{color: #9A6A12;}}
.b-approx {{color: #6F675A;}}

.source {{font-family: {MONO_FONT}; font-size: 0.68rem; color: #7D7466; margin-top: -0.35rem; margin-bottom: 1.1rem;
          letter-spacing: 0.02em;}}
.source::before {{content: "SOURCE  "; color: #B4532A;}}
.foryou {{background: transparent; border: 1px dashed #8C8370; border-radius: 2px; padding: 0.75rem 1rem;
          margin: 0.2rem 0 1.2rem 0; color: {INK};}}
.foryou .who {{display: block; font-family: {MONO_FONT}; font-size: 0.66rem; letter-spacing: 0.14em; text-transform: uppercase;
               color: #2C7A86; margin-bottom: 0.25rem;}}
.soon {{border: 1px solid {RULE}; border-radius: 2px; padding: 0.8rem 1rem; color: #4E483E;
        background: repeating-linear-gradient(135deg, rgba(180,83,42,0.06) 0 8px, transparent 8px 16px), {PAPER_HI};}}
.soon .who {{display: block; font-family: {MONO_FONT}; font-size: 0.66rem; letter-spacing: 0.14em; color: #B4532A;
             margin-bottom: 0.2rem;}}

[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{background: {PAPER_HI}; border: 1px solid {RULE};
        border-radius: 2px; padding: 0.4rem;}}
[data-testid="stExpander"] details {{border-radius: 2px !important; border-color: {RULE} !important; background: {PAPER_HI};}}
hr {{border-color: {RULE} !important;}}
a {{color: #B4532A !important;}}
/* recommendations */
.rec {{background: {PAPER_HI}; border: 1px solid {RULE}; border-left: 4px solid #B4532A; border-radius: 2px;
       padding: 0.85rem 1rem 0.6rem 1rem; margin: 0.2rem 0 0.35rem 0;}}
.rec-head {{display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.25rem;}}
.rec-id {{font-weight: 700; color: #B4532A; font-size: 0.8rem; letter-spacing: 0.06em;}}
.rec-topic {{font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase; color: #6F675A;}}
.rec-title {{font-family: {HEAD_FONT}; font-weight: 700; font-size: 1.12rem; line-height: 1.3; color: {INK};
             margin-bottom: 0.45rem;}}
.rec-body {{display: grid; grid-template-columns: minmax(84px, 26%) 1fr; gap: 0.9rem; align-items: start;}}
.rec-num {{font-family: {HEAD_FONT}; font-weight: 700; font-size: 1.45rem; line-height: 1.15; color: #3F6B4C;
           border-right: 1px solid {RULE}; padding-right: 0.6rem;}}
.rec-action {{margin: 0 0 0.35rem 0;}}
.rec-evidence {{margin: 0 0 0.3rem 0; font-size: 0.88rem; color: #4E483E;}}
.rec-who {{margin: 0; font-size: 0.74rem; color: #7D7466; letter-spacing: 0.02em;}}
.rec-group {{font-family: {HEAD_FONT}; font-weight: 700; font-size: 0.78rem; letter-spacing: 0.16em; text-transform: uppercase;
             color: #B4532A; margin: 1.1rem 0 0.4rem 0; border-bottom: 1px solid {RULE}; padding-bottom: 0.25rem;}}
.todo {{background: {PAPER_HI}; border: 1px solid {RULE}; border-top: 3px solid #3F6B4C; border-radius: 2px;
        padding: 0.8rem 1rem 0.4rem 1rem; margin: 1.4rem 0 0.4rem 0;}}
.todo .who {{display: block; font-size: 0.68rem; letter-spacing: 0.16em; text-transform: uppercase; color: #3F6B4C;
             font-weight: 700; margin-bottom: 0.2rem;}}
.todo ul {{margin: 0.2rem 0 0.4rem 1.1rem;}}
.todo li {{margin-bottom: 0.3rem;}}

/* sidebar controls in white (main-page controls keep the green theme color) */
[data-testid="stSidebar"] [data-testid="stSlider"] [role="group"] > div > div:first-child {{
    filter: grayscale(1) brightness(5);
}}
[data-testid="stSidebar"] [data-testid="stSlider"] [role="group"] > div > div:nth-child(2) {{
    background-color: #FFFFFF !important; box-shadow: 0 0 0 2px rgba(0,0,0,0.12);
}}
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stRadioOption"] p {{color: #FFFFFF !important;}}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {{
    border-color: rgba(255,255,255,0.9) !important; background-color: transparent !important;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked) > div > div:first-child {{
    background-color: #FFFFFF !important; border-color: #FFFFFF !important;
}}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked) > div > div:first-child > div {{
    background-color: #1C2621 !important;
}}
[data-testid="stSidebar"] [data-testid="stCheckbox"] label > span:first-child {{filter: grayscale(1) brightness(5);}}
</style>
"""

BADGES = {"solid": ("b-solid", "Solid"), "dep": ("b-dep", "Depends on assumptions"),
          "approx": ("b-approx", "Approximate")}


_KICKER = {"text": "Arizona Data Center Explorer"}


def setup(kicker: str = "Arizona Data Center Explorer"):
    _KICKER["text"] = kicker
    st.markdown(CSS, unsafe_allow_html=True)


def badge(kind: str, why: str = "") -> str:
    cls, text = BADGES[kind]
    return f'<span class="badge {cls}" title="{why}">{text}</span>'


def plate(question: str, kicker: str | None = None):
    st.markdown(f'<div class="plate"><h1>{question}</h1>{HORIZON_SVG}</div>', unsafe_allow_html=True)


def header(question: str, answer: str, kicker: str | None = None):
    plate(question, kicker)
    st.markdown(f'<div class="answer">{answer}</div>', unsafe_allow_html=True)


def kpi(col, label: str, value: str, note: str = "", kind: str | None = None, why: str = ""):
    b = badge(kind, why) if kind else ""
    col.markdown(f'<div class="kpi"><div class="label">{label}{b}</div><div class="value">{value}</div>'
                 f'<div class="note">{note}</div></div>', unsafe_allow_html=True)


def source(text: str):
    st.markdown(f'<div class="source">{text}</div>', unsafe_allow_html=True)


def soon(title: str, body: str):
    st.markdown(f'<div class="soon"><span class="who">Not yet analyzed</span><b>{title}</b><br>{body}</div>',
                unsafe_allow_html=True)


def style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(template="plotly_white", height=height, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="Plus Jakarta Sans, Helvetica Neue, Arial, sans-serif", size=13, color=INK),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None,
                                  font=dict(family="Plus Jakarta Sans, Helvetica Neue, Arial, sans-serif", size=11)),
                      hoverlabel=dict(bgcolor=PAPER_HI, bordercolor=RULE, font=dict(color=INK)))
    fig.update_xaxes(gridcolor="#E2D8C5", griddash="dot", zeroline=False, linecolor=INK, showline=True,
                     tickfont=dict(family="Plus Jakarta Sans, Helvetica Neue, Arial, sans-serif", size=11))
    fig.update_yaxes(gridcolor="#E2D8C5", griddash="dot", zeroline=False,
                     tickfont=dict(family="Plus Jakarta Sans, Helvetica Neue, Arial, sans-serif", size=11))
    return fig


def fmt_t(x: float) -> str:
    return f"{x/1e6:,.2f} Mt" if abs(x) >= 1e6 else f"{x/1e3:,.0f} kt"


# ---------- extra loaders for the user-driven features ----------
@st.cache_data
def az_ci_by_year() -> pd.DataFrame:
    """Arizona commercial + industrial MWh by year and utility (99999 = EIA state adjustment row, excluded)."""
    p = pd.read_parquet(P / "eia861_panel.parquet")
    a = p[(p.state == "AZ") & (p.util_num != 99999)].copy()
    a["ci_mwh"] = a.com_mwh.fillna(0) + a.ind_mwh.fillna(0)
    names = a.dropna(subset=["util_name"]).groupby("util_num").util_name.last()
    a["util_name"] = a.util_num.map(names).fillna("Other (non-reporting)")
    return a.groupby(["year", "util_name"], as_index=False).ci_mwh.sum()


@st.cache_data
def carbon_by_year() -> pd.DataFrame:
    d = carbon_hourly()
    return d.assign(year=d.ts.dt.year).groupby(["year", "respondent"])[["produced", "consumed"]].mean().reset_index()


@st.cache_data
def import_share() -> pd.Series:
    cc = pd.read_parquet(P / "consumption_ci.parquet")
    cc = cc[cc.valid]
    g = cc.groupby("respondent")
    return g.imports_mwh.sum() / g.supply_mwh.sum()


@st.cache_data
def heatmap(ba: str, col: str) -> pd.DataFrame:
    d = carbon_hourly()
    d = d[d.respondent == ba].copy()
    d["month"] = (d.ts - pd.Timedelta(hours=7)).dt.month
    return d.pivot_table(index="month", columns="hour", values=col, aggfunc="mean")


# ---------- presets for head-to-head comparisons ----------
PRESETS = {  # name: (lat, lon, BA, serving utility as in EIA-861) -- utility assignments are approximate
    "Pinal County (San Tan Valley)": (33.33, -111.42, "SRP", "Salt River Project"),
    "Flagstaff": (35.20, -111.65, "AZPS", "Arizona Public Service Co"),
    "West Phoenix (Goodyear)": (33.44, -112.36, "AZPS", "Arizona Public Service Co"),
    "Chandler / Mesa": (33.30, -111.84, "SRP", "Salt River Project"),
    "Tucson": (32.22, -110.97, "TEPC", "Tucson Electric Power Co"),
    "Cochise County (top green site)": (31.35, -109.28, "AZPS", "Arizona Public Service Co"),
}


def nearest_cell(lat: float, lon: float) -> pd.Series:
    s = sites()
    dist = np.hypot(s.lat - lat, (s.lon - lon) * np.cos(np.radians(lat))) * 111
    r = s.loc[dist.idxmin()].copy()
    r["dist_km"] = dist.min()
    return r


def cooling_index(tw_c: float) -> float:
    """On-site cooling water per kWh from the project's curve (docs/data_dictionary.md), L/kWh."""
    return 1.85 * float(np.clip((tw_c - 4.0) / 16.0, 0, 1))


# ---------- user lenses ----------
ROLES = {
    "Everyone": {"icon": "", "who": "A general view of all four questions."},
    "Regulator (ACC staff)": {"icon": "", "who": "Screens large-load applications and sets tariff rules."},
    "Lawmaker / AG office": {"icon": "", "who": "Weighs pauses, surcharges and incentive policy."},
    "Utility planner": {"icon": "", "who": "Decides how much new large load the system can accept, and where."},
    "Data-center operator": {"icon": "", "who": "Chooses sites, cooling and workload timing; reports sustainability."},
    "Water manager": {"icon": "", "who": "Protects groundwater and Colorado River supplies (ADWR, water districts)."},
    "Resident / ratepayer advocate": {"icon": "", "who": "Cares about bills, outages and local water."},
}


def role() -> str:
    return st.session_state.get("role", "Everyone")


def for_you(notes: dict):
    """Role-specific takeaway box; `notes` maps role name -> markdown text."""
    r = role()
    text = notes.get(r) or notes.get("Everyone")
    if text:
        st.markdown(f'<div class="foryou"><span class="who">Field note for: {r}</span>{text}</div>',
                    unsafe_allow_html=True)


def table(df: pd.DataFrame, name: str, **kw):
    st.dataframe(df, hide_index=True, width="stretch", **kw)
    st.download_button(f"Download {name} (CSV)", df.to_csv(index=False).encode(), f"{name}.csv", "text/csv",
                       key=f"dl_{name}", type="tertiary", icon=":material/download:")


def how_to_read(text: str):
    with st.expander("How to read this chart"):
        st.markdown(text)
