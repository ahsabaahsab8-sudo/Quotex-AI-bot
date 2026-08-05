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
MAX_RETRIES = 3

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
    """
    global _SOCKS_RELAY
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
        # Proxy from env: CAMOUFOX_PROXY, QUOTEX_PROXY, then TELEGRAM_PROXY.
        # Camoufox must use the Quotex proxy, NOT the Telegram proxy.
        # SOCKS5-with-auth proxies get a local no-auth relay (Playwright cannot
        # authenticate SOCKS5); everything else is passed straight through.
        proxy_cfg = _ensure_socks_relay()
        if proxy_cfg:
            logger.info("Camoufox: using proxy from env")

        async with AsyncCamoufox(
            humanize=True,
            geoip=False,
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
            logger.info("Camoufox: form result: %s", login_result)
            if login_result == "no inputs found":
                logger.info("Camoufox: current URL: %s", page.url)
                logger.info("Camoufox: page title: %s", await page.title())
            await asyncio.sleep(7)

            # If Quotex demands a verification code (new IP login), the page
            # stays on /sign-in. Auto-fill it from Gmail via Gmail API OTP reader.
            if "/sign-in" in page.url.lower():
                logger.info("Camoufox: checking for OTP input...")
                otp_el = None
                for _ in range(6):  # up to ~18s for the OTP field to appear
                    try:
                        otp_el = await page.query_selector(
                            'input[name="code"], input[name="otp"], '
                            'input[autocomplete="one-time-code"]'
                        )
                    except Exception:
                        otp_el = None
                    if otp_el:
                        break
                    await asyncio.sleep(3)
                if otp_el:
                    otp = await asyncio.to_thread(auto_read_otp_sync, timeout=120, since=login_ts)
                    if otp:
                        try:
                            await otp_el.fill(otp)
                            logger.info("Camoufox: OTP submitted")
                            # The OTP form needs an explicit submit (button or
                            # Enter), otherwise Quotex never processes the code.
                            try:
                                submit = await page.query_selector('button[type="submit"]')
                                if submit:
                                    await submit.click()
                                    logger.info("Camoufox: OTP submit button clicked")
                                else:
                                    await page.keyboard.press("Enter")
                                    logger.info("Camoufox: pressed Enter on OTP form")
                            except Exception as e:
                                logger.warning("Camoufox: OTP submit click failed (%s), pressing Enter", e)
                                await page.keyboard.press("Enter")
                            await asyncio.sleep(10)
                        except Exception as e:
                            logger.warning("Camoufox: OTP fill failed: %s", e)
                    else:
                        logger.warning("Camoufox: OTP input present but no code read from Gmail")

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
    """Renew SSID: Camoufox (primary), then Kameleo -> undetected-chromedriver,
    with OpenClaw as a final fallback.

    Camoufox is the main token-extraction path (custom Firefox build that
    bypasses Cloudflare), routing through the Quotex proxy from .env.
    OpenClaw (openclaw_renewal.renew_via_openclaw) remains only as a fallback.
    """
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    if not email or not password:
        logger.error("QUOTEX_EMAIL / QUOTEX_PASSWORD not set in .env")
        return None

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("SSID renewal attempt %d/%d...", attempt, MAX_RETRIES)

        # PRIMARY: Camoufox (works on both Windows and Linux)
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

    # FINAL FALLBACK: OpenClaw agent (only reached if all above failed)
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
    token = asyncio.run(renew_ssid())
    if token:
        print(f"\nToken: {token}")
    else:
        print("\nFailed to renew SSID")
