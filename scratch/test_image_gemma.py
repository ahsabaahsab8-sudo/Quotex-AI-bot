"""Test Diffusion Gemma with the captured chart image attached (multimodal)."""
import asyncio, base64, json, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
from dotenv import load_dotenv
load_dotenv()
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as m


async def main():
    with open('scratch/chart_EURUSD_otc.png', 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()

    tech_data = {"analysis_timeframe_seconds": 60, "analysis_timeframe_label": "1m",
                 "metrics_1m": {"trend": "bullish", "macd_diff": 0.5, "rsi": 55},
                 "ema_alignment": "BULLISH_ALIGNED", "adx": 28, "adx_strength": "strong"}

    print('>>> Calling Diffusion Gemma with chart image ...')
    r = await m.query_glm_analysis(tech_data, chart_b64=b64)
    print('>>> RESULT:', json.dumps(r, indent=2) if r else None)


asyncio.run(main())
