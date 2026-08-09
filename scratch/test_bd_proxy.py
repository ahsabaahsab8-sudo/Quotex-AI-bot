"""Test Bangladesh proxy with Camoufox - single proxy test."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")

PROXY = "socks5://123.136.24.161:1080"
COUNTRY = "Bangladesh"

LOGIN_JS = """
(args) => {
    var emails = document.querySelectorAll('input[name="email"]');
    var passes = document.querySelectorAll('input[name="password"]');
    if (!emails.length || !passes.length) return 'no inputs found';
    var email = emails[emails.length > 1 ? 1 : 0];
    var pass = passes[passes.length > 1 ? 1 : 0];
    email.value = args[0];
    pass.value = args[1];
    email.dispatchEvent(new Event('input', {bubbles: true}));
    pass.dispatchEvent(new Event('input', {bubbles: true}));
    var buttons = document.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
        var b = buttons[i];
        if (b.textContent.trim() === 'Sign in' && b.offsetParent !== null) {
            b.click();
            return 'clicked Sign in';
        }
    }
    return 'Sign in button not found';
}
"""

TOKEN_JS = """
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
    return null;
}
"""

async def main():
    from camoufox.async_api import AsyncCamoufox

    print(f"Testing {COUNTRY} proxy: {PROXY}")
    print(f"Email: {EMAIL}")

    try:
        async with AsyncCamoufox(
            headless=True,
            humanize=True,
            geoip=False,
            disable_coop=True,
            proxy={"server": PROXY},
        ) as browser:
            print("Browser launched OK!")
            page = await browser.new_page()

            print("Navigating to sign-in page...")
            try:
                await page.goto(
                    "https://market-qx.trade/en/sign-in/",
                    wait_until="domcontentloaded",
                    timeout=60000  # 1 minute timeout
                )
            except Exception as e:
                print(f"Navigation failed: {e}")
                return

            title = await page.title()
            print(f"Page title: {title}")
            print(f"Current URL: {page.url}")

            if "Just a moment" in title:
                print("Cloudflare detected, waiting up to 30s...")
                try:
                    await page.wait_for_function(
                        "() => !document.title.includes('Just a moment')",
                        timeout=30000
                    )
                    print("Cloudflare passed!")
                except Exception:
                    print("Cloudflare still active, continuing anyway...")

            await asyncio.sleep(20)  # 20s wait for React to fully render

            # Wait explicitly for the email input to appear
            print("Waiting for email input to appear...")
            try:
                await page.wait_for_selector('input[name="email"]', timeout=60000)  # 1 minute
                print("Email input found!")
            except Exception:
                print("Email input NOT found after 20s wait, trying anyway...")

            result = await page.evaluate(LOGIN_JS, [EMAIL, PASSWORD])
            print(f"Login form result: {result}")

            await asyncio.sleep(20)  # 20s wait after clicking sign in

            if "/trade" not in page.url:
                print("Not on trade page, navigating...")
                try:
                    await page.goto(
                        "https://market-qx.trade/en/trade",
                        wait_until="domcontentloaded",
                        timeout=60000  # 1 minute timeout
                    )
                    await asyncio.sleep(20)  # 20s wait for trade page to fully load
                except Exception as e:
                    print(f"Trade nav failed: {e}")

            print(f"Final URL: {page.url}")
            print(f"Final Title: {await page.title()}")

            token = await page.evaluate(TOKEN_JS)
            if token:
                print(f"\nSUCCESS! Token: {token[:16]}...{token[-4:]}")
                print(f"Proxy {COUNTRY} ({PROXY}) WORKS for Quotex!")
            else:
                print("\nFAILED: Token is None - login did not succeed")
                # Debug info
                info = await page.evaluate("""
                    () => ({
                        cookies: document.cookie.substring(0, 200),
                        settingsKeys: window.settings ? Object.keys(window.settings).join(',') : 'undefined',
                        url: window.location.href
                    })
                """)
                print(f"Debug - cookies: {info['cookies']}")
                print(f"Debug - settings keys: {info['settingsKeys']}")
                print(f"Debug - url: {info['url']}")

    except Exception as e:
        print(f"FAILED with exception: {e}")

asyncio.run(main())
