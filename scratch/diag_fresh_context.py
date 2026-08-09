"""Diagnose: why does _camoufox_login (fresh context) see no login inputs?
Dumps DOM state at intervals + JS console errors."""
import asyncio, os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

from renew_ssid import _ensure_socks_relay


async def main():
    from camoufox.async_api import AsyncCamoufox
    proxy_cfg = _ensure_socks_relay()
    print('proxy cfg:', proxy_cfg, flush=True)

    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=False,
        proxy=proxy_cfg, window=(1366, 860),
        i_know_what_im_doing=True,
        firefox_user_prefs={
            "gfx.xrender.enabled": False,
            "layers.acceleration.disabled": True,
            "gfx.canvas.accelerated": False,
            "webgl.disabled": True,
            "webgl.enable-webgl2": False,
            "signon.autofillForms": False,
        },
    ) as browser:
        page = await browser.new_page()

        async def block_qxbroker_nav(route):
            url = route.request.url
            if "qxbroker.com" in url and route.request.resource_type == "document":
                print(f'   [blocked nav] {url}', flush=True)
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", block_qxbroker_nav)

        page.on("console", lambda msg: print(f'   [console] {msg.type}: {msg.text[:120]}', flush=True))
        page.on("pageerror", lambda e: print(f'   [pageerror] {e}', flush=True))
        page.on("requestfailed", lambda req: print(f'   [reqfail] {req.url[:120]} :: {req.failure}', flush=True))

        print('>>> navigating...', flush=True)
        await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=120000)
        print('>>> title:', await page.title(), flush=True)
        print('>>> url:', page.url, flush=True)

        for i in range(12):
            await asyncio.sleep(3)
            state = await page.evaluate("""() => {
                const email = document.querySelectorAll('input[name="email"]').length;
                const pass = document.querySelectorAll('input[name="password"]').length;
                const code = document.querySelectorAll('input[name="code"]').length;
                const all = document.querySelectorAll('input').length;
                const btns = Array.from(document.querySelectorAll('button')).map(b => (b.textContent||'').trim()).slice(0,8);
                const body = (document.body.innerText||'').slice(0,120);
                return {email, pass, code, all, btns, body};
            }""")
            print(f'>>> [{i*3+3}s] {state}', flush=True)
            if state['email'] > 0:
                break

        print('>>> done. keeping open 15s', flush=True)
        await asyncio.sleep(15)


asyncio.run(main())
