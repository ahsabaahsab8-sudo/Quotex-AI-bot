"""Debug: proxy page structure on Quotex sign-in."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

PROXY = {
    "server": "http://84.247.60.125:6095",
    "username": "hnbdzxdm",
    "password": "zmsy6jxvhdoz",
}


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        headless=True,
        proxy=PROXY,
    ) as browser:
        page = await browser.new_page()

        print("1. Navigate to Quotex sign-in...")
        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded",
            timeout=120000
        )
        await asyncio.sleep(5)
        print(f"   URL: {page.url}")
        print(f"   Title: {await page.title()}")

        # Check page content for input fields
        info = await page.evaluate("""() => {
            var all_inputs = document.querySelectorAll('input');
            var email_inputs = document.querySelectorAll('input[name="email"]');
            var pass_inputs = document.querySelectorAll('input[name="password"]');
            var all_buttons = document.querySelectorAll('button');
            var forms = document.querySelectorAll('form');
            return {
                total_inputs: all_inputs.length,
                email_inputs: email_inputs.length,
                pass_inputs: pass_inputs.length,
                buttons: Array.from(all_buttons).map(b => ({
                    text: b.textContent.trim().substring(0, 30),
                    visible: b.offsetParent !== null,
                    type: b.type || 'button'
                })),
                forms: forms.length,
                body_class: document.body ? document.body.className.substring(0, 100) : 'no body',
                html_snippet: document.body ? document.body.innerHTML.substring(0, 500) : 'no body'
            };
        }""")
        print(f"\n2. Page structure:")
        for k, v in info.items():
            if k == 'html_snippet':
                print(f"   {k}: {v[:200]}...")
            else:
                print(f"   {k}: {v}")

        # Wait longer and recheck
        await asyncio.sleep(5)
        info2 = await page.evaluate("""() => ({
            email_count: document.querySelectorAll('input[name="email"]').length,
            pass_count: document.querySelectorAll('input[name="password"]').length,
            ready_state: document.readyState
        })""")
        print(f"\n3. After 5 more seconds:")
        print(f"   {info2}")


asyncio.run(main())
