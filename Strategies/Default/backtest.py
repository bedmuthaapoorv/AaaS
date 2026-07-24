"""
Backtests the strategy currently defined in generated_rules.py over a
historical date range.

Standalone module: only depends on universe_fetcher, nse_utils, and
generated_rules - no dependency on stock_screener.py or app.py, so this can
be lifted into a separate service later by wrapping run_backtest() in an
API endpoint.

Mechanics:
- On each trading day in [start_date, end_date], evaluates every universe
  stock using only price data available up to and including that day (no
  look-ahead), via the same generated_rules.evaluate_stock() the live
  screener uses.
- On a pass, opens a flat Rs.100 trade at the *next* trading day's open.
- Walks forward day by day (close price only, no intraday) until the close
  hits the stop-loss or take-profit threshold, or the date range ends (force
  exit at the range's last close, tagged 'RangeEnd').
- Multiple simultaneous trades on the same symbol are allowed - every
  signal opens its own independent trade.
"""

import argparse
import datetime
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
# pyrefly: ignore [missing-import]
import pandas_ta as ta

from universe_fetcher import get_top_stocks_by_sector
from nse_utils import fetch_stock_history, calculate_sector_strength
import generated_rules

WARMUP_DAYS = 400
MIN_HISTORY_ROWS = 60
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_cache")

# jugaad-data (via NSE's historical API) chunks each stock's fetch into one
# request per calendar month, and further parallelizes those chunks
# internally with its own 2-worker pool. load_universe_history additionally
# fetches FETCH_WORKERS stocks concurrently on top of that, so effective
# concurrency is FETCH_WORKERS x 2 simultaneous NSE requests. Kept
# deliberately modest (not higher) to stay well under NSE's bot-detection
# rate limiting for large multi-year backtests - see STAGGER_SECONDS below
# for the other half of that mitigation.
FETCH_WORKERS = 3
SECONDS_PER_CHUNK = 1.5
EFFECTIVE_CONCURRENCY = FETCH_WORKERS * 2

# Small random delay before each stock's fetch starts, so a 50-stock
# universe doesn't all fire its first request in the same instant (bursty
# request patterns are what typically trips bot-detection rate limits, more
# than the sustained concurrency level itself).
STAGGER_SECONDS = (0.3, 1.2)


def _month_span(from_date, to_date):
    return (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month) + 1


def estimate_runtime(start_date, end_date, limit_per_sector=50, warmup_days=WARMUP_DAYS):
    """Pre-flight estimate: how many universe stocks still need fetching from
    NSE for this date range, and a rough time range for the run. Does not
    fetch anything itself - only checks the on-disk cache and the (usually
    already-cached) universe list.

    Long ranges cost more than short ones even per-stock, since NSE's API is
    paginated by calendar month under the hood - a 5-year range issues ~60+
    monthly requests per stock, not one."""
    universe = get_top_stocks_by_sector(limit_per_sector=limit_per_sector)
    fetch_from = start_date - datetime.timedelta(days=warmup_days)

    total = len(universe)
    to_fetch = sum(
        1 for symbol in universe
        if not os.path.exists(_cache_path(symbol, fetch_from, end_date))
    )

    chunks_per_stock = _month_span(fetch_from, end_date)
    total_chunk_requests = to_fetch * chunks_per_stock
    base_seconds = (total_chunk_requests * SECONDS_PER_CHUNK) / EFFECTIVE_CONCURRENCY

    return {
        "total_stocks": total,
        "cached_stocks": total - to_fetch,
        "to_fetch_stocks": to_fetch,
        "months_per_stock": chunks_per_stock,
        "estimated_low_seconds": base_seconds,
        "estimated_high_seconds": base_seconds * 3,
    }


def _cache_path(symbol, from_date, to_date):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = f"{symbol}_{from_date.isoformat()}_{to_date.isoformat()}.csv"
    return os.path.join(CACHE_DIR, key)


def _load_symbol_history(symbol, from_date, to_date):
    """Fetch (or load cached) daily history for a symbol, normalized to
    lowercase OHLCV columns indexed by date, ascending. Historical ranges
    are immutable once in the past, so this cache never expires."""
    cache_path = _cache_path(symbol, from_date, to_date)
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")

    # Only stagger actual network fetches, not cache hits - avoids a
    # thundering-herd burst of requests when many symbols need fetching.
    time.sleep(random.uniform(*STAGGER_SECONDS))

    df = fetch_stock_history(symbol=symbol, from_date=from_date, to_date=to_date, series="EQ")
    if df is None or df.empty:
        return None

    df = df.sort_values(by="DATE").set_index("DATE")
    df = df.rename(columns={
        "OPEN": "open", "HIGH": "high", "LOW": "low", "CLOSE": "close", "VOLUME": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]]
    df.index.name = "date"

    df.to_csv(cache_path)
    return df


