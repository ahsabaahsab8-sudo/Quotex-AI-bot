"""Login to Quotex via Playwright and extract the WebSocket token."""
import asyncio, os, json, sys
from dotenv import load_dotenv
load_dotenv()

email = os.getenv("QUOTEX_EMAIL")
password = os.getenv("QUOTEX_PASSWORD")

from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = await context.new_page()
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        print(f"Navigating to market-qx.trade/en/sign-in/modal/ ...")
        
        try:
            resp = await page.goto(
                "https://market-qx.trade/en/sign-in/modal/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            print(f"Status: {resp.status if resp else 'None'}")
        except Exception as e:
            print(f"Error: {e}")
        
        await asyncio.sleep(5)
        print(f"URL: {page.url}")
        title = await page.title()
        print(f"Title: {title}")
        
        content = await page.content()
        if "Just a moment" in content or "challenge" in content.lower():
            print("CLOUDFLARE CHALLENGE - waiting for resolution...")
            for i in range(60):
                await asyncio.sleep(2)
                current_content = await page.content()
                if "Just a moment" not in current_content and "challenge" not in current_content.lower():
                    print(f"Challenge resolved after {i*2+2}s")
                    break
                print(f"  Still challenged ({i*2+2}s)")
        
        # Check for login form elements
        email_el = await page.query_selector('input[name="email"], input[type="email"], input[placeholder*="email" i]')
        pass_el = await page.query_selector('input[name="password"], input[type="password"]')
        print(f"Email input: {email_el is not None}")
        print(f"Password input: {pass_el is not None}")
        
        if email_el and pass_el:
            await email_el.fill(email)
            await pass_el.fill(password)
            print("Filled login form")
            
            submit_btn = await page.query_selector('button[type="submit"], .btn-submit, button:has-text("Sign In"), button:has-text("Log In")')
            if submit_btn:
                await submit_btn.click()
                print("Clicked submit")
            else:
                # Try pressing Enter on password field
                await pass_el.press("Enter")
                print("Pressed Enter")
            
            await asyncio.sleep(5)
            print(f"After login URL: {page.url}")
        
        # Navigate to the trading page to get settings
        print("Navigating to /en/trade ...")
        try:
            await page.goto(
                "https://market-qx.trade/en/trade",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception as e:
            print(f"Trade page error: {e}")
        await asyncio.sleep(3)
        
        # Try to extract the token
        token = await page.evaluate("""
            () => {
                try {
                    if (window.settings && window.settings.token) {
                        return window.settings.token;
                    }
                    // Try in script tags
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
        else:
            print("Token not found in page")
            
        # Print all cookies
        cookies = await context.cookies()
        for c in cookies:
            print(f"  Cookie: {c['name']} = {c['value'][:40]}...")
        
        input("Press Enter to close browser...")
        await browser.close()

asyncio.run(main())
