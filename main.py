"""
main.py
-------
Entry point: Feature Engineering -> Multi-day Training -> Single-day Backtest.

Fixes:
  1. Chronological file sorting (DD_MM_YYYY parsed from filename)
  2. % return target (via model.py)
  3. ATM-only simulation (one contract at a time)
  4. Directional accuracy as primary metric
"""

import sys
import io
import re
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))

from feature_engineering import FeatureEngineer
from model import OptionsModel, PREDICTION_HORIZON
from simulator import BacktestSimulator

RAW_DATA_DIR = Path("data/raw_option_chain")
N_TRAIN_DAYS = 7
INSTRUMENT   = "banknifty"


def parse_date_from_filename(path: Path) -> datetime:
    stem = path.stem
    m = re.search(r'(\d{2})[_](\d{2})[_](\d{4})$', stem)
    if m:
        dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime(yyyy, mm, dd)
    return datetime(1970, 1, 1)


def get_all_pairs(instrument: str = INSTRUMENT):
    opt_dir  = RAW_DATA_DIR / f"{instrument}_data/{instrument}_options"
    spot_dir = RAW_DATA_DIR / f"{instrument}_data/{instrument}_spot"

    opt_files  = sorted(opt_dir.rglob("*.csv"),  key=parse_date_from_filename)
    spot_files = sorted(spot_dir.rglob("*.csv"), key=parse_date_from_filename)

    print(f"  Indexing spot files ({len(spot_files)} found)...")
    spot_index = {}
    for sf in spot_files:
        try:
            d = str(pd.read_csv(sf, nrows=1)["date"].iloc[0])
            spot_index[d] = sf
        except Exception:
            pass

    pairs = []
    for of in opt_files:
        try:
            d = str(pd.read_csv(of, nrows=1)["date"].iloc[0])
            if d in spot_index:
                pairs.append((of, spot_index[d], parse_date_from_filename(of)))
        except Exception:
            pass

    pairs.sort(key=lambda x: x[2])
    return [(p[0], p[1]) for p in pairs]


def main():
    print("=" * 65)
    print("  NSE AI Options Bot  --  7-Day Train / 1-Day Backtest")
    print("  [Fixes: ATM-only sim | % return target | Directional Acc]")
    print("=" * 65)

    # ── Step 1: Discover files ─────────────────────────────────────────────
    print("\n[Step 1/5] Discovering data files (chronological)...")
    all_pairs = get_all_pairs(INSTRUMENT)
    print(f"  Found {len(all_pairs)} matched trading days.")

    if len(all_pairs) < N_TRAIN_DAYS + 1:
        print(f"  ERROR: Need >= {N_TRAIN_DAYS + 1} days. Exiting.")
        return

    train_pairs = all_pairs[:N_TRAIN_DAYS]
    test_pair   = all_pairs[N_TRAIN_DAYS]

    print(f"\n  TRAIN days ({N_TRAIN_DAYS}):")
    for opt_p, _ in train_pairs:
        print(f"    {opt_p.name}  ({parse_date_from_filename(opt_p).strftime('%d-%b-%Y')})")
    print(f"\n  TEST day:")
    print(f"    {test_pair[0].name}  ({parse_date_from_filename(test_pair[0]).strftime('%d-%b-%Y')})")

    # ── Step 2: Feature engineer training days ─────────────────────────────
    print("\n[Step 2/5] Feature Engineering (train days)...")
    fe = FeatureEngineer(risk_free_rate=0.05)
    train_dfs = []
    for i, (opt_p, spot_p) in enumerate(train_pairs, 1):
        print(f"  [{i}/{N_TRAIN_DAYS}] {opt_p.name}...", end=" ")
        try:
            day_df = fe.process_single_day(opt_p, spot_p)
            if len(day_df) > 0:
                train_dfs.append(day_df)
                print(f"{len(day_df):,} rows OK")
            else:
                print("0 rows, skipped")
        except Exception as e:
            print(f"ERROR: {e}")

    if not train_dfs:
        print("  ERROR: All training days failed. Exiting.")
        return

    # ── Step 3: Feature engineer test day ─────────────────────────────────
    print("\n[Step 3/5] Feature Engineering (test day)...")
    opt_p, spot_p = test_pair
    print(f"  {opt_p.name}...", end=" ")
    test_df_raw = fe.process_single_day(opt_p, spot_p)
    print(f"{len(test_df_raw):,} rows OK")

    # ── Step 4: Train ─────────────────────────────────────────────────────
    print("\n[Step 4/5] Training model (% return target)...")
    mdl = OptionsModel(horizon=PREDICTION_HORIZON, n_estimators=300)
    train_df = mdl.prepare_train(train_dfs)

    print(f"\n  Preparing test set (near-ATM)...")
    test_df = mdl.prepare_test(test_df_raw)

    if len(train_df) < 50:
        print(f"  ERROR: Only {len(train_df)} training rows. Exiting.")
        return
    if len(test_df) < 10:
        print(f"  ERROR: Only {len(test_df)} test rows. Exiting.")
        return

    mdl.train(train_df)

    print("\n[Step 4b] Evaluating on test day...")
    metrics = mdl.evaluate(test_df)

    print("\n  Feature Importances (Top 8):")
    print(mdl.feature_importance().head(8).to_string())

    # ── Step 5: ATM selection + simulation ────────────────────────────────
    print("\n[Step 5/5] Selecting ATM contract and running simulation...")
    # Classifier: get P(UP) probability for every row
    prob_up = mdl.predict_proba(test_df)

    test_df = test_df.copy()
    test_df.attrs["horizon"] = PREDICTION_HORIZON

    sim = BacktestSimulator(lot_size=25, entry_threshold=0.52, exit_threshold=0.48, max_hold_bars=10)

    # Find the ATM CE symbol on the test day
    atm_symbol = sim.find_atm_symbol(test_df, option_type="CE")

    # Run simulation on ATM symbol only (realistic single-contract backtest)
    result_df = sim.run(test_df, prob_up, atm_symbol=atm_symbol)

    # Plot chart
    chart_path = sim.plot(
        result_df,
        train_days=train_pairs,
        metrics=metrics,
    )

    print("\n" + "=" * 65)
    print("  Pipeline complete!")
    print(f"  Chart : {chart_path}")
    print("=" * 65)


if __name__ == "__main__":
    main()
