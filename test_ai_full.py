import openai, json, sys
sys.path.insert(0, '.')
import main as bot_main

client = openai.OpenAI(
    base_url='https://opencode.ai/zen/v1',
    api_key='sk-5UVZdq3bAXTbOm55FiX8LqZIy4gKz2VFs5MVdU7QFfsqXQ8evXzVDU3Y0Tc5qY32',
    timeout=60
)

sample_tech = {
    "current_price": 1.13857,
    "latest_atr": 0.00038,
    "payout_percentage": 80,
    "metrics_1m": {"rsi": 55.15, "trend": "UPTREND", "ema_9": 1.1384, "ema_20": 1.13831, "ema_50": 1.13857},
    "ema_alignment": "MIXED",
    "adx": 14.1,
    "three_candle_rule": "NONE",
    "color_probabilities": {"color_sequence_last_10": ["R","G","G","G","R","R","G","G","G","R"], "last_3_sequence": "G-G-R", "historical_probability": {"next_green_percentage": 48.7, "next_red_percentage": 51.3}}
}

data_json = json.dumps([sample_tech], indent=2)
prompt = bot_main.TRADING_PROMPT_TEMPLATE.format(data_json=data_json)

print(f"Prompt length: {len(prompt)} chars")
print(f"Prompt tokens (approx): {len(prompt) // 4}")

try:
    r = client.chat.completions.create(
        model='deepseek-v4-flash-free',
        messages=[
            {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=2048
    )
    text = r.choices[0].message.content.strip()
    print(f"\nResponse length: {len(text)} chars")
    print(f"Response first 200: {text[:200]}")
    print(f"Response last 200: {text[-200:]}")
    if text:
        try:
            parsed = json.loads(text)
            print(f"\nJSON parsed OK. Direction: {parsed.get('direction')}")
        except json.JSONDecodeError as e:
            print(f"\nJSON decode error: {e}")
    else:
        print("\nEMPTY RESPONSE")
except Exception as e:
    print(f'\nFAILED: {str(e)[:500]}')
