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

        # force login tab + fill via Playwright
        try:
            lt = page.locator('#tab-1')
            if not await lt.is_visible():
                tb = page.locator('.modal-sign__tabs-block a.modal-sign__tab', has_text='Login').first
                await tb.click(timeout=3000)
                await page.wait_for_timeout(300)
            await lt.wait_for(state='visible', timeout=8000)
            print('login tab visible')
        except Exception as e:
            print('tab err', e)

        email = os.getenv('QUOTEX_EMAIL')
        password = os.getenv('QUOTEX_PASSWORD')
        try:
            el = page.locator('#tab-1 input[name="email"]').first
            await el.wait_for(state='visible', timeout=4000)
            await el.fill(email, timeout=2500)
            print('email filled')
        except Exception as e:
            print('email err', e)
        try:
            el = page.locator('#tab-1 input[name="password"]').first
            await el.wait_for(state='visible', timeout=4000)
            await el.fill(password, timeout=2500)
            print('password filled')
        except Exception as e:
            print('pass err', e)
        try:
            btn = page.locator('#tab-1 button:has-text("Sign in")').first
            await btn.click(timeout=2500)
            print('clicked sign in')
        except Exception as e:
            print('click err', e)

        # watch for OTP input or redirect over 40s
        for i in range(13):
            await asyncio.sleep(3)
            url = page.url
            if 'sign-in' not in url.lower():
                print(f'[{i*3+3}s] NAVIGATED -> {url}')
                break
            # dump any input present
            inputs = await page.evaluate("""() => {
                var out = [];
                document.querySelectorAll('input').forEach(function(i){
                    out.push({name: i.name, type: i.type, ph: (i.placeholder||''), cls: (i.className||'').slice(0,40)});
                });
                return out;
            }""")
            otp = await page.query_selector('input[name="code"], input[name="otp"], input[autocomplete="one-time-code"]')
            print(f'[{i*3+3}s] still sign-in; OTP input found: {bool(otp)}; inputs={inputs[:8]}')
            if otp:
                print('OTP INPUT PRESENT - ready to fill')

        # dump page text to find errors
        txt = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 800) : ''")
        print('PAGE TEXT:', txt)


asyncio.run(main())
