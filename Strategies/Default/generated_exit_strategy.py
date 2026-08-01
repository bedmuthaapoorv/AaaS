import pandas as pd
import pandas_ta as ta
import numpy as np

def resolve_exit(entry_price, entry_date, signal_history_df, future_df):
    try:
        # 1. Pre-Trade Calculations (Entry Time)
        if len(signal_history_df) < 50:
            return None
        
        atr_series = ta.atr(signal_history_df['high'], signal_history_df['low'], signal_history_df['close'], length=14)
        atr_entry = atr_series.iloc[-1]
        if pd.isna(atr_entry):
            return None

        # Market Mode Calculation
        # Assuming Nifty50 data is available in signal_history_df or accessible via global context
        # If not provided, we assume the signal_history_df contains a 'nifty50_close' column
        if 'nifty50_close' not in signal_history_df.columns:
            return None
            
        nifty_ma50 = ta.sma(signal_history_df['nifty50_close'], length=50).iloc[-1]
        is_bullish = signal_history_df['nifty50_close'].iloc[-1] > nifty_ma50
        
        atr_multiplier = 2.0 if is_bullish else 1.5
        tp_pct = 0.15 if is_bullish else 0.05
        initial_sl = entry_price - (atr_multiplier * atr_entry)
        
        # State Variables
        trailing_sl = initial_sl
        highest_close = entry_price
        
        # 2. Walk Future Data
        for i, (date, row) in enumerate(future_df.iterrows()):
            close = row['close']
            trading_days_since_entry = i + 1
            
            # Daily Update Logic
            if close > highest_close:
                highest_close = close
            
            # Determine SL Mode
            if close > entry_price:
                # TRAILING Mode
                atr_today = ta.atr(future_df['high'].iloc[:i+1], 
                                   future_df['low'].iloc[:i+1], 
                                   future_df['close'].iloc[:i+1], length=14).iloc[-1]
                candidate_sl = highest_close - (atr_multiplier * atr_today)
                if candidate_sl > trailing_sl:
                    trailing_sl = candidate_sl
            
            # Exit Conditions (Priority Order)
            
            # 1. Earnings (Assuming 'earnings_date' column exists in future_df)
            if 'earnings_date' in row and pd.notna(row['earnings_date']):
                days_to_earnings = (pd.to_datetime(row['earnings_date']) - pd.to_datetime(date)).days
                if days_to_earnings <= 1:
                    return {"ExitDate": date, "ExitPrice": close, "ExitReason": "EarningsExit"}
            
            # 2. Trailing Stop-Loss
            if close <= trailing_sl:
                return {"ExitDate": date, "ExitPrice": close, "ExitReason": "TSL"}
            
            # 3. Take-Profit
            if close >= entry_price * (1 + tp_pct):
                return {"ExitDate": date, "ExitPrice": close, "ExitReason": "TP"}
            
            # 4. Max Holding Period
            if trading_days_since_entry >= 30:
                return {"ExitDate": date, "ExitPrice": close, "ExitReason": "MaxHold"}
                
        return None

    except Exception:
        return None