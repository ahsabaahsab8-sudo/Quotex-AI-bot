"""Get cookies from API login, inject into Playwright, then navigate to bypass geo-block."""
import asyncio, os, json
from dotenv import load_dotenv
load_dotenv()

email = os.getenv("QUOTEX_EMAIL")
password = os.getenv("QUOTEX_PASSWORD")

# Step 1: Get cookies from API login
from curl_cffi import requests
sess = requests.Session(impersonate="chrome120")
r = sess.post(
    "https://market-qx.trade/api/v1/sign-in",
    headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://market-qx.trade",
    },
    json={"email": email, "password": password},
    timeout=30,
)
api_token = r.json().get("result", {}).get("session")
api_cookies = dict(sess.cookies.items())
print(f"API token: {api_token[:20]}...")
print(f"API cookies: {list(api_cookies.keys())}")

# Step 2: Use Playwright with these cookies
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
            no_viewport=True,
        )
        
        # Inject API cookies into the browser context
        await context.add_cookies([
            {"name": k, "value": v, "domain": "market-qx.trade", "path": "/"}
            for k, v in api_cookies.items()
        ])
        # Also add the ssid cookie
        await context.add_cookies([
            {"name": "ssid", "value": api_token, "domain": "market-qx.trade", "path": "/"}
        ])
        
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)
        
        # Navigate to login page (should bypass geo-block with valid cookies)
        print("Navigating to login page...")
        try:
            resp = await page.goto(
                "https://market-qx.trade/en/sign-in/modal/",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            print(f"Status: {resp.status if resp else 'None'}")
        except Exception as e:
            print(f"Error: {e}")
        
        await asyncio.sleep(3)
        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")
        
        content = await page.content()
        if "not available in your region" in content:
            print("Still geo-blocked")
        elif '<input' in content and ('email' in content.lower() or 'password' in content.lower()):
            print("*** NO GEO-BLOCK! Login form found! ***")
            
            # Fill the form
            email_el = await page.query_selector('input[name="email"], input[type="email"]')
            pass_el = await page.query_selector('input[name="password"], input[type="password"]')
            if email_el and pass_el:
                await email_el.fill(email)
                await pass_el.fill(password)
                submit = await page.query_selector('button[type="submit"]')
                if submit:
                    await submit.click()
                    print("Submitted login")
                await asyncio.sleep(5)
                print(f"Post-login URL: {page.url}")
                
                # Go to trade page
                await page.goto("https://market-qx.trade/en/trade", wait_until="domcontentloaded", timeout=15000)
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
                    print(f"\n*** SSID: {token} ***")
                    session_path = os.path.join(os.path.dirname(__file__), "session.json")
                    with open(session_path, "w") as f:
                        json.dump({email: {"cookies": f"ssid={token}", "token": token, "user_agent": "Mozilla/5.0"}}, f, indent=2)
                    print("Saved!")
        else:
            print("Unknown page state")
            print(f"Body(800): {content[content.find('<body'):content.find('</body>')+7][:800]}")
        
        input("Press Enter to close browser...")
        await browser.close()

asyncio.run(main())
