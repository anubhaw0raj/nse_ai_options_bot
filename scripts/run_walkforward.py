"""Run a walk-forward backtest over the feature store.

Usage examples:
    python scripts/run_walkforward.py --start 2020-01-01 --end 2020-12-31
    python scripts/run_walkforward.py --horizon 15 --train-days 12
    python scripts/run_walkforward.py --no-calibrate --no-optimize --entry 0.70
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.walkforward import WalkForwardRunner
from src.config import load_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--start", type=date.fromisoformat, default=None)
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    ap.add_argument("--train-days", type=int, default=10,
                    help="sliding window size incl. calibration days")
    ap.add_argument("--retrain-every", type=int, default=1)
    ap.add_argument("--horizon", type=int, default=None,
                    help="prediction horizon in minutes (default from config)")
    ap.add_argument("--max-hold", type=int, default=None,
                    help="max holding bars (default 2x horizon)")
    ap.add_argument("--cal-days", type=int, default=2,
                    help="days held out of the window for calibration")
    ap.add_argument("--no-calibrate", action="store_true")
    ap.add_argument("--no-optimize", action="store_true",
                    help="use fixed entry threshold instead of auto grid")
    ap.add_argument("--no-skip", action="store_true",
                    help="trade even when calibration days show no edge")
    ap.add_argument("--entry", type=float, default=None,
                    help="fixed entry threshold (implies --no-optimize)")
    ap.add_argument("--exit", type=float, default=None)
    ap.add_argument("--no-risk", action="store_true",
                    help="disable the Phase-4 risk layer (stops, sizing, caps)")
    ap.add_argument("--deadband", type=float, default=None,
                    help="label deadband %% (the move that counts as UP); "
                         "set near the cost hurdle (~1.5) to align the label "
                         "with profitability")
    ap.add_argument("--stop", type=float, default=None,
                    help="stop-loss %% below entry fill; use 100 to disable "
                         "the stop while keeping targets and caps")
    ap.add_argument("--take-profit", type=float, default=None,
                    help="take-profit %% above entry fill")
    ap.add_argument("--max-lots", type=int, default=None,
                    help="cap on the conviction ladder")
    ap.add_argument("--grid", type=str, default=None,
                    help="comma-separated entry threshold grid, "
                         "e.g. 0.60,0.65,0.70,0.75,0.80 (hold constant when "
                         "ablating other parameters)")
    args = ap.parse_args()

    cfg = load_config()
    instrument = args.instrument or cfg["instrument"]
    if args.entry is not None:
        cfg["strategy"]["entry_threshold"] = args.entry
        args.no_optimize = True
    if args.exit is not None:
        cfg["strategy"]["exit_threshold"] = args.exit
    if args.deadband is not None:
        cfg["model"]["label_deadband_pct"] = args.deadband
    if args.stop is not None:
        cfg["risk"]["stop_loss_pct"] = args.stop
    if args.take_profit is not None:
        cfg["risk"]["take_profit_pct"] = args.take_profit
    if args.max_lots is not None:
        cfg["risk"]["max_lots"] = args.max_lots
    if args.grid is not None:
        cfg["strategy"]["threshold_grid"] = [float(x) for x in
                                             args.grid.split(",")]

    runner = WalkForwardRunner(
        cfg, instrument,
        train_days=args.train_days,
        retrain_every=args.retrain_every,
        calibrate=not args.no_calibrate,
        calibration_days=args.cal_days,
        optimize_threshold=not args.no_optimize,
        skip_if_no_edge=not args.no_skip,
        horizon=args.horizon,
        max_hold_bars=args.max_hold,
        use_risk=not args.no_risk,
    )
    runner.run(start=args.start, end=args.end)


if __name__ == "__main__":
    main()
