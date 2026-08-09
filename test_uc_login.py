"""Test undetected-chromedriver login directly."""

import os
import sys
import time
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")


def uc_login() -> str | None:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=150)
        wait = WebDriverWait(driver, 30)

        logger.info("UC: navigating to sign-in page...")
        driver.get("https://market-qx.trade/en/sign-in/")
        logger.info("UC: page loaded, title: %s", driver.title)

        if "Just a moment" in driver.title:
            logger.info("UC: waiting for Cloudflare challenge...")
            try:
                WebDriverWait(driver, 60).until(lambda d: "Just a moment" not in d.title)
                logger.info("UC: Cloudflare passed")
            except Exception:
                logger.warning("UC: Cloudflare may still be active")

        time.sleep(3)

        # Check inputs
        emails = driver.find_elements(By.CSS_SELECTOR, 'input[name="email"]')
        passes = driver.find_elements(By.CSS_SELECTOR, 'input[name="password"]')
        logger.info(f"UC: found {len(emails)} email inputs, {len(passes)} password inputs")

        email_input = emails[1] if len(emails) > 1 else emails[0]
        password_input = passes[1] if len(passes) > 1 else passes[0]
        email_input.send_keys(EMAIL)
        password_input.send_keys(PASSWORD)
        logger.info("UC: credentials filled")

        submit = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        submit.click()
        logger.info("UC: submitted login form")

        time.sleep(5)
        logger.info(f"UC: URL after login: {driver.current_url}")
        logger.info(f"UC: title after login: {driver.title}")

        if "/trade" not in driver.current_url:
            logger.info("UC: looking for OTP input...")
            try:
                otp_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="code"], input[name="otp"]'))
                )
                logger.info("UC: OTP input found")
                # Read OTP from IMAP
                from renew_ssid import auto_read_otp_sync
                otp = auto_read_otp_sync(timeout=60)
                if otp:
                    otp_input.send_keys(otp)
                    logger.info("UC: OTP submitted")
                    time.sleep(5)
                else:
                    logger.warning("UC: OTP not available via IMAP")
            except Exception as e:
                logger.warning(f"UC: no OTP input found: {e}")
                time.sleep(10)

        if "/trade" not in driver.current_url:
            logger.info("UC: navigating to trade page manually...")
            driver.get("https://market-qx.trade/en/trade")
            time.sleep(5)

        logger.info(f"UC: trade URL: {driver.current_url}")
        logger.info(f"UC: trade title: {driver.title}")

        # Extract token
        token = driver.execute_script("""
            try {
                if (window.settings && window.settings.token) return window.settings.token;
                var scripts = document.querySelectorAll('script');
                for (var i = 0; i < scripts.length; i++) {
                    var t = scripts[i].textContent;
                    if (t.includes('token')) {
                        var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                        if (m) return m[1];
                    }
                }
                var s = document.cookie.match(/ssid=([^;]+)/);
                return s ? s[1] : null;
            } catch(e) { return null; }
        """)
        logger.info(f"UC: token: {token[:30] if token else 'None'}")

        if token:
            ua = driver.execute_script("return navigator.userAgent")
            from renew_ssid import save_session
            save_session(EMAIL, token, ua)
            logger.info("UC: session saved")
            return token

        logger.error("UC: could not extract token")
        return None

    except Exception as e:
        logger.error("UC: login failed: %s", e)
        import traceback
        traceback.print_exc()
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    token = uc_login()
    if token:
        print(f"\nSUCCESS: token={token[:12]}...{token[-4:]}")
    else:
        print("\nFAILED: no token returned")
