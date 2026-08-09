"""Test the extracted SSID: connect to Quotex WebSocket and fetch candles."""
import asyncio, os, sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "A11ksa_API_Quotex"))
from api_quotex.client import AsyncQuotexClient

async def test_ssid():
    # Load token from session.json
    session_file = Path(__file__).parent / "session.json"
    if not session_file.exists():
        print("[FAIL] session.json not found")
        return False

    with open(session_file) as f:
        data = json.load(f)
    first_key = next(iter(data), None)
    if not first_key:
        print("[FAIL] session.json is empty")
        return False

    token = data[first_key].get("token")
    if not token:
        print("[FAIL] No token in session.json")
        return False

    print(f"Token: {token}")
    print(f"Email: {first_key}")

    # Build the full SSID frame as the API expects it
    ssid = f'42["authorization",{{"session":"{token}","isDemo":0,"tournamentId":0}}]'
    print(f"SSID: {ssid[:70]}...")

    # Connect using the A11ksa API client
    print("\n[1] Connecting to Quotex WebSocket...")
    client = AsyncQuotexClient(ssid=ssid, is_demo=False, region="ASIA")

    try:
        ok = await client.connect()
        if not ok:
            print("[FAIL] Could not connect to Quotex")
            return False

        print("[OK] Connected and authenticated!")

        # Try fetching candles
        print("\n[2] Fetching candles for EURUSD_otc (60s timeframe, 100 candles)...")
        candles = await client.get_candles(
            asset="EURUSD_otc",
            timeframe=60,
            count=100,
        )

        if not candles:
            print("[FAIL] No candles returned")
            return False

        print(f"[OK] Got {len(candles)} candles!")
        print(f"  First: {candles[0].timestamp} O={candles[0].open} H={candles[0].high} "
              f"L={candles[0].low} C={candles[0].close}")
        print(f"  Last:  {candles[-1].timestamp} O={candles[-1].open} H={candles[-1].high} "
              f"L={candles[-1].low} C={candles[-1].close}")

        # Try another pair
        print("\n[3] Fetching candles for EURUSD (60s timeframe, 50 candles)...")
        candles2 = await client.get_candles(
            asset="EURUSD",
            timeframe=60,
            count=50,
        )
        if candles2:
            print(f"[OK] Got {len(candles2)} candles for EURUSD!")
        else:
            print("[WARN] No candles for EURUSD")

        print("\n[SUCCESS] SSID is valid and working!")
        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.close()
        print("Connection closed.")

if __name__ == "__main__":
    success = asyncio.run(test_ssid())
    sys.exit(0 if success else 1)
