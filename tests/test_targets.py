"""The Phase-1 critical fix: targets must never mix contracts."""

import pandas as pd
import pytest

from src.models.classifier import OptionsModel


def _mk_day(symbols_prices: dict, start="2020-01-06 09:15:00") -> pd.DataFrame:
    """Interleaved rows for several symbols, sorted by datetime (like real data)."""
    rows = []
    for sym, prices in symbols_prices.items():
        opt_type = "CE" if sym.endswith("CE") else "PE"
        for i, px in enumerate(prices):
            rows.append(dict(
                symbol=sym,
                datetime=pd.Timestamp(start) + pd.Timedelta(minutes=i),
                close_opt=float(px),
                option_type=opt_type,
                moneyness=1.0,
            ))
    return pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)


def test_targets_are_per_symbol():
    # Symbol A rises every minute, symbol B falls — interleaved by time.
    df = _mk_day({
        "AAA32000CE": [100, 105, 110, 115, 120, 125, 130, 135],
        "BBB32000PE": [100, 95, 90, 85, 80, 75, 70, 65],
    })
    mdl = OptionsModel(horizon=2, deadband_pct=0.0, min_premium=1.0)
    out = mdl._build_target(mdl._encode_and_filter(df))

    a = out[out["symbol"] == "AAA32000CE"]
    b = out[out["symbol"] == "BBB32000PE"]
    assert len(a) > 0 and len(b) > 0
    assert (a["target"] == 1).all(), "rising contract must label UP"
    assert (b["target"] == 0).all(), "falling contract must label DOWN"


def test_gap_guard_drops_labels_across_quote_gaps():
    # 3 quotes, then a 30-minute gap: shifting 2 rows ahead would cross the gap.
    times = ["09:15", "09:16", "09:17", "09:47", "09:48", "09:49"]
    df = pd.DataFrame(dict(
        symbol="CCC32000CE",
        datetime=[pd.Timestamp(f"2020-01-06 {t}:00") for t in times],
        close_opt=[100.0, 101, 102, 200, 201, 202],
        option_type="CE",
        moneyness=1.0,
    ))
    mdl = OptionsModel(horizon=2, deadband_pct=0.0, min_premium=1.0)
    out = mdl._build_target(mdl._encode_and_filter(df))
    # rows 09:16 and 09:17 would need the quote 2 steps ahead → crosses gap → dropped
    kept = set(out["datetime"].dt.strftime("%H:%M"))
    assert "09:16" not in kept and "09:17" not in kept
    assert "09:15" in kept  # 09:15 → 09:17 is within the gap tolerance


def test_deadband_requires_meaningful_move():
    df = _mk_day({"DDD32000CE": [100.0, 100.05, 100.05, 100.05, 100.05]})
    mdl = OptionsModel(horizon=1, deadband_pct=0.5, min_premium=1.0)
    out = mdl._build_target(mdl._encode_and_filter(df))
    # +0.05% moves are below the 0.5% deadband → all DOWN/flat
    assert (out["target"] == 0).all()
