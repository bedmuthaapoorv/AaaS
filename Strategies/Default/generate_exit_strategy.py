import os
import sys
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types

load_dotenv()

def generate_exit_strategy():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not found.")
        print("Please create a .env file and add your API key: GEMINI_API_KEY=your_key")
        sys.exit(1)

    try:
        with open("exit_rules.md", "r", encoding="utf-8") as f:
            rules_content = f.read()
    except FileNotFoundError:
        print("Error: exit_rules.md not found in the current directory.")
        sys.exit(1)

    print("Generating python exit logic from exit_rules.md...")

    prompt = f"""
You are an expert quantitative developer.

Generate production-ready Python code implementing a backtest EXIT strategy.

The generated file must contain:

1. All necessary imports (pandas as pd, pandas_ta as ta if indicators are needed).
2. A function:

def resolve_exit(entry_price, entry_date, signal_history_df, future_df):

Parameters:

- entry_price (float): the trade's entry price (the opening price on the
  first day of future_df).
- entry_date (a date-like object): the date of entry_price.
- signal_history_df: a pandas DataFrame of OHLCV data up to and including
  the signal day (the day BEFORE entry), lowercase columns
  'open','high','low','close','volume', ascending by date, indexed by date.
  Use this ONLY to compute any indicator needed at entry time (e.g. ATR for
  a trailing stop). Never use future_df to compute entry-time indicators -
  that would be look-ahead bias.
- future_df: a pandas DataFrame of OHLCV data from entry_date through the
  last available day, inclusive, ascending by date, indexed by date, same
  lowercase columns. Walk this day by day (in order) to decide when to exit.
  Do NOT use any intraday high/low for exit triggers unless exit_rules.md
  explicitly says to - by default use only each day's 'close'.

Return value:

The function MUST return either:

(a) A dict when an exit condition triggers within future_df:
    {{
        "ExitDate": <the date from future_df's index where the exit fired>,
        "ExitPrice": <float, the close price on that date (or the
                      appropriate trigger price if exit_rules.md specifies
                      one)>,
        "ExitReason": <short string tag identifying which condition fired,
                       e.g. "SL", "TP", "TrailingATR">
    }}

(b) None, if no exit condition in exit_rules.md triggers anywhere within
    future_df. Do NOT invent a fallback exit yourself - returning None is
    correct and expected in this case. The caller (not this function)
    handles forcing a close at the range's end.

Requirements:

- Use pandas_ta as ta for any indicators (ATR, moving averages, etc.).
- Handle missing/insufficient data safely (e.g. not enough history to
  compute an indicator at entry) by returning None rather than raising.
- Never throw exceptions - wrap the body in try/except and return None on
  any error.
- Use helper functions when needed.
- Output ONLY valid Python code.
- No markdown.
- No explanations.

Critical implementation constraints:

- Never hardcode pandas_ta output column names (e.g. "ATRr_14"). Column
  suffixes vary by pandas_ta version. Instead, select columns by prefix, e.g.:
  atr_df = ta.atr(df['high'], df['low'], df['close'], length=14)
  (ta.atr returns a Series, not a DataFrame, so this one is safe as-is: use
  atr_df.iloc[-1] directly.) For any indicator that DOES return a DataFrame
  (bbands, macd, stoch, adx, etc.), select columns by prefix matching, e.g.:
  bb = ta.bbands(df['close'], length=20, std=2)
  lower_bb_col = next(c for c in bb.columns if c.startswith('BBL_'))
  lower_bb = bb[lower_bb_col].iloc[-1]
- Only compute entry-time indicators (e.g. ATR at entry) from
  signal_history_df, never from future_df - future_df is for walking
  forward and checking exit conditions only.
- If exit_rules.md describes a fallback ("what happens if nothing
  triggers"), IGNORE it - the caller always handles that itself. This
  function must only implement the specific exit conditions, and return
  None when none of them fire.

EXIT_RULES:

{rules_content}
"""

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
        )
    )

    code = response.text.strip()
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]

    with open("generated_exit_strategy.py", "w", encoding="utf-8") as f:
        f.write(code)

    print("Successfully generated generated_exit_strategy.py!")

if __name__ == "__main__":
    generate_exit_strategy()
