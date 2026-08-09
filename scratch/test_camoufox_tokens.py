import asyncio

from camoufox.async_api import AsyncCamoufox

URL = "https://market-qx.trade/en/trade?asset=EURUSD_otc"


async def main(tokens):
    for label, tok in tokens.items():
        print(f"\n===== TRY {label} =====", flush=True)
        COOKIES = [
            {"name": "ssid", "value": tok, "domain": "market-qx.trade", "path": "/"},
            {"name": "ssid", "value": tok, "url": URL},
        ]
        try:
            async with AsyncCamoufox(
                headless=True,
                humanize=True,
                geoip=False,
                disable_coop=True,
                persistent_context=True,
                user_data_dir=r"C:\Users\PC\Desktop\Quotex Signal\screenshooter\camoufox_profile",
                i_know_what_im_doing=True,
            ) as context:
                try:
                    await context.add_cookies(COOKIES)
                    print("cookies added", flush=True)
                except Exception as e:
                    print("cookie err:", e, flush=True)
                page = await context.new_page()
                await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                print("url:", page.url, flush=True)
                await asyncio.sleep(3)
                try:
                    await page.wait_for_function(
                        "() => !document.title.includes('Just a moment')", timeout=90000
                    )
                except Exception:
                    pass
                await asyncio.sleep(8)
                print("final url:", page.url, flush=True)
                print("title:", await page.title(), flush=True)
                await page.screenshot(path=rf"C:\Users\PC\Desktop\Quotex Signal\scratch\cf_{label}.png")
        except Exception as e:
            print("FATAL:", type(e).__name__, e, flush=True)


asyncio.run(
    main(
        {
            "email": "lwlxRf7TncdA1g6VeOhGyUHy4brwym8dyCFLK5Ko",
            "null": "GNOCRP6Wqzh15lOzF3fU8RyQnnBIT5FjGSjbAdsd",
            "ssid": "ejpGXpuGocySKYsiPvwa7m8XtX2bufEPjX2wTcog",
        }
    )
)
