"""Walk-forward backtest over the parquet feature store.

Phase-3 scheme per test day:
  1. FIT      : train LightGBM on the first (train_days - calibration_days)
                days of the sliding window.
  2. CALIBRATE: isotonic calibration of P(UP) on the last calibration_days
                of the window (held out from fitting).
  3. OPTIMIZE : grid-search the entry threshold by *simulating* the strategy
                (with full costs) on the calibration days; pick the threshold
                with the best net PnL. If even the best is <= 0, skip the
                test day entirely — "no edge measured, don't pay the toll."
  4. TEST     : trade the next (unseen) day with the chosen threshold.

Everything uses only data strictly before the test day — no lookahead.
Outputs a run directory under reports/ (report.md, trades.csv, equity.png,
days.csv) and appends a row to reports/experiments.csv.
"""

import csv
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
from src.models.classifier import FEATURE_COLS, OptionsModel

DEFAULT_THRESHOLD_GRID = [0.60, 0.65, 0.70, 0.75, 0.80]


class WalkForwardRunner:
    def __init__(self, cfg: dict, instrument: str,
                 train_days: int = 10, retrain_every: int = 1,
                 calibrate: bool = True, calibration_days: int = 2,
                 optimize_threshold: bool = True,
                 skip_if_no_edge: bool = True,
                 threshold_grid: list[float] | None = None,
                 horizon: int | None = None,
                 max_hold_bars: int | None = None):
        self.cfg = cfg
        self.instrument = instrument
        self.train_days = train_days
        self.retrain_every = retrain_every
        self.calibrate = calibrate
        self.calibration_days = calibration_days if calibrate else 0
        self.optimize_threshold = optimize_threshold
        self.skip_if_no_edge = skip_if_no_edge
        self.threshold_grid = threshold_grid or list(DEFAULT_THRESHOLD_GRID)

        self.store = FeatureStore(cfg["data"]["features_dir"])
        self.cost = CostModel(cfg["costs"])
        self.mcfg = dict(cfg["model"])
        if horizon:
            self.mcfg["horizon_minutes"] = horizon
        self.scfg = dict(cfg["strategy"])
        if max_hold_bars:
            self.scfg["max_hold_bars"] = max_hold_bars
        elif horizon:  # hold window should scale with prediction horizon
            self.scfg["max_hold_bars"] = max(10, 2 * horizon)

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

    def _simulate_day(self, df: pd.DataFrame, prob, day: date,
                      entry_thr: float) -> pd.DataFrame:
        """Run ATM CE+PE sims for one day; returns combined trades frame."""
        lot = lot_size_for(self.cfg, self.instrument, day)
        frames = []
        for opt_type in self.scfg["trade_option_types"]:
            atm = BacktestSimulator.find_atm_symbol(df, opt_type)
            if atm is None:
                continue
            sim = BacktestSimulator(
                lot_size=lot, cost_model=self.cost,
                entry_threshold=entry_thr,
                exit_threshold=self.scfg["exit_threshold"],
                max_hold_bars=self.scfg["max_hold_bars"])
            try:
                sim.run(df, prob, atm_symbol=atm, verbose=False)
            except ValueError:
                continue
            if len(sim.trades):
                frames.append(sim.trades)
        return (pd.concat(frames, ignore_index=True)
                if frames else pd.DataFrame())

    def _pick_threshold(self, mdl: OptionsModel,
                        cal_days: list[date]) -> tuple[float, float]:
        """Grid-search entry threshold by simulating the calibration days.

        Returns (best_threshold, best_net_pnl). Ties go to the HIGHER
        threshold (fewer trades, less cost exposure).
        """
        best_thr, best_net = self.threshold_grid[-1], float("-inf")
        cal_data = []
        for d in cal_days:
            df = self._prepared_day(mdl, d)
            if df is not None:
                cal_data.append((d, df, mdl.predict_proba(df)))
        if not cal_data:
            return best_thr, 0.0

        for thr in self.threshold_grid:
            net = 0.0
            for d, df, prob in cal_data:
                tr = self._simulate_day(df, prob, d, thr)
                if len(tr):
                    net += float(tr["pnl"].sum())
            if net >= best_net:
                best_thr, best_net = thr, net
        return best_thr, best_net

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
        entry_thr = self.scfg["entry_threshold"]
        cal_net = float("nan")

        n_iters = len(days) - self.train_days
        print(f"Walk-forward: {n_iters} test days "
              f"({days[self.train_days]} .. {days[-1]})  "
              f"train={self.train_days}d cal={self.calibration_days}d "
              f"horizon={self.mcfg['horizon_minutes']}m "
              f"hold<={self.scfg['max_hold_bars']} "
              f"calibrate={self.calibrate} optimize={self.optimize_threshold} "
              f"skip_no_edge={self.skip_if_no_edge}")

        for k, idx in enumerate(range(self.train_days, len(days))):
            test_day = days[idx]
            window = days[idx - self.train_days: idx]
            n_cal = self.calibration_days
            fit_days = window[:-n_cal] if n_cal else window
            cal_days = window[-n_cal:] if n_cal else []

            for cached in list(self._prepared_cache):
                if cached < window[0]:
                    del self._prepared_cache[cached]

            if since_retrain is None or since_retrain >= self.retrain_every:
                frames = [f for d in fit_days
                          if (f := self._prepared_day(mdl, d)) is not None]
                if not frames:
                    print(f"  {test_day}: no training data, skipped")
                    continue
                train_df = pd.concat(frames, ignore_index=True)
                if not mdl.feature_cols:
                    mdl.feature_cols = [c for c in FEATURE_COLS
                                        if c in train_df.columns]
                mdl.train(train_df)

                if self.calibrate and cal_days:
                    cal_frames = [f for d in cal_days
                                  if (f := self._prepared_day(mdl, d)) is not None]
                    if cal_frames:
                        mdl.fit_calibrator(
                            pd.concat(cal_frames, ignore_index=True))

                if self.optimize_threshold and cal_days:
                    entry_thr, cal_net = self._pick_threshold(mdl, cal_days)
                since_retrain = 0
            since_retrain += 1

            skip = (self.skip_if_no_edge and self.optimize_threshold
                    and not (cal_net > 0))
            test_df = None if skip else self._prepared_day(mdl, test_day)

            day_net, day_n = 0.0, 0
            if test_df is not None:
                prob = mdl.predict_proba(test_df)
                tr = self._simulate_day(test_df, prob, test_day, entry_thr)
                if len(tr):
                    tr["test_day"] = pd.Timestamp(test_day)
                    tr["entry_threshold"] = entry_thr
                    all_trades.append(tr)
                    day_net = float(tr["pnl"].sum())
                    day_n = len(tr)

            day_rows.append(dict(day=test_day, trades=day_n, net=day_net,
                                 entry_thr=entry_thr,
                                 cal_net=round(cal_net, 0)
                                 if cal_net == cal_net else None,
                                 skipped=bool(skip)))
            if (k + 1) % 10 == 0 or k == n_iters - 1:
                running = sum(r["net"] for r in day_rows)
                n_skip = sum(r["skipped"] for r in day_rows)
                print(f"  [{k + 1}/{n_iters}] {test_day}  thr={entry_thr:.2f}"
                      f"{' SKIP' if skip else ''}  day Rs.{day_net:,.0f}  "
                      f"running Rs.{running:,.0f}  (skipped {n_skip}d)")

        trades = (pd.concat(all_trades, ignore_index=True)
                  if all_trades else pd.DataFrame())
        days_df = pd.DataFrame(day_rows)
        days_df.to_csv(out / "days.csv", index=False)
        self._write_report(out, trades, days_df, days)
        return out

    # ── Reporting ──────────────────────────────────────────────────────────

    def _write_report(self, out: Path, trades: pd.DataFrame,
                      days_df: pd.DataFrame, days: list[date]):
        trades.to_csv(out / "trades.csv", index=False)
        m = compute_metrics(trades)
        n_skipped = int(days_df["skipped"].sum()) if len(days_df) else 0

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
                f"{days[self.train_days]} .. {days[-1]}  "
                f"h={self.mcfg['horizon_minutes']}m")
            ax1.set_ylabel("Cumulative net PnL (Rs.)")
            colors = ["#3fb950" if v >= 0 else "#f85149" for v in daily.values]
            ax2.bar(daily.index, daily.values, color=colors, width=0.8)
            ax2.set_ylabel("Daily net (Rs.)")
            for ax in (ax1, ax2):
                ax.grid(alpha=0.3)
            fig.tight_layout()
            fig.savefig(out / "equity.png", dpi=130)
            plt.close(fig)

        lines = [
            f"# Walk-forward report — {self.instrument.upper()}",
            "",
            f"- Generated : {datetime.now():%Y-%m-%d %H:%M}",
            f"- Test span : {days[self.train_days]} → {days[-1]} "
            f"({len(days) - self.train_days} days, {n_skipped} skipped by "
            f"no-edge rule)",
            f"- Train window : {self.train_days}d "
            f"(fit {self.train_days - self.calibration_days}d + "
            f"cal {self.calibration_days}d), retrain every "
            f"{self.retrain_every}d",
            f"- Horizon {self.mcfg['horizon_minutes']}m | deadband "
            f"{self.mcfg['label_deadband_pct']}% | max hold "
            f"{self.scfg['max_hold_bars']} bars",
            f"- Calibrated: {self.calibrate} | threshold: "
            f"{'auto ' + str(self.threshold_grid) if self.optimize_threshold else self.scfg['entry_threshold']}"
            f" | exit {self.scfg['exit_threshold']} | skip-no-edge: "
            f"{self.skip_if_no_edge}",
            "",
            "## Results (net of all costs)",
            "```",
            format_metrics_table(m),
            "```",
        ]
        if len(trades):
            by_type = trades.groupby("option_type")["pnl"].agg(["count", "sum"])
            lines += ["", "## By option type", "```", by_type.to_string(), "```"]
            by_thr = trades.groupby("entry_threshold")["pnl"].agg(["count", "sum"])
            lines += ["", "## By chosen entry threshold", "```",
                      by_thr.to_string(), "```"]
            monthly = trades.set_index(
                pd.to_datetime(trades["exit_time"]))["pnl"].resample("ME").sum()
            lines += ["", "## Monthly net PnL", "```", monthly.to_string(),
                      "```", "", "![equity](equity.png)"]

        (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
        self._log_experiment(out, m, days, n_skipped)
        print(f"\nReport written to {out}")
        print(format_metrics_table(m))
        if n_skipped:
            print(f"  Days skipped by no-edge rule: {n_skipped}")

    def _log_experiment(self, out: Path, m: dict, days: list[date],
                        n_skipped: int):
        log = Path(self.cfg["data"]["reports_dir"]) / "experiments.csv"
        log.parent.mkdir(parents=True, exist_ok=True)
        row = dict(
            ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
            instrument=self.instrument,
            start=days[self.train_days], end=days[-1],
            train_days=self.train_days, cal_days=self.calibration_days,
            horizon=self.mcfg["horizon_minutes"],
            max_hold=self.scfg["max_hold_bars"],
            deadband=self.mcfg["label_deadband_pct"],
            calibrated=self.calibrate,
            threshold="auto" if self.optimize_threshold
            else self.scfg["entry_threshold"],
            exit=self.scfg["exit_threshold"],
            skip_no_edge=self.skip_if_no_edge,
            skipped_days=n_skipped,
            n_trades=m.get("n_trades", 0),
            gross=round(m.get("gross_pnl", 0)),
            charges=round(m.get("total_charges", 0)),
            net=round(m.get("net_pnl", 0)),
            pf=round(m.get("profit_factor", 0), 2)
            if m.get("n_trades") else None,
            sharpe=round(m.get("sharpe", float("nan")), 2)
            if m.get("n_trades") else None,
            max_dd=round(m.get("max_drawdown", 0)),
            report=out.name,
        )
        exists = log.exists()
        with open(log, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if not exists:
                w.writeheader()
            w.writerow(row)
