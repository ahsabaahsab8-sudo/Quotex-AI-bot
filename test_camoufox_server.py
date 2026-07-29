"""Test Camoufox: block redirect to qxbroker.com, stay on market-qx.trade"""
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

        # Block qxbroker.com redirects via route interception
        async def handle_route(route):
            url = route.request.url
            if "qxbroker.com" in url:
                print(f"  BLOCKED redirect to: {url}")
                await route.abort()
            else:
                await route.continue_()

        page = await browser.new_page()
        await page.route("**/*", handle_route)

        print("\n1. Navigate to market-qx.trade/en/sign-in/...")
        try:
            await page.goto(
                "https://market-qx.trade/en/sign-in/",
                wait_until="domcontentloaded",
                timeout=120000
            )
        except Exception as e:
            print(f"   Navigation error (expected if redirect blocked): {e}")

        await asyncio.sleep(5)
        print(f"   URL: {page.url}")
        print(f"   Title: {await page.title()}")

        if "Just a moment" in await page.title():
            print("   Cloudflare challenge... waiting")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')",
                    timeout=120000
                )
            except:
                print("   Cloudflare still active")

        await asyncio.sleep(3)

        print("\n2. Fill login form...")
        # Check what inputs exist
        inputs = await page.evaluate("""() => {
            var emails = document.querySelectorAll('input[name="email"]');
            var passes = document.querySelectorAll('input[name="password"]');
            return {
                email_count: emails.length,
                pass_count: passes.length,
                email0_visible: emails.length > 0 ? emails[0].offsetParent !== null : false,
                email1_visible: emails.length > 1 ? emails[1].offsetParent !== null : false,
                page_url: window.location.href
            };
        }""")
        print(f"   Inputs: {inputs}")

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

        # Wait for redirect
        for i in range(30):
            await asyncio.sleep(2)
            url = page.url
            print(f"   [{i*2+2}s] {url}")
            if "/trade" in url:
                print("   -> ON TRADE PAGE!")
                break

        # Try manual navigation
        if "/trade" not in page.url:
            print("\n3. Trying /trade manually...")
            try:
                await page.goto(
                    "https://market-qx.trade/en/trade",
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                await asyncio.sleep(5)
            except Exception as e:
                print(f"   Manual navigation failed: {e}")
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
            print(f"   Cookies: {[(c['name'], c['value'][:15]) for c in await page.context.cookies()]}")


asyncio.run(main())
