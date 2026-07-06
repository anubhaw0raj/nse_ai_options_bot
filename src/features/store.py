"""Parquet feature store: engineer each day once, reuse forever.

Layout: data/features/{instrument}/{YYYY-MM-DD}.parquet
"""

from datetime import date
from pathlib import Path

import pandas as pd


class FeatureStore:
    def __init__(self, root: str | Path = "data/features"):
        self.root = Path(root)

    def path_for(self, instrument: str, day: date) -> Path:
        return self.root / instrument / f"{day.isoformat()}.parquet"

    def has_day(self, instrument: str, day: date) -> bool:
        return self.path_for(instrument, day).exists()

    def save_day(self, instrument: str, day: date, df: pd.DataFrame) -> Path:
        p = self.path_for(instrument, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p, index=False)
        return p

    def load_day(self, instrument: str, day: date) -> pd.DataFrame:
        return pd.read_parquet(self.path_for(instrument, day))

    def available_days(self, instrument: str,
                       start: date | None = None,
                       end: date | None = None) -> list[date]:
        folder = self.root / instrument
        if not folder.exists():
            return []
        days = sorted(date.fromisoformat(p.stem)
                      for p in folder.glob("*.parquet"))
        if start:
            days = [d for d in days if d >= start]
        if end:
            days = [d for d in days if d <= end]
        return days
