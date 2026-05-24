"""
src/simulator.py
----------------
Realistic single-ATM-contract backtest with a POSITION STATE MACHINE.

Entry rules:
  - Enter LONG when P(UP) > entry_threshold (default 0.52)
  - Must not already be in a position

Exit rules:
  - Exit when P(UP) drops below exit_threshold (default 0.48)
  - OR when position has been held for max_hold_bars (default 10 min)
  - OR at end of day

PnL: (exit_price - entry_price) * lot_size  — REAL price difference, not estimate.

Chart:
  [TL] ATM CE price + spot + trade entry/exit markers
  [TR] P(UP) confidence curve vs threshold (clear amber line on dark panel)
  [BL] Cumulative PnL with trade markers
  [BR] Trade P&L distribution
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.dates as mdates
from pathlib import Path


LOT_SIZE        = 25
ENTRY_THRESHOLD = 0.52    # enter long when P(UP) > this
EXIT_THRESHOLD  = 0.48    # exit when P(UP) drops below this
MAX_HOLD_BARS   = 10      # max minutes to hold a position
OUTPUT_DIR      = Path("data/processed_features")


class BacktestSimulator:
    def __init__(self, lot_size=LOT_SIZE,
                 entry_threshold=ENTRY_THRESHOLD,
                 exit_threshold=EXIT_THRESHOLD,
                 max_hold_bars=MAX_HOLD_BARS):
        self.lot_size        = lot_size
        self.entry_threshold = entry_threshold
        self.exit_threshold  = exit_threshold
        self.max_hold_bars   = max_hold_bars
        self._stats          = {}

    # ── ATM symbol selection ───────────────────────────────────────────────

    @staticmethod
    def find_atm_symbol(df: pd.DataFrame, option_type: str = "CE") -> str:
        sub = df[df["option_type"] == option_type].copy()
        if sub.empty:
            raise ValueError(f"No {option_type} options in test data.")
        spot_open  = sub.sort_values("datetime")["close_spot"].iloc[0]
        strikes    = sub["strike"].unique()
        atm_strike = strikes[np.argmin(np.abs(strikes - spot_open))]
        chosen     = sub[sub["strike"] == atm_strike]["symbol"].unique()[0]
        print(f"  ATM symbol : {chosen}  "
              f"(strike={atm_strike:.0f}, spot_open={spot_open:.0f})")
        return chosen

    # ── State machine backtest ─────────────────────────────────────────────

    def run(self, test_df: pd.DataFrame, prob_up: np.ndarray,
            atm_symbol: str = None) -> pd.DataFrame:
        """
        State machine simulation on a single ATM contract.

        Parameters
        ----------
        test_df    : near-ATM test DataFrame (with 'target', 'close_opt', etc.)
        prob_up    : model P(price UP) for each row in test_df (same length)
        atm_symbol : restrict to this one contract

        Returns
        -------
        df_sim with added columns: prob_up, signal, trade_id, entry, exit, pnl, cumulative_pnl
        """
        df = test_df.copy().reset_index(drop=True)
        df["prob_up"] = prob_up.astype("float32")

        # Filter to ATM contract
        if atm_symbol:
            df_sim = df[df["symbol"] == atm_symbol].copy().reset_index(drop=True)
        else:
            df_sim = df.copy()

        if df_sim.empty:
            raise ValueError(f"Symbol '{atm_symbol}' not found in test data.")

        n_rows = len(df_sim)
        print(f"  ATM contract rows: {n_rows}")

        # Initialise columns
        df_sim["signal"]       = 0       # 1 = in position this bar
        df_sim["trade_id"]     = -1
        df_sim["entry"]        = False
        df_sim["exit_trade"]   = False
        df_sim["pnl"]          = 0.0
        df_sim["cumulative_pnl"] = 0.0

        # ── State machine ─────────────────────────────────────────────────
        state         = "OUT"
        entry_price   = 0.0
        entry_bar     = 0
        trade_id      = 0
        trades        = []   # list of dicts

        for i in range(n_rows):
            p  = float(df_sim.at[i, "prob_up"])
            px = float(df_sim.at[i, "close_opt"])

            if state == "OUT":
                if p > self.entry_threshold:
                    # ENTER long
                    state       = "IN"
                    entry_price = px
                    entry_bar   = i
                    df_sim.at[i, "entry"]    = True
                    df_sim.at[i, "signal"]   = 1
                    df_sim.at[i, "trade_id"] = trade_id

            elif state == "IN":
                df_sim.at[i, "signal"]   = 1
                df_sim.at[i, "trade_id"] = trade_id
                bars_held = i - entry_bar

                exit_now = (
                    p < self.exit_threshold         # model turned bearish
                    or bars_held >= self.max_hold_bars  # max hold exceeded
                    or i == n_rows - 1              # end of day
                )
                if exit_now:
                    exit_price = px
                    pnl        = (exit_price - entry_price) * self.lot_size
                    df_sim.at[i, "pnl"]         = pnl
                    df_sim.at[i, "exit_trade"]  = True
                    trades.append(dict(
                        trade_id=trade_id,
                        entry_bar=entry_bar,
                        exit_bar=i,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        bars_held=bars_held,
                        pnl=pnl,
                    ))
                    trade_id += 1
                    state = "OUT"

        df_sim["cumulative_pnl"] = df_sim["pnl"].cumsum().astype("float32")

        # ── Stats ─────────────────────────────────────────────────────────
        trades_df = pd.DataFrame(trades)
        n_trades  = len(trades_df)
        winners   = int((trades_df["pnl"] > 0).sum()) if n_trades else 0
        win_rate  = winners / n_trades * 100 if n_trades else 0
        total_pnl = float(df_sim["cumulative_pnl"].iloc[-1])
        max_dd    = self._max_drawdown(df_sim["cumulative_pnl"].values)
        avg_win   = float(trades_df.loc[trades_df["pnl"] > 0,  "pnl"].mean()) if winners else 0
        avg_loss  = float(trades_df.loc[trades_df["pnl"] <= 0, "pnl"].mean()) if (n_trades-winners) else 0
        avg_hold  = float(trades_df["bars_held"].mean()) if n_trades else 0

        print("\n  === Backtest Results (State Machine, Single ATM CE) ===")
        print(f"    Contract     : {atm_symbol or 'All'}")
        print(f"    Total trades : {n_trades}")
        print(f"    Win rate     : {win_rate:.1f}%")
        print(f"    Avg hold     : {avg_hold:.1f} bars")
        print(f"    Avg win      : Rs.{avg_win:,.1f}")
        print(f"    Avg loss     : Rs.{avg_loss:,.1f}")
        print(f"    Total PnL    : Rs.{total_pnl:,.0f}  (real price diff x lot)")
        print(f"    Max Drawdown : Rs.{max_dd:,.0f}")

        self._stats = dict(
            n_trades=n_trades, win_rate=win_rate, total_pnl=total_pnl,
            max_dd=max_dd, avg_win=avg_win, avg_loss=avg_loss,
            avg_hold=avg_hold, contract=atm_symbol or "All",
        )
        self._trades_df = trades_df
        return df_sim

    # ── Chart ──────────────────────────────────────────────────────────────

    def plot(self, result_df: pd.DataFrame,
             save_path: str = None, train_days: list = None,
             metrics: dict = None) -> str:

        BG    = "#0d1117"
        PANEL = "#161b22"
        GRID  = "#30363d"
        TEXT  = "#e6edf3"
        DIM   = "#8b949e"

        plt.rcParams.update({
            "figure.facecolor": BG,   "axes.facecolor": PANEL,
            "axes.edgecolor": GRID,   "axes.labelcolor": TEXT,
            "xtick.color": DIM,       "ytick.color": DIM,
            "grid.color": GRID,       "text.color": TEXT,
            "axes.titlecolor": TEXT,  "axes.titleweight": "bold",
            "axes.titlesize": 11,     "font.family": "monospace",
        })

        symbol    = result_df["symbol"].iloc[0]
        test_date = str(result_df["datetime"].dt.date.iloc[0])
        train_n   = len(train_days) if train_days else "?"
        acc       = metrics.get("Accuracy", 0) if metrics else 0

        fig = plt.figure(figsize=(22, 14), facecolor=BG)
        fig.suptitle(
            f"NSE AI Options Bot  --  BankNifty Backtest  (GBM Classifier)\n"
            f"Train: {train_n} days (Jan 1-9, 2020)   |   Test: {test_date}   |   "
            f"{symbol}   |   Model Acc: {acc:.1f}%",
            fontsize=13, fontweight="bold", color=TEXT, y=0.99,
        )

        gs = gridspec.GridSpec(2, 2, figure=fig,
                               hspace=0.50, wspace=0.30,
                               top=0.93, bottom=0.08,
                               left=0.07, right=0.97)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])

        times      = result_df["datetime"]
        close_opt  = result_df["close_opt"]
        close_spot = result_df.get("close_spot")
        prob_up    = result_df["prob_up"]
        cum_pnl    = result_df["cumulative_pnl"]
        in_pos     = result_df["signal"] == 1
        entries    = result_df["entry"]
        exits      = result_df["exit_trade"]

        # ── Panel 1: ATM option price + Spot + trade markers ─────────────
        ax1.set_title("ATM CE Option Price  (Entry ▲  Exit ▼)", pad=8)
        ax1.fill_between(times, close_opt, alpha=0.18, color="#e3b341")
        ax1.plot(times, close_opt, color="#e3b341", linewidth=1.8,
                 label="ATM CE Close")

        # Shade bars where we're in a position
        ax1.fill_between(times, close_opt, alpha=0.35, color="#bc8cff",
                         where=in_pos.values, label="Holding position")

        # Entry markers (upward triangle, bright green)
        entry_times  = times[entries.values]
        entry_prices = close_opt[entries.values]
        ax1.scatter(entry_times, entry_prices, marker="^",
                    color="#39d353", s=120, zorder=8, label="Entry (LONG)")

        # Exit markers (downward triangle, red/orange)
        exit_times  = times[exits.values]
        exit_prices = close_opt[exits.values]
        ax1.scatter(exit_times, exit_prices, marker="v",
                    color="#f85149", s=120, zorder=8, label="Exit")

        ax1.set_ylabel("Option Price (Rs.)", color="#e3b341", fontsize=10)
        ax1.tick_params(axis="y", colors="#e3b341")
        ax1.legend(loc="upper left", fontsize=8, facecolor=PANEL, edgecolor=GRID)

        if close_spot is not None:
            ax1r = ax1.twinx()
            ax1r.plot(times, close_spot, color="#58a6ff", linewidth=1.4,
                      alpha=0.80, label="Spot Price")
            ax1r.set_ylabel("Spot Price (Rs.)", color="#58a6ff", fontsize=10)
            ax1r.tick_params(axis="y", colors="#58a6ff")
            ax1r.spines["right"].set_edgecolor("#58a6ff")
            ax1r.legend(loc="upper right", fontsize=8, facecolor=PANEL, edgecolor=GRID)

        # ── Panel 2: P(UP) confidence curve — crystal clear ───────────────
        ax2.set_title(
            f"Model Confidence: P(Price UP in 5 min)   [Acc: {acc:.1f}%]",
            pad=8)

        # Background shading: green when P(UP)>entry, red when P(UP)<exit
        ax2.fill_between(times, prob_up, self.entry_threshold,
                         where=(prob_up > self.entry_threshold),
                         color="#39d353", alpha=0.20, label="BUY zone")
        ax2.fill_between(times, prob_up, self.exit_threshold,
                         where=(prob_up < self.exit_threshold),
                         color="#f85149", alpha=0.20, label="EXIT zone")

        # P(UP) line — thick, bright amber, unmistakable
        ax2.plot(times, prob_up,
                 color="#ffa657",
                 linewidth=2.8,
                 alpha=1.0,
                 zorder=5,
                 label="P(UP) — model confidence")

        # Entry threshold line
        ax2.axhline(self.entry_threshold, color="#39d353", linewidth=1.6,
                    linestyle="--", alpha=0.9,
                    label=f"Entry threshold ({self.entry_threshold})")
        # Exit threshold line
        ax2.axhline(self.exit_threshold, color="#f85149", linewidth=1.6,
                    linestyle="--", alpha=0.9,
                    label=f"Exit threshold ({self.exit_threshold})")
        # 0.5 reference
        ax2.axhline(0.50, color=DIM, linewidth=0.8, linestyle=":", alpha=0.5)

        ax2.set_ylim(-0.02, 1.02)
        ax2.set_ylabel("P(price UP in 5 min)", fontsize=10)
        ax2.legend(loc="upper left", fontsize=8, facecolor=PANEL,
                   edgecolor=GRID, framealpha=0.9)

        s = self._stats
        ax2.text(0.98, 0.04,
                 f"Trades: {s['n_trades']}  |  Win: {s['win_rate']:.0f}%  |  "
                 f"Avg hold: {s['avg_hold']:.0f} bars",
                 transform=ax2.transAxes, ha="right", va="bottom",
                 color=TEXT, fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.35",
                           facecolor=PANEL, edgecolor=GRID, alpha=0.9))

        # ── Panel 3: Cumulative PnL ───────────────────────────────────────
        ax3.set_title("Cumulative P&L — State Machine (Rs.)", pad=8)
        pos_pnl = np.where(cum_pnl >= 0, cum_pnl, 0)
        neg_pnl = np.where(cum_pnl <  0, cum_pnl, 0)
        ax3.fill_between(times, pos_pnl, 0, color="#3fb950", alpha=0.40, label="Profit")
        ax3.fill_between(times, neg_pnl, 0, color="#f85149", alpha=0.40, label="Loss")
        ax3.plot(times, cum_pnl, color="#e3b341", linewidth=2.4, zorder=5)
        ax3.axhline(0, color=DIM, linewidth=1.0, linestyle="--", alpha=0.6)

        # Mark each trade exit on PnL chart
        if not self._trades_df.empty:
            for _, tr in self._trades_df.iterrows():
                eb = int(tr["exit_bar"])
                if eb < len(result_df):
                    t   = result_df["datetime"].iloc[eb]
                    pnl = result_df["cumulative_pnl"].iloc[eb]
                    clr = "#39d353" if tr["pnl"] > 0 else "#f85149"
                    ax3.scatter(t, pnl, color=clr, s=60, zorder=7, alpha=0.9)

        final_pnl = float(cum_pnl.iloc[-1])
        pnl_color = "#3fb950" if final_pnl >= 0 else "#f85149"
        y_off = 25 if final_pnl >= 0 else -35
        ax3.annotate(
            f" Final: Rs.{final_pnl:,.0f}",
            xy=(times.iloc[-1], final_pnl),
            color=pnl_color, fontsize=10, fontweight="bold",
            xytext=(-110, y_off), textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color=pnl_color, lw=1.5),
        )
        ax3.set_ylabel("Cumulative PnL (Rs.)", fontsize=10)
        ax3.legend(loc="upper left", fontsize=8, facecolor=PANEL, edgecolor=GRID)

        # ── Panel 4: Trade PnL Distribution ───────────────────────────────
        ax4.set_title("Per-Trade P&L Distribution (Rs.)", pad=8)
        if not self._trades_df.empty and len(self._trades_df) > 1:
            trade_pnl = self._trades_df["pnl"].values
            wins      = trade_pnl[trade_pnl > 0]
            losses    = trade_pnl[trade_pnl <= 0]
            all_vals  = trade_pnl
            bins      = np.linspace(all_vals.min()-1, all_vals.max()+1,
                                    min(35, max(8, len(trade_pnl)//2)))
            if len(wins):
                ax4.hist(wins,   bins=bins, color="#3fb950", alpha=0.80,
                         label=f"Wins ({len(wins)})", edgecolor=PANEL)
            if len(losses):
                ax4.hist(losses, bins=bins, color="#f85149", alpha=0.80,
                         label=f"Losses ({len(losses)})", edgecolor=PANEL)
            ax4.axvline(0, color=DIM, linewidth=1.2, linestyle="--")

            wr = len(wins) / len(trade_pnl) * 100 if len(trade_pnl) else 0
            ax4.text(0.97, 0.95, f"Win Rate: {wr:.1f}%",
                     transform=ax4.transAxes, ha="right", va="top",
                     color=TEXT, fontsize=12, fontweight="bold",
                     bbox=dict(boxstyle="round,pad=0.35",
                               facecolor=PANEL, edgecolor=GRID))
            # Best/worst trade annotation
            ax4.text(0.97, 0.78,
                     f"Best: Rs.{trade_pnl.max():,.0f}\n"
                     f"Worst: Rs.{trade_pnl.min():,.0f}",
                     transform=ax4.transAxes, ha="right", va="top",
                     color=DIM, fontsize=9,
                     bbox=dict(boxstyle="round,pad=0.3",
                               facecolor=PANEL, edgecolor=GRID, alpha=0.8))
        else:
            n = s.get("n_trades", 0)
            ax4.text(0.5, 0.5,
                     f"Only {n} trade(s) — not enough for histogram",
                     transform=ax4.transAxes, ha="center", va="center",
                     color=DIM, fontsize=12)
        ax4.set_xlabel("PnL per Trade (Rs.)", fontsize=10)
        ax4.set_ylabel("Frequency", fontsize=10)
        ax4.legend(fontsize=8, facecolor=PANEL, edgecolor=GRID)

        # ── Shared x-axis ─────────────────────────────────────────────────
        for ax in [ax1, ax2, ax3]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.xaxis.set_major_locator(
                mdates.MinuteLocator(byminute=range(0, 60, 30)))
            plt.setp(ax.xaxis.get_majorticklabels(),
                     rotation=30, ha="right", fontsize=8)
        for ax in [ax1, ax2, ax3, ax4]:
            for sp in ax.spines.values():
                sp.set_edgecolor(GRID)
            ax.grid(True, alpha=0.35, linewidth=0.5)

        # ── Bottom stats banner ────────────────────────────────────────────
        prec = metrics.get("Precision", float("nan")) if metrics else float("nan")
        rec  = metrics.get("Recall",    float("nan")) if metrics else float("nan")
        f1   = metrics.get("F1",        float("nan")) if metrics else float("nan")
        banner = (
            f"Trades: {s['n_trades']}  |  Win Rate: {s['win_rate']:.1f}%  |  "
            f"Avg Win: Rs.{s['avg_win']:.0f}  |  Avg Loss: Rs.{s['avg_loss']:.0f}  |  "
            f"Avg Hold: {s['avg_hold']:.0f} bars  |  Max DD: Rs.{s['max_dd']:,.0f}  |  "
            f"Net PnL: Rs.{s['total_pnl']:,.0f}  |  "
            f"Accuracy: {acc:.1f}%  |  Precision: {prec:.1f}%  |  F1: {f1:.1f}%"
        )
        fig.text(0.5, 0.01, banner, ha="center", fontsize=8.5,
                 color="#58a6ff",
                 bbox=dict(boxstyle="round,pad=0.4",
                           facecolor="#161b22", edgecolor=GRID, alpha=0.95))

        # ── Save ──────────────────────────────────────────────────────────
        if save_path is None:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            sym_clean = symbol.replace("/", "-")
            save_path = str(OUTPUT_DIR / f"sim_statemachine_{sym_clean}_{test_date}.png")

        plt.savefig(save_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        print(f"\n  Chart saved -> {save_path}")
        return save_path

    @staticmethod
    def _max_drawdown(cum_pnl: np.ndarray) -> float:
        peak = np.maximum.accumulate(cum_pnl)
        return float((peak - cum_pnl).max())
