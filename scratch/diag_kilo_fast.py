"""
Test smaller/faster free Kilo models with the REAL 20-factor Quotex prompt.
Candidates: laguna-xs (smaller Poolside), ling-3.0-tiny, liquid/lfm-2.5-2.6b
"""
import sys, time, json, os
sys.path.insert(0, r"c:\Users\PC\Desktop\Quotex Signal")
os.chdir(r"c:\Users\PC\Desktop\Quotex Signal")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\PC\Desktop\Quotex Signal\.env")
from openai import OpenAI

KILO_KEY  = os.getenv("KILO_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34")
KILO_BASE = "https://api.kilo.ai/api/gateway"
MAX_TOKENS = 2048

client = OpenAI(base_url=KILO_BASE, api_key=KILO_KEY, timeout=120.0)

MOCK_DATA = {
    "token": "EURUSD_OTC", "analysis_timeframe_seconds": 60, "analysis_timeframe_label": "1m",
    "ema_alignment": "BULLISH_ALIGNED", "ema_alignment_lti": "BULLISH_ALIGNED_LTI",
    "adx": 31.4, "adx_strength": "STRONG",
    "metrics_1m": {"trend": "UP", "macd_diff": 0.00042, "close": 1.08521, "rsi": 58.3, "volume": 1240},
    "metrics_5m": {"trend": "UP", "close": 1.08510},
    "metrics_15m": {"trend": "UP", "close": 1.08490},
    "support_resistance_break": {"support_50": 1.084, "resistance_50": 1.0855, "retest_resistance": True, "retest_support": False},
    "rsi_directional": {"rsi_value": 58.3, "rsi_rising": True, "rsi_falling": False},
    "stochastic_strict": {"k": 65.2, "d": 58.1, "bullish_cross_strict": False, "bearish_cross_strict": False},
    "bollinger_squeeze": {"bb_squeeze": False, "bb_rsi_buy_confluence": False, "bb_rsi_sell_confluence": False},
    "volume_trend": {"volume_increasing": True, "volume_trend_bullish": True, "volume_trend_bearish": False},
    "candlestick_at_level": {"bullish_pinbar_at_support": True, "bearish_pinbar_at_resistance": False},
    "cci": 112.5, "mfi": {"mfi_value": 62.1, "mfi_bullish_divergence": False},
    "williams_r": -28.4, "latest_atr": 0.00085, "average_atr_20": 0.00071,
    "awesome_oscillator": {"ao_value": 0.00031, "ao_cross_up": True, "ao_cross_down": False},
    "pivot_points": {"pivot_break_up": True, "r1_break_up": False, "s1_cross_down": False},
    "ichimoku": {"ichimoku_bullish": True},
    "color_probabilities": {"next_green_percentage": 67.4, "next_red_percentage": 32.6},
    "session_filter": {"is_london_ny_overlap": True}
}

# Load real template from main.py
template_lines = []
in_template = False
with open(r"c:\Users\PC\Desktop\Quotex Signal\main.py", encoding="utf-8") as f:
    for line in f:
        if 'TRADING_PROMPT_TEMPLATE = """' in line:
            in_template = True
            template_lines.append(line.split('TRADING_PROMPT_TEMPLATE = """', 1)[1])
            continue
        if in_template:
            if line.strip() == '"""':
                break
            template_lines.append(line)
TRADING_PROMPT_TEMPLATE = "".join(template_lines)
prompt = TRADING_PROMPT_TEMPLATE.replace("{data_json}", json.dumps([MOCK_DATA], indent=2))
print(f"Prompt size: {len(prompt)} chars | ~{len(prompt)//4} tokens\n")

SYSTEM_MSG = "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."

CANDIDATES = [
    ("poolside/laguna-xs-2.1:free",   "Poolside Laguna-XS 2.1 [smaller/faster]"),
    ("inclusionai/ling-3.0-tiny:free", "Ling 3.0 Tiny"),
    ("liquid/lfm-2.5-2.6b:free",      "Liquid LFM 2.5 2.6B [ultra small]"),
]

results = []
for model_id, label in CANDIDATES:
    print(f"\n{'='*65}")
    print(f"{label}")
    print(f"Model: {model_id}  | max_tokens={MAX_TOKENS} temp=0.2")
    print("="*65, flush=True)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.2,
            max_tokens=MAX_TOKENS,
        )
        elapsed = time.time() - t0
        text = (resp.choices[0].message.content or "").strip()
        finish = resp.choices[0].finish_reason if resp.choices else "?"
        usage  = resp.usage

        print(f"Time  : {elapsed:.2f}s")
        print(f"Finish: {finish}")
        print(f"Tokens: in={usage.prompt_tokens if usage else '?'} out={usage.completion_tokens if usage else '?'}")
        print(f"Output: {text[:250]}{'...' if len(text)>250 else ''}")

        clean = text.replace("```json","").replace("```","").strip()
        parsed = json.loads(clean)
        direction  = parsed.get("direction","?")
        confidence = parsed.get("confidence","?")
        print(f"\n  JSON VALID | direction={direction} | confidence={confidence}%")
        results.append((elapsed, model_id, label, "OK", direction, confidence))
    except json.JSONDecodeError as je:
        elapsed = time.time() - t0
        print(f"\n  JSON PARSE ERROR ({elapsed:.2f}s): {je}")
        results.append((elapsed, model_id, label, "JSON_ERR", "-", "-"))
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n  FAILED ({elapsed:.2f}s): {type(e).__name__}: {e}")
        results.append((elapsed, model_id, label, "FAIL", "-", "-"))

print(f"\n\n{'='*65}")
print("FINAL SUMMARY (sorted by speed)")
print("="*65)
results.sort()
for elapsed, model_id, label, status, direction, conf in results:
    icon = "OK " if status == "OK" else "ERR"
    print(f"  {icon}  {elapsed:6.1f}s  {model_id:<40}  dir={direction} conf={conf}%")
print(f"\nTarget: < 10s for real-time signal quality")
