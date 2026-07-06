"""Run a walk-forward backtest over the feature store.

Usage:
    python scripts/run_walkforward.py --start 2020-01-01 --end 2020-03-31
        [--instrument banknifty] [--train-days 10] [--retrain-every 1]
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
    ap.add_argument("--train-days", type=int, default=10)
    ap.add_argument("--retrain-every", type=int, default=1)
    ap.add_argument("--entry", type=float, default=None,
                    help="override strategy.entry_threshold")
    ap.add_argument("--exit", type=float, default=None,
                    help="override strategy.exit_threshold")
    args = ap.parse_args()

    cfg = load_config()
    instrument = args.instrument or cfg["instrument"]
    if args.entry is not None:
        cfg["strategy"]["entry_threshold"] = args.entry
    if args.exit is not None:
        cfg["strategy"]["exit_threshold"] = args.exit

    runner = WalkForwardRunner(cfg, instrument,
                               train_days=args.train_days,
                               retrain_every=args.retrain_every)
    runner.run(start=args.start, end=args.end)


if __name__ == "__main__":
    main()
