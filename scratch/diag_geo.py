"""Get the FULL page text of the sign-in page through the new proxy."""
import asyncio, os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
from renew_ssid import _ensure_socks_relay


async def main():
    proxy_cfg = _ensure_socks_relay()
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=True,
        proxy=proxy_cfg, i_know_what_im_doing=True,
    ) as browser:
        page = await browser.new_page()
        await page.goto('https://market-qx.trade/en/sign-in/', wait_until='domcontentloaded', timeout=120000)
        await asyncio.sleep(8)
        body = await page.evaluate("() => document.body.innerText")
        print('=== FULL PAGE TEXT ===', flush=True)
        print(body, flush=True)
        ip = await page.evaluate("() => fetch('https://api.ipify.org').then(r=>r.text())") if False else None
        await page.goto('https://api.ipify.org', timeout=30000)
        text = await page.evaluate("() => document.body.innerText")
        print('=== EXTERNAL IP ===', text, flush=True)


asyncio.run(main())
