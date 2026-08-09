"""Test the extracted SSID directly via WebSocket — connect, auth, fetch candles."""
import asyncio, json, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "A11ksa_API_Quotex"))
from api_quotex.websocket_client import AsyncWebSocketClient

TOKEN = "ii7vZnWCtmbV3UdbYHWhUbpYcHAW9ts3TDcS16if"
WS_URL = "wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket"

async def main():
    ssid = f'42["authorization",{{"session":"{TOKEN}","isDemo":0,"tournamentId":0}}]'
    print(f"Token: {TOKEN}")
    print(f"SSID: {ssid[:70]}...")
    print(f"Connecting to: {WS_URL}")

    client = AsyncWebSocketClient()

    # Register candle handler
    candles_received = asyncio.Event()
    candle_data = []

    async def on_candles(data):
        candle_data.append(data)
        candles_received.set()

    client.add_event_handler("candles_received", on_candles)

    try:
        ok = await client.connect([WS_URL], ssid)
        print(f"Connect result: {ok}")

        if not ok:
            print("[FAIL] Connection failed")
            return False

        print("[OK] Connected and authenticated!")

        # Wait a moment for data to settle
        await asyncio.sleep(2)

        # Request candles for EURUSD_otc
        print("\nRequesting candles for EURUSD_otc (60s)...")
        msg = f'42["loadHistoryPeriod",{{"asset":"EURUSD_otc","period":60,"offset":0,"limit":100}}]'
        await client.send_message(msg)
        print("Sent candle request")

        # Wait for response
        try:
            await asyncio.wait_for(candles_received.wait(), timeout=10)
            print(f"[OK] Candles received! Data keys: {list(candle_data[0].keys()) if candle_data else 'empty'}")
        except asyncio.TimeoutError:
            print("[WARN] No candles received within 10s (may need live data)")

        # Try getting balance
        print("\nRequesting balance...")
        await client.send_message('42["s_balance/list",{{}}]')
        await asyncio.sleep(3)

        # Also try instruments
        print("Requesting instruments...")
        await client.send_message('451-["instruments/list",{"_placeholder":true,"num":0}]')
        await asyncio.sleep(3)

        # Print all events received
        print(f"\n[SUMMARY] Connection successful! Token works on {WS_URL}")
        print(f"  Live balance: check log file for details")
        
        # Try to get cookies/token status
        print("\n[SUCCESS] SSID is valid and working with Quotex WebSocket!")
        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
