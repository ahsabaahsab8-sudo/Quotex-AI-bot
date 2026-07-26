import time, json, asyncio
from openai import OpenAI

client = OpenAI(
    base_url="https://opencode.ai/zen/v1",
    api_key="sk-5UVZdq3bAXTbOm55FiX8LqZIy4gKz2VFs5MVdU7QFfsqXQ8evXzVDU3Y0Tc5qY32",
    timeout=120.0
)

async def test():
    test_data = {
        "ema_alignment": "BULLISH_ALIGNED",
        "adx": 28, "adx_strength": "STRONG",
        "metrics_1m": {"macd_diff": 0.00015, "rsi": 62},
        "color_probabilities": {"historical_probability": {"next_green_percentage": 68, "next_red_percentage": 32}},
        "latest_atr": 0.0012, "average_atr_20": 0.0010,
        "support_resistance_break": {"retest_resistance": True, "retest_support": False}
    }
    data_json = json.dumps([test_data], indent=2)
    prompt = """You are a GATE GUARD screener for Quotex OTC trading signals.
### DATA INPUT
%s

### TIER 1 FACTORS TO CHECK
1. EMA Alignment: BULLISH_ALIGNED or BEARISH_ALIGNED? MIXED = weak.
2. ADX Strength: > 25 = trend strong. < 20 = range-bound, skip.
3. MACD Momentum: macd_diff positive or negative?
4. Support/Resistance Break: breakout + retest detected?

### OUTPUT - STRICT JSON ONLY
{"decision": "PASS or SKIP", "directional_bias": "BUY or SELL or NEUTRAL", "reason": "brief reason"}
""" % data_json

    start = time.time()
    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="deepseek-v4-flash-free",
            messages=[
                {"role": "system", "content": "You are a gate guard screener. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1, max_tokens=1024
        )
        content = completion.choices[0].message.content
        print(f"Time: {time.time()-start:.1f}s")
        print(f"Content: |{content}|")
        if content:
            cleaned = content.strip().replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)
            print(f"Parsed: {parsed}")
            return True
        print("EMPTY response")
        return False
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False

result = asyncio.run(test())
print(f"Result: {result}")
