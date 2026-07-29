"""Test pyquotex connection using the Kameleo-extracted token."""
import os, json, asyncio, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_pyquotex")

TOKEN = "GNOCRP6Wqzh15lOzF3fU8RyQnnBIT5FjGSjbAdsd"
EMAIL = "slamismail8@gmail.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"

def save_session(email, token):
    import os, json
    session_file = os.path.join(os.path.dirname(__file__), "session.json")
    data = {}
    if os.path.exists(session_file):
        with open(session_file) as f:
            data = json.load(f)
    data[email] = {
        "cookies": f"ssid={token}",
        "token": token,
        "user_agent": USER_AGENT,
    }
    with open(session_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved token to session.json")

async def main():
    # Save token first
    save_session(EMAIL, TOKEN)

    from pyquotex.stable_api import Quotex

    client = Quotex(
        email=EMAIL,
        password="not-needed",
        host="market-quotex.pro",
        lang="en",
        wss_url_override="wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket",
    )
    client.set_account_mode("REAL")
    client.set_session(
        user_agent=USER_AGENT,
        cookies=f"ssid={TOKEN}",
        ssid=TOKEN,
    )

    print("Connecting to pyquotex with token...")
    ok, msg = await client.connect()
    if not ok:
        print(f"Connection failed: {msg}")
        return

    print(f"Connected! Message: {msg}")

    # Wait for instruments
    print("Waiting for instruments...")
    try:
        await client.api.event_registry.wait_event("instruments_ready", timeout=30)
        print("Instruments ready!")
    except Exception as e:
        print(f"Instruments timeout: {e}")

    # Check balance
    print("Fetching balance...")
    balance = await client.get_balance()
    print(f"Balance: {balance}")

    # Fetch candles
    print("Fetching candles for EURUSD_otc...")
    candles = await client.get_historical_candles(
        asset="EURUSD_otc",
        amount_of_seconds=3600,
        period=60,
        timeout=30,
        max_workers=3,
    )
    if candles:
        print(f"Got {len(candles)} candles")
        print(f"First: {candles[0]}")
        print(f"Last: {candles[-1]}")
    else:
        print("No candles returned")

    # Get instruments
    print("Fetching instruments...")
    instruments = await client.get_instruments()
    if instruments:
        print(f"Got {len(instruments) if isinstance(instruments, list) else 'dict'} instruments")
    else:
        print("No instruments")

    await client.close()
    print("Done")

asyncio.run(main())
