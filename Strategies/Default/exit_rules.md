# Exit Strategy Rules

## Strategy Metadata

Exit Strategy Name: ATR Trailing Stop-Loss / Fixed Take-Profit v2
Applies To: Any trade opened by the backtester
Timeframe: Daily (closing price only, no intraday)

---

## Entry Reference

Entry Price: Opening price on the trading day immediately after the
signal day.

---

## Pre-Trade Calculations (Computed Once at Entry)

ATR_Period = 14
ATR_Entry = ATR(14) calculated on the signal day (day before entry)

Market Mode (evaluated once at entry, fixed for the trade duration):

    If Nifty50_Close > Nifty50_MA(50) on signal day:
        Market_Mode = BULLISH
        ATR_Multiplier = 2.0
        TP_Pct = 15

    Else:
        Market_Mode = BEARISH
        ATR_Multiplier = 1.5
        TP_Pct = 5

Initial_SL = EntryPrice - (ATR_Multiplier * ATR_Entry)

Notes:
- Initial_SL is computed once at entry. It is the absolute floor
  and can NEVER move downward for any reason.
- ATR_Entry uses the signal day's ATR(14) to avoid post-gap
  distortion on the entry candle.
- Market_Mode does not change mid-trade even if Nifty50 crosses
  MA(50) after entry. Mode is locked at signal day.
- If ATR_Entry is unavailable (insufficient history), reject the
  trade — do not substitute a default value.

---

## Daily State Variables

Trailing_SL   : Starts at Initial_SL. Updated daily. Never decreases.
Highest_Close : Peak closing price since entry. Starts at EntryPrice.
SL_Mode       : FIXED or TRAILING. Determined fresh each day.

---

## Daily Update Logic

Run at market close, BEFORE checking exit conditions.

### Step 1: Update Highest Close

    If Close > Highest_Close:
        Highest_Close = Close

### Step 2: Determine SL Mode

    If Close > EntryPrice:
        SL_Mode = TRAILING
        Proceed to Steps 3 and 4.

    Else:
        SL_Mode = FIXED
        Trailing_SL remains frozen at Initial_SL.
        Skip Steps 3 and 4.
        Proceed directly to Exit Conditions.

    Rationale:
    ATR trailing is a profit-protection mechanism only. When the
    trade is in loss, the only relevant level is Initial_SL. This
    prevents ATR from widening the SL during adverse moves.

### Step 3: Recalculate ATR (TRAILING mode only)

    ATR_Today = ATR(14) as of today's close

    Notes:
    - ATR_Today may spike on high-volatility days (earnings, macro
      events). The ratchet in Step 4 prevents this spike from ever
      lowering a previously locked-in SL.

### Step 4: Ratchet Trailing SL Upward Only (TRAILING mode only)

    Candidate_SL = Highest_Close - (ATR_Multiplier * ATR_Today)

    If Candidate_SL > Trailing_SL:
        Trailing_SL = Candidate_SL
    Else:
        Trailing_SL = Trailing_SL
        ← Hold. Never move SL downward under any circumstance.

---

## Exit Conditions

Check ONCE PER DAY at market close, AFTER daily update logic runs.
Conditions are evaluated in the priority order listed below.
Exit immediately when the first condition triggers.

---

### Condition 1: Pre-Earnings Hard Exit (HIGHEST PRIORITY)

    If EarningsDate is known:
        AND CalendarDaysUntilEarnings <= 1:
            EXIT immediately.
            Reason Tag: "EarningsExit"

    Notes:
    - This overrides ALL other conditions including TSL and TP.
    - If EarningsDate is unknown, skip this condition entirely —
      do not assume earnings are far away.
    - Earnings date is the confirmed board meeting / results
      announcement date from NSE or Tickertape.

---

### Condition 2: Trailing Stop-Loss

    If Close <= Trailing_SL:
        EXIT.
        Reason Tag: "TSL"

    Notes:
    - In FIXED mode (trade in loss): Trailing_SL = Initial_SL,
      so this is equivalent to a standard fixed ATR-based SL.
    - In TRAILING mode (trade in profit): Trailing_SL has
      ratcheted above Initial_SL, locking in gains progressively.

---

### Condition 3: Take-Profit

    If Market_Mode = BULLISH:
        If Close >= EntryPrice * 1.15:
            EXIT.
            Reason Tag: "TP"

    If Market_Mode = BEARISH:
        If Close >= EntryPrice * 1.05:
            EXIT.
            Reason Tag: "TP"

    Notes:
    - TP is fixed at entry based on Market_Mode.
    - TP is checked even in FIXED mode (loss zone) to capture
      sharp V-shaped reversals that skip past entry to TP in one
      or two sessions.
    - Do NOT trail the TP. It is a fixed ceiling, not a moving
      target. Taking profit early is acceptable; missing TP by
      trailing it upward is not.

---

### Condition 4: Maximum Holding Period

    If TradingDaysSinceEntry >= 30:
        EXIT at next available close.
        Reason Tag: "MaxHold"

    Notes:
    - NEW in v2. The original rules had no time-based exit.
    - Swing trades that have not triggered TSL or TP after 30
      trading days (~6 weeks) are dead trades — capital is better
      redeployed. Exit unconditionally.
    - 30 trading days is the upper bound of the "Swing Trade
      (1-30 Days)" holding period stated in the entry rules.

---

## Exit Priority Order

    1. EarningsExit  ← Overrides everything
    2. TSL           ← Second priority
    3. TP            ← Third priority
    4. MaxHold       ← Final backstop at 30 trading days

Only one exit tag is assigned per trade.

---

## Fallback

If no condition above triggers before the available data ends, do
not exit — the backtester itself force-closes any still-open trade
at the last available close, tagged "RangeEnd". Exit strategies
never need to implement this fallback themselves.

---

## Summary Reference Table

| Parameter          | BULLISH Mode          | BEARISH Mode          |
|--------------------|-----------------------|-----------------------|
| Nifty vs MA50      | Close > MA50          | Close < MA50          |
| ATR Multiplier     | 2.0                   | 1.5                   |
| Initial SL         | Entry - (2.0 x ATR)   | Entry - (1.5 x ATR)   |
| Take-Profit        | +15% from entry       | +5% from entry        |
| Trailing SL        | Active when in profit | Active when in profit |
| Fixed SL           | Active when in loss   | Active when in loss   |
| Earnings Override  | Exit 1 day before     | Exit 1 day before     |
| Max Hold           | 30 trading days       | 30 trading days       |