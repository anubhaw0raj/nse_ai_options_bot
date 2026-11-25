"""Flicker-free Plotly charts: a persistent component updated with Plotly.react.

``st.plotly_chart`` rebuilds the chart on every rerun, which makes animated
charts blank and redraw on each tick. This component's frame stays mounted;
each rerun only sends the new figure and the browser updates it in place.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import plotly
import streamlit.components.v1 as components

_DIR = Path(__file__).parent
_JS = _DIR / "plotly.min.js"
if not _JS.exists():                       # bundle the offline plotly.js once
    src = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    shutil.copyfile(src, _JS)

_component = components.declare_component("plotly_live", path=str(_DIR))


def live_chart(fig, key: str, height: int = 400) -> None:
    """Render ``fig`` (a plotly Figure) and update it in place on reruns."""
    _component(figure=fig.to_json(), height=height, key=key, default=None)
