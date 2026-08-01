"""Auto-renew SSID via Kameleo+Playwright (bypasses Cloudflare), falls back to undetected-chromedriver."""

import os
import json
import asyncio
import logging
import imaplib
import email as email_lib
import re
import time
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")
MAX_RETRIES = 3


def load_session() -> dict | None:
    try:
        with open(SESSION_FILE) as f:
            data = json.load(f)
        email = os.getenv("QUOTEX_EMAIL", "")
        if email in data:
            return data[email]
        first_key = next(iter(data), None)
        if first_key:
            return data[first_key]
    except Exception:
        pass
    return None


def save_session(email: str, token: str, ua: str = ""):
    try:
        if not ua:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        data = {}
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE) as f:
                data = json.load(f)
        data[email] = {
            "cookies": f"ssid={token}",
            "token": token,
            "user_agent": ua,
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("session.json updated")
    except Exception as e:
        logger.error(f"Failed to save session: {e}")


def auto_read_otp_sync(timeout: int = 60) -> str | None:
    imap_user = os.getenv("IMAP_EMAIL") or os.getenv("QUOTEX_EMAIL")
    imap_pass = os.getenv("IMAP_PASSWORD")
    if not imap_pass:
        logger.warning("IMAP_PASSWORD not set")
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(imap_user, imap_pass)
        mail.select("inbox")
        for _ in range(timeout):
            _, data = mail.search(None, '(FROM "quotex" UNSEEN)')
            for num in reversed(data[0].split()):
                _, msg_data = mail.fetch(num, "(RFC822)")
                body = email_lib.message_from_bytes(msg_data[0][1])
                if body.is_multipart():
                    text = ""
                    for part in body.walk():
                        if part.get_content_type() == "text/plain":
                            text = part.get_payload(decode=True).decode(errors='ignore')
                            break
                else:
                    text = body.get_payload(decode=True).decode(errors='ignore')
                match = re.search(r'\b(\d{4,6})\b', text)
                if match:
                    return match.group(1)
            time.sleep(1)
        logger.warning(f"OTP not found after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"IMAP OTP read failed: {e}")
        return None


def _uc_login() -> str | None:
    """Single undetected-chromedriver login attempt. Returns token or None."""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")

    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=150)
        wait = WebDriverWait(driver, 30)

        logger.info("UC: navigating to sign-in page...")
        driver.get("https://market-qx.trade/en/sign-in/")
        logger.info("UC: page loaded, title: %s", driver.title)

        if "Just a moment" in driver.title:
            logger.info("UC: waiting for Cloudflare challenge...")
            try:
                WebDriverWait(driver, 60).until(lambda d: "Just a moment" not in d.title)
                logger.info("UC: Cloudflare passed")
            except Exception:
                logger.warning("UC: Cloudflare may still be active")

        time.sleep(3)

        email_input = driver.find_element(By.CSS_SELECTOR, 'input[name="email"]')
        password_input = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
        email_input.send_keys(email)
        password_input.send_keys(password)
        logger.info("UC: credentials filled")

        submit = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        submit.click()
        logger.info("UC: submitted login form")
        time.sleep(4)

        if "/trade" not in driver.current_url:
            logger.info("UC: looking for OTP input...")
            try:
                otp_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="code"], input[name="otp"]'))
                )
                otp = auto_read_otp_sync(timeout=60)
                if otp:
                    otp_input.send_keys(otp)
                    logger.info("UC: OTP submitted")
                    time.sleep(3)
                else:
                    logger.warning("UC: OTP not available, waiting...")
                    time.sleep(30)
            except Exception:
                logger.warning("UC: no OTP input found, waiting for redirect...")
                time.sleep(10)

        if "/trade" not in driver.current_url:
            logger.info("UC: navigating to trade page...")
            driver.get("https://market-qx.trade/en/trade")
            time.sleep(3)

        logger.info("UC: extracting token...")
        token = driver.execute_script("""
            try {
                if (window.settings && window.settings.token) return window.settings.token;
                var scripts = document.querySelectorAll('script');
                for (var i = 0; i < scripts.length; i++) {
                    var t = scripts[i].textContent;
                    if (t.includes('token')) {
                        var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                        if (m) return m[1];
                    }
                }
                return null;
            } catch(e) { return null; }
        """)
        if not token:
            token = driver.execute_script(
                "try { var s = document.cookie.match(/ssid=([^;]+)/); return s ? s[1] : null; } catch(e) { return null; }"
            )
            if token:
                logger.info("UC: token from cookie")

        if token:
            ua = driver.execute_script("return navigator.userAgent")
            save_session(email, token, ua)
            logger.info("UC: token: %s...%s", token[:8], token[-4:])
            return token

        logger.error("UC: could not extract token")
        return None

    except Exception as e:
        logger.error("UC: login failed: %s", e)
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


