"""Test Patchright with native Playwright fill/click (human-like events)."""

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
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,720",
            ]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await ctx.new_page()

        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded", timeout=60000
        )
        print(f"Title: {await page.title()}")

        if "Just a moment" in await page.title():
            print("CF detected, waiting...")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')",
                    timeout=120000
                )
            except Exception:
                pass

        await asyncio.sleep(2)

        # Use native Playwright methods instead of JS evaluate
        try:
            # Find visible email input (second one)
            emails = await page.query_selector_all('input[name="email"]')
            if len(emails) > 1:
                await emails[1].fill(EMAIL)
            else:
                await emails[0].fill(EMAIL)

            passes = await page.query_selector_all('input[name="password"]')
            if len(passes) > 1:
                await passes[1].fill(PASSWORD)
            else:
                await passes[0].fill(PASSWORD)

            print("Fields filled via native Playwright API")

            # Click visible Sign in button
            buttons = await page.query_selector_all('button')
            clicked = False
            for b in buttons:
                text = await b.text_content()
                if text and text.strip() == "Sign in":
                    visible = await b.is_visible()
                    if visible:
                        await b.click()
                        clicked = True
                        print("Clicked Sign in via native Playwright API")
                        break
            if not clicked:
                print("Sign in button not found via native API")
        except Exception as e:
            print(f"Native interaction failed: {e}")
            # Fallback to JS
            r = await page.evaluate(
                """
                (args) => {
                    var es = document.querySelectorAll('input[name="email"]');
                    var ps = document.querySelectorAll('input[name="password"]');
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
            print(f"JS fallback: {r}")

        await asyncio.sleep(10)
        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        token = await page.evaluate(
            """
            () => {
                try { if (window.settings && window.settings.token) return window.settings.token; } catch(e) {}
                try { var s = document.cookie.match(/ssid=([^;]+)/); return s ? s[1] : null; } catch(e) {}
                return null;
            }
            """
        )
        print(f"Token: {token}")

        for c in await ctx.cookies():
            print(f"  Cookie: {c['name']} = {c['value'][:60]}")

        await browser.close()


asyncio.run(test())
