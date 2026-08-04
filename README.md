# Frontier Tradelight — AI-Assisted Swing Trading Screener & Backtester

An AI-assisted stock screener and backtester for the Indian market (NSE).
You describe an **entry strategy** and an **exit strategy** in plain
English, Gemini turns each into Python, and the tooling runs them against
real NSE data to produce a live shortlist and/or a historical, capital-aware
backtest. A Streamlit UI ties the whole flow together for click-driven use.

All of the project's code lives under [`Strategies/Default/`](Strategies/Default/).

## How it fits together

```
rules.md       --(Gemini)-->  generated_rules.py        --(used by)-->  stock_screener.py --> stock_report.csv
                                                                  \
exit_rules.md  --(Gemini)-->  generated_exit_strategy.py  ---------+-->  backtest.py --> backtest_trades.csv
                                                                  /                   --> backtest_summary.csv
                                              universe_fetcher.py                    --> backtest_portfolio.csv
                                       (Nifty 50 + sector + market-breadth data, cached)
```

- **`rules.md`** — the entry strategy spec: mandatory filters, rejection
  rules, ranking/scoring weights, and desired output columns, in plain
  English. Edit this to change or create a strategy. See
  [`RULES_GUIDE.md`](Strategies/Default/RULES_GUIDE.md) for how to write one.
- **`generate_screener.py`** — reads `rules.md`, sends it to the Gemini API,
  and writes the resulting
  `evaluate_stock(symbol, df, universe, sector_ranks, market_breadth)`
  function to `generated_rules.py`. Only rewrites `generated_rules.py` —
  safe to run anytime without touching anything else.
- **`generated_rules.py`** — generated code (checked into the repo, but
  regenerated whenever you run `generate_screener.py`). Don't hand-edit
  unless you're okay with it being overwritten.
- **`exit_rules.md`** — the exit strategy spec, in the same plain-English
  style as `rules.md`: when a trade closes (stop-loss, take-profit,
  trailing stop, time-based, or anything else computable from OHLCV). See
  the "Exit strategy" section of
  [`BACKTEST_GUIDE.md`](Strategies/Default/BACKTEST_GUIDE.md) for how to
  write one.
- **`generate_exit_strategy.py`** — reads `exit_rules.md`, sends it to
  Gemini, and writes the resulting `resolve_exit(...)` function to
  `generated_exit_strategy.py`. Same regenerate-anytime safety as above.
- **`generated_exit_strategy.py`** — generated exit logic, used only by
  `backtest.py`. `backtest.py` itself (not this file) always force-closes
  any still-open trade at the end of the backtest's date range, so a
  regenerated exit strategy can never leave a trade open forever.
- **`universe_fetcher.py`** — downloads the Nifty 50 constituent list from
  NSE, pulls price history via `jugaad-data`, ranks stocks by sector
  performance, and returns the top N stocks per sector. Results are cached
  in `universe_cache.json` for 1 day.
- **`nse_utils.py`** — shared NSE data-fetching helpers (with retry/backoff
  and rate-limit-conscious staggering), plus `calculate_sector_strength`
  and `calculate_market_breadth`, both used by the live screener and the
  backtester.
- **`stock_screener.py`** — the live entry point. Builds the stock universe,
  fetches recent daily price data per stock, computes sector-strength ranks
  and market breadth, runs `generated_rules.py`'s `evaluate_stock` on each
  stock, and writes the ranked results to `stock_report.csv`.
- **`backtest.py`** — a standalone backtesting module (no dependency on
  `stock_screener.py` or `app.py`, so it can be lifted into its own service
  later). Replays `generated_rules.py` + `generated_exit_strategy.py` over
  a historical date range with no look-ahead, then runs a second pass that
  simulates a real, capital-constrained portfolio (starting capital, a
  fixed number of concurrent position slots, compounding as trades close)
  to answer "would this strategy have actually grown my money," not just
  "did individual signals tend to work." See
  [`BACKTEST_GUIDE.md`](Strategies/Default/BACKTEST_GUIDE.md) for full
  details on both layers.
- **`app.py`** — a Streamlit UI with four tabs: edit/save/backup `rules.md`,
  run `generate_screener.py` / `stock_screener.py` with live output, browse
  `stock_report.csv`, and a Backtest tab (edit/generate `exit_rules.md`,
  run a backtest with a live progress log and a stop button, and view the
  portfolio result — final equity, total return, CAGR, and an equity curve).

## Setup

Note: This project works best with python@3.12

1. **Install dependencies:**

   ```bash
   cd Strategies/Default
   pip install -r requirements.txt
   ```

2. **Configure your Gemini API key** (only needed for `generate_screener.py`
   / `generate_exit_strategy.py`):

   ```bash
   cd Strategies/Default
   cp .env.template .env
   ```

   ```
   GEMINI_API_KEY=your_actual_key_here
   ```

## Usage

### Option A: Streamlit UI (recommended)

```bash
cd Strategies/Default
streamlit run app.py
```

Opens a browser UI with four tabs:

- **Rules** — view/edit `rules.md`, save (auto-backs up the previous
  version to `Rules_backup/`), and restore any previous version from a
  dropdown.
- **Run** — buttons to run `generate_screener.py` (rebuild
  `generated_rules.py` from `rules.md`) and `stock_screener.py` (fetch
  data, score stocks, write `stock_report.csv`), each with streamed console
  output.
