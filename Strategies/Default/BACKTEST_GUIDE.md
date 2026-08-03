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
   (not intraday highs/lows) against your chosen exit strategy.
3. It exits as soon as the exit condition fires, or — if it never fires
   before your chosen end date — force-exits at the last available close in
   the range, tagged `RangeEnd`.

A stock can open **multiple simultaneous trades** if it signals again while
an earlier trade on it is still open — each signal is treated as its own
independent ₹100 bet when resolving *whether and when* it would have exited.

### Portfolio simulation: what "total return" actually means

The per-trade ₹100 numbers above answer "did this setup tend to work,"
but they don't by themselves answer "would this strategy have grown my
money" — trades overlap in time, and a real account only has so much
capital to go around. The **Portfolio result** section answers that
question directly:

- You set a **starting capital** (e.g. ₹100,000) and a **max concurrent
  positions** count (e.g. 10 — a fixed number of position "slots").
- Every already-resolved trade above is replayed in chronological order.
  When a signal's entry date arrives and a slot is free, it gets funded at
  an equal share of *current total equity* (so position size compounds as
  the portfolio grows or shrinks) — otherwise it's recorded as **skipped
  for lack of capital**, not opened smaller.
- When multiple signals want a slot on the same day and there aren't enough
  free ones, the highest `ClosenessScore` gets priority.
- Capital from a closing trade becomes available the same day for new
  entries.

This is what "Final equity" and "Total return %" mean, and it's the
number that actually corresponds to "if I ran this strategy with ₹X, would
I have ₹1.1X after 3 years" — the individual ₹100-per-trade stats above do
not.

**Total return is cumulative over the whole date range, not per-year.** A
"+13% total return" over a 3-year backtest is not "13% a year" - it's 13%
across the entire period. `CAGR` (compound annual growth rate) is shown
alongside it specifically to answer "what's the equivalent steady yearly
rate," which is the number actually comparable to things like a bank FD
rate or an index's annual return. A large total-return number over a long
date range can correspond to a fairly modest CAGR - always check CAGR
before judging a result as strong or weak.

**Position count is a real lever, not just a detail.** With very few
slots, most signals get skipped (shown as "Skipped (no capital)"), so the
result depends heavily on *which* signals happened to get funded, not just
the average edge across all of them. Try a few different slot counts to
see how sensitive the result is - a strategy whose portfolio return swings
wildly with slot count is telling you the funded subset matters as much as
the underlying signal quality.

### Exit strategy: defined in `exit_rules.md`, just like `rules.md`

The exit strategy isn't a fixed set of built-in options — it works exactly
like the entry strategy:

```
exit_rules.md  --(Gemini)-->  generated_exit_strategy.py  --(used by)-->  backtest.py
```

Write your exit logic in plain English in `exit_rules.md` (in the Backtest
tab, or directly in the file), click **"Generate exit strategy"** to turn it
into `generated_exit_strategy.py` (a `resolve_exit(...)` function), and the
backtester calls that function to decide when each trade closes. Anything
computable from OHLCV price history works — fixed stop-loss/take-profit
percentages, a trailing ATR stop, a moving-average cross exit, a fixed
holding period, or something else entirely. The current `exit_rules.md`
uses an ATR(14) trailing stop (2.5x ATR, ratcheting up only) with **no
fixed take-profit** — winners are only closed by the trailing stop giving
back 2.5x ATR from their peak, or a 90-trading-day max holding backstop.
This was a deliberate change (see `rules.md`'s Strategy Rationale section):
a fixed take-profit caps the rare large winners that a momentum/trend
strategy depends on to offset its more frequent small losers.

One thing you never need to specify: what happens if your exit condition
never fires. `backtest.py` itself — not the generated exit logic — always
force-closes any still-open trade at the last available close in your date
range, tagged `RangeEnd`. This guarantee holds no matter what you write in
`exit_rules.md`, so a regenerated exit strategy can never accidentally leave
a trade open forever.

`exit_rules.md` gets the same backup treatment as `rules.md`: saving a
changed version automatically backs up the previous one to
`ExitRules_backup/`, and you can restore any previous exit strategy from a
dropdown in the Backtest tab.

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
- Changing only your exit strategy (editing `exit_rules.md` and
  regenerating) while keeping the same date range reuses the price-history
  cache entirely — that re-run should always be fast regardless of the
  original fetch time.

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
| `ExitReason` | Whatever tag your exit strategy uses (e.g. `SL`, `TP`, `TrailingATR`), or `RangeEnd` if nothing triggered before the date range ended (forced exit). |
| `ClosenessScore` | The strategy's own ranking score (0-100) at signal time. |
| `ProfitRs` | Profit in rupees on the flat ₹100 stake (equivalently, % return). |
| `Funded` | Whether the portfolio simulation actually had a free slot/capital to take this trade. |
| `AllocatedCapital` | How much of the portfolio was put into this trade, if funded (blank/0 otherwise). |

### Portfolio equity curve (`backtest_portfolio.csv`)

One row per date, tracking total portfolio value (cash + value of open
positions) as the simulation progresses — this is what the line chart in
the Portfolio result section plots.

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
