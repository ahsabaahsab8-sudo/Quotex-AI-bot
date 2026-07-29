"""Debug Camoufox: check .env and login on qxbroker.com."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

print(f"EMAIL from env: '{os.getenv('QUOTEX_EMAIL')}'")
print(f"PASS from env: '{os.getenv('QUOTEX_PASSWORD')[:3] if os.getenv('QUOTEX_PASSWORD') else 'NOT SET'}'")


async def main():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True,
        geoip=True,
        headless=True,
        disable_coop=True,
    ) as browser:
        page = await browser.new_page()

        # Go directly to qxbroker.com since that's where we redirect
        print("\n1. Navigate to qxbroker.com/sign-in...")
        await page.goto(
            "https://qxbroker.com/en/sign-in/",
            wait_until="domcontentloaded",
            timeout=120000
        )
        await asyncio.sleep(5)
        print(f"   URL: {page.url}")
        print(f"   Title: {await page.title()}")

        # Try a simpler form fill approach
        print("\n2. Fill credentials...")
        email = os.getenv("QUOTEX_EMAIL")
        password = os.getenv("QUOTEX_PASSWORD")

        r = await page.evaluate(
            """(args) => {
                var e = document.querySelector('input[name="email"]');
                var p = document.querySelector('input[name="password"]');
                if (!e || !p) return JSON.stringify({found: false, emails: document.querySelectorAll('input[type=email], input[name=email]').length});
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeInputValueSetter.call(e, args[0]);
                e.dispatchEvent(new Event('input', { bubbles: true }));
                nativeInputValueSetter.call(p, args[1]);
                p.dispatchEvent(new Event('input', { bubbles: true }));
                var btn = Array.from(document.querySelectorAll('button')).find(
                    b => b.textContent.trim() === 'Sign in'
                );
                if (btn) {
                    btn.click();
                    return JSON.stringify({clicked: true, btnText: btn.textContent.trim()});
                }
                return JSON.stringify({clicked: false, buttons: Array.from(document.querySelectorAll('button')).map(b=>b.textContent.trim())});
            }""",
            [email, password]
        )
        print(f"   Result: {r}")

        # Wait and watch
        for i in range(15):
            await asyncio.sleep(2)
            print(f"   [{i*2+2}s] {page.url}")
            if "/trade" in page.url:
                print("   -> ON TRADE PAGE!")
                break

        print(f"\n3. Final URL: {page.url}")
        content_preview = (await page.content())[:1500]
        if "Sign in" in content_preview or "sign-in" in page.url:
            # Check for error messages
            errors = await page.evaluate("""() => {
                var els = document.querySelectorAll('.error, .alert, [class*=error], [class*=alert], .invalid-feedback');
                return Array.from(els).map(e => e.textContent.trim()).filter(t => t);
            }""")
            print(f"   Error elements: {errors}")
            # Check if credentials are actually in the fields
            values = await page.evaluate("""() => {
                var e = document.querySelector('input[name="email"]');
                var p = document.querySelector('input[name="password"]');
                return {email_val: e ? e.value : 'N/A', pass_len: p ? p.value.length : -1};
            }""")
            print(f"   Field values: {values}")


asyncio.run(main())
