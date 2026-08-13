"""Live test: all 3 vision models analyze the SAME chart image + data, timed."""
import os, sys, json, asyncio, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

import numpy as np


def build_mock_data():
    rng = np.random.default_rng(42)
    n = 120
    t0 = int(time.time()) - n * 60
    candles = []
    price = 1.0840
    for i in range(n):
        drift = 0.00008 if i > n // 2 else 0.00003
        o = price
        c = price + drift + rng.normal(0, 0.0003)
        h = max(o, c) + abs(rng.normal(0, 0.0002))
        l = min(o, c) - abs(rng.normal(0, 0.0002))
        candles.append({"time": t0 + i * 60, "open": round(o, 5), "high": round(h, 5),
                        "low": round(l, 5), "close": round(c, 5),
                        "volume": float(rng.integers(50, 400))})
        price = c
    summary = {
        "token": "EURUSD_otc",
        "analysis_timeframe_seconds": 60,
        "analysis_timeframe_label": "1m",
        "current_price": round(price, 5),
        "latest_atr": 0.0008,
        "average_atr_20": 0.0006,
        "metrics_1m": {
            "rsi": 62.0, "ema_20": round(price - 0.0002, 5), "ema_50": round(price - 0.0006, 5),
            "macd": 0.0002, "macd_signal": 0.0001, "macd_diff": 0.0001,
            "bollinger_upper": round(price + 0.002, 5), "bollinger_middle": round(price - 0.0002, 5),
            "bollinger_lower": round(price - 0.0024, 5),
            "support_50": round(price - 0.0015, 5), "resistance_50": round(price + 0.0015, 5),
            "trend": "UP",
        },
        "metrics_5m": {"rsi": 65.0, "trend": "UP", "current_price_5m": round(price + 0.0002, 5)},
        "metrics_15m": {"trend": "UP"},
        "ema_alignment": "BULLISH_ALIGNED",
        "ema_alignment_lti": "BULLISH_ALIGNED_LTI",
        "adx": 30, "adx_strength": "strong",
        "rsi_directional": {"rsi_value": 62, "rsi_rising": True},
        "stochastic_strict": {"k": 55, "d": 50, "bullish_cross_strict": True},
        "bollinger_squeeze": {"bb_squeeze": False},
        "volume_trend": {"volume_increasing": True, "volume_trend_bullish": True},
        "candlestick_at_level": {"bullish_pinbar_at_support": False},
        "support_resistance_break": {"retest_resistance": True, "retest_support": False},
        "cci": 80, "mfi": {"mfi_value": 62, "mfi_bullish_divergence": False},
        "williams_r": -45, "awesome_oscillator": {"ao_value": 0.0001, "ao_cross_up": True},
        "pivot_points": {"pivot": round(price - 0.0005, 5), "r1": round(price + 0.001, 5),
                         "s1": round(price - 0.002, 5)},
        "ichimoku": {"ichimoku_bullish": True},
        "color_probabilities": {"next_green_percentage": 67, "next_red_percentage": 33},
        "session_filter": {"is_london_ny_overlap": True},
        "score": 8, "direction": "neutral",
    }
    return {"summary": summary, "candles": candles}


async def timed(label, coro_factory):
    t0 = time.time()
    try:
        r = await coro_factory()
        dt = time.time() - t0
        return dt, r
    except Exception as e:
        return time.time() - t0, f"ERROR: {e}"


async def main():
    from main import (
        query_gemini_flash_analysis,
        query_nemotron_vote,
        query_llama_vote,
        query_all_models,
    )
    import chart_render

    tech_data = build_mock_data()
    chart_b64 = chart_render.render_chart_to_base64(
        tech_data["candles"], summary=tech_data["summary"], token="EURUSD_otc", timeframe=60
    )
    print(f"Chart image: {len(chart_b64)} b64 chars ({len(chart_b64) * 3 // 4 // 1024} KB PNG)\n")
    summary = tech_data["summary"]

    results = {}

    dt, r = await timed("Gemini", lambda: query_gemini_flash_analysis(summary, chart_b64=chart_b64))
    results["Gemini Flash 3.1 lite"] = (dt, r)
    print(f"[1/3] Gemini Flash            -> {dt:5.1f}s")

    dt, r = await timed("DiffusionGemma", lambda: query_nemotron_vote(summary, chart_b64=chart_b64))
    results["Diffusion Gemma 26B"] = (dt, r)
    print(f"[2/3] Diffusion Gemma 26B     -> {dt:5.1f}s")

    dt, r = await timed("LlamaVision", lambda: query_llama_vote(summary, chart_b64=chart_b64))
    results["Llama 3.2 11B Vision"] = (dt, r)
    print(f"[3/3] Llama 3.2 11B Vision    -> {dt:5.1f}s")

    print("\n=== FULL 3-MODEL VOTE (query_all_models) ===")
    t0 = time.time()
    vote = await query_all_models(tech_data, pair_code="EURUSD_otc", chart_b64=chart_b64)
    vote_time = time.time() - t0
    print(f"Total signal time: {vote_time:.1f}s")
    print(f"Direction: {vote.get('direction')} | Confidence: {vote.get('confidence')}%")
    print(f"Reason preview:\n{vote.get('reason', '')[:600]}")

    print("\n=== DETAILED PER-MODEL CHECK ===")
    for name, (dt, r) in results.items():
        print(f"\n--- {name} ({dt:.1f}s) ---")
        if isinstance(r, str):
            print(r)
            continue
        if not isinstance(r, dict):
            print("NO VALID RESULT")
            continue
        d = str(r.get("direction", "")).upper()
        conf = r.get("confidence")
        ca = r.get("chart_analysis")
        print(f"  direction={d} confidence={conf} martingale={r.get('martingale_recommendation')}")
        print(f"  chart_analysis={'YES (filled from image)' if ca else 'MISSING'}")
        if ca:
            print(f"    visual_trend={ca.get('visual_trend')} override={ca.get('visual_signal_override')} agreement={ca.get('telemetry_agreement')}")
        print(f"  reason={str(r.get('reason', ''))[:160]}")


if __name__ == "__main__":
    asyncio.run(main())
