"""Single-day backtest: train on N prior days, test on the next day.

Usage:
    python scripts/run_backtest.py [--instrument banknifty] [--train-days 7]
                                   [--offset 0] [--no-plot]

`--offset K` slides the whole train/test window K days forward, so any
historical day can be tested without editing code.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.costs import CostModel
from src.backtest.simulator import BacktestSimulator
from src.config import load_config, lot_size_for
from src.data.loader import discover_days
from src.features.engineering import FeatureEngineer
from src.models.classifier import OptionsModel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--train-days", type=int, default=7)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    instrument = args.instrument or cfg["instrument"]
    mcfg, scfg = cfg["model"], cfg["strategy"]

    print("=" * 70)
    print(f"  NSE AI Options Bot - {instrument.upper()}  "
          f"({args.train_days}-day train / 1-day test, offset {args.offset})")
    print("=" * 70)

    days = discover_days(cfg["data"]["raw_dir"], instrument)
    need = args.offset + args.train_days + 1
    if len(days) < need:
        sys.exit(f"ERROR: need {need} matched days, found {len(days)}.")

    train_days = days[args.offset: args.offset + args.train_days]
    test_day = days[args.offset + args.train_days]
    print(f"  Train: {train_days[0].day} ... {train_days[-1].day}   "
          f"Test: {test_day.day}")

    fe = FeatureEngineer(risk_free_rate=cfg["risk_free_rate"],
                         moneyness_low=mcfg["moneyness_low"],
                         moneyness_high=mcfg["moneyness_high"])

    print("\n[1/4] Feature engineering ...")
    train_dfs = []
    for i, d in enumerate(train_days, 1):
        df = fe.process_single_day(d.opt, d.spot, d.fut)
        print(f"  [{i}/{len(train_days)}] {d.day}: {len(df):,} rows")
        if len(df):
            train_dfs.append(df)
    test_raw = fe.process_single_day(test_day.opt, test_day.spot, test_day.fut)
    print(f"  [test]  {test_day.day}: {len(test_raw):,} rows")

    print("\n[2/4] Training model ...")
    mdl = OptionsModel(horizon=mcfg["horizon_minutes"],
                       deadband_pct=mcfg["label_deadband_pct"],
                       moneyness_low=mcfg["moneyness_low"],
                       moneyness_high=mcfg["moneyness_high"],
                       min_premium=mcfg["min_premium"],
                       n_estimators=mcfg["n_estimators"],
                       learning_rate=mcfg["learning_rate"])
    train_df = mdl.prepare_train(train_dfs)
    test_df = mdl.prepare_test(test_raw)
    mdl.train(train_df)

    print("\n[3/4] Evaluating ...")
    metrics = mdl.evaluate(test_df)
    print("\n  Top-10 feature importances:")
    print(mdl.feature_importance().head(10).to_string())

    print("\n[4/4] Simulating ATM contracts ...")
    lot = lot_size_for(cfg, instrument, test_day.day)
    cost = CostModel(cfg["costs"])
    print(f"  Lot size on {test_day.day}: {lot}   "
          f"(cost hurdle ~ {cost.cost_hurdle_pct(200.0, lot):.2f}% "
          f"of a Rs.200 premium)")

    prob = mdl.predict_proba(test_df)
    for opt_type in scfg["trade_option_types"]:
        atm = BacktestSimulator.find_atm_symbol(test_df, opt_type)
        if atm is None:
            print(f"  No {opt_type} contract found, skipping.")
            continue
        sim = BacktestSimulator(lot_size=lot, cost_model=cost,
                                entry_threshold=scfg["entry_threshold"],
                                exit_threshold=scfg["exit_threshold"],
                                max_hold_bars=scfg["max_hold_bars"])
        result = sim.run(test_df, prob, atm_symbol=atm)
        if not args.no_plot:
            path = sim.plot(result, metrics=metrics,
                            title_extra=f"| net of costs, lot {lot}")
            print(f"  Chart: {path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
