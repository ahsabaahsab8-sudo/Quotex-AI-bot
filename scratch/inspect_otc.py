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
        instruments = await client.get_instruments()
        print(f"Total instruments returned: {len(instruments)}")
        
        otc_instruments = []
        for inst in instruments:
            code = inst[1]
            display_name = inst[2]
            category = inst[3]
            is_open = inst[14]
            payout = inst[5]
            
            if "_otc" in code.lower():
                otc_instruments.append({
                    "code": code,
                    "name": display_name,
                    "category": category,
                    "is_open": is_open,
                    "payout": payout,
                    "raw": inst
                })
                
        print(f"Total OTC instruments found: {len(otc_instruments)}")
        for i, c in enumerate(otc_instruments, 1):
            print(f"{i}. {c['name']} ({c['code']}) - Category: {c['category']}, Open: {c['is_open']}, Payout: {c['payout']}%")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
