"""Isolate: can Camoufox reach a simple site through the HTTP proxy?"""

import asyncio
from camoufox.async_api import AsyncCamoufox

PROXY = {"server": "http://151.242.178.244:59100",
         "username": "slamismail8", "password": "oWgL5jV6xM"}


async def main():
    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        disable_coop=True,
        headless=True,
        proxy=PROXY,
    ) as browser:
        page = await browser.new_page()
        for url in ["https://api.ipify.org", "https://example.com", "http://example.com"]:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                txt = (await page.content())[:80].replace("\n", " ")
                print(f"OK  {url} -> {page.url} | {txt}")
            except Exception as e:
                print(f"ERR {url} -> {str(e)[:60]}")


asyncio.run(main())