- **Results** — browse `stock_report.csv` as a sortable/filterable table,
  with a toggle to show only stocks that passed all mandatory filters.
- **Backtest** — edit/save/generate `exit_rules.md` (same
  edit-and-backup pattern as Rules), pick a date range, starting capital,
  and max concurrent positions, run a backtest with a live log and a stop
  button, and see the score-bucketed trade summary plus the real portfolio
  result (final equity, total return, CAGR, equity curve).

### Option B: Command line

**1. Define or edit your entry strategy** in `rules.md`, and your exit
strategy in `exit_rules.md`.

**2. Generate the logic** (only needed after editing the corresponding
`.md` file):

```bash
python generate_screener.py        # rules.md -> generated_rules.py
python generate_exit_strategy.py   # exit_rules.md -> generated_exit_strategy.py
```

**3a. Run the live screener:**

```bash
python stock_screener.py
```

This fetches (or loads cached) top stocks per sector, downloads recent
daily price history, computes sector-strength ranks and market breadth,
runs `evaluate_stock` on every stock, prints the top 20 by `ClosenessScore`,
and saves the full ranked results to `stock_report.csv`.

**3b. Or run a backtest:**

```bash
python backtest.py --start 2023-07-23 --end 2026-06-30 \
    --initial-capital 100000 --max-positions 10
```

This replays the strategy over the date range with no look-ahead, resolves
every signal's entry/exit independently, then simulates a real portfolio on
top of those trades. Writes `backtest_trades.csv`, `backtest_summary.csv`,
and `backtest_portfolio.csv`, and prints a portfolio summary (final equity,
total return, funded vs. skipped-for-lack-of-capital trade counts).

## Output

- **`stock_report.csv`** (live screener) — one row per evaluated stock:
  `Symbol`, `Passed` (bool), `ClosenessScore` (0–100), `FailedRules`, plus
  every metric captured in `Details` (RSI, volumes, sector rank, etc.).
- **`backtest_trades.csv`** (backtest) — one row per simulated trade:
  entry/exit dates and prices, `ExitReason`, `ClosenessScore`, `ProfitRs`,
  and whether the portfolio simulation actually funded it (`Funded`,
  `AllocatedCapital`).
- **`backtest_summary.csv`** (backtest) — trades bucketed by
  `ClosenessScore`, with win rate and mean/median/total profit per bucket.
- **`backtest_portfolio.csv`** (backtest) — the portfolio's equity curve
  over time.

## Documentation

- [`Strategies/Default/RULES_GUIDE.md`](Strategies/Default/RULES_GUIDE.md) —
  how to write `rules.md` (entry strategy).
- [`Strategies/Default/BACKTEST_GUIDE.md`](Strategies/Default/BACKTEST_GUIDE.md) —
  how the backtester and portfolio simulation work, how to write
  `exit_rules.md`, and how to read the output.
- [`Strategies/Default/rules.md`](Strategies/Default/rules.md) — the
  current entry strategy (worked example).
- [`Strategies/Default/exit_rules.md`](Strategies/Default/exit_rules.md) —
  the current exit strategy (worked example).
- Prior strategy versions — auto-saved whenever you save a changed
  `rules.md` / `exit_rules.md` (restorable from the UI's Backtest tab):
  - [`Strategies/Rules_backup/trendline_rules.md`](Strategies/Rules_backup/trendline_rules.md)
  - [`Strategies/Rules_backup/trendline_support_momentum_rules.md`](Strategies/Rules_backup/trendline_support_momentum_rules.md)
  - [`Strategies/Rules_backup/mean_reversion_rules.md`](Strategies/Rules_backup/mean_reversion_rules.md)
  - [`Strategies/Rules_backup/oversold_mean_reversion_rules.md`](Strategies/Rules_backup/oversold_mean_reversion_rules.md)
  - [`Strategies/ExitRules_backup/fixed_stop_loss_take_profit_exit_rules.md`](Strategies/ExitRules_backup/fixed_stop_loss_take_profit_exit_rules.md)

## Notes & caveats

- `universe_cache.json` and `backtest_cache/` are generated/cached data,
  not tracked in git. `universe_cache.json` expires after 1 day; the
  backtest's per-symbol history cache never expires (historical ranges are
  immutable once in the past) — delete `backtest_cache/` to force a
  refetch.
- `jugaad-data` pulls from NSE's historical (EOD) archives, which lag live
  quotes by 1+ trading session — expect some drift if you compare against
  a live/real-time source. This is inherent to any EOD data source, not a
  calculation bug.
- Because `generated_rules.py` and `generated_exit_strategy.py` are
  AI-generated, always review the diff after regenerating before trusting
  or committing it — treat the AI output as a draft, not gospel. Watch in
  particular for hardcoded `pandas_ta` column names (they vary by version)
  and swallowed exception messages — both have shown up in past
  generations.
- Backtest "total return" is cumulative over the whole date range, not
  annualized — check the accompanying CAGR figure before judging a result
  as strong or weak.
- The backtest uses *today's* Nifty 50 constituent list applied
  retroactively (survivorship bias), and doesn't model slippage or
  brokerage/STT costs.
- Never commit your real `.env` file or API key.
