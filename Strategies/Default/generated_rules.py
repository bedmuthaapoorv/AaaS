import pandas as pd
import pandas_ta as ta

def evaluate_stock(symbol, df, universe, sector_ranks, market_breadth):
    failed_rules = []
    details = {}
    passed = True

    try:
        if len(df) < 126:
            return {"Symbol": symbol, "Passed": False, "ClosenessScore": 0.0, "FailedRules": ["Insufficient data"], "Details": {}}

        # Indicators
        close = df['close']
        vol = df['volume']
        ma20 = ta.sma(close, length=20)
        ma50 = ta.sma(close, length=50)
        ma126 = ta.sma(close, length=126)
        vol_ma20 = ta.sma(vol, length=20)
        rsi = ta.rsi(close, length=14)
        
        curr_close = close.iloc[-1]
        prev_close = close.iloc[-2]
        close_20d_ago = close.iloc[-21]
        curr_vol = vol.iloc[-1]
        prev_vol = vol.iloc[-2]
        curr_ma20 = ma20.iloc[-1]
        curr_ma50 = ma50.iloc[-1]
        curr_ma126 = ma126.iloc[-1]
        curr_vol_ma20 = vol_ma20.iloc[-1]
        curr_rsi = rsi.iloc[-1]
        highest_20 = close.rolling(20).max().iloc[-1]
        
        details.update({
            "MA20": curr_ma20, "MA50": curr_ma50, "MA126": curr_ma126,
            "RSI": curr_rsi, "Volume1": curr_vol, "Volume2": prev_vol,
            "VolMA20": curr_vol_ma20, "Highest20": highest_20,
            "SectorRank": sector_ranks.get(symbol, 99)
        })

        # Rule 1: Liquidity
        if curr_vol_ma20 < 100000 or curr_close < 50:
            failed_rules.append("Liquidity floor not met")
            passed = False

        # Rule 2: Trend
        if not (curr_close > curr_ma20 > curr_ma50 > curr_ma126):
            failed_rules.append("Trend structure not met")
            passed = False

        # Rule 3: RSI
        if not (55 <= curr_rsi <= 75):
            failed_rules.append(f"RSI outside range (55-75): {curr_rsi:.2f}")
            passed = False

        # Rule 4: Volume
        if not (curr_vol > prev_vol and curr_vol >= 1.3 * curr_vol_ma20):
            failed_rules.append("Volume breakout criteria not met")
            passed = False

        # Rule 5: Breakout Proximity
        if not (curr_close >= 0.98 * highest_20 and curr_close > prev_close):
            failed_rules.append("Not pushing to 20-day high")
            passed = False

        # Rule 6: Extension
        if curr_close > 1.25 * close_20d_ago:
            failed_rules.append("Stock extended too far")
            passed = False

        # Rule 7: Sector
        rank = sector_ranks.get(symbol, 99)
        if rank > 10:
            failed_rules.append(f"Sector rank {rank} not in top 10")
            passed = False

        # Rule 8: Breadth
        if market_breadth < 45:
            failed_rules.append(f"Market breadth {market_breadth} below threshold")
            passed = False

        # Scoring
        rsi_score = 100 if 40 <= curr_rsi <= 60 else (max(0, 100 - (40 - curr_rsi) * 5) if curr_rsi < 40 else max(0, 100 - (curr_rsi - 60) * 5))
        vol_score = 100 if (curr_vol > prev_vol > vol.iloc[-3]) else (50 if (curr_vol > prev_vol or prev_vol > vol.iloc[-3]) else 0)
        sec_score = max(0, 100 - (rank - 5) * 10) if rank > 5 else 100
        dist = ((highest_20 - curr_close) / highest_20) * 100
        tl_score = 100 if dist <= 3 else max(0, 100 - (dist - 3) * 20)
        
        closeness = (tl_score * 0.40) + (sec_score * 0.25) + (vol_score * 0.20) + (rsi_score * 0.15)

    except Exception as e:
        passed = False
        failed_rules.append(f"Calculation error: {str(e)}")
        closeness = 0.0

    return {
        "Symbol": symbol,
        "Passed": passed,
        "ClosenessScore": float(closeness),
        "FailedRules": failed_rules,
        "Details": details
    }