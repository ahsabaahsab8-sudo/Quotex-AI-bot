"""Verify the chart actually renders (candles visible) after login.
Profile is now logged in, so no OTP needed. Waits longer for candles to draw.
"""
import asyncio, os, sys, base64, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chart_capture as cc


async def main():
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=False,
        proxy=cc.PROXY, persistent_context=True,
        user_data_dir=cc.PROFILE_DIR,
        i_know_what_im_doing=True, window=(1366, 860),
    ) as context:
        page = await context.new_page()
        url = cc._asset_url("EURUSD_otc")
        await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        await cc._handle_cloudflare(page)
        await asyncio.sleep(3)
        print('>>> URL:', page.url)

        # Wait for the largest canvas, then give candles time to render
        found = None
        for _ in range(45):
            try:
                found = await page.evaluate(cc._chart_selector_js())
                if found:
                    break
            except Exception:
                pass
            await asyncio.sleep(2)
        print('>>> chart found:', found)

        # Let the websocket push candle data for a while
        for i in range(5):
            await asyncio.sleep(5)
            print(f'>>> waiting for render {i} ...')

        # Method 1: toDataURL of the largest canvas
        b64 = await page.evaluate("""() => {
            const cs = Array.from(document.querySelectorAll('canvas'))
                .filter(c => { const r = c.getBoundingClientRect(); return r.width > 200 && r.height > 150; })
                .sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
                    return rb.width * rb.height - ra.width * ra.height; });
            if (!cs.length) return null;
            try {
                const d = cs[0].toDataURL('image/png');
                console.log('canvas size', cs[0].width, cs[0].height);
                return d.split(',')[1];
            } catch (e) { return 'ERR:' + e.message; }
        }""")
        print('>>> toDataURL b64 len:', len(b64) if b64 else b64)
        if b64 and not str(b64).startswith('ERR'):
            with open(os.path.join('scratch', 'chart_todataurl.png'), 'wb') as f:
                f.write(base64.b64decode(b64))
            print('>>> saved chart_todataurl.png')

        # Method 2: element screenshot of the largest canvas (compositor pixels)
        sel_js = """() => {
            const cs = Array.from(document.querySelectorAll('canvas'))
                .filter(c => { const r = c.getBoundingClientRect(); return r.width > 200 && r.height > 150; })
                .sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
                    return rb.width * rb.height - ra.width * ra.height; });
            return cs.length ? cs[0] : null;
        }"""
        el = await page.evaluate_handle(sel_js)
        el2 = el.as_element()
        if el2:
            buf = await el2.screenshot()
            with open(os.path.join('scratch', 'chart_element.png'), 'wb') as f:
                f.write(buf)
            print('>>> element screenshot bytes:', len(buf))
        else:
            print('>>> no element for screenshot')

        print('>>> Keeping browser open 30s for inspection...')
        await asyncio.sleep(30)


asyncio.run(main())
