import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")

PROXIES = [
    # Saudi Arabia (First priority)
    ("Saudi Arabia", "http://34.166.25.120:8080"),
    ("UAE", "http://47.91.104.88:3128"),
    ("Singapore", "http://143.42.66.91:80"),
    ("Austria", "http://213.33.126.130:80"),
    ("Germany", "http://47.91.65.23:3128"),
    ("Finland (999)", "http://65.108.159.129:999"),
    ("Finland (4145)", "http://65.108.159.129:4145"),
    ("Finland (3128)", "http://65.108.159.129:3128"),
    ("Finland (5153)", "http://65.108.159.129:5153"),
    ("India", "http://20.204.43.57:80"),
    ("Ecuador", "http://45.186.6.104:3128"),
    ("Trinidad & Tobago", "http://190.58.248.86:80"),
]

async def test_proxy(name, proxy_url):
    print(f"\n==========================================")
    print(f"Testing Proxy: {name} ({proxy_url})")
    print(f"==========================================")
    from camoufox.async_api import AsyncCamoufox

    proxy_cfg = {"server": proxy_url}
    try:
        async with AsyncCamoufox(
            humanize=True,
            geoip=False, # Disable geoip lookup to prevent crash on ip lookup
            disable_coop=True,
            headless=True,
            proxy=proxy_cfg,
        ) as browser:
            page = await browser.new_page()
            print(f"[{name}] Navigating to Quotex sign-in...")
            try:
                resp = await page.goto(
                    "https://market-qx.trade/en/sign-in/",
                    wait_until="domcontentloaded", timeout=25000
                )
            except Exception as e:
                print(f"[{name}] FAILED: Navigation error/timeout: {e}")
                return False, None

            title = await page.title()
            print(f"[{name}] Title: {title}")

            if "Just a moment" in title:
                print(f"[{name}] Cloudflare challenge detected, waiting...")
                try:
                    await page.wait_for_function(
                        "() => !document.title.includes('Just a moment')",
                        timeout=30000
                    )
                    print(f"[{name}] Cloudflare passed!")
                except Exception:
                    print(f"[{name}] Cloudflare timeout.")

            await asyncio.sleep(2)

            # Fill login form
            login_result = await page.evaluate(
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
                [EMAIL, PASSWORD]
            )
            print(f"[{name}] Form login action: {login_result}")
            await asyncio.sleep(5)

            # Navigate to trade page if not there
            if "/trade" not in page.url:
                try:
                    await page.goto(
                        "https://market-qx.trade/en/trade",
                        wait_until="domcontentloaded", timeout=30000
                    )
                    await asyncio.sleep(3)
                except Exception:
                    pass

            print(f"[{name}] Final URL: {page.url}")

            # Extract token
            extract_js = """
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
            token = await page.evaluate(extract_js)
            if token:
                print(f"[{name}] 🎉 SUCCESS! Token extracted: {token[:12]}...{token[-4:]}")
                return True, token
            else:
                print(f"[{name}] FAILED: Token was None")
                return False, None

    except Exception as e:
        print(f"[{name}] FAILED with exception: {e}")
        return False, None

async def main():
    print(f"Starting test for {len(PROXIES)} proxies with Camoufox...")
    results = {}
    for name, proxy_url in PROXIES:
        success, token = await test_proxy(name, proxy_url)
        results[name] = "WORKING (Token extracted)" if success else "FAILED"
        if success:
            print(f"\n🎉 FOUND WORKING PROXY: {name} -> {proxy_url}")

    print("\n================ FINAL RESULTS ================")
    for name, status in results.items():
        print(f"{name}: {status}")

if __name__ == "__main__":
    asyncio.run(main())
