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
        print('URL:', page.url)
        print('Title:', await page.title())

        js = """(args) => {
            var emails = document.querySelectorAll('input[name="email"]');
            var passes = document.querySelectorAll('input[name="password"]');
            if (!emails.length || !passes.length) return "no inputs found";
            var email = emails.length > 1 ? emails[1] : emails[0];
            var pass = passes.length > 1 ? passes[1] : passes[0];
            email.value = args[0];
            pass.value = args[1];
            email.dispatchEvent(new Event('input', { bubbles: true }));
            pass.dispatchEvent(new Event('input', { bubbles: true }));
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var b = buttons[i];
                if (b.textContent.trim() === 'Sign in' && b.offsetParent !== null) {
                    b.click();
                    return 'clicked Sign in';
                }
            }
            return 'Sign in button not found';
        }"""
        r = await page.evaluate(js, [os.getenv('QUOTEX_EMAIL'), os.getenv('QUOTEX_PASSWORD')])
        print('login:', r)
        for i in range(8):
            await asyncio.sleep(3)
            print(f'[{i*3+3}s]', page.url)
            if 'sign-in' not in page.url.lower():
                break
        try:
            otp = await page.query_selector('input[name="code"], input[name="otp"]')
            print('OTP input:', 'FOUND' if otp else 'not found')
            html = await page.content()
            print('html has otp keywords:', any(k in html.lower() for k in ['pincode', 'verification code', 'enter the code', 'authentication']))
        except Exception as e:
            print('otp check err', e)


asyncio.run(main())
