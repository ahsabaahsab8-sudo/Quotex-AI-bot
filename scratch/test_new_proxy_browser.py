"""Test the NEW proxy (104.219.238.234:38457) via Camoufox: is Quotex geo-blocked?"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

PROXY = {'server': 'http://104.219.238.234:38457', 'username': 'DVSb5shsyy', 'password': '2EjNlGB'}


async def main():
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=True,
        proxy=PROXY, i_know_what_im_doing=True,
    ) as browser:
        page = await browser.new_page()
        await page.goto('https://market-qx.trade/en/sign-in/', wait_until='domcontentloaded', timeout=120000)
        title = await page.title()
        if 'Just a moment' in title:
            print('Cloudflare detected, waiting...', flush=True)
            try:
                await page.wait_for_function("() => !document.title.includes('Just a moment')", timeout=120000)
            except Exception:
                pass
        await asyncio.sleep(5)
        body = await page.evaluate("() => document.body ? document.body.innerText : ''")
        print('=== PAGE TEXT (first 200 chars) ===', flush=True)
        print(body[:200], flush=True)
        geo = 'not available in your region' in body
        inputs = await page.evaluate("() => document.querySelectorAll('input[name=email], input[name=password]').length")
        print(f'=== GEO-BLOCKED: {geo} | login inputs found: {inputs}', flush=True)
        await page.goto('https://api.ipify.org', timeout=30000)
        ip = await page.evaluate("() => document.body.innerText")
        print('=== BROWSER EXTERNAL IP:', ip.strip(), flush=True)


asyncio.run(main())
