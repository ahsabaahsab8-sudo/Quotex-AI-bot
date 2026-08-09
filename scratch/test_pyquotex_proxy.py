"""Test whether pyquotex actually routes HTTP/WebSocket through the .env proxy."""
import os
import asyncio
import json

os.environ["QUOTEX_PROXY"] = "socks5://121.169.46.116:1090"

from pyquotex.stable_api import Quotex


async def main():
    session = json.load(open("session.json", encoding="utf-8"))
    data = next(iter(session.values()))
    email = os.getenv("QUOTEX_EMAIL", "")
    token = session.get(email, data).get("token") or data.get("ssid")
    session_data = session.get(email, data)

    client = Quotex(
        email=email,
        password="not-needed",
        host="market-quotex.pro",
        lang="en",
        wss_url_override="wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket",
        proxies={"http": os.environ["QUOTEX_PROXY"], "https": os.environ["QUOTEX_PROXY"]},
    )
    client.set_account_mode("REAL")
    client.set_session(
        user_agent=session_data.get("user_agent", "Mozilla/5.0"),
        cookies=session_data.get("cookies"),
        ssid=token,
    )

    ok, msg = await client.connect()
    print(f"connect ok={ok} msg={msg}")

    browser = client.api.browser
    print("Browser proxies attr:", browser.proxies)
    transport = browser._client._transport
    print("httpx transport type:", type(transport).__name__)
    print("transport.proxy:", getattr(getattr(transport, "_pool", None), "_proxy", None))
    print("transport._pool._proxy:", getattr(getattr(transport, "_pool", None), "_proxy", None))

    try:
        r = await browser._client.get("https://api.ipify.org", timeout=30)
        print("Outbound IP seen by httpx client:", r.text)
    except Exception as e:
        print("httpbin check failed:", type(e).__name__, e)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
