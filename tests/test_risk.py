import pandas as pd

from src.backtest.costs import CostModel
from src.backtest.simulator import BacktestSimulator
from src.risk.risk_manager import RiskManager

RCFG = dict(stop_loss_pct=10.0, take_profit_pct=20.0,
            base_lots=1, max_lots=3, conviction_step=0.05,
            max_position_premium=100000, max_trades_per_day=4,
            daily_loss_limit=3000, no_entry_first_min=5,
            no_entry_after="15:00", min_rv_15m=0.0, max_rv_15m=10.0)

COSTS = dict(brokerage_per_order=20.0, stt_sell_pct=0.0625,
             exchange_txn_pct=0.05, gst_pct=18.0, sebi_fee_pct=0.0001,
             stamp_duty_buy_pct=0.003, slippage_pct=0.0)  # no slip → exact fills


def _day_df(prices, prob_high=True, start="2020-01-06 09:30:00",
            lows=None, highs=None):
    n = len(prices)
    return pd.DataFrame(dict(
        symbol="AAA32000CE",
        option_type="CE",
        datetime=pd.date_range(start, periods=n, freq="min"),
        close_opt=[float(p) for p in prices],
        low_opt=[float(x) for x in (lows or prices)],
        high_opt=[float(x) for x in (highs or prices)],
        min_since_open=[15.0 + i for i in range(n)],
        rv_15m=0.05,
        strike=32000.0,
        close_spot=32000.0,
    ))


def _run(df, prob, rm):
    sim = BacktestSimulator(lot_size=20, cost_model=CostModel(COSTS),
                            entry_threshold=0.60, exit_threshold=0.40,
                            max_hold_bars=30, risk_manager=rm)
    import numpy as np
    return sim, sim.run(df, np.asarray(prob, dtype=float),
                        atm_symbol="AAA32000CE", verbose=False)


def test_stop_loss_triggers_intrabar():
    # entry at 100, bar 3 low touches 89 → stop at 90 fires
    df = _day_df([100, 100, 100, 100, 100],
                 lows=[100, 100, 100, 89, 100])
    prob = [0.65, 0.65, 0.65, 0.65, 0.65]
    rm = RiskManager(RCFG, entry_threshold=0.60)
    sim, _ = _run(df, prob, rm)
    assert len(sim.trades) >= 1
    assert sim.trades.iloc[0]["exit_reason"] == "stop"
    assert abs(sim.trades.iloc[0]["exit_price"] - 90.0) < 1e-6


def test_take_profit_triggers_intrabar():
    df = _day_df([100, 100, 100, 100, 100],
                 highs=[100, 100, 100, 121, 100])
    prob = [0.65] * 5
    rm = RiskManager(RCFG, entry_threshold=0.60)
    sim, _ = _run(df, prob, rm)
    assert sim.trades.iloc[0]["exit_reason"] == "target"
    assert abs(sim.trades.iloc[0]["exit_price"] - 120.0) < 1e-6


def test_conviction_ladder_sizing():
    rm = RiskManager(RCFG, entry_threshold=0.60)
    assert rm.size_lots(0.61, 100, 20) == 1      # barely above threshold
    assert rm.size_lots(0.66, 100, 20) == 2      # +1 step
    assert rm.size_lots(0.72, 100, 20) == 3      # +2 steps
    assert rm.size_lots(0.95, 100, 20) == 3      # capped at max_lots


def test_premium_cap_limits_lots():
    cfg = dict(RCFG, max_position_premium=5000)
    rm = RiskManager(cfg, entry_threshold=0.60)
    # 3 lots would be 300*20*3 = 18000 > 5000 → forced down to 1
    assert rm.size_lots(0.95, 300, 20) == 1


def test_daily_loss_kill_switch():
    rm = RiskManager(RCFG, entry_threshold=0.60)
    rm.on_exit(-3500)                            # blows the 3000 limit
    ok, why = rm.can_enter(pd.Timestamp("2020-01-06 11:00"), 60.0, 0.05)
    assert not ok and why == "daily_loss_limit"


def test_entry_time_windows():
    rm = RiskManager(RCFG, entry_threshold=0.60)
    ok, why = rm.can_enter(pd.Timestamp("2020-01-06 09:16"), 1.0, 0.05)
    assert not ok and why == "opening_window"
    ok, why = rm.can_enter(pd.Timestamp("2020-01-06 15:10"), 355.0, 0.05)
    assert not ok and why == "late_session"


def test_vol_regime_gate():
    rm = RiskManager(RCFG, entry_threshold=0.60)
    ok, why = rm.can_enter(pd.Timestamp("2020-01-06 11:00"), 60.0, 99.0)
    assert not ok and why == "market_panic"
    cfg = dict(RCFG, min_rv_15m=0.04)
    rm2 = RiskManager(cfg, entry_threshold=0.60)
    ok, why = rm2.can_enter(pd.Timestamp("2020-01-06 11:00"), 60.0, 0.01)
    assert not ok and why == "market_dead"


def test_max_trades_per_day():
    df = _day_df([100] * 40)
    # oscillate prob: enter, exit by signal, repeatedly
    prob = ([0.65, 0.65, 0.30, 0.30] * 10)
    rm = RiskManager(RCFG, entry_threshold=0.60)
    sim, _ = _run(df, prob, rm)
    assert len(sim.trades) <= RCFG["max_trades_per_day"]
