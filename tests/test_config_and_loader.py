from datetime import date
from pathlib import Path

from src.config import load_config, lot_size_for
from src.data.loader import parse_date_from_filename


def test_lot_size_eras():
    cfg = load_config()
    assert lot_size_for(cfg, "banknifty", date(2020, 3, 1)) == 20
    assert lot_size_for(cfg, "banknifty", date(2022, 1, 1)) == 25
    assert lot_size_for(cfg, "banknifty", date(2024, 1, 1)) == 15
    assert lot_size_for(cfg, "banknifty", date(2024, 12, 1)) == 30
    assert lot_size_for(cfg, "nifty", date(2020, 6, 1)) == 75


def test_filename_date_parsing():
    # options/futures style: underscore before the date
    assert parse_date_from_filename(
        Path("banknifty_fut_01_10_2020.csv")) == date(2020, 10, 1)
    # spot style: no separator between "spot" and the date
    assert parse_date_from_filename(
        Path("banknifty_spot01_01_2020.csv")) == date(2020, 1, 1)
    # non-date file
    assert parse_date_from_filename(Path("readme.csv")) is None


def test_config_has_required_sections():
    cfg = load_config()
    for key in ("data", "instruments", "model", "costs", "strategy"):
        assert key in cfg
