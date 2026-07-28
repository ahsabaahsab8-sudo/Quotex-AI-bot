"""Test all AI models individually."""
import os, sys, json, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

# Mock technical data
mock_data = {
    "summary": {
        "rsi": 45.2, "bb_position": 0.3, "macd_hist": -0.001, "ema_trend": "neutral",
        "adx": 22, "volume_sma_ratio": 1.1, "close": 1.1325, "atr": 0.005,
        "payout_percentage": 80, "volatility": "medium", "score": 7,
        "ema_9": 1.1320, "ema_21": 1.1318, "support": 1.1300, "resistance": 1.1350,
        "direction": "neutral", "hour_sin": 0.5, "hour_cos": 0.5
    }
}

async def main():
    from main import query_glm_analysis, query_deepseek_vote, query_gemini_analysis

    print("=== Testing DeepSeek (via Zen) ===")
    try:
        r = await query_deepseek_vote(mock_data["summary"])
        print(f"  Result: {json.dumps(r, indent=4) if r else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n=== Testing GLM 5.2 (via NVIDIA) ===")
    try:
        r = await query_glm_analysis(mock_data["summary"])
        print(f"  Result: {json.dumps(r, indent=4) if r else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n=== Testing Gemini (via Google) ===")
    try:
        r = await query_gemini_analysis(mock_data["summary"])
        print(f"  Result: {json.dumps(r, indent=4) if r else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
