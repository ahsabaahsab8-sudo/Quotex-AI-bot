import asyncio
import base64
import shutil
import os

from camoufox.async_api import AsyncCamoufox

URL = "https://market-qx.trade/en/trade?asset=EURUSD_otc"
TOKEN = "IpNzCCqjHiuPIsZCIW8iXulgO3U9RMuL55BQBfeK"
COOKIE_STR = (
    "lang=en; _ga=GA1.1.766764179.1783150091; __vid1=d5231b4b19b59872c944bf0a73728d07; "
    'lid=2221556; nas=["EURUSD_otc","EURCAD_otc","EURNZD_otc","USDZAR_otc","USDCAD_otc",'
    '"GBPJPY_otc","EURAUD_otc","CADCHF_otc","USDPHP_otc","USDMXN_otc","USDJPY","BRLUSD_otc",'
    '"USDPKR_otc","GBPJPY","USDNGN_otc","USDARS_otc","USDIDR_otc","EURUSD","USDEGP_otc",'
    '"TRUUSD_otc","LTCUSD_otc","NZDCHF_otc","TONUSD_otc","EURJPY","AUDNZD_otc","AVAUSD_otc",'
    '"LINUSD_otc","GBPUSD","AUDJPY","USDJPY_otc","NZDUSD_otc","AUDUSD_otc","GBPUSD_otc",'
    '"EURJPY_otc","AUDCHF_otc","USDINR_otc","GBPAUD_otc","GBPCHF_otc","GBPCAD_otc","CHFJPY_otc",'
    '"GBPNZD_otc","AUDCAD_otc","CADJPY_otc","USDDZD_otc","USDCHF_otc","EURCHF_otc","USDCOP_otc",'
    '"XAUUSD_otc","XAGUSD_otc","EURGBP","NZDCAD_otc","XRPUSD_otc","AUDUSD","EURAUD","AUDCAD",'
    '"GBPCAD","AUDCHF","CADJPY","USDBDT_otc","ETHUSD_otc","XAUUSD","NZDJPY_otc","SOLUSD_otc",'
    '"EURCHF","GBPCHF","ATOUSD_otc","BTCUSD_otc","AXSUSD_otc","BCHUSD_otc","BNBUSD_otc",'
    '"DOTUSD_otc","DASUSD_otc","ETCUSD_otc","UKBrent_otc","USCrude_otc","AUDJPY_otc","XAGUSD",'
    '"CHFJPY","USDCAD","EURCAD","AXJAUD","EURGBP_otc","CHIA50","USDCHF"]; '
    "activeAccount=live; _ga_L4T5GBPFHJ=GS2.1.s1786264625$o154$g1$t1786264632$j53$l0$h0"
)

PROFILE = r"C:\Users\PC\Desktop\Quotex Signal\scratch\fresh_profile"


def build_cookies():
    out = []
    for part in COOKIE_STR.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out.append({"name": k.strip(), "value": v.strip(), "url": URL})
    out.append({"name": "ssid", "value": TOKEN, "domain": "market-qx.trade", "path": "/", "secure": True})
    out.append({"name": "ssid", "value": TOKEN, "domain": ".market-qx.trade", "path": "/", "secure": True})
    out.append({"name": "ssid", "value": TOKEN, "url": URL})
    return out


async def main():
    if os.path.isdir(PROFILE):
        shutil.rmtree(PROFILE, ignore_errors=True)
    cookies = build_cookies()
    print("total cookies:", len(cookies), flush=True)
    try:
        async with AsyncCamoufox(
            headless=True,
            humanize=True,
            geoip=False,
            disable_coop=True,
            persistent_context=True,
            user_data_dir=PROFILE,
            i_know_what_im_doing=True,
        ) as context:
            try:
                await context.add_cookies(cookies)
                print("cookies added ok", flush=True)
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

            ok = False
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
                    ok = True
                    print(f"CHART CANVAS CAPTURED: {len(raw)} bytes", flush=True)
                else:
                    print("no canvas data", flush=True)
            except Exception as e:
                print("canvas err:", e, flush=True)
            if not ok:
                await page.screenshot(path=r"C:\Users\PC\Desktop\Quotex Signal\scratch\chart_EURUSD_otc.png")
                print("full-page screenshot saved instead", flush=True)
    except Exception as e:
        print("FATAL:", type(e).__name__, e, flush=True)


asyncio.run(main())
