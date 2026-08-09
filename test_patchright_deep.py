"""Deep test of Patchright token extraction."""

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

        await page.goto(
            "https://market-qx.trade/en/sign-in/",
            wait_until="domcontentloaded", timeout=60000
        )
        t = await page.title()
        print(f"Title: {t}")

        if "Just a moment" in t:
            print("CF detected, waiting...")
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment')",
                    timeout=120000
                )
                print("CF passed")
            except Exception:
                print("CF still active, continuing anyway")

        await asyncio.sleep(3)

        # Login
        r = await page.evaluate(
            """
            (args) => {
                var es = document.querySelectorAll('input[name="email"]');
                var ps = document.querySelectorAll('input[name="password"]');
                if (!es.length || !ps.length) return 'no inputs';
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
        await asyncio.sleep(10)
        print(f"URL after login: {page.url}")

        # Navigate to trade with networkidle
        await page.goto(
            "https://market-qx.trade/en/trade",
            wait_until="networkidle", timeout=60000
        )
        print(f"Trade URL: {page.url}")
        print(f"Trade title: {await page.title()}")
        await asyncio.sleep(5)

        # Inspect page state
        info = await page.evaluate(
            """
            () => {
                var r = {};
                r.settings = typeof window.settings;
                r.settingsValue = window.settings ? JSON.stringify(window.settings).substring(0, 500) : 'N/A';
                try { r.localStorage = JSON.stringify(window.localStorage).substring(0, 1000); } catch(e) { r.localStorage = 'err: ' + e; }
                try { r.sessionStorage = JSON.stringify(window.sessionStorage).substring(0, 1000); } catch(e) { r.sessionStorage = 'err: ' + e; }
                r.cookies = document.cookie;
                r.ssidCookie = (document.cookie.match(/ssid=([^;]+)/) || [null, null])[1];

                var globals = [];
                for (var k in window) {
                    if (k.includes('nuxt') || k.includes('vuex') || k.includes('store') || k.includes('auth') || k.includes('token') || k.includes('setting')) {
                        globals.push(k);
                    }
                }
                r.matchingGlobals = JSON.stringify(globals);

                var scripts = document.querySelectorAll('script');
                var tokenScripts = [];
                for (var i = 0; i < scripts.length; i++) {
                    var t = scripts[i].textContent || '';
                    if (t.includes('token') || t.includes('ssid')) {
                        var m1 = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                        var m2 = t.match(/ssid["']?\\s*[:=]\\s*["']([^"']+)["']/);
                        if (m1 || m2) {
                            tokenScripts.push({
                                idx: i,
                                token: m1 ? m1[1] : null,
                                ssid: m2 ? m2[1] : null,
                                src: (scripts[i].src || 'inline').substring(0, 100)
                            });
                        }
                    }
                }
                r.tokenScripts = JSON.stringify(tokenScripts);
                return r;
            }
            """
        )
        print("\n=== PAGE STATE ===")
        for k, v in info.items():
            print(f"{k}: {v}")

        # Check all cookies via Playwright API
        print("\n=== ALL COOKIES (Playwright API) ===")
        cookies = await ctx.cookies()
        for c in cookies:
            print(f"  {c['name']} = {c['value'][:80]}")

        await browser.close()


asyncio.run(test())
