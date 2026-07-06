"""Single-contract position state machine with realistic costs.

Entry : P(UP) > entry_threshold while flat
Exit  : P(UP) < exit_threshold, max holding time, or end of day
Fills : slippage-adjusted via CostModel; PnL reported NET of all charges.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.backtest.costs import CostModel

OUTPUT_DIR = Path("reports/charts")


class BacktestSimulator:
    def __init__(self, lot_size: int, cost_model: CostModel,
                 entry_threshold: float = 0.55, exit_threshold: float = 0.45,
                 max_hold_bars: int = 10):
        self.lot_size = lot_size
        self.cost = cost_model
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.max_hold_bars = max_hold_bars
        self._stats: dict = {}
        self._trades_df = pd.DataFrame()

    # ── ATM contract selection ─────────────────────────────────────────────

    @staticmethod
    def find_atm_symbol(df: pd.DataFrame, option_type: str = "CE") -> str | None:
        sub = df[df["option_type"] == option_type]
        if sub.empty:
            return None
        spot_open = sub.sort_values("datetime")["close_spot"].iloc[0]
        strikes = sub["strike"].unique()
        atm_strike = strikes[np.argmin(np.abs(strikes - spot_open))]
        return sub[sub["strike"] == atm_strike]["symbol"].iloc[0]

    # ── State-machine run ──────────────────────────────────────────────────

    def run(self, test_df: pd.DataFrame, prob_up: np.ndarray,
            atm_symbol: str, verbose: bool = True) -> pd.DataFrame:
        df = test_df.copy().reset_index(drop=True)
        df["prob_up"] = prob_up.astype("float32")

        df_sim = df[df["symbol"] == atm_symbol].copy()
        df_sim = df_sim.sort_values("datetime").reset_index(drop=True)
        if df_sim.empty:
            raise ValueError(f"Symbol '{atm_symbol}' not found in test data.")

        n = len(df_sim)
        df_sim["signal"] = 0
        df_sim["entry"] = False
        df_sim["exit_trade"] = False
        df_sim["pnl"] = 0.0

        state, entry_fill, entry_bar, entry_time = "OUT", 0.0, 0, None
        trades = []

        for i in range(n):
            p = float(df_sim.at[i, "prob_up"])
            px = float(df_sim.at[i, "close_opt"])

            if state == "OUT":
                if p > self.entry_threshold and i < n - 1:
                    state = "IN"
                    entry_fill = self.cost.buy_fill(px)
                    entry_bar, entry_time = i, df_sim.at[i, "datetime"]
                    df_sim.at[i, "entry"] = True
                    df_sim.at[i, "signal"] = 1

            elif state == "IN":
                df_sim.at[i, "signal"] = 1
                bars_held = i - entry_bar
                if (p < self.exit_threshold
                        or bars_held >= self.max_hold_bars
                        or i == n - 1):
                    exit_fill = self.cost.sell_fill(px)
                    gross = (exit_fill - entry_fill) * self.lot_size
                    charges = self.cost.round_trip_charges(
                        entry_fill, exit_fill, self.lot_size)
                    net = gross - charges
                    df_sim.at[i, "pnl"] = net
                    df_sim.at[i, "exit_trade"] = True
                    trades.append(dict(
                        symbol=atm_symbol,
                        option_type=df_sim.at[i, "option_type"],
                        entry_time=entry_time,
                        exit_time=df_sim.at[i, "datetime"],
                        entry_price=entry_fill, exit_price=exit_fill,
                        bars_held=bars_held,
                        gross=gross, charges=charges, pnl=net,
                    ))
                    state = "OUT"

        df_sim["cumulative_pnl"] = df_sim["pnl"].cumsum().astype("float32")

        trades_df = pd.DataFrame(trades)
        n_trades = len(trades_df)
        winners = int((trades_df["pnl"] > 0).sum()) if n_trades else 0
        total_net = float(df_sim["cumulative_pnl"].iloc[-1])
        total_gross = float(trades_df["gross"].sum()) if n_trades else 0.0
        total_chg = float(trades_df["charges"].sum()) if n_trades else 0.0

        self._stats = dict(
            n_trades=n_trades,
            win_rate=winners / n_trades * 100 if n_trades else 0,
            total_pnl=total_net,
            total_gross=total_gross,
            total_charges=total_chg,
            max_dd=self._max_drawdown(df_sim["cumulative_pnl"].values),
            avg_win=float(trades_df.loc[trades_df["pnl"] > 0, "pnl"].mean())
            if winners else 0.0,
            avg_loss=float(trades_df.loc[trades_df["pnl"] <= 0, "pnl"].mean())
            if n_trades - winners else 0.0,
            avg_hold=float(trades_df["bars_held"].mean()) if n_trades else 0.0,
            contract=atm_symbol,
        )
        self._trades_df = trades_df

        if verbose:
            s = self._stats
            print(f"\n  === Backtest ({atm_symbol}, lot={self.lot_size}) ===")
            print(f"    Trades       : {s['n_trades']}   "
                  f"Win rate: {s['win_rate']:.1f}%   "
                  f"Avg hold: {s['avg_hold']:.1f} bars")
            print(f"    Gross PnL    : Rs.{s['total_gross']:,.0f}")
            print(f"    Charges      : Rs.{s['total_charges']:,.0f}")
            print(f"    NET PnL      : Rs.{s['total_pnl']:,.0f}   "
                  f"Max DD: Rs.{s['max_dd']:,.0f}")
        return df_sim

    @property
    def trades(self) -> pd.DataFrame:
        return self._trades_df

    @property
    def stats(self) -> dict:
        return self._stats

    # ── Chart ──────────────────────────────────────────────────────────────

    def plot(self, result_df: pd.DataFrame, save_path: str | None = None,
             title_extra: str = "", metrics: dict | None = None) -> str:
        BG, PANEL, GRID = "#0d1117", "#161b22", "#30363d"
        TEXT, DIM = "#e6edf3", "#8b949e"

        plt.rcParams.update({
            "figure.facecolor": BG, "axes.facecolor": PANEL,
            "axes.edgecolor": GRID, "axes.labelcolor": TEXT,
            "xtick.color": DIM, "ytick.color": DIM,
            "grid.color": GRID, "text.color": TEXT,
            "axes.titlecolor": TEXT, "axes.titleweight": "bold",
            "axes.titlesize": 11, "font.family": "monospace",
        })

        symbol = result_df["symbol"].iloc[0]
        test_date = str(result_df["datetime"].dt.date.iloc[0])
        acc = metrics.get("Accuracy", float("nan")) if metrics else float("nan")

        fig = plt.figure(figsize=(22, 14), facecolor=BG)
        fig.suptitle(
            f"NSE AI Options Bot — {symbol}  |  Test: {test_date}  |  "
            f"Model Acc: {acc:.1f}%  {title_extra}",
            fontsize=13, fontweight="bold", color=TEXT, y=0.99)

        gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.50, wspace=0.30,
                               top=0.93, bottom=0.08, left=0.07, right=0.97)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])

        times = result_df["datetime"]
        close_opt = result_df["close_opt"]
        prob_up = result_df["prob_up"]
        cum_pnl = result_df["cumulative_pnl"]
        in_pos = result_df["signal"] == 1
        entries = result_df["entry"]
        exits = result_df["exit_trade"]

        # Panel 1: option price + trades
        ax1.set_title("Option Price  (Entry ▲  Exit ▼)", pad=8)
        ax1.fill_between(times, close_opt, alpha=0.18, color="#e3b341")
        ax1.plot(times, close_opt, color="#e3b341", linewidth=1.8)
        ax1.fill_between(times, close_opt, alpha=0.35, color="#bc8cff",
                         where=in_pos.values, label="Holding")
        ax1.scatter(times[entries.values], close_opt[entries.values],
                    marker="^", color="#39d353", s=120, zorder=8, label="Entry")
        ax1.scatter(times[exits.values], close_opt[exits.values],
                    marker="v", color="#f85149", s=120, zorder=8, label="Exit")
        ax1.set_ylabel("Premium (Rs.)")
        ax1.legend(loc="upper left", fontsize=8, facecolor=PANEL, edgecolor=GRID)

        if "close_spot" in result_df.columns:
            ax1r = ax1.twinx()
            ax1r.plot(times, result_df["close_spot"], color="#58a6ff",
                      linewidth=1.4, alpha=0.8)
            ax1r.set_ylabel("Spot", color="#58a6ff")
            ax1r.tick_params(axis="y", colors="#58a6ff")

        # Panel 2: model confidence
        ax2.set_title("Model Confidence  P(UP in 5 min)", pad=8)
        ax2.fill_between(times, prob_up, self.entry_threshold,
                         where=(prob_up > self.entry_threshold),
                         color="#39d353", alpha=0.20, label="BUY zone")
        ax2.fill_between(times, prob_up, self.exit_threshold,
                         where=(prob_up < self.exit_threshold),
                         color="#f85149", alpha=0.20, label="EXIT zone")
        ax2.plot(times, prob_up, color="#ffa657", linewidth=2.4, zorder=5)
        ax2.axhline(self.entry_threshold, color="#39d353", ls="--", lw=1.5)
        ax2.axhline(self.exit_threshold, color="#f85149", ls="--", lw=1.5)
        ax2.axhline(0.5, color=DIM, lw=0.8, ls=":", alpha=0.5)
        ax2.set_ylim(-0.02, 1.02)
        ax2.legend(loc="upper left", fontsize=8, facecolor=PANEL, edgecolor=GRID)

        # Panel 3: cumulative NET PnL
        ax3.set_title("Cumulative NET P&L (Rs., after all costs)", pad=8)
        ax3.fill_between(times, np.where(cum_pnl >= 0, cum_pnl, 0), 0,
                         color="#3fb950", alpha=0.4)
        ax3.fill_between(times, np.where(cum_pnl < 0, cum_pnl, 0), 0,
                         color="#f85149", alpha=0.4)
        ax3.plot(times, cum_pnl, color="#e3b341", linewidth=2.4)
        ax3.axhline(0, color=DIM, lw=1, ls="--", alpha=0.6)
        ax3.set_ylabel("Net PnL (Rs.)")

        # Panel 4: per-trade distribution
        ax4.set_title("Per-Trade NET P&L (Rs.)", pad=8)
        if len(self._trades_df) > 1:
            pnl = self._trades_df["pnl"].values
            wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
            bins = np.linspace(pnl.min() - 1, pnl.max() + 1,
                               min(35, max(8, len(pnl) // 2)))
            if len(wins):
                ax4.hist(wins, bins=bins, color="#3fb950", alpha=0.8,
                         label=f"Wins ({len(wins)})", edgecolor=PANEL)
            if len(losses):
                ax4.hist(losses, bins=bins, color="#f85149", alpha=0.8,
                         label=f"Losses ({len(losses)})", edgecolor=PANEL)
            ax4.axvline(0, color=DIM, lw=1.2, ls="--")
            ax4.legend(fontsize=8, facecolor=PANEL, edgecolor=GRID)
        else:
            ax4.text(0.5, 0.5, f"{len(self._trades_df)} trade(s)",
                     transform=ax4.transAxes, ha="center", color=DIM)
        ax4.set_xlabel("PnL per trade (Rs.)")

        for ax in (ax1, ax2, ax3):
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=30,
                     ha="right", fontsize=8)
        for ax in (ax1, ax2, ax3, ax4):
            ax.grid(True, alpha=0.35, linewidth=0.5)

        s = self._stats
        banner = (f"Trades: {s['n_trades']}  |  Win: {s['win_rate']:.1f}%  |  "
                  f"Gross: Rs.{s['total_gross']:,.0f}  |  "
                  f"Charges: Rs.{s['total_charges']:,.0f}  |  "
                  f"NET: Rs.{s['total_pnl']:,.0f}  |  "
                  f"Max DD: Rs.{s['max_dd']:,.0f}  |  Lot: {self.lot_size}")
        fig.text(0.5, 0.01, banner, ha="center", fontsize=9, color="#58a6ff",
                 bbox=dict(boxstyle="round,pad=0.4", facecolor=PANEL,
                           edgecolor=GRID, alpha=0.95))

        if save_path is None:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            save_path = str(OUTPUT_DIR /
                            f"sim_{symbol.replace('/', '-')}_{test_date}.png")
        plt.savefig(save_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        return save_path

    @staticmethod
    def _max_drawdown(cum_pnl: np.ndarray) -> float:
        if len(cum_pnl) == 0:
            return 0.0
        peak = np.maximum.accumulate(cum_pnl)
        return float((peak - cum_pnl).max())
