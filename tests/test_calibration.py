import numpy as np
import pandas as pd

from src.models.classifier import OptionsModel


def _training_frame(n=3000, seed=7) -> pd.DataFrame:
    """Synthetic frame where one feature genuinely predicts the target."""
    rng = np.random.default_rng(seed)
    signal = rng.normal(size=n)
    noise = rng.normal(size=n)
    target = (signal + 0.8 * noise > 0).astype(int)
    df = pd.DataFrame({
        "symbol": "XXX32000CE",
        "datetime": pd.date_range("2020-01-06 09:15", periods=n, freq="min"),
        "close_opt": 100.0,
        "option_type": "CE",
        "option_type_enc": 0,
        "moneyness": 1.0,
        "sig": signal,
        "target": target,
    })
    return df


def test_calibrator_output_is_valid_probability():
    df = _training_frame()
    mdl = OptionsModel(horizon=1, min_premium=1.0, n_estimators=50)
    mdl.feature_cols = ["sig", "option_type_enc", "moneyness"]
    fit, cal = df.iloc[:2000], df.iloc[2000:]
    mdl.train(fit)
    assert mdl.fit_calibrator(cal) is True

    p = mdl.predict_proba(cal)
    assert p.min() >= 0.0 and p.max() <= 1.0
    # calibrated probs should still separate the classes
    assert p[cal["target"] == 1].mean() > p[cal["target"] == 0].mean()


def test_calibrator_refused_on_tiny_or_degenerate_fold():
    df = _training_frame()
    mdl = OptionsModel(horizon=1, min_premium=1.0, n_estimators=50)
    mdl.feature_cols = ["sig", "option_type_enc", "moneyness"]
    mdl.train(df.iloc[:2000])

    tiny = df.iloc[2000:2050]
    assert mdl.fit_calibrator(tiny) is False

    degenerate = df.iloc[2000:2500].copy()
    degenerate["target"] = 1
    assert mdl.fit_calibrator(degenerate) is False
    # falls back to raw probabilities without crashing
    assert len(mdl.predict_proba(degenerate)) == len(degenerate)


def test_retrain_invalidates_calibrator():
    df = _training_frame()
    mdl = OptionsModel(horizon=1, min_premium=1.0, n_estimators=50)
    mdl.feature_cols = ["sig", "option_type_enc", "moneyness"]
    mdl.train(df.iloc[:2000])
    mdl.fit_calibrator(df.iloc[2000:])
    assert mdl.calibrator is not None
    mdl.train(df.iloc[:2000])
    assert mdl.calibrator is None
