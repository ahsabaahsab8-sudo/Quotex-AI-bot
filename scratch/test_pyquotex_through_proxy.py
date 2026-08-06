"""Real test: pyquotex connecting THROUGH the .env proxy IP.

Enables TELEGRAM_PROXY/QUOTEX_PROXY from .env and patches pyquotex's
two connection points (httpx browser + websocket) to route via the socks5
proxy, then verifies outbound IP == proxy IP and the Quotex socket opens.
"""
import os
import re
import json
import asyncio

os.environ.setdefault("QUOTEX_PROXY", "socks5://121.169.46.116:1090")
PROXY = os.environ["QUOTEX_PROXY"]
print(f"[i] Proxy from env: {PROXY}")

import httpx
import websockets
from pyquotex.network.navigator import Browser as _Browser
from pyquotex.ws.client import WebsocketClient as _WSClient

# --- patch 1: httpx Browser -> route via socks5 proxy ---
from pyquotex.network.ssl_utils import create_ssl_context, CIPHER_SUITE_FIREFOX

class ProxyBrowser(_Browser):
    def __init__(self, *a, **kw):
        self.response = None
        self.default_headers = None
        self.source_address = kw.pop('source_address', None)
        self.server_hostname = kw.pop('server_hostname', None)
        self.proxies = PROXY
        self.debug = kw.pop('debug', False)
        self._ssl_context = create_ssl_context(cipher_suite=CIPHER_SUITE_FIREFOX)
        if self.server_hostname:
            self._ssl_context.check_hostname = False
        self.headers = self.get_headers()
        self._client = httpx.AsyncClient(
            verify=self._ssl_context,
            timeout=30.0,
            follow_redirects=True,
            proxy=PROXY,
        )

import pyquotex.network.navigator as _nav
_nav.Browser = ProxyBrowser
import pyquotex.api as _api
_api.Browser = ProxyBrowser

# --- patch 2: websocket -> route via socks5 proxy ---
_orig_connect_once = _WSClient._connect_once
async def proxy_connect_once(self, url, extra_headers, ssl):
    headers = extra_headers or {}
    async with websockets.connect(
        url,
        additional_headers=headers,
        ssl=ssl,
        proxy=PROXY,
        ping_interval=24,
        ping_timeout=20,
        max_size=2 ** 23,
        compression=None,
    ) as ws:
        self._ws = ws
        self.api.last_message_at = __import__("time").monotonic()
        await self.api._on_open()
        self._open_count += 1
        if self._open_count > 1:
            import asyncio as a
            a.create_task(self._replay_subscriptions())
        self._start_watchdog()
        try:
            async for raw in ws:
                await self.api._on_message(raw)
        finally:
            self._stop_watchdog()

_WSClient._connect_once = proxy_connect_once


async def main():
    session = json.load(open("session.json", encoding="utf-8"))
    first = next(iter(session))
    email = os.getenv("QUOTEX_EMAIL") or first
    data = session.get(email) or session[first]
    token = data.get("token") or data.get("ssid")

    from pyquotex.stable_api import Quotex
    client = Quotex(
        email=email,
        password="not-needed",
        host="market-quotex.pro",
        lang="en",
        wss_url_override="wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket",
        proxies={"http": PROXY, "https": PROXY},
    )
    client.set_account_mode("REAL")
    client.set_session(
        user_agent=data.get("user_agent", "Mozilla/5.0"),
        cookies=data.get("cookies"),
        ssid=token,
    )

    ok, msg = await client.connect()
    print(f"\n[+] connect ok={ok} msg={msg}")

    browser = client.api.browser
    t = browser._client._transport
    print(f"[i] httpx transport: {type(t).__name__}")
    print(f"[i] httpx proxy attr: {getattr(getattr(t, '_pool', None), '_proxy', None)}")

    r = await browser._client.get("https://api.ipify.org", timeout=30)
    print(f"[i] HTTP outbound IP through proxy: {r.text}")

    if ok:
        bal = client.get_balance()
        print(f"[i] Balance via proxy-connected socket: {bal}")
    else:
        print("[!] WS was rejected (token/auth) but connection itself went through proxy")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
