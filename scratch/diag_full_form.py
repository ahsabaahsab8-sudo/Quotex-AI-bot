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
        await page.goto('https://market-qx.trade/en/sign-in/', wait_until='domcontentloaded', timeout=120000)
        await asyncio.sleep(5)

        # Full HTML of the sign-in form (tab-1)
        html = await page.evaluate("""() => {
            var tab = document.querySelector('#tab-1');
            return tab ? tab.outerHTML : 'NO #tab-1';
        }""")
        print(html)
        print('======')
        # also list all buttons and inputs in whole doc
        info = await page.evaluate("""() => {
            var out = {buttons: [], inputs: []};
            document.querySelectorAll('button').forEach(function(b){
                out.buttons.push({text: (b.textContent||'').trim().slice(0,20), type: b.type, cls: (b.className||'').slice(0,30)});
            });
            document.querySelectorAll('input').forEach(function(i){
                out.inputs.push({name: i.name, type: i.type});
            });
            return out;
        }""")
        import json
        print(json.dumps(info, indent=1))


asyncio.run(main())
