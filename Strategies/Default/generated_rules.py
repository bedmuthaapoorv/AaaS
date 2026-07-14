import pandas as pd
# pyrefly: ignore [missing-import]
import pandas_ta as ta
import numpy as np

def evaluate_stock(symbol, df, universe, sector_ranks):
    if len(df) < 252:
        return False, {}

    # Data Preparation
    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']
    
    # Rule 1: Increasing Volume
    if len(vol) < 4: return False, {}
    v1, v2, v3 = vol.iloc[-2], vol.iloc[-3], vol.iloc[-4]
    if not (v1 > v2 > v3): return False, {}
    
    # Rule 2: RSI Range
    rsi = ta.rsi(close, length=14)
    current_rsi = rsi.iloc[-1]
    if not (40 <= current_rsi <= 60): return False, {}
    
    # Rule 3: No Recent 52 Week High
    high_252 = high.rolling(252).max()
    recent_highs = high_252.iloc[-30:]
    if recent_highs.max() >= high.iloc[-1]: return False, {}
    days_since_52wh = (high == high.rolling(252).max())[::-1].idxmax()
    days_since_52wh = len(df) - df.index.get_loc(days_since_52wh)
    if days_since_52wh <= 30: return False, {}
    
    # Rule 4: Sector Strength
    sector = universe.get(symbol, {}).get("Sector", "Unknown")
    sector_rank = sector_ranks.get(sector, 999)
    if sector_rank > 5: return False, {}
    
    # Rule 5: Clean Trendline Support (Simplified Logic)
    # Identify local lows in last 90 days
    lookback = 90
    recent_lows = low.iloc[-lookback:]
    # Find points where price is near a potential support line
    # Simplified: Check if price is within 3% of a linear regression support
    x = np.arange(len(recent_lows))
    slope, intercept = np.polyfit(x, recent_lows, 1)
    trendline_val = slope * (len(recent_lows) - 1) + intercept
    dist_pct = abs(close.iloc[-1] - trendline_val) / trendline_val
    
    if slope <= 0 or dist_pct > 0.03: return False, {}
    
    # Count touches (points within 1% of trendline)
    trendline_points = slope * x + intercept
    touches = np.sum(np.abs(recent_lows - trendline_points) / trendline_points < 0.01)
    if touches < 2: return False, {}
    
    # Ranking Calculations
    rsi_score = 100 - abs(current_rsi - 50)
    vol_growth = (vol.iloc[-1] / vol.iloc[-20:].mean())
    trendline_quality = min(touches * 10, 100)
    
    rank_score = (0.40 * trendline_quality) + (0.25 * (10 - sector_rank) * 10) + (0.20 * vol_growth * 10) + (0.15 * rsi_score)
    
    output_dict = {
        "Symbol": symbol,
        "Company Name": universe.get(symbol, {}).get("Name", "N/A"),
        "Sector": sector,
        "Current Price": close.iloc[-1],
        "RSI(14)": current_rsi,
        "Volume[-1]": v1,
        "Volume[-2]": v2,
        "Volume[-3]": v3,
        "20D Average Volume": vol.iloc[-20:].mean(),
        "Days Since 52 Week High": days_since_52wh,
        "Sector Rank": sector_rank,
        "Trendline Touch Count": int(touches),
        "Distance From Trendline (%)": round(dist_pct * 100, 2),
        "Rank Score": rank_score
    }
    
    return True, output_dict