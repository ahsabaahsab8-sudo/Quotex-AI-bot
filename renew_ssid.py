"""Auto-renew SSID via Kameleo+Playwright (bypasses Cloudflare), falls back to undetected-chromedriver."""

import os
import json
import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")
MAX_RETRIES = 6

# UID/message-id of the last OTP email consumed, so a stale code is never
# resubmitted on a later renewal attempt. Tracks message-ids via gmail_otp.
_last_otp_uid = None


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


def _extract_otp(text: str) -> str | None:
    """Extract the actual OTP pin from a Quotex 'Authentication pincode' email.

    The email is HTML-only; the first 4-6 digit string in the raw HTML is
    '1999' from the doctype (http://www.w3.org/1999/xhtml), so a naive regex
    returns the wrong code. Anchor on the 'PIN-code' label instead.
    """
    if not text:
        return None
    body = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.DOTALL | re.IGNORECASE)
    visible = re.sub(r"<[^>]+>", " ", body)
    m = re.search(
        r"(?:pin[-\s]?code|authentication\s*pin|verification\s*cod?e)"
        r"[^0-9]{0,60}?(\d{4,6})",
        visible, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    candidates = re.findall(r"\b(\d{4,6})\b", visible)
    for c in reversed(candidates):
        if c.strip("0") and c != "1999":
            return c
    return None


from gmail_otp import fetch_latest_otp


def auto_read_otp_sync(timeout: int = 120, since=None) -> str | None:
    """Read the latest Quotex pincode from Gmail FAST via the Gmail API.

    Uses OAuth2 (client_secret JSON + gmail_token.json) instead of IMAP, so
    no app password is needed. Only the newest genuine 'Authentication
    pincode' email sent after `since` is accepted, and each code is consumed
    exactly once (module-level message-id tracker in gmail_otp).
    """
    return fetch_latest_otp(timeout=timeout, since=since)


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
                otp = auto_read_otp_sync(timeout=120)
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
                        otp = await asyncio.to_thread(auto_read_otp_sync, timeout=120)
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
            login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
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
                        otp = await asyncio.to_thread(auto_read_otp_sync, timeout=120, since=login_ts)
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


def _parse_proxy(proxy_env: str) -> dict | None:
    """Parse a socks5:// or http(s):// proxy URL into Playwright's proxy dict.

    Returns {"server": "scheme://host:port", "username": ..., "password": ...},
    or None if it cannot be parsed.
    """
    try:
        from urllib.parse import urlparse, unquote
        parts = urlparse(proxy_env)
        if not parts.hostname or not parts.port:
            return None
        server = f"{parts.scheme}://{parts.hostname}:{parts.port}"
        cfg = {"server": server}
        if parts.username:
            cfg["username"] = unquote(parts.username)
        if parts.password:
            cfg["password"] = unquote(parts.password)
        return cfg
    except Exception as e:
        logger.error("Camoufox: failed to parse proxy %s: %s", proxy_env, e)
        return None


_SOCKS_RELAY = None


class _Socks5Relay:
    """Minimal local SOCKS5 relay (no auth) forwarding to an authenticated
    upstream SOCKS5 proxy.

    Playwright's Firefox cannot authenticate SOCKS5, so we expose an
    unauthenticated local endpoint (socks5://127.0.0.1:<port>) and tunnel to
    the real proxy (with user/pass from .env) using PySocks.
    """

    def __init__(self, upstream: str):
        from urllib.parse import urlparse, unquote
        parts = urlparse(upstream)
        self.host = parts.hostname
        self.port = parts.port
        self.username = unquote(parts.username) if parts.username else None
        self.password = unquote(parts.password) if parts.password else None
        self._server = None
        self._port = None

    @property
    def local_server(self) -> str:
        return f"socks5://127.0.0.1:{self._port}"

    def start(self) -> bool:
        import threading
        import socket as _sock
        try:
            self._server = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
            self._server.setsockopt(_sock.SOL_SOCKET, _sock.SO_REUSEADDR, 1)
            self._server.bind(("127.0.0.1", 0))
            self._server.listen(64)
            self._port = self._server.getsockname()[1]
            thread = threading.Thread(target=self._accept_loop, daemon=True)
            thread.start()
            logger.info("SOCKS relay up: %s -> %s:%s", self.local_server, self.host, self.port)
            return True
        except Exception as e:
            logger.error("Failed to start SOCKS relay: %s", e)
            return False

    def _accept_loop(self):
        import socket as _sock
        import threading as _threading
        while True:
            try:
                conn, _ = self._server.accept()
                _threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except Exception as e:
                logger.warning("SOCKS relay accept loop stopped: %s", e)
                break

    def _handle(self, client):
        import socket as _sock
        try:
            client.settimeout(60)
            ver = client.recv(1)
            if ver != b"\x05":
                client.close()
                return
            nmethods = client.recv(1)[0]
            client.recv(nmethods)
            client.sendall(b"\x05\x00")  # no auth

            header = client.recv(4)
            if len(header) != 4 or header[0] != 0x05 or header[1] != 0x01:
                client.close()
                return
            atyp = header[3]
            if atyp == 0x01:
                host = _sock.inet_ntoa(client.recv(4))
            elif atyp == 0x03:
                ln = client.recv(1)[0]
                host = client.recv(ln).decode()
            elif atyp == 0x04:
                host = _sock.inet_ntop(_sock.AF_INET6, client.recv(16))
            else:
                client.close()
                return
            port = int.from_bytes(client.recv(2), "big")

            import socks as _socks
            up = _socks.socksocket()
            up.settimeout(60)
            up.set_proxy(
                _socks.SOCKS5, self.host, self.port,
                username=self.username, password=self.password,
            )
            up.connect((host, port))

            client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            self._pump(client, up)
        except Exception as e:
            logger.warning("SOCKS relay connection error: %s", e)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _pump(self, client, upstream):
        import socket as _sock
        import select
        sockets = [client, upstream]
        while True:
            try:
                r, _, _ = select.select(sockets, [], [], 30)
                if not r:
                    continue
                for s in r:
                    data = s.recv(65536)
                    if not data:
                        return
                    dst = upstream if s is client else client
                    dst.sendall(data)
            except Exception:
                return


def _ensure_socks_relay() -> dict | None:
    """Return a Camoufox-compatible (no-auth) proxy dict for the env proxy.

    For socks5 proxies with credentials, spawn a local relay so Playwright can
    use it. For plain http(s)/no-auth socks5, use the proxy directly.
    Set CAMOUFOX_USE_PROXY=false in .env to disable proxy for Camoufox too.
    """
    global _SOCKS_RELAY
    if os.getenv("CAMOUFOX_USE_PROXY", "false").lower() not in ("true", "1", "yes"):
        logger.info("Camoufox proxy DISABLED (using VPS own IP, no proxy)")
        return None
    proxy_env = os.getenv("CAMOUFOX_PROXY") or os.getenv("QUOTEX_PROXY") or os.getenv("TELEGRAM_PROXY")
    if not proxy_env:
        return None
    from urllib.parse import urlparse
    parts = urlparse(proxy_env)
    has_auth = bool(parts.username or parts.password)
    if parts.scheme.startswith("socks") and has_auth:
        if _SOCKS_RELAY is None or _SOCKS_RELAY.host != parts.hostname or _SOCKS_RELAY.port != parts.port:
            relay = _Socks5Relay(proxy_env)
            if relay.start():
                _SOCKS_RELAY = relay
            else:
                return None
        return {"server": _SOCKS_RELAY.local_server}
    return _parse_proxy(proxy_env)


async def _camoufox_login(headed: bool = False) -> str | None:
    """Login via Camoufox. Uses natural mouse clicks + Gmail API for OTP."""
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        return None

    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        logger.error("camoufox not installed")
        return None

    # Bypass proxy for Gmail API
    os.environ["NO_PROXY"] = "googleapis.com,google.com"
    os.environ["no_proxy"] = "googleapis.com,google.com"

    token = None
    ua = None
    first_load = True
    try:
        proxy_cfg = _ensure_socks_relay()

        user_prefs = {
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
            "browser.downdown.enabled": True,
        }
        if proxy_cfg:
            user_prefs["network.proxy.type"] = 1
            user_prefs["network.proxy.no_proxies_on"] = "localhost, 127.0.0.1"

        async with AsyncCamoufox(
            humanize=True,
            geoip=False,
            disable_coop=True,
            headless=not headed,
            proxy=proxy_cfg,
            firefox_user_prefs=user_prefs,
        ) as browser:
            page = await browser.new_page()

            for attempt in range(10):
                try:
                    logger.info("[1] Loading sign-in page...")
                    await page.goto("https://market-qx.trade/en/sign-in/", wait_until="domcontentloaded", timeout=60000)
                    break
                except Exception as e:
                    logger.warning("[1] Nav failed: %s", e)
                    await asyncio.sleep(5)

            # Wait for Cloudflare challenge to clear (challenge URL has __cf_chl_tk)
            try:
                for _ in range(60):
                    if "__cf_chl_tk" not in page.url.lower():
                        break
                    await asyncio.sleep(3)
            except Exception:
                pass

            # Wait: 30s first time (direct VPS is fast), 120s if proxy is slow
            using_proxy = os.getenv("CAMOUFOX_USE_PROXY", "false").lower() in ("true", "1", "yes")
            wait_time = 120 if (first_load and using_proxy) else (30 if first_load else 40)
            first_load = False
            logger.info("[2] Waiting %ds for page render...", wait_time)
            await asyncio.sleep(wait_time)
            logger.info("[2] Page ready: %s", page.url)

            # Check geo-block
            try:
                body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                if "not available in your region" in body_text:
                    logger.warning("[2] GEO BLOCKED — retrying on new IP...")
                    return None
            except Exception:
                pass

            # Fill login form via JS (robust vs Cloudflare/coordinate-clicks hanging)
            _FILL_LOGIN_JS = """
            (args) => {
                var emails = document.querySelectorAll('input[name="email"]');
                var passes = document.querySelectorAll('input[name="password"]');
                if (!emails.length || !passes.length) return "no inputs found";
                var email = emails.length > 1 ? emails[1] : emails[0];
                var pass = passes.length > 1 ? passes[1] : passes[0];
                if (!email.offsetParent || !pass.offsetParent) return "inputs not visible";
                email.focus();
                email.value = args[0];
                email.dispatchEvent(new Event('input', { bubbles: true }));
                email.dispatchEvent(new Event('change', { bubbles: true }));
                pass.focus();
                pass.value = args[1];
                pass.dispatchEvent(new Event('input', { bubbles: true }));
                pass.dispatchEvent(new Event('change', { bubbles: true }));
                return "filled";
            }
            """
            fill_res = await page.evaluate(_FILL_LOGIN_JS, [email, password])
            logger.info("[3] Login form fill: %s", fill_res)
            if fill_res != "filled":
                logger.error("[3] Email/password input not found or not visible")
                return None

            # Click Sign in via JS (prefer form submit, fall back to button click)
            _CLICK_SIGNIN_JS = """
            () => {
                var form = document.querySelector('form');
                if (form && form.requestSubmit) {
                    try { form.requestSubmit(); return "requestSubmit"; } catch (e) {}
                }
                var btns = document.querySelectorAll('button, input[type="submit"]');
                for (var i = 0; i < btns.length; i++) {
                    var b = btns[i];
                    var txt = (b.innerText || b.value || '').trim().toLowerCase();
                    if (txt.includes('sign') || txt.includes('log') || txt.includes('enter') || txt.includes('submit')) {
                        if (b.offsetParent !== null) { b.click(); return "clicked:" + txt; }
                    }
                }
                return "no submit found";
            }
            """
            click_res = await page.evaluate(_CLICK_SIGNIN_JS)
            logger.info("[5] Sign-in submit: %s", click_res)

            login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
            logger.info("[5] CLICKED!")

            # Watch for OTP or /trade
            logger.info("[6] Watching page...")
            otp_detected = False
            for i in range(90):
                await asyncio.sleep(2)
                elapsed = (i+1)*2
                try:
                    state = await asyncio.wait_for(page.evaluate("""
                        () => ({
                            url: location.href,
                            isTrade: location.href.includes('/trade'),
                            otpVisible: Array.from(document.querySelectorAll('input[name="code"]')).some(el => el.offsetParent !== null && window.getComputedStyle(el).display !== 'none')
                        })
                    """), timeout=15)
                except Exception:
                    continue
                if state["isTrade"]:
                    logger.info("[6] [%ds] ON TRADE!", elapsed)
                    break
                if state["otpVisible"]:
                    logger.info("[6] [%ds] OTP PAGE!", elapsed)
                    otp_detected = True
                    break
                if elapsed % 20 == 0:
                    logger.info("[6] [%ds] URL: %s", elapsed, state["url"])
            else:
                logger.error("[6] TIMEOUT")
                return None

            # OTP
            if otp_detected:
                logger.info("[7] Getting OTP from Gmail API...")
                otp = await asyncio.to_thread(auto_read_otp_sync, timeout=150, since=login_ts)
                if not otp:
                    logger.error("[7] No OTP received")
                    return None

                logger.info("[7] OTP: %s", otp)
                otp_pos = await page.evaluate("""
                    () => {
                        var el = document.querySelector('input[name="code"]');
                        if (!el) return null;
                        var r = el.getBoundingClientRect();
                        if (r.width === 0) return null;
                        return {x: r.x+r.width/2, y: r.y+r.height/2};
                    }
                """)
                if not otp_pos:
                    logger.error("[7] OTP input not found")
                    return None

                await page.mouse.click(otp_pos["x"], otp_pos["y"])
                await asyncio.sleep(0.5)
                await page.keyboard.type(otp, delay=100)
                await page.keyboard.press("Enter")
                logger.info("[7] OTP submitted")

                for i in range(30):
                    await asyncio.sleep(3)
                    if "/trade" in page.url.lower():
                        logger.info("[7] [%ds] ON TRADE!", (i+1)*3)
                        break

            # Navigate to trade if needed
            if "/trade" not in page.url.lower():
                try:
                    await page.goto("https://market-qx.trade/en/trade", wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(10)
                except Exception:
                    pass

            logger.info("[8] Extracting token... URL: %s", page.url)

            token = None
            for i in range(40):
                try:
                    cookies = await page.context.cookies()
                    for c in cookies:
                        if "ssid" in c["name"].lower() and c.get("value"):
                            token = c["value"]
                            break
                except Exception:
                    pass
                if not token:
                    try:
                        token = await page.evaluate("() => window.settings?.token || null")
                    except Exception:
                        pass
                if token:
                    break
                await asyncio.sleep(3)

            ua = await page.evaluate("navigator.userAgent")
            logger.info("[8] Token: %s...%s", token[:15] if token else "None", token[-5:] if token else "")
    except Exception as e:
        logger.error("Camoufox login failed: %s", e)

    if token:
        save_session(email, token, ua or "")
    return token


async def renew_ssid(force_playwright: bool = False, headed: bool = False) -> str | None:
    """Renew SSID via Camoufox ONLY (routed through the proxy from .env).

    The proxy is a rotating residential proxy, so some attempts land on exit
    IPs that Quotex geo-blocks ("not available in your region"). Each Camoufox
    launch gets a fresh exit IP, so we simply retry a few times until one isn't
    blocked. OpenClaw remains only as a final fallback.
    """
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        logger.error("QUOTEX_EMAIL / QUOTEX_PASSWORD not set in .env")
        return None

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("SSID renewal attempt %d/%d (Camoufox direct, no proxy)...", attempt, MAX_RETRIES)
        try:
            token = await _camoufox_login(headed=headed)
            if token:
                return token
        except Exception as e:
            last_err = e
            logger.warning("Camoufox attempt %d failed: %s", attempt, e)

        if attempt < MAX_RETRIES:
            wait = 8
            logger.info("Retrying in %ds (new exit IP)...", wait)
            await asyncio.sleep(wait)

    # FINAL FALLBACK: OpenClaw agent (only reached if Camoufox never succeeded)
    try:
        from openclaw_renewal import renew_via_openclaw
        token = await renew_via_openclaw()
        if token:
            return token
        logger.warning("OpenClaw renewal failed; giving up.")
    except Exception as e:
        logger.warning("OpenClaw renewal error: %s", e)

    logger.error("SSID renewal failed after %d attempts: %s", MAX_RETRIES, last_err)
    return None


async def renew_ssid_playwright(headless: bool = True) -> str | None:
    return await renew_ssid()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    headed = "--headed" in sys.argv
    token = asyncio.run(renew_ssid(headed=headed))
    if token:
        print(f"\nToken: {token}")
    else:
        print("\nFailed to renew SSID")
