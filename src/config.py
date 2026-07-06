"""Central config loader + helpers (lot size by date, paths)."""

from datetime import date as _date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | None = None) -> dict:
    p = Path(path) if path else ROOT / "config" / "settings.yaml"
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = str(ROOT)
    return cfg


def _as_date(d) -> _date:
    if isinstance(d, _date):
        return d
    if hasattr(d, "date"):          # datetime / Timestamp
        return d.date()
    return _date.fromisoformat(str(d)[:10])


def lot_size_for(cfg: dict, instrument: str, on_date) -> int:
    """Lot size in force on a given date (table keyed by effective date)."""
    table = cfg["instruments"][instrument]["lot_sizes"]
    target = _as_date(on_date)
    best = None
    for eff in sorted(table, key=_as_date):
        if _as_date(eff) <= target:
            best = table[eff]
    if best is None:
        raise ValueError(f"No lot size effective on {target} for {instrument}")
    return int(best)
