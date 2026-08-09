"""Live headed Camoufox diagnostic: open sign-in page through proxy, dump what renders."""
import asyncio, logging, os, sys
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
    from playwright.async_api import Page

    async with AsyncCamoufox(
        humanize=True,
        geoip=False,
        disable_coop=True,
        headless=False,
        proxy=proxy_cfg,
        firefox_user_prefs={
            "gfx.xrender.enabled": False,
            "layers.acceleration.disabled": True,
            "gfx.canvas.accelerated": False,
            "webgl.disabled": True,
            "webgl.enable-webgl2": False,
            "gfx.x11-egl.force-disabled": True,
            "security.prompt_for_key_storage_type": False,
            "signon.masterPasswordRequired": False,
            "signon.rememberSignons": False,
            "signon.autofillForms": False,
            "security.default_personal_cert": "Select Automatically",
            "accessibility.force_disabled": 1,
            "browser.downgrade.enabled": True,
        },
    ) as browser:
        page = await browser.new_page()

        async def log_routes(route):
            url = route.request.url
            logger.info("  [route] %s (%s)", url, route.request.resource_type)
            await route.continue_()
        await page.route("**/*", log_routes)

        logger.info("Navigating to sign-in...")
        try:
            resp = await page.goto(
                "https://market-qx.trade/en/sign-in/",
                wait_until="domcontentloaded", timeout=120000,
            )
            logger.info("goto resp status = %s", resp.status if resp else None)
        except Exception as e:
            logger.info("goto raised: %s", type(e).__name__)

        for i in range(10):
            await asyncio.sleep(3)
            url = page.url
            title = await page.title()
            logger.info("[%d] url=%s title=%s", i, url, title)
            try:
                body = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 1500) : ''")
            except Exception as e:
                body = f"<eval err {e}>"
            logger.info("[%d] BODY: %s", i, body.replace("\n", " | ")[:1500])
            if url != "about:blank" and "sign-in" in url:
                break

        await page.screenshot(path="diag_signin.png")
        logger.info("screenshot saved -> diag_signin.png")
        await asyncio.sleep(60)  # keep open for manual inspection


if __name__ == "__main__":
    asyncio.run(main())
