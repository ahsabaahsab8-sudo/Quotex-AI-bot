import os
import sys
import asyncio
import json
import time
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    # Patch pyquotex mirror before importing main
    from pyquotex.network.login import Login
    Login.base_url = "market-qx.trade"
    Login.https_base_url = "https://market-qx.trade"
    
    import main as main_module
    
    # Increase the timeout on the main module's client to 90 seconds
    main_module.nvidia_client.timeout = 90.0
    
    # Mock technical data for EURUSD (Real Market, but disagreeing trends)
    mock_tech_data = {
        "summary": {
            "token": "EURUSD",
            "current_price": 1.08500,
            "latest_atr": 0.00045,
            "average_atr_20": 0.00040,
            "pivot_points_1h": {
                "pivot": 1.08450, "r1": 1.08600, "s1": 1.08300, "r2": 1.08700, "s2": 1.08200
            },
            "detected_candlestick_patterns": ["Bullish Engulfing"],
            "metrics_1m": {
                "rsi": 53.5, "trend": "STRONG_UPTREND", "ema_20": 1.08480, "ema_50": 1.08450,
                "macd": 0.00002, "macd_signal": 0.00001, "macd_diff": 0.00001,
                "bollinger_upper": 1.08550, "bollinger_middle": 1.08470, "bollinger_lower": 1.08390,
                "support_50": 1.08350, "resistance_50": 1.08580
            },
            "metrics_5m": {
                "rsi": 42.0, "trend": "STRONG_DOWNTREND", "macd": -0.00010, "macd_signal": -0.00008, "macd_diff": -0.00002, "current_price_5m": 1.08500
            },
            "metrics_15m": None
        },
        "candles": [
            {"open": 1.08450, "high": 1.08520, "low": 1.08430, "close": 1.08500},
            {"open": 1.08500, "high": 1.08530, "low": 1.08460, "close": 1.08480},
            {"open": 1.08480, "high": 1.08540, "low": 1.08470, "close": 1.08520}
        ]
    }
    
    print("Testing query_gemini_analysis_bulk with 90s timeout...")
    start_time = time.time()
    try:
        res = await main_module.query_gemini_analysis_bulk([mock_tech_data])
        end_time = time.time()
        print(f"Response received in {end_time - start_time:.2f} seconds:")
        print(json.dumps(res, indent=2))
    except Exception as e:
        end_time = time.time()
        print(f"Failed in {end_time - start_time:.2f} seconds with error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
