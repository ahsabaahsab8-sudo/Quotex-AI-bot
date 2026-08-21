import os, time, json, sys, asyncio
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()
import main as m

mock = {
    "token": "EURUSD_otc",
    "analysis_timeframe_seconds": 60,
    "analysis_timeframe_label": "1m",
    "ema_alignment": "BULLISH_ALIGNED",
    "ema_alignment_lti": "BULLISH_ALIGNED_LTI",
    "adx": 31.4,
    "adx_strength": "STRONG",
    "metrics_1m": {"rsi": 58.3, "trend": "UP"},
    "metrics_5m": {"trend": "UP"},
    "metrics_15m": {"trend": "UP"},
    "support_resistance_break": {"retest_resistance": True, "retest_support": False},
    "rsi_directional": {"rsi_value": 58.3, "rsi_rising": True, "rsi_falling": False},
    "stochastic_strict": {"k": 65.2, "d": 58.1, "bullish_cross_strict": False, "bearish_cross_strict": False},
    "bollinger_squeeze": {"bb_squeeze": False, "bb_rsi_buy_confluence": False, "bb_rsi_sell_confluence": False},
    "volume_trend": {"volume_increasing": True, "volume_trend_bullish": True, "volume_trend_bearish": False},
    "candlestick_at_level": {"bullish_pinbar_at_support": True, "bearish_pinbar_at_resistance": False},
    "cci": 112.5,
    "mfi": {"mfi_value": 62.1, "mfi_bullish_divergence": False},
    "williams_r": -28.4,
    "latest_atr": 0.00085,
    "average_atr_20": 0.00071,
    "awesome_oscillator": {"ao_value": 0.00031, "ao_cross_up": True, "ao_cross_down": False},
    "pivot_points": {"pivot_break_up": True, "r1_break_up": False},
    "ichimoku": {"ichimoku_bullish": True},
    "color_probabilities": {"next_green_percentage": 67.4, "next_red_percentage": 32.6},
    "session_filter": {"is_london_ny_overlap": True},
}


async def run(label, client, model, max_tok):
    d = json.dumps([mock], indent=2)
    p = m.TRADING_PROMPT_TEMPLATE.format(data_json=d)
    t0 = time.time()
    try:
        c = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with { and end with }."},
                {"role": "user", "content": p},
            ],
            temperature=0.2,
            max_tokens=max_tok,
        )
        content = c.choices[0].message.content or ""
        parsed = m._parse_model_output(content)
        pd = parsed.get("direction") if parsed else None
        print(label, "[" + str(max_tok) + " tok]", round(time.time() - t0, 1), "s | parsed_dir=", pd,
              "| finish=", c.choices[0].finish_reason, "| len=", len(content))
    except Exception as e:
        print(label, "[" + str(max_tok) + " tok] ERR", type(e).__name__, str(e)[:200], round(time.time() - t0, 1), "s")


async def t():
    await run("NVIDIA Llama 3.1 8B", m.nvidia_llm_client, m.LLM_NVIDIA_MODEL, m.LLM_MAX_TOKENS)


asyncio.run(t())