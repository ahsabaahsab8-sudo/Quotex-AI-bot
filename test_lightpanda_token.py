"""Test Lightpanda browser with Playwright to extract Quotex token."""
import asyncio
from playwright.async_api import async_playwright

QUOTEX_EMAIL = "slamismail8@gmail.com"
QUOTEX_PASSWORD = "35689023Ahsan@"

async def main():
    async with async_playwright() as p:
        # Connect to Lightpanda CDP server via Docker
        browser = await p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
        contexts = browser.contexts
        if contexts:
            page = await contexts[0].new_page()
        else:
            context = await browser.new_context()
            page = await context.new_page()

        print("Navigating to Quotex sign-in...")
        await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        title = await page.title()
        print(f"Title: {title}")

        html = await page.content()
        if "Just a moment" in html or "challenge" in html.lower()[:500]:
            print("*** CLOUDFLARE CHALLENGE DETECTED ***")
        else:
            print("No Cloudflare challenge - page loaded!")

        # Fill login form
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
            [QUOTEX_EMAIL, QUOTEX_PASSWORD]
        )
        print(f"Login result: {result}")
        await asyncio.sleep(7)

        print(f"After login URL: {page.url}")
        print(f"After login title: {await page.title()}")

        # Navigate to trade
        print("Navigating to /trade...")
        await page.goto("https://market-qx.trade/en/trade", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        # Extract token
        token = await page.evaluate("""
            () => {
                try { if (window.settings && window.settings.token) return window.settings.token; } catch(e) {}
                try {
                    var scripts = document.querySelectorAll('script');
                    for (var i = 0; i < scripts.length; i++) {
                        var t = scripts[i].textContent;
                        if (t.includes('token')) {
                            var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                            if (m) return m[1];
                        }
                    }
                } catch(e) {}
                try { return document.cookie; } catch(e) {}
                return null;
            }
        """)
        print(f"Token: {token}")

        await browser.close()

asyncio.run(main())
