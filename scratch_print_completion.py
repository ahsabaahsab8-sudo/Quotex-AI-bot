import os
import sys
import asyncio
import json
from dotenv import load_dotenv

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    load_dotenv()
    
    from openai import OpenAI
    api_key = "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"
    nvidia_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )
    
    # Mock technical data with 60 candles
    mock_tech_data = {
        "summary": {
            "token": "XAUUSD_otc", "current_price": 4123.001, "latest_atr": 0.055, "average_atr_20": 0.057,
            "pivot_points_1h": {"pivot": 4122.90, "r1": 4123.20, "s1": 4122.70, "r2": 4123.40, "s2": 4122.40},
            "detected_candlestick_patterns": [],
            "metrics_1m": {"rsi": 53.5, "trend": "STRONG_UPTREND", "bollinger_upper": 4123.08, "bollinger_middle": 4122.99, "bollinger_lower": 4122.90},
            "metrics_5m": {"rsi": 67.6, "trend": "STRONG_UPTREND"},
            "metrics_15m": None
        },
        "candles": [{"open": 4122.99, "high": 4123.00, "low": 4122.99, "close": 4123.00} for _ in range(60)]
    }
    
    prompt = f"Analyze the data: {json.dumps(mock_tech_data)}"

    print("Querying stepfun-ai/step-3.7-flash with full completion print...")
    try:
        completion = nvidia_client.chat.completions.create(
            model="stepfun-ai/step-3.7-flash",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        print("Completion Object:")
        print(completion.model_dump_json(indent=2))
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
