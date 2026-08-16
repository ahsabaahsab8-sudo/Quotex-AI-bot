"""Quick test of the 3 LLM models + voting pipeline."""
import os, sys, json, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

mock_data = {
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


async def timed(label, coro):
    t0 = asyncio.get_event_loop().time()
    try:
        r = await asyncio.wait_for(coro, timeout=90)
        dt = asyncio.get_event_loop().time() - t0
        if r:
            print(f"{label}: {dt:.1f}s | direction={r.get('direction')} | conf={r.get('confidence')}")
        else:
            print(f"{label}: {dt:.1f}s | None")
        return r
    except asyncio.TimeoutError:
        print(f"{label}: TIMEOUT after 90s")
        return None
    except Exception as e:
        print(f"{label}: ERROR {type(e).__name__}: {str(e)[:150]}")
        return None


async def test_models():
    from main import (
        query_llm_nemotron_ultra,
        query_llm_nvidia_nemotron,
        query_llm_kilo_ling,
        query_all_llm_models,
    )

    await timed("Nemotron 3 Ultra (Zen)", query_llm_nemotron_ultra(mock_data))
    await timed("Llama 3.1 8B (NVIDIA)", query_llm_nvidia_nemotron(mock_data))
    await timed("Laguna-S 2.1 (Kilo)", query_llm_kilo_ling(mock_data))

    print("\n=== Full LLM Voting Pipeline ===")
    t0 = asyncio.get_event_loop().time()
    try:
        result = await asyncio.wait_for(
            query_all_llm_models({"summary": mock_data}, pair_code="EURUSD_otc"), timeout=120
        )
        dt = asyncio.get_event_loop().time() - t0
        print(f"Total time: {dt:.1f}s")
        print(f"Direction: {result.get('direction')}")
        print(f"Confidence: {result.get('confidence')}%")
        print(f"Reason: {result.get('reason', '')[:300]}")
    except Exception as e:
        print(f"Voting error: {e}")


if __name__ == "__main__":
    asyncio.run(test_models())