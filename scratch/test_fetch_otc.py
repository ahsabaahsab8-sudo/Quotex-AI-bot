import os
import asyncio
import sys
from dotenv import load_dotenv
from pyquotex.stable_api import Quotex
from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

async def main():
    load_dotenv()
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    
    client = Quotex(
        email=email,
        password=password,
        lang="en",
        host="market-qx.trade",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    client.account_is_demo = 0
    
    ok, reason = await client.connect()
    if not ok:
        print(f"Failed to connect: {reason}")
        return
        
    try:
        # Try to fetch candles for EURUSD_otc
        token = "EURUSD_otc"
        print(f"Fetching candles for {token}...")
        candles = await client.get_historical_candles(token, 18000, 60)
        if candles:
            print(f"Successfully fetched {len(candles)} candles for {token}!")
            print(f"First candle: {candles[0]}")
            print(f"Last candle: {candles[-1]}")
        else:
            print(f"Failed or empty candles returned for {token}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
