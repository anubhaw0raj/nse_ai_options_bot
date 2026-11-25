"""Plotly chart builders for the demo app (dark trading-terminal style)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

UP, DOWN = "#26a69a", "#ef5350"
PROB, THR, EXIT = "#f5a623", "#3fb950", "#f85149"
GRID, TEXT = "#21262d", "#8b949e"
BG = "rgba(0,0,0,0)"


def _full_day(df: pd.DataFrame, x_range) -> pd.DataFrame:
    """Reindex onto every minute of the session; unplayed minutes stay empty.

    With a single revealed candle Plotly cannot infer the bar width and draws
    one giant box; giving it the whole 1-minute grid fixes the width and keeps
    the time axis steady from the very first frame.
    """
    grid = pd.date_range(x_range[0], x_range[1] - pd.Timedelta(minutes=1), freq="1min")
    if not len(df):
        return pd.DataFrame({"datetime": grid})
    out = df.drop_duplicates("datetime").set_index("datetime").reindex(grid)
    return out.rename_axis("datetime").reset_index()


def _style(fig: go.Figure, height: int, x_range) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", height=height, paper_bgcolor=BG, plot_bgcolor="#0d1117",
        margin=dict(l=8, r=8, t=30, b=8), showlegend=False,
        font=dict(size=11, color="#c9d1d9"), hovermode="x unified",
        uirevision="keep")
    fig.update_xaxes(range=x_range, autorange=False, gridcolor=GRID, showspikes=True, spikecolor="#484f58",
                     spikethickness=1, rangeslider_visible=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def spot_chart(spot: pd.DataFrame, x_range, events: pd.DataFrame | None = None,
               day_open: float | None = None) -> go.Figure:
    """BankNifty 1-minute candles revealed up to the current minute."""
    fig = go.Figure()
    g = _full_day(spot, x_range)
    fig.add_trace(go.Candlestick(
        x=g["datetime"], open=g["open"], high=g["high"], low=g["low"],
        close=g["close"], increasing_line_color=UP, decreasing_line_color=DOWN,
        increasing_fillcolor=UP, decreasing_fillcolor=DOWN, name="BANKNIFTY"))
    if day_open:
        fig.add_hline(y=day_open, line=dict(color="#484f58", dash="dot", width=1))
    if events is not None and len(events):
        for _, e in events.iterrows():
            fig.add_vline(x=e["datetime"], line=dict(
                color=UP if e["kind"] == "BUY" else "#d2a8ff", width=1, dash="dot"))
    last = spot.iloc[-1] if len(spot) else None
    title = "BANKNIFTY index (1-min)"
    if last is not None:
        title += f"   <b>{last['close']:,.2f}</b>"
    fig.update_layout(title=dict(text=title, x=0.01, font=dict(size=13)))
    return _style(fig, 330, x_range)


def contract_chart(tape: pd.DataFrame, symbol: str, label: str, threshold: float,
                   exit_thr: float, x_range, trades: pd.DataFrame) -> go.Figure:
    """Premium candles + entries/exits + stop/target, with P(UP) underneath."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.66, 0.34])
    if len(tape):
        g = _full_day(tape[["datetime", "open", "high", "low", "close", "prob"]], x_range)
        fig.add_trace(go.Candlestick(
            x=g["datetime"], open=g["open"], high=g["high"], low=g["low"],
            close=g["close"], increasing_line_color=UP, decreasing_line_color=DOWN,
            increasing_fillcolor=UP, decreasing_fillcolor=DOWN, name=symbol), 1, 1)
        held = tape[tape["state"] == "IN"]
        if len(held):
            fig.add_trace(go.Scatter(x=held["datetime"], y=held["stop"], mode="lines",
                                     line=dict(color=EXIT, width=1, dash="dash"),
                                     name="stop", connectgaps=False), 1, 1)
            fig.add_trace(go.Scatter(x=held["datetime"], y=held["target"], mode="lines",
                                     line=dict(color=THR, width=1, dash="dash"),
                                     name="target", connectgaps=False), 1, 1)
        fig.add_trace(go.Scatter(x=tape["datetime"], y=tape["prob"], mode="lines",
                                 line=dict(color=PROB, width=1.6), name="P(UP)"), 2, 1)
        if threshold <= 1:                         # >1 means "sitting out today"
            fig.add_hrect(y0=threshold, y1=1, fillcolor=THR, opacity=0.08, line_width=0,
                          row=2, col=1)
            fig.add_hline(y=threshold, line=dict(color=THR, dash="dash", width=1),
                          row=2, col=1)
        fig.add_hline(y=exit_thr, line=dict(color=EXIT, dash="dash", width=1), row=2, col=1)

    ent = tape[tape["event"] == "ENTRY"] if len(tape) else tape
    if len(ent):
        # entries come from the live tape, so a position that is still open shows
        fig.add_trace(go.Scatter(
            x=ent["datetime"], y=ent["entry_fill"], mode="markers",
            marker=dict(symbol="triangle-up", size=13, color=UP,
                        line=dict(color="white", width=1)),
            name="BUY", hovertext=[f"BUY {int(l)} lot @ {p:.2f}" for l, p in
                                   zip(ent["lots"], ent["entry_fill"])]), 1, 1)
        exits = dict(zip(trades["entry_time"], trades["exit_time"])) if len(trades) else {}
        for t0 in ent["datetime"]:
            fig.add_vrect(x0=t0, x1=exits.get(t0, tape["datetime"].iloc[-1]),
                          fillcolor=PROB, opacity=0.07, line_width=0, row=1, col=1)
    if len(trades):
        ex = trades
        fig.add_trace(go.Scatter(
            x=ex["exit_time"], y=ex["exit_price"], mode="markers+text",
            marker=dict(symbol="triangle-down", size=13,
                        color=[UP if v > 0 else DOWN for v in ex["pnl"]],
                        line=dict(color="white", width=1)),
            text=[r.upper() for r in ex["exit_reason"]], textposition="top center",
            textfont=dict(size=9), name="SELL"), 1, 1)

    ltp = f"   LTP <b>{tape['close'].iloc[-1]:.2f}</b>" if len(tape) else ""
    p = f"   P(UP) <b>{tape['prob'].iloc[-1]:.2f}</b>" if len(tape) else ""
    fig.update_layout(title=dict(text=f"{label} &nbsp;<span style='color:{TEXT}'>{symbol}</span>"
                                 f"{ltp}{p}", x=0.01, font=dict(size=13)))
    fig.update_yaxes(range=[0, 1], row=2, col=1, title_text="P(UP)", title_font_size=10)
    fig.update_yaxes(title_text="Premium (Rs.)", title_font_size=10, row=1, col=1)
    return _style(fig, 430, x_range)


