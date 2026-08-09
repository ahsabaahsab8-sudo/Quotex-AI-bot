"""Headed Camoufox login via BD proxy - user fills OTP manually.

Run this on your Windows machine so the Camoufox window is visible.
1. Script opens Camoufox -> Quotex sign-in via the Bangladesh proxy.
2. Fills email/password automatically.
3. When the OTP page appears, YOU type the OTP into the visible browser.
4. Script waits for redirect to /trade, then extracts the token (ssid).
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()
EMAIL = os.getenv("QUOTEX_EMAIL")
PASSWORD = os.getenv("QUOTEX_PASSWORD")

PROXY = "socks5://144.24.111.128:1088"
COUNTRY = "India"

WAIT_FOR_OTP = 180  # seconds for you to paste the OTP manually

async def main():
    from camoufox.async_api import AsyncCamoufox

    print(f"Testing {COUNTRY} proxy: {PROXY}")
    print(f"Email: {EMAIL}")
    print(">>> Opening VISIBLE Camoufox window...")

    try:
        async with AsyncCamoufox(
            headless=False,          # VISIBLE window so you can type the OTP
            humanize=True,
            geoip=True,
            disable_coop=True,
            proxy={"server": PROXY},
        ) as browser:
            page = await browser.new_page()

            print("Navigating to sign-in page...")
            try:
                await page.goto(
                    "https://market-qx.trade/en/sign-in/",
                    wait_until="domcontentloaded",
                    timeout=90000,
                )
            except Exception as e:
                print(f"Navigation failed: {e}")

            print(f"Page title: {await page.title()}")
            print(f"Current URL: {page.url}")

            if "Just a moment" in await page.title():
                print("Cloudflare detected, waiting up to 60s...")
                try:
                    await page.wait_for_function(
                        "() => !document.title.includes('Just a moment')",
                        timeout=60000,
                    )
                    print("Cloudflare passed!")
                except Exception:
                    print("Cloudflare still active, continuing anyway...")

            await asyncio.sleep(10)

            # Fill the login form using page.fill (trusted, triggers React properly)
            print("Filling login form...")
            try:
                await page.fill('input[name="email"]', EMAIL)
                await page.fill('input[name="password"]', PASSWORD)
                print("Credentials filled.")
            except Exception as e:
                print(f"Fill failed: {e}")
                print("Trying JS fallback...")
                result = await page.evaluate(
                    """
                    (args) => {
                        var emails = document.querySelectorAll('input[name="email"]');
                        var passes = document.querySelectorAll('input[name="password"]');
                        if (!emails.length || !passes.length) return 'no inputs found';
                        var email = emails[emails.length > 1 ? 1 : 0];
                        var pass = passes[passes.length > 1 ? 1 : 0];
                        email.value = args[0];
                        pass.value = args[1];
                        email.dispatchEvent(new Event('input', {bubbles: true}));
                        pass.dispatchEvent(new Event('input', {bubbles: true}));
                        return 'filled';
                    }
                    """,
                    [EMAIL, PASSWORD],
                )
                print(f"JS fallback result: {result}")

            # Click the Sign in button
            print("Clicking Sign in...")
            clicked = False
            try:
                btn = await page.query_selector('button[type="submit"]')
                if btn:
                    await btn.click()
                    clicked = True
            except Exception:
                pass
            if not clicked:
                try:
                    result = await page.evaluate(
                        """
                        () => {
                            var buttons = document.querySelectorAll('button');
                            for (var i = 0; i < buttons.length; i++) {
                                var b = buttons[i];
                                if (b.textContent.trim() === 'Sign in' && b.offsetParent !== null) {
                                    b.click();
                                    return 'clicked Sign in';
                                }
                            }
                            return 'Sign in button not found';
                        }
                        """
                    )
                    print(f"JS click result: {result}")
                except Exception as e:
                    print(f"JS click failed: {e}")

            await asyncio.sleep(5)

            # Check if we're on OTP page
            url = page.url
            print(f"URL after submit: {url}")
            has_otp = await page.query_selector('input[name="code"], input[name="otp"], input[autocomplete="one-time-code"]')
            if has_otp or "/sign-in" in url:
                print("\n" + "=" * 60)
                print(f">>> OTP PAGE DETECTED. You have {WAIT_FOR_OTP}s.")
                print(">>> Type the OTP in the visible Camoufox window NOW.")
                print("=" * 60)

                # Also try auto-read from gmail in background as a helper
                try:
                    from renew_ssid import auto_read_otp_sync
                    print("(Background: checking Gmail for OTP... just in case)")
                    otp = await asyncio.to_thread(auto_read_otp_sync, timeout=20)
                    if otp and has_otp:
                        await page.fill('input[name="code"], input[name="otp"]', otp)
                        print(f"Auto-filled OTP from Gmail: {otp}")
                except Exception as e:
                    print(f"(Auto OTP helper unavailable: {e})")

                # Wait for user to finish OTP manually and get redirected to /trade
                for _ in range(WAIT_FOR_OTP):
                    if "/trade" in page.url:
                        print("Redirected to /trade! Login successful.")
                        break
                    await asyncio.sleep(1)
                else:
                    print("Timed out waiting for /trade redirect.")
                    # try navigating manually
                    try:
                        await page.goto(
                            "https://market-qx.trade/en/trade",
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        await asyncio.sleep(10)
                    except Exception:
                        pass

            print(f"\nFinal URL: {page.url}")
            print(f"Final Title: {await page.title()}")

            # Extract token (poll up to 60s - ssid is set after SPA websocket auth)
            TOKEN_JS = """
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
                try { var l = localStorage.getItem('token') || localStorage.getItem('ssid'); if (l) return l; } catch(e) {}
                return null;
            }
            """

            token = None
            for _attempt in range(20):  # up to 60s
                try:
                    token = await page.evaluate(TOKEN_JS)
                except Exception:
                    token = None
                if not token:
                    try:
                        cookies = await page.context.cookies()
                        for c in cookies:
                            if "ssid" in c["name"].lower() and c.get("value"):
                                token = c["value"]
                                break
                    except Exception:
                        pass
                if token:
                    break
                await asyncio.sleep(3)

            if token:
                print(f"\nSUCCESS! Token: {token[:16]}...{token[-4:]}")
                from renew_ssid import save_session
                ua = await page.evaluate("navigator.userAgent")
                save_session(EMAIL, token, ua)
                print(f"Saved to session.json. Proxy {COUNTRY} ({PROXY}) authenticated with Quotex.")
                print(f"\nFull token: {token}")
            else:
                print("\nFAILED: Token is None")
                info = await page.evaluate(
                    """
                    () => ({
                        cookies: document.cookie.substring(0, 300),
                        settingsKeys: window.settings ? Object.keys(window.settings).join(',') : 'undefined',
                        url: window.location.href
                    })
                    """
                )
                print(f"Debug - cookies: {info['cookies']}")
                print(f"Debug - settings keys: {info['settingsKeys']}")
                print(f"Debug - url: {info['url']}")

            print("Closing browser in 15s...")
            await asyncio.sleep(15)
    except Exception as e:
        print(f"FAILED with exception: {e}")

asyncio.run(main())
