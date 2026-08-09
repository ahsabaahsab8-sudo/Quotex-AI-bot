"""Test pyquotex direct API login (no browser needed)."""

import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")


async def main():
    from pyquotex.stable_api import Quotex

    client = Quotex(
        email=EMAIL,
        password=PASSWORD,
        host='market-quotex.pro',
        lang='en',
        wss_url_override='wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket',
    )
    client.set_account_mode("REAL")

    print("Attempting direct API login (email/password)...")
    ok, msg = await client.connect()
    print(f"Result: ok={ok}, msg={msg}")

    if ok:
        print("SUCCESS! Direct API login works!")
        balance = await client.get_balance()
        print(f"Balance: {balance}")

        instruments = await client.get_instruments()
        if instruments:
            print(f"Instruments count: {len(instruments) if isinstance(instruments, list) else 'dict'}")

        await client.close()
    else:
        print("Direct login failed. Need browser-based token extraction.")


asyncio.run(main())
