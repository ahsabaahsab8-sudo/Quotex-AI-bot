"""Auto-renew SSID via Playwright headless login + IMAP OTP reader."""
import os, json, asyncio, logging, imaplib, email as email_lib, re
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)
SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")

async def auto_read_otp(timeout: int = 30) -> str | None:
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

async def renew_ssid_playwright(headless: bool = True) -> str | None:
    email = os.getenv("QUOTEX_EMAIL", "slamismail8@gmail.com")
    password = os.getenv("QUOTEX_PASSWORD", "35689023Ahsan@")
    logger.info("Renewing SSID via Playwright (headless=%s)...", headless)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")

        try:
            await page.goto("https://market-qx.trade/en/sign-in", wait_until="commit", timeout=15000)
            for _ in range(45):
                await asyncio.sleep(1)
                if any(c["name"] == "cf_clearance" for c in await context.cookies()):
                    break
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)

            tab1 = await page.wait_for_selector('a.modal-sign__tab[data-value="1"]', timeout=5000)
            class_attr = await tab1.get_attribute("class") or ""
            if "active" not in class_attr:
                await tab1.click()
                await asyncio.sleep(1)

            await (await page.wait_for_selector('#tab-1 input[name="email"]', timeout=5000)).fill(email)
            await (await page.wait_for_selector('#tab-1 input[name="password"]', timeout=5000)).fill(password)

            submit = await page.query_selector('#tab-1 button.modal-sign__block-button')
            if submit:
                await submit.click()
            else:
                await page.press('#tab-1 input[name="password"]', "Enter")
            await asyncio.sleep(3)

            if "/trade" not in page.url:
                otp_input = await page.wait_for_selector('input[name="code"]', timeout=8000)
                if otp_input:
                    otp = await auto_read_otp(timeout=30)
                    if otp:
                        await otp_input.fill(otp)
                        await otp_input.press("Enter")
                    else:
                        logger.warning("OTP auto-read failed, waiting for manual entry...")
                        for _ in range(90):
                            await asyncio.sleep(1)
                            if "/trade" in page.url:
                                break
                else:
                    logger.warning("No OTP input found")
            if "/trade" not in page.url:
                await page.goto("https://market-qx.trade/en/trade", wait_until="networkidle", timeout=20000)
                await asyncio.sleep(3)

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
                logger.error("Could not extract token from trade page")
                return None

            cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in await context.cookies())
            ua = await page.evaluate("navigator.userAgent")
            session_data = {email: {"cookies": cookies_str, "token": token, "user_agent": ua}}
            with open(SESSION_FILE, "w") as f:
                json.dump(session_data, f, indent=2)
            logger.info("SSID renewed successfully: %s...%s", token[:8], token[-4:])
            return token
        finally:
            await browser.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    token = asyncio.run(renew_ssid_playwright(headless=False))
    if token:
        print(f"\nToken: {token}")
    else:
        print("\nFailed to renew SSID")
