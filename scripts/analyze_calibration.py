"""Is our probability honest? Reliability diagnosis of the walk-forward model.

Every trading decision is a threshold on P(UP), so the number has to mean what
it says. This script replays the real walk-forward protocol (fit 8d, isotonic
calibrate 2d, predict the next unseen day) over N test days and reports:

  * AUC, accuracy and Brier score, raw vs calibrated
  * a reliability table (predicted bucket -> actually observed frequency)
  * precision at the thresholds the strategy actually trades on
  * whether calibration helps, hurts, or does nothing out of sample

Usage:
    python scripts/analyze_calibration.py --start 2020-02-01 --days 30
    python scripts/analyze_calibration.py --deadband 1.5 --days 30
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from src.config import load_config
from src.features.store import FeatureStore
from src.models.classifier import FEATURE_COLS, OptionsModel

BUCKETS = [0.0, 0.35, 0.45, 0.55, 0.65, 0.70, 0.75, 0.80, 1.01]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--start", type=date.fromisoformat,
                    default=date(2020, 2, 1))
    ap.add_argument("--days", type=int, default=30,
                    help="number of test days to evaluate")
    ap.add_argument("--train-days", type=int, default=10)
    ap.add_argument("--cal-days", type=int, default=2)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--deadband", type=float, default=None)
    args = ap.parse_args()

    cfg = load_config()
    inst = args.instrument or cfg["instrument"]
    band = (args.deadband if args.deadband is not None
            else cfg["model"]["label_deadband_pct"])
    store = FeatureStore(cfg["data"]["features_dir"])
    days = store.available_days(inst, args.start, None)
    n_fit = args.train_days - args.cal_days

    mdl = OptionsModel(horizon=args.horizon, deadband_pct=band,
                       moneyness_low=cfg["model"]["moneyness_low"],
                       moneyness_high=cfg["model"]["moneyness_high"],
                       min_premium=cfg["model"]["min_premium"],
                       n_estimators=cfg["model"]["n_estimators"],
                       learning_rate=cfg["model"]["learning_rate"])
    cache: dict = {}

    def prep(day):
        if day not in cache:
            try:
                sub = mdl._encode_and_filter(store.load_day(inst, day))
                cache[day] = (mdl._build_target(sub) if len(sub)
                              else pd.DataFrame())
            except Exception:
                cache[day] = pd.DataFrame()
        return cache[day]

    print(f"{inst}: horizon {args.horizon}m, deadband {band}%, "
          f"fit {n_fit}d + cal {args.cal_days}d, {args.days} test days "
          f"from {days[args.train_days]}")

    rows, pairs = [], []
    for k in range(args.train_days, min(args.train_days + args.days,
                                        len(days))):
        test_day, window = days[k], days[k - args.train_days:k]
        fit = [f for d in window[:n_fit] if len(f := prep(d))]
        cal = [f for d in window[n_fit:] if len(f := prep(d))]
        test = prep(test_day)
        if not fit or not cal or not len(test):
            continue

        train_df = pd.concat(fit, ignore_index=True)
        mdl.feature_cols = [c for c in FEATURE_COLS if c in train_df.columns]
        mdl.train(train_df)
        raw = mdl.predict_proba_raw(test)
        ok = mdl.fit_calibrator(pd.concat(cal, ignore_index=True))
        cal_p = mdl.predict_proba(test)
        y = test["target"].values.astype(int)

        rows.append(dict(
            day=test_day, n=len(y), base=y.mean(), calibrated=ok,
            auc=roc_auc_score(y, cal_p) if len(np.unique(y)) > 1 else np.nan,
            brier_raw=brier_score_loss(y, raw),
            brier_cal=brier_score_loss(y, cal_p),
            acc=float(((cal_p >= 0.5) == y).mean()),
        ))
        pairs.append(pd.DataFrame({"p": cal_p, "raw": raw, "y": y}))
        if len(rows) % 10 == 0:
            print(f"  {len(rows)} days done ({test_day})")

        for d in list(cache):
            if d < window[0]:
                del cache[d]

    per_day = pd.DataFrame(rows)
    allp = pd.concat(pairs, ignore_index=True)

    # ---- reliability table -------------------------------------------------
    allp["bucket"] = pd.cut(allp["p"], BUCKETS, right=False)
    rel = allp.groupby("bucket", observed=True).agg(
        rows=("y", "size"), predicted=("p", "mean"), actual=("y", "mean"))
    rel["gap"] = rel["predicted"] - rel["actual"]

    lines = [
        "# Calibration diagnosis",
        "",
        f"- Generated : {datetime.now():%Y-%m-%d %H:%M}",
        f"- {inst.upper()} | horizon {args.horizon}m | deadband {band}%",
        f"- Protocol : fit {n_fit}d, isotonic calibrate {args.cal_days}d, "
        f"test next unseen day",
        f"- Test days : {len(per_day)} "
        f"({per_day['day'].min()} .. {per_day['day'].max()})",
        f"- Rows      : {len(allp):,}",
        "",
        "## Headline",
        "```",
        f"  Base rate (UP)        : {per_day['base'].mean():.3f}",
        f"  AUC                   : {per_day['auc'].mean():.4f}  "
        f"(0.5 = no skill)  [min {per_day['auc'].min():.3f} "
        f"max {per_day['auc'].max():.3f}]",
        f"  Accuracy @0.5         : {per_day['acc'].mean():.3f}",
        f"  Brier, raw            : {per_day['brier_raw'].mean():.4f}",
        f"  Brier, calibrated     : {per_day['brier_cal'].mean():.4f}",
        f"  Calibrator fitted on  : {int(per_day['calibrated'].sum())}"
        f"/{len(per_day)} days",
        "```",
        "",
        "## Reliability: what the probability promises vs. what happened",
        "```",
        rel.to_string(float_format=lambda v: f"{v:0.3f}"),
        "```",
        "",
        "## Precision at the thresholds we trade",
        "```",
    ]
    for thr in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
        sel = allp["p"] > thr
        if sel.sum():
            lines.append(
                f"  p > {thr:.2f} : {int(sel.sum()):>7,} rows  "
                f"actually UP {allp.loc[sel, 'y'].mean():.3f}  "
                f"(lift {allp.loc[sel, 'y'].mean() - allp['y'].mean():+.3f})")
        else:
            lines.append(f"  p > {thr:.2f} :       0 rows")
    lines += ["```", ""]

    out = (Path(cfg["data"]["reports_dir"])
           / f"calibration_{inst}_{datetime.now():%Y%m%d_%H%M%S}")
    out.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [0, 1], ls="--", c="gray", lw=1, label="perfect")
    ax.plot(rel["predicted"], rel["actual"], "o-", c="#1f4e79", lw=2,
            label="calibrated model")
    ax.axhline(allp["y"].mean(), c="#9c2b2b", lw=1, ls=":",
               label=f"base rate {allp['y'].mean():.3f}")
    ax.set_xlabel("predicted probability of UP")
    ax.set_ylabel("observed frequency of UP")
    ax.set_title(f"Reliability — {inst.upper()} h={args.horizon}m "
                 f"deadband {band}%")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "reliability.png", dpi=130)
    plt.close(fig)

    per_day.to_csv(out / "per_day.csv", index=False)
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
