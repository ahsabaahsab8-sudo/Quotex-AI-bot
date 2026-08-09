"""Quick test: connect via updated quotex_adapter and fetch candles."""
import asyncio, logging
from quotex_adapter import get_quotex_connection, fetch_candles, close_quotex_connection

logging.basicConfig(level=logging.INFO)

async def main():
    print("[1] Connecting via quotex_adapter (with SSID injection)...")
    client = await get_quotex_connection()
    print("[OK] Connected!")

    print("\n[2] Fetching candles for EURUSD_otc...")
    candles = await fetch_candles(client, "EURUSD_otc", count=100, timeframe=60)
    if candles:
        print(f"[OK] Got {len(candles)} candles!")
        print(f"  First: {candles[0]['time']} O={candles[0]['open']} C={candles[0]['close']}")
        print(f"  Last:  {candles[-1]['time']} O={candles[-1]['open']} C={candles[-1]['close']}")
    else:
        print("[FAIL] No candles returned")

    print("\n[3] Fetching active pairs...")
    from quotex_adapter import get_active_pairs
    pairs = await get_active_pairs(client)
    otc = len(pairs.get("OTC", []))
    real = len(pairs.get("REAL", []))
    crypto = len(pairs.get("CRYPTO", []))
    print(f"[OK] OTC={otc}, REAL={real}, CRYPTO={crypto}")

    await close_quotex_connection()
    print("\n[DONE]")

if __name__ == "__main__":
    asyncio.run(main())
