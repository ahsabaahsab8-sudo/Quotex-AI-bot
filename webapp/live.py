"""Live chart websocket manager.

Streams real-time Quotex candle data through a shared pyquotex connection and
fans it out to any number of subscribed web clients. Uses the same single SSID
connection as the signal worker (via bot_main.get_quotex_connection) so there is
only ever one Quotex identity.

Client protocol (JSON lines):
  -> {"type":"subscribe","asset":"EURUSD_otc","timeframe":60}
  -> {"type":"unsubscribe"}
  <- {"type":"candles","asset":...,"timeframe":...,"candles":[...OHLC...]}
  <- {"type":"tick","asset":...,"price":...,"time":...}
  <- {"type":"status","connected":bool,"msg":...}
"""
import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class LiveChartManager:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._jobs: dict[str, asyncio.Task] = {}     # "asset|tf" -> stream task
        self._subscribers: dict[str, list] = defaultdict(list)  # key -> [ws]

    async def handle(self, ws, user_id: int):
        key = None
        while True:
            raw = await ws.receive_json()
            msg_type = raw.get("type")
            if msg_type == "subscribe":
                asset = raw.get("asset", "")
                tf = int(raw.get("timeframe", 60))
                if not asset or asset not in _VALID_ASSETS():
                    await ws.send_json({"type": "status", "connected": False, "msg": "Invalid asset"})
                    continue
                new_key = f"{asset}|{tf}"
                if key and key != new_key:
                    if ws in self._subscribers.get(key, []):
                        self._subscribers[key].remove(ws)
                key = new_key
                if ws not in self._subscribers[key]:
                    self._subscribers[key].append(ws)
                self._ensure_stream(key, asset, tf)
                await ws.send_json({"type": "status", "connected": True,
                                    "msg": f"Subscribed {asset} @ {tf}s"})
            elif msg_type == "unsubscribe":
                if key and ws in self._subscribers.get(key, []):
                    self._subscribers[key].remove(ws)
                    key = None
            else:
                await ws.send_json({"type": "status", "connected": False, "msg": "Unknown message"})
            # cleanup handled on disconnect

    def _ensure_stream(self, key: str, asset: str, tf: int):
        if key in self._jobs and not self._jobs[key].done():
            return
        self._jobs[key] = asyncio.create_task(self._stream(key, asset, tf))
        logger.info("Live stream started: %s", key)

    async def _stream(self, key: str, asset: str, tf: int):
        client = None
        last_price = None
        try:
            import main as bot_main
            client = await bot_main.get_quotex_connection()
            candles = await bot_main.adapter_fetch_candles(client, asset, count=max(tf * 30, 3600), timeframe=tf)
            if candles:
                await self._send(key, {"type": "candles", "asset": asset, "timeframe": tf,
                                       "candles": candles[-500:]})
            while True:
                await asyncio.sleep(1.0)
                if not self._subscribers.get(key):
                    break
                try:
                    ticks = await asyncio.wait_for(
                        client.get_realtime_price(asset), timeout=4.0
                    )
                    if ticks:
                        last = ticks[-1]
                        price = float(last.get("price", last.get("close", 0)))
                        ts = int(float(last.get("time", time.time())))
                        if price > 0 and (last_price is None or price != last_price):
                            last_price = price
                            await self._send(key, {"type": "tick", "asset": asset,
                                                   "price": price, "time": ts, "timeframe": tf})
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.debug("live tick error: %s", e)
        except Exception as e:
            logger.warning("Live stream %s failed: %s", key, e)
            await self._send(key, {"type": "status", "connected": False, "msg": str(e)[:200]})
        finally:
            try:
                if client is not None:
                    await bot_main.close_quotex_connection()
            except Exception:
                pass
            self._subscribers.pop(key, None)
            self._jobs.pop(key, None)
            logger.info("Live stream ended: %s", key)

    async def _send(self, key: str, payload: dict):
        dead = []
        for ws in list(self._subscribers.get(key, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            listeners = self._subscribers.get(key, [])
            if ws in listeners:
                listeners.remove(ws)

    async def shutdown(self):
        for task in list(self._jobs.values()):
            task.cancel()
        self._jobs.clear()
        self._subscribers.clear()


_VALID_CACHE = []


def _VALID_ASSETS():
    """Small static allow-list fallback so the WS can reject garbage before
    touching Quotex. Real validation is runtime (Quotex ignores unknown assets)."""
    base = [
        "EURUSD", "EURUSD_otc", "GBPUSD", "GBPUSD_otc", "USDJPY", "USDJPY_otc",
        "USDCHF", "USDCHF_otc", "USDCAD", "USDCAD_otc", "AUDUSD", "AUDUSD_otc",
        "NZDUSD", "NZDUSD_otc", "EURJPY", "EURJPY_otc", "EURGBP", "EURGBP_otc",
        "AUDCAD", "AUDCAD_otc", "GBPJPY", "GBPJPY_otc", "USDARS_otc", "USDEGP_otc",
        # crypto (Quotex code-style: base + "_otc")
        "BTCUSD_otc", "BTCUSD", "ETHUSD_otc", "ETHUSD", "SOLUSD_otc", "SOLUSD",
        "LINUSD_otc", "LINUSD", "XRPUSD_otc", "XRPUSD", "DOGEUSD_otc", "DOGEUSD",
        "BCHUSD_otc", "BCHUSD", "LTCUSD_otc", "LTCUSD", "AVAUSD_otc", "TONUSD_otc",
        "LUNUSD_otc", "DASHUSD_otc", "ZECUSD_otc", "MATUSD_otc", "TRXUSD_otc",
        "UKBrent_otc", "USCrude_otc", "XAGUSD_otc", "XAUUSD_otc",
    ]
    # also accept anything matching <6 letters>[_otc] known pattern
    return base