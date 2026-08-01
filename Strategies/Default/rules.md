# Stock Selection Rules

## Strategy Metadata

Strategy Name: Trendline Support Momentum v2
Market: India (NSE/BSE)
Timeframe: Daily
Holding Period: Swing Trade (1-30 Days)

---

## Mandatory Filters

All rules below MUST pass.

---

### Rule 1: Minimum Liquidity Floor

Description:
Reject illiquid stocks before any other check. Ensures volume signals
are meaningful and exits are executable without slippage.

Condition:

20D_Avg_Volume >= 200000
AND
Close >= 100

Notes:
- 200,000 shares/day minimum ensures the stock is tradeable at swing
  size without moving the market against you.
- Price floor of ₹100 eliminates penny stocks whose percentage moves
  are noise-driven not momentum-driven.
- This filter runs FIRST. Stocks failing here are dropped immediately.

---

### Rule 2: Weekly RSI Trend Confirmation

Description:
Confirm the stock is in a medium-term uptrend before checking daily
signals. This prevents buying a short-term bounce inside a larger
downtrend — the core cause of the VEEV, TEL and Siemens losses.

Indicator:
Weekly_RSI(14)

Condition:

Weekly_RSI >= 50

Notes:
- Weekly RSI below 50 means the medium-term trend is bearish.
  Any daily trendline seen in this state is a relief rally, not
  a real trendline — do not enter.
- Weekly RSI is calculated on the weekly timeframe using 14 periods.
- This is the single most important addition to the original rules.

---

### Rule 3: Daily RSI Range (Tightened)

Description:
Stock must be in neutral momentum territory on the daily timeframe —
not extended, not falling. Tightened from 40-60 to 45-58 to reduce
false signals at the edges of the range.

Indicator:
RSI(14) on Daily timeframe

Condition:

45 <= Daily_RSI <= 58

Notes:
- Original range was 40-60. The edges (40-42 and 58-60) produced
  too many entries on stocks with fading momentum (RSI falling from
  above 60) or stocks not yet confirmed oversold (RSI still falling
  toward 40). Tightening to 45-58 filters these out.
- RSI must be RISING (RSI[-1] > RSI[-2]) — confirms momentum is
  building, not decelerating. A falling RSI entering the zone from
  above is a declining stock, not a trendline bounce.

Additional Condition:

Daily_RSI[-1] > Daily_RSI[-2]

---

### Rule 4: Volume — Increasing AND Above Floor

Description:
Volume must be both increasing over 3 sessions AND above the 20-day
average on the most recent session. The original rule only checked
direction, not magnitude — allowing 3 days of thin, low-conviction
volume to pass.

Condition:

Volume[-1] > Volume[-2]
AND
Volume[-2] > Volume[-3]
AND
Volume[-1] >= 1.0 * MA(Volume, 20)

Notes:
- The third condition (Volume[-1] >= 1.0x average) is the new
  addition. Volume must be at least at average on the most recent
  completed session.
- Ideal entries have Volume[-1] >= 1.2x average. Consider using
  this as a bonus scoring factor rather than a hard filter if it
  eliminates too many candidates.
- Ignore today's incomplete session volume throughout.

---

### Rule 5: No Recent 52-Week High

Description:
Avoid stocks that recently made a new 52-week high. Unchanged from v1.

Condition:

DaysSince52WeekHigh > 30

Alternative Implementation:

HighestHigh(252) was NOT made within last 30 trading sessions

---

### Rule 6: No Upcoming Earnings

Description:
NEW. Reject stocks with earnings announcements within the next 15
calendar days from the signal date. Earnings events create binary
price risk that overrides technical setups.

Condition:

DaysUntilNextEarnings > 15

Notes:
- 15 days gives a full swing cycle (10-12 days) plus a 3-day buffer
  before results risk begins to affect price.
- If earnings date is unavailable, do NOT skip this check — treat
  the stock as rejected. Unknown earnings date = unquantified risk.
- Source earnings dates from NSE announcements or Tickertape.

---

### Rule 7: Stock Above 6-Month Moving Average

Description:
Stock must be trading above its 126-day moving average. This confirms
the 6-month trend is up. A stock below its 6-month MA is in a
medium-term downtrend regardless of any short-term trendline visible
on the chart.

Condition:

Close > MA(126)

Notes:
- This was part of Rule 5 (Trendline) in v1 but is now a standalone
  mandatory filter because it is more important than trendline quality.
  A stock can have a perfect trendline and still be in a downtrend
  below MA(126).

---

### Rule 8: Clean Ascending Trendline Support

Description:
Stock must be near a well-defined ascending trendline established over
at least 6 months. Unchanged structurally from v1 but with tighter
distance requirement reduced from 3% to 2% to improve entry precision.

Requirements:

Minimum 2 confirmed touch points.
Touch points separated by at least 10 trading days.
Trendline must originate at least 126 trading days ago.
No breakdown below trendline during last 126 trading days.
Current price within 2% of trendline value (tightened from 3%).
Trendline slope must be positive.

Condition:

