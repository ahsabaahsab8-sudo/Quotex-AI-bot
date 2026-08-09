"""Verify patched quotex_adapter routes pyquotex through the .env proxy."""
import os
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()

from quotex_adapter import _connect_with_token, load_session


async def main():
    email = os.getenv("QUOTEX_EMAIL")
    session = load_session()
    token = session.get("token")
    print(f"[i] email={email} proxy_env={os.getenv('QUOTEX_PROXY')}")

    client, err = await _connect_with_token(email, token, session)
    print(f"[i] connect -> client={'OK' if client else None} err={err}")

    if client:
        browser = client.api.browser
        print(f"[i] Browser proxies: {browser.proxies}")
        r = await browser._client.get("https://api.ipify.org", timeout=30)
        print(f"[i] HTTP outbound IP through proxy: {r.text}")
        await client.close()
    else:
        print("[!] No client (token may be stale) — checking proxy routing directly")
        from quotex_adapter import _install_proxy_patch
        _install_proxy_patch(os.getenv("QUOTEX_PROXY"))
        from pyquotex.stable_api import Quotex
        c = Quotex(email=email, password="x")
        await c.connect()
        browser = c.api.browser
        print(f"[i] Browser proxies: {browser.proxies}")
        r = await browser._client.get("https://api.ipify.org", timeout=30)
        print(f"[i] HTTP outbound IP through proxy: {r.text}")
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
