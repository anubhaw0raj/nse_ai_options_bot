"""LightGBM direction classifier for option premium, N minutes ahead.

Key correctness properties (fixes the Phase-1 target bug):
  - Targets are built PER CONTRACT (groupby symbol) — the "future price" of
    BANKNIFTY...32500CE can never come from a different contract's row.
  - A time-gap guard drops labels where the contract has no quote within
    2× the horizon (illiquid gaps would otherwise create false labels).
  - Optional deadband: the future price must exceed now by `deadband_pct`
    to count as UP, so the model learns tradeable moves, not 1-tick noise.

Model: LightGBM (fast retrains for walk-forward, native NaN handling —
market-context features with warm-up NaNs don't force row drops).
"""

import warnings

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                             recall_score, roc_auc_score)

warnings.filterwarnings("ignore")

FEATURE_COLS = [
    # classical contract state
    "moneyness", "TTE", "IV", "delta", "gamma", "theta", "vega",
    # momentum
    "opt_ret_1m", "opt_ret_5m", "spot_ret_1m", "spot_ret_5m",
    # contract flow / anomaly
    "oi_chg_1m", "oi_chg_5m", "vol_z", "iv_z",
    # chain-wide modern inputs
    "pcr_oi", "pcr_vol", "iv_skew",
    # futures / institutional positioning
    "basis_pct", "fut_ret_1m", "fut_ret_5m", "fut_oi_chg_5m", "vwap_dist_pct",
    # vol regime + calendar
    "rv_15m", "rv_60m", "min_since_open", "tod_sin", "tod_cos", "dow",
    # contract type
    "option_type_enc",
]

PREDICTION_HORIZON = 5   # minutes


class OptionsModel:
    def __init__(self, horizon: int = PREDICTION_HORIZON,
                 deadband_pct: float = 0.10,
                 moneyness_low: float = 0.85, moneyness_high: float = 1.15,
                 min_premium: float = 5.0,
                 n_estimators: int = 400, learning_rate: float = 0.05):
        self.horizon = horizon
        self.deadband_pct = deadband_pct
        self.moneyness_low = moneyness_low
        self.moneyness_high = moneyness_high
        self.min_premium = min_premium
        self.model = LGBMClassifier(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            num_leaves=63,
            max_depth=-1,
            min_child_samples=50,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        self.feature_cols: list[str] = []
        self.is_trained = False
        self.calibrator: IsotonicRegression | None = None

    # ── Filtering / encoding ───────────────────────────────────────────────

    def _encode_and_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        if "option_type" not in df.columns:
            return pd.DataFrame()
        df = df.copy()
        df["option_type_enc"] = df["option_type"].map({"CE": 0, "PE": 1})
        if "moneyness" in df.columns:
            df = df[df["moneyness"].between(self.moneyness_low,
                                            self.moneyness_high)]
        if "close_opt" in df.columns:
            df = df[df["close_opt"] > self.min_premium]
        return df.copy()

    # ── Target: per-symbol future direction with gap guard ────────────────

    def _build_target(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values(["symbol", "datetime"]).reset_index(drop=True)
        g = df.groupby("symbol", sort=False)

        future_px = g["close_opt"].shift(-self.horizon)
        future_t = g["datetime"].shift(-self.horizon)

        max_gap = pd.Timedelta(minutes=self.horizon * 2)
        gap_ok = (future_t - df["datetime"]) <= max_gap

        hurdle = df["close_opt"] * (1 + self.deadband_pct / 100)
        target = (future_px > hurdle).astype(float)
        target[future_px.isna() | ~gap_ok] = np.nan

        df["target"] = target
        return df.dropna(subset=["target"]).reset_index(drop=True)

    # ── Dataset preparation ────────────────────────────────────────────────

    def prepare_train(self, days_dfs: list[pd.DataFrame],
                      verbose: bool = True) -> pd.DataFrame:
        frames = []
        for day_df in days_dfs:
            sub = self._encode_and_filter(day_df)
            if sub.empty:
                continue
            if not self.feature_cols:
                self.feature_cols = [c for c in FEATURE_COLS if c in sub.columns]
            frames.append(self._build_target(sub))

        if not frames:
            raise ValueError("No usable training data after filtering.")
        train_df = pd.concat(frames, ignore_index=True)
        if verbose:
            up = train_df["target"].mean() * 100
            print(f"  Training rows: {len(train_df):,}  "
                  f"(UP={up:.1f}% / DOWN={100 - up:.1f}%)")
        return train_df

    def prepare_test(self, test_day_df: pd.DataFrame,
                     verbose: bool = True) -> pd.DataFrame:
        sub = self._encode_and_filter(test_day_df)
        if sub.empty:
            raise ValueError("No valid options in test day after filtering.")
        if not self.feature_cols:
            self.feature_cols = [c for c in FEATURE_COLS if c in sub.columns]
        sub = self._build_target(sub)
        if verbose:
            up = sub["target"].mean() * 100
            print(f"  Test rows: {len(sub):,}  (UP={up:.1f}%)")
        return sub

    # ── Train / predict / evaluate ─────────────────────────────────────────

    def train(self, train_df: pd.DataFrame):
        X = train_df[self.feature_cols].astype(float)
        y = train_df["target"].astype(int)
        self.model.fit(X, y)
        self.is_trained = True
        self.calibrator = None          # stale after refit

    def fit_calibrator(self, cal_df: pd.DataFrame) -> bool:
        """Isotonic calibration on a held-out fold (strictly after the fit
        window, strictly before the test day). Makes P(UP)=0.7 mean ~70%,
        which is what turns entry thresholds into real expectancy statements.
        """
        if not self.is_trained:
            raise RuntimeError("Call .train() first.")
        y = cal_df["target"].values.astype(int)
        if len(cal_df) < 200 or len(np.unique(y)) < 2:
            self.calibrator = None
            return False
        raw = self.predict_proba_raw(cal_df)
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(raw, y)
        self.calibrator = iso
        return True

    def predict_proba_raw(self, df: pd.DataFrame) -> np.ndarray:
        if not self.is_trained:
            raise RuntimeError("Call .train() first.")
        X = df[self.feature_cols].astype(float)
        return self.model.predict_proba(X)[:, 1]

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        """Calibrated probability of UP when a calibrator is fitted."""
        raw = self.predict_proba_raw(df)
        if self.calibrator is not None:
            return self.calibrator.predict(raw)
        return raw

    def evaluate(self, test_df: pd.DataFrame, verbose: bool = True) -> dict:
        proba = self.predict_proba(test_df)
        y_pred = (proba >= 0.5).astype(int)
        y_true = test_df["target"].values.astype(int)

        metrics = dict(
            Accuracy=accuracy_score(y_true, y_pred) * 100,
            Precision=precision_score(y_true, y_pred, zero_division=0) * 100,
            Recall=recall_score(y_true, y_pred, zero_division=0) * 100,
            F1=f1_score(y_true, y_pred, zero_division=0) * 100,
        )
        try:
            metrics["AUC"] = roc_auc_score(y_true, proba) * 100
        except ValueError:
            metrics["AUC"] = float("nan")

        if verbose:
            print("  === Classifier Evaluation ===")
            for k, v in metrics.items():
                print(f"    {k:<10}: {v:.2f}%")
            print(f"    P(UP) range: {proba.min():.3f} – {proba.max():.3f} "
                  f"(mean {proba.mean():.3f})")
        return metrics

    def feature_importance(self) -> pd.Series:
        return pd.Series(self.model.feature_importances_,
                         index=self.feature_cols).sort_values(ascending=False)
