import os
import asyncio
import sys
from dotenv import load_dotenv
from pyquotex.stable_api import Quotex

# Patch pyquotex mirror
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
    
    print("Connecting to Quotex...")
    ok, reason = await client.connect()
    if not ok:
        print(f"Failed to connect: {reason}")
        return
        
    print("Connected successfully. Fetching active instruments...")
    try:
        instruments = await client.get_instruments()
        
        otc_currencies = []
        real_currencies = []
        crypto_commodities = []
        
        for inst in instruments:
            code = inst[1]
            display_name = inst[2]
            category = inst[3]
            is_open = inst[14]
            payout = inst[5]
            
            if not is_open or payout < 70:
                continue
                
            entry = {"code": code, "name": display_name, "payout": payout}
            
            if category == "currency":
                if "_otc" in code.lower():
                    otc_currencies.append(entry)
                else:
                    real_currencies.append(entry)
            elif category in ["crypto", "cryptocurrency", "commodity", "index"]:
                crypto_commodities.append(entry)
                
        # Sort each list by payout descending
        otc_currencies.sort(key=lambda x: x["payout"], reverse=True)
        real_currencies.sort(key=lambda x: x["payout"], reverse=True)
        crypto_commodities.sort(key=lambda x: x["payout"], reverse=True)
        
        print("\n=== OTC CURRENCIES ===")
        for i, item in enumerate(otc_currencies, 1):
            print(f"{i}. {item['name']} ({item['code']}) - Payout: {item['payout']}%")
            
        print("\n=== REAL MARKET CURRENCIES ===")
        for i, item in enumerate(real_currencies, 1):
            print(f"{i}. {item['name']} ({item['code']}) - Payout: {item['payout']}%")
            
        print("\n=== CRYPTO & COMMODITIES ===")
        for i, item in enumerate(crypto_commodities, 1):
            print(f"{i}. {item['name']} ({item['code']}) - Payout: {item['payout']}%")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
