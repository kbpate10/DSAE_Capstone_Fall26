"""Arizona Data Center Explorer. Run from this folder: streamlit run app.py"""
import streamlit as st

import core as c

st.set_page_config(page_title="AZ Data Center Explorer", layout="wide")

pages = [
    st.Page("views/start.py", title="Start here", default=True),
    st.Page("views/grid.py", title="Can the grid take it?"),
    st.Page("views/carbon.py", title="What cuts carbon?"),
    st.Page("views/water.py", title="Does clean cost water?"),
    st.Page("views/siting.py", title="Where should they go?"),
    st.Page("views/whatif.py", title="Regulator what-if"),
    st.Page("views/recommend.py", title="Recommendations"),
    st.Page("views/about.py", title="Users, methods, assumptions"),
]
with st.sidebar:
    st.markdown('<div class="side-title">Arizona Data Center Explorer</div>'
                '<div class="side-sub">A field atlas · FSE 570 · 2026</div>', unsafe_allow_html=True)
    if "role" not in st.session_state:
        st.session_state.role = "Everyone"
    st.selectbox("I am a...", list(c.ROLES), key="role",
                 help="Each page adds a short takeaway written for this user.")
    st.caption(c.ROLES[st.session_state.role]["who"])
    st.divider()
st.navigation(pages).run()
