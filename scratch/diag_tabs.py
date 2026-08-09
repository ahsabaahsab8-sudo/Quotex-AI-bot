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

        html = await page.evaluate("""() => {
            var tabs = document.querySelectorAll('[id*="tab"]');
            var info = [];
            for (var i = 0; i < tabs.length; i++) {
                var t = tabs[i];
                info.push({id: t.id, cls: (t.className||''), html: t.outerHTML.slice(0, 2500)});
            }
            return info;
        }""")
        for t in html:
            print('=== TAB:', t['id'], '| cls:', t['cls'])
            print(t['html'][:2200])
            print()


asyncio.run(main())
