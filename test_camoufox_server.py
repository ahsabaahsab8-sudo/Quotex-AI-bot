"""Test Camoufox: block nav redirect to qxbroker.com, keep page on market-qx.trade."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")
print(f"EMAIL: {'OK' if EMAIL else 'MISSING'}")
print(f"PASS: {'OK' if PASSWORD else 'MISSING'}")


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        headless=True,
        disable_coop=True,
    ) as browser:
        page = await browser.new_page()

        # Block only navigation redirects to qxbroker.com, allow resources
        async def block_nav_redirect(route):
            url = route.request.url
            if "qxbroker.com" in url and route.request.resource_type == "document":
                print(f"  BLOCKED nav redirect: {url}")
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", block_nav_redirect)

        print("1. Navigate to market-qx.trade/sign-in...")
        try:
            await page.goto(
                "https://market-qx.trade/en/sign-in/",
                wait_until="domcontentloaded", timeout=120000
            )
        except Exception as e:
            print(f"   Nav result: {e}")
        print(f"   URL: {page.url}")

        # Retry if redirected
        if "qxbroker.com" in page.url:
            print("   -> Was redirected. Retrying with block active...")
            await page.goto("about:blank", wait_until="domcontentloaded")
            await asyncio.sleep(1)
            try:
                await page.goto(
                    "https://market-qx.trade/en/sign-in/",
                    wait_until="domcontentloaded", timeout=120000
                )
            except Exception:
                pass
            print(f"   URL after retry: {page.url}")

        title = await page.title()
        print(f"   Title: {title}")

        if "Just a moment" in title:
            print("   Cloudflare challenge... waiting")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')", timeout=120000)
            except:
                print("   Cloudflare still active")

        await asyncio.sleep(3)

        print("2. Fill login form...")
        r = await page.evaluate(
            """(args) => {
                var e = document.querySelectorAll('input[name="email"]');
                var p = document.querySelectorAll('input[name="password"]');
                var email = e.length > 1 ? e[1] : e[0];
                var pass = p.length > 1 ? p[1] : p[0];
                if (!email || !pass) return "no inputs";
                email.value = args[0];
                pass.value = args[1];
                email.dispatchEvent(new Event('input', { bubbles: true }));
                pass.dispatchEvent(new Event('input', { bubbles: true }));
                var btn = Array.from(document.querySelectorAll('button')).find(
                    b => b.textContent.trim() === 'Sign in' && b.offsetParent !== null
                );
                if (btn) { btn.click(); return 'clicked'; }
                return 'no button';
            }""",
            [EMAIL, PASSWORD]
        )
        print(f"   Login: {r}")

        for i in range(30):
            await asyncio.sleep(2)
            url = page.url
            print(f"   [{i*2+2}s] {url}")
            if "/trade" in url:
                print("   -> ON TRADE!")
                break
            if i == 10 and "/trade" not in url:
                print("   -> Trying /trade manually...")
                try:
                    await page.goto("https://market-qx.trade/en/trade",
                                    wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(5)
                except Exception:
                    pass

        print(f"\n3. Final URL: {page.url}")
        print(f"   Title: {await page.title()}")

        token = await page.evaluate(
            "() => { try { return window.settings && window.settings.token ? window.settings.token : null; } catch(e) { return null; } }"
        )
        if not token:
            token = await page.evaluate("""() => {
                try {
                    var s = document.querySelectorAll('script');
                    for (var i = 0; i < s.length; i++) {
                        var t = s[i].textContent;
                        if (t && t.includes('token')) {
                            var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                            if (m) return m[1];
                        }
                    }
                } catch(e) {}
                return null;
            }""")
        if not token:
            token = await page.evaluate(
                "() => { try { var c = document.cookie.match(/ssid=([^;]+)/); return c ? c[1] : null; } catch(e) { return null; } }")
        if not token:
            cookies = await page.context.cookies()
            for c in cookies:
                if "ssid" in c["name"].lower():
                    token = c["value"]
                    break

        if token:
            print(f"\n4. TOKEN: {token[:12]}...{token[-4:]}")
        else:
            print("\n4. FAILED: no token")
            important = [(c['name'], c['value'][:15]) for c in await page.context.cookies()
                         if any(k in c['name'].lower() for k in ['ssid', 'token', 'cf', 'session'])]
            print(f"   Important cookies: {important}")


asyncio.run(main())
