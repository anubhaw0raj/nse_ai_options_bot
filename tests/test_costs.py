from src.backtest.costs import CostModel

CFG = dict(brokerage_per_order=20.0, stt_sell_pct=0.0625,
           exchange_txn_pct=0.05, gst_pct=18.0, sebi_fee_pct=0.0001,
           stamp_duty_buy_pct=0.003, slippage_pct=0.25)


def test_slippage_works_against_you():
    c = CostModel(CFG)
    assert c.buy_fill(100.0) > 100.0
    assert c.sell_fill(100.0) < 100.0


def test_flat_price_round_trip_loses_money():
    c = CostModel(CFG)
    lot = 25
    buy = c.buy_fill(200.0)
    sell = c.sell_fill(200.0)
    gross = (sell - buy) * lot
    net = gross - c.round_trip_charges(buy, sell, lot)
    assert net < 0, "zero-move trade must be a net loss after costs"


def test_charges_scale_with_turnover():
    c = CostModel(CFG)
    small = c.round_trip_charges(100, 100, 25)
    big = c.round_trip_charges(500, 500, 25)
    assert big > small > 40  # at least 2× brokerage


def test_cost_hurdle_positive():
    c = CostModel(CFG)
    assert c.cost_hurdle_pct(200.0, 25) > 0.5  # slippage alone is 0.5%