def load_universe_history(universe, start_date, end_date, warmup_days=WARMUP_DAYS, max_workers=FETCH_WORKERS):
    """Fetch (or load cached) history for every symbol in the universe,
    covering [start_date - warmup_days, end_date]. Fetches concurrently
    (matching universe_fetcher.py's worker count) since each symbol is an
    independent NSE request - this is the main lever on wall-clock fetch
    time for long date ranges."""
    fetch_from = start_date - datetime.timedelta(days=warmup_days)
    data = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {
            executor.submit(_load_symbol_history, symbol, fetch_from, end_date): symbol
            for symbol in universe
        }
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                df = future.result()
            except Exception:
                df = None
            if df is not None and not df.empty:
                data[symbol] = df
    return data


def _atr_at(df_slice, atr_period):
    """ATR(atr_period) as of the last row of df_slice, or None if there's
    not enough history yet."""
    if len(df_slice) < atr_period + 1:
        return None
    atr_series = ta.atr(df_slice["high"], df_slice["low"], df_slice["close"], length=atr_period)
    if atr_series is None or atr_series.empty or pd.isna(atr_series.iloc[-1]):
        return None
    return float(atr_series.iloc[-1])


def _open_and_resolve_trade(
    symbol, full_df, signal_day, end_date, closeness_score,
    exit_mode="fixed", sl_pct=None, tp_pct=None, atr_period=14, atr_multiplier=3.0,
):
    """Enter at the next trading day's open after signal_day, then walk
    forward (close-only, no intraday) until the exit condition fires or
    end_date is reached.

    exit_mode="fixed": exits at fixed sl_pct/tp_pct off the entry price.
    exit_mode="trailing_atr": no fixed take-profit - trails a stop at
    (highest close since entry) - atr_multiplier * ATR, where ATR is
    computed once at entry (using only data up to and including signal_day,
    so no look-ahead) and held fixed for the life of the trade. Lets winners
    run; only exits on the downside trail or RangeEnd.
    """
    future = full_df[(full_df.index.date > signal_day) & (full_df.index.date <= end_date)]
    if future.empty:
        return None

    entry_date = future.index[0]
    entry_price = float(future["open"].iloc[0])

    atr_at_entry = None
    if exit_mode == "trailing_atr":
        history_to_signal = full_df[full_df.index.date <= signal_day]
        atr_at_entry = _atr_at(history_to_signal, atr_period)
        if atr_at_entry is None:
            return None  # not enough history to size a trailing stop safely
        sl_price = entry_price - atr_multiplier * atr_at_entry
        tp_price = None
    else:
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)

    highest_close = entry_price
    exit_date, exit_price, exit_reason = None, None, None
    for ts, row in future.iterrows():
        close = float(row["close"])

        if exit_mode == "trailing_atr":
            highest_close = max(highest_close, close)
            trailing_stop = highest_close - atr_multiplier * atr_at_entry
            if close <= trailing_stop:
                exit_date, exit_price, exit_reason = ts, close, "TrailingATR"
                break
        else:
            if close <= sl_price:
                exit_date, exit_price, exit_reason = ts, close, "SL"
                break
            if close >= tp_price:
                exit_date, exit_price, exit_reason = ts, close, "TP"
                break

    if exit_date is None:
        exit_date = future.index[-1]
        exit_price = float(future["close"].iloc[-1])
        exit_reason = "RangeEnd"

    profit_rs = (exit_price - entry_price) / entry_price * 100  # on a flat Rs.100 stake

    return {
        "Symbol": symbol,
        "SignalDate": signal_day,
        "EntryDate": entry_date.date(),
        "EntryPrice": round(entry_price, 2),
        "ExitDate": exit_date.date(),
        "ExitPrice": round(exit_price, 2),
        "ExitReason": exit_reason,
        "ATRAtEntry": round(atr_at_entry, 2) if atr_at_entry is not None else None,
        "ClosenessScore": round(float(closeness_score), 2),
        "ProfitRs": round(profit_rs, 2),
    }


