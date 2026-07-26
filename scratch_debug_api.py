import os
import json
import httpx
import asyncio
from dotenv import load_dotenv

async def test_raw_api():
    load_dotenv()
    
    api_key = "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"
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Mock data matching the bot's payload
    mock_tech_data = {
        "summary": {
            "token": "EURUSD_otc",
            "current_price": 1.0825,
            "latest_atr": 0.0003,
            "average_atr_20": 0.0004,
            "pivot_points_1h": {
                "pivot": 1.0820, "r1": 1.0835, "s1": 1.0810, "r2": 1.0845, "s2": 1.0800
            },
            "detected_candlestick_patterns": ["Bullish Engulfing (Strong Bullish)"],
            "metrics_1m": {
                "rsi": 32.5, "trend": "STRONG_UPTREND", "ema_20": 1.0822, "ema_50": 1.0818,
                "macd": 0.0001, "macd_signal": 0.00008, "macd_diff": 0.00002,
                "bollinger_upper": 1.0830, "bollinger_middle": 1.0820, "bollinger_lower": 1.0810,
                "support_50": 1.0812, "resistance_50": 1.0828
            },
            "metrics_5m": {
                "rsi": 45.0, "trend": "STRONG_UPTREND", "macd": 0.0002, "macd_signal": 0.0001, "macd_diff": 0.0001, "current_price_5m": 1.0824
            },
            "metrics_15m": {
                "rsi": 50.0, "trend": "SIDEWAYS / NEUTRAL", "current_price_15m": 1.0820
            }
        },
        "candles": [
            {"open": 1.0824, "high": 1.0826, "low": 1.0823, "close": 1.0825}
            for _ in range(60)
        ]
    }
    
    prompt = f"Analyze this data and return the trade direction (UP, DOWN, or NO-TRADE) in structured JSON format. Data: {json.dumps([mock_tech_data])}"
    
    payload = {
        "model": "z-ai/glm-5.2",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"}
    }
    
    async with httpx.AsyncClient(timeout=45.0) as client:
        print("Sending POST request to Nvidia integrate API...")
        response = await client.post(url, headers=headers, json=payload)
        print(f"Status Code: {response.status_code}")
        print("Headers:")
        for k, v in response.headers.items():
            print(f"  {k}: {v}")
        print("\nResponse Body:")
        print(response.text)

if __name__ == "__main__":
    asyncio.run(test_raw_api())
