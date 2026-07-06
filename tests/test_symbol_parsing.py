import pandas as pd

from src.features.engineering import FeatureEngineer


def test_parse_symbol_components():
    df = pd.DataFrame({"symbol": ["BANKNIFTY02JAN2032500CE",
                                  "NIFTY30APR2010100PE"]})
    out = FeatureEngineer._parse_symbol(df.copy())
    assert list(out["underlying"]) == ["BANKNIFTY", "NIFTY"]
    assert list(out["strike"]) == [32500.0, 10100.0]
    assert list(out["option_type"]) == ["CE", "PE"]
    assert out["expiry_date"].iloc[0] == pd.Timestamp("2020-01-02")
    assert out["expiry_datetime"].iloc[0] == pd.Timestamp("2020-01-02 15:30:00")


def test_non_option_symbols_yield_nan():
    df = pd.DataFrame({"symbol": ["BANKNIFTY-I"]})
    out = FeatureEngineer._parse_symbol(df.copy())
    assert out["strike"].isna().all()
