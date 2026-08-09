"""Fill the form then dump EVERYTHING: all buttons, all clickable elements, screenshot."""
import asyncio, logging, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

EMAIL = os.getenv("QUOTEX_EMAIL")
PASS  = os.getenv("QUOTEX_PASSWORD")

async def main():
    from renew_ssid import _ensure_socks_relay
    proxy_cfg = _ensure_socks_relay()
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=False,
        proxy=proxy_cfg,
        firefox_user_prefs={
            "gfx.xrender.enabled": False, "layers.acceleration.disabled": True,
            "gfx.canvas.accelerated": False, "webgl.disabled": True,
            "webgl.enable-webgl2": False, "gfx.x11-egl.force-disabled": True,
            "security.prompt_for_key_storage_type": False,
            "signon.masterPasswordRequired": False, "signon.rememberSignons": False,
            "signon.autofillForms": False, "security.default_personal_cert": "Select Automatically",
            "accessibility.force_disabled": 1, "browser.downgrade.enabled": True,
        },
    ) as browser:
        page = await browser.new_page()
        try:
            await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=120000)
        except Exception:
            pass

        # wait for form
        for _ in range(60):
            ready = await page.evaluate(
                "() => { var i = document.querySelectorAll('input[name=\"email\"]'); for (var j=0;j<i.length;j++) { if (i[j].offsetParent !== null && !i[j].disabled) return true; } return false; }"
            )
            if ready: break
            await asyncio.sleep(2)

        # FILL the form
        fill_res = await page.evaluate(
            """(args) => {
                var emails = document.querySelectorAll('input[name="email"]');
                var passes = document.querySelectorAll('input[name="password"]');
                var email = null, pass = null;
                for (var i = 0; i < emails.length; i++) {
                    if (emails[i].offsetParent !== null && !emails[i].disabled) { email = emails[i]; break; }
                }
                for (var i = 0; i < passes.length; i++) {
                    if (passes[i].offsetParent !== null && !passes[i].disabled) { pass = passes[i]; break; }
                }
                if (!email || !pass) return "no inputs";
                var setVal = (el, value) => {
                    var proto = HTMLInputElement.prototype;
                    var desc = Object.getOwnPropertyDescriptor(proto, 'value');
                    desc.set.call(el, value);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                };
                setVal(email, args[0]);
                setVal(pass, args[1]);
                return "filled email=" + email.value + " passLen=" + pass.value.length;
            }""",
            [EMAIL, PASS]
        )
        logger.info("fill: %s", fill_res)

        # DUMP all buttons/clickables right after fill
        dump = await page.evaluate(
            """() => {
                var out = [];
                document.querySelectorAll('button, input[type=submit], [role=button], [role=submit]').forEach(function(b) {
                    var r = b.getBoundingClientRect();
                    out.push({
                        tag: b.tagName, type: b.type, text: (b.innerText||b.value||'').trim().slice(0,40),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                        role: b.getAttribute('role'), display: getComputedStyle(b).display,
                        visibility: getComputedStyle(b).visibility, opacity: getComputedStyle(b).opacity
                    });
                });
                return out;
            }"""
        )
        logger.info("ALL BUTTONS AFTER FILL: %s", json.dumps(dump, indent=1))

        # Also dump forms
        forms = await page.evaluate(
            """() => {
                var out = [];
                document.querySelectorAll('form').forEach(function(f) {
                    out.push({action: f.getAttribute('action'), html: f.innerHTML.slice(0,300)});
                });
                return out;
            }"""
        )
        logger.info("FORMS: %s", json.dumps(forms, indent=1))

        await page.screenshot(path="diag_after_fill.png")
        logger.info("screenshot -> diag_after_fill.png")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
