"""Test Camoufox token extraction on Railway server."""
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        headless=True,
    ) as browser:
        page = await browser.new_page()

        print("Navigating to sign-in...")
        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded",
            timeout=120000
        )
        await asyncio.sleep(3)

        # Fill login form
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
        print("Login:", r)
        await asyncio.sleep(10)
        print("URL:", page.url)

        if "/trade" not in page.url:
            await page.goto(
                "https://market-qx.trade/en/trade",
                wait_until="domcontentloaded",
                timeout=60000
            )
            await asyncio.sleep(5)

        token = await page.evaluate(
            """() => {
                try { if (window.settings && window.settings.token) return window.settings.token; } catch(e) {}
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
                try { var c = document.cookie.match(/ssid=([^;]+)/); return c ? c[1] : null; } catch(e) {}
                return null;
            }"""
        )

        if token:
            print("TOKEN:", token[:12] + "..." + token[-4:])
        else:
            print("FAILED: no token extracted")
            info = await page.evaluate("""() => {
                return {
                    settings: window.settings ? 'exists' : 'undefined',
                    cookies: document.cookie ?
                        document.cookie.split(';').map(c=>c.trim().split('=')[0]).join(',') : 'none'
                };
            }""")
            print("Debug:", info)


asyncio.run(main())
