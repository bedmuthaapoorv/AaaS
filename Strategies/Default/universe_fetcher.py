# pyrefly: ignore [missing-import]
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta

CACHE_FILE = "universe_cache.json"
CACHE_EXPIRY_DAYS = 1

def fetch_nifty_500():
    """Fetches the Nifty 500 constituents from NSE."""
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    try:
        df = pd.read_csv(url)
        # Columns: Company Name, Industry, Symbol, Series, ISIN Code
        return df
    except Exception as e:
        print(f"Error fetching Nifty 500 list: {e}")
        return None

def get_top_stocks_by_sector(limit_per_sector=50):
    """
    Fetches the Nifty 500 stocks, calculates their 6-month performance, 
    and returns the top `limit_per_sector` stocks per sector.
    """
    # Check cache first
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
                cache_date = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cache_date < timedelta(days=CACHE_EXPIRY_DAYS):
                    print("Loaded stock universe from cache.")
                    return cached_data['universe']
        except Exception as e:
            print(f"Error reading cache, fetching fresh data: {e}")

    print("Fetching Nifty 500 list from NSE...")
    nifty500_df = fetch_nifty_500()
    if nifty500_df is None or nifty500_df.empty:
        print("Failed to fetch Nifty 500, returning empty universe.")
        return {}

    # Map Symbol to .NS for yfinance
    nifty500_df['Yahoo_Ticker'] = nifty500_df['Symbol'] + ".NS"
    tickers_list = nifty500_df['Yahoo_Ticker'].tolist()

    print(f"Fetching 6-month historical data for {len(tickers_list)} stocks...")
    # yfinance bulk download is much faster than one-by-one
    data = yf.download(tickers_list, period="6mo", progress=False, group_by="ticker")

    performance = []
    
    for _, row in nifty500_df.iterrows():
        ticker = row['Yahoo_Ticker']
        try:
            # Check if we have data for this ticker
            if ticker in data and not data[ticker].empty:
                # Need to handle single/multi-index columns for yfinance download
                df = data[ticker].dropna(subset=['Close'])
                if not df.empty and len(df) > 10:
                    first_close = df['Close'].iloc[0]
                    # if Close is a series, get scalar
                    if isinstance(first_close, pd.Series):
                        first_close = first_close.iloc[0]
                    
                    last_close = df['Close'].iloc[-1]
                    if isinstance(last_close, pd.Series):
                        last_close = last_close.iloc[0]
                        
                    # Calculate % return
                    pct_return = float((last_close - first_close) / first_close * 100)
                    
                    performance.append({
                        "Ticker": ticker,
                        "Name": row['Company Name'],
                        "Sector": row['Industry'],
                        "Return": pct_return
                    })
        except Exception as e:
            # Some tickers might fail or have no data
            pass
            
    perf_df = pd.DataFrame(performance)
    
    if perf_df.empty:
        print("Failed to calculate performance, returning empty universe.")
        return {}

    # Group by Sector and get top N performers
    print("Ranking stocks by sector...")
    top_stocks = {}
    
    for sector, group in perf_df.groupby('Sector'):
        # Sort by return descending
        top_group = group.sort_values(by='Return', ascending=False).head(limit_per_sector)
        for _, row in top_group.iterrows():
            top_stocks[row['Ticker']] = {
                "Name": row['Name'],
                "Sector": row['Sector']
            }

    # Save to cache
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "universe": top_stocks
            }, f, indent=4)
        print("Saved fresh stock universe to cache.")
    except Exception as e:
        print(f"Warning: Failed to save cache: {e}")

    return top_stocks

if __name__ == "__main__":
    # Test script execution
    universe = get_top_stocks_by_sector(limit_per_sector=5)
    print(f"Total stocks in dynamic universe: {len(universe)}")
    print("Sample stocks:")
    for i, (k, v) in enumerate(universe.items()):
        if i < 10:
            print(f"{k}: {v}")
