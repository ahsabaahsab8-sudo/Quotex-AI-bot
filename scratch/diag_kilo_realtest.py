"""
Real-world test: Poolside Laguna-S (DeepSeek slot) + Nemotron 3.5 Lightning (MiMo slot)
- Uses exact same TRADING_PROMPT_TEMPLATE from main.py
- Uses realistic 20-factor Quotex data
- Same max_tokens (2048) as DeepSeek/MiMo had
- Reports response time and whether JSON is valid
"""
import sys, time, json, asyncio, os
sys.path.insert(0, r"c:\Users\PC\Desktop\Quotex Signal")
os.chdir(r"c:\Users\PC\Desktop\Quotex Signal")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\PC\Desktop\Quotex Signal\.env")

from openai import OpenAI

KILO_KEY = os.getenv("KILO_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34")
KILO_BASE = "https://api.kilo.ai/api/gateway"
MAX_TOKENS = 2048  # same as AI_OUTPUT_MAX_TOKENS default

kilo_client = OpenAI(base_url=KILO_BASE, api_key=KILO_KEY, timeout=120.0)

# ── Realistic 20-factor Quotex test data ────────────────────────────────
MOCK_DATA = {
    "token": "EURUSD_OTC",
    "analysis_timeframe_seconds": 60,
    "analysis_timeframe_label": "1m",
    "ema_alignment": "BULLISH_ALIGNED",
    "ema_alignment_lti": "BULLISH_ALIGNED_LTI",
    "adx": 31.4,
    "adx_strength": "STRONG",
    "metrics_1m": {
        "trend": "UP",
        "macd_diff": 0.00042,
        "close": 1.08521,
        "rsi": 58.3,
        "volume": 1240
    },
    "metrics_5m": {"trend": "UP", "close": 1.08510},
    "metrics_15m": {"trend": "UP", "close": 1.08490},
    "support_resistance_break": {
        "support_50": 1.08400,
        "resistance_50": 1.08550,
        "retest_resistance": True,
        "retest_support": False
    },
    "rsi_directional": {"rsi_value": 58.3, "rsi_rising": True, "rsi_falling": False},
    "stochastic_strict": {
        "k": 65.2, "d": 58.1,
        "bullish_cross_strict": False,
        "bearish_cross_strict": False
    },
    "bollinger_squeeze": {
        "bb_squeeze": False,
        "bb_rsi_buy_confluence": False,
        "bb_rsi_sell_confluence": False
    },
    "volume_trend": {
        "volume_increasing": True,
        "volume_trend_bullish": True,
        "volume_trend_bearish": False
    },
    "candlestick_at_level": {
        "bullish_pinbar_at_support": True,
        "bearish_pinbar_at_resistance": False
    },
    "cci": 112.5,
    "mfi": {"mfi_value": 62.1, "mfi_bullish_divergence": False},
    "williams_r": -28.4,
    "latest_atr": 0.00085,
    "average_atr_20": 0.00071,
    "awesome_oscillator": {"ao_value": 0.00031, "ao_cross_up": True, "ao_cross_down": False},
    "pivot_points": {
        "pivot_break_up": True, "r1_break_up": False,
        "s1_cross_down": False
    },
    "ichimoku": {"ichimoku_bullish": True},
    "color_probabilities": {
        "next_green_percentage": 67.4,
        "next_red_percentage": 32.6
    },
    "session_filter": {"is_london_ny_overlap": True}
}

# Pull prompt template directly from main.py
SYSTEM_MSG = "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."

# Read TRADING_PROMPT_TEMPLATE from main.py dynamically
import importlib.util
print("Loading TRADING_PROMPT_TEMPLATE from main.py...", flush=True)
try:
    # Just read it via grep to avoid full import (avoids telegram bot starting)
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
    print(f"Prompt template loaded: {len(TRADING_PROMPT_TEMPLATE)} chars\n", flush=True)
except Exception as e:
    print(f"Could not load template: {e}, using fallback", flush=True)
    TRADING_PROMPT_TEMPLATE = "Analyze this trading data and output JSON with direction (BUY/SELL), confidence (50-95), reason.\n{data_json}"

data_json = json.dumps([MOCK_DATA], indent=2)
prompt = TRADING_PROMPT_TEMPLATE.replace("{data_json}", data_json)

def test_model(label, model_id):
    print(f"\n{'='*65}")
    print(f"Testing: {label}")
    print(f"Model  : {model_id}")
    print(f"Tokens : max_tokens={MAX_TOKENS}, temperature=0.2")
    print(f"{'='*65}", flush=True)

    t0 = time.time()
    try:
        resp = kilo_client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=MAX_TOKENS,
        )
        elapsed = time.time() - t0
        text = (resp.choices[0].message.content or "").strip()
        finish = resp.choices[0].finish_reason if resp.choices else "?"
        usage = resp.usage

        print(f"Response time : {elapsed:.2f}s")
        print(f"Finish reason : {finish}")
        print(f"Tokens used   : in={usage.prompt_tokens if usage else '?'} out={usage.completion_tokens if usage else '?'}")
        print(f"Raw output    : {text[:300]}{'...' if len(text)>300 else ''}")

        # Try parse JSON
        clean = text.replace("```json","").replace("```","").strip()
        parsed = json.loads(clean)
        direction = parsed.get("direction", "?")
        confidence = parsed.get("confidence", "?")
        print(f"\n✅ JSON VALID   | direction={direction} | confidence={confidence}%")
        return True, elapsed

    except json.JSONDecodeError as e:
        elapsed = time.time() - t0
        print(f"\n⚠️  JSON PARSE ERROR ({elapsed:.2f}s): {e}")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n❌ FAILED ({elapsed:.2f}s): {type(e).__name__}: {e}")
        return False, elapsed

print("=" * 65)
print("  KILO CODE — DeepSeek & MiMo Replacement Test")
print("  Using REAL Quotex 20-Factor data + TRADING_PROMPT_TEMPLATE")
print("=" * 65)

ok1, t1 = test_model("Poolside Laguna-S 2.1 [DeepSeek slot]", "poolside/laguna-s-2.1:free")
ok2, t2 = test_model("NVIDIA Nemotron 3.5 Lightning [MiMo slot]", "nvidia/nemotron-3.5-lightning:free")

print(f"\n\n{'='*65}")
print("FINAL SUMMARY")
print("="*65)
print(f"  Poolside Laguna-S 2.1   (DeepSeek slot) : {'✅ OK' if ok1 else '❌ FAIL'}  {t1:.2f}s")
print(f"  Nemotron 3.5 Lightning  (MiMo slot)     : {'✅ OK' if ok2 else '❌ FAIL'}  {t2:.2f}s")
print(f"\n  Target: both < 10s for real-time trading signals")
