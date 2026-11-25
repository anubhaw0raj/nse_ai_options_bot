"""NSE AI Options Bot -- demonstration app.

Run from the repository root:
    streamlit run app/main.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)                      # config paths (data/, reports/) are repo-relative

import streamlit as st

st.set_page_config(page_title="NSE AI Options Bot", page_icon=":chart_with_upwards_trend:",
                   layout="wide", initial_sidebar_state="expanded")

pages = [
    st.Page("pages/live_replay.py", title="Live Session Replay", icon=":material/monitoring:",
            default=True),
]
st.navigation(pages).run()
