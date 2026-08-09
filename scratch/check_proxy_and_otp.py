"""Check the browser's actual external IP through the new proxy + test Gmail OTP."""
import asyncio, os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

from renew_ssid import _ensure_socks_relay
from gmail_otp import fetch_latest_otp


async def main():
    print('=== 1) Check Camoufox external IP via new proxy ===', flush=True)
    proxy_cfg = _ensure_socks_relay()
    print('proxy cfg:', proxy_cfg, flush=True)

    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=True,
        proxy=proxy_cfg, i_know_what_im_doing=True,
    ) as browser:
        page = await browser.new_page()
        try:
            ip = await page.goto('https://api.ipify.org', timeout=30000)
            text = await page.evaluate("() => document.body.innerText")
            print('BROWSER EXTERNAL IP:', text.strip(), flush=True)
        except Exception as e:
            print('IP check failed:', e, flush=True)

    print('=== 2) Test Gmail OTP reader ===', flush=True)
    otp = fetch_latest_otp(timeout=20)
    print('GMAIL OTP result:', otp, flush=True)


asyncio.run(main())
