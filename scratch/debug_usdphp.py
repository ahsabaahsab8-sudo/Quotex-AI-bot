import os
import sys
import asyncio
import traceback

# Add current workspace directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from pyquotex.stable_api import Quotex

# Patch pyquotex mirror
from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

import main as main_module

async def main():
    load_dotenv()
    token = "USDPHP_otc"
    payout = 80
    
    print(f"Connecting to Quotex to debug {token}...")
    client = await main_module.get_quotex_connection()
    is_connected = await client.check_connect()
    if not is_connected:
        print("Failed to verify connection to Quotex.")
        return
        
    print("Connected successfully. Fetching indicators...")
    try:
        tech_data = await main_module.fetch_and_process_indicators(client, token, payout=payout)
        print(f"Fetch result: {tech_data}")
    except Exception as e:
        print("EXCEPTION OCCURRED:")
        traceback.print_exc()
        
    await client.close()

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
