import os, re, json
import asyncio
from playwright.async_api import async_playwright

os.environ["QUOTEX_EMAIL"] = "slamismail8@gmail.com"
os.environ["QUOTEX_PASSWORD"] = "35689023Ahsan@"
os.environ["IMAP_EMAIL"] = "slamismail8@gmail.com"
os.environ["IMAP_PASSWORD"] = "erturulghazi786"

EMAIL = os.environ["QUOTEX_EMAIL"]
PASSWORD = os.environ["QUOTEX_PASSWORD"]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,720",
            ]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await ctx.new_page()

        # Intercept ALL network responses to find token
        captured = {}

        async def on_response(response):
            url = response.url
            try:
                if "token" in url.lower() or "ssid" in url.lower() or "login" in url.lower() or "sign" in url.lower() or "auth" in url.lower() or "session" in url.lower():
                    try:
                        body = await response.json()
                        captured[url] = body
                        print(f"[CAPTURED JSON] {url[:100]}: {json.dumps(body)[:300]}")
                    except:
                        text = await response.text()
                        if len(text) < 2000 and ("token" in text.lower() or "ssid" in text.lower()):
                            captured[url] = text[:500]
                            print(f"[CAPTURED TEXT] {url[:100]}: {text[:300]}")
            except:
                pass

        page.on("response", on_response)

        print("Navigating to sign-in...")
        await page.goto("https://market-qx.trade/en/sign-in/", wait_until="load", timeout=90000)

        # Wait for Cloudflare to clear
        for i in range(60):
            title = await page.title()
            if "Just a moment" not in title:
                print(f"Cloudflare cleared after {i}s, title: {title}")
                break
            await asyncio.sleep(1)
        else:
            print("Cloudflare still active after 60s")

        await asyncio.sleep(2)

        # Dump page content for debugging
        html = await page.content()
        print(f"Page HTML length: {len(html)}")

        # Check for iframes / shadow DOM
        frames = page.frames
        print(f"Frames count: {len(frames)}")

        # Try to find form
        for frame in frames:
            try:
                email_input = await frame.query_selector('input[name="email"]')
                if email_input:
                    print(f"Found form in frame: {frame.url}")
                    await email_input.fill(EMAIL)
                    pw_input = await frame.query_selector('input[name="password"]')
                    if pw_input:
                        await pw_input.fill(PASSWORD)
                    submit = await frame.query_selector('button[type="submit"]')
                    if submit:
                        # Intercept next navigation
                        async with page.expect_navigation(wait_until="load", timeout=30000) as nav_info:
                            await submit.click()
                        try:
                            resp = await nav_info.value
                            print(f"Navigation resulted in: {resp.url}")
                        except:
                            print("Navigation timeout - page may not have navigated")
                    else:
                        print("Submit button not found in frame")
                    break
            except Exception as e:
                print(f"Frame {frame.url}: {e}")
        else:
            print("Form not found in any frame, trying page directly")
            try:
                email_input = await page.query_selector('input[name="email"]')
                if email_input:
                    print("Found email input directly on page")
                    await email_input.fill(EMAIL)
                    pw_input = await page.query_selector('input[name="password"]')
                    if pw_input:
                        await pw_input.fill(PASSWORD)
                    submit = await page.query_selector('button[type="submit"]')
                    if submit:
                        async with page.expect_navigation(wait_until="load", timeout=30000) as nav_info:
                            await submit.click()
                        try:
                            resp = await nav_info.value
                            print(f"Navigation resulted in: {resp.url}")
                        except:
                            print("Navigation timeout")
            except Exception as e2:
                print(f"Page direct: {e2}")

        await asyncio.sleep(5)
        print(f"\nCurrent URL: {page.url}")
        print(f"Current title: {await page.title()}")

        # Check cookies
        cookies = await ctx.cookies()
        print(f"\nCookies ({len(cookies)}):")
        for c in cookies:
            if 'ssid' in c['name'].lower() or 'token' in c['name'].lower() or 'session' in c['name'].lower() or 'qx' in c['name'].lower():
                print(f"  {c['name']}: {c['value'][:50]}...")

        print(f"\nAll cookies:")
        for c in cookies:
            print(f"  {c['name']} = {c['value'][:60]}")

        # Check localStorage
        try:
            ls = await page.evaluate("JSON.stringify(window.localStorage)")
            print(f"\nlocalStorage: {ls[:500]}")
        except Exception as e:
            print(f"localStorage: {e}")

        # Check sessionStorage
        try:
            ss = await page.evaluate("JSON.stringify(window.sessionStorage)")
            print(f"\nsessionStorage: {ss[:500]}")
        except Exception as e:
            print(f"sessionStorage: {e}")

        # Try scripts
        try:
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
            print(f"\nScript extraction: {token}")
        except Exception as e:
            print(f"Script extraction error: {e}")

        # Navigate to trade
        print("\nNavigating to /trade...")
        await page.goto("https://market-qx.trade/en/trade", wait_until="load", timeout=60000)
        await asyncio.sleep(5)
        print(f"Trade page URL: {page.url}")
        print(f"Trade page title: {await page.title()}")

        cookies2 = await ctx.cookies()
        print(f"\nCookies after trade ({len(cookies2)}):")
        for c in cookies2:
            print(f"  {c['name']} = {c['value'][:60]}")

        try:
            ls2 = await page.evaluate("JSON.stringify(window.localStorage)")
            print(f"\nlocalStorage trade: {ls2[:500]}")
        except Exception as e:
            print(f"localStorage trade: {e}")

        try:
            ss2 = await page.evaluate("JSON.stringify(window.sessionStorage)")
            print(f"sessionStorage trade: {ss2[:500]}")
        except Exception as e:
            print(f"sessionStorage trade: {e}")

        try:
            token2 = await page.evaluate("""
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
            print(f"\nToken from trade: {token2}")
        except Exception as e:
            print(f"Trade extraction error: {e}")

        print(f"\nCaptured network responses: {json.dumps({k[:80]: str(v)[:100] for k, v in captured.items()}, indent=2)}")

        await browser.close()

asyncio.run(main())
