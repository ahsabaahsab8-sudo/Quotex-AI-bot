"""Nav test through the authenticated proxy."""

import asyncio
import logging
import sys

sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROXY = {
    "server": "http://84.247.60.125:6095",
    "username": "hnbdzxdm",
    "password": "zmsy6jxvhdoz",
}


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(humanize=True, geoip=True, headless=True, proxy=PROXY) as browser:
        page = await browser.new_page()
        for attempt in range(1, 6):
            try:
                logging.info("Attempt %d: navigating...", attempt)
                await page.goto(
                    "https://market-qx.trade/en/sign-in/",
                    wait_until="domcontentloaded", timeout=45000
                )
                title = await page.title()
                logging.info("Attempt %d OK: url=%s title=%s", attempt, page.url, title[:50])
                break
            except Exception as e:
                logging.warning("Attempt %d failed: %s", attempt, e)
            await asyncio.sleep(3)


asyncio.run(main())
