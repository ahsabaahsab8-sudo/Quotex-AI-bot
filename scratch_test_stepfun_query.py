import os
import sys
import asyncio
import json
import logging

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Enable logger output to stdout
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def main():
    load_dotenv()
    
    from pyquotex.network.login import Login
    Login.base_url = "market-qx.trade"
    Login.https_base_url = "https://market-qx.trade"
    
    import main as main_module
    
    # Mock technical data for XAUUSD_otc
    mock_tech_data = {
        "summary": {
            "token": "XAUUSD_otc",
            "current_price": 4123.001,
            "latest_atr": 0.055,
            "average_atr_20": 0.057,
            "payout_percentage": 85,
            "nearest_round_numbers": {
                "price": 4123.001,
                "nearest_round_above": 4125.0,
                "distance_above_pips": 2.0,
                "nearest_round_below": 4120.0,
                "distance_below_pips": 3.0
            },
            "color_probabilities": {
                "color_sequence_last_10": ["R", "R", "G", "R", "R", "G", "R", "R", "R", "R"],
                "last_3_sequence": "R-R-R",
                "historical_probability": {
                    "next_green_percentage": 78.5,
                    "next_red_percentage": 21.5,
                    "occurrences_found": 14
                }
            },
            "pivot_points_1h": {
                "pivot": 4122.90, "r1": 4123.20, "s1": 4122.70, "r2": 4123.40, "s2": 4122.40
            },
            "detected_candlestick_patterns": [],
            "metrics_1m": {
                "rsi": 53.5, "trend": "STRONG_UPTREND", "ema_20": 4122.98, "ema_50": 4122.92,
                "macd": 0.02, "macd_signal": 0.027, "macd_diff": -0.007,
                "bollinger_upper": 4123.08, "bollinger_middle": 4122.99, "bollinger_lower": 4122.90,
                "support_50": 4122.75, "resistance_50": 4123.10
            },
            "metrics_5m": {
                "rsi": 67.6, "trend": "STRONG_UPTREND", "macd": 0.13, "macd_signal": 0.13, "macd_diff": 0.0, "current_price_5m": 4123.0
            },
            "metrics_15m": None
        },
        "candles": [
            {"open": 4122.99, "high": 4123.00, "low": 4122.99, "close": 4123.00}
            for _ in range(60)
        ]
    }
    
    print("Testing query_gemini_analysis_bulk directly with logging...")
    try:
        res = await main_module.query_gemini_analysis_bulk([mock_tech_data])
        print("Response received:")
        print(json.dumps(res, indent=2))
    except Exception as e:
        import traceback
        traceback.print_exc()

from dotenv import load_dotenv

if __name__ == "__main__":
    asyncio.run(main())