def pnl_chart(curve: pd.DataFrame, x_range) -> go.Figure:
    fig = go.Figure()
    if len(curve):
        y = curve["total"]
        fig.add_trace(go.Scatter(x=curve["datetime"], y=y, mode="lines",
                                 line=dict(color=PROB, width=2), fill="tozeroy",
                                 fillcolor="rgba(245,166,35,0.12)", name="Net P&L"))
        fig.add_trace(go.Scatter(x=curve["datetime"], y=curve["realised"], mode="lines",
                                 line=dict(color="#58a6ff", width=1, dash="dot"),
                                 name="Realised"))
    fig.add_hline(y=0, line=dict(color="#484f58", width=1))
    fig.update_layout(title=dict(text="Intraday net P&L after all charges (Rs.)  "
                                 "<span style='color:#8b949e;font-size:11px'>solid: "
                                 "realised + open positions · dotted: realised</span>",
                                 x=0.01, font=dict(size=13)))
    return _style(fig, 260, x_range)


def threshold_chart(grid: pd.DataFrame, chosen: float) -> go.Figure:
    colors = [THR if abs(t - chosen) < 1e-9 else "#30363d" for t in grid["threshold"]]
    fig = go.Figure(go.Bar(x=[f"{t:.2f}" for t in grid["threshold"]], y=grid["net"],
                           marker_color=colors,
                           text=[f"Rs.{v:,.0f}<br>{n} trades" for v, n in
                                 zip(grid["net"], grid["trades"])],
                           textposition="outside"))
    fig.add_hline(y=0, line=dict(color="#484f58", width=1))
    fig.update_layout(template="plotly_dark", height=250, paper_bgcolor=BG,
                      plot_bgcolor="#0d1117", margin=dict(l=8, r=8, t=10, b=8),
                      xaxis_title="entry threshold", yaxis_title="net on calibration days",
                      font=dict(size=11))
    return fig


def importance_chart(imp: pd.Series, n: int = 10) -> go.Figure:
    top = (imp / imp.sum()).sort_values(ascending=True).tail(n)
    fig = go.Figure(go.Bar(x=top.values * 100, y=top.index, orientation="h",
                           marker_color="#58a6ff"))
    fig.update_layout(template="plotly_dark", height=250, paper_bgcolor=BG,
                      plot_bgcolor="#0d1117", margin=dict(l=8, r=8, t=10, b=8),
                      xaxis_title="share of splits (%)", font=dict(size=11))
    return fig
