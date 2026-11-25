"""The demo replay must reproduce the backtester trade-for-trade.

This is the Phase-6 acceptance rule: replaying a day through the live loop
must give the same result as the batch backtest for that day. Uses the real
feature store, so it is skipped on machines without data/features.
"""

from datetime import date

import pytest

from src.backtest.costs import CostModel
from src.backtest.simulator import BacktestSimulator
from src.config import load_config
from src.features.store import FeatureStore
from src.live.replay import prepare_session, replay_contract
from src.risk.risk_manager import RiskManager

DAYS = [date(2021, 3, 12), date(2020, 3, 16)]


def _have_store(cfg):
    st = FeatureStore(cfg["data"]["features_dir"])
    return all(st.has_day("banknifty", d) for d in DAYS)


@pytest.mark.parametrize("day", DAYS)
def test_replay_matches_backtester(day):
    cfg = load_config()
    if not _have_store(cfg):
        pytest.skip("feature store not available")
    plan, test_df, prob = prepare_session(cfg, day)
    assert test_df is not None
    cost = CostModel(cfg["costs"])
    for opt in ("CE", "PE"):
        tape, trades, sym = replay_contract(test_df, prob, opt, plan, cost)
        sim = BacktestSimulator(
            lot_size=plan.lot_size, cost_model=cost,
            entry_threshold=plan.threshold, exit_threshold=plan.exit_threshold,
            max_hold_bars=plan.max_hold_bars,
            risk_manager=RiskManager(plan.risk_cfg, plan.threshold))
        sim.run(test_df, prob, atm_symbol=sym, verbose=False)
        ref = sim.trades
        assert len(trades) == len(ref)
        if len(ref):
            assert list(trades["exit_reason"]) == list(ref["exit_reason"])
            assert trades["pnl"].sum() == pytest.approx(ref["pnl"].sum(), abs=1e-6)
        assert tape["realised"].iloc[-1] == pytest.approx(
            ref["pnl"].sum() if len(ref) else 0.0, abs=1e-6)


@pytest.mark.parametrize("day", DAYS)
def test_live_session_matches_batch(day):
    """Scoring minute by minute must give the same tape as scoring the day at once."""
    from src.live.replay import LiveSession
    cfg = load_config()
    if not _have_store(cfg):
        pytest.skip("feature store not available")
    plan, test_df, prob, model = prepare_session(cfg, day, return_model=True)
    cost = CostModel(cfg["costs"])
    live = LiveSession(plan, test_df, model, cost)
    half = live.minutes[len(live.minutes) // 2]
    live.advance_to(half)                                # pause mid-day ...
    assert live.now == half
    live.advance_to(live.minutes[-1])                    # ... then finish
    for opt, trader in live.traders.items():
        tape, trades, sym = replay_contract(test_df, prob, opt, plan, cost)
        assert trader.sym == sym
        got = trader.tape()
        assert len(got) == len(tape)
        assert got["prob"].to_numpy() == pytest.approx(tape["prob"].to_numpy(), abs=1e-6)
        assert list(got["event"]) == list(tape["event"])
        assert got["realised"].iloc[-1] == pytest.approx(tape["realised"].iloc[-1], abs=1e-6)
