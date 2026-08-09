import asyncio
import base64

from camoufox.async_api import AsyncCamoufox

URL = "https://market-qx.trade/en/trade?asset=EURUSD_otc"
COOKIES = [{"name": "ssid", "value": "ejpGXpuGocySKYsiPvwa7m8XtX2bufEPjX2wTcog", "url": URL}]


async def main():
    try:
        async with AsyncCamoufox(
            headless=True,
            humanize=True,
            geoip=False,
            disable_coop=True,
            i_know_what_im_doing=True,
        ) as context:
            page = await context.new_page()
            try:
                await context.add_cookies(COOKIES)
                print("cookies added", flush=True)
            except Exception as e:
                print("cookie error:", e, flush=True)
            try:
                await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                print("goto done, url:", page.url, flush=True)
            except Exception as e:
                print("goto error:", e, flush=True)
            await asyncio.sleep(3)
            print("TITLE:", await page.title(), flush=True)
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')", timeout=120000
                )
                print("cloudflare cleared", flush=True)
            except Exception as e:
                print("cf wait error:", e, flush=True)
            await asyncio.sleep(8)
            print("TITLE after cf:", await page.title(), flush=True)
            print("URL after:", page.url, flush=True)
            await page.screenshot(path=r"C:\Users\PC\Desktop\Quotex Signal\scratch\camoufox_qx.png")
            print("screenshot saved", flush=True)
    except Exception as e:
        print("FATAL:", type(e).__name__, e, flush=True)


asyncio.run(main())
