import os
import sys
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types

load_dotenv()

def generate_rules():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not found.")
        print("Please create a .env file and add your API key: GEMINI_API_KEY=your_key")
        sys.exit(1)

    try:
        with open("rules.md", "r", encoding="utf-8") as f:
            rules_content = f.read()
    except FileNotFoundError:
        print("Error: rules.md not found in the current directory.")
        sys.exit(1)

    print("Generating python screening logic from rules.md...")
    
    prompt = f"""
You are an expert quantitative developer.

Generate production-ready Python code.

The generated file must contain:

1. All necessary imports.
2. A function:

def evaluate_stock(symbol, df, universe, sector_ranks, market_breadth):

Where market_breadth (float, 0-100) is the percentage of the entire stock
universe currently trading above its own 50-day moving average, computed
once per day across all stocks (not specific to this symbol). It is a
broad market regime signal - a stand-in for a Nifty benchmark index, since
no external index data is available. If the RULES below define a market
breadth filter, implement it using this parameter directly - do not attempt
to compute breadth yourself from `df` (a single stock's own data cannot
tell you about the whole market).

3. The function must return:

return {{
    "Symbol": symbol,
    "Passed": bool,
    "ClosenessScore": float,
    "FailedRules": list,
    "Details": dict
}}

Definitions:

Passed:
- True only if ALL mandatory rules pass.
- False otherwise.

FailedRules:
- Human readable list of failed rules.

Examples:
[
    "RSI outside range (63.5)",
    "Sector rank 8 not in top 5",
    "Volume not increasing for last 3 sessions"
]

Details:
Store every calculated metric used.

Example:
{{
    "RSI": 54.2,
    "SectorRank": 3,
    "TrendlineDistancePct": 1.8,
    "Volume1": 1200000,
    "Volume2": 1000000,
    "Volume3": 800000
}}

ClosenessScore:

Must be between 0 and 100.

Scoring weights:

Trendline Support = 40%
Sector Strength = 25%
Volume Trend = 20%
RSI = 15%

Rule Scoring:

RSI:
40-60 => 100

Below 40:
score = max(0, 100 - (40-rsi)*5)

Above 60:
score = max(0, 100 - (rsi-60)*5)

Volume:

V1 > V2 > V3:
100

One comparison fails:
50

Both fail:
0

Sector:

Rank <= 5:
100

Rank > 5:
score = max(0, 100 - (rank-5)*10)

Trendline:

Distance <= 3%:
100

Distance > 3%:
score = max(0, 100 - (distance_pct-3)*20)

Overall ClosenessScore:

(
trendline_score * 0.40 +
sector_score * 0.25 +
volume_score * 0.20 +
rsi_score * 0.15
)

Requirements:

- Use pandas_ta as ta.
- Handle missing data safely.
- Never throw exceptions.
- Return a valid dictionary even if a stock cannot be evaluated.
- Use helper functions when needed.
- Output ONLY valid Python code.
- No markdown.
- No explanations.

Critical implementation constraints:

- Never hardcode pandas_ta output column names (e.g. "BBL_20_2.0"). Column
  suffixes vary by pandas_ta version. Instead, select columns by prefix, e.g.:
  bb = ta.bbands(df['close'], length=20, std=2)
  lower_bb_col = next(c for c in bb.columns if c.startswith('BBL_'))
  lower_bb = bb[lower_bb_col].iloc[-1]
  Apply the same prefix-matching approach for any other multi-column
  pandas_ta indicator (MACD, Stochastic, ADX, etc.).
- Some pandas_ta indicators return a single-column pandas Series instead of
  a DataFrame (e.g. ta.rsi() with a single length). Never call `.columns` on
  the result without first checking `isinstance(result, pd.DataFrame)`.
  If it is a DataFrame, select the column by prefix as above; if it is a
  Series, use it directly. Apply this check for every pandas_ta call whose
  return type (Series vs DataFrame) is not certain.
- The top-level try/except in evaluate_stock must never swallow the error
  message. On exception, append f"Calculation error: {{e}}" (the actual
  exception text) to FailedRules, not a generic "Calculation error" string.
- `universe` maps symbol -> {{"Name": str, "Sector": str}} (capitalized keys).
  `sector_ranks` maps symbol -> int directly (NOT sector name -> int). To get
  a stock's sector rank, use `sector_ranks.get(symbol, 99)` directly - do NOT
  look up the stock's sector name first and then index sector_ranks by that
  name; sector_ranks is never keyed by sector name.

RULES:

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

    with open("generated_rules.py", "w", encoding="utf-8") as f:
        f.write(code)

    print("Successfully generated generated_rules.py!")

if __name__ == "__main__":
    generate_rules()
