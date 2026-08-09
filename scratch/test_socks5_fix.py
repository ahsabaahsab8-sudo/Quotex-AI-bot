"""Verify the Quotex connection works through the SOCKS5 proxy."""
import asyncio, logging
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

async def main():
    from quotex_adapter import get_quotex_connection, fetch_candles, close_quotex_connection
    print("[1] Connecting via quotex_adapter (SOCKS5 proxy)...")
    client = await get_quotex_connection()
    print("[OK] Connected!")

    print("\n[2] Fetching candles for EURUSD_otc...")
    candles = await fetch_candles(client, "EURUSD_otc", count=20, timeframe=60)
    if candles:
        print(f"[OK] Got {len(candles)} candles! Last close={candles[-1]['close']}")
    else:
        print("[FAIL] No candles returned")

    await close_quotex_connection()
    print("\n[DONE]")

if __name__ == "__main__":
    asyncio.run(main())
