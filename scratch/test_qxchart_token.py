import asyncio
import sys, os
sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal\QuotexChart")

from pyquotex.stable_api import Quotex

EMAIL = "slamismail8@gmail.com"
TOKEN = "IpNzCCqjHiuPIsZCIW8iXulgO3U9RMuL55BQBfeK"


async def main():
    c = Quotex(email=EMAIL, password="BaconBacon2019!", host="market-qx.trade", lang="en")
    c.set_session(user_agent=c.session_data.get("user_agent") or "Mozilla/5.0", cookies=None, ssid=TOKEN)
    print("token set, connecting...", flush=True)
    ok, reason = await c.connect()
    print("connect:", ok, reason, flush=True)
    if ok:
        bal = await c.get_balance()
        print("balance:", bal, flush=True)
        assets = await c.get_all_assets()
        print("assets loaded:", len(assets), flush=True)
        print("has EURUSD_otc:", "EURUSD_otc" in assets, flush=True)
        candles = await c.get_candles("EURUSD_otc", None, 3600, 60)
        if candles:
            print("candles:", len(candles), flush=True)
            print("first:", candles[0], flush=True)
            print("last:", candles[-1], flush=True)
        await c.close()
    else:
        print("FAILED - token likely invalid or host wrong", flush=True)

asyncio.run(main())
