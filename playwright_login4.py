"""Login with Playwright - debug form loading."""
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

        # Get Cloudflare clearance
        print("Getting Cloudflare clearance...")
        await page.goto("https://market-qx.trade/en", wait_until="commit", timeout=10000)
        for i in range(30):
            await asyncio.sleep(1)
            cookies = await context.cookies()
            if any(c["name"] == "cf_clearance" for c in cookies):
                print(f"  Clearance after {i+1}s")
                break

        # Navigate to login page
        print("Loading login page...")
        try:
            resp = await page.goto("https://market-qx.trade/en/sign-in/modal/", 
                                    wait_until="load", timeout=20000)
            print(f"  Status: {resp.status if resp else 'None'}")
        except Exception as e:
            print(f"  Error: {e}")

        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()}")
        
        # Wait for the page to fully render (JS may need time)
        print("  Waiting for dynamic content...")
        await asyncio.sleep(5)
        
        # Take a screenshot to see what's there
        await page.screenshot(path="C:\\Users\\PC\\Desktop\\Quotex Signal\\login_page.png")
        print("  Screenshot saved to login_page.png")
        
        # Print page HTML structure around body
        body_html = await page.evaluate("() => document.body ? document.body.innerHTML.substring(0, 2000) : 'NO BODY'")
        print(f"  Body HTML (2000 chars):\n{body_html[:1500]}")
        
        # Check for frames
        frames = page.frames
        print(f"  Frames: {len(frames)}")
        for i, f in enumerate(frames):
            print(f"    Frame {i}: url={f.url[:80]}")
            if i > 0:  # Skip main frame
                try:
                    f_content = await f.content()
                    if len(f_content) > 100:
                        print(f"      Has content (len={len(f_content)})")
                except:
                    print(f"      Cannot access")
        
        # Try to wait for specific selectors
        try:
            await page.wait_for_selector("input", timeout=3000)
            inputs = await page.query_selector_all("input")
            print(f"  Inputs found after wait: {len(inputs)}")
            for inp in inputs:
                name = await inp.get_attribute("name") or ""
                print(f"    {name}")
        except:
            print("  No inputs appeared after 3s wait")
        
        input("Press Enter to close browser...")
        await browser.close()

asyncio.run(main())
