# Stock Selection Rules

## Strategy Metadata

Strategy Name: Breakout Momentum v6
Market: India (NSE/BSE)
Timeframe: Daily
Holding Period: Trend Trade (1-90 Days)

---

## Data Availability Note

Only the following data is available to this strategy: each stock's own
daily OHLCV (open/high/low/close/volume) history, a `SectorRank` value
(1 = best-performing sector by recent average return, higher = weaker), and
a `MarketBreadth` value (0-100: percentage of the entire universe currently
trading above its own 50-day moving average) - both computed once per day
from OHLCV data across the universe. There is NO Nifty benchmark index
data and NO earnings calendar available. Every rule below must be
computable from OHLCV + SectorRank + MarketBreadth alone.

---

## Strategy Rationale

v3 was a pullback-to-support strategy (buy near a recent low, in an
uptrend). Backtesting showed ~80%+ of v3 trades were stopped out shortly
after entry regardless of stop width, while the rare trades that survived
to the max holding period were consistently profitable. This points to a
mismatch: buying near a recent low is more often a failing bounce than a
genuine trend resumption, which is exactly what a wide ATR trailing stop
chops up. v4 flipped the entry philosophy to a breakout: buy stocks pushing
to new short-term highs on strong volume, in a confirmed uptrend.

v5 removed the fixed take-profit from the exit strategy (see
exit_rules.md) so winning trades aren't capped - trend-following systems
earn their edge from a few large winners paying for many small losers, and
a fixed take-profit destroys that asymmetry. This flipped the 3-year
backtest from net negative to slightly net positive, but the win rate
stayed stuck around 35% regardless of entry tuning.

v6 adds a market-breadth filter: pause new entries when the broader
universe itself is broad-based weak (few stocks above their own 50-day
average), since even a good individual breakout setup tends to fail when
the overall market is correcting. This is a stand-in for the Nifty-based
market-regime filter real trend traders use, built entirely from data this
pipeline already has.

---

## Mandatory Filters

All rules below MUST pass.

---

### Rule 1: Minimum Liquidity Floor

Description:
Reject illiquid stocks so volume signals are meaningful and exits are
executable without slippage.

Condition:

MA(Volume, 20) >= 100000
AND
Close >= 50

Notes:
- Kept deliberately loose since the universe is already Nifty-50-derived
  (large, liquid names) - this should rarely bind, it's a safety floor.

---

### Rule 2: Trend Structure (Moving Average Stack)

Description:
Confirm the stock is in a genuine multi-timeframe uptrend using a moving
average stack.

Condition:

Close > MA(20)
AND
MA(20) > MA(50)
AND
MA(50) > MA(126)

Notes:
- This is the core trend filter: price above a rising short-term average,
  which is above a rising medium-term average, which is above a rising
  long-term (6-month) average.

---

### Rule 3: Daily RSI Range (Strength Zone)

Description:
Stock must show strong (not merely neutral) momentum - breakout entries
need real strength behind them, unlike a pullback entry which wants
neutral RSI.

Indicator:
RSI(14) on Daily timeframe

Condition:

55 <= Daily_RSI <= 75

Notes:
- Raised from the neutral 40-65 band used in the prior pullback version.
  A genuine breakout is accompanied by RSI pushing into the upper range,
  not sitting at neutral.
- 75 as a ceiling avoids the most extreme, likely-to-mean-revert overbought
  readings while still allowing strong momentum through.
- Reverted a v4.1 tightening to 60 that shrank the sample to a
  statistically meaningless size (29 trades over 3 years) without proving
  beneficial - back to the wider band that produced a real sample (760
  trades over 3 years) to test against.

---

### Rule 4: Volume Confirmation (Breakout Volume)

Description:
A breakout without volume is a weak/fakeout signal. Require a real
volume surge, not just mild acceleration.

Condition:

Volume[-1] > Volume[-2]
AND
Volume[-1] >= 1.3 * MA(Volume, 20)

Notes:
- Raised from 0.8x (pullback version) to 1.3x average - breakout volume
  should be visibly elevated, not merely average.
- Reverted a v4.1 tightening to 2.0x that shrank the sample to a
  statistically meaningless size without proving beneficial.
