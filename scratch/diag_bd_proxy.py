"""Diagnose why login fails on BD proxy: dump error text / OTP state after submit."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")

PROXY = "socks5://123.136.24.161:1080"

async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        headless=True,
        humanize=True,
        geoip=False,
        disable_coop=True,
        proxy={"server": PROXY},
    ) as browser:
        page = await browser.new_page()
        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        print(f"Title: {await page.title()}")
        await asyncio.sleep(15)

        has_input = await page.query_selector('input[name="email"]')
        print(f"email input present: {bool(has_input)}")

        if has_input:
            await page.fill('input[name="email"]', EMAIL)
            await page.fill('input[name="password"]', PASSWORD)
            print("filled via page.fill()")
            btn = await page.query_selector('button[type="submit"]')
            if btn:
                await btn.click()
                print("clicked submit button")
            else:
                print("no submit button")
        else:
            print("no email input - page probably not loaded (Cloudflare?)")
            html = await page.content()
            print(f"html len: {len(html)}")

        await asyncio.sleep(8)
        print(f"\nURL: {page.url}")
        print(f"Title: {await page.title()}")

        state = await page.evaluate("""
            () => {
                var body = document.body ? document.body.innerText : '';
                return {
                    bodyText: body.substring(0, 1500),
                    hasOtp: !!document.querySelector('input[name="code"], input[name="otp"], input[autocomplete="one-time-code"]'),
                    inputs: Array.from(document.querySelectorAll('input')).map(i => i.name),
                    settings: window.settings ? Object.keys(window.settings).join(',') : 'undefined',
                    cookies: document.cookie,
                };
            }
        """)
        print("=== body text ===")
        print(state["bodyText"])
        print("\n=== OTP input present:", state["hasOtp"], "===")
        print("=== inputs:", state["inputs"], "===")
        print("=== settings keys:", state["settings"], "===")
        print("=== cookies:", state["cookies"], "===")

asyncio.run(main())
