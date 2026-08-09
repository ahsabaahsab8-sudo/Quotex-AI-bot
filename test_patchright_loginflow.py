"""Test Patchright - wait for natural redirect after login."""

import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")


async def test():
    from patchright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # Listen for navigation
        async def on_response(response):
            if response.status != 200:
                print(f"  [!] {response.status} {response.url[:100]}")

        page.on("response", on_response)

        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded", timeout=60000
        )
        print(f"Initial title: {await page.title()}")

        if "Just a moment" in await page.title():
            print("CF on sign-in, waiting...")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')",
                    timeout=120000
                )
            except Exception:
                pass

        await asyncio.sleep(2)
        print(f"URL before login: {page.url}")

        # Perform login
        r = await page.evaluate(
            """
            (args) => {
                var es = document.querySelectorAll('input[name="email"]');
                var ps = document.querySelectorAll('input[name="password"]');
                if (!es.length || !ps.length) return 'no inputs found';
                var e = es.length > 1 ? es[1] : es[0];
                var p = ps.length > 1 ? ps[1] : ps[0];
                e.value = args[0];
                p.value = args[1];
                e.dispatchEvent(new Event('input', {bubbles: true}));
                p.dispatchEvent(new Event('input', {bubbles: true}));
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    var b = btns[i];
                    if (b.textContent.trim() === 'Sign in' && b.offsetParent !== null) {
                        b.click();
                        return 'clicked';
                    }
                }
                return 'not found';
            }
            """,
            [EMAIL, PASSWORD]
        )
        print(f"Login: {r}")

        # Wait for navigation/redirect (natural flow)
        print("Waiting for redirect after login (max 30s)...")
        try:
            await page.wait_for_url(
                "**/trade**",
                timeout=30000
            )
            print(f"Redirected to: {page.url}")
        except Exception:
            print(f"No redirect. Current URL: {page.url}")

        # Also check if OTP page appeared
        if "/sign-in" in page.url.lower():
            print("Still on sign-in - checking for OTP...")
            otp_input = await page.query_selector('input[name="code"], input[name="otp"]')
            if otp_input:
                print("OTP input found!")
                # Try to read OTP from IMAP
                from renew_ssid import auto_read_otp_sync
                otp = await asyncio.to_thread(auto_read_otp_sync, timeout=60)
                if otp:
                    print(f"OTP: {otp}")
                    await otp_input.fill(otp)
                    # Wait for redirect after OTP
                    try:
                        await page.wait_for_url("**/trade**", timeout=30000)
                        print(f"After OTP redirect: {page.url}")
                    except Exception:
                        print("No redirect after OTP")
                else:
                    print("No OTP found via IMAP")
            else:
                print("No OTP input found")

        # Check current page state
        print(f"\nFinal URL: {page.url}")
        print(f"Final title: {await page.title()}")

        # Try token extraction regardless
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
        print(f"Token: {token[:40] if token else 'None'}")

        # All cookies
        print("\nCookies:")
        for c in await ctx.cookies():
            print(f"  {c['name']} = {c['value'][:80]}")

        await browser.close()


asyncio.run(test())
