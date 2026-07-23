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
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

from universe_fetcher import get_top_stocks_by_sector
from nse_utils import fetch_stock_history, calculate_sector_strength
import generated_rules

WARMUP_DAYS = 400
MIN_HISTORY_ROWS = 60
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_cache")
FETCH_SECONDS_PER_STOCK = 3  # rough average per stock, including retries


def estimate_runtime(start_date, end_date, limit_per_sector=50, warmup_days=WARMUP_DAYS):
    """Pre-flight estimate: how many universe stocks still need fetching from
    NSE for this date range, and a rough time range for the run. Does not
    fetch anything itself - only checks the on-disk cache and the (usually
    already-cached) universe list."""
    universe = get_top_stocks_by_sector(limit_per_sector=limit_per_sector)
    fetch_from = start_date - datetime.timedelta(days=warmup_days)

    total = len(universe)
    to_fetch = sum(
        1 for symbol in universe
        if not os.path.exists(_cache_path(symbol, fetch_from, end_date))
    )

    return {
        "total_stocks": total,
        "cached_stocks": total - to_fetch,
        "to_fetch_stocks": to_fetch,
        "estimated_low_seconds": to_fetch * FETCH_SECONDS_PER_STOCK,
        "estimated_high_seconds": to_fetch * FETCH_SECONDS_PER_STOCK * 3,
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


def load_universe_history(universe, start_date, end_date, warmup_days=WARMUP_DAYS):
    """Fetch (or load cached) history for every symbol in the universe,
    covering [start_date - warmup_days, end_date]."""
    fetch_from = start_date - datetime.timedelta(days=warmup_days)
    data = {}
    for symbol in universe:
        try:
            df = _load_symbol_history(symbol, fetch_from, end_date)
        except Exception:
            df = None
        if df is not None and not df.empty:
            data[symbol] = df
    return data


def _open_and_resolve_trade(symbol, full_df, signal_day, end_date, sl_pct, tp_pct, closeness_score):
    """Enter at the next trading day's open after signal_day, then walk
    forward (close-only, no intraday) until SL/TP or end_date."""
    future = full_df[(full_df.index.date > signal_day) & (full_df.index.date <= end_date)]
    if future.empty:
        return None

    entry_date = future.index[0]
    entry_price = float(future["open"].iloc[0])
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    exit_date, exit_price, exit_reason = None, None, None
    for ts, row in future.iterrows():
        close = float(row["close"])
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
        "ClosenessScore": round(float(closeness_score), 2),
        "ProfitRs": round(profit_rs, 2),
    }


def run_backtest(start_date, end_date, sl_pct, tp_pct, limit_per_sector=50, progress_callback=None):
    """Run the backtest. Returns (trades_df, summary_df).

    progress_callback, if given, is called as progress_callback(done, total, day)
    once per simulated trading day.
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

    trades = []
    total_days = len(all_dates)

    for day_idx, day in enumerate(all_dates):
        if progress_callback:
            progress_callback(day_idx + 1, total_days, day)

        snapshot = {}
        for symbol, df in data.items():
            df_slice = df[df.index.date <= day]
            if len(df_slice) >= MIN_HISTORY_ROWS and df_slice.index[-1].date() == day:
                snapshot[symbol] = df_slice

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
                symbol, data[symbol], day, end_date, sl_pct, tp_pct, result.get("ClosenessScore", 0.0)
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
    parser.add_argument("--sl", required=True, type=float, help="Stop-loss percent, e.g. 5")
    parser.add_argument("--tp", required=True, type=float, help="Take-profit percent, e.g. 10")
    parser.add_argument("--limit-per-sector", type=int, default=50)
    parser.add_argument("--trades-out", default="backtest_trades.csv")
    parser.add_argument("--summary-out", default="backtest_summary.csv")
    args = parser.parse_args()

    def progress(done, total, day):
        print(f"Evaluating day {done}/{total} ({day})...")

    trades_df, summary_df = run_backtest(
        args.start, args.end, args.sl, args.tp,
        limit_per_sector=args.limit_per_sector,
        progress_callback=progress,
    )

    trades_df.to_csv(args.trades_out, index=False)
    summary_df.to_csv(args.summary_out, index=False)

    print(f"\n{len(trades_df)} trades simulated.")
    print(summary_df.to_string(index=False))
    print(f"\nTrades saved to {args.trades_out}")
    print(f"Summary saved to {args.summary_out}")


if __name__ == "__main__":
    main()