- Ignore today's incomplete session volume throughout.
- Stocks with missing volume data should be rejected.

---

### Rule 5: Breakout Proximity to Short-Term High

Description:
Price should be pushing to a new short-term high (a breakout entry) rather
than sitting well below it. This replaces trendline touch-point/slope
detection, which generated code cannot reliably compute from raw OHLCV.

Condition:

Close >= 0.98 * Highest_Close(20)
AND
Close > Close[-1]

Where:
Highest_Close(20) = the highest closing price over the last 20 trading
sessions (including today).

Notes:
- "Within 2% of the 20-day high" while still passing Rule 2's uptrend
  stack is the breakout-in-an-uptrend setup this strategy is built around.
- Close > Close[-1] (today closed higher than yesterday) confirms today is
  an up day, not a stall/reversal day at the highs.
- Reverted a v4.1 tightening to 0.995 that shrank the sample to a
  statistically meaningless size without proving beneficial.

---

### Rule 6: Not Already Extended Too Far

Description:
Avoid chasing a stock that has already run up too much very recently -
prefer the early stage of a breakout over a multi-week extended move.

Condition:

Close <= 1.25 * Close[-20]

Notes:
- Price no more than 25% above where it was 20 trading days ago. This
  excludes stocks in the middle/late stage of a parabolic run, while still
  allowing genuine fresh breakouts through.

---

### Rule 7: Sector Strength

Description:
Stock must belong to a top-performing sector, using the SectorRank already
computed by the backtester/screener (ranked by each sector's average
30-day return - no Nifty-relative or fundamental data involved).

Condition:

SectorRank <= 10

Notes:
- With only ~15 sectors in the Nifty universe, Top 10 is a meaningful cut
  without being so tight it starves the strategy of trades.
- Reverted a v4.1 tightening to Top 5 that shrank the sample to a
  statistically meaningless size without proving beneficial.

---

### Rule 8: Market Breadth Filter (v6)

Description:
Pause new entries when the broader market is itself broad-based weak, even
if this individual stock's setup looks fine in isolation. A good breakout
setup is more likely to fail when most other stocks are simultaneously
breaking down - this is a systemic risk no single-stock filter can catch.

Condition:

MarketBreadth >= 45

Notes:
- MarketBreadth is the % of the entire universe trading above its own
  50-day moving average, computed once per day (not specific to this
  stock) - use the market_breadth parameter directly, do not compute it
  from this stock's own data.
- 45 was chosen from the historical distribution of this metric over the
  backtest period (mean ~57, median ~58, 10th percentile ~28): a cutoff of
  45 excludes roughly the weakest 30% of trading days (broad corrections)
  while still allowing the large majority of days through.

---

## Rejection Rules

Reject stock if ANY mandatory filter fails.

---

## Ranking Rules

After filtering, rank candidates.

### Rank Score

Score =
30% Sector_Strength_Score
+
30% Volume_Score
+
25% Breakout_Quality_Score
+
15% RSI_Strength_Score

Where:

Sector_Strength_Score = max(0, 100 - (SectorRank - 1) * 10)
(Rank 1 = 100, declining 10 points per rank)

Volume_Score = min(100, (Volume[-1] / MA(Volume, 20)) * 40)
(1.3x average volume = 52 points, 2.5x average volume or more = 100 points)

Breakout_Quality_Score = max(0, 100 - ((Highest_Close(20) - Close) / Highest_Close(20) * 100) * 30)
(Close exactly at the 20-day high = 100 points, 2% below it = ~40 points)

RSI_Strength_Score = max(0, 100 - abs(Daily_RSI - 65) * 4)
(Rewards RSI closest to 65, the middle of the strength zone; 0 points at
RSI 40 or 90)

Higher score is better.

---

## Output Columns

Return:

- Symbol
- Company Name
- Sector
- Sector Rank
- Current Price
- Daily RSI(14)
- Volume[-1]
- Volume[-2]
- 20D Average Volume
- Volume[-1] / 20D Avg (ratio)
- 20-Day High
- Distance From 20-Day High (%)
- Close vs Close[-20] (%)
- Rank Score

Sort:

Rank Score DESC

Limit:

Top 20 Stocks
