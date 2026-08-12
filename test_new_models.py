"""Quick test of the 3 new AI models for Quotex signal."""
import os, sys, json, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

mock_data = {
    "summary": {
        "token": "EURUSD_otc",
        "current_price": 1.0850,
        "latest_atr": 0.0008,
        "average_atr_20": 0.0006,
        "metrics_1m": {
            "rsi": 55.0,
            "ema_20": 1.0845,
            "ema_50": 1.0830,
            "macd": 0.0002,
            "macd_signal": 0.0001,
            "macd_diff": 0.0001,
            "bollinger_upper": 1.0880,
            "bollinger_middle": 1.0850,
            "bollinger_lower": 1.0820,
            "support_50": 1.0820,
            "resistance_50": 1.0880,
            "trend": "UP"
        },
        "metrics_5m": {
            "rsi": 60.0,
            "ema_20": 1.0840,
            "ema_50": 1.0825,
            "macd": 0.0003,
            "macd_signal": 0.0002,
            "macd_diff": 0.0001,
            "current_price_5m": 1.0855,
            "trend": "UP"
        },
        "ema_alignment": "BULLISH_ALIGNED",
        "ema_alignment_lti": "BULLISH_ALIGNED_LTI",
        "adx": 28,
        "adx_strength": "strong",
        "rsi_directional": {"rsi_value": 55, "rsi_rising": True},
        "stochastic_strict": {"k": 45, "d": 40, "bullish_cross_strict": True},
        "bollinger_squeeze": {"bb_squeeze": False},
        "volume_trend": {"volume_increasing": True, "volume_trend_bullish": True},
        "candlestick_at_level": {"bullish_pinbar_at_support": False},
        "support_resistance_break": {"retest_resistance": True, "retest_support": False},
        "color_probabilities": {"next_green_percentage": 65, "next_red_percentage": 35},
        "session_filter": {"is_london_ny_overlap": True},
        "score": 8,
        "direction": "neutral"
    }
}


async def test_models():
    from main import query_gemini_flash_analysis, query_ling_vote, query_nemotron_vote, query_all_models

    print("=== Model 1: Gemini Flash (chart-capable) ===")
    t0 = asyncio.get_event_loop().time()
    try:
        r = await query_gemini_flash_analysis(mock_data["summary"])
        dt = asyncio.get_event_loop().time() - t0
        print(f"  Time: {dt:.1f}s | Result: {json.dumps(r, indent=2) if r else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n=== Model 2: Ling 3.0 Tiny (OpenRouter) ===")
    t0 = asyncio.get_event_loop().time()
    try:
        r = await query_ling_vote(mock_data["summary"])
        dt = asyncio.get_event_loop().time() - t0
        print(f"  Time: {dt:.1f}s | Result: {json.dumps(r, indent=2) if r else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n=== Model 3: Nemotron 3.5 Lightning 30B (NVIDIA, low tokens) ===")
    t0 = asyncio.get_event_loop().time()
    try:
        r = await query_nemotron_vote(mock_data["summary"])
        dt = asyncio.get_event_loop().time() - t0
        print(f"  Time: {dt:.1f}s | Result: {json.dumps(r, indent=2) if r else 'None'}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n=== Full Voting Pipeline (query_all_models) ===")
    t0 = asyncio.get_event_loop().time()
    try:
        result = await query_all_models(mock_data, pair_code="EURUSD_otc")
        dt = asyncio.get_event_loop().time() - t0
        print(f"  Total time: {dt:.1f}s")
        print(f"  Direction: {result.get('direction')}")
        print(f"  Confidence: {result.get('confidence')}%")
        print(f"  Reason: {result.get('reason', '')[:200]}")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_models())
