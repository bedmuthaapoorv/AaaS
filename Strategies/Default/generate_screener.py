import os
import sys
from dotenv import load_dotenv
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
        with open("rules.md", "r") as f:
            rules_content = f.read()
    except FileNotFoundError:
        print("Error: rules.md not found in the current directory.")
        sys.exit(1)

    print("Generating python screening logic from rules.md...")
    
    prompt = f"""
    You are an expert quantitative developer. I will provide you with a stock screening rules document in markdown format.
    Your task is to generate a Python function named `evaluate_stock` that evaluates a stock against these rules.

    The function signature must be exactly:
    ```python
    def evaluate_stock(symbol, df, universe, sector_ranks):
        # ... your code ...
    ```

    Inputs:
    - `symbol`: The stock ticker string (e.g. "RELIANCE.NS").
    - `df`: A pandas DataFrame containing OHLCV data for the stock. Columns include 'Open', 'High', 'Low', 'Close', 'Volume'. It is indexed by Date. 
    - `universe`: A dictionary where `universe[symbol]["Name"]` and `universe[symbol]["Sector"]` give the company name and sector.
    - `sector_ranks`: A dictionary mapping sector names to their rank (integer, lower is better).

    Requirements:
    1. The function must return a tuple: `(passed, output_dict)`
       - `passed`: A boolean indicating if the stock passed ALL mandatory and rejection filters.
       - `output_dict`: A dictionary containing the exact columns specified in the "Output Columns" section of the rules.
    2. You must import `pandas_ta` as `ta` and any other standard python libraries you need INSIDE the generated python file (at the top).
    3. Output ONLY valid Python code. Do not wrap it in ```python``` markdown blocks. Do not add any conversational text.

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

    with open("generated_rules.py", "w") as f:
        f.write(code)

    print("Successfully generated generated_rules.py!")

if __name__ == "__main__":
    generate_rules()
