"""Test Camoufox token extraction on Railway server."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        headless=True,
        disable_coop=True,
    ) as browser:
        page = await browser.new_page()

        print("1. Navigate to sign-in...")
        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded",
            timeout=120000
        )
        print("   Title:", await page.title())

        # Wait for page to fully stabilize
        await asyncio.sleep(5)

        # Fill and submit login
        print("2. Fill login form...")
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
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    if (buttons[i].textContent.trim() === 'Sign in' && buttons[i].offsetParent !== null) {
                        buttons[i].click();
                        return 'clicked';
                    }
                }
                return 'button not found';
            }""",
            [os.getenv("QUOTEX_EMAIL"), os.getenv("QUOTEX_PASSWORD")]
        )
        print("   Login:", r)

        # Wait for navigation/redirect loop
        for i in range(30):
            await asyncio.sleep(2)
            current = page.url
            print(f"   [{i*2+2}s] {current}")
            title = await page.title()
            if "trade" in current.lower() or "Live trading" in title:
                print("   -> ON TRADE PAGE!")
                break
            if "/sign-in" not in current.lower() and "login" not in current.lower():
                # Maybe we landed somewhere else - try /trade
                print(f"   -> Landed on: {current}, trying /trade...")
                await page.goto("https://market-qx.trade/en/trade",
                                wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)
                if "trade" in page.url.lower():
                    break

        # If we are on qxbroker.com, try navigating to trade
        if "qxbroker.com" in page.url and "/trade" not in page.url:
            print("3. On qxbroker.com, navigating to market-qx.trade/trade...")
            await page.goto("https://market-qx.trade/en/trade",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

        print(f"4. Final URL: {page.url}")
        print(f"   Title: {await page.title()}")

        # Extract token
        token = await page.evaluate("() => { try { return window.settings && window.settings.token ? window.settings.token : null; } catch(e) { return null; } }")
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
            token = await page.evaluate("() => { try { var c = document.cookie.match(/ssid=([^;]+)/); return c ? c[1] : null; } catch(e) { return null; } }")
        if not token:
            cookies = await page.context.cookies()
            for c in cookies:
                if "ssid" in c["name"].lower():
                    token = c["value"]
                    break

        if token:
            print(f"5. TOKEN: {token[:12]}...{token[-4:]}")
        else:
            print("5. FAILED: no token")
            important_cookies = [(c['name'], c['value'][:20]) for c in await page.context.cookies()
                                 if any(k in c['name'].lower() for k in ['ssid', 'token', 'session', 'cf'])]
            print(f"   Important cookies: {important_cookies}")


asyncio.run(main())
