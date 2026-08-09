import asyncio, os, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
from dotenv import load_dotenv
load_dotenv()

PROXY = {'server': 'http://104.219.238.233:32771', 'username': 'DVSmpzf89o', 'password': 'It6t7Ev'}


async def main():
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=False,
        proxy=PROXY, persistent_context=True,
        user_data_dir='sessions/camoufox_chart_profile',
        i_know_what_im_doing=True, window=(1366, 860),
    ) as context:
        page = await context.new_page()
        await page.goto('https://market-qx.trade/en/sign-in/', wait_until='domcontentloaded', timeout=90000)
        await asyncio.sleep(3)

        # dump the checkbox + submit area of tab-1
        html = await page.evaluate("""() => {
            var tab = document.querySelector('#tab-1');
            var s = tab.outerHTML;
            var i = s.indexOf('checkbox');
            if (i < 0) i = s.indexOf('rules');
            if (i < 0) i = s.indexOf('Sign in');
            return s.slice(Math.max(0, i - 800), i + 1500);
        }""")
        print(html)


asyncio.run(main())
