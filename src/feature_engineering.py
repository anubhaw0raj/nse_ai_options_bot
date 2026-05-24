import pandas as pd
import numpy as np
from pathlib import Path
import py_vollib_vectorized 
from py_vollib_vectorized.api import get_all_greeks, vectorized_implied_volatility

class FeatureEngineer:
    def __init__(self, risk_free_rate=0.05):
        self.risk_free_rate = risk_free_rate

    def _convert_datetime(self, df):
        """Combines date and time columns into a single datetime object."""
        if 'date' in df.columns and 'time' in df.columns:
            # We convert to string first to handle cases where pandas parsed it as int (e.g. 20200102)
            df['datetime'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
        return df

    def _parse_symbol(self, df):
        """Extracts components from option symbol (e.g., NIFTY02JAN2010100PE)."""
        if 'symbol' in df.columns and df['symbol'].str.contains('CE|PE').any():
            # Regex to extract Underlying, Expiry, Strike, Type
            # Pattern: (Underlying)(Expiry)(Strike)(Type)
            pattern = r'^([A-Z]+)(\d{2}[A-Z]{3}\d{2})(\d+)(CE|PE)$'
            extracted = df['symbol'].str.extract(pattern)
            df['underlying'] = extracted[0]
            df['expiry_str'] = extracted[1]
            df['strike'] = extracted[2].astype(float)
            df['option_type'] = extracted[3]
            
            # Convert expiry to datetime
            df['expiry_date'] = pd.to_datetime(df['expiry_str'], format='%d%b%y', errors='coerce')
            # Assuming expiry happens at 15:30:00 on the expiry day
            df['expiry_datetime'] = df['expiry_date'] + pd.Timedelta(hours=15, minutes=30)
            
        return df

    def _calculate_tte(self, df):
        """Calculates Time to Expiry (TTE) in annualized terms."""
        if 'expiry_datetime' in df.columns and 'datetime' in df.columns:
            # TTE in seconds
            tte_seconds = (df['expiry_datetime'] - df['datetime']).dt.total_seconds()
            
            # Avoid <= 0 TTE (if traded exactly on expiry minute or after)
            # Set minimum TTE to 1 minute to avoid divide by zero in greeks
            tte_seconds = np.where(tte_seconds <= 0, 60, tte_seconds)
            
            # Annualize (365 days)
            df['TTE'] = tte_seconds / (365 * 24 * 60 * 60)
        return df

    def _calculate_greeks(self, df):
        """Calculates IV and Greeks using py_vollib_vectorized."""
        required_cols = ['close_opt', 'close_spot', 'strike', 'TTE', 'option_type']
        
        if not all(col in df.columns for col in required_cols):
            return df
            
        # Map CE/PE to c/p for py_vollib
        flag = df['option_type'].map({'CE': 'c', 'PE': 'p'}).values
        
        S = df['close_spot'].values.astype(float)
        K = df['strike'].values.astype(float)
        t = df['TTE'].values.astype(float)
        r = np.full_like(S, self.risk_free_rate)
        price = df['close_opt'].values.astype(float)
        
        # Calculate IV
        df['IV'] = vectorized_implied_volatility(price, S, K, t, r, flag, q=0, return_as='numpy', on_error='ignore')
        
        # Replace NaN IV with a small number or 0 for Greeks calculation to not crash
        iv_for_greeks = np.nan_to_num(df['IV'].values, nan=0.0001)
        
        # Calculate Greeks
        greeks = get_all_greeks(flag, S, K, t, r, iv_for_greeks, q=0, return_as='dict')
        
        df['delta'] = greeks['delta']
        df['gamma'] = greeks['gamma']
        df['theta'] = greeks['theta']
        df['vega']  = greeks['vega']
        df['rho']   = greeks['rho']
        
        return df

    def _calculate_momentum(self, df):
        """Calculates 1-minute and 5-minute rolling returns for options and spot."""
        # Ensure sorted by time for accurate pct_change
        df = df.sort_values(by=['symbol', 'datetime'])
        
        # Option returns (multiplied by 100 for percentage scale)
        df['opt_ret_1m'] = df.groupby('symbol')['close_opt'].pct_change(1) * 100
        df['opt_ret_5m'] = df.groupby('symbol')['close_opt'].pct_change(5) * 100
        
        # Spot returns
        df['spot_ret_1m'] = df.groupby('symbol')['close_spot'].pct_change(1) * 100
        df['spot_ret_5m'] = df.groupby('symbol')['close_spot'].pct_change(5) * 100
        
        return df

    def process_single_day(self, opt_path, spot_path):
        """Processes a single day of option and spot data."""
        print(f"Loading Options: {opt_path}")
        df_opt = pd.read_csv(opt_path)
        print(f"Loading Spot: {spot_path}")
        df_spot = pd.read_csv(spot_path)
        
        # 1. Datetime Conversion
        df_opt = self._convert_datetime(df_opt)
        df_spot = self._convert_datetime(df_spot)
        
        # 2. Symbol Parsing & TTE
        df_opt = self._parse_symbol(df_opt)
        df_opt = self._calculate_tte(df_opt)
        
        # 3. Merge Spot and Options on datetime
        df_merged = pd.merge(
            df_opt,
            df_spot[['datetime', 'open', 'high', 'low', 'close']],
            on='datetime',
            how='inner',
            suffixes=('_opt', '_spot')
        )
        
        if len(df_merged) == 0:
            print("Warning: Inner merge resulted in 0 rows. Datetimes might not match exactly.")
            return df_merged

        # 4. Calculate Moneyness
        df_merged['moneyness'] = df_merged['close_spot'] / df_merged['strike']
        
        # 5. Calculate Greeks
        df_merged = self._calculate_greeks(df_merged)
        
        # 6. Calculate Momentum
        df_merged = self._calculate_momentum(df_merged)
        
        # 7. Memory Optimization
        float64_cols = df_merged.select_dtypes(include=['float64']).columns
        df_merged[float64_cols] = df_merged[float64_cols].astype('float32')
        
        return df_merged

if __name__ == "__main__":
    RAW_DATA_DIR = Path("data/raw_option_chain")
    opt_dir = RAW_DATA_DIR / "banknifty_data/banknifty_options"
    spot_dir = RAW_DATA_DIR / "banknifty_data/banknifty_spot"
    
    print(f"Searching for data in {RAW_DATA_DIR}...")
    opt_files = list(opt_dir.rglob("*.csv"))
    
    if not opt_files:
        print("No option files found. Ensure the raw_option_chain folder has the expected structure.")
    else:
        opt_path = opt_files[0]
        try:
            df_opt_sample = pd.read_csv(opt_path, nrows=1)
            opt_date = df_opt_sample['date'].iloc[0]
            
            spot_files = list(spot_dir.rglob("*.csv"))
            matched_spot = None
            
            for sf in spot_files:
                try:
                    df_spot_sample = pd.read_csv(sf, nrows=1)
                    if df_spot_sample['date'].iloc[0] == opt_date:
                        matched_spot = sf
                        break
                except Exception:
                    continue
                    
            if matched_spot:
                fe = FeatureEngineer(risk_free_rate=0.05)
                df_processed = fe.process_single_day(opt_path, matched_spot)
                
                if len(df_processed) > 0:
                    print(f"\nProcessing Complete! Processed {len(df_processed)} rows.")
                    print("\nFirst 5 rows of engineered features:")
                    cols_to_show = ['datetime', 'symbol', 'close_opt', 'close_spot', 'strike', 'TTE', 'moneyness', 'IV', 'delta', 'theta']
                    print(df_processed[cols_to_show].head())
                    print("\nAll columns:", list(df_processed.columns))
                    print("\nData types (Memory Optimized):")
                    print(df_processed.dtypes)
            else:
                print(f"Could not find matching spot file for date: {opt_date}")
        except Exception as e:
            print(f"Error during processing: {e}")
