"""Test specific proxy with full Camoufox browser."""
import asyncio, os
from dotenv import load_dotenv
from camoufox.async_api import AsyncCamoufox
load_dotenv()

async def main():
    async with AsyncCamoufox(humanize=True, headless=False, proxy={"server": "http://27.147.235.238:58080"}) as browser:
        p = await browser.new_page()
        print("Loading Quotex sign-in...")
        await p.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        print("URL:", p.url)
        print("Title:", await p.title())
        emails = await p.evaluate("() => document.querySelectorAll('input[name=\"email\"]').length")
        print("Email fields:", emails)
        if emails > 0:
            print("SUCCESS: Login form loaded!")
        else:
            html = await p.content()
            print("Has challenge:", "challenge" in html.lower())
        input("Press Enter to close browser...")

asyncio.run(main())
