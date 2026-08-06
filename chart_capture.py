"""Fast Quotex chart screenshot capture via Camoufox.

Uses a persistent Camoufox profile so the account logs in ONCE (with
auto-read OTP from Gmail); every subsequent capture reuses the saved
profile and goes straight to the trade page - no re-login, no OTP.

Returns a base64 PNG of the candlestick chart for the requested token.
"""

import os
import base64
import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Working proxy for Camoufox (HTTP). Override via CAMOUFOX_PROXY env if set.
DEFAULT_PROXY = "http://104.219.238.234:38457"
PROXY = {"server": "http://104.219.238.234:38457", "username": "DVSb5shsyy", "password": "2EjNlGB"}

BASE_URL = "https://market-qx.trade"
TRADE_URL = BASE_URL + "/en/trade"

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "sessions", "camoufox_chart_profile")

# Timeframe param values accepted by the Quotex trade page (seconds -> UI time).
_UI_TIME = {60: 1, 120: 2, 180: 3, 300: 5, 600: 10, 900: 15, 1800: 30}


def _load_session_cookie() -> str | None:
    """Best-effort: pull the saved ssid so we can pre-seed the browser session."""
    try:
        import json
        with open(os.path.join(os.path.dirname(__file__), "session.json"), encoding="utf-8") as f:
            data = json.load(f)
        email = os.getenv("QUOTEX_EMAIL", "")
        s = data.get(email) if email in data else data.get(next(iter(data), None), {})
        token = s.get("token") or ""
        cookies = s.get("cookies") or ""
        if not token:
            token = cookies.replace("ssid=", "")
        return token or None
    except Exception:
        return None


def _proxy_dict() -> dict | None:
    """Use the known-good HTTP proxy. Env proxies are only honored if HTTP(S):
    Firefox (Camoufox) cannot authenticate SOCKS5, and the geonix SOCKS proxy
    in .env is broken. So prefer PROXY unless an http(s) env proxy is set."""
    env = os.getenv("CAMOUFOX_PROXY") or os.getenv("QUOTEX_PROXY") or ""
    if env:
        from urllib.parse import urlparse
        p = urlparse(env)
        if p.scheme in ("http", "https"):
            d = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
            if p.username:
                d["username"] = p.username
            if p.password:
                d["password"] = p.password
            return d
    return PROXY


def _chart_selector_js() -> str:
    """Return JS that finds the chart canvas / container element."""
    return """
    () => {
        // Prefer a canvas that is actually chart-sized (largest canvas on the page)
        const canvases = Array.from(document.querySelectorAll('canvas'));
        let best = null, bestArea = 0;
        for (const c of canvases) {
            const r = c.getBoundingClientRect();
            if (r.width < 200 || r.height < 150) continue;
            const area = r.width * r.height;
            if (area > bestArea) { bestArea = area; best = c; }
        }
        if (best) return {tag: 'canvas'};
        // Fallback: common chart containers
        const sels = ['.chart', '.trading-chart', '[class*="chartContainer"]',
                      '[class*="chart-container"]', '[class*="tradingChart"]',
                      '#chart', '#chart-container', '.tv-lightweight-charts'];
        for (const s of sels) {
            const el = document.querySelector(s);
            if (el) {
                const r = el.getBoundingClientRect();
                if (r.width >= 200 && r.height >= 150) return {tag: 'container', sel: s};
            }
        }
        return null;
    }
    """


def _asset_url(asset: str) -> str:
    """Build trade URL for a given Quotex symbol (e.g. EURUSD_otc)."""
    return f"{TRADE_URL}?asset={asset}"


async def _is_blank_canvas(page) -> bool:
    """Return True if the chart canvas is present but blank (no candles drawn yet)."""
    try:
        r = await page.evaluate(
            """() => {
                const cs = Array.from(document.querySelectorAll('canvas'))
                    .filter(c => { const r = c.getBoundingClientRect(); return r.width > 200 && r.height > 150; })
                    .sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
                        return rb.width * rb.height - ra.width * ra.height; });
                if (!cs.length) return null;
                const c = cs[0];
                if (c.toDataURL) {
                    try {
                        const d = c.toDataURL('image/png').split(',')[1];
                        if (d && d.length > 15000) return false;
                    } catch (e) {}
                }
                return true;
            }"""
        )
        return r if r is not None else True
    except Exception:
        return True


async def _handle_cloudflare(page) -> None:
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass
    if "Just a moment" in title:
        logger.info("chart_capture: waiting for Cloudflare challenge...")
        try:
            await page.wait_for_function(
                "() => !document.title.includes('Just a moment')", timeout=120000
            )
            logger.info("chart_capture: Cloudflare passed")
        except Exception:
            logger.warning("chart_capture: Cloudflare may still be active, continuing...")
        await asyncio.sleep(2)


