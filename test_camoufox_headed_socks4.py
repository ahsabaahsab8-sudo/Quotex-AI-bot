"""Live headed Camoufox login test through a SOCKS4 proxy — watch on screen."""

import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")

PROXY = {"server": "socks4://202.142.159.204:31026"}


async def main():
    from camoufox.async_api import AsyncCamoufox

    print("Opening Camoufox window (headed) with proxy", PROXY["server"])
    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        disable_coop=True,
        headless=False,
        proxy=PROXY,
    ) as browser:
        page = await browser.new_page()

        print("Navigating to Quotex sign-in...")
        try:
            await page.goto(
                "https://market-qx.trade/en/sign-in/",
                wait_until="domcontentloaded", timeout=120000
            )
        except Exception as e:
            print(f"goto error: {e}")
        print(f"URL: {page.url} | Title: {await page.title()}")
        await asyncio.sleep(5)

        if "Just a moment" in await page.title():
            print("Cloudflare detected, waiting up to 2 min...")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')",
                    timeout=120000
                )
            except Exception:
                pass

        await asyncio.sleep(3)
        result = await page.evaluate(
            """
            (args) => {
                var emails = document.querySelectorAll('input[name="email"]');
                var passes = document.querySelectorAll('input[name="password"]');
                if (!emails.length || !passes.length) return "no inputs found";
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
            [EMAIL, PASSWORD]
        )
        print(f"Login: {result}")
        await asyncio.sleep(8)
        print(f"URL after login: {page.url}")

        from renew_ssid import auto_read_otp_sync
        from datetime import datetime, timezone, timedelta
        login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)

        if "/sign-in" in page.url.lower():
            print("Checking for OTP input...")
            otp_el = None
            for _ in range(8):
                try:
                    otp_el = await page.query_selector(
                        'input[name="code"], input[name="otp"], '
                        'input[autocomplete="one-time-code"]'
                    )
                except Exception:
                    otp_el = None
                if otp_el:
                    break
                await asyncio.sleep(3)
            if otp_el:
                otp = await asyncio.to_thread(auto_read_otp_sync, timeout=120, since=login_ts)
                if otp:
                    await otp_el.fill(otp)
                    print(f"OTP submitted: {otp}")
                    await asyncio.sleep(6)
                else:
                    print("No OTP read")
            else:
                print("No OTP input found")

        print("Navigating to trade page...")
        try:
            await page.goto(
                "https://market-qx.trade/en/trade",
                wait_until="domcontentloaded", timeout=60000
            )
        except Exception as e:
            print(f"trade goto error: {e}")
        await asyncio.sleep(5)
        print(f"Trade URL: {page.url}")

        token = await page.evaluate(
            """
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
                return null;
            }
            """
        )
        if token:
            print(f"SUCCESS: token={token[:12]}...{token[-4:]}")
            from renew_ssid import save_session
            ua = await page.evaluate("navigator.userAgent")
            save_session(EMAIL, token, ua)
        else:
            print("FAILED: no token")

        print("Window stays open 30s so you can watch...")
        await asyncio.sleep(30)


asyncio.run(main())
