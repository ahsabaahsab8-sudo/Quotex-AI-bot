"""Test proxies with Camoufox for Quotex."""

import asyncio, sys

PROXY_STR = sys.argv[1] if len(sys.argv) > 1 else None
PROXY = {"server": PROXY_STR} if PROXY_STR else None

async def main():
    from camoufox.async_api import AsyncCamoufox

    print(f"\n=== Testing: {PROXY_STR or 'NO PROXY'} ===")
    try:
        async with AsyncCamoufox(
            humanize=True, geoip=True, disable_coop=True,
            proxy=PROXY,
        ) as browser:
            page = await browser.new_page()
            await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(10)
            title = await page.title()
            has_email = await page.evaluate("!!document.querySelector('input[name=\"email\"]')")
            inputs = await page.evaluate("document.querySelectorAll('input').length")
            print(f"  Title: {title}")
            print(f"  Total inputs: {inputs}")
            print(f"  Email field: {has_email}")
            if has_email:
                print("  >>> OK - LOGIN FORM LOADED!")
            else:
                print("  >>> FAILED - Form blocked")
    except Exception as e:
        print(f"  >>> Error: {str(e)[:80]}")

asyncio.run(main())