async def _force_login_tab(page) -> None:
    try:
        login_tab = page.locator("#tab-1")
        if not await login_tab.is_visible():
            tab_btn = page.locator(".modal-sign__tabs-block a.modal-sign__tab", has_text="Login").first
            await tab_btn.click(timeout=3000)
            await page.wait_for_timeout(300)
        await login_tab.wait_for(state="visible", timeout=8000)
    except Exception:
        try:
            await page.locator('a.header__button-log-in, a[href$="/en/sign-in/"]').first.click(timeout=2000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass


_FILL_LOGIN_JS = """
(args) => {
    var emails = document.querySelectorAll('input[name="email"]');
    var passes = document.querySelectorAll('input[name="password"]');
    if (!emails.length || !passes.length) return "no inputs found";
    var email = emails.length > 1 ? emails[1] : emails[0];
    var pass = passes.length > 1 ? passes[1] : passes[0];
    if (!email.offsetParent || !pass.offsetParent) return "inputs not visible";
    email.value = args[0];
    pass.value = args[1];
    email.dispatchEvent(new Event('input', { bubbles: true }));
    pass.dispatchEvent(new Event('input', { bubbles: true }));
    var form = email.closest('form');
    if (form && form.requestSubmit) {
        try {
            form.requestSubmit();
            return "requestSubmit";
        } catch (e) {}
    }
    var buttons = document.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
        var b = buttons[i];
        if (b.textContent.trim() === "Sign in" && b.offsetParent !== null) {
            b.click();
            return "clicked Sign in";
        }
    }
    return "no submit found";
}
"""


async def _fill_login(page, email: str, password: str) -> str:
    try:
        await _force_login_tab(page)
    except Exception:
        pass
    return await page.evaluate(_FILL_LOGIN_JS, [email, password])


async def _complete_login(page, since) -> bool:
    """After the login form submits, wait for the OTP field (input[name="code"],
    can appear up to ~90s later), read the code from Gmail, fill it, submit,
    and confirm the redirect off /sign-in."""
    from renew_ssid import auto_read_otp_sync

    otp_task = asyncio.create_task(
        asyncio.to_thread(auto_read_otp_sync, timeout=150, since=since)
    )

    code_el = None
    loop = asyncio.get_event_loop()
    deadline = loop.time() + 100
    while loop.time() < deadline:
        if "sign-in" not in page.url.lower():
            await asyncio.sleep(2)
            return True
        try:
            code_el = await page.query_selector('input[name="code"], input[name="otp"]')
        except Exception:
            code_el = None
        if code_el:
            break
        await asyncio.sleep(2)

    if not code_el:
        logger.warning("chart_capture: OTP field never appeared")
        return False

    try:
        otp = await asyncio.wait_for(otp_task, timeout=30)
    except Exception:
        otp = None
    if not otp:
        logger.warning("chart_capture: no OTP read from Gmail")
        return False

    try:
        await code_el.fill(otp)
        logger.info("chart_capture: OTP filled")
        try:
            submit = await page.query_selector('button[type="submit"]')
            if submit:
                await submit.click()
                logger.info("chart_capture: OTP submit button clicked")
            else:
                await page.keyboard.press("Enter")
                logger.info("chart_capture: pressed Enter on OTP form")
        except Exception:
            await page.keyboard.press("Enter")
    except Exception as e:
        logger.error("chart_capture: OTP fill failed: %s", e)
        return False

    for _ in range(40):
        await asyncio.sleep(3)
        if "sign-in" not in page.url.lower():
            return True
    return "sign-in" not in page.url.lower()


async def _ensure_logged_in(page) -> bool:
    """Login once via the persistent profile if the trade page redirects to sign-in."""
    if "sign-in" not in page.url.lower():
        return True
    logger.info("chart_capture: profile not logged in, performing login...")
    email = os.getenv("QUOTEX_EMAIL", "")
    password = os.getenv("QUOTEX_PASSWORD", "")
    if not email or not password:
        logger.error("chart_capture: QUOTEX_EMAIL/QUOTEX_PASSWORD not set")
        return False
    login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    await page.goto(f"{BASE_URL}/en/sign-in/", wait_until="domcontentloaded", timeout=90000)
    await _handle_cloudflare(page)
    await asyncio.sleep(3)
    r = await _fill_login(page, email, password)
    logger.info("chart_capture: login form: %s", r)
    if r == "no inputs found":
        return False
    return await _complete_login(page, login_ts)


async def capture_chart_image(asset: str, timeframe_seconds: int = 60, timeout: float = 90.0) -> str | None:
    """Capture the chart for `asset` and return a base64 PNG, or None on failure."""
    from camoufox.async_api import AsyncCamoufox

    ui_time = _UI_TIME.get(int(timeframe_seconds), 1)
    url = _asset_url(asset)
    ssid = _load_session_cookie()
    proxy = _proxy_dict()

    logger.info("chart_capture: capturing %s (tf=%ss) via Camoufox...", asset, timeframe_seconds)

    try:
        async with AsyncCamoufox(
            humanize=True,
            geoip=False,
            disable_coop=True,
            headless=True,
            proxy=proxy,
            persistent_context=True,
            user_data_dir=PROFILE_DIR,
            i_know_what_im_doing=True,
        ) as context:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await _handle_cloudflare(page)

            if not await _ensure_logged_in(page):
                logger.error("chart_capture: login failed, cannot reach trade page")
                return None

            # Select the requested timeframe via the URL param if the page supports it
            try:
                if "sign-in" not in page.url.lower() and "/trade" in page.url.lower():
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            # Wait for the chart to render (canvas present AND candles drawn)
            # A present-but-blank canvas produces a ~4KB PNG; a rendered chart
            # produces tens of KB. Poll until non-blank or timeout.
            blank_detected = None
            for _ in range(int(timeout / 2)):
                try:
                    found = await page.evaluate(_chart_selector_js())
                    if found:
                        blank_detected = await _is_blank_canvas(page)
                        if blank_detected is False:
                            break
                except Exception:
                    pass
                await asyncio.sleep(2)

            if blank_detected:
                # Chart element exists but still blank; give candles more time
                for _ in range(20):
                    try:
                        if await _is_blank_canvas(page) is False:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(2)

            try:
                found = await page.evaluate(_chart_selector_js())
            except Exception:
                found = None

            if not found:
                logger.warning("chart_capture: no chart element found for %s", asset)
                # Still save a full-page screenshot for debugging
                try:
                    await page.screenshot(path=os.path.join(os.path.dirname(__file__), "scratch", "chart_fallback.png"))
                except Exception:
                    pass
                return None

            # Screenshot the chart element (PNG)
            if found["tag"] == "canvas":
                b64 = await page.evaluate(
                    """() => {
                        const cs = Array.from(document.querySelectorAll('canvas'))
                            .filter(c => { const r = c.getBoundingClientRect(); return r.width > 200 && r.height > 150; })
                            .sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
                                return rb.width * rb.height - ra.width * ra.height; });
                        const c = cs[0];
                        if (!c) return null;
                        try {
                            const d = c.toDataURL('image/png');
                            return d.split(',')[1];
                        } catch (e) { return null; }
                    }"""
                )
                if b64:
                    return b64
                # Fallback: clip screenshot to the canvas bounding box
                try:
                    el = await page.evaluate_handle(
                        """() => {
                            const cs = Array.from(document.querySelectorAll('canvas'))
                                .filter(c => { const r = c.getBoundingClientRect(); return r.width > 200 && r.height > 150; })
                                .sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
                                    return rb.width * rb.height - ra.width * ra.height; });
                            return cs.length ? cs[0] : null;
                        }"""
                    )
                    canvas_el = el.as_element()
                    if canvas_el:
                        buf = await canvas_el.screenshot()
                        return base64.b64encode(buf).decode()
                except Exception:
                    pass
                return None

            sel = found.get("sel") or ".chart"
            el = await page.query_selector(sel)
            if not el:
                el = await page.query_selector(".chart") or await page.query_selector("[class*='chart']")
            if el:
                buf = await el.screenshot()
                return base64.b64encode(buf).decode()

            logger.warning("chart_capture: chart container screenshot failed for %s", asset)
            return None
    except Exception as e:
        logger.error("chart_capture: failed for %s: %s", asset, e)
        return None


async def capture_chart_to_file(asset: str, timeframe_seconds: int = 60, out_path: str | None = None) -> str | None:
    """Capture the chart and write the PNG to disk. Returns the path, or None."""
    b64 = await capture_chart_image(asset, timeframe_seconds)
    if not b64:
        return None
    if not out_path:
        out_path = os.path.join(os.path.dirname(__file__), "scratch", f"chart_{asset}.png")
    raw = base64.b64decode(b64)
    with open(out_path, "wb") as f:
        f.write(raw)
    logger.info("chart_capture: saved chart to %s (%d bytes)", out_path, len(raw))
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    import sys
    asset = sys.argv[1] if len(sys.argv) > 1 else "EURUSD_otc"
    tf = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    path = asyncio.run(capture_chart_to_file(asset, tf))
    print("SAVED:", path)
