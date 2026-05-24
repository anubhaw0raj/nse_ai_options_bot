"""
src/model.py
------------
Upgraded to a BINARY CLASSIFIER predicting option price direction:
  1 = option price will be HIGHER in N minutes (BUY signal)
  0 = option price will be LOWER or flat (no trade)

Why classification instead of regression:
  - Regression on % return fails because options have negative theta drift
    that dominates the target, so the model predicts ~0 for everything.
  - Direction is all we need for a BUY/NO-BUY strategy.
  - Primary metric: Directional Accuracy (classification accuracy).

Features: near-ATM options (moneyness 0.85-1.15), option_type encoded 0/1.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, classification_report)
import warnings
warnings.filterwarnings("ignore")

MONEYNESS_LOW  = 0.85
MONEYNESS_HIGH = 1.15

FEATURE_COLS = [
    "moneyness", "TTE", "IV",
    "delta", "gamma", "theta", "vega", "rho",
    "opt_ret_1m", "opt_ret_5m", "spot_ret_1m", "spot_ret_5m",
    "oi", "volume",
    "option_type_enc",
]

PREDICTION_HORIZON = 5   # minutes ahead


class OptionsModel:
    """
    Gradient Boosting Classifier for next-N-minute option price direction.
    Predicts: 1 = price will go UP, 0 = price will go DOWN/flat.
    """

    def __init__(self, horizon: int = PREDICTION_HORIZON, n_estimators: int = 300):
        self.horizon      = horizon
        self.scaler       = StandardScaler()
        self.model        = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )
        self.feature_cols: list = []
        self.is_trained        = False

    # ── Internal: encode + filter ──────────────────────────────────────────

    @staticmethod
    def _encode_and_filter(df: pd.DataFrame) -> pd.DataFrame:
        if "option_type" not in df.columns:
            return pd.DataFrame()
        df = df.copy()
        df["option_type_enc"] = df["option_type"].map({"CE": 0, "PE": 1})
        if "moneyness" in df.columns:
            df = df[df["moneyness"].between(MONEYNESS_LOW, MONEYNESS_HIGH)].copy()
        # Only options with meaningful price (avoids near-zero division issues)
        if "close_opt" in df.columns:
            df = df[df["close_opt"] > 5.0].copy()
        return df

    # ── Target builder: binary direction ──────────────────────────────────

    @staticmethod
    def _build_target(sub: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """
        target = 1 if future_price > current_price else 0
        Computed per-day to prevent day-boundary leakage.
        """
        future_price  = sub["close_opt"].shift(-horizon)
        sub["target"] = (future_price > sub["close_opt"]).astype(int)
        return sub.dropna(subset=["target"])

    # ── Multi-day train preparation ────────────────────────────────────────

    def prepare_train(self, days_dfs: list) -> pd.DataFrame:
        per_day_frames = []
        total_raw      = 0

        for day_df in days_dfs:
            sub = self._encode_and_filter(day_df)
            if sub.empty:
                continue
            sub = sub.sort_values("datetime").reset_index(drop=True)
            if not self.feature_cols:
                self.feature_cols = [c for c in FEATURE_COLS if c in sub.columns]
            sub = sub.dropna(subset=self.feature_cols)
            total_raw += len(sub)
            sub = self._build_target(sub, self.horizon)
            per_day_frames.append(sub)

        if not per_day_frames:
            raise ValueError("No usable data after filtering.")

        train_df = pd.concat(per_day_frames, ignore_index=True)
        up_pct = train_df["target"].mean() * 100
        print(f"  Training rows: {len(train_df):,}  (raw: {total_raw:,})")
        print(f"  Class balance: UP={up_pct:.1f}%  DOWN={100-up_pct:.1f}%")
        return train_df

    # ── Single-day test preparation ────────────────────────────────────────

    def prepare_test(self, test_day_df: pd.DataFrame) -> pd.DataFrame:
        sub = self._encode_and_filter(test_day_df)
        if sub.empty:
            raise ValueError("No valid options found in test day.")
        sub = sub.sort_values("datetime").reset_index(drop=True)
        sub = sub.dropna(subset=self.feature_cols)
        sub = self._build_target(sub, self.horizon)
        up_pct = sub["target"].mean() * 100
        print(f"  Test rows: {len(sub):,}  (UP={up_pct:.1f}%  DOWN={100-up_pct:.1f}%)")
        return sub

    # ── Training ───────────────────────────────────────────────────────────

    def train(self, train_df: pd.DataFrame):
        X = train_df[self.feature_cols].values.astype(float)
        y = train_df["target"].values.astype(int)
        self.scaler.fit(X)
        self.model.fit(self.scaler.transform(X), y)
        self.is_trained = True
        print("  Classifier training complete.")

    # ── Prediction: returns probability of UP (class=1) ───────────────────

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        """Returns probability that price will go UP (0.0 to 1.0)."""
        if not self.is_trained:
            raise RuntimeError("Call .train() first.")
        X = df[self.feature_cols].values.astype(float)
        return self.model.predict_proba(self.scaler.transform(X))[:, 1]

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Returns class labels (0 or 1) using 0.5 decision threshold."""
        return (self.predict_proba(df) >= 0.5).astype(int)

    # ── Evaluation ─────────────────────────────────────────────────────────

    def evaluate(self, test_df: pd.DataFrame) -> dict:
        y_pred_proba = self.predict_proba(test_df)
        y_pred       = (y_pred_proba >= 0.5).astype(int)
        y_true       = test_df["target"].values.astype(int)

        acc  = accuracy_score(y_true, y_pred) * 100
        prec = precision_score(y_true, y_pred, zero_division=0) * 100
        rec  = recall_score(y_true, y_pred, zero_division=0) * 100
        f1   = f1_score(y_true, y_pred, zero_division=0) * 100

        metrics = dict(
            Accuracy=acc, Precision=prec, Recall=rec, F1=f1,
            # Keep these keys for chart banner compatibility
            Directional_Acc=acc, R2=float("nan"), MAE_pct=float("nan"),
        )

        print("\n  === Classifier Evaluation ===")
        print(f"    Accuracy    : {acc:.2f}%")
        print(f"    Precision   : {prec:.2f}%  (of BUY signals, how many were right)")
        print(f"    Recall      : {rec:.2f}%  (of actual UPs, how many we caught)")
        print(f"    F1 Score    : {f1:.2f}%")
        print("\n  Classification Report:")
        print(classification_report(y_true, y_pred,
                                    target_names=["DOWN", "UP"],
                                    zero_division=0))

        # Probability distribution insight
        print(f"  Prob(UP) stats: "
              f"min={y_pred_proba.min():.3f}  max={y_pred_proba.max():.3f}  "
              f"mean={y_pred_proba.mean():.3f}")
        return metrics

    # ── Feature importance ─────────────────────────────────────────────────

    def feature_importance(self) -> pd.Series:
        return pd.Series(
            self.model.feature_importances_,
            index=self.feature_cols
        ).sort_values(ascending=False)
