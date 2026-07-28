"""Quotex login via Playwright - email/password + manual OTP + SSID extraction."""
import asyncio, os, json, sys, re
from playwright.async_api import async_playwright, TimeoutError as PwTimeout

QUOTEX_EMAIL = "slamismail8@gmail.com"
QUOTEX_PASSWORD = "35689023Ahsan@"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        # Step 1: Get past Cloudflare
        print("[1] Bypassing Cloudflare...")
        await page.goto("https://market-qx.trade/en/sign-in", wait_until="commit", timeout=15000)
        for i in range(45):
            await asyncio.sleep(1)
            cookies = await context.cookies()
            if any(c["name"] == "cf_clearance" for c in cookies):
                print(f"  Cloudflare cleared after {i+1}s")
                break

        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(2)

        # Step 2: Click Sign In tab (data-value=1) if not already active
        print("[2] Clicking Sign In tab...")
        try:
            tab1 = await page.wait_for_selector('a.modal-sign__tab[data-value="1"]', timeout=5000)
            is_active = await tab1.get_attribute("class") or ""
            if "active" not in is_active:
                await tab1.click()
                await asyncio.sleep(1)
                print("  Sign In tab clicked")
            else:
                print("  Sign In tab already active")
        except Exception as e:
            print(f"  Tab click skipped: {e}")

        # Step 3: Fill email & password
        print("[3] Filling credentials...")
        email_el = await page.wait_for_selector('#tab-1 input[name="email"]', timeout=5000)
        await email_el.fill(QUOTEX_EMAIL)
        pass_el = await page.wait_for_selector('#tab-1 input[name="password"]', timeout=5000)
        await pass_el.fill(QUOTEX_PASSWORD)
        print(f"  Email: {QUOTEX_EMAIL}")
        print(f"  Password: {'*' * len(QUOTEX_PASSWORD)}")

        # Step 4: Submit
        print("[4] Submitting login form...")
        submit_btn = await page.query_selector('#tab-1 button.modal-sign__block-button')
        if submit_btn:
            await submit_btn.click()
        else:
            await pass_el.press("Enter")
        print("  Form submitted")

        # Step 5: Wait - either OTP field or redirect to trade
        print("[5] Waiting for OTP input or redirect to trade page...")
        await asyncio.sleep(3)
        current_url = page.url
        print(f"  Current URL: {current_url}")

        # Check if we got redirected to trade page already (no OTP)
        if "/trade" in current_url:
            print("  Already on trade page - no OTP needed")
        else:
            # Look for OTP / verification code input
            otp_input = None
            for selector in [
                'input[name="code"]',
                'input[name="otp"]',
                'input[placeholder*="code" i]',
                'input[placeholder*="otp" i]',
                'input[autocomplete="one-time-code"]',
                'input[inputmode="numeric"]',
            ]:
                otp_input = await page.query_selector(selector)
                if otp_input:
                    print(f"  Found OTP input: {selector}")
                    break

            if not otp_input:
                # Try to find any additional input that appeared
                all_inputs = await page.query_selector_all("input")
                for inp in all_inputs:
                    attrs = await inp.evaluate("""
                        el => ({
                            name: el.name,
                            type: el.type,
                            placeholder: el.placeholder,
                            id: el.id,
                            class: el.className,
                            hidden: el.type === 'hidden',
                        })
                    """)
                    if not attrs["hidden"] and attrs["name"] not in ("_token", "email", "password", "remember"):
                        print(f"  New input: {attrs}")
                        if not otp_input:
                            otp_input = inp

            if otp_input:
                print("\n  [OTP] OTP sent to your email. Paste the code into the browser OTP field.")
                print("  [OTP] The script will auto-detect when the page redirects to trade page.")
                print("  [OTP] Waiting up to 120 seconds for OTP...\n")

                # Wait for URL to change to /trade (meaning OTP was accepted)
                for _ in range(120):
                    await asyncio.sleep(1)
                    try:
                        cur = page.url
                        if "/trade" in cur:
                            print(f"  Redirected to trade page!")
                            break
                    except:
                        pass
                else:
                    print("  Timed out waiting for OTP. Checking if OTP was already entered...")

            # Check final URL
            current_url = page.url
            print(f"  Final URL: {current_url}")

        # Step 6: Navigate to trade page if not already there
        if "/trade" not in page.url:
            print("[6] Navigating to trade page...")
            await page.goto("https://market-qx.trade/en/trade", wait_until="networkidle", timeout=20000)
            await asyncio.sleep(3)
        else:
            print("[6] Already on trade page")

        # Step 7: Extract token/SSID
        print("[7] Extracting SSID token...")
        token = await page.evaluate("""
            () => {
                try {
                    if (window.settings && window.settings.token)
                        return window.settings.token;
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const t = s.textContent;
                        if (t.includes('token')) {
                            const m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                            if (m) return m[1];
                        }
                    }
                    return null;
                } catch(e) { return null; }
            }
        """)

        ssid = None
        if token:
            print(f"\n  [OK] Token found: {token}")
            ssid = token
        else:
            # Try from cookies
            print("  Token not in page, checking cookies...")
            cookies = await context.cookies()
            for c in cookies:
                name_lower = c["name"].lower()
                if name_lower in ("ssid", "session", "token", "qx_session"):
                    print(f"  Found cookie: {c['name']} = {c['value']}")
                    ssid = c["value"]
                    break

        # Also try to execute the SSID extraction function in console
        if not ssid:
            print("  Trying console SSID extraction...")
            ssid = await page.evaluate("""
                () => {
                    try {
                        var s = document.cookie.match(/ssid=([^;]+)/);
                        return s ? s[1] : null;
                    } catch(e) { return null; }
                }
            """)
            if ssid:
                print(f"  SSID from cookie: {ssid}")

        if ssid:
            print(f"\n  [OK] SSID: {ssid}")

            # Save session
            cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in await context.cookies())
            ua = await page.evaluate("navigator.userAgent")
            session_data = {
                QUOTEX_EMAIL: {
                    "cookies": cookies_str,
                    "token": ssid,
                    "user_agent": ua,
                }
            }
            with open("session.json", "w") as f:
                json.dump(session_data, f, indent=2)
            print(f"  [OK] Saved to session.json")
        else:
            print("  [FAIL] Could not extract SSID token")

        print("\nDone. Browser stays open - close manually when ready.")
        input("Press Enter to close browser...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
