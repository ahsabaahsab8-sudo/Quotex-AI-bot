"""Debug why login fails on qxbroker.com (server's forced domain)."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        headless=True,
        disable_coop=True,
    ) as browser:
        page = await browser.new_page()

        # Track XHR/fetch requests
        api_calls = []

        async def track_request(req):
            if req.method == "POST":
                api_calls.append({
                    "url": req.url[:120],
                    "method": req.method,
                    "headers": dict(req.headers),
                })

        page.on("request", track_request)

        print("1. Navigate to qxbroker.com/sign-in...")
        await page.goto("https://qxbroker.com/en/sign-in/",
                        wait_until="load", timeout=120000)
        await asyncio.sleep(3)
        print(f"   URL: {page.url}")

        if "Just a moment" in await page.title():
            print("   Cloudflare... waiting")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')", timeout=120000)
            except:
                print("   Cloudflare still up")

        await asyncio.sleep(2)

        print(f"2. Fill form with {EMAIL}")
        # Use native InputEvent for better compatibility
        r = await page.evaluate(
            """(args) => {
                var e = document.querySelectorAll('input[name="email"]');
                var p = document.querySelectorAll('input[name="password"]');
                var email = e.length > 1 ? e[1] : e[0];
                var pass = p.length > 1 ? p[1] : p[0];
                if (!email || !pass) return "no inputs";

                // Native setter
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(email, args[0]);
                email.dispatchEvent(new InputEvent('input', { bubbles: true }));
                nativeInputValueSetter.call(pass, args[1]);
                pass.dispatchEvent(new InputEvent('input', { bubbles: true }));

                // Also set directly
                email.value = args[0];
                pass.value = args[1];

                var btn = Array.from(document.querySelectorAll('button')).find(
                    b => b.textContent.trim() === 'Sign in' && b.offsetParent !== null
                );
                if (btn) {
                    btn.click();
                    return 'clicked';
                }
                return 'no button';
            }""",
            [EMAIL, PASSWORD]
        )
        print(f"   Result: {r}")

        await asyncio.sleep(3)

        # Check what POST requests were made
        print(f"\n3. POST requests made: {len(api_calls)}")
        for c in api_calls:
            print(f"   POST {c['url']}")
        api_calls.clear()

        # Wait longer and track
        for i in range(20):
            await asyncio.sleep(1)
            if api_calls:
                for c in api_calls:
                    print(f"   [{i+3}s] POST {c['url']}")
                api_calls.clear()

            if "/trade" in page.url:
                print(f"   [{i+3}s] ON TRADE PAGE!")
                break
            if i % 5 == 0:
                print(f"   [{i+3}s] {page.url}")

        print(f"\n4. Final URL: {page.url}")
        print(f"   Title: {await page.title()}")

        # Try to get token
        token = await page.evaluate(
            "() => { try { return window.settings && window.settings.token ? window.settings.token : null; } catch(e) { return null; } }"
        )
        if token:
            print(f"5. TOKEN: {token[:12]}...{token[-4:]}")
        else:
            print("5. No token. Checking page state...")
            state = await page.evaluate("""() => ({
                url: window.location.href,
                settings: window.settings ? Object.keys(window.settings).join(',') : 'no settings',
                has_ssid_cookie: (document.cookie.match(/ssid=([^;]+)/) || [null])[1] ? true : false,
                cookies: document.cookie.split(';').map(c => c.trim().split('=')[0]),
                scripts: document.querySelectorAll('script').length
            })""")
            print(f"   State: {state}")

        cookies = await page.context.cookies()
        ssid_cookies = [c for c in cookies if 'ssid' in c['name'].lower()]
        print(f"\n   SSID cookies: {[f'{c[\"name\"]}={c[\"value\"][:15]}...' for c in ssid_cookies]}")
        print(f"   Total cookies: {len(cookies)}")


asyncio.run(main())
