import time
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="jugaad_data")

from jugaad_data.nse import stock_df


def fetch_stock_history(symbol, from_date, to_date, series="EQ", retries=3, backoff_seconds=2):
    """Fetch NSE history for a symbol, retrying transient failures (rate
    limiting / bot-detection blocks show up as empty or non-JSON responses)."""
    last_error = None
    for attempt in range(retries):
        try:
            return stock_df(symbol=symbol, from_date=from_date, to_date=to_date, series=series)
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(backoff_seconds * (attempt + 1))
    raise last_error


def calculate_sector_strength(data, universe):
    """Rank sectors by average 30-day return and map each symbol to its sector's rank.

    `data` maps symbol -> a DataFrame with a lowercase 'close' column, sorted
    ascending by date. Only uses data already present in each DataFrame, so
    passing a date-truncated slice (as the backtester does) keeps this
    look-ahead free.
    """
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
