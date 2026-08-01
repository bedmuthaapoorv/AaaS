import pandas as pd
import pandas_ta as ta
import numpy as np

def evaluate_stock(symbol, df, universe, sector_ranks):
    failed_rules = []
    details = {}
    passed = True

    try:
        if len(df) < 130:
            return {"Symbol": symbol, "Passed": False, "ClosenessScore": 0.0, "FailedRules": ["Insufficient data"], "Details": {}}

        # Data Prep
        close = df['close']
        vol = df['volume']
        ma20 = ta.sma(close, length=20)
        ma50 = ta.sma(close, length=50)
        ma126 = ta.sma(close, length=126)
        rsi = ta.rsi(close, length=14)
        vol_sma20 = ta.sma(vol, length=20)

        curr_close = close.iloc[-1]
        curr_vol = vol.iloc[-1]
        avg_vol_20 = vol_sma20.iloc[-1]
        curr_rsi = rsi.iloc[-1]
        
        details.update({
            "Price": curr_close,
            "Volume1": curr_vol,
            "Volume2": vol.iloc[-2],
            "Volume3": vol.iloc[-3],
            "RSI": curr_rsi,
            "MA126": ma126.iloc[-1]
        })

        # Rule 1: Liquidity
        if avg_vol_20 < 200000 or curr_close < 100:
            passed = False
            failed_rules.append("Liquidity floor not met")

        # Rule 3: Daily RSI
        if not (45 <= curr_rsi <= 58) or not (rsi.iloc[-1] > rsi.iloc[-2]):
            passed = False
            failed_rules.append(f"Daily RSI range/momentum invalid ({curr_rsi:.2f})")

        # Rule 4: Volume
        if not (curr_vol > vol.iloc[-2] > vol.iloc[-3]) or not (curr_vol >= avg_vol_20):
            passed = False
            failed_rules.append("Volume trend or magnitude insufficient")

        # Rule 7: MA126
        if curr_close <= ma126.iloc[-1]:
            passed = False
            failed_rules.append("Price below 6-month MA")

        # Rule 8: Proxy Trendline
        dist_pct = abs(curr_close - close.iloc[-10:].min()) / curr_close * 100
        details["TrendlineDistancePct"] = dist_pct
        if not (dist_pct <= 2 and curr_close > ma20.iloc[-1] > ma50.iloc[-1] > ma126.iloc[-1]):
            passed = False
            failed_rules.append("Trendline support criteria not met")

        # Rule 9: Sector
        rank = sector_ranks.get(symbol, 99)
        details["SectorRank"] = rank
        if rank > 5:
            passed = False
            failed_rules.append(f"Sector rank {rank} not in top 5")

        # Scoring
        rsi_score = 100 if 40 <= curr_rsi <= 60 else (max(0, 100 - abs(40-curr_rsi)*5) if curr_rsi < 40 else max(0, 100 - (curr_rsi-60)*5))
        vol_score = 100 if (curr_vol > vol.iloc[-2] > vol.iloc[-3]) else (50 if (curr_vol > vol.iloc[-2] or vol.iloc[-2] > vol.iloc[-3]) else 0)
        sec_score = max(0, 100 - (rank-5)*10) if rank > 5 else 100
        tl_score = max(0, 100 - (dist_pct-3)*20) if dist_pct > 3 else 100
        
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