"""
Test NVIDIA Nemotron 3.5 Lightning 30B via NVIDIA API
- Non-streaming (matches main.py pattern)
- Low tokens + thinking disabled for max speed
- Real 20-factor Quotex prompt
"""
import sys, time, json, os
sys.path.insert(0, r"c:\Users\PC\Desktop\Quotex Signal")

from openai import OpenAI

NVIDIA_KEY  = "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"
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
MODEL       = "nvidia/nemotron-3.5-lightning-30b-a3b"

client = OpenAI(base_url=NVIDIA_BASE, api_key=NVIDIA_KEY, timeout=120.0)

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
print(f"Prompt: {len(prompt)} chars\n")

SYSTEM_MSG = "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."

def run_test(label, max_tokens, enable_thinking, reasoning_budget=None):
    print(f"\n{'='*65}")
    print(f"TEST: {label}")
    print(f"  model={MODEL}")
    print(f"  max_tokens={max_tokens}  enable_thinking={enable_thinking}  reasoning_budget={reasoning_budget}")
    print("="*65, flush=True)

    extra = {}
    if reasoning_budget is not None:
        extra = {"chat_template_kwargs": {"enable_thinking": enable_thinking}, "reasoning_budget": reasoning_budget}
    else:
        extra = {"chat_template_kwargs": {"enable_thinking": enable_thinking}}

    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.2,
            top_p=0.95,
            max_tokens=max_tokens,
            extra_body=extra,
            stream=False
        )
        elapsed = time.time() - t0
        text    = (resp.choices[0].message.content or "").strip()
        finish  = resp.choices[0].finish_reason if resp.choices else "?"
        usage   = resp.usage
        thinking = getattr(resp.choices[0].message, "reasoning_content", None) if resp.choices else None

        print(f"  Time  : {elapsed:.2f}s")
        print(f"  Finish: {finish}")
        print(f"  Tokens: in={usage.prompt_tokens if usage else '?'} out={usage.completion_tokens if usage else '?'}")
        if thinking:
            print(f"  Think : {str(thinking)[:100]}...")
        print(f"  Output: {text[:300]}{'...' if len(text)>300 else ''}")

        clean  = text.replace("```json","").replace("```","").strip()
        parsed = json.loads(clean)
        print(f"\n  JSON VALID | direction={parsed.get('direction','?')} | confidence={parsed.get('confidence','?')}%")
        return True, elapsed, parsed.get("direction","?"), parsed.get("confidence","?")

    except json.JSONDecodeError as je:
        elapsed = time.time() - t0
        print(f"\n  JSON PARSE ERROR ({elapsed:.2f}s): {je}")
        print(f"  Raw: {text[:200] if 'text' in dir() else 'N/A'}")
        return False, elapsed, "-", "-"
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n  FAILED ({elapsed:.2f}s): {type(e).__name__}: {str(e)[:120]}")
        return False, elapsed, "-", "-"

print("=" * 65)
print("  NVIDIA Nemotron 3.5 Lightning 30B — Speed Test")
print("  Goal: find lowest token setting that still returns valid JSON fast")
print("=" * 65)

results = []

# Test 1: No thinking, low tokens (fastest possible)
ok, t, d, c = run_test("NO thinking, max_tokens=512", max_tokens=512, enable_thinking=False)
results.append((t, "512 tok, no think", ok, d, c))

# Test 2: No thinking, 1024 tokens
ok, t, d, c = run_test("NO thinking, max_tokens=1024", max_tokens=1024, enable_thinking=False)
results.append((t, "1024 tok, no think", ok, d, c))

# Test 3: Thinking with small budget 256, output tokens 512
ok, t, d, c = run_test("Thinking budget=256, max_tokens=512", max_tokens=512, enable_thinking=True, reasoning_budget=256)
results.append((t, "think256 + 512 tok", ok, d, c))

print(f"\n\n{'='*65}")
print("FINAL COMPARISON")
print("="*65)
for t, label, ok, direction, conf in sorted(results):
    icon = "OK " if ok else "ERR"
    print(f"  {icon}  {t:6.2f}s  {label:<30}  dir={direction} conf={conf}%")
print(f"\nTarget: < 10s")
