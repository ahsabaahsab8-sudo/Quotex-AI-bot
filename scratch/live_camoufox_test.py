"""LIVE headed Camoufox test - watch login + OTP + chart capture live.
Follows renew_ssid.py login format exactly (idea/flow only):
  navigate -> handle Cloudflare -> fill form -> click Sign in -> wait
  -> OTP from Gmail -> submit -> navigate to /trade -> screenshot chart.
Long waits (up to 60s+) at every step.
"""
import asyncio, os, logging
from datetime import datetime, timezone, timedelta
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
from dotenv import load_dotenv
load_dotenv()

PROXY = {'server': 'http://104.219.238.233:32771', 'username': 'DVSmpzf89o', 'password': 'It6t7Ev'}
EMAIL = os.getenv('QUOTEX_EMAIL')
PASSWORD = os.getenv('QUOTEX_PASSWORD')
login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)


async def main():
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=False,
        proxy=PROXY, persistent_context=True,
        user_data_dir='sessions/camoufox_chart_profile',
        i_know_what_im_doing=True, window=(1366, 860),
    ) as context:
        page = await context.new_page()

        # ── 1. Navigate to sign-in (renew_ssid format) ──
        print('>>> [1] Opening sign-in page ... (watch browser)')
        await page.goto('https://market-qx.trade/en/sign-in/', wait_until='domcontentloaded', timeout=120000)
        title = await page.title()
        print('>>> Title:', title)
        if 'Just a moment' in title:
            print('>>> Cloudflare detected, waiting up to 2 min...')
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')", timeout=120000)
                print('>>> Cloudflare passed')
            except Exception:
                print('>>> Cloudflare still active, continuing...')
        await asyncio.sleep(5)

        # ── 2. Fill email + password (renew_ssid evaluate approach) ──
        print('>>> [2] Filling email + password ...')
        fill_js = """(args) => {
            var emails = document.querySelectorAll('input[name="email"]');
            var passes = document.querySelectorAll('input[name="password"]');
            if (!emails.length || !passes.length) return "no inputs found";
            var email = emails.length > 1 ? emails[1] : emails[0];
            var pass = passes.length > 1 ? passes[1] : passes[0];
            email.value = args[0];
            pass.value = args[1];
            email.dispatchEvent(new Event('input', { bubbles: true }));
            pass.dispatchEvent(new Event('input', { bubbles: true }));
            return "filled";
        }"""
        r = await page.evaluate(fill_js, [EMAIL, PASSWORD])
        print('>>> fill result:', r)
        await asyncio.sleep(2)

        # verify values actually registered
        vals = await page.evaluate("""() => {
            var e = document.querySelectorAll('input[name="email"]');
            var p = document.querySelectorAll('input[name="password"]');
            var email = e.length > 1 ? e[1] : e[0];
            var pass = p.length > 1 ? p[1] : p[0];
            return {email: email ? email.value.length : -1, pass: pass ? pass.value.length : -1};
        }""")
        print('>>> field value lengths:', vals)

        # ── 3. Click Sign in (renew_ssid: click button with text "Sign in") ──
        print('>>> [3] Clicking Sign in ...')
        clicked = await page.evaluate("""() => {
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var b = buttons[i];
                if (b.textContent.trim() === "Sign in" && b.offsetParent !== null) {
                    b.click();
                    return "clicked Sign in";
                }
            }
            return "Sign in button not found";
        }""")
        print('>>>', clicked)

        # ── 4. Wait up to 90s for OTP input or redirect ──
        print('>>> [4] Waiting for OTP input or redirect (up to 90s)...')
        otp = None
        for i in range(45):
            await asyncio.sleep(2)
            url = page.url
            try:
                otp = await page.query_selector(
                    'input[name="code"], input[name="otp"], input[autocomplete="one-time-code"]')
            except Exception:
                otp = None
            print(f'>>> [{i*2+2}s] url={url} otp_input={"YES" if otp else "no"}')
            if otp:
                print('>>> OTP FIELD APPEARED')
                break
            if 'sign-in' not in url.lower():
                print('>>> LOGGED IN, no OTP needed')
                break

        # ── 5. Read OTP from Gmail + submit (renew_ssid format) ──
        if otp:
            print('>>> [5] Reading OTP from Gmail API (timeout 120s)...')
            from renew_ssid import auto_read_otp_sync
            code = await asyncio.to_thread(auto_read_otp_sync, timeout=120, since=login_ts)
            print('>>> OTP read from Gmail:', code)
            if code:
                await otp.fill(code)
                print('>>> OTP SUBMITTED - waiting for redirect up to 90s...')
                for i in range(45):
                    await asyncio.sleep(2)
                    url = page.url
                    print(f'>>> [{i*2+2}s] url={url}')
                    if 'sign-in' not in url.lower():
                        print('>>> LOGGED IN!')
                        break
            else:
                print('>>> NO OTP code from Gmail, waiting 60s manually...')
                await asyncio.sleep(60)
        else:
            print('>>> No OTP input, waiting 30s for login to finish...')
            await asyncio.sleep(30)

        # ── 6. Navigate to trade page for EURUSD_otc ──
        print('>>> [6] Navigating to trade page for EURUSD_otc ...')
        try:
            await page.goto('https://market-qx.trade/en/trade?asset=EURUSD_otc',
                            wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print('>>> goto trade error:', str(e)[:120])
        await asyncio.sleep(10)

        print('>>> Final URL:', page.url)
        print('>>> Title:', await page.title())

        # check if logged in
        logged_in = 'sign-in' not in page.url.lower()
        print('>>> LOGGED IN:', logged_in)
        if not logged_in:
            print('>>> STILL ON SIGN-IN - login did not complete')
            txt = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 300) : ''")
            print('>>> PAGE TEXT:', txt)

        # ── 7. Screenshot chart canvas ──
        if logged_in:
            print('>>> [7] Capturing chart...')
            found = await page.evaluate("""() => {
                const cs = Array.from(document.querySelectorAll('canvas'));
                let best = null, area = 0;
                for (const c of cs) {
                    const r = c.getBoundingClientRect();
                    if (r.width > 200 && r.height > 150 && r.width * r.height > area) {
                        area = r.width * r.height; best = c;
                    }
                }
                return best ? {w: Math.round(best.getBoundingClientRect().width), h: Math.round(best.getBoundingClientRect().height)} : null;
            }""")
            print('>>> CHART CANVAS:', found)
            await page.screenshot(path='scratch/live_chart_full.png')
            if found:
                el = await page.query_selector('canvas')
                buf = await el.screenshot()
                with open('scratch/live_chart_canvas.png', 'wb') as f:
                    f.write(buf)
                print('>>> CHART SAVED -> scratch/live_chart_canvas.png')
            else:
                txt = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 300) : ''")
                print('>>> PAGE TEXT:', txt)

        print('>>> DONE - browser stays open 60s so you can see everything')
        await asyncio.sleep(60)


asyncio.run(main())
