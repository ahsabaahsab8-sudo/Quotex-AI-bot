"""Test full pipeline: connect, fetch indicators, run AI models."""
import asyncio, json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()
os.environ["QUOTEX_EMAIL"] = "slamismail8@gmail.com"

from main import get_quotex_connection, fetch_and_process_indicators, query_all_models
from quotex_adapter import close_quotex_connection

async def main():
    print("[1] Connecting to Quotex...")
    client = await get_quotex_connection()
    print("[OK] Connected\n")

    print("[2] Fetching indicators for EURUSD_otc...")
    tech_data = await fetch_and_process_indicators(client, "EURUSD_otc")
    if tech_data is None:
        print("[FAIL] No tech data")
        return
    if tech_data == "LOW_VOLATILITY":
        print("[SKIP] Low volatility")
        return

    print("[OK] Got tech data")
    summary = tech_data.get("summary", tech_data)
    print(f"  Summary keys: {list(summary.keys())}")
    print(f"  Score: {summary.get('score', 'N/A')}")
    print(f"  Direction: {summary.get('direction', 'N/A')}")

    print("\n[3] Running AI pipeline (all 3 models)...")
    result = await query_all_models(summary, pair_code="EURUSD_otc")
    print(f"\n[RESULT] {json.dumps(result, indent=2, default=str)}")

    await close_quotex_connection()
    print("\n[DONE]")

if __name__ == "__main__":
    asyncio.run(main())
