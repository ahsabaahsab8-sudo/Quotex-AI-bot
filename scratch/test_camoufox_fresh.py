import asyncio
import base64

from camoufox.async_api import AsyncCamoufox

URL = "https://market-qx.trade/en/trade?asset=EURUSD_otc"
TOKEN = "IpNzCCqjHiuPIsZCIW8iXulgO3U9RMuL55BQBfeK"
COOKIE_STR = 'lang=en; _ga=GA1.1.766764179.1783150091; __vid1=d5231b4b19b59872c944bf0a73728d07; lid=2221556; nas=["EURUSD_otc"%2C"EURCAD_otc"]; activeAccount=live; _ga_L4T5GBPFHJ=GS2.1.s1786264625$o154$g1$t1786264632$j53$l0$h0'


def parse_cookie_str(s):
    out = []
    for part in s.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out.append({"name": k.strip(), "value": v.strip(), "url": URL})
    return out


async def main():
    print("===== FRESH SESSION TEST =====", flush=True)
    cookies = parse_cookie_str(COOKIE_STR)
    cookies.append({"name": "ssid", "value": TOKEN, "domain": "market-qx.trade", "path": "/"})
    cookies.append({"name": "ssid", "value": TOKEN, "url": URL})
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
                await context.add_cookies(cookies)
                print("cookies added:", len(cookies), flush=True)
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

            canvas_found = False
            try:
                data = await page.evaluate(
                    """() => {
                        const canv = [...document.querySelectorAll('canvas')]
                            .filter(c => c.width > 200 && c.height > 150)
                            .sort((a,b) => (b.width*b.height)-(a.width*a.height))[0];
                        if (!canv) return null;
                        return canv.toDataURL('image/png');
                    }"""
                )
                if data and data.startswith("data:image/png"):
                    raw = base64.b64decode(data.split(",", 1)[1])
                    with open(r"C:\Users\PC\Desktop\Quotex Signal\scratch\chart_EURUSD_otc.png", "wb") as f:
                        f.write(raw)
                    canvas_found = True
                    print(f"CHART CANVAS CAPTURED: {len(raw)} bytes", flush=True)
                else:
                    print("no canvas data", flush=True)
            except Exception as e:
                print("canvas err:", e, flush=True)

            if not canvas_found:
                await page.screenshot(path=r"C:\Users\PC\Desktop\Quotex Signal\scratch\chart_EURUSD_otc.png")
                print("full-page screenshot saved instead", flush=True)
    except Exception as e:
        print("FATAL:", type(e).__name__, e, flush=True)


asyncio.run(main())
