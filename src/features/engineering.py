"""Feature engineering: classical greeks + modern option-market inputs.

Per 1-minute option row we compute:

Contract-level
  - TTE, moneyness, IV, delta/gamma/theta/vega/rho (py_vollib_vectorized)
  - option & spot momentum (1m / 5m returns)
  - OI change 1m/5m, volume z-score, IV z-score  (per contract, rolling)

Market-context (merged onto every row by minute)
  - Put/Call ratio of OI and of volume across the near-ATM chain
  - IV skew (mean PE IV − mean CE IV, near-ATM band)
  - Futures basis % (fut − spot), futures 1m/5m returns, futures OI change,
    distance from futures VWAP  ← institutional positioning signals
  - Realized volatility of spot (15m / 60m rolling)
  - Time-of-day (minutes since open, sin/cos), day-of-week

These "modern inputs" (OI flow, PCR, skew, basis, vol regime) are what
actually move option prices intraday beyond pure spot direction.
"""

import numpy as np
import pandas as pd
from py_vollib_vectorized.api import get_all_greeks, vectorized_implied_volatility

SESSION_MINUTES = 375           # 09:15 → 15:30
MARKET_OPEN = pd.Timedelta(hours=9, minutes=15)


class FeatureEngineer:
    def __init__(self, risk_free_rate: float = 0.05,
                 moneyness_low: float = 0.85, moneyness_high: float = 1.15):
        self.risk_free_rate = risk_free_rate
        self.moneyness_low = moneyness_low
        self.moneyness_high = moneyness_high

    # ── Basic parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _convert_datetime(df: pd.DataFrame) -> pd.DataFrame:
        if "date" in df.columns and "time" in df.columns:
            df["datetime"] = pd.to_datetime(
                df["date"].astype(str) + " " + df["time"].astype(str))
        return df

    @staticmethod
    def _parse_symbol(df: pd.DataFrame) -> pd.DataFrame:
        """Extract underlying / expiry / strike / type from e.g. BANKNIFTY02JAN2032500CE."""
        if "symbol" not in df.columns:
            return df
        pattern = r"^([A-Z]+)(\d{2}[A-Z]{3}\d{2})(\d+)(CE|PE)$"
        extracted = df["symbol"].str.extract(pattern)
        df["underlying"] = extracted[0]
        df["expiry_str"] = extracted[1]
        df["strike"] = pd.to_numeric(extracted[2], errors="coerce")
        df["option_type"] = extracted[3]
        df["expiry_date"] = pd.to_datetime(df["expiry_str"], format="%d%b%y",
                                           errors="coerce")
        df["expiry_datetime"] = df["expiry_date"] + pd.Timedelta(hours=15, minutes=30)
        return df

    @staticmethod
    def _calculate_tte(df: pd.DataFrame) -> pd.DataFrame:
        tte_seconds = (df["expiry_datetime"] - df["datetime"]).dt.total_seconds()
        tte_seconds = np.where(tte_seconds <= 0, 60, tte_seconds)
        df["TTE"] = tte_seconds / (365 * 24 * 60 * 60)
        return df

    # ── Greeks / IV ────────────────────────────────────────────────────────

    def _calculate_greeks(self, df: pd.DataFrame) -> pd.DataFrame:
        flag = df["option_type"].map({"CE": "c", "PE": "p"}).values
        S = df["close_spot"].values.astype(float)
        K = df["strike"].values.astype(float)
        t = df["TTE"].values.astype(float)
        r = np.full_like(S, self.risk_free_rate)
        price = df["close_opt"].values.astype(float)

        df["IV"] = vectorized_implied_volatility(
            price, S, K, t, r, flag, q=0, return_as="numpy", on_error="ignore")

        iv_for_greeks = np.nan_to_num(df["IV"].values, nan=0.0001)
        greeks = get_all_greeks(flag, S, K, t, r, iv_for_greeks, q=0,
                                return_as="dict")
        for g in ("delta", "gamma", "theta", "vega", "rho"):
            df[g] = greeks[g]
        return df

    # ── Per-contract rolling features ──────────────────────────────────────

    @staticmethod
    def _contract_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values(["symbol", "datetime"])
        g = df.groupby("symbol", sort=False)

        df["opt_ret_1m"] = g["close_opt"].pct_change(1) * 100
        df["opt_ret_5m"] = g["close_opt"].pct_change(5) * 100
        df["spot_ret_1m"] = g["close_spot"].pct_change(1) * 100
        df["spot_ret_5m"] = g["close_spot"].pct_change(5) * 100

        # OI flow — who is building / unwinding positions in this contract
        df["oi_chg_1m"] = g["oi"].pct_change(1) * 100
        df["oi_chg_5m"] = g["oi"].pct_change(5) * 100

        # Activity + IV anomaly vs. the contract's own recent history
        def _zscore(s: pd.Series, window: int, minp: int) -> pd.Series:
            m = s.rolling(window, min_periods=minp).mean()
            sd = s.rolling(window, min_periods=minp).std()
            return (s - m) / sd

        df["vol_z"] = g["volume"].transform(lambda s: _zscore(s, 30, 10))
        df["iv_z"] = g["IV"].transform(lambda s: _zscore(s, 60, 20))
        return df

    # ── Market-context features (one row per minute, merged back) ─────────

    def _market_context(self, df_merged: pd.DataFrame, df_spot: pd.DataFrame,
                        df_fut: pd.DataFrame | None) -> pd.DataFrame:
        # Near-ATM chain aggregates: PCR + IV skew
        band = df_merged[df_merged["moneyness"].between(
            self.moneyness_low, self.moneyness_high)]

        oi_pivot = band.pivot_table(index="datetime", columns="option_type",
                                    values="oi", aggfunc="sum")
        vol_pivot = band.pivot_table(index="datetime", columns="option_type",
                                     values="volume", aggfunc="sum")
        iv_pivot = band.pivot_table(index="datetime", columns="option_type",
                                    values="IV", aggfunc="mean")

        ctx = pd.DataFrame(index=oi_pivot.index)
        if {"CE", "PE"}.issubset(oi_pivot.columns):
            ctx["pcr_oi"] = oi_pivot["PE"] / oi_pivot["CE"].replace(0, np.nan)
            ctx["pcr_vol"] = vol_pivot["PE"] / vol_pivot["CE"].replace(0, np.nan)
            ctx["iv_skew"] = iv_pivot["PE"] - iv_pivot["CE"]

        # Spot realized volatility (vol regime)
        spot = df_spot.sort_values("datetime").set_index("datetime")
        spot_ret = spot["close"].pct_change() * 100
        ctx = ctx.join(spot_ret.rolling(15, min_periods=5).std().rename("rv_15m"),
                       how="outer")
        ctx = ctx.join(spot_ret.rolling(60, min_periods=15).std().rename("rv_60m"),
                       how="outer")

        # Futures: basis, momentum, OI flow, VWAP distance
        if df_fut is not None and len(df_fut):
            fut = df_fut.sort_values("datetime").set_index("datetime")
            ctx = ctx.join((fut["close"].pct_change(1) * 100).rename("fut_ret_1m"),
                           how="outer")
            ctx = ctx.join((fut["close"].pct_change(5) * 100).rename("fut_ret_5m"),
                           how="outer")
            if "oi" in fut.columns:
                ctx = ctx.join((fut["oi"].pct_change(5) * 100)
                               .rename("fut_oi_chg_5m"), how="outer")

            joined = fut[["close"]].join(spot[["close"]], how="inner",
                                         lsuffix="_fut", rsuffix="_spot")
            basis = ((joined["close_fut"] - joined["close_spot"])
                     / joined["close_spot"] * 100)
            ctx = ctx.join(basis.rename("basis_pct"), how="outer")

            if "volume" in fut.columns:
                pv = (fut["close"] * fut["volume"]).cumsum()
                vv = fut["volume"].cumsum().replace(0, np.nan)
                vwap = pv / vv
                ctx = ctx.join(((fut["close"] - vwap) / vwap * 100)
                               .rename("vwap_dist_pct"), how="outer")

        # Time-of-day / calendar
        idx = ctx.index
        min_open = ((idx - idx.normalize()) - MARKET_OPEN).total_seconds() / 60
        frac = np.clip(min_open / SESSION_MINUTES, 0, 1)
        ctx["min_since_open"] = min_open
        ctx["tod_sin"] = np.sin(2 * np.pi * frac)
        ctx["tod_cos"] = np.cos(2 * np.pi * frac)
        ctx["dow"] = idx.dayofweek

        return ctx.reset_index().rename(columns={"index": "datetime"})

    # ── Main entry: one trading day ────────────────────────────────────────

    def process_single_day(self, opt_path, spot_path, fut_path=None,
                           verbose: bool = False) -> pd.DataFrame:
        if verbose:
            print(f"Loading Options: {opt_path}")
        df_opt = pd.read_csv(opt_path)
        df_spot = pd.read_csv(spot_path)
        df_fut = pd.read_csv(fut_path) if fut_path else None

        df_opt = self._convert_datetime(df_opt)
        df_spot = self._convert_datetime(df_spot)
        if df_fut is not None:
            df_fut = self._convert_datetime(df_fut)

        df_opt = self._parse_symbol(df_opt)
        df_opt = df_opt.dropna(subset=["strike", "option_type"])
        df_opt = self._calculate_tte(df_opt)

        df_merged = pd.merge(
            df_opt,
            df_spot[["datetime", "open", "high", "low", "close"]],
            on="datetime", how="inner", suffixes=("_opt", "_spot"))

        if len(df_merged) == 0:
            return df_merged

        df_merged["moneyness"] = df_merged["close_spot"] / df_merged["strike"]
        df_merged = self._calculate_greeks(df_merged)
        df_merged = self._contract_features(df_merged)

        ctx = self._market_context(df_merged, df_spot, df_fut)
        df_merged = df_merged.merge(ctx, on="datetime", how="left")

        float64_cols = df_merged.select_dtypes(include=["float64"]).columns
        df_merged[float64_cols] = df_merged[float64_cols].astype("float32")
        return df_merged
