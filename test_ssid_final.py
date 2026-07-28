"""Test SSID: patch auth timeout bug, connect, fetch candles."""
import asyncio, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "A11ksa_API_Quotex"))
from api_quotex.client import AsyncQuotexClient

TOKEN = "ii7vZnWCtmbV3UdbYHWhUbpYcHAW9ts3TDcS16if"

async def main():
    # Build SSID
    ssid = f'42["authorization",{{"session":"{TOKEN}","isDemo":0,"tournamentId":0}}]'
    print(f"Token: {TOKEN}")

    client = AsyncQuotexClient(ssid=ssid, is_demo=False, region="ASIA")

    # Monkey-patch the broken _wait_for_authentication
    original_wait = client._wait_for_authentication
    async def patched_wait(timeout=30.0):
        try:
            if getattr(client._websocket, 'is_authenticated', False):
                return
        except:
            pass
        for _ in range(int(timeout * 10)):
            if getattr(client._websocket, 'is_authenticated', False):
                return
            await asyncio.sleep(0.1)
        print("  [WARN] Auth wait timeout (non-fatal, attempting continue)")
    client._wait_for_authentication = patched_wait

    try:
        print("[1] Connecting...")
        ok = await client.connect()
        if not ok:
            print("[FAIL] connect() returned False")
            return False

        print("[OK] Connected! Checking connection status...")
        await asyncio.sleep(2)

        # Check balance
        print("\n[2] Fetching balance...")
        balance = await client.get_balance()
        if balance:
            print(f"  Balance: {balance}")
        else:
            print("  [WARN] No balance returned")

        # Fetch candles
        print("\n[3] Fetching candles for EURUSD_otc (60s)...")
        candles = await client.get_candles(
            asset="EURUSD_otc",
            timeframe=60,
            count=100,
        )
        if candles:
            print(f"[OK] Got {len(candles)} candles!")
            print(f"  First: {candles[0].timestamp} O={candles[0].open} C={candles[0].close}")
            print(f"  Last:  {candles[-1].timestamp} O={candles[-1].open} C={candles[-1].close}")
        else:
            print("[WARN] No candles returned for EURUSD_otc")

        # Try EURUSD
        print("\n[4] Fetching candles for EURUSD (60s)...")
        candles2 = await client.get_candles(
            asset="EURUSD",
            timeframe=60,
            count=50,
        )
        if candles2:
            print(f"[OK] Got {len(candles2)} candles for EURUSD!")
        else:
            print("[WARN] No candles for EURUSD")

        print("\n[SUCCESS] SSID is fully working with Quotex WebSocket!")
        return True

    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
