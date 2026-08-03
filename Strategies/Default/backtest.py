"""
Backtests the strategy currently defined in generated_rules.py, using the
exit logic currently defined in generated_exit_strategy.py, over a
historical date range.

Standalone module: only depends on universe_fetcher, nse_utils,
generated_rules, and generated_exit_strategy - no dependency on
stock_screener.py or app.py, so this can be lifted into a separate service
later by wrapping run_backtest() in an API endpoint.

Mechanics:
- On each trading day in [start_date, end_date], evaluates every universe
  stock using only price data available up to and including that day (no
  look-ahead), via the same generated_rules.evaluate_stock() the live
  screener uses.
- On a pass, opens a flat Rs.100 trade at the *next* trading day's open.
- Walks forward day by day (close price only, no intraday by default -
  generated_exit_strategy.py decides the exact exit condition, since it's
  generated from exit_rules.md the same way generated_rules.py is generated
  from rules.md) until generated_exit_strategy.resolve_exit() finds an exit,
  or the date range ends. This module - not the generated exit logic -
  always force-closes any still-open trade at the range's last close,
  tagged 'RangeEnd', so that fallback can never be silently missed by a
  regenerated exit strategy.
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

from universe_fetcher import get_top_stocks_by_sector
from nse_utils import fetch_stock_history, calculate_sector_strength, calculate_market_breadth
import generated_rules
import generated_exit_strategy

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


def _open_and_resolve_trade(symbol, full_df, signal_day, end_date, closeness_score):
    """Enter at the next trading day's open after signal_day, then hand off
    to generated_exit_strategy.resolve_exit() to decide when to exit.

    generated_exit_strategy.py is regenerated from exit_rules.md the same
    way generated_rules.py is regenerated from rules.md - this function
    doesn't know or care what exit logic it implements (fixed SL/TP,
    trailing ATR, or anything else the user writes).

    If resolve_exit() returns None (no exit condition fired) or raises, this
    function - not the generated exit logic - force-closes the trade at the
    last available close in range, tagged 'RangeEnd'. This guarantee holds
    regardless of what exit_rules.md says, so a regenerated exit strategy
    can never accidentally leave a trade open forever.
    """
    future = full_df[(full_df.index.date > signal_day) & (full_df.index.date <= end_date)]
    if future.empty:
        return None

    entry_date = future.index[0]
    entry_price = float(future["open"].iloc[0])
    signal_history = full_df[full_df.index.date <= signal_day]

    exit_result = None
    try:
        exit_result = generated_exit_strategy.resolve_exit(entry_price, entry_date, signal_history, future)
    except Exception:
        exit_result = None

    if exit_result is not None:
        exit_date = exit_result["ExitDate"]
        exit_price = float(exit_result["ExitPrice"])
        exit_reason = exit_result["ExitReason"]
    else:
        exit_date = future.index[-1]
        exit_price = float(future["close"].iloc[-1])
        exit_reason = "RangeEnd"

    # pd.Timestamp is itself a subclass of datetime.date (via datetime.datetime),
    # so a plain isinstance check can't distinguish them - always normalize
    # through pd.Timestamp(...).date() instead, which is safe for a
    # datetime.date, a datetime.datetime, or a pd.Timestamp alike.
    exit_date = pd.Timestamp(exit_date).date()
    profit_rs = (exit_price - entry_price) / entry_price * 100  # on a flat Rs.100 stake

    return {
        "Symbol": symbol,
        "SignalDate": signal_day,
        "EntryDate": entry_date.date(),
        "EntryPrice": round(entry_price, 2),
        "ExitDate": exit_date,
        "ExitPrice": round(exit_price, 2),
        "ExitReason": exit_reason,
        "ClosenessScore": round(float(closeness_score), 2),
        "ProfitRs": round(profit_rs, 2),
    }


def run_backtest(start_date, end_date, limit_per_sector=50, progress_callback=None):
    """Run the backtest. Returns (trades_df, summary_df).

    progress_callback, if given, is called as progress_callback(done, total, day)
    once per simulated trading day.

    Exit logic comes entirely from generated_exit_strategy.py (regenerated
    from exit_rules.md) - this function doesn't take SL/TP/ATR parameters
    itself; edit exit_rules.md and regenerate to change exit behavior.
    """
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
        market_breadth_today = calculate_market_breadth(snapshot)

        for symbol, df_slice in snapshot.items():
            try:
                result = generated_rules.evaluate_stock(symbol, df_slice, universe, sector_ranks_today, market_breadth_today)
            except Exception:
                continue

            if not result.get("Passed"):
                continue

            trade = _open_and_resolve_trade(
                symbol, data[symbol], day, end_date, result.get("ClosenessScore", 0.0)
            )
            if trade:
                trades.append(trade)

    trade_columns = [
        "Symbol", "SignalDate", "EntryDate", "EntryPrice",
        "ExitDate", "ExitPrice", "ExitReason", "ClosenessScore", "ProfitRs",
    ]
    trades_df = pd.DataFrame(trades, columns=trade_columns)
    summary_df = summarize_trades(trades_df)
    return trades_df, summary_df


def simulate_portfolio(trades_df, initial_capital=100000.0, max_concurrent_positions=10):
    """
    Simulates a real, capital-constrained portfolio on top of the already
    fully-resolved trade list from run_backtest() (each trade's entry/exit
    dates and % return are computed independently of capital - this
    function only decides which signals the portfolio actually had room to
    fund, and compounds capital as positions open and close).

    Position sizing: each newly funded trade gets
    (current total equity) / max_concurrent_positions - an equal-weight
    slot recomputed fresh each time, so position size compounds with
    portfolio growth. When more signals fire on a day than there are free
    slots, higher ClosenessScore gets priority; the rest are marked
    unfunded (skipped for lack of capital), not opened at a smaller size.

    Returns (portfolio_df, trades_df) where portfolio_df is a chronological
    equity curve (Date, Equity) and trades_df is the input with two added
    columns: Funded (bool) and AllocatedCapital (float).
    """
    trades = trades_df.copy()
    if trades.empty:
        trades["Funded"] = pd.Series(dtype=bool)
        trades["AllocatedCapital"] = pd.Series(dtype=float)
        return pd.DataFrame(columns=["Date", "Equity"]), trades

    trades["EntryDate"] = pd.to_datetime(trades["EntryDate"])
    trades["ExitDate"] = pd.to_datetime(trades["ExitDate"])

    entries_by_date = {}
    for idx, row in trades.iterrows():
        entries_by_date.setdefault(row["EntryDate"], []).append(idx)

    cash = initial_capital
    open_positions = {}  # idx -> allocated capital
    funded = {}
    allocated = {}
    equity_curve = []

    all_dates = sorted(set(trades["EntryDate"]).union(trades["ExitDate"]))
    for date in all_dates:
        # Exits before entries on the same day, so freed capital is
        # available for same-day reinvestment.
        exits_today = trades.index[trades["ExitDate"] == date]
        for idx in exits_today:
            if funded.get(idx):
                profit_pct = trades.loc[idx, "ProfitRs"]
                cash += open_positions.pop(idx) * (1 + profit_pct / 100)

        entries_today = sorted(
            entries_by_date.get(date, []),
            key=lambda i: trades.loc[i, "ClosenessScore"],
            reverse=True,
        )
        for idx in entries_today:
            if len(open_positions) >= max_concurrent_positions:
                funded[idx] = False
                continue
            total_equity = cash + sum(open_positions.values())
            size = total_equity / max_concurrent_positions
            if size <= cash:
                open_positions[idx] = size
                cash -= size
                funded[idx] = True
                allocated[idx] = size
            else:
                funded[idx] = False

        equity_curve.append({"Date": date, "Equity": cash + sum(open_positions.values())})

    trades["Funded"] = trades.index.map(lambda i: funded.get(i, False))
    trades["AllocatedCapital"] = trades.index.map(lambda i: round(allocated.get(i, 0.0), 2))
    trades["EntryDate"] = trades["EntryDate"].dt.date
    trades["ExitDate"] = trades["ExitDate"].dt.date

    portfolio_df = pd.DataFrame(equity_curve)
    return portfolio_df, trades


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
    parser = argparse.ArgumentParser(
        description="Backtest the current generated_rules.py strategy using generated_exit_strategy.py for exits."
    )
    parser.add_argument("--start", required=True, type=_parse_date, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=_parse_date, help="End date YYYY-MM-DD")
    parser.add_argument("--limit-per-sector", type=int, default=50)
    parser.add_argument("--initial-capital", type=float, default=100000.0, help="Starting portfolio capital, e.g. 100000")
    parser.add_argument("--max-positions", type=int, default=10, help="Max number of concurrent open positions")
    parser.add_argument("--trades-out", default="backtest_trades.csv")
    parser.add_argument("--summary-out", default="backtest_summary.csv")
    parser.add_argument("--portfolio-out", default="backtest_portfolio.csv")
    args = parser.parse_args()

    def progress(done, total, day):
        print(f"Evaluating day {done}/{total} ({day})...")

    trades_df, summary_df = run_backtest(
        args.start, args.end,
        limit_per_sector=args.limit_per_sector,
        progress_callback=progress,
    )

    portfolio_df, trades_df = simulate_portfolio(
        trades_df, initial_capital=args.initial_capital, max_concurrent_positions=args.max_positions
    )

    trades_df.to_csv(args.trades_out, index=False)
    summary_df.to_csv(args.summary_out, index=False)
    portfolio_df.to_csv(args.portfolio_out, index=False)

    print(f"\n{len(trades_df)} trades simulated.")
    print(summary_df.to_string(index=False))

    if not portfolio_df.empty:
        final_equity = portfolio_df["Equity"].iloc[-1]
        total_return_pct = (final_equity - args.initial_capital) / args.initial_capital * 100
        funded_count = int(trades_df["Funded"].sum())
        skipped_count = len(trades_df) - funded_count
        print(f"\n--- PORTFOLIO ({args.max_positions} concurrent slots, Rs.{args.initial_capital:,.0f} start) ---")
        print(f"Funded trades: {funded_count} (skipped for lack of capital: {skipped_count})")
        print(f"Final equity: Rs.{final_equity:,.2f}")
        print(f"Total return: {total_return_pct:.2f}%")

    print(f"\nTrades saved to {args.trades_out}")
    print(f"Summary saved to {args.summary_out}")
    print(f"Portfolio equity curve saved to {args.portfolio_out}")


if __name__ == "__main__":
    main()
