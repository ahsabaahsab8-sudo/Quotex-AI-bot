import asyncio, os, sys, json, logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")
from quotex_adapter import load_session, _patch_check_connect_timeout
from pyquotex.stable_api import Quotex
from pyquotex.types import ReconnectPolicy

async def main():
    session = load_session()
    token = session.get("token")
    _patch_check_connect_timeout()
    for host, wss in [
        ("market-qx.trade", "wss://ws2.market-qx.trade/socket.io/?EIO=3&transport=websocket"),
        ("market-quotex.pro", "wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket"),
    ]:
        client = Quotex(
            email="slamismail8@gmail.com", password="not-needed",
            host=host, lang="en", wss_url_override=wss,
            reconnect_policy=ReconnectPolicy(enabled=False),
        )
        client.set_account_mode("REAL")
        client.set_session(
            user_agent=session.get("user_agent") or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) Gecko/20100101 Firefox/152.0",
            cookies=session.get("cookies"), ssid=token,
        )
        ok, msg = await client.connect()
        print(f"host={host} -> ok={ok} msg={msg}", flush=True)
        if ok:
            bal = await client.get_balance()
            print("  balance:", bal, flush=True)
            try:
                await client.api.close()
            except Exception:
                pass

asyncio.run(main())
