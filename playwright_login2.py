"""Navigate to Quotex, wait for CF clearance, then re-navigate and login."""
import asyncio, os, json
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

        # Navigate to get challenged and get cf_clearance
        print("Step 1: First visit to get Cloudflare challenge...")
        await page.goto("https://market-qx.trade/en", wait_until="commit", timeout=10000)
        
        for i in range(30):
            await asyncio.sleep(1)
            cookies = await context.cookies()
            if any(c["name"] == "cf_clearance" for c in cookies):
                print(f"  cf_clearance set after {i+1}s")
                break
        
        # Now navigate again - should pass Cloudflare
        print("Step 2: Re-navigating (should bypass Cloudflare now)...")
        try:
            resp = await page.goto("https://market-qx.trade/en/sign-in/modal/", 
                                    wait_until="domcontentloaded", timeout=15000)
            print(f"  Status: {resp.status if resp else 'None'}")
        except Exception as e:
            print(f"  Error: {e}")
        
        await asyncio.sleep(3)
        title = await page.title()
        print(f"  Title: {title}")
        content = await page.content()
        
        if "Just a moment" in content:
            print("  Still challenged! Trying to wait more...")
            await asyncio.sleep(10)
            # Try again
            try:
                resp = await page.goto("https://market-qx.trade/en/sign-in/modal/",
                                        wait_until="domcontentloaded", timeout=15000)
                print(f"  Re-navigate status: {resp.status if resp else 'None'}")
            except:
                pass
            content = await page.content()
        
        print(f"  Page URL: {page.url}")
        
        # Check for login form
        email_el = await page.query_selector('input[name="email"], input[type="email"]')
        pass_el = await page.query_selector('input[name="password"], input[type="password"]')
        print(f"  Email input found: {email_el is not None}")
        print(f"  Password input found: {pass_el is not None}")
        
        if "Just a moment" not in content and email_el and pass_el:
            print("\nStep 3: Logging in...")
            await email_el.fill(email)
            await pass_el.fill(password)
            submit = await page.query_selector('button[type="submit"]')
            if submit:
                await submit.click()
            else:
                await pass_el.press("Enter")
            
            await asyncio.sleep(5)
            print(f"  After login URL: {page.url}")
            
            # Navigate to trade page
            print("Step 4: Going to trade page...")
            await page.goto("https://market-qx.trade/en/trade", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(3)
            
            # Extract token
            token = await page.evaluate("""
                () => {
                    try {
                        if (window.settings && window.settings.token) return window.settings.token;
                        const scripts = document.querySelectorAll('script');
                        for (const s of scripts) {
                            if (s.textContent.includes('token')) {
                                const m = s.textContent.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                                if (m) return m[1];
                            }
                        }
                        return null;
                    } catch(e) { return null; }
                }
            """)
            
            if token:
                print(f"\n*** TOKEN: {token} ***")
                # Save to session.json
                session_path = os.path.join(os.path.dirname(__file__), "session.json")
                with open(session_path, "w") as f:
                    json.dump({
                        email: {
                            "cookies": f"ssid={token}",
                            "token": token,
                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        }
                    }, f, indent=2)
                print(f"Saved to {session_path}")
            else:
                print("Token not found in page")
                # Try via evaluate
                page_content = await page.content()
                import re
                matches = re.findall(r'token["\']?\s*[:=]\s*["\']([^"\']+)["\']', page_content)
                print(f"Token matches in HTML: {matches[:3]}")
        else:
            print("Cannot login - page blocked or form not found")
        
        input("Press Enter to close browser...")
        await browser.close()

asyncio.run(main())
