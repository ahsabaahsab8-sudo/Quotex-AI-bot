"""Session keeper for Quotex — auto-fetches SSID, saves to session.json, auto-refreshes on expiry."""

import os
import json
import asyncio
import time
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")
API_BASE = "https://market-qx.trade"


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
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
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


async def refresh_token_via_api(email: str, password: str) -> str | None:
    from curl_cffi import requests
    try:
        sess = requests.Session(impersonate="chrome110")
        r = sess.post(
            f"{API_BASE}/api/v1/sign-in",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": API_BASE,
            },
            json={"email": email, "password": password},
            timeout=30,
        )
        data = r.json()
        token = data.get("result", {}).get("session")
        if token and len(token) >= 8:
            return token
        logger.error(f"API login failed: {data}")
        return None
    except Exception as e:
        logger.error(f"API login error: {e}")
        return None


class QuotexSessionKeeper:
    """Wraps ChipaDevTeam QuotexAPI with automatic SSID refresh + keepalive."""

    def __init__(self, email: str, password: str, is_demo: bool = True):
        self.email = email
        self.password = password
        self.is_demo = is_demo
        self.api = None
        self._ssid: str | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._connected = False

    @property
    def ssid(self) -> str | None:
        return self._ssid

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> bool:
        ssid = await self._resolve_ssid()
        if not ssid:
            logger.error("Could not obtain SSID")
            return False
        self._ssid = ssid
        ok = await self._connect_with_ssid(ssid)
        if not ok:
            return False
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        return True

    async def stop(self):
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        if self.api:
            try:
                await self.api.disconnect()
            except Exception:
                pass
        self._connected = False

    async def _resolve_ssid(self) -> str | None:
        saved = load_session()
        if saved and saved.get("token"):
            token = saved["token"]
            logger.info(f"Loaded SSID from session.json: {token[:12]}...")
            return token
        logger.info("No saved SSID, fetching fresh token...")
        token = await refresh_token_via_api(self.email, self.password)
        if token:
            save_session(self.email, token)
            return token
        return None

    async def _connect_with_ssid(self, ssid: str) -> bool:
        try:
            from QuotexAPI import QuotexAPI, QuotexConfig
            cfg = QuotexConfig(
                QUOTEX_SSID=ssid,
                QUOTEX_IS_DEMO=self.is_demo,
                _env_file=None,
            )
            self.api = QuotexAPI(config=cfg)
            await self.api.connect()
            profile = await self.api.login_with_ssid()
            logger.info(f"Connected: {profile.email}")
            self._connected = True
            return True
        except Exception as e:
            logger.warning(f"SSID connection failed: {e}")
            return False

    async def _refresh_and_reconnect(self) -> bool:
        logger.info("Refreshing SSID...")
        token = await refresh_token_via_api(self.email, self.password)
        if not token:
            logger.error("Token refresh failed")
            return False
        self._ssid = token
        save_session(self.email, token)
        if self.api:
            try:
                await self.api.disconnect()
            except Exception:
                pass
        ok = await self._connect_with_ssid(token)
        if ok:
            logger.info("Reconnected with fresh SSID")
        return ok

    async def _watchdog_loop(self):
        ping_interval = 15
        while True:
            await asyncio.sleep(ping_interval)
            try:
                if self.api and self.api.is_connected:
                    continue
            except Exception:
                pass
            logger.warning("Connection lost, attempting reconnection...")
            ok = await self._refresh_and_reconnect()
            if not ok:
                logger.error("Watchdog: failed to reconnect")
                for attempt in range(3):
                    await asyncio.sleep(5 * (attempt + 1))
                    ok = await self._refresh_and_reconnect()
                    if ok:
                        break
                if not ok:
                    logger.critical("Watchdog: all reconnection attempts failed")
