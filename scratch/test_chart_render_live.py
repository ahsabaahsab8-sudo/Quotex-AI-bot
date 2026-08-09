# -*- coding: utf-8 -*-
"""Live test: fetch candles via adapter + render chart PNG -> base64."""
import asyncio
import sys, os

sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")

from dotenv import load_dotenv
load_dotenv(r"C:\Users\PC\Desktop\Quotex Signal\.env")

import chart_render
from quotex_adapter import get_quotex_connection, close_quotex_connection, fetch_candles


async def main():
    pair = "EURUSD_otc"
    client = await get_quotex_connection()
    print("connected:", client is not None, flush=True)
    candles = await fetch_candles(client, pair, count=60 * 120, timeframe=60)
    await close_quotex_connection()
    print("candles:", len(candles) if candles else 0, flush=True)
    if not candles:
        print("FAIL: no candles", flush=True)
        return
    print("sample candle:", candles[-1], flush=True)

    png = chart_render.render_chart_to_png(candles, summary=None, token=pair, timeframe=60)
    print("png bytes:", len(png) if png else 0, flush=True)
    if not png:
        print("FAIL: render returned None", flush=True)
        return
    out = r"C:\Users\PC\Desktop\Quotex Signal\scratch\test_render_chart.png"
    with open(out, "wb") as f:
        f.write(png)
    print("saved:", out, flush=True)

    b64 = chart_render.render_chart_to_base64(candles, summary=None, token=pair, timeframe=60)
    print("b64 chars:", len(b64) if b64 else 0, flush=True)


asyncio.run(main())