def run_backtest(
    start_date, end_date, sl_pct=None, tp_pct=None, limit_per_sector=50, progress_callback=None,
    exit_mode="fixed", atr_period=14, atr_multiplier=3.0,
):
    """Run the backtest. Returns (trades_df, summary_df).

    progress_callback, if given, is called as progress_callback(done, total, day)
    once per simulated trading day.

    exit_mode="fixed" (default) uses sl_pct/tp_pct off the entry price.
    exit_mode="trailing_atr" ignores sl_pct/tp_pct and instead trails a stop
    at atr_multiplier x ATR(atr_period) below the highest close since entry,
    with no fixed take-profit.
    """
    if exit_mode == "fixed" and (sl_pct is None or tp_pct is None):
        raise ValueError("sl_pct and tp_pct are required when exit_mode='fixed'.")
    universe = get_top_stocks_by_sector(limit_per_sector=limit_per_sector)
    if not universe:
        raise RuntimeError("Could not build stock universe.")

    data = load_universe_history(universe, start_date, end_date)
    if not data:
        raise RuntimeError("No historical data could be fetched for any stock in the universe.")

    all_dates = sorted({
        ts.date() for df in data.values() for ts in df.index
        if start_date <= ts.date() <= end_date
    })

    # Precompute each symbol's dates as a plain list once (avoids repeated
    # `.index.date` conversion, which is the expensive part of slicing).
    symbol_dates = {symbol: df.index.date for symbol, df in data.items()}
    # Pointer into each symbol's rows: index of the last row known to be
    # available as of the current day. Advances monotonically as `day`
    # advances, so building each day's snapshot is O(stocks) instead of
    # O(stocks x rows) - the loop below never re-scans older rows.
    pos = {symbol: -1 for symbol in data}

    trades = []
    total_days = len(all_dates)

    for day_idx, day in enumerate(all_dates):
        if progress_callback:
            progress_callback(day_idx + 1, total_days, day)

        snapshot = {}
        for symbol, df in data.items():
            dates = symbol_dates[symbol]
            p = pos[symbol]
            n = len(dates)
            while p + 1 < n and dates[p + 1] <= day:
                p += 1
            pos[symbol] = p

            if p + 1 >= MIN_HISTORY_ROWS and p >= 0 and dates[p] == day:
                snapshot[symbol] = df.iloc[:p + 1]

        if not snapshot:
            continue

        sector_ranks_today = calculate_sector_strength(snapshot, universe)

        for symbol, df_slice in snapshot.items():
            try:
                result = generated_rules.evaluate_stock(symbol, df_slice, universe, sector_ranks_today)
            except Exception:
                continue

            if not result.get("Passed"):
                continue

            trade = _open_and_resolve_trade(
                symbol, data[symbol], day, end_date, result.get("ClosenessScore", 0.0),
                exit_mode=exit_mode, sl_pct=sl_pct, tp_pct=tp_pct,
                atr_period=atr_period, atr_multiplier=atr_multiplier,
            )
            if trade:
                trades.append(trade)

    trades_df = pd.DataFrame(trades)
    summary_df = summarize_trades(trades_df)
    return trades_df, summary_df


def summarize_trades(trades_df):
    """Bucket trades by ClosenessScore and report win rate / profit per bucket."""
    columns = ["ScoreBucket", "Trades", "WinRatePct", "MeanProfitRs", "MedianProfitRs", "TotalProfitRs"]
    if trades_df.empty:
        return pd.DataFrame(columns=columns)

    bins = [0, 20, 40, 60, 80, 100]
    labels = ["0-20", "20-40", "40-60", "60-80", "80-100"]
    trades_df = trades_df.copy()
    trades_df["ScoreBucket"] = pd.cut(trades_df["ClosenessScore"], bins=bins, labels=labels, include_lowest=True)

    summary = trades_df.groupby("ScoreBucket", observed=True).agg(
        Trades=("ProfitRs", "count"),
        WinRatePct=("ProfitRs", lambda s: round((s > 0).mean() * 100, 1)),
        MeanProfitRs=("ProfitRs", lambda s: round(s.mean(), 2)),
        MedianProfitRs=("ProfitRs", lambda s: round(s.median(), 2)),
        TotalProfitRs=("ProfitRs", lambda s: round(s.sum(), 2)),
    ).reset_index()

    return summary


def _parse_date(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Backtest the current generated_rules.py strategy.")
    parser.add_argument("--start", required=True, type=_parse_date, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=_parse_date, help="End date YYYY-MM-DD")
    parser.add_argument("--exit-mode", choices=["fixed", "trailing_atr"], default="fixed")
    parser.add_argument("--sl", type=float, help="Stop-loss percent, e.g. 5 (required if --exit-mode=fixed)")
    parser.add_argument("--tp", type=float, help="Take-profit percent, e.g. 10 (required if --exit-mode=fixed)")
    parser.add_argument("--atr-period", type=int, default=14, help="ATR lookback period (trailing_atr mode)")
    parser.add_argument("--atr-multiplier", type=float, default=3.0, help="ATR multiplier for the trailing stop (trailing_atr mode)")
    parser.add_argument("--limit-per-sector", type=int, default=50)
    parser.add_argument("--trades-out", default="backtest_trades.csv")
    parser.add_argument("--summary-out", default="backtest_summary.csv")
    args = parser.parse_args()

    if args.exit_mode == "fixed" and (args.sl is None or args.tp is None):
        parser.error("--sl and --tp are required when --exit-mode=fixed")

    def progress(done, total, day):
        print(f"Evaluating day {done}/{total} ({day})...")

    trades_df, summary_df = run_backtest(
        args.start, args.end, sl_pct=args.sl, tp_pct=args.tp,
        limit_per_sector=args.limit_per_sector,
        progress_callback=progress,
        exit_mode=args.exit_mode,
        atr_period=args.atr_period,
        atr_multiplier=args.atr_multiplier,
    )

    trades_df.to_csv(args.trades_out, index=False)
    summary_df.to_csv(args.summary_out, index=False)

    print(f"\n{len(trades_df)} trades simulated.")
    print(summary_df.to_string(index=False))
    print(f"\nTrades saved to {args.trades_out}")
    print(f"Summary saved to {args.summary_out}")


if __name__ == "__main__":
    main()
