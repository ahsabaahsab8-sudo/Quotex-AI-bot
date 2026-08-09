"""Quick test: provided proxy + Camoufox + Quotex login + token extraction."""

import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")

PROXY_HTTP = {
    "server": "http://178.104.94.136:35069",
    "username": "DVS7ibIvyh",
    "password": "NQmMehp",
}
PROXY_SOCKS = {
    "server": "socks5://178.104.94.136:35069",
    "username": "DVS7ibIvyh",
    "password": "NQmMehp",
}


async def check_ip(page):
    try:
        resp = await page.goto("https://api.ipify.org", wait_until="domcontentloaded", timeout=30000)
        text = await page.text_content("body")
        print(f"  Proxy IP: {text}")
        return text
    except Exception as e:
        print(f"  IP check failed: {e}")
        return None


async def run_with_proxy(proxy, label):
    print(f"\n===== TEST PROXY: {label} =====")
    from camoufox.async_api import AsyncCamoufox
    try:
        async with AsyncCamoufox(
            humanize=True,
            geoip=True,
            disable_coop=True,
            headless=True,
            proxy=proxy,
        ) as browser:
            page = await browser.new_page()
            ip = await check_ip(page)
            if not ip:
                print("  PROXY FAILED - cannot reach internet")
                return
            print(f"  Proxy reachable from {label}")
            await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=120000)
            title = await page.title()
            print(f"  Sign-in title: {title}")
            if "Just a moment" in title:
                print("  Cloudflare detected, waiting...")
                try:
                    await page.wait_for_function(
                        "() => !document.title.includes('Just a moment')", timeout=60000)
                    print("  Cloudflare passed")
                except Exception:
                    print("  Cloudflare still active, continuing...")
            await asyncio.sleep(3)
            result = await page.evaluate(
                """(args) => {
                    var emails = document.querySelectorAll('input[name="email"]');
                    var passes = document.querySelectorAll('input[name="password"]');
                    var email = emails.length > 1 ? emails[1] : emails[0];
                    var pass = passes.length > 1 ? passes[1] : passes[0];
                    if (!email || !pass) return "no inputs found";
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
                }""",
                [EMAIL, PASSWORD],
            )
            print(f"  Login: {result}")
            print("  Waiting for redirect to /trade (max 2 min)...")
            try:
                await page.wait_for_url("**/trade**", timeout=120000)
                print("  -> On trade page")
            except Exception:
                print("  Timeout; current URL: " + page.url)
                try:
                    await page.goto("https://market-qx.trade/en/trade", wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(5)
                except Exception as e:
                    print(f"  Manual nav failed: {e}")

            token = await page.evaluate(
                """() => {
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
                }"""
            )
            if token:
                print(f"  SUCCESS TOKEN: {token[:16]}...{token[-4:]} (len={len(token)})")
            else:
                print("  FAILED: no token")
                info = await page.evaluate(
                    """() => {
                        var r = {};
                        r.url = location.href;
                        r.title = document.title;
                        r.settings = window.settings ? Object.keys(window.settings).join(',') : 'undefined';
                        r.cookies = document.cookie;
                        return r;
                    }"""
                )
                for k, v in info.items():
                    print(f"    {k}: {str(v)[:300]}")
                cookies = await page.context.cookies()
                important = [(c["name"], c["value"][:15]) for c in cookies
                             if any(k in c["name"].lower() for k in ["ssid", "token", "session", "cf"])]
                print(f"    Important cookies: {important}")
    except Exception as e:
        import traceback
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("http", "both"):
        await run_with_proxy(PROXY_HTTP, "HTTP proxy")
    if mode in ("socks", "both"):
        await run_with_proxy(PROXY_SOCKS, "SOCKS5 proxy")


asyncio.run(main())
