# Strategies — Trendline Support Momentum Screener

An AI-assisted stock screener for the Indian market (NSE). You describe a
trading strategy in plain English (`rules.md`), Gemini turns it into a Python
scoring function (`generated_rules.py`), and the screener runs that function
against a dynamically built stock universe to produce a ranked shortlist. A
Streamlit UI (`app.py`) ties the whole flow together for click-driven use.

## How it fits together

```
rules.md  --(Gemini)-->  generated_rules.py  --(used by)-->  stock_screener.py --> stock_report.csv
                                                                     ^
                                                        universe_fetcher.py
                                                        (Nifty 50 + sector data, cached)
```

- **`rules.md`** — the strategy spec in human-readable form: mandatory filters,
  rejection rules, ranking/scoring weights, and desired output columns. Edit
  this file to change or create a strategy. See
  [`RULES_GUIDE.md`](RULES_GUIDE.md) for how to write one.
- **`generate_screener.py`** — reads `rules.md`, sends it to the Gemini API,
  and writes the resulting `evaluate_stock(symbol, df, universe, sector_ranks)`
  function to `generated_rules.py`. Only rewrites `generated_rules.py` — safe
  to run anytime without touching `stock_screener.py`.
- **`generated_rules.py`** — generated code (checked into the repo, but
  regenerated whenever you run `generate_screener.py`). Don't hand-edit unless
  you're okay with it being overwritten.
- **`universe_fetcher.py`** — downloads the Nifty 50 constituent list from
  NSE, pulls 6-month price history via `jugaad-data`, ranks stocks by sector
  performance, and returns the top N stocks per sector. Results are cached in
  `universe_cache.json` for 1 day.
- **`stock_screener.py`** — the main entry point. Builds the stock universe,
  fetches ~400 days of daily price data per stock via `jugaad-data`, computes
  real sector-strength ranks from that data, runs `generated_rules.py`'s
  `evaluate_stock` on each stock, and writes the ranked results to
  `stock_report.csv`.
- **`app.py`** — a Streamlit UI with three tabs: edit/save `rules.md`, run
  `generate_screener.py` / `stock_screener.py` with live output, and browse
  `stock_report.csv`.

## Setup

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your Gemini API key** (only needed for `generate_screener.py`):

   Copy `.env.template` to `.env` and fill in your key:

   ```bash
   cp .env.template .env
   ```

   ```
   GEMINI_API_KEY=your_actual_key_here
   ```

## Usage

### Option A: Streamlit UI (recommended)

```bash
streamlit run app.py
```

Opens a browser UI with three tabs:

- **Rules** — view/edit `rules.md` and save changes.
- **Run** — buttons to run `generate_screener.py` (rebuild `generated_rules.py`
  from `rules.md`) and `stock_screener.py` (fetch data, score stocks, write
  `stock_report.csv`), each with streamed console output.
- **Results** — browse `stock_report.csv` as a sortable/filterable table, with
  a toggle to show only stocks that passed all mandatory filters.

### Option B: Command line

**1. Define or edit your strategy** in `rules.md`. The current strategy
("Trendline Support Momentum") looks for stocks:

- with rising volume over the last 3 sessions,
- with RSI(14) between 40–60 (not overbought/oversold),
- not near a recent 52-week high,
- in a top-5 performing sector,
- sitting near a clean ascending trendline support.

**2. Generate the screening logic** (only needed after editing `rules.md`):

```bash
python generate_screener.py
```

**3. Run the screener:**

```bash
python stock_screener.py
```

This will:

- Fetch (or load cached) top stocks per sector via `universe_fetcher.py`.
- Download ~400 days of daily price history per stock via `jugaad-data`.
- Compute sector-strength ranks from each sector's average 30-day return.
- Run `generated_rules.py`'s `evaluate_stock` on every stock.
- Print the top 20 stocks by `ClosenessScore` to the console.
- Save the full ranked results to `stock_report.csv`.

## Output

`stock_report.csv` contains one row per evaluated stock with:

- `Symbol`, `Passed` (bool — passed all mandatory filters), `ClosenessScore`
  (0–100, higher is better), `FailedRules` (why it didn't pass, if it didn't),
  plus every metric captured in `Details` (RSI, volumes, sector rank,
  trendline distance, etc.).

## Notes & caveats

- `universe_cache.json` expires after 1 day; delete it to force a fresh
  fetch of the Nifty 50 universe. Neither it nor `stock_report.csv` are
  tracked in git — both are generated output.
- `jugaad-data` pulls from NSE's historical (EOD) archives, which typically
  lag live quotes by 1+ trading session. If you compare `RSI`/other metrics
  against a live/real-time source, expect some drift — this is inherent to
  any EOD data source, not a calculation bug.
- Because `generated_rules.py` is AI-generated from `rules.md`, always
  review the diff after running `generate_screener.py` before trusting or
  committing it — treat it as reviewable code, not a black box.
- Never commit your real `.env` file or API key.
