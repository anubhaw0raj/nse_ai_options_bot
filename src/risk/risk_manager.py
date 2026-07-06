"""Phase-4 risk layer: entry gates, position sizing, daily limits.

One RiskManager instance governs ONE contract for ONE trading day
(the walk-forward runs CE and PE sequentially, so portfolio-level
interleaved limits arrive with the Phase-6 orchestrator).

Gates (checked at entry time):
  - max trades per day, daily loss kill-switch
  - no-entry windows (opening minutes, last part of the session)
  - volatility regime band on 15-minute realized vol (too dead → no move
    to capture; too wild → spreads and slippage swamp the edge)

Sizing (conviction ladder):
  lots = base_lots + floor((P_up − entry_threshold) / conviction_step)
  capped by max_lots and by max_position_premium. Calibrated probabilities
  make this meaningful: deeper conviction → more lots → the flat brokerage
  is amortized over a larger position.
"""

from datetime import time as dtime


class RiskManager:
    def __init__(self, risk_cfg: dict, entry_threshold: float):
        c = risk_cfg
        self.stop_loss_pct = float(c.get("stop_loss_pct", 12.0)) / 100
        self.take_profit_pct = float(c.get("take_profit_pct", 24.0)) / 100
        self.base_lots = int(c.get("base_lots", 1))
        self.max_lots = int(c.get("max_lots", 3))
        self.conviction_step = float(c.get("conviction_step", 0.06))
        self.max_position_premium = float(c.get("max_position_premium", 20000))
        self.max_trades_per_day = int(c.get("max_trades_per_day", 4))
        self.daily_loss_limit = float(c.get("daily_loss_limit", 3000))
        self.no_entry_first_min = float(c.get("no_entry_first_min", 5))
        hh, mm = str(c.get("no_entry_after", "15:00")).split(":")
        self.no_entry_after = dtime(int(hh), int(mm))
        self.min_rv = float(c.get("min_rv_15m", 0.0))
        self.max_rv = float(c.get("max_rv_15m", 1e9))
        self.entry_threshold = entry_threshold

        self.day_net = 0.0
        self.n_trades = 0

    # ── Entry gate ─────────────────────────────────────────────────────────

    def can_enter(self, ts, min_since_open, rv_15m) -> tuple[bool, str]:
        if self.n_trades >= self.max_trades_per_day:
            return False, "max_trades"
        if self.day_net <= -self.daily_loss_limit:
            return False, "daily_loss_limit"
        if min_since_open == min_since_open and \
                min_since_open < self.no_entry_first_min:
            return False, "opening_window"
        if ts is not None and ts.time() >= self.no_entry_after:
            return False, "late_session"
        if rv_15m == rv_15m and rv_15m is not None:  # NaN-safe
            if rv_15m < self.min_rv:
                return False, "market_dead"
            if rv_15m > self.max_rv:
                return False, "market_panic"
        return True, "ok"

    # ── Position sizing ────────────────────────────────────────────────────

    def size_lots(self, prob_up: float, premium: float, lot_size: int) -> int:
        extra = int(max(0.0, prob_up - self.entry_threshold)
                    / self.conviction_step)
        lots = min(self.base_lots + extra, self.max_lots)
        while lots > 1 and premium * lot_size * lots > self.max_position_premium:
            lots -= 1
        return max(lots, 1)

    # ── Bookkeeping ────────────────────────────────────────────────────────

    def on_exit(self, net_pnl: float):
        self.day_net += net_pnl
        self.n_trades += 1
