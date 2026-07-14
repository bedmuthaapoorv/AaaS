# Stock Selection Rules

## Strategy Metadata

Strategy Name: Trendline Support Momentum
Market: India (NSE/BSE)
Timeframe: Daily
Holding Period: Swing Trade (1-30 Days)

---

## Mandatory Filters

All rules below MUST pass.

### Rule 1: Increasing Volume

Description:
Volume should show increasing participation over the last 3 completed trading sessions.

Condition:

Volume[-1] > Volume[-2]
AND
Volume[-2] > Volume[-3]

Notes:
- Ignore today's volume.
- Use only completed market sessions.
- Stocks with missing volume data should be rejected.

---

### Rule 2: RSI Range

Description:
Avoid overbought and oversold stocks.

Indicator:
RSI(14)

Condition:

40 <= RSI <= 60

Notes:
- Use daily timeframe.
- Calculate using 14 periods.

---

### Rule 3: No Recent 52 Week High

Description:
Avoid stocks that recently hit a new 52-week high.

Condition:

DaysSince52WeekHigh > 30

Alternative Implementation:

HighestHigh(252) was NOT made within last 30 trading sessions

---

### Rule 4: Sector Strength

Description:
Stock must belong to a sector showing strong relative performance this month.

Condition:

SectorRank <= Top 5

Suggested Sector Ranking Formula:

SectorReturnLast30Days
+
SectorVolumeGrowth
+
RelativePerformanceVsNifty

Notes:
- Determine sector performance using all stocks in the sector.
- Rank sectors monthly.
- Only consider stocks from the top 5 sectors.

---

### Rule 5: Clean Trendline Support

Description:
Stock should be trading near a well-defined ascending trendline support.

Requirements:

Minimum 2 confirmed touch points.

Touch points should be separated by at least 10 trading days.

No major breakdown below trendline during last 90 days.

Current price must be within 3% of trendline.

Condition:

TrendlineTouches >= 2
AND
DistanceFromTrendline <= 3%
AND
TrendlineSlope > 0

---

## Rejection Rules

Reject stock if ANY condition is true.

---

## Ranking Rules

After filtering, rank candidates.

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

---

## Output Columns

Return:

- Symbol
- Company Name
- Sector
- Current Price
- RSI(14)
- Volume[-1]
- Volume[-2]
- Volume[-3]
- 20D Average Volume
- Days Since 52 Week High
- Sector Rank
- Trendline Touch Count
- Distance From Trendline (%)
- Rank Score

Sort:

Rank Score DESC

Limit:

Top 20 Stocks