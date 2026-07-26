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
    
    from pyquotex.network.login import Login
    Login.base_url = "market-qx.trade"
    Login.https_base_url = "https://market-qx.trade"
    
    from openai import OpenAI
    api_key = "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"
    nvidia_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )
    
    import main as main_module
    
    # Mock technical data for XAUUSD_otc
    mock_tech_data = {
        "summary": {
            "token": "XAUUSD_otc",
            "current_price": 4123.001,
            "latest_atr": 0.055,
            "average_atr_20": 0.057,
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
    
    prompt = f"""
You are an ELITE OTC QUOTEX TRADER and RISK MANAGER. Your job is to survive, not to gamble.

### MISSION
Analyze the following technical data and select the SINGLE BEST 1-MINUTE TRADE signal from the list. 
Your primary goal is CAPITAL PROTECTION. Your secondary goal is HIGH PROBABILITY.

### DATA INPUT
{json.dumps([mock_tech_data], indent=2)}

### THE 4 LAWS OF TRADING - ANALYZE IN THIS ORDER

**LAW 1: OTC TRAP FILTER - MOST IMPORTANT**
Check this first. If ANY of these are true, set "direction": "NO-TRADE" and confidence < 60:
1. Spike Trap (Adaptive): If the wicks of the last 3 candles are abnormally large compared to the asset's average candle body size (wick size > 2.5x of the average candle body size). This indicates broker manipulation.
2. News/Breakout Spike (Adaptive): The price moved abnormally fast in the last 1-2 candles relative to the average ATR (price change > 3x average ATR).
3. Flat Market: ATR is extremely low and volatility is frozen (no movement = no trade).

**LAW 2: MULTI-TIMEFRAME CONFLUENCE & PULLBACKS - 40 POINTS**
Score 0-40.
- Full Trend Alignment: 1m, 5m, and 15m trends align perfectly (all STRONG_UPTREND for Buy, or all STRONG_DOWNTREND for Sell) -> 40 points.
- Trend Pullbacks: 1m trend is UP, 5m trend is UP, but 15m is sideways/neutral, and price is touching the EMA-20 or middle Bollinger Band (retesting support) -> 35 points.
- Breakout Retests: Price broke a major resistance/support level and is holding above/below it -> 35 points.
- Penalty: 1m trend is directly opposite of 5m/15m with no pullback structure -> -20 points.

**LAW 3: LOCATION & MOMENTUM - 40 POINTS**
Score 0-40.
- Location: Price is near Support, S1/S2 Pivot for Buy, or Resistance, R1/R2 Pivot for Sell -> 25 points. (Middle of range = 0 points).
- Momentum: For BUY: RSI between 30 and 65 is best. For SELL: RSI between 35 and 70 is best. If RSI is overextended (>80 or <20) -> -10 points.

**LAW 4: CANDLE CONFIRMATION - 20 POINTS**
Score 0-20. Need 1 clear pattern at support/resistance.
- BUY: Hammer, Bullish Engulfing, Pin Bar at Support -> 20 points.
- SELL: Shooting Star, Bearish Engulfing at Resistance -> 20 points.
- No pattern -> max 5 points.

### DECISION RULE
1. Calculate Total Score = Law2 + Law3 + Law4. Max 100.
2. You are in "Decisive Trading Mode". If Total Score >= 60, choose "direction": "UP" or "DOWN" based on which side has the higher score, and set "confidence": Total Score.
3. If Total Score < 60: "direction": "NO-TRADE", "confidence": Total Score. Only choose NO-TRADE if the setup is genuinely flat or violates Law 1. If there is a slight edge, make the call!

### CHAIN OF THOUGHT MANDATE
To ensure maximum accuracy, you MUST perform step-by-step mathematical derivations. Fill out the "chain_of_thought_reasoning" fields. You must write out the calculations, the exact numbers, comparing body sizes, wick lengths, and distances to support/resistance levels. Make it extremely detailed.

### OUTPUT RULES - STRICT JSON ONLY
You MUST output only a valid JSON object. No extra text, intro, or explanations.
{{
  "token": "string, the selected asset name",
  "direction": "string, strictly 'UP', 'DOWN', or 'NO-TRADE'",
  "confidence": int (range 60 to 95),
  "chain_of_thought_reasoning": {{
    "step_1_otc_trap_derivation": "Perform and write out the exact calculations of wicks vs body size for the last 3 candles, and the price change vs average ATR to prove there is no broker spike trap.",
    "step_2_trend_confluence_derivation": "Analyze the EMA-20/50 and MACD alignment on 1m, 5m, and 15m timeframes to calculate exact trend strength.",
    "step_3_location_and_momentum_derivation": "Calculate the exact distance to pivot lines, Bollinger Bands, and support/resistance levels. Write out the RSI value and verify it is not overextended.",
    "step_4_candlestick_pattern_derivation": "Analyze the Open, High, Low, and Close values of the last 3 candles to confirm the exact candlestick pattern formation."
  }},
  "analysis": {{
    "otc_trap_check": "string, did it pass Law 1? Why?",
    "trend_alignment": "string, score out of 40 and reason",
    "support_resistance": "string, score out of 40 and reason", 
    "candlestick_patterns": "string, score out of 20 and reason"
  }},
  "reason": "string, detailed technical analysis reasoning explaining the final decision and why it is high-probability or why a NO-TRADE was issued"
}}
"""

    print("Sending direct prompt query to stepfun-ai/step-3.7-flash...")
    try:
        completion = nvidia_client.chat.completions.create(
            model="stepfun-ai/step-3.7-flash",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise trading assistant. Your task is to output ONLY a valid JSON object matching the requested schema. Do not write any conversational text, introductory thoughts, explanations, or summaries outside the JSON object. Start your output directly with '{' and end with '}'."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            top_p=0.7,
            max_tokens=2048,
            stream=False,
            response_format={"type": "json_object"}
        )
        print("Raw Response:")
        print(completion.choices[0].message.content)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
