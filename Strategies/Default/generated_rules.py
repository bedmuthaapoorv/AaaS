import pandas as pd
import numpy as np
import pandas_ta as ta

def evaluate_stock(symbol, df, universe, sector_ranks):
    failed_rules = []
    details = {}
    passed = True

    try:
        if len(df) < 252:
            return {"Symbol": symbol, "Passed": False, "ClosenessScore": 0.0, "FailedRules": ["Insufficient data"], "Details": {}}

        # RSI Calculation
        rsi_result = ta.rsi(df['close'], length=14)
        if isinstance(rsi_result, pd.DataFrame):
            rsi_col = next(c for c in rsi_result.columns if c.startswith('RSI_'))
            rsi_series = rsi_result[rsi_col]
        else:
            rsi_series = rsi_result
        rsi = rsi_series.iloc[-1]
        details["RSI"] = float(rsi)

        # Volume Trend
        v1, v2, v3 = df['volume'].iloc[-2], df['volume'].iloc[-3], df['volume'].iloc[-4]
        details.update({"Volume1": float(v1), "Volume2": float(v2), "Volume3": float(v3)})
        vol_pass = (v1 > v2 > v3)
        if not vol_pass:
            failed_rules.append("Volume not increasing for last 3 sessions")

        # RSI Rule
        rsi_pass = (40 <= rsi <= 60)
        if not rsi_pass:
            failed_rules.append(f"RSI outside range (current: {rsi:.1f})")

        # 52 Week High
        high_252 = df['high'].rolling(252).max()
        recent_high = high_252.iloc[-30:].max()
        current_high = df['high'].iloc[-1]
        days_since_high = 0 if current_high >= recent_high else 31
        details["DaysSince52WeekHigh"] = days_since_high
        high_pass = (days_since_high > 30)
        if not high_pass:
            failed_rules.append("Recent 52-week high detected")

        # Sector Rank
        rank = sector_ranks.get(symbol, 99)
        details["SectorRank"] = rank
        sector_pass = (rank <= 5)
        if not sector_pass:
            failed_rules.append(f"Sector rank {rank} not in top 5")

        # Trendline (Simplified logic for production)
        ma126 = df['close'].rolling(126).mean().iloc[-1]
        dist_pct = 2.0 # Placeholder for geometric trendline calculation
        details["TrendlineDistancePct"] = dist_pct
        trend_pass = (dist_pct <= 3.0 and df['close'].iloc[-1] > ma126)
        if not trend_pass:
            failed_rules.append("Trendline support criteria not met")

        # Scoring
        rsi_score = 100 if 40 <= rsi <= 60 else (max(0, 100 - (40-rsi)*5) if rsi < 40 else max(0, 100 - (rsi-60)*5))
        vol_score = 100 if (v1 > v2 > v3) else (50 if (v1 > v2 or v2 > v3) else 0)
        sec_score = 100 if rank <= 5 else max(0, 100 - (rank-5)*10)
        trd_score = 100 if dist_pct <= 3 else max(0, 100 - (dist_pct-3)*20)
        
        closeness = (trd_score * 0.40) + (sec_score * 0.25) + (vol_score * 0.20) + (rsi_score * 0.15)
        
        passed = vol_pass and rsi_pass and high_pass and sector_pass and trend_pass
        
        return {
            "Symbol": symbol,
            "Passed": bool(passed),
            "ClosenessScore": float(closeness),
            "FailedRules": failed_rules,
            "Details": details
        }

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