import pandas as pd
import pandas_ta as ta
import numpy as np

def evaluate_stock(symbol, df, universe, sector_ranks):
    failed_rules = []
    details = {}
    
    try:
        if len(df) < 100:
            return {"Symbol": symbol, "Passed": False, "ClosenessScore": 0.0, "FailedRules": ["Insufficient data (<100 sessions)"], "Details": {}}

        close = df['close']
        volume = df['volume']
        
        # Indicators
        rsi_series = ta.rsi(close, length=14)
        rsi = rsi_series.iloc[-1] if not rsi_series.empty else np.nan
        
        sma20 = ta.sma(close, length=20).iloc[-1]
        sma100 = ta.sma(close, length=100).iloc[-1]
        
        bb = ta.bbands(close, length=20, std=2)
        lbb_col = next((c for c in bb.columns if c.startswith('BBL_')), None)
        lbb = bb[lbb_col].iloc[-1] if lbb_col else np.nan
        
        vol_prev = volume.iloc[-2]
        avg_vol20 = volume.iloc[-21:-1].mean()
        
        dist_sma20 = ((sma20 - close.iloc[-1]) / sma20) * 100
        sector_rank = sector_ranks.get(symbol, 99)
        
        details = {
            "RSI": float(rsi),
            "SMA20": float(sma20),
            "DistanceFromSMA20": float(dist_sma20),
            "LowerBB": float(lbb),
            "VolumePrev": float(vol_prev),
            "AvgVolume20": float(avg_vol20),
            "SMA100": float(sma100),
            "SectorRank": int(sector_rank)
        }

        # Mandatory Rules
        if np.isnan(rsi) or rsi > 30:
            failed_rules.append(f"RSI {rsi:.2f} not <= 30")
        
        if close.iloc[-1] >= sma20 or dist_sma20 < 5:
            failed_rules.append("Price not extended below SMA20 by 5%")
            
        if close.iloc[-1] > lbb:
            failed_rules.append("Price above Lower Bollinger Band")
            
        if vol_prev <= (1.5 * avg_vol20):
            failed_rules.append("Volume capitulation not met")
            
        if close.iloc[-1] < (0.85 * sma100):
            failed_rules.append("Structural breakdown (Price < 85% SMA100)")
            
        if sector_rank > 10:
            failed_rules.append(f"Sector rank {sector_rank} not in top 10")

        passed = len(failed_rules) == 0

        # Scoring
        rsi_score = max(0, (30 - rsi) * (100 / 30)) if not np.isnan(rsi) else 0
        dist_score = min(100, dist_sma20 * 10)
        vol_score = min(100, ((vol_prev / avg_vol20) - 1) * 100) if avg_vol20 > 0 else 0
        sec_score = max(0, 100 - (sector_rank - 1) * 10)
        
        closeness = (rsi_score * 0.35) + (dist_score * 0.30) + (vol_score * 0.20) + (sec_score * 0.15)

        return {
            "Symbol": symbol,
            "Passed": passed,
            "ClosenessScore": float(closeness),
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