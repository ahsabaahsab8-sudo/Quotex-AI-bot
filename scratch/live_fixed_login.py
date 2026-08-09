"""LIVE test of the fixed chart_capture login flow (headed browser).
Watches: fill -> submit -> OTP field (~57s) -> OTP from Gmail -> trade page.
"""
import asyncio, os, logging
from datetime import datetime, timezone, timedelta
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chart_capture as cc

PROXY = cc.PROXY


async def main():
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=False,
        proxy=PROXY, persistent_context=True,
        user_data_dir=cc.PROFILE_DIR,
        i_know_what_im_doing=True, window=(1366, 860),
    ) as context:
        page = await context.new_page()
        url = cc._asset_url("EURUSD_otc")
        print('>>> Opening:', url)
        await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        await cc._handle_cloudflare(page)
        await asyncio.sleep(3)

        if "sign-in" in page.url.lower():
            print('>>> NOT logged in -> running fixed login flow...')
            login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
            await page.goto(f"{cc.BASE_URL}/en/sign-in/", wait_until="domcontentloaded", timeout=90000)
            await cc._handle_cloudflare(page)
            await asyncio.sleep(3)
            r = await cc._fill_login(page, os.getenv('QUOTEX_EMAIL'), os.getenv('QUOTEX_PASSWORD'))
            print('>>> fill result:', r)
            ok = await cc._complete_login(page, login_ts)
            print('>>> login ok:', ok)
        else:
            print('>>> Already logged in')

        print('>>> final URL:', page.url)

        # Try chart capture
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        found = None
        for _ in range(45):
            try:
                found = await page.evaluate(cc._chart_selector_js())
                if found:
                    break
            except Exception:
                pass
            await asyncio.sleep(2)
        print('>>> chart found:', found)
        if found:
            b64 = await page.evaluate("""() => {
                const c = document.querySelector('canvas');
                if (!c) return null;
                try { return c.toDataURL('image/png').split(',')[1]; } catch(e) { return null; }
            }""")
            print('>>> b64 length:', len(b64) if b64 else None)
            if b64:
                with open(os.path.join('scratch', 'chart_fixed_test.png'), 'wb') as f:
                    import base64
                    f.write(base64.b64decode(b64))
                print('>>> saved scratch/chart_fixed_test.png')

        print('>>> Keeping browser open 45s for inspection...')
        await asyncio.sleep(45)


asyncio.run(main())
