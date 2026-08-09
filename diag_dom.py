"""Live headed diagnostic: dump the sign-in DOM (forms + buttons) so we can pick exact selectors."""
import asyncio, logging, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from renew_ssid import _ensure_socks_relay
    proxy_cfg = _ensure_socks_relay()
    logger.info("proxy_cfg = %s", proxy_cfg)

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
        logger.info("Navigating to sign-in...")
        try:
            await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=120000)
        except Exception:
            pass
        logger.info("URL after nav: %s", page.url)

        # wait for form
        for _ in range(60):
            ready = await page.evaluate(
                """() => {
                    var inputs = document.querySelectorAll('input[name="email"]');
                    for (var i = 0; i < inputs.length; i++) {
                        var el = inputs[i];
                        if (el.offsetParent !== null && !el.disabled && el.type !== 'hidden') return true;
                    }
                    return false;
                }"""
            )
            if ready:
                break
            await asyncio.sleep(2)
        logger.info("form ready, dumping DOM...")

        dom = await page.evaluate(
            """() => {
                var out = {forms: [], buttons: []};
                document.querySelectorAll('form').forEach(function(f){
                    out.forms.push({action: f.getAttribute('action'), id: f.id, cls: f.className});
                });
                document.querySelectorAll('button, input[type=submit]').forEach(function(b){
                    var r = b.getBoundingClientRect();
                    out.buttons.push({
                        tag: b.tagName, type: b.type, text: (b.innerText||b.value||'').trim().slice(0,40),
                        visible: r.width > 0 && r.height > 0,
                        rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
                        formAction: (b.form ? b.form.getAttribute('action') : null)
                    });
                });
                return out;
            }"""
        )
        print("FORMS:", json.dumps(dom["forms"], indent=1))
        print("BUTTONS:", json.dumps(dom["buttons"], indent=1))
        await page.screenshot(path="diag_dom.png")
        logger.info("screenshot -> diag_dom.png")
        await asyncio.sleep(45)


if __name__ == "__main__":
    asyncio.run(main())
