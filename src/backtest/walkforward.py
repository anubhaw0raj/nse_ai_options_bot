"""Walk-forward backtest over the parquet feature store.

Scheme: train on the last `train_days` trading days, test the next day,
slide forward one day at a time. The model is refit every `retrain_every`
days. Each test day trades the ATM CE and ATM PE via the state-machine
simulator (net of costs). Outputs a run directory under reports/ with
trades.csv, report.md and equity.png.
"""

from datetime import date, datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.backtest.costs import CostModel
from src.backtest.metrics import (compute_metrics, daily_pnl_series,
                                  format_metrics_table)
from src.backtest.simulator import BacktestSimulator
from src.config import lot_size_for
from src.features.store import FeatureStore
from src.models.classifier import OptionsModel


class WalkForwardRunner:
    def __init__(self, cfg: dict, instrument: str,
                 train_days: int = 10, retrain_every: int = 1):
        self.cfg = cfg
        self.instrument = instrument
        self.train_days = train_days
        self.retrain_every = retrain_every
        self.store = FeatureStore(cfg["data"]["features_dir"])
        self.cost = CostModel(cfg["costs"])
        self.mcfg = cfg["model"]
        self.scfg = cfg["strategy"]
        self._prepared_cache: dict[date, pd.DataFrame] = {}

    # ── Helpers ────────────────────────────────────────────────────────────

    def _new_model(self) -> OptionsModel:
        m = self.mcfg
        return OptionsModel(horizon=m["horizon_minutes"],
                            deadband_pct=m["label_deadband_pct"],
                            moneyness_low=m["moneyness_low"],
                            moneyness_high=m["moneyness_high"],
                            min_premium=m["min_premium"],
                            n_estimators=m["n_estimators"],
                            learning_rate=m["learning_rate"])

    def _prepared_day(self, mdl: OptionsModel, day: date) -> pd.DataFrame | None:
        """Load + filter + label a day once; cache across sliding windows."""
        if day not in self._prepared_cache:
            try:
                raw = self.store.load_day(self.instrument, day)
                sub = mdl._encode_and_filter(raw)
                self._prepared_cache[day] = (
                    mdl._build_target(sub) if not sub.empty else pd.DataFrame())
            except Exception:
                self._prepared_cache[day] = pd.DataFrame()
        df = self._prepared_cache[day]
        return df if len(df) else None

    # ── Main loop ──────────────────────────────────────────────────────────

    def run(self, start: date | None = None, end: date | None = None,
            out_dir: str | Path | None = None) -> Path:
        days = self.store.available_days(self.instrument, start, end)
        if len(days) <= self.train_days:
            raise ValueError(
                f"Need > {self.train_days} feature days in range, "
                f"found {len(days)}. Run scripts/build_features.py first.")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(out_dir) if out_dir else (
            Path(self.cfg["data"]["reports_dir"])
            / f"walkforward_{self.instrument}_{stamp}")
        out.mkdir(parents=True, exist_ok=True)

        mdl = self._new_model()
        all_trades: list[pd.DataFrame] = []
        day_rows: list[dict] = []
        since_retrain = None

        n_iters = len(days) - self.train_days
        print(f"Walk-forward: {n_iters} test days "
              f"({days[self.train_days]} .. {days[-1]}), "
              f"train window {self.train_days}d, "
              f"retrain every {self.retrain_every}d")

        for k, idx in enumerate(range(self.train_days, len(days))):
            test_day = days[idx]
            window = days[idx - self.train_days: idx]

            # keep the cache bounded to the sliding window + test day
            for cached in list(self._prepared_cache):
                if cached < window[0]:
                    del self._prepared_cache[cached]

            if since_retrain is None or since_retrain >= self.retrain_every:
                frames = [f for d in window
                          if (f := self._prepared_day(mdl, d)) is not None]
                if not frames:
                    print(f"  {test_day}: no training data, skipped")
                    continue
                train_df = pd.concat(frames, ignore_index=True)
                if not mdl.feature_cols:
                    from src.models.classifier import FEATURE_COLS
                    mdl.feature_cols = [c for c in FEATURE_COLS
                                        if c in train_df.columns]
                mdl.train(train_df)
                since_retrain = 0
            since_retrain += 1

            test_df = self._prepared_day(mdl, test_day)
            if test_df is None:
                print(f"  {test_day}: no test data, skipped")
                continue

            prob = mdl.predict_proba(test_df)
            lot = lot_size_for(self.cfg, self.instrument, test_day)

            day_net, day_trades = 0.0, 0
            for opt_type in self.scfg["trade_option_types"]:
                atm = BacktestSimulator.find_atm_symbol(test_df, opt_type)
                if atm is None:
                    continue
                sim = BacktestSimulator(
                    lot_size=lot, cost_model=self.cost,
                    entry_threshold=self.scfg["entry_threshold"],
                    exit_threshold=self.scfg["exit_threshold"],
                    max_hold_bars=self.scfg["max_hold_bars"])
                try:
                    sim.run(test_df, prob, atm_symbol=atm, verbose=False)
                except ValueError:
                    continue
                if len(sim.trades):
                    tr = sim.trades.copy()
                    tr["test_day"] = pd.Timestamp(test_day)
                    all_trades.append(tr)
                    day_net += tr["pnl"].sum()
                    day_trades += len(tr)

            day_rows.append(dict(day=test_day, trades=day_trades, net=day_net))
            if (k + 1) % 10 == 0 or k == n_iters - 1:
                running = sum(r["net"] for r in day_rows)
                print(f"  [{k + 1}/{n_iters}] {test_day}  "
                      f"day net Rs.{day_net:,.0f}  running Rs.{running:,.0f}")

        trades = (pd.concat(all_trades, ignore_index=True)
                  if all_trades else pd.DataFrame())
        self._write_report(out, trades, days)
        return out

    # ── Reporting ──────────────────────────────────────────────────────────

    def _write_report(self, out: Path, trades: pd.DataFrame,
                      days: list[date]):
        trades.to_csv(out / "trades.csv", index=False)
        m = compute_metrics(trades)

        # Equity curve figure
        if len(trades):
            daily = daily_pnl_series(trades)
            cum = daily.cumsum()
            fig, (ax1, ax2) = plt.subplots(
                2, 1, figsize=(14, 8), sharex=True,
                gridspec_kw={"height_ratios": [2, 1]})
            ax1.plot(cum.index, cum.values, lw=2, color="#e3b341")
            ax1.fill_between(cum.index, cum.values, 0,
                             where=cum.values >= 0, alpha=0.25, color="#3fb950")
            ax1.fill_between(cum.index, cum.values, 0,
                             where=cum.values < 0, alpha=0.25, color="#f85149")
            ax1.axhline(0, color="gray", lw=1, ls="--")
            ax1.set_title(
                f"Walk-forward equity (NET) — {self.instrument.upper()}  "
                f"{days[self.train_days]} .. {days[-1]}")
            ax1.set_ylabel("Cumulative net PnL (Rs.)")
            colors = ["#3fb950" if v >= 0 else "#f85149" for v in daily.values]
            ax2.bar(daily.index, daily.values, color=colors, width=0.8)
            ax2.set_ylabel("Daily net (Rs.)")
            for ax in (ax1, ax2):
                ax.grid(alpha=0.3)
            fig.tight_layout()
            fig.savefig(out / "equity.png", dpi=130)
            plt.close(fig)

        # Markdown report
        lines = [
            f"# Walk-forward report — {self.instrument.upper()}",
            "",
            f"- Generated : {datetime.now():%Y-%m-%d %H:%M}",
            f"- Test span : {days[self.train_days]} → {days[-1]} "
            f"({len(days) - self.train_days} days)",
            f"- Train window : {self.train_days} days, retrain every "
            f"{self.retrain_every} day(s)",
            f"- Entry/exit thresholds : {self.scfg['entry_threshold']} / "
            f"{self.scfg['exit_threshold']}, max hold "
            f"{self.scfg['max_hold_bars']} bars",
            f"- Label deadband : {self.mcfg['label_deadband_pct']}%  |  "
            f"horizon {self.mcfg['horizon_minutes']}m",
            "",
            "## Results (net of all costs)",
            "```",
            format_metrics_table(m),
            "```",
        ]
        if len(trades):
            by_type = trades.groupby("option_type")["pnl"].agg(["count", "sum"])
            lines += ["", "## By option type", "```",
                      by_type.to_string(), "```"]
            monthly = trades.set_index(
                pd.to_datetime(trades["exit_time"]))["pnl"].resample("ME").sum()
            lines += ["", "## Monthly net PnL", "```",
                      monthly.to_string(), "```",
                      "", "![equity](equity.png)"]

        (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nReport written to {out}")
        print(format_metrics_table(m))
