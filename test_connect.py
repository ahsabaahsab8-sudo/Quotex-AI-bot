import asyncio, os
from dotenv import load_dotenv

load_dotenv(".env")

from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"
from pyquotex.stable_api import Quotex

async def test():
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    print(f"Email: {email}")

    client = Quotex(
        email=email,
        password=password,
        lang="en",
        host="market-qx.trade",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    client.account_is_demo = 0

    print(f"Session token: {client.session_data.get('token', 'NONE')[:30]}")
    print(f"Session cookies: {'EXISTS' if client.session_data.get('cookies') else 'EMPTY'}")

    ok, reason = await client.connect()
    print(f"Connect: ok={ok}, reason={reason}")

    if ok:
        print("SUCCESS - Quotex connected!")
        r = await client.check_connect()
        print(f"Check connect: {r}")
        await client.close()

asyncio.run(test())
