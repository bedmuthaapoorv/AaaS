# How to Use the Backtest Tool

The backtest simulates your current strategy (whatever `generated_rules.py`
implements right now, derived from `rules.md`) against historical NSE data,
so you can see how it would have actually performed instead of just trusting
the logic on faith.

## What it does

For every trading day in the date range you choose, it evaluates every
stock in the universe using only price data available up to that day (no
look-ahead) — the exact same `evaluate_stock` function the live screener
uses. Whenever a stock signals a pass:

1. It opens a flat **₹100 trade** at the **next trading day's open**.
2. It walks forward day by day, checking that day's **closing price only**
   (not intraday highs/lows) against your stop-loss and take-profit
   percentages.
3. It exits as soon as either threshold is hit, or — if neither is hit
   before your chosen end date — force-exits at the last available close in
   the range, tagged `RangeEnd`.

A stock can open **multiple simultaneous trades** if it signals again while
an earlier trade on it is still open — each signal is treated as its own
independent ₹100 bet.

## Estimated time before you run

Before you click "Run backtest," the UI shows a pre-flight estimate: how
many of the universe's stocks already have cached price history for your
exact date range, and how many still need fetching from NSE. Fetching is
the slow part (network-bound); the day-by-day simulation itself is fast
local computation once the data is in hand.

- If everything is cached: **well under a minute**.
- If stocks still need fetching: expect roughly **a few seconds per
  uncached stock** (NSE requests, including retries on slow responses) —
  the estimate range widens for a fresh date range with nothing cached yet.
- Changing only the Stop-Loss/Take-Profit values while keeping the same
  date range reuses the cache entirely — that re-run should always be fast
  regardless of the original fetch time.

## Stopping a run midway

Click **"Stop backtest"** while a run is in progress. This terminates the
underlying process immediately. Note: results (`backtest_trades.csv` /
`backtest_summary.csv`) are only written once a run **finishes** — stopping
early discards that run's progress rather than saving a partial result.
You'll need to let a run complete to see its output.

## Reading the output

### Individual trades (`backtest_trades.csv`)

One row per simulated trade:

| Column | Meaning |
|---|---|
| `Symbol` | The stock traded. |
| `SignalDate` | The day the strategy's conditions passed. |
| `EntryDate` | The next trading day — when the trade actually opens. |
| `EntryPrice` | That day's opening price. |
| `ExitDate` | The day the trade closed out. |
| `ExitPrice` | The closing price on the exit day. |
| `ExitReason` | `SL` (stop-loss hit), `TP` (take-profit hit), or `RangeEnd` (neither hit before the date range ended — forced exit). |
| `ClosenessScore` | The strategy's own ranking score (0-100) at signal time. |
| `ProfitRs` | Profit in rupees on the flat ₹100 stake (equivalently, % return). |

### Summary by ClosenessScore bucket (`backtest_summary.csv`)

Trades are grouped into score buckets (0-20, 20-40, 40-60, 60-80, 80-100) so
you can see whether higher scores actually correspond to better outcomes:

| Column | Meaning |
|---|---|
| `ScoreBucket` | The `ClosenessScore` range for this row. |
| `Trades` | Number of trades that fell in this bucket. |
| `WinRatePct` | % of trades in this bucket with positive `ProfitRs`. |
| `MeanProfitRs` | Average profit across trades in this bucket. |
| `MedianProfitRs` | Median profit (less skewed by outliers than the mean). |
| `TotalProfitRs` | Sum of all profit in this bucket. |

This is the actual data-driven way to answer "what score should I trust" —
if the 80-100 bucket doesn't clearly outperform the 40-60 bucket in win rate
and mean profit, the score isn't as predictive as its formula implies, and
that's worth knowing before you rely on it.

## Known limitations (read before trusting results)

- **Survivorship bias:** the backtest uses *today's* Nifty 50 constituent
  list applied retroactively. Stocks that were dropped from or added to the
  index during your date range aren't accounted for, which can flatter
  results slightly.
- **Data lag:** like the live screener, this relies on NSE's end-of-day
  archives via `jugaad-data` — no intraday fills, no slippage, no
  brokerage/STT/transaction costs factored into `ProfitRs`.
- **Small sample sizes:** short date ranges or a strategy with strict
  filters can produce very few trades per bucket — a bucket with 2 trades
  and a 100% win rate doesn't mean much statistically. Prefer longer date
  ranges and look at `Trades` counts before trusting `WinRatePct`.
