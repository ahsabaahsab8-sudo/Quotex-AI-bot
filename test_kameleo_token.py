import asyncio
import json
from playwright.async_api import async_playwright
from kameleo.local_api_client import KameleoLocalApiClient
from kameleo.local_api_client.models.create_profile_request import CreateProfileRequest

QUOTEX_EMAIL = "slamismail8@gmail.com"
QUOTEX_PASSWORD = "35689023Ahsan@"

async def main():
    client = KameleoLocalApiClient(endpoint="http://localhost:5050")
    fingerprints = client.fingerprint.search_fingerprints("desktop", None, "chrome")
    profile = client.profile.create_profile(CreateProfileRequest(fingerprint_id=fingerprints[0].id))
    print(f"Kameleo profile: {profile.id}")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"ws://localhost:5050/playwright/{profile.id}")
        page = await browser.contexts[0].new_page()

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

        # Use JS to fill the VISIBLE inputs (second set, not the hidden trap)
        result = await page.evaluate(
            """
            (args) => {
                var emails = document.querySelectorAll('input[name="email"]');
                var passes = document.querySelectorAll('input[name="password"]');
                if (emails.length < 2 || passes.length < 2) return "not enough inputs: emails=" + emails.length + " passes=" + passes.length;

                // Use visible inputs (second set)
                var email = emails[1];
                var pass = passes[1];
                email.value = args[0];
                pass.value = args[1];
                email.dispatchEvent(new Event('input', { bubbles: true }));
                pass.dispatchEvent(new Event('input', { bubbles: true }));

                // Find visible Sign In button
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

        print(f"Trade URL: {page.url}")
        print(f"Trade title: {await page.title()}")

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

        # Check all cookies for ssid
        cookies = await browser.contexts[0].cookies()
        for c in cookies:
            if "ssid" in c["name"].lower():
                print(f"*** FOUND SSID: {c['name']} = {c['value'][:60]} ***")

        print("\nAll cookies:")
        for c in cookies:
            print(f"  {c['name']} = {c['value'][:60]}")

        await asyncio.sleep(2)

    client.profile.stop_profile(profile.id)
    client.profile.delete_profile(profile.id)
    print("Done")

asyncio.run(main())
