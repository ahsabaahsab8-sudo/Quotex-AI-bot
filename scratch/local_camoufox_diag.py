"""Diagnose the sign-in page: what is blocking the form (CF challenge / fingerprint overlay)? Screenshot included."""

import asyncio
import logging
import sys
import os

sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROXY = {
    "server": "http://84.247.60.125:6095",
    "username": "hnbdzxdm",
    "password": "zmsy6jxvhdoz",
}


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(humanize=True, geoip=True, headless=True, proxy=PROXY) as browser:
        page = await browser.new_page()
        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded", timeout=45000
        )
        logging.info("Loaded. URL=%s", page.url)

        for wait in (2, 6, 12):
            await asyncio.sleep(wait)
            info = await page.evaluate(
                """() => {
                    var r = {};
                    r.title = document.title;
                    r.url = location.href;
                    r.inputs = document.querySelectorAll('input').length;
                    r.inputs_by_name = Array.from(document.querySelectorAll('input')).map(i => i.name || i.type).slice(0, 10);
                    r.buttons = Array.from(document.querySelectorAll('button')).map(b => (b.textContent || '').trim().substring(0, 25)).slice(0, 10);
                    r.iframes = document.querySelectorAll('iframe').length;
                    r.iframe_srcs = Array.from(document.querySelectorAll('iframe')).map(f => (f.src || '').substring(0, 60)).slice(0, 5);
                    r.forms = document.querySelectorAll('form').length;
                    r.body_class = (document.body && document.body.className || '').substring(0, 80);
                    r.body_text = (document.body ? document.body.innerText : '').substring(0, 300);
                    r.turnstile = !!document.querySelector('[id*=turnstile], [class*=challenge], [class*=captcha]');
                    return r;
                }"""
            )
            logging.info("--- after %ds wait ---", wait)
            for k, v in info.items():
                logging.info("  %s: %s", k, v)
            if info["inputs"] > 0:
                break

        await page.screenshot(path="scratch/signin_debug.png")
        logging.info("Screenshot saved to scratch/signin_debug.png")


asyncio.run(main())
