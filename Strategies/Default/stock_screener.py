# pyrefly: ignore [missing-import]
import yfinance as yf
import pandas as pd
import numpy as np

# pyrefly: ignore [missing-import]
import pandas_ta as ta
from scipy.stats import linregress
import datetime
import warnings
warnings.filterwarnings('ignore')

from universe_fetcher import get_top_stocks_by_sector

# 1. Fetch Dynamic Stock Universe by Sector
print("Initializing Dynamic Stock Universe...")
STOCK_UNIVERSE = get_top_stocks_by_sector(limit_per_sector=50)
if not STOCK_UNIVERSE:
    print("Warning: Dynamic fetch failed, falling back to basic sample.")
    STOCK_UNIVERSE = {
        "RELIANCE.NS": {"Name": "Reliance Industries", "Sector": "Energy"},
        "TCS.NS": {"Name": "Tata Consultancy Services", "Sector": "IT"},
    }

def fetch_data(tickers, period="1y"):
    """Fetch historical data for all tickers."""
    print("Fetching data...")
    data = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, period=period, progress=False)
            if not df.empty and len(df) > 100:
                # Flatten MultiIndex columns if present (yfinance sometimes returns this)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[ticker] = df
        except Exception as e:
            print(f"Failed to fetch {ticker}: {e}")
    return data

def calculate_sector_strength(data, universe):
    """Calculate relative sector strength (mock implementation for demonstration)."""
    # In a real scenario, this would aggregate returns and volume across all stocks in a sector.
    # Here, we assign random ranks for demonstration since we have a tiny universe.
    sectors = list(set([info["Sector"] for info in universe.values()]))
    
    # Let's say Financial Services and IT are always top for testing
    ranked_sectors = {
        "Financial Services": 1,
        "IT": 2,
        "Energy": 3,
        "Consumer Goods": 4,
        "Telecommunication": 5,
        "Construction": 6
    }
    return ranked_sectors

def find_trendline_touches(df):
    """Find trendline touches and distance."""
    # Simplified approach for demonstration
    # In a robust system, you'd use pivot points (argrelextrema).
    # Here we just look at the lowest lows over the last 90 days.
    recent = df.iloc[-90:].copy()
    if len(recent) < 90:
        return 0, 100, 0
    
    # We will simulate the trendline quality for now to allow some stocks to pass
    # Real trendline detection is quite complex for a single script.
    
    # Let's assume a dummy touch count between 1 and 3, and a dummy distance
    import random
    touches = random.choice([1, 2, 3])
    distance = random.uniform(0.5, 5.0)
    slope = random.uniform(-0.5, 1.5)
    
    return touches, distance, slope

def analyze_stocks(data, universe, sector_ranks):
    results = []

    import generated_rules

    for symbol, df in data.items():
        if len(df) < 50:
            continue

        try:
            result = generated_rules.evaluate_stock(
                symbol,
                df,
                universe,
                sector_ranks
            )

            if result:
                results.append(result)

        except Exception as e:
            print(f"Error evaluating {symbol}: {e}")

            results.append({
                "Symbol": symbol,
                "Passed": False,
                "ClosenessScore": 0,
                "FailedRules": [str(e)],
                "Details": {}
            })

    return results

def main():
    tickers = list(STOCK_UNIVERSE.keys())
    data = fetch_data(tickers)
    sector_ranks = calculate_sector_strength(data, STOCK_UNIVERSE)
    results = analyze_stocks(data, STOCK_UNIVERSE, sector_ranks)

    if not results:
        print("No results generated.")
        return

    csv_rows = []

    for result in results:

        row = {
            "Symbol": result["Symbol"],
            "Passed": result["Passed"],
            "ClosenessScore": round(
                result["ClosenessScore"],
                2
            ),
            "FailedRules": "; ".join(
                result["FailedRules"]
            )
        }

        details = result.get("Details", {})

        for key, value in details.items():
            row[key] = value

        csv_rows.append(row)

    df_results = pd.DataFrame(csv_rows)

    df_results = df_results.sort_values(
        by="ClosenessScore",
        ascending=False
    )

    print("\n--- BEST STOCKS BY CLOSENESS SCORE ---")
    print(df_results.head(20).to_string(index=False))

    df_results.to_csv(
        "stock_report.csv",
        index=False
    )

    print(
        "\nResults saved to stock_report.csv"
    )

if __name__ == "__main__":
    main()
