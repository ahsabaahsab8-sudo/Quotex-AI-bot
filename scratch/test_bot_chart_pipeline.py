"""End-to-end: replicate quotex_bot.py chart pipeline for a user-selected pair+timeframe."""
import asyncio, base64, json, os, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import main as bot_main
from quotex_adapter import close_quotex_connection


async def main():
    pair = sys.argv[1] if len(sys.argv) > 1 else "EURUSD_otc"
    tf = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    print(f">>> Pair: {pair} | Timeframe: {tf}s", flush=True)

    print(">>> Step 1/4: Connecting to Quotex (bot adapter)...", flush=True)
    client = await bot_main.get_quotex_connection()
    print(">>> connected:", client is not None, flush=True)

    print(f">>> Step 2/4: Fetching candles + indicators for {pair} @ {tf}s...", flush=True)
    tech_data = await bot_main.fetch_and_process_indicators(client, pair, timeframe=tf)
    if tech_data is None:
        print(">>> FAIL: no tech_data", flush=True)
        return
    candles = tech_data.get("candles")
    print(f">>> candles fetched: {len(candles) if candles else 0}", flush=True)
    if not candles:
        print(">>> FAIL: no candles", flush=True)
        return

    print(">>> Step 3/4: Rendering chart PNG (this is what gets attached)...", flush=True)
    import chart_render
    chart_b64 = chart_render.render_chart_to_base64(
        candles, summary=tech_data.get("summary"), token=pair, timeframe=tf,
    )
    print(f">>> chart_b64 len: {len(chart_b64) if chart_b64 else 0}", flush=True)
    if chart_b64:
        out = os.path.join(PROJECT_ROOT, "scratch", "bot_chart_live.png")
        with open(out, "wb") as f:
            f.write(base64.b64decode(chart_b64))
        print(f">>> saved {out}", flush=True)
    else:
        print(">>> FAIL: chart render returned None", flush=True)

    print(">>> Step 4/4: Running 3-model vote WITH chart image attached...", flush=True)
    ai_result = await bot_main.query_all_models(
        tech_data["summary"], pair_code=pair, chart_b64=chart_b64,
    )
    print(">>> VOTE RESULT:", json.dumps(ai_result, indent=2) if ai_result else None, flush=True)

    await close_quotex_connection()


asyncio.run(main())
