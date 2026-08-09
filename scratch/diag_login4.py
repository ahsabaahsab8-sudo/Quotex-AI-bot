import asyncio, os, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
from dotenv import load_dotenv
load_dotenv()

PROXY = {'server': 'http://104.219.238.233:32771', 'username': 'DVSmpzf89o', 'password': 'It6t7Ev'}


async def main():
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=True,
        proxy=PROXY, persistent_context=True,
        user_data_dir='sessions/camoufox_chart_profile',
        i_know_what_im_doing=True,
    ) as context:
        page = await context.new_page()
        await page.goto('https://market-qx.trade/en/sign-in/', wait_until='domcontentloaded', timeout=90000)
        await asyncio.sleep(3)

        email = os.getenv('QUOTEX_EMAIL')
        password = os.getenv('QUOTEX_PASSWORD')

        # check rules checkboxes first
        try:
            await page.locator('#tab-1 input[name="rules"]').check(timeout=3000)
            print('rules checked')
        except Exception as e:
            print('rules err', str(e)[:100])
        try:
            await page.locator('#tab-1 input[name="not-us-citizen"]').check(timeout=3000)
            print('not-us-citizen checked')
        except Exception as e:
            print('citizen err', str(e)[:100])

        el = page.locator('#tab-1 input[name="email"]').first
        await el.fill(email, timeout=2500)
        el = page.locator('#tab-1 input[name="password"]').first
        await el.fill(password, timeout=2500)
        print('filled')

        try:
            await page.locator('#tab-1 button:has-text("Sign in")').first.click(timeout=5000)
            print('clicked (no nav wait)')
        except Exception as e:
            print('click err', str(e)[:150])

        for i in range(12):
            await asyncio.sleep(3)
            url = page.url
            otp = await page.query_selector('input[name="code"], input[name="otp"], input[autocomplete="one-time-code"]')
            print(f'[{i*3+3}s] url={url} otp={bool(otp)}')
            if otp:
                print('OTP READY')
                # try to read OTP from gmail
                from renew_ssid import auto_read_otp_sync
                from datetime import datetime, timezone, timedelta
                since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=30)
                code = await asyncio.to_thread(auto_read_otp_sync, timeout=60, since=since)
                print('OTP read:', code)
                if code:
                    await otp.fill(code)
                    print('OTP filled')
                    await asyncio.sleep(6)
                    print('url after otp:', page.url)
                break
            if 'sign-in' not in url.lower():
                print('NAVIGATED!')
                break


asyncio.run(main())
