# Stock Selection Rules

## Strategy Metadata

Strategy Name: Oversold Mean Reversion
Market: India (NSE/BSE)
Timeframe: Daily
Holding Period: Swing Trade (3-15 Days)

---

## Mandatory Filters

All rules below MUST pass.

### Rule 1: Oversold RSI

Description:
Stock must be meaningfully oversold, signaling exhaustion of the recent
selling pressure rather than a stock that is merely dipping.

Indicator:
RSI(14)

Condition:

RSI <= 30

Notes:
- Use daily timeframe.
- Calculate using 14 periods.
- Stocks with missing RSI data should be rejected.

---

### Rule 2: Extended Below Mean

Description:
Price must be stretched well below its recent average, since mean reversion
trades need meaningful distance to revert back toward.

Indicator:
20-Day Simple Moving Average (SMA20)

Condition:

Close < SMA20
AND
DistanceFromSMA20 >= 5%

Where:

DistanceFromSMA20 = ((SMA20 - Close) / SMA20) * 100

Notes:
- Use only completed sessions.
- Stocks with fewer than 20 sessions of history should be rejected.

---

### Rule 3: Bollinger Band Breach

Description:
Price should be trading at or below the lower Bollinger Band, a classic
statistical extreme suggesting the move is overdone in the short term.

Indicator:
Bollinger Bands (20, 2)

Condition:

Close <= LowerBollingerBand

---

### Rule 4: Volume Capitulation

Description:
Look for a spike in volume on the down move, suggesting capitulation
(panic selling) rather than a slow, low-conviction drift lower — capitulation
volume often marks a local bottom.

Condition:

Volume[-1] > (1.5 * AverageVolume20)

Where:

AverageVolume20 = 20-day average volume, excluding today.

Notes:
- Ignore today's volume.
- Stocks with missing volume data should be rejected.

---

### Rule 5: No Structural Breakdown

Description:
Exclude stocks that are oversold because of a structural/fundamental
breakdown (extended downtrend) rather than a short-term overreaction —
mean reversion works best on stocks still in a broader uptrend or range,
not stocks in a persistent downtrend.

Indicator:
100-Day Simple Moving Average (SMA100)

Condition:

Close >= (0.85 * SMA100)

Notes:
- Stocks with fewer than 100 sessions of history should be rejected.
- This rule filters out stocks that are down more than 15% below their
  longer-term trend, which usually reflects a broken trend rather than a
  short-term dip.

---

### Rule 6: Avoid Weak Sectors

Description:
Prefer reversion candidates from sectors that are not themselves in a
structural downtrend, since individual-stock reversion is more reliable
when it isn't fighting sector-wide weakness.

Condition:

SectorRank <= Top 10

Notes:
- Determine sector performance using all stocks in the sector.
- Rank sectors by recent average return.
- This is intentionally a looser cutoff (top 10, not top 5) since mean
  reversion candidates are, by definition, short-term underperformers even
  within strong sectors.

---

## Rejection Rules

Reject stock if ANY mandatory filter fails.

---

## Ranking Rules

After filtering, rank candidates.

### Rank Score

Score =
35% Oversold Severity
+
30% Distance From Mean
+
20% Volume Capitulation Strength
+
15% Sector Strength

Where:

Oversold Severity Score = max(0, (30 - RSI) * (100 / 30))
(0 at RSI=30, 100 at RSI=0)

Distance From Mean Score = min(100, DistanceFromSMA20 * 10)
(capped at 100; 10% distance or more scores 100)

Volume Capitulation Score = min(100, ((Volume[-1] / AverageVolume20) - 1) * 100)
(capped at 100; 2x average volume or more scores 100)

Sector Strength Score = max(0, 100 - (SectorRank - 1) * 10)
(rank 1 = 100, declining 10 points per rank)

Higher score is better.

---

## Output Columns

Return:

- Symbol
- Company Name
- Sector
- Current Price
- RSI(14)
- SMA20
- Distance From SMA20 (%)
- Lower Bollinger Band
- Volume[-1]
- 20D Average Volume
- SMA100
- Sector Rank
- Rank Score

Sort:

Rank Score DESC

Limit:

Top 20 Stocks
