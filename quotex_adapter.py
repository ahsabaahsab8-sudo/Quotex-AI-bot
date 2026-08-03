"""Adapter using pyquotex with auto-renewing SSID.

Primary renewal: API-based (fast, no browser).
Fallback: Playwright headless login + IMAP OTP.
Proactive watchdog refreshes token every 20 min before expiry."""

import os
import json
import time
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_client = None
_watchdog_task = None
TOKEN_REFRESH_INTERVAL = 1200  # 20 minutes

# Every timeframe Quotex can expose, in seconds.
SUPPORTED_TIMEFRAMES = [
    1, 5, 15, 30, 60, 120, 180, 300, 600, 900,
    1800, 2700, 3600, 7200, 10800, 14400, 86400, 604800,
]

# Per-pair active timeframe cache: {pair: {"tfs": [...], "ts": epoch}}
_TIMEFRAME_CACHE: dict[str, dict] = {}
_TIMEFRAME_CACHE_TTL = 300.0  # 5 minutes

# Raw instrument rows parsed once and reused for timeframe extraction.
_instruments_tf_index = {"data": {}, "ts": 0.0}
_INSTRUMENTS_INDEX_TTL = 60.0


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
    proxy_str = os.getenv("QUOTEX_PROXY") or os.getenv("TELEGRAM_PROXY") or ""
    proxies = None
    if proxy_str:
        _install_proxy_patch(proxy_str)
        logger.info("pyquotex: connecting to Quotex via proxy %s", proxy_str)
        proxies = {"http": proxy_str, "https": proxy_str}
    else:
        logger.info("pyquotex: connecting to Quotex DIRECTLY (no proxy)")
    client = Quotex(
        email=email,
        password='not-needed',
        host='market-quotex.pro',
        lang='en',
        wss_url_override='wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket',
        proxies=proxies,
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
    await client.api.event_registry.wait_event("instruments_ready", timeout=30)
    return client, None


def _install_proxy_patch(proxy_str: str) -> None:
    """Force pyquotex's HTTP (httpx) and WebSocket transports through the proxy.

    Stock pyquotex ignores the ``proxies`` parameter: ``Browser()`` is built
    with no args in ``api.py`` and ``websockets.connect()`` has no proxy arg,
    so both connection points are patched at runtime here.
    """
    if getattr(_install_proxy_patch, "_installed", None) == proxy_str:
        return

    import httpx
    import websockets
    if int(websockets.__version__.split(".")[0]) < 15:
        raise ConnectionError(
            "pyquotex proxy patch requires websockets>=15 "
            f"(found {websockets.__version__}). Run: pip install -U websockets"
        )
    import pyquotex.api as api_mod
    import pyquotex.network.navigator as nav_mod
    from pyquotex.network.navigator import Browser as _OrigBrowser
    from pyquotex.network.ssl_utils import (
        create_ssl_context,
        CIPHER_SUITE_FIREFOX,
    )
    from pyquotex.ws.client import WebsocketClient

    class _ProxyBrowser(_OrigBrowser):
        def __init__(self, *args, **kwargs):
            self.response = None
            self.default_headers = None
            self.source_address = kwargs.pop("source_address", None)
            self.server_hostname = kwargs.pop("server_hostname", None)
            self.proxies = proxy_str
            self.debug = kwargs.pop("debug", False)
            self._ssl_context = create_ssl_context(cipher_suite=CIPHER_SUITE_FIREFOX)
            if self.server_hostname:
                self._ssl_context.check_hostname = False
            self.headers = self.get_headers()
            self._client = httpx.AsyncClient(
                verify=self._ssl_context,
                timeout=30.0,
                follow_redirects=True,
                proxy=proxy_str,
            )

    _orig_connect_once = WebsocketClient._connect_once

    async def _proxy_connect_once(self, url, extra_headers, ssl):
        headers = extra_headers or {}
        async with websockets.connect(
            url,
            additional_headers=headers,
            ssl=ssl,
            proxy=proxy_str,
            ping_interval=24,
            ping_timeout=20,
            max_size=2 ** 23,
            compression=None,
        ) as ws:
            self._ws = ws
            self.api.last_message_at = time.monotonic()
            await self.api._on_open()
            self._open_count += 1
            if self._open_count > 1:
                asyncio.create_task(self._replay_subscriptions())
            self._start_watchdog()
            try:
                async for raw in ws:
                    await self.api._on_message(raw)
            finally:
                self._stop_watchdog()

    nav_mod.Browser = _ProxyBrowser
    api_mod.Browser = _ProxyBrowser
    WebsocketClient._connect_once = _proxy_connect_once
    _install_proxy_patch._installed = proxy_str
    logger.info("pyquotex proxy patch installed: %s", proxy_str)


async def _renew_token() -> str | None:
    """Renew SSID — OpenClaw agent first, then Camoufox/Playwright fallbacks.

    renew_ssid() already tries the OpenClaw agent (openclaw_renewal) before
    its built-in browser methods, so this just delegates to it."""
    from renew_ssid import renew_ssid
    return await renew_ssid(force_playwright=False)


async def _watchdog_loop():
    """Proactively refresh the SSID every TOKEN_REFRESH_INTERVAL seconds
    so the token never expires between signal requests."""
    while True:
        await asyncio.sleep(TOKEN_REFRESH_INTERVAL)
        logger.info("Watchdog: proactively refreshing SSID...")
        try:
            new_token = await _renew_token()
            if new_token:
                logger.info("Watchdog: SSID refreshed successfully")
            else:
                logger.warning("Watchdog: SSID refresh failed, will retry next cycle")
        except Exception as e:
            logger.error(f"Watchdog: SSID refresh error: {e}")


def start_watchdog():
    global _watchdog_task
    if _watchdog_task is None or _watchdog_task.done():
        _watchdog_task = asyncio.create_task(_watchdog_loop())
        logger.info("Token watchdog started (refresh every %ds)", TOKEN_REFRESH_INTERVAL)


def stop_watchdog():
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()
        _watchdog_task = None
        logger.info("Token watchdog stopped")


async def _connect_with_retries(email, token, session, attempts=4, delay=3):
    """Try connecting with a token several times before giving up.

    Proxy hiccups are transient; retrying the same still-valid token avoids
    triggering a costly Camoufox re-login on every brief proxy failure.
    Backs off a bit between attempts (3s, 6s, 10s, ...).
    """
    last_err = None
    for i in range(1, attempts + 1):
        client, err = await _connect_with_token(email, token, session)
        if client:
            return client, None
        last_err = err
        if i < attempts:
            wait = delay * i
            logger.warning(
                "Connection attempt %d/%d failed (%s); retrying in %ds...",
                i, attempts, err, wait,
            )
            await asyncio.sleep(wait)
    return None, last_err


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

    if token:
        _client, err = await _connect_with_retries(email, token, session)
        if _client:
            logger.info("Quotex connected via existing SSID")
            start_watchdog()
            return _client
        logger.warning("SSID connection failed after retries (%s); attempting auto-renew...", err)

    logger.info("Auto-renewing SSID...")
    try:
        new_token = await _renew_token()
    except Exception as e:
        logger.error("SSID renewal process failed: %s", e)
        new_token = None

    if not new_token:
        raise ConnectionError("Auto-renew failed. Ensure QUOTEX_EMAIL / QUOTEX_PASSWORD / IMAP_PASSWORD "
                              "are set in .env")

    session = load_session()
    _client, err = await _connect_with_retries(email, new_token, session)
    if not _client:
        raise ConnectionError(f"pyquotex connect failed after renewal: {err}")

    logger.info("Quotex connected via fresh SSID (auto-renewed)")
    start_watchdog()
    return _client


async def close_quotex_connection():
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            pass
    _client = None


def _ticks_to_candles(ticks: list[dict], period: int) -> list[dict]:
    """Aggregate raw Quotex tick rows ({time, price, ...}) into OHLC candles.

    For sub-minute periods (e.g. 30s) history/load returns per-tick price
    rows instead of OHLC candles, so pyquotex's parser hands back dicts
    without open/close/high/low. Group ticks into `period`-sized buckets.
    """
    buckets: dict[int, dict] = {}
    for t in ticks:
        if not isinstance(t, dict):
            continue
        try:
            ts = float(t['time'])
            price = float(t['price'])
        except (KeyError, TypeError, ValueError):
            continue
        bucket = int(ts // period) * period
        b = buckets.get(bucket)
        if b is None:
            buckets[bucket] = {
                "time": bucket, "open": price, "high": price,
                "low": price, "close": price, "volume": 1,
            }
            continue
        b["high"] = max(b["high"], price)
        b["low"] = min(b["low"], price)
        b["close"] = price
        b["volume"] += 1
    return list(buckets.values())


async def fetch_candles(client, token: str, count: int = 18000, timeframe: int = 60) -> list | None:
    try:
        amount = max(count, 3600)
        candles = await client.get_historical_candles(
            asset=token,
            amount_of_seconds=amount,
            period=timeframe,
            timeout=30,
            max_workers=3,
        )
        if not candles:
            return None
        if isinstance(candles[0], dict) and "open" not in candles[0]:
            candles = _ticks_to_candles(candles, timeframe)
            if not candles:
                return None
        return [{"time": int(c['time']), "open": float(c['open']), "close": float(c['close']),
                 "high": float(c['high']), "low": float(c['low']), "volume": float(c.get('volume', 0))}
                for c in candles]
    except Exception as e:
        logger.error(f"fetch_candles failed for {token}: {e}")
        return None


async def _get_instruments(client) -> list:
    instruments = await client.get_instruments()
    if not instruments:
        return []
    if isinstance(instruments, dict) and 'name' in instruments:
        return [instruments]
    if isinstance(instruments, list):
        return instruments
    return []


def _get_sym(item) -> tuple[str, int, str]:
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


# ─── ACTIVE TIMEFRAME DISCOVERY ──────────────────────────────────────

def format_timeframe_label(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    mins = seconds / 60
    if mins.is_integer():
        m = int(mins)
        if m < 60:
            return f"{m}m"
        h = m / 60
        if h.is_integer() and m % 60 == 0:
            hr = int(h)
            if hr < 24:
                return f"{hr}h"
            d = hr / 24
            if hr % 24 == 0:
                return f"{int(d)}d"
        return f"{m}m"
    hours = mins / 60
    return f"{hours:g}h"


def _parse_timeframes_from_item(item) -> list[int] | None:
    """Extract active timeframes from a raw instrument row.

    Quotex embeds per-asset active timeframes in the raw instruments data:
    row[12] is a list of [period, "put"/"call"] pairs and is the ONLY
    authoritative source. row[15] is per-timeframe payout info (price 0 means
    the timeframe is NOT available) and always lists every period, so it must
    NOT be merged in, otherwise inactive timeframes leak into the menu.
    """
    tfs = []
    if isinstance(item, dict):
        for key in ("timeframes", "available_timeframes", "active_timeframes"):
            raw = item.get(key)
            if not isinstance(raw, list):
                continue
            for x in raw:
                if isinstance(x, (list, tuple)) and x:
                    try:
                        tfs.append(int(x[0]))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(x, dict) and x.get("time") is not None:
                    try:
                        tfs.append(int(x["time"]))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(x, (int, str)):
                    try:
                        tfs.append(int(x))
                    except (ValueError, TypeError):
                        pass
            break
        return sorted(set(tfs)) if tfs else None

    if isinstance(item, (list, tuple)):
        if len(item) > 12 and isinstance(item[12], list):
            for x in item[12]:
                if isinstance(x, (list, tuple)) and x:
                    try:
                        tfs.append(int(x[0]))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(x, (int, str)):
                    try:
                        tfs.append(int(x))
                    except (ValueError, TypeError):
                        pass
        return sorted(set(tfs)) if tfs else None
    return None


async def _load_timeframe_index(client) -> dict:
    """Cache {pair: [active_timeframes]} parsed from raw instruments."""
    now = time.time()
    if _instruments_tf_index["data"] and now - _instruments_tf_index["ts"] < _INSTRUMENTS_INDEX_TTL:
        return _instruments_tf_index["data"]
    try:
        instruments = await _get_instruments(client)
    except Exception as e:
        logger.warning(f"Failed to load instruments for timeframe index: {e}")
        return _instruments_tf_index["data"]

    index = {}
    for item in instruments:
        sym, _, _ = _get_sym(item)
        if not sym:
            continue
        tfs = _parse_timeframes_from_item(item)
        if tfs:
            index[sym] = tfs
    if index:
        _instruments_tf_index["data"] = index
        _instruments_tf_index["ts"] = now
    return index


async def _probe_timeframes(client, pair: str) -> list[int]:
    """Fallback: request a tiny candle batch per timeframe sequentially.

    pyquotex shares the candles_ready_{asset} event per asset, so parallel
    probes on the same asset would race — this runs sequentially. Only used
    when the raw instrument rows carry no timeframe data.
    """
    active = []
    for tf in SUPPORTED_TIMEFRAMES:
        try:
            candles = await client.get_candles(
                asset=pair,
                end_from_time=None,
                offset=tf * 10,
                period=tf,
                timeout=5,
            )
            if candles:
                active.append(tf)
        except Exception as e:
            logger.debug(f"Probe {pair} @ {tf}s failed: {e}")
    return active


def clear_timeframe_cache():
    _TIMEFRAME_CACHE.clear()
    _instruments_tf_index["data"] = {}
    _instruments_tf_index["ts"] = 0.0


async def get_asset_timeframes(client, pair: str) -> list[int]:
    """Return the active timeframes Quotex has for a pair.

    Primary: parse them straight from the raw instruments data (no extra
    requests, instant). Fallback: probe each master timeframe with a tiny
    candle request. Result is cached per pair for _TIMEFRAME_CACHE_TTL.
    """
    now = time.time()
    cached = _TIMEFRAME_CACHE.get(pair)
    if cached and now - cached.get("ts", 0) < _TIMEFRAME_CACHE_TTL:
        return cached["tfs"]

    tfs = []
    try:
        index = await _load_timeframe_index(client)
        tfs = index.get(pair, [])
    except Exception as e:
        logger.warning(f"Timeframe index lookup failed for {pair}: {e}")

    if not tfs:
        logger.info(f"No timeframe metadata for {pair}; falling back to probe")
        tfs = await _probe_timeframes(client, pair)

    if not tfs:
        tfs = [60]

    _TIMEFRAME_CACHE[pair] = {"tfs": tfs, "ts": now}
    return tfs
