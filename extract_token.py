"""
Quotex SSID Token Extractor
First page load = 2 min wait. Retries = 40s wait.
"""
import os, time, json, re, asyncio, logging
from datetime import datetime, timezone, timedelta

# Bypass system proxy for Gmail API (Google doesn't need our Quotex proxy)
os.environ["NO_PROXY"] = "googleapis.com,google.com,imap.gmail.com"
os.environ["no_proxy"] = "googleapis.com,google.com,imap.gmail.com"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("quotex")

EMAIL = os.environ.get("QUOTEX_EMAIL", "slamismail8@gmail.com")
PASSWORD = os.environ.get("QUOTEX_PASSWORD", "35689023Ahsan@")


def read_otp_from_gmail(since_time, timeout=120):
    from gmail_otp import fetch_latest_otp
    logger.info(">> Getting OTP from Gmail API...")
    return fetch_latest_otp(timeout=timeout, since=since_time)


async def extract_token():
    from camoufox.async_api import AsyncCamoufox

    proxy_config = {
        "server": "http://172.93.103.135:35669",
        "username": "DVSlm9nplp",
        "password": "iJUCWQd",
    }

    async with AsyncCamoufox(headless=False, proxy=proxy_config, geoip=False) as browser:
        page = await browser.new_page()
        page.set_default_timeout(120000)
        n = 0
        first_load = True

        async def snap(tag):
            nonlocal n; n += 1
            try: await page.screenshot(path=f"step{n:02d}_{tag}.png")
            except: pass

        while True:
            try:
                # 1. Navigate
                logger.info("[1] Loading page...")
                for i in range(10):
                    try:
                        await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=60000)
                        break
                    except:
                        await asyncio.sleep(5)

                # 2. Wait — 2 min first time, 40s after
                wait_time = 120 if first_load else 40
                first_load = False
                logger.info("[2] Waiting %ds for page render...", wait_time)
                await asyncio.sleep(wait_time)
                logger.info("[2] Page ready: %s", page.url)
                await snap("loaded")

                # Check geo block
                body = await page.evaluate("() => document.body?.innerText || ''")
                if "not available in your region" in body:
                    logger.error("[2] GEO BLOCKED"); await asyncio.sleep(60); continue

                # 3. Find email input
                email_pos = await page.evaluate("""
                    () => {
                        var els = document.querySelectorAll('input[name="email"]');
                        for (var el of els) {
                            var r = el.getBoundingClientRect();
                            if (r.width > 50 && r.height > 10) return {x: r.x+r.width/2, y: r.y+r.height/2};
                        }
                        return null;
                    }
                """)
                if not email_pos:
                    logger.error("[3] Email not found"); await asyncio.sleep(10); continue

                logger.info("[3] Typing email at (%d,%d)...", email_pos["x"], email_pos["y"])
                await page.mouse.click(email_pos["x"], email_pos["y"])
                await asyncio.sleep(0.5)
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(EMAIL, delay=50)
                logger.info("[3] Email done")

                # 4. Find password input
                pass_pos = await page.evaluate("""
                    () => {
                        var els = document.querySelectorAll('input[name="password"]');
                        for (var el of els) {
                            var r = el.getBoundingClientRect();
                            if (r.width > 50 && r.height > 10) return {x: r.x+r.width/2, y: r.y+r.height/2};
                        }
                        return null;
                    }
                """)
                if not pass_pos:
                    logger.error("[4] Password not found"); await asyncio.sleep(10); continue

                logger.info("[4] Typing password at (%d,%d)...", pass_pos["x"], pass_pos["y"])
                await page.mouse.click(pass_pos["x"], pass_pos["y"])
                await asyncio.sleep(0.5)
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(PASSWORD, delay=50)
                logger.info("[4] Password done")
                await snap("filled")

                # 5. Find and click Sign in button
                # Dump ALL buttons first to debug
                all_buttons = await page.evaluate("""
                    () => {
                        var result = [];
                        document.querySelectorAll('button').forEach(b => {
                            var r = b.getBoundingClientRect();
                            result.push({
                                type: b.type, txt: (b.innerText||'').trim().slice(0,40),
                                x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2),
                                w: Math.round(r.width), h: Math.round(r.height)
                            });
                        });
                        return result;
                    }
                """)
                logger.info("[5] All buttons: %s", json.dumps(all_buttons))

                # Find the Sign in button
                btn_pos = None
                for b in all_buttons:
                    if b["w"] > 100 and b["h"] > 40 and "sign in" in b["txt"].lower():
                        btn_pos = b
                        break

                # Fallback: largest submit button
                if not btn_pos:
                    for b in all_buttons:
                        if b["type"] == "submit" and b["w"] > 100 and b["h"] > 40:
                            btn_pos = b
                            break

                if not btn_pos:
                    logger.error("[5] No Sign in button found — retrying..."); await asyncio.sleep(10); continue

                login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
                logger.info("[5] Clicking '%s' at (%d,%d)...", btn_pos["txt"], btn_pos["x"], btn_pos["y"])
                await page.mouse.click(btn_pos["x"], btn_pos["y"])
                logger.info("[5] CLICKED!")
                await snap("clicked")

                # 6. Watch page
                logger.info("[6] Watching page...")
                otp_detected = False
                for i in range(90):
                    await asyncio.sleep(2)
                    elapsed = (i+1)*2
                    state = await page.evaluate("""
                        () => ({
                            url: location.href,
                            isTrade: location.href.includes('/trade'),
                            otpVisible: Array.from(document.querySelectorAll('input[name="code"]')).some(el => el.offsetParent !== null && window.getComputedStyle(el).display !== 'none')
                        })
                    """)
                    if state["isTrade"]:
                        logger.info("[6] [%ds] >>> ON TRADE!", elapsed); break
                    if state["otpVisible"]:
                        logger.info("[6] [%ds] >>> OTP PAGE!", elapsed)
                        otp_detected = True
                        await snap("otp"); break
                    if elapsed % 20 == 0:
                        logger.info("[6] [%ds] URL: %s", elapsed, state["url"])
                else:
                    logger.warning("[6] TIMEOUT — retrying..."); await snap("timeout"); continue

                # 7. OTP
                if otp_detected:
                    logger.info("[7] Getting OTP from Gmail...")
                    otp = await asyncio.to_thread(read_otp_from_gmail, login_ts, timeout=150)
                    if not otp:
                        logger.error("[7] No OTP"); continue
                    logger.info("[7] OTP: %s", otp)

                    otp_pos = await page.evaluate("""
                        () => {
                            var el = document.querySelector('input[name="code"]');
                            if (!el) return null;
                            var r = el.getBoundingClientRect();
                            if (r.width === 0) return null;
                            return {x: r.x+r.width/2, y: r.y+r.height/2};
                        }
                    """)
                    if not otp_pos:
                        logger.error("[7] OTP input gone"); continue

                    await page.mouse.click(otp_pos["x"], otp_pos["y"])
                    await asyncio.sleep(0.5)
                    await page.keyboard.type(otp, delay=100)
                    await page.keyboard.press("Enter")
                    logger.info("[7] OTP submitted")
                    await snap("otp_sent")

                    for i in range(30):
                        await asyncio.sleep(3)
                        if "/trade" in page.url.lower():
                            logger.info("[7] [%ds] ON TRADE!", (i+1)*3); break
                    else:
                        continue

                # 8. Token
                if "/trade" not in page.url.lower():
                    try:
                        await page.goto("https://market-qx.trade/en/trade", wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(10)
                    except: pass

                logger.info("[8] Extracting token... URL: %s", page.url)
                await snap("trade")

                token = None
                for i in range(40):
                    try:
                        for c in await page.context.cookies():
                            if "ssid" in c["name"].lower() and c.get("value"):
                                token = c["value"]; break
                    except: pass
                    if not token:
                        token = await page.evaluate("() => window.settings?.token || null")
                    if token:
                        logger.info("[8] >>> TOKEN: %s...%s", token[:15], token[-5:]); break
                    await asyncio.sleep(3)

                await snap("final")
                return token

            except Exception as e:
                logger.error("[ERR] %s", e); await asyncio.sleep(10)


if __name__ == "__main__":
    token = asyncio.run(extract_token())
    if token:
        session = json.load(open("session.json")) if os.path.exists("session.json") else {}
        session["quotex_ssid"] = token
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open("session.json", "w") as f: json.dump(session, f, indent=2)
        print("\n=== TOKEN SAVED ===")
    else:
        print("\n=== FAILED ===")
