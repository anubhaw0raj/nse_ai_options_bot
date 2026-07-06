"""Build the parquet feature store from raw CSVs (one-time per day).

Usage:
    python scripts/build_features.py --start 2020-01-01 --end 2020-03-31
                                     [--instrument banknifty] [--force]
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config
from src.data.loader import discover_days
from src.features.engineering import FeatureEngineer
from src.features.store import FeatureStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--start", type=date.fromisoformat, default=None)
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    ap.add_argument("--force", action="store_true",
                    help="rebuild even if parquet already exists")
    args = ap.parse_args()

    cfg = load_config()
    instrument = args.instrument or cfg["instrument"]
    mcfg = cfg["model"]

    days = discover_days(cfg["data"]["raw_dir"], instrument,
                         start=args.start, end=args.end)
    store = FeatureStore(cfg["data"]["features_dir"])
    fe = FeatureEngineer(risk_free_rate=cfg["risk_free_rate"],
                         moneyness_low=mcfg["moneyness_low"],
                         moneyness_high=mcfg["moneyness_high"])

    todo = [d for d in days if args.force or not store.has_day(instrument, d.day)]
    print(f"{instrument}: {len(days)} raw days in range, "
          f"{len(todo)} to build, {len(days) - len(todo)} cached.")

    t0 = time.time()
    ok = failed = 0
    for i, d in enumerate(todo, 1):
        try:
            df = fe.process_single_day(d.opt, d.spot, d.fut)
            if len(df) == 0:
                print(f"  [{i}/{len(todo)}] {d.day}: 0 rows, skipped")
                failed += 1
                continue
            store.save_day(instrument, d.day, df)
            ok += 1
            if i % 10 == 0 or i == len(todo):
                rate = (time.time() - t0) / i
                print(f"  [{i}/{len(todo)}] {d.day}: {len(df):,} rows  "
                      f"({rate:.1f}s/day, ~{rate * (len(todo) - i) / 60:.0f} min left)")
        except Exception as e:
            failed += 1
            print(f"  [{i}/{len(todo)}] {d.day}: ERROR {e}")

    print(f"\nDone in {(time.time() - t0) / 60:.1f} min — "
          f"{ok} built, {failed} failed/empty.")


if __name__ == "__main__":
    main()