KAMELEO_ENGINE_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "Kameleo", "Kameleo.Engine.exe"
)
KAMELEO_ENDPOINT = "http://localhost:5050"


def _ensure_kameleo_engine():
    """Start Kameleo engine if not already running."""
    import subprocess
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", 5050))
        s.close()
        logger.info("Kameleo engine already running on port 5050")
        return True
    except ConnectionRefusedError:
        pass
    finally:
        s.close()
    if not os.path.exists(KAMELEO_ENGINE_PATH):
        logger.error("Kameleo engine not found at %s", KAMELEO_ENGINE_PATH)
        return False
    logger.info("Starting Kameleo engine...")
    try:
        subprocess.Popen(
            [KAMELEO_ENGINE_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for i in range(15):
            time.sleep(1)
            s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s2.connect(("127.0.0.1", 5050))
                s2.close()
                logger.info("Kameleo engine started")
                return True
            except ConnectionRefusedError:
                pass
            finally:
                s2.close()
        logger.error("Kameleo engine did not start within 15s")
        return False
    except Exception as e:
        logger.error("Failed to start Kameleo engine: %s", e)
        return False


async def _kameleo_login() -> str | None:
    """Login via Kameleo+Playwright. Returns token or None."""
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        return False

    if not _ensure_kameleo_engine():
        return None

    try:
        from kameleo.local_api_client import KameleoLocalApiClient
        from kameleo.local_api_client.models.create_profile_request import CreateProfileRequest
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("kameleo.local_api_client or playwright not installed")
        return None

    client = KameleoLocalApiClient(endpoint=KAMELEO_ENDPOINT)
    try:
        fingerprints = client.fingerprint.search_fingerprints("desktop", None, "chrome")
        if not fingerprints:
            logger.error("No Kameleo fingerprints available")
            return None
        profile = client.profile.create_profile(CreateProfileRequest(fingerprint_id=fingerprints[0].id))
        logger.info("Kameleo profile: %s", profile.id)
    except Exception as e:
        logger.error("Kameleo profile creation failed: %s", e)
        return None

    token = None
    ua = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(
                f"ws://localhost:5050/playwright/{profile.id}"
            )
            page = await browser.contexts[0].new_page()

            logger.info("Navigating to sign-in page...")
            await page.goto(
                "https://market-qx.trade/en/sign-in/",
                wait_until="domcontentloaded", timeout=60000
            )
            await asyncio.sleep(3)

            # Fill login form (visible inputs, second set)
            login_result = await page.evaluate(
                """
                (args) => {
                    var emails = document.querySelectorAll('input[name="email"]');
                    var passes = document.querySelectorAll('input[name="password"]');
                    if (!emails.length || !passes.length) return "no inputs found";
                    var email = emails.length > 1 ? emails[1] : emails[0];
                    var pass = passes.length > 1 ? passes[1] : passes[0];
                    email.value = args[0];
                    pass.value = args[1];
                    email.dispatchEvent(new Event('input', { bubbles: true }));
                    pass.dispatchEvent(new Event('input', { bubbles: true }));
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var b = buttons[i];
                        if (b.textContent.trim() === "Sign in" && b.offsetParent !== null) {
                            b.click();
                            return "clicked Sign in";
                        }
                    }
                    return "Sign in button not found";
                }
                """,
                [email, password]
            )
            logger.info("Login form: %s", login_result)
            await asyncio.sleep(7)

            # If still on sign-in page, check for OTP
            if "/sign-in" in page.url.lower():
                logger.info("Checking for OTP input...")
                try:
                    otp_el = await page.query_selector('input[name="code"], input[name="otp"]')
                    if otp_el:
                        otp = await asyncio.to_thread(auto_read_otp_sync, timeout=60)
                        if otp:
                            await otp_el.fill(otp)
                            logger.info("OTP submitted")
                            await asyncio.sleep(5)
                except Exception:
                    pass

            # Navigate to trade page
            await page.goto(
                "https://market-qx.trade/en/trade",
                wait_until="domcontentloaded", timeout=60000
            )
            await asyncio.sleep(3)

            # Extract token
            token = await page.evaluate("""
                () => {
                    try { if (window.settings && window.settings.token) return window.settings.token; } catch(e) {}
                    try {
                        var scripts = document.querySelectorAll('script');
                        for (var i = 0; i < scripts.length; i++) {
                            var t = scripts[i].textContent;
                            if (t.includes('token')) {
                                var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                                if (m) return m[1];
                            }
                        }
                    } catch(e) {}
                    try { var s = document.cookie.match(/ssid=([^;]+)/); return s ? s[1] : null; } catch(e) {}
                    return null;
                }
            """)
            if not token:
                # Try cookie fallback via Playwright API
                cookies = await browser.contexts[0].cookies()
                for c in cookies:
                    if "ssid" in c["name"].lower():
                        token = c["value"]
                        break

            ua = await page.evaluate("navigator.userAgent")
            logger.info("Token extracted: %s...%s", token[:8] if token else "None", token[-4:] if token else "")
    except Exception as e:
        logger.error("Kameleo login failed: %s", e)
    finally:
        try:
            client.profile.stop_profile(profile.id)
        except Exception:
            pass
        try:
            client.profile.delete_profile(profile.id)
        except Exception:
            pass

    if token:
        save_session(email, token, ua or "")
    return token


def _is_linux() -> bool:
    import platform
    return platform.system() == "Linux"


async def _patchright_login() -> str | None:
    """Login via Patchright (patched Playwright with Cloudflare bypass).
    Works on Linux (Railway) and Windows."""
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        return None

    try:
        from patchright.async_api import async_playwright
    except ImportError:
        logger.error("patchright not installed. Run: pip install patchright && patchright install chromium")
        return None

    token = None
    ua = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1280,720",
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            logger.info("Patchright: navigating to sign-in page...")
            await page.goto(
                "https://market-qx.trade/en/sign-in/",
                wait_until="domcontentloaded", timeout=120000
            )

            # Handle Cloudflare challenge if present
            title = await page.title()
            if "Just a moment" in title:
                logger.info("Patchright: waiting for Cloudflare challenge...")
                try:
                    await page.wait_for_function(
                        "() => !document.title.includes('Just a moment')",
                        timeout=120000
                    )
                    logger.info("Patchright: Cloudflare passed")
                except Exception:
                    logger.warning("Patchright: Cloudflare may still be active, continuing...")

            await asyncio.sleep(3)

            # Fill login form (visible inputs, second set)
            login_result = await page.evaluate(
                """
                (args) => {
                    var emails = document.querySelectorAll('input[name="email"]');
                    var passes = document.querySelectorAll('input[name="password"]');
                    if (!emails.length || !passes.length) return "no inputs found";
                    var email = emails.length > 1 ? emails[1] : emails[0];
                    var pass = passes.length > 1 ? passes[1] : passes[0];
                    email.value = args[0];
                    pass.value = args[1];
                    email.dispatchEvent(new Event('input', { bubbles: true }));
                    pass.dispatchEvent(new Event('input', { bubbles: true }));
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var b = buttons[i];
                        if (b.textContent.trim() === "Sign in" && b.offsetParent !== null) {
                            b.click();
                            return "clicked Sign in";
                        }
                    }
                    return "Sign in button not found";
                }
                """,
                [email, password]
            )
            logger.info("Patchright: form result: %s", login_result)
            await asyncio.sleep(7)

            # OTP check
            if "/sign-in" in page.url.lower():
                logger.info("Patchright: checking for OTP input...")
                try:
                    otp_el = await page.query_selector('input[name="code"], input[name="otp"]')
                    if otp_el:
                        otp = await asyncio.to_thread(auto_read_otp_sync, timeout=60)
                        if otp:
                            await otp_el.fill(otp)
                            logger.info("Patchright: OTP submitted")
                            await asyncio.sleep(5)
                except Exception:
                    pass

            # Navigate to trade page
            await page.goto(
                "https://market-qx.trade/en/trade",
                wait_until="domcontentloaded", timeout=60000
            )
            await asyncio.sleep(3)

            # Extract token
            token = await page.evaluate("""
                () => {
                    try { if (window.settings && window.settings.token) return window.settings.token; } catch(e) {}
                    try {
                        var scripts = document.querySelectorAll('script');
                        for (var i = 0; i < scripts.length; i++) {
                            var t = scripts[i].textContent;
                            if (t.includes('token')) {
                                var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                                if (m) return m[1];
                            }
                        }
                    } catch(e) {}
                    try { var s = document.cookie.match(/ssid=([^;]+)/); return s ? s[1] : null; } catch(e) {}
                    return null;
                }
            """)
            if not token:
                cookies = await context.cookies()
                for c in cookies:
                    if "ssid" in c["name"].lower():
                        token = c["value"]
                        break

            ua = await page.evaluate("navigator.userAgent")
            logger.info("Patchright: token: %s...%s", token[:8] if token else "None", token[-4:] if token else "")

            await browser.close()
    except Exception as e:
        logger.error("Patchright login failed: %s", e)

    if token:
        save_session(email, token, ua or "")
    return token


async def _camoufox_login() -> str | None:
    """Login via Camoufox (custom Firefox build with C++ stealth).
    Works on both Windows and Linux. Bypasses Cloudflare reliably."""
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        return None

    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        logger.error("camoufox not installed. Run: pip install camoufox[geoip] && python -m camoufox fetch")
        return None

    token = None
    ua = None
    try:
        # Optional proxy from env var: TELEGRAM_PROXY, QUOTEX_PROXY, or CAMOUFOX_PROXY
        proxy_cfg = None
        proxy_env = os.getenv("TELEGRAM_PROXY") or os.getenv("QUOTEX_PROXY") or os.getenv("CAMOUFOX_PROXY")
        if proxy_env:
            proxy_cfg = {"server": proxy_env}
            logger.info("Camoufox: using proxy from env")

        async with AsyncCamoufox(
            humanize=True,
            geoip=True,
            disable_coop=True,
            headless=True,
            proxy=proxy_cfg,
            firefox_user_prefs={
                # Skip glxtest/GPU detection — missing glxtest binary SIGSEGVs
                # on headless Linux containers (daijro/camoufox#456)
                "gfx.xrender.enabled": False,
                "layers.acceleration.disabled": True,
                "gfx.canvas.accelerated": False,
                "webgl.disabled": True,
                "webgl.enable-webgl2": False,
                "gfx.x11-egl.force-disabled": True,
                # Disable Firefox prompts that block in non-interactive envs
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

            # Block navigation redirect to qxbroker.com but allow sub-resources
            async def block_qxbroker_nav(route):
                url = route.request.url
                if "qxbroker.com" in url and route.request.resource_type == "document":
                    logger.info("Camoufox: blocked nav redirect to qxbroker.com")
                    await route.abort()
                else:
                    await route.continue_()
            await page.route("**/*", block_qxbroker_nav)

            logger.info("Camoufox: navigating to sign-in page...")
            resp = None
            try:
                resp = await page.goto(
                    "https://market-qx.trade/en/sign-in/",
                    wait_until="domcontentloaded", timeout=120000
                )
            except Exception:
                pass

            final_url = page.url
            logger.info("Camoufox: URL after nav: %s", final_url)

            # Retry with navigation redirect blocked if we got redirected
            if "qxbroker.com" in final_url:
                logger.info("Camoufox: server redirected to qxbroker.com, retrying with redirect blocked...")
                await page.goto(
                    "about:blank",
                    wait_until="domcontentloaded", timeout=10000
                )
                await asyncio.sleep(1)
                try:
                    await page.goto(
                        "https://market-qx.trade/en/sign-in/",
                        wait_until="domcontentloaded", timeout=120000
                    )
                except Exception:
                    pass
                final_url = page.url
                logger.info("Camoufox: URL after retry: %s", final_url)

            # Handle Cloudflare if present
            title = await page.title()
            if "Just a moment" in title:
                logger.info("Camoufox: Cloudflare detected, waiting...")
                try:
                    await page.wait_for_function(
                        "() => !document.title.includes('Just a moment')",
                        timeout=120000
                    )
                    logger.info("Camoufox: Cloudflare passed")
                except Exception:
                    logger.warning("Camoufox: Cloudflare still active, continuing...")

            await asyncio.sleep(3)

            # Fill login form (visible inputs, second set)
            login_result = await page.evaluate(
                """
                (args) => {
                    var emails = document.querySelectorAll('input[name="email"]');
                    var passes = document.querySelectorAll('input[name="password"]');
                    if (!emails.length || !passes.length) return "no inputs found";
                    var email = emails.length > 1 ? emails[1] : emails[0];
                    var pass = passes.length > 1 ? passes[1] : passes[0];
                    email.value = args[0];
                    pass.value = args[1];
                    email.dispatchEvent(new Event('input', { bubbles: true }));
                    pass.dispatchEvent(new Event('input', { bubbles: true }));
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var b = buttons[i];
                        if (b.textContent.trim() === "Sign in" && b.offsetParent !== null) {
                            b.click();
                            return "clicked Sign in";
                        }
                    }
                    return "Sign in button not found";
                }
                """,
                [email, password]
            )
            logger.info("Camoufox: form result: %s", login_result)
            if login_result == "no inputs found":
                logger.info("Camoufox: current URL: %s", page.url)
                logger.info("Camoufox: page title: %s", await page.title())
            await asyncio.sleep(10)

            # Navigate to trade page if not already there
            if "/trade" not in page.url:
                try:
                    await page.goto(
                        "https://market-qx.trade/en/trade",
                        wait_until="domcontentloaded", timeout=60000
                    )
                    await asyncio.sleep(5)
                except Exception:
                    pass

            logger.info("Camoufox: trade URL: %s", page.url)

            # Extract token — poll/wait for up to 60s instead of one-shot.
            # The SSID cookie / window.settings.token is written only after the
            # trade SPA's websocket auth completes, which is slower over a
            # proxy on servers (was returning None on the VPS).
            token = None
            extract_js = """
                () => {
                    try { if (window.settings && window.settings.token) return window.settings.token; } catch(e) {}
                    try {
                        var scripts = document.querySelectorAll('script');
                        for (var i = 0; i < scripts.length; i++) {
                            var t = scripts[i].textContent;
                            if (t && t.includes('token')) {
                                var m = t.match(/["']token["']\\s*[:=]\\s*["']([^"']+)["']/);
                                if (m) return m[1];
                            }
                        }
                    } catch(e) {}
                    try { var s = document.cookie.match(/ssid=([^;]+)/); return s ? s[1] : null; } catch(e) {}
                    try { var l = localStorage.getItem('token') || localStorage.getItem('ssid'); if (l) return l; } catch(e) {}
                    try { var st = sessionStorage.getItem('token') || sessionStorage.getItem('ssid'); if (st) return st; } catch(e) {}
                    return null;
                }
            """
            for _attempt in range(20):  # 20 x 3s = up to 60s
                try:
                    token = await page.evaluate(extract_js)
                except Exception:
                    token = None
                if not token:
                    try:
                        cookies = await page.context.cookies()
                        for c in cookies:
                            if "ssid" in c["name"].lower():
                                if c.get("value"):
                                    token = c["value"]
                                    break
                    except Exception:
                        pass
                if token:
                    break
                await asyncio.sleep(3)

            ua = await page.evaluate("navigator.userAgent")
            logger.info("Camoufox: token: %s...%s", token[:8] if token else "None", token[-4:] if token else "")
    except Exception as e:
        logger.error("Camoufox login failed: %s", e)

    if token:
        save_session(email, token, ua or "")
    return token


async def renew_ssid(force_playwright: bool = False) -> str | None:
    """Renew SSID: Camoufox (primary, cross-platform), Kameleo (Windows), falls back to undetected-chromedriver."""
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        logger.error("QUOTEX_EMAIL / QUOTEX_PASSWORD not set in .env")
        return None

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("SSID renewal attempt %d/%d...", attempt, MAX_RETRIES)

        # Camoufox works on both Windows and Linux
        try:
            token = await _camoufox_login()
            if token:
                return token
        except Exception as e:
            last_err = e
            logger.warning("Camoufox attempt %d failed: %s", attempt, e)

        # Kameleo fallback (Windows only)
        if not _is_linux():
            try:
                token = await _kameleo_login()
                if token:
                    return token
            except Exception as e:
                last_err = e
                logger.warning("Kameleo attempt %d failed: %s", attempt, e)

        # Fallback to undetected-chromedriver
        try:
            token = await asyncio.to_thread(_uc_login)
            if token:
                return token
        except Exception as e:
            last_err = e
            logger.warning("UC fallback attempt %d failed: %s", attempt, e)

        if attempt < MAX_RETRIES:
            wait = attempt * 10
            logger.info("Retrying in %ds...", wait)
            await asyncio.sleep(wait)

    logger.error("SSID renewal failed after %d attempts: %s", MAX_RETRIES, last_err)
    return None


async def renew_ssid_playwright(headless: bool = True) -> str | None:
    return await renew_ssid()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    token = asyncio.run(renew_ssid())
    if token:
        print(f"\nToken: {token}")
    else:
        print("\nFailed to renew SSID")
