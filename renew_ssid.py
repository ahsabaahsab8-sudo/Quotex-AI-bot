"""Auto-renew SSID via Playwright (headless browser login only).

Proactive watchdog runs every 20 min so the token is always fresh.
Retries 3 times with backoff. High timeouts (30-60s)."""

import os
import json
import asyncio
import logging
import imaplib
import email as email_lib
import re

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")
MAX_RETRIES = 3


def load_session() -> dict | None:
    try:
        with open(SESSION_FILE) as f:
            data = json.load(f)
        email = os.getenv("QUOTEX_EMAIL", "")
        if email in data:
            return data[email]
        first_key = next(iter(data), None)
        if first_key:
            return data[first_key]
    except Exception:
        pass
    return None


def save_session(email: str, token: str, ua: str = ""):
    try:
        if not ua:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        data = {}
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE) as f:
                data = json.load(f)
        data[email] = {
            "cookies": f"ssid={token}",
            "token": token,
            "user_agent": ua,
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("session.json updated")
    except Exception as e:
        logger.error(f"Failed to save session: {e}")


async def auto_read_otp(timeout: int = 60) -> str | None:
    imap_user = os.getenv("IMAP_EMAIL") or os.getenv("QUOTEX_EMAIL")
    imap_pass = os.getenv("IMAP_PASSWORD")
    if not imap_pass:
        logger.warning("IMAP_PASSWORD not set, OTP auto-read unavailable")
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(imap_user, imap_pass)
        mail.select("inbox")
        for _ in range(timeout):
            _, data = mail.search(None, '(FROM "quotex" UNSEEN)')
            for num in reversed(data[0].split()):
                _, msg_data = mail.fetch(num, "(RFC822)")
                body = email_lib.message_from_bytes(msg_data[0][1])
                if body.is_multipart():
                    text = ""
                    for part in body.walk():
                        if part.get_content_type() == "text/plain":
                            text = part.get_payload(decode=True).decode(errors='ignore')
                            break
                else:
                    text = body.get_payload(decode=True).decode(errors='ignore')
                match = re.search(r'\b(\d{4,6})\b', text)
                if match:
                    return match.group(1)
            await asyncio.sleep(1)
        logger.warning(f"OTP not found after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"IMAP OTP read failed: {e}")
        return None


async def _wait_cf(context, timeout: int = 60) -> bool:
    for i in range(timeout):
        await asyncio.sleep(1)
        if any(c["name"] == "cf_clearance" for c in await context.cookies()):
            return True
    return False


async def _ensure_login_page(page, context) -> bool:
    """Navigate to sign-in page, handle Cloudflare, ensure login form is visible."""
    for attempt in range(3):
        logger.info("Playwright: loading sign-in page (attempt %d/3)...", attempt + 1)
        try:
            await page.goto("https://market-qx.trade/en/sign-in/", wait_until="commit", timeout=30000)
        except Exception:
            pass
        ok = await _wait_cf(context, 60)
        if ok:
            logger.info("Playwright: Cloudflare cleared")
        else:
            logger.warning("Playwright: Cloudflare clearance timeout, proceeding anyway...")
        try:
            await page.wait_for_load_state("load", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3)
        title = await page.title()
        if "Just a moment" not in title:
            logger.info("Playwright: page loaded: %s", title)
            return True
        logger.warning("Playwright: still blocked by Cloudflare, retrying...")
    logger.error("Playwright: failed to load sign-in page after 3 attempts")
    return False


async def _find_login_form(page):
    """Find login email and password fields using multiple selector strategies."""
    email_field = None
    password_field = None

    # Strategy 1: Look for tab structure with #tab-1 (old layout)
    tab1 = await page.query_selector("#tab-1")
    if tab1:
        email_field = await tab1.query_selector('input[name="email"]')
        password_field = await tab1.query_selector('input[name="password"]')
        if email_field and password_field:
            logger.info("Playwright: found login form inside #tab-1")
            return email_field, password_field

    # Strategy 2: Look for login form specifically (not registration)
    all_emails = await page.query_selector_all('input[name="email"]')
    all_passwords = await page.query_selector_all('input[name="password"]')

    # Find the login email (it's usually before the registration one or has no id)
    for e in all_emails:
        eid = await e.get_attribute("id") or ""
        is_visible = await e.is_visible()
        if is_visible and not eid:
            email_field = e
            break

    for p in all_passwords:
        pid = await p.get_attribute("id") or ""
        is_visible = await p.is_visible()
        if is_visible:
            password_field = p
            break

    if email_field and password_field:
        logger.info("Playwright: found login form via field scanning")
        return email_field, password_field

    # Strategy 3: Grab any visible email/password inputs
    inputs = await page.query_selector_all("input:not([type='hidden']):not([type='checkbox'])")
    for inp in inputs:
        inp_type = await inp.get_attribute("type") or ""
        name = await inp.get_attribute("name") or ""
        if inp_type == "email" or name == "email":
            email_field = inp
        if inp_type == "password" or name == "password":
            password_field = inp

    if email_field and password_field:
        logger.info("Playwright: found form fields via type scan")
        return email_field, password_field

    logger.error("Playwright: could not find login form fields")
    return None, None


async def _playwright_login() -> str | None:
    from playwright.async_api import async_playwright

    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false })")

        try:
            if not await _ensure_login_page(page, context):
                return None

            email_el, pass_el = await _find_login_form(page)
            if not email_el or not pass_el:
                return None

            logger.info("Playwright: filling credentials...")
            await email_el.fill(email)
            await pass_el.fill(password)

            submit = await page.query_selector('button[type="submit"]')
            if not submit:
                submit = await page.query_selector(
                    '#tab-1 button.modal-sign__block-button, '
                    'button:has-text("Log in"), button:has-text("Sign in"), '
                    'button:has-text("Login")'
                )
            if submit:
                await submit.click()
                logger.info("Playwright: clicked submit button")
            else:
                await pass_el.press("Enter")
                logger.info("Playwright: pressed Enter")

            await asyncio.sleep(3)

            if "/trade" not in page.url:
                logger.info("Playwright: looking for OTP input...")
                otp_el = None
                for sel in [
                    'input[name="code"]', 'input[name="otp"]',
                    'input[placeholder*="code" i]', 'input[autocomplete="one-time-code"]',
                ]:
                    otp_el = await page.query_selector(sel)
                    if otp_el:
                        break
                if otp_el:
                    otp = await auto_read_otp(timeout=60)
                    if otp:
                        await otp_el.fill(otp)
                        await otp_el.press("Enter")
                        logger.info("Playwright: OTP submitted")
                    else:
                        logger.warning("Playwright: OTP auto-read failed, waiting for redirect...")
                        for _ in range(120):
                            await asyncio.sleep(1)
                            if "/trade" in page.url:
                                break
                else:
                    logger.warning("Playwright: no OTP input found, waiting for redirect...")
                    for _ in range(30):
                        await asyncio.sleep(1)
                        if "/trade" in page.url:
                            break

            if "/trade" not in page.url:
                logger.info("Playwright: navigating to trade page...")
                try:
                    await page.goto("https://market-qx.trade/en/trade", wait_until="load", timeout=45000)
                except Exception:
                    pass
                await asyncio.sleep(3)

            logger.info("Playwright: extracting token...")
            token = await page.evaluate("""
                () => {
                    try {
                        if (window.settings && window.settings.token)
                            return window.settings.token;
                        const scripts = document.querySelectorAll('script');
                        for (const s of scripts) {
                            const t = s.textContent;
                            if (t.includes('token')) {
                                const m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                                if (m) return m[1];
                            }
                        }
                        return null;
                    } catch(e) { return null; }
                }
            """)
            if not token:
                token = await page.evaluate(
                    "() => { try { var s = document.cookie.match(/ssid=([^;]+)/); return s ? s[1] : null; } catch(e) { return null; } }"
                )
                if token:
                    logger.info("Playwright: token from cookie")
            if not token:
                logger.error("Playwright: could not extract token")
                return None

            cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in await context.cookies())
            ua = await page.evaluate("navigator.userAgent")
            save_session(email, token, ua)
            logger.info("Playwright: token: %s...%s", token[:8], token[-4:])
            return token
        finally:
            await browser.close()


async def renew_ssid(force_playwright: bool = True) -> str | None:
    """Renew SSID via Playwright with retries."""
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        logger.error("QUOTEX_EMAIL / QUOTEX_PASSWORD not set in .env")
        return None

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("SSID renewal attempt %d/%d...", attempt, MAX_RETRIES)
        try:
            token = await _playwright_login()
            if token:
                return token
        except Exception as e:
            last_err = e
            logger.warning("Attempt %d failed: %s", attempt, e)
        if attempt < MAX_RETRIES:
            wait = attempt * 10
            logger.info("Retrying in %ds...", wait)
            await asyncio.sleep(wait)

    logger.error("SSID renewal failed after %d attempts: %s", MAX_RETRIES, last_err)
    return None


async def renew_ssid_playwright(headless: bool = True) -> str | None:
    return await renew_ssid(force_playwright=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    token = asyncio.run(renew_ssid())
    if token:
        print(f"\nToken: {token}")
    else:
        print("\nFailed to renew SSID")
