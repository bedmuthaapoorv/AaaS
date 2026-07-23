import pandas as pd
import numpy as np
import pandas_ta as ta
from scipy.stats import linregress

def evaluate_stock(symbol, df, universe, sector_ranks):
    failed_rules = []
    details = {}
    
    try:
        if len(df) < 130:
            return {"Symbol": symbol, "Passed": False, "ClosenessScore": 0.0, "FailedRules": ["Insufficient data"], "Details": {}}

        # RSI Calculation
        rsi_df = ta.rsi(df['close'], length=14)
        rsi_val = rsi_df.iloc[-1]
        details["RSI"] = float(rsi_val)
        
        # Volume Trend
        v1, v2, v3 = df['volume'].iloc[-1], df['volume'].iloc[-2], df['volume'].iloc[-3]
        details.update({"Volume1": float(v1), "Volume2": float(v2), "Volume3": float(v3)})
        
        # Sector Rank
        sector_rank = sector_ranks.get(symbol, 99)
        details["SectorRank"] = sector_rank
        
        # 52 Week High
        high_252 = df['high'].rolling(252).max()
        days_since_high = (high_252 == df['high']).iloc[-30:].sum()
        details["DaysSince52WeekHigh"] = int(days_since_high)
        
        # Trendline Logic (Simplified approximation for production)
        # Find local minima over 126 days
        lookback = 126
        recent_df = df.iloc[-lookback:].copy()
        recent_df['minima'] = recent_df['low'][(recent_df['low'].shift(1) > recent_df['low']) & (recent_df['low'].shift(-1) > recent_df['low'])]
        minima_indices = recent_df.index[recent_df['minima'].notna()].tolist()
        
        trendline_dist = 10.0
        touch_count = len(minima_indices)
        if touch_count >= 2:
            x = np.arange(len(recent_df))
            slope, intercept, _, _, _ = linregress(x, recent_df['low'])
            trendline_val = slope * (len(recent_df) - 1) + intercept
            trendline_dist = abs((df['close'].iloc[-1] - trendline_val) / trendline_val) * 100
        
        details["TrendlineDistancePct"] = float(trendline_dist)
        details["TrendlineTouches"] = touch_count
        
        # Scoring
        rsi_score = 100 if 40 <= rsi_val <= 60 else (max(0, 100 - (40 - rsi_val) * 5) if rsi_val < 40 else max(0, 100 - (rsi_val - 60) * 5))
        
        vol_score = 100 if (v1 > v2 > v3) else (50 if (v1 > v2 or v2 > v3) else 0)
        
        sec_score = 100 if sector_rank <= 5 else max(0, 100 - (sector_rank - 5) * 10)
        
        tl_score = 100 if trendline_dist <= 3 else max(0, 100 - (trendline_dist - 3) * 20)
        
        closeness_score = (tl_score * 0.40) + (sec_score * 0.25) + (vol_score * 0.20) + (rsi_score * 0.15)
        
        # Mandatory Rules Check
        if not (v1 > v2 > v3): failed_rules.append("Volume not increasing for last 3 sessions")
        if not (40 <= rsi_val <= 60): failed_rules.append(f"RSI outside range ({rsi_val:.1f})")
        if days_since_high > 0: failed_rules.append("Recent 52-week high detected")
        if sector_rank > 5: failed_rules.append(f"Sector rank {sector_rank} not in top 5")
        if touch_count < 2 or trendline_dist > 3: failed_rules.append("Trendline support criteria not met")
        
        return {
            "Symbol": symbol,
            "Passed": len(failed_rules) == 0,
            "ClosenessScore": float(closeness_score),
            "FailedRules": failed_rules,
            "Details": details
        }
        
    except Exception as e:
        return {
            "Symbol": symbol,
            "Passed": False,
            "ClosenessScore": 0.0,
            "FailedRules": [f"Calculation error: {str(e)}"],
            "Details": {}
        }