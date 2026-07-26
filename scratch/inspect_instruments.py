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
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    client.account_is_demo = 0
    
    ok, reason = await client.connect()
    if not ok:
        print(f"Failed to connect: {reason}")
        return
        
    try:
        instruments = await client.get_instruments()
        print(f"Total instruments returned: {len(instruments)}")
        
        # Look for real currencies and print their attributes
        real_currencies_all = []
        for inst in instruments:
            code = inst[1]
            display_name = inst[2]
            category = inst[3]
            is_open = inst[14]
            payout = inst[5]
            
            if category == "currency" and "_otc" not in code.lower():
                real_currencies_all.append({
                    "code": code,
                    "name": display_name,
                    "is_open": is_open,
                    "payout": payout
                })
                
        print(f"Total real currencies found: {len(real_currencies_all)}")
        for i, c in enumerate(real_currencies_all[:30], 1):
            print(f"{i}. {c['name']} ({c['code']}) - Open: {c['is_open']}, Payout: {c['payout']}%")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
