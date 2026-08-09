"""Probe Quotex trade page: does it load with injected ssid, what DOM has the chart?"""
import asyncio
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROXY = {"server": "http://104.219.238.233:32771", "username": "DVSmpzf89o", "password": "It6t7Ev"}


def load_session():
    with open("session.json", encoding="utf-8") as f:
        data = json.load(f)
    email = os.getenv("QUOTEX_EMAIL", "")
    if email in data:
        return data[email]
    return data[next(iter(data), None)]


async def main():
    from camoufox.async_api import AsyncCamoufox

    session = load_session()
    ssid = session.get("token") or (session.get("cookies") or "").replace("ssid=", "")

    async with AsyncCamoufox(
        humanize=True,
        geoip=False,
        disable_coop=True,
        headless=True,
        proxy=PROXY,
    ) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        domain = "https://market-qx.trade"
        await context.add_cookies([
            {"name": "ssid", "value": ssid, "domain": ".market-qx.trade", "path": "/"},
            {"name": "ssid", "value": ssid, "domain": ".qxbroker.com", "path": "/"},
        ])

        url = "https://market-qx.trade/en/trade?asset=EURUSD_otc"
        print("Navigating:", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            print("goto:", e)
        await asyncio.sleep(6)

        print("URL:", page.url)
        print("Title:", await page.title())

        # dump useful selectors
        info = await page.evaluate("""() => {
            const q = (sel) => document.querySelectorAll(sel).length;
            const canv = Array.from(document.querySelectorAll('canvas')).map(c => {
                const r = c.getBoundingClientRect();
                return {w: Math.round(r.width), h: Math.round(r.height), cls: (c.className||'').slice(0,40)};
            });
            const sels = {};
            ['.chart', '#chart', '.trading-chart', '[class*=chart]', '[class*=Chart]',
             'svg', '.asset-title', '[class*=asset]', '[class*=Asset]',
             '.trade-wrapper', '.trading-panel', '[id*=chart]', '[id*=Chart]']
                .forEach(s => sels[s] = q(s));
            return {canvas: canv.slice(0,8), sels};
        }""")
        print("INFO:", json.dumps(info, indent=2))

        # screenshot whole page to inspect
        await page.screenshot(path="scratch/chart_page_probe.png", full_page=False)
        print("saved scratch/chart_page_probe.png")


asyncio.run(main())
