"""Adapter using pyquotex with real SSID from browser session.

Auto-renews expired SSID via Playwright headless login + IMAP OTP."""

import os, json, asyncio, logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

_client: Optional['Quotex'] = None


class SimpleCandle:
    def __init__(self, data: list):
        self.timestamp = datetime.fromtimestamp(data[0])
        self.open = float(data[1])
        self.close = float(data[2])
        self.high = float(data[3])
        self.low = float(data[4])
        self.volume = float(data[5]) if len(data) > 5 else 0.0


def load_session() -> dict | None:
    session_file = os.path.join(os.path.dirname(__file__), "session.json")
    try:
        with open(session_file) as f:
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


async def _connect_with_token(email, token, session):
    from pyquotex.stable_api import Quotex
    client = Quotex(
        email=email,
        password='not-needed',
        host='market-quotex.pro',
        lang='en',
        wss_url_override='wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket',
    )
    client.set_account_mode("REAL")
    client.set_session(
        user_agent=session.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        cookies=session.get("cookies"),
        ssid=token,
    )
    ok, msg = await client.connect()
    if not ok:
        await client.close()
        return None, msg
    await client.api.event_registry.wait_event("instruments_ready", timeout=15)
    return client, None


async def get_quotex_connection():
    global _client

    if _client is not None:
        try:
            b = await _client.get_balance()
            if b is not None:
                return _client
        except Exception:
            pass
        try:
            await _client.close()
        except Exception:
            pass
        _client = None

    email = os.getenv("QUOTEX_EMAIL")
    if not email:
        raise ConnectionError("QUOTEX_EMAIL not set")

    session = load_session()
    token = session.get("token") if session else None

    # First attempt with existing token
    if token:
        _client, err = await _connect_with_token(email, token, session)
        if _client:
            logger.info("Quotex connected via existing SSID")
            return _client
        logger.warning("SSID expired or invalid, attempting auto-renew...")

    # Auto-renew SSID via Playwright
    logger.info("Auto-renewing SSID via Playwright headless login...")
    try:
        from renew_ssid import renew_ssid_playwright
        new_token = await renew_ssid_playwright(headless=True)
    except Exception as e:
        logger.error("SSID renewal process failed: %s", e)
        new_token = None

    if not new_token:
        raise ConnectionError("Auto-renew failed. Set IMAP_PASSWORD in .env for auto-OTP, "
                              "or manually run: python playwright_login_otp.py --headed")

    session = load_session()
    _client, err = await _connect_with_token(email, new_token, session)
    if not _client:
        raise ConnectionError(f"pyquotex connect failed after renewal: {err}")

    logger.info("Quotex connected via fresh SSID (auto-renewed)")
    return _client


async def close_quotex_connection():
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            pass
    _client = None


async def fetch_candles(client, token: str, count: int = 18000, timeframe: int = 60) -> list | None:
    try:
        amount = max(count, 3600)
        candles = await client.get_historical_candles(
            asset=token,
            amount_of_seconds=amount,
            period=timeframe,
            timeout=15,
            max_workers=3,
        )
        if not candles:
            return None
        return [{"time": int(c['time']), "open": float(c['open']), "close": float(c['close']),
                 "high": float(c['high']), "low": float(c['low']), "volume": float(c.get('volume', 0))}
                for c in candles]
    except Exception as e:
        logger.error(f"fetch_candles failed for {token}: {e}")
        return None


async def _get_instruments(client) -> list:
    """Get raw instruments list from pyquotex client."""
    instruments = await client.get_instruments()
    if not instruments:
        return []
    if isinstance(instruments, dict) and 'name' in instruments:
        return [instruments]
    if isinstance(instruments, list):
        return instruments
    return []


def _get_sym(item) -> tuple[str, int, str]:
    """Extract (symbol, payout, type) from list or dict instrument."""
    if isinstance(item, dict):
        name = str(item.get('name', ''))
        payout_raw = item.get('profit', {})
        payout = int(payout_raw.get('min', 80)) if isinstance(payout_raw, dict) else int(payout_raw)
        typ = str(item.get('type', 'currency'))
        return name, payout, typ
    if isinstance(item, (list, tuple)) and len(item) >= 6:
        return str(item[1]), int(item[5]), str(item[3])
    return '', 80, 'currency'


async def get_active_pairs(client) -> dict:
    try:
        instruments = await _get_instruments(client)
    except Exception:
        return {"OTC": [], "REAL": [], "CRYPTO": []}

    otc, real, crypto = [], [], []
    for item in instruments:
        sym, payout, typ = _get_sym(item)
        if not sym:
            continue
        typ_lower = typ.lower()
        is_otc = "_otc" in sym.lower()
        if typ_lower != 'currency':
            crypto.append((payout, sym))
        elif is_otc:
            otc.append((payout, sym))
        else:
            real.append((payout, sym))

    sort_key = lambda x: (-x[0], x[1])
    return {"OTC": sorted(otc, key=sort_key), "REAL": sorted(real, key=sort_key), "CRYPTO": sorted(crypto, key=sort_key)}


async def get_asset_payout(client, asset: str) -> int:
    try:
        for item in await _get_instruments(client):
            sym, payout, _ = _get_sym(item)
            if sym == asset:
                return payout
    except Exception:
        pass
    return 80
