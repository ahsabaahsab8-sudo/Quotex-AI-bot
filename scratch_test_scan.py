import asyncio
from dotenv import load_dotenv
import logging

# Patch pyquotex mirror
from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

from main import run_market_scan

logging.basicConfig(level=logging.INFO)

async def test():
    load_dotenv()
    print("Starting market scan test...")
    try:
        signal = await run_market_scan()
        print("\n=== SCAN RESULT ===")
        import json
        print(json.dumps(signal, indent=2))
    except Exception as e:
        print(f"Error during scan: {e}")

if __name__ == "__main__":
    asyncio.run(test())
