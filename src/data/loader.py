"""Raw data discovery: pair option / spot / futures CSVs by trading day.

Dates are parsed from filenames (``*DD_MM_YYYY.csv``) instead of opening
every CSV, which makes discovery instant across ~7,000 files.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DATE_RE = re.compile(r"(\d{2})_(\d{2})_(\d{4})$")


def parse_date_from_filename(path: Path) -> date | None:
    m = DATE_RE.search(path.stem)
    if not m:
        return None
    dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(yyyy, mm, dd)
    except ValueError:
        return None


@dataclass(frozen=True)
class DayFiles:
    day: date
    opt: Path
    spot: Path
    fut: Path | None = None


def _index_by_date(folder: Path) -> dict[date, Path]:
    idx: dict[date, Path] = {}
    if not folder.exists():
        return idx
    for f in folder.rglob("*.csv"):
        d = parse_date_from_filename(f)
        if d is not None:
            idx[d] = f
    return idx


def discover_days(raw_dir, instrument: str,
                  start: date | None = None,
                  end: date | None = None) -> list[DayFiles]:
    """All trading days with both an options and a spot file (futures optional)."""
    base = Path(raw_dir) / f"{instrument}_data"
    opt_idx = _index_by_date(base / f"{instrument}_options")
    spot_idx = _index_by_date(base / f"{instrument}_spot")
    fut_idx = _index_by_date(base / f"{instrument}_fut")

    days = sorted(set(opt_idx) & set(spot_idx))
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]
    return [DayFiles(d, opt_idx[d], spot_idx[d], fut_idx.get(d)) for d in days]
