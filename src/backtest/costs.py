"""Indian options transaction-cost model (long options, buy → sell round trip).

Components (configurable in config/settings.yaml → costs):
  - flat brokerage per executed order (discount broker style)
  - STT on sell-side premium turnover
  - exchange transaction charges on both sides
  - SEBI turnover fee, stamp duty (buy side), GST on fees
  - slippage applied directly to the fill price (per side, % of premium)

Every simulated fill in the backtester goes through this model so reported
PnL is NET of what the trade would actually cost.
"""


class CostModel:
    def __init__(self, cost_cfg: dict):
        self.brokerage = float(cost_cfg.get("brokerage_per_order", 20.0))
        self.stt_sell = float(cost_cfg.get("stt_sell_pct", 0.0625)) / 100
        self.txn = float(cost_cfg.get("exchange_txn_pct", 0.05)) / 100
        self.gst = float(cost_cfg.get("gst_pct", 18.0)) / 100
        self.sebi = float(cost_cfg.get("sebi_fee_pct", 0.0001)) / 100
        self.stamp_buy = float(cost_cfg.get("stamp_duty_buy_pct", 0.003)) / 100
        self.slippage = float(cost_cfg.get("slippage_pct", 0.25)) / 100

    # ── Fill prices (slippage works against you on both sides) ────────────
    def buy_fill(self, price: float) -> float:
        return price * (1 + self.slippage)

    def sell_fill(self, price: float) -> float:
        return price * (1 - self.slippage)

    # ── Statutory + broker charges for one round trip ─────────────────────
    def round_trip_charges(self, buy_price: float, sell_price: float,
                           lot_size: int) -> float:
        buy_turn = buy_price * lot_size
        sell_turn = sell_price * lot_size
        both = buy_turn + sell_turn

        brokerage = 2 * self.brokerage
        stt = sell_turn * self.stt_sell
        txn = both * self.txn
        sebi = both * self.sebi
        stamp = buy_turn * self.stamp_buy
        gst = (brokerage + txn + sebi) * self.gst
        return brokerage + stt + txn + sebi + stamp + gst

    def cost_hurdle_pct(self, price: float, lot_size: int) -> float:
        """Round-trip cost as % of position value — the move needed to break even."""
        if price <= 0:
            return 0.0
        charges = self.round_trip_charges(price, price, lot_size)
        slip = 2 * self.slippage * 100
        return charges / (price * lot_size) * 100 + slip
