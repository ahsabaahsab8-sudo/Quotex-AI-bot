import asyncio, os, sys, logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

from pyquotex.stable_api import Quotex

# Force debug logging on pyquotex
import pyquotex.api as api_mod
original_on_message = api_mod.QuotexAPI._on_message
async def debug_on_message(self, msg):
    msg_str = msg.decode("utf-8", errors="ignore") if isinstance(msg, bytes) else str(msg)
    if "s_authorization" in msg_str or "authorization/reject" in msg_str:
        print(f"\n*** AUTH MSG: {msg_str[:300]}")
    await original_on_message(self, msg)
api_mod.QuotexAPI._on_message = debug_on_message

async def test():
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")

    client = Quotex(
        email=email, password=password,
        lang="en", host="market-qx.trade",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    client.account_is_demo = 0

    token = client.session_data.get("token", "")
    print(f"Token loaded: {token[:30] if token else 'EMPTY'}...")

    ok, reason = await client.connect()
    print(f"\nConnect result: ok={ok}, reason={reason}")

    if ok:
        r = await client.check_connect()
        print(f"Check connect: {r}")
        await client.close()

asyncio.run(test())
