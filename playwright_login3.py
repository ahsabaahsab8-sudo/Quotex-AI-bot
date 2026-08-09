"""Login with Playwright - Cloudflare bypass works, fix form detection."""
import asyncio, os, json, re
from dotenv import load_dotenv
load_dotenv()

email = os.getenv("QUOTEX_EMAIL")
password = os.getenv("QUOTEX_PASSWORD")

from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        # First visit to get Cloudflare clearance
        print("Getting Cloudflare clearance...")
        await page.goto("https://market-qx.trade/en", wait_until="commit", timeout=10000)
        for i in range(30):
            await asyncio.sleep(1)
            cookies = await context.cookies()
            if any(c["name"] == "cf_clearance" for c in cookies):
                print(f"  Clearance after {i+1}s")
                break

        # Navigate to login page (now with clearance)
        print("Loading login page...")
        await page.goto("https://market-qx.trade/en/sign-in/modal/", wait_until="networkidle", timeout=15000)
        await asyncio.sleep(3)
        print(f"  Title: {await page.title()}")
        
        # Debug - print all input elements on the page
        inputs = await page.query_selector_all("input")
        print(f"  Found {len(inputs)} input elements:")
        for inp in inputs:
            name = await inp.get_attribute("name") or ""
            inp_type = await inp.get_attribute("type") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            id_attr = await inp.get_attribute("id") or ""
            print(f"    input: name={name}, type={inp_type}, placeholder={placeholder[:30]}, id={id_attr}")
        
        buttons = await page.query_selector_all("button")
        print(f"  Found {len(buttons)} buttons:")
        for btn in buttons:
            btn_type = await btn.get_attribute("type") or ""
            text = await btn.inner_text() or ""
            print(f"    button: type={btn_type}, text={text[:30]}")
        
        # Also print page content for reference
        content = await page.content()
        # Try to find the login form area
        if "login" in content.lower() or "sign" in content.lower():
            print("  Login/sign content detected")
        
        # Try broader selectors for form fields
        email_el = await page.query_selector('[placeholder*="mail" i], [placeholder*="email" i], input[name="email"], input[type="email"]')
        pass_el = await page.query_selector('[placeholder*="password" i], [placeholder*="pass" i], input[name="password"], input[type="password"]')
        print(f"  Email found: {email_el is not None}")
        print(f"  Password found: {pass_el is not None}")
        
        if email_el and pass_el:
            print("\nLogging in...")
            await email_el.fill(email)
            await pass_el.fill(password)
            
            # Try various submit approaches
            submit_btn = await page.query_selector('button[type="submit"], button:has-text("Sign"), button:has-text("Log")')
            if submit_btn:
                await submit_btn.click()
                print("  Clicked submit button")
            else:
                await pass_el.press("Enter")
                print("  Pressed Enter")
            
            await asyncio.sleep(5)
            print(f"  After login URL: {page.url}")
            
            # Navigate to trade page
            print("Going to trade page...")
            await page.goto("https://market-qx.trade/en/trade", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(3)
            
            # Extract token
            token = await page.evaluate("""
                () => {
                    try {
                        if (window.settings && window.settings.token) return window.settings.token;
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
            
            if token:
                print(f"\n*** TOKEN: {token} ***")
                session_path = os.path.join(os.path.dirname(__file__), "session.json")
                with open(session_path, "w") as f:
                    json.dump({
                        email: {
                            "cookies": f"ssid={token}",
                            "token": token,
                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        }
                    }, f, indent=2)
                print(f"Saved to session.json")
            else:
                # Try to get it from navigation/API responses
                print("Token not found in page. Trying cookies...")
                cookies = await context.cookies()
                for c in cookies:
                    if "ssid" in c["name"].lower() or "token" in c["name"].lower() or "session" in c["name"].lower():
                        print(f"  Cookie: {c['name']} = {c['value'][:30]}")
        else:
            print("Cannot find login form")
        
        input("Press Enter to close browser...")
        await browser.close()

asyncio.run(main())
