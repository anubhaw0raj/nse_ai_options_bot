"""Bar-by-bar session replay -- the engine behind the live demo.

Two stages, mirroring what the system would do on a real trading day:

1. ``prepare_session`` -- "before the open": load the previous ``train_days``
   feature days, fit LightGBM on the first part, calibrate on the last
   ``cal_days``, search the entry threshold by simulating post-cost profit
   on the calibration days, and decide whether to trade at all (no-edge
   rule). Identical to one iteration of ``WalkForwardRunner.run``.

2. ``replay_contract`` -- "the session": walk the ATM contract minute by
   minute through the same state machine, risk gates and cost model as
   ``BacktestSimulator.run``, but record the full state at every bar
   (probability, gate verdict, open position, stop/target, unrealised and
   realised P&L). The demo UI reveals these rows one minute at a time.

Every value at minute t is computed from data at or before t, so revealing
the tape progressively is equivalent to running live. ``tests/test_replay.py``
checks that the trades produced here are identical to the backtester's.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.backtest.costs import CostModel
from src.backtest.simulator import BacktestSimulator
from src.backtest.walkforward import WalkForwardRunner
from src.config import lot_size_for
from src.models.classifier import FEATURE_COLS
from src.risk.risk_manager import RiskManager


@dataclass
class SessionPlan:
    day: date
    fit_days: list[date]
    cal_days: list[date]
    horizon: int
    lot_size: int
    n_train_rows: int = 0
    up_rate: float = float("nan")
    fit_seconds: float = 0.0
    calibrated: bool = False
    threshold: float = float("nan")
    cal_net: float = float("nan")
    skip: bool = False
    grid: list[dict] = field(default_factory=list)
    importance: pd.Series | None = None
    test_rows: int = 0
    max_hold_bars: int = 30
    exit_threshold: float = 0.45
    risk_cfg: dict | None = None


def _runner(cfg: dict, horizon: int, train_days: int, cal_days: int,
            use_risk: bool, grid: list[float] | None) -> WalkForwardRunner:
    return WalkForwardRunner(cfg, cfg.get("instrument", "banknifty"),
                             train_days=train_days, calibration_days=cal_days,
                             horizon=horizon, use_risk=use_risk,
                             threshold_grid=grid)


def prepare_session(cfg: dict, day: date, horizon: int = 15,
                    train_days: int = 13, cal_days: int = 5,
                    use_risk: bool = True, grid: list[float] | None = None,
                    return_model: bool = False):
    """Train, calibrate and choose a threshold using only days before ``day``.

    Returns (plan, test_df, prob) -- the prepared test-day frame and the
    calibrated P(UP) of every row (both None if the day has no usable data);
    with ``return_model=True`` the trained, calibrated model is appended.
    """
    r = _runner(cfg, horizon, train_days, cal_days, use_risk, grid)
    inst = r.instrument
    days = r.store.available_days(inst)
    if day not in days:
        raise ValueError(f"{day} is not in the feature store")
    idx = days.index(day)
    if idx < train_days:
        raise ValueError(f"need {train_days} earlier days before {day}")
    window = days[idx - train_days: idx]
    fit_days, cdays = (window[:-cal_days], window[-cal_days:]) if cal_days \
        else (window, [])

    plan = SessionPlan(day=day, fit_days=fit_days, cal_days=cdays,
                       horizon=r.mcfg["horizon_minutes"],
                       lot_size=lot_size_for(cfg, inst, day),
                       max_hold_bars=r.scfg["max_hold_bars"],
                       exit_threshold=r.scfg["exit_threshold"],
                       risk_cfg=r.rcfg)

    mdl = r._new_model()
    frames = [f for d in fit_days if (f := r._prepared_day(mdl, d)) is not None]
    if not frames:
        raise ValueError("no training data in the window")
    train_df = pd.concat(frames, ignore_index=True)
    mdl.feature_cols = [c for c in FEATURE_COLS if c in train_df.columns]
    plan.n_train_rows = len(train_df)
    plan.up_rate = float(train_df["target"].mean())

    t0 = time.perf_counter()
    mdl.train(train_df)
    plan.fit_seconds = time.perf_counter() - t0
    plan.importance = mdl.feature_importance()

    if cdays:
        cal_frames = [f for d in cdays if (f := r._prepared_day(mdl, d)) is not None]
        if cal_frames:
            plan.calibrated = mdl.fit_calibrator(pd.concat(cal_frames, ignore_index=True))

        # threshold search, keeping every grid point for display
        cal_data = [(d, df, mdl.predict_proba(df)) for d in cdays
                    if (df := r._prepared_day(mdl, d)) is not None]
        best_thr, best_net = r.threshold_grid[-1], float("-inf")
        for thr in r.threshold_grid:
            net, n = 0.0, 0
            for d, df, prob in cal_data:
                tr = r._simulate_day(df, prob, d, thr)
                if len(tr):
                    net += float(tr["pnl"].sum())
                    n += len(tr)
            plan.grid.append(dict(threshold=thr, net=net, trades=n))
            if net >= best_net:          # ties -> higher threshold
                best_thr, best_net = thr, net
        plan.threshold, plan.cal_net = best_thr, best_net
        plan.skip = not (best_net > 0)
    else:
        plan.threshold = r.scfg["entry_threshold"]

    test_df = r._prepared_day(mdl, day)
    if test_df is None:
        return (plan, None, None, mdl) if return_model else (plan, None, None)
    plan.test_rows = len(test_df)
    prob = mdl.predict_proba(test_df)
    return (plan, test_df, prob, mdl) if return_model else (plan, test_df, prob)


class ContractTrader:
    """The trading state machine for ONE contract, advanced one bar at a time.

    Same order of checks, fills and charges as ``BacktestSimulator.run``.
    ``last_time`` is the contract's final bar of the session (known in advance
    from the session schedule): no entry is opened on it and any open position
    is closed there, exactly as the backtester does.
    """

    def __init__(self, symbol: str, option_type: str, plan: SessionPlan,
                 cost: CostModel, threshold: float, last_time: pd.Timestamp):
        self.sym, self.opt, self.plan, self.cost = symbol, option_type, plan, cost
        self.thr, self.last_time = threshold, last_time
        self.rm = RiskManager(plan.risk_cfg, threshold) if plan.risk_cfg is not None else None
        self.lot = plan.lot_size
        self.state, self.entry_fill, self.entry_bar, self.entry_time = "OUT", 0.0, 0, None
        self.lots, self.realised, self.charges_paid, self.i = 1, 0.0, 0.0, 0
        self.rows: list[dict] = []
        self.trades: list[dict] = []

    def _close(self, bar, exit_fill, held, reason):
        qty = self.lot * self.lots
        gross = (exit_fill - self.entry_fill) * qty
        chg = self.cost.round_trip_charges(self.entry_fill, exit_fill, qty)
        net = gross - chg
        self.realised += net
        self.charges_paid += chg
        self.trades.append(dict(symbol=self.sym, option_type=self.opt,
                                entry_time=self.entry_time, exit_time=bar["datetime"],
                                entry_price=self.entry_fill, exit_price=exit_fill,
                                bars_held=held, lots=self.lots, qty=qty, gross=gross,
                                charges=chg, pnl=net, exit_reason=reason))
        if self.rm is not None:
            self.rm.on_exit(net)
        self.state = "OUT"
        return reason

    def step(self, bar, p: float) -> dict:
        """Process one bar of this contract with its model probability ``p``."""
        i, cost, rm = self.i, self.cost, self.rm
        px = float(bar["close_opt"])
        is_last = bar["datetime"] >= self.last_time
        event, gate = "", ""

        if self.state == "OUT":
            if p > self.thr and not is_last:
                ok = True
                if rm is not None:
                    ok, gate = rm.can_enter(bar["datetime"], float(bar["min_since_open"]),
                                            float(bar["rv_15m"]))
                    if ok:
                        self.lots = rm.size_lots(p, px, self.lot)
                else:
                    self.lots = 1
                if ok:
                    self.state = "IN"
                    self.entry_fill = cost.buy_fill(px)
                    self.entry_bar, self.entry_time = i, bar["datetime"]
                    event = "ENTRY"
        else:
            held = i - self.entry_bar
            done = False
            if rm is not None:
                stop_px = self.entry_fill * (1 - rm.stop_loss_pct)
                tp_px = self.entry_fill * (1 + rm.take_profit_pct)
                lo, hi = float(bar["low_opt"]), float(bar["high_opt"])
                if lo == lo and lo <= stop_px:
                    event = self._close(bar, cost.sell_fill(stop_px), held, "stop"); done = True
                elif hi == hi and hi >= tp_px:
                    event = self._close(bar, cost.sell_fill(tp_px), held, "target"); done = True
            if not done:
                if p < self.plan.exit_threshold:
                    event = self._close(bar, cost.sell_fill(px), held, "signal")
                elif held >= self.plan.max_hold_bars:
                    event = self._close(bar, cost.sell_fill(px), held, "time")
                elif is_last:
                    event = self._close(bar, cost.sell_fill(px), held, "eod")

        in_pos = self.state == "IN"
        row = dict(
            datetime=bar["datetime"], open=bar["open_opt"], high=bar["high_opt"],
            low=bar["low_opt"], close=px, volume=bar["volume"], oi=bar["oi"],
            iv=bar["IV"], delta=bar["delta"], prob=p, state=self.state, event=event,
            gate=gate, lots=self.lots if in_pos else 0,
            entry_fill=self.entry_fill if in_pos else np.nan,
            stop=self.entry_fill * (1 - rm.stop_loss_pct) if (in_pos and rm) else np.nan,
            target=self.entry_fill * (1 + rm.take_profit_pct) if (in_pos and rm) else np.nan,
            bars_held=(i - self.entry_bar) if in_pos else 0,
            unrealised=((cost.sell_fill(px) - self.entry_fill) * self.lot * self.lots)
            if in_pos else 0.0,
            realised=self.realised, charges=self.charges_paid,
            trades_done=len(self.trades),
            day_loss_used=-(rm.day_net) if rm else 0.0)
        self.rows.append(row)
        self.i += 1
        return row

    def tape(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)

    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.trades)


def replay_contract(test_df: pd.DataFrame, prob: np.ndarray, option_type: str,
                    plan: SessionPlan, cost: CostModel,
                    threshold: float | None = None
                    ) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    """Whole-day tape for the ATM contract of one option type (batch form).

    Runs ``ContractTrader`` over every bar; returns (tape, trades, symbol).
    """
    thr = plan.threshold if threshold is None else threshold
    df = test_df.copy().reset_index(drop=True)
    df["prob_up"] = np.asarray(prob, dtype="float32")
    sym = BacktestSimulator.find_atm_symbol(df, option_type)
    if sym is None:
        return pd.DataFrame(), pd.DataFrame(), None
    bars = df[df["symbol"] == sym].sort_values("datetime").reset_index(drop=True)
    trader = ContractTrader(sym, option_type, plan, cost, thr, bars["datetime"].iloc[-1])
    for _, bar in bars.iterrows():
        trader.step(bar, float(bar["prob_up"]))
    return trader.tape(), trader.trades_frame(), sym


class LiveSession:
    """Runs a prepared day minute by minute, scoring each minute as it arrives.

    At every new minute the trained model scores that minute's whole option
    chain (features come from the feature store, which is built causally),
    then the ATM call and put traders take one step. Nothing after the current
    minute is ever touched. ``tests/test_replay.py`` checks that stepping
    through a whole day gives exactly the batch result.
    """

    def __init__(self, plan: SessionPlan, test_df: pd.DataFrame, model,
                 cost: CostModel, trade: bool = True):
        self.plan, self.model, self.cost = plan, model, cost
        df = test_df.sort_values(["datetime", "symbol"]).reset_index(drop=True)
        self.by_minute = {t: g for t, g in df.groupby("datetime", sort=True)}
        self.minutes = list(self.by_minute)
        self.traders: dict[str, ContractTrader] = {}
        thr = plan.threshold if trade else 2.0          # 2.0 = never enter
        for opt in ("CE", "PE"):
            sym = BacktestSimulator.find_atm_symbol(df, opt)
            if sym is not None:
                last = df.loc[df["symbol"] == sym, "datetime"].max()
                self.traders[opt] = ContractTrader(sym, opt, plan, cost, thr, last)
        self.scored: list[pd.DataFrame] = []           # chain probabilities so far
        self.pos = 0                                    # minutes processed
        self.score_ms = 0.0

    @property
    def now(self) -> pd.Timestamp | None:
        return self.minutes[self.pos - 1] if self.pos else None

    def advance_to(self, t: pd.Timestamp) -> int:
        """Process every minute up to and including ``t``; returns minutes done."""
        n = 0
        while self.pos < len(self.minutes) and self.minutes[self.pos] <= t:
            minute = self.minutes[self.pos]
            rows = self.by_minute[minute]
            t0 = time.perf_counter()
            p = self.model.predict_proba(rows)
            self.score_ms = (time.perf_counter() - t0) * 1000
            chain = rows[["symbol", "datetime"]].copy()
            chain["prob"] = p
            self.scored.append(chain)
            for tr in self.traders.values():
                hit = np.flatnonzero(rows["symbol"].to_numpy() == tr.sym)
                if len(hit):
                    tr.step(rows.iloc[hit[0]], float(p[hit[0]]))
            self.pos += 1
            n += 1
        return n

    def chain_probs(self) -> pd.DataFrame:
        return (pd.concat(self.scored, ignore_index=True) if self.scored
                else pd.DataFrame(columns=["symbol", "datetime", "prob"]))


def charges_breakdown(cost: CostModel, buy: float, sell: float, qty: int) -> dict:
    """Itemised round-trip charges (same formula as CostModel)."""
    bt, st = buy * qty, sell * qty
    both = bt + st
    brk = 2 * cost.brokerage
    txn, sebi = both * cost.txn, both * cost.sebi
    d = dict(brokerage=brk, stt=st * cost.stt_sell, exchange=txn, sebi=sebi,
             stamp=bt * cost.stamp_buy, gst=(brk + txn + sebi) * cost.gst)
    d["total"] = sum(d.values())
    return d
