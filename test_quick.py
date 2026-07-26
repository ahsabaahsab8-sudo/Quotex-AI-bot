import asyncio, os, logging
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

from pyquotex.stable_api import Quotex

async def test():
    c = Quotex(
        email=os.getenv("QUOTEX_EMAIL"),
        password=os.getenv("QUOTEX_PASSWORD"),
        lang="en", host="market-qx.trade",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    c.account_is_demo = 0
    t = c.session_data.get("token", "")[:30]
    print(f"Token: {t}...")
    ok, r = await c.connect()
    print(f"Connect: ok={ok}, reason={r}")
    if ok:
        print("Connected!")
        await c.close()

asyncio.run(test())
