import os
import asyncio
import sys
import json
from dotenv import load_dotenv
from openai import OpenAI

# Add project root to python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import main as main_module

async def main():
    load_dotenv()
    
    # We will query DeepSeek with some mock data to see what it returns
    mock_data = {
        "token": "AUDCAD_otc",
        "current_price": 0.9235,
        "latest_atr": 0.0005,
        "average_atr_20": 0.0005,
        "metrics_1m": {
            "rsi": 45, "trend": "SIDEWAYS / NEUTRAL", "ema_9": 0.9234, "ema_20": 0.9233, "ema_50": 0.9230,
            "macd": 0, "macd_signal": 0, "macd_diff": 0, "bollinger_upper": 0.9240, "bollinger_middle": 0.9235,
            "bollinger_lower": 0.9230, "support_50": 0.9220, "resistance_50": 0.9250
        }
    }
    
    data_json = json.dumps([mock_data], indent=2)
    prompt = main_module.TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    
    ZEN_KEY = os.getenv("OPENCODE_ZEN_KEY", "sk-5UVZdq3bAXTbOm55FiX8LqZIy4gKz2VFs5MVdU7QFfsqXQ8evXzVDU3Y0Tc5qY32")
    zen_client = OpenAI(base_url="https://opencode.ai/zen/v1", api_key=ZEN_KEY)
    
    print("Querying DeepSeek...")
    try:
        completion = await asyncio.to_thread(
            zen_client.chat.completions.create,
            model="deepseek-v4-flash-free",
            messages=[
                {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2, max_tokens=4096
        )
        text = completion.choices[0].message.content.strip()
        print("\n--- Raw DeepSeek Output ---")
        print(text)
        print("---------------------------")
        
        # Try parsing
        text_clean = text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text_clean)
        print("Successfully parsed JSON!")
        print(parsed)
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
