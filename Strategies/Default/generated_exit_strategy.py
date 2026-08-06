import pandas as pd
import pandas_ta as ta

def resolve_exit(entry_price, entry_date, signal_history_df, future_df):
    try:
        # 1. Pre-Trade Calculation
        if len(signal_history_df) < 14:
            return None
        
        atr_entry_series = ta.atr(signal_history_df['high'], signal_history_df['low'], signal_history_df['close'], length=14)
        atr_entry = atr_entry_series.iloc[-1]
        
        if pd.isna(atr_entry):
            return None
            
        initial_sl = entry_price - (2.5 * atr_entry)
        
        # 2. Initialize State Variables
        trailing_sl = initial_sl
        highest_close = entry_price
        
        # 3. Walk through future_df
        # future_df includes entry_date. We iterate through all days.
        for i, (current_date, row) in enumerate(future_df.iterrows()):
            close = row['close']
            trading_days_since_entry = i + 1
            
            # Daily Update Logic
            # Step 1: Update Highest Close
            if close > highest_close:
                highest_close = close
            
            # Step 2: Ratchet Trailing Stop
            # Need history up to current day to compute ATR
            # Combine signal_history_df and future_df up to current date
            combined_df = pd.concat([signal_history_df, future_df.loc[:current_date]])
            atr_today_series = ta.atr(combined_df['high'], combined_df['low'], combined_df['close'], length=14)
            atr_today = atr_today_series.iloc[-1]
            
            if not pd.isna(atr_today):
                candidate_sl = highest_close - (2.5 * atr_today)
                if candidate_sl > trailing_sl:
                    trailing_sl = candidate_sl
            
            # Exit Conditions
            # Condition 1: Trailing Stop-Loss
            if close <= trailing_sl:
                return {
                    "ExitDate": current_date,
                    "ExitPrice": close,
                    "ExitReason": "TSL"
                }
            
            # Condition 2: Maximum Holding Period
            if trading_days_since_entry >= 90:
                return {
                    "ExitDate": current_date,
                    "ExitPrice": close,
                    "ExitReason": "MaxHold"
                }
                
        return None
        
    except Exception:
        return None