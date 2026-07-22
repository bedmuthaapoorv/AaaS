# How to Write `rules.md`

`rules.md` is the only file you need to edit to define a strategy. It's a
plain-English spec — you never write Python. When you run
`generate_screener.py`, its full text gets pasted into a prompt sent to
Gemini, which turns it into `generated_rules.py` (a function that scores
every stock). This guide explains what to put in it and why, so the
generated code actually does what you intend.

## What data is available to reference

Every rule you write has to be computable from what the screener actually
fetches per stock. Don't invent a metric it has no way to calculate. You have:

- **Daily OHLCV price history** (~400 days) per stock: `open`, `high`, `low`,
  `close`, `volume`. You can reference relative days like `Volume[-1]`
  (yesterday), `Volume[-2]` (the day before), or ranges like `HighestHigh(252)`
  (highest high over the last 252 trading days ≈ 1 year).
- **Standard technical indicators** computed from that price history — RSI,
  moving averages, etc. (the generator uses `pandas_ta`, so anything that
  library supports is fair game).
- **Sector info** — each stock's sector name, and a `SectorRank` (1 = best
  performing sector by recent average return, higher = weaker).
- **Company/sector metadata** — name, sector, current price.

If a rule needs something outside this (e.g. options data, news sentiment,
fundamentals like P/E), it won't be computable — the generator will either
skip it or hallucinate a stand-in, which defeats the point.

## Required structure

Keep these five sections. The generator (see the prompt in
`generate_screener.py`) expects the whole file, so consistent headings make
it far more reliable, but the section order below is the one that's been
tested and works well.

### 1. Strategy Metadata

Free-form context: strategy name, market, timeframe, holding period. Doesn't
drive logic, but helps Gemini and future readers understand intent.

```markdown
## Strategy Metadata

Strategy Name: Trendline Support Momentum
Market: India (NSE/BSE)
Timeframe: Daily
Holding Period: Swing Trade (1-30 Days)
```

### 2. Mandatory Filters

The core of the strategy: a numbered list of rules that **all** must pass for
a stock to be considered a valid pick. Each rule should have:

- **Description** — one sentence, plain English, of *why* this filter exists.
- **Condition** — the precise, computable logic. Use comparison operators
  (`>`, `<`, `<=`, `AND`, `OR`) against the data fields above. Be exact about
  numbers — "RSI between 40 and 60" is fine, "RSI is reasonable" is not.
- **Notes** (optional) — edge cases: what to do with missing data, which
  sessions to include/exclude, etc. These matter — vague edge cases produce
  inconsistent generated code.

```markdown
### Rule 1: Increasing Volume

Description:
Volume should show increasing participation over the last 3 completed trading sessions.

Condition:

Volume[-1] > Volume[-2]
AND
Volume[-2] > Volume[-3]

Notes:
- Ignore today's volume.
- Stocks with missing volume data should be rejected.
```

Repeat this pattern for each filter (RSI range, distance from 52-week high,
sector strength, trendline proximity, or whatever your strategy needs).

### 3. Rejection Rules

Usually just a one-liner stating the logical relationship between the
mandatory filters:

```markdown
## Rejection Rules

Reject stock if ANY mandatory filter fails.
```

### 4. Ranking Rules

Stocks that pass the mandatory filters still need to be ranked against each
other. Define a **weighted score out of 100%** — the weights must sum to
100, and each component needs a precise sub-formula so it's unambiguous how
to compute it:

```markdown
## Ranking Rules

### Rank Score

Score =
40% Trendline Quality
+
25% Sector Strength
+
20% Volume Growth
+
15% RSI Closeness To 50

Where:

RSI Score = 100 - abs(RSI - 50)

Higher score is better.
```

Every weighted component should have a "Where: ... Score = ..." definition
like the RSI one above, otherwise Gemini has to guess how to translate it
into a 0–100 number.

### 5. Output Columns

List exactly what you want to see in the final report, plus how to sort and
how many results to keep:

```markdown
## Output Columns

Return:

- Symbol
- Company Name
- Sector
- Current Price
- RSI(14)
- Sector Rank
- Rank Score

Sort:

Rank Score DESC

Limit:

Top 20 Stocks
```

## Tips for writing good rules

- **Be numeric, not vibes-based.** "Volume should be picking up" is
  ambiguous; "Volume[-1] > Volume[-2] AND Volume[-2] > Volume[-3]" isn't.
- **One condition per line**, joined with `AND`/`OR` — makes it trivial for
  the generator (and you) to see exactly what's being checked.
- **State the weight breakdown for scoring explicitly**, and make sure the
  percentages add up to 100%.
- **Call out missing-data behavior.** If volume or RSI can't be computed
  for a stock (too little history, delisted, etc.), say what should happen
  (usually: reject it, don't crash).
- **Change one section at a time.** After editing `rules.md`, re-run
  `generate_screener.py` and skim the diff in `generated_rules.py` before
  trusting it — treat the AI output as a draft, not gospel.
- **Keep it to what's computable from price + volume + sector data.**
  Anything else (fundamentals, news, options flow) isn't available to the
  screener and will produce unreliable generated code.

## Full example

See [`rules.md`](rules.md) in this directory for a complete, working example
strategy ("Trendline Support Momentum") that follows every convention above.
Copy its structure when starting a new strategy — swap out the rules,
weights, and output columns, but keep the same sections and level of
precision.
