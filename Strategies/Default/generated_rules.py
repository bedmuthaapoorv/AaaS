import pandas as pd
# pyrefly: ignore [missing-import]
import numpy as np
# pyrefly: ignore [missing-import]
import pandas_ta as ta

def get_rsi(df):
    rsi = ta.rsi(df['close'], length=14)
    return rsi.iloc[-1] if not rsi.empty else np.nan

def get_volume_data(df):
    if len(df) < 4:
        return None, None, None
    return df['volume'].iloc[-3], df['volume'].iloc[-2], df['volume'].iloc[-1]

def get_days_since_52w_high(df):
    if len(df) < 252:
        return np.nan
    high_252 = df['high'].rolling(window=252).max()
    last_high_idx = df.index[df['high'] == high_252.iloc[-1]].tolist()
    if not last_high_idx:
        return 999
    return (df.index[-1] - last_high_idx[-1]).days

def calculate_trendline_metrics(df):
    if len(df) < 90:
        return 0, 100.0, 0
    
    recent_df = df.tail(90)
    lows = recent_df['low']
    
    touches = 0
    min_dist = 100.0
    
    # Simplified trendline logic: find local minima
    local_minima = recent_df[recent_df['low'] == recent_df['low'].rolling(window=5, center=True).min()]
    
    if len(local_minima) >= 2:
        touches = len(local_minima)
        slope = (local_minima['low'].iloc[-1] - local_minima['low'].iloc[0]) / len(local_minima)
        dist = abs((df['close'].iloc[-1] - local_minima['low'].iloc[-1]) / local_minima['low'].iloc[-1]) * 100
        return touches, dist, slope
    
    return 0, 100.0, 0

def evaluate_stock(symbol, df, universe, sector_ranks):
    failed_rules = []
    details = {}
    
    try:
        rsi = get_rsi(df)
        v3, v2, v1 = get_volume_data(df)
        days_since_high = get_days_since_52w_high(df)
        sector_rank = sector_ranks.get(symbol, 99)
        touches, dist, slope = calculate_trendline_metrics(df)
        
        details = {
            "RSI": float(rsi),
            "Volume1": float(v1), "Volume2": float(v2), "Volume3": float(v3),
            "DaysSince52WeekHigh": float(days_since_high),
            "SectorRank": int(sector_rank),
            "TrendlineTouches": int(touches),
            "TrendlineDistancePct": float(dist)
        }

        # Rule Checks
        if not (v1 > v2 > v3): failed_rules.append("Volume not increasing for last 3 sessions")
        if not (40 <= rsi <= 60): failed_rules.append(f"RSI outside range ({rsi:.1f})")
        if days_since_high <= 30: failed_rules.append("Recent 52-week high")
        if sector_rank > 5: failed_rules.append(f"Sector rank {sector_rank} not in top 5")
        if touches < 2 or dist > 3 or slope <= 0: failed_rules.append("Trendline criteria not met")

        # Scoring
        rsi_score = 100 if 40 <= rsi <= 60 else (max(0, 100 - (40-rsi)*5) if rsi < 40 else max(0, 100 - (rsi-60)*5))
        vol_score = 100 if (v1 > v2 > v3) else (50 if (v1 > v2 or v2 > v3) else 0)
        sec_score = 100 if sector_rank <= 5 else max(0, 100 - (sector_rank-5)*10)
        trd_score = 100 if dist <= 3 else max(0, 100 - (dist-3)*20)
        
        closeness = (trd_score * 0.40) + (sec_score * 0.25) + (vol_score * 0.20) + (rsi_score * 0.15)

        return {
            "Symbol": symbol,
            "Passed": len(failed_rules) == 0,
            "ClosenessScore": float(closeness),
            "FailedRules": failed_rules,
            "Details": details
        }
    except Exception:
        return {
            "Symbol": symbol,
            "Passed": False,
            "ClosenessScore": 0.0,
            "FailedRules": ["Evaluation error"],
            "Details": {}
        }