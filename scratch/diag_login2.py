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

        js = """(args) => {
            var emails = document.querySelectorAll('input[name="email"]');
            var passes = document.querySelectorAll('input[name="password"]');
            var email = emails.length > 1 ? emails[1] : emails[0];
            var pass = passes.length > 1 ? passes[1] : passes[0];
            email.value = args[0];
            pass.value = args[1];
            email.dispatchEvent(new Event('input', { bubbles: true }));
            pass.dispatchEvent(new Event('input', { bubbles: true }));
            var buttons = document.querySelectorAll('button');
            var found = [];
            for (var i = 0; i < buttons.length; i++) {
                var b = buttons[i];
                found.push((b.textContent || '').trim());
                if ((b.textContent || '').trim().toLowerCase().indexOf('sign in') !== -1 && b.offsetParent !== null) {
                    b.click();
                }
            }
            return {clicked: true, buttons: found};
        }"""
        r = await page.evaluate(js, [os.getenv('QUOTEX_EMAIL'), os.getenv('QUOTEX_PASSWORD')])
        print('login result:', r)
        await asyncio.sleep(8)
        print('URL:', page.url)
        await page.screenshot(path='scratch/login_after_click.png')
        print('saved screenshot')
        # dump visible text for errors
        txt = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 1500) : ''")
        print('PAGE TEXT:', txt[:1000])


asyncio.run(main())
