import time

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
