"""Live Session Replay -- watch the system trade a historical day minute by minute.

Before the open the system trains on the preceding days, calibrates its
probabilities, picks an entry threshold by simulating post-cost profit and
decides whether to trade at all. The session then plays bar by bar: market
data, model probability, risk checks, orders, positions and P&L after every
Indian charge -- exactly what the backtester computes (see tests/test_replay.py).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from app import components as C
from app.plotly_live import live_chart
from src.backtest.costs import CostModel
from src.config import load_config
from src.features.store import FeatureStore
from src.live.replay import LiveSession, charges_breakdown, prepare_session

SESSION_START = pd.Timedelta(hours=9, minutes=15)
SESSION_END = pd.Timedelta(hours=15, minutes=30)
SPEEDS = {"Slow  (2 min / s)": 1, "Normal  (6 min / s)": 3,
          "Fast  (20 min / s)": 10, "Very fast  (60 min / s)": 30}
TICK = 0.5                                    # seconds between frames


# ─────────────────────────────────────────────────────────── data / caching ──
@st.cache_resource
def _cfg():
    return load_config()


@st.cache_resource
def _store():
    return FeatureStore(_cfg()["data"]["features_dir"])


@st.cache_data
def _days() -> list[date]:
    return _store().available_days(_cfg()["instrument"])


@st.cache_data
def _featured_days() -> pd.DataFrame:
    """Days from the latest 5-day-calibration walk-forward run, for quick picks."""
    try:
        ex = pd.read_csv("reports/experiments.csv")
        ex = ex[(ex["cal_days"] == 5) & (ex["horizon"] == 15)]
        frames = []
        for rep in ex["report"]:
            p = f"reports/{rep}/days.csv"
            try:
                frames.append(pd.read_csv(p, parse_dates=["day"]))
            except FileNotFoundError:
                pass
        if not frames:
            return pd.DataFrame()
        d = pd.concat(frames).drop_duplicates("day").sort_values("day")
        return d[d["trades"] > 0]
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=40, persist="disk")
def _session(day_iso: str, horizon: int, train_days: int, cal_days: int,
             use_risk: bool, grid: tuple[float, ...]):
    """Everything done 'before the open' (cached on disk per day + settings)."""
    cfg = _cfg()
    day = date.fromisoformat(day_iso)
    plan, test_df, _prob, model = prepare_session(
        cfg, day, horizon, train_days, cal_days, use_risk, list(grid), return_model=True)
    raw = _store().load_day(cfg["instrument"], day)
    return dict(plan=plan, raw=raw, test_df=test_df, model=model)


def _spot_frame(raw: pd.DataFrame) -> pd.DataFrame:
    s = (raw.groupby("datetime")[["open_spot", "high_spot", "low_spot", "close_spot"]]
         .first().reset_index())
    s.columns = ["datetime", "open", "high", "low", "close"]
    return s.sort_values("datetime").reset_index(drop=True)


def _context(raw: pd.DataFrame) -> pd.DataFrame:
    cols = ["pcr_oi", "pcr_vol", "iv_skew", "rv_15m", "rv_60m", "basis_pct",
            "vwap_dist_pct", "fut_ret_5m", "spot_ret_5m"]
    return raw.groupby("datetime")[cols].first().sort_index()


# ──────────────────────────────────────────────────────────────── helpers ──
def _rs(v: float, sign: bool = True) -> str:
    s = f"{abs(v):,.0f}"
    return (("+" if v >= 0 else "−") if sign else "") + "Rs." + s


GATE_TEXT = {"max_trades": "trade limit reached", "daily_loss_limit": "daily loss limit hit",
             "opening_window": "opening 5 minutes", "late_session": "after 15:00",
             "market_dead": "market too quiet", "market_panic": "market too volatile"}


def _event_feed(tapes: dict, t: pd.Timestamp, n: int = 10) -> list[str]:
    msgs = []
    for opt, (tape, trades, sym) in tapes.items():
        if tape is None or not len(tape):
            continue
        cur = tape[tape["datetime"] <= t]
        last_gate = None
        for _, r in cur.iterrows():
            hhmm = (f"<code style='color:#8b949e'>{r['datetime']:%H:%M}</code>")
            if r["event"] == "ENTRY":
                msgs.append((r["datetime"], f"{hhmm} 🟢 <b>BUY {opt}</b> {r['lots']} lot · "
                             f"P(UP) {r['prob']:.2f} · fill Rs.{r['entry_fill']:.2f}"))
            elif r["event"]:
                tr = trades[trades["exit_time"] == r["datetime"]]
                pnl = float(tr["pnl"].iloc[0]) if len(tr) else 0.0
                icon, col = ("✅", "#3fb950") if pnl > 0 else ("🔻", "#f85149")
                msgs.append((r["datetime"], f"{hhmm} {icon} <b>SELL {opt}</b> · "
                             f"{r['event'].upper()} · net <span style='color:{col}'>"
                             f"{_rs(pnl)}</span>"))
            elif r["gate"] and r["gate"] != "ok" and r["gate"] != last_gate:
                msgs.append((r["datetime"], f"{hhmm} ⛔ {opt} signal {r['prob']:.2f} "
                             f"<span style='color:#8b949e'>blocked: "
                             f"{GATE_TEXT.get(r['gate'], r['gate'])}</span>"))
            last_gate = r["gate"] if r["gate"] not in ("", "ok") else None
    msgs.sort(key=lambda m: m[0], reverse=True)
    return [m for _, m in msgs[:n]]


def _order_book(views: dict, lot_size: int) -> pd.DataFrame:
    rows = []
    for opt, (tape, trades, sym) in views.items():
        if len(tape):
            for _, r in tape[tape["event"] == "ENTRY"].iterrows():
                rows.append(dict(Time=r["datetime"], Side="BUY", Contract=sym,
                                 Qty=int(r["lots"] * lot_size), Price=f"{r['entry_fill']:.2f}",
                                 Reason="model signal", Charges="", Net=""))
        if len(trades):
            for _, tr in trades.iterrows():
                rows.append(dict(Time=tr["exit_time"], Side="SELL", Contract=sym,
                                 Qty=int(tr["qty"]), Price=f"{tr['exit_price']:.2f}",
                                 Reason=tr["exit_reason"], Charges=f"{tr['charges']:.2f}",
                                 Net=_rs(tr["pnl"])))
    if not rows:
        return pd.DataFrame()
    ob = pd.DataFrame(rows).sort_values("Time", ascending=False)
    ob["Time"] = ob["Time"].dt.strftime("%H:%M")
    return ob


def _chain(raw: pd.DataFrame, probs: pd.DataFrame, t: pd.Timestamp, spot: float,
           expiry, traded: set[str], step: int = 100, width: int = 5) -> pd.DataFrame:
    snap = raw[(raw["datetime"] <= t) & (raw["datetime"] > t - pd.Timedelta(minutes=5))]
    snap = snap[snap["expiry_date"] == expiry].sort_values("datetime") \
        .groupby("symbol").tail(1)
    atm = round(spot / step) * step
    strikes = [atm + k * step for k in range(-width, width + 1)]
    snap = snap[snap["strike"].isin(strikes)]
    pr = probs[probs["datetime"] <= t].sort_values("datetime").groupby("symbol").tail(1)
    snap = snap.merge(pr[["symbol", "prob"]], on="symbol", how="left")
    side = {}
    for ot in ("CE", "PE"):
        s = snap[snap["option_type"] == ot].set_index("strike")
        side[ot] = s
    rows = []
    for k in strikes:
        r = {"Strike": str(int(k))}
        mark = {"CE": "", "PE": ""}
        for ot in ("CE", "PE"):
            s = side[ot]
            if k in s.index:
                x = s.loc[k]
                r[f"{ot} OI"] = float(x["oi"])
                r[f"{ot} ΔOI 5m %"] = float(x["oi_chg_5m"])
                r[f"{ot} IV %"] = float(x["IV"]) * 100
                r[f"{ot} LTP"] = float(x["close_opt"])
                r[f"{ot} P(UP)"] = float(x["prob"]) if x["prob"] == x["prob"] else np.nan
                if x["symbol"] in traded:
                    mark[ot] = "▶ " if ot == "CE" else " ◀"
            else:
                for c in ("OI", "ΔOI 5m %", "IV %", "LTP", "P(UP)"):
                    r[f"{ot} {c}"] = np.nan
        r["Strike"] = (mark["CE"] + ("★ " if k == atm else "") + str(int(k)) + mark["PE"])
        rows.append(r)
    cols = ["CE OI", "CE ΔOI 5m %", "CE IV %", "CE P(UP)", "CE LTP", "Strike",
            "PE LTP", "PE P(UP)", "PE IV %", "PE ΔOI 5m %", "PE OI"]
    return pd.DataFrame(rows)[cols]


# ──────────────────────────────────────────────────────────────── sidebar ──
cfg = _cfg()
cost = CostModel(cfg["costs"])
days = _days()
st.session_state.setdefault("cursor", 0)
st.session_state.setdefault("playing", False)

with st.sidebar:
    st.markdown("### 📅 Trading day")
    feat = _featured_days()
    pick_mode = st.radio("Choose", ["Featured days", "Any date"], horizontal=True,
                         label_visibility="collapsed")
    if pick_mode == "Featured days" and len(feat):
        labels = {f"{r.day:%a %d %b %Y}  ·  {int(r.trades)} trades  ·  {_rs(r.net)}": r.day.date()
                  for r in feat.itertuples()}
        day = labels[st.selectbox("Days the system traded (backtest)", list(labels))]
    else:
        valid = [d for d in days if d.year in (2020, 2021)]
        day = st.date_input("Date (2020–2021 development years)", value=date(2021, 3, 12),
                            min_value=valid[13], max_value=valid[-1])
        if day not in days:
            st.warning("Market closed or no data that day — showing the next trading day.")
            day = next(d for d in days if d >= day)

    with st.expander("⚙️ Strategy settings"):
        horizon = st.select_slider("Prediction horizon (min)", [5, 15, 30], value=15)
        train_days = st.slider("Training window (days)", 8, 20, 13)
        cal_days = st.slider("Calibration days (inside the window)", 2, 6, 5)
        use_risk = st.toggle("Risk manager", value=True)
        grid = tuple(st.multiselect("Threshold grid", [0.60, 0.65, 0.70, 0.75, 0.80],
                                    default=[0.65, 0.70, 0.75, 0.80]) or [0.70])

    st.markdown("### ▶️ Playback")
    c1, c2, c3 = st.columns(3)
    if c1.button("⏯", help="Play / pause", width="stretch"):
        st.session_state.playing = not st.session_state.playing
    if c2.button("⏮", help="Back to the open", width="stretch"):
        st.session_state.cursor, st.session_state.playing = 0, False
        st.session_state.live_key = None          # start a fresh session
    if c3.button("⏭", help="Jump to the close", width="stretch"):
        st.session_state.cursor, st.session_state.playing = 10_000, False
    speed = SPEEDS[st.select_slider("Speed", list(SPEEDS), value="Normal  (6 min / s)")]

key = (day.isoformat(), horizon, train_days, cal_days, use_risk, tuple(sorted(grid)))
if st.session_state.get("key") != key:
    st.session_state.key, st.session_state.cursor, st.session_state.playing = key, 0, False

# ───────────────────────────────────────────────────────── before the open ──
with st.spinner(f"Before the open: loading {train_days} trading days, training LightGBM, "
                f"calibrating and searching the entry threshold…"):
    S = _session(*key)
plan, raw = S["plan"], S["raw"]
# Streamlit dims ("stale") every element of a fragment while it reruns, which
# makes the charts blink on every tick. Keep them fully opaque instead.
st.markdown("""<style>
div[data-testid="stElementContainer"][data-stale="true"],
div[data-stale="true"] { opacity: 1 !important; transition: none !important; }
</style>""", unsafe_allow_html=True)
spot_all, ctx = _spot_frame(raw), _context(raw)
x_range = [pd.Timestamp(day) + SESSION_START, pd.Timestamp(day) + SESSION_END]

st.markdown(f"## BANKNIFTY options · live session replay  "
            f"<span style='color:#8b949e;font-size:18px'>{day:%A, %d %B %Y}</span>",
            unsafe_allow_html=True)

trade_today = not plan.skip
with st.expander("🌅 Before the open — how today's model was built", expanded=st.session_state.cursor == 0):
    a, b, c, d = st.columns(4)
    last_win = plan.cal_days[-1] if plan.cal_days else plan.fit_days[-1]
    a.metric("Training window", f"{len(plan.fit_days) + len(plan.cal_days)} trading days",
             f"{len(plan.fit_days)} fit + {len(plan.cal_days)} calibrate · "
             f"{plan.fit_days[0]:%d %b} → {last_win:%d %b}", delta_color="off")
    b.metric("Training rows", f"{plan.n_train_rows:,}", f"{plan.up_rate:.0%} labelled UP",
             delta_color="off")
    c.metric("LightGBM fit", f"{plan.fit_seconds:.1f} s",
             "calibrated (isotonic)" if plan.calibrated else "uncalibrated", delta_color="off")
    d.metric("Entry threshold", f"{plan.threshold:.2f}",
             f"calibration net {_rs(plan.cal_net)}", delta_color="off")
    g1, g2 = st.columns([1.2, 1])
    with g1:
        st.caption("Threshold search — each candidate simulated on the calibration days, "
                   "net of all charges")
        if plan.grid:
            st.plotly_chart(C.threshold_chart(pd.DataFrame(plan.grid), plan.threshold),
                            width="stretch", config={"displayModeBar": False})
    with g2:
        st.caption("What the model relied on (top 10 features)")
        if plan.importance is not None:
            st.plotly_chart(C.importance_chart(plan.importance), width="stretch",
                            config={"displayModeBar": False})
    if trade_today:
        st.success(f"**Decision: TRADE today.** Best threshold {plan.threshold:.2f} made "
                   f"{_rs(plan.cal_net)} on the {len(plan.cal_days)} calibration days.")
    else:
        st.warning(f"**Decision: SIT OUT today.** Even the best threshold lost money on the "
                   f"calibration days ({_rs(plan.cal_net)}), so the no-edge rule keeps the "
                   f"system flat. The model still runs and is shown live below.")

if S["test_df"] is None:
    st.error("No usable option data for this day.")
    st.stop()

show_what_if = False
if not trade_today:
    show_what_if = st.toggle("Show what the system *would* have traded anyway (demo only)",
                             value=False)
live_key = trade_today or show_what_if
if st.session_state.get("live_key") != (key, live_key):
    st.session_state.live = LiveSession(plan, S["test_df"], S["model"], cost,
                                        trade=live_key)
    st.session_state.live_key = (key, live_key)
live: LiveSession = st.session_state.live
minutes = spot_all["datetime"].tolist()
first = next(iter(live.traders.values()))
expiry = raw.loc[raw["symbol"] == first.sym, "expiry_date"].iloc[0]


# ───────────────────────────────────────────────────────────── the session ──
@st.fragment(run_every=TICK if st.session_state.playing else None)
def session_view():
    if st.session_state.playing:
        st.session_state.cursor += speed
    cur = min(st.session_state.cursor, len(minutes) - 1)
    if cur >= len(minutes) - 1:
        st.session_state.playing = False
    t = minutes[cur]
    done = live.advance_to(t)            # score + trade every new minute up to t
    spot = spot_all.iloc[: cur + 1]
    s_now, s_open = float(spot["close"].iloc[-1]), float(spot_all["open"].iloc[0])

    views = {opt: (tr.tape(), tr.trades_frame(), tr.sym)
             for opt, tr in live.traders.items()}

    realised = sum(float(v[0]["realised"].iloc[-1]) for v in views.values() if len(v[0]))
    unreal = sum(float(v[0]["unrealised"].iloc[-1]) for v in views.values() if len(v[0]))
    charges = sum(float(v[0]["charges"].iloc[-1]) for v in views.values() if len(v[0]))
    n_tr = sum(int(v[0]["trades_done"].iloc[-1]) for v in views.values() if len(v[0]))
    open_pos = sum(1 for v in views.values() if len(v[0]) and v[0]["state"].iloc[-1] == "IN")

    status = "CLOSED" if cur >= len(minutes) - 1 else ("LIVE" if st.session_state.playing
                                                         else "PAUSED")
    colour = {"LIVE": "#3fb950", "PAUSED": "#f5a623", "CLOSED": "#8b949e"}[status]
    st.markdown(
        f"<div style='display:flex;gap:18px;align-items:center;margin:-6px 0 4px 0'>"
        f"<span style='font-size:30px;font-weight:700'>{t:%H:%M}</span>"
        f"<span style='color:{colour};border:1px solid {colour};border-radius:12px;"
        f"padding:1px 10px;font-weight:600'>● {status}</span>"
        f"<span style='color:#8b949e'>bar {cur + 1} / {len(minutes)} · model scored "
        f"{len(live.by_minute.get(live.now, [])) if live.now is not None else 0} contracts at "
        f"this minute in {live.score_ms:.0f} ms · uses only data up to now</span></div>",
        unsafe_allow_html=True)

    m = st.columns(6)
    m[0].metric("BANKNIFTY", f"{s_now:,.2f}", f"{s_now - s_open:+,.2f} ({(s_now / s_open - 1):+.2%})")
    m[1].metric("Net P&L today", _rs(realised + unreal), delta=None)
    m[2].metric("Realised", _rs(realised))
    m[3].metric("Open positions", f"{open_pos}", _rs(unreal) if open_pos else "flat",
                delta_color="off")
    m[4].metric("Round trips", f"{n_tr}")
    m[5].metric("Charges paid", _rs(charges, sign=False))

    evs = []
    for opt, (tv, tr, sym) in views.items():
        for _, r in tv[tv["event"] != ""].iterrows():
            evs.append(dict(datetime=r["datetime"], kind="BUY" if r["event"] == "ENTRY" else "SELL"))
    live_chart(C.spot_chart(spot, x_range, pd.DataFrame(evs), s_open), key="spot", height=330)

    cc = st.columns(2)
    for col, opt, label in ((cc[0], "CE", "ATM CALL"), (cc[1], "PE", "ATM PUT")):
        tv, tr, sym = views[opt]
        with col:
            live_chart(C.contract_chart(tv, sym, label, plan.threshold if live_key else 2.0,
                                        plan.exit_threshold, x_range, tr),
                       key=f"c_{opt}", height=430)

    left, mid, right = st.columns([1.05, 1.6, 1.15])
    with left:
        st.markdown("##### 💼 Positions")
        for opt, (tv, tr, sym) in views.items():
            if not len(tv):
                continue
            r = tv.iloc[-1]
            if r["state"] == "IN":
                pnl_c = "#3fb950" if r["unrealised"] >= 0 else "#f85149"
                st.markdown(
                    f"<div style='border:1px solid #30363d;border-radius:8px;padding:8px 10px;"
                    f"margin-bottom:6px'><b>LONG {opt}</b> · {sym}<br>"
                    f"qty {int(r['lots'] * plan.lot_size)} @ {r['entry_fill']:.2f} · LTP "
                    f"{r['close']:.2f}<br><span style='color:{pnl_c};font-size:18px;font-weight:700'>"
                    f"{_rs(r['unrealised'])}</span> &nbsp;<span style='color:#8b949e'>open</span><br>"
                    f"<span style='color:#f85149'>stop {r['stop']:.2f}</span> · "
                    f"<span style='color:#3fb950'>target {r['target']:.2f}</span> · "
                    f"{int(r['bars_held'])}/{plan.max_hold_bars} min</div>",
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f"<div style='border:1px solid #21262d;border-radius:8px;padding:8px 10px;"
                    f"margin-bottom:6px;color:#8b949e'><b>{opt}</b> · flat · watching "
                    f"{sym}<br>P(UP) {r['prob']:.2f} vs entry "
                    f"{plan.threshold:.2f}</div>", unsafe_allow_html=True)

        st.markdown("##### 🛡️ Risk checks")
        rc = plan.risk_cfg or {}
        ctx_now = ctx[ctx.index <= t].iloc[-1] if len(ctx[ctx.index <= t]) else None
        rv = float(ctx_now["rv_15m"]) if ctx_now is not None else np.nan
        mins = (t - t.normalize() - SESSION_START).total_seconds() / 60
        used = max((int(v[0]["trades_done"].iloc[-1]) for v in views.values() if len(v[0])),
                   default=0)
        loss = max((float(v[0]["day_loss_used"].iloc[-1]) for v in views.values() if len(v[0])),
                   default=0.0)
        checks = [
            ("Opening window passed", mins >= rc.get("no_entry_first_min", 5), f"{mins:.0f} min since open"),
            ("Before 15:00 cut-off", t.time() < pd.Timestamp("15:00").time(), ""),
            ("Volatility in band", rc.get("min_rv_15m", 0) <= rv <= rc.get("max_rv_15m", 9),
             f"rv₁₅ {rv:.3f} in [{rc.get('min_rv_15m', 0)}, {rc.get('max_rv_15m', 0)}]"),
            ("Trades below limit", used < rc.get("max_trades_per_day", 4),
             f"{used}/{rc.get('max_trades_per_day', 4)} per contract"),
            ("Daily loss within limit", loss < rc.get("daily_loss_limit", 3000),
             f"{_rs(-loss)} of −Rs.{rc.get('daily_loss_limit', 3000):,.0f}"),
        ]
        if not plan.risk_cfg:
            st.caption("Risk manager switched off in settings.")
        for name, ok, note in checks:
            st.markdown(f"{'🟢' if ok else '🔴'} {name} <span style='color:#8b949e;font-size:12px'>"
                        f"{note}</span>", unsafe_allow_html=True)

    with mid:
        st.markdown(f"##### 🔗 Option chain at {t:%H:%M} · expiry {pd.Timestamp(expiry):%d %b}")
        traded = {v[2] for v in views.values()}
        ch = _chain(raw, live.chain_probs(), t, s_now, expiry, traded)
        oi_max = float(np.nanmax(ch[["CE OI", "PE OI"]].values)) if len(ch) else 1.0
        st.dataframe(
            ch, hide_index=True, width="stretch", height=420,
            column_config={
                "CE OI": st.column_config.ProgressColumn("CE OI", format="%.0f",
                                                         min_value=0, max_value=oi_max),
                "PE OI": st.column_config.ProgressColumn("PE OI", format="%.0f",
                                                         min_value=0, max_value=oi_max),
                **{c: st.column_config.NumberColumn(c, format="%.2f")
                   for c in ("CE LTP", "PE LTP", "CE P(UP)", "PE P(UP)")},
                **{c: st.column_config.NumberColumn(c, format="%.1f")
                   for c in ("CE IV %", "PE IV %", "CE ΔOI 5m %", "PE ΔOI 5m %")},
            })
        st.caption("★ at-the-money strike · ▶ ◀ contracts the system trades · P(UP) = "
                   "calibrated probability that the premium rises over the next "
                   f"{plan.horizon} minutes")

    with right:
        st.markdown("##### 📡 Market context")
        if ctx_now is not None:
            k1, k2 = st.columns(2)
            k1.metric("Put–call ratio (OI)", f"{ctx_now['pcr_oi']:.2f}")
            k2.metric("IV skew (PE − CE)", f"{ctx_now['iv_skew'] * 100:+.1f} pts")
            k1.metric("Futures basis", f"{ctx_now['basis_pct']:+.2f}%")
            k2.metric("From futures VWAP", f"{ctx_now['vwap_dist_pct']:+.2f}%")
        st.markdown("##### 📜 Activity")
        feed = _event_feed(views, t)
        if feed:
            st.markdown("<div style='font-size:13px;line-height:1.55'>" +
                        "<br>".join(feed) + "</div>", unsafe_allow_html=True)
        else:
            st.caption("No signals yet.")

    curve = []
    for opt, (tv, tr, sym) in views.items():
        if len(tv):
            curve.append(tv.set_index("datetime")[["realised", "unrealised"]])
    if curve:
        cv = pd.concat(curve, axis=1, keys=range(len(curve))).ffill().fillna(0)
        cv = pd.DataFrame({"realised": cv.xs("realised", axis=1, level=1).sum(axis=1),
                           "unrealised": cv.xs("unrealised", axis=1, level=1).sum(axis=1)})
        cv["total"] = cv["realised"] + cv["unrealised"]
        cv = cv.reset_index()
    else:
        cv = pd.DataFrame()
    p1, p2 = st.columns([1.6, 1])
    with p1:
        live_chart(C.pnl_chart(cv, x_range), key="pnl", height=260)
    with p2:
        st.markdown("##### 🧾 Order book")
        ob = _order_book(views, plan.lot_size)
        if len(ob):
            st.dataframe(ob, hide_index=True, width="stretch", height=230)
        else:
            st.caption("No orders yet.")

    if cur >= len(minutes) - 1:
        _closing_summary(views)


def _closing_summary(views: dict):
    trades = [v[1] for v in views.values() if len(v[1])]
    st.markdown("### 🔔 Market closed — day summary")
    if not trades:
        st.info("No trades today.")
        return
    tr = pd.concat(trades, ignore_index=True)
    g, c, n = tr["gross"].sum(), tr["charges"].sum(), tr["pnl"].sum()
    a, b, cc, d = st.columns(4)
    a.metric("Gross P&L", _rs(g))
    b.metric("Charges", _rs(-c))
    cc.metric("Net P&L", _rs(n))
    d.metric("Win rate", f"{(tr['pnl'] > 0).mean():.0%}", f"{len(tr)} round trips",
             delta_color="off")
    items = [charges_breakdown(cost, r.entry_price, r.exit_price, int(r.qty))
             for r in tr.itertuples()]
    br = pd.DataFrame(items).sum()
    st.caption("Where the charges went: " + " · ".join(
        f"{k} Rs.{br[k]:,.2f}" for k in ("brokerage", "stt", "exchange", "gst", "stamp", "sebi"))
        + "  (slippage is already inside the fill prices)")


session_view()
