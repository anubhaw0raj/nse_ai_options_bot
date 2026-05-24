import os
import pandas as pd
from pathlib import Path

# Define the base directory
RAW_DATA_DIR = Path("data/raw_option_chain")

def inspect_all_data_categories():
    print(f"🔍 Scanning {RAW_DATA_DIR} for the 6 main data categories...\n")
    
    if not RAW_DATA_DIR.exists():
        print(f"❌ Error: The folder {RAW_DATA_DIR} does not exist.")
        return

    # List of the specific categories we want to sample
    categories = [
        "banknifty_data/banknifty_fut",
        "banknifty_data/banknifty_options",
        "banknifty_data/banknifty_spot",
        "nifty_data/nifty_fut",
        "nifty_data/nifty_options",
        "nifty_data/nifty_spot"
    ]

    for category in categories:
        # Create the exact path to the category
        category_path = RAW_DATA_DIR / category
        
        print("=" * 80)
        print(f"📂 FOLDER: {category}")
        
        if not category_path.exists():
            print(f"  ❌ Missing folder! Could not find: {category_path}")
            print("=" * 80 + "\n")
            continue
            
        # rglob finds all CSVs, no matter how deep they are buried in Year/Month folders
        csv_files = list(category_path.rglob("*.csv"))
        
        if not csv_files:
            print(f"  ❌ No CSV files found inside {category_path}")
            print("=" * 80 + "\n")
            continue
            
        # Grab the first file to test
        first_file = csv_files[0]
        print(f"  ✅ Found {len(csv_files)} files. Sampling: {first_file.name}")
        
        try:
            # Read just the first 5 rows
            df = pd.read_csv(first_file, nrows=5)
            print("\n  📊 First 5 rows:")
            print(df)
            
            # Print the columns as a clean list
            print(f"\n  📋 Columns: {list(df.columns)}")
            
        except Exception as e:
            print(f"  ❌ Error reading file: {e}")
            
        print("=" * 80 + "\n")

if __name__ == "__main__":
    inspect_all_data_categories()