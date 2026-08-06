"""Integration: capture chart + query_all_models with chart_b64."""
import asyncio, base64, json, os, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chart_capture, main as m


async def main():
    pair = sys.argv[1] if len(sys.argv) > 1 else "EURUSD_otc"
    print('>>> Capturing chart ...')
    b64 = await chart_capture.capture_chart_image(pair, timeframe_seconds=60, timeout=60.0)
    print('>>> b64 len:', len(b64) if b64 else None)

    tech_data = {"summary": {"analysis_timeframe_seconds": 60, "analysis_timeframe_label": "1m",
                 "metrics_1m": {"trend": "bullish", "macd_diff": 0.5, "rsi": 55},
                 "ema_alignment": "BULLISH_ALIGNED", "adx": 28, "adx_strength": "strong"}}

    print('>>> Running query_all_models ...')
    r = await m.query_all_models(tech_data, pair_code=pair, chart_b64=b64)
    print('>>> VOTE RESULT:', json.dumps(r, indent=2) if r else None)


asyncio.run(main())