TrendlineTouches >= 2
AND
DistanceFromTrendline <= 2%
AND
TrendlineSlope > 0
AND
TrendlineOrigin >= 126 trading days ago
AND
NoBreakdownBelow(Trendline, 126 days)

Notes:
- Distance tightened from 3% to 2% to ensure entries are genuinely
  AT support, not approaching it from 3% away.
- If your backtesting engine cannot detect trendlines algorithmically,
  use the following proxy condition instead:

  PROXY (if trendline detection unavailable):
  Close is within 2% of the lowest close of the last 10 trading days
  AND Close > MA(20)
  AND MA(20) > MA(50)
  AND MA(50) > MA(126)
  (This MA stack confirms an uptrend across all timeframes as a
  trendline substitute)

---

### Rule 9: Sector Strength

Description:
Stock must belong to a top-performing sector. Expanded formula with
explicit weights for backtester implementation.

Condition:

SectorRank <= Top 5

Sector Ranking Formula (explicit weights for backtester):

SectorScore =
  (0.50 * SectorReturnLast30Days_vs_Nifty)
+ (0.30 * SectorVolumeGrowthLast30Days)
+ (0.20 * SectorBreadth)

Where:
SectorReturnLast30Days_vs_Nifty =
  Median return of all stocks in sector over last 30 days
  MINUS Nifty50 return over same 30 days

SectorVolumeGrowthLast30Days =
  (Median Volume last 10 days / Median Volume 11-30 days ago) - 1

SectorBreadth =
  Percentage of stocks in sector trading above their MA(20)

Notes:
- Rank all sectors by SectorScore descending.
- Only stocks in the top 5 ranked sectors pass this filter.
- Recompute sector ranks at the start of each calendar month.
- Minimum 5 stocks per sector required to compute a valid rank.
  Sectors with fewer than 5 stocks are excluded from ranking.

---

### Rule 5: Clean Trendline Support

Description:
Stock should be trading near a well-defined ascending trendline support
that has been established over a minimum of 6 months (approximately 126
trading days).

Requirements:

Minimum 2 confirmed touch points.

Touch points should be separated by at least 10 trading days.

Trendline must originate from at least 126 trading days ago (6 months).

No major breakdown below trendline during last 126 trading days.

Current price must be within 3% of trendline.

Stock must be trading above its 126-day (6-month) moving average.

Condition:

TrendlineTouches >= 2
AND
DistanceFromTrendline <= 3%
AND
TrendlineSlope > 0
AND
TrendlineOrigin >= 126 trading days ago
AND
Close > MA(126)
AND
NoBreadownBelow(Trendline, 126 days)

## Rejection Rules

Reject stock immediately if ANY of the following is true.
These are checked AFTER mandatory filters, as a final safety layer.

1. Stock has declined more than 25% from its 52-week high
   AND the decline happened within the last 60 trading days.
   (Indicates active distribution, not healthy correction)

2. Promoter holding has decreased by more than 2% in the last
   two consecutive quarters.
   (Insider exit signal — Bandhan Bank pattern)

3. Last reported quarterly earnings showed PAT decline > 20% YoY.
   (Fundamental deterioration underneath the trendline)

4. Stock is classified as a penny stock (Close < ₹100).
   (Already caught by Rule 1 but explicit rejection for clarity)

---

## Ranking Rules

After all filters pass, rank candidates by score.

### Rank Score

Score =
  35% * Trendline_Quality_Score
+ 20% * Sector_Strength_Score
+ 20% * Volume_Score
+ 15% * Weekly_RSI_Score
+ 10% * RSI_Proximity_Score

Where:

Trendline_Quality_Score:
  Base: TrendlineTouches / 5 * 100 (capped at 100)
  Bonus: +10 if TrendlineTouches >= 3
  Bonus: +10 if TrendlineOrigin >= 252 trading days (1 year)

Sector_Strength_Score:
  (6 - SectorRank) / 5 * 100
  (Rank 1 = 100, Rank 5 = 20)

Volume_Score:
  (Volume[-1] / MA(Volume,20)) * 50
  Capped at 100.
  (1.0x avg = 50 points, 2.0x avg = 100 points)

Weekly_RSI_Score:
  (Weekly_RSI - 50) * 4
  Capped at 100, floored at 0.
  (Weekly RSI 50 = 0 points, Weekly RSI 75 = 100 points)

RSI_Proximity_Score:
  100 - abs(Daily_RSI - 52) * 5
  Floored at 0.
  (Rewards RSI closest to 52, slightly above neutral)

Higher score = better candidate.

---

## Output Columns

Return the following for each candidate:

- Symbol
- Company Name
- Sector
- Sector Rank
- Current Price
- Daily RSI(14)
- Weekly RSI(14)
- Volume[-1]
- Volume[-2]
- Volume[-3]
- 20D Average Volume
- Volume[-1] / 20D Avg (ratio)
- Days Since 52-Week High
- Distance From Trendline (%)
- Trendline Touch Count
- Trendline Origin (trading days ago)
- Close vs MA(126) (% above)
- Days Until Next Earnings
- Last Quarter PAT Change YoY (%)
- Rank Score

Sort: Rank Score DESC
Limit: Top 20 Stocks
