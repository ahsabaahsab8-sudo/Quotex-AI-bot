import asyncio
import os
import sys
from dotenv import load_dotenv
from pyquotex.stable_api import Quotex

# Patch pyquotex mirror
from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

import logging
# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    
    if not email or not password:
        print("Error: QUOTEX_EMAIL or QUOTEX_PASSWORD is not set in .env file.")
        return
        
    print(f"Starting interactive login for {email}...")
    print("If this is a new IP (due to VPN), you will be prompted to enter the PIN code sent to your email.")
    
    client = Quotex(
        email=email,
        password=password,
        lang="en",
        host="market-qx.trade",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    client.account_is_demo = 0  # Connect using REAL to match activeAccount=live
    
    # Connect. If PIN is required, it will automatically prompt in the terminal.
    ok, reason = await client.connect()
    if ok:
        print("\nSUCCESS! Successfully authenticated and saved session to session.json.")
        is_connected = await client.check_connect()
        print(f"Session test connection: {is_connected}")
    else:
        print(f"\nFAILED to connect: {reason}")

if __name__ == "__main__":
    asyncio.run(main())
