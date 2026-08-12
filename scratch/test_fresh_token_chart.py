# -*- coding: utf-8 -*-
"""Test the freshly renewed SSID with the working bundled pyquotex (QuotexChart)
on host market-qx.trade, fetch live candles, render chart PNG (same as test_render_chart.png)."""
import asyncio
import sys, os, json, base64

sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal\QuotexChart")
sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")

from pyquotex.stable_api import Quotex
import chart_render

EMAIL = "slamismail8@gmail.com"

def get_fresh_token():
    with open(os.path.join(r"C:\Users\PC\Desktop\Quotex Signal", "session.json")) as f:
        data = json.load(f)
    return data.get(EMAIL, {}).get("token")

async def main():
    token = get_fresh_token()
    print("fresh token:", (token or "")[:15] + "...", flush=True)
    c = Quotex(email=EMAIL, password="BaconBacon2019!", host="market-qx.trade", lang="en")
    c.set_session(
        user_agent=c.session_data.get("user_agent") or "Mozilla/5.0",
        cookies=None, ssid=token,
    )
    ok, reason = await c.connect()
    print("connect:", ok, reason, flush=True)
    if not ok:
        print("FAIL: connection", flush=True)
        return

    candles = await c.get_candles("EURUSD_otc", None, 3600, 60)
    print("candles:", len(candles) if candles else 0, flush=True)
    if not candles:
        print("FAIL: no candles", flush=True)
        await c.close()
        return
    print("sample:", candles[-1], flush=True)

    norm = [{"time": int(x["time"]), "open": float(x["open"]), "close": float(x["close"]),
             "high": float(x["high"]), "low": float(x["low"]), "volume": float(x.get("volume", 0))}
            for x in candles]

    png = chart_render.render_chart_to_png(norm, summary=None, token="EURUSD_otc", timeframe=60)
    print("png bytes:", len(png) if png else 0, flush=True)
    if not png:
        print("FAIL: render None", flush=True)
        await c.close()
        return
    out = r"C:\Users\PC\Desktop\Quotex Signal\scratch\bot_chart_live.png"
    with open(out, "wb") as f:
        f.write(png)
    print("saved:", out, flush=True)
    b64 = chart_render.render_chart_to_base64(norm, summary=None, token="EURUSD_otc", timeframe=60)
    print("b64 chars:", len(b64) if b64 else 0, flush=True)
    await c.close()

asyncio.run(main())
