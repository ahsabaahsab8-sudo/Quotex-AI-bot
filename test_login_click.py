"""Live test: Playwright native fill + click."""
import os, sys, asyncio, logging

sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger()

from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(
        headless=False,
        proxy={"server": "http://172.93.103.135:35669", "username": "DVSx4xivlq", "password": "DeiTC2x"},
        geoip=False,
        firefox_user_prefs={"network.proxy.type": 1, "network.proxy.no_proxies_on": "localhost, 127.0.0.1"}
    ) as browser:
        page = await browser.new_page()
        page.set_default_timeout(60000)

        # Navigate with retries
        url = "https://market-qx.trade/en/sign-in/"
        for attempt in range(5):
            logger.info("Navigate attempt %d: %s ...", attempt + 1, url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(5)
                logger.info("Title: %s | URL: %s", await page.title(), page.url)
                break
            except Exception as e:
                logger.warning("Nav failed: %s", e)
                await asyncio.sleep(5)
        else:
            return

        EMAIL = "slamismail8@gmail.com"
        PASSWORD = "35689023Ahsan@"

        # === METHOD 1: Playwright native fill() ===
        logger.info("Trying Playwright locator.fill()...")
        try:
            email_input = page.locator('input[name="email"]').first
            await email_input.click(timeout=5000)
            await email_input.fill(EMAIL, timeout=5000)
            logger.info("Email filled via .fill()")
        except Exception as e:
            logger.warning("Email .fill() failed: %s", e)

        try:
            pass_input = page.locator('input[name="password"]').first
            await pass_input.click(timeout=5000)
            await pass_input.fill(PASSWORD, timeout=5000)
            logger.info("Password filled via .fill()")
        except Exception as e:
            logger.warning("Password .fill() failed: %s", e)

        # Verify DOM values
        vals = await page.evaluate("""
            () => {
                var e = document.querySelector('input[name="email"]');
                var p = document.querySelector('input[name="password"]');
                return {email: e?.value, passLen: p?.value?.length};
            }
        """)
        logger.info("DOM values after .fill(): %s", vals)

        # Take screenshot
        await page.screenshot(path="diag_after_fill3.png")
        logger.info("Screenshot: diag_after_fill3.png")

        # === Click Sign in ===
        if vals.get("email") and vals.get("passLen", 0) > 0:
            logger.info("Values confirmed in DOM — clicking Sign in...")
            try:
                await page.get_by_role("button", name="Sign in").click(timeout=5000)
                logger.info("Sign in clicked!")
            except Exception as e:
                logger.warning("getByRole failed: %s — trying locator...", e)
                try:
                    await page.locator('button[type="submit"]:has-text("Sign in")').click(timeout=5000)
                    logger.info("Sign in clicked via locator!")
                except Exception as e2:
                    logger.error("All click methods failed: %s", e2)
        else:
            logger.error("Values NOT in DOM — fill() didn't work. Trying keyboard approach...")
            # Fallback: triple-click to select all, then type
            try:
                await email_input.click(click_count=3)
                await page.keyboard.type(EMAIL, delay=30)
                await pass_input.click(click_count=3)
                await page.keyboard.type(PASSWORD, delay=30)
                vals2 = await page.evaluate("() => ({email: document.querySelector('input[name=\"email\"]')?.value, passLen: document.querySelector('input[name=\"password\"]')?.value?.length})")
                logger.info("After keyboard type: %s", vals2)
                if vals2.get("email") and vals2.get("passLen", 0) > 0:
                    await page.get_by_role("button", name="Sign in").click(timeout=5000)
                    logger.info("Sign in clicked after keyboard fill!")
            except Exception as e:
                logger.error("Keyboard fallback failed: %s", e)

        # Watch for changes
        logger.info("Watching for 60s...")
        for i in range(30):
            await asyncio.sleep(2)
            cur_url = page.url
            if (i+1) % 5 == 0:
                logger.info("  [%ds] URL: %s", (i+1)*2, cur_url)
            if "/trade" in cur_url.lower():
                logger.info("  >>> ON /trade!")
                break
            has_otp = await page.evaluate("() => { var el = document.querySelector('input[name=\"code\"]'); return el ? (el.offsetParent !== null) : false; }")
            if has_otp:
                logger.info("  >>> OTP FIELD appeared!")
                break
            # Check for errors periodically
            if (i+1) % 5 == 0:
                errors = await page.evaluate("""
                    () => {
                        var errs = document.querySelectorAll('.error, .alert, .invalid-feedback, [class*="error"], [class*="Error"]');
                        return Array.from(errs).map(e => e.innerText.trim()).filter(Boolean).slice(0, 3);
                    }
                """)
                if errors:
                    logger.info("  >>> Errors: %s", errors)

        await page.screenshot(path="diag_login_final.png", full_page=True)
        logger.info("Final screenshot saved")

        # Debug: show the form's onsubmit handler
        handler = await page.evaluate("""
            () => {
                var form = document.querySelector('form[action*="sign-in"]');
                if (!form) return 'no form';
                return {
                    action: form.action,
                    onsubmit: form.getAttribute('onsubmit'),
                    method: form.method,
                    hasQXvId: typeof QXvId !== 'undefined',
                    QXvIdKeys: typeof QXvId !== 'undefined' ? Object.keys(QXvId) : null
                };
            }
        """)
        logger.info("Form handler: %s", handler)

        logger.info("Done. Waiting 15s...")
        await asyncio.sleep(15)

asyncio.run(main())
