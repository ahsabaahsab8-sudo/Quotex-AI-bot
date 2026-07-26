import os
import sys
import json
import requests
from dotenv import load_dotenv

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv(dotenv_path=".env")

def main():
    token = "EURUSD_otc"
    # Extremely minimized telemetry data to save tokens and credit cost
    tech_data = {
        "summary": {
            "token": token,
            "current_price": 1.09450,
            "latest_atr": 0.00012,
            "average_atr_20": 0.00011,
            "payout_percentage": 88,
            "nearest_round_numbers": {
                "price": 1.09450,
                "nearest_round_above": 1.09500,
                "distance_above_pips": 5.0,
                "nearest_round_below": 1.09400,
                "distance_below_pips": 5.0
            },
            "color_probabilities": {
                "color_sequence_last_10": ["G", "G", "R", "G", "G", "R", "G", "G", "G", "R"],
                "last_3_sequence": "G-G-R",
                "historical_probability": {
                    "next_green_percentage": 68.4,
                    "next_red_percentage": 31.6,
                    "occurrences_found": 19
                }
            },
            "pivot_points_1h": {
                "pivot": 1.09400, "r1": 1.09480, "s1": 1.09350, "r2": 1.09520, "s2": 1.09300
            },
            "detected_candlestick_patterns": [],
            "metrics_1m": {
                "rsi": 58.5, "trend": "STRONG_UPTREND", "ema_20": 1.09440, "ema_50": 1.09410,
                "macd": 0.00005, "macd_signal": 0.00004, "macd_diff": 0.00001,
                "bollinger_upper": 1.09470, "bollinger_middle": 1.09440, "bollinger_lower": 1.09410,
                "support_50": 1.09415, "resistance_50": 1.09465
            },
            "metrics_5m": {
                "rsi": 62.0, "trend": "STRONG_UPTREND", "macd": 0.00012, "macd_signal": 0.00010, "macd_diff": 0.00002, "current_price_5m": 1.09450
            },
            "metrics_15m": None
        },
        "candles": [
            {"open": 1.09445, "high": 1.09455, "low": 1.09440, "close": 1.09450},
            {"open": 1.09440, "high": 1.09450, "low": 1.09435, "close": 1.09445},
            {"open": 1.09435, "high": 1.09445, "low": 1.09430, "close": 1.09440}
        ]
    }
        
    print(f"Constructing minimized prompt for {token}...")
    
    system_prompt = "You are a precise trading assistant. Output ONLY a valid JSON object matching the requested schema."
    
    summary_data = tech_data.get("summary", tech_data)
    user_prompt = f"""
Analyze the following technical telemetry data and choose BUY or SELL:
{json.dumps([summary_data], separators=(',', ':'))}

Rules:
1. Direction must be BUY or SELL. SKIP/NO-TRADE is forbidden.
2. Provide step-by-step mathematical reasoning.
3. Recommend martingale: M0/M1/M2.

Format strictly as:
{{
  "token": "EURUSD_otc",
  "direction": "BUY" or "SELL",
  "confidence": 50-95,
  "martingale_recommendation": "M0",
  "chain_of_thought_reasoning": {{
    "step_1_otc_trap_and_payout_derivation": "...",
    "step_2_trend_confluence_derivation": "...",
    "step_3_location_and_round_number_derivation": "...",
    "step_4_otc_cycle_and_color_probability_derivation": "..."
  }},
  "analysis": {{
    "otc_payout_and_trap_check": "...",
    "trend_alignment": "...",
    "support_resistance_round_numbers": "...", 
    "otc_cycles_color_probabilities": "..."
  }},
  "reason": "..."
}}
"""

    url = "https://direct.evolink.ai/v1/messages"
    payload = {
        "model": "claude-opus-5",
        "max_tokens": 1000,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }
    headers = {
        "Authorization": "sk-77qH7wGrnLSknBZvCqWXINBQybGTagX9RDTFC6ygtqZvoCGm",
        "Content-Type": "application/json"
    }

    print("Sending request to Evolink API for Claude Opus 5...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=90.0)
        print(f"HTTP Status Code: {response.status_code}")
        print("Response text:")
        print(response.text)
    except Exception as e:
        print(f"API Request Exception: {e}")

if __name__ == "__main__":
    main()
