"""Full login + token extraction test with proxy."""

import asyncio, os
from dotenv import load_dotenv
load_dotenv()

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")
PROXY = {"server": "socks5://121.169.46.116:1090"}

async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True, geoip=True, disable_coop=True,
        proxy=PROXY,
    ) as browser:
        page = await browser.new_page()

        print("Navigating to Quotex sign-in...")
        await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=120000)
        title = await page.title()
        print(f"Title: {title}")

        if "Just a moment" in title:
            print("Cloudflare detected, waiting...")
            await page.wait_for_function("() => !document.title.includes('Just a moment')", timeout=120000)
            print("Cloudflare passed")

        await asyncio.sleep(3)

        # Fill login form
        result = await page.evaluate(
            """
            (args) => {
                var emails = document.querySelectorAll('input[name="email"]');
                var passes = document.querySelectorAll('input[name="password"]');
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
        print("Waiting for OTP entry (you have 2 minutes)...")
        try:
            await page.wait_for_url("**/trade**", timeout=120000)
            print("Login successful, redirected to trade")
        except Exception:
            print("Timeout, trying direct navigation...")
            await page.goto("https://market-qx.trade/en/trade", wait_until="domcontentloaded", timeout=60000)

        print(f"Trade URL: {page.url}")

        # Extract token
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
            print("FAILED: no token returned")

asyncio.run(main())
