# Exit Strategy Rules

## Strategy Metadata

Exit Strategy Name: ATR Trailing Stop, Let Winners Run v5
Applies To: Any trade opened by the backtester
Timeframe: Daily (closing price only, no intraday)

---

## Data Availability Note

Only the entry price/date and each stock's own daily OHLCV history (before
and after entry) are available. There is NO Nifty benchmark index data and
NO earnings calendar available - do not condition any exit logic on either.
Every rule below must be computable from OHLCV alone.

---

## Entry Reference

Entry Price: Opening price on the trading day immediately after the signal
day.

---

## Pre-Trade Calculation (Computed Once at Entry)

ATR_Period = 14
ATR_Entry = ATR(14) calculated using price history up to and including the
signal day (the day before entry) - never using data from entry day onward.

Initial_SL = EntryPrice - (2.5 * ATR_Entry)

Notes:
- If ATR_Entry cannot be computed (insufficient history), do not open this
  trade - treat it as no exit condition available and let the caller skip
  it, rather than opening a trade with no stop-loss.

---

## Daily State Variables

Trailing_SL   : Starts at Initial_SL. Updated daily. Never decreases.
Highest_Close : Peak closing price since entry. Starts at EntryPrice.

---

## Daily Update Logic

Run at market close, BEFORE checking exit conditions, using only OHLCV data
available up to and including that day.

### Step 1: Update Highest Close

If Close > Highest_Close:
    Highest_Close = Close

### Step 2: Ratchet Trailing Stop Upward Only

Recompute ATR(14) using price history up to and including today.

Candidate_SL = Highest_Close - (2.5 * ATR_Today)

If Candidate_SL > Trailing_SL:
    Trailing_SL = Candidate_SL
Else:
    Trailing_SL remains unchanged.

Notes:
- The stop only ever moves up, never down, regardless of what today's ATR
  computes to. This locks in gains progressively as the trade moves in
  profit and never gives back protection already earned.

---

## Exit Conditions

Check ONCE PER DAY at market close, AFTER the daily update logic above runs.
Evaluate in this priority order; exit on the first condition that fires.

### Condition 1: Trailing Stop-Loss

If Close <= Trailing_SL:
    EXIT.
    Reason Tag: "TSL"

---

### Condition 2: Maximum Holding Period

If TradingDaysSinceEntry >= 90:
    EXIT at that day's close.
    Reason Tag: "MaxHold"

Notes:
- NO fixed take-profit in this version (v5). Trend-following/momentum
  strategies earn their edge from a small number of large winners paying
  for many small losers - capping gains at a fixed percentage destroys
  that asymmetry. The ONLY exit for a winning trade is the trailing stop
  itself giving back 2.5x ATR from the peak; there is no ceiling on how
  far a trade can run before that happens.
- Extended from 30 to 90 trading days (~4.5 months) versus earlier
  versions. A real trend needs months, not weeks, to develop into a large
  winner - a 30-day cap was forcing an exit right as a genuine trend might
  start to compound. This is a real backstop against truly stagnant
  capital, not a target.

---

## Exit Priority Order

1. TSL      <- checked first each day
2. MaxHold  <- final backstop at 90 trading days

Only one exit tag is assigned per trade.

---

## Fallback

If no condition above triggers before the available data ends, do not exit -
the backtester itself force-closes any still-open trade at the last
available close, tagged "RangeEnd". Exit strategies never need to implement
this fallback themselves.
