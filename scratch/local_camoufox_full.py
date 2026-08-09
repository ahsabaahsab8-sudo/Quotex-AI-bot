"""Full Camoufox login + token extraction locally via the IP proxy, with nav retry."""

import asyncio
import logging
import sys

sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from dotenv import load_dotenv
load_dotenv(override=True)

import os
from renew_ssid import auto_read_otp_sync

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")
PROXY = {
    "server": "http://84.247.60.125:6095",
    "username": "hnbdzxdm",
    "password": "zmsy6jxvhdoz",
}

PREFS = {
    "security.prompt_for_key_storage_type": False,
    "signon.masterPasswordRequired": False,
    "signon.rememberSignons": False,
    "signon.autofillForms": False,
    "security.default_personal_cert": "Select Automatically",
    "accessibility.force_disabled": 1,
    "browser.downgrade.enabled": True,
}


async def nav_with_retry(page, url, attempts=5):
    last = None
    for i in range(1, attempts + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            return True
        except Exception as e:
            last = e
            logging.warning("Nav attempt %d failed: %s", i, e)
            await asyncio.sleep(4)
    logging.error("All nav attempts failed: %s", last)
    return False


async def main():
    from camoufox.async_api import AsyncCamoufox

    logging.info("Email: %s  Proxy: %s", EMAIL, PROXY["server"])

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        disable_coop=True,
        headless=True,
        proxy=PROXY,
        firefox_user_prefs=PREFS,
    ) as browser:
        page = await browser.new_page()

        async def block_qxbroker_nav(route):
            url = route.request.url
            if "qxbroker.com" in url and route.request.resource_type == "document":
                logging.info("Blocked nav redirect to qxbroker.com")
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", block_qxbroker_nav)

        if not await nav_with_retry(page, "https://market-qx.trade/en/sign-in/"):
            return
        logging.info("URL after nav: %s", page.url)

        title = await page.title()
        logging.info("Title: %s", title)
        if "Just a moment" in title:
            logging.info("Cloudflare detected, waiting...")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')", timeout=120000
                )
                logging.info("Cloudflare passed")
            except Exception:
                logging.warning("Cloudflare still active, continuing...")
        await asyncio.sleep(3)

        result = await page.evaluate(
            """
            (args) => {
                var emails = document.querySelectorAll('input[name="email"]');
                var passes = document.querySelectorAll('input[name="password"]');
                if (!emails.length || !passes.length) return "no inputs found: " + document.querySelectorAll('input').length;
                var email = emails.length > 1 ? emails[1] : emails[0];
                var pass = passes.length > 1 ? passes[1] : passes[0];
                email.value = args[0];
                pass.value = args[1];
                email.dispatchEvent(new Event('input', { bubbles: true }));
                pass.dispatchEvent(new Event('input', { bubbles: true }));
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var b = buttons[i];
                    if (b.textContent.trim() === "Sign in" && b.offsetParent !== null) {
                        b.click();
                        return "clicked Sign in";
                    }
                }
                return "Sign in button not found";
            }
            """,
            [EMAIL, PASSWORD],
        )
        logging.info("Login form: %s", result)
        await asyncio.sleep(7)

        if "/sign-in" in page.url.lower():
            logging.info("Still on sign-in, checking for OTP input...")
            try:
                otp_el = await page.query_selector('input[name="code"], input[name="otp"]')
                if otp_el:
                    logging.info("OTP input found, reading from IMAP...")
                    otp = await asyncio.to_thread(auto_read_otp_sync, timeout=60)
                    if otp:
                        await otp_el.fill(otp)
                        logging.info("OTP submitted")
                        await asyncio.sleep(5)
            except Exception as e:
                logging.warning("OTP handling: %s", e)

        if "/trade" not in page.url:
            await nav_with_retry(page, "https://market-qx.trade/en/trade", attempts=3)
            await asyncio.sleep(5)
        logging.info("Trade URL: %s", page.url)

        extract_js = """
            () => {
                try { if (window.settings && window.settings.token) return window.settings.token; } catch(e) {}
                try {
                    var scripts = document.querySelectorAll('script');
                    for (var i = 0; i < scripts.length; i++) {
                        var t = scripts[i].textContent;
                        if (t && t.includes('token')) {
                            var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                            if (m) return m[1];
                        }
                    }
                } catch(e) {}
                try { var s = document.cookie.match(/ssid=([^;]+)/); return s ? s[1] : null; } catch(e) {}
                try { var l = localStorage.getItem('token') || localStorage.getItem('ssid'); if (l) return l; } catch(e) {}
                try { var st = sessionStorage.getItem('token') || sessionStorage.getItem('ssid'); if (st) return st; } catch(e) {}
                return null;
            }
        """
        token = None
        for _ in range(20):
            try:
                token = await page.evaluate(extract_js)
            except Exception:
                token = None
            if not token:
                try:
                    cookies = await page.context.cookies()
                    for c in cookies:
                        if "ssid" in c["name"].lower() and c.get("value"):
                            token = c["value"]
                            break
                except Exception:
                    pass
            if token:
                break
            await asyncio.sleep(3)

        if token:
            logging.info("TOKEN: %s...%s", token[:10], token[-4:])
            ua = await page.evaluate("navigator.userAgent")
            from renew_ssid import save_session
            save_session(EMAIL, token, ua)
            print("TOKEN_RESULT: SUCCESS")
        else:
            logging.warning("No token found")
            try:
                info = await page.evaluate(
                    """() => ({
                        url: location.href,
                        settings: window.settings ? Object.keys(window.settings).join(',') : 'undefined',
                        cookies: document.cookie.substring(0, 200),
                    })"""
                )
                logging.warning("Debug: %s", info)
            except Exception:
                pass
            print("TOKEN_RESULT: FAILED")


asyncio.run(main())
