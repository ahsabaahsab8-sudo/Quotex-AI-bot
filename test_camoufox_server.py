"""Test Camoufox token extraction from the REAL login page: market-qx.trade"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")
print(f"EMAIL loaded: {'YES' if EMAIL else 'NO'}")
print(f"PASS loaded: {'YES' if PASSWORD else 'NO'}")


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        headless=True,
        disable_coop=True,
    ) as browser:
        page = await browser.new_page()

        # Navigate to the REAL login page
        print("\n1. Navigate to market-qx.trade/en/sign-in/...")
        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="load",
            timeout=120000
        )
        print(f"   URL after load: {page.url}")
        await asyncio.sleep(3)
        print(f"   URL after 3s: {page.url}")
        print(f"   Title: {await page.title()}")

        # If redirected, log it
        if "qxbroker.com" in page.url:
            print("   -> Redirected to qxbroker.com! Checking DNS...")

        await asyncio.sleep(3)

        # Fill form on whatever page we're on
        print("\n2. Fill login form...")
        r = await page.evaluate(
            """(args) => {
                var e = document.querySelectorAll('input[name="email"]');
                var p = document.querySelectorAll('input[name="password"]');
                var email = e.length > 1 ? e[1] : e[0];
                var pass = p.length > 1 ? p[1] : p[0];
                if (!email || !pass) return "inputs not found";
                email.value = args[0];
                pass.value = args[1];
                email.dispatchEvent(new Event('input', { bubbles: true }));
                pass.dispatchEvent(new Event('input', { bubbles: true }));
                var btn = Array.from(document.querySelectorAll('button')).find(
                    b => b.textContent.trim() === 'Sign in' && b.offsetParent !== null
                );
                if (btn) { btn.click(); return 'clicked'; }
                return 'button not found';
            }""",
            [EMAIL, PASSWORD]
        )
        print(f"   Login: {r}")

        # Wait for redirect to /trade
        for i in range(30):
            await asyncio.sleep(2)
            url = page.url
            print(f"   [{i*2+2}s] {url}")
            if "/trade" in url:
                print("   -> ON TRADE PAGE!")
                break

        # Try navigating to /trade manually
        if "/trade" not in page.url:
            print("\n3. Login didn't redirect. Navigating to /trade manually...")
            await page.goto(
                "https://market-qx.trade/en/trade",
                wait_until="domcontentloaded",
                timeout=60000
            )
            await asyncio.sleep(5)
            print(f"   URL: {page.url}")

        print(f"\n4. Final URL: {page.url}")
        print(f"   Title: {await page.title()}")

        # Extract token
        token = await page.evaluate("() => { try { return window.settings && window.settings.token ? window.settings.token : null; } catch(e) { return null; } }")
        if not token:
            token = await page.evaluate("""() => {
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
                return null;
            }""")
        if not token:
            token = await page.evaluate("() => { try { var c = document.cookie.match(/ssid=([^;]+)/); return c ? c[1] : null; } catch(e) { return null; } }")
        if not token:
            cookies = await page.context.cookies()
            for c in cookies:
                if "ssid" in c["name"].lower():
                    token = c["value"]
                    break

        if token:
            print(f"\n5. TOKEN: {token[:12]}...{token[-4:]}")
        else:
            print("\n5. FAILED: no token")
            print(f"   All cookies: {[(c['name'], c['value'][:15]) for c in await page.context.cookies()]}")


asyncio.run(main())
