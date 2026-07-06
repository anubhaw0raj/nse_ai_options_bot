"""Quick sanity inspector: sample one CSV from each raw data category.

Run:  python -m src.data.inspector
"""

from pathlib import Path

import pandas as pd

RAW_DATA_DIR = Path("data/raw_option_chain")

CATEGORIES = [
    "banknifty_data/banknifty_fut",
    "banknifty_data/banknifty_options",
    "banknifty_data/banknifty_spot",
    "nifty_data/nifty_fut",
    "nifty_data/nifty_options",
    "nifty_data/nifty_spot",
]


def inspect_all_data_categories(raw_dir: Path = RAW_DATA_DIR):
    print(f"Scanning {raw_dir} ...\n")
    if not raw_dir.exists():
        print(f"ERROR: {raw_dir} does not exist.")
        return

    for category in CATEGORIES:
        path = raw_dir / category
        print("=" * 80)
        print(f"FOLDER: {category}")
        if not path.exists():
            print(f"  missing: {path}")
            continue
        csv_files = list(path.rglob("*.csv"))
        if not csv_files:
            print("  no CSV files found")
            continue
        first = csv_files[0]
        print(f"  {len(csv_files)} files. Sampling {first.name}:")
        try:
            df = pd.read_csv(first, nrows=5)
            print(df)
            print(f"  Columns: {list(df.columns)}")
        except Exception as e:
            print(f"  read error: {e}")
    print("=" * 80)


if __name__ == "__main__":
    inspect_all_data_categories()
