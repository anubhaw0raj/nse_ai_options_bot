"""Portfolio-level performance metrics from a walk-forward trade log."""

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def daily_pnl_series(trades: pd.DataFrame) -> pd.Series:
    """Net PnL summed per calendar day of exit."""
    if trades.empty:
        return pd.Series(dtype=float)
    d = pd.to_datetime(trades["exit_time"]).dt.normalize()
    return trades.groupby(d)["pnl"].sum().sort_index()


def max_drawdown(cum: np.ndarray) -> float:
    if len(cum) == 0:
        return 0.0
    peak = np.maximum.accumulate(cum)
    return float((peak - cum).max())


def compute_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return dict(n_trades=0)

    pnl = trades["pnl"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]

    daily = daily_pnl_series(trades)
    cum = daily.cumsum().values
    std = daily.std()
    downside = daily[daily < 0].std()

    m = dict(
        n_trades=len(trades),
        n_days=len(daily),
        win_rate=len(wins) / len(trades) * 100,
        gross_pnl=float(trades["gross"].sum()) if "gross" in trades else float("nan"),
        total_charges=float(trades["charges"].sum()) if "charges" in trades else float("nan"),
        net_pnl=float(pnl.sum()),
        expectancy=float(pnl.mean()),
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        profit_factor=float(wins.sum() / abs(losses.sum()))
        if losses.sum() != 0 else float("inf"),
        avg_hold_bars=float(trades["bars_held"].mean())
        if "bars_held" in trades else float("nan"),
        max_drawdown=max_drawdown(cum),
        best_day=float(daily.max()),
        worst_day=float(daily.min()),
        sharpe=float(daily.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))
        if std and std > 0 else float("nan"),
        sortino=float(daily.mean() / downside * np.sqrt(TRADING_DAYS_PER_YEAR))
        if downside and downside > 0 else float("nan"),
    )
    return m


def format_metrics_table(m: dict) -> str:
    if m.get("n_trades", 0) == 0:
        return "No trades executed.\n"
    rows = [
        ("Trades", f"{m['n_trades']}  over {m['n_days']} days"),
        ("Win rate", f"{m['win_rate']:.1f}%"),
        ("Gross PnL", f"Rs.{m['gross_pnl']:,.0f}"),
        ("Charges", f"Rs.{m['total_charges']:,.0f}"),
        ("NET PnL", f"Rs.{m['net_pnl']:,.0f}"),
        ("Expectancy / trade", f"Rs.{m['expectancy']:,.1f}"),
        ("Avg win / loss", f"Rs.{m['avg_win']:,.0f} / Rs.{m['avg_loss']:,.0f}"),
        ("Profit factor", f"{m['profit_factor']:.2f}"),
        ("Avg hold", f"{m['avg_hold_bars']:.1f} bars"),
        ("Max drawdown", f"Rs.{m['max_drawdown']:,.0f}"),
        ("Best / worst day", f"Rs.{m['best_day']:,.0f} / Rs.{m['worst_day']:,.0f}"),
        ("Sharpe (daily, ann.)", f"{m['sharpe']:.2f}"),
        ("Sortino (daily, ann.)", f"{m['sortino']:.2f}"),
    ]
    w = max(len(k) for k, _ in rows)
    return "\n".join(f"  {k:<{w}} : {v}" for k, v in rows) + "\n"
