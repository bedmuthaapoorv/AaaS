import pandas as pd
# pyrefly: ignore [missing-import]
import numpy as np

# pyrefly: ignore [missing-import]
import pandas_ta as ta
# pyrefly: ignore [missing-import]
from scipy.stats import linregress
import datetime
import warnings
warnings.filterwarnings('ignore')

from universe_fetcher import get_top_stocks_by_sector
from nse_utils import fetch_stock_history

# 1. Fetch Dynamic Stock Universe by Sector
print("Initializing Dynamic Stock Universe...")
STOCK_UNIVERSE = get_top_stocks_by_sector(limit_per_sector=50)
if not STOCK_UNIVERSE:
    print("Warning: Dynamic fetch failed, falling back to basic sample.")
    STOCK_UNIVERSE = {
        "RELIANCE": {"Name": "Reliance Industries", "Sector": "Energy"},
        "TCS": {"Name": "Tata Consultancy Services", "Sector": "IT"},
    }

def fetch_data(tickers, days=400):
    """Fetch historical data for all tickers."""
    print("Fetching data...")
    to_date = datetime.date.today()
    from_date = to_date - datetime.timedelta(days=days)
    data = {}
    for ticker in tickers:
        try:
            df = fetch_stock_history(symbol=ticker, from_date=from_date, to_date=to_date, series="EQ")
            if df is not None and not df.empty and len(df) > 100:
                df = df.sort_values(by="DATE").set_index("DATE")
                df = df.rename(columns={
                    "OPEN": "open",
                    "HIGH": "high",
                    "LOW": "low",
                    "CLOSE": "close",
                    "VOLUME": "volume",
                })
                data[ticker] = df
        except Exception as e:
            print(f"Failed to fetch {ticker}: {e}")
    return data

def calculate_sector_strength(data, universe):
    """Rank sectors by average 30-day return and map each symbol to its sector's rank."""
    sector_returns = {}

    for symbol, info in universe.items():
        df = data.get(symbol)
        if df is None or len(df) < 30:
            continue

        recent = df["close"].iloc[-30:]
        pct_return = (recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0] * 100

        sector = info["Sector"]
        sector_returns.setdefault(sector, []).append(pct_return)

    sector_avg_return = {
        sector: sum(returns) / len(returns)
        for sector, returns in sector_returns.items()
    }

    ranked_sectors = sorted(sector_avg_return, key=sector_avg_return.get, reverse=True)
    sector_rank = {sector: rank + 1 for rank, sector in enumerate(ranked_sectors)}

    return {
        symbol: sector_rank.get(info["Sector"], 99)
        for symbol, info in universe.items()
    }

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
