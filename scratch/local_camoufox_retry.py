"""Retry goto through the proxy, printing each error, to characterize proxy behavior vs the browser."""

import asyncio
import logging
import sys

sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from dotenv import load_dotenv
load_dotenv(override=True)

import os

PROXY = {"server": os.getenv("QUOTEX_PROXY")}


async def main():
    from camoufox.async_api import AsyncCamoufox

    logging.info("Using proxy: %s", PROXY["server"])
    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        disable_coop=True,
        proxy=PROXY,
    ) as browser:
        page = await browser.new_page()

        for attempt in range(1, 6):
            try:
                logging.info("Attempt %d: navigating...", attempt)
                await page.goto(
                    "https://market-qx.trade/en/sign-in/",
                    wait_until="domcontentloaded", timeout=45000
                )
                url = page.url
                title = await page.title()
                logging.info("Attempt %d OK: url=%s title=%s", attempt, url, title[:40])
                if "sign-in" in url and "Just a moment" not in title:
                    logging.info("Reached login page. SUCCESS")
                    break
            except Exception as e:
                logging.warning("Attempt %d failed: %s", attempt, e)
            await asyncio.sleep(5)


asyncio.run(main())
